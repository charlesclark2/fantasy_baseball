"""
morning_watchdog_sensor.py — A1.6

Belt-and-suspenders watchdog for daily_ingestion_job. The scheduled run fires
at 12:00 UTC; if something prevents it from starting (agent unavailability,
code-location load failure, scheduler miss), this sensor catches the gap.

Logic (evaluated every 15 minutes):
  - Before 13:30 UTC: skip (job has time to complete normally).
  - After 15:00 UTC: skip (window expired; manual intervention if needed).
  - Between 13:30–15:00 UTC: query daily_model_predictions for today's morning
    rows. If none exist AND regular-season games are scheduled today, emit a
    RunRequest to trigger daily_ingestion_job.

run_key=f"morning-watchdog-{today}" guarantees the sensor fires at most once
per calendar day, even across multiple ticks in the 13:30–15:00 window.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

from dagster import DefaultSensorStatus, RunRequest, SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

_WINDOW_START = time(13, 30)  # 13:30 UTC — 90 min after scheduled start
_WINDOW_END = time(15, 0)     # 15:00 UTC — give up; page on-call if needed

# E11.1-W12: reads moved off Snowflake to the S3 lakehouse via DuckDB (instance-role
# credential_chain — Snowflake-free). daily_model_predictions (W7b) + stg_statsapi_games
# are both already on S3.


def _has_morning_predictions(today: str) -> bool:
    from betting_ml.utils.lakehouse_monitor import duck, lh

    conn = duck()
    try:
        (n,) = conn.execute(
            f"""
            SELECT COUNT(*) FROM read_parquet('{lh('daily_model_predictions')}', union_by_name=true)
            WHERE score_date = ? AND prediction_type = 'morning'
            """,
            [today],
        ).fetchone()
        return int(n) > 0
    finally:
        conn.close()


def _has_games_today(today: str) -> bool:
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
        return int(n) > 0
    finally:
        conn.close()


# E11.23: default_status=RUNNING — self-start on the box / after a DB reset (INC-16 class).
@sensor(job=daily_ingestion_job, minimum_interval_seconds=900,
        default_status=DefaultSensorStatus.RUNNING)
def morning_watchdog_sensor(context: SensorEvaluationContext):
    """
    Fallback trigger: fires daily_ingestion_job if morning predictions are
    missing by 13:30 UTC on a game day. At most one trigger per calendar day.
    """
    now_utc = datetime.now(UTC)
    current_time = now_utc.time().replace(tzinfo=None)
    today = date.today().isoformat()

    if current_time < _WINDOW_START:
        yield SkipReason(
            f"Too early ({current_time.strftime('%H:%M')} UTC) — "
            f"watchdog window opens at {_WINDOW_START.strftime('%H:%M')} UTC."
        )
        return

    if current_time > _WINDOW_END:
        yield SkipReason(
            f"Window closed ({current_time.strftime('%H:%M')} UTC > "
            f"{_WINDOW_END.strftime('%H:%M')} UTC). "
            f"If the job still hasn't run, manual intervention is required."
        )
        return

    # Inside the 13:30–15:00 window: check for morning predictions.
    try:
        if _has_morning_predictions(today):
            yield SkipReason(
                f"Morning predictions already present for {today} — pipeline ran on schedule."
            )
            return
    except Exception as exc:
        yield SkipReason(f"Lakehouse check failed — skipping watchdog tick: {exc}")
        return

    # No morning predictions yet; confirm there are games before triggering.
    try:
        if not _has_games_today(today):
            yield SkipReason(
                f"No regular-season games scheduled for {today} — off-day, skip trigger."
            )
            return
    except Exception as exc:
        yield SkipReason(f"Lakehouse schedule check failed — skipping watchdog tick: {exc}")
        return

    context.log.warning(
        "morning_watchdog_sensor: no morning predictions for %s by %s UTC. "
        "Triggering daily_ingestion_job as fallback.",
        today,
        current_time.strftime("%H:%M"),
    )
    yield RunRequest(
        run_key=f"morning-watchdog-{today}",
        tags={
            "triggered_by": "morning_watchdog_sensor",
            "watchdog_trigger_utc": current_time.strftime("%H:%M"),
        },
    )
