-- =============================================================================
-- mart_clv_labeled_games.sql
-- Grain: one row per (game_pk, market_type) where market_type ∈ {h2h, totals}
-- Purpose: Canonical source of CLV-labeled games for the Epic 12 meta-model.
--          Only materializes rows meeting all four CLV label conditions.
--          Prediction selection: one canonical v6 champion prediction per game_pk.
--
-- ⚠️ SERVING-COUPLED (E11.1-W6): the /performance page reads this at request time
-- (Snowflake FALLBACK behind the DynamoDB cache). Value-identical parity required.
--
-- Sources:
--   Predictions: betting_ml.daily_model_predictions (2026-05-10+, live only)
--   Lines:       mart_closing_line_value
--   Results:     mart_game_results
--
-- DuckDB branch (E11.1-W6): daily_model_predictions is a TYPED view over its S3
-- parquet (registered by run_w1_lakehouse.py); mart_closing_line_value /
-- mart_game_results are migrated W6/W5 marts. Snowflake (else) branch is a thin view
-- over the lakehouse_ext external table.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

with

-- One canonical pre-game prediction per game: post_lineup > morning, live > backfill,
-- latest wins. Pinned to the production champion model_version (E13.11: 'v6').
best_prediction as (
    select
        *,
        row_number() over (
            partition by game_pk
            order by
                case when prediction_type = 'post_lineup' then 1 else 2 end,
                case when coalesce(is_backfill, false) then 2 else 1 end,
                inserted_at desc
        ) as _rn
    from {{ source('betting_ml', 'daily_model_predictions') }}
    where prediction_type in ('morning', 'post_lineup')
      and model_version = 'v6'
),

predictions as (
    select * from best_prediction where _rn = 1
),

clv as (
    select * from mart_closing_line_value
),

results as (
    select * from mart_game_results
),

-- H2H labeled rows
h2h_rows as (
    select
        p.game_pk,
        p.game_date,
        'h2h'                                                           as market_type,
        p.inserted_at                                                   as predicted_at,
        p.inserted_at                                                   as bet_execution_price_timestamp,
        c.close_snapshot_ts                                             as closing_price_timestamp,
        c.open_vf_home                                                  as bovada_open_devig_prob,
        c.close_vf_home                                                 as bovada_close_devig_prob,
        p.consensus_win_prob                                            as model_prob,
        p.h2h_edge                                                      as model_edge,
        coalesce(c.clv_home_ml, c.close_vf_home - c.open_vf_home)        as clv,
        (coalesce(c.clv_home_ml, c.close_vf_home - c.open_vf_home) > 0)::boolean as clv_positive,
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

-- Totals labeled rows
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
        coalesce(c.clv_over_prob, c.close_vf_over - c.open_vf_over)      as clv,
        (coalesce(c.clv_over_prob, c.close_vf_over - c.open_vf_over) > 0)::boolean as clv_positive,
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

{% else %}

{{ config(materialized='view', tags=['w6_lakehouse']) }}

select * from baseball_data.lakehouse_ext.mart_clv_labeled_games

{% endif %}
