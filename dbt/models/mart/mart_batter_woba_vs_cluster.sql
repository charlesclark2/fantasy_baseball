{{
    config(
        materialized = 'table',
        unique_key   = "batter_id || '~' || cluster_id::varchar || '~' || game_date::varchar"
    )
}}

-- Grain: batter_id × cluster_id × game_date
-- Career-cumulative wOBA per batter vs. each pitcher cluster, through game_date - 1.
-- Leakage guard: window uses UNBOUNDED PRECEDING to interval '1 day' preceding.
-- Shrinkage toward league average for small samples (prior 30 PA).
-- Gate: only emit rows where pa_count >= 10 (min PA vs. a cluster).
--
-- Availability: cluster data begins 2015; game_year >= 2016 rows are populated
-- (prior-season join: game_year - 1 = season in pitcher_clusters).
-- Full table refresh required (career cumulative cannot be computed incrementally).
--
-- Leakage guard: pitcher cluster joined on prior-season assignment
-- (pc.season = game_year - 1). PK on pitcher_clusters is (pitcher_id, season) —
-- one row per pair, no deduplication needed.

with pa_with_clusters as (
    select
        ppe.batter_id,
        ppe.game_date,
        ppe.game_year,
        ppe.woba_value,
        ppe.woba_denom,
        ppe.xwoba,
        pc.cluster_id
    from {{ ref('mart_pitch_play_event') }} ppe
    left join {{ source('statsapi', 'pitcher_clusters') }} pc
        on  pc.pitcher_id = ppe.pitcher_id
        and pc.season     = ppe.game_year - 1
    where ppe.plate_appearance_event is not null
      and ppe.game_year >= 2016
      and pc.cluster_id is not null
),

-- Step 1: Daily PA aggregation to make rolling windows efficient
daily_pa as (
    select
        batter_id,
        cluster_id,
        game_date,
        count(*)            as daily_pa,
        sum(woba_value)     as daily_woba_sum,
        sum(woba_denom)     as daily_woba_denom,
        avg(xwoba)          as daily_xwoba
    from pa_with_clusters
    group by 1, 2, 3
),

-- Step 2: Career-cumulative window through the day before each game_date
rolling as (
    select
        batter_id,
        cluster_id,
        game_date,
        sum(daily_pa) over (
            partition by batter_id, cluster_id
            order by game_date
            range between unbounded preceding and interval '1 day' preceding
        )                   as pa_count,
        sum(daily_woba_sum) over (
            partition by batter_id, cluster_id
            order by game_date
            range between unbounded preceding and interval '1 day' preceding
        )                   as woba_sum,
        sum(daily_woba_denom) over (
            partition by batter_id, cluster_id
            order by game_date
            range between unbounded preceding and interval '1 day' preceding
        )                   as woba_denom_sum,
        avg(daily_xwoba) over (
            partition by batter_id, cluster_id
            order by game_date
            range between unbounded preceding and interval '1 day' preceding
        )                   as raw_xwoba
    from daily_pa
),

-- Step 3: Shrinkage toward league average; gate at min 10 PA
with_shrinkage as (
    select
        batter_id,
        cluster_id,
        game_date,
        pa_count,
        round(
            woba_sum / nullif(woba_denom_sum, 0),
            3
        )                   as raw_woba,
        round(raw_xwoba, 3) as raw_xwoba,
        pa_count / (pa_count + 30.0) as shrink_weight,
        round(
            (pa_count / (pa_count + 30.0)) * coalesce(woba_sum / nullif(woba_denom_sum, 0), 0.320)
            + (1 - pa_count / (pa_count + 30.0)) * 0.320,
            3
        )                   as adj_woba,
        round(
            (pa_count / (pa_count + 30.0)) * coalesce(raw_xwoba, 0.315)
            + (1 - pa_count / (pa_count + 30.0)) * 0.315,
            3
        )                   as adj_xwoba
    from rolling
    where pa_count >= 10
)

select * from with_shrinkage
