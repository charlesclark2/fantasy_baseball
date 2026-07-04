from dagster import DefaultScheduleStatus, ScheduleDefinition

from pipeline.jobs.daily_ingestion_job import daily_ingestion_job

daily_ingestion_schedule = ScheduleDefinition(
    job=daily_ingestion_job,
    cron_schedule="0 12 * * *",  # 08:00 EDT (UTC-4)
    # E11.23: default_status=RUNNING so the PRIMARY serving pipeline self-starts on the box
    # (and after any Dagster-DB reset / re-host — the INC-16 class) instead of silently booting
    # STOPPED. check_monitors_healthy_op (in the daily job) alarms if it is ever manually STOPPED.
    default_status=DefaultScheduleStatus.RUNNING,
)
