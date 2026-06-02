# Baseball Data Mart Inventory
## Current State Reference — As of 2026-06-02 (7.M complete; sub-model signals live + orchestrated)

> **Update 2026-06-02:** All six sub-model signal generators now ship champions and write signals (run_env_v4, offense_v2, starter_v1, starter_ip_v1, bullpen_v1+v2, matchup_v1) — the §6 "signal mart Missing" gaps are closed. The signal generators are wired into the Dagster `daily_ingestion_job` (Epic O.2/8.6), scoring the recently-completed game window daily. `mart_sub_model_signals` lives in `baseball_data.betting` (not `betting_ml` — corrected below).

This document inventories every Snowflake table created via DDL scripts and every dbt model in the project. It is intended as a reference for understanding the current data modeling state and identifying gaps relative to the architecture described in `quant_sports_intel_models/baseball/refined_architecture_proposal.md`.

---

# Quick Reference

| Layer | Count | Location |
|---|---|---|
| Raw source tables (DDL) | 18 tables + 2 tasks + 4 procedures | `scripts/ddl/` |
| dbt sources | 35+ raw tables across 9 schemas | `dbt/models/sources.yml` |
| dbt staging models | 27 models | `dbt/models/staging/` |
| dbt mart models | 55 models | `dbt/models/mart/` |
| dbt feature models | 20 models (~400+ columns) | `dbt/models/feature/` |

**Data flow:**
```
Raw ingestion scripts
  → Raw tables (scripts/ddl/)
  → dbt staging (flatten, dedupe, rename)
  → dbt mart (rolling stats, archetypes, odds consensus, matchup matrices)
  → dbt feature (pre-game feature vectors, leakage guards)
  → predict_today.py (consumes feature_pregame_game_features)
```

---

# 1. Raw Source Tables (scripts/ddl/)

All raw tables follow an append-only design with `load_id` and `ingestion_ts` metadata columns. JSON payloads are stored as `raw_json VARIANT` alongside extracted convenience columns.

## 1.1 Odds API

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `mlb_events_raw` | `baseball_data.oddsapi` | one row per (ingestion_ts, event_id) | `event_id`, `commence_time`, `home_team`, `away_team`, `raw_json` | Append-only. Full JSON payload from /events endpoint. |
| `mlb_odds_raw` | `baseball_data.oddsapi` | one row per (ingestion_ts, event_id) | `event_id`, `bookmakers_count`, `http_status_code`, `raw_json` | Append-only. Nested bookmaker→market→outcome JSON. |
| `odds_snapshots_historical` | `baseball_data.oddsapi` | one row per (snapshot_ts, event_id) | `snapshot_ts`, `event_id`, `raw_json` | Historical snapshots 2021–2025 at 12:00/17:00/23:00 UTC. |

## 1.2 Stats API

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `monthly_schedule` | `baseball_data.statsapi` | one row per ingestion snapshot | `ingestion_ts`, `load_id`, `capture_reason`, `json_field` | **Append-only** (Epic T). Nested dates[] → games[] JSON. `capture_reason`: `'daily_full_month'` (once-daily) or `'intraday_gameday'` (30-min game-day cron). Dedup in staging via `qualify row_number() over (partition by game_pk order by ingestion_ts desc nulls last)`. |
| `venues_raw` | `baseball_data.statsapi` | one row per ingestion snapshot | `venue_id`, `json_field`, `ingest_date` | **Append-only** (Epic T). Hydrated fieldInfo (turf, roof), location, timezone. Dedup in staging by latest ingest_date per venue_id. |
| `player_transactions` | `baseball_data.statsapi` | one row per (transaction_id) | `transaction_id`, `player_id`, `team_id`, `transaction_date`, `type_code` | IL placements, activations, reinstatements. Daily 7-day lookback. |
| `umpire_game_log` | `baseball_data.statsapi` | one row per ingestion snapshot | `game_pk`, `umpire_name`, `umpire_id`, `k_pct`, `bb_pct`, `data_source`, `loaded_at` | **Append-only** (Epic T). UNIQUE constraint dropped. `data_source`: `'umpscorecards'` (historical, tendency metrics), `'statsapi'` (daily HP assignment), `'statsapi_backfill'` (recovery via backfill_umpire_assignments.py). Dedup in staging by `data_source` priority + `loaded_at desc`. |
| `weather_raw` | `baseball_data.statsapi` | one row per ingestion snapshot | `game_pk`, `venue_id`, `weather_observation_type`, `hours_to_first_pitch`, `temp_f`, `wind_speed_mph`, `loaded_at` | **Append-only** (Epic T). Outdoor parks only. `weather_observation_type`: `'forecast_pregame'` (daily), `'observed_at_first_pitch'` (archive after game), `'forecast_intraday'` (T-24h/T-6h/T-3h/T-1h). Dedup in staging partitioned by `(game_pk, venue_id, weather_observation_type, hours_to_first_pitch)`. |
| `pitcher_clusters` | `baseball_data.statsapi` | one row per (pitcher_id, season) | `pitcher_id`, `cluster_id`, `cluster_label` | K-means cluster assignments computed by betting_ml/scripts. |
| `batter_clusters` | `baseball_data.statsapi` | one row per (batter_id, season) | `batter_id`, `cluster_id`, `cluster_label` | K-means cluster assignments. |

## 1.3 Baseball Savant

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `batter_pitches` | `baseball_data.savant` | one row per pitch | `pitch_sk` (MD5), `game_pk`, `batter_id`, `pitcher_id`, `pitch_type`, `launch_speed`, `estimated_woba` | ~140 columns. Includes bat tracking (2023-07-14+), xBA, xwOBA, game context, fielder assignments. |
| `catcher_framing_raw` | `baseball_data.savant` | one row per ingestion snapshot | `player_id`, `season`, `snapshot_date`, `framing_runs`, `defensive_runs`, `ingestion_timestamp` | **Append-only** (Epic T). FanGraphs catcher framing. Weekly snapshots. Dedup in staging partitioned by `(player_id, season, snapshot_date)`. |
| `ref_players` | `baseball_data.savant` | one row per player | `mlb_bam_id`, `player_name` | Player reference. MLBAM ID to name mapping. |

## 1.4 FanGraphs

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `fg_stuff_plus_raw` | `baseball_data.fangraphs` | one row per (pitcher_id, season, load_id) | `fg_pitcher_id`, `season`, `stuff_plus`, `location_plus`, `pitching_plus` | Append-only. Full Stuff+ leaderboard snapshots. 2020+. |
| `fg_zips_pitching_raw` | `baseball_data.fangraphs` | one row per (pitcher_id, season, projection_type, load_id) | `fg_pitcher_id`, `projection_type`, `era`, `strikeout_rate` | ZiPS, Steamer, rZIPS projections. |
| `fg_zips_hitting_raw` | `baseball_data.fangraphs` | one row per (batter_id, season, projection_type, load_id) | `fg_batter_id`, `projection_type`, `woba`, `hr` | ZiPS, Steamer, rZIPS projections. |
| `fg_hitting_leaderboard_raw` | `baseball_data.fangraphs` | one row per (batter_id, season, window_type, load_id) | `fg_batter_id`, `window_type`, `woba`, `xwoba`, `iso`, `bb_pct` | Rolling windows: 7d, 14d, 30d, season. Append-only. |

## 1.5 Action Network

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `public_betting_raw` | `baseball_data.actionnetwork` | one row per ingestion snapshot | `game_date`, `an_game_id`, `home_ml_money_pct`, `away_ml_money_pct`, `over_money_pct`, `under_money_pct`, `ingestion_timestamp` | **Append-only** (Epic T). Public betting percentages (moneyline & totals). Data available from 2024-02-22 onward only; pre-2024 is permanently unrecoverable. Dedup in staging partitioned by `(game_date, an_game_id)`. |

## 1.6 External / Computed

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `oaa_team_season_raw` | `baseball_data.external` | one row per ingestion snapshot | `team_abbrev`, `game_year`, `oaa`, `drs`, `n_opportunities`, `defense`, `loaded_at` | **Append-only** (Epic T). Team OAA/DRS from FanGraphs fielding leaderboard. 2016+. Backfill via weekly snapshots is not feasible (FanGraphs API ignores startdate/enddate for OAA — forward-only from T.4.C conversion date). Dedup in mart via `qualify row_number() over (partition by team_abbrev, game_year order by loaded_at desc nulls last)`. |
| `team_elo_history` | `baseball_data.betting` | one row per (game_pk, team_abbrev) | `game_pk`, `team_abbrev`, `elo_pre`, `elo_post` | Pre/post-game Elo ratings. Computed by compute_elo.py (K=4, HOME_ADV=24, season regression to 1500). |

## 1.7 Monitoring & Config

| Table | Schema | Grain | Notes |
|---|---|---|---|
| `model_health_log` | `baseball_data.betting_ml` | one row per (run_date, target, window_days) | ECE, Brier, sample size, alert flag. Written by compute_model_health.py. |
| `placed_bets` | `baseball_data.betting_ml` | one row per bet_id | Individual bet records with outcome tracking. American odds, stake, Kelly, EV, profit/loss. |
| `daily_model_predictions` | `baseball_data.betting_ml` | one row per (score_date, game_pk, model_version) | Written by predict_today.py. Includes calibrated_win_prob, data_source flag. |
| `pipeline_run_log` | `baseball_data.config` | one row per (task_name, run_ts) | Orchestration audit. Written by Snowflake task DAG. |
| `lineup_monitor_state` | `baseball_data.config` | one row per (game_pk) | Lineup confirmation state tracking for re-scoring trigger. |

## 1.8 Parlay API

Parlay API is the replacement for The Odds API (hard cutover 2026-06-01). All tables live in `baseball_data.parlayapi`. Provisioned via `scripts/ddl/parlayapi_raw_tables.sql`. Auth: X-API-Key header for most endpoints; `/events/canonical` requires `apiKey` query param instead.

| Table | Schema | Grain | Key Columns | Notes |
|---|---|---|---|---|
| `mlb_events_raw` | `baseball_data.parlayapi` | one row per ingestion run | `ingestion_ts`, `load_id`, `event_id`, `canonical_event_id`, `commence_time`, `home_team`, `away_team`, `raw_json` | Full response from `/v1/sports/baseball_mlb/events`. `commence_time` is 19:00:00Z placeholder for all games. |
| `mlb_odds_raw` | `baseball_data.parlayapi` | one row per ingestion run | `ingestion_ts`, `load_id`, `event_id`, `canonical_event_id`, `bookmakers_count`, `raw_json` | Full response from `/v1/sports/baseball_mlb/odds`. Nested bookmaker→market→outcome JSON. |
| `mlb_matches_raw` | `baseball_data.parlayapi` | one row per ingestion run | `ingestion_ts`, `load_id`, `game_date`, `record_count`, `raw_json` | From `/v1/historical/sports/baseball_mlb/matches`. Flat per-source array with game results and `has_odds` flag. |
| `mlb_line_movement_raw` | `baseball_data.parlayapi` | one row per ingestion run per event_id | `ingestion_ts`, `load_id`, `event_id`, `record_count`, `markets_captured`, `raw_json` | From `/v1/sports/baseball_mlb/line-movement`. `raw_json` contains a nested `snapshots[]` array of timestamped price changes per (source × market). |
| `mlb_canonical_events_raw` | `baseball_data.parlayapi` | one row per ingestion run | `ingestion_ts`, `load_id`, `sport_key`, `event_count`, `raw_json` | From `/v1/sports/baseball_mlb/events/canonical`. **Only Parlay API endpoint with real per-game start times.** Response has no `event_id` — only `canonical_event_id`. Added Story 0.10. |

## 1.9 Sub-Model Signal Outputs (script-managed)

Written by the `betting_ml/scripts/**/generate_*_signals.py` champions (not dbt models; `CREATE TABLE IF NOT EXISTS` + MERGE / SCD-2). Refreshed daily for the recently-completed game window by the Dagster `daily_ingestion_job` signal phase (Epic O.2 / 8.6). Consumed by the `feature_pregame_sub_model_signals` PIVOT (§4).

| Table | Schema | Grain | Writer | Notes |
|---|---|---|---|---|
| `mart_sub_model_signals` | `baseball_data.betting` | (game_pk, side, signal_name, sub_model_version) SCD-2 | `scd2_writer.py` | Long-format SCD-2 store (~757K rows). Holds run_env_v4, bullpen_v1, bullpen_v2, matchup_v1 signal rows. `is_current`, `valid_from`, `valid_to`, `computed_at`, `record_hash`. **Lives in `betting`, not `betting_ml`.** |
| `offense_v2_signals` | `baseball_data.betting_features` | (game_pk, side, model_version) | `offense_v2/generate_offense_signals.py` | NegBin: pred_runs_mu, pred_runs_dispersion, pred_runs_raw, uncertainty. MERGE upsert. |
| `starter_suppression_signals` | `baseball_data.betting_features` | (game_pk, side, model_version) | `starter_v1/generate_starter_signals.py` | Normal: starter_suppression_mu/sigma/signal, uncertainty. MERGE upsert. |
| `starter_ip_signals` | `baseball_data.betting_features` | (game_pk, side, model_version) | `starter_v1/generate_starter_ip_signals.py` | NegBin (outs): starter_ip_mu, dispersion, signal, p80/p20_outs, uncertainty, is_bulk_usage. MERGE upsert. |

## 1.10 Snowflake Tasks & Procedures

| Object | Type | Schedule | Purpose |
|---|---|---|---|
| `task_lineup_monitor` | Task + Procedure | Hourly (0 * * * * ET) | Polls for confirmed lineups; triggers dbt_staging_build.yml via GitHub Actions. **⚠️ MIGRATION GAP (2026-06-02): still RESUMED but superseded by the Dagster `lineup_monitor_sensor` (Epic 0.5.7).** Both write `baseball_data.config.lineup_monitor_state`; the task wins the hourly race and marks games triggered, so the sensor finds no new lineups and fires only rarely (4× since deploy). **Action: `ALTER TASK baseball_data.config.task_lineup_monitor SUSPEND;`** to let the Dagster sensor own lineup monitoring (completes 0.5.10 decommission). |
| `proc_savant_ingestion` | Procedure | On-demand | Fetches prior-day Statcast CSV incrementally from Baseball Savant. |

---

# 2. dbt Staging Models

All staging models output to `baseball_data.betting`. Default materialization: `table` unless noted.

## 2.1 Odds API Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_oddsapi_events` | one row per event_id (latest snapshot) | Deduplicates to latest snapshot per event. Excludes null raw_json. | table |
| `stg_oddsapi_odds` | (ingestion_ts, event_id, bookmaker, market, outcome) | 3-level lateral flatten: bookmakers → markets → outcomes. Deduplicates us/us2 regions within load_id. | table |

## 2.2 Action Network Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_actionnetwork_public_betting` | (game_date, an_game_id) | Cleans betting percentages for moneyline and totals markets. | table |
| `stg_actionnetwork_public_betting_snapshots` | (game_pk, loaded_at) | All ingestion snapshots from public_betting_raw, normalized (ARI→AZ) and joined to mart_game_results for game_pk resolution. Record hash on (home_ml_money_pct, home_ml_ticket_pct, over_money_pct, over_ticket_pct). Same-day unresolved games excluded until game completes. Coverage: 2026-05-07 (Epic T.3) onward. **Added Epic 15 Story 15.6.** | table |

## 2.3 Stats API Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_statsapi_games` | one row per game_pk | Flattens nested dates[] → games[] JSON. Extracts score, teams, status. | table |
| `stg_statsapi_lineups` | (game_pk, player_id, side) | Flattens batting-order lineup from schedule response. One row per player. | table |
| `stg_statsapi_lineups_wide` | (game_pk, side) | Pivots lineup to wide format — one column per batting slot (1–9). | table |
| `stg_statsapi_probable_pitchers` | (game_pk, side) | Extracts home/away probable pitchers from schedule response. QUALIFY-deduped to latest snapshot per (game_pk, side). Used by matchup models. | table |
| `stg_statsapi_starter_snapshots` | (game_pk, side, ingestion_ts) | All ingestion snapshots of probable pitcher from `monthly_schedule` — no latest-only dedup. Feeds `feature_pregame_starter_status` SCD-2 model. QUALIFY deduplicates at `(game_pk, side, ingestion_ts)` to handle same game appearing in multiple monthly fetch responses simultaneously. Pre-Epic-T null `ingestion_ts` coalesced to sentinel `1970-01-01`. **Added Epic 15 Story 15.4.** | table |
| `stg_statsapi_venues` | venue_id | Flattens venue JSON (roof_type, turf, coordinates, timezone). | table |
| `stg_statsapi_player_injury_status` | (player_id, transaction_date) | Derives IL status (10d, 60d, 7d, none) from transaction type codes. | table |
| `stg_statsapi_player_profiles` | one row per player_id (latest) | Deduplicates player_profiles_raw to latest by last_fetched_at. Exposes full_name, birth_date, height_inches, weight_lbs, primary_position_code, active flag. Used for age computation in archetype clustering. | table |
| `stg_statsapi_transactions` | one row per transaction_id | Deduplicates from player_transactions raw table. IL placements, activations, reinstatements with player_id, team_id, transaction_date, type_code. Card 7.I. | table |
| `stg_statsapi_umpire_game_log` | (game_pk, umpire_name) | Cleans umpire assignment + tendency metrics. Computes trailing z-scores. | table |
| `stg_statsapi_umpire_snapshots` | (game_pk, loaded_at) | All ingestion snapshots from statsapi.umpire_game_log — no latest-only dedup. QUALIFY deduplicates at (game_pk, loaded_at) preferring umpscorecards rows. Record hash on (umpire_name, total_runs, total_run_impact, accuracy_above_expected). Feeds feature_pregame_umpire_status SCD-2. Coverage: ~2026-05-02 (Epic T.4). **Added Epic 15 Story 15.7.** | table |

## 2.4 Savant / Statcast Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_batter_pitches` | one row per pitch | Renames to snake_case. MD5 surrogate key on (game_pk, at_bat_number, pitch_number, batter_id, pitcher_id, inning, inning_half). Suppresses deprecated PitchF/X fields. | table |
| `stg_batter_sprint_speed` | one row per (player_mlbam_id, season) — latest snapshot | Deduplicates sprint_speed_raw to most recent snapshot_date per player × season. Exposes Statcast sprint speed (ft/s). Used in lineup features. | table |
| `stg_weather_raw` | (game_pk, venue_id) | Cleans and validates weather observations. QUALIFY deduplicates to latest row per (game_pk, venue_id, observation_type, hours_to_first_pitch). | view |
| `stg_weather_raw_snapshots` | (game_pk, loaded_at) | All forecast_pregame ingestion snapshots from weather_raw — no latest-only dedup. Pre-computes wind_component_mph and is_dome via ref_venues join. Adds record_hash over (temp_f, wind_component_mph, humidity_pct, condition_text). Feeds feature_pregame_weather_status SCD-2 model. Coverage: Epic T.2 (2026-05-01) onward. **Added Epic 15 Story 15.5.** | table |

## 2.5 FanGraphs Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_fangraphs__stuff_plus` | (fg_pitcher_id, season) — latest ingestion | Deduplicates to latest. Unpacks pitch-mix percentages (FA, SI, FC, SL, CU, CH, FS). | table |
| `stg_fangraphs__pitcher_arsenal` | (fg_pitcher_id, pitch_type, season) | Unpivots the wide Stuff+ raw payload into per-pitch-type rows. Normalizes FA/FF (pfx vs. sp system naming). Source: fg_stuff_plus_raw. | table |
| `stg_fangraphs__hitting_leaderboard` | (fg_batter_id, season, window_type, window_date_range) | Deduplicates raw snapshot. Unpacks rolling hitting stats. | table |
| `stg_fangraphs__zips_pitching` | (fg_pitcher_id, season, projection_type) — latest | Deduplicates. Unpacks ZiPS/Steamer pitching projections. | table |
| `stg_fangraphs__zips_hitting` | (fg_batter_id, season, projection_type) — latest | Deduplicates. Unpacks ZiPS/Steamer hitting projections. | table |

## 2.6 Parlay API Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_parlayapi_odds` | `(ingestion_ts, event_id, bookmaker_key, market_key, outcome_name)` | 3-level lateral flatten: events → bookmakers → markets → outcomes. Includes `canonical_event_id` and `source_system = 'parlay_api'` discriminator. `commence_time` is 19:00:00Z placeholder for all rows. | table |
| `stg_parlayapi_line_movement` | `(ingestion_ts, event_id, bookmaker_key, market_key, player, snapshot_ts)` | Two-level lateral flatten: response array → per-(source × market), then `snapshots[]` → one row per timestamped price point. Live-data-only (no historical `_an`-suffix books). | table |
| `stg_parlayapi_canonical_events` | `(ingestion_ts, canonical_event_id)` | Lateral flatten of `raw_json` array. Converts empty-string `commence_time` to NULL via `NULLIF`. Exposes real per-game scheduled start times. No `event_id` present — join via `stg_parlayapi_odds` bridge on `canonical_event_id`. **Added Story 0.10.** | table |

---

# 3. dbt Mart Models

All mart models output to `baseball_data.betting`. Most materialize as `table`; 13 use incremental MERGE on game_date or pitch_sk.

## 3.1 Game & Odds Foundation

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_game_results` | one row per game_pk | incremental (game_date) | Game scores, teams, home/away outcomes. Source of truth for training labels. |
| `mart_odds_events` | (ingestion_ts, event_id) | table | Cleaned event snapshots from Odds API. |
| `mart_odds_outcomes` | (event_id, bookmaker, market, outcome) | table | All bookmaker lines per market per event. |
| `mart_odds_consensus` | (event_id, market_key) | table | Vig-free consensus probability across all books. |
| `mart_odds_line_movement` | `game_pk` | table | Opening and pre-game implied probabilities per game. h2h and totals line movement as signed deltas (pregame − open). 2021–2025: Odds API historical snapshots. 2026+: Parlay API hourly snapshots with real commence_time leakage guard sourced from `stg_parlayapi_canonical_events` (Story 0.10). Bookmaker: bovada. |
| `mart_closing_line_value` | (game_pk, prediction_date) | table | Model probability vs closing market odds. CLV computation. |
| `mart_prediction_clv` | (game_pk, prediction_date) | table | Full CLV evaluation: model edge, market edge, CLV, realized outcome. |
| `mart_bookmaker_disagreement` | (game_pk, snapshot_date) | table | Morning-snapshot spread across sharp and soft book tiers. 7 disagreement features. |
| `mart_game_odds_bridge` | (game_pk, event_id) | table | Maps Stats API game_pk to Parlay API event_id (2026+) or Odds API event_id (historical). Crosswalk for joining odds snapshots to game features. |

## 3.2 Team Rolling Stats

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_team_rolling_offense` | (team, game_date) | table | 30-day rolling team offensive metrics (runs, wOBA, strikeout rate, walk rate). |
| `mart_team_rolling_pitching` | (team, game_date) | table | 30-day rolling team pitching metrics (ERA, FIP, strikeout rate). |
| `mart_team_pythagorean_rolling` | (team, game_date) | table | Rolling Pythagorean win% and residual (actual W% minus Pythagorean). Regression-to-mean indicator. **New in Phase 8.** |
| `mart_team_season_record` | (team, season, record_date) | table | Running win-loss record through each game date. |
| `mart_team_schedule_context` | (team, game_pk) | table | Days rest, home/away status, back-to-back flag, travel context. |
| `mart_team_fielding_oaa` | (team, season) | table | Team OAA and DRS from FanGraphs fielding leaderboard. Current-season refresh. |
| `mart_team_base_state_splits` | (team, game_date) | table | Rolling run-scoring efficiency in runners-on, RISP, and late-inning situations. **New in Phase 8.** |
| `mart_home_away_splits` | (team, season) | table | Season home/away offensive and pitching splits (wOBA, ERA, runs). |
| `mart_team_vs_pitcher_hand` | (team, game_date, pitcher_hand) | table | Rolling team offensive splits vs LHP and RHP. Handedness-adjusted run-scoring rates. |
| `mart_head_to_head_team_history` | (home_team, away_team, season) | table | Season head-to-head team records, runs scored/allowed, and recent form. |

## 3.3 Player Rolling Stats

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_batter_rolling_stats` | (batter_id, game_date) | table | 30-day rolling batter stats: wOBA, ISO, strikeout%, walk%, wOBA differential. |
| `mart_pitcher_rolling_stats` | (pitcher_id, game_date) | table | 30-day rolling pitcher stats: ERA, FIP, K%, BB%, HR rate. |
| `mart_starting_pitcher_game_log` | (pitcher_id, game_pk) | incremental (game_date) | Per-start game log for starter trend analysis. |
| `mart_starter_csw_rolling` | (pitcher_id, game_date) | table | Rolling CSW% (called strikes + whiffs per pitch) by pitch type and overall. Last 3 and last 5 starts. **Added Phase 8.** |
| `mart_starter_pitch_mix_rolling` | (pitcher_id, game_date) | table | Rolling pitch-mix percentages vs. historical baseline. Drift score from baseline. **New in Phase 8.** |

## 3.4 Player Profiles & Splits

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_batter_profile_summary` | (batter_id, season) | table | Season batting profile: PA, wOBA, strikeout%, walk%, HR%, hard-hit%. |
| `mart_batter_vs_handedness_splits` | (batter_id, season, pitcher_hand) | table | Prior-season platoon splits vs LHP and RHP. |
| `mart_pitcher_arsenal_summary` | (pitcher_id, season) | table | Pitcher arsenal composition and effectiveness per pitch type. |
| `mart_pitcher_profile_summary` | (pitcher_id, game_year) | table | Pitcher season profile for k-means archetype clustering (Card 7.2). Joins arsenal summary (pitch mix, velocity, movement, Stuff+) with outcome metrics (K%, BB%, whiff rate, GB rate). Includes birth_date from stg_statsapi_player_profiles for age computation. Stratum-B features NULL 2015–2019. Season coverage: 2015+. |
| `mart_pitcher_vs_handedness_splits` | (pitcher_id, season, batter_hand) | table | Prior-season platoon performance vs LHB and RHB. |

## 3.5 Bullpen

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_bullpen_effectiveness` | (team, game_date) | table | Rolling bullpen ERA, xwOBA, K/BB by team. Handedness mix. |
| `mart_bullpen_handedness_splits` | (team, season, batter_hand) | table | Bullpen ERA and xwOBA allowed vs LHB and RHB. |
| `mart_bullpen_leverage` | (team, game_date) | table | Leverage-weighted bullpen workload. IP in prior 1/2/3 days. High-leverage arm usage. Closer availability proxy. **Added Phase 8.** |
| `mart_bullpen_workload` | (team, game_date) | table | Raw bullpen workload: appearances, IP, days since last outing per reliever. |

## 3.6 Catcher

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_catcher_framing` | (catcher_id, season) | table | Blended framing runs saved and defensive runs from FanGraphs. 99.8% game coverage. **Added Phase 8.** |

## 3.7 Matchup & Archetype

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_batter_archetype_vs_pitcher_cluster` | (batter_cluster_id, pitcher_cluster_id, season) | incremental (season) | Cross-tabulation of batter archetype × pitcher cluster matchup outcomes (wOBA, K%, BB%, hard-hit%). Population-level matchup matrix. |
| `mart_batter_bat_tracking_profile` | (batter_id, game_date) | table | Rolling bat tracking metrics: bat speed, swing length, attack angle (2023-07-14+). |
| `mart_pitcher_batter_history` | (pitcher_id, batter_id) | table | Career pitcher-batter head-to-head history: PA, strikeout%, walk%, wOBA, xwOBA. Bayesian-shrunk estimates for low-PA pairs. |
| `mart_pitcher_pitch_archetype` | (pitcher_id, season) | table | Pitcher pitch mix by archetype (power FB, breaking ball heavy, soft/command, mixed). |
| `mart_batter_vs_pitch_archetype` | (batter_id, season, pitch_archetype) | table | Batter performance by pitch archetype (wOBA, K%, BB%, ISO). |
| `mart_batter_woba_vs_cluster` | (batter_id, pitcher_cluster_id, season) | table | Batter wOBA by pitcher cluster. Generalization of individual h2h for sparse pairs. |
| `mart_pitcher_cluster_matchups` | (pitcher_cluster_id, batter_cluster_id, season) | table | Aggregate matchup stats by cluster pair. Used when individual h2h sample is insufficient. |

## 3.8 Park & Venue

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_park_run_factors` | (venue_id, season) | table | Prior-season park run factors: home run rate, total runs per game. |
| `mart_eb_park_factors` | (venue_id, season) | table | Thin passthrough over `betting.eb_park_factors_raw` (MERGE-upserted by fit_park_priors.py). Exposes EB-smoothed overall run factor, uncertainty, shrinkage_factor, prior_mean/variance, n_games. Feature layer joins on game_year − 1. Replaces raw_park_run_factor_3yr in `feature_pregame_park_features`. |
| `mart_park_factors_granular` | (venue_id, season) | table | EB-smoothed granular park factors (HR, 2B/3B, 1B, BB, SO, wOBA) from Baseball Savant statcast-park-factors (3yr rolling, all bat sides). Written by fit_granular_park_priors.py (Epic 3A.2). All eb_* columns are ratios (1.0 = league average). Feature layer joins on game_year − 1. |

## 3.9 Pitch-Level Facts (Incremental)

All seven models below are incremental MERGE on `pitch_sk` or `(game_pk, game_date)`.

| Model | Grain | Description |
|---|---|---|
| `mart_pitch_characteristics` | one row per pitch | Pitch physics: type, velocity, spin rate, movement, release point. |
| `mart_pitch_play_event` | one row per pitch | Game-state context: score, outs, baserunners, leverage. |
| `mart_pitch_game_context` | one row per pitch | Score differential, inning, count state at pitch time. |
| `mart_pitch_fielding` | one row per pitch | Fielding alignment, shift flag, spray chart context. |
| `mart_pitch_hitter_profile` | one row per pitch | Batter season stats at time of pitch. |
| `mart_pitch_pitcher_profile` | one row per pitch | Pitcher season stats at time of pitch. |
| `mart_pitch_hit_characteristics` | one row per pitch | Hit outcome: launch angle, exit velocity, xBA, xwOBA, hit type. |

## 3.10 FanGraphs Dimensions & Facts

| Model | Schema | Grain | Description |
|---|---|---|---|
| `dim_fangraphs_player_xref` | betting | (fg_player_id) | FanGraphs ↔ MLBAM ID crossref. |
| `fct_fangraphs_hitting_analytics` | betting | (fg_batter_id, season, window_type) | Rolling hitting leaderboard (wOBA, ISO, K%, by window). |
| `fct_fangraphs_pitching_analytics` | betting | (fg_pitcher_id, season) | ZiPS projections aggregated + Stuff+ metrics. |
| `fct_fangraphs_pitcher_arsenal_wide` | betting | (fg_pitcher_id, season) | Pitcher arsenal breakdown (FA%, SL%, CH%, CU% etc.) in wide format. |

---

# 4. dbt Feature Models

All feature models output to `baseball_data.betting_features`. All materialize as `table`. Grain is `game_pk` for the master table and `game_pk × side` for per-team detail tables.

**Leakage guards enforced across all models:**
- Rolling window joins use `game_date < official_date` (strictly less than — excludes game-day data)
- Platoon splits: prior season only (`season - 1`)
- Park run factors: prior season only
- Season record: `record_date = official_date - 1` (day before game)

| Model | Grain | Upstream | ~Columns | Description |
|---|---|---|---|---|
| `feature_pregame_injury_status` | (player_id, valid_from) | stg_statsapi_player_injury_status | ~8 | SCD-2 table tracking IL status per player. `valid_from`/`valid_to` are midnight TIMESTAMP_NTZ casts of status dates. `is_current = true` = currently on IL. Zero-length intervals (same-day place+activate noise) filtered at this layer. Consumed by `feature_pregame_lineup_features` slot_injury CTE for injury-adjusted wOBA. **Added Epic 15 Story 15.3.** Coverage: 2021-03-01 onward. |
| `feature_pregame_starter_status` | (game_pk, side, valid_from) | stg_statsapi_starter_snapshots | ~8 | SCD-2 table tracking probable starter changes per game/side. `valid_from` = ingestion_ts when pitcher identity changed (detected via LAG). `is_current = true` = most recent assignment. Sentinel `valid_from = 1970-01-01` for pre-Epic-T games (no intraday change history available). Consumed by `feature_pregame_starter_features` `probable_pitchers` CTE. **Added Epic 15 Story 15.4.** Coverage: Full history (static) pre-Epic-T; intraday scratch tracking from 2026-05-12 onward. |
| `feature_pregame_weather_status` | (game_pk, valid_from) | stg_weather_raw_snapshots | ~10 | SCD-2 table tracking forecast_pregame weather state per game. New row only when hash(temp_f, wind_component_mph, humidity_pct, condition_text) changes between fetches. `is_current = true` = most recent forecast. wind_component_mph pre-computed from ref_venues. Consumed by `feature_pregame_weather_features` via `is_current = true` filter. 3 SCD-2 singular tests. **Added Epic 15 Story 15.5.** Coverage: Epic T.2 (2026-05-01) onward. |
| `feature_pregame_public_betting_status` | (game_pk, valid_from) | stg_actionnetwork_public_betting_snapshots | ~13 | SCD-2 table tracking Action Network public betting % per game. New row only when hash(home_ml_money_pct, home_ml_ticket_pct, over_money_pct, over_ticket_pct) changes. Single denormalized row per game (ML + totals co-located). Dual coverage gap: (1) Action Network pre-2024-02-22 unrecoverable; (2) pre-Epic-T snapshots not captured. 3 SCD-2 singular tests. **Added Epic 15 Story 15.6.** Coverage: 2026-05-07 (Epic T.3) onward. |
| `feature_pregame_public_betting_features` | game_pk | feature_pregame_public_betting_status (SCD-2) | ~12 | Current-state view over feature_pregame_public_betting_status (is_current = true). Grain: one row per game_pk. Replaces direct stg_actionnetwork_public_betting join in downstream models. **Added Epic 15 Story 15.6.** |
| `feature_pregame_lineup_features` | (game_pk, side) | mart_batter_rolling_stats, mart_batter_vs_handedness_splits, mart_batter_profile_summary, stg_fangraphs__zips_hitting, mart_batter_bat_tracking_profile, **feature_pregame_injury_status** (SCD-2) | ~55 | Aggregates 30-day rolling and season-to-date batter stats across all 9 lineup slots. LHB/RHB counts. Handedness-specific wOBA (vs LHP/RHP). ZiPS hitting projections per slot with Bayesian rookie shrinkage (k=200 PA, Story 2.6). Bat-tracking columns (lineup_avg_bat_speed, lineup_bat_speed_std, lineup_avg_swing_length, lineup_avg_attack_angle, lineup_bat_speed_vs_starter_velo) — NULL pre-2023-07-14 (Story 2.9). SCD-2 columns present (valid_from, valid_to, is_current, computed_at, record_hash). `slot_injury` CTE reads from `feature_pregame_injury_status` with point-in-time `valid_from`/`valid_to` filter (Epic 15 Story 15.3). |
| `feature_pregame_starter_features` | (game_pk, side) | mart_starter_rolling_stats, mart_pitcher_vs_handedness_splits, mart_starter_csw_rolling, mart_starter_pitch_mix_rolling, **feature_pregame_starter_status** (SCD-2) | ~30 | 30-day rolling starter stats + career platoon splits. CSW% last 3 starts. Pitch-mix drift score. NULL when pitcher has <30 IP career history. `probable_pitchers` CTE reads from `feature_pregame_starter_status WHERE is_current = true` (Epic 15 Story 15.4); previously read from `stg_statsapi_probable_pitchers`. |
| `feature_pregame_bullpen_state_features` | (game_pk, side) | mart_bullpen_effectiveness, mart_bullpen_workload, mart_bullpen_leverage | ~25 | Bullpen effectiveness, leverage workload, handedness mix. High-leverage IP prior 1/3 days. Closer availability proxy. |
| `feature_pregame_team_features` | (game_pk, side) | mart_team_rolling_offense, mart_team_rolling_pitching, mart_team_schedule_context, mart_team_pythagorean_rolling, mart_team_base_state_splits | ~20 | 30-day rolling team offensive/pitching metrics. Schedule context (days rest, home/away, back-to-back). Pythagorean residual. Base-state efficiency. |
| `feature_pregame_odds_features` | game_pk | mart_odds_outcomes, mart_odds_line_movement, mart_bookmaker_disagreement, stg_actionnetwork_public_betting | ~15 | Market-implied probabilities, bookmaker disagreement spread (7 features), public betting percentages. Market columns — subject to exclusion in market-blind retrains. |
| `feature_pregame_park_status` | (venue_id, season) | mart_eb_park_factors, stg_statsapi_venues (SCD-2) | ~7 | SCD-2 table for park factors. Natural key: (venue_id, season). valid_from = first game at venue for season; valid_to = first game of next season (NULL for current active venues). Retired venues closed with season_close + 1 day. 362 rows, 36 venues, 30 active (2026). No snapshot staging — source is annual grain. **Added Epic 15 Story 15.8.** |
| `feature_pregame_park_features` | game_pk | mart_park_run_factors | ~5 | Prior-season park run factors. NULL for season-opening games (no prior-season data). NOT re-pointed to SCD-2 — game_year-1 join is already correct; use feature_pregame_park_status for AS-OF queries. |
| `feature_pregame_weather_features` | game_pk | **feature_pregame_weather_status** (SCD-2) | ~5 | Wind speed, wind direction, temperature, humidity. NULL for dome stadiums. Re-pointed to SCD-2 source in Epic 15 Story 15.5; reads `is_current = true` rows. |
| `feature_pregame_umpire_status` | (game_pk, valid_from) | stg_statsapi_umpire_snapshots (SCD-2) | ~10 | SCD-2 table for HP umpire assignments. Natural key: game_pk (one HP ump per game; no ump_position column in source). New row when umpire_name or tendency stats change. Coverage: ~2026-05-02 (Epic T.4). **Added Epic 15 Story 15.7.** |
| `feature_pregame_umpire_features` | game_pk | stg_statsapi_umpire_game_log | ~8 | HP umpire assignment + trailing z-scores of tendency metrics (called strikes above avg, run expectancy delta, run impact, accuracy). Reads stg_statsapi_umpire_game_log directly (not re-pointed to SCD-2) — forward-only SCD-2 coverage would break historical trailing z-score computation. feature_pregame_umpire_status available for AS-OF point-in-time queries. |
| `feature_pregame_game_features` | game_pk (master) | All feature_pregame_* tables, mart_game_results, mart_catcher_framing | ~285+ | Master pre-game feature table. Joins lineup, starter, team, odds, park, weather, umpire, cluster matchup, batter archetype matchup, H2H matchup, line movement, bookmaker disagreement, bullpen handedness/leverage, base-state splits, and public betting feature models. **Does NOT join feature_pregame_sub_model_signals** — that integration is Layer 3 (Epic 9). `has_full_data` flag selects games with complete lineups, starters with 30+ IP history, and prior-season park factors. Consumed by predict_today.py and training scripts. Bat-tracking columns added Story 2.9. EB batter posteriors (avg_eb_woba/k_pct/bb_pct/iso/uncertainty, eb_coverage_pct × home/away), EB starter posteriors (eb_xwoba_against/k_pct/bb_pct/xwoba_uncertainty × home/away), and EB bullpen quality (bp_eb_xwoba/uncertainty/coverage_pct × home/away) added to SQL (Epic 7.M, 2026-06-01) — requires `dbtf run -s feature_pregame_game_features` + `validate_feature_selection.py` re-run to propagate. |
| `feature_pregame_sub_model_signals` | (game_pk, side) | mart_sub_model_signals (`baseball_data.betting`), offense_v2_signals, starter_suppression_signals, starter_ip_signals (`baseball_data.betting_features`) | dynamic | Wide-format pivot over mart_sub_model_signals + direct JOINs to the dedicated `*_signals` tables (§1.9). Each registered (signal_name, sub_model_version) pair becomes one column via MAX(CASE WHEN) static pivot. SCD-2 filtered to is_current = true. Refreshed daily by `dbt_sub_model_signals_rebuild` in the Dagster signal phase (Epic O.2). **Registered signal blocks:** run_env_v3/v4 (run_env_mu, run_env_dispersion, run_env_signal, environment_volatility); offense_v1 (pred_runs_raw, runs_index); offense_v2 (pred_runs_mu, pred_runs_dispersion, pred_runs_raw, uncertainty); starter_v1 (starter_suppression_mu/sigma/signal, uncertainty — via direct JOIN); starter_ip_v1 (starter_ip_mu, starter_ip_dispersion, starter_ip_signal, starter_ip_p80_outs, starter_ip_p20_outs, starter_ip_uncertainty, starter_ip_is_bulk_usage — **OUTS UNITS: divide by 3.0 for innings display; keep as outs for NegBin CDF in 6D Candidate B** — via direct JOIN); bullpen_v1 (availability_index, fatigue_signal, quality_mu/sigma/signal, high_leverage_availability_proxy, late_game_volatility_signal); bullpen_v2 (bullpen_mu, bullpen_dispersion, bullpen_fatigue_adjusted_mu, uncertainty — NegBin distributional, Epic 6D); **matchup_v1 (matchup_advantage_mu/sigma, matchup_volatility_signal, matchup_soft_vs_hard_delta, matchup_k_pressure_signal, matchup_power_signal — Ridge soft-mixture, Epic 8; availability-gated, null for sparse-archetype games).** **Added Epic 2, Story 2.1. Last updated Epic 8.4 (matchup block) + Epic O.2 daily refresh (2026-06-02).** |
| `feature_pitcher_batter_h2h_matchups` | (game_pk, batter_id) | mart_pitcher_batter_history, mart_pitcher_pitch_archetype, mart_batter_vs_pitch_archetype | ~20 | Career h2h history for each batter vs today's opposing starter. PA, K%, wOBA, xwOBA with Bayesian shrinkage for low-sample pairs. |
| `feature_pitcher_cluster_matchups` | (game_pk, batter_id) | statsapi.pitcher_clusters, statsapi.batter_clusters, mart_batter_archetype_vs_pitcher_cluster | ~10 | Batter archetype vs pitcher cluster matchup stats. Generalization when direct h2h history is sparse. 6-cluster batter taxonomy. |
| `feature_batter_archetype_matchups` | (game_pk, batter_id) | statsapi.batter_clusters, mart_batter_archetype_vs_pitcher_cluster | ~5 | Batter cluster assignment + cluster quality (silhouette score). |

---

# 5. Key Patterns and Conventions

| Pattern | Description |
|---|---|
| Append-only raw tables | All raw ingestion tables are append-only with `load_id` and `ingestion_ts`. No in-place updates. |
| JSON-first raw storage | Full `raw_json VARIANT` payload stored alongside extracted convenience columns. Allows re-extraction if schema changes. |
| MD5 surrogate keys | Pitch-level tables use MD5 hash of natural key components as `pitch_sk`. Enables deduplication in incremental models. |
| Row-number deduplication | Staging models use `qualify row_number() over (...) = 1` to deduplicate to latest snapshot per entity. |
| Lateral flatten | Odds API staging uses 3-level lateral flatten (bookmakers → markets → outcomes). |
| Strict leakage guards | All rolling windows use `<` (not `<=`) on game_date. Prior-season-only for platoon splits and park factors. |
| `has_full_data` flag | Feature master table gate for unbiased training subset selection. |
| Incremental MERGE | 13 mart models use incremental strategy with `unique_key` MERGE to avoid full rebuilds on large pitch-level tables. |
| Model versioning | `daily_model_predictions` includes `model_version` (v0 through v4). `model_registry.yaml` tracks artifact paths, gates, and wave decisions. Sidebar filter on 4_Model_Performance.py reads versions dynamically — no code change needed on promotion. |

---

# 6. Gap Analysis — Architecture vs. Current State

This section identifies what is missing or incomplete relative to the architecture defined in `refined_architecture_proposal.md`.

## 6.1 Sub-Model Infrastructure (Epic 2) — ✅ Complete

| Gap | Status | Notes |
|---|---|---|
| Sub-model output table (`mart_sub_model_signals` + `feature_pregame_sub_model_signals`) | ✅ **Done** | Script-managed table `mart_sub_model_signals` in `baseball_data.betting` (see §1.9). dbt wide-pivot `feature_pregame_sub_model_signals` added. Story 2.1. |
| `sub_model_registry.yaml` | ✅ **Done** | `betting_ml/sub_model_registry.yaml` — full schema + 10 entries (run_env_v1/v2/v3/v4, offense_v1/v2, starter_v1, starter_ip_v1, bullpen_v1/v2, matchup_v1). Story 2.2. Last updated Epic 6D Story 6D.4 (2026-06-01). |
| Sub-model evaluation harness (`evaluate_sub_model.py`) | ✅ **Done** | `betting_ml/scripts/evaluate_sub_model.py` — walk-forward temporal CV, ablation comparison, promotion gate evaluation. Story 2.3. |
| `computed_at` timestamps on feature marts | ✅ **Done** | SCD-2 columns (valid_from, valid_to, is_current, computed_at, record_hash) added to feature_pregame_lineup_features (Story 2.6) and all new feature marts (Story 2.4). |

## 6.2 Run Environment Model (Epic 3)

| Gap | Status | Notes |
|---|---|---|
| Historical weather backfill (pre-ingestion-start) | ✅ **Done** | `observed_at_first_pitch` coverage from 2021-04-01 onward (12,469 games through 2026-05-28). Pre-Epic-T rows have NULL `weather_observation_type` (same date range, 12,073 rows). `forecast_pregame` forward-only from 2026-05-14; `forecast_intraday` from 2026-05-15. No pre-2021 data, consistent with overall training window. |
| Run environment signal mart | ✅ **Done** | `run_env_v4` champion (Ridge + NegBin, Epic 3D) writes `run_env_mu`, `run_env_dispersion`, `run_env_signal` to `mart_sub_model_signals`. Backfilled + daily via Dagster. Current through latest completed slate. |
| Opponent quality controls in training dataset | **Present** | Team and starter features exist; dataset join logic needs to be defined. |

## 6.3 Offensive Quality Model (Epic 4)

| Gap | Status | Notes |
|---|---|---|
| ZiPS/Steamer projection features in lineup model | **Partial** | `fg_zips_hitting_raw` exists and is staged, but ZiPS features are not currently in `feature_pregame_lineup_features`. |
| Lineup depth / entropy features | **Partial** | `lineup_depth_score` appears in `idea_notes.md` but is not confirmed in the current `feature_pregame_lineup_features` schema. |
| Lineup injury penalty | **Present** | Injury-adjusted wOBA (`injury_adj_avg_woba_30d`, `injury_adj_avg_xwoba_30d`, `injured_player_count`) live in `feature_pregame_lineup_features` via `slot_injury` CTE (Epic 15 Story 15.3). |
| EB batter posteriors in master feature table | ✅ **Done** | `avg_eb_woba`, `avg_eb_k_pct`, `avg_eb_bb_pct`, `avg_eb_iso`, `avg_eb_woba_uncertainty`, `eb_coverage_pct` (home + away) live in `feature_pregame_game_features`. Promoted via 7.M market-blind retrains (2026-06-01). |
| Offensive quality signal mart | ✅ **Done** | `offense_v2` champion (LightGBM + NegBin, Epic 4D) writes `pred_runs_mu`, `pred_runs_dispersion`, `pred_runs_raw`, `uncertainty` to `betting_features.offense_v2_signals` (§1.9). Backfilled + daily via Dagster. |

## 6.4 Starter Suppression Model (Epic 5)

| Gap | Status | Notes |
|---|---|---|
| CSW% rolling | **Present** | `mart_starter_csw_rolling` added in Phase 8. In `feature_pregame_starter_features`. |
| Arsenal drift score | **Present** | `mart_starter_pitch_mix_rolling` added in Phase 8. |
| EB starter posteriors in master feature table | ✅ **Done** | `eb_xwoba_against`, `eb_k_pct`, `eb_bb_pct`, `eb_xwoba_uncertainty` (home_starter + away_starter) live in `feature_pregame_game_features`. Promoted via 7.M market-blind retrains (2026-06-01). |
| Starter suppression signal mart | ✅ **Done** | `starter_v1` (NGBoost Normal xwOBA-against, Epic 5) → `betting_features.starter_suppression_signals`; `starter_ip_v1` (LightGBM + NegBin outs, Epic 5D) → `betting_features.starter_ip_signals` (§1.9). Both backfilled + daily via Dagster. |
| Projected xFIP from ZiPS | **Partial** | `fg_zips_pitching_raw` is staged but columns `home_starter_proj_xfip` / `away_starter_proj_xfip` are all-NaN in production (noted in model_registry.yaml). |

## 6.5 Bullpen State Model (Epic 6)

| Gap | Status | Notes |
|---|---|---|
| Leverage-weighted workload features | **Present** | `mart_bullpen_leverage` added in Phase 8. In `feature_pregame_bullpen_state_features`. |
| EB bullpen quality in master feature table | ✅ **Done** | `bp_eb_xwoba`, `bp_eb_uncertainty`, `bp_eb_coverage_pct` (home + away) live in `feature_pregame_game_features`. Promoted via 7.M market-blind retrains (2026-06-01). |
| Bullpen fatigue signal mart | ✅ **Done** | `bullpen_v1` (NGBoost xwOBA quality: availability_index, fatigue_signal, quality_mu/sigma/signal, high_leverage_availability_proxy, late_game_volatility_signal) and `bullpen_v2` (LightGBM + NegBin runs: bullpen_mu, dispersion, fatigue_adjusted_mu, uncertainty — Epic 6D) both write to `mart_sub_model_signals`. Backfilled + daily via Dagster (`--v2-only` in the daily op). |
| Version 2 target (conditional on game-state model) | ✅ **Done** | `bullpen_v2` NegBin distributional model (Epic 6D) supersedes the deferred supervised V2; Candidate B scales by `starter_ip_p20_outs`. |

## 6.6 Matchup Model (Epic 8)

| Gap | Status | Notes |
|---|---|---|
| Batter archetype clusters | **Present** | `statsapi.batter_clusters` and `mart_batter_archetype_vs_pitcher_cluster` exist. 6-cluster taxonomy. |
| Pitcher archetype clusters | **Present** | `statsapi.pitcher_clusters` and `mart_pitcher_pitch_archetype` exist. |
| Archetype definition documentation | ✅ **Done** | `quant_sports_intel_models/baseball/archetype_definitions.md` — 5 batter archetypes, 6 pitcher archetypes, per-season member counts, stability flags, matchup signals, Epic 7 requirements. Story 2.9. |
| Bat tracking matchup feature (bat speed vs. fastball velocity) | ✅ **Done** | `lineup_avg_bat_speed`, `lineup_bat_speed_std`, `lineup_avg_swing_length`, `lineup_avg_attack_angle`, `lineup_bat_speed_vs_starter_velo` live in `feature_pregame_lineup_features`. NULL pre-2023-07-14. Story 2.9. |
| Matchup signal mart | ✅ **Done** | `matchup_v1` champion (Ridge soft-mixture, Epic 8) writes `matchup_advantage_mu/sigma`, `matchup_volatility_signal`, `matchup_soft_vs_hard_delta`, `matchup_k_pressure_signal`, `matchup_power_signal` to `mart_sub_model_signals` (26,068 rows through 2026-05-31; 23,045 `signal_available`). Backfilled + daily via Dagster (Epic 8.6). Availability-gated — null for sparse-archetype / early-call-up games. |

## 6.7 CLV Meta-Model (Epic 12)

| Gap | Status | Notes |
|---|---|---|
| CLV-labeled game count | **41 games** | All from 2026-05-04 to 2026-05-06. Far below the 500-game exploratory threshold. |
| Meta-model data gate | **Gated** | Correctly not started. Monitoring in `mart_prediction_clv` and `mart_closing_line_value`. |
| `prediction_ts` stored per prediction | **Partial** | `score_date` exists; exact prediction timestamp per row is not confirmed. |

## 6.8 Temporal Data Platform (Epic 13 / Epic 15)

| Gap | Status | Notes |
|---|---|---|
| SCD Type-2 — market state / odds snapshots | ✅ **Done (15.1)** | `feature_pregame_market_features` SCD-2. `valid_from` = bookmaker_last_update. 136,457 rows. Dagster op wired. 2026-05-28. |
| SCD Type-2 — lineup state | ✅ **Done (15.2)** | `feature_pregame_lineup_state` (Python-managed DDL table). 1,544 rows, 10 scratches detected. `feature_pregame_lineup_features` re-pointed. Dagster op wired. 2026-05-28. |
| SCD Type-2 — injury status | ✅ **Done (15.3)** | `feature_pregame_injury_status` (dbt-managed). Coverage 2021-03-01+. 3 SCD-2 singular tests passing. `feature_pregame_lineup_features` slot_injury CTE re-pointed. 2026-05-28. |
| SCD Type-2 — projected starter | ✅ **Done (15.4)** | `feature_pregame_starter_status` (dbt-managed). `stg_statsapi_starter_snapshots` feeds all history. Pre-Epic-T sentinel `valid_from = 1970-01-01`. Intraday scratch tracking from 2026-05-12. 3 SCD-2 singular tests passing. `feature_pregame_starter_features` re-pointed. 2026-05-28. |
| SCD Type-2 — weather forecasts | ✅ **Done (15.5)** | `feature_pregame_weather_status` (dbt-managed). `stg_weather_raw_snapshots` feeds all history. Coverage: Epic T.2 (2026-05-01) onward; forecast_pregame only. 3 SCD-2 singular tests passing. `feature_pregame_weather_features` re-pointed. 2026-05-29. |
| SCD Type-2 — public betting | ✅ **Done (15.6)** | `feature_pregame_public_betting_status` (dbt-managed). `stg_actionnetwork_public_betting_snapshots` feeds all history. Coverage: 2026-05-07 (Epic T.3) onward. Dual gap documented. 3 SCD-2 singular tests passing. `feature_pregame_public_betting_features` is current-state view. 2026-05-29. |
| SCD Type-2 — umpire assignments | ✅ **Done (15.7)** | `feature_pregame_umpire_status`. 25,731 games (all single-row; no intraday substitution data yet). Coverage ~2026-05-02 (Epic T.4). 2026-05-29. |
| SCD Type-2 — park factors | ✅ **Done (15.8)** | `feature_pregame_park_status`. 362 rows (2015–2026), 36 venues, 30 active in 2026. Retired venues closed at season_close + 1 day. 2026-05-29. |
| Point-in-time feature joins (AS OF semantics) | ✅ **Done (15.9)** | Validated for all 8 SCD-2 marts. AS-OF queries confirmed exact feature match (6/6 fields, 3 games) vs stored `feature_snapshot`. See per-mart coverage table below. |
| `feature_ts` / `computed_at` on feature marts | **Complete** | `computed_at` on all 8 SCD-2 feature models (15.1–15.8). |
| Historical CLV reconstruction infrastructure | ✅ **Done (15.9)** | `prediction_snapshots` captures `feature_snapshot` (VARIANT) + `model_artifact_s3_uri` at prediction time. `validate_scd2_reconstruction.py` validates AS-OF + model inference. See per-mart coverage table below. |
| Temporal audit of existing tables for leakage risk | **Not done** | Leakage guards enforced in feature layer but no formal temporal audit of the mart layer exists. Epic 13.1. |

### Per-Mart SCD-2 Coverage (Epic 15 — Complete 2026-05-29)

AS-OF validation confirmed 2026-05-29 on game_pks 823384, 824280, 824360 (predicted_at 2026-05-15T14:06:05). All 6 spot-checked fields match `feature_snapshot` exactly. Run `scripts/validate_scd2_reconstruction.py` for full prediction reconstruction (±0.001).

| Story | SCD-2 Table | Coverage Start | Backfill Type | Pre-Cutoff Approximation |
|-------|-------------|---------------|---------------|--------------------------|
| 15.1 | `feature_pregame_market_features` | 2020-07-23 (Odds API) | `full` (append-only raw) | None — full history available via Odds API backfill |
| 15.2 | `feature_pregame_lineup_state` | 2026-05-12 (Epic T) | `forward-only` | Pre-T: permanently unrecoverable; feature model uses last-known lineup state |
| 15.3 | `feature_pregame_injury_status` | 2021-03-01 | `full` (append-only transactions) | None — full history from `player_transactions` |
| 15.4 | `feature_pregame_starter_status` | 2015 (final state) / 2026-05-12 (intraday) | `full` (with sentinel) | Pre-Epic-T rows use `valid_from = 1970-01-01` sentinel (final assignment only; no intraday history) |
| 15.5 | `feature_pregame_weather_status` | 2026-05-01 (Epic T.2) | `forward-only` | Pre-T: NULL for all weather columns; dome flag from venue static data |
| 15.6 | `feature_pregame_public_betting_status` | 2026-05-07 (Epic T.3) | `forward-only` | Pre-T: NULL for all betting % columns; two permanent gaps (ActionNetwork pre-2024-02-22, pre-Epic-T) |
| 15.7 | `feature_pregame_umpire_status` | 2026-05-02 (Epic T.4) | `forward-only` | Pre-T: use `stg_statsapi_umpire_game_log` (final deduped state; no intraday substitution history) |
| 15.8 | `feature_pregame_park_status` | 2015 | `full` | None — full annual history; retired venues closed at season_close + 1 day |

## 6.9 Market-Blind Retrains (Epic 7.M — ✅ Complete 2026-06-01)

| Model | Status | Version | CV Metric | Notes |
|---|---|---|---|---|
| home_win market-blind retrain | ✅ **Promoted** | v3 | Brier 0.1985 | XGBoost, 369 features, market_blind: true. max_depth=4, lr=0.0241, n_estimators=380. |
| run_differential market-blind retrain | ✅ **Promoted** | v3 | MAE 3.1041 | NGBoost Normal, 369 features, market_blind: true. n_estimators=500. |
| total_runs market-blind retrain | ✅ **Promoted** | v4 | MAE 3.4008 | NGBoost Normal (switched from LogNormal), 369 features, market_blind: true. |

---

# 7. Summary: What Exists vs. What the Architecture Needs

| Architecture Layer | Current State | Gap Size |
|---|---|---|
| Raw data ingestion | Comprehensive. Statcast, FanGraphs, Odds API (historical), Parlay API (live, 2026+), Stats API, Action Network, weather, umpires, OAA. | Minimal — historical weather confirmed 2021+. Parlay API cutover 2026-06-01. |
| Staging layer | Complete for all current sources including all 3 Parlay API staging models. | None — add new staging models as new sources are added. |
| Rolling stats / mart layer | Very strong. Team, player, pitcher, bullpen, matchup, archetype, odds all covered. | None — sub-model output tables now created (§1.9). |
| Feature layer (pre-game vectors) | Strong. 250+ columns. Leakage guards enforced. Sub-model signals flow into `feature_pregame_sub_model_signals`. | Medium — ZiPS features partially unused; signals not yet joined into `feature_pregame_game_features` (Layer 3 / Epic 9). |
| Market-blind model retrains | ✅ Complete (Epic 7.M, 2026-06-01). All three targets promoted: home_win v3 (Brier 0.1985), run_diff v3 (MAE 3.1041), total_runs v4 (MAE 3.4008). 493-day backfill run. | None. |
| Sub-model infrastructure | ✅ Complete (Epic 2). Output table, registry, eval harness, SCD-2 columns all shipped. | None — infrastructure ready for Epics 3–8. |
| Sub-model signals (run env, offense, starter, bullpen, matchup) | ✅ All six champions trained and generating signals: run_env_v4, offense_v2, starter_v1, starter_ip_v1, bullpen_v1+v2, matchup_v1 (Epics 3D/4D/5/5D/6D/8). Orchestrated daily via Dagster (Epic O.2/8.6). | None for signal generation — next is Layer-3 integration (Epic 9): join signals into the model feature matrix + stacking weights. |
| Archetype clustering | ✅ Exists in Snowflake. Documentation complete (`archetype_definitions.md`). Stability flags documented. | Epic 7 revalidation required before matchup_v1 training. |
| CLV meta-model | Correctly gated. 41 CLV games. | Large time horizon — not a data gap, a data-accumulation gap. |
| Temporal/SCD infrastructure | ✅ **Complete** — Epic 15 all 9 stories done (8 SCD-2 marts + 15.9 CLV reconstruction validation). AS-OF queries validated. Per-mart coverage table in §6.8. | Epic 16 (Sequential Prior Update) next. |
