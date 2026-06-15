-- =============================================================================
-- feature_pregame_weather_features.sql
-- Grain: one row per game_pk
-- Purpose: Pre-game weather features for outdoor MLB parks.
--
-- TWO SOURCES, unioned by game_pk (Story 31.4 weather repair, 2026-06-15):
--
--   1. forecast_pregame  → the LIVE SERVE path. This is the only weather
--      available at inference time (a pregame forecast), so it defines serving.
--      Comes through the SCD-2 chain (stg_weather_raw_snapshots →
--      feature_pregame_weather_status, is_current = true). Exists 2026-05-01+.
--
--   2. observed_at_first_pitch → the HISTORICAL TRAINING backfill. The
--      forecast_pregame observation type did not exist before 2026-05-01, so
--      without this the feature was ~100% NULL across the entire training
--      window (2021–2025) and feature-selection correctly dropped it (Story
--      31.0 finding). The realized first-pitch observation is a faithful
--      stand-in for the pregame forecast — on the 406 2026 games that have
--      both, temp corr 0.97 (bias +0.3°F) and wind corr 0.73 (bias +0.6 mph),
--      near-unbiased. Training-on-observed / serving-on-forecast is therefore
--      an acceptable substitution for run-environment features. Observed is
--      used ONLY for games the live forecast path does not already cover (i.e.
--      all pre-2026 history + any 2026 game lacking a pregame forecast).
--
-- wind_component_mph (positive = blowing out toward CF, negative = in toward
-- home plate) is computed here for the observed rows the same way the SCD-2
-- staging layer computes it for the forecast rows, so both sources carry an
-- identical feature definition. Dome parks have is_dome = TRUE and NULL
-- wind_component_mph; dome imputation is handled in Python preprocessing.
-- =============================================================================

{{ config(materialized='table') }}

with forecast as (

    -- Live serving source: pregame forecast (Epic T.2 2026-05-01 onward).
    select
        game_pk,
        venue_id,
        temp_f,
        wind_speed_mph,
        wind_direction_deg,
        humidity_pct,
        wind_component_mph,
        is_dome
    from {{ ref('feature_pregame_weather_status') }}
    where is_current = true

),

observed_dedup as (

    -- Historical training backfill: realized first-pitch OBSERVED weather.
    -- One row per game_pk (latest ingestion).
    select
        game_pk::integer            as game_pk,
        venue_id::integer           as venue_id,
        temp_f::float               as temp_f,
        wind_speed_mph::float       as wind_speed_mph,
        wind_direction_deg::integer as wind_direction_deg,
        humidity_pct::integer       as humidity_pct
    from {{ source('statsapi', 'weather_raw') }}
    where weather_observation_type = 'observed_at_first_pitch'
    qualify row_number() over (
        partition by game_pk
        order by loaded_at desc nulls last
    ) = 1

),

observed as (

    select
        o.game_pk,
        o.venue_id,
        o.temp_f,
        o.wind_speed_mph,
        o.wind_direction_deg,
        o.humidity_pct,
        case
            when rv.roof_type in ('open', 'convertible')
                and rv.park_facing_degrees is not null
                then round(
                    o.wind_speed_mph * cos(
                        (o.wind_direction_deg - rv.park_facing_degrees) * pi() / 180
                    ), 2)
            else null
        end                                                       as wind_component_mph,
        case when rv.roof_type = 'fixed' then true else false end as is_dome
    from observed_dedup o
    left join {{ ref('ref_venues') }} rv using (venue_id)
    -- Backfill only games the live forecast path does not already cover.
    where o.game_pk not in (select game_pk from forecast)

)

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
from forecast

union all

select
    game_pk,
    venue_id,
    'observed_at_first_pitch' as weather_observation_type,
    temp_f,
    wind_speed_mph,
    wind_direction_deg,
    humidity_pct,
    wind_component_mph,
    is_dome
from observed
