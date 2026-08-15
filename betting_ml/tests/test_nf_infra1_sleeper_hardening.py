"""NF-INFRA1 — the Sleeper feed must FAIL LOUD, refuse a degraded land, and prove the artifact moved.

THE DEFECT (NF-FRESH1, 2026-08-15): `sports_nfl_sleeper_injuries_job` returned SUCCESS on 19
consecutive daily runs while `nfl/raw/sleeper_injuries` held ONE 19-day-old Delta commit. The op
died at `duckdb.connect(read_only=True)` in ~114ms and a bare `except Exception` reported it green.

THREE INDEPENDENT INVARIANTS, because the bug had three layers and fixing any one alone leaves it:
  1. a run that produced nothing must be RED — the op raises rather than swallowing;
  2. a DEGRADED land must be REFUSED, not written. The Delta write is a whole-PARTITION overwrite,
     so landing a crosswalk-less frame does not sit beside the good snapshot, it replaces it. The
     tempting "make the DuckDB optional and land native-gsis rows" was MEASURED at 16.7% of
     rostered / 22.1% of flagged and would drop 95 of 122 flagged players while reporting success —
     strictly worse than a loud break;
  3. the ARTIFACT is checked, not just the producer (INC-41) — the producer reported success for
     19 days; only the Delta log disagreed.

The decisions live in PURE functions (`classify_land`, `sports_delta_freshness.classify`) so they
are testable in the fast gate; the op is additionally read as SOURCE, because a Dagster-wiring test
skips when the dbt manifest is absent and a skipped test defends nothing.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from betting_ml.monitoring import sports_delta_freshness as SDF
from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI

_REPO = Path(__file__).resolve().parents[2]
_JOB = _REPO / "pipeline/jobs/sports_nfl_sleeper_injuries_job.py"

_HEALTHY = {"n_fetched": 2800, "n_resolved": 2499, "pct_resolved": 89.3,
            "n_native_gsis": 470, "n_crosswalk_resolved": 2029, "n_flagged": 122}


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1. classify_land — may this snapshot be written?
# ══════════════════════════════════════════════════════════════════════════════════════════
def test_a_healthy_land_is_written_silently():
    v = SI.classify_land(_HEALTHY)
    assert (v["verdict"], v["should_write"], v["severity"]) == ("OK", True, None)


def test_an_empty_feed_refuses_the_write_and_is_critical():
    """Zero skill-position players is an upstream outage or a changed payload shape — never a quiet
    day. Writing it would replace the good partition with nothing."""
    v = SI.classify_land({"n_fetched": 0, "n_resolved": 0, "pct_resolved": 0.0, "n_flagged": 0})
    assert v["verdict"] == "EMPTY_FEED"
    assert v["should_write"] is False
    assert v["severity"] == "CRITICAL"


def test_a_collapsed_crosswalk_refuses_the_write():
    """The measured native-only regime (16.7% of rostered / 22.1% of flagged). This is the land the
    story explicitly forbids: plausible-looking, 100%-matched after the drop, and missing most
    flagged players."""
    v = SI.classify_land({"n_fetched": 2800, "n_resolved": 468, "pct_resolved": 16.7,
                          "n_native_gsis": 468, "n_crosswalk_resolved": 0, "n_flagged": 27})
    assert v["verdict"] == "CROSSWALK_DEGRADED"
    assert v["should_write"] is False
    assert v["severity"] == "CRITICAL"


def test_resolving_nothing_at_all_refuses_the_write():
    v = SI.classify_land({"n_fetched": 2800, "n_resolved": 0, "pct_resolved": 0.0, "n_flagged": 0})
    assert v["verdict"] == "CROSSWALK_DEGRADED"
    assert v["should_write"] is False


def test_the_floor_separates_the_two_MEASURED_regimes_with_margin():
    """The floor is derived from the two regimes (native-only ~17-22%, crosswalked ~89-100%), not
    reverse-engineered from a run's answer (NF1.8). Both regimes must land on the correct side."""
    assert 22.1 < SI.DEFAULT_MIN_PCT_RESOLVED < 89.3


def test_a_zero_flagged_land_still_WRITES_but_reports_its_magnitude():
    """A quality warning, not an outage: refusing the write here would discard a real snapshot over
    a survivable signal. It must still be visible rather than silent."""
    v = SI.classify_land({**_HEALTHY, "n_flagged": 0})
    assert v["verdict"] == "PARTIAL"
    assert v["should_write"] is True
    assert v["severity"] == "WARN"


def test_every_refusal_names_the_magnitude_not_just_a_verdict():
    v = SI.classify_land({"n_fetched": 2800, "n_resolved": 468, "pct_resolved": 16.7,
                          "n_native_gsis": 468, "n_crosswalk_resolved": 0, "n_flagged": 27})
    assert "468" in v["reason"] and "2800" in v["reason"] and "16.7" in v["reason"]


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2. the coverage is measured BEFORE the unresolved-row drop
# ══════════════════════════════════════════════════════════════════════════════════════════
def _fetched(rows):
    return pd.DataFrame(rows, columns=["sleeper_player_id", "player_name", "position", "team",
                                       "gsis_id", "injury_status", "injury_body_part",
                                       "proj_status"])


def test_coverage_is_pre_drop_so_a_collapsed_crosswalk_is_VISIBLE(monkeypatch):
    """⭐ THE WHOLE POINT. `coverage()` on the LANDED frame reports 100% matched by construction —
    the drop already removed every unresolved row — so it cannot tell a healthy crosswalk from a
    dead one. Only `n_resolved / n_fetched` can."""
    fetched = _fetched([
        ("1", "A", "WR", "MIA", "00-1", None, None, None),      # native id
        ("2", "B", "RB", "KC", None, "PUP", "knee", "PUP"),     # needs the crosswalk
        ("3", "C", "TE", "SF", None, "IR", "back", "RES"),      # needs the crosswalk
        ("4", "D", "QB", "NYJ", None, None, None, None),        # never resolves
    ])
    monkeypatch.setattr(SI, "fetch_sleeper_players", lambda **kw: fetched.copy())
    # The crosswalk is DEAD: it resolves nothing, exactly as it would with no NFL marts built.
    monkeypatch.setattr(SI.A, "attach_gsis",
                        lambda con, df, season, schema="main_nfl_marts": df.assign(
                            player_id=pd.array([pd.NA] * len(df), dtype="string")))

    landed, cov = SI.load_sleeper_injuries_with_coverage(object(), 2026)

    assert cov["n_fetched"] == 4
    assert cov["n_resolved"] == 1            # the single native id
    assert cov["n_crosswalk_resolved"] == 0  # the tell
    assert cov["pct_resolved"] == 25.0
    # And the post-drop view — the one the old op logged — is a flattering 100%.
    assert SI.coverage(landed)["pct_matched"] == 100.0
    assert SI.classify_land(cov)["should_write"] is False


def test_a_healthy_crosswalk_is_attributed_to_the_crosswalk_not_to_native_ids(monkeypatch):
    fetched = _fetched([
        ("1", "A", "WR", "MIA", "00-1", None, None, None),
        ("2", "B", "RB", "KC", None, "PUP", "knee", "PUP"),
    ])
    monkeypatch.setattr(SI, "fetch_sleeper_players", lambda **kw: fetched.copy())
    monkeypatch.setattr(SI.A, "attach_gsis",
                        lambda con, df, season, schema="main_nfl_marts": df.assign(
                            player_id=pd.array(["00-2"] * len(df), dtype="string")))

    landed, cov = SI.load_sleeper_injuries_with_coverage(object(), 2026)
    assert (cov["n_resolved"], cov["n_native_gsis"], cov["n_crosswalk_resolved"]) == (2, 1, 1)
    assert cov["n_flagged"] == 1
    assert set(landed["season"]) == {2026}
    assert SI.classify_land(cov)["should_write"] is True


def test_an_empty_fetch_does_not_explode_and_refuses_the_land(monkeypatch):
    monkeypatch.setattr(SI, "fetch_sleeper_players", lambda **kw: _fetched([]))
    monkeypatch.setattr(SI.A, "attach_gsis",
                        lambda con, df, season, schema="main_nfl_marts": df)
    landed, cov = SI.load_sleeper_injuries_with_coverage(object(), 2026)
    assert len(landed) == 0 and cov["n_fetched"] == 0
    assert SI.classify_land(cov)["verdict"] == "EMPTY_FEED"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3. the op itself raises — read as SOURCE, because a wiring test skips without the manifest
# ══════════════════════════════════════════════════════════════════════════════════════════
def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(_JOB.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {_JOB} — the guard is stale, not passing")


def test_the_ingest_op_can_raise_at_all():
    fn = _function("nfl_sleeper_injuries_ingest_op")
    assert any(isinstance(n, ast.Raise) for n in ast.walk(fn)), (
        "the ingest op contains no `raise` — a run that lands nothing would be green again "
        "(NF-FRESH1's 19 SUCCESS runs)")


def test_every_except_handler_in_the_ingest_op_re_raises():
    """The bare `except Exception:` + `context.log.warning(...)` that ate a 114ms death for 19 days.
    A handler is allowed to page first; it may not end the story."""
    fn = _function("nfl_sleeper_injuries_ingest_op")
    handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
    assert handlers, "no except handler found in the ingest op — this guard is passing on nothing"
    for handler in handlers:
        assert any(isinstance(n, ast.Raise) for n in ast.walk(handler)), (
            "an except handler in the ingest op swallows its exception — that is the NF-FRESH1 bug")


def test_the_write_is_gated_on_the_land_verdict():
    """`should_write` must be consulted BEFORE `write_dataframe`, not after: the Delta write is a
    whole-partition overwrite, so a post-hoc check cannot un-destroy the good snapshot."""
    src = _JOB.read_text()
    assert src.index("should_write") < src.index("s3io.write_dataframe"), (
        "the land verdict must be evaluated before the Delta write")


def test_a_zero_row_write_is_an_error_not_a_log_line():
    """⚠️ Asserted STRUCTURALLY, on the zero-row branch itself. The first cut of this guard checked
    `"raise Exception" in ast.unparse(fn)` and stayed GREEN when this branch's raise was replaced by
    a log line — the op's OTHER raises satisfied it. That is the NF-D17 vacuity mode (a clause
    satisfied by something other than the thing it names), caught only by RED-proving it."""
    fn = _function("nfl_sleeper_injuries_ingest_op")
    branches = [n for n in ast.walk(fn)
                if isinstance(n, ast.If) and isinstance(n.test, ast.UnaryOp)
                and isinstance(n.test.op, ast.Not) and ast.unparse(n.test.operand) == "n"]
    assert len(branches) == 1, (
        "expected exactly one `if not n:` (zero-rows-written) branch in the ingest op; found "
        f"{len(branches)} — this guard is stale, not passing")
    assert any(isinstance(x, ast.Raise) for x in ast.walk(branches[0])), (
        "`write_dataframe` returning 0 (its empty-slice skip) must FAIL the run — an op that is "
        "green over an unwritten table is the entire NF-FRESH1 failure mode")


def test_the_job_asserts_the_artifact_and_not_only_the_producer():
    src = _JOB.read_text()
    assert "nfl_sleeper_injuries_freshness_op" in src
    assert "sports_delta_freshness" in src, (
        "INC-41: only a freshness read from INSIDE the landed Delta log catches a producer that "
        "succeeds while writing nothing")


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4. the Delta freshness SLA
# ══════════════════════════════════════════════════════════════════════════════════════════
_NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
_CONTRACT = SDF.by_name("nfl_sleeper_injuries")


def _reading(hours_ago: float, *, rows: int | None = 2499, version: int = 12):
    return SDF.DeltaReading(name=_CONTRACT.name, last_commit=_NOW - timedelta(hours=hours_ago),
                            version=version, rows=rows)


def test_a_fresh_daily_commit_is_ok():
    v = SDF.classify(_CONTRACT, _reading(4), now=_NOW)
    assert v["verdict"] == "OK" and v["severity"] is None
    assert SDF.is_problem(v) is False


def test_the_19_day_freeze_this_exists_to_catch_is_critical():
    v = SDF.classify(_CONTRACT, _reading(19 * 24), now=_NOW)
    assert v["verdict"] == "STALE"
    assert v["severity"] == "CRITICAL"
    assert SDF.is_problem(v) is True


def test_one_missed_cycle_warns_rather_than_paging_critical():
    """A skipped daily run and a dead feed are different events; collapsing them onto CRITICAL is
    how a monitor gets muted."""
    v = SDF.classify(_CONTRACT, _reading(50), now=_NOW)
    assert v["verdict"] == "STALE" and v["severity"] == "WARN"


def test_an_unreadable_delta_log_is_UNVERIFIED_never_healthy():
    """NF1.7(a): a check that could not run is not a check that passed."""
    v = SDF.classify(_CONTRACT, SDF.DeltaReading(name=_CONTRACT.name, error="TableNotFoundError"),
                     now=_NOW)
    assert v["verdict"] == "UNKNOWN"
    assert v["severity"] == "WARN"
    assert SDF.is_problem(v) is True


def test_a_recent_commit_that_wrote_zero_rows_is_still_a_problem():
    v = SDF.classify(_CONTRACT, _reading(1, rows=0), now=_NOW)
    assert v["verdict"] == "EMPTY" and v["severity"] == "CRITICAL"


def test_an_ABSENT_row_metric_is_not_read_as_zero():
    """delta-rs does not always report `num_output_rows`; treating a missing metric as 0 would page
    EMPTY on every healthy commit."""
    v = SDF.classify(_CONTRACT, _reading(1, rows=None), now=_NOW)
    assert v["verdict"] == "OK"


def test_the_sla_admits_a_late_daily_run_but_not_a_skipped_day():
    assert 24 < _CONTRACT.max_lag_hours < 48


def test_reading_an_absent_table_returns_an_error_rather_than_raising(tmp_path):
    """The reader must never take the op down — an unreadable table becomes UNKNOWN/WARN."""
    reading = SDF.read_contract(_CONTRACT, local_root=str(tmp_path / "nothing-here"))
    assert reading.readable is False and reading.error


def test_the_commit_timestamp_is_parsed_from_epoch_millis():
    """delta-rs reports `timestamp` as epoch ms; misreading it would peg every table UNKNOWN."""
    entry = {"timestamp": int(_NOW.timestamp() * 1000), "version": 3}
    assert SDF._commit_timestamp(entry) == _NOW


def test_an_unknown_contract_name_raises_rather_than_silently_checking_nothing():
    with pytest.raises(KeyError):
        SDF.by_name("nfl_not_a_real_table")


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5. the real Dagster wiring (skips when the dbt manifest is absent — the E11.23 fast-gate rule)
# ══════════════════════════════════════════════════════════════════════════════════════════
def _skip_without_manifest():
    """`pipeline/__init__.py` reads the dbt manifest at import, so these skip rather than crash at
    collection when it is absent. The clauses above are deliberately manifest-free, so the
    load-bearing invariants are defended even where these skip."""
    if not (_REPO / "dbt/target/manifest.json").exists():
        pytest.skip("dbt manifest absent — `pipeline` is not importable in the fast gate")


def test_the_freshness_check_runs_downstream_of_the_land_as_a_graph_edge():
    """An INC-25 ordering fact, not a cron offset: the artifact assertion must read the commit this
    run made, which means it cannot start until the ingest and rebuild have finished."""
    _skip_without_manifest()
    from pipeline.jobs.sports_nfl_sleeper_injuries_job import sports_nfl_sleeper_injuries_job

    graph = sports_nfl_sleeper_injuries_job.graph
    assert {n.name for n in graph.nodes} == {
        "nfl_sleeper_injuries_ingest_op", "nfl_sleeper_injuries_rebuild_op",
        "nfl_sleeper_injuries_freshness_op"}

    deps = graph.dependencies
    freshness = next(k for k in deps if "freshness" in k.name)
    rebuild = next(k for k in deps if "rebuild" in k.name)
    assert {d.node for d in deps[freshness].values()} == {"nfl_sleeper_injuries_rebuild_op"}
    assert {d.node for d in deps[rebuild].values()} == {"nfl_sleeper_injuries_ingest_op"}


def test_a_missing_sports_duckdb_RAISES_instead_of_reporting_a_green_run(tmp_path, monkeypatch):
    """⭐ THE NF-FRESH1 REGRESSION TEST, end to end through the real op: an absent DuckDB used to
    produce a 114ms SUCCESS. It must now fail the run, and it must do so BEFORE touching Sleeper."""
    _skip_without_manifest()
    import importlib

    from dagster import build_op_context

    mod = importlib.import_module("pipeline.jobs.sports_nfl_sleeper_injuries_job")
    monkeypatch.setenv("SPORTS_DUCKDB_PATH", str(tmp_path / "definitely-absent.duckdb"))
    paged: list[tuple] = []
    monkeypatch.setattr(mod, "_page",
                        lambda ctx, title, body, **kw: paged.append((title, kw.get("severity"))))

    with pytest.raises(Exception, match="precondition failed"):
        mod.nfl_sleeper_injuries_ingest_op(build_op_context())
    assert paged and paged[0][1] == "CRITICAL"
    assert "DuckDB missing" in paged[0][0]


def test_the_missing_duckdb_page_names_the_volume_and_the_job_that_creates_it(tmp_path, monkeypatch):
    """A page that says only "it failed" costs the operator the same hour every time.

    ⚠️ Asserted on the VOLUME NAME, not on `BOX_VOLUME_DIR`: the remedy also interpolates
    `BOX_DUCKDB_PATH`, which CONTAINS `BOX_VOLUME_DIR` as a substring, so a `BOX_VOLUME_DIR in
    remedy` clause was satisfied incidentally and stayed green when the volume sentence was deleted.
    The red proof found that; the tokens below are the ones an operator actually acts on."""
    from betting_ml.utils.sports_duckdb import BOX_DUCKDB_PATH, missing_duckdb_remedy

    monkeypatch.setenv("SPORTS_DUCKDB_PATH", str(tmp_path / "absent.duckdb"))
    remedy = missing_duckdb_remedy(tmp_path / "absent.duckdb")
    assert "sports_duckdb" in remedy, "the remedy must name the VOLUME to look for"
    assert BOX_DUCKDB_PATH in remedy, "the remedy must state what to set the env var to"
    assert "sports_nfl_dbt_build_job" in remedy, "the remedy must name the job that creates it"
    assert "env.required" in remedy, "the remedy must say why the next deploy will fail"
