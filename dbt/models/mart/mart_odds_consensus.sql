-- =============================================================================
-- mart_odds_consensus.sql
-- Grain: one row per event_id
-- Purpose: Pre-game bookmaker consensus aggregation across all bookmakers.
--          Computes consensus, sharp, and soft vig-adjusted implied probabilities
--          for the home team moneyline, plus consensus totals line and over
--          probability.
--
-- Leakage guard: only bookmaker_last_update < commence_time snapshots included.
-- Sharp books (Card 3.11): lowvig, betonlineag, bovada.
-- Soft books (Card 3.11): draftkings, fanduel, betmgm, williamhill_us, betrivers.
--
-- DuckDB branch (E11.1-W6): reads the migrated mart_odds_outcomes; Snowflake (else)
-- branch is a thin view over the lakehouse_ext external table. iff()/count_if() are
-- reimplemented with CASE / count(*) FILTER for DuckDB.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

pre_game_snapshots as (
    select *
    from mart_odds_outcomes
    where bookmaker_last_update < commence_time
),

latest_per_book as (
    select *
    from pre_game_snapshots
    qualify row_number() over (
        partition by event_id, bookmaker_key, market_key, outcome_name
        order by ingestion_ts desc
    ) = 1
),

-- ── H2H (moneyline) — one row per event × bookmaker ──────────────────────────

h2h_per_book as (
    select
        event_id,
        bookmaker_key,
        max(case when is_home_outcome then outcome_price_american end) as home_price,
        max(case when is_away_outcome then outcome_price_american end) as away_price,
        bookmaker_key in ('lowvig', 'betonlineag', 'bovada')          as is_sharp,
        bookmaker_key in ('draftkings', 'fanduel', 'betmgm',
                          'williamhill_us', 'betrivers')              as is_soft
    from latest_per_book
    where market_key = 'h2h'
    group by event_id, bookmaker_key
),

h2h_vig_adjusted as (
    select
        event_id,
        bookmaker_key,
        is_sharp,
        is_soft,
        (case when home_price < 0
              then abs(home_price) / (abs(home_price) + 100.0)
              else 100.0 / (home_price + 100.0)
         end)
        / nullif(
            (case when home_price < 0
                  then abs(home_price) / (abs(home_price) + 100.0)
                  else 100.0 / (home_price + 100.0)
             end)
            +
            (case when away_price < 0
                  then abs(away_price) / (abs(away_price) + 100.0)
                  else 100.0 / (away_price + 100.0)
             end)
        , 0)                                                          as home_imp
    from h2h_per_book
    where home_price is not null
      and away_price is not null
),

-- ── Totals (over/under) — one row per event × bookmaker ──────────────────────

totals_per_book as (
    select
        event_id,
        bookmaker_key,
        max(outcome_point)                                                    as total_line,
        max(case when outcome_name = 'Over'  then outcome_price_american end) as over_price,
        max(case when outcome_name = 'Under' then outcome_price_american end) as under_price
    from latest_per_book
    where market_key = 'totals'
    group by event_id, bookmaker_key
),

totals_vig_adjusted as (
    select
        event_id,
        bookmaker_key,
        total_line,
        (case when over_price < 0
              then abs(over_price) / (abs(over_price) + 100.0)
              else 100.0 / (over_price + 100.0)
         end)
        / nullif(
            (case when over_price < 0
                  then abs(over_price) / (abs(over_price) + 100.0)
                  else 100.0 / (over_price + 100.0)
             end)
            +
            (case when under_price < 0
                  then abs(under_price) / (abs(under_price) + 100.0)
                  else 100.0 / (under_price + 100.0)
             end)
        , 0)                                                                  as over_imp
    from totals_per_book
    where over_price  is not null
      and under_price is not null
),

-- ── Consensus aggregation ─────────────────────────────────────────────────────

h2h_consensus as (
    select
        event_id,
        avg(home_imp)::double                                              as home_win_prob_consensus,
        case when count(*) filter (where is_sharp) > 0
             then avg(case when is_sharp then home_imp end)::double end    as home_win_prob_sharp,
        case when count(*) filter (where is_soft) > 0
             then avg(case when is_soft  then home_imp end)::double end    as home_win_prob_soft,
        case when count(*) filter (where is_sharp) > 0
              and count(*) filter (where is_soft) > 0
             then (avg(case when is_sharp then home_imp end)
                   - avg(case when is_soft  then home_imp end))::double end as sharp_soft_ml_delta,
        nullif(stddev(home_imp), 0)::double                                as ml_consensus_std,
        count(bookmaker_key)::integer                                     as market_bookmaker_count
    from h2h_vig_adjusted
    group by event_id
),

totals_consensus as (
    select
        event_id,
        avg(total_line)::double                                            as total_line_consensus,
        nullif(stddev(total_line), 0)::double                              as total_line_std,
        avg(over_imp)::double                                              as over_prob_consensus,
        count(bookmaker_key)::integer                                     as totals_bookmaker_count
    from totals_vig_adjusted
    group by event_id
)

select
    h.event_id,
    h.home_win_prob_consensus,
    h.home_win_prob_sharp,
    h.home_win_prob_soft,
    h.sharp_soft_ml_delta,
    h.ml_consensus_std,
    h.market_bookmaker_count,
    t.total_line_consensus,
    t.total_line_std,
    t.over_prob_consensus,
    t.totals_bookmaker_count
from h2h_consensus h
left join totals_consensus t
    on t.event_id = h.event_id

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_odds_consensus

{% endif %}
