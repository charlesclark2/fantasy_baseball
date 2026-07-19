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
    CRITICAL_SENSORS,
    REQUIRED_INTRADAY_FLAGS,
    flag_problems,
    SENSOR_TICK_CEILING_OVERRIDES,
    stale_running_sensor_ticks,
    stale_sensor_ticks,
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


# ── INC-32 stale-tick detector (the sensor-daemon-wedged-mid-slate mode) ──────────
# A continuously-ticking critical sensor (NOT in the once-daily override map — sorted[0] is
# clv_alert_sensor, which IS overridden, so pick the first non-overridden one).
_A_CRITICAL = next(
    n for n in sorted(CRITICAL_SENSORS) if n not in SENSOR_TICK_CEILING_OVERRIDES
)


def test_stale_sensor_tick_flagged_over_ceiling():
    # 90 min since last tick, ceiling 60 min → flagged
    problems = stale_sensor_ticks({_A_CRITICAL: 90 * 60}, max_age_s=3600)
    assert any(_A_CRITICAL in p and "STALE" in p for p in problems)


# ── 2026-07-19 per-sensor ceiling overrides (once-daily sensors false-paged daily) ──
def test_once_daily_sensor_not_flagged_at_19h():
    """clv/model_health tick once per day by design (minimum_interval=86400): a ~19h age is
    NORMAL and must not page — this exact case fired a false CRITICAL two days running."""
    ages = {"clv_alert_sensor": 1152 * 60, "model_health_alert_sensor": 1152 * 60}
    assert stale_sensor_ticks(ages, max_age_s=3600) == []


def test_once_daily_sensor_flagged_past_override_ceiling():
    """A once-daily sensor silent past its 30h ceiling IS a real wedge → flagged."""
    problems = stale_sensor_ticks({"clv_alert_sensor": 31 * 3600}, max_age_s=3600)
    assert any("clv_alert_sensor" in p and "STALE" in p for p in problems)


def test_override_sensors_are_critical_sensors():
    """Every override key must be a real critical sensor (catch renames going stale)."""
    assert set(SENSOR_TICK_CEILING_OVERRIDES) <= CRITICAL_SENSORS


def test_fresh_sensor_tick_not_flagged():
    assert stale_sensor_ticks({_A_CRITICAL: 5 * 60}, max_age_s=3600) == []


def test_none_age_not_flagged():
    """No tick data (never evaluated / DB reset) is the STOPPED check's job, not staleness."""
    assert stale_sensor_ticks({_A_CRITICAL: None}, max_age_s=3600) == []


def test_non_critical_sensor_staleness_ignored():
    assert stale_sensor_ticks({"some_random_sensor": 999 * 60}, max_age_s=3600) == []


class _TickInstance:
    """Instance stand-in whose all_instigator_state() returns sensor states carrying an
    instigator_data.last_tick_timestamp (epoch seconds)."""

    def __init__(self, name_to_last_tick_ts):
        self._states = [
            SimpleNamespace(
                instigator_name=n,
                instigator_data=SimpleNamespace(last_tick_timestamp=ts),
            )
            for n, ts in name_to_last_tick_ts.items()
        ]

    def all_instigator_state(self, *a, **k):  # noqa: ARG002
        return self._states


def test_stale_running_sensor_ticks_reads_instance():
    now = 1_000_000.0
    inst = _TickInstance({
        _A_CRITICAL: now - 2 * 3600,            # 2h stale → flagged
        "not_a_critical_sensor": now - 10 * 3600,  # ignored (not critical)
    })
    problems = stale_running_sensor_ticks(inst, now, max_age_s=3600)
    assert any(_A_CRITICAL in p for p in problems)
    assert all("not_a_critical_sensor" not in p for p in problems)


def test_stale_running_sensor_ticks_fresh_clean():
    now = 1_000_000.0
    inst = _TickInstance({_A_CRITICAL: now - 60})  # 1 min ago
    assert stale_running_sensor_ticks(inst, now, max_age_s=3600) == []
