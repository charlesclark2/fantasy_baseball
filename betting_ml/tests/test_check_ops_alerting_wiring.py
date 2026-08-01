"""E11.30 — "ALERT-tier" must actually `send_alert`, not just `context.log.warning`.

WHY THIS EXISTS
    E11.27 found that of the check_*_op / monitor family, only `check_monitors_healthy_op`
    (E11.23) and `update_archetype_posteriors_op` (E11.22) actually called `send_alert`.
    `check_served_prediction_integrity_op`, `check_feature_block_coverage_op`,
    `check_odds_coverage_op`, and `check_injury_status_health_op` only ever reached
    `context.log.warning` in their (default) non-strict path — a Dagster step-log line
    nobody was watching. `check_served_prediction_integrity_op` had ALREADY had a
    `feature_store_frac<0.80` fallback detector when the E11.24 §8 intraday_fallback blind
    spot persisted for days: the detection logic existed the whole time, the page never
    fired. This is the recurrence guard for that class: an op tagged ALERT-tier must
    actually page on its real-condition path.

Fast-gate-safe AST/source inspection ONLY (no `pipeline` import, which pulls the dbt
manifest — absent in CI, see test_intraday_fallback_wiring.py / test_lineup_intraday_
s3_rebuild.py for the same convention). Asserts each op's send_alert call exists, is
guarded by the SAME discriminating signal already computed for its log banner (never
unconditional), and carries the right severity.

The companion execution-level proof (mocked _run_script + mocked send_alert through a real
Dagster op run) is test_check_ops_alerting_execution.py, which SKIPS without a compiled dbt
manifest. `send_alert` itself hits SNS, so neither layer can prove a page reaches an inbox —
that is still a live-box smoke (see the CLAUDE.md E11.30 landmine)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_OPS = _REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"


def _op_fn(name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(_OPS.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found in daily_ingestion_ops.py")


def _op_src(name: str) -> str:
    return ast.unparse(_op_fn(name))


class TestWiringOddsCoverage:
    def test_pages_on_the_freeze_metric(self):
        src = _op_src("check_odds_coverage_op")
        assert "send_alert(" in src
        assert "odds_coverage_freeze" in src
        assert "CRITICAL" in src

    def test_page_is_guarded_by_the_freeze_flag_not_unconditional(self):
        fn = _op_fn("check_odds_coverage_op")
        # find the `if freeze:` guard and confirm send_alert lives inside it
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                test_src = ast.unparse(node.test)
                if test_src == "freeze":
                    assert "send_alert(" in ast.unparse(node.body)
                    return
        pytest.fail("no `if freeze:` guard found wrapping the send_alert call")

    def test_strict_halt_path_does_not_need_its_own_send_alert(self):
        """The strict/HALT branch re-raises — that fails the op/job, which the pre-existing
        run_failure_alert_sensor already pages CRITICAL for (daily_ingestion_job is
        HALT-tier). A second direct send_alert call in that branch would be a redundant page,
        not a missing one."""
        fn = _op_fn("check_odds_coverage_op")
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        # the handler wrapping the _run_script call (the largest one) still re-raises when
        # strict — a small inner `except ValueError: pass` (float-parse) is a distractor.
        outer = max(handlers, key=lambda h: len(ast.unparse(h)))
        assert "raise" in ast.unparse(outer)


class TestWiringFeatureBlockCoverage:
    def test_pages_on_the_degraded_count_metric(self):
        src = _op_src("check_feature_block_coverage_op")
        assert "send_alert(" in src
        assert "feature_block_degraded_count" in src
        assert "CRITICAL" in src and "ERROR" in src

    def test_page_is_guarded_by_degraded_count_not_unconditional(self):
        fn = _op_fn("check_feature_block_coverage_op")
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and "degraded_count" in ast.unparse(node.test):
                assert "send_alert(" in ast.unparse(node.body)
                return
        pytest.fail("no degraded_count guard found wrapping the send_alert call")

    def test_severity_escalates_on_a_whole_slate_date_outage(self):
        """A whole-slate date outage (the E9.53 signature the window aggregate alone
        dilutes away) must page CRITICAL, not just ERROR."""
        src = _op_src("check_feature_block_coverage_op")
        assert "severity='CRITICAL' if date_outage_count > 0 else 'ERROR'" in src


class TestWiringServedPredictionIntegrity:
    def test_pages_on_the_problem_count_metric(self):
        src = _op_src("check_served_prediction_integrity_op")
        assert "send_alert(" in src
        assert "served_integrity_problem_count" in src
        assert "CRITICAL" in src

    def test_page_is_guarded_by_problem_count_not_unconditional(self):
        fn = _op_fn("check_served_prediction_integrity_op")
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and "problem_count" in ast.unparse(node.test):
                assert "send_alert(" in ast.unparse(node.body)
                return
        pytest.fail("no problem_count guard found wrapping the send_alert call")


class TestWiringInjuryStatusHealth:
    def test_pages_on_implausible_and_unknown_but_not_feed_freshness_alone(self):
        src = _op_src("check_injury_status_health_op")
        assert "send_alert(" in src
        assert "IMPLAUSIBLE" in src and "CRITICAL" in src
        assert "UNKNOWN" in src and "WARN" in src

    def test_ok_short_circuits_before_any_page(self):
        fn = _op_fn("check_injury_status_health_op")
        src = ast.unparse(fn)
        assert "metrics.get('injury_status_ok') == '1'" in src
        # the OK short-circuit must appear textually before the send_alert call
        assert src.index('injury_status_ok') < src.index("send_alert(")

    def test_feed_freshness_only_failure_does_not_page(self):
        """A feed_freshness-only failure (il_plausibility OK) must return before send_alert —
        that alone is the documented, already-understood off-season ingest hole; paging on
        it daily for ~4 months would be pure alert fatigue with no new action to take."""
        fn = _op_fn("check_injury_status_health_op")
        src = ast.unparse(fn)
        assert "if severity is None:" in src
        assert src.index("if severity is None:") < src.index("send_alert(")

    def test_op_still_never_raises_in_the_non_strict_path(self):
        """ALERT-tier: an IL badge is a profile adornment — the new send_alert call must not
        introduce a raise on the non-strict path."""
        fn = _op_fn("check_injury_status_health_op")
        # everything after the try/except block (the non-strict body) must contain no raise
        body_stmts = fn.body
        try_idx = next(i for i, s in enumerate(body_stmts) if isinstance(s, ast.Try))
        rest = body_stmts[try_idx + 1:]
        for stmt in rest:
            for node in ast.walk(stmt):
                assert not isinstance(node, ast.Raise)
