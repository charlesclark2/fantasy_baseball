-- =============================================================================
-- feature_pregame_injury_status.sql
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
-- =============================================================================

{{ config(materialized='table') }}

with

source as (
    -- Zero-length intervals (status_start_date = status_end_date) are intra-day
    -- transaction noise from same-day place+activate events and must be dropped
    -- before SCD-2 promotion; they are never valid pregame windows.
    select *
    from {{ ref('stg_statsapi_player_injury_status') }}
    where status_end_date is null
       or status_end_date > status_start_date
),

with_scd2_cols as (
    select
        player_id,
        player_name,
        is_injured,

        -- SCD-2 temporal columns; date-cast to midnight TIMESTAMP_NTZ because
        -- IL transactions are reported at day granularity (no intraday precision).
        status_start_date::timestamp_ntz                    as valid_from,
        status_end_date::timestamp_ntz                      as valid_to,
        (status_end_date is null)                           as is_current,

        -- Record hash over the state value for audit/diff tooling.
        md5(cast(is_injured as varchar))                    as record_hash,
        sysdate()                                           as computed_at

    from source
)

select * from with_scd2_cols
