"""E11.23 — the silently-not-running guard's pure detectors (fast-gate safe).

The cutover-runtime-landmine class CI can't otherwise see: a serving-critical sensor/schedule that
boots STOPPED, or an intraday-refresh flag shipped gated-off, silently never runs (odds froze 3 days
with NO alert). Two pure detectors lock it in: ``flag_problems`` (any permanently-on intraday flag
not == "1") and ``stopped_critical_instigators`` (any critical sensor/schedule explicitly STOPPED).

Imports ``betting_ml.monitoring.monitor_health`` — NOT ``pipeline`` — on purpose: importing the
pipeline package triggers the dbt-manifest read (absent in the fast gate). The op-level / registration
cross-checks that DO need pipeline live in ``test_monitor_health_wiring.py`` (manifest-guarded).
"""
from __future__ import annotations

from types import SimpleNamespace

from betting_ml.monitoring.monitor_health import (
    REQUIRED_INTRADAY_FLAGS,
    flag_problems,
    stopped_critical_instigators,
)

_ALL_FLAGS_OK = {f: "1" for f in REQUIRED_INTRADAY_FLAGS}


class _FakeInstance:
    """Minimal DagsterInstance stand-in: ``all_instigator_state`` returns states with the given
    names (all treated as STOPPED — the guard only queries with the STOPPED filter)."""

    def __init__(self, stopped_names):
        self._stopped = [SimpleNamespace(instigator_name=n) for n in stopped_names]

    def all_instigator_state(self, instigator_statuses=None):  # noqa: ARG002
        return self._stopped


# ── flag detector ───────────────────────────────────────────────────────────────
def test_all_flags_ok_no_problems():
    assert flag_problems(_ALL_FLAGS_OK) == []


def test_missing_intraday_flag_is_flagged():
    env = dict(_ALL_FLAGS_OK)
    del env["SCHEDULE_LAKEHOUSE_INTRADAY"]
    problems = flag_problems(env)
    assert any("SCHEDULE_LAKEHOUSE_INTRADAY" in p for p in problems)
    assert len(problems) == 1


def test_flag_set_to_zero_is_flagged():
    problems = flag_problems({**_ALL_FLAGS_OK, "LINEUP_INTRADAY_S3_REBUILD": "0"})
    assert any("LINEUP_INTRADAY_S3_REBUILD" in p for p in problems)


def test_empty_env_flags_all_required():
    assert len(flag_problems({})) == len(REQUIRED_INTRADAY_FLAGS)


# ── stopped-instigator detector ──────────────────────────────────────────────────
def test_stopped_critical_sensor_detected():
    problems = stopped_critical_instigators(_FakeInstance(["odds_current_rebuild_sensor"]))
    assert any("odds_current_rebuild_sensor" in p and "STOPPED" in p for p in problems)


def test_stopped_critical_schedule_detected():
    problems = stopped_critical_instigators(_FakeInstance(["daily_ingestion_job_schedule"]))
    assert any("daily_ingestion_job_schedule" in p and "STOPPED" in p for p in problems)


def test_non_critical_stopped_instigator_ignored():
    """A STOPPED schedule that is deliberately operator-gated (e.g. the paid public-betting
    capture) must NOT alarm — only the critical set does."""
    inst = _FakeInstance(["intraday_public_betting_daytime", "weekly_ml_job_schedule"])
    assert stopped_critical_instigators(inst) == []


def test_no_stopped_instigators_clean():
    assert stopped_critical_instigators(_FakeInstance([])) == []
