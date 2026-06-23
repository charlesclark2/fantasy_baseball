{{
    config(
        materialized='table'
    )
}}

-- Grain: pitcher_id × game_year (season). One row per pitcher per season.
--
-- Edge Program Story E13.4 — Candidate B1 (times-through-order penalty).
-- The dossier's #1 ranked gap: `pitcher_times_thru_order` exists raw in stg_batter_pitches
-- but feeds ZERO pre-game feature. This mart splits a pitcher's xwOBA-against by how many
-- times he has faced the batting order in a game (1st time vs 3rd+ time), so a downstream
-- feature can carry the *fade* (3rd-time penalty) the market under-prices vs the pitcher's
-- season average.
--
-- xwOBA-against convention MIRRORS mart_pitcher_rolling_stats: sum(xwoba) / count(xwoba),
-- where xwoba = estimated_woba_using_speedangle. batters faced (`*_bf`) counts PA-ending
-- events (woba_denom > 0) and backs the downstream empirical-Bayes shrinkage.
--
-- ⚠️ SNOWFLAKE CAST GOTCHA (the bug that silently zeroed this whole feature, 2026-06-23):
-- the ratio casts below use `::number(18,6)`, NOT bare `::numeric`. In Snowflake
-- `::numeric` == `::number(38,0)` == scale 0, so `(0.2965)::numeric` ROUNDS TO THE INTEGER 0
-- *before* `round(...,4)` runs — every xwOBA-against materialized as 0 (and the per-pitcher
-- penalty likewise, except the rare |diff|>=0.5 pitcher rounding to ±1, which produced the
-- tell-tale tiny-but-nonzero season means). Always give an explicit scale when casting a
-- fractional ratio. The assert_tto_splits_xwoba_not_zeroed singular test guards the regression.
--
-- LEAK SAFETY: per-season aggregate — consumers MUST join on the PRIOR season (game_year - 1),
-- like mart_pitcher_vs_handedness_splits. Regular season only (game_type = 'R').
--
-- NOTE (cost): EVAL-ONLY candidate (gated by the E13.4 lift-test). Materialized as a `table`
-- like the analogous handedness-splits mart; if B1 promotes, consider a season-incremental
-- rebuild to avoid re-scanning the full pitch table on every build.

with pitches as (
    select
        pitcher_id,
        game_year,
        pitcher_times_thru_order,
        xwoba,
        woba_denom
    from {{ ref('stg_batter_pitches') }}
    where game_type = 'R'
      and pitcher_times_thru_order is not null
),

-- 1st time through the order (pre-filtered → plain aggregates only)
tto1 as (
    select
        pitcher_id,
        game_year                                   as season,
        sum(xwoba)                                  as xwoba_sum,
        count(xwoba)                                as xwoba_n,
        count(case when woba_denom > 0 then 1 end)  as bf
    from pitches
    where pitcher_times_thru_order = 1
    group by pitcher_id, game_year
),

-- 3rd+ time through the order — the fade window (pre-filtered → plain aggregates only)
tto3 as (
    select
        pitcher_id,
        game_year                                   as season,
        sum(xwoba)                                  as xwoba_sum,
        count(xwoba)                                as xwoba_n,
        count(case when woba_denom > 0 then 1 end)  as bf
    from pitches
    where pitcher_times_thru_order >= 3
    group by pitcher_id, game_year
)

select
    t1.pitcher_id,
    t1.season,
    t1.bf                                                                   as tto1_bf,
    t3.bf                                                                   as tto3_bf,
    least(t1.bf, t3.bf)                                                     as tto_min_bf,
    round((t1.xwoba_sum / nullif(t1.xwoba_n, 0))::number(18,6), 4)          as tto1_xwoba_against,
    round((t3.xwoba_sum / nullif(t3.xwoba_n, 0))::number(18,6), 4)          as tto3_xwoba_against,
    -- the penalty: 3rd-time xwOBA-against minus 1st-time. Positive = the pitcher fades
    -- the deeper he goes into the order.
    round(
        ((t3.xwoba_sum / nullif(t3.xwoba_n, 0))
         - (t1.xwoba_sum / nullif(t1.xwoba_n, 0)))::number(18,6), 4
    )                                                                      as tto3_xwoba_penalty
-- inner join → keep only pitcher-seasons with BOTH buckets measurable
from tto1 t1
inner join tto3 t3
    on  t1.pitcher_id = t3.pitcher_id
    and t1.season     = t3.season
where t1.xwoba_n > 0
  and t3.xwoba_n > 0
