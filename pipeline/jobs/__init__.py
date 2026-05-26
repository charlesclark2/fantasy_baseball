from pipeline.jobs.snowflake_check import snowflake_check_job
from pipeline.jobs.daily_ingestion_job import daily_ingestion_job
from pipeline.jobs.intraday_jobs import (
    intraday_schedule_job,
    intraday_weather_job,
    odds_snapshot_job,
)

all_jobs = [
    snowflake_check_job,
    daily_ingestion_job,
    odds_snapshot_job,
    intraday_weather_job,
    intraday_schedule_job,
]
