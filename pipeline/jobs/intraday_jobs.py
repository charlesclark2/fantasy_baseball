from dagster import in_process_executor, job

from pipeline.ops.intraday_ops import (
    check_games_today,
    intraday_lineup_rebuild,
    intraday_schedule_capture,
    intraday_weather_capture,
    odds_clv_dbt_rebuild,
    odds_current_dbt_rebuild,
    odds_snapshot_dbt_rebuild,
    odds_snapshot_ingest,
)


# Story A2.16 extension (2026-06-15) — cap at ONE concurrent run. 17 cron schedules
# point at this job (10:00-22:00 EDT, some only 10 min apart); the `concurrency_group`
# tag is auto-limited to 1 by the deployment_settings run_queue applyLimitPerUniqueValue
# rule, so a slow/late run QUEUES the next schedule instead of stacking + contending on
# the same Parlay tables (pairs with the new _POLL_TIMEOUT 600s op ceiling in
# intraday_ops, which bounds the 2026-06-15 odds_snapshot_1955_edt wedge).
@job(executor_def=in_process_executor, tags={"concurrency_group": "odds_snapshot"})
def odds_snapshot_job():
    has_games = check_games_today()
    start = odds_snapshot_ingest(has_games=has_games)
    odds_snapshot_dbt_rebuild(start=start)


# Story 12.3.7 / A2.18 — dbt rebuild for the ODDS API live path. The capture itself runs
# every 30 min on a Railway cron container (off the Dagster+ bill); Dagster only pays for
# the warehouse rebuild, decoupled from capture cadence. Split into two by freshness need:
#
#   odds_current_rebuild_job  — LIGHT (stg + mart_odds_outcomes). Fired by
#     odds_current_rebuild_sensor on a dynamic game-hours window (hourly from first-pitch
#     -3h to last first pitch + a near-close tick). ~12-14 game-day rebuilds, 0 on dark days.
#   odds_clv_rebuild_job      — FULL post-hoc CLV/line-movement marts. Run ONCE/day post-game
#     by odds_clv_rebuild_schedule (the closing line doesn't exist until first pitch).
@job(executor_def=in_process_executor, tags={"concurrency_group": "odds_oddsapi_rebuild"})
def odds_current_rebuild_job():
    odds_current_dbt_rebuild()


@job(executor_def=in_process_executor, tags={"concurrency_group": "odds_oddsapi_rebuild"})
def odds_clv_rebuild_job():
    odds_clv_dbt_rebuild()


@job(executor_def=in_process_executor)
def intraday_weather_job():
    intraday_weather_capture()


@job(executor_def=in_process_executor)
def intraday_schedule_job():
    done = intraday_schedule_capture()
    intraday_lineup_rebuild(start=done)
