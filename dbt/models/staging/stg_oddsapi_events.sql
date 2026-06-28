-- =============================================================================
-- stg_oddsapi_events.sql  (E11.1-W3pre lakehouse decommission)
-- Grain: one row per event_id (latest ingestion snapshot).
-- Source: baseball_data.oddsapi.mlb_events_raw — the full /events API response
-- array as a single VARIANT row per ingestion run. Lateral flatten expands that
-- array to one row per event per run; dedup collapses to the latest snapshot.
--
-- DuckDB branch (E11.1-W3pre): reads the RAW JSON parquet exported to S3
-- (lakehouse_raw/mlb_events_raw/), flattens it with DuckDB JSON functions, and is
-- built to S3 by run_w1_lakehouse.py (W3PRE_MODELS). The Snowflake (else) branch Snowflake
-- branch is a thin view over the lakehouse_ext external table holding that output.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

-- ── DuckDB flatten (reproduces the Snowflake lateral-flatten + dedup below) ──
with src as (

    select ingestion_ts, load_id, x_requests_used, x_requests_remaining, raw_json
    from read_parquet('{{ lakehouse_raw_loc("mlb_events_raw") }}**/*.parquet', union_by_name=true)
    where raw_json is not null
      and json_type(raw_json) = 'ARRAY'
      and json_array_length(raw_json) > 0

),

events_flattened as (

    select
        ingestion_ts,
        load_id,
        x_requests_used,
        x_requests_remaining,
        unnest(from_json(raw_json, '["JSON"]'))         as event
    from src

)

select
    ingestion_ts,
    load_id,
    x_requests_used,
    x_requests_remaining,

    json_extract_string(event, '$.id')                  as event_id,
    json_extract_string(event, '$.sport_key')           as sport_key,
    json_extract_string(event, '$.sport_title')         as sport_title,
    json_extract_string(event, '$.commence_time')::timestamp as commence_time,
    json_extract_string(event, '$.home_team')           as home_team,
    json_extract_string(event, '$.away_team')           as away_team

from events_flattened
qualify row_number() over (
    partition by json_extract_string(event, '$.id')
    order by ingestion_ts desc
) = 1

{% else %}

{{ config(materialized='view', tags=['w3pre_lakehouse']) }}

select * from baseball_data.lakehouse_ext.stg_oddsapi_events

{% endif %}
