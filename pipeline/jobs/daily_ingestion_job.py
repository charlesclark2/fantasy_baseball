from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    backfill_prediction_log,
    check_data_freshness,
    check_prediction_coverage,
    compute_elo,
    compute_model_health,
    dbt_daily_build,
    dbt_lineup_feature_rebuild,
    dbt_mart_prediction_clv,
    dbt_pregame_odds_rebuild,
    dbt_umpire_feature_rebuild,
    ingest_action_network,
    ingest_fangraphs_catcher_framing,
    ingest_fangraphs_hitting_leaderboard,
    ingest_fangraphs_stuff_plus,
    ingest_oaa,
    ingest_sprint_speed,
    ingest_parlay_canonical_events,
    ingest_parlay_events,
    ingest_parlay_odds,
    ingest_statcast,
    ingest_statsapi_schedule,
    ingest_transactions,
    ingest_umpires_early,
    ingest_umpires_late,
    ingest_weather,
    predict_today_morning,
    update_lineup_state_scd2,
    update_market_features_scd2,
)


@job(executor_def=in_process_executor)
def daily_ingestion_job():
    s1 = ingest_parlay_events()
    s2 = ingest_parlay_canonical_events(start=s1)
    s3 = ingest_parlay_odds(start=s2)
    s4 = ingest_action_network(start=s3)
    s5 = ingest_statcast(start=s4)
    s6 = ingest_statsapi_schedule(start=s5)
    s7 = ingest_weather(start=s6)
    s8 = ingest_umpires_early(start=s7)
    s9 = ingest_fangraphs_stuff_plus(start=s8)
    s10 = ingest_fangraphs_catcher_framing(start=s9)
    s11 = ingest_fangraphs_hitting_leaderboard(start=s10)
    s11b = ingest_sprint_speed(start=s11)
    s12 = ingest_transactions(start=s11b)
    s13 = ingest_oaa(start=s12)
    s14 = compute_elo(start=s13)
    s15 = check_data_freshness(start=s14)
    s16 = dbt_daily_build(start=s15)
    # SCD-2 update: mart_odds_outcomes is now fresh; update market features and
    # rebuild feature_pregame_odds_features before the prediction step.
    s16b = update_market_features_scd2(start=s16)
    s16c = dbt_pregame_odds_rebuild(start=s16b)
    # SCD-2 update: monthly_schedule is now fresh; update lineup state and
    # rebuild feature_pregame_lineup_features before the prediction step.
    s16d = update_lineup_state_scd2(start=s16c)
    s16e = dbt_lineup_feature_rebuild(start=s16d)
    s17 = ingest_umpires_late(start=s16e)
    s18 = dbt_umpire_feature_rebuild(start=s17)
    s19 = predict_today_morning(start=s18)
    s20 = check_prediction_coverage(start=s19)
    s21 = dbt_mart_prediction_clv(start=s20)
    s22 = compute_model_health(start=s21)
    backfill_prediction_log(start=s22)
