from dagster import in_process_executor, job

from pipeline.ops.sensor_ops import (
    catchup_ingest_statcast,
    catchup_rebuild_outcome_mirrors,
    catchup_refresh_ext_tables,
    lineup_dbt_clv_rebuild,
    lineup_dbt_feature_rebuild,
    lineup_dbt_staging_rebuild,
    lineup_ingest_umpires,
    lineup_intraday_s3_feature_rebuild,
    lineup_predict,
)
from pipeline.ops.daily_ingestion_ops import (
    build_zone_matchup_overlay_op,
    compute_elo,
    dbt_build_bullpen_posteriors_op,
    dbt_umpire_feature_rebuild,
    finalize_prior_slate_game_detail_op,
    generate_pick_narratives_op,
    predict_today_morning,
    update_archetype_posteriors_op,
    update_matchup_cell_posteriors_op,
    update_player_posteriors_op,
    update_team_posteriors_op,
    write_serving_store_intraday_op,
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
    """BUILD-ORDERING INVARIANT (Story 30.13): the intraday self-heal path. Rebuild
    staging → regenerate the S3 W8b feature parquet → copy the feature store + EB
    starter/lineup posteriors → re-score. lineup_predict MUST stay last among the rebuild
    ops (do NOT reorder). Fires every ~10 min in the active window, so an intraday
    starter/lineup change is absorbed within one cycle (the residual inter-cycle staleness
    is covered by the serve-time freshness gate, 30.13 Task 4).  Overnight-sourced blocks
    (bullpen/team/pythag/elo) are intentionally NOT rebuilt here — they don't change intraday.

    2026-06-30 (824819 fix) — lineup_intraday_s3_feature_rebuild was inserted between the
    staging rebuild and the feature copy. Post-W8b-cutover the served lineup/matchup/aggregator
    features are a COPY of a daily-frozen S3 parquet (the dbt prod branch reads lakehouse_ext);
    lineup_dbt_feature_rebuild only re-COPIES that ext table, so without regenerating the S3
    parquet an intraday confirmation never reached the post_lineup re-score and the game looped
    forever. The new op (gated default-OFF) regenerates the S3 chain first.

    E11.4 (2026-06-19) — removed two ops from the head and tail of this chain:
      • lineup_ingest_schedule: the 30-min Railway schedule_capture cron now handles
        statsapi schedule ingestion (services/schedule_capture/), eliminating ~1 min of
        Dagster run-minutes per trigger and the redundant per-trigger ingest.
      • lineup_odds_snapshot (Parlay events/odds/line-movement): the Parlay odds capture
        was decommissioned 2026-06-16 (Story 12.3.7 / A2.18) — live odds now come from
        The Odds API Railway cron (services/odds_capture/) + odds_current_rebuild_sensor.
        Removing the dead Parlay call eliminates another ~1 min per trigger and a CLV
        rebuild that waited on a no-op Parlay API round-trip.
    """
    # Story 30.5 — ingest today's HP-umpire assignment here (afternoon, when MLB
    # has posted it), idempotently, so the confirmed-lineup re-score reflects the
    # actual umpire. The 07:00 daily ops run too early to ever catch it.
    s1u = lineup_ingest_umpires()
    s2 = lineup_dbt_staging_rebuild(start=s1u)
    # 2026-06-30 (824819 restart-loop fix) — REGENERATE the S3 W8b feature parquet so an
    # intraday lineup/starter confirmation reaches the post_lineup re-score. MUST sit AFTER
    # staging (needs fresh stg_statsapi_lineups_wide for the SCD-2 write) and BEFORE the
    # feature copy below (which reads the lakehouse_ext tables this op refreshes). Gated
    # default-OFF (LINEUP_INTRADAY_S3_REBUILD) → logged no-op when off, so no behaviour change
    # until the operator validates on the box. MIRROR-tier: a failure is loud but does not
    # block the re-score. See the op docstring for the full gap explanation.
    s2b = lineup_intraday_s3_feature_rebuild(start=s2)
    # Story A2.11 — the EB lineup/starter posteriors are now dbt models built INSIDE
    # lineup_dbt_feature_rebuild (incremental → recomputes the confirmed-lineup games)
    # before the features that ref() them, so the post-lineup prediction reflects the
    # actual batters. (Was a separate lineup_compute_posteriors Python op.)
    s2c = lineup_dbt_feature_rebuild(start=s2b)
    s3 = lineup_predict(start=s2c)
    # E9.13 — generate plain-English pick narratives after the post-lineup re-score,
    # before the CLV rebuild + serving store write so Railway PG picks up pick_narrative.
    # Soft-fail: Cortex outage must not block the serving write.
    s3n = generate_pick_narratives_op(start=s3)
    clv = lineup_dbt_clv_rebuild(start=s3n)
    serve = write_serving_store_intraday_op(predict_done=clv)
    # E11.20 phase-2a (2026-07-20) — the zone-overlay generator's ONLY trigger used to be the
    # pre-dawn daily job (~11:40pm PT), when today's lineups cannot exist yet, so it wrote ZERO
    # overlays on the organic path for three weeks and the app's Matchup Zone Analysis surface sat
    # empty. WARN-tier and deliberately the TERMINAL leaf — it runs where lineups actually are
    # confirmed, but downstream of the serving write so its (~1 min) profile build can never delay
    # the Epic A1 post_lineup SLA. Idempotent: it overwrites the same as_of= keys, so re-running it
    # on every trigger through the slate just accumulates overlays as more lineups post.
    build_zone_matchup_overlay_op(start=serve)


@job(executor_def=in_process_executor, tags={"concurrency_group": "statcast_catchup"})
def statcast_catchup_job():
    # Fired by statcast_freshness_sensor once yesterday's Statcast finally lands.
    # Ingest pitches to S3 → REFRESH the pitch external tables so the SF-target views see them
    # → refresh the posteriors that depend on the now-complete games (they read the pitch-derived
    # mart_game_results VIEW) → fold them into the feature marts → re-score today so the live
    # slate reflects the caught-up data → settle yesterday's game-detail (E9.41b).
    # E9.41b (2026-07-18): both head ops had silently no-op'd since the W11-E lakehouse migration
    # (SF savant.batter_pitches write retired + stg_batter_pitches enabled=false on the SF target),
    # so the catch-up landed NOTHING. catchup_ingest_statcast now runs the S3 ingest and
    # catchup_refresh_ext_tables (was catchup_dbt_rebuild) refreshes the ext tables.
    s1 = catchup_ingest_statcast()
    s2 = catchup_refresh_ext_tables(start=s1)
    # E9.41 — rebuild the settled-outcome S3 MIRROR parquets (mart_game_results → CLV-label marts)
    # off the just-landed pitches, so a late game's outcome reaches the serving reads (featured
    # recap heal + finalize + /performance) THIS run, not only at the next 08:00 daily. Before the
    # posteriors, which read mart_game_results.
    s2b = catchup_rebuild_outcome_mirrors(start=s2)
    # Story A2.11 — bullpen EB posteriors (dbt) before the sequential team update.
    eb = dbt_build_bullpen_posteriors_op(start=s2b)
    pp = update_player_posteriors_op(start=eb)
    pt = update_team_posteriors_op(start=pp)
    pm = update_matchup_cell_posteriors_op(start=pt)
    # INC-2 (2026-06-22): refresh the archetype posteriors daily here too (previously
    # unwired → stale since 2026-05-31), after the sequential posteriors and before
    # dbt_umpire_feature_rebuild folds mart_player_archetype_posteriors into the
    # feature store + the morning re-score reads it.
    ar = update_archetype_posteriors_op(start=pm)
    # A2.3: recompute Elo on the now-current mart_game_results (compute_elo reads
    # mart_game_results, which is pitch-derived and therefore lagged by the same
    # Statcast availability gap this catch-up resolves). Without this, Elo stays
    # stale until the next 07:00 daily run even after the catch-up self-heals.
    # Story A2.11 — starter/lineup EB posteriors are now built inside
    # dbt_umpire_feature_rebuild (after the sequential ops), so no separate ops here.
    el = compute_elo(start=ar)
    s3 = dbt_umpire_feature_rebuild(start=el)
    s4 = predict_today_morning(start=s3)
    serve = write_serving_store_intraday_op(predict_done=s4)
    # E9.41b — settle YESTERDAY's stored game-detail Finals (→ the model-vs-market "who
    # called it" scorecards) the moment its late Statcast lands, not only at the next 08:00
    # daily run. The intraday serve above re-writes TODAY's blobs only; a late (West-coast)
    # game's outcome is INNER-JOINed off the pitch-derived mart_game_results VIEW, so once
    # catchup_ingest_statcast lands yesterday's pitches the view is fresh and this re-resolves
    # the completed prior slate's game-detail blobs to status='Final' from it. Terminal
    # WARN-tier leaf (finalize catches its own exceptions) — a failure logs loud and can never
    # fail the catch-up. Scope note: the sensor stops firing this job past today's first-pitch
    # deadline (protective — re-running predict_today_morning post-first-pitch would race the
    # lineup_monitor's intraday re-scores), so the rare "Savant publishes after the deadline"
    # tail still settles at the next 08:00 daily finalize; the featured recap self-heals on read
    # (E9.41) regardless.
    finalize_prior_slate_game_detail_op(start=serve)
