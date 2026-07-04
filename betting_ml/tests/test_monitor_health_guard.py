"""E11.23 — the silently-not-running guard (``check_monitors_healthy_op``).

The cutover-runtime-landmine class CI can't otherwise see: a serving-critical sensor/schedule that
boots STOPPED, or an intraday-refresh flag shipped gated-off, silently never runs (odds froze 3 days
with NO alert). Two pure detectors lock it in: ``_flag_problems`` (any permanently-on intraday flag
not == "1") and ``_stopped_critical_instigators`` (any critical sensor/schedule explicitly STOPPED).
The op wraps the latter best-effort so a broken/ephemeral instance degrades to the flag check
(ALERT-tier — the guard NEVER HALTs).
"""
from __future__ import annotations

from types import SimpleNamespace

from dagster import DagsterInstance, in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    _CRITICAL_SCHEDULES,
    _CRITICAL_SENSORS,
    _REQUIRED_INTRADAY_FLAGS,
    _flag_problems,
    _stopped_critical_instigators,
    check_monitors_healthy_op,
)

_ALL_FLAGS_OK = {f: "1" for f in _REQUIRED_INTRADAY_FLAGS}


class _FakeInstance:
    """Minimal DagsterInstance stand-in: ``all_instigator_state`` returns states with the given
    names (all treated as STOPPED — the guard only queries with the STOPPED filter)."""

    def __init__(self, stopped_names):
        self._stopped = [SimpleNamespace(instigator_name=n) for n in stopped_names]

    def all_instigator_state(self, instigator_statuses=None):  # noqa: ARG002
        return self._stopped


# ── flag detector ───────────────────────────────────────────────────────────────
def test_all_flags_ok_no_problems():
    assert _flag_problems(_ALL_FLAGS_OK) == []


def test_missing_intraday_flag_is_flagged():
    env = dict(_ALL_FLAGS_OK)
    del env["SCHEDULE_LAKEHOUSE_INTRADAY"]
    problems = _flag_problems(env)
    assert any("SCHEDULE_LAKEHOUSE_INTRADAY" in p for p in problems)
    assert len(problems) == 1


def test_flag_set_to_zero_is_flagged():
    problems = _flag_problems({**_ALL_FLAGS_OK, "LINEUP_INTRADAY_S3_REBUILD": "0"})
    assert any("LINEUP_INTRADAY_S3_REBUILD" in p for p in problems)


def test_empty_env_flags_all_required():
    assert len(_flag_problems({})) == len(_REQUIRED_INTRADAY_FLAGS)


# ── stopped-instigator detector ──────────────────────────────────────────────────
def test_stopped_critical_sensor_detected():
    problems = _stopped_critical_instigators(_FakeInstance(["odds_current_rebuild_sensor"]))
    assert any("odds_current_rebuild_sensor" in p and "STOPPED" in p for p in problems)


def test_stopped_critical_schedule_detected():
    problems = _stopped_critical_instigators(_FakeInstance(["daily_ingestion_job_schedule"]))
    assert any("daily_ingestion_job_schedule" in p and "STOPPED" in p for p in problems)


def test_non_critical_stopped_instigator_ignored():
    """A STOPPED schedule that is deliberately operator-gated (e.g. the paid public-betting
    capture) must NOT alarm — only the critical set does."""
    inst = _FakeInstance(["intraday_public_betting_daytime", "weekly_ml_job_schedule"])
    assert _stopped_critical_instigators(inst) == []


def test_no_stopped_instigators_clean():
    assert _stopped_critical_instigators(_FakeInstance([])) == []


# ── op-level best-effort / never-HALT ─────────────────────────────────────────────
@job(executor_def=in_process_executor)
def _guard_job():
    check_monitors_healthy_op()


def test_op_never_raises_on_healthy_ephemeral_instance(monkeypatch):
    """The op runs end-to-end against a real ephemeral instance (empty → nothing STOPPED) with all
    flags set → succeeds, no alarm."""
    for f in _REQUIRED_INTRADAY_FLAGS:
        monkeypatch.setenv(f, "1")
    result = _guard_job.execute_in_process(instance=DagsterInstance.ephemeral())
    assert result.success


def test_op_never_raises_when_flags_missing(monkeypatch):
    """Even with flags unset (would alarm), the op SUCCEEDS — ALERT-tier, never HALT."""
    for f in _REQUIRED_INTRADAY_FLAGS:
        monkeypatch.delenv(f, raising=False)
    result = _guard_job.execute_in_process(instance=DagsterInstance.ephemeral())
    assert result.success


def test_critical_sets_match_registered_instigators():
    """The critical names must match what's actually registered, or the guard checks phantoms."""
    from pipeline.sensors import all_sensors
    from pipeline.schedules import all_schedules

    sensor_names = {s.name for s in all_sensors}
    schedule_names = {s.name for s in all_schedules}
    assert _CRITICAL_SENSORS <= sensor_names, f"phantom sensors: {_CRITICAL_SENSORS - sensor_names}"
    assert _CRITICAL_SCHEDULES <= schedule_names, (
        f"phantom schedules: {_CRITICAL_SCHEDULES - schedule_names}"
    )


def test_critical_instigators_self_start():
    """The 'permanently on' AC: every critical sensor/schedule declares default_status=RUNNING so
    it self-starts on the box / after a DB reset instead of silently booting STOPPED (E11.23)."""
    from dagster import DefaultScheduleStatus, DefaultSensorStatus

    from pipeline.sensors import all_sensors
    from pipeline.schedules import all_schedules

    for s in all_sensors:
        if s.name in _CRITICAL_SENSORS:
            assert s.default_status == DefaultSensorStatus.RUNNING, (
                f"critical sensor {s.name} must be default_status=RUNNING"
            )
    for s in all_schedules:
        if s.name in _CRITICAL_SCHEDULES:
            assert s.default_status == DefaultScheduleStatus.RUNNING, (
                f"critical schedule {s.name} must be default_status=RUNNING"
            )
