"""
pregame_alert_sensor.py — A1.5

Fires an alert 45 minutes before today's earliest scheduled game if the
morning pipeline has not completed successfully or lineup-confirmed predictions
are not yet available.

Alert mechanism: raises an exception, which marks the sensor tick as FAILED
and triggers Dagster Cloud's standard email-on-failure notification.

Cursor stores the last-alerted date (ISO string) so at most one alert fires
per calendar day even if multiple ticks land in the 25-minute alert window.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from dagster import SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_ML_SCHEMA = "baseball_data.betting_ml"
_MART_SCHEMA = "baseball_data.betting"

# Alert fires when now_utc is in [first_pitch - ALERT_LEAD, first_pitch - ALERT_CLOSE].
_ALERT_LEAD_MIN = 55    # open the window this many minutes before first pitch
_ALERT_CLOSE_MIN = 30   # close the window (predictions should be live by this point)


def _get_earliest_first_pitch_utc(today: str) -> datetime | None:
    from betting_ml.utils.data_loader import get_snowflake_connection

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT MIN(CONVERT_TIMEZONE('UTC', game_date)) AS earliest_utc
            FROM {_MART_SCHEMA}.stg_statsapi_games
            WHERE official_date = %s AND game_type = 'R'
            """,
            [today],
        )
        row = cur.fetchone()
        if row is None or row[0] is None:
            return None
        return row[0].replace(tzinfo=UTC) if row[0].tzinfo is None else row[0].astimezone(UTC)
    finally:
        conn.close()


def _get_pipeline_status(today: str) -> dict | None:
    from betting_ml.utils.data_loader import get_snowflake_connection

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT pipeline_status, n_games_scored, lineup_confirmed_complete_ts,
                   predict_today_complete_ts
            FROM {_ML_SCHEMA}.pipeline_status
            WHERE run_date = %s
            """,
            [today],
        )
        cols = [d[0].lower() for d in cur.description]
        row = cur.fetchone()
        return dict(zip(cols, row)) if row else None
    finally:
        conn.close()


def _get_n_scheduled(today: str) -> int:
    from betting_ml.utils.data_loader import get_snowflake_connection

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COUNT(*) FROM {_MART_SCHEMA}.stg_statsapi_games
            WHERE official_date = %s AND game_type = 'R'
            """,
            [today],
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()


@sensor(minimum_interval_seconds=600)
def pregame_alert_sensor(context: SensorEvaluationContext):
    """
    Alert sensor: fires 45 minutes before the earliest scheduled game if
    pipeline_status != 'complete' or lineup predictions are missing.
    """
    today = date.today().isoformat()

    # Deduplicate: only one alert per calendar day.
    if context.cursor == today:
        yield SkipReason(f"Already alerted for {today}.")
        return

    try:
        first_pitch_utc = _get_earliest_first_pitch_utc(today)
    except Exception as exc:
        yield SkipReason(f"Could not fetch first pitch time: {exc}")
        return

    if first_pitch_utc is None:
        yield SkipReason(f"No regular-season games scheduled for {today}.")
        return

    now_utc = datetime.now(UTC)
    window_open = first_pitch_utc - timedelta(minutes=_ALERT_LEAD_MIN)
    window_close = first_pitch_utc - timedelta(minutes=_ALERT_CLOSE_MIN)

    if now_utc < window_open:
        yield SkipReason(
            f"Alert window not yet open. Opens at {window_open.strftime('%H:%M')} UTC "
            f"(first pitch {first_pitch_utc.strftime('%H:%M')} UTC)."
        )
        return

    if now_utc > window_close:
        yield SkipReason(
            f"Alert window closed at {window_close.strftime('%H:%M')} UTC "
            f"without triggering — pipeline was healthy or game already started."
        )
        return

    # Inside the window: check pipeline status.
    try:
        status_row = _get_pipeline_status(today)
        n_scheduled = _get_n_scheduled(today)
    except Exception as exc:
        yield SkipReason(f"Snowflake status check failed — skipping alert tick: {exc}")
        return

    pipeline_status = status_row["pipeline_status"] if status_row else "missing"
    n_scored = status_row["n_games_scored"] if status_row else 0
    lineup_confirmed = (
        status_row["lineup_confirmed_complete_ts"] is not None if status_row else False
    )

    is_healthy = (pipeline_status == "complete") and lineup_confirmed

    if is_healthy:
        yield SkipReason(
            f"Pipeline healthy: status={pipeline_status}, "
            f"n_games={n_scored}/{n_scheduled}, lineup_confirmed=True."
        )
        return

    # Alert.
    context.update_cursor(today)
    raise Exception(
        f"⚠️ Diamond Edge pipeline alert — {today}: "
        f"pipeline_status={pipeline_status}, "
        f"n_games_scored={n_scored}/{n_scheduled}, "
        f"lineup_confirmed={str(lineup_confirmed).lower()}. "
        f"Check Dagster Cloud for details."
    )
