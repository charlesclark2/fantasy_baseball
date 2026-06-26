-- =============================================================================
-- mart_pitcher_batter_history.sql   (E11.1-W2 lakehouse decommission)
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
--
-- E11.1-W2: dual-branch lakehouse model. Upstream mart_pitch_play_event is a W1
-- lakehouse parquet — run_w1_lakehouse.py registers it as a view before this
-- model builds (plain table name in the duckdb branch resolves to that view).
-- =============================================================================

{{
    config(
        materialized = 'view',
        tags         = ['w2_lakehouse']
    )
}}

{% if target.name == 'duckdb' %}

-- ⚠️ E11.1-W2 BUG FIX: this model previously read woba_value/woba_denom/xwoba from
-- mart_pitch_play_event — but W1d's duckdb branch of that mart DROPPED those columns
-- (its external table still DECLARES them, so Snowflake silently read NULL). Result:
-- since W1d (2026-06-25) every woba_value_sum/woba_denom_sum/xwoba_sum/xwoba_obs in
-- this table was 0 (verified: 0/1,229,704 rows nonzero), zeroing the H2H matchup
-- features. The woba columns live in stg_batter_pitches (full-PA, incl. K/BB), so we
-- source directly from there. is_terminal_pitch = (plate_appearance_event is not null),
-- so the PA grain (and pa_count) is unchanged — only the woba columns become REAL.
with pa_events as (
    select
        pitcher_id,
        batter_id,
        game_date::date     as game_date,
        woba_value,
        woba_denom,
        xwoba
    from stg_batter_pitches
    where plate_appearance_event is not null   -- = mart_pitch_play_event.is_terminal_pitch
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

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitcher_batter_history

{% endif %}
