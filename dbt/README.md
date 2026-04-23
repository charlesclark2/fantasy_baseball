# Baseball Betting and Fantasy Analytics

A dbt project for analyzing MLB Statcast pitch-level data to predict game outcomes and support fantasy baseball decision-making.

## Project Goals

**Game Outcome Prediction**
Transform raw Statcast pitch data into clean, analysis-ready mart models that capture the full context of every pitch — pitch characteristics, game situation, batter/pitcher matchups, batted ball quality, and fielding alignment. The long-term goal is to use these features to build models that predict future game outcomes for betting analysis.

**Fantasy Baseball Projections**
Extend the pitch-level foundation into player-level projections and matchup analysis. Future enhancements will focus on batter and pitcher performance metrics, rest and usage patterns, and platoon splits to support fantasy lineup decisions and waiver wire analysis.

## Data Sources

- **`baseball_data.savant`** — MLB Statcast pitch-level data (`batter_pitches`, `ref_players`). One row per pitch per plate appearance per game.
- **`baseball_data.statsapi`** — MLB Stats API (`monthly_schedule` as variant JSON, `venues_raw`). Game schedules, confirmed lineups, and ballpark metadata.
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

    -- Platoon split models (one row per player × pitcher/batter hand × season)
    mart_batter_vs_handedness_splits  -- Batter performance vs. LHP/RHP by season
    mart_pitcher_vs_handedness_splits -- Pitcher effectiveness vs. LHB/RHB by season

    -- Historical context models
    mart_head_to_head_team_history -- Season and all-time H2H record for every franchise pair
```

## Key Concepts

- **Grain**: Pitch-level mart models are at pitch grain — one row per pitch. Aggregate models are documented with their grain in the header comment of each file.
- **Join key**: `pitch_sk` — an MD5-based surrogate key on `(game_pk, at_bat_number, batter_id, pitch_number, pitcher_id, inning_half)`. All pitch-grain mart models join freely on this key.
- **Rolling windows**: Aggregate models use Snowflake `RANGE BETWEEN INTERVAL 'N days' PRECEDING AND CURRENT ROW` for 7/14/30-day windows and `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` (partitioned by `game_year`) for season-to-date.
- **Regular season filter**: All rolling stat and split models filter to `game_type = 'R'` to exclude Spring Training and Playoffs from historical normalization.
- **Derived flags**: Boolean and categorical columns (e.g. `is_barrel`, `count_leverage`, `is_infield_shift`) are computed in the mart layer to avoid repeating logic downstream.
- **Bat tracking**: Columns like `bat_speed_mph`, `swing_length_ft`, and `attack_angle_degrees` are only available from the 2023 season onward.

## Running the Project

```bash
# Install dependencies
dbt deps

# Build all models and run tests
dbt build

# Build a single model and its tests
dbt build --select mart_team_vs_pitcher_hand

# Run tests only
dbt test
```
