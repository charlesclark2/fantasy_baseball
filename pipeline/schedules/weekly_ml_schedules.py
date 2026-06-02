from dagster import ScheduleDefinition

from pipeline.jobs.weekly_ml_job import weekly_ml_job

# Mondays 10:00 UTC (06:00 EDT) — matches the Bayesian meta-model retraining
# window (Epic 12 Story 12.4). Weights only change on sub-model retrain / signal
# promotion, so a weekly cadence is sufficient (Epic 9 Story 9.6 / Epic O.3).
weekly_ml_schedule = ScheduleDefinition(
    job=weekly_ml_job,
    cron_schedule="0 10 * * 1",
    execution_timezone="UTC",
)
