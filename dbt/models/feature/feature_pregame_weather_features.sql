-- =============================================================================
-- feature_pregame_weather_features.sql
-- Grain: one row per game_pk
-- Purpose: Pre-game weather features for outdoor MLB parks.
--
-- Source: feature_pregame_weather_status (SCD-2). Re-pointed in Epic 15
-- story 15.5 — reads is_current = true rows, which represent the most
-- recent pregame forecast state for each game.
--
-- Dome parks have is_dome = TRUE and NULL wind_component_mph. Imputation
-- (league-average fill for dome parks) is handled in the Python preprocessing
-- layer, not here.
--
-- Coverage: Epic T.2 conversion date (2026-05-01) onward. Pre-T games have
-- no row in this table. wind_component_mph is pre-computed in the SCD-2
-- staging layer (stg_weather_raw_snapshots).
--
-- OBSERVATION TYPE: forecast_pregame only (enforced at the snapshot staging
-- layer). forecast_intraday and observed_at_first_pitch must NOT enter this
-- feature — run_env models were trained on forecast_pregame exclusively.
-- =============================================================================

{{ config(materialized='table') }}

select
    game_pk,
    venue_id,
    'forecast_pregame'      as weather_observation_type,
    temp_f,
    wind_speed_mph,
    wind_direction_deg,
    humidity_pct,
    wind_component_mph,
    is_dome
from {{ ref('feature_pregame_weather_status') }}
where is_current = true
