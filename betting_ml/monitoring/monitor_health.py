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
    # 2026-07-07: the reliable 30-min cron backstop for the lineup re-score (the
    # lineup_monitor_sensor tick was unreliable → repeated manual kicks). Serving-critical —
    # a manual STOP means post_lineup predictions silently stop refreshing. Two exprs cover
    # the game-day window (cron can't wrap midnight).
    "lineup_monitor_schedule_daytime",
    "lineup_monitor_schedule_overnight",
})
# Intraday / cutover env flags that must be permanently "1" on the box. An unset one = a
# silently-gated-off refresh (3 of the 5 incidents). Scoped to the flags we are confident should
# be ON everywhere post-cutover; extend this AND the BOX_OPERATIONS.md §10 table together.
REQUIRED_INTRADAY_FLAGS = (
    "SCHEDULE_LAKEHOUSE_INTRADAY",   # INC-22: keeps served game-state / lineups fresh
    "LINEUP_INTRADAY_S3_REBUILD",    # intraday lineup re-score reaches the S3 feature parquet
    "W8A_LAKEHOUSE_S3",              # feature-layer + EB served from S3 (cut over 2026-06-30)
    "W8B_LAKEHOUSE_S3",              # serving aggregator served from S3 (cut over 2026-06-30)
)


def flag_problems(env) -> list[str]:
    """Pure: the required intraday/cutover flags in ``env`` that are not set to '1' (a
    silently-gated-off refresh). Never raises."""
    return [
        f"required intraday flag not set to '1': {flag} (={env.get(flag)!r})"
        for flag in REQUIRED_INTRADAY_FLAGS
        if env.get(flag) != "1"
    ]


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
