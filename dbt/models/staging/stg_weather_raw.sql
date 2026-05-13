{{
    config(
        materialized='table'
    )
}}

select
    game_pk::integer            as game_pk,
    venue_id::integer           as venue_id,
    game_datetime_utc::timestamp_ntz as game_datetime_utc,
    fetch_offset_hours::float   as fetch_offset_hours,
    temp_f::float               as temp_f,
    wind_speed_mph::float       as wind_speed_mph,
    wind_direction_deg::integer as wind_direction_deg,
    humidity_pct::integer       as humidity_pct,
    condition_text::varchar     as condition_text,
    api_source::varchar         as api_source,
    loaded_at::timestamp_ntz    as loaded_at

from {{ source('statsapi', 'weather_raw') }}

-- Dedup to latest row per game × venue. Once T.2 adds weather_observation_type
-- and hours_to_first_pitch, expand the partition to include those columns.
qualify row_number() over (
    partition by game_pk, venue_id
    order by loaded_at desc
) = 1
