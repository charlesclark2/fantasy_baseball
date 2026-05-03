-- stg_statsapi_umpire_game_log.sql
-- Grain: one row per game_pk (deduped to most-recent loaded_at).
-- Source: baseball_data.statsapi.umpire_game_log
--
-- Rows from UmpScorecards (data_source='umpscorecards') carry full tendency metrics.
-- Rows from the daily Stats API ingest (data_source='statsapi') carry only
-- umpire_name and umpire_id; tendency columns are NULL.

{{ config(materialized='table') }}

with

deduped as (
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
        loaded_at,
        row_number() over (
            partition by game_pk
            order by
                -- prefer umpscorecards rows (have tendency metrics) over statsapi rows
                case when data_source = 'umpscorecards' then 0 else 1 end,
                loaded_at desc
        ) as rn
    from {{ source('statsapi', 'umpire_game_log') }}
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
