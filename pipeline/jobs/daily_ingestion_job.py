from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    backfill_prediction_log,
    build_zone_matchup_overlay_op,
    ingest_player_props_op,
    write_batter_tb_projections_op,
    write_pitcher_k_projections_op,
    check_data_freshness,
    check_monitors_healthy_op,
    check_odds_coverage_op,
    check_feature_block_coverage_op,
    check_injury_status_health_op,
    check_intraday_fallback_op,
    check_served_prediction_integrity_op,
    check_artifact_freshness_op,
    check_dbt_test_results_op,
    check_w11_tail_coverage_op,
    check_prediction_coverage,
    compute_elo,
    compute_model_health,
    dbt_build_bullpen_posteriors_op,
    dbt_daily_build,
    dbt_lineup_feature_rebuild,
    dbt_mart_prediction_clv,
    dbt_pregame_odds_rebuild,
    dbt_sub_model_signals_rebuild,
    dbt_umpire_feature_rebuild,
    export_w9_signals_to_s3_op,
    generate_bullpen_signals_op,
    generate_defense_quality_signals_op,
    generate_env_state_signals_op,
    generate_matchup_signals_op,
    generate_offense_signals_op,
    generate_totals_generative_signals_op,
    generate_pick_narratives_op,
    generate_run_env_signals_op,
    generate_starter_ip_signals_op,
    generate_starter_signals_op,
    rebuild_sub_model_signals_consumer_op,
    signal_freshness_check,
    signal_freshness_failure_hook,
    update_archetype_posteriors_op,
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
    ingest_statcast,
    ingest_statcast_to_s3_op,
    lakehouse_schedule_export_op,
    lakehouse_w1_pitch_marts_op,
    lakehouse_w2_marts_op,
    lakehouse_w3_marts_op,
    lakehouse_w3pre_flatten_op,
    lakehouse_w6_odds_marts_op,
    lakehouse_w7b_serving_op,
    lakehouse_spine_odds_bridge_op,
    lakehouse_w8a_feature_layer_op,
    lakehouse_w8b_aggregator_op,
    lakehouse_w11_nightly_op,
    lakehouse_delta_maintenance_op,
    refresh_w1_external_tables_op,
    ingest_statsapi_schedule,
    ingest_transactions,
    ingest_umpire_scorecards,
    ingest_umpires_early,
    ingest_umpires_late,
    ingest_weather,
    finalize_prior_slate_game_detail_op,
    predict_today_morning,
    reexport_matchup_cell_posteriors_op,
    reexport_player_seq_posteriors_op,
    reexport_team_seq_posteriors_op,
    settle_user_bets_op,
    update_lineup_state_scd2,
    update_market_features_scd2,
    write_api_cache_op,
    write_serving_store_op,
)


@job(executor_def=in_process_executor, hooks={signal_freshness_failure_hook})
def daily_ingestion_job():
    """BUILD-ORDERING INVARIANT (Story 30.13): every serving-path feature block is
    rebuilt from the latest ingestion BEFORE predict_today_morning. The op chain below
    encodes it — ingest_* → dbt_daily_build → sub-model signals → SCD-2 lineup/odds
    rebuilds → bullpen EB → sequential posteriors → dbt_umpire_feature_rebuild (feature
    store + today's EB starter/lineup posteriors) → predict_today_morning. Do NOT move
    predict (or write_api_cache/write_serving_store) ahead of any rebuild op; the
    `start=`/`predict_done=` threading is the guarantee. Serve-time freshness is the
    backstop if a rebuild silently fails (Story 30.13 Task 4 gate in predict_today)."""
    # E11.23 — silently-not-running heartbeat. Standalone (no upstream / downstream): runs every
    # daily job and ALARMS (never HALTs) if a serving-critical sensor/schedule is STOPPED or a
    # permanently-on intraday flag is unset — the cure for the class where a cutover left an
    # intraday refresh gated-off or a sensor booted STOPPED and silently never ran.
    check_monitors_healthy_op()
    s4 = ingest_action_network()
    s5 = ingest_statcast(start=s4)
    # E11.1-W1d: S3 lakehouse build is HALT/serving-critical — mart_pitch_* are served
    # via Snowflake external tables backed by these parquets. Must complete BEFORE
    # dbt_daily_build so the feature build reads fresh pitch data.
    # ⭐ E11.20: run_w1_lakehouse_op is DECOMPOSED into the per-wave chain below — the
    # old monolith's internal sequence is now graph edges, so each wave is independently
    # retryable and its Dagster duration attributes the daily wall clock (E11.21). The
    # ordering invariants are load-bearing: schedule export before the W6 Group-C
    # flattens; W1→W2→W3 (each reads the prior wave); W3pre before W6 (fresh
    # stg_derivative_odds); spine before the odds bridge; W8a before W8b (the aggregator
    # reads the W8a layer); the W11 nightly tail after W8b (W11d joins the W8b spine).
    s5b = ingest_statcast_to_s3_op(start=s5)
    # 🚨 INC-37 ORDERING INVARIANT (2026-08-01, P1 — a whole slate served on an amputated feature
    # set) — ingest_statsapi_schedule MUST run BEFORE lakehouse_schedule_export_op / the W3pre
    # flatten. It used to sit at s6, AFTER the entire lk1-lk10 lakehouse chain, so every daily
    # feature build flattened whatever schedule the last INTRADAY capture had left in S3. That is
    # harmless on 363 days (yesterday's capture already covers today) and FATAL on the 1st of a
    # month: run_schedule iterates whole months, so the final capture of a month carries ZERO
    # games for the 1st, and the build produced a game universe that stopped at the month
    # boundary — no 08-01 rows in mart_game_spine / the W1-W6 marts / the whole W8a feature
    # layer, so feature_pregame_game_features served 5 of 6 coverage blocks at 0% and
    # predict_today fell to intraday_fallback on all 15 games. Observed identically on 06-01 and
    # 07-01. This is the INC-25 rule for the schedule: a consumer reading an S3 mirror must be
    # rebuilt DOWNSTREAM of the refresh that feeds it, in the SAME run.
    # Pinned by betting_ml/tests/test_schedule_build_ordering_guard.py — do NOT move this back.
    s6 = ingest_statsapi_schedule(start=s5b)
    lk1 = lakehouse_schedule_export_op(start=s6)
    lk2 = lakehouse_w1_pitch_marts_op(start=lk1)
    lk3 = lakehouse_w2_marts_op(start=lk2)
    lk4 = lakehouse_w3_marts_op(start=lk3)
    lk5 = lakehouse_w3pre_flatten_op(start=lk4)
    lk6 = lakehouse_w6_odds_marts_op(start=lk5)
    lk7 = lakehouse_w7b_serving_op(start=lk6)
    lk8 = lakehouse_spine_odds_bridge_op(start=lk7)
    lk9 = lakehouse_w8a_feature_layer_op(start=lk8)
    lk10 = lakehouse_w8b_aggregator_op(start=lk9)
    s5c = lakehouse_w11_nightly_op(start=lk10)
    s5d = refresh_w1_external_tables_op(start=s5c)
    # E11.20 — Delta compaction/vacuum (WARN tier, off the critical path: nothing
    # downstream depends on it; a failure defers maintenance to tomorrow).
    lakehouse_delta_maintenance_op(start=s5d)
    # Durable odds-coverage DQ guard (2026-07-02 incident). The odds marts (mart_odds_outcomes
    # + mart_game_odds_bridge) are now fresh; detect the "bridge freeze" class — 0 has_odds rows
    # for the current slate while spine + outcomes are both fresh — before the prediction path.
    # ALERT-continue by default; HALTs here only when ODDS_COVERAGE_STRICT=1 (see the op docstring).
    s5e = check_odds_coverage_op(start=s5d)
    # ⏬ check_feature_block_coverage_op USED TO SIT HERE (as s5f). It was MOVED to just before
    # predict (see s18f below) because it was positioned UPSTREAM OF ITS OWN PRODUCER — see the
    # comment there for the full reasoning. Do NOT move it back.
    # INC-37 — ingest_statsapi_schedule moved UP to s6 (before lk1); the ingest chain continues here.
    s7 = ingest_weather(start=s5e)
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
    # Story B1 — settle pending user bets against last night's finals (now fresh
    # in stg_statsapi_games). Off the critical prediction path: fans out from
    # dbt_daily_build and is never depended on, so a settle failure can't block
    # predictions or the API cache.
    settle_user_bets_op(start=s16)
    # INC-41 — page when a SERVING-CRITICAL dbt test goes red. Fans in DIRECTLY off
    # dbt_daily_build (s16) because that op is where the suite runs and where its
    # target/run_results.json is captured; anything later would only add distance between the
    # measurement and the read. It reads that captured artifact — it never re-runs the tests
    # (that would double the suite and resume COMPUTE_WH, a new waker during the live E11.24
    # soak). Nothing depends on it, exactly like settle_user_bets_op above, so it is structurally
    # incapable of blocking predictions: the test step stays WARN-tier / non-blocking and INC-6
    # is not regressed. ALERT-tier, always — it pages via send_alert and never HALTs.
    check_dbt_test_results_op(start=s16)
    # Epic O.2 — sub-model signal generation for the recently-completed game
    # window. Fan out from dbt_daily_build (mart_game_results + feature marts are
    # fresh), fan in to the PIVOT rebuild, then a (non-blocking) freshness check.
    # bullpen runs after starter_ip — it reads starter_ip_signals for v2 scaling.
    sig_run_env    = generate_run_env_signals_op(start=s16)
    sig_offense    = generate_offense_signals_op(start=s16)
    # E2.5 — per-side generative totals signal (totals_generative_v1). Reported into the pivot but NOT
    # in the signal_freshness HALT floor (nothing consumes it yet → must not gate predict_today).
    sig_totals_gen = generate_totals_generative_signals_op(start=s16)
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
    # INC-25 — ORDERING FIX (P0 serving-down). After the W8a cutover the Snowflake consumer
    # feature_pregame_sub_model_signals reads the S3 parquet built from these stores, so the chain
    # MUST be: generators write SF stores → export stores to S3 → rebuild the consumer parquet from
    # the fresh stores → materialize the SF consumer → gate. Previously the store mirror + consumer
    # parquet were built at job START (before the generators) so the consumer served a slate-stale
    # pivot and signal_freshness_check HALTed the job.
    # 1) export_w9_signals_to_s3_op is now the fan-in of all 9 generators (SF stores → S3 parquet)
    #    + emits the at-the-source empty-slate coverage ALERT.
    sig_stores_s3 = export_w9_signals_to_s3_op(
        run_env_done=sig_run_env,
        offense_done=sig_offense,
        totals_gen_done=sig_totals_gen,
        starter_done=sig_starter,
        starter_ip_done=sig_starter_ip,
        bullpen_done=sig_bullpen,
        matchup_done=sig_matchup,
        env_state_done=sig_env_state,
        defense_quality_done=sig_defense_quality,
    )
    # 2) rebuild the CONSUMER S3 parquet from the fresh stores (+ refresh its ext table). No-op until
    #    the W8a cutover (W8A_LAKEHOUSE_S3=1); serving-critical/HALT once cut over.
    sig_consumer = rebuild_sub_model_signals_consumer_op(start=sig_stores_s3)
    # 3) materialize the SF consumer table from the now-fresh parquet, then 4) gate on freshness.
    sig_rebuild = dbt_sub_model_signals_rebuild(start=sig_consumer)
    sig_fresh = signal_freshness_check(start=sig_rebuild)
    # SCD-2 update: mart_odds_outcomes is now fresh; update market features and
    # rebuild feature_pregame_odds_features before the prediction step.
    s16b = update_market_features_scd2(start=sig_fresh)
    s16c = dbt_pregame_odds_rebuild(start=s16b)
    # SCD-2 update: monthly_schedule is now fresh; update lineup state and
    # rebuild feature_pregame_lineup_features before the prediction step.
    s16d = update_lineup_state_scd2(start=s16c)
    s16e = dbt_lineup_feature_rebuild(start=s16d)
    # E9.48 — assert the freshly-rebuilt IL status is neither frozen nor self-
    # contradictory (someone flagged CURRENTLY on the IL who has since played). Sits
    # directly on the rebuild it validates. ALERT-tier: never blocks the slate.
    s16f = check_injury_status_health_op(start=s16e)
    s17 = ingest_umpires_late(start=s16f)
    # Story 30.5 — pull UmpScorecards tendency rows (the daily feed that was missing)
    # after the assignment retry and before dbt_umpire_feature_rebuild, so the
    # trailing-3yr ump z-scores recompute on current data. Soft-fail (non-critical).
    s17u = ingest_umpire_scorecards(start=s17)
    # Story A2.11 — refresh the EB bullpen posteriors (now dbt models) BEFORE the
    # sequential team update, whose bullpen_xwoba branch reads eb_bullpen_posteriors.
    # (Was compute_eb_bullpen_posteriors_op; see the 2026-05-29 stall.)
    eb_bullpen = dbt_build_bullpen_posteriors_op(start=s17u)
    # Epic O.4 / 16.4 — advance yesterday's sequential posteriors after pitch data
    # (dbt_daily_build) lands and before feature_pregame_game_features is rebuilt
    # in dbt_umpire_feature_rebuild, so it picks up the fresh team posteriors.
    p_player  = update_player_posteriors_op(start=eb_bullpen)
    # 🩸 INC-25 ORDERING FIX (E11.24, 2026-08-09) — re-mirror player_sequential_posteriors to S3
    # NOW, downstream of the writer directly above. lakehouse_w8a_feature_layer_op mirrors that
    # table at lk9, ~40 min EARLIER in this same run, so the S3 parquet was always exactly one
    # writer-cycle behind: measured 2026-08-09, SF max(update_ts) 08-08 13:02:18 vs S3 08-07
    # 13:02:08 — a +24.00h gap and 38.7h of staleness against a 36h freshness threshold.
    # A FAN-OUT LEAF, deliberately: nothing consumes its output, so a mirror failure can never
    # block p_team / p_matchup / predict. It pages instead (ALERT tier). Do NOT thread it into
    # the p_player → p_team chain.
    reexport_player_seq_posteriors_op(start=p_player)
    p_team    = update_team_posteriors_op(start=p_player)
    # 🩸 INC-25 ORDERING FIX (E11.24 Bundle, 2026-08-14) — the SAME defect one table over.
    # lakehouse_w8b_aggregator_op mirrors team_sequential_posteriors at lk10, ~40 min EARLIER in
    # this same run, so the S3 parquet always trailed the writer directly above: measured
    # 2026-08-14, SF max(update_ts) 13:03:04 / 83,636 rows vs S3 10:16:26 / 83,619 — 2.78h and 17
    # rows behind. PR #772 refused to flip this table's freshness entry to S3 because of it.
    # The lk10 mirror STAYS (the --w8b build reads it) and the order cannot be swapped — the
    # writer needs the SF eb_bullpen_posteriors copy, which needs the ext refresh, which runs
    # after lk10 (a genuine cycle, documented at lineup_intraday_s3_feature_rebuild / E9.53).
    # A FAN-OUT LEAF: nothing consumes its output, so a mirror failure can never block p_matchup
    # or predict. It pages instead (ALERT tier). Do NOT thread it into the chain.
    reexport_team_seq_posteriors_op(start=p_team)
    p_matchup = update_matchup_cell_posteriors_op(start=p_team)
    # 🩸 E11.24 Bundle — matchup_cell_sequential_posteriors had NO S3 prefix at all. Its mirror is
    # BORN downstream of its writer rather than being added to the lk10 export set, so the family's
    # fourth member is never created with the INC-25 trail pre-installed. Fan-out leaf, as above.
    reexport_matchup_cell_posteriors_op(start=p_matchup)
    # E11.8 (INC-8 fix) — archetype posteriors MUST also run in the daily job,
    # not only in statcast_catchup_job. The catchup sensor skips when Statcast
    # data arrived before the 07:00 run (rare but real), leaving
    # mart_player_archetype_posteriors un-updated for that day. Running here
    # after sequential posteriors (they share the mart_game_results dependency)
    # and before dbt_umpire_feature_rebuild mirrors the catchup job's ordering.
    p_archetype = update_archetype_posteriors_op(start=p_matchup)
    # Story A2.11 — the forward-looking today's-slate EB posteriors (starter +
    # lineup) are now dbt models built INSIDE dbt_umpire_feature_rebuild, after the
    # sequential update ops (so their as-of sequential column is fresh) and before
    # the features that ref() them. Lineup confirmations after this point are still
    # handled authoritatively by the lineup_monitor sensor.
    s18 = dbt_umpire_feature_rebuild(start=p_archetype)
    # Durable served-feature-block coverage guard (F2 / F2-recurrence — umpire block collapsed
    # 2026-07-02 AND 2026-07-03). Detects a whole feature block silently zeroing in
    # feature_pregame_game_features (ext VALUE:-case mismatch / precursor not wired) before predict.
    # ALERT-continue by default; HALTs only when FEATURE_COVERAGE_STRICT=1 (see the op docstring).
    #
    # ⭐ POSITION IS LOAD-BEARING — IT MUST RUN AFTER dbt_umpire_feature_rebuild (2026-08-03).
    # It used to sit at s5f, ~13 ops EARLIER, immediately after check_odds_coverage_op. But the op
    # directly above is the one that BUILDS two of the blocks this guard asserts on: its selector
    # rebuilds mart_bullpen_effectiveness → feature_pregame_team_features →
    # feature_pregame_game_features{,_raw}, i.e. it is what populates
    # {home,away}_bp_eb_xwoba (the `bullpen_eb` block) and ump_accuracy_zscore (`umpire`).
    # So at s5f the guard read a store that was one FOLD behind, and flagged as a "WHOLE-SLATE
    # OUTAGE" a date that this very run heals a few ops later:
    #     08-01 run flagged 07-30 (0%);  08-03 run flagged 08-01 (0%)
    # and BOTH of those dates read 100% once the same run finished. That is a recurring
    # near-daily false CRITICAL page on the one guard that exists to catch silent zeroing —
    # precisely the alarm-fatigue failure mode the _DATE_OUTAGE_SKIP_NEWEST comment warns about,
    # and it would make FEATURE_COVERAGE_STRICT=1 a guaranteed daily HALT.
    # Raising the newest-date exemption to 2 would have hidden the symptom while ALSO blinding
    # the guard for an extra day; measuring AFTER the producer is the honest fix and keeps the
    # exemption at its designed meaning ("today's games have not been played yet").
    # Still UPSTREAM of predict, so FEATURE_COVERAGE_STRICT=1 retains its power to stop a bad
    # slate being scored. Do NOT hoist this back into the early ingest chain.
    s18f = check_feature_block_coverage_op(start=s18)
    s19 = predict_today_morning(start=s18f)
    # E9.13 — generate plain-English pick narratives (Snowflake Cortex) BEFORE the
    # serving writes so Railway PG picks up pick_narrative alongside pick_explanation.
    # Soft-fail, so a Cortex outage never blocks write_serving_store_op.
    s19n = generate_pick_narratives_op(start=s19)
    # E9.31b — generate zone-overlay JSONs for today's batter × starter pairs.
    # WARN-tier: fans out from predict_today_morning in parallel with narrative
    # generation; writes directly to S3 (never blocks serving or predictions).
    build_zone_matchup_overlay_op(start=s19)
    # E5.5 — daily K-projection payloads for the /props page. WARN-tier; fans out from
    # predict_today_morning in parallel with the zone overlays; writes DynamoDB + S3, never blocks.
    write_pitcher_k_projections_op(start=s19)
    # E5.9 — daily batter TB-projection payloads for the /props Total Bases tab. WARN-tier;
    # fans out from predict_today_morning like its E5.5 pitcher-side sibling; Snowflake-free
    # (DuckDB/S3 reads only); writes DynamoDB + S3, never blocks predictions or serving.
    write_batter_tb_projections_op(start=s19)
    # E11.22 — served-prediction integrity gate (the permanent INPUT-integrity monitor). Reads
    # TODAY's just-written daily_model_predictions and ALARMS per serving tier on the migration
    # failure classes parity misses and the 30-day sensor only catches weeks later: wrong-date
    # (INC-22), fell-to-intraday_fallback (INC-25), post_lineup coverage collapse (INC-17-P2), and
    # FLAT output (INC-24). Fans out from predict (must run AFTER it writes) so it never blocks the
    # serving writes. ALERT-continue by default; HALTs only when SERVED_INTEGRITY_STRICT=1.
    check_served_prediction_integrity_op(start=s19)
    # E11.27 — per-slate intraday_fallback monitor (E11.24 §8 / INC-35 blind-spot closer). A
    # NARROWER sibling of the integrity gate above: keyed specifically on the SERIOUS
    # slate-wide/high-share fallback signature and/or any feature_store=0 tier, silent on the
    # chronic ~1-game/slate baseline. ALERT-tier, ALWAYS — no --strict escalation exists; it
    # pages via send_alert but never blocks the serving writes. Fans out from predict.
    check_intraday_fallback_op(start=s19)
    # INC-37 — the W11 serving tail (umpire / weather / public_betting) today-guard. Those three
    # blocks are the ones _FEATURE_STORE_COVERAGE_BLOCKS does not contain and
    # check_feature_block_coverage_op structurally cannot see (it excludes the anchor date, so it
    # is a store-HISTORY guard): on 2026-08-01 they held 0 of 15 slate games and a front-end panel
    # was blank while the coverage gate read 0.878 and nothing paged. Fans out from predict —
    # which is far downstream of the lakehouse_w11_nightly_op build it validates — so a blank
    # transparency panel can never withhold a slate's predictions. ALERT-tier, always: it pages
    # via send_alert and has no strict escalation.
    check_w11_tail_coverage_op(start=s19)
    # INC-41 — per-artifact freshness SLAs on serving-critical parquet. Asserts that each
    # registered artifact has ADVANCED (a CONTENT timestamp inside the parquet, never the S3
    # mtime, which PR #638's atomic copy refreshes even when the data is unchanged), with lag
    # counted only across each writer's declared active hours so the deliberate 10.5h overnight
    # capture gap is not a breach. Closes the hole INC-41 exposed: on 2026-08-06 the lineups
    # parquet froze for 6.5h while the FEED stayed healthy, so every source-watching check read
    # green, the lineup monitor reported "No newly confirmed lineups" ~40 times and the op
    # returned SUCCESS. Fans out from predict — DOWNSTREAM of the W7b/W8a builds it guards, per
    # INC-40 (a monitor upstream of its own producer manufactures a false stale-alarm). The daily
    # run cannot catch an INTRADAY freeze, which is INC-41's exact shape — the off-cycle
    # artifact_freshness_job runs the same check on the writer's cadence between daily runs.
    # ALERT-tier, always: pages via send_alert, never HALTs.
    check_artifact_freshness_op(start=s19)
    # E5.1b — daily player-prop odds catch-up (mlb/props/ S3). WARN-tier; hangs off predict so
    # its ~few-minute paid Odds API pull never delays the serving-critical predict path. Gated
    # PROPS_DAILY_INGEST (default OFF) → a no-op loud-skip until the operator flips it. Historical
    # endpoint → lands yesterday's slate; idempotent partition-skip → only pays for the new day.
    ingest_player_props_op(start=s19)
    write_api_cache_op(predict_done=s19n)
    s_serve = write_serving_store_op(predict_done=s19n)
    # 2026-07-15 — finalize YESTERDAY's game-detail blobs to status='Final' so the model-vs-market
    # scorecards populate. Nothing else re-writes a slate's game-detail after its games end (the
    # intraday odds sensor window closes at last first pitch; the daily serving write is TODAY-only),
    # so completed slates were freezing at 'Live'. WARN-tier, terminal leaf — runs after the serving
    # write so it never delays today's picks and a failure can't block the daily path.
    finalize_prior_slate_game_detail_op(start=s_serve)
    s19b = update_pipeline_status(start=s19n)
    s20 = check_prediction_coverage(start=s19b)
    s21 = dbt_mart_prediction_clv(start=s20)
    s22 = compute_model_health(start=s21)
    backfill_prediction_log(start=s22)
