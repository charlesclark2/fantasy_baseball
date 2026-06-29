-- =============================================================================
-- mart_prediction_clv.sql
-- Grain: one row per (game_pk, model_version, retrain_tag).
-- Purpose: Joins daily_model_predictions to mart_closing_line_value to surface CLV
--          metrics alongside model predictions. (Canonical-row selection:
--          post_lineup > morning, live > backfill, most-recent inserted_at.)
--
-- DuckDB branch (E11.1-W6): daily_model_predictions is a TYPED view over its S3
-- parquet (registered by run_w1_lakehouse.py); mart_closing_line_value is the
-- migrated W6 mart. Snowflake (else) branch is a thin view over the lakehouse_ext
-- external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

predictions_ranked as (
    select
        *,
        row_number() over (
            partition by game_pk, model_version, coalesce(retrain_tag, '')
            order by
                case when prediction_type = 'post_lineup' then 1 else 2 end,
                case when coalesce(is_backfill, false) then 2 else 1 end,
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
        open_vf_over,
        close_vf_over,
        clv_over_prob,
        n_books_with_clv,
        data_source                                                     as clv_data_source,
        close_snapshot_ts
    from mart_closing_line_value
)

select
    -- ── Prediction keys ───────────────────────────────────────────────────────
    p.score_date,
    p.game_pk,
    p.game_date,
    p.model_version,
    p.retrain_tag,
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
    p.over_prob_consensus,
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
    c.open_vf_over,
    c.close_vf_over,
    c.clv_over_prob,
    c.n_books_with_clv,
    c.clv_data_source,
    c.close_snapshot_ts,

    -- ── Serving provenance ────────────────────────────────────────────────────
    p.is_backfill,

    -- ── CLV has data flag ─────────────────────────────────────────────────────
    (c.clv_home_ml is not null)::boolean                                as has_clv

from predictions p
left join clv c
    on  c.game_pk = p.game_pk

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_prediction_clv

{% endif %}
