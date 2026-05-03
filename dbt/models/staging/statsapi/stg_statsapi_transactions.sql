-- =============================================================================
-- stg_statsapi_transactions.sql
-- Grain: one row per transaction_id (deduplicated from player_transactions)
-- Source: baseball_data.statsapi.player_transactions
-- Card 7.I — Injury / Confirmed Lineup Features
-- =============================================================================

{{ config(materialized='table') }}

with

raw as (
    select * from {{ source('statsapi', 'player_transactions') }}
),

deduped as (
    select
        transaction_id,
        player_id,
        player_name,
        team_id,
        team_name,
        transaction_date,
        effective_date,
        resolution_date,
        type_code,
        type_description,
        description,
        ingestion_ts,
        row_number() over (
            partition by transaction_id
            order by ingestion_ts desc
        ) as rn
    from raw
)

select
    transaction_id,
    player_id,
    player_name,
    team_id,
    team_name,
    transaction_date,
    effective_date,
    resolution_date,
    type_code,
    type_description,
    description,
    ingestion_ts
from deduped
where rn = 1
