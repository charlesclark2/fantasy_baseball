-- =============================================================================
-- stg_weather_raw_snapshots.sql
-- Grain: one row per (game_pk, loaded_at) for forecast_pregame observations.
-- Purpose: Feed SCD-2 change detection in feature_pregame_weather_status.
--          Retains ALL ingestion snapshots so weather changes (forecast updates)
--          can be tracked temporally.
--
-- Scope: forecast_pregame only. forecast_intraday and observed_at_first_pitch
--        are excluded here because the downstream feature model was trained
--        exclusively on forecast_pregame data — mixing types creates a
--        train/inference distribution mismatch.
--
-- Coverage: Epic T.2 conversion date (2026-05-01) onward. Pre-T weather
--           history is permanently unrecoverable.
--
-- wind_component_mph computed here (positive = blowing out toward CF,
-- negative = in toward home plate) so the SCD-2 table carries the final
-- feature value and does not require a downstream ref_venues join.
-- =============================================================================

{{ config(materialized='table') }}

with source as (

    select
        game_pk::integer                as game_pk,
        venue_id::integer               as venue_id,
        temp_f::float                   as temp_f,
        wind_speed_mph::float           as wind_speed_mph,
        wind_direction_deg::integer     as wind_direction_deg,
        humidity_pct::integer           as humidity_pct,
        condition_text::varchar         as condition_text,
        loaded_at::timestamp_ntz        as loaded_at
    from {{ source('statsapi', 'weather_raw') }}
    where weather_observation_type = 'forecast_pregame'

),

with_venue as (

    select
        s.*,
        case
            when rv.roof_type in ('open', 'convertible')
                and rv.park_facing_degrees is not null
                then round(
                    s.wind_speed_mph * cos(
                        (s.wind_direction_deg - rv.park_facing_degrees) * pi() / 180
                    ), 2)
            else null
        end                                                 as wind_component_mph,
        case when rv.roof_type = 'fixed' then true else false end as is_dome
    from source s
    left join {{ ref('ref_venues') }} rv using (venue_id)

)

select
    game_pk,
    venue_id,
    temp_f,
    wind_speed_mph,
    wind_direction_deg,
    humidity_pct,
    condition_text,
    wind_component_mph,
    is_dome,
    md5(
        coalesce(cast(temp_f as varchar), '')           || '|' ||
        coalesce(cast(wind_component_mph as varchar), '') || '|' ||
        coalesce(cast(humidity_pct as varchar), '')     || '|' ||
        coalesce(condition_text, '')
    )                                                   as record_hash,
    loaded_at
from with_venue
qualify row_number() over (
    partition by game_pk, loaded_at
    order by temp_f nulls last
) = 1
