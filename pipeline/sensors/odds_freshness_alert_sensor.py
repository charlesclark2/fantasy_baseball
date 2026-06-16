"""odds_freshness_alert_sensor.py — Story 12.3.7 / A2.18.

The single-vendor safety net. After retiring Parlay (2026-06-16), The Odds API is the SOLE
live odds source — which is exactly the single-vendor exposure that caused the 12.3.3 incident
(Parlay's quota silently stepped 100k→500 for ~2 weeks with NO alarm, an unrecoverable data
loss). This sensor is the alarm Parlay never had: it fails its tick (firing Dagster+'s standard
alert) when the Railway → Odds-API capture goes stale OR the monthly request quota runs low.

Two gates (raise on either):
  1. STALENESS — the Railway cron writes `oddsapi.mlb_odds_raw` every 30 min, 24/7 (the `odds`
     endpoint always returns the upcoming slate, in-season). If the newest ingestion is older
     than _STALE_MINUTES (≈3 missed fires) the capture is down — Railway crashed, key expired,
     or the plan lapsed.
  2. QUOTA — the Odds-API `x-requests-remaining` header (logged on each call into
     `mart_odds_outcomes`) below _QUOTA_FLOOR is early warning that the $59/mo plan's monthly
     credits are nearly exhausted (or a renewal gap), BEFORE capture actually fails.

Transient Snowflake/connection errors → SkipReason (don't page on our own infra blip; matches
odds_current_rebuild_sensor / pregame_snapshot_sensor). A genuine stale/low-quota condition
persists across ticks and will fire as soon as the connection recovers.

NOTE (off-season): in-season this is safe to run 24/7. If captures legitimately stop (All-Star
break / off-season → 0 upcoming events → ingestion_ts stops advancing), add a "games in the next
N days" guard before the staleness raise to avoid false pages.
"""
from __future__ import annotations

from dagster import SensorEvaluationContext, SkipReason, sensor

# ── thresholds ────────────────────────────────────────────────────────────────
_STALE_MINUTES = 90      # ≈3 missed 30-min Railway fires → capture is down
# $59/mo plan = 100k credits/mo; normal burn ≈8.6k/mo (6cr × ~48 calls/day), so `remaining`
# should sit ~90-100k all month. A reading < 10k means a non-reset/lapsed renewal or a runaway
# burn (10×+ normal) — genuinely alert-worthy, with weeks of lead time before 100k is exhausted.
# Stays false-alarm-free even at 3× cadence (~26k/mo). Re-tune if the plan size changes.
_QUOTA_FLOOR = 10000

# UTC-on-UTC: mlb_odds_raw.ingestion_ts is TIMESTAMP_NTZ written in UTC; SYSDATE() is current
# UTC as NTZ, so DATEDIFF avoids any LTZ/session-tz ambiguity.
_FRESHNESS_SQL = (
    "SELECT DATEDIFF('minute', MAX(ingestion_ts), SYSDATE()) AS age_min, "
    "MAX(ingestion_ts) AS latest FROM baseball_data.oddsapi.mlb_odds_raw"
)
_QUOTA_SQL = (
    "SELECT x_requests_remaining, ingestion_ts FROM baseball_data.betting.mart_odds_outcomes "
    "WHERE source_system = 'odds_api' AND x_requests_remaining IS NOT NULL "
    "ORDER BY ingestion_ts DESC LIMIT 1"
)


@sensor(minimum_interval_seconds=1800)  # every ~30 min, aligned to the capture cadence
def odds_freshness_alert_sensor(context: SensorEvaluationContext):
    """Alert if the Odds-API live capture goes stale or its monthly quota runs low."""
    from betting_ml.utils.data_loader import get_snowflake_connection

    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_FRESHNESS_SQL)
            age_min, latest = cur.fetchone()
            cur.execute(_QUOTA_SQL)
            quota_row = cur.fetchone()
            cur.close()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — transient infra; skip, retry next tick
        yield SkipReason(f"Could not read odds freshness/quota (transient): {exc}")
        return

    problems: list[str] = []

    # 1. staleness
    if latest is None:
        problems.append("oddsapi.mlb_odds_raw is EMPTY — capture never landed")
    elif age_min is not None and age_min > _STALE_MINUTES:
        problems.append(
            f"STALE capture: newest mlb_odds_raw ingest {age_min} min ago "
            f"(> {_STALE_MINUTES}) — Railway cron down / key expired / plan lapsed"
        )

    # 2. quota
    remaining = quota_row[0] if quota_row else None
    if remaining is not None and remaining < _QUOTA_FLOOR:
        problems.append(
            f"LOW quota: x_requests_remaining={remaining} (< {_QUOTA_FLOOR}) — "
            f"Odds-API monthly credits nearly exhausted / renewal gap"
        )

    if problems:
        raise Exception(
            "ODDS CAPTURE ALERT (single-vendor Odds-API): "
            + "; ".join(problems)
            + ". Check the Railway odds_capture service logs + the Odds-API plan/key. "
            "Manual failover: re-enable the Parlay odds_snapshot schedules in "
            "pipeline/schedules/intraday_schedules.py (defs retained) if Parlay is re-subscribed."
        )

    context.log.info(
        "Odds capture healthy: last ingest %s min ago; x_requests_remaining=%s",
        age_min, remaining,
    )
    yield SkipReason(
        f"Odds capture healthy: {age_min} min since last ingest, quota {remaining}."
    )
