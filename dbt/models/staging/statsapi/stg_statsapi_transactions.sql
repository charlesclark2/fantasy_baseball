-- =============================================================================
-- stg_statsapi_transactions.sql   (E11.1-W7b lakehouse decommission)
-- Grain: one row per transaction_id (deduplicated from player_transactions)
-- Source: baseball_data.statsapi.player_transactions
-- Card 7.I — Injury / Confirmed Lineup Features
--
-- Precursor in the W7b profile_identity chain:
--   player_transactions → THIS → stg_statsapi_player_injury_status →
--   feature_pregame_injury_status (SCD-2) → mart_player_profile_identity.
--
-- DuckDB branch (E11.1-W7b): reads the player_transactions TYPED parquet
-- (lakehouse/player_transactions/part-0.parquet, exported by
-- scripts/export_w7b_precursors_to_s3.py — the W4/W5 typed-table export pattern;
-- the table is already relational, so no raw-JSON flatten is needed and the
-- duckdb dedup is value-identical to the Snowflake one). The ingest writer
-- (ingest_transactions.py) KEEPS its Snowflake append — this reads the
-- one-time/opt-in S3 mirror, same recurring-freshness caveat as W4/W5.
-- The Snowflake (else) branch is unchanged (rollback path).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w7b_lakehouse']) }}

with raw as (
    -- E11.1-W11 read-repoint: live-writer raw mirror (lakehouse_raw/, dual-written by
    -- ingest_transactions.py under W11_RAW_WRITE_MODE) instead of the SF-sourced W7b snapshot.
    select *
    from read_parquet('{{ lakehouse_raw_loc("player_transactions") }}**/*.parquet', union_by_name=true)
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

{% else %}

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

{% endif %}
