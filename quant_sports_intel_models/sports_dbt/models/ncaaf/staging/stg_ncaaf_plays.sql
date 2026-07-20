-- stg_ncaaf_plays — flatten CFBD /plays (NCAAF-P1.1).
--
-- ONE row per play (~2.2M rows over 2014–2025) — the raw material every derived efficiency
-- metric is built from: `ppa` is CFBD's own EPA-analog, and down/distance/yardsToGoal give the
-- success-rate + explosiveness definitions the rollups apply.
--
-- Success rate is defined HERE (once) on the standard convention so every consumer agrees:
--   1st down ≥ 50% of distance · 2nd down ≥ 70% · 3rd/4th down ≥ 100%.
-- Non-scrimmage plays (kickoffs, punts, PATs, timeouts, end-of-period markers) are FLAGGED
-- rather than dropped — `is_scrimmage_play` lets a consumer choose, and the play universe stays
-- complete for anything drive-oriented.
--
-- ⚠️ `wallclock` is kept as the raw ISO VARCHAR — the INC-23 discipline (raw stays VARCHAR, the
-- reader casts at the use-site). season from the Delta partition; week from the `_week` tag.
-- Materialized as a TABLE (the delta_scan-stacking cure — the N0.3 landmine).
{{ config(materialized='table') }}

with raw as (
    select season, week as partition_week, raw_json
    from {{ ncaaf_delta('plays') }}
),

flat as (
    select
        'ncaaf'                                                            as sport,
        season,
        coalesce(try_cast(json_extract_string(raw_json, '$._week') as integer),
                 partition_week)                                           as week,
        json_extract_string(raw_json, '$.id')                              as play_id,
        json_extract_string(raw_json, '$.gameId')::bigint                  as game_id,
        json_extract_string(raw_json, '$.driveId')                         as drive_id,
        try_cast(json_extract_string(raw_json, '$.driveNumber') as integer) as drive_number,
        try_cast(json_extract_string(raw_json, '$.playNumber')  as integer) as play_number,
        json_extract_string(raw_json, '$.offense')                         as offense_team,
        json_extract_string(raw_json, '$.offenseConference')               as offense_conference,
        json_extract_string(raw_json, '$.defense')                         as defense_team,
        json_extract_string(raw_json, '$.defenseConference')               as defense_conference,
        json_extract_string(raw_json, '$.home')                            as home_team,
        json_extract_string(raw_json, '$.away')                            as away_team,
        try_cast(json_extract_string(raw_json, '$.offenseScore') as integer) as offense_score,
        try_cast(json_extract_string(raw_json, '$.defenseScore') as integer) as defense_score,
        try_cast(json_extract_string(raw_json, '$.period')   as integer)   as period,
        coalesce(try_cast(json_extract_string(raw_json, '$.clock.minutes') as integer), 0) * 60
            + coalesce(try_cast(json_extract_string(raw_json, '$.clock.seconds') as integer), 0)
                                                                           as clock_seconds_remaining,
        try_cast(json_extract_string(raw_json, '$.down')     as integer)   as down,
        try_cast(json_extract_string(raw_json, '$.distance') as integer)   as distance,
        try_cast(json_extract_string(raw_json, '$.yardline') as integer)   as yardline,
        try_cast(json_extract_string(raw_json, '$.yardsToGoal') as integer) as yards_to_goal,
        try_cast(json_extract_string(raw_json, '$.yardsGained') as integer) as yards_gained,
        (json_extract_string(raw_json, '$.scoring') = 'true')              as is_scoring_play,
        json_extract_string(raw_json, '$.playType')                        as play_type,
        json_extract_string(raw_json, '$.playText')                        as play_text,
        try_cast(json_extract_string(raw_json, '$.ppa') as double)         as ppa,
        -- ISO string kept VARCHAR (INC-23): the reader casts ::timestamp at the use-site
        json_extract_string(raw_json, '$.wallclock')                       as wallclock
    from raw
    where json_extract_string(raw_json, '$.id') is not null
)

select
    *,
    -- a scrimmage snap (excludes kickoffs / punts / PATs / clock + administrative markers)
    (play_type is not null
     and play_type not ilike '%kickoff%'
     and play_type not ilike '%punt%'
     and play_type not ilike '%extra point%'
     and play_type not ilike '%timeout%'
     and play_type not ilike '%end of%'
     and play_type not ilike '%penalty%'
     and play_type not ilike '%uncategorized%')                            as is_scrimmage_play,
    (play_type ilike '%pass%' or play_type ilike '%sack%'
     or play_type ilike '%interception%')                                  as is_pass_play,
    (play_type ilike '%rush%')                                             as is_rush_play,
    -- passing downs = 2nd & ≥8 or 3rd/4th & ≥5 (the standard CFB convention); else standard down
    (down = 2 and distance >= 8) or (down in (3, 4) and distance >= 5)     as is_passing_down,
    -- ⭐ the ONE success-rate definition (50% / 70% / 100% of distance by down)
    case
        when down is null or distance is null or yards_gained is null then null
        when down = 1 then yards_gained >= 0.5 * distance
        when down = 2 then yards_gained >= 0.7 * distance
        when down in (3, 4) then yards_gained >= distance
    end                                                                    as is_successful_play
from flat
