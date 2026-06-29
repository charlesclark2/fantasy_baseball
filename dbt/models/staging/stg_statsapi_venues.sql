-- =============================================================================
-- stg_statsapi_venues.sql  (E11.1-W6 lakehouse decommission)
-- Grain: one row per venue_id (latest ingest).
-- Source: baseball_data.statsapi.venues_raw — one VARIANT (json_field) row per
--         ingest, top-level {"venues":[{...}]} with a single element. xrefIds is
--         pivoted to columns via conditional aggregation.
--
-- DuckDB branch (E11.1-W6): flattens the RAW JSON parquet (lakehouse_raw/venues_raw/),
-- exported by scripts/export_w6_raw_to_s3.py. The Snowflake (else) branch is a thin
-- view over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with source as (

    select
        venue_id,
        ingest_date::date                                   as ingest_date,
        json_extract(json_field, '$.venues[0]')             as venue
    from read_parquet('{{ lakehouse_raw_loc("venues_raw") }}**/*.parquet', union_by_name=true)
    where json_field is not null

),

xrefs_flattened as (

    select
        s.venue_id,
        json_extract_string(x.xref, '$.xrefType')           as xref_type,
        json_extract_string(x.xref, '$.xrefId')             as xref_id
    from source s,
         unnest(from_json(json_extract(s.venue, '$.xrefIds'), '["JSON"]')) as x(xref)

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
    json_extract_string(s.venue, '$.name')                          as venue_name,
    json_extract_string(s.venue, '$.season')::integer               as season,
    json_extract_string(s.venue, '$.active')::boolean               as is_active,
    s.ingest_date,

    -- Location
    json_extract_string(s.venue, '$.location.address1')             as address,
    json_extract_string(s.venue, '$.location.city')                 as city,
    json_extract_string(s.venue, '$.location.state')                as state,
    json_extract_string(s.venue, '$.location.stateAbbrev')          as state_abbrev,
    json_extract_string(s.venue, '$.location.postalCode')           as postal_code,
    json_extract_string(s.venue, '$.location.country')              as country,
    json_extract_string(s.venue, '$.location.defaultCoordinates.latitude')::double  as latitude,
    json_extract_string(s.venue, '$.location.defaultCoordinates.longitude')::double as longitude,
    json_extract_string(s.venue, '$.location.elevation')::integer   as elevation_ft,
    json_extract_string(s.venue, '$.location.azimuthAngle')::double  as azimuth_angle,
    json_extract_string(s.venue, '$.location.phone')                as phone,

    -- Timezone
    json_extract_string(s.venue, '$.timeZone.id')                   as timezone_id,
    json_extract_string(s.venue, '$.timeZone.tz')                   as timezone_abbrev,
    json_extract_string(s.venue, '$.timeZone.offset')::integer      as timezone_utc_offset,
    json_extract_string(s.venue, '$.timeZone.offsetAtGameTime')::integer as timezone_utc_offset_at_game_time,

    -- Field dimensions and specs
    json_extract_string(s.venue, '$.fieldInfo.capacity')::integer   as capacity,
    json_extract_string(s.venue, '$.fieldInfo.turfType')            as turf_type,
    json_extract_string(s.venue, '$.fieldInfo.roofType')            as roof_type,
    json_extract_string(s.venue, '$.fieldInfo.leftLine')::integer   as left_line_ft,
    json_extract_string(s.venue, '$.fieldInfo.left')::integer       as left_ft,
    json_extract_string(s.venue, '$.fieldInfo.leftCenter')::integer as left_center_ft,
    json_extract_string(s.venue, '$.fieldInfo.center')::integer     as center_ft,
    json_extract_string(s.venue, '$.fieldInfo.rightCenter')::integer as right_center_ft,
    json_extract_string(s.venue, '$.fieldInfo.rightLine')::integer  as right_line_ft,

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

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.stg_statsapi_venues

{% endif %}
