"""
statcast_freshness_sensor.py — pipeline SLA hardening (post-incident 2026-06-10).

Root cause it addresses: Baseball Savant publishes day-D Statcast later than the
07:00-ET daily run can reliably see it, so `ingest_statcast` lands nothing for
"yesterday" and the whole pitch-derived chain (mart_game_results → feature store
→ every _one_day_ago posterior) silently runs a day behind. The daily run exits
green, so it hid for days.

This sensor makes the cadence data-driven instead of clock-driven: it polls for
yesterday's pitch data and, the moment Savant has it, fires `statcast_catchup_job`
to land it + make today's slate whole — with a hard deadline before first pitch.

Cadence (every 30 min; all date/time reasoning in US/Eastern = the baseball day):
  - Before _EARLIEST ET            → skip (yesterday's data won't be up yet).
  - No regular-season games yesterday → skip (nothing to wait for).
  - Yesterday's pitch data present   → skip ("fresh").
  - Missing & > _DEADLINE_LEAD before today's first pitch → RunRequest the
        catch-up (hourly run_key ⇒ bounded retries; self-stops once data lands).
  - Missing & within _DEADLINE_LEAD of first pitch → log ERROR + SkipReason. This
        is the loud signal the daily run never had; attach a Dagster+ alert policy
        to this sensor to page on it.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dagster import RunRequest, SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.jobs.sensor_jobs import statcast_catchup_job

_ET = ZoneInfo("America/New_York")
_EARLIEST = time(4, 0)              # don't bother before 04:00 ET
_DEADLINE_LEAD = timedelta(hours=2)  # must be in ≥ 2h before today's first pitch
_DEFAULT_DEADLINE = time(13, 0)     # used when today has no games to anchor on

_MART_SCHEMA = "baseball_data.betting"
_SAVANT_SCHEMA = "baseball_data.savant"


def _conn():
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _had_rs_games(conn, d: date) -> bool:
    cur = conn.cursor()
    cur.execute(
        f"SELECT COUNT(*) FROM {_MART_SCHEMA}.stg_statsapi_games "
        f"WHERE official_date = %s AND game_type = 'R'",
        [d.isoformat()],
    )
    return int(cur.fetchone()[0]) > 0


def _pitches_present(conn, d: date) -> bool:
    # game_date is stored as TEXT (ISO yyyy-mm-dd) in the raw Savant table.
    cur = conn.cursor()
    cur.execute(
        f"SELECT COUNT(*) FROM {_SAVANT_SCHEMA}.batter_pitches WHERE game_date = %s",
        [d.isoformat()],
    )
    return int(cur.fetchone()[0]) > 0


def _first_pitch_et(conn, d: date) -> datetime | None:
    """Earliest first-pitch for date d, as an aware US/Eastern datetime.
    game_datetime is the StatsAPI UTC instant; treat a naive value as UTC."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT MIN(game_datetime) FROM {_MART_SCHEMA}.stg_statsapi_games "
        f"WHERE official_date = %s AND game_type = 'R'",
        [d.isoformat()],
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    val = row[0]
    if isinstance(val, str):
        val = datetime.fromisoformat(val.replace("Z", "+00:00"))
    if val.tzinfo is None:
        val = val.replace(tzinfo=ZoneInfo("UTC"))
    return val.astimezone(_ET)


@sensor(job=statcast_catchup_job, minimum_interval_seconds=1800)
def statcast_freshness_sensor(context: SensorEvaluationContext):
    now_et = datetime.now(_ET)
    today = now_et.date()
    yesterday = today - timedelta(days=1)

    if now_et.time() < _EARLIEST:
        yield SkipReason("Before 04:00 ET — yesterday's Statcast won't be published yet.")
        return

    try:
        conn = _conn()
    except Exception as e:  # transient connection issue — don't error the sensor
        yield SkipReason(f"Snowflake connection failed: {e}")
        return
    try:
        if not _had_rs_games(conn, yesterday):
            yield SkipReason(f"No regular-season games on {yesterday} — nothing to wait for.")
            return
        if _pitches_present(conn, yesterday):
            yield SkipReason(f"Statcast for {yesterday} already present — fresh.")
            return

        first_pitch = _first_pitch_et(conn, today)
    finally:
        conn.close()

    deadline = (first_pitch - _DEADLINE_LEAD) if first_pitch else \
        datetime.combine(today, _DEFAULT_DEADLINE, tzinfo=_ET)

    if now_et >= deadline:
        fp = first_pitch.strftime("%H:%M ET") if first_pitch else "n/a"
        context.log.error(
            f"[SLA BREACH] Statcast for {yesterday} still not published and we are "
            f"within {_DEADLINE_LEAD} of today's first pitch ({fp}). Today's slate will "
            f"score WITHOUT {yesterday}'s completed games. Manual check of Baseball Savant "
            f"/ savant_ingestion.py needed."
        )
        yield SkipReason(f"PAST DEADLINE: {yesterday} Statcast missing within "
                         f"{_DEADLINE_LEAD} of first pitch — see ERROR log / alert.")
        return

    # Missing, before the deadline → fire the catch-up. Hourly run_key bounds
    # retries to ~1/hour; once the catch-up lands the data the next tick sees it
    # present and skips.
    run_key = f"statcast-catchup-{yesterday}-{now_et:%H}"
    context.log.info(f"Statcast for {yesterday} not yet landed; firing catch-up (run_key={run_key}).")
    yield RunRequest(
        run_key=run_key,
        tags={"triggered_by": "statcast_freshness_sensor", "catchup_date": yesterday.isoformat()},
    )
