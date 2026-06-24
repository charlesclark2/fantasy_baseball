# E11.8 / E11.12 — Feed → Caller → Monitor Matrix

**Last updated: E11.12 (2026-06-23).** E11.8 (2026-06-22) established the initial matrix
after INC-7/8. E11.12 closes the residual class: antipattern sweep of event-date `ts_col`
monitors + complete enumeration of ALL feeds including standalone scripts (the INC-11 gap).

---

## How alerts fire

Dagster's standard mechanism: a sensor tick that **raises an Exception** marks the tick as
FAILED and triggers the Dagster+ email-on-failure alert. A `SkipReason` (used for transient
errors and off-day skips) is silent — it never pages.

**Contract**:
- **HARD-ALERT**: sensor raises → tick FAILS → email fires. Serving-critical feeds.
- **WARN**: `check_data_freshness` op (WARN tier in daily_ingestion_job) or `context.log.warning`. Advisory.
- **HALT**: op raises inside the job. Blocks predictions.

---

## ts_col type key

| Type | Meaning | Problem |
|------|---------|---------|
| **ingest** | `CURRENT_TIMESTAMP` / `datetime.now()` / `snapshot_date` (set when script runs) | None — always advances when feed runs |
| **event** | `game_date`, `as_of_date`, `effective_date`, `month_end_date` — reflects WHEN the event happened | Goes stale on legitimately quiet days (off-days, no roster moves). Cannot distinguish "quiet day" from "broken feed." |
| **event+offset** | `game_date` + `eod_offset_hours` | Mitigates the event-date gap for predictable lags (e.g. Statcast publishes next morning). Still event-date at its core. |
| **ingest (dbt)** | `current_date()` / `CURRENT_TIMESTAMP` set by the dbt model at build time | Same as ingest — advances every time dbt runs |

---

## Primary Feed → Caller → Monitor Matrix

| Feed | Table | Caller | Cadence | Severity | Monitor | ts_col | ts_col type | Notes |
|------|-------|--------|---------|----------|---------|--------|-------------|-------|
| **Odds (live)** | `oddsapi.mlb_odds_raw` | Railway `odds_capture` service | 30 min, 24/7 | **HARD-ALERT** | `odds_freshness_alert_sensor` (raises; staleness > 90 min OR quota low) | `ingestion_ts` | **ingest** | INC-7 root cause — original incident |
| **Schedule / games** | `statsapi.monthly_schedule` + `betting.stg_statsapi_games` | Railway `schedule_capture` cron + daily job | 30 min (Railway) + daily | **HARD-ALERT** | `schedule_freshness_alert_sensor` (raises; stale > 4h OR 0 games on game day after 14:30 UTC) | `month_end_date` (calendar boundary) / direct game count | **event** (monthly) | E11.8. check_data_freshness uses month_end_date — can only catch a missed MONTHLY load, NOT mid-month failures; schedule_freshness_alert_sensor is authoritative for daily continuity |
| **Statcast pitches** | `savant.batter_pitches` | `ingest_statcast` op (daily job) + `statcast_catchup_job` | Daily (+ catchup sensor) | **HARD-ALERT** | `statcast_freshness_sensor` (raises on SLA breach); `check_data_freshness` auxiliary | `game_date` + `eod_offset_hours=33` | **event+offset** | E11.12 fix: `game_day_only=True` in check_data_freshness to avoid All-Star-break false positives; HARD-ALERT sensor is the real guard |
| **Predictions written** | `betting_ml.daily_model_predictions` | `predict_today_morning` op (daily job) | Daily + post-lineup | **HARD-ALERT** | `pregame_alert_sensor` (raises 45 min before first pitch) | n/a (row count) | n/a | Catches any upstream failure blocking predict |
| **Model health / skill** | `betting_ml.daily_model_predictions` (rolling 30d) | `compute_model_health` op (daily job) | Daily | **HARD-ALERT** | `model_health_alert_sensor` (raises on corr/spread/Brier gate failure) | n/a | n/a | Catches serving regressions |
| **Signal freshness** | `betting_features.feature_pregame_sub_model_signals` | 8 signal-gen ops (daily job) | Daily | **HALT** | `signal_freshness_check` op (raises if run_env or offense signals absent) | n/a | n/a | Blocks predict if critical signals missing |
| **Pipeline completeness** | `betting_ml.pipeline_status` | `update_pipeline_status` op (daily job) | Daily | **HARD-ALERT** | `pregame_alert_sensor` (checks pipeline_status == 'complete') | n/a | n/a | |
| **Daily job watchdog** | `betting_ml.daily_model_predictions` | `morning_watchdog_sensor` | Daily | Fires job | `morning_watchdog_sensor` (RunRequest to re-trigger job) | n/a | n/a | Watchdog, not alert |
| **Odds quota** | `oddsapi.mlb_odds_raw.x_requests_remaining` | (same as odds_capture) | 30 min | **HARD-ALERT** | `odds_freshness_alert_sensor` (raises on low MAIN-key quota) | n/a | n/a | Part of odds sensor |
| **Archetype posteriors** | `betting.mart_player_archetype_posteriors` | `update_archetype_posteriors_op` (daily job + catchup job) | Daily | **WARN** | `check_data_freshness` (non_blocking, 48h, **game_day_only=True**) | `as_of_date` | **event** | INC-8/E11.8. E11.12: fixed game_day_only False→True; as_of_date = last game_date processed, doesn't advance on off-days |
| **Player sequential posteriors** | `betting.player_sequential_posteriors` | `update_player_posteriors_op` (daily job + catchup) | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) | `update_ts` | **ingest** | ✓ |
| **Team sequential posteriors** | `betting.team_sequential_posteriors` | `update_team_posteriors_op` (daily job + catchup) | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) | `update_ts` | **ingest** | ✓ |
| **Matchup-cell posteriors** | `betting.matchup_cell_sequential_posteriors` | `update_matchup_cell_posteriors_op` (daily job + catchup) | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) — **NEW E11.12** | `update_ts` | **ingest** | Was unmonitored |
| **EB bullpen posteriors** | `betting.eb_bullpen_team_posteriors` | `dbt_build_bullpen_posteriors_op` (daily job + catchup) | Daily | **WARN** | `check_data_freshness` (non_blocking, 48h) | `fit_date` = `current_date()` | **ingest (dbt)** | ✓ |
| **Umpire HP assignment** | `statsapi.umpire_game_log` (statsapi source) | `ingest_umpires_early/late` ops + `lineup_ingest_umpires` (sensor) | Daily (+ lineup trigger) | **WARN** | `check_data_freshness` (non_blocking, 48h, game_day_only=True) | `game_date` | **event** | Acceptable: game_day_only=True avoids off-day false positives; WARN tier |
| **Umpire scorecards (tendency)** | `statsapi.umpire_game_log` (umpscorecards source) | `ingest_umpire_scorecards` op (daily job) | Daily | **WARN** | `check_data_freshness` (non_blocking, 96h) | `game_date` | **event** | Acceptable: 96h threshold covers ~4 game-day gaps; WARN tier |
| **FanGraphs Stuff+** | `fangraphs.fg_stuff_plus_raw` | `ingest_fangraphs_stuff_plus` op (daily job, Sunday only) | Weekly Sunday | **WARN** | `check_data_freshness` (blocking in script, 192h) | `ingestion_ts` | **ingest** | ✓ |
| **FanGraphs hitting leaderboard** | `fangraphs.fg_hitting_leaderboard_raw` | `ingest_fangraphs_hitting_leaderboard` op (daily job) | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h) | `ingestion_ts` | **ingest** | Fantasy asset only |
| **Player transactions** | `statsapi.player_transactions` | `ingest_transactions` op (daily job) | Daily | **WARN** | `check_data_freshness` (non_blocking, 36h on `ingestion_ts`) | `ingestion_ts` | **ingest** | INC-12 fix: was `effective_date`/168h (event-date — quiet-day false stale) |
| **ActionNetwork public betting** | `actionnetwork.public_betting_raw` | `ingest_action_network` op (daily job) | Daily | **WARN** | `check_data_freshness` (blocking in script, 36h) | `ingestion_timestamp` | **ingest** | ✓ |
| **Derivative odds (team/alt totals)** | `oddsapi.derivative_odds_raw` | Railway cron (E2.0b) | 30 min | **WARN** | `check_data_freshness` (non_blocking, 4h) | `ingestion_ts` | **ingest** | NEW E11.8; EVAL/CLV-only |
| **Park factors** | `betting.eb_park_factors_raw` | `fit_park_priors.py` (HAND-RUN, annual) | Annual (season start) | **WARN** | `check_data_freshness` (non_blocking, 4320h / 180d) | `fit_date` = `current_date()` | **ingest (dbt)** | ✓ |
| **Sprint speed** | `savant.sprint_speed_raw` | `ingest_sprint_speed` op (daily job, Sunday only) | Weekly Sunday | **WARN** | `check_data_freshness` (non_blocking, 192h) — **NEW E11.12** | `snapshot_date` | **ingest** | Was unmonitored |
| **Catcher framing** | `savant.catcher_framing_raw` | `ingest_fangraphs_catcher_framing` op (daily job, Sunday only) | Weekly Sunday | **WARN** | `check_data_freshness` (non_blocking, 192h) — **NEW E11.12** | `snapshot_date` | **ingest** | Was unmonitored |
| **OAA (Outs Above Average)** | `external.oaa_team_season_raw` | `ingest_oaa` op (daily job, soft-fail) | Daily | **WARN** | `check_data_freshness` (non_blocking, 48h) — **NEW E11.12** | `loaded_at` | **ingest** | Was unmonitored; prior-season OAA used in features only |
| **Player profiles** | `statsapi.player_profiles_raw` | `ingest_player_profiles_update` op (`weekly_player_profiles_job`) | Weekly | **WARN** | `check_data_freshness` (non_blocking, 192h) — **NEW E11.12** | `last_fetched_at` | **ingest** | Was unmonitored |
| **Weather** | Open-Meteo (no raw table) | `ingest_weather` op (daily + intraday) | Daily + intraday | None | No alert; weather is a WARN-tier input with imputation fallback | n/a | n/a | No raw Snowflake table to monitor |
| **CLV drift** | `betting_features.feature_pregame_meta_model_features` | `dbt_mart_prediction_clv` op (daily job) | Daily | **HARD-ALERT** | `clv_alert_sensor` (raises if pct_positive_clv < 35%) | n/a | n/a | Model-quality alert, not feed freshness |
| **H2H conviction picks** | `betting_ml.daily_model_predictions` | (same as predictions written) | Daily pre-game | Informational | `conviction_pick_alert_sensor` (raises with picks digest) | n/a | n/a | Not a freshness alert |

---

## Scheduling audit — caller enumeration (INC-8/11 class)

Every ingestion/compute feed across `pipeline/ops/` (Dagster) **and** `scripts/` (standalone). The
INC-11 class: a script with NO scheduled caller stalls silently. Every entry is either wired or
explicitly documented as intentional one-off.

### Dagster-wired scripts (recurring, have a caller)

| Script | Caller job | Cadence | Notes |
|--------|------------|---------|-------|
| `savant_ingestion.py batter_pitches` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `ingest_statsapi.py schedule` | `daily_ingestion_job` (+ Railway `schedule_capture` cron) | Daily + 30 min | |
| `ingest_weather.py` | `daily_ingestion_job` + `intraday_jobs` (soft-fail) | Daily + intraday | |
| `ingest_umpires.py` | `daily_ingestion_job` (early + late) + `lineup_monitor_job` | Daily + lineup trigger | |
| `ingest_fangraphs_stuff_plus.py` | `daily_ingestion_job` (Sunday only) | Weekly | |
| `ingest_catcher_framing.py` | `daily_ingestion_job` (Sunday only) | Weekly | |
| `ingest_fangraphs_hitting_leaderboard.py` | `daily_ingestion_job` | Daily | |
| `ingest_sprint_speed.py` | `daily_ingestion_job` (Sunday only) | Weekly | |
| `ingest_transactions.py` | `daily_ingestion_job` | Daily | |
| `ingest_oaa.py` | `daily_ingestion_job` (soft-fail) | Daily | |
| `ingest_actionnetwork_betting.py` | `daily_ingestion_job` | Daily | |
| `ingest_umpire_scorecards.py` | `daily_ingestion_job` (soft-fail) | Daily | |
| `parlay_api_ingestion.py` | `intraday_jobs` (odds_snapshot_ingest) | Intraday (sensor) | Pre-game odds snapshots |
| `parlay_api_ingestion.py line-movement` | `intraday_jobs` (odds_snapshot_ingest) | Intraday (sensor) | Line movement capture |
| `backfill_lineup_state_scd2.py` | `daily_ingestion_job` | Daily | SCD-2 update |
| `backfill_market_features_scd2.py` | `daily_ingestion_job` | Daily | SCD-2 update |
| `ingest_statcast_to_s3.py` | `daily_ingestion_job` (soft-fail, W1 track) | Daily | S3 Parquet write; Snowflake primary |
| `run_w1_lakehouse.py` | `daily_ingestion_job` (soft-fail, W1 track) | Daily | S3 lakehouse rebuild |
| `predict_today.py` (morning) | `daily_ingestion_job` + `statcast_catchup_job` | Daily + catchup | |
| `predict_today.py` (post_lineup) | `lineup_monitor_job` | Intraday (sensor) | |
| `write_serving_store.py` (run_all) | `daily_ingestion_job` | Daily | Full serving store write |
| `write_serving_store.py` (--picks --game-detail --book-odds) | `lineup_monitor_job` + `intraday_jobs` | Intraday | Volatile sections only |
| `write_api_cache.py` | `daily_ingestion_job` | Daily | S3 cache warm |
| `generate_pick_narratives.py` | `daily_ingestion_job` + `lineup_monitor_job` (soft-fail) | Daily + lineup | Cortex narrative gen |
| `check_data_freshness.py` | `daily_ingestion_job` (WARN tier, non-blocking) | Daily | Freshness monitor |
| `check_signal_freshness.py` | `daily_ingestion_job` (HALT tier, `signal_freshness_check` op) | Daily | |
| `check_prediction_coverage.py` | `daily_ingestion_job` | Daily | |
| `update_pipeline_status.py` | `daily_ingestion_job` | Daily | |
| `compute_model_health.py` | `daily_ingestion_job` | Daily | |
| `backfill_prediction_log.py` | `daily_ingestion_job` | Daily | Idempotent log hydration |
| `settle_user_bets.py` | `daily_ingestion_job` (soft-fail) | Daily | |
| `ingest_player_profiles.py update` | `weekly_player_profiles_job` | Weekly | |
| `betting_ml/scripts/compute_elo.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `betting_ml/scripts/sequential_bayes/update_player_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `betting_ml/scripts/sequential_bayes/update_team_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | |
| `betting_ml/scripts/eb_priors/compute_archetype_posteriors.py` | `daily_ingestion_job` + `statcast_catchup_job` | Daily | INC-8/E11.8 fix: was un-wired |
| `betting_ml/scripts/generate_bullpen_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/generate_run_env_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/offense_v2/generate_offense_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/starter_v1/generate_starter_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/starter_v1/generate_starter_ip_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/eb_priors/generate_matchup_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/generate_env_state_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/generate_defense_quality_signals.py` | `daily_ingestion_job` | Daily | |
| `betting_ml/scripts/compute_stacking_weights.py` | `weekly_ml_job` (Monday) | Weekly | |
| `betting_ml/scripts/train_bayesian_meta_model.py` | `weekly_meta_model_job` (Wednesday) | Weekly | |

### Railway cron services (non-Dagster callers)

| Service | Table written | Cadence | Monitor |
|---------|--------------|---------|---------|
| `odds_capture` | `oddsapi.mlb_odds_raw` | 30 min, 24/7 | `odds_freshness_alert_sensor` HARD-ALERT |
| `schedule_capture` | `statsapi.monthly_schedule` | 30 min | `schedule_freshness_alert_sensor` HARD-ALERT |
| (Railway cron E2.0b) | `oddsapi.derivative_odds_raw` | 30 min | `check_data_freshness` WARN 4h |

### Intentional one-off / hand-run scripts (INC-11 class — documented, not wired)

These scripts have NO recurring Dagster caller by design. A future sweep must NOT flag them as
the INC-11 pattern; they are intentional one-offs.

| Script | Purpose | Caller | Why no recurring schedule |
|--------|---------|--------|--------------------------|
| `scripts/odds_api_ingestion.py` | Historical Odds API backfills | HAND-RUN | **LEGACY** — The Odds API live feed migrated to Railway `odds_capture` cron (Parlay API Migration Phase 0, 2026-05-26); this script is preserved for historical backfill only |
| `scripts/export_statcast_to_s3.py` | Export `stg_batter_pitches` → S3 Parquet for W1 lakehouse setup | HAND-RUN | W1 setup/re-sync script; >1 min per season; documented hand-off |
| `scripts/derivative_odds_backfill.py` | One-off backfill of derivative odds | HAND-RUN | One-time migration |
| `scripts/ingest_umpires_historical.py` | Historical umpire assignment backfill | HAND-RUN | One-time backfill |
| `scripts/parity_check_w1.py` | W1 S3-vs-Snowflake parity | One-shot Dagster job (`w1_parity_job`, 2026-06-25) | One-time verification |
| `scripts/pregame_snapshot.py` | Pre-game odds snapshot GH Actions monitor | GH Actions `.github/workflows/` | **LEGACY/deprecated** — writes `$GITHUB_OUTPUT`; being decommissioned with GH Actions (story 0.5.10) |
| `scripts/lineup_monitor.py` | Lineup confirmation GH Actions trigger | GH Actions `.github/workflows/` | **LEGACY/deprecated** — replaced by Dagster `lineup_monitor_sensor` |
| `scripts/oddsapi_historical_dry_run.py` | Analysis / dry-run | HAND-RUN | Analysis script, not a feed |
| `scripts/probe_ms2_multisport_props.py` | Multisport prop market probe | HAND-RUN | Exploration; multi-sport is pre-season (NCAAF Aug, NFL mid-Aug) |
| `scripts/validate_fangraphs_pipeline.py` | FanGraphs pipeline validation | HAND-RUN | Validation tool, not a feed |
| `scripts/validate_scd2_reconstruction.py` | SCD-2 accuracy validation | HAND-RUN | Validation tool, not a feed |
| `scripts/compare_model_versions.py` | Model version diff analysis | HAND-RUN | Analysis tool, not a feed |
| `scripts/savant_ingestion.py` (park factors) | Park factor raw data for `fit_park_priors.py` | HAND-RUN | Annual season-start |
| `scripts/ingest_savant_park_factors.py` | Park factor raw data variant | HAND-RUN | Annual season-start |
| `scripts/ingest_fangraphs_zips_csv.py` | FanGraphs ZiPS projections (CSV import) | HAND-RUN | Annual; analytics/fantasy only |
| `scripts/ingest_fangraphs_zips_hitting.py` | FanGraphs ZiPS hitting projections | HAND-RUN | Annual; analytics/fantasy only |
| `scripts/ingest_fangraphs_zips_pitching.py` | FanGraphs ZiPS pitching projections | HAND-RUN | Annual; analytics/fantasy only |
| `scripts/backfill_*.py` (all) | Historical backfills | HAND-RUN | One-time migration/recovery scripts |
| `scripts/migrate_*.py` (all) | Data migrations | HAND-RUN | One-time migrations |

---

## Monitor-the-monitors

**INC-5 lesson**: a freshness monitor that itself silently fails is the same blind spot.

All HARD-ALERT sensors follow this contract:
- **Transient Snowflake / connection errors** → `yield SkipReason(...)`. Tick succeeds. The real condition
  persists across ticks and will fire once the connection recovers.
- **Real problem detected** → `raise Exception(...)`. Tick FAILS → email fires. Self-heals on next tick.
- **Off-day / outside alert window** → `yield SkipReason(...)`. Silent skip.

**E11.8 fix**: `statcast_freshness_sensor` previously used `SkipReason` for SLA breach (data still
missing within 2h of first pitch) → silent. Changed to `raise Exception` so SLA breach actually pages.

**Dagster+ configuration**: enable "sensor tick failure" alert policy for all HARD-ALERT sensors
(`odds_freshness_alert_sensor`, `schedule_freshness_alert_sensor`, `statcast_freshness_sensor`,
`pregame_alert_sensor`, `model_health_alert_sensor`).

---

## Display-derived status coverage (INC-12 lesson)

Some user-visible statuses are **not monitored at the source level** because they derive from a
multi-hop chain. A source-table freshness check catches a feed outage but NOT a stale serving-store
blob if the write step is skipped or the cache read returns a stale permanent row.

| Display status | Chain | Risk | Coverage |
|---------------|-------|------|----------|
| `is_on_il` (player page) | `player_transactions` → dbt marts → `api_cache player/{id}` | Stale `is_permanent` blob survives date rollover | INC-12 fix: `pg.get_cache` now uses `ORDER BY updated_at DESC` on permanent path |
| Player game log | `mart_starting_pitcher_game_log` → `api_cache player/{id}` | Same stale-blob issue | Same fix |
| Team record / score | `stg_statsapi_games` → `api_cache picks/game/{pk}` | Non-permanent — date-scoped, refreshes daily | OK |
| Model skill score | `daily_model_predictions` (rolling 30d) | Monitored by `model_health_alert_sensor` (HARD-ALERT) | OK |

**Lesson**: any blob written `is_permanent=True` that reflects a **mutable current state**
(IL status, team roster, player availability) needs the serving-store read path to always return
the **latest** write. The `ORDER BY updated_at DESC` fix closes this class for all permanent-blob reads.

---

## E11.12 — Event-date antipattern sweep summary

ts_col values that use event-dates rather than ingest heartbeats, and the disposition for each:

| Feed | ts_col | Type | Disposition |
|------|--------|------|-------------|
| `batter_pitches` | `game_date` (+ offset) | event+offset | **FIXED**: `game_day_only=True` added — avoids All-Star-break false positives; statcast_freshness_sensor (HARD-ALERT) is the real guard |
| `monthly_schedule` | `month_end_date` | event (monthly) | **ACCEPTABLE with caveat**: no ingest heartbeat column available; only catches missed monthly load (not mid-month failures); schedule_freshness_alert_sensor (HARD-ALERT) is authoritative — comment updated |
| `umpire_game_log [statsapi]` | `game_date` | event | **ACCEPTABLE**: `game_day_only=True` limits checks to game days, mitigating the off-day issue; WARN tier |
| `umpire_game_log [umpscorecards]` | `game_date` | event | **ACCEPTABLE**: 96h threshold + WARN tier; a 4-day off streak produces a non-blocking alert at most |
| `mart_player_archetype_posteriors` | `as_of_date` | event (= last game_date) | **FIXED**: `game_day_only=True` added — `as_of_date` doesn't advance on off-days (no new games → no new computation); only check on game days |
| `eb_bullpen_team_posteriors` | `fit_date` | **ingest (dbt)** | ✓ `current_date()` in dbt model — always set to build date, never event-date |
| `player_sequential_posteriors` | `update_ts` | **ingest** | ✓ |
| `team_sequential_posteriors` | `update_ts` | **ingest** | ✓ |
| `matchup_cell_sequential_posteriors` | `update_ts` | **ingest** | ✓ (new monitor) |
| All other feeds | `ingestion_ts` / `ingestion_timestamp` / `loaded_at` / `last_fetched_at` / `snapshot_date` | **ingest** | ✓ |

---

## What would have caught each incident

| Incident | Root cause | Would have been caught by |
|----------|-----------|--------------------------|
| **INC-8** (archetype op wired only into statcast_catchup_job — skips when Statcast is early) | op existed in Dagster but was missing from the unconditional `daily_ingestion_job` | A complete **caller matrix** showing `update_archetype_posteriors_op` wired only into `statcast_catchup_job` (conditional on fresh Statcast) — not the unconditional daily job. E11.8 only checked whether an op *existed* in Dagster; didn't verify which *job* called it. |
| **INC-11** (compute_archetype_posteriors.py script never wired anywhere) | standalone script in `betting_ml/scripts/` with no Dagster caller at all | Enumerating **ALL scripts** in `scripts/` AND `betting_ml/scripts/` for a scheduled caller — not just auditing Dagster op definitions. E11.8's scheduling audit enumerated Dagster ops only, missing standalone scripts entirely. |
| **INC-12** (player_transactions monitor used effective_date — quiet days look stale; real bug was serving read non-determinism, but the sparse-feed monitor could have caught an actual feed failure earlier) | `effective_date` is an event-date that doesn't advance on days with no roster moves | The **event-date antipattern sweep** (E11.12 Part A) — flagging `effective_date` on a sparse feed as an event-date that can't distinguish "quiet day" from "broken feed," and switching to `ingestion_ts`. |

---

## Resolution quick-reference

| Alert | First check | Manual fix |
|-------|-------------|------------|
| `odds_freshness_alert_sensor` STALE | Railway `odds_capture` service logs | Restart odds_capture Railway service |
| `odds_freshness_alert_sensor` QUOTA | Odds-API dashboard: plan / renewal | Top up MAIN key or re-enable Parlay |
| `schedule_freshness_alert_sensor` | Railway `schedule_capture` service logs | `uv run python scripts/ingest_statsapi.py schedule` |
| `statcast_freshness_sensor` SLA | Baseball Savant publish time; savant_ingestion logs | `uv run python scripts/savant_ingestion.py batter_pitches` |
| `pregame_alert_sensor` | `pipeline_status` row for today; Dagster daily job run | Re-trigger `daily_ingestion_job` from Dagster UI |
| `model_health_alert_sensor` | `betting_ml.model_health_log`; serving feature coverage | Inspect post-lineup predictions for feature nulls |
| Archetype posteriors stale (WARN) | `mart_player_archetype_posteriors.as_of_date` | `uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --mode today` |
| Sprint speed stale (WARN) | `savant.sprint_speed_raw.snapshot_date` (MAX) | `uv run python scripts/ingest_sprint_speed.py --season $(date +%Y)` |
| Catcher framing stale (WARN) | `savant.catcher_framing_raw.snapshot_date` (MAX) | `uv run python scripts/ingest_catcher_framing.py --season $(date +%Y)` |
| OAA stale (WARN) | `external.oaa_team_season_raw.loaded_at` (MAX) | `uv run python scripts/ingest_oaa.py --season $(date +%Y)` |
| Player profiles stale (WARN) | `statsapi.player_profiles_raw.last_fetched_at` (MAX) | `uv run python scripts/ingest_player_profiles.py update` |
| Matchup-cell posteriors stale (WARN) | `betting.matchup_cell_sequential_posteriors.update_ts` (MAX) | `uv run python betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py --date $(date +%Y-%m-%d)` |
