-- stg_ncaaf_roster — flatten CFBD /roster (NCAAF-P0.4).
--
-- One row per player on a team's season roster (CFBD athlete `id` is the stable player key).
-- The raw JSON has NO season field → `season` comes from the Delta partition column. Feeds the
-- year-over-year roster-CONTINUITY signal in the mart (a player on the same team in season N
-- AND N-1 = a "returning" player; a portal arrival is NOT continuity). Covers all divisions —
-- the mart's returning-production spine restricts to the FBS universe. Roster is a season
-- snapshot set pre-season ⇒ leakage-safe. Sport-tagged. Materialized as a TABLE (delta_scan cure).
{{ config(materialized='table') }}
with raw as (
    select season, raw_json
    from {{ ncaaf_delta('roster') }}
)
select
    'ncaaf'                                          as sport,
    season                                           as season,
    json_extract_string(raw_json, '$.id')            as player_id,
    json_extract_string(raw_json, '$.team')          as team,
    json_extract_string(raw_json, '$.position')      as position,
    try_cast(json_extract_string(raw_json, '$.year') as int) as class_year,
    json_extract_string(raw_json, '$.firstName')     as first_name,
    json_extract_string(raw_json, '$.lastName')      as last_name,
    -- ⭐ P1.2b bridge: the recruiting RECORD ids linked to this roster player. The CFBD
    -- /roster payload carries `recruitIds` (a JSON array of recruiting-record ids), and the
    -- ONLY key that actually joins is `roster.recruitIds` ↔ `recruiting_players.id` — NOT
    -- the recruiting `athleteId` the data inventory originally documented (that matches 7
    -- rows in 12 seasons; recruitIds→id matches 60,883). Empty for most rows (walk-ons,
    -- transfers, pre-2014 arrivals with no recruiting record). Stored as a VARCHAR[] so a
    -- downstream model can `unnest` it directly. NULL/empty stays empty — a player with no
    -- recruiting record is genuinely unlinked, not a match failure.
    coalesce(
        try_cast(json_extract(raw_json, '$.recruitIds') as varchar[]),
        cast([] as varchar[])
    )                                                as recruit_ids
from raw
where json_extract_string(raw_json, '$.id') is not null
  and json_extract_string(raw_json, '$.team') is not null
