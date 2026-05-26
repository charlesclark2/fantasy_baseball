from dagster import in_process_executor, job

from pipeline.ops.sensor_ops import (
    lineup_dbt_clv_rebuild,
    lineup_dbt_staging_rebuild,
    lineup_ingest_schedule,
    lineup_odds_snapshot,
    lineup_predict,
    pregame_dbt_clv_rebuild,
    pregame_odds_snapshot,
)


@job(executor_def=in_process_executor)
def lineup_monitor_job():
    s1 = lineup_ingest_schedule()
    s2 = lineup_dbt_staging_rebuild(start=s1)
    s3 = lineup_predict(start=s2)
    s4 = lineup_odds_snapshot(start=s3)
    lineup_dbt_clv_rebuild(start=s4)


@job(executor_def=in_process_executor)
def pregame_snapshot_job():
    start = pregame_odds_snapshot()
    pregame_dbt_clv_rebuild(start=start)
