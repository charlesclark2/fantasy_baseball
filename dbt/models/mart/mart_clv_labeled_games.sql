-- =============================================================================
-- mart_clv_labeled_games.sql
-- Grain: one row per (game_pk, market_type) where market_type ∈ {h2h, totals}
--
-- Purpose: Canonical source of CLV-labeled games for the Epic 12 meta-model.
--          Only materializes rows meeting all four CLV label conditions:
--            1. A live pre-game prediction exists (morning or post_lineup)
--            2. Opening market price exists (open_vf_home / open_vf_over)
--            3. Closing market price exists (close_vf_home / close_vf_over)
--            4. Game result exists (home_team_won IS NOT NULL)
--
--          This is the gate-threshold tracker referenced by all Epic 12 stories.
--          "50 CLV-labeled games" means 50 distinct game_pk values in this mart.
--
-- Prediction selection: one canonical prediction per game_pk, preferring
--          post_lineup over morning, then latest inserted_at as tiebreaker.
--          Backfill and null prediction_type rows are excluded — only real-time
--          pre-game predictions represent bets we could have placed.
--
-- CLV direction: clv and clv_positive are always measured from the home/over
--          perspective (consistent with mart_closing_line_value). Use model_edge
--          to determine the direction of the actual bet for meta-model training.
--
-- Sources:
--   Predictions: betting_ml.daily_model_predictions (2026-05-10+, live only)
--   Lines:       mart_closing_line_value
--   Results:     mart_game_results
-- =============================================================================

{{ config(materialized='table') }}

with

-- One canonical pre-game prediction per game: post_lineup > morning, latest wins
best_prediction as (
    select
        *,
        row_number() over (
            partition by game_pk
            order by
                case when prediction_type = 'post_lineup' then 1 else 2 end,
                inserted_at desc
        ) as _rn
    from {{ source('betting_ml', 'daily_model_predictions') }}
    where prediction_type in ('morning', 'post_lineup')
),

predictions as (
    select * from best_prediction where _rn = 1
),

clv as (
    select * from {{ ref('mart_closing_line_value') }}
),

results as (
    select * from {{ ref('mart_game_results') }}
),

-- H2H labeled rows: one row per game where all four h2h label conditions are met
h2h_rows as (
    select
        p.game_pk,
        p.game_date,
        'h2h'                                                           as market_type,
        p.inserted_at                                                   as predicted_at,
        -- In the current system, bet execution and prediction happen together
        p.inserted_at                                                   as bet_execution_price_timestamp,
        c.close_snapshot_ts                                             as closing_price_timestamp,
        c.open_vf_home                                                  as bovada_open_devig_prob,
        c.close_vf_home                                                 as bovada_close_devig_prob,
        p.consensus_win_prob                                            as model_prob,
        p.h2h_edge                                                      as model_edge,
        -- clv = close − open of the devig probs (schema definition). Source
        -- mart_closing_line_value.clv_home_ml is avg(per-book close−open) and can be
        -- NULL when no single book carried BOTH an open and close price even though the
        -- avg open/close (guaranteed non-null by the WHERE) are present; fall back to
        -- close−open of those displayed probs so the not_null label contract holds.
        coalesce(c.clv_home_ml, c.close_vf_home - c.open_vf_home)        as clv,
        (coalesce(c.clv_home_ml, c.close_vf_home - c.open_vf_home) > 0)::boolean as clv_positive,
        -- actual_outcome = 1 if home team won (consistent with home-perspective CLV)
        r.home_team_won::integer                                        as actual_outcome
    from predictions p
    inner join clv c
        on  c.game_pk = p.game_pk
    inner join results r
        on  r.game_pk = p.game_pk
    where p.consensus_win_prob  is not null
      and c.open_vf_home        is not null
      and c.close_vf_home       is not null
      and r.home_team_won       is not null
),

-- Totals labeled rows: one row per game where all four totals label conditions are met
totals_rows as (
    select
        p.game_pk,
        p.game_date,
        'totals'                                                        as market_type,
        p.inserted_at                                                   as predicted_at,
        p.inserted_at                                                   as bet_execution_price_timestamp,
        c.close_snapshot_ts                                             as closing_price_timestamp,
        c.open_vf_over                                                  as bovada_open_devig_prob,
        c.close_vf_over                                                 as bovada_close_devig_prob,
        p.totals_model_prob                                             as model_prob,
        p.totals_edge                                                   as model_edge,
        -- See h2h note: clv_over_prob (avg per-book close−open) is NULL when no single
        -- book carried both an open and close over-price; fall back to close−open of the
        -- displayed avg devig probs (non-null by the WHERE) so the not_null test holds.
        -- (2026-06-10 had 2 such totals games — the catchup_dbt_rebuild test failure.)
        coalesce(c.clv_over_prob, c.close_vf_over - c.open_vf_over)      as clv,
        (coalesce(c.clv_over_prob, c.close_vf_over - c.open_vf_over) > 0)::boolean as clv_positive,
        -- actual_outcome = 1 if total runs exceeded the opening total line (over won)
        case
            when r.home_final_score + r.away_final_score > c.open_total_line then 1
            else 0
        end                                                             as actual_outcome
    from predictions p
    inner join clv c
        on  c.game_pk = p.game_pk
    inner join results r
        on  r.game_pk = p.game_pk
    where p.totals_model_prob   is not null
      and c.open_vf_over        is not null
      and c.close_vf_over       is not null
      and r.home_team_won       is not null
      and c.open_total_line     is not null
),

final as (
    select * from h2h_rows
    union all
    select * from totals_rows
)

select * from final
