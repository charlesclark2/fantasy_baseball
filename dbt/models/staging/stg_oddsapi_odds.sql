-- =============================================================================
-- stg_oddsapi_odds.sql  (E11.1-W3pre lakehouse decommission)
-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key, outcome_name).
-- Source: baseball_data.oddsapi.mlb_odds_raw — one VARIANT row per (event, ingestion run).
-- Three lateral flattens: bookmakers[] → markets[] → outcomes[]. Within a load_id,
-- the same (bookmaker × market × outcome) can appear in both us and us2 region
-- responses, so a row_number dedup keeps one.
--
-- ⚠️ SERVING-COUPLED: feeds mart_odds_outcomes, which predict_today.py and
-- write_serving_store.py read at request time. The DuckDB/Snowflake outputs MUST be
-- value-identical (parity-gated) before the Snowflake (else) branch view is cut over.
--
-- DuckDB branch (E11.1-W3pre): flattens the RAW JSON parquet (lakehouse_raw/mlb_odds_raw/);
-- built to S3 by run_w1_lakehouse.py. The Snowflake (else) branch is a thin view
-- over the lakehouse_ext external table holding that output.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

with src as (

    select ingestion_ts, load_id, request_params, x_requests_used, x_requests_remaining, raw_json
    from read_parquet('{{ lakehouse_raw_loc("mlb_odds_raw") }}**/*.parquet', union_by_name=true)
    where raw_json is not null
      and json_extract_string(raw_json, '$.id') is not null
      and json_extract(raw_json, '$.bookmakers') is not null

),

bookmakers_flattened as (

    select
        ingestion_ts,
        load_id,
        request_params,
        x_requests_used,
        x_requests_remaining,
        json_extract_string(raw_json, '$.id')               as event_id,
        json_extract_string(raw_json, '$.sport_key')        as sport_key,
        json_extract_string(raw_json, '$.sport_title')      as sport_title,
        json_extract_string(raw_json, '$.commence_time')::timestamp as commence_time,
        json_extract_string(raw_json, '$.home_team')        as home_team,
        json_extract_string(raw_json, '$.away_team')        as away_team,
        unnest(from_json(json_extract(raw_json, '$.bookmakers'), '["JSON"]')) as bookmaker
    from src

),

markets_flattened as (

    select
        ingestion_ts, load_id, request_params, x_requests_used, x_requests_remaining,
        event_id, sport_key, sport_title, commence_time, home_team, away_team,
        json_extract_string(bookmaker, '$.key')             as bookmaker_key,
        json_extract_string(bookmaker, '$.title')           as bookmaker_title,
        json_extract_string(bookmaker, '$.last_update')::timestamp as bookmaker_last_update,
        unnest(from_json(json_extract(bookmaker, '$.markets'), '["JSON"]')) as market
    from bookmakers_flattened

),

outcomes_flattened as (

    select
        ingestion_ts, load_id, request_params, x_requests_used, x_requests_remaining,
        event_id, sport_key, sport_title, commence_time, home_team, away_team,
        bookmaker_key, bookmaker_title, bookmaker_last_update,
        json_extract_string(market, '$.key')                as market_key,
        json_extract_string(market, '$.last_update')::timestamp as market_last_update,
        unnest(from_json(json_extract(market, '$.outcomes'), '["JSON"]')) as outcome
    from markets_flattened

)

select
    ingestion_ts,
    load_id,
    json_extract_string(request_params, '$.markets')        as market_requested,
    json_extract_string(request_params, '$.regions')        as region_requested,
    x_requests_used,
    x_requests_remaining,

    event_id,
    sport_key,
    sport_title,
    commence_time,
    home_team,
    away_team,

    bookmaker_key,
    bookmaker_title,
    bookmaker_last_update,

    market_key,
    market_last_update,

    json_extract_string(outcome, '$.name')                  as outcome_name,
    json_extract_string(outcome, '$.price')::integer        as outcome_price_american,
    case
        when json_extract_string(outcome, '$.price')::integer >= 100
            then (json_extract_string(outcome, '$.price')::integer / 100.0) + 1.0
        else (100.0 / abs(json_extract_string(outcome, '$.price')::integer)) + 1.0
    end::double                                             as outcome_price_decimal,
    json_extract_string(outcome, '$.point')::double         as outcome_point

from outcomes_flattened
qualify row_number() over (
    partition by load_id, event_id, bookmaker_key, market_key, json_extract_string(outcome, '$.name')
    order by ingestion_ts
) = 1

{% else %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

select * from baseball_data.lakehouse_ext.stg_oddsapi_odds

{% endif %}
