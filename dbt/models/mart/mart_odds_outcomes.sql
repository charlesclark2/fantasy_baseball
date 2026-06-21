-- =============================================================================
-- mart_odds_outcomes.sql
-- Grain: one row per (ingestion_ts, event_id, bookmaker_key, market_key,
--        outcome_name)
-- Purpose: Unified odds outcomes from The Odds API (all eras). Historical rows
--          (2021–2025) and live rows (2026+) all come from The Odds API.
--          Parlay API was the live source 2026-05-23 – 2026-06-16; its rows
--          remain in the table as cold archive (source_system = 'parlay_api')
--          but no new Parlay rows are appended (E11.6 decommission 2026-06-21).
--          Deduplication within a load_id prevents duplicate rows when the
--          same bookmaker appears across multiple Odds API region calls (us/us2).
-- Join key:   event_id → mart_odds_events (Odds API)
-- Discriminator: source_system ('odds_api' | 'parlay_api')
-- =============================================================================

{{
    config(
        materialized = 'incremental',
        incremental_strategy = 'append',
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
    {% if is_incremental() %}
    where ingestion_ts > (select max(ingestion_ts) from {{ this }})
    {% endif %}

),

combined as (

    -- E11.6 (2026-06-21): Parlay API permanently decommissioned. Historical Parlay rows
    -- remain in the table as cold archive; no new rows appended from this branch.
    select * from odds_api

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
