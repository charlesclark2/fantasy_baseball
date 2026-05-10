-- =============================================================================
-- mart_odds_outcomes.sql
-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key,
--        outcome_name)
-- Purpose: Unified odds outcomes from all ingestion sources. Historical rows
--          (2021–2025) come from The Odds API; live rows (2026+) come from
--          both Odds API and Parlay API during the parallel overlap period,
--          then Parlay API only after the 2026-06-01 cutover.
--          Deduplication within a load_id prevents duplicate rows when the
--          same bookmaker appears across multiple Odds API region calls (us/us2).
--          Parlay API rows carry no dual-region overlap so no dedup is needed.
-- Join key:   event_id → mart_odds_events (Odds API) or stg_parlayapi_odds
-- Discriminator: source_system ('odds_api' | 'parlay_api')
-- New columns (Parlay API migration):
--   source_system         — discriminates row origin
--   doubleheader_ambiguous — true when StatsAPI shows a DH for this matchup;
--                            Parlay API collapses both DH games into one event.
--                            Always false for Odds API rows.
-- Note: Parlay API commence_time is a 19:00:00Z slate placeholder, not the
--       actual game start. Use bookmaker_last_update for leakage guards, not
--       commence_time, when working with Parlay API rows.
-- =============================================================================

{{
    config(
        materialized = 'table'
    )
}}

with odds_api as (

    select
        ingestion_ts,
        load_id,
        market_requested,
        region_requested,
        x_requests_used,
        x_requests_remaining,
        'odds_api'::varchar                                     as source_system,
        event_id,
        sport_key,
        sport_title,
        commence_time,
        home_team,
        away_team,
        false::boolean                                          as doubleheader_ambiguous,
        bookmaker_key,
        bookmaker_title,
        bookmaker_last_update,
        market_key,
        market_last_update,
        outcome_name,
        outcome_price_american,
        outcome_price_decimal,
        outcome_point
    from {{ ref('stg_oddsapi_odds') }}

),

parlay_api as (

    select
        ingestion_ts,
        load_id,
        market_requested,
        region_requested,
        x_requests_used,
        x_requests_remaining,
        source_system,
        event_id,
        sport_key,
        sport_title,
        commence_time,
        home_team,
        away_team,
        doubleheader_ambiguous,
        bookmaker_key,
        bookmaker_title,
        bookmaker_last_update,
        market_key,
        market_last_update,
        outcome_name,
        outcome_price_american,
        outcome_price_decimal,
        outcome_point
    from {{ ref('stg_parlayapi_odds') }}

),

combined as (

    select * from odds_api
    union all
    select * from parlay_api

)

select

    -- ── Ingestion metadata ────────────────────────────────────────────────────
    ingestion_ts,
    load_id,
    x_requests_used,
    x_requests_remaining,
    market_requested,
    region_requested,

    -- ── Source discriminator ──────────────────────────────────────────────────
    source_system,

    -- ── Event identifiers ─────────────────────────────────────────────────────
    event_id,
    sport_key,
    sport_title,
    commence_time,
    convert_timezone('UTC', 'America/Los_Angeles', commence_time)::date as commence_date,
    home_team,
    away_team,

    -- ── Doubleheader flag (Parlay API only; always false for Odds API rows) ───
    doubleheader_ambiguous,

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

from combined
