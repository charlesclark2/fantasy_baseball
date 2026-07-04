"""
pregame_alert_sensor.py — A1.5

Fires an alert 45 minutes before today's earliest scheduled game if lineup-confirmed
predictions are not yet available.

Alert mechanism: raises an exception, which marks the sensor tick as FAILED
and triggers the standard email-on-failure notification.

Cursor stores the last-alerted date (ISO string) so at most one alert fires
per calendar day even if multiple ticks land in the 25-minute alert window.

E11.1-W12: reads moved off Snowflake to the S3 lakehouse via DuckDB (instance-role
credential_chain — Snowflake-free). The schedule read is `stg_statsapi_games` (on S3).
The pipeline-health read changed SOURCE: the old `betting_ml.pipeline_status` state table
is NOT on S3 (it is W13 serving-state), so health is now judged directly from the OUTPUT —
`daily_model_predictions` post_lineup rows with `lineup_confirmed = TRUE`. This is a more
direct check of exactly what pregame_alert guards (are lineup-confirmed predictions live
before first pitch) than the intermediate status flag, and it uses an already-on-S3 table.
The "morning pipeline ran at all" half of the old check is covered by morning_watchdog_sensor.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from dagster import DefaultSensorStatus, SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Alert fires when now_utc is in [first_pitch - ALERT_LEAD, first_pitch - ALERT_CLOSE].
_ALERT_LEAD_MIN = 55    # open the window this many minutes before first pitch
_ALERT_CLOSE_MIN = 30   # close the window (predictions should be live by this point)


def _get_earliest_first_pitch_utc(today: str) -> datetime | None:
    from betting_ml.utils.lakehouse_monitor import duck, lh, to_utc_datetime

    conn = duck()
    try:
        # game_date reads back as an ISO VARCHAR from the lakehouse (INC-23); MIN on ISO strings
        # still gives the earliest first-pitch instant — to_utc_datetime coerces it (never .tzinfo it).
        row = conn.execute(
            f"""
            SELECT MIN(game_date) AS earliest_utc
            FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true)
            WHERE official_date = ? AND game_type = 'R'
            """,
            [today],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return to_utc_datetime(row[0])
    finally:
        conn.close()


def _get_post_lineup_status(today: str) -> dict:
    """Lineup-confirmed prediction coverage for today, from the daily_model_predictions
    OUTPUT (the on-S3 replacement for the betting_ml.pipeline_status state table). Returns
    n_post_lineup (post_lineup rows) and n_confirmed (those flagged lineup_confirmed)."""
    from betting_ml.utils.lakehouse_monitor import duck, lh

    conn = duck()
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS n_post_lineup,
                   COUNT(*) FILTER (WHERE lineup_confirmed) AS n_confirmed
            FROM read_parquet('{lh('daily_model_predictions')}', union_by_name=true)
            WHERE score_date = ? AND prediction_type = 'post_lineup'
            """,
            [today],
        ).fetchone()
    finally:
        conn.close()
    return {"n_post_lineup": int(row[0] or 0), "n_confirmed": int(row[1] or 0)}


def _get_n_scheduled(today: str) -> int:
    from betting_ml.utils.lakehouse_monitor import duck, lh

    conn = duck()
    try:
        (n,) = conn.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true)
            WHERE official_date = ? AND game_type = 'R'
            """,
            [today],
        ).fetchone()
        return int(n)
    finally:
        conn.close()


# E11.23: default_status=RUNNING — self-start on the box / after a DB reset (INC-16 class).
@sensor(minimum_interval_seconds=600, default_status=DefaultSensorStatus.RUNNING)
def pregame_alert_sensor(context: SensorEvaluationContext):
    """
    Alert sensor: fires 45 minutes before the earliest scheduled game if no
    lineup-confirmed predictions are available yet for today.
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

    # Inside the window: check lineup-confirmed prediction coverage (the OUTPUT-side health
    # signal — the on-S3 replacement for the betting_ml.pipeline_status state table).
    try:
        status = _get_post_lineup_status(today)
        n_scheduled = _get_n_scheduled(today)
    except Exception as exc:
        yield SkipReason(f"Lakehouse status check failed — skipping alert tick: {exc}")
        return

    n_post_lineup = status["n_post_lineup"]
    n_confirmed = status["n_confirmed"]

    # Healthy = at least one lineup-confirmed post_lineup prediction exists. By 55–30 min
    # before the EARLIEST first pitch the earliest game(s) must have confirmed lineups, so a
    # confirmed prediction must exist; later games whose lineups post nearer their own first
    # pitch legitimately lag, so we don't require full-slate coverage (which would false-page).
    is_healthy = n_confirmed > 0

    if is_healthy:
        yield SkipReason(
            f"Pipeline healthy: {n_confirmed} lineup-confirmed post_lineup prediction(s) "
            f"({n_post_lineup} post_lineup rows / {n_scheduled} scheduled)."
        )
        return

    # Alert.
    context.update_cursor(today)
    raise Exception(
        f"⚠️ Diamond Edge pipeline alert — {today}: "
        f"NO lineup-confirmed predictions yet "
        f"(post_lineup_rows={n_post_lineup}, confirmed={n_confirmed}, "
        f"scheduled={n_scheduled}). The lineup-confirmed predict pass has not produced "
        f"picks within the pre-game window. Check Dagit for the lineup_predict run."
    )
