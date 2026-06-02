from dagster import ScheduleDefinition

from pipeline.jobs.clv_monitoring_job import clv_monitoring_job

weekly_clv_monitoring_schedule = ScheduleDefinition(
    job=clv_monitoring_job,
    cron_schedule="0 12 * * 1",  # 08:00 EDT every Monday
    execution_timezone="UTC",
)
