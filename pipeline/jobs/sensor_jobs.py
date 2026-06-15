from dagster import in_process_executor, job

from pipeline.ops.sensor_ops import (
    catchup_dbt_rebuild,
    catchup_ingest_statcast,
    lineup_dbt_clv_rebuild,
    lineup_dbt_feature_rebuild,
    lineup_dbt_staging_rebuild,
    lineup_ingest_schedule,
    lineup_ingest_umpires,
    lineup_odds_snapshot,
    lineup_predict,
    pregame_dbt_clv_rebuild,
    pregame_odds_snapshot,
)
from pipeline.ops.daily_ingestion_ops import (
    compute_elo,
    dbt_build_bullpen_posteriors_op,
    dbt_umpire_feature_rebuild,
    predict_today_morning,
    update_matchup_cell_posteriors_op,
    update_player_posteriors_op,
    update_team_posteriors_op,
    write_serving_store_op,
)


# Story A2.16 (2026-06-15) — the `concurrency_group` run tag caps each sensor job at
# ONE concurrent run via the deployment-settings run_queue.tag_concurrency_limits rule
# (applyLimitPerUniqueValue: each distinct group value → limit 1). The lineup-monitor
# sensor fires every 10 min in the active window; before this, a single wedged run
# (incident 2026-06-15: lineup_dbt_clv_rebuild hung) let the sensor stack 3 overlapping
# runs that contended on the same Snowflake tables and multiplied compute. With the
# limit, overlapping triggers QUEUE behind the in-flight run instead of running
# concurrently (and the new 30-min subprocess timeout bounds the wedge that starts it).
# NB: RUN-level concurrency — distinct from the op-pool `dagster/concurrency_key` tag.
@job(executor_def=in_process_executor, tags={"concurrency_group": "lineup_monitor"})
def lineup_monitor_job():
    s1 = lineup_ingest_schedule()
    # Story 30.5 — ingest today's HP-umpire assignment here (afternoon, when MLB
    # has posted it), idempotently, so the confirmed-lineup re-score reflects the
    # actual umpire. The 07:00 daily ops run too early to ever catch it.
    s1u = lineup_ingest_umpires(start=s1)
    s2 = lineup_dbt_staging_rebuild(start=s1u)
    # Story A2.11 — the EB lineup/starter posteriors are now dbt models built INSIDE
    # lineup_dbt_feature_rebuild (incremental → recomputes the confirmed-lineup games)
    # before the features that ref() them, so the post-lineup prediction reflects the
    # actual batters. (Was a separate lineup_compute_posteriors Python op.)
    s2c = lineup_dbt_feature_rebuild(start=s2)
    s3 = lineup_predict(start=s2c)
    s4 = lineup_odds_snapshot(start=s3)
    clv = lineup_dbt_clv_rebuild(start=s4)
    write_serving_store_op(predict_done=clv)


@job(executor_def=in_process_executor, tags={"concurrency_group": "pregame_snapshot"})
def pregame_snapshot_job():
    start = pregame_odds_snapshot()
    pregame_dbt_clv_rebuild(start=start)


@job(executor_def=in_process_executor, tags={"concurrency_group": "statcast_catchup"})
def statcast_catchup_job():
    # Fired by statcast_freshness_sensor once yesterday's Statcast finally lands.
    # Ingest pitches → rebuild the pitch-derived marts/feature store → refresh the
    # posteriors that depend on the now-complete games → fold them into the feature
    # marts → re-score today so the live slate reflects the caught-up data.
    s1 = catchup_ingest_statcast()
    s2 = catchup_dbt_rebuild(start=s1)
    # Story A2.11 — bullpen EB posteriors (dbt) before the sequential team update.
    eb = dbt_build_bullpen_posteriors_op(start=s2)
    pp = update_player_posteriors_op(start=eb)
    pt = update_team_posteriors_op(start=pp)
    pm = update_matchup_cell_posteriors_op(start=pt)
    # A2.3: recompute Elo on the now-current mart_game_results (compute_elo reads
    # mart_game_results, which is pitch-derived and therefore lagged by the same
    # Statcast availability gap this catch-up resolves). Without this, Elo stays
    # stale until the next 07:00 daily run even after the catch-up self-heals.
    # Story A2.11 — starter/lineup EB posteriors are now built inside
    # dbt_umpire_feature_rebuild (after the sequential ops), so no separate ops here.
    el = compute_elo(start=pm)
    s3 = dbt_umpire_feature_rebuild(start=el)
    s4 = predict_today_morning(start=s3)
    write_serving_store_op(predict_done=s4)
