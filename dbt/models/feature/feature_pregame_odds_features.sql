-- =============================================================================
-- feature_pregame_odds_features.sql
-- Grain: one row per game_pk (regular season games only)
-- Purpose: Pre-game betting market features. Integrates pre-game moneyline and
--          totals odds from the selected bookmaker into the Phase 2 feature store.
--
-- Step 0 — Bookmaker selection (analysis run 2026-04-23 against mart_odds_outcomes):
--   Candidates evaluated: all bookmakers with ≥80% coverage in both h2h and totals.
--   Selected: lowvig
--     h2h coverage:    99.3% (3,080 of 3,101 events), median vig 2.33%
--     totals coverage: 98.9% (3,068 of 3,101 events), median vig 3.39%
--   Runner-up betonlineag ties on h2h vig (2.33%) but trails on totals (4.71% vs 3.39%).
--   All other major bookmakers (draftkings, fanduel, bovada, etc.) are ≥4.0% h2h vig.
--   lowvig is the clear winner on both vig metrics.
--
-- Leakage guard: only odds snapshots where ingestion_ts < commence_time are used.
-- The most recent pre-game snapshot per (event_id, market_key, outcome_name) is
-- selected via ROW_NUMBER() ordered by ingestion_ts desc. No same-game-day prices
-- inferred after first pitch are ever included.
--
-- has_odds: inherited from mart_game_odds_bridge — true when an event_id was matched
-- for the game. Does NOT guarantee odds price columns are populated. Card 3 (historical
-- odds backfill) is partial: 2023 (226 events) + live 2026 only. All price columns are
-- null when no pre-game lowvig snapshot exists for an event.
--
-- Vig-adjusted implied probabilities:
--   raw_i = 1.0 / decimal_price_i
--   implied_prob_i = raw_i / sum(raw) → home + away = 1.0, over + under = 1.0
-- =============================================================================

{{ config(materialized='table') }}

with

games as (
    select
        game_pk,
        game_date::date    as game_date,
        game_year::integer as game_year,
        home_team,
        away_team
    from {{ ref('mart_game_results') }}
    where game_type = 'R'
),

bridge as (
    select
        game_pk,
        event_id,
        has_odds
    from {{ ref('mart_game_odds_bridge') }}
),

-- Pre-game lowvig snapshots only (ingestion_ts < commence_time).
-- Dedup to most recent snapshot per outcome so line movement doesn't
-- produce multiple rows. Filtering happens before ROW_NUMBER so the
-- window only ranks pre-game rows.
odds_pre_game as (
    select
        event_id,
        market_key,
        outcome_name,
        ingestion_ts,
        commence_time,
        outcome_price_american,
        outcome_price_decimal,
        outcome_point,
        is_home_outcome,
        is_away_outcome,
        row_number() over (
            partition by event_id, market_key, outcome_name
            order by ingestion_ts desc
        ) as _rn
    from {{ ref('mart_odds_outcomes') }}
    where bookmaker_key = 'lowvig'
      and ingestion_ts < commence_time
),

-- Pivot home and away moneylines into one row per event.
-- SUM(1/decimal) - 1 gives the total overround (vig) on the h2h market.
h2h as (
    select
        event_id,
        max(ingestion_ts)                                               as odds_ingestion_ts,
        max(commence_time)                                              as commence_time,
        max(case when is_home_outcome then outcome_price_american end)  as home_moneyline_american,
        max(case when is_away_outcome then outcome_price_american end)  as away_moneyline_american,
        max(case when is_home_outcome then outcome_price_decimal  end)  as home_moneyline_decimal,
        max(case when is_away_outcome then outcome_price_decimal  end)  as away_moneyline_decimal,
        sum(1.0 / outcome_price_decimal) - 1.0                         as total_market_vig
    from odds_pre_game
    where market_key = 'h2h'
      and _rn = 1
    group by event_id
),

-- Pivot Over and Under into one row per event.
-- outcome_point carries the line (e.g. 8.5); most recent snapshot wins
-- when the line moves during the day.
totals as (
    select
        event_id,
        max(case when outcome_name = 'Over'  then outcome_point          end) as total_line,
        max(case when outcome_name = 'Over'  then outcome_price_american end) as over_american,
        max(case when outcome_name = 'Under' then outcome_price_american end) as under_american,
        max(case when outcome_name = 'Over'  then outcome_price_decimal  end) as over_decimal,
        max(case when outcome_name = 'Under' then outcome_price_decimal  end) as under_decimal,
        sum(1.0 / outcome_price_decimal) - 1.0                               as totals_market_vig
    from odds_pre_game
    where market_key = 'totals'
      and _rn = 1
    group by event_id
)

select

    -- ── Game keys ─────────────────────────────────────────────────────────────
    g.game_pk,
    g.game_date,
    g.game_year,
    g.home_team,
    g.away_team,

    -- ── Odds availability flag ─────────────────────────────────────────────────
    -- true = event_id matched in mart_game_odds_bridge; does not guarantee prices.
    coalesce(b.has_odds, false)::boolean                                as has_odds,

    -- ── Bookmaker metadata ────────────────────────────────────────────────────
    case when b.has_odds then 'lowvig' end                              as odds_bookmaker_key,
    h2h.odds_ingestion_ts,
    case
        when h2h.odds_ingestion_ts is not null
        then datediff('hour', h2h.odds_ingestion_ts, h2h.commence_time)
    end::integer                                                        as odds_hours_before_game,

    -- ── Moneyline (h2h market) ────────────────────────────────────────────────
    h2h.home_moneyline_american,
    h2h.away_moneyline_american,
    h2h.home_moneyline_decimal,
    h2h.away_moneyline_decimal,

    -- ── Vig-adjusted win probabilities ────────────────────────────────────────
    -- home_implied_prob + away_implied_prob = 1.0 by construction
    case
        when h2h.home_moneyline_decimal is not null
         and h2h.away_moneyline_decimal is not null
        then (1.0 / h2h.home_moneyline_decimal)
             / ((1.0 / h2h.home_moneyline_decimal) + (1.0 / h2h.away_moneyline_decimal))
    end::float                                                          as home_implied_prob,

    case
        when h2h.home_moneyline_decimal is not null
         and h2h.away_moneyline_decimal is not null
        then (1.0 / h2h.away_moneyline_decimal)
             / ((1.0 / h2h.home_moneyline_decimal) + (1.0 / h2h.away_moneyline_decimal))
    end::float                                                          as away_implied_prob,

    h2h.total_market_vig,

    -- ── Totals (over/under market) ────────────────────────────────────────────
    totals.total_line,
    totals.over_american,
    totals.under_american,

    -- over_implied_prob + under_implied_prob = 1.0 by construction
    case
        when totals.over_decimal  is not null
         and totals.under_decimal is not null
        then (1.0 / totals.over_decimal)
             / ((1.0 / totals.over_decimal) + (1.0 / totals.under_decimal))
    end::float                                                          as over_implied_prob,

    case
        when totals.over_decimal  is not null
         and totals.under_decimal is not null
        then (1.0 / totals.under_decimal)
             / ((1.0 / totals.over_decimal) + (1.0 / totals.under_decimal))
    end::float                                                          as under_implied_prob,

    totals.totals_market_vig

from games g
left join bridge b  on b.game_pk   = g.game_pk
left join h2h       on h2h.event_id = b.event_id
left join totals    on totals.event_id = b.event_id
