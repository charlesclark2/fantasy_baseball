-- =============================================================================
-- stg_statsapi_probable_pitchers.sql   (E11.1-W7b lakehouse decommission)
-- Grain: one row per game_pk per side (home / away)
-- Purpose: Extract probablePitcher from the Stats API monthly schedule JSON.
--          Populated 1–3 days before game time once the rotation is announced.
--          probable_pitcher_id is null when the field is absent (rotation not
--          yet set or game too far in the future). No rows are dropped.
--          Join to stg_statsapi_games on game_pk for full game context.
--
-- ⚠️ SERVING-COUPLED (W7b serving-mart backlog): read by the request-path
-- last-resort (picks.py get_game_detail) direct-from-S3 AND by the pregame
-- feature build. The DuckDB/Snowflake outputs MUST be value-identical
-- (parity-gated) before the Snowflake (else) branch view is cut over.
--
-- DuckDB branch (E11.1-W7b): flattens the RAW JSON parquet
-- (lakehouse_raw/monthly_schedule/) — the SAME blob the W3pre stg_statsapi_games
-- and W6 stg_statsapi_lineups flatten, already exported by
-- scripts/export_odds_raw_to_s3.py. The Snowflake (else) branch is a thin view
-- over the lakehouse_ext external table.
--
-- ⚠️ Freshness: monthly_schedule has a known native-vs-S3 divergence band-aided
-- by the 30-min intraday re-export; this duckdb branch just flattens whatever
-- raw parquet is current (same as stg_statsapi_games), so no special handling.
--
-- ⚠️ OOM/parity note: like stg_statsapi_games, the month-blobs are large
-- (~1.4 MB each, ~750k game-rows pre-dedup). We collapse to ONE row per game_pk
-- (latest ingestion_ts) BEFORE deriving the two sides, so only the ~26k
-- latest-snapshot games inflate. The probable pitcher for a game never reverts
-- across re-fetches, so the latest snapshot == the per-(game,side) latest — the
-- final per-(game_pk, side) qualify is a belt-and-suspenders no-op after the
-- game-grain dedup (value-identical to the Snowflake per-(game,side) dedup).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w7b_lakehouse']) }}

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

-- Collapse blob multiplicity to one (latest-ingestion) snapshot per game_pk BEFORE
-- the two-side derivation (the OOM guard). Order key matches the per-(game,side)
-- dedup below (ingestion_ts desc nulls last).
deduped as (

    select ingestion_ts, game
    from games_flattened
    qualify row_number() over (
        partition by json_extract_string(game, '$.gamePk')::integer
        order by ingestion_ts desc nulls last
    ) = 1

),

home_side as (

    select
        json_extract_string(game, '$.gamePk')::integer                     as game_pk,
        json_extract_string(game, '$.officialDate')::date                  as game_date,
        'home'                                                             as side,
        json_extract_string(game, '$.teams.home.probablePitcher.id')::integer       as probable_pitcher_id,
        json_extract_string(game, '$.teams.home.probablePitcher.fullName')          as probable_pitcher_name,
        ingestion_ts
    from deduped

),

away_side as (

    select
        json_extract_string(game, '$.gamePk')::integer                     as game_pk,
        json_extract_string(game, '$.officialDate')::date                  as game_date,
        'away'                                                             as side,
        json_extract_string(game, '$.teams.away.probablePitcher.id')::integer       as probable_pitcher_id,
        json_extract_string(game, '$.teams.away.probablePitcher.fullName')          as probable_pitcher_name,
        ingestion_ts
    from deduped

),

all_sides as (

    select * from home_side
    union all
    select * from away_side

)

select
    game_pk,
    game_date,
    side,
    probable_pitcher_id,
    probable_pitcher_name,
    ingestion_ts::timestamp                                                as ingestion_ts
from all_sides
qualify row_number() over (
    partition by game_pk, side
    order by ingestion_ts desc nulls last
) = 1

{% else %}

{{
    config(
        materialized = 'table'
    )
}}

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
        ingestion_ts
    from games_flattened

),

away_side as (

    select
        game:gamePk::integer                                        as game_pk,
        game:officialDate::date                                     as game_date,
        'away'                                                      as side,
        game:teams:away:probablePitcher:id::integer                 as probable_pitcher_id,
        game:teams:away:probablePitcher:fullName::varchar           as probable_pitcher_name,
        ingestion_ts
    from games_flattened

),

all_sides as (

    select * from home_side
    union all
    select * from away_side

)

select *
from all_sides
qualify row_number() over (
    partition by game_pk, side
    order by ingestion_ts desc nulls last
) = 1

{% endif %}
