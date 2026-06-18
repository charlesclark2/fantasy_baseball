-- =============================================================================
-- mart_derivative_closes.sql
-- Grain: one row per (game_pk, market_key, bookmaker_key, outcome_name)
-- Purpose: Closing derivative-market odds (team totals, alternate totals,
--          first-5-innings / first-half totals and moneyline) for MLB games.
--          "Closing" = the last pre-game snapshot in derivative_odds_raw
--          (actual_snapshot_ts <= commence_time).
--
-- ⚠️  EVAL/CLV-ONLY — for E2.6 derivative gate validation and CLV measurement.
--     Must NEVER be joined into model training feature matrices
--     (market-blind constraint, Edge Program §0.1 Principle 3).
--
-- Coverage: 2023-05-03 → present (Odds API additional-market history limit).
-- Source:   stg_derivative_odds (from scripts/derivative_odds_backfill.py E2.0)
-- Join:     event_id → mart_game_odds_bridge → game_pk
--
-- Markets:
--   team_totals      — team run total (outcome_description = team name; outcome_point = line)
--   alternate_totals — alternate full-game total lines
--   h2h_h1           — F5 moneyline (innings 1–5)
--   totals_h1        — F5 run total over/under
-- =============================================================================

{{
    config(
        materialized='table'
    )
}}

with derivative_odds as (

    select
        event_id,
        commence_time,
        home_team,
        away_team,
        actual_snapshot_ts,
        bookmaker_key,
        bookmaker_title,
        market_key,
        outcome_name,
        outcome_description,
        outcome_price_american,
        outcome_price_decimal,
        outcome_point,
        -- rank snapshots newest-first within pre-game window
        row_number() over (
            partition by event_id, market_key, bookmaker_key, outcome_name
            order by actual_snapshot_ts desc
        ) as snap_rank
    from {{ ref('stg_derivative_odds') }}
    -- leakage guard: only pre-game snapshots count as "closing"
    where actual_snapshot_ts <= commence_time

),

closing as (

    select *
    from derivative_odds
    where snap_rank = 1

),

-- Resolve event_id → game_pk via the existing bridge.
-- Bridge stores both the Odds API event_id (2023-2025 backfill) and the
-- Parlay API event_id (2026+); join on whichever is non-null.
game_bridge as (

    select
        game_pk,
        odds_api_event_id,
        parlay_api_event_id
    from {{ ref('mart_game_odds_bridge') }}
    where game_pk is not null

)

select
    -- Game identity
    b.game_pk,
    c.event_id,
    c.commence_time,
    c.home_team,
    c.away_team,

    -- Closing snapshot metadata
    c.actual_snapshot_ts                    as close_snapshot_ts,

    -- Bookmaker
    c.bookmaker_key,
    c.bookmaker_title,

    -- Market
    c.market_key,

    -- Outcome
    c.outcome_name,
    -- description carries the team name for team_totals; null for other markets
    c.outcome_description,
    c.outcome_price_american,
    c.outcome_price_decimal,
    -- line (Over/Under point for totals markets; null for h2h_h1)
    c.outcome_point,

    -- Convenience: is_over flag for totals markets
    case
        when c.market_key in ('team_totals', 'alternate_totals', 'totals_h1')
         and lower(c.outcome_name) = 'over'
            then true
        when c.market_key in ('team_totals', 'alternate_totals', 'totals_h1')
         and lower(c.outcome_name) = 'under'
            then false
        else null
    end::boolean                            as is_over,

    -- De-vigged implied probability (standard two-way de-vig)
    -- Used by E2.6 CLV calculation: model_prob vs this close_implied_prob
    case
        when c.outcome_price_decimal is not null and c.outcome_price_decimal > 1.0
            then 1.0 / c.outcome_price_decimal
        else null
    end::float                              as raw_implied_prob

from closing c
inner join game_bridge b
    on (
        c.event_id = b.odds_api_event_id
        or c.event_id = b.parlay_api_event_id
    )
