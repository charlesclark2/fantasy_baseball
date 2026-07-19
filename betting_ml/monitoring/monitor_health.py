"""E11.23 — the silently-not-running detector (import-safe core).

The E11.1 cutover left a class of RUNTIME failures CI can't see (it mocks all IO): intraday
refresh jobs shipped GATED-OFF and serving-critical sensors/schedules that boot STOPPED, so they
SILENTLY NEVER RUN — odds froze 3 days with NO alert; the lineup monitor was dead 2 days. The
``default_status=RUNNING`` flips on those sensors/schedules are the structural cure; the pieces
here are the DETECTOR that ``pipeline.ops.daily_ingestion_ops.check_monitors_healthy_op`` runs
inside every daily job (ALERT-tier: emails CRITICAL, never HALTs).

Lives in ``betting_ml`` (NOT ``pipeline``) on purpose: importing the ``pipeline`` package triggers
``pipeline/__init__.py`` → the dbt manifest read, which is absent in the fast-test gate. Keeping the
pure logic + the critical sets here makes them unit-testable without the manifest. The intended-state
table in ``services/dagster/aws/BOX_OPERATIONS.md §10`` is the source of truth — extend both together.
"""
from __future__ import annotations

# Serving-critical sensors that must always be RUNNING (each carries default_status=RUNNING).
CRITICAL_SENSORS = frozenset({
    "run_failure_alert_sensor",
    "odds_current_rebuild_sensor",
    "odds_freshness_alert_sensor",
    "schedule_freshness_alert_sensor",
    "statcast_freshness_sensor",
    "lineup_monitor_sensor",
    "pregame_alert_sensor",
    "conviction_pick_alert_sensor",
    "morning_watchdog_sensor",
    "clv_alert_sensor",
    "model_health_alert_sensor",
})
# Serving-critical schedules that must always be RUNNING (each carries default_status=RUNNING).
# The intraday_schedule_capture_* / intraday_public_betting_* schedules are deliberately EXCLUDED —
# they stay operator-gated (double-ingest / paid-capture opt-in), so a STOPPED one is expected.
CRITICAL_SCHEDULES = frozenset({
    "daily_ingestion_job_schedule",
    "odds_clv_rebuild_daily",
    # INC-32 (2026-07-18): lineup_monitor_schedule_daytime/_overnight were REMOVED from the critical
    # set. They were added 2026-07-07 as a backstop when the lineup_monitor_SENSOR was unreliable,
    # but running both drivers double-fires lineup_monitor_job (a check-then-act race → 2 runs per
    # confirmed lineup → doubled dbt-runner contention). The sensor is now the SOLE driver
    # (un-wedgeable + tick-staleness heartbeat), and these schedules boot STOPPED as a manual
    # fallback — so a STOPPED one is EXPECTED and must NOT page.
})
# Intraday / cutover env flags that must be permanently "1" on the box. An unset one = a
# silently-gated-off refresh (3 of the 5 incidents). Scoped to the flags we are confident should
# be ON everywhere post-cutover; extend this AND the BOX_OPERATIONS.md §10 table together.
REQUIRED_INTRADAY_FLAGS = (
    "SCHEDULE_LAKEHOUSE_INTRADAY",   # INC-22: keeps served game-state / lineups fresh
    "LINEUP_INTRADAY_S3_REBUILD",    # intraday lineup re-score reaches the S3 feature parquet
    "W8A_LAKEHOUSE_S3",              # feature-layer + EB served from S3 (cut over 2026-06-30)
    "W8B_LAKEHOUSE_S3",              # serving aggregator served from S3 (cut over 2026-06-30)
    # E11.20-COST (2026-07-16): W7B was found NEVER SET on the box — intended ON since the
    # W7b cutover, but unenforced flags silently drift (daily predict/serving read SF for
    # weeks, and the intraday book-odds --s3 gate stayed off). Enforce both like W8A/W8B.
    "W7A_LAKEHOUSE_S3",              # matchup/posterior/profile consumer reads from S3 (W7a)
    "W7B_LAKEHOUSE_S3",              # predict_today / write_serving_store read from S3 (W7b)
)


def flag_problems(env) -> list[str]:
    """Pure: the required intraday/cutover flags in ``env`` that are not set to '1' (a
    silently-gated-off refresh). Never raises."""
    return [
        f"required intraday flag not set to '1': {flag} (={env.get(flag)!r})"
        for flag in REQUIRED_INTRADAY_FLAGS
        if env.get(flag) != "1"
    ]


# INC-32 (2026-07-18) — the "daemon stopped mid-slate" detector. E11.23's stopped-instigator check
# only catches a sensor that was EXPLICITLY toggled STOPPED. It is BLIND to a sensor that is still
# nominally RUNNING but whose evaluations have STALLED — e.g. a sensor eval that blocked forever on an
# un-timed-out subprocess (the lineup_monitor.py wedge that stopped ALL sensor evals ~21:30Z on 7/17,
# so 7 of 15 games never got post_lineup). The daemon evaluates every RUNNING sensor continuously and
# records a tick each time (even a SkipReason ticks), so a critical sensor whose most-recent tick is
# hours old means the daemon/sensor is wedged. Default staleness ceiling 60 min (env-overridable):
# every critical sensor ticks well inside that when the daemon is healthy (the slowest floor is the
# 10-min lineup monitor).
import os as _os

_SENSOR_TICK_STALE_SECONDS = float(_os.environ.get("SENSOR_TICK_STALE_SECONDS", "3600"))

# 2026-07-19 — per-sensor ceiling overrides. The flat 60-min ceiling assumed every critical
# sensor ticks continuously, but clv_alert_sensor and model_health_alert_sensor declare
# minimum_interval_seconds=86400 (once per day BY DESIGN) — so the flat ceiling paged a false
# "STALE (1152 min)" CRITICAL every single day at the daily-job check. A once-daily sensor is
# only genuinely stale past ~a day + slack; 30h tolerates daily-job drift without masking a
# real multi-day wedge. Keep this map in sync with any sensor whose minimum_interval exceeds
# the flat ceiling.
SENSOR_TICK_CEILING_OVERRIDES: dict = {
    "clv_alert_sensor": 30 * 3600.0,
    "model_health_alert_sensor": 30 * 3600.0,
}


def stale_sensor_ticks(last_tick_ages: dict, max_age_s: float) -> list[str]:
    """Pure: the CRITICAL_SENSORS whose most-recent tick is older than the sensor's ceiling —
    ``SENSOR_TICK_CEILING_OVERRIDES`` when present (once-daily sensors), else ``max_age_s``.

    ``last_tick_ages`` maps sensor name → seconds since its last tick. A ``None`` age (no tick data
    / never evaluated) is NOT flagged here — 'never started' is the STOPPED check's job; this
    targets 'was ticking, now stalled'. Sorted, deterministic, never raises."""
    problems: list[str] = []
    for name in sorted(CRITICAL_SENSORS):
        age = last_tick_ages.get(name)
        ceiling = SENSOR_TICK_CEILING_OVERRIDES.get(name, max_age_s)
        if age is not None and age > ceiling:
            problems.append(
                f"critical sensor tick STALE: {name} (last tick {age / 60:.0f} min ago > "
                f"{ceiling / 60:.0f} min ceiling) — the sensor-daemon has likely wedged and "
                f"evaluations STOPPED (INC-32)"
            )
    return problems


def stale_running_sensor_ticks(instance, now_ts: float,
                               max_age_s: float | None = None) -> list[str]:
    """The CRITICAL_SENSORS registered in ``instance`` whose last tick is older than ``max_age_s``
    (default ``_SENSOR_TICK_STALE_SECONDS``). Reads each sensor's persisted ``last_tick_timestamp``
    and defers the decision to the pure ``stale_sensor_ticks``. Best-effort — may raise on an
    ephemeral/CI instance; the caller treats introspection as best-effort (ALERT-tier)."""
    if max_age_s is None:
        max_age_s = _SENSOR_TICK_STALE_SECONDS
    ages: dict = {}
    # Match by name (CRITICAL_SENSORS are all sensors; names are unambiguous) — avoids depending on
    # the exact InstigatorType import path across Dagster versions.
    for state in instance.all_instigator_state():
        name = getattr(state, "instigator_name", None)
        if name not in CRITICAL_SENSORS:
            continue
        data = getattr(state, "instigator_data", None)
        last_tick = getattr(data, "last_tick_timestamp", None) if data is not None else None
        ages[name] = (now_ts - last_tick) if last_tick else None
    return stale_sensor_ticks(ages, max_age_s)


def stopped_critical_instigators(instance) -> list[str]:
    """The serving-critical sensors/schedules that are EXPLICITLY STOPPED in the Dagster instance.
    ``all_instigator_state(STOPPED)`` returns only instigators with a persisted STOPPED row (someone
    toggled it off); a self-starting default-RUNNING instigator that was never toggled has NO row →
    not flagged (correct: it is running by default). May raise (ephemeral/CI instance) — the caller
    treats introspection as best-effort."""
    from dagster._core.scheduler.instigation import InstigatorStatus

    stopped = {
        s.instigator_name
        for s in instance.all_instigator_state(instigator_statuses={InstigatorStatus.STOPPED})
    }
    return [
        f"critical instigator STOPPED in Dagster: {name}"
        for name in sorted((CRITICAL_SENSORS | CRITICAL_SCHEDULES) & stopped)
    ]
