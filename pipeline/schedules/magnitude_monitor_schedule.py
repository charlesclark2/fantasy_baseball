from dagster import ScheduleDefinition

from pipeline.jobs.magnitude_monitor_job import magnitude_monitor_job

# Mondays 12:00 UTC (08:00 EDT) — weekly accrual check for Story 28.3.
# Runs after the weekly_ml_job (10:00 UTC) so any new stacking weights are
# already applied before the monitor logs its snapshot.
magnitude_monitor_schedule = ScheduleDefinition(
    job=magnitude_monitor_job,
    cron_schedule="0 12 * * 1",
    execution_timezone="UTC",
)
