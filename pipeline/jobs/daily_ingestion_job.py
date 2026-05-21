from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    backfill_prediction_log,
    check_data_freshness,
    check_prediction_coverage,
    compute_elo,
    compute_model_health,
    dbt_daily_build,
    dbt_mart_prediction_clv,
    dbt_umpire_feature_rebuild,
    ingest_action_network,
    ingest_fangraphs_catcher_framing,
    ingest_fangraphs_hitting_leaderboard,
    ingest_fangraphs_stuff_plus,
    ingest_oaa,
    ingest_odds_api_events,
    ingest_odds_api_odds,
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
)


@job(executor_def=in_process_executor)
def daily_ingestion_job():
    s1 = ingest_odds_api_events()
    s2 = ingest_odds_api_odds(start=s1)
    s3 = ingest_parlay_events(start=s2)
    s4 = ingest_parlay_canonical_events(start=s3)
    s5 = ingest_parlay_odds(start=s4)
    s6 = ingest_action_network(start=s5)
    s7 = ingest_statcast(start=s6)
    s8 = ingest_statsapi_schedule(start=s7)
    s9 = ingest_weather(start=s8)
    s10 = ingest_umpires_early(start=s9)
    s11 = ingest_fangraphs_stuff_plus(start=s10)
    s12 = ingest_fangraphs_catcher_framing(start=s11)
    s13 = ingest_fangraphs_hitting_leaderboard(start=s12)
    s14 = ingest_transactions(start=s13)
    s15 = ingest_oaa(start=s14)
    s16 = compute_elo(start=s15)
    s17 = check_data_freshness(start=s16)
    s18 = dbt_daily_build(start=s17)
    s19 = ingest_umpires_late(start=s18)
    s20 = dbt_umpire_feature_rebuild(start=s19)
    s21 = predict_today_morning(start=s20)
    s22 = check_prediction_coverage(start=s21)
    s23 = dbt_mart_prediction_clv(start=s22)
    s24 = compute_model_health(start=s23)
    backfill_prediction_log(start=s24)
