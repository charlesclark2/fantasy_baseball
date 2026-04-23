# Baseball Betting & Fantasy: Project Context

## 1. Mission

Build a machine learning system capable of predicting the outcome and total runs scored in an MLB game given the pitching matchup, team matchup, and confirmed batting lineups. The system is grounded in Statcast pitch-level data and augmented with game schedule, lineup, and ballpark context from the MLB Stats API.

The project is currently in the **data mart development phase**. All modeling, feature engineering, and ML infrastructure comes after the mart layer is complete and validated.

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Data Warehouse | Snowflake |
| Transformation | dbt (SQL) |
| Ingestion | Python (`scripts/ingest_statsapi.py`) |
| ML (planned) | Python (`betting_ml/`) |
| EDA (planned) | Jupyter (`exploratory_data_analysis/`) |

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
- **Bat tracking (2023 onward only):** `bat_speed_mph`, `swing_length_ft`, `attack_angle_degrees`, `swing_path_tilt`, `attack_direction`, `hyper_speed`
- **Intercept offset (2024 onward only):** `intercept_offset_x_inches`, `intercept_offset_y_inches`

**`ref_players`** — Player reference table with BAM IDs, full names, and career date ranges.

### 4.2 MLB Stats API (`baseball_data.statsapi`)

**`monthly_schedule`** — One row per ingested month. The `json_field` VARIANT column contains full game metadata including confirmed pre-game batting lineups (`lineups.homePlayers`, `lineups.awayPlayers`). Ingested via `scripts/ingest_statsapi.py schedule`.

**`venues_raw`** — One row per ballpark. The `json_field` VARIANT column contains field dimensions, surface type, roof type, GPS coordinates, elevation, timezone, and cross-reference IDs. Ingested via `scripts/ingest_statsapi.py venues`.

### 4.3 Seeds

**`ref_teams`** — Static 33-row reference table (30 active franchises + legacy abbreviation entries). Contains `team_abbrev`, `team_id`, `team_name`, `league` (AL/NL), `division` (East/Central/West), and `is_active` flag.

---

## 5. Data Architecture

### 5.1 Staging Layer

Five models normalize and type-cast raw sources. All staging models are materialized as **tables** so downstream mart views have a stable, pre-computed base.

| Model | Source | Grain | Key Notes |
|---|---|---|---|
| `stg_batter_pitches` | savant.batter_pitches | Pitch | Generates `pitch_sk`; renames all columns to snake_case |
| `stg_statsapi_games` | statsapi.monthly_schedule (JSON flatten) | Game | Extracts game metadata, scores, teams, venue |
| `stg_statsapi_lineups` | monthly_schedule JSON | Player × game × side | Unpivots lineup JSON to one row per player per batting-order slot per side; deduped on month-boundary overlap |
| `stg_statsapi_lineups_wide` | stg_statsapi_lineups | Team × game × side | Wide pivot — one row per team per game with 9 batting-order slot columns |
| `stg_statsapi_venues` | statsapi.venues_raw (JSON flatten) | Venue | Extracts park dimensions, surface, roof, coordinates, elevation, timezone |

### 5.2 Mart Layer

Twenty mart models organized by grain. Pitch-grain models are materialized as **incremental tables** (merge on `pitch_sk`). Aggregate and rolling models are materialized as **tables**.

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

#### Game-Level Model (1 model)

| Model | Contents |
|---|---|
| `mart_game_results` | Final score, teams, league/division, winner, run differential, extra innings flag, interleague flag |

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

#### Specialty Models (6 models)

| Model | Grain | Contents |
|---|---|---|
| `mart_team_season_record` | Team × game | Cumulative W/L record and win % through each date |
| `mart_starting_pitcher_game_log` | Starter × game | IP, outs recorded, K, BB, earned runs, ERA, avg fastball velo per start |
| `mart_bullpen_workload` | Reliever × game | Innings pitched, inherited runners, days since last appearance |
| `mart_batter_vs_handedness_splits` | Batter × pitcher hand × season | AVG, wOBA, xwOBA, K%, BB%, hard-hit % vs. LHP and RHP |
| `mart_pitcher_vs_handedness_splits` | Pitcher × batter hand × season | K%, BB%, wOBA against, hard-hit % against vs. LHB and RHB |
| `mart_head_to_head_team_history` | Team pair × season | Season and all-time H2H record, run differential, and extra-innings rate for every franchise pair; abbreviations normalized to canonical form (e.g. OAK → ATH) for continuous franchise history |

---

## 6. Key Design Notes

**Bat tracking availability:** `bat_speed_mph`, `swing_length_ft`, `attack_angle_degrees`, and related fields are available in Statcast data **starting in 2023 only**. Models referencing these columns will produce nulls for pre-2023 rows. ML features built on bat tracking should be clearly scoped to the 2023+ era or treated as optional feature sets.

**Expected metrics availability:** `xba`, `xwoba`, `xslg` are only populated for in-play events (balls put in play). They are null for called strikes, swinging strikes, fouls, and walks.

**Intercept offset fields** (`intercept_offset_x_inches`, `intercept_offset_y_inches`) are available **starting in 2024 only**.

**Rolling window season isolation:** All rolling window CTEs partition by `game_year` to prevent November stats from bleeding into April of the following season.

**Regular season filter:** All rolling stats, splits, and workload models apply `game_type = 'R'` to exclude Spring Training, All-Star, Wild Card, Division Series, Championship Series, and World Series games. The prediction target is regular season games.

**Incremental merge on `pitch_sk`:** Pitch-grain mart models use `MERGE` so late-arriving Statcast corrections are applied rather than duplicated.

---

## 7. Known Data Quality Issues

### Resolved
| Issue | Resolution |
|---|---|
| 25 pitches with `balls = 4` | Accepted; `error_if >= 26` threshold set |
| 1 pitch with `strikes = 3` on a hit | Fixed in source |
| 413 pitches with `release_speed < 40 mph` (Eephus) | Bounds relaxed to 28–110 mph |
| 748 pitches with `effective_speed < 40 mph`, 1 at 194.6 mph | Bounds relaxed to 26–115 mph |
| `innings_pitched` float division bug in `mart_starting_pitcher_game_log` | Fixed: `floor(outs/3) + (mod(outs,3) * 0.1)` |
| Duplicate lineups from month-boundary API overlap | Fixed: `QUALIFY ROW_NUMBER() = 1` in `stg_statsapi_lineups` |
| Raw count columns (`strikeouts`, `walks`, `at_bats`, `total_bases`, `hard_hit_balls`, `barrels`, `batted_balls`) dropped from final SELECT in `mart_team_vs_pitcher_hand` | Added missing columns to `rolling` CTE SELECT list |

### Pending Investigation
- Null `is_barrel`, `is_hard_hit`, `is_sweet_spot` flags in `mart_pitch_hit_characteristics`
- Null fielding alignment flags in `mart_pitch_fielding`
- Duplicate `game_pk` values in `stg_statsapi_games` (potential month-boundary or doubleheader issue)
- Null `woba` and rolling `woba_*` rows in `mart_team_vs_pitcher_hand` when all PAs in a game have `woba_denom = 0` — `null between 0 and 2` fails `expression_is_true` (5 tests)
- Null `hard_hit_balls` and `barrels` in `mart_team_vs_pitcher_hand` for games with no balls in play — `sum()` of all-null inputs returns null, not 0 (2 tests)
- Null `woba` and `woba_against` in `mart_home_away_splits` — same root cause as `mart_team_vs_pitcher_hand` woba nulls (2 tests)
- `games_std >= games_7d` test fails at season boundaries in `mart_home_away_splits` — the 7-day window has no year partition and can span season boundaries while `games_std` resets; test design issue, not a data error (1 test)
- `hard_hit_pct` inconsistency in `mart_batter_vs_handedness_splits` (pitch-level vs. PA-level aggregation edge case)
- `release_extension_ft` bounds check pending investigation in `mart_pitch_characteristics`

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
| Lineup data (confirmed pre-game) | Complete (staging) |
| Ballpark context | Complete (staging) |
| Data quality tests | Mostly complete; 10 pending issues |
| ML feature store | Not started |
| Prediction models | Not started |
| Betting/sizing layer | Not started |

The main gap between current state and a deployable prediction model is the **feature assembly layer** — joining the mart tables into a single pre-game feature vector per game — and the **ML pipeline** itself.

---

## 9. Roadmap

### Phase 1 — Complete and Stabilize the Data Mart (Current Phase)

Estimated completion: before ML work begins.

**Goals:**
- Resolve all 5 pending data quality issues
- Confirm `stg_statsapi_games` deduplication strategy for doubleheaders
- Confirm `mart_pitch_hit_characteristics` null flag root cause and fix
- Confirm `mart_pitch_fielding` null flag root cause and fix
- Validate `mart_team_vs_pitcher_hand` raw count columns and wOBA null edge case
- Validate `mart_batter_vs_handedness_splits` hard-hit aggregation logic
- Add `venue_id` / park factor join to `mart_game_results` (venue context is staged but not yet joined)
- Confirm lineup data is reliably populated for historical games (coverage audit)
- Document data availability windows (Statcast coverage by year, lineup coverage by year)

**Deliverables:**
- All dbt tests passing at error thresholds
- Full coverage audit documented in `data_quality_issues.md`

---

### Phase 2 — Pre-Game Feature Assembly

The prediction task requires a single feature vector per game, assembled from information available **before first pitch**. This phase builds that assembly layer.

**New models to build:**

| Model | Grain | Description |
|---|---|---|
| `mart_pregame_lineup_features` | Game × side | For each team/side: join `stg_statsapi_lineups_wide` with `mart_batter_rolling_stats` (most recent game before this one) and `mart_batter_vs_handedness_splits` (season-to-date) to produce a lineup-level feature vector (9-slot batter stats + aggregated team batting metrics) |
| `mart_pregame_starter_features` | Game × starter | For each starting pitcher: join `mart_starting_pitcher_game_log` with `mart_pitcher_rolling_stats` (most recent game) and `mart_pitcher_vs_handedness_splits` to produce a pre-game pitcher feature vector |
| `mart_pregame_team_features` | Game × team | For each team: join `mart_team_rolling_offense`, `mart_team_rolling_pitching`, `mart_team_vs_pitcher_hand`, `mart_team_season_record`, and `mart_bullpen_workload` into a single team context row |
| `mart_pregame_park_features` | Game | Join `mart_game_results` with `stg_statsapi_venues` to attach park dimensions, elevation, surface, and roof type — known park factor drivers |
| `mart_pregame_game_features` | Game | Master assembly: join all four pre-game feature tables into a single wide row per game. This is the direct input to ML feature engineering. |

**Key design constraints:**
- All features must be computed from data available **as of game_date - 1 day** (no data leakage)
- Rolling windows should use the most recent N-game or N-day window ending the day before the game
- Lineup slot features should account for confirmed lineup order and opposing starter handedness
- Park features are static per venue (no rolling needed)

---

### Phase 3 — Exploratory Data Analysis

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

### Phase 4 — Baseline Prediction Models

Build initial models in `betting_ml/` using the assembled feature store from Phase 2.

**Targets:**
- **Total runs scored** (regression; enables over/under analysis)
- **Run differential** (regression; calibrated to win probability)
- **Binary win outcome** (classification; moneyline proxy)

**Baseline approach:**
1. XGBoost regression and classification baselines — strong performance on tabular data, handles missing values (pre-2023 bat tracking nulls), interpretable via SHAP
2. Train on regular season games with confirmed lineups (limit to `game_type = 'R'` where lineup data is populated)
3. Cross-validate by season (train on years N−k through N−1, evaluate on year N) to respect temporal ordering
4. Evaluate regression targets with MAE and RMSE; classification with log loss and Brier score
5. Calibrate probability outputs (Platt scaling or isotonic regression) before any EV calculations

**Feature groups to evaluate:**
- Team rolling offense (7/14/30-day wOBA, runs, K%, BB%)
- Team rolling pitching (7/14/30-day wOBA against, K%, BB%)
- Platoon adjustment (team offense vs. pitcher hand)
- Starter features (recent ERA, xwOBA against, K%, fastball velo trend)
- Lineup features (aggregated batter wOBA + handedness composition vs. starter)
- Park features (dimensions, elevation, surface)
- Season record (win% as proxy for overall team quality)

---

### Phase 5 — Model Refinement and Feature Expansion

Once baselines are established:

**Feature additions:**
- Weather data (temperature, wind speed/direction, humidity) — strong park-era interaction; requires external data source
- Umpire tendencies (ball/strike zone size) — significant but requires additional data
- Bullpen availability score: derive from `mart_bullpen_workload` (days rest + recent IP for top relievers)
- Travel schedule / home vs. away streaks
- Batter/pitcher head-to-head history (build from `stg_batter_pitches` with `GROUP BY batter_id, pitcher_id`)
- Player injury status (requires external data source)

**Model improvements:**
- Neural network approaches (TabNet, MLP) if tabular baselines plateau
- Ensemble / stacking of run total and win probability models
- Separate era models: pre-2023 (no bat tracking) and 2023+ (full bat tracking features)
- Position-aware lineup encoding (slot 1–9 weighted differently, or positional encoding)

**Validation improvements:**
- Walk-forward evaluation by week, not just season
- Calibration curves by run total bucket (high-scoring vs. pitcher-duel games)
- Separate evaluation for home vs. away, dome vs. outdoor, AL vs. NL

---

### Phase 6 — Betting Application Layer

Build the `betting_ml/` application layer that translates model outputs into actionable information.

**Components:**

| Component | Description |
|---|---|
| Pre-game prediction pipeline | Given tomorrow's confirmed lineups and starting pitchers, produce predicted run total, run differential, and win probability for each game |
| Market comparison | Compare model probability to implied probability from current market odds (requires odds data source) |
| Expected value calculator | `EV = (model_probability × payout) - (1 - model_probability)` |
| Kelly criterion sizer | `f* = (bp - q) / b` where `b` = decimal odds - 1, `p` = model win prob, `q` = 1 - p; apply fractional Kelly for risk management |
| Backtesting framework | Simulate historical betting decisions using model outputs vs. closing line odds to estimate long-run edge |
| Daily pipeline | Automated pre-game scoring: fetch that day's confirmed lineups via Stats API, run prediction, output edge rankings |

**Risk controls:**
- Never bet on games with missing lineup data (model degrades significantly)
- Minimum confidence threshold before flagging a game as actionable
- Track closing line value (CLV): if the model identified edge that the market later confirmed, the model is functioning correctly

---

### Phase 7 — Production Infrastructure

Operationalize the full stack:

- Scheduled dbt runs (daily) to refresh staging and mart tables with new Statcast data
- Scheduled ingestion of that day's lineup data via `ingest_statsapi.py`
- Automated model scoring pipeline that triggers once lineups are confirmed (typically 3–4 hours before first pitch)
- Output dashboard or notification system for actionable game flags
- Model performance monitoring: track prediction accuracy week-over-week, flag model drift

---

## 10. Predicted Timeline

| Phase | Milestone | Estimated State |
|---|---|---|
| Phase 1 | All dbt tests passing, data quality issues resolved | Near-term (days to weeks) |
| Phase 2 | Pre-game feature assembly mart models built and tested | Weeks |
| Phase 3 | EDA complete, target variable and feature candidates validated | Weeks |
| Phase 4 | Baseline XGBoost models trained, cross-validated, calibrated | Weeks to months |
| Phase 5 | Refined models with expanded feature set, era-aware approach | Months |
| Phase 6 | Betting application layer with EV calculation and backtesting | Months |
| Phase 7 | Automated daily pipeline, monitoring, dashboard | Months |

---

## 11. File Reference

| Path | Purpose |
|---|---|
| `dbt/dbt_project.yml` | dbt project configuration (profile, materializations) |
| `dbt/models/sources.yml` | Source table definitions (savant, statsapi) |
| `dbt/models/staging/schema.yml` | Staging model schemas and tests |
| `dbt/models/mart/schema.yml` | Mart model schemas and tests |
| `dbt/seeds/ref_teams.csv` | Static team reference (30 franchises + legacy abbreviations) |
| `dbt/README.md` | dbt layer documentation |
| `dbt/data_quality_issues.md` | Known issues, root cause analysis, and resolutions |
| `scripts/ingest_statsapi.py` | Python ingestion for Stats API schedule and venues |
| `betting_ml/` | Placeholder — ML model code lives here (Phase 4+) |
| `exploratory_data_analysis/` | Placeholder — EDA notebooks live here (Phase 3+) |
