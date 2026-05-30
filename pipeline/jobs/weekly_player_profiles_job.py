from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import ingest_player_profiles_update


@job(executor_def=in_process_executor)
def weekly_player_profiles_job():
    ingest_player_profiles_update()
