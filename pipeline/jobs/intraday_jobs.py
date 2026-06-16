from dagster import in_process_executor, job

from pipeline.ops.intraday_ops import (
    check_games_today,
    intraday_lineup_rebuild,
    intraday_schedule_capture,
    intraday_weather_capture,
    odds_oddsapi_dbt_rebuild,
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
# on a Railway cron container (off the Dagster+ bill); `odds_rebuild_sensor` fires this job
# only when new rows land in oddsapi.mlb_odds_raw, so Dagster pays for the (quick) warehouse
# rebuild, never the I/O-bound HTTP poll.
@job(executor_def=in_process_executor, tags={"concurrency_group": "odds_oddsapi_rebuild"})
def odds_oddsapi_rebuild_job():
    odds_oddsapi_dbt_rebuild()


@job(executor_def=in_process_executor)
def intraday_weather_job():
    intraday_weather_capture()


@job(executor_def=in_process_executor)
def intraday_schedule_job():
    done = intraday_schedule_capture()
    intraday_lineup_rebuild(start=done)
