-- =============================================================================
-- stg_statsapi_games.sql  (E11.1-W3pre lakehouse decommission)
-- Grain: one row per game_pk (latest ingestion; postponed-DH tiebreaker).
-- Source: baseball_data.statsapi.monthly_schedule — one VARIANT row per month.
-- Two-level flatten: dates[] → games[].
--
-- ⚠️ DOUBLE-DUTY / SERVING-COUPLED: feeds mart_game_odds_bridge (serving) AND many
-- other mart families. The DuckDB/Snowflake outputs MUST be value-identical
-- (parity-gated) before the Snowflake (else) branch view is cut over.
-- NOTE: the monthly_schedule WRITER (ingest_statsapi.py) is NOT flipped this session
-- (out of the W3pre writer scope), so raw freshness here relies on the recurring
-- Snowflake→S3 export step in run_w1_lakehouse / the export script until it flips.
--
-- DuckDB branch (E11.1-W3pre): flattens the RAW JSON parquet (lakehouse_raw/monthly_schedule/);
-- built to S3 by run_w1_lakehouse.py. The Snowflake (else) branch is a thin view
-- over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

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

-- E11.1-W3pre OOM fix: collapse to one row per game_pk BEFORE the wide field projection.
-- The full flatten is ~1,712 month-blobs (~1.4 MB each, 2.4 GB total) × ~435 games ≈ 750k
-- rows; running the 30+ json_extract_string projections across all of them (then the dedup
-- window) exhausted RAM even with disk spilling — the wide materialization doesn't spill.
-- Deduping on the narrow (ingestion_ts, game) rows first drops the projected set to ~26k
-- surviving games. The window partition/order is byte-identical to the original, so output
-- is unchanged (one row per game_pk, latest ingestion, postponed-DH tiebreaker).
deduped as (

    select ingestion_ts, game
    from games_flattened
    qualify row_number() over (
        partition by json_extract_string(game, '$.gamePk')::integer
        order by
            ingestion_ts desc nulls last,
            case when json_extract_string(game, '$.doubleHeader') in ('Y', 'S') then 0 else 1 end asc,
            json_extract_string(game, '$.gameNumber')::integer desc nulls last
    ) = 1

)

select
    -- Primary identifiers
    json_extract_string(game, '$.gamePk')::integer                  as game_pk,
    json_extract_string(game, '$.gameGuid')                         as game_guid,

    -- Game metadata
    json_extract_string(game, '$.gameType')                         as game_type,
    json_extract_string(game, '$.season')::integer                  as season,
    json_extract_string(game, '$.gameDate')::timestamptz            as game_date,
    json_extract_string(game, '$.officialDate')::date               as official_date,
    json_extract_string(game, '$.dayNight')                         as day_night,
    json_extract_string(game, '$.doubleHeader')                     as double_header,
    json_extract_string(game, '$.gameNumber')::integer              as game_number,
    json_extract_string(game, '$.gamesInSeries')::integer           as games_in_series,
    json_extract_string(game, '$.seriesGameNumber')::integer        as series_game_number,
    json_extract_string(game, '$.seriesDescription')                as series_description,
    json_extract_string(game, '$.scheduledInnings')::integer        as scheduled_innings,
    json_extract_string(game, '$.isTie')::boolean                   as is_tie,

    -- Game status
    json_extract_string(game, '$.status.abstractGameState')         as abstract_game_state,
    json_extract_string(game, '$.status.detailedState')             as detailed_state,
    json_extract_string(game, '$.status.statusCode')                as status_code,

    -- Home team
    json_extract_string(game, '$.teams.home.team.id')::integer      as home_team_id,
    json_extract_string(game, '$.teams.home.team.name')             as home_team_name,
    json_extract_string(game, '$.teams.home.score')::integer        as home_score,
    json_extract_string(game, '$.teams.home.isWinner')::boolean     as home_is_winner,
    json_extract_string(game, '$.teams.home.leagueRecord.wins')::integer   as home_wins,
    json_extract_string(game, '$.teams.home.leagueRecord.losses')::integer as home_losses,

    -- Away team
    json_extract_string(game, '$.teams.away.team.id')::integer      as away_team_id,
    json_extract_string(game, '$.teams.away.team.name')             as away_team_name,
    json_extract_string(game, '$.teams.away.score')::integer        as away_score,
    json_extract_string(game, '$.teams.away.isWinner')::boolean     as away_is_winner,
    json_extract_string(game, '$.teams.away.leagueRecord.wins')::integer   as away_wins,
    json_extract_string(game, '$.teams.away.leagueRecord.losses')::integer as away_losses,

    -- Venue
    json_extract_string(game, '$.venue.id')::integer                as venue_id,
    json_extract_string(game, '$.venue.name')                       as venue_name,

    ingestion_ts::timestamp                                         as ingestion_ts

from deduped

{% else %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

select * from baseball_data.lakehouse_ext.stg_statsapi_games

{% endif %}
