"""E11.4 — CI guard for the intraday job decomposition.

Verifies:
  1. intraday_schedule_job and intraday_weather_job are NOT in all_intraday_schedules
     (their Railway cron services have taken over; Dagster must not auto-fire them).
  2. lineup_monitor_job does NOT reference lineup_ingest_schedule or lineup_odds_snapshot
     (schedule capture → Railway cron; Parlay odds → decommissioned).
  3. services/schedule_capture/ and services/weather_capture/ directories exist and
     contain the required files.
  4. trigger_dbt.py exits 0 when DBT_RUNNER_URL is unset (graceful no-op).

Import strategy: pipeline.* loaded via importlib.util to avoid triggering
pipeline/__init__.py (which requires Snowflake credentials in the test env).
"""
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO = Path(__file__).parents[2]


def _load(name: str, rel: str):
    path = str(_REPO / rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── 1. all_intraday_schedules must NOT include the decommissioned jobs ────────
# Parse the source rather than executing the module — executing triggers real dagster
# validation in the full test suite environment.

class TestDecommissionedSchedules:
    """AST-based checks that the decommissioned schedule objects were removed from
    all_intraday_schedules without executing intraday_schedules.py (which would require
    dagster + live jobs in the test env)."""

    @pytest.fixture(autouse=True)
    def _read_src(self):
        self._src = (_REPO / "pipeline" / "schedules" / "intraday_schedules.py").read_text()

    def _all_schedules_body(self) -> str:
        """Extract the text of the all_intraday_schedules = [...] literal."""
        src = self._src
        start = src.find("all_intraday_schedules = [")
        assert start != -1, "all_intraday_schedules definition not found"
        end = src.find("]", start)
        return src[start:end + 1]

    def test_intraday_schedule_job_not_in_all_schedules(self):
        """intraday_schedule_capture_* schedules must not be in the list."""
        body = self._all_schedules_body()
        assert "intraday_schedule_capture" not in body, (
            "intraday_schedule_capture schedule is still in all_intraday_schedules — "
            "E11.4 moved this to Railway cron (services/schedule_capture/)"
        )

    def test_intraday_weather_job_not_in_all_schedules(self):
        """intraday_weather_* schedules must not be in the list."""
        body = self._all_schedules_body()
        assert "intraday_weather_schedule" not in body, (
            "intraday_weather_schedule is still in all_intraday_schedules — "
            "E11.4 moved this to Railway cron (services/weather_capture/)"
        )

    def test_all_intraday_schedules_is_list(self):
        """The list must still be defined (not removed entirely)."""
        assert "all_intraday_schedules = [" in self._src

    def test_odds_clv_rebuild_still_present(self):
        """CLV rebuild stays on Dagster (once/day post-game; not a polling job)."""
        body = self._all_schedules_body()
        assert "odds_clv_rebuild_schedule" in body, (
            "odds_clv_rebuild_schedule should remain in all_intraday_schedules"
        )


# ── 2. lineup_monitor_job must not reference the decommissioned ops ───────────

class TestLineupMonitorJobSlimmed:
    """Parse sensor_jobs.py source to verify the decommissioned ops are not wired in."""

    def test_lineup_ingest_schedule_not_imported(self):
        """lineup_ingest_schedule must not appear in the import block.
        Names may still appear in doc-strings / comments as historical context."""
        import ast
        src = (_REPO / "pipeline" / "jobs" / "sensor_jobs.py").read_text()
        tree = ast.parse(src)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "lineup_ingest_schedule" not in imported, (
            "lineup_ingest_schedule is still imported in sensor_jobs.py — "
            "E11.4 moved schedule ingestion to Railway cron"
        )

    def test_lineup_odds_snapshot_not_imported(self):
        """lineup_odds_snapshot must not appear in the import block."""
        import ast
        src = (_REPO / "pipeline" / "jobs" / "sensor_jobs.py").read_text()
        tree = ast.parse(src)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "lineup_odds_snapshot" not in imported, (
            "lineup_odds_snapshot is still imported in sensor_jobs.py — "
            "Parlay odds were decommissioned 2026-06-16 (Story 12.3.7)"
        )

    def test_lineup_monitor_job_calls_lineup_ingest_umpires_first(self):
        """After the E11.4 slim, umpire ingest is the first op in the chain."""
        src = (_REPO / "pipeline" / "jobs" / "sensor_jobs.py").read_text()
        # The job body should call lineup_ingest_umpires() without a start= arg.
        assert "lineup_ingest_umpires()" in src, (
            "lineup_ingest_umpires() should be called without start= "
            "(it's now the first op in lineup_monitor_job)"
        )


# ── 3. lineup_ingest_umpires op has no 'start' input ─────────────────────────

class TestLineupIngestUmpiresSig:
    """Verify the op signature was updated to remove the start input."""

    def test_no_start_input(self):
        src = (_REPO / "pipeline" / "ops" / "sensor_ops.py").read_text()
        # Find the lineup_ingest_umpires function. Confirm the @op decorator
        # directly above it no longer contains 'ins'.
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "def lineup_ingest_umpires" in line:
                # Look at the decorator on the preceding line(s).
                preceding = " ".join(lines[max(0, i - 5):i])
                assert "ins=" not in preceding, (
                    "lineup_ingest_umpires still has an 'ins=' in its @op decorator — "
                    "it should be the chain head now (no start input)"
                )
                return
        pytest.fail("lineup_ingest_umpires not found in sensor_ops.py")


# ── 4. Railway cron service files exist ──────────────────────────────────────

class TestCronServiceFiles:
    _REQUIRED = {
        "services/schedule_capture": ["Dockerfile", "entrypoint.sh", "railway.toml", "trigger_dbt.py"],
        "services/weather_capture": ["Dockerfile", "entrypoint.sh", "railway.toml"],
    }

    @pytest.mark.parametrize("svc_dir,files", list(_REQUIRED.items()))
    def test_required_files_exist(self, svc_dir, files):
        base = _REPO / svc_dir
        for fname in files:
            assert (base / fname).exists(), (
                f"Missing E11.4 cron service file: {svc_dir}/{fname}"
            )

    def test_schedule_capture_entrypoint_active_window_guard(self):
        src = (_REPO / "services" / "schedule_capture" / "entrypoint.sh").read_text()
        assert "active window" in src.lower() or "outside" in src.lower(), (
            "schedule_capture/entrypoint.sh should have a time-window guard"
        )

    def test_weather_capture_entrypoint_active_window_guard(self):
        src = (_REPO / "services" / "weather_capture" / "entrypoint.sh").read_text()
        assert "active window" in src.lower() or "outside" in src.lower(), (
            "weather_capture/entrypoint.sh should have a time-window guard"
        )

    def test_schedule_capture_railway_toml_cron(self):
        src = (_REPO / "services" / "schedule_capture" / "railway.toml").read_text()
        assert "cronSchedule" in src
        assert "*/30" in src, "schedule_capture should fire every 30 min"

    def test_weather_capture_railway_toml_cron(self):
        src = (_REPO / "services" / "weather_capture" / "railway.toml").read_text()
        assert "cronSchedule" in src

    def test_trigger_dbt_graceful_when_url_unset(self, monkeypatch, tmp_path):
        """trigger_dbt.py must exit 0 when DBT_RUNNER_URL is not set."""
        monkeypatch.delenv("DBT_RUNNER_URL", raising=False)

        # Load trigger_dbt.py in a subprocess-safe way by exec'ing with sys.argv mocked.
        trigger_src = (_REPO / "services" / "schedule_capture" / "trigger_dbt.py").read_text()
        # Patch sys.exit and sys.argv; confirm it calls sys.exit(0).
        captured_exit = {}

        def fake_exit(code):
            captured_exit["code"] = code
            raise SystemExit(code)

        ns = {"__name__": "__main__"}
        with patch("sys.argv", ["trigger_dbt.py", "run", "--select", "stg_test"]), \
             patch("sys.exit", side_effect=fake_exit):
            try:
                exec(compile(trigger_src, "trigger_dbt.py", "exec"), ns)
            except SystemExit:
                pass

        assert captured_exit.get("code") == 0, (
            "trigger_dbt.py should exit 0 when DBT_RUNNER_URL is unset"
        )
