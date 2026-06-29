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
--
-- ⚠️ SERVING-COUPLED (E11.1-W6): read at request time by predict_today.py /
-- write_serving_store.py (batch) and the picks/odds serving fallback. The
-- DuckDB/Snowflake outputs MUST be value-identical (parity-gated). The live
-- Snowflake table is odds_api-only (no Parlay archive rows present), so the
-- full DuckDB rebuild from stg_oddsapi_odds reproduces it exactly.
--
-- DuckDB branch (E11.1-W6): the former incremental(append) build becomes a full
-- rebuild (view) over the migrated stg_oddsapi_odds; the Snowflake (else) branch
-- is a thin view over the lakehouse_ext external table. (First W6 incremental→view
-- conversion — same pattern as W5's mart_game_results.)
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with odds_api as (

    select
        -- stg_oddsapi_odds carries ingestion_ts as VARCHAR (the lakehouse_raw tier pins it to
        -- utf8); Snowflake's mart_odds_outcomes.ingestion_ts is TIMESTAMP_NTZ. Cast here so the
        -- grain + every downstream `ingestion_ts < commence_time` leakage guard
        -- (mart_odds_line_movement / mart_closing_line_value) binds, and parity matches the
        -- Snowflake type. Session TZ=UTC ⇒ naive (historical export) and +00:00 (live writer)
        -- strings both land on the same UTC wall time.
        ingestion_ts::timestamp                                as ingestion_ts,
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
    from stg_oddsapi_odds

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
    -- Snowflake convert_timezone('UTC','America/Los_Angeles', commence_time)::date →
    -- DuckDB AT TIME ZONE chain (commence_time is a naive UTC timestamp).
    (commence_time::timestamp at time zone 'UTC' at time zone 'America/Los_Angeles')::date as commence_date,
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

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_odds_outcomes

{% endif %}
