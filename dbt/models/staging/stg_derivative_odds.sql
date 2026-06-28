-- =============================================================================
-- stg_derivative_odds.sql  (E11.1-W3pre lakehouse decommission)
-- Grain: one row per (actual_snapshot_ts, event_id, bookmaker_key, market_key, outcome_name).
-- Source: baseball_data.oddsapi.derivative_odds_raw, written by
--         scripts/derivative_odds_backfill.py (E2.0). Three-level flatten:
--         bookmakers[] → markets[] → outcomes[].
--
-- ⚠️  EVAL/CLV-ONLY — derivative-market closing lines (team totals, alt totals, F5).
--     NEVER joined into training features (market-blind, §0.1 Principle 3). Not on the
--     live serving path → safe to migrate.
--
-- DuckDB branch (E11.1-W3pre): flattens the RAW JSON parquet (lakehouse_raw/derivative_odds_raw/);
-- built to S3 by run_w1_lakehouse.py. Timestamps are read as ISO VARCHAR from the raw
-- parquet and cast ::timestamp here (repo date-serialization convention). The Snowflake (else) branch
-- Snowflake branch is a thin view over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

with src as (

    select
        ingestion_ts, load_id, event_id,
        requested_snapshot_ts, actual_snapshot_ts, previous_snapshot_ts, next_snapshot_ts,
        markets_requested, regions_requested, x_requests_remaining, x_requests_last,
        raw_json
    from read_parquet('{{ lakehouse_raw_loc("derivative_odds_raw") }}**/*.parquet', union_by_name=true)
    where raw_json is not null
      and json_extract_string(raw_json, '$.id') is not null
      and json_extract(raw_json, '$.bookmakers') is not null

),

bookmakers_flattened as (

    select
        ingestion_ts, load_id, event_id,
        requested_snapshot_ts, actual_snapshot_ts, previous_snapshot_ts, next_snapshot_ts,
        markets_requested, regions_requested, x_requests_remaining, x_requests_last,
        json_extract_string(raw_json, '$.sport_key')        as sport_key,
        json_extract_string(raw_json, '$.commence_time')::timestamp as commence_time,
        json_extract_string(raw_json, '$.home_team')        as home_team,
        json_extract_string(raw_json, '$.away_team')        as away_team,
        unnest(from_json(json_extract(raw_json, '$.bookmakers'), '["JSON"]')) as bookmaker
    from src

),

markets_flattened as (

    select
        ingestion_ts, load_id, event_id,
        requested_snapshot_ts, actual_snapshot_ts, previous_snapshot_ts, next_snapshot_ts,
        markets_requested, regions_requested, x_requests_remaining, x_requests_last,
        sport_key, commence_time, home_team, away_team,
        json_extract_string(bookmaker, '$.key')             as bookmaker_key,
        json_extract_string(bookmaker, '$.title')           as bookmaker_title,
        json_extract_string(bookmaker, '$.last_update')::timestamp as bookmaker_last_update,
        unnest(from_json(json_extract(bookmaker, '$.markets'), '["JSON"]')) as market
    from bookmakers_flattened

),

outcomes_flattened as (

    select
        ingestion_ts, load_id, event_id,
        requested_snapshot_ts, actual_snapshot_ts, previous_snapshot_ts, next_snapshot_ts,
        markets_requested, regions_requested, x_requests_remaining, x_requests_last,
        sport_key, commence_time, home_team, away_team,
        bookmaker_key, bookmaker_title, bookmaker_last_update,
        json_extract_string(market, '$.key')                as market_key,
        json_extract_string(market, '$.last_update')::timestamp as market_last_update,
        unnest(from_json(json_extract(market, '$.outcomes'), '["JSON"]')) as outcome
    from markets_flattened
    where json_extract_string(market, '$.outcomes') is not null

)

select
    ingestion_ts::timestamp                                 as ingestion_ts,
    load_id,
    requested_snapshot_ts::timestamp                        as requested_snapshot_ts,
    actual_snapshot_ts::timestamp                           as actual_snapshot_ts,
    previous_snapshot_ts::timestamp                         as previous_snapshot_ts,
    next_snapshot_ts::timestamp                             as next_snapshot_ts,
    markets_requested,
    regions_requested,
    x_requests_remaining,
    x_requests_last,

    event_id,
    sport_key,
    commence_time,
    home_team,
    away_team,

    bookmaker_key,
    bookmaker_title,
    bookmaker_last_update,

    market_key,
    market_last_update,

    json_extract_string(outcome, '$.name')                  as outcome_name,
    json_extract_string(outcome, '$.description')           as outcome_description,
    json_extract_string(outcome, '$.price')::integer        as outcome_price_american,
    case
        when json_extract_string(outcome, '$.price')::integer >= 100
            then (json_extract_string(outcome, '$.price')::integer / 100.0) + 1.0
        when json_extract_string(outcome, '$.price')::integer = 0
            then null
        else (100.0 / abs(json_extract_string(outcome, '$.price')::integer)) + 1.0
    end::double                                             as outcome_price_decimal,
    json_extract_string(outcome, '$.point')::double         as outcome_point

from outcomes_flattened
where json_extract_string(outcome, '$.price')::integer is not null

{% else %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

select * from baseball_data.lakehouse_ext.stg_derivative_odds

{% endif %}
