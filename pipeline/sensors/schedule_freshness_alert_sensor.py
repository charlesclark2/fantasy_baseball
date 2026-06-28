"""schedule_freshness_alert_sensor.py — E11.8

HARD-ALERT for schedule / game-data staleness (serving-critical path).

INC-7 showed that a feed can silently die for weeks if the only monitoring is a
WARN-tier op (check_data_freshness) that is always swallowed by try/except.
This sensor fills that gap for schedule data: `stg_statsapi_games` must have
today's rows by a reasonable deadline on any game day; if it doesn't, a stale
schedule means predictions were either skipped or scored against yesterday's
game list — both silent corruptions.

Two gates (raise on either):

  1. SCHEDULE STALE — `monthly_schedule` hasn't been refreshed since > 4h ago
     on a game day. Both the Railway schedule_capture cron (every 30 min) and the
     daily_ingestion_job ingest_statsapi_schedule op must be dead for this to fire.
     Checked after 14:30 UTC (2.5h after the daily job fires) to avoid false alarms
     during the job's normal run window.

  2. NO GAMES LOADED — monthly_schedule shows R-games today but stg_statsapi_games
     has 0 rows for today. The dbt staging build didn't complete (or failed), or the
     raw ingest never landed. Either way predictions would run blind.

Transient Snowflake failures → SkipReason (don't page on our own infra blip).
Real staleness / missing data persists across ticks → fires once per day.

Off-season: when monthly_schedule has no upcoming R-games the sensor skips quietly.
"""
from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

from dagster import SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

_MART_SCHEMA = "baseball_data.betting"
_RAW_SCHEMA  = "baseball_data.statsapi"

# Only evaluate in the window after the daily job has had time to complete.
# Daily job fires at 12:00 UTC; ingest_statsapi_schedule is step 3, typically
# done by 12:05–12:10. 14:30 is generous and avoids false alarms mid-run.
_WINDOW_OPEN_UTC  = time(14, 30)
_WINDOW_CLOSE_UTC = time(20, 0)   # give up; if still missing, pregame_alert_sensor covers it

# Schedule is ingested every 30 min by Railway cron + daily job; 4h stale means
# both paths have been down for ≥ 7 missed Railway fires or the daily job failed.
_STALE_HOURS = 4


def _get_connection():
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _monthly_schedule_age_hours(conn) -> float | None:
    """Minutes since the last monthly_schedule row was written (via month_end_date)."""
    cur = conn.cursor()
    # month_end_date is a DATE; cast to TIMESTAMP_NTZ to get DATEDIFF in hours.
    cur.execute(
        f"SELECT DATEDIFF('hour', MAX(month_end_date::TIMESTAMP_NTZ), SYSDATE()) "
        f"FROM {_RAW_SCHEMA}.monthly_schedule"
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _monthly_schedule_has_today(conn, today: str) -> bool:
    """Does monthly_schedule contain R-games for today?"""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM {_RAW_SCHEMA}.monthly_schedule,
             LATERAL FLATTEN(input => json_field:dates) d,
             LATERAL FLATTEN(input => d.value:games) g
        WHERE g.value:officialDate::DATE = %s
          AND g.value:gameType::VARCHAR = 'R'
        """,
        [today],
    )
    return int(cur.fetchone()[0]) > 0


def _stg_games_has_today(conn, today: str) -> bool:
    """Does the dbt-built stg_statsapi_games table have any rows for today?"""
    cur = conn.cursor()
    cur.execute(
        f"SELECT COUNT(*) FROM {_MART_SCHEMA}.stg_statsapi_games "
        f"WHERE official_date = %s AND game_type = 'R'",
        [today],
    )
    return int(cur.fetchone()[0]) > 0


@sensor(minimum_interval_seconds=1800)  # check every ~30 min, aligned to capture cadence
def schedule_freshness_alert_sensor(context: SensorEvaluationContext):
    """HARD-alert when schedule/game data is stale on a game day.

    Raises (fails the tick → Dagster email-on-failure) if:
      (a) monthly_schedule age > _STALE_HOURS on a game day, OR
      (b) monthly_schedule shows games today but stg_statsapi_games has none.

    Transient Snowflake → SkipReason.  Off-day / outside alert window → SkipReason.
    One alert per calendar day (cursor deduplication).
    """
    now_utc = datetime.now(UTC)
    current_time = now_utc.time().replace(tzinfo=None)
    today = date.today().isoformat()

    # Deduplicate: only raise once per day.
    if context.cursor == today:
        yield SkipReason(f"Already alerted for schedule staleness on {today}.")
        return

    if current_time < _WINDOW_OPEN_UTC:
        yield SkipReason(
            f"Before alert window ({current_time.strftime('%H:%M')} UTC < "
            f"{_WINDOW_OPEN_UTC.strftime('%H:%M')} UTC) — daily job still running."
        )
        return

    if current_time > _WINDOW_CLOSE_UTC:
        yield SkipReason(
            f"Window closed at {_WINDOW_CLOSE_UTC.strftime('%H:%M')} UTC "
            f"without detecting staleness — pregame_alert_sensor covers the tail."
        )
        return

    try:
        conn = _get_connection()
    except Exception as exc:
        yield SkipReason(f"Snowflake connection failed (transient): {exc}")
        return

    problems: list[str] = []
    try:
        # Gate 1: monthly_schedule freshness (raw ingest).
        age = _monthly_schedule_age_hours(conn)
        has_games_in_raw = _monthly_schedule_has_today(conn, today)

        if has_games_in_raw:
            if age is None:
                problems.append(
                    "monthly_schedule is EMPTY — schedule ingest never ran or table was dropped"
                )
            elif age > _STALE_HOURS:
                problems.append(
                    f"monthly_schedule is STALE: {age:.1f}h since last write "
                    f"(> {_STALE_HOURS}h). Both Railway schedule_capture cron AND "
                    f"daily_ingestion_job ingest_statsapi_schedule are likely down."
                )

            # Gate 2: stg_statsapi_games completeness (dbt model).
            if not _stg_games_has_today(conn, today):
                problems.append(
                    f"stg_statsapi_games has 0 rows for {today} even though "
                    f"monthly_schedule contains today's R-games. The dbt staging build "
                    f"(dbt_daily_build / schedule_capture dbt trigger) did not complete."
                )
    finally:
        conn.close()

    if not problems:
        yield SkipReason(
            f"Schedule data healthy for {today}: monthly_schedule {age:.1f}h old, "
            f"stg_statsapi_games populated."
        )
        return

    context.update_cursor(today)
    msg = (
        f"SCHEDULE DATA ALERT ({today}): "
        + "; ".join(problems)
        + ". Check the host-cron schedule_capture (capture.crontab), the daily_ingestion_job "
        "ingest_statsapi_schedule op, and the Dagit run history. "
        "Manual fix: uv run python scripts/ingest_statsapi.py schedule"
    )
    # INC-16-P6: email directly (Dagster+ tick-failure alerting is gone post-cutover);
    # still raise so the tick is marked FAILED in Dagit.
    from pipeline.utils.alerting import send_alert
    send_alert("Schedule data stale/missing", msg, severity="CRITICAL", dedup_key="schedule_freshness")
    raise Exception(msg)
