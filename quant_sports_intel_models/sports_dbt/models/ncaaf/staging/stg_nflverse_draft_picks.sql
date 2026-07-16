-- stg_nflverse_draft_picks — flatten nflverse draft_picks (NCAAF-P0.3).
--
-- The NFL side of the draft-slot key (`pick` IS the overall pick — ncaaf_data_inventory.md
-- §4.2) PLUS the feeder's TARGET outcomes (car_av / w_av / games / … — already here, no extra
-- source, §4.3). ⚠️ the target_* columns are POST-draft: they are the P1A modelling TARGET,
-- NOT features — never fold them into a pregame/pre-draft feature matrix (market-blind /
-- leakage-safe discipline). `cfb_player_id` is the sports-reference SLUG that attaches combine
-- measurables nflverse-internally (it is NOT joinable to CFBD's numeric collegeAthleteId).
with raw as (
    select raw_json
    from {{ ncaaf_delta('nflverse_draft_picks') }}
)
select
    'ncaaf'                                                as sport,
    json_extract_string(raw_json, '$.season')::int        as draft_year,
    json_extract_string(raw_json, '$.pick')::int          as overall_pick,
    json_extract_string(raw_json, '$.round')::int         as draft_round,
    json_extract_string(raw_json, '$.gsis_id')            as gsis_id,
    json_extract_string(raw_json, '$.pfr_player_id')      as pfr_player_id,
    json_extract_string(raw_json, '$.cfb_player_id')      as cfb_player_id,
    json_extract_string(raw_json, '$.pfr_player_name')    as player_name,
    json_extract_string(raw_json, '$.position')           as position,
    json_extract_string(raw_json, '$.college')            as college,
    json_extract_string(raw_json, '$.team')               as nfl_team,
    -- TARGET outcomes (leakage-unsafe as features — prefixed target_)
    try_cast(json_extract_string(raw_json, '$.car_av') as double)          as target_car_av,
    try_cast(json_extract_string(raw_json, '$.w_av') as double)            as target_w_av,
    try_cast(json_extract_string(raw_json, '$.dr_av') as double)           as target_dr_av,
    try_cast(json_extract_string(raw_json, '$.games') as double)           as target_games,
    try_cast(json_extract_string(raw_json, '$.seasons_started') as double) as target_seasons_started,
    try_cast(json_extract_string(raw_json, '$.probowls') as double)        as target_probowls,
    try_cast(json_extract_string(raw_json, '$.allpro') as double)          as target_allpro,
    (json_extract_string(raw_json, '$.hof') in ('true','True','1'))        as target_hof
from raw
where json_extract_string(raw_json, '$.pick') is not null
qualify row_number() over (
    partition by json_extract_string(raw_json, '$.season')::int,
                 json_extract_string(raw_json, '$.pick')::int
    order by (json_extract_string(raw_json, '$.gsis_id') is null),
             json_extract_string(raw_json, '$.pfr_player_name')
) = 1
