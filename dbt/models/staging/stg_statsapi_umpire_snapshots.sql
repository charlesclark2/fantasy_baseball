-- stg_statsapi_umpire_snapshots.sql
-- Grain: one row per (game_pk, loaded_at). Preserves all ingestion snapshots
-- for SCD-2 change detection in feature_pregame_umpire_status.
--
-- Source rows are unique at (game_pk, loaded_at); QUALIFY is a safety guard
-- in case a future ingest produces duplicate timestamps, preferring umpscorecards
-- rows (which carry full tendency metrics) over statsapi rows.
--
-- Record hash: umpire_id + tendency stats. Catches both pre-game substitutions
-- (umpire_id changes) and post-game UmpScorecards enrichment (stats populate).
--
-- Coverage: Epic T.4 onward (~2026-05-02). Pre-T umpire data exists only in
-- stg_statsapi_umpire_game_log (final-state, no intraday history).
--
-- E11.1-W11 Tier-B lakehouse migration. DuckDB branch reads the umpire_game_log S3 raw
-- mirror (lakehouse_raw/umpire_game_log/); Snowflake (else) branch is a thin view over the
-- lakehouse_ext external table (rollback path). loaded_at is read via try_cast(... as
-- timestamp) — the INC-23 use-site cast for the SF-bridge(TIMESTAMP)↔live-writer(ISO VARCHAR)
-- union that union_by_name reconciles to VARCHAR. The SCD-2 spans are parity-verified before
-- cutover (a real run — a parity SELECT alone won't prove the snapshot/hash logic).

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w11b_lakehouse']) }}

with source as (
    select
        game_pk::integer                        as game_pk,
        game_date::date                         as game_date,
        season::integer                         as season,
        umpire_name::varchar                    as umpire_name,
        umpire_id::varchar                      as umpire_id,
        try_cast(total_runs as double)          as total_runs,
        try_cast(total_run_impact as double)    as total_run_impact,
        try_cast(accuracy_above_expected as double) as accuracy_above_expected,
        data_source::varchar                    as data_source,
        try_cast(loaded_at as timestamp)        as loaded_at
    from read_parquet('{{ lakehouse_raw_loc("umpire_game_log") }}**/*.parquet', union_by_name=true)
),

with_hash as (
    select
        *,
        md5(
            coalesce(cast(umpire_name             as varchar), '') || '|' ||
            coalesce(cast(total_runs              as varchar), '') || '|' ||
            coalesce(cast(total_run_impact        as varchar), '') || '|' ||
            coalesce(cast(accuracy_above_expected as varchar), '')
        )                                           as record_hash
    from source
)

select *
from with_hash
qualify row_number() over (
    partition by game_pk, loaded_at
    order by case when data_source = 'umpscorecards' then 0 else 1 end
) = 1

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.stg_statsapi_umpire_snapshots

{% endif %}
