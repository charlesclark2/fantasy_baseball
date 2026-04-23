-- =============================================================================
-- mart_odds_outcomes.sql
-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key,
--        outcome_name)
-- Purpose: Full history of odds outcomes from The Odds API across all
--          bookmakers and markets. Historical snapshots are preserved so
--          downstream models can analyze line movement and bookmaker
--          comparisons over time.
--          Deduplication within a load_id prevents duplicate rows when the
--          same bookmaker appears across multiple region calls (us / us2).
-- Join key: event_id → mart_odds_events
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with odds as (

    select * from {{ ref('stg_oddsapi_odds') }}

)

select

    -- ── Ingestion metadata ────────────────────────────────────────────────────
    ingestion_ts,
    load_id,
    x_requests_used,
    x_requests_remaining,
    market_requested,
    region_requested,

    -- ── Event identifiers ─────────────────────────────────────────────────────
    event_id,
    sport_key,
    sport_title,
    commence_time,
    commence_time::date                                    as commence_date,
    home_team,
    away_team,

    -- ── Bookmaker ─────────────────────────────────────────────────────────────
    bookmaker_key,
    bookmaker_title,
    bookmaker_last_update,

    -- ── Market ────────────────────────────────────────────────────────────────
    market_key,
    market_last_update,

    -- ── Outcome ───────────────────────────────────────────────────────────────
    outcome_name,
    outcome_price_american,
    outcome_price_decimal,
    outcome_point,          -- non-null for totals (Over/Under line); null for h2h

    -- ── Derived flags ─────────────────────────────────────────────────────────
    (outcome_point is not null)::boolean                   as is_totals_market,
    (outcome_name = home_team)::boolean                    as is_home_outcome,
    (outcome_name = away_team)::boolean                    as is_away_outcome

from odds
