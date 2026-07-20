-- stg_ncaaf_teams — flatten CFBD /teams/fbs (NCAAF-P1.1).
--
-- ONE row per (season, team_id): the FBS team registry as it stood in that season, carrying the
-- attributes that DRIFT (conference, division, classification — realignment) plus the stable
-- identity/venue block. This is the SOURCE for the SCD-2 `dim_team` + `dim_conference`.
--
-- ⚠️ The raw record has NO season field (a year-only pull) → `season` comes from the Delta
-- PARTITION column. That is exactly what makes realignment observable: the same team_id appears
-- once per season with the conference of record for that season.
--
-- Materialized as a TABLE (not the staging-default view): the delta_scan-stacking cure — DuckDB's
-- delta extension cannot serialize a DeltaScan inside a complex downstream plan (the N0.3
-- landmine), so every NCAAF staging model that a mart joins is physical.
{{ config(materialized='table') }}

with raw as (
    select season, raw_json
    from {{ ncaaf_delta('teams') }}
)

select
    'ncaaf'                                                       as sport,
    season                                                        as season,
    json_extract_string(raw_json, '$.id')::bigint                 as team_id,
    json_extract_string(raw_json, '$.school')                     as team,
    json_extract_string(raw_json, '$.mascot')                     as mascot,
    json_extract_string(raw_json, '$.abbreviation')               as abbreviation,
    -- ── the DRIFTING attributes (SCD-2 payload in dim_team) ──────────────────────────────
    json_extract_string(raw_json, '$.conference')                 as conference,
    json_extract_string(raw_json, '$.division')                   as conference_division,
    json_extract_string(raw_json, '$.classification')             as classification,
    -- ── venue / geography (stable-ish; carried for the environment feature block) ────────
    json_extract_string(raw_json, '$.location.name')              as venue_name,
    json_extract_string(raw_json, '$.location.city')              as venue_city,
    json_extract_string(raw_json, '$.location.state')             as venue_state,
    json_extract_string(raw_json, '$.location.timezone')          as venue_timezone,
    try_cast(json_extract_string(raw_json, '$.location.latitude')  as double) as venue_latitude,
    try_cast(json_extract_string(raw_json, '$.location.longitude') as double) as venue_longitude,
    try_cast(json_extract_string(raw_json, '$.location.elevation') as double) as venue_elevation_m,
    try_cast(json_extract_string(raw_json, '$.location.capacity')  as integer) as venue_capacity,
    (json_extract_string(raw_json, '$.location.dome')  = 'true')  as venue_is_dome,
    (json_extract_string(raw_json, '$.location.grass') = 'true')  as venue_is_grass
from raw
where json_extract_string(raw_json, '$.id') is not null
  and season is not null
