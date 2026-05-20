from dagster import ScheduleDefinition

from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

daily_ingestion_schedule = ScheduleDefinition(
    job=daily_ingestion_job,
    cron_schedule="0 12 * * *",  # 08:00 EDT (UTC-4)
)
