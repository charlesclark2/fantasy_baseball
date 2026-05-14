{{
    config(
        materialized='table'
    )
}}

select
    game_pk::integer                    as game_pk,
    venue_id::integer                   as venue_id,
    game_datetime_utc::timestamp_ntz    as game_datetime_utc,
    fetch_offset_hours::float           as fetch_offset_hours,
    temp_f::float                       as temp_f,
    wind_speed_mph::float               as wind_speed_mph,
    wind_direction_deg::integer         as wind_direction_deg,
    humidity_pct::integer               as humidity_pct,
    condition_text::varchar             as condition_text,
    api_source::varchar                 as api_source,
    coalesce(
        weather_observation_type::varchar,
        'forecast_pregame'
    )                                   as weather_observation_type,
    hours_to_first_pitch::integer       as hours_to_first_pitch,
    loaded_at::timestamp_ntz            as loaded_at

from {{ source('statsapi', 'weather_raw') }}

-- Dedup to latest row per (game × venue × observation type × checkpoint).
-- forecast_pregame: one current row per game/venue.
-- observed_at_first_pitch: one row per game/venue (hours_to_first_pitch is NULL).
-- forecast_intraday: one row per game/venue per checkpoint (hours_to_first_pitch ∈ {1,3,6,24}).
qualify row_number() over (
    partition by game_pk, venue_id, weather_observation_type, hours_to_first_pitch
    order by loaded_at desc nulls last
) = 1
