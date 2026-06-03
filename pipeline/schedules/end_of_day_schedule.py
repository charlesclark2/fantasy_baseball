"""End-of-day posterior update schedule (Epic O.4 / Epic 16.4).

Fires at 05:00 UTC (01:00 EDT) daily — gives yesterday's game results time to land
in mart_game_results and gives statcast/pitch data time to ingest, while completing
well before the 12:00 UTC morning daily_ingestion_job consumes the updated posteriors.
"""

from dagster import ScheduleDefinition

from pipeline.jobs.end_of_day_job import end_of_day_job

end_of_day_schedule = ScheduleDefinition(
    job=end_of_day_job,
    cron_schedule="0 5 * * *",  # 05:00 UTC (01:00 EDT)
    name="end_of_day_posteriors",
)
