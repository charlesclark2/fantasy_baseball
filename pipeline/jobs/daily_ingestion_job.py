from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    backfill_prediction_log,
    check_data_freshness,
    check_prediction_coverage,
    compute_eb_bullpen_posteriors_op,
    compute_elo,
    compute_lineup_posteriors_op,
    compute_model_health,
    compute_starter_posteriors_op,
    dbt_daily_build,
    dbt_lineup_feature_rebuild,
    dbt_mart_prediction_clv,
    dbt_pregame_odds_rebuild,
    dbt_sub_model_signals_rebuild,
    dbt_umpire_feature_rebuild,
    generate_bullpen_signals_op,
    generate_defense_quality_signals_op,
    generate_env_state_signals_op,
    generate_matchup_signals_op,
    generate_offense_signals_op,
    generate_run_env_signals_op,
    generate_starter_ip_signals_op,
    generate_starter_signals_op,
    signal_freshness_check,
    signal_freshness_failure_hook,
    update_pipeline_status,
    update_player_posteriors_op,
    update_team_posteriors_op,
    update_matchup_cell_posteriors_op,
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
    write_api_cache_op,
)


@job(executor_def=in_process_executor, hooks={signal_freshness_failure_hook})
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
    # Epic O.2 — sub-model signal generation for the recently-completed game
    # window. Fan out from dbt_daily_build (mart_game_results + feature marts are
    # fresh), fan in to the PIVOT rebuild, then a (non-blocking) freshness check.
    # bullpen runs after starter_ip — it reads starter_ip_signals for v2 scaling.
    sig_run_env    = generate_run_env_signals_op(start=s16)
    sig_offense    = generate_offense_signals_op(start=s16)
    sig_starter    = generate_starter_signals_op(start=s16)
    sig_starter_ip = generate_starter_ip_signals_op(start=s16)
    sig_bullpen    = generate_bullpen_signals_op(start=sig_starter_ip)
    sig_matchup    = generate_matchup_signals_op(start=s16)
    # Epic 27.2 — Kalman env-state signal (runs concurrently with the other six).
    # Runs the full-history league + team filter on each call; fast (<1 min) because
    # the Kalman recursion over ~2500 dates is pure Python and the Snowflake
    # mart_game_results aggregation resolves in seconds.
    sig_env_state  = generate_env_state_signals_op(start=s16)
    # Story 27.4 — defense quality signal (OAA + sprint speed).
    # Reads mart_team_defense_quality_rolling (dbt-built; prior-season OAA + EB sprint speed).
    # Shared signal for Epic 27 (totals) and Epic 28 (H2H) per R33.
    sig_defense_quality = generate_defense_quality_signals_op(start=s16)
    sig_rebuild    = dbt_sub_model_signals_rebuild(
        run_env_done=sig_run_env,
        offense_done=sig_offense,
        starter_done=sig_starter,
        starter_ip_done=sig_starter_ip,
        bullpen_done=sig_bullpen,
        matchup_done=sig_matchup,
        env_state_done=sig_env_state,
        defense_quality_done=sig_defense_quality,
    )
    sig_fresh = signal_freshness_check(start=sig_rebuild)
    # SCD-2 update: mart_odds_outcomes is now fresh; update market features and
    # rebuild feature_pregame_odds_features before the prediction step.
    s16b = update_market_features_scd2(start=sig_fresh)
    s16c = dbt_pregame_odds_rebuild(start=s16b)
    # SCD-2 update: monthly_schedule is now fresh; update lineup state and
    # rebuild feature_pregame_lineup_features before the prediction step.
    s16d = update_lineup_state_scd2(start=s16c)
    s16e = dbt_lineup_feature_rebuild(start=s16d)
    s17 = ingest_umpires_late(start=s16e)
    # Epic 6A — refresh yesterday's EB bullpen posteriors (eb_bullpen_posteriors +
    # eb_bullpen_team_posteriors) BEFORE the sequential team update, whose
    # bullpen_xwoba branch reads eb_bullpen_posteriors for reliever-PA membership,
    # and before dbt_umpire_feature_rebuild, which rebuilds the bullpen features.
    # Missing op was the cause of the 2026-05-29 bullpen-seq / champion-bullpen stall.
    eb_bullpen = compute_eb_bullpen_posteriors_op(start=s17)
    # Epic O.4 / 16.4 — advance yesterday's sequential posteriors after pitch data
    # (dbt_daily_build) lands and before feature_pregame_game_features is rebuilt
    # in dbt_umpire_feature_rebuild, so it picks up the fresh team posteriors.
    p_player  = update_player_posteriors_op(start=eb_bullpen)
    p_team    = update_team_posteriors_op(start=p_player)
    p_matchup = update_matchup_cell_posteriors_op(start=p_team)
    # A1.11 Stage 4 — forward-looking today's-slate EB posteriors (starter +
    # best-effort lineup), chained after the yesterday-advancing posteriors and
    # before dbt_umpire_feature_rebuild so their outputs land in the rebuilt
    # lineup/starter/game features. Lineup confirmations after this point are
    # handled authoritatively by the lineup_monitor sensor.
    p_starter = compute_starter_posteriors_op(start=p_matchup)
    p_lineup  = compute_lineup_posteriors_op(start=p_starter)
    s18 = dbt_umpire_feature_rebuild(start=p_lineup)
    s19 = predict_today_morning(start=s18)
    write_api_cache_op(predict_done=s19)
    s19b = update_pipeline_status(start=s19)
    s20 = check_prediction_coverage(start=s19b)
    s21 = dbt_mart_prediction_clv(start=s20)
    s22 = compute_model_health(start=s21)
    backfill_prediction_log(start=s22)
