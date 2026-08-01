"""E11.30 — execution-level proof that the check_*_op family pages via send_alert.

Companion to test_check_ops_alerting_wiring.py (which is fast-gate-safe AST inspection).
This module SKIPS entirely without a compiled dbt manifest (same convention as
test_monitor_health_wiring.py — importing `pipeline` runs pipeline/__init__.py, which reads
the dbt manifest, absent in the fast CI job). It runs locally / on the box after a dbt
compile.

Each test executes the REAL Dagster op end-to-end with `_run_script` mocked to return a
crafted stdout (simulating the underlying check script's [METRIC] lines) and
`pipeline.utils.alerting.send_alert` mocked to a MagicMock — proving the op pages on the
discriminating real condition and stays silent on the healthy/benign one. This is the
"mocked-SNS test" the E11.30 story requires; `send_alert` itself hits SNS, so a live-box
smoke (deliberately trip a FREEZE/DEGRADED/IMPLAUSIBLE condition, confirm the email lands)
is still required before trusting the page path in prod.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST = _REPO / "dbt" / "target" / "manifest.json"
if not _MANIFEST.exists():  # pipeline import needs the compiled dbt manifest
    pytest.skip(
        "pipeline import requires dbt/target/manifest.json (absent in the fast gate); "
        "runs locally / on the box after a dbt compile.",
        allow_module_level=True,
    )

from dagster import DagsterInstance, in_process_executor, job  # noqa: E402

import pipeline.ops.daily_ingestion_ops as dio  # noqa: E402
import pipeline.utils.alerting as alerting  # noqa: E402


def _run_op(monkeypatch, op, stdout: str):
    """Execute a single Nothing-in/Nothing-out op with `_run_script` mocked to return
    `stdout` and `send_alert` mocked to a MagicMock. Returns the send_alert mock."""
    monkeypatch.setattr(dio, "_run_script", lambda *a, **k: stdout)
    mock_alert = MagicMock()
    monkeypatch.setattr(alerting, "send_alert", mock_alert)

    @job(executor_def=in_process_executor)
    def _j():
        op()

    result = _j.execute_in_process(instance=DagsterInstance.ephemeral())
    assert result.success
    return mock_alert


class TestOddsCoverageExecution:
    def test_freeze_pages_critical(self, monkeypatch):
        stdout = "[METRIC] odds_coverage_score=0.0000\n[METRIC] odds_coverage_freeze=1"
        mock_alert = _run_op(monkeypatch, dio.check_odds_coverage_op, stdout)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.kwargs["severity"] == "CRITICAL"
        assert mock_alert.call_args.kwargs["dedup_key"] == "odds_coverage_freeze"

    def test_healthy_slate_never_pages(self, monkeypatch):
        stdout = "[METRIC] odds_coverage_score=1.0000\n[METRIC] odds_coverage_freeze=0"
        mock_alert = _run_op(monkeypatch, dio.check_odds_coverage_op, stdout)
        mock_alert.assert_not_called()

    def test_no_odds_yet_never_pages(self, monkeypatch):
        """The exact false-positive the guard must never trigger on."""
        stdout = "[METRIC] odds_coverage_score=1.0000\n[METRIC] odds_coverage_freeze=0"
        mock_alert = _run_op(monkeypatch, dio.check_odds_coverage_op, stdout)
        mock_alert.assert_not_called()


class TestFeatureBlockCoverageExecution:
    def test_degraded_block_pages(self, monkeypatch):
        stdout = (
            "[METRIC] feature_block_min_cov_ratio=0.1000\n"
            "[METRIC] feature_block_date_outage_count=0\n"
            "[METRIC] feature_block_degraded_count=1"
        )
        mock_alert = _run_op(monkeypatch, dio.check_feature_block_coverage_op, stdout)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.kwargs["severity"] == "ERROR"

    def test_whole_slate_date_outage_pages_critical(self, monkeypatch):
        stdout = (
            "[METRIC] feature_block_min_cov_ratio=0.0500\n"
            "[METRIC] feature_block_date_outage_count=3\n"
            "[METRIC] feature_block_degraded_count=1"
        )
        mock_alert = _run_op(monkeypatch, dio.check_feature_block_coverage_op, stdout)
        assert mock_alert.call_args.kwargs["severity"] == "CRITICAL"

    def test_healthy_never_pages(self, monkeypatch):
        stdout = (
            "[METRIC] feature_block_min_cov_ratio=1.0000\n"
            "[METRIC] feature_block_date_outage_count=0\n"
            "[METRIC] feature_block_degraded_count=0"
        )
        mock_alert = _run_op(monkeypatch, dio.check_feature_block_coverage_op, stdout)
        mock_alert.assert_not_called()


class TestServedPredictionIntegrityExecution:
    def test_problem_pages_critical(self, monkeypatch):
        stdout = "[METRIC] served_integrity_problem_count=2"
        mock_alert = _run_op(monkeypatch, dio.check_served_prediction_integrity_op, stdout)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.kwargs["severity"] == "CRITICAL"

    def test_healthy_never_pages(self, monkeypatch):
        stdout = "[METRIC] served_integrity_problem_count=0"
        mock_alert = _run_op(monkeypatch, dio.check_served_prediction_integrity_op, stdout)
        mock_alert.assert_not_called()


class TestInjuryStatusHealthExecution:
    def test_implausible_pages_critical(self, monkeypatch):
        stdout = (
            "[METRIC] injury_status_ok=0\n"
            "[METRIC] injury_status_feed_freshness=OK\n"
            "[METRIC] injury_status_il_plausibility=IMPLAUSIBLE"
        )
        mock_alert = _run_op(monkeypatch, dio.check_injury_status_health_op, stdout)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.kwargs["severity"] == "CRITICAL"

    def test_unknown_plausibility_pages_warn(self, monkeypatch):
        stdout = (
            "[METRIC] injury_status_ok=0\n"
            "[METRIC] injury_status_feed_freshness=OK\n"
            "[METRIC] injury_status_il_plausibility=UNKNOWN"
        )
        mock_alert = _run_op(monkeypatch, dio.check_injury_status_health_op, stdout)
        mock_alert.assert_called_once()
        assert mock_alert.call_args.kwargs["severity"] == "WARN"

    def test_feed_freshness_only_failure_does_not_page(self, monkeypatch):
        """The documented off-season ingest hole — must log-only, never page (alert fatigue)."""
        stdout = (
            "[METRIC] injury_status_ok=0\n"
            "[METRIC] injury_status_feed_freshness=STALE\n"
            "[METRIC] injury_status_il_plausibility=OK"
        )
        mock_alert = _run_op(monkeypatch, dio.check_injury_status_health_op, stdout)
        mock_alert.assert_not_called()

    def test_healthy_never_pages(self, monkeypatch):
        stdout = (
            "[METRIC] injury_status_ok=1\n"
            "[METRIC] injury_status_feed_freshness=OK\n"
            "[METRIC] injury_status_il_plausibility=OK"
        )
        mock_alert = _run_op(monkeypatch, dio.check_injury_status_health_op, stdout)
        mock_alert.assert_not_called()
