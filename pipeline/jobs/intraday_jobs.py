from dagster import in_process_executor, job

from pipeline.ops.intraday_ops import (
    intraday_lineup_rebuild,
    intraday_public_betting_capture,
    intraday_schedule_capture,
    intraday_weather_capture,
    odds_clv_dbt_rebuild,
    odds_current_dbt_rebuild,
    write_book_odds_op,
)


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
    dbt_done = odds_current_dbt_rebuild()
    write_book_odds_op(start=dbt_done)


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


# E11.1-W11-D addendum — hourly ActionNetwork public-betting capture (the E13.16 public-%→line-movement
# precursor). One op, its own job so it can be scheduled independently (hourly, pre-game window). Boots
# STOPPED per repo convention — a merge is a no-op until the operator toggles it on.
@job(executor_def=in_process_executor)
def intraday_public_betting_job():
    intraday_public_betting_capture()
