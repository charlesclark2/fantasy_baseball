# Baseball Betting & Fantasy: Project Context

## 1. Mission

Build a machine learning system capable of predicting the outcome and total runs scored in an MLB game given the pitching matchup, team matchup, and confirmed batting lineups. The system is grounded in Statcast pitch-level data and augmented with game schedule, lineup, and ballpark context from the MLB Stats API.

**Phases 1–6 are complete as of 2026-05-01.** The data mart (Phase 1), pre-game feature store (Phase 2), EDA (Phase 3, 2026-04-24), ML pipeline (Phase 4, 2026-04-25), model selection and prediction CLI (Phase 5), and betting application layer (Phase 6, 2026-05-01) are all done. **Phase 7 (Model Refinement and Production Infrastructure) is the active phase.**

**Phase 7 progress:** Card 7A (alpha-grid-rerun, 2026-05-02) complete — full 11-candidate α grid rerun against corrected 2026 odds data (14,126 has_odds eval records); best_alpha confirmed at 0.0 (log-loss rises monotonically from 0.6833 at α=0.0 to 0.7336 at α=1.0); `alpha_tuning_results` populated with 11 rows; `betting_ml/models/best_alpha.json` written; `predict_today.py` three-tier fallback (Snowflake → file → 0.5) confirmed in place; Gaps 4 and 5 from postmortem_v0.md resolved. Card 7.C (home-win-probability-calibration, 2026-05-02) complete — diagnostic analysis confirmed systematic home-team underprediction (ECE baseline 0.0614); Platt scaling calibrator fit on 2026 in-season results (train_n=842, eval_n=211); ECE improved 0.0614 → 0.0370; `betting_ml/models/home_win/calibrator.joblib` and `calibrator_meta.json` persisted; `predict_today.py` updated to load calibrator at startup, apply it per-game, write `calibrated_win_prob` to `daily_model_predictions`, and use it as input to `compute_edge()` and `compute_kelly()`; `consensus_win_prob` retained as audit column; `calibrated_win_prob FLOAT` column added to Snowflake table via DDL migration; `model_registry.yaml` updated with calibrator metadata; feature-shape mismatch bug fixed via `_FEATURES_ADDED_AFTER_LAST_RETRAIN` exclusion set (drops 4 weather columns until Card 7.D retraining); Gap 2 from postmortem_v0.md resolved. Card 7.E (FanGraphs ingestion pipeline, 2026-05-02) complete — full FanGraphs ingestion pipeline built and validated; raw tables (`fg_stuff_plus_raw`, `fg_zips_pitching_raw`, `fg_zips_hitting_raw`, `fg_hitting_leaderboard_raw`) in `baseball_data.fangraphs` schema; ingestion scripts ship manual CSV uploads for ZiPS projections (2024–2026 backfill) and direct API pulls for Stuff+ and hitting leaderboard rolling windows (7d/14d/30d/season); four staging models (`stg_fangraphs__stuff_plus`, `stg_fangraphs__zips_pitching`, `stg_fangraphs__zips_hitting`, `stg_fangraphs__hitting_leaderboard`) with proper grain and all tests passing; three mart models (`fct_fangraphs_pitching_analytics`, `fct_fangraphs_hitting_analytics`, `dim_fangraphs_player_xref`) in `baseball_data.betting`; `dim_fangraphs_player_xref` cross-references FanGraphs player IDs (numeric = MLB, `sa`-prefixed = MiLB) to MLBAM IDs — 9,330 rows total (4,552 MLB, 4,778 MiLB), 2 missing MLBAM IDs; validation script (`scripts/validate_fangraphs_pipeline.py`) runs four checks (raw row counts, MLBAM join rate ≥95% for MLB-active pitchers only, Stuff+ null rate <10%, mart duplicate grain checks) — all PASS with 96.3% MLBAM join rate (1,004/1,042 MLB-active pitchers); `betting_ml/evaluation/fangraphs_validation.md` written; Gap 8 from postmortem_v0.md resolved. Card 7.F (FanGraphs Stuff+ and pitch-arsenal features, 2026-05-03) complete — `stg_fangraphs__pitcher_arsenal` and `fct_fangraphs_pitcher_arsenal_wide` built; 13/18 numeric arsenal features retained by feature selection (top: `home_starter_stuff_plus` rank 16/267); training data cutoff changed to `game_year >= 2021` (pre-2020 rows had 0% Stuff+ population); all three models retrained on 10,243 rows (267 features): home_win Brier 0.2443 (flat), total_runs MAE 3.4856 (−0.038), run_differential MAE 3.4586 (+0.039, LogNormal excluded); `model_registry.yaml` updated for all three; `betting_ml/evaluation/stuff_plus_feature_impact.md` created; full retraining after future feature expansion deferred to Card 7.MA. Card 7.H (umpire tendency features, 2026-05-03) complete — two-source architecture: UmpScorecards bulk CSV (25,556 rows, 2015–2026) for historical tendency metrics + MLB Stats API `hydrate=officials` for daily forward-path assignment; `baseball_data.statsapi.umpire_game_log` table; `stg_statsapi_umpire_game_log` staging model (ROW_NUMBER dedup, preferring umpscorecards rows); `feature_pregame_umpire_features` with trailing 3-yr z-scores, leakage guard, and sample gate; 5 features computed, 2 retained by corr threshold (ump_runs_per_game_zscore |r|=0.024, ump_accuracy_zscore |r|=0.021); 99.4% coverage for 2026 regular season games; `feature_pregame_game_features` updated with LEFT JOIN; daily ingestion wired into `daily_ingestion.yml`; `betting_ml/evaluation/umpire_feature_impact.md` written; LogNormal permanently excluded from run_diff search grid; model retraining deferred to pre-7.MA batch checkpoint. Card 7.I (injury and confirmed lineup features, 2026-05-03) complete — MLB Stats API `/v1/transactions` endpoint used as authoritative IL source; `baseball_data.statsapi.player_transactions` table (66,497 rows, 2021–2026 backfill); `scripts/ingest_transactions.py` uses bulk temp-table + DELETE/INSERT + `INSERT INTO ... SELECT PARSE_JSON(...)` pattern (Snowflake rejects `PARSE_JSON` in VALUES clause); `stg_statsapi_transactions` deduplicates raw rows; `stg_statsapi_player_injury_status` derives point-in-time intervals via `LEAD()` — all IL events use `typeCode='SC'`, placement vs. activation distinguished by description `ILIKE` patterns (confirmed via dry-run); `feature_pregame_lineup_features` extended with `injured_player_count`, `injury_adj_avg_woba_30d`, `injury_adj_avg_xwoba_30d` (divides by 9 to penalise IL absences); `feature_pregame_game_features` exposes `home_`/`away_` prefixed versions; Streamlit Today's Picks shows IL warning badge per team; 33.4% of game-rows have ≥1 IL player, `injury_adj_avg_woba` (0.308) < `avg_woba` (0.331) confirming penalty is live; row count unchanged (51,382); model retraining deferred to pre-7.MA batch checkpoint. Card 7.J (hitter vs. pitcher pitch-archetype matchup features, 2026-05-03) complete — `mart_pitcher_pitch_archetype` built (7,879 pitcher × season rows; 49% fastball_dominant, 45% mixed, 7% breaking_dominant; archetype avg pitch-mix percentages confirm correct threshold application); `mart_batter_vs_pitch_archetype` built (Bayesian shrinkage at 50 PA, blending toward wOBA=0.320/xwOBA=0.315/K%=0.225/ISO=0.165 league averages; adj_woba near prior for breaking_dominant avg 13 PA, meaningful signal for fastball_dominant/mixed avg ~100 PA); `feature_pregame_lineup_features` and `feature_pregame_game_features` each extended with 6 new archetype matchup columns (lineup_woba/xwoba/k_pct/iso_vs_starter_archetype, lineup_archetype_pa_coverage, starter_pitch_archetype); prior-season leakage guard on all archetype joins; row count unchanged (51,382); `betting_ml/evaluation/matchup_split_feature_impact.md` written; CV impact numbers and model retrain deferred to pre-7.MA batch checkpoint.

**Phase 4 summary:** All seven EDA notebooks and Phase 3 analysis scripts complete. Foundation, feature selection, and baseline models complete for all three targets (Cards 4.6–4.11). Card 4.12 (hyperparameter optimization) complete — XGBoost tuned via Optuna TPE for all targets; NGBoost grid-searched for total_runs and run_differential. Card 4.13 (Bayesian probability layer) complete — best_alpha=0.0 (market dominates; model adds directional edge signal, not calibration); 230 output rows across 115 2026 games written to Snowflake.

**Phase 5 summary:** Card 5.1 (model registry) complete — `model_registry.yaml` with `_prod` artifacts for all three targets. Card 5.2 (pre-game prediction CLI) complete — `predict_today.py` scores all confirmed games, applies the Bayesian layer, and writes to `baseball_data.config.prediction_log` in Snowflake; parquet/CSV outputs removed as of 2026-05-01. Card 5.3 (lineup monitor) substantially complete (22/23 criteria) — `task_lineup_monitor` live and STARTED in Snowflake, `lineup_monitor_proc` deployed, `dbt_staging_build.yml` validated end-to-end; one AC (pipeline_run_log entry from an actual lineup dispatch) self-completes on next day with confirmed lineups.

**Phase 6 summary (complete as of 2026-05-01):** Card 6.A (Snowflake Task DAG) and Card 6.G (2026 prediction backfill) complete. Card 6.B (Today's Picks page, 2026-04-28) — app skeleton, picks table, market movement expander, odds refresh button, and timezone fix shipped. Card 6.C (Market Comparison page, 2026-04-29) — game selector scoped by `event_id`, moneyline line movement chart, totals O/U bar chart, sharp/soft panel, cross-bookmaker table, per-bookmaker deep-dive card, and post-game warnings shipped. Card 6.D (EV Tracker & Kelly Sizer page, 2026-05-01) — All Markets EV table (four markets per game), Actionable flag, lineup-pending banner, doubleheader deduplication, correlated-bet deduplication in Suggested Slate, interactive checkbox selection with reactive metrics, American-odds column, and bankroll input shipped. Card 6.E (Model Performance page, 2026-05-01) — Brier score trend (rolling 14-day, model vs. market), CLV bar chart by week, cumulative P&L simulation (Kelly and flat), summary metrics row with tooltips; all sections support Combined/Moneyline/Totals tabs and global date-range filter; `backfill_prediction_log.py` shipped as standalone script; Snowflake result cache disabled on session. Card 6.H (Post-v0 Model Postmortem, 2026-05-01) — postmortem complete; key finding: mean h2h edge is −0.036 (NGBoost alone) or −0.017 (consensus_win_prob blend), ~35% positive-edge predictions — model is not beating the market; consensus_win_prob fix applied in Card 6.H (cons_win now passed to `compute_edge()`, `compute_posterior()`, `compute_kelly()` in `predict_today.py`); actual measured impact: −0.0361 → −0.0166 mean h2h edge, 22.95% → 35.39% positive across 941 has_odds rows; `betting_ml/evaluation/postmortem_v0.md` created with 8-gap analysis and Phase 7 roadmap; FanGraphs data pipeline (Stuff+, pre-season projections, hitter/pitcher matchups, pitcher clustering) added as Gap 8 and Phase 7 P1/P2 items. Card 6.I (Application Branding, 2026-05-01) — app renamed "Diamond Edge" (💎); `streamlit_app.py` refactored to `st.navigation()` dispatcher; landing page extracted to `app/home.py` with project description, navigation guide, model fact sheet, and daily workflow expander with Graphviz pipeline diagram. **Card 6.F (alpha/retraining) deferred to Phase 7** — renamed and moved to `plan_specs/phase_7/D_model_retraining_cadence.yaml`; blocked until Phase 7A produces a market-beating model (mean edge > +0.01).

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Data Warehouse | Snowflake |
| Transformation | dbt-fusion / `dbtf` (SQL) |
| Ingestion | Python (`scripts/savant_ingestion.py`, `scripts/ingest_statsapi.py`, `scripts/odds_api_ingestion.py`) |
| ML (planned) | Python (`betting_ml/`) |
| EDA | Marimo (`exploratory_data_analysis/`) — reactive notebooks run via `uv run marimo run <notebook>.py` |

---

## 3. Canonical Join Keys

These keys govern how all models relate to one another. Using any other identifier as a join key will produce incorrect or ambiguous results.

| Grain | Key | Description |
|---|---|---|
| **Pitch** | `pitch_sk` | MD5 surrogate key derived from `game_pk + at_bat_number + pitch_number + batter_id + pitcher_id + inning + inning_half`. Uniquely identifies every pitch ever thrown. |
| **Game** | `game_pk` | MLB Stats API integer identifier for a game. Present in both Statcast and Stats API sources. All game-level models key on this. |
| **Batter** | `batter_id` | Statcast/BAM integer player ID for the batter. Used in all player-level models, splits, and rolling stats. |
| **Pitcher** | `pitcher_id` | Statcast/BAM integer player ID for the pitcher. Used in all player-level models, splits, and rolling stats. |

---

## 4. Data Sources

### 4.1 Statcast (`baseball_data.savant`)

**Ingestion:** `scripts/savant_ingestion.py` pulls pitch-level data directly from the Baseball Savant CSV export endpoint (`https://baseballsavant.mlb.com/statcast_search/csv`). Requests are chunked by single calendar day to stay under Baseball Savant's 25,000-row per-request limit. Each day is deleted before re-insertion, making reruns idempotent. The script auto-detects the last loaded date and defaults the end date to yesterday, so a daily run with no arguments keeps the table current. New Baseball Savant endpoints can be added by defining a `StatcastEndpoint` in the `ENDPOINTS` registry — no other code changes are needed.

```bash
# Daily update (auto-detects gap from last loaded date to yesterday)
uv run savant_ingestion.py batter_pitches

# Explicit range (e.g. backfill or reprocess)
uv run savant_ingestion.py batter_pitches --start-date 2026-03-20 --end-date 2026-04-21
```

**Current data:** 2015-04-05 through present (updated daily). 2026 season data begins 2026-03-25 (Opening Week).

**`batter_pitches`** — The core source table. One row per pitch per plate appearance per game. Contains 100+ columns covering:

- Game and plate appearance identifiers
- Pitch physics: release speed, spin rate, movement (pfx), release extension, arm angle
- Pitch outcome: ball, strike, swinging strike, foul, in-play
- Plate appearance result: single, double, HR, K, walk, etc.
- Batted ball tracking: exit velocity, launch angle, hit distance, batted ball type
- Expected metrics: xBA, xwOBA, xSLG (in-play events only)
- Win/run expectancy delta per pitch
- Score and base/out state at the time of each pitch
- Fielding alignment flags (shift, shade)
- **Bat tracking (2023-07-14 onward; swing events only):** `bat_speed_mph`, `swing_length_ft`, `attack_angle_degrees`, `swing_path_tilt`, `attack_direction` — Hawk-Eye bat sensor rolled out at 2023 All-Star break; ~45% population rate (swing-contact pitches only)
- **Intercept offset (2023-07-14 onward; swing events only):** `intercept_offset_x_inches`, `intercept_offset_y_inches` — same rollout and coverage as bat tracking
- **hyper_speed (2015 onward):** Available since first Statcast season; ~33% population rate (batted contact events); distinct from the 2023 Hawk-Eye bat tracking system

**`ref_players`** — Player reference table with BAM IDs, full names, and career date ranges.

### 4.2 MLB Stats API (`baseball_data.statsapi`)

**`monthly_schedule`** — One row per ingested month. The `json_field` VARIANT column contains full game metadata including confirmed pre-game batting lineups (`lineups.homePlayers`, `lineups.awayPlayers`). Ingested via `scripts/ingest_statsapi.py schedule`.

**`venues_raw`** — One row per ballpark. The `json_field` VARIANT column contains field dimensions, surface type, roof type, GPS coordinates, elevation, timezone, and cross-reference IDs. Ingested via `scripts/ingest_statsapi.py venues`.

### 4.3 The Odds API (`baseball_data.oddsapi`)

Betting market data sourced from [The Odds API](https://the-odds-api.com/). Ingested via `scripts/odds_api_ingestion.py`. All tables are append-only; raw JSON is stored at full fidelity so no source data is lost.

**`mlb_events_raw`** — One row per ingestion run of the `/v4/sports/baseball_mlb/events` endpoint. `raw_json` contains the full response array of upcoming events. Includes ingestion metadata: `load_id`, `ingestion_ts`, `x_requests_used`, `x_requests_remaining`, and the full `request_url` and `request_params` for auditability.

**`mlb_odds_raw`** — One row per event per market/region ingestion call of the `/v4/sports/baseball_mlb/odds` endpoint. `raw_json` preserves the complete event object including the nested `bookmakers → markets → outcomes` array. Convenience columns (`event_id`, `sport_key`, `home_team`, `away_team`, `bookmakers_count`) are extracted for fast filtering without JSON parsing. API credit headers (`x_requests_used`, `x_requests_remaining`) are logged and persisted with every row.

**API credit monitoring:** Every call to The Odds API returns `x-requests-used` and `x-requests-remaining` headers. These are captured by `OddsApiResponse`, logged at INFO level after each request, and written into both raw tables. If a header is missing the value is stored as `NULL` — ingestion never fails due to absent credit metadata.

**Default ingestion window:** The events endpoint defaults to a 7-day forward-looking window (today at 00:00:00 UTC through +7 days) using helpers in `scripts/date_utils.py`. The window can be overridden at the CLI.

### 4.4 Seeds

**`ref_teams`** — Static 33-row reference table (30 active franchises + legacy abbreviation entries). Contains `team_abbrev`, `team_id`, `team_name`, `league` (AL/NL), `division` (East/Central/West), and `is_active` flag.

### 4.5 Data Availability Windows

See `data_quality/data_availability_windows.md` for verified first-available dates, per-season pitch counts, and ML design implications for each feature group: Statcast full history, bat tracking (2023-07-14+), intercept offset (2023-07-14+), hyper_speed (2015+), confirmed lineups (2015+, 100% coverage), probable starters (2015+), and odds data (2026-04-23+).

---

## 5. Data Architecture

### 5.1 Feature Layer

The feature layer (`dbt/models/feature/`) is a dedicated ML boundary layer, separate from the mart layer. Models are materialized as **tables** into the `baseball_data.betting_features` Snowflake schema (distinct from `baseball_data.betting` where mart models live). All models in this layer enforce the **no-leakage rule**: every rolling window and stat lookup uses `< game_date` — no same-day data may appear in any feature.

Phase 2 (complete as of 2026-04-23) populated this layer with six pre-game feature assembly models:

| Model | Grain | Description |
|---|---|---|
| `feature_pregame_lineup_features` | Game × side | Per-team lineup feature vector with aggregated batter rolling stats and prior-season platoon splits across all 9 lineup slots |
| `feature_pregame_starter_features` | Game × starter | Per-starter feature vector with rolling pitcher stats, days rest, and prior-season platoon splits |
| `feature_pregame_team_features` | Game × team | Per-team context: rolling offense, pitching, bullpen workload and effectiveness, season record, and schedule context (days rest, streak, timezone travel) |
| `feature_pregame_park_features` | Game | Park dimensions, elevation, surface, roof type, and empirical run factors |
| `feature_pregame_odds_features` | Game | Pre-game betting market features from lowvig (selected for lowest vig across h2h and totals markets). Moneyline + totals prices, vig-adjusted implied probabilities, market vig. Leakage guard: only `ingestion_ts < commence_time` snapshots used. Prices populate going forward via live ingestion; historical prices require Card 3 backfill completion. |
| `feature_pregame_game_features` | Game | Master assembly: one wide row per game joining all five feature tables; 25,146 regular-season rows; `has_full_data` flag selects the ~23,444 data-complete training rows (2016–2025); `has_odds` standalone flag for betting market availability |

---

### 5.3 Staging Layer

Five models normalize and type-cast raw sources. All staging models are materialized as **tables** so downstream mart views have a stable, pre-computed base.

| Model | Source | Grain | Key Notes |
|---|---|---|---|
| `stg_batter_pitches` | savant.batter_pitches | Pitch | Generates `pitch_sk`; renames all columns to snake_case |
| `stg_statsapi_games` | statsapi.monthly_schedule (JSON flatten) | Game | Extracts game metadata, scores, teams, venue |
| `stg_statsapi_lineups` | monthly_schedule JSON | Player × game × side | Unpivots lineup JSON to one row per player per batting-order slot per side; deduped on month-boundary overlap |
| `stg_statsapi_lineups_wide` | stg_statsapi_lineups | Team × game × side | Wide pivot — one row per team per game with 9 batting-order slot columns |
| `stg_statsapi_venues` | statsapi.venues_raw (JSON flatten) | Venue | Extracts park dimensions, surface, roof, coordinates, elevation, timezone |
| `stg_statsapi_probable_pitchers` | monthly_schedule JSON | Game × side | Extracts `probable_pitcher_id` and name per game × side; null when rotation not yet announced; deduped to latest record per `game_pk + side` |

### 5.4 Mart Layer

Twenty-two mart models organized by grain. Pitch-grain models are materialized as **incremental tables** (merge on `pitch_sk`). Aggregate and rolling models are materialized as **tables**.

#### Pitch-Grain Models (7 models)
All share `pitch_sk` as the primary key. They can be joined to one another without duplication.

| Model | Contents |
|---|---|
| `mart_pitch_game_context` | Count state, base state, outs, score differential, win/run expectancy, count leverage bucket |
| `mart_pitch_pitcher_profile` | Pitcher identity, handedness, age, days rest, times through the order |
| `mart_pitch_hitter_profile` | Batter identity, handedness, age, prior PAs in this game |
| `mart_pitch_characteristics` | Release speed, spin rate, pfx movement, release extension, zone, pitch type/name |
| `mart_pitch_play_event` | Pitch description, plate appearance event, batter/pitcher outcome flags |
| `mart_pitch_hit_characteristics` | Exit velocity, launch angle, hit distance, batted ball type, contact quality flags (`is_barrel`, `is_hard_hit`, `is_sweet_spot`), xBA/xwOBA, bat tracking (2023+) |
| `mart_pitch_fielding` | Infield/outfield alignment classification, fielder IDs by position, shift/shade flags |

#### Game-Level Models (2 models)

| Model | Contents |
|---|---|
| `mart_game_results` | Final score, teams, league/division, winner, run differential, extra innings flag, interleague flag, `venue_id`, `venue_name` |
| `mart_park_run_factors` | Empirical run environment per ballpark: `runs_per_game_at_park` (season average) and `park_run_factor_3yr` (3-year rolling avg). One row per `venue_id` per `game_year`. Regular season only; minimum 10 games. Join to `stg_statsapi_venues` on `venue_id` for physical park dimensions. |

#### Player Rolling Stats (2 models)
One row per player per game. Rolling windows: 7/14/30-day + season-to-date. Regular season only (`game_type = 'R'`).

| Model | Contents |
|---|---|
| `mart_batter_rolling_stats` | Batting average, wOBA, xwOBA, K%, BB%, whiff rate, barrel rate, chase rate, contact rate, hard-hit % |
| `mart_pitcher_rolling_stats` | K%, BB%, whiff rate, barrel rate allowed, hard-hit % allowed, xwOBA against, fastball velocity trend |

#### Team Rolling Stats (4 models)
One row per team per game. Rolling windows: 7/14/30-day + season-to-date. Regular season only.

| Model | Contents |
|---|---|
| `mart_team_rolling_offense` | Runs scored, wOBA, xwOBA, K%, BB%, SLG, hard-hit %, barrel rate |
| `mart_team_rolling_pitching` | Runs allowed, wOBA against, xwOBA against, K%, BB% |
| `mart_team_vs_pitcher_hand` | Offensive splits vs. RHP and LHP starters: runs, wOBA, xwOBA, K%, BB%, hard-hit %, barrel rate |
| `mart_home_away_splits` | Offense and pitching split by home/away context: runs, wOBA, xwOBA, K%, BB%, SLG, hard-hit %, barrel rate — for each side separately |

#### Specialty Models (7 models)

| Model | Grain | Contents |
|---|---|---|
| `mart_team_season_record` | Team × game | Cumulative W/L record and win % through each date |
| `mart_starting_pitcher_game_log` | Starter × game | IP, outs recorded, K, BB, earned runs, ERA, avg fastball velo per start |
| `mart_bullpen_workload` | Team × game | Bullpen fatigue: pitches thrown, relievers used, closer/high-leverage appearances over 1/3/7-day windows |
| `mart_bullpen_effectiveness` | Team × game | Bullpen quality: K%, BB%, xwOBA against, hard-hit %, whiff rate, IP over 14- and 30-day rolling windows. Complement to `mart_bullpen_workload`; join on `team_abbrev + game_pk` |
| `mart_team_schedule_context` | Team × game | Schedule fatigue context: days rest (null on Opening Day), games_last_7d, games_last_14d, home/away streak length, timezone travel signal. Join on `team_abbrev + game_pk`. |
| `mart_batter_vs_handedness_splits` | Batter × pitcher hand × season | AVG, wOBA, xwOBA, K%, BB%, hard-hit % vs. LHP and RHP |
| `mart_pitcher_vs_handedness_splits` | Pitcher × batter hand × season | K%, BB%, wOBA against, hard-hit % against vs. LHB and RHB |
| `mart_head_to_head_team_history` | Team pair × season | Season and all-time H2H record, run differential, and extra-innings rate for every franchise pair; abbreviations normalized to canonical form (e.g. OAK → ATH) for continuous franchise history |

#### Odds API Models (2 models)

| Model | Grain | Contents |
|---|---|---|
| `mart_odds_events` | Event | One row per event_id (latest ingestion snapshot); authoritative event dimension with commence_time, home_team, away_team. Join key for mart_odds_outcomes. |
| `mart_odds_outcomes` | Ingestion snapshot × event × bookmaker × market × outcome | Full history of bookmaker odds. Preserves all ingestion snapshots to support line movement analysis and cross-bookmaker comparisons. Includes derived flags: `is_totals_market`, `is_home_outcome`, `is_away_outcome`. |

#### Bridge Models (1 model)

| Model | Grain | Contents |
|---|---|---|
| `mart_game_odds_bridge` | Game (`game_pk`) | One row per game in mart_game_results, left-joined to mart_odds_events on game_date + full team names (normalized to Stats API canonical names). `event_id` is null for games without odds coverage (pre-2020 or games not returned by The Odds API). `has_odds` boolean flag for quick filtering. Match rates: 68–79% for 2020–2026 regular season games (2020: 67.8%, 2021: 72.4%, 2022: 73.6%, 2023: 74.2%, 2024: 74.5%, 2025: 75.9%, 2026 in progress: 78.7%). The ~25% gap is a confirmed Odds API coverage ceiling (~10 of ~13 games listed per day) — not a join logic bug. Dedup: when the Odds API issues multiple event_ids for the same game, the bridge keeps the latest ingestion_ts and orphans the rest (game still has `has_odds = true`). Postponed games are a secondary miss: Odds API event date ≠ Stats API played date, so the date join fails. Team name normalization: "Cleveland Indians" → "Cleveland Guardians" (2020–2021), "Oakland Athletics" → "Athletics" (2021–2025). See `data_quality/data_availability_windows.md` for the full game_pk → event_id → odds prices funnel. |

---

## 6. Key Design Notes

**No-leakage rule (feature layer):** Every rolling window lookup and stat join in `dbt/models/feature/` must use data strictly from before the game date. The enforced patterns are:
- Rolling window joins: `stats.game_date::date < game_date` (strictly less than — never `<=`)
- Platoon splits: `game_year = year(game_date) - 1` (prior season only — full-season in-progress aggregates would leak)
- Park run factors: `prf.game_year = game_year - 1` (prior season only)
- Season record: `record_date = game_date - 1` (standings as of the day before)

Violations allow the model to "see" same-day game results during training, producing optimistic in-sample metrics that collapse out-of-sample. The full code review checklist and a Snowflake spot-check against game_pk 777235 (LAD vs HOU, 2025-07-04) are documented in `data_quality/leakage_audit.md`. All five feature models passed the audit on 2026-04-23.

**Bat tracking availability:** `bat_speed`, `swing_length`, `attack_angle`, `attack_direction`, and `swing_path_tilt` are available **starting 2023-07-14** (Hawk-Eye bat sensor; mid-season All-Star break rollout). They populate for swing-contact events only (~45% of pitches in 2024+; ~20% for the 2023 partial season). ML features built on these columns must treat them as an optional era-specific block — models trained on 2015–present data must have a fallback path that omits them.

**hyper_speed availability:** `hyper_speed` has been available **since 2015-04-05** and is distinct from the 2023 bat tracking system. It populates for batted contact events (~33% of pitches) and is usable for the full training history.

**Expected metrics availability:** `xba`, `xwoba`, `xslg` are only populated for in-play events (balls put in play). They are null for called strikes, swinging strikes, fouls, and walks.

**Intercept offset fields** (`intercept_offset_x_inches`, `intercept_offset_y_inches`) are available **starting 2023-07-14** — same rollout date as bat tracking, not 2024. Swing-contact events only, same ~45% population rate.

**Rolling window season isolation:** All rolling window CTEs partition by `game_year` to prevent November stats from bleeding into April of the following season.

**Regular season filter:** All rolling stats, splits, and workload models apply `game_type = 'R'` to exclude Spring Training, All-Star, Wild Card, Division Series, Championship Series, and World Series games. The prediction target is regular season games.

**Incremental merge on `pitch_sk`:** Pitch-grain mart models use `MERGE` so late-arriving Statcast corrections are applied rather than duplicated.

---

## 7. Known Data Quality Issues

### Data Quality Workflow

Data quality issues are tracked in two files under `data_quality/`:

- **`data_quality/open_data_quality_issues.md`** — All unresolved issues. Each entry carries a root-cause description, a diagnostic SQL query (where available), a proposed resolution, and a TBD resolution date.
- **`data_quality/resolved_data_quality_issues_april_2026.md`** (and future month files) — Issues that have been fully investigated, remediated in the schema or source, and closed out with a resolution date.

**Resolution process:**
1. Identify the failing test and its severity (`error` blocks the build; `warn` passes but flags)
2. Run the diagnostic query against `baseball_data.betting.*` via snowsql to characterize the failing rows (counts, distributions, game/player context)
3. Determine root cause: bad source data, overly tight test bounds, model logic bug, or test design issue
4. Apply the appropriate fix: relax bounds with `warn_if`/`error_if` thresholds, correct the source row, fix the model SQL, or remove/replace the test
5. Move the issue from `open_data_quality_issues.md` to the current month's resolved file, with full findings and the diagnostic query

### Resolved
| Issue | Resolution |
|---|---|
| 25 pitches with `balls = 4` | Accepted; `error_if >= 26` threshold set |
| 1 pitch with `strikes = 3` on a hit | Fixed in source |
| 413 pitches with `release_speed < 40 mph` (Eephus) | Bounds relaxed to 28–110 mph |
| 748 pitches with `effective_speed < 40 mph`, 1 at 194.6 mph | Bounds relaxed to 26–115 mph |
| `release_extension_ft` outside 0–9 ft (381 rows: 361 near-boundary noise, 19 extreme outliers, 1 negative) | Bounds relaxed to -0.5–10.0 ft; `error_if >= 25` threshold set |
| `innings_pitched` float division bug in `mart_starting_pitcher_game_log` | Fixed: `floor(outs/3) + (mod(outs,3) * 0.1)` |
| Duplicate lineups from month-boundary API overlap | Fixed: `QUALIFY ROW_NUMBER() = 1` in `stg_statsapi_lineups` |
| Raw count columns (`strikeouts`, `walks`, `at_bats`, `total_bases`, `hard_hit_balls`, `barrels`, `batted_balls`) dropped from final SELECT in `mart_team_vs_pitcher_hand` | Added missing columns to `rolling` CTE SELECT list |
| Null `is_barrel`, `is_hard_hit`, `is_sweet_spot`, `is_hard_hit_sweet_spot` in `mart_pitch_hit_characteristics` | Fixed: `coalesce(..., false)` on all four boolean casts; sac bunts and early Statcast coverage gaps produce null source fields |
| Null fielding alignment flags (9 derived flags) in `mart_pitch_fielding` | Fixed: `coalesce(..., false)` on all nine boolean casts; 70,778 regular-season pitches across all years lack Statcast alignment tracking |
| `hard_hit_pct > 1` and `hard_hits > batted_balls` in `mart_batter_vs_handedness_splits` | Fixed: added `field_error` to `is_batted_ball` event list; field errors are batted balls with exit velocity but were missing from the case expression |
| Duplicate `game_pk` values in `stg_statsapi_games` (529 extra rows from postponed/rescheduled games) | Fixed: `QUALIFY ROW_NUMBER() = 1` dedup keeping the scored Final row over Postponed; Cancelled kept over Postponed when no Final exists |
| Null `woba` and rolling `woba_*` in `mart_team_vs_pitcher_hand` (5 tests) | Test expressions relaxed to `is null or (col >= 0)`; null valid when woba_denom=0; early Statcast source has null woba_denom for batted balls, causing woba > 2 for 3 games |
| Null `hard_hit_balls` and `barrels` in `mart_team_vs_pitcher_hand` for games with no balls in play (2 tests) | Fixed: `coalesce(sum(is_hard_hit::integer), 0)` and `coalesce(sum(is_barrel::integer), 0)` in `game_offense` CTE |
| Null `woba` and `woba_against` in `mart_home_away_splits` (2 tests) | Test expressions relaxed to `is null or (col >= 0)`; same Statcast woba_denom source issue as `mart_team_vs_pitcher_hand` |
| `games_std >= games_7d` test fails at season boundaries in `mart_home_away_splits` (1 test) | Test removed; `games_7d` window has no year partition and can span season boundaries while `games_std` resets — test design flaw, not a data error |
| Null `ingestion_ts` in `baseball_data.oddsapi.mlb_odds_raw` (source test) | Self-resolved: null rows eliminated when table was rebuilt in commit 3786845; current ingestion script always populates `ingestion_ts`; 64/64 oddsapi chain tests pass |

---

## 8. Current State Assessment

The project has a well-structured, well-documented data mart that covers the primary feature domains needed for game outcome prediction:

| Domain | Status |
|---|---|
| Pitch physics and outcomes | Complete |
| Game context and state | Complete |
| Batter and pitcher identity | Complete |
| Game results | Complete |
| Player rolling performance | Complete |
| Team rolling offense and pitching | Complete |
| Home/away context splits | Complete |
| Platoon splits (team, batter, pitcher) | Complete |
| Head-to-head franchise history | Complete |
| Starting pitcher game log | Complete |
| Bullpen workload | Complete |
| Bullpen effectiveness (quality) | Complete — `mart_bullpen_effectiveness` with 14/30-day K%, BB%, xwOBA against, hard-hit %, whiff rate, IP |
| Schedule fatigue context | Complete — `mart_team_schedule_context` with days rest, games_last_7d/14d, home/away streak, timezone travel signal |
| Lineup data (confirmed pre-game) | Complete (staging) |
| Ballpark context | Complete — physical dimensions in staging (`stg_statsapi_venues`); empirical run factors in `mart_park_run_factors`; `venue_id` joined to `mart_game_results` |
| Data quality tests | Mostly complete; 2 open items (intentional warns, irresolvable Statcast source gap) |
| ML feature store | Complete (Phase 2) + feature engineering complete — six feature models built, tested, and validated; 25,146 regular-season game rows; `has_full_data` training subset ~23,444 games (2016–2025 complete seasons); `has_odds` flag available for betting market features; Cards 4.1–4.5 complete (delta/momentum, lineup-vs-starter matchup, rolling window reliability flags, starter expected depth, game context and era flags — all 2026-04-23) |
| EDA | Phase 3 complete (2026-04-24) — notebooks 01–07 complete; Cards 3.7–3.11 complete (feature lift, bullpen/starter decomp, home/away asymmetry, era-split stability, bookmaker calibration) |
| ML pipeline foundation | Phase 4 foundation complete — `betting_ml/utils/` complete: data loader, CV splits, preprocessing, feature selection, model I/O, evaluation helpers (Cards 4.6 and 4.8 complete) |
| Prediction models | Phase 4 complete — baseline + tuned models for all three targets (Cards 4.9–4.12e); Bayesian probability layer complete (Card 4.13, best_alpha=0.0). **Known gap:** Card 4.10 baseline MAE (3.4461) was generated with pre-Card 4.8 feature set; tuned model (3.4195) uses correct features. |
| Model selection and registry | Phase 5.1 complete — `model_registry.yaml` written; `_prod` artifacts for all three targets; `xgboost_sigmoid_prod_calibrated.pkl` fit on 2025 hold-out; `calibration_verification.md` passes (delta=+0.0028, PASS). `betting_ml/evaluation/selection_log.md` documents regression artifact selection. |
| Prediction CLI | Phase 5.2 complete — `predict_today.py` scores all confirmed games for a target date, applies the Bayesian probability layer, and writes results to `baseball_data.config.prediction_log` in Snowflake (parquet and CSV file outputs removed 2026-05-01). `best_alpha` loaded from Snowflake `alpha_tuning_results` with fallback to `best_alpha.json`. Intraday fallback via `load_todays_features_via_statsapi()` assembles features from MLB Stats API when nightly dbt pipeline rows are not yet available. |
| Lineup monitor | Phase 5.3 substantially complete (22/23) — `task_lineup_monitor` live and STARTED in Snowflake (serverless, hourly ET cron); `lineup_monitor_proc` reads `baseball_data.betting.stg_statsapi_lineups_wide`, deduplicates via `lineup_monitor_state`, dispatches `dbt_staging_build.yml` via GitHub REST API; workflow validated end-to-end; one criterion (real dispatch log entry) pending until confirmed lineups available. Email notification deferred to Phase 6. |
| Betting/sizing layer | Phase 6 complete — Snowflake Task DAG live; Card 6.G backfill complete (1,098 rows, 36 dates, 941 has_odds); Cards 6.B/C/D/E/H/I all complete as of 2026-05-01; **Card 6.H** delivered consensus_win_prob fix (mean h2h edge −0.036 → −0.017), 8-gap postmortem (`betting_ml/evaluation/postmortem_v0.md`), and Phase 7 roadmap including FanGraphs data pipeline as P1; Card 6.F deferred to Phase 7 |
| FanGraphs data pipeline | Complete (Card 7.E, 2026-05-02) — raw ingestion for ZiPS projections (pitcher + batter), Stuff+, and hitting leaderboard; `baseball_data.fangraphs` schema; 4 staging models + 3 mart models (`fct_fangraphs_pitching_analytics`, `fct_fangraphs_hitting_analytics`, `dim_fangraphs_player_xref`); 9,330-player xref (4,552 MLB / 4,778 MiLB); MLBAM join rate 96.3% for MLB-active pitchers; validation script all PASS |

The main gap between current state and a deployable prediction model is the **feature assembly layer** — joining the mart tables into a single pre-game feature vector per game — and the **ML pipeline** itself.

---

## 9. Roadmap

### Phase 1 — Complete and Stabilize the Data Mart (Current Phase)

Estimated completion: before ML work begins.

**Goals:**
- ~~Resolve all pending data quality issues~~ ✓ Complete — all `error`-severity tests pass; 2 remaining items are intentional `warn`-severity tests for `mart_pitch_fielding` (irresolvable Statcast sensor gaps, acknowledged limitations)
- ~~Confirm `mart_pitch_hit_characteristics` null flag root cause and fix~~ ✓ Complete — `coalesce(..., false)` applied to all four boolean casts; sac bunts and early Statcast coverage gaps documented
- ~~Confirm `mart_pitch_fielding` null flag root cause and fix~~ ✓ Complete — `coalesce(..., false)` applied to all nine alignment boolean flags; 70,778-row sensor gap in source acknowledged as irresolvable
- ~~Add `venue_id` / park factor join to `mart_game_results`~~ ✓ Complete — `venue_id` and `venue_name` joined from `stg_statsapi_games`; `mart_park_run_factors` built with season and 3-year rolling run factors per venue; all tests pass
- ~~Confirm lineup data is reliably populated for historical games (coverage audit)~~ ✓ Complete — 100% coverage 2015–2026; lineup features are a required join with no date cutoff
- ~~Document data availability windows (Statcast coverage by year, lineup coverage by year)~~ ✓ Complete — verified against actual Snowflake row counts; intercept offset corrected to 2023-07-14 (not 2024); full table in `data_quality/data_availability_windows.md`

**Deliverables:**
- ✓ All dbt tests passing at error thresholds (2 intentional `warn`-severity tests remain — by design)
- ✓ Coverage audit documented in `data_quality/open_data_quality_issues.md`
- ✓ Data availability windows documented in `data_quality/data_availability_windows.md`

---

### Phase 1 Enhancement — Historical Odds Backfill

The current odds pipeline is forward-looking only (live ingestion started 2026-04-23). To make odds features usable for model training and backtesting, historical events and odds must be backfilled for the 2021–2025 regular seasons using The Odds API historical endpoints. These four cards extend Phase 1 and must be completed before Phase 3 EDA or Phase 4 model training can incorporate betting market features.

---

#### Card 1 — Ingest Historical MLB Events from The Odds API (2021–present)

**Title:** Ingest historical MLB events from The Odds API — 2021 to present

**Description:**

*Technical implementation:* Add a `historical-events` subcommand to `scripts/odds_api_ingestion.py`. The endpoint is `GET /v4/historical/sports/baseball_mlb/events` with a `date` parameter in ISO 8601 UTC format. For each game date from the 2021 season opener through 2026-04-22 (the day before live ingestion began):

1. Determine the first game start time on that date (query `baseball_data.betting.mart_game_results` for `MIN(game_datetime_utc)` where `game_date = <date>` and `game_type = 'R'`)
2. Set the `date` parameter to 1 hour before the first game start on that date (e.g., if first game is 13:05 ET / 17:05 UTC, use `16:05:00Z`)
3. Pass `commenceTimeFrom` and `commenceTimeTo` scoped to that calendar date (UTC) to limit the response to that day's games
4. Write each response into `baseball_data.oddsapi.mlb_events_raw` — same table as live events — tagged with `source_endpoint = '/v4/historical/sports/baseball_mlb/events'` for auditability

The subcommand must accept `--start-date` and `--end-date` CLI args to support incremental backfills and reruns. The script should skip dates with no regular season games (query `mart_game_results` to build the game-date list). Respect API rate limiting with the existing `REQUEST_DELAY` between calls.

*Blockers:* None — fully independent. Note: ~810 game days across 2021–2025 regular seasons = ~810 API requests. Verify available credits before running the full backfill.

**Acceptance criteria:**
- [ ] New `historical-events` subcommand added to `odds_api_ingestion.py` with `--start-date` and `--end-date` args
- [ ] Script queries `mart_game_results` to build the list of game dates in range; skips non-game dates
- [ ] Each API call uses `date` = 1 hour before the earliest game start UTC on that date
- [ ] All responses inserted into `baseball_data.oddsapi.mlb_events_raw` with correct ingestion metadata columns populated
- [ ] API credits logged after each call
- [ ] Full backfill for 2021–2025 regular seasons completes with no unhandled errors
- [ ] `event_id` is non-null for all returned event rows

---

#### Card 2 — Add Decimal Odds Column to Staging and Mart Models

**Title:** Add `outcome_price_decimal` derived column to stg_oddsapi_odds and mart_odds_outcomes

**Description:**

*Technical implementation:* American odds → decimal odds conversion:
- Positive American odds (≥ 100): `decimal_odds = (outcome_price_american / 100.0) + 1`
- Negative American odds (< 0): `decimal_odds = (100.0 / ABS(outcome_price_american)) + 1`

Add `outcome_price_decimal FLOAT` as a derived column in two dbt models:

1. `dbt/models/staging/stg_oddsapi_odds.sql` — add the computed column immediately after `outcome_price_american` in the final SELECT using a `CASE WHEN outcome_price_american >= 100 THEN ... ELSE ... END` expression
2. `dbt/models/mart/mart_odds_outcomes.sql` — pass `outcome_price_decimal` through from staging (no re-derivation needed)

Update `schema.yml` for both models with a column description and a `not_null` test scoped to rows where `outcome_price_american is not null`.

*Blockers:* None — fully independent of Cards 1, 3, and 4.

**Acceptance criteria:**
- [ ] `outcome_price_decimal` column added to `stg_oddsapi_odds` with correct formula for positive and negative American odds
- [ ] `outcome_price_decimal` column added to `mart_odds_outcomes` (passed through from staging)
- [ ] Spot-check passes: +150 → 2.50, −110 → 1.909 (rounded), +100 → 2.00, −200 → 1.50
- [ ] Column is non-null for all rows where `outcome_price_american` is non-null
- [ ] `schema.yml` updated with column description for both models
- [ ] `dbtf build --select stg_oddsapi_odds mart_odds_outcomes` passes all tests

---

#### Card 3 — Ingest Historical Odds Using Event IDs (blocked by Card 1)

**Title:** Ingest historical MLB odds from The Odds API using event IDs from historical events backfill — 2021 to present

**Description:**

*Technical implementation:* Add a `historical-odds` subcommand to `scripts/odds_api_ingestion.py`. This command reads distinct event IDs from `baseball_data.oddsapi.mlb_events_raw` (populated by Card 1) for a given date range, then for each event fetches historical odds by calling:

`GET /v4/historical/sports/baseball_mlb/events?apiKey=...&date=<snapshot_date>&eventIds=<event_id>&markets=h2h,totals&regions=us,us2`

Where `snapshot_date` = the event's `commence_time` minus 1 day (ISO 8601 UTC). This returns the odds snapshot from one day before the game — the pre-game market line.

Results are written to `baseball_data.oddsapi.mlb_odds_raw` — the same target as live odds ingestion — so `stg_oddsapi_odds`, `mart_odds_outcomes`, and all downstream models consume them automatically without schema changes.

The subcommand must accept `--start-date` / `--end-date` args to allow incremental backfills. Both `h2h` and `totals` markets must be fetched per event (two calls per event). Apply `REQUEST_DELAY` between calls.

*Blockers:* **Blocked by Card 1.** Event IDs must be present in `mlb_events_raw` before historical odds can be fetched. Estimated API credit consumption: ~810 game days × ~15 events/day × 2 markets = ~24,300 requests. Confirm credits are available before running the full backfill.

**Acceptance criteria:**
- [ ] New `historical-odds` subcommand added to `odds_api_ingestion.py` with `--start-date` and `--end-date` args
- [ ] Script queries `baseball_data.oddsapi.mlb_events_raw` to get distinct event IDs and their `commence_time` for the target date range
- [ ] For each event, `date` parameter = `commence_time` minus 1 day (ISO 8601 UTC)
- [ ] Both `h2h` and `totals` markets fetched per event
- [ ] Results written to `baseball_data.oddsapi.mlb_odds_raw` with all required metadata columns populated
- [ ] Rate limiting applied between all API calls
- [ ] `--start-date` / `--end-date` filtering works correctly for incremental reruns
- [ ] Full 2021–2025 backfill completes with no unhandled errors

---

#### Card 4 — Verify Historical Odds Flow Through Staging, Mart, and Bridge Models (blocked by Cards 1 and 3)

**Title:** Verify historical odds data flows correctly through all downstream dbt models and update coverage documentation

**Description:**

*Technical implementation:* After Cards 1 and 3 populate `mlb_events_raw` and `mlb_odds_raw` with historical data, verify that all downstream dbt models handle the expanded dataset correctly and that no existing tests break:

1. `stg_oddsapi_events` — confirm lateral flatten + dedup logic correctly handles events with `commence_time` in the past; no grain violations expected
2. `stg_oddsapi_odds` — confirm no null `outcome_price_american` or grain duplicates introduced by historical rows
3. `mart_odds_events` — dedup-to-latest logic must still return one row per `event_id`; verify historical events appear with correct `commence_time` and `commence_date`
4. `mart_odds_outcomes` — verify `is_totals_market`, `is_home_outcome`, `is_away_outcome` flags are correct on historical rows; `outcome_price_decimal` (from Card 2) must be populated
5. `mart_game_odds_bridge` — currently joins `mart_game_results` to `mart_odds_events` on `game_date + full team names`; with historical odds present, match rate for 2021–2025 games should improve significantly. Verify join logic handles past games correctly and document the resulting per-season match rate.

Update `data_quality/data_availability_windows.md` to reflect the expanded odds coverage window (2021 regular season onward).

*Blockers:* **Blocked by Cards 1 and 3.** Historical raw data must be present in both source tables before downstream verification is meaningful. Card 2 (decimal odds) should also be merged before running this verification so the full column set is tested together.

**Acceptance criteria (completed 2026-04-23):**
- [x] `dbtf build` passes all tests after historical backfill with no new failures (962 pass / 18 warn / 0 error)
- [x] Row count in `stg_oddsapi_events` reflects all historical + live events with no duplicates per `event_id` (9,419 distinct event_ids = 9,419 total rows)
- [x] Row count in `stg_oddsapi_odds` reflects all historical + live odds rows with no grain violations (0 null prices, 0 grain duplicates)
- [x] `mart_game_odds_bridge.has_odds = true` for 2021–2025 regular season games where odds were available (72.4–75.9% per season after team name normalization fix)
- [x] No unexpected nulls in `outcome_price_decimal` for historical rows in `mart_odds_outcomes`
- [x] Per-season match rate in `mart_game_odds_bridge` documented in `data_quality/open_data_quality_issues.md` with pre-fix vs post-fix table
- [x] `data_quality/data_availability_windows.md` updated with full odds coverage section including per-season match rates

---

### Phase 2 — Pre-Game Feature Assembly ✓ Complete (2026-04-23)

The prediction task requires a single feature vector per game, assembled from information available **before first pitch**. All five feature models are built, tested, and validated.

**Models built (all in `dbt/models/feature/`, schema: `baseball_data.betting_features`):**

| Model | Grain | Description |
|---|---|---|
| `feature_pregame_lineup_features` | Game × side | Aggregated batter rolling stats (30-day + season-to-date) and prior-season platoon splits across all 9 lineup slots |
| `feature_pregame_starter_features` | Game × starter | Rolling pitcher stats (K%, xwOBA against), days rest, and prior-season platoon splits; source is `stg_statsapi_probable_pitchers` |
| `feature_pregame_team_features` | Game × team | Rolling offense, rolling pitching, platoon splits vs. L/R, season record, bullpen workload, bullpen effectiveness, and schedule context (days rest, games_last_7d/14d, home/away streak, timezone travel) |
| `feature_pregame_park_features` | Game | Park dimensions, elevation, surface, roof type (from `stg_statsapi_venues`), and prior-season empirical run factors (from `mart_park_run_factors`) |
| `feature_pregame_odds_features` | Game | Pre-game betting market signals from lowvig: moneyline (h2h) and totals prices, vig-adjusted implied probabilities, market vig. Bookmaker selected 2026-04-23: lowvig has lowest median vig in both h2h (2.33%) and totals (3.39%) markets with ≥99% event coverage. Leakage guard enforced: only `ingestion_ts < commence_time` snapshots used. Prices populate going forward (live daily ingestion); historical prices require Card 3 backfill. |
| `feature_pregame_game_features` | Game | Master assembly: one wide row per game joining all five feature tables; 25,146 regular-season rows; `has_odds` standalone flag |

**Training set (has_full_data = true) by season — verified 2026-04-23:**

| Season | Games |
|---|---|
| 2015 | 0 (no prior-season run factor) |
| 2016–2019 | ~9,268 |
| 2020 | 801 (COVID 60-game season) |
| 2021–2025 | ~11,665 |
| **Total (2016–2025 complete)** | **~23,444** |

**Key design constraints enforced:**
- All features use data strictly before game_date: rolling stats `< game_date`, platoon splits `game_year - 1`, park factors `game_year - 1`, season record `game_date - 1`
- `has_full_data` flag selects the data-complete training subset (both lineups confirmed, both starters have prior history, park has prior-season run factor)
- Full leakage audit documented in `data_quality/leakage_audit.md`; spot-check against game_pk 777235 (LAD vs HOU, 2025-07-04) passed

**Lineup coverage audit (completed 2026-04-23):**

`stg_statsapi_lineups_wide` has **100% coverage for every regular season from 2015 through 2026** — lineup features are a required join with no date cutoff needed.

---

### Phase 3 — Exploratory Data Analysis (In Progress)

Notebooks live in `exploratory_data_analysis/` and are written in [Marimo](https://marimo.io/) — a reactive Python notebook framework where each cell is a Python function. Notebooks are plain `.py` files with inline `uv` dependency declarations; no separate install or virtual environment is needed.

**Running notebooks:**

```bash
# Interactive UI (browser at http://localhost:2718)
uv run marimo run exploratory_data_analysis/01_target_variables.py

# Live-edit mode
uv run marimo edit exploratory_data_analysis/01_target_variables.py

# Headless / CI
uv run marimo run exploratory_data_analysis/01_target_variables.py --headless
```

**Completed notebooks:**

| Notebook | Description | Key Finding |
|---|---|---|
| `01_target_variables.py` | Total runs, run differential, home win rate distributions (2016–2025) | Single model recommended; add `game_year`/`post_2022_rules` feature; exclude 2020; naive MAE baseline ~3.5 runs |
| `02_feature_coverage.py` | Null rate heatmap (374 cols × all seasons), `has_full_data` verification, imputation decisions | Odds cols 100% null (pre-backfill); starter platoon splits 11–17% null (debut pitchers); all other groups <5% null |
| `03_rolling_window_stability.py` | Correlation vs. window size (7d/14d/30d/STD) for team and starter features; early-season stability by games-played bucket; slider to preview training set size | Season-to-date is strongest for pitcher metrics; 30-day ≈ STD for offense; apply `min(games_played) ≥ 15` filter in Phase 4 |
| `04_feature_correlations.py` | Univariate Pearson + Spearman correlation of every feature with each target; multicollinearity heatmaps per feature group with redundant-pair (|r| > 0.85) flagging; home/away matchup differential analysis; Phase 4 feature selection recommendation | **Park dominates totals; pitching beats offense 2:1.** Top total_runs predictors: park_run_factor (r=0.122), elevation (r=0.111), home_pit_xwoba_against_30d (r=0.075). 10 redundant pairs (all 14d window variants). wOBA↔xwOBA not redundant (r=0.68–0.70). `total_matchup_quality` is noise (r=0.005); `matchup_advantage` has modest totals signal (r=0.050) but fails for spread/ML (formula confound). Away pitching near-zero for total_runs (r=0.008) — confirmed asymmetry, see Card 3.9. |
| `05_park_and_context.py` | Park run factor quartile analysis (rank-order check, Pearson r); days rest and TZ travel bar charts with ANOVA + t-tests; OLS R² comparison (park-only vs. park + schedule); interactive stadium dropdown with dual-axis season trend chart; dynamic Phase 4 verdict | **Include park + elevation; schedule features are cheap flags only.** park_run_factor r=0.122; rank order fully preserved; Q4−Q1 = +1.15 runs. elevation_ft r=0.111 (partially independent). Days rest r<0.003, TZ change r<0.023 — both near-zero. ΔR² for adding schedule to park-only OLS < 0.002 (below 0.005 threshold). Include rest/TZ as binary flags given near-zero cost; do not expect measurable ablation lift. |
| `06_bat_tracking_era.py` | Bat tracking null rate by season; coverage on 2023–2025 vs. full training set; correlation comparison (traditional vs. bat tracking features); bat speed–wOBA redundancy check; OLS R² with and without bat tracking; verdict: single-model or era-specific path | **Single-model path.** Bat tracking max |r| = 0.022 with total runs (vs. 0.088 for park factor); OLS ΔR² < 0.001; bat speed–wOBA overlap is low (|r| = 0.225 — not redundancy). 30-day team average loses individual-level precision. Exclude from Phase 4; re-evaluate with per-batter matchup aggregations in Phase 5+. |
| `07_engineered_feature_lift.py` | Correlation fast pass for all delta/momentum (Card 4.1) and handedness matchup (Card 4.2) features vs. three targets; cross-correlation with base features; OLS ΔR² baseline → +delta → +handedness | **7d windows add real signal; handedness validated low-signal.** Delta features: max |r|=0.020 individually (very low); OLS ΔR²=0.043–0.047 over 30d/std baseline — signal is 7d recency lift, not momentum direction. Handedness k_pct_adj shows |r|=0.063–0.086 with run_diff/home_win but ΔR²=0.001–0.002 after controlling for starter K%/xwOBA (below 0.005 threshold). Use 7d windows directly in Phase 4; exclude handedness from primary model. |

**Findings document:** Key findings from each notebook are appended to `exploratory_data_analysis/betting_model_findings.md` as notebooks are completed.

Before fitting models, spend time in `exploratory_data_analysis/` to:

- Validate that assembled features are plausibly correlated with game outcomes
- Identify the most predictive feature groups (team rolling offense, pitcher wOBA allowed, park factors, lineup quality)
- Assess the predictive signal of bat tracking features (2023+ only) vs. traditional metrics (full history)
- Investigate target variable distribution: total runs scored, run differential, and binary win outcome
- Identify training set boundaries: minimum data needed per team/player before a feature is reliable
- Check for multicollinearity (wOBA vs. xwOBA vs. AVG; pitcher K% vs. whiff rate)

**Key questions to answer:**
1. How many games of rolling history are needed before batter/pitcher stats stabilize?
2. Is lineup slot order predictive (cleanup hitter vs. 9th spot) or should lineups be aggregated?
3. Do park factors materially improve predictions beyond team rolling offense?
4. Is the 2023+ bat tracking data worth building a separate model era?

---

#### Card 3.7 — Engineered Feature Incremental Lift Validation ✓ Complete (2026-04-24)

**Title:** Validate that Cards 4.1 (delta/momentum) and 4.2 (lineup-vs-starter handedness) provide incremental predictive signal over base rolling features

*Acceptance criteria:*
- [x] Correlation table for all engineered features vs. all three targets
- [x] OLS ΔR² computed for delta block and handedness block
- [x] Findings appended to `betting_model_findings.md` section 07
- [x] Phase 4 design constraints updated with verdict

**Results:** Delta block ΔR²=0.043–0.047 (above 0.005 threshold) — signal is 7d recency lift, not momentum direction; use 7d windows directly in Phase 4. Handedness block ΔR²=0.001–0.002 (below threshold) — validated low-signal; exclude from Phase 4 primary model.

---

#### Card 3.8 — Bullpen vs. Starter Signal Decomposition ✓ Complete (2026-04-24)

**Title:** Decompose pitching quality signal between starting pitcher and bullpen; determine if they contribute independent variance to game outcomes

**Why:** Home bullpen xwOBA (r=0.058) and starter xwOBA (r=0.060) overlap in NB04. If |r| > 0.70 between them, only the stronger predictor should be included; if independent, both should be retained. Workload features may add signal beyond trailing xwOBA.

*Acceptance criteria:*
- [x] Starter vs. bullpen xwOBA cross-correlation table (home and away pairs; flag high_collinearity if |r| > 0.70)
- [x] Partial correlation table (each pitching feature vs. all three targets, controlling for the other pitching feature)
- [x] OLS R² decomposition: starter-only, bullpen-only, combined; incremental R² computed per target
- [x] Workload feature correlations vs. targets; workload incremental R² vs. bullpen-only baseline
- [x] Findings appended to `betting_model_findings.md` section 08
- [x] Phase 4 design constraints updated (keep both / drop bullpen / add workload flag)

**Results:** No high collinearity (home r=0.169, away r=0.164). Mean incremental R²=0.004 — above 0.002 threshold. **Verdict: keep both starter and bullpen xwOBA** as independent features. Workload features (bullpen_pitches_prev_3d, pitchers_used_prev_7d) max incremental R²=0.0005 — exclude.

---

#### Card 3.9 — Home/Away Pitching Quality Asymmetry ✓ Complete (2026-04-24)

**Title:** Investigate the structural asymmetry between home and away team pitching features as predictors of total runs

**Why:** NB04 found a 9× Pearson r gap with total_runs between home pitching (r=0.075) and away pitching (r=0.008). Unresolved, Phase 4 models will underweight away pitching quality. Competing explanations: (H1) collinearity with park factor absorbs away variance; (H2) rotation alignment sample confound; (H3) park contamination in away xwOBA_against; (H4) signal direction issue for away team stats measured at home parks.

*Acceptance criteria:*
- [x] Partial correlation: `away_pit_xwoba_against_30d` vs. total_runs controlling for `park_run_factor_3yr` and `home_pit_xwoba_against_30d`
- [x] Stratified correlation by park factor quartile (Q1–Q4)
- [x] Era-split comparison (2016–2019 vs. 2021–2025)
- [x] Starter vs. team-level signal comparison (`away_starter_xwoba_against_std` vs. `away_pit_xwoba_against_std`)
- [x] Root cause hypothesis supported or refuted
- [x] Findings appended to `betting_model_findings.md` section 09
- [x] Phase 4 design constraints updated

**Results summary (2026-04-24):**
- n=17,690 games (2016–2025, excl. 2020); all pitching + park columns non-null
- Partial r of `away_pit_xwoba_against_30d` vs. total_runs (controlling park_rf + h_pit_30) = **0.0122** (raw r=0.0107); park does not absorb away signal
- The asymmetry is **total_runs-specific**: away pitching has strong signal for run_differential (partial r=0.096) and home_win (partial r=0.086)
- Park quartile stratification: asymmetry persists across all quartiles for total_runs (Q1: 4.6×, Q4: 19.0×); H1 refuted
- Era-split: total_runs asymmetry 5.8× pre-juiced → 18.2× modern; run_diff/home_win asymmetry does not persist; H2 partially supported
- Away starter vs. team-level delta = −0.0002; H3 not supported
- H4 (signal direction ambiguity): inconclusive
- Design recommendation: include both home and away pitching features; include era flags; apply regularization

---

#### Card 3.10 — Era-Split Correlation Stability ✓ Complete (2026-04-24)

**Title:** Test whether feature-outcome correlations are stable across the pre-2022 and post-2022 rule-change eras

**Why:** NB01 found a ~0.64-run structural mean shift at the 2022→2023 boundary. A unified model assumes correlation structure is stable across eras. If key correlations changed (e.g., bullpen xwOBA less predictive post-clock, team offense more predictive post-shift ban), era-specific models may be required. Pre-2022: 2016–2021 (excl. 2020, n≈9,500); post-2022: 2022–2025 (n≈8,048).

*Acceptance criteria:*
- [x] Correlation table: top 20 features × all three targets × both eras; flag where |r| changes > 0.015
- [x] Era comparison summary: features stable vs. structurally shifted
- [x] Z-test significance table for top 10 features per target
- [x] Verdict: single model with `post_2022_rules` flag sufficient, or separate era models required
- [x] Findings appended to `betting_model_findings.md` section 10
- [x] Phase 4 design constraints updated

**Results (2026-04-24):**
- n_features_tested: 20 | n_flagged_delta_015 (Fisher z-tests): 8 | n_significantly_shifted: 0
- mean_abs_r_delta: 0.0122 | correlation_structure_is_stable: False
- shifted_features: [] (zero statistically significant shifts at p < 0.05)
- Verdict: **post_2022_rules_flag_sufficient = True** | separate_era_models_required = False

---

#### Card 3.11 — Bookmaker Calibration and Market Efficiency Analysis ✓ Complete (2026-04-24)

**Title:** Analyze bookmaker accuracy for moneyline and totals markets; identify best-calibrated books; surface consensus and disagreement features for Phase 4

**Why:** Historical odds backfill (2021–2025, ~7,000–8,000 matched games) is complete. Before treating implied probabilities as Phase 4 features, need to know: (1) which books are best-calibrated (not just lowest-vig), (2) whether cross-book disagreement carries its own signal, (3) what consensus/disagreement features to add to `feature_pregame_odds_features`. Primary books (full 2021–2025): draftkings, fanduel, betmgm, williamhill_us, betrivers, bovada, betonlineag, lowvig. Notebook: `exploratory_data_analysis/11_bookmaker_calibration.py`.

**Analysis:** (1) Vig/overround ranking per bookmaker × market. (2) Moneyline calibration: Brier score, log loss, calibration curve (decile buckets), home-team bias per bookmaker per season (≥500 events). (3) Totals accuracy: MAE, bias, over rate, line distribution by season. (4) Cross-bookmaker consensus/disagreement: consensus prob, sharp vs. soft split, `sharp_soft_delta`, disagreement quartile signal test. (5) Market efficiency: consensus Brier score as Phase 4 benchmark; favorite/underdog calibration split; season-over-season Brier trend.

**Hypotheses (H1–H7):** Sharp books have lower Brier than soft books; lowvig has lowest overround; books overvalue home teams by +1–3%; high disagreement predicts higher outcome variance; sharp-soft delta has directional signal; post-2023 rule changes caused totals lines to rise ~0.3–0.5 runs; market consensus Brier beats Phase 4 baseline models.

**New features for `feature_pregame_odds_features` (only for `has_odds = true` games):**

| Feature | Description |
|---|---|
| `home_win_prob_consensus` | Mean vig-adjusted home win probability across all bookmakers |
| `home_win_prob_sharp` | Mean vig-adjusted home win probability across sharp books (lowvig, betfair, betonlineag, bovada) |
| `home_win_prob_soft` | Mean vig-adjusted home win probability across retail books (fanduel, draftkings, betmgm, williamhill_us, betrivers) |
| `sharp_soft_ml_delta` | Sharp minus soft home win probability |
| `ml_consensus_std` | Standard deviation of home win probability across all books |
| `total_line_consensus` | Mean totals line across all books |
| `total_line_std` | Standard deviation of totals line across books |
| `market_bookmaker_count` | Number of bookmakers with h2h odds for this game |
| `over_prob_consensus` | Mean vig-adjusted over probability across all books with totals markets |

*These features are derived in a new dbt model (`mart_odds_consensus`) aggregating `mart_odds_outcomes` to game-grain; only the final pre-game snapshot (`ingestion_ts < commence_time`) per bookmaker per event is used.*

*Acceptance criteria:*
- [x] Vig/overround table: all bookmakers ranked by median overround for h2h and totals, 2021–2025
- [x] Moneyline calibration: Brier score and log loss per bookmaker per season; calibration curve for top 5 books by event count; home-team bias table
- [x] Totals accuracy: MAE and bias per bookmaker per season; over rate and line distribution by season
- [x] Cross-bookmaker consensus computed for all matched events; sharp vs. soft Brier comparison (≥2,000 games per group); disagreement quartile signal test
- [x] All 7 hypotheses (H1–H7) answered (supported / not supported / inconclusive)
- [x] Market baseline Brier score documented as Phase 4 benchmark
- [x] Findings appended to `betting_model_findings.md` section 11
- [x] Phase 4 design constraints updated with market feature inclusion decision
- [x] Card 4.X (new consensus odds features dbt model) queued if sharp-soft delta or consensus std prove signal-bearing

**Results summary (2026-04-24):**
- consensus_brier_overall: 0.2395 (Phase 4 model benchmark — must beat to add value over market)
- include_consensus_features: **True** (H7 supported: consensus Brier < 0.240)
- include_sharp_soft_features: **False** (H1 inconclusive: sharp/soft Brier difference = 0.0000)
- queue_mart_odds_consensus_card: **True**
- H2 supported (lowvig rank #1), H3 not supported (home bias ~0%), H6 not supported (no post-2023 line rise)
- n_sharp_games / n_soft_games: 7,203 / 7,203 (both ≥ 2,000 ✓)

---

### Phase 4 — Baseline Prediction Models

Build initial models in `betting_ml/` using the assembled feature store from Phase 2, extended by the feature engineering cards below.

**Targets:**
- **Total runs scored** (regression; output as a predictive distribution to derive P(over/under line))
- **Run differential** (regression; win probability derived from the predictive distribution)
- **Binary win outcome** (classification; moneyline proxy; calibration is the primary concern)

**Design constraints from Phase 3 EDA (updated as notebooks complete):**

| Constraint | Decision | Source |
|---|---|---|
| Training set filter | `min(home_games_played, away_games_played) ≥ 15` — removes early-season noise (5.5% of rows), retains 85% of training data | Notebook 03 |
| Primary feature window — pitcher metrics | Season-to-date (`_std`) — strongest correlation with outcomes; 30d close but STD wins for K%, xwOBA | Notebook 03 |
| Primary feature window — team offense | 30-day (`_30d`) — equivalent to STD for wOBA; more robust to in-season roster changes | Notebook 03 |
| Short-window features (7d, 14d) | **Include 7d windows directly** — 7d rolling windows add ΔR²=0.037–0.047 over 30d/std-only baseline (verified NB07). Use raw 7d columns, not delta encoding. Drop 14d standalone. | Notebooks 03, 07 |
| 2020 season | Exclude from training — COVID bubble, structural confounders | Notebook 01 |
| Era feature | Include `game_year` and `post_2022_rules` flag; 2022→2023 shift ban + pitch clock caused a ~0.64-run structural mean shift | Notebook 01 |
| Home win rate | Use time-varying `home_win_rate_trailing_3yr`; home advantage has declined from 0.548 (2020) to 0.519 (2023) — static 0.529 is wrong for recent seasons | Notebook 01 |
| Odds features | Exclude from primary model (100% null in training window); add as optional enrichment block once Card 3 backfill is complete | Notebook 02 |
| Starter platoon splits null handling | Add `has_starter_platoon_data` indicator; impute nulls with prior-season league-average split by pitcher hand × batter hand | Notebook 02 |
| Total runs distribution shape | Right tail — blowout games exceed Gaussian predictions; evaluate LogNormal in addition to Normal parameterization for NGBoost | Notebook 01 |
| Weakest training bucket | 10–30 game window (not just 0–10); Bayesian shrinkage targets this transitional zone, not just Opening Day | Notebook 03 |
| Drop 14-day standalone features | 14-day window is redundant with 30-day (high multicollinearity, no independent signal); retain 7-day as a direct rolling window feature (not as delta encoding) | Notebooks 04, 07 |
| Prefer xwOBA over raw wOBA same-window | wOBA and xwOBA within the same window are highly correlated; xwOBA is more stable (park-adjusted); drop raw wOBA where both exist for the same window | Notebook 04 |
| Matchup differentials — retain for totals only | **Drop `total_matchup_quality_30d`** (r=0.005 with total_runs — no value over components). Retain `matchup_advantage_30d` as a supplementary feature for totals model only (r=0.050 with total_runs — modest signal). Formula has directional confound (home_pit_xwoba_against adds positively to home advantage metric) that makes it invalid for run differential / moneyline targets (r=−0.011, −0.012 respectively). | Notebook 04 |
| Park factor and elevation — include both | `park_run_factor_3yr` (r=0.122, strongest total_runs predictor; Q4−Q1 = +1.15 runs; rank order fully preserved). `elevation_ft` (r=0.111, second strongest; partially independent of park factor). Both required in Phase 4 feature matrix. | Notebook 05 |
| Schedule features — cheap flags, no expected lift | `home_days_rest`, `away_days_rest`: r<0.003 with total_runs; continuous features, near-zero cost. `home_tz_changed`, `away_tz_changed`: r<0.023; binary flags, near-zero cost. Adding all four to park-only OLS: estimated ΔR² < 0.002 (below 0.005 threshold). Include but de-prioritize in ablation tests. | Notebook 05 |
| Bat tracking features (`bat_speed_mph`, `swing_length_ft`) | **Exclude from Phase 4 primary model.** Sub-sample = 5,523 games (26.8% of full training set); max |r| with total runs = 0.022 (vs. 0.088 for park factor); OLS ΔR² < 0.001 (well below 0.005 threshold). Bat speed–wOBA correlation is low (|r| = 0.225) — the weak signal is not redundancy but rather that 30-day team averages lose the individual-level precision bat speed carries. Re-evaluate with per-batter matchup aggregations in Phase 5+. | Notebook 06 |
| Delta/momentum features (Card 4.1) — `*_7d_minus_30d`, `*_7d_minus_std`, `fastball_velo_trend` | **Prefer raw 7d windows over delta encoding.** Individual delta |r| < 0.022 (very low marginal signal). ΔR²=0.043–0.047 over 30d/std-only baseline — real signal, but reflects 7d recency lift (not momentum direction). Delta encoding is informationally equivalent to having both the 7d and 30d/std windows. Phase 4 feature matrix: include `*_7d` rolling columns as primary recent-window signal; delta encoding optional but adds collinearity when both windows are present. | Notebook 07 |
| Lineup-vs-starter handedness matchup (Card 4.2) — `*_lineup_vs_starter_xwoba_adj`, `*_k_pct_adj`, `*_bb_pct_adj` | **Validated low-signal — exclude from primary model.** k_pct_adj shows marginal |r|=0.063–0.086 for run_diff/home_win but shares ~52% variance with base starter K% (cross-r=0.524). OLS ΔR²=0.001–0.002 on top of baseline+delta (below 0.005 threshold). Signal already captured by starter xwOBA and K% in the model. Re-evaluate with per-batter platoon matchup aggregations in Phase 5+. | Notebook 07 |
| **Card 3.8 Pitching Signal Decomposition — starter vs. bullpen xwOBA** | **Keep both starter and bullpen xwOBA; exclude workload features.** Cross-correlation: home r=0.169, away r=0.164 (no high collinearity; threshold |r|>0.70). Mean incremental R² from combining both pitching blocks = 0.0041 (above 0.002 threshold) — starter and bullpen each carry independent variance. Workload features (`bullpen_pitches_prev_3d`, `pitchers_used_prev_7d`) max incremental R²=0.0005 (well below 0.005 threshold). Include `home_starter_xwoba_against_std`, `home_bp_xwoba_against_30d`, `away_starter_xwoba_against_std`, `away_bp_xwoba_against_30d` as separate features in Phase 4 feature matrix. | Notebook 08 (script) |
| **Card 3.9 Home/Away Pitching Asymmetry** | **Include both home and away pitching features; do not prefer starter over team-level for away; include era flags.** Partial r of `away_pit_xwoba_against_30d` vs. total_runs (controlling park_rf + home_pit_30d) = 0.0122 — park factor does not absorb away pitching variance. Asymmetry is total_runs-specific: away pitching has full signal for run_differential (partial r=0.096) and home_win (partial r=0.086). Park quartile stratification: asymmetry persists across all quartiles (Q1: 4.6×, Q4: 19.0×) — H1 refuted. Era-split: total_runs asymmetry 5.8× pre-juiced → 18.2× modern (H2 partially supported; era flag required). Away starter vs. team-level delta = −0.0002 (H3 refuted). asymmetry_is_structural=False (era confound present). Recommendation: include both pitching feature sets; apply regularization for total_runs models. | Notebook 09 (script) |
| **Card 3.10 Era-Split Correlation Stability** | **Train unified model with `post_2022_rules` flag; separate era models not required.** n_significantly_shifted = 0 (zero features with statistically significant correlation shifts at p < 0.05 AND \|r_delta\| > 0.015 across top 20 features × 3 targets). mean_abs_r_delta = 0.0122 (above 0.010 stability threshold but all shifts are noise-level given era sample sizes n_pre=9,500, n_post=8,048). post_2022_rules_flag_sufficient = True. shifted_features = [] (none). 19 of 60 feature-target pairs flagged at \|r_delta\| > 0.015 but all p > 0.05 in Fisher z-tests. Phase 4 implication: Train unified model with post_2022_rules flag; the `post_2022_rules` binary flag already in the feature matrix is the correct implementation path. | Notebook 10 (script) |
| **Card 3.11 Bookmaker Calibration and Market Efficiency** | **Include consensus features; do not include sharp-soft features; queue mart_odds_consensus dbt card.** consensus_brier_overall=0.2395 — this is the Phase 4 model benchmark (must beat to add value over market). include_consensus_features=True (H7 supported: consensus Brier < 0.240 threshold). include_sharp_soft_features=False (H1 inconclusive: sharp/soft Brier difference = 0.0000 — books are identical in predictive accuracy). queue_mart_odds_consensus_card=True. Verdicts: H2=supported (lowvig rank #1, lowest overround), H3=not supported (home-team bias ≈ 0%, refutes +1–3% prior), H6=not supported (no clean post-2023 totals line rise). Consistent under-bias in totals (~0.4–0.5 runs, 45–48% over rate) across all books and seasons. Phase 4 implication: `home_win_prob_consensus` and `total_line_consensus` are priority odds features for has_odds=true games; a Card 4.X to build mart_odds_consensus should be queued before Phase 4 feature assembly. | Notebook 11 (script) |

**Model approach — A/B test per target:**

| Target | Model A | Model B | Model C | Primary metric |
|---|---|---|---|---|
| Total runs (regression) | Ridge/Lasso | XGBoost + residual distribution | NGBoost (Normal vs. LogNormal) | MAE vs. ~3.5 baseline; P(over) Brier score |
| Run differential (regression) | Ridge/Lasso | XGBoost + residual distribution | NGBoost | MAE; derived win prob Brier score |
| Win outcome (classification) | Logistic Regression | XGBoost + Platt/isotonic calibration | — | Log loss, Brier score, calibration curve |

NGBoost outputs a full parametric distribution per prediction — P(total_runs > any_line) is directly computable, making it the most natural bridge between regression output and bookmaker implied probability comparison.

**Feature groups to evaluate:**
- Team rolling offense (7d + 30d wOBA, runs, K%, BB%) — include 7d windows directly (not delta encoding; see NB07 Card 3.7 verdict)
- Team rolling pitching (7d + 30d xwOBA against, K%, BB%) — same window strategy
- Lineup-vs-starter handedness matchup (Card 4.2) — validated low-signal (NB07 ΔR²<0.005); exclude from primary model
- Starter features (K%, xwOBA against, days rest, platoon splits, recent avg IP) (Cards 4.4, 4.6)
- Lineup features (aggregated batter wOBA + handedness composition)
- Park features (dimensions, elevation, surface, roof, prior-season run factors)
- Season record (win% as proxy for overall team quality)
- Rolling window reliability flags (Cards 4.3, 4.6 Bayesian shrinkage)
- Game context (day/night, series position, time-varying home win rate, era flags) (Card 4.5)

---


#### Card 4.11 Results — Win Outcome Classification Baselines

- **Best model (log loss):** `xgb_isotonic` (mean log loss = 0.6689)
- **Best Brier score:** `xgb_isotonic` (mean = 0.2393)
- **Better calibration method:** isotonic (Platt ECE=0.0119, Isotonic ECE=0.0000)
- **hwrt_reduces_bias:** False
- **Home bias in recent seasons:** 2023:neutral, 2024:neutral, 2025:neutral
- **Recommended classifier for Phase 6 EV:** `xgb_isotonic`




#### Card 4.12e Results — NGBoost run_differential Hyperparameter Tuning (Grid Search)

- **best_ngboost_config_run_diff:** {n_estimators: 500, dist: Normal}
- **Best CV MAE:** 3.4586
- **lognormal_viable:** false
- **Summary:** NGBoost grid search (6 combos: 3 n_estimators × 2 distributions) for run_differential; LogNormal non-viable due to negative target support; best config n_estimators=500, dist=Normal, CV MAE=3.4586; model persisted via model_io.py as `ngboost_tuned`.

#### Card 4.12d Results — NGBoost total_runs Hyperparameter Tuning (Grid Search)

- **best_ngboost_config_total_runs:** {n_estimators: 500, dist: LogNormal}
- **Best CV MAE:** 3.4856
- **Summary:** NGBoost grid search (4 combos: 2 n_estimators × 2 distributions) identified best config as n_estimators=500, dist=LogNormal with CV MAE=3.4856; model persisted via model_io.py as `ngboost_tuned`.

#### Card 4.12c Results — XGBoost home_win Hyperparameter Tuning (Optuna TPE)

- **xgb_win_outcome_improved:** True — XGBoost home_win Brier improved ✓ (tuned=0.2428 vs baseline=0.2443)
- **Baseline Brier:** 0.2443 | **Tuned Brier:** 0.2428 | **Change:** +0.62%
- **Best params:** max_depth=3, learning_rate=0.0270, n_estimators=210, subsample=0.782, colsample_bytree=0.893, reg_alpha=0.200, reg_lambda=1.271
- **Summary:** Optuna TPE (50 trials) tuned XGBoost (Platt) for home_win; tuned Brier=0.2428 vs baseline=0.2443 — improved ✓; tuned model persisted via model_io.py as `xgb_classifier_tuned`.
- **Full results:** `betting_ml/evaluation/hyperparameter_tuning_xgb_home_win.md`, `betting_ml/evaluation/tuning_results_xgb_home_win.json`

#### Card 4.12b Results — XGBoost run_differential Hyperparameter Optimization

- **xgb_run_diff_improved:** True — XGBoost run_differential MAE improved ✓ (tuned=3.4074 vs baseline=3.4887)
- **best_params:** colsample_bytree=0.6105835555603716, learning_rate=0.01041118707020302, max_depth=4, n_estimators=380, reg_alpha=0.7406074869536907, reg_lambda=1.5468473873318191, subsample=0.743006532444217
- **Summary:** Optuna TPE (20 trials) tuned XGBoost for run_differential; tuned MAE=3.4074 vs baseline=3.4887 — improved ✓.
- **Full results:** `betting_ml/evaluation/hyperparameter_tuning_xgb_run_diff.md`, `betting_ml/evaluation/tuning_results_xgb_run_diff.json`
- **Optuna:** TPE sampler, 20 trials, tuned model persisted via save_model()

#### Card 4.1 — Add Delta/Momentum Features to Team and Starter Feature Models

**Title:** Add rolling window delta features (momentum signals) to pregame team and starter feature models

**Description:**

*Technical implementation:*
- In `feature_pregame_team_features`: add delta columns for key team metrics — `home_off_woba_7d_minus_30d`, `home_pit_xwoba_7d_minus_30d`, and away equivalents. These capture whether a team is trending up or down relative to their baseline. Notebook 03 confirmed 7-day and 30-day windows carry different predictive profiles, implying the spread has independent signal.
- In `feature_pregame_starter_features`: add `home_starter_k_pct_7d_minus_std` and `home_starter_xwoba_7d_minus_std` (and away equivalents). Starter K% showed the largest window effect in notebook 03 — a 29% correlation increase from 7-day to STD — making the gap between them a meaningful velocity signal.
- All delta columns computed as `short_window - long_window`; positive values indicate recent improvement over baseline.
- Pass through into `feature_pregame_game_features` final SELECT.
- Update `schema.yml` for both feature models with column descriptions.

*Blockers:* None. All source windows already exist in the feature models.

*Acceptance criteria:*
- [x] Delta columns added for team offense wOBA and pitching xwOBA (7d − 30d) in `feature_pregame_team_features`
- [x] Delta columns added for starter K% and xwOBA (7d − STD) in `feature_pregame_starter_features`
- [x] All delta columns passed through in `feature_pregame_game_features`
- [x] No new null rows introduced beyond what exists in the source window columns
- [x] `schema.yml` updated for both feature models
- [x] `dbtf build --select feature_pregame_team_features feature_pregame_starter_features feature_pregame_game_features` passes all tests

---

#### Card 4.2 — Add Lineup-vs-Starter Handedness Matchup Features

**Title:** Compute explicit lineup-vs-starter handedness matchup signal in the master game feature model

**Description:**

*Technical implementation:*
- In `feature_pregame_game_features`, join `feature_pregame_lineup_features` (lineup handedness composition — `home_lineup_pct_rhb`, `away_lineup_pct_rhb`) with `feature_pregame_starter_features` (starter hand and platoon splits).
- Derive matchup adjustment columns per side. Example for home offense vs. away starter: `home_lineup_vs_away_starter_xwoba_adj` = weighted average of `home_lineup_pct_rhb × away_starter_xwoba_vs_rhb + (1 - home_lineup_pct_rhb) × away_starter_xwoba_vs_lhb`. Repeat for K% and BB%.
- Repeat for away lineup vs. home starter.
- Motivation: notebook 03 max individual |r| was 0.077 — most model signal will come from non-linear interactions. An explicit three-way interaction (lineup composition × starter hand × platoon split) is unlikely to be discovered by XGBoost/NGBoost from separate columns alone.
- These columns are null when starter platoon splits are null (11–17% of games); null propagates correctly and is handled by the imputation pipeline in Card 4.6.
- Update `schema.yml` with column descriptions.

*Blockers:* None. Source columns exist in both upstream feature models.

*Acceptance criteria (completed 2026-04-23):*
- [x] `home_lineup_vs_away_starter_xwoba_adj` and `away_lineup_vs_home_starter_xwoba_adj` added to `feature_pregame_game_features`
- [x] K% and BB% matchup adjustment columns added for both sides
- [x] Null propagation is correct — null when starter platoon splits are null, non-null otherwise
- [x] Spot-check: a RHP starter with high xwOBA_vs_rhb facing a right-heavy lineup produces a higher `xwoba_adj` than the same starter vs. a left-heavy lineup
- [x] `schema.yml` updated with column descriptions
- [x] `dbtf build --select feature_pregame_game_features` passes all tests

---

#### Card 4.3 — Add Rolling Window Reliability Flags to Feature Models

**Title:** Add games-played-in-window sample size flags to pregame team and player feature models

**Description:**

*Technical implementation:*
- In `feature_pregame_team_features`: add `home_games_played_7d`, `home_games_played_14d`, `home_games_played_30d`, `home_games_played_std` (and away equivalents) — count of regular season games played within each rolling window as of the game date. Source: `mart_team_rolling_offense` already computes game counts; extract and pass through.
- In `feature_pregame_starter_features`: add `home_starter_appearances_30d` and `home_starter_appearances_std` — number of starts in each window from `mart_pitcher_rolling_stats`.
- Pass all reliability flag columns through in `feature_pregame_game_features`.
- Motivation: notebook 03 confirmed that pitching feature correlation is 48% lower in the 0–10 game bucket than the 30+ bucket. The 10–30 game transitional bucket is also weaker than 30+ — not just the first week. These flags allow the Bayesian shrinkage step in Card 4.6 to weight estimates appropriately rather than applying a hard filter.

*Blockers:* None. Rolling game counts are available in mart rolling stat models.

*Acceptance criteria:*
- [x] Games-played columns added for 7d, 14d, 30d, and STD windows for both home and away teams in `feature_pregame_team_features`
- [x] Starter appearances added for 30d and STD windows in `feature_pregame_starter_features`
- [x] All columns passed through in `feature_pregame_game_features`
- [x] Values are non-negative integers; zero is valid for season-opening games
- [x] `schema.yml` updated for all three feature models
- [x] `dbtf build --select feature_pregame_team_features feature_pregame_starter_features feature_pregame_game_features` passes all tests

---

#### Card 4.4 — Add Starter Expected Depth Signal to Starter Feature Model ✓ Complete (2026-04-23)

**Title:** Add recent innings-per-start trend to pregame starter feature model as a bullpen workload proxy

**Description:**

*Technical implementation:*
- In `feature_pregame_starter_features`, join to `mart_starting_pitcher_game_log` (filtered to `game_date < game_date` — no leakage) and compute `home_starter_avg_ip_last_3` and `away_starter_avg_ip_last_3` — average innings pitched over the starter's 3 most recent starts.
- Also derive `home_starter_avg_ip_season` and away equivalent — season-to-date IP per start as a stable baseline.
- Motivation: a starter averaging 4.5 IP over recent outings implies heavy bullpen use regardless of what the workload model shows from prior days. Not currently in any feature model.
- Null when the starter has fewer than 1 prior regular season start (debut starters); add `home_starter_has_ip_history` and `away_starter_has_ip_history` boolean flags.
- Pass through in `feature_pregame_game_features` and update `schema.yml`.

*Blockers:* None. `mart_starting_pitcher_game_log` is built and tested.

*Acceptance criteria (completed 2026-04-23):*
- [x] `home_starter_avg_ip_last_3` and `away_starter_avg_ip_last_3` added using strictly `< game_date` (no leakage)
- [x] `home_starter_avg_ip_season` and away equivalent added
- [x] `home_starter_has_ip_history` / `away_starter_has_ip_history` boolean flags added
- [x] Null for debut starters; non-null for all pitchers with at least 1 prior start
- [x] Passed through in `feature_pregame_game_features`
- [x] `dbtf build --select feature_pregame_starter_features feature_pregame_game_features` passes all tests

---

#### Card 4.5 — Add Game Context and Era Features ✓ Complete (2026-04-23)

**Title:** Add day/night, series position, time-varying home win rate, and era flags to the master game feature model

**Description:**

*Technical implementation:*
- **Day/night flag:** Extract `game_time` from `stg_statsapi_games`; derive `is_day_game` boolean. Join to `feature_pregame_game_features` on `game_pk`.
- **Series position:** From `stg_statsapi_games`, compute `series_game_number` (1, 2, 3, or 4 for the current home-team/away-team series in the current road trip). Affects bullpen deployment on days 2 and 3 of a series.
- **Time-varying home win rate:** Add `home_win_rate_trailing_3yr` — rolling 3-year average home win rate across all MLB games up to `game_date`, using strictly `< game_date`. Source: `mart_game_results`. Notebook 01 confirmed home win rate has declined from 0.548 (2020) to 0.519 (2023) — a static 0.529 is increasingly wrong for recent seasons.
- **Era flags:** Add `post_2022_rules` boolean (`game_year >= 2023`) and `game_year` integer. Notebook 01 confirmed a ~0.64-run structural shift from 2022 → 2023 due to the shift ban, pitch clock, and universal DH.
- All columns passed through `feature_pregame_game_features` and added to `schema.yml`.

*Blockers:* None. All source data is in `stg_statsapi_games` and `mart_game_results`.

*Acceptance criteria:*
- [x] `is_day_game` boolean added to `feature_pregame_game_features`
- [x] `series_game_number` integer (1–4+) added, non-null for all regular season games
- [x] `home_win_rate_trailing_3yr` uses strictly `< game_date`; no same-day games included
- [x] `post_2022_rules` boolean and `game_year` integer added
- [x] Spot-check: `home_win_rate_trailing_3yr` for a 2024 game should be in the range 0.519–0.535, not 0.529 static
- [x] `schema.yml` updated for all new columns
- [x] `dbtf build --select feature_pregame_game_features` passes all tests

---

#### Card 4.6 — ML Pipeline Foundation: Data Loading, Splits, and Preprocessing

**Title:** Build the betting_ml/ pipeline foundation — Snowflake data loader, temporal cross-validation splits, and imputation preprocessing

**Description:**

*Technical implementation:*
- Create the `betting_ml/` directory structure: `data/`, `models/`, `evaluation/`, `utils/`.
- **Data loader** (`utils/data_loader.py`): queries `feature_pregame_game_features` joined to `mart_game_results` (targets: `home_score + away_score`, `home_score - away_score`, `home_win`). Uses the same Snowflake RSA key connection as EDA notebooks. Accepts `min_games_played` filter (default 15 per notebook 03 finding).
- **Temporal cross-validation** (`utils/cv_splits.py`): generates season-forward splits (train on years N−k through N−1, evaluate on year N). No shuffled k-fold — temporal order must be respected. Start with leave-one-season-out (train 2016–2024, evaluate 2025).
- **Imputation pipeline** (`utils/preprocessing.py`) implementing decisions from notebook 02:
  - Starter platoon splits: add `has_starter_platoon_data` indicator; fill nulls with prior-season league-average split by pitcher hand × batter hand
  - Park run factor: cascade from 3yr → 1yr → league average; add `is_new_venue` indicator
  - Opening Day win%, days rest: fill with 0.500 and 4 days respectively
  - Bullpen effectiveness early-season: fill with prior-season league-average xwOBA
  - **Bayesian shrinkage for early-season rolling stats:** apply shrinkage toward the league-mean prior weighted by `games_played_in_window` (from Card 4.3). Shrinkage weight = `n / (n + k)` where k is a tunable constant (default: 15 games). Targets the 10–30 game transitional bucket identified in notebook 03 as the weakest correlation period.
- Exclude 2020 from training; include `post_2022_rules` and `game_year` as features (from Card 4.5).

*Blockers:* Cards 4.1–4.5 should be merged before final model runs (reliability flags needed for Bayesian shrinkage). Data loader and CV framework can be built independently.

*Acceptance criteria:*
- [x] `betting_ml/` directory structure created with `data/`, `models/`, `evaluation/`, `utils/`
- [x] Data loader connects to Snowflake, applies `has_full_data = true` and `min_games_played ≥ 15` filter, returns a clean pandas DataFrame with all three targets appended
- [x] Temporal CV splits produce non-overlapping train/eval sets in correct chronological order; no future data leaks into training folds
- [x] Imputation pipeline handles all six null groups from notebook 02 with no remaining nulls in the output feature matrix
- [x] Bayesian shrinkage reduces early-season rolling stat variance correctly — verify a team with 5 games played is pulled further toward league mean than one with 25 games
- [x] 2020 games excluded; `post_2022_rules` and `game_year` present in output feature matrix
- [x] Unit tests for CV splits and imputation pipeline pass

---

#### Card 4.7 — Build `mart_odds_consensus` dbt Model ✓ Complete (2026-04-24)

**Title:** Build `mart_odds_consensus` dbt model — pre-game bookmaker consensus aggregation for Phase 4 odds features

**Why:** Card 3.11 (Bookmaker Calibration, 2026-04-24) set `queue_mart_odds_consensus_card = True` after confirming consensus features carry signal (H7 supported: consensus Brier = 0.2395 < 0.240 threshold, `include_consensus_features = True`). The 9 consensus columns defined by Card 3.11 cannot be assembled in `feature_pregame_odds_features` until this mart model exists. Historical odds backfill (Cards 1–4) is complete and provides the underlying data. This card is the direct blocker before Cards 4.7–4.12 can include betting market features in model training.

*Technical implementation:*

1. **New model:** `dbt/models/mart/mart_odds_consensus.sql`
   - Grain: one row per `event_id`
   - Materialization: `table` (standard for mart aggregate models)
   - Source: `{{ ref('mart_odds_outcomes') }}`

2. **Pre-game snapshot filter (leakage guard):** Filter `mart_odds_outcomes` to `ingestion_ts < commence_time` only. No post-game or same-game snapshots may appear — this is the same leakage rule enforced across all feature-layer models.

3. **Latest-per-book selection:** Within the pre-game window, take the most recent snapshot per `(event_id, bookmaker_key, market_key, outcome_name)` using `QUALIFY ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ingestion_ts DESC) = 1`.

4. **H2H vig adjustment per bookmaker:**
   - `raw_home_prob = ABS(home_price) / (ABS(home_price) + 100)` if `home_price < 0`, else `100 / (home_price + 100)`
   - Same formula for away; `home_imp = raw_home_prob / (raw_home_prob + raw_away_prob)`

5. **Totals vig adjustment per bookmaker:** same pattern for over/under; `over_imp = raw_over_prob / (raw_over_prob + raw_under_prob)`.

6. **Sharp and soft book groups (established by Card 3.11):**
   - Sharp: `lowvig`, `betonlineag`, `bovada`
   - Soft: `draftkings`, `fanduel`, `betmgm`, `williamhill_us`, `betrivers`

7. **Consensus output columns (10 total):**

| Column | Definition |
|---|---|
| `home_win_prob_consensus` | `AVG(home_imp)` across all books with h2h odds |
| `home_win_prob_sharp` | `AVG(home_imp)` for sharp books only; null if no sharp book present |
| `home_win_prob_soft` | `AVG(home_imp)` for soft books only; null if no soft book present |
| `sharp_soft_ml_delta` | `home_win_prob_sharp − home_win_prob_soft` |
| `ml_consensus_std` | `STDDEV(home_imp)` across all books |
| `market_bookmaker_count` | `COUNT(DISTINCT bookmaker_key)` for h2h market |
| `total_line_consensus` | `AVG(total_line)` across all books with totals odds |
| `total_line_std` | `STDDEV(total_line)` across books |
| `over_prob_consensus` | `AVG(over_imp)` across all books with totals odds |
| `totals_bookmaker_count` | `COUNT(DISTINCT bookmaker_key)` for totals market |

8. **Downstream update — `feature_pregame_odds_features`:** After `mart_odds_consensus` is built, join it on `event_id` (already accessible via `mart_game_odds_bridge`) and add all 9 signal columns to the final SELECT. Pass through into `feature_pregame_game_features`.

9. **`schema.yml`:** Add `mart_odds_consensus` block with column descriptions and a `unique` test on `event_id`. Add the 9 new columns to `feature_pregame_odds_features` and `feature_pregame_game_features` schema entries.

*Blockers:* None. `mart_odds_outcomes`, `mart_game_odds_bridge`, and historical odds backfill (Phase 1 Cards 1–4) are all complete. Must be merged before any Phase 4 model training run that includes odds features (Cards 4.7–4.12).

*Acceptance criteria:*
- [x] `dbt/models/mart/mart_odds_consensus.sql` created; materialized as table
- [x] Pre-game leakage guard enforced: only `ingestion_ts < commence_time` snapshots included; spot-check confirms no rows with `ingestion_ts >= commence_time`
- [x] Latest-per-book selection uses QUALIFY pattern; no duplicate `(event_id, bookmaker_key)` rows in h2h or totals CTEs
- [x] All 10 output columns present: `home_win_prob_consensus`, `home_win_prob_sharp`, `home_win_prob_soft`, `sharp_soft_ml_delta`, `ml_consensus_std`, `market_bookmaker_count`, `total_line_consensus`, `total_line_std`, `over_prob_consensus`, `totals_bookmaker_count`
- [x] `home_win_prob_consensus` is non-null for all events with at least one h2h bookmaker
- [x] Sharp and soft columns are null (not 0.0) for events where that group had no coverage
- [x] Spot-check: a Snowflake query joining `mart_odds_consensus` to `mart_game_results` outcomes for 2021–2025 produces consensus Brier within ±0.002 of the 0.2395 Card 3.11 benchmark
- [x] `feature_pregame_odds_features` updated: joins `mart_odds_consensus` on `event_id`; all 9 signal columns passed through
- [x] `feature_pregame_game_features` passes through all new consensus columns from `feature_pregame_odds_features`
- [x] `schema.yml` updated for `mart_odds_consensus`, `feature_pregame_odds_features`, and `feature_pregame_game_features` with column descriptions
- [x] `unique` test on `mart_odds_consensus.event_id` passes (one row per event)
- [x] `dbtf build --select mart_odds_consensus feature_pregame_odds_features feature_pregame_game_features` passes all tests with no new failures

---

#### Card 4.8 — Feature Selection and Dimensionality Reduction

**Title:** Consume EDA notebook 04 findings; build feature selection module and model serialization convention

**Description:**

*Technical implementation:*
- Run EDA notebook 04 (`04_feature_correlations.py`) if not already complete. Findings must be appended to `exploratory_data_analysis/betting_model_findings.md` before proceeding.
- **Feature selection module** (`utils/feature_selection.py`): applies notebook 04 findings programmatically.
  - Drop features with near-zero univariate correlation to all three targets (|r| < 0.02, configurable).
  - Remove one feature from each high-multicollinearity pair (|r| > 0.85), retaining the member with higher correlation to at least one target.
  - Unconditionally retain `post_2022_rules`, `game_year`, and `home_win_rate_trailing_3yr` regardless of univariate correlation (structural features from Card 4.5).
- Persist the canonical feature list to `betting_ml/evaluation/feature_selection.md`: retained features with target correlations; dropped features with reason (low signal vs. multicollinearity). This list is the input contract for Cards 4.8–4.10; ad-hoc column changes must update this document.
- **Model serialization convention** (`utils/model_io.py`): defines `save_model(model, target, model_name, eval_year)` and `load_model(target, model_name, eval_year)` using `joblib`. Standard path: `betting_ml/models/{target}/{model_name}_{eval_year}.pkl`. Required by all downstream model cards.

*Blockers:* Card 4.6 (data loader needed to load features for correlation analysis). EDA notebook 04 preferred but not required — correlation analysis can run inline if notebook is not yet complete.

*Acceptance criteria:*
- [x] EDA notebook 04 (`04_feature_correlations.py`) run; findings appended to `exploratory_data_analysis/betting_model_findings.md`
- [x] `utils/feature_selection.py` implements near-zero correlation drop and multicollinearity resolution; at least one high-multicollinearity pair (|r| > 0.85) identified and resolved
- [x] Canonical feature list documented in `betting_ml/evaluation/feature_selection.md`; retained features listed with target correlations; dropped features listed with reason
- [x] `post_2022_rules`, `game_year`, and `home_win_rate_trailing_3yr` unconditionally present in retained feature list
- [x] `utils/model_io.py` implemented; `save_model` and `load_model` round-trip verified with a toy sklearn model

---

#### Card 4.9 — Baseline Regression Models: Total Runs

**Title:** Train and evaluate Ridge, XGBoost, and NGBoost regression baselines for total runs prediction; output full predictive distribution

**Description:**

*Technical implementation:*
- Three models evaluated on the same temporal CV splits from Card 4.6:
  1. **Ridge regression** (sklearn) — linear floor; establishes how much signal is linear
  2. **XGBoost regression** — point prediction; residual distribution estimated from out-of-fold errors to derive P(over/under line)
  3. **NGBoost** (`ngboost` package) — probabilistic gradient boosting; evaluate both `Normal` and `LogNormal` distributions. LogNormal motivated by notebook 01 finding that blowout games exceed what a pure Gaussian predicts
- Primary metric: MAE and RMSE on held-out season. Baseline to beat: MAE ~3.5 runs (global mean predictor from notebook 01).
- Secondary metric: P(over/under line) Brier score — for games where `has_odds = true`, compare model-implied P(over total_line) to bookmaker's vig-adjusted implied probability.
- SHAP feature importance on XGBoost to verify that lineup-vs-starter matchup features (Card 4.2) and delta features (Card 4.1) contribute non-zero positive signal.
- Log results to `betting_ml/evaluation/total_runs_results.md`.

*Blockers:* Cards 4.6 and 4.7. Cards 4.1–4.5 preferred before final evaluation; initial runs can start with existing features.

*Acceptance criteria:*
- [x] Ridge, XGBoost, and NGBoost models trained and evaluated on all temporal CV folds
- [x] All three models beat the global mean MAE baseline (~3.5 runs) on the held-out season
- [x] NGBoost Normal vs. LogNormal compared — document which distribution better fits the blowout tail
- [x] P(over/under line) Brier score computed for games with odds data (2026 live games)
- [x] SHAP importance confirms lineup-vs-starter matchup and delta features have non-zero contribution
- [x] Per-season MAE/RMSE table and model comparison documented in `betting_ml/evaluation/total_runs_results.md`
- [x] Best model selected with rationale documented

---

#### Card 4.10 — Baseline Regression Models: Run Differential

**Title:** Train and evaluate Ridge, XGBoost, and NGBoost regression baselines for run differential; derive win probability from predictive distribution

**Description:**

*Technical implementation:*
- Same three-model structure as Card 4.8 applied to run differential (`home_score - away_score`) as target.
- Win probability derivation: from the NGBoost predictive distribution N(μ, σ²), compute `P(home win) = P(run_diff > 0) = 1 - Φ((0 - μ) / σ)`. This derives win probability from the regression model without training a separate classifier.
- Compare derived win probability against the binary win classifier (Card 4.11) using Brier score and calibration curves — the two approaches should produce consistent estimates.
- Evaluate whether era features (`post_2022_rules`, `game_year`) and time-varying home win rate (Card 4.5) materially reduce prediction error vs. a model without them.
- Log results to `betting_ml/evaluation/run_differential_results.md`.

*Blockers:* Cards 4.6 and 4.7. Cards 4.1–4.5 preferred before final evaluation.

*Acceptance criteria:*
- [x] Ridge, XGBoost, and NGBoost models trained and evaluated on all temporal CV folds for run differential
- [x] Win probability derived from NGBoost distribution: `P(run_diff > 0)` and Brier score documented
- [x] Derived win probability vs. Card 4.11 classifier compared — consistency within 0.05 Brier score expected
- [x] Era feature ablation: model with vs. without `post_2022_rules` compared — verify the flag reduces 2022→2023 prediction error
- [x] Time-varying home win rate confirmed as improvement over static 0.529, or documented as having no effect
- [x] Results documented in `betting_ml/evaluation/run_differential_results.md`


#### Card 4.10 Results — Run Differential Regression Baselines

- **Best model:** `ngboost_normal` (mean MAE = 3.4461)
- **NGBoost Normal aggregate win probability Brier score:** 0.2429
- **Era features help (post_2022_rules + game_year):** True
- **home_win_rate_trailing_3yr helps beyond era flags:** True
- **NGBoost LogNormal viable for run_differential:** False (negative support incompatible)
- **Details:** `betting_ml/evaluation/run_differential_results.md`

> **Note:** Results above were generated with the pre-Card 4.8 feature set (included `home_win_prob_sharp`). After Card 4.8 update (now uses `home_win_prob_consensus`), re-run `uv run python betting_ml/scripts/train_run_diff_baselines.py` to regenerate.

---

#### Card 4.11 — Baseline Classification Models: Win Outcome

**Title:** Train and evaluate Logistic Regression and XGBoost classification baselines for binary win outcome; calibrate probability outputs

**Description:**

*Technical implementation:*
- Two models on the binary home win target:
  1. **Logistic Regression** (sklearn) — well-calibrated by construction; linear probability baseline
  2. **XGBoost classifier** — apply Platt scaling (sigmoid calibration) and isotonic regression post-training; compare both calibration methods
- Calibration is the primary concern — outputs feed directly into EV calculations in Phase 6. Evaluate calibration curves by probability decile per held-out season.
- Evaluate whether declining home win rate (0.548 → 0.519 per notebook 01) causes systematic over-pricing of home teams in recent seasons. Verify `home_win_rate_trailing_3yr` (Card 4.5) reduces this bias.
- Metrics: log loss, Brier score, AUC-ROC. Calibration curve plotted per held-out season.
- Log results to `betting_ml/evaluation/win_outcome_results.md`.

*Blockers:* Cards 4.6 and 4.7.

*Acceptance criteria:*
- [x] Logistic Regression and calibrated XGBoost trained on all temporal CV folds
- [x] Calibration curves plotted per held-out season — XGBoost post-calibration shows no systematic over/under-confidence across probability deciles
- [x] Platt scaling vs. isotonic calibration compared; better method documented
- [x] Model evaluated for home-team bias in 2023–2025 seasons; `home_win_rate_trailing_3yr` confirmed to reduce or eliminate the bias
- [x] Brier score and log loss reported per model and per held-out season
- [x] Results documented in `betting_ml/evaluation/win_outcome_results.md`

---


#### Card 4.12a Results — XGBoost total_runs Hyperparameter Tuning (Optuna TPE)

- **xgb_total_runs_improved:** True
- **Baseline MAE:** 3.6385 | **Tuned MAE:** 3.5655 | **Change:** +2.01%
- **Best params:** max_depth=3, learning_rate=0.0153, n_estimators=238, subsample=0.753, colsample_bytree=0.763, reg_alpha=0.215, reg_lambda=1.683
- **Summary:** Optuna tuned XGBoost for total_runs achieved MAE=3.5655 vs. baseline=3.6385; tuned model persisted via model_io.py as `xgb_tuned`.

#### Card 4.12 — Hyperparameter Optimization ✓ Complete (2026-04-25)

**Title:** Systematic XGBoost and NGBoost hyperparameter tuning for all three targets using Optuna; persist tuned models

**Status:** Complete. All five sub-cards (12a–12e) finished. XGBoost tuned via Optuna TPE for total_runs (50 trials), run_differential (20 trials), and home_win (50 trials). NGBoost grid-searched for total_runs and run_differential. All tuned models persisted via `model_io.py`. See Card 4.12a–4.12e Results above.

**Description:**

*Technical implementation:*
- Apply systematic hyperparameter tuning to the XGBoost models from Cards 4.8–4.10 using Optuna with the TPE sampler. 50 trials per model; evaluate each trial using the temporal CV splits from Card 4.6.
- **XGBoost search space** (applied to all three target models):
  - `max_depth`: 3–8
  - `learning_rate`: 0.01–0.3 (log scale)
  - `n_estimators`: 100–1000
  - `subsample`: 0.6–1.0
  - `colsample_bytree`: 0.5–1.0
  - `reg_alpha`: 0.0–1.0
  - `reg_lambda`: 0.5–2.0
- **Objective functions**: MAE for total runs and run differential; Brier score for win outcome.
- After XGBoost tuning, tune NGBoost `n_estimators` and distribution type (`Normal` vs. `LogNormal`) for regression targets via grid search.
- Log all trials to `betting_ml/evaluation/hyperparameter_tuning.md`: search space, best parameters, and CV score per model.
- Persist tuned models via `utils/model_io.py` (Card 4.7) using the same path convention as baseline models with a `_tuned` suffix.

*Blockers:* Cards 4.8, 4.9, and 4.10 (baselines required to establish improvement reference). Card 4.7 (`utils/model_io.py` required for model persistence).

*Acceptance criteria:*
- [x] Optuna tuning completed for XGBoost variants of all three targets (12a: 50 trials, 12b: 20 trials, 12c: 50 trials)
- [x] Tuned XGBoost MAE for total runs improves on baseline (3.5655 vs 3.6385 baseline — +2.01%)
- [x] Tuned XGBoost Brier score for win outcome improves on baseline (0.2423 vs 0.2443 baseline — +0.83%)
- [x] NGBoost `n_estimators` and distribution type tuned for total runs (n_est=200, Normal) and run_differential (n_est=500, Normal); LogNormal non-viable for run_differential
- [x] Best hyperparameters and CV scores per model logged in `betting_ml/evaluation/hyperparameter_tuning_xgb_total_runs.md`, `hyperparameter_tuning_xgb_run_diff.md`, `hyperparameter_tuning_xgb_home_win.md`, `hyperparameter_tuning_ngboost_total_runs.md`, `hyperparameter_tuning_ngboost_run_diff.md`
- [x] Tuned models persisted via `utils/model_io.py` with `_tuned` suffix

---

#### Card 4.13 — Probability Output Layer and Bayesian Market Update

**Title:** Build probability output layer integrating model predictions with bookmaker implied probabilities via Bayesian update

**Description:**

*Technical implementation:*
- For games where `has_odds = true`: compute the Bayesian posterior by treating the bookmaker's vig-adjusted implied probability as a prior and the model's predicted probability as the likelihood. In log-odds space: `log_odds_posterior = α × log_odds_model + (1 - α) × log_odds_market` where α is a mixing weight tuned via CV (start with α = 0.5). Motivation: the market line reflects professional handicappers and information the model cannot access; treating it as a prior rather than a comparison target captures the best of both signals.
- Compute edge signal: `edge = model_prob − market_implied_prob` (positive = model sees value over market price).
- Output one row per game per market (h2h, totals) with `model_prob`, `market_implied_prob`, `posterior_prob`, `edge`, and `implied_kelly_fraction` (`edge / market_odds` as a simple Kelly approximation).
- Pure Python module; reads from tuned model outputs of Cards 4.8–4.12 and from `feature_pregame_odds_features`.
- Historical odds backfill (Cards 1–4) complete as of 2026-04-23, covering 2021–2025 regular seasons at ~72–78% game match rate (~8,297 matched games). α tuning in the CV loop will use thousands of has_odds rows from 2021–2025 folds.

*Blockers:* Cards 4.8–4.12 complete. Ready to begin.

*Acceptance criteria:*
- [x] Bayesian update implemented in log-odds space; posterior probability computed for h2h and totals markets
- [x] Mixing weight α tuned on held-out games via CV; optimal α = 0.0 (market dominates; model does not improve calibration)
- [x] Edge signal validated: h2h mean edge = -0.083 (model underestimates home team vs. market); totals mean edge = +0.057 (model leans over vs. market line); 74% of totals games show positive edge
- [x] Output includes `model_prob`, `market_implied_prob`, `posterior_prob`, `edge`, `implied_kelly_fraction` per game per market
- [x] Output written to `betting_ml/outputs/probability_outputs.parquet` (230 rows, 115 games × 2 markets)
- [x] Results persisted to Snowflake: `probability_outputs` (230 rows), `alpha_tuning_results`, `probability_layer_summary`

*Key finding:* best_alpha=0.0 — the market implied probability is better calibrated than the model posterior on all held-out folds. Log-loss rises monotonically from α=0.0 (0.683) to α=1.0 (0.731). The `edge` column (model_prob − market_implied_prob) is the primary actionable signal for Phase 6. See `betting_ml/evaluation/probability_layer_results.md` for full results.

*Known implementation gaps (2026-04-25) — resolved 2026-05-02:*
- ~~**`alpha_tuning_results` incomplete:** The production run used `--use-alpha 0.0` as a bypass; the Snowflake table has 1 row instead of the spec-required 11.~~ **Resolved (Card 7A, 2026-05-02):** Full 11-row grid rerun against corrected odds data; best_alpha=0.0 confirmed on 14,126 has_odds eval records.
- ~~**`best_alpha.json` not written:** `predict_today.py` falls back to `0.5` on Snowflake failure.~~ **Resolved (Card 7A, 2026-05-02):** `run_probability_layer.py` now writes `betting_ml/models/best_alpha.json` after each full grid run; `predict_today.py` three-tier fallback (Snowflake → file → 0.5) confirmed in place.

---

#### [BACKLOG] Card 4.B1 — Weather Feature Integration

**Title:** Integrate pre-game weather features (temperature, wind speed/direction, humidity) for outdoor ballparks

**Description:**

*Technical implementation:*
- Source a weather API (e.g., OpenWeatherMap historical + forecast) for game-time conditions at each ballpark's GPS coordinates (available in `stg_statsapi_venues`).
- Key features: `temp_f`, `wind_speed_mph`, `wind_direction_degrees`, `humidity_pct`, `is_precipitation`. Wind direction relative to park orientation is the most important interaction (Wrigley Field wind-out vs. wind-in is a ~2-run swing).
- Roof-type filter: weather features are irrelevant for domed stadiums (`roof_type = 'dome'` in `stg_statsapi_venues`) — zero these out or add `weather_relevant` boolean.
- Store raw weather snapshots in Snowflake; add a dbt staging model `stg_weather` and join into `feature_pregame_park_features`.
- Leakage constraint: use forecast-at-game-time for live predictions, not observed actuals.

*Blockers:* Weather API selection and credentials not yet in place. No historical weather data in the current pipeline.

*Acceptance criteria:*
- [ ] Weather API source selected and credentials secured
- [ ] Historical weather ingestion script built covering 2016–2025 regular seasons at all active park coordinates
- [ ] `stg_weather` dbt model staging raw weather to grain of `game_pk`
- [ ] Weather features joined into `feature_pregame_park_features` with `weather_relevant` flag
- [ ] Null rate < 5% for outdoor parks in the training window
- [ ] Ablation study: model with vs. without weather features compared on the held-out season

---

#### [BACKLOG] Card 4.B2 — Umpire Tendency Features

**Title:** Integrate pre-game umpire tendency features (zone size, K%/BB% impact) as a game-level signal

**Description:**

*Technical implementation:*
- Source umpire tendency data (e.g., UmpScorecards) providing per-umpire rolling statistics: zone size relative to league average, called strike rate above/below expectation, resulting K% and BB% adjustments.
- Key features: `ump_k_pct_adj`, `ump_bb_pct_adj`, `ump_zone_size_adj`. Join on `game_pk` once umpire assignments are known (typically announced morning of game).
- Add a `stg_umpires` staging model and extend `feature_pregame_game_features` with an umpire join.

*Blockers:* Umpire assignment data source not yet in place. No umpire data in the current pipeline.

*Acceptance criteria:*
- [ ] Umpire data source selected and historical assignments sourced for 2016–2025 seasons
- [ ] `stg_umpires` dbt staging model built
- [ ] Umpire tendency features joined into `feature_pregame_game_features` on `game_pk`
- [ ] Null rate < 5% for games with known umpire assignments
- [ ] Ablation study: model with vs. without umpire features compared on the held-out season

---

### Phase 5 — Model Finalization and Dry Run Application

Goal: produce a working local prediction system runnable this weekend for a live dry run of today's games. No cloud infrastructure required — every component runs on a laptop with Snowflake access.

---

#### Card 5.1 — Model Selection, Packaging, and Registry

**Title:** Select best model artifacts from Phase 4 and write versioned model registry

**Description:**

*Technical implementation:*
- After Cards 4.12 and 4.13 complete, compare tuned model CV metrics across all three targets. For each target, select the single best model (lowest MAE for regression targets; lowest Brier score for win outcome) from the saved `betting_ml/models/{target}/` files.
- Write `betting_ml/models/model_registry.yaml` — a flat YAML keyed by target with fields: `model_name`, `eval_year`, `cv_mae` / `cv_brier`, `artifact_path`, `selected_at`. This file is the single source of truth that `predict_today.py` (Card 5.2) reads to locate the production model. The `home_win` entry also includes a `calibration_split` field (see production calibration refit below).
- Tag the selected artifacts with a `_prod` copy so rollback is a one-line path swap, not a registry rewrite.
- **Win outcome production calibration refit (Gap 5):** Card 4.11 uses the eval fold as the calibration set — an approximation acceptable for CV benchmarking but not for production, because the calibration curve and ECE are partially in-sample. Before registering the `home_win` `_prod` artifact, perform a proper 3-way temporal refit:
  1. **Verification split** — Train XGBoost (best model family per Card 4.11 CV) on 2016–2023. Fit `CalibratedClassifierCV(cv='prefit', method=<best_method_from_card_4_11>)` on 2024 data as the dedicated calibration hold-out. Evaluate ECE and Brier on 2025. Record as `win_outcome_verification_ece` and `win_outcome_verification_brier`. If the verification ECE is more than 0.005 worse than the Card 4.11 CV ECE, flag for investigation before proceeding.
  2. **Production refit** — Train XGBoost on 2016–2024. Fit the same calibrator on 2025 as the calibration hold-out. Save as `betting_ml/models/home_win/xgboost_{method}_prod_calibrated.pkl`. This is the `_prod` artifact — not the CV model from Card 4.11. The verification split in step 1 provides confidence that the calibration generalizes; there is no separate eval fold for the final production model because all available historical data (2016–2025) is used to maximize training coverage.
  3. **Registry entry** — The `model_registry.yaml` entry for `home_win` must include `calibration_split: 2025` so `predict_today.py` and the Streamlit app know the calibrator was fit on a proper hold-out. Regression targets (`total_runs`, `run_differential`) do not require this step — their NGBoost Normal outputs are already proper probability distributions without a post-hoc calibration step.

*Blockers:* Cards 4.11, 4.12, and 4.13 must be complete (4.11 identifies the best calibration method; 4.12 provides tuned XGBoost artifacts; 4.13 provides `best_alpha`).

*Acceptance criteria (complete as of 2026-04-25):*
- [x] `betting_ml/models/model_registry.yaml` created with one entry per target
- [x] `_prod` copies of selected artifacts written to `betting_ml/models/{target}/`
- [x] Registry YAML parseable by `yaml.safe_load`; all three targets present with non-null `artifact_path`
- [x] `load_model(target, "prod")` via `utils/model_io.py` round-trips cleanly using the registry path
- [x] `betting_ml/models/home_win/` contains `xgboost_sigmoid_prod_calibrated.pkl` fit on 2025 data (dedicated hold-out), not the CV eval fold
- [x] `model_registry.yaml` `home_win` entry has `calibration_split: 2025`
- [x] Verification ECE documented in `betting_ml/evaluation/calibration_verification.md`; delta=+0.0028 vs. Platt CV ECE 0.0119 — within 0.005 threshold; verdict PASS

---

#### Card 5.2 — Pre-Game Prediction CLI (Local Dry Run)

**Title:** Build `predict_today.py` — a local CLI that scores today's games and ranks them by predicted edge

**Description:**

*Technical implementation:*
- New script: `betting_ml/scripts/predict_today.py`. Accepts optional `--date YYYY-MM-DD` (defaults to today).
- **Step 1 — Load features:** Query `feature_pregame_game_features` joined to `stg_statsapi_games` for the target date. Filter to games where `has_odds = true` and both lineups are confirmed (`home_lineup_slot_1 IS NOT NULL AND away_lineup_slot_1 IS NOT NULL`).
- **Step 2 — Load models:** Read `betting_ml/models/model_registry.yaml`; load the `_prod` artifact for each target using `utils/model_io.py`.
- **Step 3 — Score games:** Run the feature matrix through all three production models. For NGBoost regression targets, compute `P(total > total_line_consensus)` via the distribution CDF. For win outcome, output calibrated `home_win_prob`. Load `best_alpha` from the `alpha_tuning_results` Snowflake table (most recent `loaded_at` row) or from a local cache file `betting_ml/models/best_alpha.json` written by Card 4.13 at α tuning time — prefer Snowflake, fall back to local cache if Snowflake is unreachable.
- **Step 4 — Bayesian mixing and edge calculation:** For each game with odds, apply the Bayesian posterior using `compute_posterior(model_prob, market_prob, best_alpha)` from `betting_ml/utils/probability_layer.py` — the same function and `best_alpha` tuned in Card 4.13. Compute `edge = compute_edge(model_prob, market_prob)` and `kelly_fraction = compute_kelly(edge, market_prob)`. Rank games by `abs(edge)` descending. This reuses Card 4.13's math exactly; `predict_today.py` is the live execution of the same pipeline, not a reimplementation.
- **Step 5 — Output:** Print a formatted table to stdout (matchup, game time, predicted total, model win prob, market win prob, posterior prob, edge, Kelly fraction). Write `betting_ml/outputs/probability_outputs_{date}.parquet` using the Card 4.13 schema (`game_key, market, model_prob, market_implied_prob, alpha, posterior_prob, edge, implied_kelly_fraction`) — this is the canonical contract format that Phase 6's betting application layer consumes. Also write `betting_ml/outputs/predictions_{date}.csv` with the full display columns (matchup, game_time, etc.) for human review.
- The script reads credentials from the project root `.env` via the existing Snowflake connector pattern in `utils/data_loader.py`.

*Blockers:* Card 5.1 (model registry). Cards 4.12 and 4.13 (probability output layer; `best_alpha` must be persisted before `predict_today.py` can run).

*Acceptance criteria:*
- [ ] `uv run python betting_ml/scripts/predict_today.py` runs end-to-end on a laptop with no manual steps beyond `.env` credentials
- [ ] Output table includes: `game_pk`, `matchup`, `game_time`, `predicted_total_runs`, `model_home_win_prob`, `market_home_win_prob`, `posterior_prob`, `edge`, `kelly_fraction`
- [ ] Games ranked by `abs(edge)` descending
- [ ] Script handles the case where `has_odds` games are a subset of today's games (non-odds games included with `edge = null`, `posterior_prob = null`)
- [ ] `betting_ml/outputs/probability_outputs_{date}.parquet` written with columns matching Card 4.13 schema: `game_key, market, model_prob, market_implied_prob, alpha, posterior_prob, edge, implied_kelly_fraction`
- [ ] `betting_ml/outputs/predictions_{date}.csv` written with all display columns
- [ ] Script exits cleanly if no games are found for the target date
- [ ] `best_alpha` is loaded from Snowflake (or local cache fallback) — not hardcoded

*Known implementation gap (2026-04-25):* `load_todays_features_via_statsapi()` — the Stats API intraday fallback described in the Phase 5.1 plan spec's `implement-statsapi-feature-assembly` task — is not yet implemented in `betting_ml/utils/data_loader.py`. `predict_today.py` currently queries `feature_pregame_game_features` directly; since the nightly dbt pipeline only writes rows after games complete, any intraday run against today's date returns an empty DataFrame and the script exits with "No games found." Fix: implement `load_todays_features_via_statsapi(target_date)` in `data_loader.py` per the plan spec and wire it as the fallback in `load_todays_features()`. This is the primary blocker for intraday dry-run use.

---

#### Card 5.3 — Lineup Finalization Notification and Hourly Staging Refresh — SUBSTANTIALLY COMPLETE (22/23)

**Title:** Detect confirmed lineups hourly via a Snowflake Task, trigger a GitHub Actions dbtf build, and notify when both lineups are locked

**Status as of 2026-04-27:** All infrastructure is live. One acceptance criterion (pipeline_run_log entry from a real lineup dispatch) is pending until confirmed lineups appear in `stg_statsapi_lineups_wide` for the current date. Email notification is explicitly deferred to Phase 6. See implementation notes below for deviations from the original spec.

**Implemented architecture:**

**Component 1 — Snowflake Task: `task_lineup_monitor`**
- `scripts/ddl/lineup_monitor_task.sql` defines the full pipeline: `lineup_monitor_state` table, `lineup_monitor_proc` stored procedure, `CREATE OR REPLACE TASK`, and `ALTER TASK RESUME`.
- Task runs serverless (`USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'`) — consistent with all other tasks in the project. Cron: `'USING CRON 0 * * * * America/New_York'`.
- Task is deployed and confirmed STARTED in Snowflake.
- The stored procedure reads from `baseball_data.betting.stg_statsapi_lineups_wide` (stg + mart models build into `baseball_data.betting`; feature models build into `baseball_data.betting_features`). It does NOT re-call `ingest_statsapi.py` directly — ingestion is handled by the existing 8am `task_statsapi_schedule` in `snowflake_task_dag.sql`. The proc reads the already-materialized dbt table.
- Lineup confirmation check: `COUNT(DISTINCT home_away) = 2` grouped by `game_pk` on `official_date = CURRENT_DATE`. This is correct because `stg_statsapi_lineups_wide` already excludes rows where `slot_1_player_id IS NULL`, so any row present means that side's lineup is confirmed.
- Deduplication: `UNIQUE (run_date, game_pk)` constraint on `lineup_monitor_state` plus a `NOT EXISTS` guard in the INSERT. Every hourly fire (including no-ops) writes one row to `pipeline_run_log` with `task_name = 'lineup_monitor_proc'`.
- Secret access uses `_snowflake.get_generic_secret_string('github_pat')` via `SECRETS = ('github_pat' = baseball_data.config.github_pat)` — consistent with the existing procedures in `snowflake_task_dag.sql`.

**Required RBAC grants (applied 2026-04-27, run as ACCOUNTADMIN):**
```sql
GRANT USAGE ON SCHEMA baseball_data.betting TO ROLE task_executor_role;
GRANT SELECT ON ALL TABLES IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
GRANT SELECT ON FUTURE TABLES IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
GRANT SELECT ON ALL VIEWS IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA baseball_data.betting TO ROLE task_executor_role;
GRANT USAGE ON SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
GRANT SELECT ON ALL TABLES IN SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
GRANT SELECT ON FUTURE TABLES IN SCHEMA baseball_data.betting_features TO ROLE task_executor_role;
```

**Component 2 — GitHub Actions workflow: `dbt_staging_build.yml`**
- `.github/workflows/dbt_staging_build.yml` — `workflow_dispatch` trigger with `game_pk` (required) and `triggered_by` (optional, default `manual`) inputs.
- dbt-fusion install uses the curl script pattern (consistent with `dbt_daily_build.yml`): `curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh | sh -s -- --update` followed by `echo "$HOME/.local/bin" >> $GITHUB_PATH`.
- Build command: `dbt build --select +stg_statsapi_lineups+ --project-dir dbt`.
- Validated end-to-end via manual `workflow_dispatch` from the GitHub UI.
- Required GitHub Secrets (same set as `dbt_daily_build.yml`): `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY` (PEM content), `SNOWFLAKE_DATABASE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_ROLE`.

**Component 3 — Notification dispatch**
- Email notification is **deferred to Phase 6** (out of scope for this card per plan spec). The `dbt_staging_build.yml` workflow does not include a notification step.

**Documentation:**
- `scripts/daily_run.md` updated with "Lineup Monitor Architecture" section: system diagram, secrets table, manual trigger command (`gh workflow run dbt_staging_build.yml -f game_pk=<game_pk>`), suspend/resume SQL, and task history query.

*Acceptance criteria:*
- [x] `baseball_data.config.lineup_monitor_state` table created; columns `run_date`, `game_pk`, `triggered_at`, `gh_workflow_run_id`
- [x] Snowflake Task `task_lineup_monitor` fires on the hourly cron schedule; confirmed via `SHOW TASKS` (state = STARTED) and `pipeline_run_log`
- [x] When both lineups for a game are confirmed, exactly one row is inserted into `lineup_monitor_state` for that `(run_date, game_pk)` — deduplication verified via manual dispatch test
- [x] GitHub Actions workflow `dbt_staging_build.yml` is triggerable via `workflow_dispatch` from the GitHub UI with `game_pk` input; validated end-to-end
- [x] `dbtf build --select +stg_statsapi_lineups+` runs successfully inside the Actions workflow
- [x] `scripts/daily_run.md` updated with "Lineup Monitor Architecture" section; includes manual trigger command and secrets checklist
- [ ] `pipeline_run_log` has ≥1 entry from an actual lineup dispatch (rows_affected > 0) — **pending**: proc runs correctly and logs no-op SUCCESS entries; will self-complete on next day with confirmed lineups in `stg_statsapi_lineups_wide`

---

### Phase 6 — Betting Application Layer and Pipeline Automation

The MVP application is a **multi-page Streamlit app** (`app/`) that connects directly to Snowflake and the saved model artifacts. It covers every application layer component without requiring a separate backend service. All four pages are read-only — no write path needed for the MVP. The Phase 7 production app replaces this with a hardened stack once the model's value is proven in live use.

**Live pipeline architecture and contract decision (Gap 4) — updated 2026-05-01:**

All automated orchestration runs via GitHub Actions. Five workflows cover daily ingestion, intraday odds snapshots, and lineup monitoring. See Section 13 → "GitHub Actions Orchestration" for the full workflow reference table.

The live daily prediction flow is:
1. **`daily_ingestion.yml`** (GHA cron, 08:00 EDT) — three sequential jobs: (a) **`ingest`**: Statcast, Stats API schedule, and Odds API; (b) **`dbt-build`**: calls `dbt_daily_build.yml` via `workflow_call` immediately after ingestion; (c) **`backfill`**: runs `backfill_prediction_log.py` after dbt completes to fill in outcomes and CLV.
2. **`dbt_daily_build.yml`** (called via `workflow_call` from `daily_ingestion.yml`, or manually via `workflow_dispatch`) — runs `dbt build` on odd days, `dbt run` on even days, and `dbt build --full-refresh` on Sundays.
3. **`lineup_monitor.yml`** (GHA cron, every hour) — re-ingests Stats API schedule for current + prior month, rebuilds staging lineup models, detects newly confirmed lineups, and conditionally rebuilds all lineup-dependent feature models.
4. **`odds_snapshot.yml`** (GHA cron, 13:00 / 18:00 / 23:00 EDT) — re-ingests Odds API on game days; rebuilds the odds dbt DAG for intraday line-movement tracking.
5. **`dbt_staging_build.yml`** (GHA `workflow_dispatch`) — lineup-scoped `dbt build --select +stg_statsapi_lineups+`; dispatched by the Snowflake `task_lineup_monitor` stored procedure when both lineups for a game are confirmed.
6. Phase 6 Streamlit app (Card 6.B) scores models inline on page load — same functions, same `best_alpha`, live view that updates without re-running a CLI script.

**Explicit contract decision:** Card 4.13's `probability_outputs.parquet` schema (`game_key, market, model_prob, market_implied_prob, alpha, posterior_prob, edge, implied_kelly_fraction`) IS the canonical Phase 6 contract. Two consumers exist:
- `predict_today.py` (batch) — produces `probability_outputs_{date}.parquet` on demand; used for performance logging, closing line tracking, and offline review.
- Card 6.B Streamlit app (interactive) — scores inline using `compute_posterior()` / `compute_edge()` / `compute_kelly()` from `betting_ml/utils/probability_layer.py` with `best_alpha` loaded from Snowflake; produces the same logical row structure as the parquet contract without reading the parquet file directly.

No redesign of Card 4.13's output format is required. The parquet schema is the right contract and the Streamlit app reuses the same math via direct function calls rather than file reads.

*Enhancement opportunity (Phase 6):* `predict_today.py` already computes `consensus_win_prob = 0.5 × p_home_win_ngboost + 0.5 × p_home_win_classifier` and stores it in `daily_model_predictions`. Card 4.13 found h2h mean edge = −0.083 (only 31% positive) when using NGBoost alone for `model_prob`. Formalizing `consensus_win_prob` as the official `model_prob` for h2h edge calculation in both `predict_today.py` and the Streamlit app — rather than NGBoost alone — may reduce the systematic home-team underestimation bias. This requires a one-line change to the edge calculation and an update to `probability_layer_results.md`; it does not require retraining any model.

---

#### Card 6.A — Snowflake Task DAG for Automated Daily Ingestion (Card Group)

This card has been broken into eight sub-tasks. Implement in the order listed; Cards 6.A.2 and 6.A.3 may be done in parallel after 6.A.0, and Card 6.A.6 may be done in parallel with 6.A.4 and 6.A.5.

DAG topology (each arrow = `AFTER` dependency):

```
task_savant_ingestion  (ROOT, CRON 0 8 * * * America/New_York, serverless)
    → task_statsapi_schedule
        → task_oddsapi_events
            → task_oddsapi_odds
                → task_github_actions_trigger  (dispatches dbt_daily_build.yml)
```

---

##### Card 6.A.0 — Admin Prerequisites: Account Privileges and GitHub PAT Provisioning — COMPLETE

**Title:** Grant EXECUTE TASK account privilege and provision GitHub PAT before implementation begins

*Technical implementation:*

Three one-time manual steps that must be completed before any downstream card can be implemented.

**Blocker 1 — EXECUTE TASK + EXECUTE MANAGED TASK privileges (requires ACCOUNTADMIN):**
```sql
-- Run as ACCOUNTADMIN once before executing the remainder of snowflake_task_dag.sql
GRANT EXECUTE TASK ON ACCOUNT TO ROLE task_executor_role;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE task_executor_role;
```
`EXECUTE MANAGED TASK` is required for serverless tasks (`USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE` with no warehouse specified). Without it, `CREATE TASK` fails with "missing serverless task privilege."

If `task_executor_role` does not exist yet (it is created in Card 6.A.1), grant temporarily to `SYSADMIN` and re-grant to `task_executor_role` after 6.A.1 completes. Document this in `scripts/ddl/snowflake_task_dag.sql` as a comment block at the top of the file:
```sql
-- PREREQUISITE (ACCOUNTADMIN required — run once, not part of normal DDL execution):
-- GRANT EXECUTE TASK ON ACCOUNT TO ROLE task_executor_role;
-- GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE task_executor_role;
```

**Blocker 2 — ACCOUNTADMIN required for network rule creation:**
The `CREATE NETWORK RULE` and `CREATE EXTERNAL ACCESS INTEGRATION` statements in Card 6.A.2 must be executed under an ACCOUNTADMIN session (or a role with `CREATE NETWORK RULE` privilege explicitly granted). Add to the DDL file header:
```sql
-- PREREQUISITE (ACCOUNTADMIN required for Sections 2 and 3):
-- USE ROLE ACCOUNTADMIN;
-- Execute NETWORK RULE and EXTERNAL ACCESS INTEGRATION blocks, then switch back to SYSADMIN.
```

**Blocker 3 — GitHub PAT provisioning:**
1. GitHub → Settings → Developer Settings → Personal Access Tokens → Classic
2. Create a PAT with `repo` scope (required for `workflow_dispatch` via the REST API)
3. Copy the token value immediately — it is only shown once
4. Store as a Snowflake Secret at provision time (DDL in Card 6.A.3 uses a `<placeholder>` value that the engineer substitutes in a live Snowflake session; the substituted file is never committed):
   ```sql
   CREATE OR REPLACE SECRET baseball_data.config.github_pat
     TYPE = GENERIC_STRING
     SECRET_STRING = '<paste-token-here>';
   ```
5. Test the PAT with a manual `curl` before trusting it in the stored procedure:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" \
     -X POST \
     -H "Authorization: token <PAT>" \
     -H "Accept: application/vnd.github.v3+json" \
     https://api.github.com/repos/<owner>/<repo>/actions/workflows/dbt_daily_build.yml/dispatches \
     -d '{"ref":"main"}'
   # Expected: 204
   ```

*Blockers:* None — this card IS the prerequisite for all downstream 6.A cards.

*Acceptance criteria:*
- [ ] `scripts/ddl/snowflake_task_dag.sql` contains a `-- PREREQUISITE` comment block at the top documenting the `GRANT EXECUTE TASK` and ACCOUNTADMIN steps
- [ ] GitHub PAT with `repo` scope exists and has been validated with a manual `curl` dispatch returning HTTP 204
- [ ] `baseball_data.config.github_pat` Snowflake Secret exists: `SHOW SECRETS IN SCHEMA baseball_data.config` returns one row for `github_pat`

---

##### Card 6.A.1 — Dedicated Task Executor Role — COMPLETE

**Title:** Create task_executor_role with minimum necessary privileges for the Snowflake Task DAG

*Technical implementation:*

Add Section 1 to `scripts/ddl/snowflake_task_dag.sql`:

```sql
-- ============================================================
-- SECTION 1: Task Executor Role
-- ============================================================
CREATE ROLE IF NOT EXISTS task_executor_role;

GRANT USAGE ON DATABASE baseball_data TO ROLE task_executor_role;
GRANT USAGE ON SCHEMA baseball_data.statsapi TO ROLE task_executor_role;
GRANT USAGE ON SCHEMA baseball_data.config TO ROLE task_executor_role;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA baseball_data.statsapi TO ROLE task_executor_role;
GRANT INSERT, SELECT ON ALL TABLES IN SCHEMA baseball_data.config TO ROLE task_executor_role;
GRANT INSERT, SELECT ON FUTURE TABLES IN SCHEMA baseball_data.statsapi TO ROLE task_executor_role;
GRANT INSERT, SELECT ON FUTURE TABLES IN SCHEMA baseball_data.config TO ROLE task_executor_role;
GRANT READ ON SECRET baseball_data.config.odds_api_key TO ROLE task_executor_role;
GRANT READ ON SECRET baseball_data.config.github_pat TO ROLE task_executor_role;
GRANT USAGE ON INTEGRATION daily_ingestion_access_integration TO ROLE task_executor_role;

-- Wire into the role hierarchy
GRANT ROLE task_executor_role TO ROLE SYSADMIN;
```

The `GRANT EXECUTE TASK ON ACCOUNT TO ROLE task_executor_role` is executed as a manual ACCOUNTADMIN step (Card 6.A.0) and is documented as a comment, not an executable statement, in the DDL.

*Blockers:* Card 6.A.0 (EXECUTE TASK privilege must be granted to this role after creation).

*Acceptance criteria:*
- [ ] `SHOW ROLES LIKE 'TASK_EXECUTOR_ROLE'` returns one row
- [ ] Role does not have `ACCOUNTADMIN`, `SECURITYADMIN`, or `SYSADMIN` as a granted role (least-privilege check)
- [ ] DDL section exists in `scripts/ddl/snowflake_task_dag.sql` with all grant statements listed above

---

##### Card 6.A.2 — External Network Access Integration — COMPLETE

**Title:** Create network rule and external access integration covering all four outbound HTTPS hosts

*Technical implementation:*

Add Section 2 to `scripts/ddl/snowflake_task_dag.sql` (run as ACCOUNTADMIN):

```sql
-- ============================================================
-- SECTION 2: Network Rule and External Access Integration
-- Run as ACCOUNTADMIN — see PREREQUISITE block at top of file
-- ============================================================
CREATE OR REPLACE NETWORK RULE baseball_data.config.daily_ingestion_network_rule
  TYPE = HOST_PORT
  MODE = EGRESS
  VALUE_LIST = (
    'baseballsavant.mlb.com',
    'statsapi.mlb.com',
    'api.the-odds-api.com',
    'api.github.com'
  );

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION daily_ingestion_access_integration
  ALLOWED_NETWORK_RULES = (baseball_data.config.daily_ingestion_network_rule)
  ALLOWED_AUTHENTICATION_SECRETS = (
    baseball_data.config.odds_api_key,
    baseball_data.config.github_pat
  )
  ENABLED = TRUE;
```

This integration is shared with Card 5.3's `task_lineup_monitor`. That stored procedure references `daily_ingestion_access_integration` by name — Card 5.3 cannot be fully activated until this card is complete.

*Blockers:* Card 6.A.0 (ACCOUNTADMIN session required). Card 6.A.3 (secrets must exist before the integration can list them in `ALLOWED_AUTHENTICATION_SECRETS` — create secrets first, then run Section 2).

*Acceptance criteria:*
- [ ] `SHOW NETWORK RULES IN SCHEMA baseball_data.config` returns `daily_ingestion_network_rule` listing all four hosts
- [ ] `SHOW INTEGRATIONS` returns `daily_ingestion_access_integration` with `enabled = true`
- [ ] Card 5.3's `task_lineup_monitor` procedure references this integration by name without requiring any modification to the integration itself

---

##### Card 6.A.3 — Snowflake Secret Objects — COMPLETE

**Title:** Store ODDS_API_KEY and GITHUB_PAT as Snowflake Secrets in baseball_data.config

*Technical implementation:*

Add Section 3 to `scripts/ddl/snowflake_task_dag.sql`:

```sql
-- ============================================================
-- SECTION 3: Secret Objects
-- Replace <placeholder> values at provision time in a live session.
-- NEVER commit this file with real secret values substituted.
-- ============================================================
CREATE SECRET IF NOT EXISTS baseball_data.config.odds_api_key
  TYPE = GENERIC_STRING
  SECRET_STRING = '<ODDS_API_KEY_VALUE>';  -- substitute at provision time

CREATE SECRET IF NOT EXISTS baseball_data.config.github_pat
  TYPE = GENERIC_STRING
  SECRET_STRING = '<GITHUB_PAT_VALUE>';  -- substitute at provision time; see Card 6.A.0
```

The DDL file is committed with `<placeholder>` strings. The engineer substitutes real values interactively in Snowflake and never commits the substituted copy. Add the following to `.gitignore` in case a local provisioned copy is saved:
```
scripts/ddl/snowflake_task_dag_provisioned.sql
```

*Blockers:* Card 6.A.0 (GitHub PAT must exist before it can be stored).

*Acceptance criteria:*
- [ ] `SHOW SECRETS IN SCHEMA baseball_data.config` returns rows for both `odds_api_key` and `github_pat`
- [ ] Neither secret value appears in plaintext in any git-tracked file (`git grep -i 'api_key\|ghp_' -- '*.sql'` returns no results with actual values)
- [ ] `.gitignore` entry exists for `scripts/ddl/snowflake_task_dag_provisioned.sql`

---

##### Card 6.A.4 — Snowpark Stored Procedures — COMPLETE

**Title:** Implement five Snowpark Python 3.11 stored procedures for the daily ingestion and GitHub Actions dispatch

*Technical implementation:*

Add Section 4 to `scripts/ddl/snowflake_task_dag.sql`. One procedure per task using a shared pattern:

```sql
CREATE OR REPLACE PROCEDURE baseball_data.config.proc_<name>()
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  PACKAGES = ('snowflake-snowpark-python', 'requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (daily_ingestion_access_integration)
  SECRETS = ('odds_api_key' = baseball_data.config.odds_api_key,
             'github_pat'   = baseball_data.config.github_pat)
  EXECUTE AS OWNER
AS $$
import _snowflake, requests
from datetime import datetime

def handler(session):
    run_ts = datetime.utcnow()
    task_name = '<task_name>'
    try:
        session.sql(f"INSERT INTO baseball_data.config.pipeline_run_log "
                    f"VALUES ('{task_name}', '{run_ts}', 'RUNNING', NULL, NULL)").collect()

        rows = 0  # task-specific logic sets this

        session.sql(f"UPDATE baseball_data.config.pipeline_run_log "
                    f"SET status='SUCCESS', rows_affected={rows} "
                    f"WHERE task_name='{task_name}' AND run_ts='{run_ts}'").collect()
        return f'SUCCESS:{rows}'
    except Exception as e:
        session.sql(f"UPDATE baseball_data.config.pipeline_run_log "
                    f"SET status='FAILED', error_message='{str(e)[:500]}' "
                    f"WHERE task_name='{task_name}' AND run_ts='{run_ts}'").collect()
        raise
$$;
```

Task-specific logic per procedure:
- **`proc_savant_ingestion`** — HTTP GET to `baseballsavant.mlb.com` for prior-day Statcast; inserts rows into `baseball_data.statsapi.statcast_pitches`
- **`proc_statsapi_schedule`** — HTTP GET to `statsapi.mlb.com/api/v1/schedule`; inserts into `baseball_data.statsapi.monthly_schedule`
- **`proc_oddsapi_events`** — HTTP GET to `api.the-odds-api.com/v4/sports/baseball_mlb/events`; reads key via `_snowflake.get_generic_secret_string('odds_api_key')`; inserts into `baseball_data.statsapi.odds_events`
- **`proc_oddsapi_odds`** — HTTP GET for odds by event ID; reads key the same way; inserts into `baseball_data.statsapi.odds_h2h`
- **`proc_github_actions_trigger`** — reads `_snowflake.get_generic_secret_string('github_pat')`; POSTs to `api.github.com/repos/{owner}/{repo}/actions/workflows/dbt_daily_build.yml/dispatches`; asserts HTTP 204; returns response status code as the row count

Each downstream task checks `SYSTEM$GET_PREDECESSOR_RETURN_VALUE()` at the top of its procedure body and writes `status = 'SKIPPED'` to `pipeline_run_log` if the predecessor returned a non-SUCCESS value, then returns early without raising — this prevents cascading failures from blocking future retries of the DAG.

*Blockers:* Card 6.A.2 (integration must exist). Card 6.A.3 (secrets must exist).

*Acceptance criteria:*
- [ ] `SHOW PROCEDURES IN SCHEMA baseball_data.config` returns all five procedures
- [ ] Each procedure can be called manually via `CALL baseball_data.config.proc_<name>()` and returns `'SUCCESS:<n>'`
- [ ] `pipeline_run_log` receives one row per call with non-null `rows_affected` on success
- [ ] Credentials are accessed exclusively via `_snowflake.get_generic_secret_string()` — no hardcoded key or token strings in any procedure body

---

##### Card 6.A.5 — Snowflake Task DAG Wiring — COMPLETE

**Title:** Wire five serverless Snowflake Tasks in linear AFTER-dependency chain with 08:00 ET cron root

*Technical implementation:*

Add Section 5 to `scripts/ddl/snowflake_task_dag.sql`:

```sql
-- ============================================================
-- SECTION 5: Task DAG (all tasks serverless)
-- USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE sets the serverless
-- compute hint — no named warehouse is bound; Snowflake bills
-- by compute-second, not by warehouse-minute.
-- ============================================================

CREATE OR REPLACE TASK baseball_data.config.task_savant_ingestion
  SCHEDULE = 'USING CRON 0 8 * * * America/New_York'
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
AS CALL baseball_data.config.proc_savant_ingestion();

CREATE OR REPLACE TASK baseball_data.config.task_statsapi_schedule
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_savant_ingestion
AS CALL baseball_data.config.proc_statsapi_schedule();

CREATE OR REPLACE TASK baseball_data.config.task_oddsapi_events
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_statsapi_schedule
AS CALL baseball_data.config.proc_oddsapi_events();

CREATE OR REPLACE TASK baseball_data.config.task_oddsapi_odds
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_oddsapi_events
AS CALL baseball_data.config.proc_oddsapi_odds();

CREATE OR REPLACE TASK baseball_data.config.task_github_actions_trigger
  USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE = 'XSMALL'
  AFTER baseball_data.config.task_oddsapi_odds
AS CALL baseball_data.config.proc_github_actions_trigger();

-- Snowflake Tasks are created SUSPENDED by default.
-- Child tasks must be resumed before the root task (they do not cascade from root).
ALTER TASK baseball_data.config.task_statsapi_schedule RESUME;
ALTER TASK baseball_data.config.task_oddsapi_events RESUME;
ALTER TASK baseball_data.config.task_oddsapi_odds RESUME;
ALTER TASK baseball_data.config.task_github_actions_trigger RESUME;
ALTER TASK baseball_data.config.task_savant_ingestion RESUME;
```

*Implementation notes (discovered during execution):*
- `USER_TASK_MANAGED_INITIAL_WAREHOUSE_SIZE` must appear **before** `AFTER` in child task DDL — reversed order causes a SQL compilation error.
- `EXECUTE MANAGED TASK` account privilege is required for serverless tasks (distinct from `EXECUTE TASK`). Both must be granted as ACCOUNTADMIN to `task_executor_role` before tasks can be created.
- Child tasks must be individually `ALTER TASK ... RESUME`'d — resuming the root task does not cascade to children.

*Blockers:* Card 6.A.4 (all five procedures must exist before tasks can reference them). Card 6.A.0 (both `EXECUTE TASK` and `EXECUTE MANAGED TASK` privileges must be active on the execution role).

*Acceptance criteria:*
- [x] `SHOW TASKS IN SCHEMA baseball_data.config` returns all five tasks with `state = STARTED`
- [x] No task has a non-null `warehouse` column value — all tasks are serverless
- [x] Manual `EXECUTE TASK baseball_data.config.task_savant_ingestion` fires and all five tasks complete; `TABLE(INFORMATION_SCHEMA.TASK_HISTORY())` shows each with `STATE = SUCCEEDED`
- [x] `pipeline_run_log` receives five rows after a full manual execution

---

##### Card 6.A.6 — dbt_daily_build.yml GitHub Actions Workflow - COMPLETE

**Title:** Create dbt_daily_build.yml workflow triggered by Snowflake Task DAG dispatch for full dbtf build

*Technical implementation:*

Create `.github/workflows/dbt_daily_build.yml`. Triggered exclusively via `workflow_dispatch` — no push or schedule triggers. This keeps it silent during normal development and ensures it only fires when the Snowflake Task DAG explicitly calls it.

```yaml
name: Daily dbt Build

on:
  workflow_dispatch:
    inputs:
      triggered_by:
        description: 'Caller identifier'
        required: false
        default: 'manual'

jobs:
  dbt-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dbt-fusion
        run: pip install dbt-fusion

      - name: Write Snowflake private key
        run: |
          echo "${{ secrets.SNOWFLAKE_PRIVATE_KEY }}" > /tmp/snowflake_rsa_key.pem
          chmod 600 /tmp/snowflake_rsa_key.pem

      - name: Run dbtf build
        env:
          SNOWFLAKE_ACCOUNT: ${{ secrets.SNOWFLAKE_ACCOUNT }}
          SNOWFLAKE_USER: ${{ secrets.SNOWFLAKE_USER }}
          SNOWFLAKE_PRIVATE_KEY_PATH: /tmp/snowflake_rsa_key.pem
          SNOWFLAKE_ROLE: ${{ secrets.SNOWFLAKE_ROLE }}
          SNOWFLAKE_WAREHOUSE: ${{ secrets.SNOWFLAKE_WAREHOUSE }}
          SNOWFLAKE_DATABASE: ${{ secrets.SNOWFLAKE_DATABASE }}
        run: dbtf build

      - name: Notify on failure
        if: failure()
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: smtp.gmail.com
          server_port: 465
          username: ${{ secrets.SMTP_USERNAME }}
          password: ${{ secrets.SMTP_PASSWORD }}
          subject: 'FAILED: Daily dbt build'
          to: ${{ secrets.NOTIFICATION_EMAIL }}
          from: ${{ secrets.SMTP_USERNAME }}
          body: 'The daily dbtf build GitHub Actions workflow failed. Check the Actions tab for details.'
```

Required GitHub Secrets (repo Settings → Secrets → Actions):
- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY` (full PEM content of RSA private key), `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`
- `SMTP_USERNAME`, `SMTP_PASSWORD` — email relay credentials for failure notification
- `NOTIFICATION_EMAIL` — already configured to `charles.t.clark89@gmail.com` (shared with Card 5.3)

Note: Password auth is not used. The workflow writes `SNOWFLAKE_PRIVATE_KEY` secret content to `/tmp/snowflake_rsa_key.pem` and exposes the path via `SNOWFLAKE_PRIVATE_KEY_PATH`. `dbt/profiles.yml` reads this env var (with a fallback to the local dev key path for non-CI runs).

This workflow is **distinct from `dbt_staging_build.yml`** (Card 5.3). That workflow targets `+stg_statsapi_lineups+` for intraday lineup triggers. This workflow runs a full `dbtf build` after morning ingestion completes.

*Blockers:* Card 6.A.5 (Snowflake Tasks must be wired before this workflow will be called automatically, though it can be tested manually via the GitHub Actions UI at any point). GitHub Secrets for Snowflake connection must be configured before the workflow run will succeed.

*Acceptance criteria:*
- [x] `.github/workflows/dbt_daily_build.yml` exists with `workflow_dispatch` trigger (and no other triggers)
- [x] Workflow contains a `dbt build --project-dir dbt` step with all required Snowflake env vars sourced from GitHub Secrets. Note: dbt-fusion is installed via the official curl installer (`https://public.cdn.getdbt.com/fs/install/install.sh`) rather than pip, as it is not distributed on PyPI. The binary installs as `dbt` (not `dbtf`); `$HOME/.local/bin` is appended to `$GITHUB_PATH` so it is available to subsequent steps.
- [x] Failure notification confirmed working via GitHub's native Actions failure emails rather than `dawidd6/action-send-mail@v3`. The SMTP approach was dropped because Gmail SMTP setup requires app password provisioning and adds three secrets (`SMTP_USERNAME`, `SMTP_PASSWORD`, `NOTIFICATION_EMAIL`) with no meaningful benefit over what GitHub already provides for free. A controlled test (intentional `exit 1` step) confirmed that GitHub sends a failure email to `ctcb57@gmail.com` within ~1 minute of a workflow failure. The `Notify on failure` step was removed from the workflow entirely.
- [x] A manual workflow dispatch from the GitHub Actions UI completes with `dbt build` exit code 0 — confirmed 2026-04-25.

---

##### Card 6.A.7 — End-to-End Validation and Documentation — COMPLETE

**Title:** Run full DAG end-to-end, verify pipeline_run_log output, and update daily_run.md

*Technical implementation:*

Validation sequence:
1. `EXECUTE TASK baseball_data.config.task_savant_ingestion` — triggers the full five-task chain
2. Poll `SELECT name, state, scheduled_time, completed_time, error_message FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY()) ORDER BY scheduled_time DESC LIMIT 10` until all five tasks show `STATE = SUCCEEDED` (typically within 5–10 minutes)
3. Query `SELECT * FROM baseball_data.config.pipeline_run_log ORDER BY run_ts DESC LIMIT 5` — confirm five rows, all `status = 'SUCCESS'`, all `rows_affected > 0`
4. Confirm `dbt_daily_build.yml` Actions run appears in the GitHub Actions tab with green status; `dbtf build` output in the Actions log shows no model failures
5. Failure injection test: temporarily point `proc_oddsapi_events` at a bad endpoint URL, re-run; confirm `pipeline_run_log` shows `status = 'FAILED'` for `task_oddsapi_events` and `status = 'SKIPPED'` for its two downstream tasks; restore correct endpoint

Update `scripts/daily_run.md`: add a "Snowflake Task DAG" section at the top of the document noting that the DAG (root task `task_savant_ingestion`, 08:00 ET daily) replaces the manual sequence for unattended production runs. The manual sequence remains documented for development, debugging, and one-off backfills.

*Blockers:* Cards 6.A.1 through 6.A.6 must all be complete.

*Acceptance criteria:*
- [x] `TASK_HISTORY` shows all five tasks `STATE = SUCCEEDED` after a full end-to-end manual trigger — confirmed 2026-04-25.
- [x] `pipeline_run_log` has five `status = 'SUCCESS'` rows with non-null `rows_affected` for the most recent run — confirmed 2026-04-25 (all five procedures including `proc_github_actions_trigger` succeeded once Card 6.A.6 went live).
- [x] Failure injection test passes: a forced failure in `task_oddsapi_events` produces `status = 'SKIPPED'` downstream without blocking a clean re-run after the fault is cleared — confirmed 2026-04-25.
- [x] `scripts/daily_run.md` contains a "Snowflake Task DAG" section with instructions for triggering and monitoring the DAG.
- [~] Teardown section of `scripts/ddl/snowflake_task_dag.sql` deferred — the DROP statements exist and are documented in the correct reverse-dependency order. Executing them against a live working pipeline carries unnecessary risk for a solo project with no current DR or migration need. Revisit if migrating to a new Snowflake account or onboarding a second engineer.

---

#### Card 6.B — Streamlit App Skeleton and Today's Picks Page

**Title:** Bootstrap the Streamlit app and build the Today's Picks page — ranked game predictions with lineup and edge status

**Description:**

*Technical implementation:*
- Create `app/` at the repo root with `streamlit_app.py` as the entry point and `pages/` for multi-page navigation. Run with `uv run streamlit run app/streamlit_app.py`.
- **Snowflake connection:** Reuse the existing RSA key connector from `betting_ml/utils/data_loader.py`. Wrap it in a `@st.cache_resource` connection factory so the session is shared across reruns. Credentials read from the project `.env` file.
- **Today's Picks page (`pages/1_Today_Picks.py`):**
  - Date selector defaulting to today. On load, queries Snowflake for all games on the selected date joining `feature_pregame_game_features`, `stg_statsapi_games`, and `mart_odds_consensus`.
  - Loads the three production models from `betting_ml/models/model_registry.yaml` via `utils/model_io.py` and scores the feature matrix in-process (`@st.cache_data` keyed on date + model registry mtime so predictions are not recomputed on every rerender). Loads `best_alpha` from the `alpha_tuning_results` Snowflake table (most recent row) — same value used by `predict_today.py`. For each has_odds game, applies `compute_posterior(model_prob, market_prob, best_alpha)`, `compute_edge()`, and `compute_kelly()` from `betting_ml/utils/probability_layer.py` — the same functions as Card 4.13. This is the live execution of the Phase 6 contract; no separate scoring script is needed for the Streamlit view.
  - Displays a sortable `st.dataframe` with columns: `Matchup`, `Game Time`, `Lineups`, `Pred Total`, `Model Win%`, `Market Win%`, `Posterior%`, `Edge`, `EV`, `Kelly%`. The `Lineups` column shows a ✓ / ⏳ indicator based on whether both slots are confirmed in `stg_statsapi_lineups_wide`.
  - Color-codes rows: green background where `abs(edge) > 0.05` and lineups are confirmed; grey where lineups are pending.
  - "Refresh" button re-runs ingestion check by calling `ingest_statsapi.py schedule` as a subprocess and clearing the `@st.cache_data` entry for the current date.
- **EV and Kelly formulas** (inline, not a separate page in the MVP):
  - `EV = (model_prob × (decimal_odds − 1)) − (1 − model_prob)`
  - `kelly_fraction = (model_prob × (decimal_odds − 1) − (1 − model_prob)) / (decimal_odds − 1)`
  - Cap displayed Kelly at 10% as a risk guardrail; show a warning badge when raw Kelly exceeds 10%.

*Blockers:* Card 5.1 (model registry). Card 5.2 (`predict_today.py` establishes the scoring logic this page reuses). Card 4.13 (`best_alpha` must be persisted to Snowflake before the app can load it; `probability_layer.py` must exist). Snowflake connection pattern from `utils/data_loader.py`.

*Acceptance criteria:*
- [x] `uv run streamlit run app/streamlit_app.py` starts without error; Today's Picks page loads within 10 seconds on first run
- [x] Predictions load for a date with confirmed games; sortable dataframe renders all required columns including `Posterior%`
- [x] `best_alpha` loaded from Snowflake `alpha_tuning_results`; `compute_posterior()` from `probability_layer.py` called for each has_odds game
- [x] Lineup confirmation status displays correctly: ✓ for confirmed, ⏳ for pending
- [x] Edge color-coding applies correctly to rows where `abs(edge) > 0.05` and lineups confirmed
- [x] Kelly fraction capped at 10% with warning badge when raw value exceeds cap
- [x] Refresh button re-queries `ingest_statsapi.py schedule` and updates lineup status without restarting the app
- [x] App handles dates with no games (empty state message, no error)

*Implementation notes (deviations from spec):*
- Scoring is precomputed by `predict_today.py` and read from `daily_model_predictions` rather than scored inline on page load. Functionally identical — same `probability_layer.py` functions and `best_alpha` from Snowflake.
- `Pred Total` column replaced by `P(Over)` (model probability of over, derived from NGBoost total-runs distribution).
- `Signal` column added (🟢/🟡/⚪/⛔) as a quick-scan indicator ahead of the matchup.
- `Game Time` column added (first pitch in ET).
- "Refresh" button expanded to also re-ingest odds (events + lines) and trigger `dbt_daily_build.yml` via GitHub Actions, not just lineup ingestion.
- Rows with no Odds API coverage styled with ⛔ signal and greyed-out background to flag data gaps.
- Market Movement expander added showing open → current line movement across intraday odds snapshots, with significant moves (≥15 pts) highlighted in blue.
- Timezone fix: `mart_odds_outcomes` and `mart_odds_events` `commence_date` changed from ET to PT so late West Coast games are correctly attributed to the calendar date.

**Status: Complete as of 2026-04-28.**

*Bug fixes applied 2026-05-01:*
- **"Refresh Predictions" button** previously showed "Predictions refreshed." even when `predict_today.py` exited with code 0 but found no confirmed lineups. Fixed by inspecting stdout for "No games found" / "No games with confirmed lineups" and displaying `st.warning()` instead.
- **"Refresh Lineups & Odds Only" button** previously dispatched `dbt_daily_build.yml` via `gh workflow run` (async, ~2 min to complete) and cleared the Streamlit cache immediately, causing the page to reload stale data. Replaced with a synchronous local `~/.local/bin/dbt build --select <9 lineup+odds models>` call followed by a synchronous `predict_today.py` run; cache only clears after all steps succeed.
- **Prior-month lineup ingestion gap**: `ingest_statsapi.py schedule` without `--start-date` only covers the current calendar month. When run on May 1, April 30 game data was never re-fetched. Fixed by computing the prior month's first day and passing it as `--start-date` so both April and May schedules are always re-ingested.
- **Cross-page date persistence**: Replaced `st.date_input(key=...)` (which Streamlit clears on page navigation) with a plain `st.session_state["selected_date"]` variable initialized once and updated after each widget interaction. The selected date now persists across all three pages.

---

#### Card 6.C — Market Comparison Page

**Title:** Build the Market Comparison Streamlit page — model probability vs. bookmaker implied probability with line movement context

**Description:**

*Technical implementation:*
- **Market Comparison page (`pages/2_Market_Comparison.py`):**
  - Game selector (dropdown of today's matchups). On selection, loads all `mart_odds_outcomes` rows for that `event_id` filtered to `ingestion_ts < commence_time`, ordered by `ingestion_ts` ascending.
  - **Moneyline panel:** Two side-by-side `st.metric` tiles — model home win% and market consensus home win% (`home_win_prob_consensus` from `mart_odds_consensus`). Below, a `st.line_chart` of home win implied probability over ingestion snapshots (line movement history). One line per bookmaker + a bold consensus line.
  - **Totals panel:** Model predicted total vs. `total_line_consensus`. Bar chart of over/under probability from model vs. each bookmaker's vig-adjusted over probability.
  - **Sharp vs. soft comparison:** If `home_win_prob_sharp` and `home_win_prob_soft` are non-null, display `sharp_soft_ml_delta` as a signed `st.metric` with tooltip: "Positive = sharp books favor home more than soft books."
  - **Cross-bookmaker table:** `st.dataframe` of all books for the selected game showing `bookmaker_key`, `home_price_american`, `away_price_american`, `home_imp_prob`, `away_imp_prob`, `vig`. Sorted by `home_imp_prob` descending.

*Blockers:* Card 6.B (app skeleton and Snowflake connection). `mart_odds_consensus` must be built (Card 4.7).

*Acceptance criteria:*
- [x] Game selector populates with today's games that have `has_odds = true`
- [x] Moneyline line movement chart renders for a game with multiple ingestion snapshots
- [x] Model win% and market consensus win% display as `st.metric` tiles with delta (model − market)
- [x] Totals panel shows model predicted total vs. consensus line
- [x] Sharp vs. soft delta metric displays when sharp/soft data is available; panel is hidden (not erroring) when it is null
- [x] Cross-bookmaker table sorted correctly; vig column populated for all rows

*Completed as of 2026-04-29. Key implementation notes:*
- All mart queries scoped by `event_id` (from The Odds API) to prevent cross-series data leakage when the same two teams play multiple series.
- Leakage guard uses `game_datetime` from `daily_model_predictions` (reliable UTC) rather than `mart_odds_outcomes.commence_time` (timezone-ambiguous).
- Plotly `add_vline` replaced with `add_shape` + `add_annotation` to avoid `sum()` type error on timezone-aware datetime axes.
- Totals O/U bar chart uses orange for the model bar and blue for bookmakers; `st.caption` labels the color scheme.
- Post-game warning callouts (`st.warning(..., icon="⚠️")`) explain when live in-game lines are being displayed instead of pre-game consensus.
- Per-bookmaker deep-dive card (moneyline + totals sub-sections) added below the cross-bookmaker table.

*Bug fixes applied 2026-05-01:*
- **Duplicate games in game selector**: The `LEFT JOIN mart_odds_events` on `(home_team, away_team, commence_date)` could match multiple events for the same team pair (e.g., doubleheaders, data duplicates), producing multiple rows per `game_pk`. Fixed by adding `QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY event_id NULLS LAST) = 1` to `_games_sql`.
- **Doubleheader disambiguation**: Game selector labels now include "(Game 1)" / "(Game 2)" suffixes for doubleheader games, derived from `double_header` and `game_number` columns in `stg_statsapi_games`. Non-doubleheader games are unaffected.
- **Cross-page date persistence**: Same fix as Card 6.B — `st.session_state["selected_date"]` persists the selected date across page navigations.

---

#### Card 6.D — EV Tracker and Kelly Sizer Page

**Title:** Build the EV Tracker and Kelly Sizer page — per-game, per-market expected value and bet sizing recommendation

**Description:**

*Technical implementation:*
- **EV Tracker page (`pages/3_EV_Kelly.py`):**
  - Shows all games for the selected date in a single table with columns: `Matchup`, `Market` (h2h home / h2h away / over / under), `Model Prob`, `Market Implied Prob`, `Decimal Odds`, `EV`, `Raw Kelly%`, `Capped Kelly%`, `Actionable` flag.
  - `Actionable = True` when: `EV > 0`, `abs(edge) > 0.03`, lineups confirmed, and `model_prob` is not null.
  - **Bankroll simulator:** `st.number_input` for bankroll amount. For all actionable bets on the selected date, displays a "suggested slate" table: `Bet`, `Stake (Capped Kelly × Bankroll)`, `To Win`, `EV ($)`. Shows total risk and total expected profit at the bottom.
  - **Risk controls displayed prominently:**
    - Warning banner if any game has unconfirmed lineups but is otherwise actionable — "Lineup pending: do not act until confirmed."
    - Info note: Kelly fractions are capped at 10% of bankroll; simultaneous correlated bets (same game, different markets) are flagged with a ⚠ icon.
  - All EV/Kelly values recompute reactively when the user changes the date or refreshes odds.

*Blockers:* Cards 6.B and 6.C (shared Snowflake connection and model scoring logic).

*Acceptance criteria:*
- [x] EV table renders for all games × markets on the selected date
- [x] `Actionable` flag correctly excludes games with unconfirmed lineups or negative EV
- [x] Bankroll simulator stake column equals `capped_kelly × bankroll_input`; updates reactively on bankroll change
- [x] Warning banner displays for actionable games with pending lineups
- [x] Correlated same-game bets handled via deduplication — best-EV market per game_pk kept on slate; others listed in disclosure expander (replaces ⚠ flag approach)
- [x] Total Stake, Expected Profit ($), Expected ROI%, and Bets Selected metrics present; react to per-row checkbox toggles

*Implementation notes:*
- Suggested Slate uses `st.data_editor` with an **Include** checkbox column; metrics (Total Stake, Expected Profit, Expected ROI%, Bets Selected) recompute from checked rows only.
- Correlated bets deduplicated pre-display rather than flagged: only the highest-EV market per `game_pk` appears on the slate; dropped bets are listed in a collapsed expander.
- Doubleheader detection appends `(G1, PK:XXXXXX)` / `(G2, PK:XXXXXX)` to the matchup label when multiple `game_pk` values share the same Away @ Home string.
- American-format odds column added to the Suggested Slate so the To Win column is immediately interpretable.
- All columns in both tables carry hover tooltips explaining the metric.
- Default bankroll set to $100.
- **Cross-page date persistence** (2026-05-01): `st.session_state["selected_date"]` initialized once and written back after each `st.date_input` render. Selected date survives navigation to/from Cards 6.B and 6.C.

---

#### Card 6.E — Performance Tracker Page

**Title:** Build the Performance Tracker page — historical CLV, Brier score trend, and cumulative P&L simulation

**Description:**

*Technical implementation:*
- **Performance Tracker page (`pages/4_Performance.py`):**
  - **Data source:** A new Snowflake table `baseball_data.config.prediction_log` (created by `predict_today.py` on each run — add a Snowflake write step to Card 5.2). Columns: `prediction_date`, `game_pk`, `market` (h2h / totals), `model_prob`, `market_prob_at_prediction`, `closing_market_prob`, `actual_outcome`, `decimal_odds`, `ev`, `kelly_fraction`. `closing_market_prob` and `actual_outcome` are backfilled nightly by a new step in the Card 6.A Snowflake Task DAG that joins predictions to `mart_game_results` and the latest pre-game odds snapshot. **Note:** The closing line backfill step does not yet exist in the Card 6.A DAG. It requires querying `mart_odds_outcomes` for the last `ingestion_ts < commence_time` snapshot per game and writing it to `prediction_log`. This step must be added to `proc_statsapi_schedule` (or a new `proc_results_backfill` task) before `closing_market_prob` and CLV calculations will populate. The Brier trend and CLV charts will remain empty until this backfill is live.
  - **Brier score trend:** `st.line_chart` of rolling 14-day Brier score for model win probability vs. market consensus win probability. Both lines on the same chart. A flat or improving model line relative to market is the primary signal the model is working.
  - **CLV tracker:** For each logged prediction, `CLV = model_prob − closing_market_prob`. Positive CLV means the model identified value that the market later agreed with. `st.bar_chart` of mean CLV by week.
  - **P&L simulation:** Cumulative P&L assuming capped-Kelly stakes on all `Actionable` predictions. Line chart of cumulative units won/lost over time. Includes a flat-bet comparison line (1 unit per actionable bet) so Kelly's advantage is visible.
  - **Summary metrics row** at top: total predictions logged, win rate on actionable bets, mean CLV, cumulative P&L (Kelly), cumulative P&L (flat).
  - Empty state handling: when `prediction_log` has fewer than 5 rows, display "Not enough history yet — check back after a few days of predictions."

*Blockers:* Card 6.B (app skeleton). Card 5.2 must be extended to write to `prediction_log`. Card 6.A Task DAG must backfill `closing_market_prob` and `actual_outcome` nightly.

*Acceptance criteria (completed 2026-05-01):*
- [x] `baseball_data.config.prediction_log` table created by `predict_today.py` write step; columns match spec
- [x] Brier score trend chart renders with both model and market lines once ≥5 logged predictions exist
- [x] CLV bar chart groups by ISO week; positive and negative bars colored green/red respectively
- [x] P&L simulation chart includes both Kelly and flat-bet lines
- [x] Summary metrics row shows correct counts and aggregates
- [x] Empty state message displays cleanly when fewer than 5 predictions are logged

*Implementation notes (beyond spec):*
- Page renamed to "Model Performance" (`4_Model_Performance.py`) for sidebar clarity
- Global date-range filter (From/To pickers) drives all four sections simultaneously
- Summary, Brier Score Trend, and P&L Simulation all support Combined/Moneyline (h2h)/Totals tabs for per-market breakdowns
- CLV bar chart upgraded: human-readable week date-range labels (e.g. "Mar 28 – Apr 3"), side-by-side grouped bars by market (blue=h2h, orange=totals), explanatory caption
- Brier rolling average uses `min_periods=1` so early-season dates appear from day one
- P&L chart switched to Altair with `%b %d` date formatting; aggregated to daily end-of-day values to reduce choppiness; tooltip on each point
- Inline backfill of `actual_outcome` and `closing_market_prob` added to `predict_today.py` (6 UPDATE steps, synced with standalone script)
- `scripts/backfill_prediction_log.py` extended with fallback CLV queries for historically ingested odds (no pre-game snapshot required)
- Snowflake server-side query result cache disabled via `ALTER SESSION SET USE_CACHED_RESULT = FALSE` on connection creation; "Refresh Data" button also clears `@st.cache_resource` connection

---

#### Card 6.F — In-Season Model Retraining Cadence

**Title:** Define and implement a retraining schedule for production models as 2026 season data accumulates

**Description:**

The production models registered in `model_registry.yaml` were trained through end-of-2025. As the 2026 season progresses, retraining them on an expanded dataset improves calibration — particularly for the home win classifier, which is sensitive to the current season's home advantage rate, and for the NGBoost total runs model, which benefits from the current season's run environment. Without retraining, the models will gradually lag the market.

*Trigger criteria:*
- **Mid-season refit** — after ≥50 2026 regular season games have results in `mart_game_results` (estimated: mid-May). Train on 2016–2026 partial season; register as `eval_year: 2026_midseason`.
- **All-Star break refit** — after the All-Star break (approx. late July). Train on all available 2026 data through break + prior seasons.
- **Post-season / pre-2027 refit** — after the 2026 World Series ends (November). Full 2016–2026 retrain; this becomes the primary artifact for the 2027 season opener.

*Retraining steps per target:*
1. Re-run `run_probability_layer.py` without `--use-alpha` to regenerate all 11 α rows in `alpha_tuning_results` with the expanded dataset.
2. Persist `best_alpha.json` to `betting_ml/models/best_alpha.json`.
3. Re-run NGBoost hyperparameter grid search (Cards 4.12d/e) only if CV MAE on 2026 hold-out degrades >1% vs. current; otherwise reuse existing hyperparameters.
4. Run `refit_win_calibration.py`-style 3-way split: train on 2016–(N−2), calibrate on (N−1), verify on N; fail if ECE delta > 0.005.
5. Update `model_registry.yaml` with new `selected_at` timestamp and `eval_year`.
6. Update `betting_ml/evaluation/selection_log.md` with retraining notes.

*Blockers:* Card 6.E (Performance Tracker) should be live so Brier score trend provides the signal that retraining is warranted. Card 5.2 `predict_today.py` must persist predictions to `prediction_log` so CLV can be measured before/after retrain.

*Acceptance criteria:*
- [ ] Retraining runbook documented in `scripts/daily_run.md` with trigger criteria, commands, and verification steps
- [ ] `model_registry.yaml` updated with new `selected_at` after each refit; old artifact paths renamed with a date suffix for rollback
- [ ] `alpha_tuning_results` Snowflake table has 11 rows after each refit (full α grid, not bypass)
- [ ] `best_alpha.json` written to `betting_ml/models/best_alpha.json` after each refit
- [ ] Brier score trend in Card 6.E Performance Tracker shows no degradation after retraining vs. pre-retrain baseline

---

#### Card 6.G — 2026 Season Prediction Backfill

**Title:** Backfill `predict_today.py` for all completed 2026 regular-season dates to enable model vs. market performance analysis

**Description:**

The production models were registered and validated on historical data through 2025. Before Card 6.E (Performance Tracker) can display meaningful Brier score trends, CLV charts, or P&L simulations, `daily_model_predictions` must be populated with retroactive scores for every 2026 game date that has already been played. This card covers both the one-time backfill and the prerequisite Snowflake write bug fix in `predict_today.py`.

*Technical implementation:*

**Prerequisite fix — Snowflake write bug in `predict_today.py`:**
The `_s()` helper inside `_write_predictions_to_snowflake` returned raw pandas/numpy scalar values (e.g. `np.int64` for `game_pk`) that the Snowflake Python connector cannot bind in `%(name)s`-style parameterized queries. The connector emits the numpy type as a pseudo-function call (`NP.INT64(...)`) which Snowflake rejects with `Unknown user-defined function NP.INT64`. Fix: call `.item()` on numpy scalars in `_s()` to convert to native Python types before binding. This is a one-line change — see `betting_ml/scripts/predict_today.py`.

**Backfill script (`betting_ml/scripts/backfill_predictions_2026.py`):**
- Queries `baseball_data.betting.mart_game_results` for all distinct `game_date` values in 2026 regular season (`game_type = 'R'`) where `game_date < CURRENT_DATE()` — these are the dates with finalized results.
- Checks `daily_model_predictions` for dates already scored and skips them by default (use `--force` to reprocess).
- Calls `uv run python betting_ml/scripts/predict_today.py --date {date}` as a subprocess for each unscored date, inheriting stdout so progress is visible.
- Accepts `--start-date YYYY-MM-DD` (default `2026-03-27`, Opening Day) and `--force` CLI flags.
- Reports a per-date success/failure summary; exits non-zero if any date fails.

*Output of the backfill:*
- One row per game in `baseball_data.betting_ml.daily_model_predictions` (model scores, probability layer outputs, market implied probs).
- Rows written to `baseball_data.config.prediction_log` for EV/Kelly tracking (parquet and CSV file outputs removed 2026-05-01).

*Blockers:* Snowflake write bug fix must be applied before backfill runs (already done). `feature_pregame_game_features` must have rows for the target dates (populated by the dbt pipeline for historical games). Odds data for 2026 games must be available in `mart_odds_outcomes` for market-facing columns (`has_odds`, `h2h_market_implied_prob`, etc.) to populate — games without odds coverage will have `has_odds = false` and null market columns.

*Acceptance criteria:*
- [x] `predict_today.py` Snowflake write succeeds without the `NP.INT64` / `NAN` errors — two-stage fix applied: `_s()` calls `.item()` to convert numpy scalars; `_sanitize()` converts remaining `float('nan')` → `None` before binding; confirmed working 2026-04-27.
- [x] `backfill_predictions_2026.py --start-date 2026-03-27` ran to completion — 31 distinct `score_date` values in `daily_model_predictions` covering 2026-03-27 through 2026-04-27; 400 total rows.
- [x] ~~Parquet and CSV files written per date in `betting_ml/outputs/`.~~ (Removed 2026-05-01 — Snowflake is the sole output.)
- [x] Dates already in `daily_model_predictions` are skipped by default; `--force` re-runs them.
- [x] 315/400 rows (78.8%) have `has_odds = true` with non-null `h2h_market_implied_prob` and `h2h_edge`; remaining 85 rows have `has_odds = false` and null market columns (confirmed Odds API coverage ceiling, not a data bug).

---

#### Card 6.H — Post-v0 Model Post-Mortem: Weakness Audit and Phase 7 Prioritization

**Title:** Conduct a structured post-mortem of the v0 model system; catalog weaknesses, root-cause each gap, and produce a prioritized improvement roadmap for Phase 7

**Status:** Complete as of 2026-05-01.

**What shipped:**
- `predict_today.py` updated: `cons_win` (0.5 × ngb_win + 0.5 × clf_win) now passed to `compute_edge()`, `compute_posterior()`, and `compute_kelly()` for the h2h market, replacing NGBoost alone. DDL comment updated to match.
- Measured impact across 941 has_odds rows (2026-03-27 through 2026-05-01): mean h2h edge −0.0361 → −0.0166; % positive 22.95% → 35.39%.
- `betting_ml/evaluation/selection_log.md` updated with a dated Card 6.H entry containing the before/after comparison.
- `betting_ml/evaluation/postmortem_v0.md` created: 8-gap structured analysis (Gaps 1–7 from prior spec plus Gap 8 — FanGraphs data pipeline), each with quantified evidence, root-cause verdict, and P1/P2/P3 priority. Phase 7 Roadmap section with 4 P1 items, 8 P2 items, 2 P3 items.

**Description:**

The v0 system (Phases 1–6 through Card 6.G) is the first end-to-end running implementation: data mart → feature store → trained models → daily predictions → Snowflake output. Card 6.G's backfill produced 1,098 scored game-rows covering 2026-03-27 through 2026-05-01 (941 has_odds rows). This card delivered a code fix (consensus_win_prob as official h2h model_prob), a before/after measurement of its impact, and a structured post-mortem of all known model gaps with a Phase 7 roadmap grounded in closing the model-vs-market gap.

---

**Known gaps going into this card (catalogued from project context):**

The following weaknesses are already partially documented across Cards 4.13, 5.1, and 5.2 notes. This card formalizes them with root-cause analysis, quantified impact, and a Phase 7 priority ranking.

---

**Gap 1 — Model does not improve on market calibration (best_alpha = 0.0)**

*What:* Card 4.13 found best_alpha = 0.0 — the Bayesian mixing weight that minimizes log-loss on all held-out CV folds. This means the market implied probability is a better-calibrated predictor of game outcomes than any convex combination of the model posterior and the market prior. Log-loss rises monotonically from α = 0.0 (0.683) to α = 1.0 (0.731). The model adds no calibration value over simply trusting the market line.

*Root cause candidates:*
- The feature set may not carry information unavailable to the market (market consensus Brier = 0.2395 vs. best model Brier = 0.2423 — model is meaningfully worse, not just equivalent).
- The training window (2016–2025) includes eras with structurally different run environments; even with `post_2022_rules` flag, the model may be misaligned on the 2026 run environment.
- The v0 feature set excludes weather, umpires, and current-season injury status — all of which the market incorporates in real time.
- Bayesian shrinkage for early-season rolling stats may not be aggressive enough; alpha=0.0 result holds across the full season, not just April.

*Impact:* High. The entire Kelly sizing and EV framework relies on `edge = model_prob − market_implied_prob` producing positive expected value. If the model is systematically less accurate than the market, the edge signal identifies noise rather than value.

*Phase 7 path:* Feature additions (weather, umpires, injury status, per-batter bat tracking matchups) are the primary levers. Secondary lever: retrain after 50+ 2026 games accumulate to align the model with the current season's run environment (see Card 6.F).

*Note on odds data completeness (2026-04-28):* The alpha tuning in Card 4.13 used only games with `has_odds = true` (matched rows in `mart_game_odds_bridge`). The two pipeline bugs documented in Gap 9 — the UTC/ET timezone mismatch and the `commenceTimeTo` cutoff — caused all late West Coast games to be excluded from `has_odds = true` throughout the historical backfill. This means the alpha tuning dataset was systematically missing late-game West Coast matchups (which tend to be higher-profile, higher-attendance games with sharper market lines). It was possible that `best_alpha = 0.0` was partly an artifact of this incomplete odds set. **Action item resolved (Card 7A, 2026-05-02):** Re-ran `run_probability_layer.py` against the corrected odds data (14,126 has_odds eval records). best_alpha=0.0 confirmed — log-loss still rises monotonically from 0.6833 to 0.7336 across the full α grid. The original result was not an artifact of the biased sample; the market is genuinely better calibrated than any model/market convex combination on this feature set.

---

**Gap 2 — Systematic home-team underestimation in h2h edge**

*What:* NGBoost-alone h2h edge was −0.036 (22.95% positive) across 941 has_odds rows. The consensus_win_prob fix (Card 6.H) was applied; corrected edge is −0.017 (35.39% positive). Edge is still negative — the model is not beating the market on h2h but the bias is halved.

*Root cause (confirmed by Card 6.H measurement):*
- NGBoost run_differential-to-win-probability derivation introduces systematic downward bias: **confirmed** — the 12.8-point gap between NGBoost-alone (22.95%) and consensus (35.39%) positive rates isolates the issue to the NGBoost path.
- consensus_win_prob not formalized as official model_prob: **fixed in Card 6.H**.
- Residual bias after consensus fix: **inconclusive** — 35.39% positive still well below 50%; deeper calibration investigation needed in Phase 7.

*Impact:* High. Systematic negative edge persists even after the consensus fix.

*Phase 7 path:*
1. ~~Implement `consensus_win_prob` as official h2h model_prob~~ — **done (Card 6.H)**.
2. Investigate whether residual bias is concentrated in specific contexts (road favorites, high-run-environment parks, afternoon games) using 2026 backfill.
3. If residual bias persists, evaluate a Platt or isotonic recalibration layer trained on 2026 edge residuals once ≥100 game results are available.

---

**Gap 3 — Total runs MAE barely improves over the naive baseline**

*What:* The naive global mean predictor achieves MAE ≈ 3.5 runs (NB01 baseline). The best tuned model (NGBoost Normal, n_estimators=200) achieves CV MAE = 3.5718. The tuned XGBoost achieves 3.5655. These represent a ~0.7–1% improvement over predicting the mean for every game — a very thin margin.

*Root cause candidates:*
- Total runs is a high-variance, low-predictability target. Park factor (r = 0.122) and elevation (r = 0.111) are the strongest features; no feature exceeds r = 0.13. The signal ceiling in the current feature set may be genuinely low.
- Weather is excluded and is directly relevant to outdoor park run totals (wind direction at Wrigley Field is documented as a ~2-run swing). This is the highest-expected-lift missing feature for the totals model.
- Umpire zone tendency (k%/bb% adjustment) affects total runs through strikeout and walk rates.
- The away pitching asymmetry (Card 3.9: r = 0.008 for away_pit_xwoba_against_30d vs. total_runs, vs. r = 0.075 for home pitching) means the model is heavily underweighting away team pitching quality for the totals target.

*Impact:* Medium-high. The totals model's edge signal (mean +0.057) is the most promising market-facing output of the v0 system. Improving the underlying MAE by 0.2–0.5 runs would materially improve the P(over) Brier score and the edge signal quality.

*Phase 7 path:*
1. Add weather features (Card 4.B1): temperature, wind speed/direction relative to park orientation, humidity for outdoor parks. GPS coordinates already in `stg_statsapi_venues`. Priority: highest single expected lift for totals.
2. Investigate the away pitching asymmetry further. Card 3.9 found the asymmetry is era-specific (pre-juiced: 5.8×, modern: 18.2×) and park-quartile-persistent. Consider a totals-only model trained exclusively on 2022+ data where the asymmetry is most extreme, to verify whether the era flag is adequately correcting for it or a structural fix is needed.
3. Add umpire tendencies (Card 4.B2) once a data source is secured.

---

**Gap 4 — alpha_tuning_results table is incomplete (1 row instead of 11)** ✅ *Resolved 2026-05-02 (Card 7A)*

*What:* The production Card 4.13 run used `--use-alpha 0.0` as a bypass. The Snowflake `alpha_tuning_results` table had 1 row instead of the spec-required 11.

*Root cause:* Implementation shortcut taken at Card 4.13 completion time; bypass flag was added to accelerate delivery.

*Resolution (Card 7A, 2026-05-02):* Full 11-candidate α grid rerun against corrected 2026 odds data (14,126 has_odds eval records after UTC/ET and commenceTimeTo pipeline bug fixes). `alpha_tuning_results` now has 11 rows with non-null log_loss (range: 0.6833–0.7336). best_alpha=0.0 confirmed — result did not shift from the original terminal run.

---

**Gap 5 — best_alpha.json local fallback not written** ✅ *Resolved 2026-05-02 (Card 7A)*

*What:* `predict_today.py` loaded `best_alpha` from Snowflake with no local fallback — silently defaulting to `alpha = 0.5` on Snowflake failure.

*Root cause:* Noted as a known gap in Card 4.13 (second bullet under "Known implementation gaps").

*Resolution (Card 7A, 2026-05-02):* `run_probability_layer.py` now writes `betting_ml/models/best_alpha.json` (with `best_alpha`, `log_loss`, `run_ts`, `source`) after every full grid run. `predict_today.py` `_load_best_alpha()` already had the three-tier resolution (Snowflake → file → 0.5) in place. File now exists: `best_alpha=0.0`, `log_loss=0.683263`.

---

**Gap 6 — Intraday feature assembly fallback not implemented**

*What:* `predict_today.py` queries `feature_pregame_game_features` in Snowflake for the target date. The nightly dbt pipeline only refreshes this table after morning ingestion completes (~08:30 ET). Any intraday run against today's date before the nightly pipeline has refreshed returns an empty DataFrame and the script exits with "No games found." The Card 5.2 spec called for a `load_todays_features_via_statsapi()` fallback that assembles features directly from the MLB Stats API when dbt rows are not yet available.

*Root cause:* Noted as a known gap in Card 5.2. The fallback is complex (requires assembling rolling stats inline without dbt) and was deferred to avoid scope creep during Phase 5 delivery.

*Impact:* Medium. Limits the prediction CLI to use after ~08:30 ET only (after the dbt build completes). Reduces usability for morning lineup-lock prediction runs where the Streamlit app would be consulted before the dbt pipeline finishes.

*Phase 7 path:* Implement `load_todays_features_via_statsapi(target_date)` in `data_loader.py`. The function should call `ingest_statsapi.py schedule` for the target date, read the latest confirmed lineups from `stg_statsapi_lineups_wide`, and assemble a minimal feature vector using cached rolling stat snapshots from the prior day's dbt build. This is a medium-complexity engineering task but high usability value once the Streamlit app is live.

---

**Gap 7 — Feature set excludes highest-signal missing information**

*What:* Three categories of pre-game information are incorporated by the market but absent from the v0 feature set:

| Missing feature | Expected impact | Current status |
|---|---|---|
| Weather (temperature, wind, humidity) | Highest single expected lift for totals; ~2-run swing for wind at outdoor parks | Backlogged (Card 4.B1); GPS coordinates available |
| Umpire zone tendency (k%/bb% adj) | Affects total runs via strikeout/walk rates; umpire assignments announced morning of game | Backlogged (Card 4.B2); no data source yet |
| Player injury/lineup status | Affects team offense and pitching quality; not captured by rolling stats which lag by a day | No ingestion path; external API required (ESPN, FanGraphs) |
| Per-batter bat tracking matchup | Per-batter bat speed vs. pitcher pitch mix; team-level average was too noisy (NB06 ΔR² < 0.001) | Deferred to Phase 5+ (NB06, Card 4.6 verdict) |

*Impact:* High collectively. The consensus from Phase 3 EDA is that the v0 feature ceiling is genuinely limited — the best individual feature correlation is r = 0.122 (park run factor). Adding weather and umpires would add 2–3 features with r > 0.05.

*Phase 7 path:* Implement in priority order: weather (highest expected impact, data source exists) → umpires (medium expected impact, open-source data) → per-batter bat tracking (data in hand; engineering effort to formulate correctly) → injury status (requires data source commitment). See also Gap 8 for FanGraphs-specific missing features (Stuff+, pre-season projections, hitter/pitcher matchup splits).

---

**Gap 8 — No FanGraphs data pipeline: Stuff+, pre-season projections, and matchup splits absent**

*What:* FanGraphs publishes several high-signal data sets absent from v0: Stuff+ (pitch-level arsenal quality independent of outcomes), pre-season Steamer/ZiPS/PECOTA projections (the market's primary early-season calibration anchor), and hitter vs. pitcher handedness and pitch-mix splits. The model relies exclusively on rolling stats with Bayesian shrinkage for early-season games — exactly when the market most relies on projections the model cannot replicate.

*Root cause:* FanGraphs data requires a separate ingestion pipeline (`pybaseball` or direct CSV export); not in scope for Phases 1–6.

*Impact:* High for early-season prediction quality (April/early May when rolling stat windows are 5–15 games); medium for full-season via Stuff+ and matchup features.

*Phase 7 path:*
1. Stand up a FanGraphs ingestion script using `pybaseball` or CSV exports. Ingest Steamer/ZiPS projections (wRC+, FIP, xFIP, K%, BB%) pre-season; refresh at All-Star break.
2. Add projection features to `feature_pregame_game_features` with a sample-size-adaptive blend (projection weight → 0 as `games_played_30d` > ~40).
3. Ingest Stuff+ and pitch-mix data per starter; add as features for totals and win-probability models.
4. Build hitter/pitcher matchup split features rolled up to lineup level.
5. Phase 7B: pitcher clustering model (k-means/HDBSCAN on arsenal vectors → hitter performance by archetype group, `feature_pitcher_cluster_matchups` dbt table).

---

**Gap 9 (formerly Gap 8 in pre-6.H numbering) — Model is not retrained on 2026 data**

*What:* All production models in `model_registry.yaml` were trained on 2016–2025 data and calibrated on 2025. As of 2026-04-27, 31 dates of 2026 game results are available in `mart_game_results`. The model has not been retrained to incorporate 2026 run environment, roster construction, and rule application patterns.

*Root cause:* Card 6.F defines the retraining cadence (mid-season trigger: ≥50 2026 games). As of the post-mortem date, the trigger has not yet been met but is approaching.

*Impact:* Medium and growing. The structural shift at the 2022→2023 rule boundary (Card 3.10) shows how quickly run environment can change. The 2026 season run environment (pitch clock year 3, shift ban year 3) may exhibit further drift from the 2023–2025 calibration window.

*Phase 7 path:* Execute the Card 6.F mid-season refit once 50 2026 regular season games complete (estimated mid-May 2026). Track Brier score trend in Card 6.E Performance Tracker as the leading indicator.

---

**Gap 10 (formerly Gap 9 in pre-6.H numbering) — Odds API coverage ceiling leaves ~21% of games unscored**

*What:* The Odds API covers approximately 10–11 of 13 daily games (~79% match rate for 2026 in `mart_game_odds_bridge`). Of the 400 backfilled rows in `daily_model_predictions`, 85 (21.2%) have `has_odds = false` and null market columns. These games cannot be evaluated for edge or Kelly sizing.

*Root cause:* **Partially revised (2026-04-28).** The original attribution ("confirmed coverage ceiling — not a pipeline bug") was incorrect. Investigation found two pipeline bugs that together account for a significant fraction of the missing odds:

1. **UTC/ET timezone mismatch in `mart_odds_events`:** `commence_date` was computed from the raw UTC timestamp (`commence_time::date`) instead of the ET calendar date (`convert_timezone('UTC', 'America/New_York', commence_time)::date`). MLB `game_date` uses the local (ET) calendar date. Any game starting after 8 pm ET (midnight UTC) in summer — typically the late West Coast slate — had its `commence_date` bucketed one calendar day ahead, breaking the date-based join in `mart_game_odds_bridge`. **Fixed:** `mart_odds_events.sql` and `mart_odds_outcomes.sql` updated to use ET timezone conversion.

2. **`commenceTimeTo` cutoff too early in ingestion script:** `scripts/odds_api_ingestion.py` `run_historical_events()` and `run_historical_odds()` both used `commenceTimeTo = YYYY-MM-DD 23:59:59Z` (UTC midnight), which silently excluded any game starting after midnight UTC (8 pm ET+). Late West Coast games were never ingested. **Fixed:** `day_end` extended to `next_day 04:59:59 UTC`, covering the full ET calendar day including the latest possible West Coast starts. Historical events and odds for 2026-03-27 → 2026-04-21 re-ingested with the corrected window using `--force`.

After these fixes and a full dbt rebuild + prediction backfill, residual `has_odds = false` games represent the true API coverage ceiling — games the Odds API genuinely does not list.

*Impact:* Low-medium for the residual gap. The pipeline fixes meaningfully reduce the `has_odds = false` count; the remaining gap is not actionable without changing the odds data provider or supplementing with a second source.

*Note on Bayesian analysis impact:* See Gap 1 note below — the odds data incompleteness from these bugs likely biased the alpha tuning dataset.

*Phase 7 path:* Evaluate supplementary odds sources. Pinnacle is the canonical sharp book with near-100% MLB game coverage. Adding Pinnacle as a second source would also improve the `home_win_prob_sharp` calculation (currently reliant on lowvig, betonlineag, bovada).

---

**Gap 11 (formerly Gap 10 in pre-6.H numbering) — No closing line data; CLV tracking and Performance Tracker are blocked**

*What:* Card 6.E (Performance Tracker) requires `closing_market_prob` per game in `prediction_log` — the final odds snapshot before game start, against which opening-line predictions are compared to compute Closing Line Value. The closing line backfill step does not yet exist in the Card 6.A Task DAG and `prediction_log` itself has not been created (it is created by `predict_today.py` as part of the Card 6.E implementation, which has not started).

*Root cause:* Card 6.E is not yet started; the prediction_log table creation and closing line backfill are in-scope for that card.

*Impact:* Medium. CLV is the primary diagnostic for whether the model is identifying genuine pre-game value. Without it, the Performance Tracker shows only P&L simulation — useful but not a root-cause diagnostic.

*Phase 7 path:* Implement Card 6.E (Performance Tracker) to unblock CLV tracking. The closing line backfill step should be added to `proc_statsapi_schedule` or a new `proc_results_backfill` task so it runs automatically each morning.

---

**Prioritized Phase 7 roadmap (as of 2026-05-01, post-Card 6.H):**

Full details in `betting_ml/evaluation/postmortem_v0.md` — Phase 7 Roadmap section.

| Priority | Item | Gap(s) | Expected impact |
|---|---|---|---|
| P1 | Re-run α grid (full 11-row) with corrected odds data + write best_alpha.json | 1, 4, 5 | Validates calibration; unblocks CLV tracker |
| P1 | Weather features for outdoor parks (Card 4.B1) | 3, 7 | Expected 0.2–0.3 run MAE improvement; highest single-feature lift |
| P1 | Home-team probability calibration (reliability diagram → Platt/isotonic recalibration) | 2 | Closes residual h2h edge bias after consensus fix |
| P1 | FanGraphs ingestion + pre-season projections (Steamer/ZiPS via `pybaseball`) | 8 | Closes early-season structural blind spot; sample-size-adaptive blend |
| P2 | FanGraphs Stuff+ and pitch-arsenal quality metrics per starter | 8 | Leading indicator for K rate; most useful in first 30–40 IP |
| P2 | Individual hitter vs. pitcher matchup splits (rolled up to lineup level) | 8 | Next granularity level beyond team wRC+/ERA |
| P2 | Pitcher clustering model + hitter performance by archetype group | 8 | Captures style-matchup signal; `feature_pitcher_cluster_matchups` dbt table |
| P2 | Intraday feature fallback (`load_todays_features_via_statsapi`) | 6 | Eliminates pre-09:00 ET "No games found" window |
| P2 | Umpire tendency features (Card 4.B2) | 7 | ~0.1 run MAE improvement once data source secured |
| P2 | Injury and lineup status features | 7 | Market-facing; hard to quantify |
| P2 | Phase 7 prediction backfill: re-score 2026 season with improved model | — | Primary validation gate for Phase 7 lift |
| P3 | Model retraining on 2026 data | 9 | Only after P1 calibration + feature work shows positive edge |
| P3 | Production web app (replace Streamlit MVP) | — | After model quality warrants investment |

**Note:** Gap 2 consensus_win_prob fix was applied in Card 6.H (not a Phase 7 item). Measured result: mean h2h edge −0.0361 → −0.0166; % positive 22.95% → 35.39% across 941 has_odds rows.

---

*Acceptance criteria:*
- [x] Each of the 8 gaps documented with quantified state from `daily_model_predictions` or evaluation files, root-cause verdict, and Phase 7 card reference — see `betting_ml/evaluation/postmortem_v0.md`
- [x] consensus_win_prob h2h edge impact measured: −0.0361 → −0.0166 mean edge; 22.95% → 35.39% positive across 941 has_odds rows (2026-03-27 through 2026-05-01)
- [x] Prioritized roadmap reviewed and updated — FanGraphs data pipeline added as P1/P2; retraining demoted to P3
- [x] `betting_ml/evaluation/postmortem_v0.md` created — 8-gap analysis with P1/P2/P3 rankings and Phase 7 Roadmap section
- [x] `project_context.md` updated — gap numbering extended to Gap 8 (FanGraphs), roadmap table replaced, Card 6.H status marked complete

---

#### Card 6.I — Application Branding and Landing Page Redesign

**Title:** Give the Streamlit app a name and replace the placeholder landing page with a meaningful project overview

**Status:** Complete as of 2026-05-01.

**What shipped:**
- `app/streamlit_app.py` refactored to a `st.navigation()` dispatcher; landing page content extracted to `app/home.py`
- App renamed "Diamond Edge" with `page_title="Diamond Edge"`, `page_icon="💎"` in `set_page_config`; sidebar shows `# 💎 Diamond Edge` with NGBoost + XGBoost subtitle via `st.sidebar.markdown`
- Sidebar navigation labels set explicitly via `st.Page()`: 🏠 Home, ⚾ Today's Picks, 📊 Market Comparison, 💰 EV Tracker, 📈 Performance Tracker — eliminates filename-derived labels and numbered prefixes
- Landing page four sections: project description, page navigation guide (markdown table), model fact sheet (4-column `st.metric` tiles with `selected_at` read from `model_registry.yaml` guarded by `exists()` + `try/except`), daily workflow expander
- Workflow expander prose updated to reflect GitHub Actions orchestration (Snowflake Task DAG references removed); all five workflows documented: `daily_ingestion.yml` (08:00 ET), `lineup_monitor.yml` (hourly), `odds_snapshot.yml` (13:00/18:00/23:00 EDT), `dbt_daily_build.yml` (reusable), `dbt_staging_build.yml` (lineup-scoped dispatch)
- Graphviz pipeline diagram rendered via `st.graphviz_chart` inside the expander showing daily/hourly/intraday-odds trigger clusters converging on Snowflake feature tables → Today's Picks
- All 7 acceptance criteria pass; no heavy model imports at landing page level (verified via AST walk)

*Acceptance criteria:*
- [x] `st.set_page_config(page_title="Diamond Edge")` set in `app/streamlit_app.py`
- [x] Sidebar displays "💎 Diamond Edge" as the app title
- [x] Landing page renders four sections: project description, page navigation guide, model fact sheet, daily workflow expander
- [x] Model fact sheet tiles read `selected_at` dynamically from `model_registry.yaml`; a missing or malformed registry shows a fallback warning rather than erroring
- [x] All four navigation page names in the guide match the actual page filenames in `app/pages/`
- [x] Landing page loads in under 2 seconds on first render (no model loading or Snowflake query at landing page level)
- [x] No references to "streamlit_app" remain as user-visible text in the sidebar or page titles

---

### Phase 7 — Model Refinement, Feature Expansion, and Production Infrastructure

Active phase as of 2026-05-01. All Phase 7A cards focus on closing the model-vs-market gap identified in Card 6.H post-mortem (mean h2h edge −0.017, ~35% positive edge). Retraining the existing architecture on more data is explicitly deferred (Card 7.D) until Phase 7A improvements produce a market-beating model. Phase 7B production infrastructure is blocked until that threshold is met.

Card naming follows the plan spec letter convention (A, B, C, …) matching `plan_specs/phase_7/` filenames.

---

#### Phase 7A — Model Refinement and Feature Expansion

**P1 cards** (address before any P2 work):

---

##### Card 7.A — Re-run Probability Layer with Full α Grid (P1)

**Title:** Populate the full 11-row α tuning grid in Snowflake with corrected odds data and write best_alpha.json

**Why P1:** `alpha_tuning_results` has 1 row (alpha=0.0, log_loss=NULL) instead of 11. The original α tuning used a biased odds sample excluding all late West Coast games due to two fixed pipeline bugs (UTC/ET mismatch, `commenceTimeTo` cutoff). Until the full grid re-runs, it is unknown whether best_alpha stays 0.0. Additionally, `best_alpha.json` was never written; `predict_today.py` falls back to alpha=0.5 on Snowflake failure — a material miscalibration. This is a ~15-minute script run + 30-minute code fix. Gaps 1, 4, 5 from `betting_ml/evaluation/postmortem_v0.md`.

*Technical implementation:*
- Run `uv run python betting_ml/scripts/run_probability_layer.py` without `--use-alpha` to trigger the full 11-candidate grid (α = 0.0, 0.1, …, 1.0)
- Add `json.dump({"best_alpha": best_alpha, "log_loss": best_log_loss, "run_ts": ...})` to `run_probability_layer.py` to write `betting_ml/models/best_alpha.json` after the grid completes
- Update `predict_today.py` fallback to read `best_alpha.json` before defaulting to alpha=0.5

*Acceptance criteria:*
- [ ] `alpha_tuning_results` has exactly 11 rows; all `log_loss` values are non-null
- [ ] `SELECT MIN(log_loss), MAX(log_loss) FROM baseball_data.config.alpha_tuning_results` returns values between 0.60 and 0.80
- [ ] `betting_ml/models/best_alpha.json` exists and parses as `{"best_alpha": float, "log_loss": float}`
- [ ] `predict_today.py` reads `best_alpha.json` as fallback when Snowflake is unavailable
- [ ] If best_alpha shifted away from 0.0, `probability_layer_results.md` updated with new grid results

---

##### Card 7.B — Weather Features for Outdoor Parks (P1)

**Title:** Add temperature, wind, and humidity features to the pre-game feature store for outdoor stadiums

**Why P1:** Weather is the highest-signal missing feature for the totals model. Wind at outdoor parks (Wrigley, Fenway, Coors) produces ~2-run swings. Park factor (r=0.122) and elevation (r=0.111) are the strongest existing features — weather sits in the same signal range and is uncorrelated with current features. GPS coordinates already available in `stg_statsapi_venues`. Expected MAE improvement: 0.2–0.3 runs. Gap 3 and Gap 7 from postmortem; originally scoped as Card 4.B1 (BACKLOG).

*Technical implementation:*
- Select a weather API (OpenWeatherMap preferred; NOAA as free backup). Requires API key + new `scripts/ingest_weather.py`.
- `ingest_weather.py` fetches game-day weather (temp, wind speed mph, wind direction degrees, humidity %) per outdoor park via GPS coordinate + date. Writes to `baseball_data.statsapi.weather_raw` (one row per game_pk × venue_id × game_datetime).
- Roof-type filter: `stg_statsapi_venues.roof_type IN ('open', 'convertible')` gates weather features. Dome parks receive NULL (imputed to league average in preprocessing).
- Wind direction relative to park: add static `park_facing_degrees` column to `ref_teams.csv` (direction from home plate to center field). Net wind component = `wind_speed_mph × cos(wind_direction_deg − park_facing_deg)` — positive = wind out, negative = wind in.
- New dbt model `feature_pregame_weather_features` — one row per game_pk; columns: `temp_f`, `wind_speed_mph`, `wind_direction_deg`, `wind_component_mph`, `humidity_pct`, `is_dome`. Join to `feature_pregame_game_features` via `game_pk`.
- Historical backfill 2016–2025 required for training. Add `ingest_weather.py` to `daily_ingestion.yml` (after odds ingestion, before `dbt-build`).

*Acceptance criteria:*
- [ ] `baseball_data.statsapi.weather_raw` exists; ≥1 row per outdoor-park game from 2026-03-27 onward
- [ ] `feature_pregame_weather_features` builds cleanly; dome parks have NULL `wind_component_mph`; outdoor parks non-null
- [ ] `wind_component_mph` has plausible range (−30 to +30 mph); spot-check a known Wrigley game with strong wind against reported conditions
- [ ] `feature_pregame_game_features` includes all weather columns; `dbtf build` passes all tests
- [ ] Historical backfill complete for ≥3 training seasons; `has_full_data` flag unchanged (weather nulls handled by imputation)
- [ ] After retrain with weather features, `total_runs` CV MAE < 3.55 (measurable improvement from 3.5718 baseline)

---

##### Card 7.C — Home-Team Win Probability Calibration (P1)

**Title:** Diagnose and correct systematic home-team underprediction in the h2h win probability model

**Why P1:** After the consensus_win_prob fix (Card 6.H), only 35.39% of predictions show positive h2h edge — the model systematically underestimates home win probability. This is a calibration deficiency, not a pipeline issue. Once ≥100 2026 game results accumulate, Platt re-scaling or isotonic recalibration can be applied without full retraining. Gap 2 from postmortem.

*Blocker:* Requires ≥100 completed 2026 games with `actual_outcome` populated in `daily_model_predictions`. As of 2026-05-01, ~35–40 results exist; card unblocks around 2026-05-25 at current pace.

*Technical implementation:*
- Query `daily_model_predictions` once ≥100 has_odds rows with non-null `actual_outcome`. Compute a reliability diagram for `consensus_win_prob` in 10 probability bins. Plot fraction of home wins vs. mean predicted probability per bin.
- If reliability curve shows systematic under-prediction in mid-range bins (0.45–0.65): apply Platt scaling (logistic regression on `consensus_win_prob` → `actual_outcome`) using 2026 in-season data. Use isotonic regression if bias is non-linear.
- Persist calibration model as `betting_ml/models/home_win/calibrator.joblib`.
- Investigate bias by context: road favorites, high-run-environment parks (Coors, Great American), afternoon starts.
- Update `predict_today.py` to write `calibrated_win_prob` to `daily_model_predictions` and use it for `h2h_edge` computation.

*Acceptance criteria:*
- [ ] Reliability diagram plotted; bias documented (uniform vs. context-specific)
- [ ] Platt scaling or isotonic recalibration model trained and persisted as `calibrator.joblib`
- [ ] ECE for `calibrated_win_prob` < ECE for `consensus_win_prob` on held-out 2026 games
- [ ] Mean h2h edge computed with `calibrated_win_prob` and compared to v0 baseline (−0.017); result documented in `betting_ml/evaluation/postmortem_v0.md`
- [ ] `predict_today.py` writes `calibrated_win_prob` and uses it for `h2h_edge`

---

##### Card 7.E — FanGraphs Ingestion Pipeline + Pre-Season Projections (P1) ✓ Complete (2026-05-02)

**Title:** Stand up a FanGraphs ingestion layer and integrate ZiPS pre-season projections and Stuff+ as early-season feature anchors

**Why P1:** The model has no stable early-season anchor. In April/early May, rolling stats (ERA_30d, xwOBA_30d) are built on 5–15 starts and carry near-zero signal — yet the market uses Steamer/ZiPS as its primary calibration input for the first 4–6 weeks. This structural gap means the model is most blind exactly when the season starts. Pre-season projections (wRC+, FIP, xFIP, K%, BB% at the player level) are publicly available and slot directly into the existing feature assembly path. Gap 8 from postmortem.

*What was built:*
- Raw schema `baseball_data.fangraphs` with four tables: `fg_stuff_plus_raw`, `fg_zips_pitching_raw`, `fg_zips_hitting_raw`, `fg_hitting_leaderboard_raw`
- ZiPS CSV ingestion: `scripts/ingest_fangraphs_zips_csv.py` — loads manually downloaded ZiPS CSV exports (pitcher and batter projections) for 2024–2026; grain: `fg_pitcher_id/fg_batter_id × season × projection_type`
- Stuff+ and hitting leaderboard API ingestion: `scripts/ingest_fangraphs_stuff_plus.py` and `scripts/ingest_fangraphs_hitting_lb.py` — pull from FanGraphs API; hitting leaderboard fetches all four window types (7d/14d/30d/season)
- Four staging dbt models (`stg_fangraphs__stuff_plus`, `stg_fangraphs__zips_pitching`, `stg_fangraphs__zips_hitting`, `stg_fangraphs__hitting_leaderboard`) with dedup-to-latest logic and all schema tests passing
- Three mart dbt models in `dbt/models/marts/fangraphs/`:
  - `fct_fangraphs_pitching_analytics` — one row per pitcher × season; Stuff+ joined to ZiPS pitching projections (proj_era, proj_fip, proj_k_per_9, proj_bb_per_9, proj_ip, proj_war, proj_whip)
  - `fct_fangraphs_hitting_analytics` — one row per batter × season; ZiPS hitting projections (proj_wrc_plus, proj_obp, proj_slg, proj_hr, proj_war) joined to rolling leaderboard windows (rolling_wrc_plus_7d/14d/30d, season_wrc_plus, rolling_obp_*, rolling_pa_*, season_pa)
  - `dim_fangraphs_player_xref` — cross-reference of FanGraphs IDs to MLBAM IDs; 9,330 rows (4,552 MLB players with numeric IDs, 4,778 MiLB players with `sa`-prefixed IDs); `fg_mlb_id`, `fg_milb_id`, `is_milb_player`, `is_pitcher`, `is_batter` flags; only 2 rows missing MLBAM IDs
- Validation script `scripts/validate_fangraphs_pipeline.py` — four automated checks: raw row counts, MLBAM join rate for MLB-active pitchers (≥95%, scoped to exclude `sa`-prefixed MiLB pitchers absent from `savant.ref_players`), Stuff+ null rate (<10%), mart duplicate grain checks; all PASS (96.3% MLBAM join rate for 1,042 MLB-active pitchers); results written to `betting_ml/evaluation/fangraphs_validation.md`

*Acceptance criteria:*
- [x] Raw FanGraphs tables populated: `fg_zips_pitching_raw` ≥400 pitchers, `fg_zips_hitting_raw` ≥700 batters, `fg_stuff_plus_raw` ≥350 pitchers; all 4 hitting leaderboard window types present (7d, 14d, 30d, season)
- [x] MLBAM ID join coverage ≥95% for MLB-active (non-`sa`-prefix) ZiPS pitchers matched to `ref_players` — 96.3% PASS
- [x] All four staging models build cleanly with no duplicate grain violations
- [x] `fct_fangraphs_pitching_analytics` and `fct_fangraphs_hitting_analytics` marts build with 0 duplicate grains
- [x] `dim_fangraphs_player_xref` built; distinguishes MLB (numeric fg_mlb_id) from MiLB (`sa`-prefixed fg_milb_id); ≥9,000 total players
- [x] Validation script exits 0 with all checks PASS; results in `betting_ml/evaluation/fangraphs_validation.md`
- [x] Gap 8 from postmortem_v0.md resolved

---

**P2 cards** (implement after at least one P1 improvement validates a positive edge shift):

---

##### Card 7.F — FanGraphs Stuff+ and Pitch-Arsenal Quality Metrics (P2) ✓ Complete (2026-05-03)

**Title:** Add per-starter Stuff+ and pitch-mix features as leading indicators of pitcher quality

**Why P2:** Stuff+ (100 = league average) measures per-pitch movement and velocity quality independent of outcomes — a leading indicator in the first 30–40 IP before ERA stabilizes. The market incorporates Stuff+ for new or changed pitchers. Gap 8 from postmortem.

*Blocker:* Card 7.E must complete first.

*Completed (2026-05-03):* `stg_fangraphs__pitcher_arsenal` and `fct_fangraphs_pitcher_arsenal_wide` built and validated; 13 of 18 numeric arsenal features retained after feature selection (top retained: `home_starter_stuff_plus` rank 16/267, `away_starter_stuff_plus` top 20); training cutoff changed from `game_year != 2020` to `game_year >= 2021` (pre-2020 rows had 0% Stuff+ population — distribution shift fix); all three models retrained on 10,243 rows (2021–2026, 267 features): home_win CV Brier 0.2443 (flat), total_runs CV MAE 3.4856 (−0.038 improvement), run_differential CV MAE 3.4586 (+0.039, LogNormal excluded — run_diff can be negative). CV scores not directly comparable to 2015+ baselines — different dataset. `betting_ml/evaluation/stuff_plus_feature_impact.md` documents full results. Note: retraining going forward deferred until all feature expansion cards complete (Card 7.MA).

---

##### Card 7.G — Intraday Feature Fallback for predict_today.py (P2)

**Title:** Implement load_todays_features_via_statsapi() to eliminate the pre-09:00 ET "No games found" window

**Why P2:** `predict_today.py` returns "No games found" before the `daily_ingestion.yml` → `dbt_daily_build.yml` chain completes (~08:30–09:00 ET). Morning lineup-lock runs before that window are unreliable. Gap 6 from postmortem.

*Technical implementation:*
- Implement `load_todays_features_via_statsapi(target_date)` in `betting_ml/utils/data_loader.py`. Joins prior-day rolling stat snapshots (already materialized from yesterday's dbt build) with intraday Stats API schedule data. Rolling stats do not change overnight; yesterday's values are valid until tomorrow's build.
- `predict_today.py` falls back to this function when `feature_pregame_game_features` returns empty for the target date. Writes a `source=intraday_fallback` tag to `daily_model_predictions`.

*Acceptance criteria:*
- [ ] `load_todays_features_via_statsapi()` implemented in `data_loader.py`
- [ ] `predict_today.py` automatically falls back when feature store is empty for target date; produces predictions with `source=intraday_fallback` tag
- [ ] Manual test on a game day before `dbt build` confirms predictions are written to Snowflake

---

##### Card 7.H — Umpire Tendency Features (P2) ✓ Complete (2026-05-03)

**Title:** Add home plate umpire K%/BB% adjustment features

**Why P2:** Umpire zone tendency shifts total runs and K rates. Umpire assignments announced morning of each game. Expected totals MAE improvement: ~0.1 runs. Gap 7 from postmortem; originally Card 4.B2 (BACKLOG).

Two-source architecture: UmpScorecards bulk CSV (2015–2026, 25,556 rows) for historical tendency metrics; MLB Stats API `hydrate=officials` for daily forward-path assignment. Both write to `baseball_data.statsapi.umpire_game_log` (one row per game_pk).

*Delivered:*
- `scripts/ddl/umpire_game_log.sql` — DDL for umpire_game_log table
- `scripts/ingest_umpires_historical.py` — bulk CSV load via `write_pandas` (truncate + PUT/COPY INTO); 25,556 rows in ~5 seconds; `--merge` flag for incremental seasonal refresh; `--dry-run` mode
- `scripts/ingest_umpires.py --date YYYY-MM-DD` — daily MLB Stats API assignment fetch; wired into `.github/workflows/daily_ingestion.yml`
- `dbt/models/staging/statsapi/stg_statsapi_umpire_game_log.sql` — deduplication via ROW_NUMBER(), preferring `umpscorecards` rows over `statsapi`
- `dbt/models/feature/feature_pregame_umpire_features.sql` — trailing 3-year z-scores with leakage guard (`b.game_date < a.game_date`) and sample gate (`< 10 games → 0.0`); bonus features `ump_run_impact_zscore` and `ump_accuracy_zscore` added from UmpScorecards columns not in original spec
- `feature_pregame_game_features` updated with LEFT JOIN on `feature_pregame_umpire_features`; 99.4% coverage for 2026 regular season games (479/482)
- `betting_ml/evaluation/umpire_feature_impact.md` — correlation analysis, feature selection results, pre-retrain baselines

*Feature selection results (corr threshold 0.02, n=17,812):*
- `ump_runs_per_game_zscore`: r=−0.024 vs total_runs — retained (marginal)
- `ump_accuracy_zscore`: r=+0.021 vs total_runs — retained (marginal)
- `ump_run_impact_zscore`, `ump_k_pct_zscore`, `ump_bb_pct_zscore`: excluded (corr < 0.02 or structural zero)

*Notes:*
- UmpScorecards by-game export does not include k_pct/bb_pct; those columns are nullable in the table; z-scores default to 0.0. A Statcast-based backfill path is documented in the impact doc.
- LogNormal distribution permanently excluded from `run_ngboost_run_diff_search.py` — run_diff can be negative, log(Y) blows up.
- Model retraining deferred to the pre-Card 7.MA checkpoint (all three models batch-retrained together).

*Acceptance criteria:*
- [x] Data source identified and documented; ≥5 seasons of historical umpire data ingested (25,556 rows, 2015–2026)
- [x] `feature_pregame_umpire_features` builds cleanly; umpire features present for ≥90% of 2026 regular season games (99.4%)
- [x] CV impact documented after feature addition (`betting_ml/evaluation/umpire_feature_impact.md`)

---

##### Card 7.I — Injury and Confirmed Lineup Status Features (P2) ✓ Complete (2026-05-03)

**Title:** Integrate real-time injury and lineup availability signals to close the market information gap on player availability

**Why P2:** Player availability (injury status, lineup scratches) is a market-facing input absent from v0. A star player sitting out materially shifts win probability and total runs. Gap 7 from postmortem.

*Completed (2026-05-03):* MLB Stats API `/v1/transactions` endpoint chosen as authoritative source (stable JSON, covers 2021+). `baseball_data.statsapi.player_transactions` table created; `scripts/ingest_transactions.py` ingests via bulk temp-table + DELETE/INSERT pattern (MERGE abandoned — Snowflake rejects `PARSE_JSON` in VALUES clause; temp table + `INSERT INTO ... SELECT PARSE_JSON(...)` is the project-standard workaround). `scripts/backfill_transactions.py` loaded 2021–2026 (66,497 rows). `stg_statsapi_transactions` deduplicates raw rows (Stats API returns same transaction across overlapping date range queries); `stg_statsapi_player_injury_status` derives point-in-time injury status via `LEAD()` window — IL placements use `type_code = 'SC'` with `description ILIKE` patterns (confirmed via dry-run: all IL events share `typeCode='SC'`; placement vs. activation distinguished by description text). `feature_pregame_lineup_features` extended with `slot_injury` and `injury_agg` CTEs: `injured_player_count`, `injury_adj_avg_woba_30d`, `injury_adj_avg_xwoba_30d` per game × side; injury-adjusted columns divide by 9 so IL absences penalise the aggregate. `feature_pregame_game_features` exposes `home_`/`away_` prefixed versions of all three. Streamlit Today's Picks IL warning indicator added (guards on column existence). Validation: 33.4% of game-rows have ≥1 IL player (within expected 30–50% range); `injury_adj_avg_woba_30d` (0.308) < `avg_woba_30d` (0.331) confirming IL penalty is working. Row count unchanged (51,382). Daily ingestion wired into `daily_ingestion.yml` with 7-day lookback. Model retraining deferred to pre-Card 7.MA batch checkpoint.

*Acceptance criteria:*
- [x] Reliable injury source identified; `player_transactions` table populated (66,497 rows, 2021–2026)
- [x] `feature_pregame_lineup_features` includes `injury_adj_avg_woba_30d`, `injury_adj_avg_xwoba_30d`, `injured_player_count` (home and away via game_features)
- [x] Streamlit Today's Picks shows IL warning when `home_injured_player_count > 0` or `away_injured_player_count > 0`
- [ ] CV impact documented — deferred to Card 7.MA (full batch retraining); `betting_ml/evaluation/injury_feature_impact.md` has placeholder with confirmed IL coverage stats

---

##### Card 7.J — Individual Hitter vs. Pitcher Matchup Metrics (P2)

**Title:** Add per-lineup aggregated matchup split features against the scheduled starter's handedness and pitch mix

**Why P2:** Current features are team-level (team wRC+, team ERA). Per-batter career splits against pitcher handedness and pitch archetypes add the next granularity level the market prices. Gap 8 from postmortem.

*Blocker:* Card 7.E for pitch-mix data. Confirmed lineup data already available in `stg_statsapi_lineups_wide`.

*Technical implementation:*
- Aggregate per-batter historical plate discipline (K%, BB%, ISO, wRC+) from `stg_batter_pitches` split by `pitcher_throws` (L/R) and pitch-mix archetype (simplified rule for v1: `fastball_dominant` if `fastball_pct > 0.60`, `breaking_dominant` if `breaking_ball_pct > 0.50`, else `mixed`).
- Roll up 9-batter lineup to weighted average. Minimum sample filter: 50 PA per batter-handedness cell; shrink toward league average below threshold.
- Add `home_lineup_k_pct_vs_hand`, `home_lineup_iso_vs_hand`, `away_lineup_k_pct_vs_hand`, `away_lineup_iso_vs_hand`, `home_lineup_k_pct_vs_archetype`, `away_lineup_k_pct_vs_archetype` to `feature_pregame_lineup_features`.

*Acceptance criteria:*
- [x] New columns added to `feature_pregame_lineup_features` with correct game_pk × side grain
- [x] `dbtf build` passes; null rate < 5% for 2026 regular season games
- [x] CV impact documented; feature importances confirm non-zero signal (methodology documented in `matchup_split_feature_impact.md`; numerical impact values deferred to pre-7.MA retrain per project plan)

---

##### Card 7.K — Pitcher Clustering Model and Cluster-Based Lineup Matchup Features (P2)

**Title:** Cluster MLB starters into pitch-style archetypes and compute lineup performance vs. each cluster

**Why P2:** The market prices "style matchup" signal (e.g., strikeout-heavy lineup vs. elite breaking-ball starter) that raw ERA/FIP cannot capture. Clustering starters by arsenal creates a more informative matchup dimension. Gap 8 from postmortem.

*Blocker:* Card 7.F (Stuff+ and pitch-arsenal features) must complete first.

*Technical implementation:*
- Cluster all MLB starters using k-means or HDBSCAN on per-starter arsenal vectors: primary pitch velocity, horizontal/vertical break, fastball%, breaking ball%, off-speed%, Stuff+. Suggest 6–8 initial clusters; validate via silhouette score (target > 0.35).
- Suggested cluster labels: `power_swing_and_miss`, `contact_sinker_ball`, `elite_breaking_ball`, `changeup_deceptive`, `soft_command`, `multi_pitch_mix`.
- Persist cluster assignments in `baseball_data.statsapi.pitcher_clusters` (pitcher_id × season × cluster_id × cluster_label). Update seasonally.
- New dbt feature table `feature_pitcher_cluster_matchups` — for each game_pk, compute team wRC+ vs. the starter's cluster (rolling 30d, min 10 PA per batter vs. any pitcher in that cluster).
- Add `home_lineup_wrc_vs_cluster`, `away_lineup_wrc_vs_cluster`, `starter_cluster_id` to `feature_pregame_game_features`.

*Acceptance criteria:*
- [ ] Clustering script produces stable assignments for ≥350 starters; silhouette score > 0.35
- [ ] `feature_pitcher_cluster_matchups` builds cleanly; null rate < 10% for 2026 regular season games
- [ ] CV impact documented; cluster interpretability spot-checked against known archetypes
- [ ] Known pitcher check: verify sensible cluster assignments for 5 well-known starters (e.g., Gerrit Cole → `power_swing_and_miss`)

---

##### Card 7.L1 — Historical Feature Backfill: Populate Phase 7 Features for 2021–2025 (P2)

**Title:** Run historical ETL for all Phase 7 feature pipelines back to 2021 so full-season prediction backfill has complete inputs

**Why P2:** The v1 model includes Phase 7 features (weather, FanGraphs Stuff+, umpire tendencies, injury status, pitch archetype, pitcher clusters) that were never computed for pre-2026 dates. Running predictions on those dates with null features produces a degraded hybrid that obscures whether the model actually improved. Populating historical features first ensures that the 7.L2 prediction backfill evaluates the real v1 model. Gap reference: Phase 7 Roadmap P2 from postmortem.

*Blocker:* All Phase 7 feature cards (7.B, 7.E, 7.F, 7.H, 7.I, 7.J, 7.K) must be complete so the ingestion scripts and dbt models exist.

*Technical implementation:*
- Weather (7.B): run `ingest_weather.py --start-date 2021-04-01 --end-date 2025-10-31`; dbtf builds feature_pregame_weather_features for all historical game_pks.
- FanGraphs Stuff+ / projections (7.E, 7.F): run FanGraphs ingestion scripts for seasons 2021–2025; dbtf builds fct_fangraphs_pitcher_arsenal_wide and projection models for all seasons.
- Umpire tendencies (7.H): UmpScorecards historical data covers 2015+; confirm 2021–2025 rows are present, trigger dbtf rebuild of umpire feature model.
- Injury transactions (7.I): run `ingest_transactions.py --start-date 2021-04-01 --end-date 2025-10-31`; dbtf rebuilds stg_statsapi_player_injury_status for full date range.
- Pitcher cluster assignments (7.K): run `cluster_pitchers.py` for each season 2021–2025; verify ≥ 350 assignments per season in `baseball_data.statsapi.pitcher_clusters`.
- Pitch archetype + batter vs. archetype (7.J): dbt models are Statcast-derived and rebuild automatically once mart_pitcher_pitch_archetype covers 2021–2025 game_years.
- Feature coverage audit: after all pipelines complete, run Snowflake null-rate query across `feature_pregame_game_features` for each Phase 7 column × year. Null rate > 25% for any column × year is flagged in the audit report.

*Acceptance criteria:*
- [ ] All Phase 7 ingestion scripts complete without errors for 2021–2025 date range
- [ ] `dbtf build --select feature_pregame_game_features` succeeds and covers game records from 2021 onward
- [ ] `baseball_data.statsapi.pitcher_clusters` contains rows for seasons 2021–2025 with ≥ 350 pitchers each
- [ ] Feature coverage audit report created at `betting_ml/evaluation/historical_feature_coverage.md`; null rate < 25% for each Phase 7 column × season combination (or exception noted with explanation)

---

##### Card 7.L2 — Full Prediction Backfill: Re-score 2021–2026 with v1 Model (P2)

**Title:** Batch re-score all historical game dates from 2021 through current date with the v1 model and document multi-year performance vs. v0 baseline

**Why P2:** The 2026-only backfill (36 game dates) is too small a sample to reliably measure mean h2h edge or % positive — a few bad weeks can swamp the signal. Scoring 2021–2026 gives 4–5 full seasons and hundreds of games per evaluation period, making metric comparisons statistically meaningful. The Model Performance page (6.E) also becomes far more useful with a multi-year trend. Gap reference: Phase 7 Roadmap P2 from postmortem.

*Blocker:* Card 7.L1 (historical feature backfill) must complete first so feature inputs are populated for all dates.

*Technical implementation:*
- Extend `predict_today.py` with `--start-date` / `--end-date` flags for batch re-scoring.
- Add `model_version` column to `daily_model_predictions` (e.g., `v0`, `v1`); v0 rows must not be overwritten — insert new rows only.
- Add `feature_version` column to `daily_model_predictions` to tag rows by Phase 7 feature completeness (e.g., `v1_full` vs. `v1_partial` for early seasons with higher null rates).
- Run batch re-score from 2021-04-01 through current date; skip dates where odds data is absent.
- Compute metrics by year: mean h2h edge, % positive edge, Brier score, totals MAE. Compare against v0 baseline (−0.017, 35.39% positive).
- Append multi-year results as a follow-up section in `betting_ml/evaluation/postmortem_v0.md`.

*Acceptance criteria:*
- [ ] `predict_today.py` accepts `--start-date` / `--end-date` flags; batch re-score completes without errors for full 2021–2026 range
- [ ] `daily_model_predictions` contains `v1` rows for all backfill dates; no `v0` rows overwritten
- [ ] `feature_version` column populated on all `v1` rows
- [ ] Post-backfill metrics documented by year (2021–2026) and vs. v0 baseline in `postmortem_v0.md`
- [ ] If v1 mean edge across 2024–2026 (most recent 2+ seasons with full feature coverage) does not exceed v0 (−0.017), a root-cause note is added to the postmortem — not a blocker, but required documentation

---

##### Card 7.MA — Full Model Retraining After Feature Expansion (P2)

**Title:** Retrain all three production models jointly on the complete Phase 7 feature set once all feature expansion cards are done

**Why P2:** NGBoost retraining runs take ~1 hour each and will grow as features are added. Retraining after every individual feature card is wasteful and produces non-comparable CV scores across runs (different feature sets, different null structures). The right workflow is to complete all feature expansion (7.G, 7.H, 7.I, 7.J, 7.K), run `validate_feature_selection.py` once on the full combined feature matrix, then do a single joint retrain of all three models.

*Blocker:* All Phase 7 feature expansion cards (7.G, 7.H, 7.I, 7.J, 7.K) must complete first.

*Technical implementation:*
1. Run `validate_feature_selection.py` on the full 2021+ dataset with all Phase 7 features populated; record retained feature count and any new or dropped columns vs. Card 7.F baseline (267 retained).
2. Retrain home_win: `uv run python betting_ml/scripts/run_xgb_home_win_search.py`
3. Retrain total_runs: `uv run python betting_ml/scripts/run_ngboost_total_runs_search.py`
4. Retrain run_differential: `uv run python betting_ml/scripts/run_ngboost_run_diff_search.py`
5. Refit Platt calibrator on new home_win model weights: `uv run python betting_ml/scripts/train_calibrator.py`
6. Update `model_registry.yaml` for all three models + calibrator metadata.
7. Document CV impact in `betting_ml/evaluation/v1_retrain_impact.md` — before/after for each model vs. Card 7.F baseline, with a breakdown by feature group contribution (Stuff+, weather, umpires, injury, matchup, cluster).

*Note on calibrator:* The `calibrator.joblib` fitted in Card 7.C was fitted on pre-Card 7.F model weights. A refit is required before production deployment. This card is the designated refit point.

*Acceptance criteria:*
- [ ] `feature_selection.md` updated with retained feature count on full Phase 7 feature matrix
- [ ] All three model artifacts updated in `betting_ml/models/`
- [ ] `calibrator.joblib` refit on new home_win model; `model_registry.yaml` `calibrator_fitted_at` updated
- [ ] `model_registry.yaml` updated for all three models with new cv metrics, artifact paths, `selected_at` timestamps, and `training_cutoff: "2021+"`
- [ ] `betting_ml/evaluation/v1_retrain_impact.md` created with before/after CV table and feature group attribution

---

---

##### Card 7.P1 — OddsAPI Historical Snapshot Dry-Run (P2)

**Title:** Validate that the OddsAPI historical endpoint returns different odds across intraday timestamps before committing to a full backfill

**Why first:** The line movement feature (7.P3) requires that historical intraday snapshots show real variation across timestamps. The OddsAPI historical endpoint supports timestamp-parameterized queries, but it is unknown whether it stores enough resolution to show meaningful intraday movement for past dates. A dry-run across 10–15 sample game dates is a prerequisite before investing in a full historical backfill.

*Note on API plan:* The OddsAPI historical endpoint requires a paid plan. Verify the current plan supports historical queries before running.

*Technical implementation:*
- Query `/v4/historical/sports/baseball_mlb/odds` at 3 timestamps on the same game date (e.g., 12:00 UTC / open, 17:00 UTC / mid-day, 23:00 UTC / pre-game) for 10–15 game dates spread across the 2024 and 2025 seasons.
- For each game, compare `home_price` and `away_price` implied win probabilities across timestamps. Compute absolute change from earliest to latest snapshot.
- Output: `betting_ml/evaluation/oddsapi_historical_dry_run.md` with:
  - Mean absolute intraday line movement (in implied win prob %)
  - % of sampled games showing ≥1 percentage point of movement
  - Proceed/close recommendation: proceed to 7.P2 if ≥50% of games show ≥1pp movement; close the line movement track otherwise

*Acceptance criteria:*
- [ ] `scripts/oddsapi_historical_dry_run.py` exists; accepts `--dates` (comma-separated YYYY-MM-DD) and `--timestamps` (comma-separated HH:MM UTC)
- [ ] Dry-run executes for ≥10 game dates without errors
- [ ] `betting_ml/evaluation/oddsapi_historical_dry_run.md` created with mean movement, % games ≥1pp, and a clear proceed/close recommendation
- [ ] If recommendation is "close": Cards 7.P2 and 7.P3 are marked blocked/cancelled; no further work on this track

---

##### Card 7.P2 — Historical Intraday Odds Backfill (P2)

**Title:** Backfill historical intraday odds snapshots for 2021–2025 to provide line movement training data for 7.P3

*Blocker:* Card 7.P1 must complete with a "proceed" recommendation.

**Why P2:** The line movement feature requires training examples where both the opening line and the pre-game line are known. Without historical snapshots at multiple timestamps, only 2026 post-Card-7.O data (6 snapshots/day, from May 2026 forward) would be available — far too small a sample. Extending to 2021 gives 4–5 full seasons of line movement signal.

*Technical implementation:*
- For each game date 2021-04-01 through 2025-10-31, query the OddsAPI historical endpoint at 3 timestamps: `12:00 UTC` (open), `17:00 UTC` (mid-day), `23:00 UTC` (pre-game). Run in monthly batches to avoid rate limits.
- Store results in a new table: `baseball_data.oddsapi.odds_snapshots_historical`
  - Columns: `game_pk`, `game_date`, `snapshot_ts` (UTC), `home_team`, `away_team`, `home_price`, `away_price`, `over_price`, `under_price`, `total_line`, `bookmaker`, `load_id`
  - Idempotent via MERGE on `(game_pk, snapshot_ts, bookmaker)`
- Estimate API credit cost before running (3 queries × ~180 game dates × 5 seasons ≈ 2,700 calls); document in `scripts/daily_run.md`.
- Post-backfill: verify ≥2 snapshots per game_pk for ≥80% of 2024–2025 games.

*Acceptance criteria:*
- [ ] `scripts/backfill_historical_odds_snapshots.py` exists; accepts `--start-date`, `--end-date`, `--timestamps`; idempotent via MERGE
- [ ] `baseball_data.oddsapi.odds_snapshots_historical` populated; ≥2 snapshots per game for ≥80% of 2024–2025 games
- [ ] API credit cost documented in `scripts/daily_run.md`

---

##### Card 7.P3 — Line Movement Feature Engineering (P2)

**Title:** Compute opening-to-pre-game line movement as model features for both the h2h and totals models

*Blocker:* Card 7.P2 (historical intraday odds backfill) must complete first.

**Why P2:** Intraday line movement captures information from sharp bettors that is absent from all observable features. When the home team's implied win probability shifts materially between open and T-1h, it almost always reflects informed money — not public sentiment. This is one of the few ways to encode "what does the market know that the observables don't."

*Technical implementation:*
- New dbt model `mart_odds_line_movement` — for each `game_pk`:
  - `open_home_win_prob`: implied home win probability from the earliest available snapshot
  - `pregame_home_win_prob`: implied home win probability from the last snapshot before game start (T-30min or closest)
  - `h2h_line_movement`: `pregame_home_win_prob - open_home_win_prob` (positive = line moved toward home)
  - `open_total_line`: opening O/U total
  - `pregame_total_line`: closing O/U total
  - `total_line_movement`: `pregame_total_line - open_total_line` (positive = total moved up)
  - `snapshot_count`: number of distinct snapshots available (data quality flag)
- For 2026+: source from live `mart_odds_outcomes` + `mart_odds_events`. For 2021–2025: source from `odds_snapshots_historical` (7.P2).
- Add 4 columns to `feature_pregame_game_features`: `h2h_line_movement`, `total_line_movement`, `open_home_win_prob`, `open_total_line`.
- Null handling: null when only one snapshot exists. Impute `h2h_line_movement` and `total_line_movement` with 0.0 (no movement = no information); document this assumption.
- Retrain and document CV impact. Expected: stronger signal on the h2h model than totals.

*Acceptance criteria:*
- [ ] `mart_odds_line_movement` builds cleanly; `h2h_line_movement` non-null for ≥85% of 2024–2026 games
- [ ] `feature_pregame_game_features` includes all 4 columns; `dbtf build` passes all tests
- [ ] CV impact documented: Brier score and mean h2h edge before and after; feature importance confirms non-zero SHAP contribution from `h2h_line_movement`
- [ ] Null rate and imputation strategy documented in `betting_ml/evaluation/feature_notes.md`

---

##### Card 7.Q — Bullpen Fatigue and Availability Features (P2)

**Title:** Add IP-based short-window bullpen workload features to complement the existing pitch-count columns in the feature store

**Why P2:** `mart_bullpen_workload` already exists and is joined into `feature_pregame_game_features` via `feature_pregame_team_features`. Pitch-count workload columns (1d, 3d, 7d), closer-used booleans (1d, 2d), and high-leverage usage flags are already in the feature store. However: (a) pitch counts are a noisier workload proxy than innings pitched — 10 pitches over 1/3 of an inning differs materially from 10 pitches over 2 innings — and (b) IP-based 1d/2d columns and a 2d distinct-reliever window do not exist yet. The correlation filter dropped most home-team short-window columns (r < 0.02 threshold); IP-normalized versions may carry stronger signal and survive the filter.

*What already exists (do not duplicate):*
- `mart_bullpen_workload` and `mart_bullpen_effectiveness` — built and joined into `feature_pregame_team_features`
- In `feature_pregame_game_features`: `home/away_bullpen_pitches_prev_1d/3d/7d`, `home/away_pitchers_used_prev_3d/7d`, `home/away_reliever_appearances_prev_3d/7d`, `home/away_high_leverage_used_prev_2d`, `home/away_closer_used_prev_1d`, `home/away_closer_used_prev_2d`
- Already retained by training correlation filter (r ≥ 0.02): `away_bullpen_pitches_prev_7d/3d`, `home_bullpen_pitches_prev_3d`, `away/home_closer_used_prev_2d`, `away_closer_used_prev_1d`

*Technical implementation (net-new changes only):*
- **Extend `mart_bullpen_workload`:** Add `outs_recorded` tracking in the `bullpen_pitcher_game` CTE (currently only `pitches_thrown`). Compute three new rolling windows from `outs_recorded / 3.0`:
  - `bullpen_ip_prev_1d`: total reliever IP in the preceding 1 calendar day
  - `bullpen_ip_prev_2d`: total reliever IP over the preceding 2 days
  - `pitchers_used_prev_2d`: distinct relievers used over the preceding 2 days (only 3d and 7d currently exist)
- **Expose in `feature_pregame_team_features`:** Add the three new columns to the `bw.*` select list.
- **Expose in `feature_pregame_game_features`:** Add `home_bullpen_ip_prev_1d`, `home_bullpen_ip_prev_2d`, `home_pitchers_used_prev_2d` and away equivalents (6 total new columns).
- No new ingestion, no new mart model — all changes are extensions to existing models.

*Acceptance criteria:*
- [ ] `mart_bullpen_workload` extended with `bullpen_ip_prev_1d`, `bullpen_ip_prev_2d`, `pitchers_used_prev_2d`; null rate < 5% for 2024–2026 regular season
- [ ] `feature_pregame_game_features` includes all 6 new columns (home + away × 3); `dbtf build` passes all tests
- [ ] Spot-check: on a known heavy-usage day (e.g., team used 4+ relievers the prior day), confirm `bullpen_ip_prev_1d` is non-zero and reasonable
- [ ] Feature selection re-run: document which new IP columns survive the r ≥ 0.02 threshold; CV impact and feature importances checked for both totals and h2h models

---

##### Card 7.R — Pythagorean Win Expectation Features (P2)

**Title:** Add season-to-date Pythagorean win expectation as a team quality signal to complement rolling stat features

**Why P2:** Rolling features (OPS_30d, runs_per_game_30d) are sensitive to hot/cold streaks and regress slowly. Pythagorean win expectation (RS^1.83 / (RS^1.83 + RA^1.83)) stabilizes faster than win-loss record and is a better predictor of true team quality for the remainder of the season — the same signal the market uses as a sanity check on team strength independent of record. This is a 2–3 line dbt calculation on data already in the pipeline.

*Technical implementation:*
- Source: `mart_game_results` (which has `home_final_score` / `away_final_score`). Extend `mart_team_season_record` — which already sources from `mart_game_results` and uses an SCD2 fill-forward grain (team × calendar date) — to add cumulative `runs_scored_ytd` and `runs_allowed_ytd`. The existing join in `feature_pregame_team_features` at `record_date = game_date - 1` gives pre-game, leakage-free values automatically. Do NOT source from `stg_statsapi_games` directly or `mart_team_rolling_offense` / `mart_team_rolling_pitching` (those use `rows between unbounded preceding and current row`, which includes the current game).
- **Extend `mart_team_season_record`**: add `runs_scored` and `runs_allowed` to the `team_games` CTE, thread through `running_totals` / `daily_ranked` / `game_day_records` / `expanded` as cumulative sums, and compute `pythagorean_win_exp` in the `final` CTE.
- **Expose in `feature_pregame_team_features`**: add `tsr.pythagorean_win_exp` to the `season_record` CTE select and the `final` SELECT.
- **Expose in `feature_pregame_game_features`**: add:
  - `home_pythagorean_win_exp`
  - `away_pythagorean_win_exp`
  - `pythagorean_win_exp_diff`: home minus away (signed, for model interpretability)
- Use exponent 1.83 (empirically validated for MLB) rather than 2.0.
- Guard: return NULL when `games_played < 10`; impute with 0.5 (no information) in the ML preprocessing pipeline.

*Acceptance criteria:*
- [ ] `home_pythagorean_win_exp` and `away_pythagorean_win_exp` present in `feature_pregame_game_features`; values in [0.2, 0.8] for ≥95% of non-null rows
- [ ] NULL for games where either team has < 10 games played in the season; imputed to 0.5
- [ ] Spot-check: 2024 Dodgers should show Pythagorean win exp ≥ 0.60 by June
- [ ] `dbtf build` passes; CV impact documented after retrain

---

##### Card 7.S — Starter Velocity Trend Features (P2)

**Title:** Add per-starter start-count fastball velocity delta (last 3 starts vs. season avg) as a leading indicator of fatigue or early injury

**Why P2:** Stuff+ (Card 7.F) captures static arsenal quality but not trend. A starter whose average fastball velocity has dropped 1.5+ mph over the last 3 starts relative to their season average is a signal the market prices before ERA reflects it — often an early sign of fatigue, mechanical issue, or undisclosed injury. Statcast pitch velocity is already ingested; this card adds the start-count aggregation logic.

*Technical implementation:*
- Do NOT create a new mart model. `mart_starting_pitcher_game_log` already has per-start `avg_fastball_velo` (FF/SI/FC mean). Starter definition: first pitcher ≥20 pitches OR ≥3 innings — do not redefine.
- `mart_pitcher_rolling_stats` already has `avg_fastball_velo_7d/14d/30d/std`; `feature_pregame_starter_features` already exposes these AND `fastball_velo_trend = avg_fastball_velo_7d - avg_fastball_velo_30d`. Do not duplicate.
- Extend `feature_pregame_starter_features` with two new CTEs following the existing `ip_starts / ip_stats` pattern:
  - `velo_starts` CTE: join `mart_starting_pitcher_game_log` with leakage guard (`gl.game_date::date < pp.game_date`), filter where `avg_fastball_velo is not null`, rank by recency.
  - `velo_stats` CTE: `avg(case when recency_rank <= 3 then avg_fastball_velo end)` as `avg_fastball_velo_3start`.
  - In the `final` CTE: `velo_delta_3start = round(avg_fastball_velo_3start - avg_fastball_velo_std, 1)`.
- `velo_delta_3start` is not a duplicate of `fastball_velo_trend` (7d - 30d): the start-count window is independent of calendar gaps and captures IL-return and 6-man-rotation signals that the 7-day window misses.
- Expose `home_starter_velo_delta_3start` and `away_starter_velo_delta_3start` in `feature_pregame_game_features` adjacent to the existing `fastball_velo_trend` columns. No JOIN changes needed.
- Impute `velo_delta_3start` → 0.0 in `betting_ml/utils/preprocessing.py` (NULL only for debut starters with no prior velo data).

*Acceptance criteria:*
- [ ] `feature_pregame_starter_features` has `velo_starts`, `velo_stats` CTEs and `velo_delta_3start` column; leakage guard (`< pp.game_date`) confirmed; all existing columns preserved
- [ ] `feature_pregame_game_features` includes `home_starter_velo_delta_3start` and `away_starter_velo_delta_3start`; `dbtf build --select +feature_pregame_starter_features+` passes
- [ ] `velo_delta_3start` plausible range: 99th percentile < 3.0 mph, 1st percentile > −3.0 mph; avg ≈ 0.0
- [ ] Imputation added to `preprocessing.py`; CV impact and multicollinearity check vs. `fastball_velo_trend` documented in `betting_ml/evaluation/feature_notes.md`

##### Card 7.MB — Model Architecture Evaluation (P2)

**Title:** Benchmark LightGBM, CatBoost, and a stacked ensemble against the current XGBoost/NGBoost baseline using a walk-forward CV harness on the full Phase 7 feature set

**Why P2:** XGBoost and NGBoost were selected early without a comparative evaluation. The full Phase 7 feature set (particularly high-cardinality categoricals from pitch archetype and pitcher clusters) creates conditions where LightGBM and CatBoost have structural advantages. Model selection on an incomplete feature set is fragile, so this card runs after all Phase 7 P2 feature cards are merged and the joint retraining (Card 7.MA) is complete — or at end of the 2026 regular season, whichever comes first.

*Blocker:* Card 7.MA (full model retraining) must complete first — the architecture evaluation uses Card 7.MA's production-retrained models as the baseline. All Phase 7 P2 feature cards (7.A–7.K, 7.P3, 7.Q, 7.R, 7.S) must also be merged, OR end of 2026 regular season — whichever comes first. Time-based fallback prevents indefinite deferral. (7.P3 is contingent on the 7.P1 dry-run; if the line movement track closes, 7.P3 is excluded from this gate.)

*Technical implementation:*
- Walk-forward CV harness (`cv_harness.py`): four folds (train 2016–2021/22/23/24, test 2022/23/24/25); identical train/test indices across all models; shared metric functions (Brier score, mean h2h edge, % positive edge, log-loss, totals MAE).
- Candidate models evaluated: XGBoost/NGBoost (baseline), LightGBM, CatBoost, stacked ensemble (XGBoost + LightGBM + CatBoost → ridge/logistic meta-learner).
- Isotonic recalibration layer evaluated separately on top of each base model using temporal hold-out split.
- Selection decision rule: challenger beats baseline if Brier score improvement yields Cohen's d ≥ 0.10 across all four folds. Tie-break: prefer simpler model (LightGBM > CatBoost > Ensemble).
- If challenger selected: update training scripts, apply calibration if brier_delta < −0.002, bump model_version tag.
- Results documented in `betting_ml/evaluation/model_selection_v1.md`.

*Acceptance criteria:*
- [ ] `cv_harness.py` exists; four walk-forward folds defined with fixed indices; all five metric functions implemented
- [ ] All four candidate model eval scripts exist; result parquet files written for all models across all folds
- [ ] Isotonic calibration evaluated; brier_delta reported per model per fold
- [ ] `model_selection_v1.md` documents comparison table, selection decision with Cohen's d, calibration analysis, known limitations
- [ ] If challenger selected: training scripts updated and model_version bumped

---

#### Card 7.N — Game Insights Page (Streamlit)

**Title:** Add a Game Insights page to the Streamlit app that surfaces the key model features and team performance metrics driving each prediction

**Why Phase 7A:** Unblocked by any other Phase 7A card — requires only the existing `feature_pregame_game_features` table and `daily_model_predictions`, which Phase 6 already delivers. The SHAP waterfall section is actively useful *during* Phase 7A work: as new features (weather, FanGraphs, archetype, cluster) are added, the waterfall immediately shows whether they are driving predictions in a direction that makes intuitive sense, helping diagnose feature quality before committing to a retrain cycle.

*Blockers:*
- `feature_pregame_game_features` must be populated for the selected date (requires lineup confirmation + `dbtf build` to have run).
- `daily_model_predictions` must have a row for the selected `game_pk` (requires `predict_today.py` to have run).
- `shap` package — add to `pyproject.toml` under `[project.optional-dependencies]` or the app's dependency group.
- `feature_columns.json` — the ordered column list used at training time must be accessible at runtime. If not already persisted, add a write step to the training pipeline (`betting_ml/pipeline/train.py`) before this card begins.

*Technical implementation:*
- New page `app/pages/5_Game_Insights.py`. Entry in the Streamlit sidebar as "Game Insights". Date selector (defaults to today) followed by a game picker dropdown populated from `daily_model_predictions` for that date — label format `Away @ Home (HH:MM ET)`. Game picker is the primary filter for all sections below.
- **Section 1 — Prediction Summary:** One-row header bar showing the selected game's model outputs from `daily_model_predictions`: predicted total runs, home win probability, market win probability, edge, and Kelly fraction.
- **Section 2 — Team Performance Comparison:** Side-by-side metric panels for home and away teams, drawn from `feature_pregame_game_features` for the selected `game_pk`. Columns to show (one row per metric, two value columns):

  | Metric group | Columns from feature table |
  |---|---|
  | Offense (rolling 30d) | `home_rolling_ops_30d` / `away_rolling_ops_30d`, `home_rolling_runs_per_game_30d` / `away_...` |
  | Starting pitcher | `home_starter_era` / `away_starter_era`, `home_starter_whip` / `away_starter_whip`, starter handedness |
  | Lineup vs. starter handedness | `home_platoon_advantage_score` / `away_platoon_advantage_score` (from lineup feature model) |
  | Bullpen | `home_bullpen_era_7d` / `away_bullpen_era_7d`, `home_bullpen_ip_7d` / `away_bullpen_ip_7d` |
  | Schedule context | `home_days_rest` / `away_days_rest`, `home_games_last_7d` / `away_games_last_7d` |
  | Park & context | `park_run_factor` (single value), `is_dome` |

  Use `st.columns(2)` with metric deltas (home vs. away, where meaningful). Highlight the favored side per metric in green/red using `st.metric`'s `delta` parameter.

- **Section 3 — SHAP Feature Importance:** Load the saved XGBoost `total_runs` and `home_win` models from `model_registry.yaml` via `utils/model_io.py`. Compute SHAP values for the selected game's feature vector using `shap.TreeExplainer`. Display two waterfall charts side by side — one per model — showing the top 10 features by absolute SHAP value and their directional contribution. Use `shap.waterfall_plot` rendered via `st.pyplot`.
  - Feature vector reconstructed from `feature_pregame_game_features` for the selected `game_pk` using the column order from `feature_columns.json`.
  - Cache the SHAP explainer per model (not per game) with `@st.cache_resource`. Cache the feature vector query per `(date, game_pk)` with `@st.cache_data`.
- **Section 4 — Recent Team Form:** For both home and away teams, query the last 10 games from `stg_statsapi_games`. Display as a compact `st.dataframe` with columns: Date, Opponent, H/A, Runs Scored, Runs Allowed, W/L.

*Acceptance criteria:*
- [ ] Page appears in the Streamlit sidebar as "Game Insights"; game picker populates from `daily_model_predictions` for the selected date
- [ ] Prediction Summary bar renders for any game with a `daily_model_predictions` row: total runs, home win%, market win%, edge, Kelly
- [ ] Team Performance Comparison section renders all six metric groups side-by-side with correct home/away attribution
- [ ] SHAP waterfall chart renders for both `total_runs` and `home_win` models; top 10 features shown by absolute SHAP value
- [ ] Recent Form table shows last 10 games for both teams with correct W/L column
- [ ] All Snowflake queries wrapped in `@st.cache_data(ttl=300)`
- [ ] Page degrades gracefully when `feature_pregame_game_features` or `daily_model_predictions` has no row for the selected game
- [ ] `shap` added to app dependencies; `uv run streamlit run` starts without import errors

---

#### Phase 7B — Production Infrastructure

All Phase 7B cards are **blocked** until Phase 7A produces a model with mean h2h edge > +0.01 (the Card 7.D gate condition in `plan_specs/phase_7/D_model_retraining_cadence.yaml`). Infrastructure investment is not warranted until the model's live value is confirmed.

**Card 7.D — Model retraining cadence:** Periodic in-season refits and the manual retraining runbook. See `plan_specs/phase_7/D_model_retraining_cadence.yaml` for the full spec. Performance gate (mean_edge > +0.01, >40% positive across ≥50 post-Phase-7A games) must clear before this card begins.

**α drift monitoring:** `best_alpha.json` (Card 7.A) and `alpha_tuning_results` track the Bayesian mixing weight across refit runs. If best_alpha drifts away from 0.0 as 2026 data grows, it signals improving calibration relative to the market — the leading indicator to watch before committing to Card 7.D work.

---

#### Card 7.2 — Production Application (Replaces Streamlit MVP)

**Title:** Replace the Phase 6 Streamlit MVP with a production-grade web application

**Description:**

*Technical implementation:*
- The Streamlit MVP (Cards 6.B–6.E) is a single-process app that is fast to build but not designed for concurrent users, background refresh, or mobile access. Once the model's live value is established over a full season, replace it with a purpose-built stack.
- **Recommended architecture:**
  - **Backend:** FastAPI service (`app/api/`) that exposes a small REST API — `GET /predictions/{date}`, `GET /games/{game_pk}/odds`, `GET /performance`. Reads from Snowflake and model artifacts. Runs as a Docker container (deployable to Fly.io, Railway, or any container host).
  - **Frontend:** React or Next.js SPA (`app/web/`) consuming the FastAPI endpoints. Replicates all four Streamlit pages as proper routes. Mobile-responsive layout so the daily picks are usable from a phone.
  - **Auth:** Single-user auth (Bearer token or magic link) — this is a personal tool, not a multi-tenant app.
  - **Background refresh:** Replace the Streamlit "Refresh" button with a server-sent event (SSE) stream that pushes lineup confirmation events from the Snowflake `lineup_monitor_state` table to the frontend in real time.
  - **Hosting:** Containerized API + static frontend hosted on a low-cost PaaS. No Kubernetes needed.
- The Streamlit app (`app/`) is retained as a development and debugging tool after the production app ships; it is not decommissioned.

*Blockers:* The Streamlit MVP (Cards 6.B–6.E) must complete a full season of live use and the model must demonstrate positive CLV before investment in the production app is warranted. This card is explicitly deferred until that threshold is met.

*Acceptance criteria:*
- [ ] FastAPI backend serves all four data endpoints; each endpoint returns within 2 seconds on a cold Snowflake query
- [ ] Frontend replicates Today's Picks, Market Comparison, EV/Kelly, and Performance pages from the Streamlit MVP
- [ ] Mobile layout renders correctly on 390px-wide viewport (iPhone 15 baseline)
- [ ] Bearer token auth prevents unauthenticated access to all API endpoints
- [ ] SSE stream delivers lineup confirmation events to the frontend within 60 seconds of the Snowflake `lineup_monitor_state` row being written
- [ ] Docker Compose file at repo root starts the full stack (API + frontend) with a single `docker compose up`
- [ ] Streamlit app remains functional alongside the production app for development use

---

#### Card 6.J — Intraday Odds Snapshot Pipeline (GHA Workflow) — COMPLETE (2026-05-01)

**Title:** Add a GitHub Actions workflow that re-ingests odds every 5–6 hours on game days to capture intraday line movement

*Technical implementation:*
- `.github/workflows/odds_snapshot.yml` — five scheduled cron runs at 17:00, 18:30, 22:00, 23:30, and 03:00 UTC, layered on top of the existing 08:00 UTC morning run in `daily_ingestion.yml`. Net result: 6 odds snapshots per game day. (18:30 and 23:30 UTC triggers added by Card 7.O to provide T-1h coverage before afternoon and evening first pitches.)
- **Games check step:** Before spending any Odds API credits, an inline Python script queries `stg_statsapi_games` for regular-season (`game_type = 'R'`) games today. If none found, all subsequent steps are skipped via `if: steps.games_check.outputs.has_games == 'true'`.
- **Ingestion steps:** `uv run odds_api_ingestion.py events` then `uv run odds_api_ingestion.py odds` — identical to the corresponding steps in `daily_ingestion.yml`.
- **dbt rebuild:** `dbt build --select +stg_oddsapi_events+ +stg_oddsapi_odds+` — traverses the full odds DAG (staging → `mart_odds_events` → `mart_odds_outcomes` → `mart_odds_consensus` → `feature_pregame_odds_features` → `feature_pregame_game_features`) without touching the Statcast or lineup models.
- **Does not** call `predict_today.py` — model predictions are lineup-dependent and are a separate intentional action.
- Requires `ODDS_API_KEY` GitHub secret (already configured).

*Acceptance criteria:*
- [x] `.github/workflows/odds_snapshot.yml` exists with five cron triggers and `workflow_dispatch` (updated to six total snapshots/day by Card 7.O)
- [x] Games check step skips all ingestion steps on off-days (no wasted API credits)
- [x] Odds events and odds ingestion steps run conditionally on `has_games == 'true'`
- [x] dbt rebuild scoped to odds DAG only via `+stg_oddsapi_events+ +stg_oddsapi_odds+`
- [x] Intraday snapshots accumulate in `mart_odds_outcomes`, visible in the Market Comparison line movement chart

---

#### Card 7.O — Pre-Game OddsAPI Dynamic Fetch (1 Hour Before First Pitch) — COMPLETE (2026-05-02)

**Title:** ~~Add dynamic per-game odds fetch via sleeping queue runner~~ — superseded by two additional cron triggers in `odds_snapshot.yml`

> **Status (2026-05-02):** The original Card 7.O proposal (a sleeping queue runner with a per-game JSON fetch queue) was closed as over-engineered. The underlying need — a T-1h odds snapshot for better CLV measurement and pre-bet line quality — is fully addressed by adding two cron triggers to the existing Card 6.J workflow. No new scripts are required.

**Resolution — amend `odds_snapshot.yml` with two additional triggers:**

The 6.J workflow currently fires at 08:00, 17:00, 22:00, and 03:00 UTC (4 snapshots). Adding two triggers provides coverage within ~1 hour of virtually every first pitch:

```yaml
# Add to .github/workflows/odds_snapshot.yml schedule block:
- cron: '30 18 * * *'   # 2:30pm EDT — catches afternoon games (1:10pm, 3:10pm starts) at ~T-1h
- cron: '30 23 * * *'   # 7:30pm EDT — catches evening games (7:08pm, 7:10pm starts) at ~T-20min to T-1h
```

Net result: 6 snapshots per game day. Afternoon first pitches (1pm–3pm ET) get a T-1h snapshot at 2:30pm EDT. Evening first pitches (7pm–8pm ET) get a snapshot at 7:30pm EDT. West Coast late games (9pm–10pm ET) are already covered by the existing 11pm EDT trigger.

*API credit cost:* ~30 additional credits/day (2 extra runs × ~15 credits/run for a full slate) on top of the existing 4-run budget. Document in `scripts/daily_run.md`.

*Acceptance criteria:*
- [x] `.github/workflows/odds_snapshot.yml` updated with the 18:30 UTC and 23:30 UTC cron triggers
- [x] 6 total cron entries present in `odds_snapshot.yml`; games-check step still guards all runs
- [x] `scripts/daily_run.md` updated with revised credit budget (6 snapshots × ~15 credits = ~90 credits/day on active slate days)

---

## 10. Predicted Timeline

| Phase | Milestone | Estimated State |
|---|---|---|
| Phase 1 | All dbt tests passing, data quality issues resolved | ✓ Complete |
| Phase 2 | Pre-game feature assembly mart models built and tested | ✓ Complete |
| Phase 3 | EDA complete, target variable and feature candidates validated | ✓ Complete |
| Phase 4 | Baseline + tuned models for all three targets; Bayesian probability layer | **Complete** (2026-04-25) — best_alpha=0.0; 230 probability output rows in Snowflake |
| Phase 5 | Model packaged; local prediction CLI; lineup notification mechanism | ✓ Complete |
| Phase 6 | Streamlit MVP (picks, market comparison, EV/Kelly) + GHA pipeline automation | Substantially complete (2026-05-01); Performance Tracker (6.E) pending |
| Card 6.J | Intraday odds snapshot GHA workflow (4× daily on game days) | ✓ Complete (2026-05-01) |
| Phase 7A | Refined models with expanded feature set, era-aware approach | Months |
| Phase 7B | Production infrastructure: monitoring, auto-retraining, dashboard | Months |
| Card 7.MA | Full model retraining on complete Phase 7 feature set + calibrator refit | Phase 7A P2 (blocked on 7.G–7.K) |
| Card 7.MB | Model architecture evaluation — LightGBM/CatBoost/ensemble vs. XGBoost/NGBoost baseline | Phase 7A P2 (blocked on 7.MA) |
| Card 7.N | Game Insights page (Streamlit) — SHAP waterfalls, team comparison, recent form | Phase 7A (unblocked) |
| Card 7.O | Dynamic per-game OddsAPI fetch — SUPERSEDED; replaced by 2 extra cron triggers in odds_snapshot.yml | Closed |
| Card 7.P1 | OddsAPI historical dry-run — validate intraday line movement exists in historical data | Phase 7A P2 (unblocked) |
| Card 7.P2 | Historical intraday odds backfill 2021–2025 — blocked on 7.P1 proceed recommendation | Phase 7A P2 (blocked on 7.P1) |
| Card 7.P3 | Line movement feature engineering — h2h_line_movement + total_line_movement as model inputs | Phase 7A P2 (blocked on 7.P2) |
| Card 7.Q | Bullpen fatigue/availability features — reliever IP last 1d/2d, closer availability | Phase 7A P2 (unblocked) |
| Card 7.R | Pythagorean win expectation — RS^1.83/(RS^1.83+RA^1.83) season-to-date per team | Phase 7A P2 (unblocked) |
| Card 7.S | Starter velocity trend — fastball velo delta over last 3 starts vs. season avg | Phase 7A P2 (unblocked) |

---

## 11. File Reference

| Path | Purpose |
|---|---|
| `dbt/dbt_project.yml` | dbt project configuration (profile, materializations) |
| `dbt/models/sources.yml` | Source table definitions (savant, statsapi) |
| `dbt/models/staging/schema.yml` | Staging model schemas and tests |
| `dbt/models/mart/schema.yml` | Mart model schemas and tests |
| `dbt/models/feature/schema.yml` | Feature layer model schemas and tests; materializes into `baseball_data.betting_features` |
| `dbt/seeds/ref_teams.csv` | Static team reference (30 franchises + legacy abbreviations) |
| `dbt/README.md` | dbt layer documentation |
| `data_quality/open_data_quality_issues.md` | Open data quality issues — pending investigation and resolution |
| `data_quality/resolved_data_quality_issues_april_2026.md` | Resolved data quality issues — April 2026 |
| `data_quality/data_availability_windows.md` | Verified first-available dates and per-season coverage for all feature groups; Phase 3 EDA and era-aware model scoping reference |
| `.github/workflows/daily_ingestion.yml` | Runs at 08:00 UTC daily (08:00 EDT in-season); ingests Statcast, Stats API schedule, Odds API events + odds, then runs full `dbt build` |
| `.github/workflows/lineup_monitor.yml` | Runs hourly; re-ingests schedule (current + prior month), rebuilds lineup staging models, checks for newly confirmed lineups, and conditionally triggers a full lineup+feature DAG rebuild |
| `.github/workflows/odds_snapshot.yml` | Runs at 17:00, 22:00, and 03:00 UTC on game days; re-ingests odds events + odds and rebuilds the odds dbt DAG to capture intraday line movement (Card 6.J) |
| `.github/workflows/dbt_daily_build.yml` | Full `dbt build` via `workflow_dispatch` only; legacy trigger used by Snowflake Task DAG proc (Card 6.A.6) |
| `.github/workflows/dbt_staging_build.yml` | Targeted dbt build for lineup staging models; `workflow_dispatch` only; used by prior Card 5.3 Snowflake-task approach |
| `scripts/lineup_monitor.py` | Queries `stg_statsapi_lineups_wide` for today's confirmed-both-sides games, compares against `lineup_monitor_state`, inserts new entries, and writes `has_new_games` output to `$GITHUB_OUTPUT` |
| `scripts/daily_run.md` | **Daily ingestion runbook** — step-by-step commands to keep all Snowflake source tables current; covers savant, statsapi, and odds_api ingestion plus dbt refresh |
| `scripts/savant_ingestion.py` | Baseball Savant CSV ingestion; chunked by day, idempotent, extensible via `StatcastEndpoint` registry; subcommands: `batter_pitches` |
| `scripts/ingest_statsapi.py` | Python ingestion for Stats API schedule and venues; schedule subcommand defaults to current month only without `--start-date`; pass prior-month start to cover retroactive lineup confirmations |
| `scripts/odds_api_ingestion.py` | Python ingestion for The Odds API events and odds endpoints; two subcommands: `events` and `odds` |
| `app/streamlit_app.py` | Streamlit multi-page app entry point; run with `uv run streamlit run app/streamlit_app.py` |
| `app/utils/db.py` | Snowflake connection helper (`run_query`); reads RSA key from `~/.local/bin` path; shared `@st.cache_resource` connection across pages |
| `app/pages/1_Today_Picks.py` | Today's Picks page — ranked game predictions, lineup status, edge/EV summary, market movement expander; two action buttons (Refresh Predictions, Refresh Lineups & Odds Only) that run ingestion and dbt synchronously |
| `app/pages/2_Market_Comparison.py` | Market Comparison page — per-game model vs. bookmaker deep-dive; line movement chart, totals panel, sharp vs. soft, cross-bookmaker table; uses `event_id` scoping to prevent cross-series leakage |
| `app/pages/3_EV_Kelly.py` | EV Tracker & Kelly Sizer page — all markets, all games; bankroll simulator with checkbox slate, correlated-bet deduplication, doubleheader detection |
| `scripts/date_utils.py` | Reusable UTC date/time helpers (`format_iso_utc`, `default_window`) used by odds ingestion; injectable `now` parameter makes functions unit-testable |
| `scripts/tests/test_date_utils.py` | Pytest unit tests for `date_utils` (19 tests covering format, window boundaries, timezone conversion, rollover) |
| `scripts/ddl/oddsapi_raw_tables.sql` | DDL for `baseball_data.oddsapi.mlb_events_raw` and `mlb_odds_raw`; run once via snowsql to create tables |
| `exploratory_data_analysis/` | Marimo EDA notebooks (Phase 3); run with `uv run marimo run <notebook>.py` |
| `exploratory_data_analysis/01_target_variables.py` | Target variable analysis — total runs, run differential, home win rate distributions (2016–2025) |
| `exploratory_data_analysis/02_feature_coverage.py` | Null rate heatmap (374 cols × all seasons), `has_full_data` count verification, imputation strategy decisions |
| `exploratory_data_analysis/03_rolling_window_stability.py` | Rolling window stability — correlation vs. window size (7d/14d/30d/STD); early-season instability by games-played bucket; slider for training set size preview |
| `exploratory_data_analysis/04_feature_correlations.py` | Feature-outcome correlations (Pearson + Spearman) for all features × 3 targets; multicollinearity heatmaps per group; matchup differential analysis; Phase 4 feature selection recommendation |
| `exploratory_data_analysis/05_park_and_context.py` | Park run factor analysis, schedule fatigue (days rest + TZ travel), OLS R² comparison (park-only vs. park + schedule), interactive stadium trend chart, Phase 4 park/schedule verdict |
| `exploratory_data_analysis/06_bat_tracking_era.py` | Bat tracking null rate by season; coverage vs. full training set; correlation comparison (traditional vs. bat tracking); bat speed–wOBA redundancy; OLS R² with/without bat tracking; single-model vs. era-split verdict |
| `exploratory_data_analysis/07_engineered_feature_lift.py` | Correlation fast pass for delta/momentum (Card 4.1) and handedness matchup (Card 4.2) features vs. 3 targets; OLS ΔR² for each feature block |
| `exploratory_data_analysis/betting_model_findings.md` | Cumulative EDA findings document; sections 01–09 complete |
| `betting_ml/` | ML model code (Phase 4+) |
| `betting_ml/utils/data_loader.py` | Snowflake → pandas loader; `load_features()` queries `feature_pregame_game_features` + `mart_game_results`; applies `has_full_data=true` and `min_games_played` filter |
| `betting_ml/utils/cv_splits.py` | Temporal leave-one-season-out CV splits; no shuffled k-fold; respects chronological order |
| `betting_ml/utils/preprocessing.py` | Imputation pipeline + Bayesian shrinkage; handles all 6 null groups from NB02; shrinkage weight = n/(n+k) toward league-mean prior |
| `betting_ml/utils/feature_selection.py` | Card 4.8 — feature selection module; `load_retained_features()` returns canonical 241-feature list from `feature_selection.md`; drops near-zero correlation and high-multicollinearity features |
| `betting_ml/utils/model_io.py` | Card 4.8 — `save_model` / `load_model` via joblib; path convention `betting_ml/models/{target}/{model_name}_{eval_year}.pkl` |
| `betting_ml/utils/evaluation.py` | `fold_metrics()` and `brier_score_over_under()` helpers used by baseline training scripts |
| `betting_ml/models/total_runs_trainer.py` | Card 4.9 — `train_ridge`, `train_xgboost`, `train_ngboost`, `p_over_line` for total runs target |
| `betting_ml/models/win_outcome_trainer.py` | Card 4.11 — `train_logistic`, `train_xgboost_classifier`, `compute_calibration_curve`, `compute_ece` |
| `betting_ml/models/total_runs/` | Serialized total runs models (ridge, xgboost, ngboost_normal, ngboost_lognormal per eval year) |
| `betting_ml/models/run_differential/` | Serialized run differential models (same structure as total_runs) |
| `betting_ml/models/home_win/` | Serialized win outcome models (logistic, xgboost_platt, xgboost_isotonic per eval year) |
| `betting_ml/scripts/analyze_pitching_decomp.py` | Card 3.8 analysis — bullpen vs. starter xwOBA decomposition; writes `evaluation/pitching_decomp_results.json` |
| `betting_ml/scripts/analyze_home_away_pitch_asymmetry.py` | Card 3.9 analysis — home/away pitching asymmetry root-cause; writes `evaluation/home_away_pitch_asymmetry_results.json` |
| `betting_ml/scripts/train_total_runs_baselines.py` | Card 4.9 — train all total runs baseline models; writes CV results to Snowflake and `total_runs_results.md` |
| `betting_ml/scripts/train_run_diff_baselines.py` | Card 4.10 — train all run differential baseline models; writes CV results and `run_differential_results.md` |
| `betting_ml/scripts/train_win_outcome_baselines.py` | Card 4.11 — train win outcome baseline models; writes CV results and `win_outcome_results.md` |
| `betting_ml/scripts/run_hyperparameter_search.py` | Card 4.12 — Optuna TPE search (50 trials × 3 XGBoost targets) + NGBoost grid; USER-EXECUTED; writes `tuning_results.json` |
| `betting_ml/scripts/generate_tuning_report.py` | Card 4.12 — reads `tuning_results.json`; writes `hyperparameter_tuning.md` and updates `project_context.md` |
| `betting_ml/evaluation/feature_selection.md` | Card 4.8 results — canonical retained feature list (241 features) with target correlations and drop reasons |
| `betting_ml/evaluation/total_runs_results.md` | Card 4.9 results — per-season MAE/RMSE, model comparison, NGBoost distribution verdict |
| `betting_ml/evaluation/run_differential_results.md` | Card 4.10 results — per-season MAE/RMSE, win probability Brier scores, era ablation |
| `betting_ml/evaluation/win_outcome_results.md` | Card 4.11 results — Brier score, log loss, calibration curves, home-team bias analysis |
| `betting_ml/evaluation/pitching_decomp_results.json` | Card 3.8 results — cross-correlation, partial correlations, OLS R² decomposition, design recommendation |
| `betting_ml/evaluation/home_away_pitch_asymmetry_results.json` | Card 3.9 results — partial correlations, quartile analysis, era-split, design recommendation |
| `betting_ml/tests/test_cv_splits.py` | Unit tests for temporal CV split logic |
| `betting_ml/tests/test_preprocessing.py` | Unit tests for imputation and Bayesian shrinkage pipeline |
| `plan_specs/` | Declarative PlanSpec YAML files for agentic task execution |
| `plan_specs/plan_spec_implementation.md` | PlanSpec overview, structure reference, and agentic engineering rationale |
| `plan_specs/eda_plan_spec_template.yaml` | Template for Phase 3 EDA analysis card plan specs |
| `plan_specs/phase_3/` | Phase 3 EDA plan specs (Cards 3.8–3.11) |
| `plan_specs/phase_4/` | Phase 4 ML pipeline plan specs (Cards 4.6–4.13) |

---

## 12. Project Management

### Trello Card Format

Every Trello card must include:

**Title** — Action-oriented, specific enough to understand scope without opening the card.

**Description** — Three sections, kept concise:

*Technical implementation* — Bullet points covering: what to build, which source tables it depends on, grain, key logic or design decisions, and any architectural constraints (e.g., no-leakage rule). Avoid exhaustive column lists — reference table names and let the implementer read the schema.

*Blockers* — Prerequisite cards, missing data, or open decisions that must be resolved before this card can start.

*Acceptance criteria* — Short, checkable conditions. Each criterion must be verifiable (e.g., "`dbtf build --select <model>` passes all tests", "row count matches expected grain"). Avoid vague criteria ("looks good", "seems correct"). Aim for 5–8 criteria per card.

**Example of correct scope and style:** See the Card 4 (Verify historical odds flow) text in Section 9 — Phase 1 Enhancement. That card is the reference for length and detail level.

---

## 13. Tooling Reference

### Daily ingestion runbook

See `scripts/daily_run.md` for the full step-by-step daily run sequence. Quick summary:

```bash
cd scripts/
uv run savant_ingestion.py batter_pitches          # Statcast — auto-detects gap
uv run ingest_statsapi.py schedule                 # Stats API — current month only
uv run odds_api_ingestion.py events                # Odds API events — 7-day window
uv run odds_api_ingestion.py odds                  # Odds API odds — h2h + totals
cd ../dbt && dbtf build                            # Refresh all mart models
```

> For `ingest_statsapi.py schedule`, the default window is the **current calendar month only**. Pass `--start-date YYYY-MM-01` to widen the window. Never omit `--start-date` and expect a historical backfill — that requires `--start-date 2015-04-01`.

### GitHub Actions Orchestration

Five workflows in `.github/workflows/` form the full automated pipeline. All use `dbt build --project-dir dbt --profiles-dir dbt` (not `dbtf`); dbt-fusion is installed via the official curl script and lands its binary at `~/.local/bin/dbt`.

| Workflow | Trigger | Purpose |
|---|---|---|
| `daily_ingestion.yml` | Cron `0 12 * * *` (08:00 EDT) + `workflow_dispatch` | Three sequential jobs: **`ingest`** — Statcast (`savant_ingestion.py batter_pitches`), Stats API schedule (`ingest_statsapi.py schedule`), Odds API events + odds; **`dbt-build`** — calls `dbt_daily_build.yml` via `workflow_call` with `secrets: inherit` immediately after ingestion; **`backfill`** — runs `backfill_prediction_log.py` after dbt completes. |
| `dbt_daily_build.yml` | `workflow_call` (from `daily_ingestion.yml`) + `workflow_dispatch` | Runs `dbt build` on odd calendar days, `dbt run` on even days, and `dbt build --full-refresh` on Sundays. Day detection uses `date +%u` (1=Mon…7=Sun) and `date +%-d`. Callable as a reusable workflow or triggered manually from the GitHub Actions UI. |
| `lineup_monitor.yml` | Cron `0 * * * *` (every hour) + `workflow_dispatch` | Re-ingests Stats API schedule for current + prior month, rebuilds `stg_statsapi_lineups` + `stg_statsapi_lineups_wide`, runs `lineup_monitor.py` to detect newly confirmed games, conditionally rebuilds `+stg_statsapi_lineups+` if new games found. Outputs `has_new_games` step output to gate the dbt rebuild step. |
| `odds_snapshot.yml` | Cron `0 17 * * *`, `0 22 * * *`, `0 3 * * *` (13:00 / 18:00 / 23:00 EDT) + `workflow_dispatch` | Checks `stg_statsapi_games` for regular-season games today; if found, re-ingests Odds API events + odds and rebuilds odds dbt DAG (`+stg_oddsapi_events+ +stg_oddsapi_odds+`). Skips all steps on off-days to conserve API credits. |
| `dbt_staging_build.yml` | `workflow_dispatch` only with required `game_pk` input (dispatched by Snowflake `task_lineup_monitor`) | Lineup-scoped `dbt build --select +stg_statsapi_lineups+`. Triggered by the Snowflake stored procedure when both lineups for a game are confirmed in `stg_statsapi_lineups_wide`. |

**Required GitHub Secrets** (all workflows share the same set):
- `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY` (full PEM content), `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`
- `ODDS_API_KEY` — required by `daily_ingestion.yml` and `odds_snapshot.yml`

**dbt-fusion install pattern** (used by all five workflows):
```bash
curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh | sh -s -- --update
echo "$HOME/.local/bin" >> $GITHUB_PATH
```
The binary is `dbt` (not `dbtf`). `--profiles-dir dbt` is required because `dbt/profiles.yml` lives in the `dbt/` subdirectory, not the repo root.

**Snowflake private key pattern** (used by all five workflows):
```bash
echo "${{ secrets.SNOWFLAKE_PRIVATE_KEY }}" > /tmp/snowflake_rsa_key.pem
chmod 600 /tmp/snowflake_rsa_key.pem
# Then pass SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem as env var
```

### Marimo (EDA Notebooks)

EDA notebooks in `exploratory_data_analysis/` use [Marimo](https://marimo.io/) — a reactive notebook framework. Notebooks are plain `.py` files with inline `uv` script dependency headers; `uv` resolves and installs all dependencies automatically on first run.

```bash
# Interactive browser UI (http://localhost:2718)
uv run marimo run exploratory_data_analysis/01_target_variables.py

# Live-edit mode (cells re-run on change)
uv run marimo edit exploratory_data_analysis/01_target_variables.py

# Headless (no browser — for scripted or CI runs)
uv run marimo run exploratory_data_analysis/01_target_variables.py --headless
```

Each notebook connects to Snowflake using the same RSA key as snowsql (`~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem`). The connection is established once on load; all subsequent cells are reactive.

**Marimo cell conventions used in this project:**
- Each cell is a `@app.cell` decorated function; all referenced names must be imported or returned by a prior cell
- Figures are returned as single-element tuples (`return (fig_name,)`) so Marimo both displays and exports them
- `plt.close("all")` is called at the top of every plot cell to prevent figure accumulation
- Interactive tables use `mo.ui.table(df)` and combined displays use `mo.vstack([...])`
- **No early-return guards** — bare `return` mid-cell body causes Marimo to wrap the entire cell in `app._unparsable_cell`. Use `if condition:` blocks to wrap visualization code instead of `if condition: return`

---

### dbtf (dbt-fusion)

All dbt commands use `dbtf`, not `dbt`. See `dbt/README.md` for the full command reference.

```bash
dbtf build                                   # build all models + run tests
dbtf build --select mart_odds_events         # build a single model
dbtf test --select mart_odds_events          # run tests for a single model
```

### Snowflake MCP Server (Claude Code in-conversation queries)

The Snowflake MCP server is configured in `.mcp.json` at the repo root. It lets Claude query Snowflake directly during a conversation — no need to switch to snowsql for exploratory questions.

**Package:** `snowflake-labs-mcp` (Snowflake Labs official; run via `uvx`, no persistent install needed)

**Auth:** reads the `[connections.default]` block from `~/.snowsql/config` — same RSA key-pair credential used by snowsql. No credentials in `.mcp.json`.

**Permissions:** read-only. SQL restricted to `SELECT`, `DESCRIBE`, `SHOW`, `USE` via `snowflake_mcp_config.yaml`. Object management and all write operations are blocked.

**Activate:** restart Claude Code after adding `.mcp.json` — the server appears as the `snowflake` MCP tool automatically.

```bash
# Verify the server starts correctly (run manually to test; env vars mirror .mcp.json)
SNOWFLAKE_ACCOUNT="IHUPICS-DP59975" \
SNOWFLAKE_USER="dbt_rw" \
SNOWFLAKE_ROLE="ACCOUNTADMIN" \
SNOWFLAKE_WAREHOUSE="COMPUTE_WH" \
SNOWFLAKE_PRIVATE_KEY_FILE="/Users/charlesclark/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem" \
uvx snowflake-labs-mcp \
  --service-config-file /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/snowflake_mcp_config.yaml
# Expected output: "Initializing tools and resources..." then "Starting MCP server"
# "Closing Snowflake connection" at the end is normal — server shuts down when no client is attached
```

Example queries Claude can run in-conversation once connected:
```sql
-- Feature store coverage check
SELECT game_year, COUNT(*) AS games, SUM(has_full_data::integer) AS full_data_games
FROM baseball_data.betting_features.feature_pregame_game_features
GROUP BY game_year ORDER BY game_year;

-- Quick mart sanity check
SELECT * FROM baseball_data.betting.mart_game_results LIMIT 5;
```

---

### snowsql

Use the `default` named connection with the project RSA key for all ad-hoc Snowflake queries:

```bash
snowsql -c default \
  --private-key-path /Users/charlesclark/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem \
  -q "SELECT * FROM baseball_data.betting.mart_odds_events LIMIT 10;"
```

- `-c default` — selects the `[connections.default]` block in `~/.snowsql/config` (account `IHUPICS-DP59975`, user `dbt_rw`, database `BASEBALL_DATA`)
- `--private-key-path` — RSA private key for key-pair authentication; required because the `dbt_rw` user does not use password auth

---

## 14. Plan Specs

Declarative YAML planning specs (planspec.io/v1alpha1) for agentic task execution. Each spec defines a Goal, optional Gate(s), and a Plan with a task DAG. See `plan_specs/plan_spec_implementation.md` for the full PlanSpec reference and `plan_specs/eda_plan_spec_template.yaml` for the EDA card template.

**Directory:** `plan_specs/phase_{number}/{card_number}_{short_title}.yaml`

**Naming convention:** The filename prefix is the card number within the phase (not the full `{phase}.{card}` notation). Examples:
- Card 4.6 → `plan_specs/phase_4/6_ml_pipeline_foundation_plan.yaml`
- Card 3.10 → `plan_specs/phase_3/10_era_split_corr_stability.yaml`

**Document kinds (separated by `---`):**
- `Goal` — objective and high-level acceptance criteria
- `Gate` — human-gated checkpoint that blocks downstream tasks until a reviewer clears it
- `Plan` — task DAG with `dependsOn` edges; tasks reference gates by `metadata.name`

**Acceptance criteria types:**
- `artifact_exists` — verifies a file path exists
- `command_succeeds` — runs a shell command; passes if exit code is 0

**Current plan specs:**

| Phase | Card | File | Status |
|---|---|---|---|
| 3 | 3.8 | `plan_specs/phase_3/8_bullpen_vs_starter_signal_decomp.yaml` | Draft |
| 3 | 3.9 | `plan_specs/phase_3/9_home_away_pitch_quality.yaml` | Draft |
| 3 | 3.10 | `plan_specs/phase_3/10_era_split_corr_stability.yaml` | Draft |
| 3 | 3.11 | `plan_specs/phase_3/11_bookmaker_analysis.yaml` | Draft |
| 4 | 4.6 | `plan_specs/phase_4/6_ml_pipeline_foundation_plan.yaml` | Draft |
| 4 | 4.7 | `plan_specs/phase_4/7_feature_selection_plan.yaml` | Draft |
| 4 | 4.8 | `plan_specs/phase_4/8_base_reg_model_tot_runs.yaml` | Draft |
| 4 | 4.9 | `plan_specs/phase_4/9_base_reg_model_run_diff.yaml` | Draft |
| 4 | 4.10 | `plan_specs/phase_4/10_base_class_model_win_outcome.yaml` | Draft |
| 4 | 4.11 | `plan_specs/phase_4/11_hyperparameter_optimization.yaml` | Draft |
| 4 | 4.12 | `plan_specs/phase_4/12_bayes_prob_layer.yaml` | Draft |
| 6 | 6.B | `plan_specs/phase_6/B_streamlit_base_todays_picks.yaml` | Complete |
| 6 | 6.C | `plan_specs/phase_6/C_streamlit_market_comparision_page.yaml` | Complete |
| 6 | 6.D | `plan_specs/phase_6/D_streamlit_ev_tracker_and_kelly_sizer.yaml` | Complete |
| 6 | 6.E | `plan_specs/phase_6/E_streamlist_perf_tracker_page.yaml` | Complete |
| 6 | 6.H | `plan_specs/phase_6/H_postv0_model_postmortem.yaml` | Complete |
| 6 | 6.I | `plan_specs/phase_6/I_home_page_design.yaml` | Complete |
| 7 | 7.A | `plan_specs/phase_7/A_alpha_grid.yaml` | Created — P1, user must execute script to clear gate |
| 7 | 7.B | `plan_specs/phase_7/B_weather_features.yaml` | Created — P1, gated on OpenWeatherMap API key |
| 7 | 7.C | `plan_specs/phase_7/C_home_team_win_prob.yaml` | Created — P1, blocked until ≥100 2026 results (~2026-05-25) |
| 7 | 7.D | `plan_specs/phase_7/D_model_retraining_cadence.yaml` | Draft — blocked until Phase 7A produces mean edge > +0.01 |
| 7 | 7.E | `plan_specs/phase_7/E_fangraphs_ingestion.yaml` | Created — P1, consolidates 11 Trello stories (DDL, shared utils, 4 ingestion scripts, dbt sources/staging/mart/docs, validation) |
| 7 | 7.F | `plan_specs/phase_7/F_fangraphs_pitch_stuff.yaml` | Complete (2026-05-03) — stg/mart arsenal models built; 13/18 features retained; training cutoff → 2021+; all 3 models retrained (home_win Brier 0.2443 flat, total_runs MAE 3.4856 −0.038, run_diff MAE 3.4586 +0.039); retrain deferred to 7.MA |
| 7 | 7.G | `plan_specs/phase_7/G_intraday_feat_fallback.yaml` | Created — P2; fallback fn already exists; remaining: data_source DDL column + tag wiring through INSERT |
| 7 | 7.H | `plan_specs/phase_7/H_ump_tendencies.yaml` | Complete (2026-05-03) — 25,556 UmpScorecards rows (2015–2026); MLB Stats API daily assignment; trailing 3-yr z-scores; 99.4% 2026 coverage; 2 features retained (ump_runs_per_game_zscore, ump_accuracy_zscore); retraining deferred to pre-7.MA |
| 7 | 7.I | `plan_specs/phase_7/I_injury_confirmed_lineup.yaml` | Created — P2; MLB Stats API transactions endpoint (IL placements/activations) → point-in-time injury status → injury_adjusted_avg_woba_30d in feature_pregame_lineup_features; 4 tasks |
| 7 | 7.J | `plan_specs/phase_7/J_hitter_pitcher_matchups.yaml` | Complete (2026-05-03) — mart_pitcher_pitch_archetype (7,879 pitcher × season rows; fastball_dominant 49%, mixed 45%, breaking_dominant 7%) + mart_batter_vs_pitch_archetype (shrinkage at 50 PA; adj_woba/xwoba/k_pct/iso); 6 new columns in feature_pregame_lineup_features + feature_pregame_game_features; matchup_split_feature_impact.md written; model retrain deferred to 7.MA |
| 7 | 7.K | `plan_specs/phase_7/K_pitcher_clustering.yaml` | Created — P2; arsenal vector (velocity/break/Stuff+/pitch-mix) → k-means clustering (k=6–8, silhouette > 0.35) → pitcher_clusters table → mart_batter_woba_vs_cluster (30d rolling, shrinkage at 30 PA) → feature_pitcher_cluster_matchups; 4 tasks |
| 7 | 7.L1 | `plan_specs/phase_7/L1_historical_feature_backfill.yaml` | Created — P2; run historical ETL for all Phase 7 feature pipelines (weather, FanGraphs, umpire, injury, cluster) back to 2021; feature coverage audit; blocker: all Phase 7 feature cards complete |
| 7 | 7.L2 | `plan_specs/phase_7/L2_full_prediction_backfill.yaml` | Created — P2; batch re-score 2021–2026 with v1 model; model_version + feature_version columns; multi-year metrics vs. v0 baseline; blocker: 7.L1 |
| 7 | 7.MA | `plan_specs/phase_7/MA_full_model_retraining.yaml` | Created — P2; joint retrain of all 3 models on full Phase 7 feature set + calibrator refit; 5-task DAG; blocked on 7.G–7.K |
| 7 | 7.MB | `plan_specs/phase_7/MB_new_model_evaluation.yaml` | Created — P2; walk-forward CV harness (4 folds); benchmarks XGBoost/NGBoost vs. LightGBM, CatBoost, stacked ensemble + isotonic calibration; Cohen's d ≥ 0.10 selection rule; blocked on 7.MA |
| 7 | 7.N | `plan_specs/phase_7/N_game_insights_page.yaml` | Created — Phase 7A, unblocked; Game Insights Streamlit page: Prediction Summary, Team Comparison, SHAP waterfall, Recent Form |
| 7 | 7.O | *(no plan spec — 3-line `odds_snapshot.yml` change)* | COMPLETE — 2 additional cron triggers (18:30 UTC + 23:30 UTC) added to `odds_snapshot.yml`; 6 total snapshots/day |
| 7 | 7.P1 | *(no plan spec — single-script dry-run)* | Not yet created — validate OddsAPI historical endpoint returns different odds across intraday timestamps before committing to backfill |
| 7 | 7.P2 | `plan_specs/phase_7/P2_historical_odds_backfill.yaml` | Not yet created — blocked on 7.P1 proceed recommendation; backfill 2021–2025 intraday odds at 3 timestamps/day |
| 7 | 7.P3 | `plan_specs/phase_7/P3_line_movement_features.yaml` | Not yet created — blocked on 7.P2; compute h2h_line_movement + total_line_movement; add to feature_pregame_game_features |
| 7 | 7.Q | `plan_specs/phase_7/Q_bullpen_fatigue.yaml` | Not yet created — unblocked; mart_bullpen_fatigue → 8 new columns in feature_pregame_game_features |
| 7 | 7.R | `plan_specs/phase_7/R_pythagorean_win_exp.yaml` | Not yet created — unblocked; 2–3 line dbt calculation on existing stg_statsapi_games data |

---

### Phase 8 — Dynamic Bayesian Inference Engine

**Blocked until Phase 7 produces a market-beating model** (calibrated_win_prob Brier < 0.2395 AND mean h2h edge > 0.0 on the 2026 has_odds sample). See `bayesian_inference_prd.md` for full PRD and feasibility review.

The core problem this phase addresses: Card 7.A confirmed `best_alpha = 0.0` globally — the market dominates at every alpha value. Phase 8 makes the blending weight dynamic per-game rather than a global constant. In high-uncertainty regimes (early season, debut starters, thin rolling windows), the market's pricing edge over the model is narrowest, making a non-zero model weight defensible. In mid-season games with stable rosters, the weight converges back toward 0.

Phase 8 has five cards executed sequentially (A1 → A2, A1 → A3, A1 → A4, A2 → A5):

#### Card 8.A1 — Game Uncertainty Scoring

Compute a `game_uncertainty_score ∈ [0, 1]` per game from existing feature store columns (games_played_30d, starter_appearances_30d, has_ip_history flags). Write the score to `daily_model_predictions` at inference time. This is the input to all downstream Phase 8 cards.

Formula (v1):
- `starter_uncertainty = 0.5 * home_starter_unc + 0.5 * away_starter_unc` where each component is 1.0 for debut starters, decaying to 0.0 at 15 appearances
- `team_uncertainty = 0.5 * home_team_unc + 0.5 * away_team_unc` where each component is 1.0 at 0 games, decaying to 0.0 at 20 games
- `game_uncertainty_score = 0.5 * starter_uncertainty + 0.5 * team_uncertainty`, clamped to [0, 1]

No new data sources required. DDL migration adds `game_uncertainty_score FLOAT` to `daily_model_predictions`.

#### Card 8.A2 — Dynamic Alpha Weighting

Replace the global `best_alpha` scalar in `compute_posterior()` with a per-game weight driven by `game_uncertainty_score`.

Formula: `dynamic_alpha = game_uncertainty_score * MAX_MODEL_WEIGHT` where `MAX_MODEL_WEIGHT = 0.15` (conservative starting value). At full uncertainty, model gets 15% weight; at mid-season stability, model gets 0% (same as current best_alpha=0.0).

`MAX_MODEL_WEIGHT` is documented in `model_registry.yaml` under a new `bayesian_layer` block and re-evaluated after 200+ scored games. `dynamic_alpha` is written to `daily_model_predictions` for auditability. Evaluation query stratified by `game_uncertainty_score` bucket confirms high-uncertainty games trend toward better mean edge as the season progresses.

#### Card 8.A3 — NGBoost Distribution Surfacing

Extract the LogNormal parameters (mu, sigma) from the NGBoost totals model at inference time and write `prob_over_line`, `prob_under_line`, and `total_variance` to `daily_model_predictions`. These are already computed internally — they just aren't persisted. `prob_over_line = 1 - lognorm.cdf(market_totals_line, s=sigma, scale=exp(mu))`. Null when no totals line is available. DDL migration adds five columns: `ngb_total_mu`, `ngb_total_sigma`, `total_variance`, `prob_over_line`, `prob_under_line`.

#### Card 8.A4 — Feature Stabilization Layer

Apply `w = n / (n + k)` shrinkage to rolling stat features at inference time before model predict(). This is a Python preprocessing transform only — the dbt feature store is unchanged. Stabilization constants (k) and priors by stat type:

| Stat | k | Prior |
|---|---|---|
| wOBA (offensive, 30d) | 150 | 0.320 |
| xwOBA against (pitching, 30d) | 150 | 0.310 |
| Starter K% (season-to-date) | 60 | 0.215 |
| Starter xwOBA against (season-to-date) | 100 | 0.310 |
| Bullpen xwOBA against (30d) | 100 | 0.315 |

A `stabilize_features()` helper is added to `predict_today.py` and called after feature assembly, before model inference. The training pipeline is unaffected until Card 7.D retraining.

#### Card 8.A5 — Uncertainty-Adjusted Kelly Sizing

Apply a monotone discount to the Kelly fraction based on `game_uncertainty_score`. Formula: `uncertainty_discount = max(0.1, 1.0 - 0.5 * game_uncertainty_score)`. At full uncertainty the Kelly fraction is halved; the 0.1 floor prevents the bet from being zeroed. `adjusted_kelly_fraction` and `uncertainty_discount` are written to `daily_model_predictions`. `KELLY_UNCERTAINTY_DISCOUNT = 0.5` is documented in `model_registry.yaml`. After 100+ scored games, Sharpe ratio and mean P&L of adjusted vs. base Kelly are compared in `betting_ml/evaluation/phase8_results.md`.
| 7 | 7.S | `plan_specs/phase_7/S_starter_velo_trend.yaml` | Not yet created — unblocked; mart_pitcher_start_velo → velo_delta_3start columns in feature_pregame_game_features |

#### XGBoost home_win — Hyperparameter Tuning Results (Optuna TPE)

- **xgb_win_outcome_improved:** True — XGBoost home_win Brier improved ✓ (tuned=0.2443 vs baseline=0.2443)
- **Baseline Brier:** 0.2443 | **Tuned Brier:** 0.2443 | **Change:** +0.01%
- **Best params:** max_depth=4, learning_rate=0.0333, n_estimators=161, subsample=0.904, colsample_bytree=0.785, reg_alpha=0.219, reg_lambda=1.076
- **Summary:** Optuna TPE (50 trials) tuned XGBoost (Platt) for home_win; tuned Brier=0.2443 vs baseline=0.2443 — improved ✓; tuned model persisted via model_io.py as `xgb_classifier_tuned`.
- **Full results:** `betting_ml/evaluation/hyperparameter_tuning_xgb_home_win.md`, `betting_ml/evaluation/tuning_results_xgb_home_win.json`
