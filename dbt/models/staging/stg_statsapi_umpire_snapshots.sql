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

{{ config(materialized='table') }}

with source as (
    select
        game_pk::integer                        as game_pk,
        game_date::date                         as game_date,
        season::integer                         as season,
        umpire_name::varchar                    as umpire_name,
        umpire_id::varchar                      as umpire_id,
        total_runs::float                       as total_runs,
        total_run_impact::float                 as total_run_impact,
        accuracy_above_expected::float          as accuracy_above_expected,
        data_source::varchar                    as data_source,
        loaded_at::timestamp_ntz                as loaded_at
    from {{ source('statsapi', 'umpire_game_log') }}
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
