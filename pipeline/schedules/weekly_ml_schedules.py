from dagster import ScheduleDefinition

from pipeline.jobs.weekly_ml_job import weekly_meta_model_job, weekly_ml_job

# Mondays 10:00 UTC (06:00 EDT). Weights only change on sub-model retrain / signal
# promotion, so a weekly cadence is sufficient (Epic 9 Story 9.6 / Epic O.3).
weekly_ml_schedule = ScheduleDefinition(
    job=weekly_ml_job,
    cron_schedule="0 10 * * 1",
    execution_timezone="UTC",
)

# Wednesdays 10:00 UTC — offset from the Monday stacking-weights job to spread the
# Snowflake compute load (the MCMC retrain is the slow op). Epic O.5 / Story 12.9.
weekly_meta_model_schedule = ScheduleDefinition(
    job=weekly_meta_model_job,
    cron_schedule="0 10 * * 3",
    execution_timezone="UTC",
)
