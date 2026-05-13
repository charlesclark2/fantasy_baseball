{{
    config(
        materialized='table'
    )
}}

-- Each row in venues_raw has a "venues" array containing exactly one element.
-- LATERAL FLATTEN extracts it; xrefIds is then pivoted via conditional aggregation
-- so each cross-reference type becomes its own column.

with source as (
    select
        venue_id,
        ingest_date,
        json_field:venues[0] as venue
    from {{ source('statsapi', 'venues_raw') }}
),

xrefs_flattened as (
    select
        s.venue_id,
        x.value:xrefType::varchar   as xref_type,
        x.value:xrefId::varchar     as xref_id
    from source s,
    lateral flatten(input => s.venue:xrefIds) x
),

xrefs_pivoted as (
    select
        venue_id,
        max(case when xref_type = 'retrosheet'          then xref_id end) as xref_retrosheet_id,
        max(case when xref_type = 'weather_channel_loc' then xref_id end) as xref_weather_channel_loc_id,
        max(case when xref_type = 'ballpark_code'       then xref_id end) as xref_ballpark_code,
        max(case when xref_type = 'stubhub'             then xref_id end) as xref_stubhub_id,
        max(case when xref_type = 'weatherbug_station'  then xref_id end) as xref_weatherbug_station_id
    from xrefs_flattened
    group by venue_id
)

select
    -- Primary identifiers
    s.venue_id,
    s.venue:name::varchar                               as venue_name,
    s.venue:season::integer                             as season,
    s.venue:active::boolean                             as is_active,
    s.ingest_date,

    -- Location
    s.venue:location:address1::varchar                  as address,
    s.venue:location:city::varchar                      as city,
    s.venue:location:state::varchar                     as state,
    s.venue:location:stateAbbrev::varchar               as state_abbrev,
    s.venue:location:postalCode::varchar                as postal_code,
    s.venue:location:country::varchar                   as country,
    s.venue:location:defaultCoordinates:latitude::float as latitude,
    s.venue:location:defaultCoordinates:longitude::float as longitude,
    s.venue:location:elevation::integer                 as elevation_ft,
    s.venue:location:azimuthAngle::float                as azimuth_angle,
    s.venue:location:phone::varchar                     as phone,

    -- Timezone
    s.venue:timeZone:id::varchar                        as timezone_id,
    s.venue:timeZone:tz::varchar                        as timezone_abbrev,
    s.venue:timeZone:offset::integer                    as timezone_utc_offset,
    s.venue:timeZone:offsetAtGameTime::integer          as timezone_utc_offset_at_game_time,

    -- Field dimensions and specs
    s.venue:fieldInfo:capacity::integer                 as capacity,
    s.venue:fieldInfo:turfType::varchar                 as turf_type,
    s.venue:fieldInfo:roofType::varchar                 as roof_type,
    s.venue:fieldInfo:leftLine::integer                 as left_line_ft,
    s.venue:fieldInfo:left::integer                     as left_ft,
    s.venue:fieldInfo:leftCenter::integer               as left_center_ft,
    s.venue:fieldInfo:center::integer                   as center_ft,
    s.venue:fieldInfo:rightCenter::integer              as right_center_ft,
    s.venue:fieldInfo:rightLine::integer                as right_line_ft,

    -- Cross-reference IDs
    x.xref_retrosheet_id,
    x.xref_weather_channel_loc_id,
    x.xref_ballpark_code,
    x.xref_stubhub_id,
    x.xref_weatherbug_station_id

from source s
left join xrefs_pivoted x
    on s.venue_id = x.venue_id
qualify row_number() over (
    partition by s.venue_id
    order by s.ingest_date desc
) = 1
