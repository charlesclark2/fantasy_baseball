-- =============================================================================
-- mart_pitcher_batter_history.sql
-- Grain: one row per (pitcher_id, batter_id, game_date)
-- Purpose: Per-game plate-appearance aggregates between each pitcher-batter pair.
--          Source for the head-to-head (H2H) historical wOBA / xwOBA features
--          (Card 8.J). Bayesian shrinkage and the leakage guard
--          (game_date < prediction_date) are applied at the feature join layer
--          in feature_pitcher_batter_h2h_matchups, not here.
--
-- Column notes:
--   pa_count        Number of plate appearances between the pair on this date.
--   woba_value_sum  Sum of woba_value across those PA (numerator for wOBA).
--   woba_denom_sum  Sum of woba_denom across those PA (denominator for wOBA;
--                   excludes IBB and similar non-counting events).
--   xwoba_sum       Sum of xwOBA across PA where xwOBA is observed.
--   xwoba_obs       Count of PA with non-null xwOBA (denominator for AVG xwOBA).
-- =============================================================================

{{ config(materialized='table') }}

with pa_events as (
    select
        pitcher_id,
        batter_id,
        game_date::date     as game_date,
        woba_value,
        woba_denom,
        xwoba
    from {{ ref('mart_pitch_play_event') }}
    where is_terminal_pitch = true
      and pitcher_id is not null
      and batter_id  is not null
)

select
    pitcher_id,
    batter_id,
    game_date,
    count(*)                                                            as pa_count,
    sum(coalesce(woba_value, 0))                                        as woba_value_sum,
    sum(coalesce(woba_denom, 0))                                        as woba_denom_sum,
    sum(case when xwoba is not null then xwoba else 0 end)              as xwoba_sum,
    sum(case when xwoba is not null then 1 else 0 end)                  as xwoba_obs
from pa_events
group by pitcher_id, batter_id, game_date
