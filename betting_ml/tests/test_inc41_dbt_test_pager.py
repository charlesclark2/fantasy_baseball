"""INC-41 — guards for the dbt-test pager (page when a SERVING-CRITICAL dbt test goes red).

WHAT THESE PROVE, and why each layer is here.

    In INC-41 the dbt test WORKED — it went red on the nulled odds price — and nobody was
    notified, because the daily test step is WARN-tier by design (INC-6) and its failure is
    caught, logged, and left to surface days later in CI. A pager for that is only worth having
    if it fires on the right failures and STAYS SILENT on the rest, so the suite is a two-sided
    RED proof:

      • a `severity: error` (serving-critical) failure  -> pages CRITICAL
      • a `severity: warn` (peripheral) failure         -> SILENT
      • a clean suite                                   -> SILENT
      • results missing / unreadable                    -> WARN, never scored healthy (NF1.7 (a))
      • a `severity: warn` test that ERRORED            -> SILENT  ← the false-page guard

    That last case is the one this module exists for. Measured against dbt-fusion, a test that
    cannot EXECUTE reports `status: "error"` whatever its configured severity, so a status-keyed
    pager would page CRITICAL every time a PERIPHERAL test broke — the alert fatigue that gets a
    monitor muted (E11.27). Only the manifest's configured severity separates the two.

⭐ THE FIXTURES ARE REAL dbt-fusion OUTPUT, NOT HAND-WRITTEN JSON.
    Every `run_results.json` under `fixtures/inc41_dbt_run_results/` was produced by running the
    real `dbt build` (dbt-fusion 2.0.0-preview.204) against a throwaway DuckDB project whose
    schema mirrors this repo's own contract split — a serving-critical `not_null` at
    `severity: error` beside a peripheral `unique` at `severity: warn`. The generator is
    `docs/inc41_dbt_test_pager.md`. This matters: a hand-authored fixture encodes the test
    author's BELIEF about dbt's output format, so the suite would stay green if that belief were
    wrong — which is the NF-C0e lesson (a test that reads a value back under the key the code
    wrote can never catch a wrong key) and the reason `status: "error"` on a warn-severity test
    was found at all. `manifest_severities.json` is a real extract of the real manifest, keeping
    fusion's genuine UPPERCASE severity values.

Fast-gate-safe: imports `pipeline` ONLY in the classes guarded on the dbt manifest (E11.23).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

import pytest

from betting_ml.monitoring.dbt_test_results import (
    DEFAULT_SEVERITY,
    SEVERITY_ERROR,
    SEVERITY_UNKNOWN,
    SEVERITY_WARN,
    STATE_CLEAN,
    STATE_FAILURES,
    STATE_NOT_RUN,
    STATE_UNAVAILABLE,
    classify,
    dedup_key,
    load_severity_map,
    normalise_severity,
    page_decision,
    render,
)

_REPO = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "inc41_dbt_run_results"

SCENARIOS = ("all_pass", "error_severity_failure", "warn_severity_failure",
             "warn_severity_errored")


def _fixture(scenario: str) -> tuple[dict, dict[str, str]]:
    """Return (captured payload, severity map) for a real dbt-fusion fixture."""
    run_results = json.loads((_FIXTURES / scenario / "run_results.json").read_text())
    severities = load_severity_map(str(_FIXTURES / scenario / "manifest_severities.json"))
    payload = {
        "available": True,
        "tested": True,
        "provenance": {"command": "build", "generated_at": "2026-08-07T00:00:00Z"},
        "run_results": run_results,
    }
    return payload, severities


class TestTheFixturesAreRealDbtOutput:
    """If these drift, every verdict below is asserting against something dbt never emits."""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_every_scenario_has_both_artifacts(self, scenario):
        assert (_FIXTURES / scenario / "run_results.json").exists()
        assert (_FIXTURES / scenario / "manifest_severities.json").exists()

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_run_results_has_the_shape_the_parser_relies_on(self, scenario):
        rr = json.loads((_FIXTURES / scenario / "run_results.json").read_text())
        assert isinstance(rr["results"], list) and rr["results"]
        assert rr["metadata"]["generated_at"]
        assert rr["args"]["command"] == "build"

    def test_fusion_writes_severity_uppercase(self):
        """The case-normalisation in `normalise_severity` is load-bearing, not cosmetic: fusion
        stores "ERROR"/"WARN" while dbt-core stores lowercase. A verbatim comparison would
        classify every test as unresolvable — the silent-NULL class this repo hits through
        Snowflake `VALUE:` case-sensitivity."""
        raw = json.loads((_FIXTURES / "all_pass" / "manifest_severities.json").read_text())
        stored = {n["config"]["severity"] for n in raw["nodes"].values()}
        assert stored == {"ERROR", "WARN"}, f"fusion severity casing changed: {stored}"


class TestTheAcceptanceCriteria:
    """The four AC states, each read off a REAL dbt-fusion artifact."""

    def test_error_severity_failure_pages_critical(self):
        """The INC-41 shape: a serving-critical contract goes red on a nulled price."""
        payload, severities = _fixture("error_severity_failure")
        verdict = classify(payload, severities)

        assert verdict.state == STATE_FAILURES
        assert [f.name for f in verdict.error_severity] == ["not_null_served_prices_price"]
        assert verdict.warn_severity == ()

        severity, message = page_decision(verdict)
        assert severity == "CRITICAL"
        assert "not_null_served_prices_price" in message

    def test_warn_severity_failure_is_silent(self):
        """A peripheral data-quality check going red must NOT page — that is the entire point of
        the severity split, and paging here is what would get this monitor muted."""
        payload, severities = _fixture("warn_severity_failure")
        verdict = classify(payload, severities)

        assert [f.name for f in verdict.warn_severity] == ["unique_served_prices_price"]
        assert verdict.error_severity == ()
        assert page_decision(verdict)[0] is None

    def test_a_clean_suite_is_silent(self):
        payload, severities = _fixture("all_pass")
        verdict = classify(payload, severities)

        assert verdict.state == STATE_CLEAN
        assert verdict.tests_total == 2 and verdict.tests_passed == 2
        assert page_decision(verdict)[0] is None

    def test_missing_results_page_warn_and_are_never_scored_healthy(self):
        """A check that did not run is not a pass (NF1.7 (a)) — but it is not CRITICAL either."""
        verdict = classify({"available": False, "tested": True,
                            "reason": "dbt-runner has no run_results for run abc123"})

        assert verdict.state == STATE_UNAVAILABLE
        severity, message = page_decision(verdict)
        assert severity == "WARN"
        assert "UNVERIFIED" in message
        assert "NOT a clean bill of health" in message

    def test_an_unparseable_artifact_is_unavailable_not_clean(self):
        for junk in ({"available": True, "run_results": {"results": "not-a-list"}},
                     {"available": True, "run_results": None},
                     "not-a-dict",
                     None):
            assert classify(junk).state == STATE_UNAVAILABLE, junk
            assert page_decision(classify(junk))[0] == "WARN"


class TestTheFalsePageGuard:
    """THE case this module exists for — see the module docstring."""

    def test_a_warn_severity_test_that_errored_does_not_page(self):
        """`status: "error"` is severity-INDEPENDENT: it means the test could not execute. A
        peripheral test broken by a renamed column must not wake anyone."""
        payload, severities = _fixture("warn_severity_errored")
        verdict = classify(payload, severities)

        broken = [f for f in verdict.warn_severity if f.name == "peripheral_broken"]
        assert broken, f"expected the errored warn test in the warn bucket: {verdict}"
        assert broken[0].status == "error" and broken[0].could_not_execute
        assert verdict.error_severity == ()
        assert page_decision(verdict)[0] is None

    def test_but_an_error_severity_test_that_errored_DOES_page(self):
        """The other side: a serving-critical contract that cannot be EVALUATED is not passing.
        Same status, opposite verdict — proving severity, not status, is doing the work."""
        payload, _ = _fixture("warn_severity_errored")
        promoted = {"test.credence_fixture.peripheral_broken": SEVERITY_ERROR}
        verdict = classify(payload, promoted)

        assert [f.name for f in verdict.error_severity] == ["peripheral_broken"]
        severity, message = page_decision(verdict)
        assert severity == "CRITICAL"
        assert "COULD NOT EXECUTE" in message

    def test_status_alone_cannot_separate_the_two_cases(self):
        """Proves the premise: both fixtures' broken test carries the IDENTICAL status, so any
        status-keyed pager necessarily gets one of the two wrong."""
        payload, _ = _fixture("warn_severity_errored")
        statuses = {r["status"] for r in payload["run_results"]["results"]
                    if r["unique_id"].endswith("peripheral_broken")}
        assert statuses == {"error"}


class TestSeverityResolution:
    def test_uppercase_and_lowercase_both_normalise(self):
        assert normalise_severity("WARN") == SEVERITY_WARN
        assert normalise_severity("warn") == SEVERITY_WARN
        assert normalise_severity("ERROR") == SEVERITY_ERROR

    def test_absent_severity_defaults_to_error_like_dbt_itself(self):
        """dbt's own default is `error`, so a contract that declares nothing IS serving-critical.
        Defaulting to WARN here would silently un-page most of the project."""
        assert normalise_severity(None) == DEFAULT_SEVERITY == SEVERITY_ERROR

    def test_an_unreadable_manifest_yields_an_empty_map_not_a_crash(self):
        assert load_severity_map("/nonexistent/manifest.json") == {}
        assert load_severity_map(None) == {}

    def test_without_a_manifest_a_fail_status_still_pages(self):
        """`fail` is emitted ONLY for an error-severity test (measured), so inferring ERROR from
        it is safe and keeps the pager working if the manifest is ever unavailable."""
        payload, _ = _fixture("error_severity_failure")
        verdict = classify(payload, severity_map={})
        assert [f.name for f in verdict.error_severity] == ["not_null_served_prices_price"]
        assert page_decision(verdict)[0] == "CRITICAL"

    def test_without_a_manifest_an_error_status_is_UNKNOWN_and_pages_only_warn(self):
        """`error` is severity-independent, so it must NEVER be inferred as serving-critical.
        Unresolvable is reported honestly at WARN — neither silently dropped nor promoted."""
        payload, _ = _fixture("warn_severity_errored")
        verdict = classify(payload, severity_map={})

        assert [f.name for f in verdict.unknown_severity] == ["peripheral_broken"]
        assert verdict.error_severity == ()
        severity, message = page_decision(verdict)
        assert severity == "WARN"
        assert "UNRESOLVED" in message

    def test_a_warn_status_is_never_inferred_as_pageable(self):
        payload, _ = _fixture("warn_severity_failure")
        verdict = classify(payload, severity_map={})
        assert verdict.error_severity == ()
        assert page_decision(verdict)[0] is None


class TestNotRunIsSilentButUnavailableIsNot:
    """The distinction that keeps this pager quiet enough to be trusted.

    `dbt_daily_build` runs the full suite only on build days (Sunday + every 3rd midweek). If a
    day with no test suite were reported as "unverified", this would WARN on a routine cadence
    and train the operator to ignore it — the same carve-out `artifact_freshness` makes for a
    writer's declared inactive hours. UNAVAILABLE (the suite ran, results unreadable) is the
    genuinely unverified state and stays WARN."""

    def test_no_suite_ran_is_silent(self):
        verdict = classify({"available": False, "tested": False,
                            "reason": "this dbt invocation ran no test suite"})
        assert verdict.state == STATE_NOT_RUN
        assert page_decision(verdict)[0] is None

    def test_a_selection_containing_no_tests_is_silent(self):
        """A `source_status:fresher+` build that selected only views measured nothing — and
        nothing was expected of it."""
        verdict = classify({"available": True, "run_results": {
            "results": [{"unique_id": "model.credence.some_view", "status": "success"}]}})
        assert verdict.state == STATE_NOT_RUN
        assert page_decision(verdict)[0] is None

    def test_the_two_states_are_not_conflated(self):
        not_run = classify({"available": False, "tested": False, "reason": "x"})
        unavailable = classify({"available": False, "tested": True, "reason": "x"})
        assert not_run.state != unavailable.state
        assert page_decision(not_run)[0] is None
        assert page_decision(unavailable)[0] == "WARN"


class TestModelResultsAreNotMistakenForTests:
    def test_a_failing_model_is_ignored_here(self):
        """Model failures are the `run` step's business and it is HALT-tier — it already stopped
        the job. Counting them here would double-page on something predictions already gated on."""
        verdict = classify({"available": True, "run_results": {"results": [
            {"unique_id": "model.credence.broken", "status": "error"},
            {"unique_id": "test.credence.some_check.abc", "status": "pass"},
        ]}}, {"test.credence.some_check.abc": SEVERITY_ERROR})
        assert verdict.error_severity == ()
        assert verdict.tests_total == 1 and verdict.tests_passed == 1
        assert page_decision(verdict)[0] is None


class TestDedupKeyCarriesTheAffectedSet:
    """send_alert rate-limits per key for an hour. A constant key would let an ongoing failure on
    contract A swallow the FIRST page for a new failure on contract B — the INC-39 "a smoke test
    ate the real alert's slot" hazard arriving by a different road."""

    def _verdict_for(self, names):
        return classify({"available": True, "run_results": {"results": [
            {"unique_id": f"test.credence.{n}.abc", "status": "fail", "failures": 1}
            for n in names]}}, {f"test.credence.{n}.abc": SEVERITY_ERROR for n in names})

    def test_a_different_failing_set_yields_a_different_key(self):
        assert dedup_key(self._verdict_for(["a"])) != dedup_key(self._verdict_for(["a", "b"]))

    def test_the_same_set_is_stable_regardless_of_order(self):
        assert dedup_key(self._verdict_for(["a", "b"])) == dedup_key(self._verdict_for(["b", "a"]))

    def test_the_key_stays_bounded_for_a_large_failing_set(self):
        key = dedup_key(self._verdict_for([f"contract_number_{i:03d}" for i in range(80)]))
        assert len(key) < 256
        # still set-sensitive after truncation
        other = dedup_key(self._verdict_for([f"contract_number_{i:03d}" for i in range(81)]))
        assert key != other


# ── the pipeline-side plumbing (needs the dbt manifest to import `pipeline`) ─────────────────

_MANIFEST = _REPO / "dbt" / "target" / "manifest.json"
requires_pipeline = pytest.mark.skipif(
    not _MANIFEST.exists(), reason="needs the dbt manifest to import `pipeline` (E11.23)"
)


@requires_pipeline
class TestProvenanceRejectsAStaleArtifact:
    """dbt overwrites target/run_results.json on every invocation, so "the file on disk" is not
    "this run's results". Both of these would otherwise be reported as a CLEAN suite."""

    def test_a_run_step_artifact_cannot_certify_the_test_suite(self):
        """`dbt run` executes no tests, so its run_results contains zero test nodes — "0 failures"
        from a command that tested nothing is the most dangerous possible false green."""
        from pipeline.ops._dbt_exec import _verify_provenance
        _, reason = _verify_provenance(
            {"args": {"command": "run"}, "metadata": {"generated_at": "2026-08-07T00:00:00Z"}},
            started_at=time.time())
        assert "executes no tests" in reason

    def test_an_artifact_generated_before_this_invocation_is_rejected(self):
        from pipeline.ops._dbt_exec import _verify_provenance
        _, reason = _verify_provenance(
            {"args": {"command": "test"}, "metadata": {"generated_at": "2020-01-01T00:00:00Z"}},
            started_at=time.time())
        assert "stale artifact" in reason

    def test_a_genuine_test_artifact_passes(self):
        from pipeline.ops._dbt_exec import _verify_provenance
        prov, reason = _verify_provenance(
            {"args": {"command": "test"},
             "metadata": {"generated_at": "2026-08-07T00:00:00Z", "invocation_id": "xyz"}},
            started_at=0.0)
        assert reason == ""
        assert prov["command"] == "test" and prov["invocation_id"] == "xyz"

    def test_a_rejected_artifact_reaches_the_pager_as_UNAVAILABLE_not_clean(self):
        """End of the chain: a stale artifact must surface as a WARN page, never as silence."""
        verdict = classify({"available": False, "tested": True,
                            "reason": "the captured run_results is from a `dbt run` invocation"})
        assert page_decision(verdict)[0] == "WARN"


@requires_pipeline
class TestTheOpExecutesEndToEnd:
    """The INC-39 lesson: one test must exercise the REAL leg. Here that is the real
    `capture_dbt_results` write -> the real `load_dbt_results` read -> the real classifier ->
    the real op, running in a real Dagster job. Only the dbt-runner HTTP call and SNS are stubbed,
    so nothing between them is a string a test author wrote."""

    def _run(self, monkeypatch, scenario, http_status=200):
        """Capture a real artifact for a synthetic run id, then execute the real op over it."""
        from dagster import DagsterInstance, in_process_executor, job

        import pipeline.ops._dbt_exec as dbt_exec
        import pipeline.ops.daily_ingestion_ops as dio
        import pipeline.utils.alerting as alerting

        if scenario is not None:
            body = json.loads((_FIXTURES / scenario / "run_results.json").read_text())
            body["metadata"]["generated_at"] = (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z")
            manifest = str(_FIXTURES / scenario / "manifest_severities.json")
        else:
            body, manifest = None, str(_FIXTURES / "all_pass" / "manifest_severities.json")

        response = MagicMock()
        response.status_code = http_status
        response.json.return_value = body if body is not None else {}
        monkeypatch.setattr(dbt_exec.requests, "get", lambda *a, **k: response)

        real_join = dbt_exec.os.path.join
        monkeypatch.setattr(
            dio.os.path, "join",
            lambda *p: manifest if p[-1] == "manifest.json" else real_join(*p))

        mock_alert = MagicMock()
        monkeypatch.setattr(alerting, "send_alert", mock_alert)

        captured: dict = {}

        @dbt_exec_noop_op(captured)
        def _capture_op(context):
            # REAL capture: fetches through the (stubbed) runner, verifies provenance, persists.
            dbt_exec.capture_dbt_results(
                context, {"run_id": "abc123", "runner_url": "http://dbt-runner:8080"},
                started_at=0.0)

        @job(executor_def=in_process_executor)
        def _j():
            dio.check_dbt_test_results_op(start=_capture_op())

        result = _j.execute_in_process(instance=DagsterInstance.ephemeral())
        assert result.success, "the pager must never fail the job — it is ALERT-tier"
        return mock_alert

    def test_a_red_serving_contract_pages_critical(self, monkeypatch):
        alert = self._run(monkeypatch, "error_severity_failure")
        alert.assert_called_once()
        assert alert.call_args.kwargs["severity"] == "CRITICAL"
        assert "not_null_served_prices_price" in alert.call_args.args[1]

    def test_a_peripheral_failure_never_pages(self, monkeypatch):
        self._run(monkeypatch, "warn_severity_failure").assert_not_called()

    def test_an_errored_peripheral_test_never_pages(self, monkeypatch):
        self._run(monkeypatch, "warn_severity_errored").assert_not_called()

    def test_a_clean_suite_never_pages(self, monkeypatch):
        self._run(monkeypatch, "all_pass").assert_not_called()

    def test_an_unreachable_runner_pages_warn_and_the_op_still_succeeds(self, monkeypatch):
        alert = self._run(monkeypatch, None, http_status=404)
        alert.assert_called_once()
        assert alert.call_args.kwargs["severity"] == "WARN"


def dbt_exec_noop_op(_captured):
    """Build the upstream capture op's decorator (defined at module scope so Dagster sees a
    plain function, not a bound method)."""
    from dagster import Nothing, Out, op
    return lambda fn: op(name="_inc41_capture", out=Out(Nothing))(fn)


@requires_pipeline
class TestTheRunnerServesTheArtifactItCaptured:
    """The dbt-runner is a SEPARATE container with no shared volume, so without this endpoint the
    op would read a `target/run_results.json` that is not the daily suite's output — silently
    stale forever. Capture happens at run time, not request time, so a later dbt invocation
    cannot overwrite what a given run_id returns."""

    def _server(self, tmp_path, monkeypatch):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_inc41_dbt_runner", _REPO / "services" / "dbt_runner" / "server.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        target = tmp_path / "target"
        target.mkdir()
        monkeypatch.setattr(mod, "_DBT_PROJECT_DIR", str(tmp_path))
        # The module reads DBT_RUNNER_AUTH_TOKEN at import, so it inherits whatever the developer
        # has exported. Clear it here so these tests exercise the ARTIFACT plumbing; auth has its
        # own test below.
        monkeypatch.setattr(mod, "_AUTH_TOKEN", "")
        return mod, target

    def test_the_endpoint_requires_the_bearer_token(self, tmp_path, monkeypatch):
        """It serves internal build output over the compose network — same auth as /run, /status."""
        from fastapi import HTTPException
        mod, target = self._server(tmp_path, monkeypatch)
        monkeypatch.setattr(mod, "_AUTH_TOKEN", "s3cret")
        (target / "run_results.json").write_text(
            (_FIXTURES / "all_pass" / "run_results.json").read_text())
        mod._runs["run0"] = {"status": "success"}
        mod._capture_run_results("run0")

        with pytest.raises(HTTPException) as exc:
            mod.get_run_results("run0", authorization=None)
        assert exc.value.status_code == 401
        # …and succeeds with it.
        assert mod.get_run_results("run0", authorization="Bearer s3cret")["results"]

    def test_capture_then_serve_round_trips_the_real_artifact(self, tmp_path, monkeypatch):
        mod, target = self._server(tmp_path, monkeypatch)
        real = (_FIXTURES / "error_severity_failure" / "run_results.json").read_text()
        (target / "run_results.json").write_text(real)

        mod._runs["run1"] = {"status": "success"}
        mod._capture_run_results("run1")

        assert mod.get_run_results("run1", authorization=None) == json.loads(real)

    def test_a_later_invocation_cannot_change_an_earlier_runs_results(self, tmp_path, monkeypatch):
        """The provenance guarantee: run1's slot keeps run1's artifact after run2 overwrites the
        file on disk. A read-at-request-time endpoint would hand back run2's results for run1."""
        mod, target = self._server(tmp_path, monkeypatch)
        (target / "run_results.json").write_text(
            (_FIXTURES / "error_severity_failure" / "run_results.json").read_text())
        mod._runs["run1"] = {"status": "failed"}
        mod._capture_run_results("run1")

        (target / "run_results.json").write_text(
            (_FIXTURES / "all_pass" / "run_results.json").read_text())
        mod._runs["run2"] = {"status": "success"}
        mod._capture_run_results("run2")

        run1_statuses = {r["status"] for r in mod.get_run_results("run1", None)["results"]
                         if r["unique_id"].startswith("test.")}
        assert "fail" in run1_statuses, "run1 must still report its own failure"

    def test_a_run_that_wrote_no_artifact_404s_rather_than_returning_empty(
            self, tmp_path, monkeypatch):
        """404 so the caller reports UNVERIFIED. Returning `{}` would classify as a clean suite."""
        from fastapi import HTTPException
        mod, _ = self._server(tmp_path, monkeypatch)
        mod._runs["run3"] = {"status": "success"}
        mod._capture_run_results("run3")  # no file on disk

        with pytest.raises(HTTPException) as exc:
            mod.get_run_results("run3", None)
        assert exc.value.status_code == 404

    def test_capture_never_raises_on_a_corrupt_artifact(self, tmp_path, monkeypatch):
        """Capture is observability only; it must never affect the HALT-tier dbt op."""
        mod, target = self._server(tmp_path, monkeypatch)
        (target / "run_results.json").write_text("{not json")
        mod._runs["run4"] = {"status": "success"}
        mod._capture_run_results("run4")  # must not raise
        assert "run4" not in mod._run_results

    def test_the_registry_is_bounded(self, tmp_path, monkeypatch):
        mod, target = self._server(tmp_path, monkeypatch)
        (target / "run_results.json").write_text(
            (_FIXTURES / "all_pass" / "run_results.json").read_text())
        for i in range(mod._RUN_RESULTS_KEEP + 10):
            mod._capture_run_results(f"r{i}")
        assert len(mod._run_results) <= mod._RUN_RESULTS_KEEP


@requires_pipeline
class TestInc6IsNotRegressed:
    """The pager must not become a gate. INC-6 (2026-06-21) had a peripheral test failure block
    every prediction; fixing INC-41 by making the test step blocking would be a bad trade."""

    def test_the_dbt_test_step_still_swallows_its_failure(self):
        """The `test` invocation must stay inside a try/except that only warns."""
        import inspect

        import pipeline.ops.daily_ingestion_ops as dio
        source = inspect.getsource(dio.dbt_daily_build)
        stripped = "\n".join(line for line in source.splitlines()
                             if not line.strip().startswith("#"))
        assert "context.log.warning(" in stripped
        assert "raise" not in stripped, "the dbt test step must never re-raise (INC-6)"

    @staticmethod
    def _upstreams_by_node() -> dict[str, list[str]]:
        """{node -> its upstream node names}, read off the COMPILED Dagster graph.

        Not the source order: `in_process_executor` runs topologically, so asserting on line
        order would be vacuous (the INC-40 lesson). An earlier draft of this test called a
        Dagster API that does not exist and fell back to an empty list — so it passed no matter
        how the graph was wired. Hence the positive control below: this helper must be PROVEN to
        find real edges before its empty result means anything (NF1.7 (a) / NF-D17)."""
        from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

        graph = daily_ingestion_job.graph
        deps = graph.dependency_structure
        return {
            node: sorted({h.node_name
                          for handles in deps.input_to_upstream_outputs_for_node(node).values()
                          for h in handles})
            for node in graph.node_dict
        }

    def test_the_dependency_probe_actually_finds_edges(self):
        """POSITIVE CONTROL. Without this, `dependents == []` below could mean "the pager is a
        leaf" OR "the probe sees nothing at all" — and those are not the same finding."""
        upstreams = self._upstreams_by_node()
        assert upstreams["check_dbt_test_results_op"] == ["dbt_daily_build"], \
            "the probe cannot even see the pager's OWN upstream edge"
        assert len([n for n, u in upstreams.items() if "dbt_daily_build" in u]) > 3

    def test_nothing_in_the_daily_job_depends_on_the_pager(self):
        """Structural proof it cannot withhold a slate: it is a leaf, exactly like
        settle_user_bets_op. A failure here could not block predictions even if it raised."""
        upstreams = self._upstreams_by_node()
        dependents = sorted(n for n, u in upstreams.items()
                            if "check_dbt_test_results_op" in u)
        assert dependents == [], f"the pager must be a leaf; depended on by {dependents}"

    def test_the_pager_op_does_not_re_run_dbt(self):
        """It reads the artifact the suite already produced. Re-running would double the suite
        and RESUME COMPUTE_WH — a new waker, on a warehouse where ~80% of the burn is wake/idle
        (E11.20-COST) and the E11.24 soak is live. Comments are stripped first, so the prose
        explaining this cannot itself satisfy the guard (the INC-38 lesson)."""
        import inspect

        import pipeline.ops.daily_ingestion_ops as dio
        source = inspect.getsource(dio.check_dbt_test_results_op)
        code = "\n".join(line for line in source.splitlines()
                         if not line.strip().startswith("#"))
        # drop the docstring
        if '"""' in code:
            head, _, rest = code.partition('"""')
            code = head + rest.partition('"""')[2]
        for forbidden in ("_run_dbt", "_run_script", "subprocess", "snowflake"):
            assert forbidden not in code, f"the pager must not call {forbidden}"
