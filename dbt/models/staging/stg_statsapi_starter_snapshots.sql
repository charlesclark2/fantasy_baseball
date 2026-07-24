-- =============================================================================
-- stg_statsapi_starter_snapshots.sql
-- Grain: one row per (game_pk, side, ingestion_ts) — every ingestion snapshot,
--        not just the latest.
-- Purpose: Feed SCD-2 change detection in feature_pregame_starter_status.
--          Unlike stg_statsapi_probable_pitchers, this model retains all
--          ingestion snapshots so that probable starter changes (scratches) can
--          be tracked temporally.
--
-- Pre-Epic-T rows (ingestion_ts IS NULL in source) are assigned the sentinel
-- value 1970-01-01 00:00:00 so they appear as the "first known state" and are
-- not dropped during SCD-2 interval computation.
--
-- Dedup note: the same game can appear in two monthly_schedule rows at the same
-- ingestion_ts (e.g., May and June monthly API fetches run simultaneously).
-- QUALIFY keeps one row per (game_pk, side, ingestion_ts), preferring non-null
-- probable_pitcher_id; when both non-null, picks the lower ID deterministically.
--
-- Coverage: full history from monthly_schedule inception.
--
-- E11.1-W8a (upstream feature-layer migration): DuckDB branch flattens the RAW
-- JSON parquet (lakehouse_raw/monthly_schedule/) — the SAME blob the W3pre
-- stg_statsapi_games / W6 stg_statsapi_lineups / W7b stg_statsapi_probable_pitchers
-- flatten. UNLIKE probable_pitchers this retains EVERY (game_pk, side, ingestion_ts)
-- snapshot (no latest-only game-grain dedup) — the snapshot history is the whole
-- point — so the month-blob explosion is NOT collapsed early (the run_w1_lakehouse
-- _build_w8a sets memory_limit + threads, same OOM guard as stg_statsapi_games).
-- The Snowflake (else) branch is a thin view over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w8a_lakehouse']) }}

with src as (

    select json_field, ingestion_ts
    from read_parquet('{{ lakehouse_raw_loc("monthly_schedule") }}**/*.parquet', union_by_name=true)
    where json_field is not null

),

dates_flattened as (

    select
        ingestion_ts,
        unnest(from_json(json_extract(json_field, '$.dates'), '["JSON"]')) as date_obj
    from src

),

games_flattened as (

    select
        ingestion_ts,
        unnest(from_json(json_extract(date_obj, '$.games'), '["JSON"]')) as game
    from dates_flattened

),

home_side as (

    select
        json_extract_string(game, '$.gamePk')::integer                              as game_pk,
        json_extract_string(game, '$.officialDate')::date                           as game_date,
        'home'                                                                       as side,
        json_extract_string(game, '$.teams.home.probablePitcher.id')::integer       as probable_pitcher_id,
        json_extract_string(game, '$.teams.home.probablePitcher.fullName')          as probable_pitcher_name,
        coalesce(ingestion_ts::timestamp, '1970-01-01 00:00:00'::timestamp)         as ingestion_ts
    from games_flattened

),

away_side as (

    select
        json_extract_string(game, '$.gamePk')::integer                              as game_pk,
        json_extract_string(game, '$.officialDate')::date                           as game_date,
        'away'                                                                       as side,
        json_extract_string(game, '$.teams.away.probablePitcher.id')::integer       as probable_pitcher_id,
        json_extract_string(game, '$.teams.away.probablePitcher.fullName')          as probable_pitcher_name,
        coalesce(ingestion_ts::timestamp, '1970-01-01 00:00:00'::timestamp)         as ingestion_ts
    from games_flattened

),

combined as (

    select * from home_side
    union all
    select * from away_side

)

select *
from combined
qualify row_number() over (
    partition by game_pk, side, ingestion_ts
    order by probable_pitcher_id nulls last
) = 1

{% else %}

{{ config(materialized='view', tags=['w8a_lakehouse']) }}

-- E11.20 phase-2a STRAGGLER CUTOVER (2026-07-23, sibling of the stg_statsapi_probable_pitchers
-- fix): the native statsapi.monthly_schedule writer was retired when the schedule capture flipped
-- S3-native, which FROZE the old `source('statsapi','monthly_schedule')` read at 2026-07-20 17:00.
-- This model feeds the SCD-2 starter-change history (feature_pregame_starter_status), so a frozen
-- source silently drops every post-7/20 probable-starter announcement / scratch on the Snowflake
-- path. The header already described this as a thin view over the lakehouse_ext external table;
-- this makes the code match, mirroring the already-cut-over stg_statsapi_games. The duckdb branch
-- BUILT this ext preserving EVERY (game_pk, side, ingestion_ts) snapshot (the SCD-2 grain is the
-- whole point), so no re-dedup here — verified fresh 7/23 with the full snapshot history intact.
select
    game_pk,
    game_date,
    side,
    probable_pitcher_id,
    probable_pitcher_name,
    ingestion_ts
from baseball_data.lakehouse_ext.stg_statsapi_starter_snapshots

{% endif %}
