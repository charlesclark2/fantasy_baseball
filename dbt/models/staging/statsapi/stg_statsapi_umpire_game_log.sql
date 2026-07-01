-- stg_statsapi_umpire_game_log.sql
-- Grain: one row per game_pk (deduped to most-recent loaded_at).
-- Source: baseball_data.statsapi.umpire_game_log
--
-- Rows from UmpScorecards (data_source='umpscorecards') carry full tendency metrics.
-- Rows from the daily Stats API ingest (data_source='statsapi') carry only
-- umpire_name and umpire_id; tendency columns are NULL.
--
-- E11.1-W11 Tier-B lakehouse migration. DuckDB branch reads the umpire_game_log S3 raw
-- mirror (lakehouse_raw/umpire_game_log/, dual-written by the 4 umpire ingests under
-- W11_RAW_WRITE_MODE + the one-time export_w11_raw_to_s3.py bridge). The Snowflake (else)
-- branch is a thin view over the lakehouse_ext external table (rollback path). loaded_at is
-- read via try_cast(... as timestamp) — the INC-23 use-site cast: the raw mirror UNIONs the
-- SF-typed bridge (TIMESTAMP) with the live-writer rows (ISO VARCHAR, stamped by
-- umpire_mirror_rows), which union_by_name reconciles to VARCHAR; try_cast parses both.

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11b_lakehouse']) }}

with

source as (
    select * from read_parquet('{{ lakehouse_raw_loc("umpire_game_log") }}**/*.parquet', union_by_name=true)
),

deduped as (
    select
        game_pk::integer                             as game_pk,
        game_date::date                              as game_date,
        season::integer                              as season,
        umpire_name::varchar                         as umpire_name,
        umpire_id::varchar                           as umpire_id,
        try_cast(k_pct as double)                    as k_pct,
        try_cast(bb_pct as double)                   as bb_pct,
        try_cast(total_runs as integer)              as total_runs,
        try_cast(called_strikes_above_avg as double) as called_strikes_above_avg,
        try_cast(run_expectancy_delta as double)     as run_expectancy_delta,
        try_cast(total_run_impact as double)         as total_run_impact,
        try_cast(accuracy_above_expected as double)  as accuracy_above_expected,
        data_source::varchar                         as data_source,
        try_cast(loaded_at as timestamp)             as loaded_at,
        row_number() over (
            partition by game_pk
            order by
                -- prefer umpscorecards rows (have tendency metrics) over statsapi rows
                case when data_source = 'umpscorecards' then 0 else 1 end,
                try_cast(loaded_at as timestamp) desc nulls last
        ) as rn
    from source
)

select
    game_pk,
    game_date,
    season,
    umpire_name,
    umpire_id,
    k_pct,
    bb_pct,
    total_runs,
    called_strikes_above_avg,
    run_expectancy_delta,
    total_run_impact,
    accuracy_above_expected,
    data_source,
    loaded_at
from deduped
where rn = 1

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.stg_statsapi_umpire_game_log

{% endif %}
