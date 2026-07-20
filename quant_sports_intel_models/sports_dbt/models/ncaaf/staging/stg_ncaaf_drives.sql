-- stg_ncaaf_drives — flatten CFBD /drives (NCAAF-P1.1).
--
-- ONE row per drive. The drive is the natural unit for scoring-opportunity / field-position
-- efficiency (points-per-opportunity, drive-success rate), which the week rollups derive.
-- CFBD nests startTime/endTime/elapsed as {minutes, seconds} objects → flattened to seconds.
--
-- season comes from the Delta partition; week from the ingest's `_week` tag (partition fallback).
-- Materialized as a TABLE (the delta_scan-stacking cure — the N0.3 landmine).
{{ config(materialized='table') }}

with raw as (
    select season, week as partition_week, raw_json
    from {{ ncaaf_delta('drives') }}
)

select
    'ncaaf'                                                            as sport,
    season,
    coalesce(try_cast(json_extract_string(raw_json, '$._week') as integer),
             partition_week)                                           as week,
    json_extract_string(raw_json, '$.id')                              as drive_id,
    json_extract_string(raw_json, '$.gameId')::bigint                  as game_id,
    try_cast(json_extract_string(raw_json, '$.driveNumber') as integer) as drive_number,
    json_extract_string(raw_json, '$.offense')                         as offense_team,
    json_extract_string(raw_json, '$.offenseConference')               as offense_conference,
    json_extract_string(raw_json, '$.defense')                         as defense_team,
    json_extract_string(raw_json, '$.defenseConference')               as defense_conference,
    (json_extract_string(raw_json, '$.isHomeOffense') = 'true')        as is_home_offense,
    (json_extract_string(raw_json, '$.scoring') = 'true')              as is_scoring_drive,
    json_extract_string(raw_json, '$.driveResult')                     as drive_result,
    try_cast(json_extract_string(raw_json, '$.plays')  as integer)     as plays,
    try_cast(json_extract_string(raw_json, '$.yards')  as integer)     as yards,
    try_cast(json_extract_string(raw_json, '$.startPeriod') as integer) as start_period,
    try_cast(json_extract_string(raw_json, '$.endPeriod')   as integer) as end_period,
    try_cast(json_extract_string(raw_json, '$.startYardline')   as integer) as start_yardline,
    try_cast(json_extract_string(raw_json, '$.startYardsToGoal') as integer) as start_yards_to_goal,
    try_cast(json_extract_string(raw_json, '$.endYardline')     as integer) as end_yardline,
    try_cast(json_extract_string(raw_json, '$.endYardsToGoal')  as integer) as end_yards_to_goal,
    -- {minutes, seconds} objects → a single comparable scalar
    coalesce(try_cast(json_extract_string(raw_json, '$.elapsed.minutes') as integer), 0) * 60
        + coalesce(try_cast(json_extract_string(raw_json, '$.elapsed.seconds') as integer), 0)
                                                                       as elapsed_seconds,
    try_cast(json_extract_string(raw_json, '$.startOffenseScore') as integer) as start_offense_score,
    try_cast(json_extract_string(raw_json, '$.startDefenseScore') as integer) as start_defense_score,
    try_cast(json_extract_string(raw_json, '$.endOffenseScore')   as integer) as end_offense_score,
    try_cast(json_extract_string(raw_json, '$.endDefenseScore')   as integer) as end_defense_score
from raw
where json_extract_string(raw_json, '$.id') is not null
