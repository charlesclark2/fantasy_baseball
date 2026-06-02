from pipeline.jobs.snowflake_check import snowflake_check_job
from pipeline.jobs.daily_ingestion_job import daily_ingestion_job
from pipeline.jobs.intraday_jobs import (
    intraday_schedule_job,
    intraday_weather_job,
    odds_snapshot_job,
)
from pipeline.jobs.sensor_jobs import lineup_monitor_job, pregame_snapshot_job
from pipeline.jobs.weekly_player_profiles_job import weekly_player_profiles_job
from pipeline.schedules.historical_matches_schedule import historical_matches_catchup_job
from pipeline.jobs.clv_monitoring_job import clv_monitoring_job

all_jobs = [
    snowflake_check_job,
    daily_ingestion_job,
    odds_snapshot_job,
    intraday_weather_job,
    intraday_schedule_job,
    lineup_monitor_job,
    pregame_snapshot_job,
    weekly_player_profiles_job,
    historical_matches_catchup_job,
    clv_monitoring_job,
]
