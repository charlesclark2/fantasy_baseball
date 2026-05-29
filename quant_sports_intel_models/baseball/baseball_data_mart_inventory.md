# Baseball Data Mart Inventory
## Current State Reference — As of 2026-05-28

This document inventories every Snowflake table created via DDL scripts and every dbt model in the project. It is intended as a reference for understanding the current data modeling state and identifying gaps relative to the architecture described in `quant_sports_intel_models/baseball/refined_architecture_proposal.md`.

---

# Quick Reference

| Layer | Count | Location |
|---|---|---|
| Raw source tables (DDL) | 18 tables + 2 tasks + 4 procedures | `scripts/ddl/` |
| dbt sources | 35+ raw tables across 9 schemas | `dbt/models/sources.yml` |
| dbt staging models | 22 models | `dbt/models/staging/` |
| dbt mart models | 57 models | `dbt/models/mart/` |
| dbt feature models | 15 models (~400+ columns) | `dbt/models/feature/` |

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

## 1.10 Snowflake Tasks & Procedures

| Object | Type | Schedule | Purpose |
|---|---|---|---|
| `task_lineup_monitor` | Task + Procedure | Hourly (0 * * * * ET) | Polls for confirmed lineups; triggers dbt_staging_build.yml via GitHub Actions. |
| `proc_savant_ingestion` | Procedure | On-demand | Fetches prior-day Statcast CSV incrementally from Baseball Savant. |

---

# 2. dbt Staging Models

All staging models output to `baseball_data.betting`. Default materialization: `table` unless noted.

## 2.1 Odds API Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_oddsapi_events` | one row per event_id (latest snapshot) | Deduplicates to latest snapshot per event. Excludes null raw_json. | table |
| `stg_oddsapi_odds` | (ingestion_ts, event_id, bookmaker, market, outcome) | 3-level lateral flatten: bookmakers → markets → outcomes. Deduplicates us/us2 regions within load_id. | table |
| `stg_oddsapi_market_consensus` | one row per (event_id, market_key) | Aggregates American/decimal odds across all bookmakers. Vig-free aggregation via additive method. | table |

## 2.2 Action Network Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_actionnetwork_public_betting` | (game_date, an_game_id) | Cleans betting percentages for moneyline and totals markets. | table |

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
| `stg_statsapi_umpire_game_log` | (game_pk, umpire_name) | Cleans umpire assignment + tendency metrics. Computes trailing z-scores. | table |

## 2.4 Savant / Statcast Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_batter_pitches` | one row per pitch | Renames to snake_case. MD5 surrogate key on (game_pk, at_bat_number, pitch_number, batter_id, pitcher_id, inning, inning_half). Suppresses deprecated PitchF/X fields. | table |
| `stg_weather_raw` | (game_pk, venue_id) | Cleans and validates weather observations. | view |

## 2.5 FanGraphs Staging

| Model | Grain | Key Transformation | Materialization |
|---|---|---|---|
| `stg_fangraphs__stuff_plus` | (fg_pitcher_id, season) — latest ingestion | Deduplicates to latest. Unpacks pitch-mix percentages (FA, SI, FC, SL, CU, CH, FS). | table |
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
| `feature_pregame_lineup_features` | (game_pk, side) | mart_batter_rolling_stats, mart_batter_vs_handedness_splits, mart_batter_profile_summary, stg_fangraphs__zips_hitting, mart_batter_bat_tracking_profile, **feature_pregame_injury_status** (SCD-2) | ~55 | Aggregates 30-day rolling and season-to-date batter stats across all 9 lineup slots. LHB/RHB counts. Handedness-specific wOBA (vs LHP/RHP). ZiPS hitting projections per slot with Bayesian rookie shrinkage (k=200 PA, Story 2.6). Bat-tracking columns (lineup_avg_bat_speed, lineup_bat_speed_std, lineup_avg_swing_length, lineup_avg_attack_angle, lineup_bat_speed_vs_starter_velo) — NULL pre-2023-07-14 (Story 2.9). SCD-2 columns present (valid_from, valid_to, is_current, computed_at, record_hash). `slot_injury` CTE reads from `feature_pregame_injury_status` with point-in-time `valid_from`/`valid_to` filter (Epic 15 Story 15.3). |
| `feature_pregame_starter_features` | (game_pk, side) | mart_starter_rolling_stats, mart_pitcher_vs_handedness_splits, mart_starter_csw_rolling, mart_starter_pitch_mix_rolling, **feature_pregame_starter_status** (SCD-2) | ~30 | 30-day rolling starter stats + career platoon splits. CSW% last 3 starts. Pitch-mix drift score. NULL when pitcher has <30 IP career history. `probable_pitchers` CTE reads from `feature_pregame_starter_status WHERE is_current = true` (Epic 15 Story 15.4); previously read from `stg_statsapi_probable_pitchers`. |
| `feature_pregame_bullpen_state_features` | (game_pk, side) | mart_bullpen_effectiveness, mart_bullpen_workload, mart_bullpen_leverage | ~25 | Bullpen effectiveness, leverage workload, handedness mix. High-leverage IP prior 1/3 days. Closer availability proxy. |
| `feature_pregame_team_features` | (game_pk, side) | mart_team_rolling_offense, mart_team_rolling_pitching, mart_team_schedule_context, mart_team_pythagorean_rolling, mart_team_base_state_splits | ~20 | 30-day rolling team offensive/pitching metrics. Schedule context (days rest, home/away, back-to-back). Pythagorean residual. Base-state efficiency. |
| `feature_pregame_odds_features` | game_pk | mart_odds_outcomes, mart_odds_line_movement, mart_bookmaker_disagreement, stg_actionnetwork_public_betting | ~15 | Market-implied probabilities, bookmaker disagreement spread (7 features), public betting percentages. Market columns — subject to exclusion in market-blind retrains. |
| `feature_pregame_park_features` | game_pk | mart_park_run_factors | ~5 | Prior-season park run factors. NULL for season-opening games (no prior-season data). |
| `feature_pregame_weather_features` | game_pk | statsapi.weather_raw | ~5 | Wind speed, wind direction, temperature, humidity. NULL for dome stadiums. |
| `feature_pregame_umpire_features` | game_pk | stg_statsapi_umpire_game_log | ~8 | HP umpire assignment + trailing z-scores of tendency metrics (called strikes above avg, run expectancy delta, run impact, accuracy). |
| `feature_pregame_game_features` | game_pk (master) | All feature_pregame_* tables, mart_game_results, mart_catcher_framing | ~260+ | Master pre-game feature table. Joins all 9 component feature tables including feature_pregame_sub_model_signals. `has_full_data` flag selects games with complete lineups, starters with 30+ IP history, and prior-season park factors. Consumed by predict_today.py and training scripts. Home/away bat-tracking std columns added Story 2.9. |
| `feature_pregame_sub_model_signals` | (game_pk, side) | mart_sub_model_signals (betting_ml DDL table) | dynamic | Wide-format pivot over mart_sub_model_signals. Each registered (signal_name, sub_model_version) pair becomes a column. Currently wired for run_env_v1 signals (run_env_signal_v1, environment_volatility_v1). Add column blocks as Epics 3–8 ship. SCD-2 filtered to is_current = true. **Added Epic 2, Story 2.1.** |
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
| Model versioning | `daily_model_predictions` includes `model_version` (v0/v1/v2). `model_registry.yaml` tracks artifact paths, gates, and wave decisions. |

---

# 6. Gap Analysis — Architecture vs. Current State

This section identifies what is missing or incomplete relative to the architecture defined in `refined_architecture_proposal.md`.

## 6.1 Sub-Model Infrastructure (Epic 2) — ✅ Complete

| Gap | Status | Notes |
|---|---|---|
| Sub-model output table (`mart_sub_model_signals` + `feature_pregame_sub_model_signals`) | ✅ **Done** | DDL table `mart_sub_model_signals` in `baseball_data.betting_ml`. dbt wide-pivot view `feature_pregame_sub_model_signals` added. Story 2.1. |
| `sub_model_registry.yaml` | ✅ **Done** | `betting_ml/sub_model_registry.yaml` — full schema + 5 entries (run_env_v1, offense_v1, starter_v1, bullpen_v1, matchup_v1). Story 2.2. |
| Sub-model evaluation harness (`evaluate_sub_model.py`) | ✅ **Done** | `betting_ml/scripts/evaluate_sub_model.py` — walk-forward temporal CV, ablation comparison, promotion gate evaluation. Story 2.3. |
| `computed_at` timestamps on feature marts | ✅ **Done** | SCD-2 columns (valid_from, valid_to, is_current, computed_at, record_hash) added to feature_pregame_lineup_features (Story 2.6) and all new feature marts (Story 2.4). |

## 6.2 Run Environment Model (Epic 3)

| Gap | Status | Notes |
|---|---|---|
| Historical weather backfill (pre-ingestion-start) | **Unknown** | Weather coverage before the ingestion script was added is not documented. |
| Run environment signal mart | **Missing** | `run_environment_signal`, `weather_run_modifier`, `umpire_run_modifier`, `environment_volatility_signal` not yet generated. |
| Opponent quality controls in training dataset | **Present** | Team and starter features exist; dataset join logic needs to be defined. |

## 6.3 Offensive Quality Model (Epic 4)

| Gap | Status | Notes |
|---|---|---|
| ZiPS/Steamer projection features in lineup model | **Partial** | `fg_zips_hitting_raw` exists and is staged, but ZiPS features are not currently in `feature_pregame_lineup_features`. |
| Lineup depth / entropy features | **Partial** | `lineup_depth_score` appears in `idea_notes.md` but is not confirmed in the current `feature_pregame_lineup_features` schema. |
| Lineup injury penalty | **Partial** | `stg_statsapi_player_injury_status` exists; injury-adjusted feature use in lineup model is not confirmed. |
| Offensive quality signal mart | **Missing** | `lineup_run_creation_signal`, `top_3_lineup_strength`, `lineup_uncertainty_score` not materialized as sub-model outputs. |

## 6.4 Starter Suppression Model (Epic 5)

| Gap | Status | Notes |
|---|---|---|
| CSW% rolling | **Present** | `mart_starter_csw_rolling` added in Phase 8. In `feature_pregame_starter_features`. |
| Arsenal drift score | **Present** | `mart_starter_pitch_mix_rolling` added in Phase 8. |
| Starter suppression signal mart | **Missing** | `starter_run_suppression_signal`, `starter_expected_ip_signal` not materialized as sub-model outputs. |
| Projected xFIP from ZiPS | **Partial** | `fg_zips_pitching_raw` is staged but columns `home_starter_proj_xfip` / `away_starter_proj_xfip` are all-NaN in production (noted in model_registry.yaml). |

## 6.5 Bullpen State Model (Epic 6)

| Gap | Status | Notes |
|---|---|---|
| Leverage-weighted workload features | **Present** | `mart_bullpen_leverage` added in Phase 8. In `feature_pregame_bullpen_state_features`. |
| Bullpen fatigue signal mart | **Missing** | `bullpen_fatigue_signal`, `high_leverage_availability_proxy` not materialized as sub-model outputs. |
| Version 2 target (conditional on game-state model) | **Future** | No game-state leverage-context model exists yet. V2 is correctly deferred. |

## 6.6 Matchup Model (Epic 8)

| Gap | Status | Notes |
|---|---|---|
| Batter archetype clusters | **Present** | `statsapi.batter_clusters` and `mart_batter_archetype_vs_pitcher_cluster` exist. 6-cluster taxonomy. |
| Pitcher archetype clusters | **Present** | `statsapi.pitcher_clusters` and `mart_pitcher_pitch_archetype` exist. |
| Archetype definition documentation | ✅ **Done** | `quant_sports_intel_models/baseball/archetype_definitions.md` — 5 batter archetypes, 6 pitcher archetypes, per-season member counts, stability flags, matchup signals, Epic 7 requirements. Story 2.9. |
| Bat tracking matchup feature (bat speed vs. fastball velocity) | ✅ **Done** | `lineup_avg_bat_speed`, `lineup_bat_speed_std`, `lineup_avg_swing_length`, `lineup_avg_attack_angle`, `lineup_bat_speed_vs_starter_velo` live in `feature_pregame_lineup_features`. NULL pre-2023-07-14. Story 2.9. |
| Matchup signal mart | **Missing** | `matchup_advantage_signal`, `matchup_volatility_signal` not materialized as sub-model outputs. |

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
| SCD Type-2 — weather forecasts | **Missing** | `feature_pregame_weather_features`. Epic 15 Story 15.5. |
| SCD Type-2 — public betting | **Missing** | `feature_pregame_public_betting_features`. Epic 15 Story 15.6. |
| SCD Type-2 — umpire assignments | **Missing** | `feature_pregame_umpire_features`. Epic 15 Story 15.7. |
| SCD Type-2 — park factors | **Missing** | `feature_pregame_park_features`. Epic 15 Story 15.8. |
| Point-in-time feature joins (AS OF semantics) | **Partial** | Implemented for: odds (15.1), lineup (15.2), injury (15.3), starter (15.4). Remaining: weather, public betting, umpire, park. |
| `feature_ts` / `computed_at` on feature marts | **Partial** | `computed_at` on all SCD-2 feature models (15.1–15.4). Legacy mart models still lack it. |
| Historical CLV reconstruction infrastructure | **Missing** | No `feature_snapshot_id`, `prediction_ts`, `lineup_state_version` tracking at prediction time. Epic 15.9. |
| Temporal audit of existing tables for leakage risk | **Not done** | Leakage guards enforced in feature layer but no formal temporal audit of the mart layer exists. Epic 13.1. |

## 6.9 Market-Blind Retrains (Epic 1 — Immediate)

| Gap | Status | Notes |
|---|---|---|
| home_win market-blind retrain | **Ready to run** | `_MARKET_COLS_TO_EXCLUDE` populated in `train_elasticnet_prod.py`. Target date ~2026-05-22. |
| total_runs market-blind retrain | **Needs script update** | NGBoost training script needs market exclusion list added. 4 noise features to drop. |
| run_diff market-blind retrain | **Needs script update + feature set upgrade** | Must switch from `feature_columns.json` (294 features) to `load_features()` full set. Most urgent. |

---

# 7. Summary: What Exists vs. What the Architecture Needs

| Architecture Layer | Current State | Gap Size |
|---|---|---|
| Raw data ingestion | Comprehensive. Statcast, FanGraphs, Odds API (historical), Parlay API (live, 2026+), Stats API, Action Network, weather, umpires, OAA. | Small — historical weather backfill unknown. Parlay API cutover 2026-06-01. |
| Staging layer | Complete for all current sources including all 3 Parlay API staging models. | None — add new staging models as new sources are added. |
| Rolling stats / mart layer | Very strong. Team, player, pitcher, bullpen, matchup, archetype, odds all covered. | Small — sub-model output marts not yet created. |
| Feature layer (pre-game vectors) | Strong. 250+ columns. Leakage guards enforced. | Medium — ZiPS features partially unused; sub-model signals not yet flowing. |
| Market-blind model retrains | Ready but not yet run. | Small — scripts need updates; target date ~2026-05-22. |
| Sub-model infrastructure | ✅ Complete (Epic 2). Output table, registry, eval harness, SCD-2 columns all shipped. | None — infrastructure ready for Epics 3–8. |
| Sub-model signals (run env, offense, starter, bullpen, matchup) | Raw inputs all exist. Signal computation not done. | Medium per sub-model — no trained models yet, no output marts. Epic 3 is next. |
| Archetype clustering | ✅ Exists in Snowflake. Documentation complete (`archetype_definitions.md`). Stability flags documented. | Epic 7 revalidation required before matchup_v1 training. |
| CLV meta-model | Correctly gated. 41 CLV games. | Large time horizon — not a data gap, a data-accumulation gap. |
| Temporal/SCD infrastructure | **Partial** — 4 of 8 Epic 15 marts complete (odds, lineup, injury, starter). Weather, public betting, umpire, park remain. | Stories 15.5–15.8 next; CLV reconstruction (15.9) after all 8 marts done. |
