# Baseball Betting and Fantasy Analytics

A dbt project for analyzing MLB Statcast pitch-level data to predict game outcomes and support fantasy baseball decision-making.

## Project Goals

**Game Outcome Prediction**
Transform raw Statcast pitch data into clean, analysis-ready mart models that capture the full context of every pitch — pitch characteristics, game situation, batter/pitcher matchups, batted ball quality, and fielding alignment. The long-term goal is to use these features to build models that predict future game outcomes for betting analysis.

**Fantasy Baseball Projections**
Extend the pitch-level foundation into player-level projections and matchup analysis. Future enhancements will focus on batter and pitcher performance metrics, rest and usage patterns, and platoon splits to support fantasy lineup decisions and waiver wire analysis.

## Data Source

All data originates from MLB Statcast via the `baseball_data.savant` schema. The pipeline ingests pitch-level data from `savant_batter_pitches` and player reference data from `ref_players`.

## Project Structure

```
models/
  staging/        # Clean and rename raw Statcast columns; establish surrogate keys
  mart/           # Pitch-level analytical models, each focused on a domain
    mart_pitch_game_context         -- Score state, count/base state, win/run expectancy
    mart_pitch_pitcher_profile      -- Pitcher identity, handedness, age, rest/usage
    mart_pitch_hitter_profile       -- Batter identity, handedness, age, matchup context
    mart_pitch_characteristics      -- Velocity, movement, spin, zone location
    mart_pitch_play_event           -- Pitch and plate appearance outcomes
    mart_pitch_hit_characteristics  -- Batted ball physics and contact quality (in-play only)
    mart_pitch_fielding             -- Defensive alignment and fielder identity
```

All mart models share a common `pitch_sk` surrogate key and can be joined freely at pitch grain.

## Running the Project

```bash
# Install dependencies
dbt deps

# Build all models
dbt build

# Run tests only
dbt test
```

## Key Concepts

- **Grain**: All mart models are at pitch grain — one row per pitch.
- **Join key**: `pitch_sk` — an MD5-based surrogate key on `(game_pk, at_bat_number, batter_id, pitch_number, pitcher_id, inning_half)`.
- **Derived flags**: Boolean and categorical columns (e.g. `is_barrel`, `count_leverage`, `pitcher_rest_bucket`) are computed in the mart layer to avoid repeating logic downstream.
- **Bat tracking**: Columns like `bat_speed_mph`, `swing_length_ft`, and `attack_angle_degrees` are only available from the 2023 season onward.
