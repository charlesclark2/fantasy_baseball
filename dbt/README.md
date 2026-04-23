# Baseball Betting and Fantasy Analytics

A dbt project for analyzing MLB Statcast pitch-level data to predict game outcomes and support fantasy baseball decision-making.

## Project Goals

**Game Outcome Prediction**
Transform raw Statcast pitch data into clean, analysis-ready mart models that capture the full context of every pitch — pitch characteristics, game situation, batter/pitcher matchups, batted ball quality, and fielding alignment. The long-term goal is to use these features to build models that predict future game outcomes for betting analysis.

**Fantasy Baseball Projections**
Extend the pitch-level foundation into player-level projections and matchup analysis. Future enhancements will focus on batter and pitcher performance metrics, rest and usage patterns, and platoon splits to support fantasy lineup decisions and waiver wire analysis.

## Data Sources

- **`baseball_data.savant`** — MLB Statcast pitch-level data (`batter_pitches`, `ref_players`). One row per pitch per plate appearance per game. Ingested via `scripts/savant_ingestion.py` (Baseball Savant CSV endpoint, chunked by day). Run `uv run savant_ingestion.py batter_pitches` daily to keep current; pass `--start-date` / `--end-date` for backfills or reprocessing.
- **`baseball_data.statsapi`** — MLB Stats API (`monthly_schedule` as variant JSON, `venues_raw`). Game schedules, confirmed lineups, and ballpark metadata.
- **`baseball_data.oddsapi`** — The Odds API betting market data. Two raw tables: `mlb_events_raw` (one row per events pull; full response array in `raw_json`) and `mlb_odds_raw` (one row per event per market/region pull; nested bookmaker/market/outcome structure in `raw_json`). Both tables carry `x_requests_used` and `x_requests_remaining` columns for API credit monitoring. Ingested via `scripts/odds_api_ingestion.py`.
- **Seeds** — `ref_teams.csv`: static reference mapping 30 franchises to IDs, abbreviations, leagues, and divisions.

## Project Structure

```
models/
  staging/                       # Clean, rename, cast raw source data; establish surrogate keys
    stg_batter_pitches            -- Flattens Statcast pitch-level columns; adds pitch_sk surrogate key
    stg_statsapi_games            -- Flattens JSON schedule to one row per game
    stg_statsapi_lineups          -- Unpivots confirmed lineup arrays by batting order slot
    stg_statsapi_lineups_wide     -- Wide pivot: one row per team per game
    stg_statsapi_venues           -- Ballpark dimensions, elevation, timezone
    stg_statsapi_probable_pitchers -- Probable starters per game × side; null when rotation not yet announced

  mart/
    -- Pitch-grain models (incremental, merge on pitch_sk)
    -- One row per pitch; join any combination freely on pitch_sk.
    mart_pitch_game_context       -- Score state, count/base state, win/run expectancy
    mart_pitch_pitcher_profile    -- Pitcher identity, handedness, age, rest/usage, times through order
    mart_pitch_hitter_profile     -- Batter identity, handedness, age, prior PAs in game
    mart_pitch_characteristics    -- Velocity, movement, spin, release mechanics, zone location
    mart_pitch_play_event         -- Pitch outcome and plate appearance result
    mart_pitch_hit_characteristics -- Batted ball physics and contact quality (in-play pitches only)
    mart_pitch_fielding           -- Defensive alignment, shift flags, fielder IDs at time of pitch

    -- Game-level models
    mart_game_results             -- Final score, winner, extra innings; aggregated from pitch level
    mart_park_run_factors         -- Prior-season and 3-year rolling run factors per venue; join on venue_id + game_year

    -- Player rolling stats (one row per player × game; 7/14/30-day + season-to-date windows)
    mart_pitcher_rolling_stats    -- K%, BB%, whiff rate, barrel rate allowed, fastball velo
    mart_batter_rolling_stats     -- AVG, wOBA, xwOBA, discipline metrics

    -- Team rolling stats (one row per team × game; 7/14/30-day + season-to-date windows)
    mart_team_rolling_offense     -- Runs scored, wOBA, xwOBA, K%, BB%, slugging, hard-hit %
    mart_team_rolling_pitching    -- Runs allowed, wOBA against, xwOBA against, K%, BB%
    mart_team_vs_pitcher_hand     -- Team offense split by opposing starter handedness (L/R)
    mart_home_away_splits         -- Team offense + pitching split by home/away context (rolling)
    mart_team_season_record       -- Cumulative W/L/win% through each game date

    -- Pitcher usage models
    mart_starting_pitcher_game_log -- IP, outs, K, BB, ERA per start
    mart_bullpen_workload         -- Reliever innings, inherited runners, days rest
    mart_bullpen_effectiveness    -- Bullpen quality: K%, BB%, xwOBA against, whiff rate over 14/30-day rolling windows
    mart_team_schedule_context    -- Schedule fatigue: days rest, games_last_7d/14d, home/away streak length, timezone travel signal

    -- Platoon split models (one row per player × pitcher/batter hand × season)
    mart_batter_vs_handedness_splits  -- Batter performance vs. LHP/RHP by season
    mart_pitcher_vs_handedness_splits -- Pitcher effectiveness vs. LHB/RHB by season

    -- Historical context models
    mart_head_to_head_team_history -- Season and all-time H2H record for every franchise pair

    -- Odds API models (one row per event; one row per event × bookmaker × market × outcome)
    mart_odds_events                -- One row per event_id (latest snapshot); event dimension
    mart_odds_outcomes              -- Full history of bookmaker odds; supports line movement analysis

    -- Bridge models
    mart_game_odds_bridge           -- One row per game_pk; links mart_game_results to mart_odds_events

  feature/                         # ML pre-game feature vectors; materializes into baseball_data.betting_features
    feature_pregame_lineup_features  -- One row per game × side; aggregated batter rolling stats + prior-season platoon splits across all 9 lineup slots
    feature_pregame_starter_features -- One row per game × pitcher; starting pitcher rolling stats, days rest, platoon splits
    feature_pregame_team_features    -- One row per game × team; rolling offense, pitching, bullpen workload/effectiveness, season win%, schedule context (days rest, streak, travel)
    feature_pregame_park_features    -- One row per game; park dimensions, elevation, surface, roof type, prior-season run factors
    feature_pregame_game_features    -- One row per game (master assembly); joins all four upstream feature tables into a single wide ML input row
```

## Key Concepts

- **Grain**: Pitch-level mart models are at pitch grain — one row per pitch. Aggregate models are documented with their grain in the header comment of each file.
- **Join key**: `pitch_sk` — an MD5-based surrogate key on `(game_pk, at_bat_number, batter_id, pitch_number, pitcher_id, inning_half)`. All pitch-grain mart models join freely on this key.
- **Rolling windows**: Aggregate models use Snowflake `RANGE BETWEEN INTERVAL 'N days' PRECEDING AND CURRENT ROW` for 7/14/30-day windows and `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` (partitioned by `game_year`) for season-to-date.
- **Regular season filter**: All rolling stat and split models filter to `game_type = 'R'` to exclude Spring Training and Playoffs from historical normalization.
- **Derived flags**: Boolean and categorical columns (e.g. `is_barrel`, `count_leverage`, `is_infield_shift`) are computed in the mart layer to avoid repeating logic downstream.
- **Bat tracking**: Columns like `bat_speed_mph`, `swing_length_ft`, and `attack_angle_degrees` are only available from the 2023 season onward.
- **Feature layer**: Models in `feature/` materialize into `baseball_data.betting_features` (separate from `baseball_data.betting` where mart models live). Every join in the feature layer enforces a strict no-leakage rule — rolling stats use `< game_date`, platoon splits and park factors use `game_year - 1`, and season record uses `game_date - 1`. See `data_quality/leakage_audit.md` for the full code review checklist and spot-check results.

## Running the Project

This project uses **dbt-fusion** (`dbtf`), not the standard `dbt` CLI. Use `dbtf` for all commands.

```bash
# Install dependencies
dbtf deps

# Build all models and run tests
dbtf build

# Build a single model and its tests
dbtf build --select mart_team_vs_pitcher_hand

# Run tests only
dbtf test
```

## Data Quality

All dbt tests are schema tests defined in `models/mart/schema.yml` and `models/staging/schema.yml`. Tests use `error` severity by default; `warn` severity is reserved for acknowledged source-data limitations that cannot be resolved at the model layer.

**Current status:** All `error`-severity tests pass. Two intentional `warn`-severity tests remain:
- `not_null_mart_pitch_fielding_if_fielding_alignment` — 70,778 pitches (0.96%) lack alignment tracking in the Statcast source (sensor gap, not a model bug); highest concentration in 2015–2016
- `not_null_mart_pitch_fielding_of_fielding_alignment` — Same 70,778 rows; both alignment columns are always null together

The nine derived boolean alignment flags (`is_infield_shift`, etc.) are all protected with `coalesce(..., false)` and are never null.

**Issue tracking:**
- Open issues: `data_quality/open_data_quality_issues.md`
- Resolved issues: `data_quality/resolved_data_quality_issues_april_2026.md`

**Resolution workflow:**
1. Identify the failing test and its severity
2. Run a diagnostic query via snowsql to characterize failing rows
3. Determine root cause (source data gap, model logic bug, or test design flaw)
4. Apply fix and confirm build passes
5. Move entry from open to resolved file; update `project_context.md`

## Querying Snowflake Directly

Use the `default` snowsql connection with the project RSA key for all ad-hoc queries:

```bash
snowsql -c default \
  --private-key-path /Users/charlesclark/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem \
  -q "SELECT * FROM baseball_data.betting.mart_odds_events LIMIT 10;"
```

The `-c default` flag selects the named connection defined in `~/.snowsql/config` (account `IHUPICS-DP59975`, user `dbt_rw`, database `BASEBALL_DATA`). The `--private-key-path` flag supplies the RSA private key used for key-pair authentication.
