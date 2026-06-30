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

{{ config(materialized='table') }}

with source as (

    select json_field, ingestion_ts
    from {{ source('statsapi', 'monthly_schedule') }}

),

dates_flattened as (

    select d.value as date_obj, ingestion_ts
    from source,
    lateral flatten(input => json_field:dates) d

),

games_flattened as (

    select g.value as game, ingestion_ts
    from dates_flattened,
    lateral flatten(input => date_obj:games) g

),

home_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'home'                                                      as side,
        game:teams:home:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:home:probablePitcher:fullName::varchar           as probable_pitcher_name,
        coalesce(ingestion_ts, '1970-01-01 00:00:00'::timestamp_ntz) as ingestion_ts
    from games_flattened

),

away_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'away'                                                      as side,
        game:teams:away:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:away:probablePitcher:fullName::varchar           as probable_pitcher_name,
        coalesce(ingestion_ts, '1970-01-01 00:00:00'::timestamp_ntz) as ingestion_ts
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

{% endif %}
