-- =============================================================================
-- mart_prediction_clv.sql
-- Grain: one row per (prediction_date, game_pk, model_version)
--        — mirrors daily_model_predictions grain.
-- Purpose: Joins daily_model_predictions to mart_closing_line_value to
--          surface CLV metrics alongside model predictions.
--
--          CLV interpretation:
--            clv_home_ml > 0: market moved toward home team winning by close.
--            clv_home_ml < 0: market moved away from home team by close.
--            mean_clv_ml > 0 across all has_odds games: model is consistently
--                ahead of where the market settles (real predictive edge).
--
--          Aggregate CLV metrics for use in Streamlit and evaluation:
--            mean_clv_ml       = AVG(clv_home_ml) WHERE clv_home_ml IS NOT NULL
--            mean_clv_total    = AVG(clv_total)   WHERE clv_total IS NOT NULL
--            pct_positive_clv  = fraction of games where clv_home_ml > 0
-- =============================================================================

{{ config(materialized='table') }}

with

predictions_ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, score_date
            order by
                -- prefer post_lineup (has confirmed lineup features); fall back to morning
                case when prediction_type = 'post_lineup' then 1 else 2 end,
                inserted_at desc
        ) as _rn
    from {{ source('betting_ml', 'daily_model_predictions') }}
),

predictions as (
    select * from predictions_ranked where _rn = 1
),

clv as (
    select
        game_pk,
        game_date,
        open_vf_home,
        close_vf_home,
        clv_home_ml,
        open_total_line,
        close_total_line,
        clv_total,
        n_books_with_clv,
        data_source                                                     as clv_data_source,
        close_snapshot_ts
    from {{ ref('mart_closing_line_value') }}
)

select
    -- ── Prediction keys ───────────────────────────────────────────────────────
    p.score_date,
    p.game_pk,
    p.game_date,
    p.model_version,
    p.prediction_type,
    p.inserted_at                                                       as prediction_inserted_at,
    p.data_source                                                       as prediction_data_source,

    -- ── Game context ──────────────────────────────────────────────────────────
    p.home_team,
    p.away_team,
    p.home_team_abbrev,
    p.away_team_abbrev,
    p.has_odds,
    p.game_datetime,

    -- ── Model predictions ─────────────────────────────────────────────────────
    p.calibrated_win_prob,
    p.consensus_win_prob,
    p.pred_total_runs,
    p.p_over_ngboost,
    p.h2h_market_implied_prob,
    p.h2h_edge,
    p.h2h_kelly_fraction,
    p.total_line_consensus,
    p.totals_model_prob,
    p.totals_edge,
    p.totals_kelly_fraction,

    -- ── CLV metrics (null when no closing snapshot available) ─────────────────
    c.open_vf_home,
    c.close_vf_home,
    c.clv_home_ml,
    c.open_total_line,
    c.close_total_line,
    c.clv_total,
    c.n_books_with_clv,
    c.clv_data_source,
    c.close_snapshot_ts,

    -- ── CLV has data flag ─────────────────────────────────────────────────────
    (c.clv_home_ml is not null)::boolean                                as has_clv

from predictions p
left join clv c
    on  c.game_pk = p.game_pk
