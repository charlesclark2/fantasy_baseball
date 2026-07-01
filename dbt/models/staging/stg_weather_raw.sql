-- stg_weather_raw.sql
-- Grain: latest row per (game_pk, venue_id, observation_type, hours_to_first_pitch).
-- Scope: all observation types (forecast_pregame / forecast_intraday / observed_at_first_pitch).
--
-- E11.1-W11 Tier-C lakehouse migration. DuckDB branch reads the weather_raw S3 raw mirror
-- (lakehouse_raw/weather_raw/, dual-written by ingest_weather / backfill_observed_weather under
-- W11_RAW_WRITE_MODE + the one-time export_w11_raw_to_s3.py bridge). The Snowflake (else) branch is
-- a thin view over the lakehouse_ext external table (rollback path). game_datetime_utc / loaded_at
-- are read via try_cast(... as timestamp) — the INC-23 use-site cast: the raw mirror UNIONs the
-- SF-typed bridge (TIMESTAMP) with the live-writer rows (ISO VARCHAR from weather_mirror_rows), which
-- union_by_name reconciles to VARCHAR; try_cast parses both. Numeric cols use try_cast (the raw mirror
-- keeps scalars native but a mixed bridge/live union is safest cast at the use-site).

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11c_lakehouse']) }}

with source as (
    select * from read_parquet('{{ lakehouse_raw_loc("weather_raw") }}**/*.parquet', union_by_name=true)
)

select
    game_pk::integer                                    as game_pk,
    venue_id::integer                                   as venue_id,
    try_cast(game_datetime_utc as timestamp)            as game_datetime_utc,
    try_cast(fetch_offset_hours as double)              as fetch_offset_hours,
    try_cast(temp_f as double)                          as temp_f,
    try_cast(wind_speed_mph as double)                  as wind_speed_mph,
    try_cast(wind_direction_deg as integer)             as wind_direction_deg,
    try_cast(humidity_pct as integer)                   as humidity_pct,
    condition_text::varchar                             as condition_text,
    api_source::varchar                                 as api_source,
    coalesce(
        weather_observation_type::varchar,
        'forecast_pregame'
    )                                                   as weather_observation_type,
    try_cast(hours_to_first_pitch as integer)           as hours_to_first_pitch,
    try_cast(loaded_at as timestamp)                    as loaded_at
from source
qualify row_number() over (
    partition by game_pk, venue_id, weather_observation_type, hours_to_first_pitch
    order by try_cast(loaded_at as timestamp) desc nulls last
) = 1

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.stg_weather_raw

{% endif %}
