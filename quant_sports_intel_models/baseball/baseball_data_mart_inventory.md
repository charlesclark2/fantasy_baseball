# Baseball Data Mart Inventory
## Current State Reference — As of 2026-06-17 (Epic 33 expected-lineup + playing-time marts; A2.11 EB-posterior dbt migration; player-identity serving mart)

> **Update 2026-06-17 (dbt model inventory freshness pass):** Documented **8 dbt models** that existed in `dbt/models/` but were missing from this inventory. (1) **New `dbt/models/eb_posteriors/` directory (5 models, Story A2.11)** — the dbt migration of the Python EB-posterior scripts (`compute_lineup/starter/bullpen_posteriors.py`): `eb_batter_posteriors_raw`, `eb_starter_posteriors`, `eb_bullpen_posteriors`, `eb_bullpen_team_posteriors`, and support model `int_bullpen_ali_by_season` — all output to `baseball_data.betting`, incremental MERGE/delete+insert. See new §3.12. (2) **Epic 33 pregame-projection marts:** `mart_player_game_starts` (Story 33.1 Task 1a — leakage-safe confirmed-starter FACT) and `feature_pregame_expected_lineup` (Story 33.3 — Σ P(start)·stat / Σ P(start) pre-lineup offense aggregates). See §3.13 + §4. (3) **`mart_player_profile_identity`** — single source of truth for the player-profile serving path (`write_serving_store.py`). See §3.13. Also flagged: `mart_pitcher_cluster_matchups` (§3.7) is documented but **not currently built** in `dbt/models/`. Counts in Quick Reference corrected (mart 55→60, feature 20→24, + eb_posteriors 5). **NOTE: §6 Gap Analysis is NOT refreshed in this pass — its CLV game count (§6.7, "41 games") is stale; live CLV labels are now ~345 h2h / ~288 totals.**

> **Update 2026-06-13 (Story 27.7 — season-normalized contact-quality features):** The master `feature_pregame_game_features` is now a **thin wrapper**: the heavy as-of assembly moved verbatim to a new `feature_pregame_game_features_raw`, and the public model adds a `<col>_seasonnorm` column for each of the 34 contact-quality features (xwOBA / hard-hit / barrel families). The normalization z-scores each contact feature against a new **`feature_league_contact_baseline`** — a strictly-prior, AS-OF current-season league baseline (no same-day/future games), shrunk toward the prior season early. This fixes the totals contact→runs **conversion-regime over-bias** (2025 contact got harder but runs stayed flat; see [[project_totals_model_directional_bias]] / Story 27.6). The 34-name list is shared between the dbt macro `as_of_contact_baseline()` and `betting_ml/utils/season_normalization.py` (drift-guarded). DDL compiles clean; **Snowflake build + totals retrain (`--season-normalize`) pending.** See Stories 27.7 / 27.8 in `implementation_guide.md`.

> **Update 2026-06-10 (Epic A1.11 — forward-looking feature store):** New `mart_game_spine` keystone (§3.1) UNIONs completed `mart_game_results` with today's not-yet-played `stg_statsapi_games`, so the feature store can hold **today's scheduled games** instead of falling back to the intraday assembly. Feature marts that previously spined on `mart_game_results` (`feature_pregame_game_features`, `feature_pregame_team_features`, `feature_pregame_park_features`, `feature_pregame_bullpen_state_features`, `feature_pregame_odds_features`) now spine on `mart_game_spine` and carry an `is_scheduled` flag. The point-in-time joins for those marts switched to an **exact-or-as-of fallback** (§5): completed games keep their byte-for-byte exact `game_pk`/`record_date` row; scheduled games carry forward the team's latest strictly-prior belief. This fixed the all-NULL scheduled-game blocks for sequential posteriors (`feature_pregame_game_features.team_seq`) and standings + season Pythagorean (`feature_pregame_team_features.season_record`). Dev-verified 2026-06-10 (6/6 coverage blocks 15/15 on the 2026-06-09 slate); prod promote pending. See Epic A1.11 / A1.13 in `implementation_guide.md`.

> **Update 2026-06-02:** All six sub-model signal generators now ship champions and write signals (run_env_v4, offense_v2, starter_v1, starter_ip_v1, bullpen_v1+v2, matchup_v1) — the §6 "signal mart Missing" gaps are closed. The signal generators are wired into the Dagster `daily_ingestion_job` (Epic O.2/8.6), scoring the recently-completed game window daily. `mart_sub_model_signals` lives in `baseball_data.betting` (not `betting_ml` — corrected below).

This document inventories every Snowflake table created via DDL scripts and every dbt model in the project. It is intended as a reference for understanding the current data modeling state and identifying gaps relative to the architecture described in `quant_sports_intel_models/baseball/refined_architecture_proposal.md`.

---

# Quick Reference

| Layer | Count | Location |
|---|---|---|
| Raw source tables (DDL) | 18 tables + 2 tasks + 4 procedures | `scripts/ddl/` |
| dbt sources | 35+ raw tables across 9 schemas | `dbt/models/sources.yml` |
| dbt staging models | 27 models | `dbt/models/staging/` |
| dbt mart models | 60 models | `dbt/models/mart/` |
| dbt feature models | 24 models (~400+ columns) | `dbt/models/feature/` |
| dbt EB-posterior models | 5 models | `dbt/models/eb_posteriors/` (Story A2.11) |
| dbt FanGraphs mart models | 4 models | `dbt/models/marts/fangraphs/` (§3.10) |

**Total dbt models on disk: 120** (27 staging + 60 mart + 24 feature + 5 eb_posteriors + 4 marts/fangraphs).

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
| `mart_game_results` | one row per game_pk | incremental (game_date) | Game scores, teams, home/away outcomes. Source of truth for training labels. Pitch-derived ⇒ only ever holds **completed** games. |
| `dim_team_name_lookup` | one row per team-name variant (lowercased) | view | **Canonical team-name resolver (Epic A1.9).** Maps ANY feed name variant → team_id + canonical abbrev/name, from `ref_teams` + the `ref_team_aliases` seed. Replaces per-site inline CASE / `_normalize_team_name` band-aids that silently dropped odds for relocated franchises (the Athletics name drift). Consumer contract: normalize input as `lower(regexp_replace(trim(name), '^G[12] ', ''))` before joining. |
| `mart_game_spine` | one row per game_pk | view | **Forward-looking game spine (Epic A1.11).** UNION of completed `mart_game_results` (pass-through, byte-for-byte) + today's scheduled `stg_statsapi_games` not yet in results (`is_scheduled = true`, NULL scores). Scheduled-game team abbrevs resolved via `dim_team_name_lookup` (A1.9). Feature marts spine on this (not `mart_game_results`) so the feature store can serve today's not-yet-played games; a game moves from the scheduled branch to the completed branch automatically once its pitches land. |
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
| `mart_pitcher_cluster_matchups` | (pitcher_cluster_id, batter_cluster_id, season) | table | Aggregate matchup stats by cluster pair. Used when individual h2h sample is insufficient. **⚠️ 2026-06-17: NOT currently built — no model file in `dbt/models/` and not a declared source. The matchup features instead source `mart_batter_archetype_vs_pitcher_cluster` (above). Either build or remove this entry.** |

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

## 3.11 CLV, Pipeline & Epic-27 Marts (inventory catch-up 2026-06-13)

These models existed in `dbt/models/` but were missing from this inventory; added during the Story 27.7 freshness pass.

| Model | Schema | Grain | Description |
|---|---|---|---|
| `mart_clv_labeled_games` | betting | (game_pk, market_type ∈ {h2h, totals}) | Canonical source of CLV-labeled games for the Epic 12 meta-model. Only materializes rows meeting all four label conditions (live pre-game prediction + opening price + closing price + game result). "50 CLV-labeled games" = 50 distinct game_pk here. Upstream: mart_closing_line_value, mart_game_results. |
| `mart_clv_label_count` | betting | one row | Gate-threshold tracker (view) over `mart_clv_labeled_games`: live_total_count + pct_clv_positive vs the Epic 12 story thresholds (≥10/50/100/200/500/1000). |
| `mart_pipeline_status` | betting | latest run | Thin view over `baseball_data.betting_ml.pipeline_status` for the Streamlit app; adds an `is_fresh` flag (predict_today completed successfully within the last 6h). Epic A1.3. |
| `mart_pitcher_batted_ball_profile` | betting | (pitcher_id, game_year) | Starter batted-ball profile (GB%/FB%/LD%/Popup%) from Statcast (`stg_batter_pitches`), for the gb×eb_so_factor / fb×eb_hr_factor interaction terms (Epic 27.5). Coverage 2015+; min 50 batters faced; consumers join game_year−1 (leakage guard). |
| `mart_reliever_top3_availability` | betting | (pitching_team, game_pk) | Pre-game availability of each team's three highest-leverage relievers (ranked by rolling 30-day leverage workload over strictly-prior appearances). Upstream: mart_pitch_play_event, mart_starting_pitcher_game_log, stg_batter_pitches. |
| `mart_team_defense_quality_rolling` | betting | (game_pk, side) | Team defensive-quality composite (fielding-team perspective): prior-season OAA + EB-smoothed prior-season sprint speed → per-season z-scored `defense_quality_mu` (Story 27.4, leakage-safe). Upstream: mart_game_spine, stg_batter_sprint_speed. |

## 3.12 Empirical-Bayes Posterior Models (`dbt/models/eb_posteriors/`)

**Added 2026-06-17 (Story A2.11 — dbt migration of the Python EB-posterior scripts).** These replace the daily `betting_ml/scripts/eb_priors/compute_*_posteriors.py` warehouse path with closed-form conjugate shrinkage expressed directly in dbt — removing train/serve skew between the Python and SQL surfaces and cutting daily compute. All output to `baseball_data.betting` (no custom schema → `target.schema`, matching the Python tables they replace). All incremental.

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `eb_batter_posteriors_raw` | (game_pk, batting_slot, batter_id) — confirmed lineups | incremental MERGE | Beta-Binomial EB for wOBA/K%/BB% + Normal-Normal for ISO, ZiPS-blended at low PA (w=min(PA/150,1)), plus the Epic-16.2 as-of sequential wOBA column. `eb_data_source ∈ {prior_only, zips_blend, full_eb}`. Sourced from CONFIRMED lineups (`stg_statsapi_lineups`, ~3h pre-game) → no future-game spine benefit; pure cost + skew cleanup. |
| `eb_starter_posteriors` | (game_pk, pitcher_id) — probable starters | incremental MERGE | Normal-Normal conjugate shrinkage of season-to-date xwOBA-against / K% / BB% toward experience-band priors. **⭐ 30.6 residual fix:** sourced from `stg_statsapi_probable_pitchers` → ranges over the FULL schedule spine incl. +1/+2-day games (the Python was scoped to today's slate, leaving future games' starter-EB NULL at serve). Validated byte-for-byte vs the Python table on closed 2025 before cutover. |
| `eb_bullpen_posteriors` | (game_pk, pitcher_id) — relievers who appeared | incremental MERGE | Normal-Normal EB shrinkage of season-to-date reliever xwOBA-against / K% / BB% toward (leverage_role × age_band) priors. `leverage_role` from prior-season aLI; `role_changed` from full current-season aLI. Retrospective reliever set (who actually pitched, from `stg_batter_pitches`) → no future spine. Leakage guard: season-to-date sums only strictly-prior games. |
| `eb_bullpen_team_posteriors` | (game_pk, team) | incremental MERGE | Outs-in-game-weighted aggregate of the per-reliever EB xwOBA / uncertainty (replaces `compute_bullpen_posteriors._aggregate_to_team`). Equal weighting when a team's total outs = 0 (mirrors the Python fallback). Reads `eb_bullpen_posteriors`. |
| `int_bullpen_ali_by_season` | (season, pitcher_id) — relievers ≥20 appearances | incremental (delete+insert by season) | Support model: normalized average Leverage Index (aLI) per reliever-season = (pitcher's mean per-AB \|Δ home win-exp\|) / (season mean across all relievers). Joined TWICE by `eb_bullpen_posteriors` (season-1 → leverage_role; full season → role_changed). Incremental recomputes current + prior season only. |

## 3.13 Playing-Time & Player-Identity Marts (Epic 33 / serving)

**Added 2026-06-17.** Output to `baseball_data.betting`.

| Model | Grain | Materialization | Description |
|---|---|---|---|
| `mart_player_game_starts` | (game_pk, team, side, player_id) — a CONFIRMED STARTER | table | **Story 33.1 Task 1a.** Leakage-safe START FACT: `mart_game_spine` (unpivoted home/away) ⋈ `stg_statsapi_lineups` (one row = one posted starter). Intentionally actual-starts-only (no `did_start=0` rows — the candidate panel + label + rolling start-rates are built downstream in `build_playing_time_dataset.py`). Keyed on leakage-safe `official_date`. Scheduled games produce no rows (no posted lineup yet — correct: serving predicts today's starters from recent starts). Coverage 2015+. Feeds the playing-time P(start) model + 33.3. **Sibling `mart_player_start_probability` (the P(start) output, Story 33.1 Task 3a) is Python-written, not a dbt model.** |
| `mart_player_profile_identity` | (player_id, player_type ∈ {batter, pitcher}) — active-2026 players | table | Single source of truth for the player-profile serving path (`write_serving_store.py` → `api_cache` player/{id} blobs). full_name/position/team (profiles primary, lineups fallback), bats, birth_date + derived age, height/weight (NULL for lineup-only players), `is_on_il` + `il_since` from `feature_pregame_injury_status`. Spans players in `mart_batter_rolling_stats` OR `mart_starting_pitcher_game_log`. |

---

# 4. dbt Feature Models

All feature models output to `baseball_data.betting_features`. All materialize as `table`. Grain is `game_pk` for the master table and `game_pk × side` for per-team detail tables.

**Leakage guards enforced across all models:**
- Rolling window joins use `game_date < official_date` (strictly less than — excludes game-day data)
- Platoon splits: prior season only (`season - 1`)
- Park run factors: prior season only
- Season record: completed games use `record_date = official_date - 1` (day before game); scheduled games (A1.11) carry forward the latest **strictly-prior** `record_date` (exact-or-as-of, §5) — still leakage-safe (no same-day or future rows).

| Model | Grain | Upstream | ~Columns | Description |
|---|---|---|---|---|
| `feature_pregame_injury_status` | (player_id, valid_from) | stg_statsapi_player_injury_status | ~8 | SCD-2 table tracking IL status per player. `valid_from`/`valid_to` are midnight TIMESTAMP_NTZ casts of status dates. `is_current = true` = currently on IL. Zero-length intervals (same-day place+activate noise) filtered at this layer. Consumed by `feature_pregame_lineup_features` slot_injury CTE for injury-adjusted wOBA. **Added Epic 15 Story 15.3.** Coverage: 2021-03-01 onward. |
| `feature_pregame_starter_status` | (game_pk, side, valid_from) | stg_statsapi_starter_snapshots | ~8 | SCD-2 table tracking probable starter changes per game/side. `valid_from` = ingestion_ts when pitcher identity changed (detected via LAG). `is_current = true` = most recent assignment. Sentinel `valid_from = 1970-01-01` for pre-Epic-T games (no intraday change history available). Consumed by `feature_pregame_starter_features` `probable_pitchers` CTE. **Added Epic 15 Story 15.4.** Coverage: Full history (static) pre-Epic-T; intraday scratch tracking from 2026-05-12 onward. |
| `feature_pregame_weather_status` | (game_pk, valid_from) | stg_weather_raw_snapshots | ~10 | SCD-2 table tracking forecast_pregame weather state per game. New row only when hash(temp_f, wind_component_mph, humidity_pct, condition_text) changes between fetches. `is_current = true` = most recent forecast. wind_component_mph pre-computed from ref_venues. Consumed by `feature_pregame_weather_features` via `is_current = true` filter. 3 SCD-2 singular tests. **Added Epic 15 Story 15.5.** Coverage: Epic T.2 (2026-05-01) onward. |
| `feature_pregame_public_betting_status` | (game_pk, valid_from) | stg_actionnetwork_public_betting_snapshots | ~13 | SCD-2 table tracking Action Network public betting % per game. New row only when hash(home_ml_money_pct, home_ml_ticket_pct, over_money_pct, over_ticket_pct) changes. Single denormalized row per game (ML + totals co-located). Dual coverage gap: (1) Action Network pre-2024-02-22 unrecoverable; (2) pre-Epic-T snapshots not captured. 3 SCD-2 singular tests. **Added Epic 15 Story 15.6.** Coverage: 2026-05-07 (Epic T.3) onward. |
| `feature_pregame_public_betting_features` | game_pk | feature_pregame_public_betting_status (SCD-2) | ~12 | Current-state view over feature_pregame_public_betting_status (is_current = true). Grain: one row per game_pk. Replaces direct stg_actionnetwork_public_betting join in downstream models. **Added Epic 15 Story 15.6.** |
| `feature_pregame_lineup_features` | (game_pk, side) | mart_batter_rolling_stats, mart_batter_vs_handedness_splits, mart_batter_profile_summary, stg_fangraphs__zips_hitting, mart_batter_bat_tracking_profile, **feature_pregame_injury_status** (SCD-2) | ~55 | Aggregates 30-day rolling and season-to-date batter stats across all 9 lineup slots. LHB/RHB counts. Handedness-specific wOBA (vs LHP/RHP). ZiPS hitting projections per slot with Bayesian rookie shrinkage (k=200 PA, Story 2.6). Bat-tracking columns (lineup_avg_bat_speed, lineup_bat_speed_std, lineup_avg_swing_length, lineup_avg_attack_angle, lineup_bat_speed_vs_starter_velo) — NULL pre-2023-07-14 (Story 2.9). SCD-2 columns present (valid_from, valid_to, is_current, computed_at, record_hash). `slot_injury` CTE reads from `feature_pregame_injury_status` with point-in-time `valid_from`/`valid_to` filter (Epic 15 Story 15.3). |
| `feature_pregame_starter_features` | (game_pk, side) | mart_starter_rolling_stats, mart_pitcher_vs_handedness_splits, mart_starter_csw_rolling, mart_starter_pitch_mix_rolling, **feature_pregame_starter_status** (SCD-2) | ~30 | 30-day rolling starter stats + career platoon splits. CSW% last 3 starts. Pitch-mix drift score. NULL when pitcher has <30 IP career history. `probable_pitchers` CTE reads from `feature_pregame_starter_status WHERE is_current = true` (Epic 15 Story 15.4); previously read from `stg_statsapi_probable_pitchers`. |
| `feature_pregame_bullpen_state_features` | (game_pk, side) | **mart_game_spine**, mart_bullpen_effectiveness, mart_bullpen_workload, mart_bullpen_leverage | ~25 | Bullpen effectiveness, leverage workload, handedness mix. High-leverage IP prior 1/3 days. Closer availability proxy. **A1.11:** spines on `mart_game_spine`; bullpen-state blocks use exact-or-as-of so today's scheduled games carry forward the latest prior bullpen state. |
| `feature_pregame_team_features` | (game_pk, side) | **mart_game_spine**, mart_team_rolling_offense, mart_team_rolling_pitching, mart_team_schedule_context, mart_team_pythagorean_rolling, mart_team_base_state_splits, mart_team_season_record | ~20 | 30-day rolling team offensive/pitching metrics. Schedule context (days rest, home/away, back-to-back). Pythagorean residual. Base-state efficiency. **A1.11:** spines on `mart_game_spine` (carries `is_scheduled`); `season_record` CTE uses exact-or-as-of so standings (wins/losses/games_back/streak) and season Pythagorean (pythagorean_win_exp/residual_season) populate for today's scheduled games instead of going NULL. |
| `feature_pregame_odds_features` | game_pk | **mart_game_spine**, mart_odds_outcomes, mart_odds_line_movement, mart_bookmaker_disagreement, stg_actionnetwork_public_betting | ~15 | Market-implied probabilities, bookmaker disagreement spread (7 features), public betting percentages. Market columns — subject to exclusion in market-blind retrains. **A1.11:** spines on `mart_game_spine` so today's scheduled games carry current odds/line-movement rows. |
| `feature_pregame_park_status` | (venue_id, season) | mart_eb_park_factors, stg_statsapi_venues (SCD-2) | ~7 | SCD-2 table for park factors. Natural key: (venue_id, season). valid_from = first game at venue for season; valid_to = first game of next season (NULL for current active venues). Retired venues closed with season_close + 1 day. 362 rows, 36 venues, 30 active (2026). No snapshot staging — source is annual grain. **Added Epic 15 Story 15.8.** |
| `feature_pregame_park_features` | game_pk | **mart_game_spine**, mart_park_run_factors | ~5 | Prior-season park run factors. NULL for season-opening games (no prior-season data). NOT re-pointed to SCD-2 — game_year-1 join is already correct; use feature_pregame_park_status for AS-OF queries. **A1.11:** spines on `mart_game_spine` so today's scheduled games get prior-season park factors (the game_year-1 join needs no as-of fallback). |
| `feature_pregame_weather_features` | game_pk | **feature_pregame_weather_status** (SCD-2) | ~5 | Wind speed, wind direction, temperature, humidity. NULL for dome stadiums. Re-pointed to SCD-2 source in Epic 15 Story 15.5; reads `is_current = true` rows. |
| `feature_pregame_umpire_status` | (game_pk, valid_from) | stg_statsapi_umpire_snapshots (SCD-2) | ~10 | SCD-2 table for HP umpire assignments. Natural key: game_pk (one HP ump per game; no ump_position column in source). New row when umpire_name or tendency stats change. Coverage: ~2026-05-02 (Epic T.4). **Added Epic 15 Story 15.7.** |
| `feature_pregame_umpire_features` | game_pk | stg_statsapi_umpire_game_log | ~8 | HP umpire assignment + trailing z-scores of tendency metrics (called strikes above avg, run expectancy delta, run impact, accuracy). Reads stg_statsapi_umpire_game_log directly (not re-pointed to SCD-2) — forward-only SCD-2 coverage would break historical trailing z-score computation. feature_pregame_umpire_status available for AS-OF point-in-time queries. |
| `feature_pregame_meta_model_features` | (game_pk, market_type ∈ {h2h, totals}) | mart_clv_labeled_games, mart_odds_consensus, mart_odds_line_movement, mart_bookmaker_disagreement, mart_game_odds_bridge, feature_pregame_public_betting_features, stg_statsapi_games/lineups | dynamic | **Incremental** (unique_key game_pk+market_type). Training-ready feature mart for the Epic 12 CLV meta-model — base rows from `mart_clv_labeled_games`, enriched with all seven meta-model feature groups (model signal, signal completeness, market, line-movement, public betting, etc.). Built ahead of the label-count gates so it is production-ready when labels accumulate. *(Inventory catch-up 2026-06-13.)* |
| `feature_pregame_game_features` | game_pk (master) | **feature_pregame_game_features_raw**, **feature_league_contact_baseline** | ~690 (incl. 34 `_seasonnorm`; see §4.1) | Master pre-game feature surface (public name; read by predict_today.py, training, the app, the pipeline). **Story 27.7 (2026-06-13): now a THIN wrapper** — the heavy assembly moved to `feature_pregame_game_features_raw`; this model passes every raw column through unchanged and ADDS a `<col>_seasonnorm` version of each of the 34 contact-quality features (z-score vs the strictly-prior AS-OF league baseline in `feature_league_contact_baseline` — the contact→runs conversion regime fix). Raw contact columns are retained for comparison. NULL/zero-variance baselines coalesce the z-score to 0. Splitting the assembly out keeps the public name + every consumer stable while computing the expensive as-of joins once. See the `_raw` row below for the join/feature lineage (lineup, starter, team, odds, park, weather, umpire, cluster/archetype/H2H matchup, line movement, bookmaker disagreement, bullpen, base-state, public betting; **does NOT** join feature_pregame_sub_model_signals — Layer 3 / Epic 9). |
| `feature_pregame_game_features_raw` | game_pk | All feature_pregame_* tables, mart_game_spine, mart_game_results, mart_catcher_framing | ~655 | **Story 27.7:** the RAW heavy assembly (the prior contents of `feature_pregame_game_features`). Joins lineup, starter, team, odds, park, weather, umpire, cluster matchup, batter archetype matchup, H2H matchup, line movement, bookmaker disagreement, bullpen handedness/leverage, base-state splits, and public betting feature models. `has_full_data` flag selects games with complete lineups, starters with 30+ IP history, and prior-season park factors. Bat-tracking columns (Story 2.9). EB batter posteriors (avg_eb_woba/k_pct/bb_pct/iso/uncertainty, eb_coverage_pct × home/away), EB starter posteriors (eb_xwoba_against/k_pct/bb_pct/xwoba_uncertainty × home/away), EB bullpen quality (bp_eb_xwoba/uncertainty/coverage_pct × home/away) — Epic 7.M (2026-06-01). **A1.11 (2026-06-10):** spines on `mart_game_spine` (carries `is_scheduled`) so it holds today's scheduled games; the `team_seq` sequential-posterior CTE uses an exact-or-as-of fallback (completed games keep the exact `game_pk` row, scheduled games carry forward the latest strictly-prior belief). Sequential/lineup/starter blocks for today depend on the Python posterior tables being computed for the slate (`compute_lineup/starter_posteriors.py` + `update_team_posteriors.py`). **Do NOT add new consumers here — read the public `feature_pregame_game_features` (a superset).** |
| `feature_league_contact_baseline` | (game_year, game_date) | feature_pregame_game_features_raw | ~70 (mu/sd × 34 + n_asof_min) | **Story 27.7, Task 1.** Strictly-prior AS-OF league baseline (mean `<col>__mu` + std `<col>__sd`) for every contact-quality feature, one row per (season, date). Powers the `_seasonnorm` columns in the public master table (the contact→runs conversion regime fix; see [[project_totals_model_directional_bias]]). **Leakage-safe:** each date's stats are computed over STRICTLY-PRIOR same-season games only (window frame excludes the current date — `assert_contact_baseline_no_lookahead` test), shrunk toward the prior season's full-season stats with pseudo-count `contact_baseline_shrinkage_k` (default 200) so a baseline exists before the current season accrues. The dbt counterpart of the Task-1 league run-environment monitor (`run_env_regime_monitor.py`): same as-of + prior-anchor methodology, applied per contact feature instead of to the league run rate. Stats/shrinkage live in the `as_of_contact_baseline()` macro (`dbt/macros/season_normalize_contact.sql`); the 34-name list is shared with `betting_ml/utils/season_normalization.py` (drift-guarded by `test_season_norm_parity`). |
| `feature_pregame_sub_model_signals` | (game_pk, side) | mart_sub_model_signals (`baseball_data.betting`), offense_v2_signals, starter_suppression_signals, starter_ip_signals (`baseball_data.betting_features`) | dynamic | Wide-format pivot over mart_sub_model_signals + direct JOINs to the dedicated `*_signals` tables (§1.9). Each registered (signal_name, sub_model_version) pair becomes one column via MAX(CASE WHEN) static pivot. SCD-2 filtered to is_current = true. Refreshed daily by `dbt_sub_model_signals_rebuild` in the Dagster signal phase (Epic O.2). **Registered signal blocks:** run_env_v3/v4 (run_env_mu, run_env_dispersion, run_env_signal, environment_volatility); offense_v1 (pred_runs_raw, runs_index); offense_v2 (pred_runs_mu, pred_runs_dispersion, pred_runs_raw, uncertainty); starter_v1 (starter_suppression_mu/sigma/signal, uncertainty — via direct JOIN); starter_ip_v1 (starter_ip_mu, starter_ip_dispersion, starter_ip_signal, starter_ip_p80_outs, starter_ip_p20_outs, starter_ip_uncertainty, starter_ip_is_bulk_usage — **OUTS UNITS: divide by 3.0 for innings display; keep as outs for NegBin CDF in 6D Candidate B** — via direct JOIN); bullpen_v1 (availability_index, fatigue_signal, quality_mu/sigma/signal, high_leverage_availability_proxy, late_game_volatility_signal); bullpen_v2 (bullpen_mu, bullpen_dispersion, bullpen_fatigue_adjusted_mu, uncertainty — NegBin distributional, Epic 6D); **matchup_v1 (matchup_advantage_mu/sigma, matchup_volatility_signal, matchup_soft_vs_hard_delta, matchup_k_pressure_signal, matchup_power_signal — Ridge soft-mixture, Epic 8; availability-gated, null for sparse-archetype games).** **Added Epic 2, Story 2.1. Last updated Epic 8.4 (matchup block) + Epic O.2 daily refresh (2026-06-02).** |
| `feature_pregame_expected_lineup` | (game_pk, home_away) | mart_player_start_probability (Story 33.1), mart_batter_rolling_stats, mart_batter_vs_handedness_splits | ~20 | **Story 33.3 (added 2026-06-17).** The PRE-LINEUP-available replacement for the dropped Class-B lineup-AVERAGED batter aggregates. Instead of averaging the 9 confirmed starters (unknown pre-lineup), takes the probability-weighted expectation over the candidate roster: `expected_stat = Σ P(start)·stat / Σ P(start)`, with P(start) from `mart_player_start_probability` (walk-forward) and per-batter stats resolved strictly-prior (same as-of carry-forward as `feature_pregame_lineup_features`). Leakage-safe + needs no confirmed lineup; injuries subsumed (P(start) downweights injured). **v1 scope:** rolling-30d + std + prior-season platoon (vs-LHP/RHP); matchup families (vs-pitch-archetype / vs-cluster / bat-tracking) are a documented follow-on (need the opposing probable starter). |
| `feature_pitcher_batter_h2h_matchups` | (game_pk, batter_id) | mart_pitcher_batter_history, mart_pitcher_pitch_archetype, mart_batter_vs_pitch_archetype | ~20 | Career h2h history for each batter vs today's opposing starter. PA, K%, wOBA, xwOBA with Bayesian shrinkage for low-sample pairs. |
| `feature_pitcher_cluster_matchups` | (game_pk, batter_id) | statsapi.pitcher_clusters, statsapi.batter_clusters, mart_batter_archetype_vs_pitcher_cluster | ~10 | Batter archetype vs pitcher cluster matchup stats. Generalization when direct h2h history is sparse. 6-cluster batter taxonomy. |
| `feature_batter_archetype_matchups` | (game_pk, batter_id) | statsapi.batter_clusters, mart_batter_archetype_vs_pitcher_cluster | ~5 | Batter cluster assignment + cluster quality (silhouette score). |

## 4.1 Column-Group Map — model-input surfaces (added 2026-06-17)

A **family-level** map of what's actually in the model-input tables — enough to answer "what can I feature on?" without opening each `.sql`. This is intentionally **not** an exhaustive column list (that churns every retrain — regenerate it from `INFORMATION_SCHEMA.COLUMNS` / dbt `catalog.json` if you need the full set). Column counts verified against Snowflake `INFORMATION_SCHEMA` on 2026-06-17.

### `feature_pregame_game_features` — the master surface (**~690 columns**)

The public model-input table (read by `predict_today.py`, training, the app). Most blocks exist as mirrored **`home_*` / `away_*`** pairs, each with rolling windows (`_7d`/`_14d`/`_30d`), a season-to-date (`_std`) variant, and platoon splits (`_vs_lhp`/`_vs_rhp` / `_vs_lhb`/`_vs_rhb`). The 369-feature model contract is a curated **subset** of these.

| Family | Representative columns | Source block |
|---|---|---|
| **Lineup / offense** (largest) | `home_off_runs_per_game_30d`, `away_avg_xwoba_vs_rhp`, `home_lineup_xwoba_vs_starter_archetype`, `home_lineup_avg_xwoba_vs_cluster`, `avg_eb_woba` (+`_uncertainty`/`_coverage_pct`), `lineup_avg_bat_speed`, `injury_adj_avg_woba_30d`, `home_lhb_count` | `feature_pregame_lineup_features` |
| **Starter** | `home_starter_stuff_plus`, `away_starter_fastball_stuff_plus`, `home_starter_k_pct_14d`, `home_starter_xwoba_against_30d`, `home_starter_whiff_rate_std`, `eb_xwoba_against`, `home_starter_avg_ip_season`, `home_starter_days_rest`, `home_starter_avg_fastball_velo` | `feature_pregame_starter_features` |
| **Team pitching / standings** | `home_pit_woba_against_30d`, `away_pit_k_pct_std`, `away_pit_xwoba_against_14d`, `pythagorean_win_exp_diff`, `home_pythagorean_win_exp`, `away_games_back`, `away_wins`/`away_losses`, `home_win_rate_trailing_3yr`, `home_games_last_7d` | `feature_pregame_team_features` |
| **Bullpen** | `home_bp_xwoba_against_30d`, `bp_eb_xwoba` (+`_uncertainty`/`_coverage_pct`), `away_bullpen_pitches_prev_7d`, `away_high_leverage_used_prev_2d`, `home_closer_used_prev_2d`, `home_bp_k_pct_30d` | `feature_pregame_bullpen_state_features` |
| **Odds / market** ⚠️ *market-blind champions EXCLUDE this whole family* | `home_win_prob_consensus`, `over_prob_consensus`, `total_line_consensus`, `over_american`/`under_american`, `under_implied_prob`, `total_line_movement`, `home_h2h_line_movement`, `ml_consensus_std`, `market_bookmaker_count` | `feature_pregame_odds_features` |
| **Season-normalized contact** (34) | `<contact>_seasonnorm` — each of 34 xwOBA / hard-hit / barrel features z-scored vs the strictly-prior league baseline (Story 27.7) | `feature_league_contact_baseline` |
| **Umpire** (7) | `ump_run_impact_zscore`, `ump_accuracy_zscore` | `feature_pregame_umpire_features` |
| **Weather** (5) | `temp_f`, `wind_component_mph`, `wind_direction_deg`, `humidity_pct` | `feature_pregame_weather_features` |
| **Park** | `park_run_factor_3yr`, `runs_per_game_at_park`, `elevation_ft` (+ dimensions `left_ft`/`center_ft`/… in `_raw`) | `feature_pregame_park_features` |
| **Matchup / cluster** | `home_starter_cluster_id`, H2H families (most per-batter matchup detail lives in `feature_pitcher_batter_h2h_matchups` / `feature_pitcher_cluster_matchups`, NOT the master) | matchup feature models |
| **Identifiers / context / meta** | `game_pk`, `game_year`, `venue_id`, `post_2022_rules`, `series_game_number`, `home_starter_days_rest`, `has_full_data`, `is_new_venue`, `has_starter_platoon_data` | spine / context |

> ⚠️ **Contract vs. mart:** the identifier columns `game_year`, `venue_id`, `home_starter_pitcher_id` still exist in the mart but were **dropped from the model contracts** by Epic 30.1 (leakage/OOD). Market-blind champions also exclude the entire odds/market family. The mart is a superset of any single model's inputs.

### Per-team source marts (the `home_*`/`away_*` blocks before they merge into the master)

| Mart | Cols | Dominant families |
|---|---|---|
| `feature_pregame_team_features` | ~119 | team pitching (`_pit_`), standings/Pythagorean, schedule context, base-state |
| `feature_pregame_starter_features` | ~89 | starter rolling + platoon + CSW + pitch-mix drift + EB starter posteriors |
| `feature_pregame_lineup_features` | ~75 | lineup-aggregated offense, platoon splits, EB batter posteriors, bat-tracking, injury-adjusted |
| `feature_pregame_odds_features` | ~31 | consensus implied probs, line movement, bookmaker disagreement, public betting (market-only) |
| `feature_pregame_bullpen_state_features` | ~19 | bullpen effectiveness, leverage workload, closer availability |

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
| Forward-looking spine (A1.11) | Feature marts spine on `mart_game_spine` (completed `mart_game_results` ∪ today's scheduled `stg_statsapi_games`) so the feature store can serve today's not-yet-played games rather than always falling back to the intraday assembly. Each spined row carries an `is_scheduled` flag. |
| Exact-or-as-of fallback (A1.11) | Point-in-time joins on the spine resolve as: completed game (`is_scheduled = false`) → ONLY the exact `game_pk`/`record_date` row (byte-for-byte preservation of historical feature vectors); scheduled game (`is_scheduled = true`) → the latest **strictly-prior** row (`source.game_date < spine.game_date`), `qualify`d to prefer exact-then-most-recent. Applied to sequential posteriors, season record/standings, season Pythagorean, bullpen, and park blocks. Leakage-safe (never reads a same-day or future row). |
| `has_full_data` flag | Feature master table gate for unbiased training subset selection. |
| Incremental MERGE | 13 mart models use incremental strategy with `unique_key` MERGE to avoid full rebuilds on large pitch-level tables. |
| Model versioning | `daily_model_predictions` includes `model_version` (v0 through v4). `model_registry.yaml` tracks artifact paths, gates, and wave decisions. Sidebar filter on 4_Model_Performance.py reads versions dynamically — no code change needed on promotion. |

---

# 6. Gap Analysis — Architecture vs. Current State

This section identifies what is missing or incomplete relative to the architecture defined in `refined_architecture_proposal.md`.

> **Refreshed 2026-06-17.** §6.1–6.8 (sub-model + temporal infrastructure) are stable. §6.7 (CLV) and §6.9 (model retrains) are brought current below, and **new subsections §6.10–§6.15 cover the epics that postdate the original gap analysis** — Layer-3 aggregation (9/10/11), sequential + full-Bayesian (16/16B/17), the production-model audit & serving-honesty work (30), the totals/data-expansion frontier (27/31/32), the pregame-projection layer (33), and the decision layer (19/22). The blunt headline since the original draft: **the models are well-built but have no demonstrated market edge** (4 H2H + ~9 totals no-edge confirmations), and the binding constraint shifted from "missing features" to **serving honesty + decision-layer leverage**. `implementation_guide.md` remains the authoritative per-story status; this section is the architecture-level summary.

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
| Opponent quality controls in training dataset | ✅ **Present** | Team + starter + bullpen features all join into `feature_pregame_game_features`; the master feature surface is the training dataset. |
| Within-season scoring-environment state (the run-env *frontier*) | 🔬 **Epic 27 (active)** | The static run-env signal can't track the contact→runs conversion regime shift (2025 contact got harder, runs flat). Epic 27 adds within-season state: season-normalized contact features (27.7 → `feature_league_contact_baseline` + the `_seasonnorm` columns, §3.11/§4), team defense-quality (`mart_team_defense_quality_rolling`), batted-ball interactions (`mart_pitcher_batted_ball_profile`), reliever-availability (`mart_reliever_top3_availability`), + the 27.9 ball-CoR scoping spike. The unsolved totals *variance* gap lives here. See §6.13. |

## 6.3 Offensive Quality Model (Epic 4)

| Gap | Status | Notes |
|---|---|---|
| ZiPS/Steamer projection features in lineup model | ✅ **Present** | ZiPS hitting projections are joined per slot in `feature_pregame_lineup_features` with Bayesian rookie shrinkage (k=200 PA, Story 2.6). |
| Expected-lineup (pre-lineup) offense aggregates | ✅ **New — Epic 33.3** | `feature_pregame_expected_lineup` (§4) reconstructs the lineup-averaged offense as Σ P(start)·stat / Σ P(start) so morning/pre-lineup serving no longer imputes those columns to a constant. See §6.14. |
| Lineup depth / entropy features | **Partial / not prioritized** | `lineup_depth_score` is not confirmed in the current `feature_pregame_lineup_features` schema; not on the critical path. |
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

## 6.7 CLV Meta-Model (Epic 12) — 12.4 BUILT + CONVERGED (2026-06-16)

The "41 games / correctly-not-started" status in the original draft is **superseded**. The label infrastructure and the v0 Bayesian model now exist.

| Gap | Status | Notes |
|---|---|---|
| CLV-labeled game count | ✅ **Gates cleared** | `mart_clv_labeled_games` (§3.11): **12,797 labeled games** (4,924 h2h / 7,873 totals), 2021-04-01 → 2026-06-15, 35.3% CLV-positive. ⚠️ That total **includes the historical-proxy backfill** (predicted_at = backfill date). The **truly-live subset** (game-time predictions, game_date ≥ 2026-05-04) is **441 h2h / 385 totals** — which clears the Epic 12 ≥50 and ≥100 gates. `mart_clv_label_count` tracks the thresholds. |
| Bayesian sequential meta-model (12.4) | ✅ **BUILT + CONVERGED (2026-06-16)** | `train_bayesian_meta_model.py` — all 3 convergence gates pass (R-hat 1.0, CI-width 0.076, top-quartile +0.15). Feature set is data-forced lean (several wishlist features NULL at morning serve); `edge_mag` + `open_extremity` credibly nonzero, `pub_align` null. See `[[project_epic12_4_status]]`. |
| Meta-model feature mart | ✅ **Done** | `feature_pregame_meta_model_features` (§4, incremental) — all seven meta-model feature groups, built ahead of the gates. |
| Gate integration into Epic 19 (12.5) | ⬜ **Next** | Wire `meta_p_clv_positive` into the permission gate as a 6th criterion once `meta_n_games_trained ≥ 100` (Story 12.5). 12.9/O.5 wire the weekly Dagster retrain. |
| `prediction_ts` stored per prediction | ✅ **Present** | `prediction_snapshots` captures `feature_snapshot` + timestamp + model artifact URI (Epic 15.9). Provenance/backfill flag added Story 30.7. |

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

## 6.9 Production Champion Models (current `model_registry.yaml`, 2026-06-17)

The Epic 7.M market-blind retrains (v3/v4, 2026-06-01) are superseded. Current promoted champions — all **market-blind**, advanced by Epic 30 feature-hygiene (30.1 dropped the leakage-prone identifier features `home_starter_pitcher_id` / `venue_id` / `game_year`; 30.4 contract cleanup):

| Target | Champion | Version | CV Metric | Notes |
|---|---|---|---|---|
| home_win | `xgb_classifier_market_blind` | **v5** | Brier **0.1948** | XGBoost + Platt. Rollback: v3 `xgb_eb_enriched`. |
| run_differential | `ngboost_tuned_market_blind` | **v5** | MAE **3.066** | NGBoost Normal, n=500. |
| total_runs | `ngboost_tuned` (Normal n=500) | — | MAE **3.3251** | **`bet_paused = true`** — Epic 19 surfaces NO totals bets until it beats prior-predictive NLL 2.8893 AND prior-naive Brier 0.248 on a rolling-60 live window (≥9 totals no-edge confirmations; see §6.13). |

**Pre-lineup (morning) variants — Epic 33.0 (`pre_lineup_v1`):** separate Class-A models trained on only morning-available features, served when lineups are unconfirmed: home_win 156 feats, run_diff 126, total_runs 89. Each beats the coinflip floor, so a morning pick is strictly better than abstaining; `predict_today.py` serves pre-lineup in the morning and the champion post-lineup. See §6.14.

---

## 6.10 Layer-3 Aggregation Models (Epics 9 / 10 / 11) — built, NO market edge

| Component | Status | Notes |
|---|---|---|
| Signal integration / stacking (Epic 9) | ✅ Built; weak | Sub-model signals flow into `feature_pregame_sub_model_signals`; stacking weights ≈ near-uniform ⇒ signals weak/redundant. |
| Layer-3 totals distribution (Epic 10) | 🟡 Shadow-only | NegBin distribution model; neither it nor the point model beats Bovada/naive on honest 2026. Totals **bet-paused**. |
| Layer-3 H2H retrain (Epic 11) | 🔴 No edge | On clean 2026 the market (Brier ~0.197) beats the model (~0.222). 4 independent H2H no-edge confirmations (11, 16B.7, 28.4, 28.5). |
| Layer-3 in-sample leakage | ✅ Diagnosed | `generate_*_signals.py` scored 2021+ with sub-models trained 2021-25 → only 2026 is honest OOS. `[[project_layer3_signal_leakage]]`. |

## 6.11 Sequential Posteriors & Full Bayesian (Epics 16 / 16B / 17)

| Component | Status | Notes |
|---|---|---|
| Sequential prior-update engine (Epic 16) | ✅ Done (2026-06-03) | Player (16.1) + team (16.3) sequential posteriors, backfilled all seasons 2021-26; `team_seq` block in `feature_pregame_game_features_raw`. |
| Sequential sub-model enrichment (16B) | 🔴 CLOSED/FAIL (2026-06-04) | Combined-μ 9.01 > 8.85 gate; +0.40 totals bias unchanged after all 4 sub-model retrains. |
| Full Bayesian propagation / PyMC NegBin (Epic 17) | 🔴 CLOSED (2026-06-05) | Structural Jensen floor (β²σ²/2) ⇒ floor 8.87 > 8.81 threshold; within-season regime shift not learnable from available signals. 7th totals no-edge confirmation. |

## 6.12 Production-Model Audit & Serving Honesty (Epic 30) — the binding constraint

| Finding / fix | Status | Notes |
|---|---|---|
| Live home_win ≈ ZERO skill | 🔴 → 🟢 root-caused | Live corr ≈ 0.001 / Brier 0.252 vs CV 0.198. Root cause (30.3) = **point-in-time completeness, NOT a contract bug**: morning serve imputes ~30% of the matrix to constants (feature store sparse pre-game, dense post-game) ⇒ the 0.42 offline corr is optimistic. |
| Feature hygiene (30.1) | ✅ Done | Dropped `home_starter_pitcher_id` / `venue_id` / `game_year` (memorization / OOD) from all 3 contracts → re-promotes (now v5). |
| Serving fix | ✅ Done | Serving-parity guard + bind picks to the dense post-lineup path + the pre-lineup models (Epic 33.0) for morning. Freshness gate (30.13) abstains+alerts on stale features. |
| Umpire feed (30.5) | ✅ Done | `ump_*_zscore` null 34.6%→1.1% (UmpScorecards JSON loader + afternoon assignment). |
| Provenance + explainability | ✅ Done | Champion-lineage SCD + `is_backfill` flag (30.7); per-pick SHAP attribution `pick_explanation` (30.15). |

## 6.13 Totals Variance Frontier & Data Expansion (Epics 27 / 31 / 32)

The totals model is **level-unbiased but per-game variance-deficient** (Story 29.1: trails the market line by ~0.53 RMSE; it knows the average, not which game is 6 vs 11 runs). This — not a missing feature — is why totals is bet-paused.

| Thread | Status | Notes |
|---|---|---|
| Within-season env state (Epic 27) | 🔬 Active | Season-normalized contact (27.7), defense-quality, batted-ball interactions, reliever-availability marts (§3.11); 27.9 ball-CoR spike. |
| Orthogonal data expansion (Epic 31) | 🟡 Mostly closed as no-signal | Weather (forecast-only; CLOSED as noise for totals), team-OAA (corr −0.023, no signal). 31.5 (rolling Stuff+/Location+) LOW/GATED. Conclusion: the constraint is information-structural, not data breadth. |
| Generative per-side totals (Epic 32) | 🔬 Research / deferred | Model home/away runs as separate count distributions → convolve → honest predictive variance + alt-line pricing. Gated behind 27 + 30.2 + 30.6; only escalate if the cheaper 30.2 variance wiring is insufficient. |

## 6.14 Pregame Projection Layer (Epic 33) — pre-lineup serving

Recovers the lineup-gated signal by **projecting** it rather than dropping it (the high-fidelity half of 30.8).

| Component | Status | Notes |
|---|---|---|
| Pre-lineup baseline models (33.0) | ✅ Done (2026-06-15) | Class-A home_win/run_diff/total_runs (156/126/89 feats); serving split wired in `predict_today.py`; `pre_lineup_v1` lineage. |
| Player playing-time P(start) (33.1) | ✅ Done (2026-06-16) | `mart_player_game_starts` (§3.13) + `mart_player_start_probability` (Python). Learned P(start) beats raw rate (precision@k 0.802, ECE 0.014). |
| Expected-lineup feature family (33.3) | ✅ Built (2026-06-16) | `feature_pregame_expected_lineup` (§4) — Σ P(start)·stat / Σ P(start) pre-lineup offense aggregates. |
| Rotation / probable projection (33.2) | ⬜ Opportunistic | Fills the ~7-14% look-ahead tail where the probable isn't announced. |

## 6.15 Decision Layer (Epics 19 / 22) — the under-exploited lever

With point accuracy ceilinged and no market edge on straight bets, the decision layer (which bets to take, how much) is where EV most plausibly remains.

| Component | Status | Notes |
|---|---|---|
| Permission gate (Epic 19) | 🟡 Built, validation pending | `compute_bet_permission()` + `qualified_bet`/`gate_signals_met`/`game_conviction_score` columns exist. 19.3 backtest (does qualified beat unqualified on CLV?) gates promoting it to the default view. ⚠️ 19.6: conviction/gate columns are NULL on current live rows (dropped from the write path) — restore before sorting the app on them. |
| Calibration audit (9.8) | ✅ Done (2026-06-16) | Served posteriors calibrated on 2026 → unblocks 22.4. home_win live-calib is a deliberate A2.9 identity (don't recalibrate). |
| Uncertainty-aware selection + σ-Kelly (22.4) | ⬜ Unblocked | Abstain on low edge-to-σ; σ-scale Kelly. Orthogonal to the accuracy ceiling. Advisory only ([[feedback_no_auto_betting]]). |
| Correlation-adjusted portfolio Kelly (22.1 → 22.2) | ⬜ Specced | Pairwise bet correlation → portfolio-variance-budgeted Kelly. |

---

# 7. Summary: What Exists vs. What the Architecture Needs

| Architecture Layer | Current State | Gap Size |
|---|---|---|
| Raw data ingestion | Comprehensive. Statcast, FanGraphs, Odds API (historical), Parlay API (live, 2026+), Stats API, Action Network, weather, umpires, OAA. | Minimal — historical weather confirmed 2021+. Parlay API cutover 2026-06-01. |
| Staging layer | Complete for all current sources including all 3 Parlay API staging models. | None — add new staging models as new sources are added. |
| Rolling stats / mart layer | Very strong. Team, player, pitcher, bullpen, matchup, archetype, odds all covered. | None — sub-model output tables now created (§1.9). |
| Feature layer (pre-game vectors) | Strong. ~690 columns (master; see §4.1 column-group map) + `_seasonnorm` contact set. Leakage guards enforced. + expected-lineup (pre-lineup) aggregates (33.3). | Low — the gap is no longer feature breadth; see "Market edge" + "Serving honesty" below. |
| Production champion models | ✅ All 3 promoted, market-blind, Epic-30-hygiene-cleaned: home_win **v5** (Brier 0.1948), run_diff **v5** (MAE 3.066), total_runs (NGBoost Normal, MAE 3.3251) — **totals bet-PAUSED**. + pre_lineup_v1 morning variants (§6.9/§6.14). | None on accuracy; see Market edge. |
| Sub-model infrastructure | ✅ Complete (Epic 2). Output table, registry, eval harness, SCD-2 columns all shipped. | None. |
| Sub-model signals (run env, offense, starter, bullpen, matchup) | ✅ All six champions trained + generating signals (run_env_v4, offense_v2, starter_v1, starter_ip_v1, bullpen_v1+v2, matchup_v1). Daily via Dagster. | Layer-3 integration done but weak (§6.10). |
| EB posteriors | ✅ Python scripts now also migrated to dbt (`dbt/models/eb_posteriors/`, Story A2.11, §3.12). | Validation/cutover per story. |
| Layer-3 aggregation + **market edge** | 🔴 Built, **NO market edge** — 4 H2H + ~9 totals no-edge confirmations (§6.10/§6.13). Totals bet-paused. | **The real gap.** Edge most plausibly lives in the decision layer (§6.15) + CLV meta-model, not a better point model. |
| Serving honesty | 🟢 Root-caused + fixed (Epic 30): live zero-skill was point-in-time imputation, not a contract bug; fixed via serving guard + pre-lineup models + freshness gate (§6.12). | Confirm live skill ≈ offline on the post-30 re-measure. |
| CLV meta-model | ✅ 12.4 BUILT + CONVERGED (2026-06-16); labels cleared (§6.7). | Integration into the gate (12.5) + accumulate to ≥500 (12.6). |
| Decision layer (Epic 19/22) | 🟡 Permission gate built; 9.8 calibration done. | 19.3 validation; 22.4 σ-aware selection (unblocked); 19.6 restore conviction persistence (§6.15). |
| Temporal/SCD infrastructure | ✅ **Complete** — Epic 15 all 9 stories (8 SCD-2 marts + 15.9 reconstruction). Sequential posteriors (Epic 16) done; full-Bayesian (17) closed (§6.11). | None. |
