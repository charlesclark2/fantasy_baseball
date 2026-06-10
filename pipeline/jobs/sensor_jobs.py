from dagster import in_process_executor, job

from pipeline.ops.sensor_ops import (
    catchup_dbt_rebuild,
    catchup_ingest_statcast,
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
from pipeline.ops.daily_ingestion_ops import (
    compute_eb_bullpen_posteriors_op,
    compute_elo,
    compute_lineup_posteriors_op,
    compute_starter_posteriors_op,
    dbt_umpire_feature_rebuild,
    predict_today_morning,
    update_matchup_cell_posteriors_op,
    update_player_posteriors_op,
    update_team_posteriors_op,
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


@job(executor_def=in_process_executor)
def statcast_catchup_job():
    # Fired by statcast_freshness_sensor once yesterday's Statcast finally lands.
    # Ingest pitches → rebuild the pitch-derived marts/feature store → refresh the
    # posteriors that depend on the now-complete games → fold them into the feature
    # marts → re-score today so the live slate reflects the caught-up data.
    s1 = catchup_ingest_statcast()
    s2 = catchup_dbt_rebuild(start=s1)
    eb = compute_eb_bullpen_posteriors_op(start=s2)
    pp = update_player_posteriors_op(start=eb)
    pt = update_team_posteriors_op(start=pp)
    pm = update_matchup_cell_posteriors_op(start=pt)
    ps = compute_starter_posteriors_op(start=pm)
    pl = compute_lineup_posteriors_op(start=ps)
    # A2.3: recompute Elo on the now-current mart_game_results (compute_elo reads
    # mart_game_results, which is pitch-derived and therefore lagged by the same
    # Statcast availability gap this catch-up resolves). Without this, Elo stays
    # stale until the next 07:00 daily run even after the catch-up self-heals.
    el = compute_elo(start=pl)
    s3 = dbt_umpire_feature_rebuild(start=el)
    predict_today_morning(start=s3)
