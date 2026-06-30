-- =============================================================================
-- feature_pregame_injury_status.sql   (E11.1-W7b lakehouse decommission)
-- Grain: one row per player_id × status interval (valid_from, valid_to)
-- Source: stg_statsapi_player_injury_status
-- Epic 15, Story 15.3 — Injury status SCD-2
-- =============================================================================
-- Promotes stg_statsapi_player_injury_status to the feature layer with standard
-- SCD-2 columns. One row per distinct injury-status period per player.
--
-- Point-in-time join pattern (use is_current = false for historical replay):
--   ON  inj.player_id  = batter_id
--   AND inj.valid_from <= :prediction_ts
--   AND (inj.valid_to  >  :prediction_ts OR inj.valid_to IS NULL)
--
-- is_injured = true  → player is on IL / paternity / bereavement list
-- is_injured = false → player returned / activated
-- No matching row    → treat as available (COALESCE to false in consumer)
--
-- Coverage: full history from player_transactions inception (2021-03-01+).
-- Source is append-only so full rebuild is idempotent.
--
-- DuckDB branch (E11.1-W7b): reads the migrated stg_statsapi_player_injury_status
-- (registered as a DuckDB view by run_w1_lakehouse.py). The SCD-2 promotion is the
-- same body with Snowflake→DuckDB dialect rewrites:
--   ::timestamp_ntz → ::timestamp   (DuckDB has no _ntz suffix; both are wall-clock)
--   sysdate()       → current_timestamp
--   md5(cast(... as varchar)) is DuckDB-native.
-- The Snowflake (else) branch is unchanged (rollback path).
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w7b_lakehouse']) }}

with

source as (
    -- Zero-length intervals (status_start_date = status_end_date) are intra-day
    -- transaction noise from same-day place+activate events and must be dropped
    -- before SCD-2 promotion; they are never valid pregame windows.
    select *
    from stg_statsapi_player_injury_status
    where status_end_date is null
       or status_end_date > status_start_date
),

with_scd2_cols as (
    select
        player_id,
        player_name,
        is_injured,

        -- SCD-2 temporal columns; date-cast to midnight TIMESTAMP because IL
        -- transactions are reported at day granularity (no intraday precision).
        status_start_date::timestamp                        as valid_from,
        status_end_date::timestamp                          as valid_to,
        (status_end_date is null)                           as is_current,

        -- Record hash over the state value for audit/diff tooling.
        md5(cast(is_injured as varchar))                    as record_hash,
        current_timestamp                                   as computed_at

    from source
)

select * from with_scd2_cols

{% else %}

-- E11.1-W8b: FINALIZE the dual-branch (the W7b-deferred cutover). The Snowflake side
-- now reads the lakehouse_ext external table over the DuckDB-built S3 parquet (created
-- by generate_w7b_external_tables.py / W7B_TABLES — feature_pregame_injury_status already
-- has an external table). Was a native `table` materialize from stg_statsapi_player_injury_status;
-- the DuckDB branch above is the build that produces that parquet. Parity-gated by
-- parity_check_w8b.py. Materialized='table' so downstream ref()s (mart_player_profile_identity,
-- feature_pregame_lineup_features) see a concrete table with the same grain.
{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_injury_status

{% endif %}
