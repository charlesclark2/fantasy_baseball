-- stg_ncaaf_transfer_portal — flatten CFBD /player/portal (NCAAF-P0.4).
--
-- One row per portal ENTRY. `season` = the season the transfer window PRECEDES (a season=N
-- entry has transferDate in the N-1/N off-season, verified live: 2024 entries span Dec-2022 →
-- May-2024) → a team's season-N portal class is known PRE-SEASON. Coverage: the portal era,
-- CFBD data starts 2021 (2014-2020 have no rows) — the mart flags portal_data_covered.
--   origin      = the school the player LEFT (an OUT for that team)
--   destination = the school the player JOINED (an IN for that team); NULL = uncommitted /
--                 left CFB (attrition), still an OUT for the origin.
--   stars (2-5, ~89% present) / rating (247 composite 0-1, ~55% present) = incoming talent grade.
-- ⭐ Leakage-safe (pre-season). Sport-tagged. Materialized as a TABLE (the delta_scan-stacking
--   cure — see stg_ncaaf_returning_production).
{{ config(materialized='table') }}
with raw as (
    select season, raw_json
    from {{ ncaaf_delta('transfer_portal') }}
)
select
    'ncaaf'                                                   as sport,
    season                                                    as season,
    json_extract_string(raw_json, '$.firstName')             as first_name,
    json_extract_string(raw_json, '$.lastName')              as last_name,
    json_extract_string(raw_json, '$.position')              as position,
    json_extract_string(raw_json, '$.origin')                as origin,
    json_extract_string(raw_json, '$.destination')           as destination,
    try_cast(json_extract_string(raw_json, '$.transferDate') as timestamp) as transfer_date,
    try_cast(json_extract_string(raw_json, '$.stars')  as int)    as stars,
    try_cast(json_extract_string(raw_json, '$.rating') as double) as rating,
    json_extract_string(raw_json, '$.eligibility')           as eligibility,
    (json_extract_string(raw_json, '$.stars')::int >= 4)     as is_blue_chip
from raw
