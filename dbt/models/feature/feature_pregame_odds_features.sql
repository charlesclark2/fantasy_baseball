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
-- Source (Story 15.1): feature_pregame_market_features (SCD-2 mart).
--   Replaces direct mart_odds_outcomes query. Reads is_current = TRUE rows,
--   which are equivalent to the prior most-recent-pre-game-snapshot logic.
--   For point-in-time replay use:
--     WHERE valid_from <= :prediction_ts
--       AND (valid_to IS NULL OR valid_to > :prediction_ts)
--
-- has_odds: inherited from mart_game_odds_bridge — true when an event_id was matched
-- for the game. Does NOT guarantee odds price columns are populated. Card 3 (historical
-- odds backfill) is partial: 2023 (226 events) + live 2026 only. All price columns are
-- null when no pre-game lowvig snapshot exists for an event.
--
-- Historical coverage cutoff:
--   Odds API (source_system = 'odds_api'):   2021-01-01 onward
--   Parlay API (source_system = 'parlay_api'): 2026-05-26 onward
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w8a_lakehouse']) }}

with

games as (
    -- A1.11 — spine on mart_game_spine so today's scheduled games get odds
    -- features; historical rows unchanged.
    select
        game_pk,
        game_date::date    as game_date,
        game_year::integer as game_year,
        home_team,
        away_team
    from mart_game_spine
    where game_type = 'R'
),

bridge as (
    select
        game_pk,
        event_id,
        has_odds
    from mart_game_odds_bridge
),

-- Current lowvig h2h snapshot from the SCD-2 market features table.
-- is_current = TRUE is equivalent to the prior "most recent pre-game snapshot"
-- logic. For point-in-time replay, replace with valid_from/valid_to filter.
-- 2026-07-20 rescheduled-game guard: the SCD-2 keys currency PER COMMENCE_TIME, so a
-- postponed→rescheduled game carries a ZOMBIE is_current row at its ORIGINAL slot
-- alongside the makeup's row (2 per market → the ×4 game_pk fan-out in this model +
-- the aggregator; pks 823356/823357/824414). Until the SCD-2 closes superseded-commence
-- rows itself, keep exactly one current row per game: latest commence wins (the makeup),
-- freshest snapshot as tiebreak.
h2h as (
    select
        game_pk,
        valid_from                          as odds_ingestion_ts,
        commence_time,
        home_moneyline_american,
        away_moneyline_american,
        home_moneyline_decimal,
        away_moneyline_decimal,
        home_implied_prob,
        away_implied_prob,
        total_market_vig
    from feature_pregame_market_features
    where bookmaker_key = 'lowvig'
      and market_type   = 'h2h'
      and is_current    = true
    qualify row_number() over (
        partition by game_pk
        order by commence_time desc, valid_from desc
    ) = 1
),

consensus_odds as (
    select * from mart_odds_consensus
),

-- Current lowvig totals snapshot. (Same rescheduled-game zombie-current guard as h2h.)
totals as (
    select
        game_pk,
        total_line,
        over_american,
        under_american,
        over_implied_prob,
        under_implied_prob,
        totals_market_vig
    from feature_pregame_market_features
    where bookmaker_key = 'lowvig'
      and market_type   = 'totals'
      and is_current    = true
    qualify row_number() over (
        partition by game_pk
        order by commence_time desc, valid_from desc
    ) = 1
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

    -- ── Vig-adjusted win probabilities (pre-computed in feature_pregame_market_features)
    h2h.home_implied_prob,
    h2h.away_implied_prob,
    h2h.total_market_vig,

    -- ── Totals (over/under market) ────────────────────────────────────────────
    totals.total_line,
    totals.over_american,
    totals.under_american,
    totals.over_implied_prob,
    totals.under_implied_prob,
    totals.totals_market_vig,

    -- ── Consensus market features (mart_odds_consensus, Card 3.11) ────────────
    -- home_win_prob_consensus: Brier = 0.2395 on 2021–2025 (Card 3.11 benchmark)
    -- Sharp books: lowvig, betonlineag, bovada. Soft: draftkings, fanduel, betmgm,
    -- williamhill_us, betrivers. sharp/soft columns are null when that group has
    -- no pre-game coverage for this event; not recommended as primary training
    -- features (include_sharp_soft_features = False per Card 3.11).
    con.home_win_prob_consensus,
    con.home_win_prob_sharp,
    con.home_win_prob_soft,
    con.sharp_soft_ml_delta,
    con.ml_consensus_std,
    con.market_bookmaker_count,
    con.total_line_consensus,
    con.total_line_std,
    con.over_prob_consensus

from games g
left join bridge b       on b.game_pk  = g.game_pk
left join h2h            on h2h.game_pk = g.game_pk
left join totals         on totals.game_pk = g.game_pk
left join consensus_odds con on con.event_id = b.event_id

{% else %}

{{ config(materialized='table') }}

select * from baseball_data.lakehouse_ext.feature_pregame_odds_features

{% endif %}
