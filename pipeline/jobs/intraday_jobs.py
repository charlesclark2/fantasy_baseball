from dagster import in_process_executor, job

from pipeline.ops.intraday_ops import (
    check_games_today,
    intraday_schedule_capture,
    intraday_weather_capture,
    odds_snapshot_dbt_rebuild,
    odds_snapshot_ingest,
)


@job(executor_def=in_process_executor)
def odds_snapshot_job():
    has_games = check_games_today()
    start = odds_snapshot_ingest(has_games=has_games)
    odds_snapshot_dbt_rebuild(start=start)


@job(executor_def=in_process_executor)
def intraday_weather_job():
    intraday_weather_capture()


@job(executor_def=in_process_executor)
def intraday_schedule_job():
    intraday_schedule_capture()
