-- =============================================================================
-- feature_pregame_weather_features.sql
-- Grain: one row per game_pk
-- Purpose: Pre-game weather features for outdoor MLB parks. Computes
--          wind_component_mph (positive = wind out toward CF, negative = in)
--          using the park's compass bearing from home plate to center field.
--
-- Dome parks (roof_type = 'fixed') have is_dome = TRUE and NULL
-- wind_component_mph. Imputation (league-average fill for dome parks) is
-- handled in the Python preprocessing layer, not here.
--
-- LEAKAGE NOTE: weather is fetched before first pitch and stored in
-- weather_raw. The fetch_offset_hours column captures how far before first
-- pitch the data was collected. QUALIFY keeps the fetch closest to first
-- pitch to maximize accuracy without using post-game data.
-- =============================================================================

{{ config(materialized='table') }}

with weather as (
    select
        w.game_pk,
        w.venue_id,
        w.temp_f,
        w.wind_speed_mph,
        w.wind_direction_deg,
        w.humidity_pct,

        -- Wind component: positive = blowing out toward CF (favors offense)
        --                 negative = blowing in toward home plate (suppresses offense)
        -- Formula: wind_speed × cos(wind_direction − park_facing_degrees)
        -- cos() in Snowflake takes radians; multiply degrees by π/180
        case
            when rv.roof_type in ('open', 'convertible')
                and rv.park_facing_degrees is not null
                then round(
                    w.wind_speed_mph * cos(
                        (w.wind_direction_deg - rv.park_facing_degrees) * pi() / 180
                    ), 2)
            else null
        end                                     as wind_component_mph,

        case when rv.roof_type = 'fixed' then true else false end as is_dome

    from {{ ref('stg_weather_raw') }} w
    left join {{ ref('ref_venues') }} rv using (venue_id)

    qualify row_number() over (
        partition by w.game_pk
        order by abs(w.fetch_offset_hours) asc  -- prefer fetch closest to first pitch
    ) = 1
)

select * from weather
