-- stg_ncaaf_games — flatten the raw CFBD /games Delta table (NCAAF-P0.2).
--
-- The raw tier lands each CFBD record as a `raw_json` VARCHAR (schema-stable across 12
-- seasons); this staging layer flattens it with DuckDB JSON functions (the MLB W3pre
-- VARIANT→staging pattern). Timestamps are cast at the USE-SITE (::timestamp on the ISO
-- string — the INC-23 discipline: raw stays VARCHAR, the reader casts).
-- ⭐ sport-tagged (the multi-sport serving/entitlement decision — baked in from day one).
with raw as (
    select raw_json
    from {{ ncaaf_delta('games') }}
)
select
    'ncaaf'                                                as sport,
    json_extract_string(raw_json, '$.id')::bigint         as game_id,
    json_extract_string(raw_json, '$.season')::int        as season,
    json_extract_string(raw_json, '$.week')::int          as week,
    json_extract_string(raw_json, '$.seasonType')         as season_type,
    json_extract_string(raw_json, '$.startDate')::timestamp as start_date,
    (json_extract_string(raw_json, '$.completed') = 'true')     as completed,
    (json_extract_string(raw_json, '$.neutralSite') = 'true')   as neutral_site,
    (json_extract_string(raw_json, '$.conferenceGame') = 'true') as conference_game,
    json_extract_string(raw_json, '$.homeId')::bigint     as home_team_id,
    json_extract_string(raw_json, '$.homeTeam')           as home_team,
    json_extract_string(raw_json, '$.homeClassification') as home_classification,
    json_extract_string(raw_json, '$.homeConference')     as home_conference,
    json_extract_string(raw_json, '$.homePoints')::int    as home_points,
    json_extract_string(raw_json, '$.awayId')::bigint     as away_team_id,
    json_extract_string(raw_json, '$.awayTeam')           as away_team,
    json_extract_string(raw_json, '$.awayClassification') as away_classification,
    json_extract_string(raw_json, '$.awayConference')     as away_conference,
    json_extract_string(raw_json, '$.awayPoints')::int    as away_points,
    -- FBS-only modelling universe (ncaaf_data_inventory.md §9 gap 8): both sides 'fbs'.
    -- ⚠️ coalesce → FALSE: CFBD leaves classification NULL on a few hundred games (mostly
    -- non-FBS opponents). An UNKNOWN division is not FBS, and a NULL flag would propagate a
    -- three-valued filter into every downstream `where is_fbs_matchup` (P1.1).
    coalesce(json_extract_string(raw_json, '$.homeClassification') = 'fbs'
        and json_extract_string(raw_json, '$.awayClassification') = 'fbs', false) as is_fbs_matchup
from raw
where json_extract_string(raw_json, '$.id') is not null
