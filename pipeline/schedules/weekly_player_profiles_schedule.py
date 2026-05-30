from dagster import ScheduleDefinition

from pipeline.jobs.weekly_player_profiles_job import weekly_player_profiles_job

weekly_player_profiles_schedule = ScheduleDefinition(
    job=weekly_player_profiles_job,
    cron_schedule="0 10 * * 0",  # 06:00 EDT every Sunday
    execution_timezone="UTC",
)
