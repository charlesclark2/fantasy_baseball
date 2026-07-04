"""E11.23 — monitor-health WIRING checks that need the ``pipeline`` package.

These cross-check the import-safe ``betting_ml.monitoring.monitor_health`` constants against the
ACTUAL registered sensors/schedules and assert the 'permanently on' AC (default_status=RUNNING) plus
that the guard op never HALTs. Importing ``pipeline`` triggers ``pipeline/__init__.py`` → the dbt
manifest read, which is absent in the fast-test gate — so this whole module SKIPS when the manifest
isn't built (it runs locally / on the box, where it exists, and is the pipeline-side box verify).
"""
from __future__ import annotations

from pathlib import Path

import pytest

_MANIFEST = Path(__file__).resolve().parents[2] / "dbt" / "target" / "manifest.json"
if not _MANIFEST.exists():  # pipeline import needs the compiled dbt manifest
    pytest.skip(
        "pipeline import requires dbt/target/manifest.json (absent in the fast gate); "
        "runs locally / on the box after a dbt compile.",
        allow_module_level=True,
    )

from dagster import DagsterInstance, in_process_executor, job  # noqa: E402

from betting_ml.monitoring.monitor_health import (  # noqa: E402
    CRITICAL_SCHEDULES,
    CRITICAL_SENSORS,
    REQUIRED_INTRADAY_FLAGS,
)
from pipeline.ops.daily_ingestion_ops import check_monitors_healthy_op  # noqa: E402


def test_critical_sets_match_registered_instigators():
    """The critical names must match what's actually registered, or the guard checks phantoms."""
    from pipeline.schedules import all_schedules
    from pipeline.sensors import all_sensors

    sensor_names = {s.name for s in all_sensors}
    schedule_names = {s.name for s in all_schedules}
    assert CRITICAL_SENSORS <= sensor_names, f"phantom sensors: {CRITICAL_SENSORS - sensor_names}"
    assert CRITICAL_SCHEDULES <= schedule_names, (
        f"phantom schedules: {CRITICAL_SCHEDULES - schedule_names}"
    )


def test_critical_instigators_self_start():
    """The 'permanently on' AC: every critical sensor/schedule declares default_status=RUNNING so
    it self-starts on the box / after a DB reset instead of silently booting STOPPED (E11.23)."""
    from dagster import DefaultScheduleStatus, DefaultSensorStatus

    from pipeline.schedules import all_schedules
    from pipeline.sensors import all_sensors

    for s in all_sensors:
        if s.name in CRITICAL_SENSORS:
            assert s.default_status == DefaultSensorStatus.RUNNING, (
                f"critical sensor {s.name} must be default_status=RUNNING"
            )
    for s in all_schedules:
        if s.name in CRITICAL_SCHEDULES:
            assert s.default_status == DefaultScheduleStatus.RUNNING, (
                f"critical schedule {s.name} must be default_status=RUNNING"
            )


@job(executor_def=in_process_executor)
def _guard_job():
    check_monitors_healthy_op()


def test_op_never_raises_on_healthy_ephemeral_instance(monkeypatch):
    """The op runs end-to-end against a real ephemeral instance (empty → nothing STOPPED) with all
    flags set → succeeds, no alarm."""
    for f in REQUIRED_INTRADAY_FLAGS:
        monkeypatch.setenv(f, "1")
    result = _guard_job.execute_in_process(instance=DagsterInstance.ephemeral())
    assert result.success


def test_op_never_raises_when_flags_missing(monkeypatch):
    """Even with flags unset (would alarm), the op SUCCEEDS — ALERT-tier, never HALT."""
    for f in REQUIRED_INTRADAY_FLAGS:
        monkeypatch.delenv(f, raising=False)
    result = _guard_job.execute_in_process(instance=DagsterInstance.ephemeral())
    assert result.success
