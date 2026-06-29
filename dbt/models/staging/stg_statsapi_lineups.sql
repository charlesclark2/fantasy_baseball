-- =============================================================================
-- stg_statsapi_lineups.sql  (E11.1-W6 lakehouse decommission)
-- Grain: one row per (game_pk, home_away, batting_order) — a posted starter.
-- Source: baseball_data.statsapi.monthly_schedule — one VARIANT (json_field) row
--         per month-snapshot; dates[] → games[] → lineups.{home,away}Players[].
--         batting_order = 1-based position in the lineup array.
--
-- DuckDB branch (E11.1-W6): flattens the RAW JSON parquet
-- (lakehouse_raw/monthly_schedule/) — the SAME blob the W3pre stg_statsapi_games
-- flattens, already exported by scripts/export_odds_raw_to_s3.py. The Snowflake
-- (else) branch is a thin view over the lakehouse_ext external table.
--
-- ⚠️ OOM/parity note: like stg_statsapi_games, the month-blobs are large (~1.4 MB
-- each, ~750k game-rows pre-dedup). Exploding every snapshot's lineup before the
-- dedup would balloon to ~13M player-rows. We collapse to ONE row per game_pk
-- (latest ingestion_ts, matching the player-grain dedup's order key) BEFORE
-- exploding players, so only the ~26k latest-snapshot lineups inflate. A posted
-- lineup never loses a slot across re-fetches, so the latest snapshot's lineup ==
-- the per-slot latest — value-identical to the Snowflake per-(game,side,slot)
-- dedup (the final qualify is a belt-and-suspenders no-op after the game dedup).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

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
-- exploding the lineup arrays (the OOM guard). Order key matches the player-grain
-- dedup below (ingestion_ts desc nulls last).
deduped as (

    select ingestion_ts, game
    from games_flattened
    qualify row_number() over (
        partition by json_extract_string(game, '$.gamePk')::integer
        order by ingestion_ts desc nulls last
    ) = 1

),

home_players as (

    select
        json_extract_string(game, '$.gamePk')::integer      as game_pk,
        json_extract_string(game, '$.officialDate')::date   as official_date,
        'home'                                              as home_away,
        unnest(range(1, len(from_json(json_extract(game, '$.lineups.homePlayers'), '["JSON"]')) + 1)) as batting_order,
        unnest(from_json(json_extract(game, '$.lineups.homePlayers'), '["JSON"]')) as player,
        ingestion_ts
    from deduped
    where json_extract(game, '$.lineups.homePlayers') is not null

),

away_players as (

    select
        json_extract_string(game, '$.gamePk')::integer      as game_pk,
        json_extract_string(game, '$.officialDate')::date   as official_date,
        'away'                                              as home_away,
        unnest(range(1, len(from_json(json_extract(game, '$.lineups.awayPlayers'), '["JSON"]')) + 1)) as batting_order,
        unnest(from_json(json_extract(game, '$.lineups.awayPlayers'), '["JSON"]')) as player,
        ingestion_ts
    from deduped
    where json_extract(game, '$.lineups.awayPlayers') is not null

),

all_players as (
    select * from home_players
    union all
    select * from away_players
)

select
    game_pk,
    official_date,
    home_away,
    batting_order,

    json_extract_string(player, '$.id')::integer            as player_id,
    json_extract_string(player, '$.fullName')               as full_name,
    json_extract_string(player, '$.firstName')              as first_name,
    json_extract_string(player, '$.lastName')               as last_name,
    json_extract_string(player, '$.useName')                as use_name,

    json_extract_string(player, '$.primaryPosition.code')         as position_code,
    json_extract_string(player, '$.primaryPosition.name')         as position_name,
    json_extract_string(player, '$.primaryPosition.type')         as position_type,
    json_extract_string(player, '$.primaryPosition.abbreviation') as position_abbreviation,

    ingestion_ts::timestamp                                 as ingestion_ts

from all_players
qualify row_number() over (
    partition by game_pk, home_away, batting_order
    order by ingestion_ts desc nulls last
) = 1

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.stg_statsapi_lineups

{% endif %}
