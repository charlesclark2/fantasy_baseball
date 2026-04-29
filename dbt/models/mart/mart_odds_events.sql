-- =============================================================================
-- mart_odds_events.sql
-- Grain: one row per event_id (latest ingestion snapshot)
-- Purpose: Clean, relational table of upcoming and recent MLB events sourced
--          from The Odds API. Deduplicates to the most recently ingested
--          snapshot per event. Use this as the authoritative event dimension
--          when joining to mart_odds_outcomes.
-- Join key: event_id
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with events as (

    select * from {{ ref('stg_oddsapi_events') }}

)

select

    -- ── Keys ──────────────────────────────────────────────────────────────────
    event_id,

    -- ── Event metadata ────────────────────────────────────────────────────────
    sport_key,
    sport_title,
    commence_time,
    convert_timezone('UTC', 'America/Los_Angeles', commence_time)::date as commence_date,

    -- ── Teams ─────────────────────────────────────────────────────────────────
    home_team,
    away_team,

    -- ── Ingestion metadata ────────────────────────────────────────────────────
    ingestion_ts,
    load_id,
    x_requests_used,
    x_requests_remaining

from events
