"""schedule_freshness_alert_sensor.py — E11.8

HARD-ALERT for schedule / game-data staleness (serving-critical path).

INC-7 showed that a feed can silently die for weeks if the only monitoring is a
WARN-tier op (check_data_freshness) that is always swallowed by try/except.
This sensor fills that gap for schedule data: `stg_statsapi_games` must have
today's rows by a reasonable deadline on any game day; if it doesn't, a stale
schedule means predictions were either skipped or scored against yesterday's
game list — both silent corruptions.

Two gates (raise on either):

  1. SCHEDULE STALE — the raw `monthly_schedule` lakehouse export hasn't been refreshed
     since > _STALE_HOURS ago on a game day (a feed-death backstop; see the threshold note
     below). Both the host-cron schedule_capture and the daily_ingestion_job ingest path
     (→ the S3 re-export) must be dead for this to fire. Checked after 14:30 UTC (2.5h after
     the daily job fires) to avoid false alarms during the job's normal run window.

  2. NO GAMES LOADED — monthly_schedule shows R-games today but stg_statsapi_games
     has 0 rows for today. The dbt/lakehouse staging build didn't complete (or failed), or
     the raw ingest never landed. Either way predictions would run blind.

Transient lakehouse/S3 failures → SkipReason (don't page on our own infra blip).
Real staleness / missing data persists across ticks → fires once per day.

Off-season: when monthly_schedule has no upcoming R-games the sensor skips quietly.

E11.1-W12: reads moved off Snowflake to the S3 lakehouse via DuckDB. Gate 1's freshness
signal is now `monthly_schedule.ingestion_ts` (the raw-export heartbeat the 30-min intraday
re-export advances) instead of the weak `month_end_date` proxy (a calendar boundary that
could never detect mid-month feed stalls). The raw-vs-flattened independence the two gates
rely on is preserved: gate 1 reads `lakehouse_raw/monthly_schedule` (the raw JSON), gate 2
reads `lakehouse/stg_statsapi_games` (the flattened build) — distinct objects, distinct
writers.
"""
from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

from dagster import DefaultSensorStatus, SensorEvaluationContext, SkipReason, sensor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Only evaluate in the window after the daily job has had time to complete.
# Daily job fires at 12:00 UTC; ingest_statsapi_schedule is step 3, typically
# done by 12:05–12:10. 14:30 is generous and avoids false alarms mid-run.
_WINDOW_OPEN_UTC  = time(14, 30)
_WINDOW_CLOSE_UTC = time(20, 0)   # give up; if still missing, pregame_alert_sensor covers it

# Gate-1 staleness threshold for the raw monthly_schedule S3 export.
# E11.1-W12 cadence note: the host-cron schedule_capture exports monthly_schedule → S3 on a
# MORNING-weighted 30-min cadence (observed ~09:00–14:00 UTC) plus the ~12:00-UTC daily job —
# it is NOT a flat 24/7 30-min feed. So a healthy feed can legitimately read ~6h old at the
# 20:00-UTC window close. The pre-W12 Snowflake gate-1 measured `month_end_date` (a calendar
# boundary that is ALWAYS "fresh" while the current month is loaded), so it never detected
# staleness at all; a tight S3 threshold here would be a NEW false-alarm source. 12h is set so
# gate-1 fires only on an UNAMBIGUOUS feed death (no morning export at all → age ≫ 12h even at
# window open) while tolerating the morning-weighted cadence. Gate-2 (raw-has-today vs
# stg-missing) is the sharp, threshold-free daily-continuity signal. Operator: retighten toward
# 4h once/if the box's schedule-export cron is confirmed to run continuously through 20:00 UTC.
_STALE_HOURS = 12


def _get_connection():
    from betting_ml.utils.lakehouse_monitor import duck
    return duck()


def _monthly_schedule_age_hours(conn) -> float | None:
    """Hours since the last raw monthly_schedule snapshot was exported to S3 (via
    ingestion_ts, the raw-export heartbeat). ingestion_ts is a VARCHAR ISO timestamp (UTC)."""
    from betting_ml.utils.lakehouse_monitor import lh_raw

    row = conn.execute(
        f"SELECT MAX(ingestion_ts::timestamp) "
        f"FROM read_parquet('{lh_raw('monthly_schedule')}', union_by_name=true)"
    ).fetchone()
    if not row or row[0] is None:
        return None
    now_utc_naive = datetime.now(UTC).replace(tzinfo=None)
    return (now_utc_naive - row[0]).total_seconds() / 3600.0


def _monthly_schedule_has_today(conn, today: str) -> bool:
    """Does the raw monthly_schedule JSON contain R-games for today? json_field is a VARCHAR
    JSON blob ({"dates":[{"games":[{officialDate,gameType,...}]}]}); unnest the nested arrays
    across all snapshots (a boolean count — snapshot dedup is irrelevant for >0)."""
    from betting_ml.utils.lakehouse_monitor import lh_raw

    (n,) = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM read_parquet('{lh_raw('monthly_schedule')}', union_by_name=true) ms,
             UNNEST(json_extract(ms.json_field, '$.dates[*].games[*]')) AS t(g)
        WHERE json_extract_string(g, '$.officialDate') = ?
          AND json_extract_string(g, '$.gameType') = 'R'
        """,
        [today],
    ).fetchone()
    return int(n) > 0


def _stg_games_has_today(conn, today: str) -> bool:
    """Does the built stg_statsapi_games table have any rows for today?"""
    from betting_ml.utils.lakehouse_monitor import lh

    (n,) = conn.execute(
        f"SELECT COUNT(*) FROM read_parquet('{lh('stg_statsapi_games')}', union_by_name=true) "
        f"WHERE official_date = ? AND game_type = 'R'",
        [today],
    ).fetchone()
    return int(n) > 0


# E11.23: default_status=RUNNING — self-start on the box / after a DB reset (INC-16 class).
@sensor(minimum_interval_seconds=1800, default_status=DefaultSensorStatus.RUNNING)  # check every ~30 min, aligned to capture cadence
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
        yield SkipReason(f"Lakehouse (DuckDB/S3) connection failed (transient): {exc}")
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
