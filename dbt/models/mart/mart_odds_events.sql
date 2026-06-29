-- =============================================================================
-- mart_odds_events.sql
-- Grain: one row per event_id (latest ingestion snapshot)
-- Purpose: Clean, relational table of upcoming and recent MLB events sourced
--          from The Odds API. Deduplicates to the most recently ingested
--          snapshot per event. Use this as the authoritative event dimension
--          when joining to mart_odds_outcomes.
-- Join key: event_id
--
-- DuckDB branch (E11.1-W6): reads the migrated stg_oddsapi_events; the Snowflake
-- (else) branch is a thin view over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with events as (

    select * from stg_oddsapi_events

)

select

    -- ── Keys ──────────────────────────────────────────────────────────────────
    event_id,

    -- ── Event metadata ────────────────────────────────────────────────────────
    sport_key,
    sport_title,
    commence_time,
    (commence_time::timestamp at time zone 'UTC' at time zone 'America/Los_Angeles')::date as commence_date,

    -- ── Teams ─────────────────────────────────────────────────────────────────
    home_team,
    away_team,

    -- ── Ingestion metadata ────────────────────────────────────────────────────
    ingestion_ts,
    load_id,
    x_requests_used,
    x_requests_remaining

from events

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_odds_events

{% endif %}
