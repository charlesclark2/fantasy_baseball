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
  2. QUOTA — the Odds-API `x-requests-remaining` header (logged on every call into
     `mlb_odds_raw`) on the MAIN 100k key below _QUOTA_FLOOR is early warning that the $59/mo
     plan's monthly credits are nearly exhausted (or a renewal gap), BEFORE capture fails.

     ⚠️ TWO-KEY DESIGN: by design the live path drains the cheap STARTER key (500/mo) FIRST,
     then falls back to the MAIN key (100k/mo). So the captured `x_requests_remaining` is the
     starter key's (≤500) for the first ~500 credits of each month, then the main key's. We must
     NOT alert on the starter drain (≤500 is expected every month) — only on the MAIN key getting
     low. The discriminator is magnitude: any reading > _STARTER_CAP (500) is unambiguously the
     main key (starter is capped at 500). We watch the latest main-key reading only; during the
     pure-starter phase there is no recent main-key row → skip (main key healthy/unused).
     (A cleaner long-term fix would tag the key identity in the capture row; magnitude suffices
     while the starter cap is a fixed 500.) Historical loads use the main key but write a
     different table (odds_snapshots_historical), so they don't pollute this live signal.

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
_STARTER_CAP = 500       # starter key's monthly allotment; readings ≤ this are the STARTER key
                         # (expected drain every month) — alert only on MAIN-key readings (> this)
# MAIN plan = 100k credits/mo; normal main burn ≈8k/mo, so the main key's `remaining` sits
# ~90-100k all month. A MAIN-key reading < 10k means a non-reset/lapsed renewal or a runaway
# burn (10×+ normal) — genuinely alert-worthy, with weeks of lead time before 100k is exhausted.
# The window where we alert is (_STARTER_CAP, _QUOTA_FLOOR) = (500, 10000). Re-tune if plan sizes change.
_QUOTA_FLOOR = 10000

# UTC-on-UTC: mlb_odds_raw.ingestion_ts is TIMESTAMP_NTZ written in UTC; SYSDATE() is current
# UTC as NTZ, so DATEDIFF avoids any LTZ/session-tz ambiguity.
_FRESHNESS_SQL = (
    "SELECT DATEDIFF('minute', MAX(ingestion_ts), SYSDATE()) AS age_min, "
    "MAX(ingestion_ts) AS latest FROM baseball_data.oddsapi.mlb_odds_raw"
)
# Latest MAIN-key reading only (remaining > starter cap). Read from raw (current every capture,
# no rebuild lag). NULL result = main key not recently used (pure-starter phase) → no quota concern.
_QUOTA_SQL = (
    "SELECT x_requests_remaining FROM baseball_data.oddsapi.mlb_odds_raw "
    "WHERE x_requests_remaining > %s "
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
            cur.execute(_QUOTA_SQL, [_STARTER_CAP])
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

    # 2. quota — MAIN key only (readings > _STARTER_CAP). The starter key's expected ≤500 drain
    #    is filtered out in SQL, so this never false-pages during the monthly starter phase. NULL
    #    = main key not recently used (pure-starter phase) → no concern.
    remaining = quota_row[0] if quota_row else None
    if remaining is not None and remaining < _QUOTA_FLOOR:
        problems.append(
            f"LOW main-key quota: x_requests_remaining={remaining} (< {_QUOTA_FLOOR}) — "
            f"Odds-API 100k monthly credits nearly exhausted / renewal gap"
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
