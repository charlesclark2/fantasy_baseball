from dagster import in_process_executor, job

from pipeline.ops.sensor_ops import (
    lineup_compute_posteriors,
    lineup_dbt_clv_rebuild,
    lineup_dbt_feature_rebuild,
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
    # A1.11 Stage 4 — recompute EB lineup posteriors on the now-confirmed lineups
    # and rebuild the lineup/game features before predicting, so the post-lineup
    # prediction reflects the actual batters (not the morning best-effort pass).
    s2b = lineup_compute_posteriors(start=s2)
    s2c = lineup_dbt_feature_rebuild(start=s2b)
    s3 = lineup_predict(start=s2c)
    s4 = lineup_odds_snapshot(start=s3)
    lineup_dbt_clv_rebuild(start=s4)


@job(executor_def=in_process_executor)
def pregame_snapshot_job():
    start = pregame_odds_snapshot()
    pregame_dbt_clv_rebuild(start=start)
