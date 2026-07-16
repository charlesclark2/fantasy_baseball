-- stg_ncaaf_cfbd_draft_picks — flatten CFBD /draft/picks (NCAAF-P0.3).
--
-- The COLLEGE side of the NFL-feeder draft-slot key (ncaaf_data_inventory.md §4.2):
-- (year, overall) ⇄ nflverse draft_picks (season, pick). `collegeAthleteId` is the bridge
-- back into the CFBD college universe (roster / production). The xref itself is built by the
-- Python DuckDB-over-Delta builder (feeder/xref.py) — this view is the dbt-DAG entry point
-- for downstream (P1A) consumers of the raw draft table. Sport-tagged from day one.
with raw as (
    select raw_json
    from {{ ncaaf_delta('cfbd_draft_picks') }}
)
select
    'ncaaf'                                                    as sport,
    json_extract_string(raw_json, '$.year')::int              as draft_year,
    json_extract_string(raw_json, '$.overall')::int           as overall_pick,
    json_extract_string(raw_json, '$.round')::int             as draft_round,
    json_extract_string(raw_json, '$.pick')::int              as pick_in_round,
    json_extract_string(raw_json, '$.collegeAthleteId')::bigint as college_athlete_id,
    json_extract_string(raw_json, '$.nflAthleteId')           as nfl_athlete_id,
    json_extract_string(raw_json, '$.name')                   as player_name,
    json_extract_string(raw_json, '$.position')              as position,
    json_extract_string(raw_json, '$.collegeTeam')           as college_team,
    json_extract_string(raw_json, '$.collegeConference')     as college_conference,
    json_extract_string(raw_json, '$.nflTeam')               as nfl_team,
    try_cast(json_extract_string(raw_json, '$.preDraftGrade') as double)  as pre_draft_grade,
    try_cast(json_extract_string(raw_json, '$.preDraftRanking') as int)   as pre_draft_ranking,
    try_cast(json_extract_string(raw_json, '$.preDraftPositionRanking') as int) as pre_draft_position_ranking
from raw
where json_extract_string(raw_json, '$.overall') is not null
-- one row per draft slot (guards a rare supplemental/duplicate pick)
qualify row_number() over (
    partition by json_extract_string(raw_json, '$.year')::int,
                 json_extract_string(raw_json, '$.overall')::int
    order by (json_extract_string(raw_json, '$.collegeAthleteId') is null),
             json_extract_string(raw_json, '$.name')
) = 1
