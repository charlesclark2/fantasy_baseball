{{
    config(
        materialized = 'incremental',
        unique_key   = ['batter_cluster_id', 'pitcher_cluster_id', 'game_date']
    )
}}

-- Grain: batter_cluster_id × pitcher_cluster_id × game_date (anchor)
-- Population-level rolling wOBA for each batter-archetype × pitcher-archetype pairing.
--
-- Purpose: Because this is a population summary (all batters of archetype X vs. all pitchers
-- of cluster Y), it is stable even for rare individual matchups and provides a strong prior
-- for lineups with thin per-batter PA history vs. a specific cluster.
--
-- Leakage guards (both applied):
--   - batter_clusters joined on game_year - 1 = season (prior-season batter archetype)
--   - pitcher_clusters joined on game_year - 1 = season (prior-season pitcher archetype)
-- This prevents in-season cluster assignments from leaking into PA events used to build
-- the population stat.
--
-- Rolling window: 180-day preceding (wider than per-batter mart; population stats are more
-- stable and benefit from the larger sample without meaningful time drift).
--
-- Shrinkage toward league average (wOBA=0.320, xwOBA=0.315):
--   weight = pa_count / (pa_count + 100)   [higher prior weight than per-batter due to
--   population grain already pooling many individual batters]
--
-- Availability: cluster data begins 2020 (prior-season lag → effective from 2021 games).
-- Gate: only emit rows where pa_count >= 50 (population min PA for the pairing).

with
{% if is_incremental() %}
max_anchor as (
    select max(game_date) as max_date from {{ this }}
),
{% endif %}

-- PA events tagged with (batter_cluster_id, pitcher_cluster_id, game_date)
-- using prior-season cluster assignments for both sides (leakage guard).
pa_events as (
    select
        ppe.game_date,
        ppe.game_year,
        bc.cluster_id   as batter_cluster_id,
        pc.cluster_id   as pitcher_cluster_id,
        ppe.woba_value,
        ppe.woba_denom,
        ppe.xwoba
    from {{ ref('mart_pitch_play_event') }} ppe
    -- Batter archetype: join prior-season batter cluster (game_year - 1 = season)
    join {{ source('statsapi', 'batter_clusters') }} bc
        on  bc.batter_id = ppe.batter_id
        and bc.season    = ppe.game_year - 1
    -- Pitcher archetype: join prior-season pitcher cluster (game_year - 1 = season)
    -- Use the latest snapshot for the prior season to get a stable full-season assignment.
    join (
        select pitcher_id, season, cluster_id,
               row_number() over (
                   partition by pitcher_id, season
                   order by snapshot_date desc
               ) as rn
        from {{ source('statsapi', 'pitcher_clusters') }}
    ) pc
        on  pc.pitcher_id = ppe.pitcher_id
        and pc.season     = ppe.game_year - 1
        and pc.rn         = 1
    where ppe.plate_appearance_event is not null
      and ppe.game_year >= 2021
    {% if is_incremental() %}
      and ppe.game_date > (select max_date from max_anchor)
    {% endif %}
),

-- Step 1: Daily PA aggregation per (batter_cluster_id, pitcher_cluster_id, game_date)
daily_pa as (
    select
        batter_cluster_id,
        pitcher_cluster_id,
        game_date,
        count(*)            as daily_pa,
        sum(woba_value)     as daily_woba_sum,
        sum(woba_denom)     as daily_woba_denom,
        avg(xwoba)          as daily_xwoba
    from pa_events
    group by 1, 2, 3
),

-- Step 2: 180-day rolling window through game_date - 1 (no same-day leakage)
rolling as (
    select
        batter_cluster_id,
        pitcher_cluster_id,
        game_date,
        sum(daily_pa) over (
            partition by batter_cluster_id, pitcher_cluster_id
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                   as pa_count,
        sum(daily_woba_sum) over (
            partition by batter_cluster_id, pitcher_cluster_id
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                   as woba_sum,
        sum(daily_woba_denom) over (
            partition by batter_cluster_id, pitcher_cluster_id
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                   as woba_denom_sum,
        avg(daily_xwoba) over (
            partition by batter_cluster_id, pitcher_cluster_id
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                   as raw_xwoba
    from daily_pa
),

-- Step 3: Shrinkage toward league average; gate at min 50 PA
with_shrinkage as (
    select
        batter_cluster_id,
        pitcher_cluster_id,
        game_date,
        pa_count,
        round(
            woba_sum / nullif(woba_denom_sum, 0),
            3
        )                   as raw_woba,
        round(raw_xwoba, 3) as raw_xwoba,
        pa_count / (pa_count + 100.0) as shrink_weight,
        round(
            (pa_count / (pa_count + 100.0)) * coalesce(woba_sum / nullif(woba_denom_sum, 0), 0.320)
            + (1 - pa_count / (pa_count + 100.0)) * 0.320,
            3
        )                   as adj_woba,
        round(
            (pa_count / (pa_count + 100.0)) * coalesce(raw_xwoba, 0.315)
            + (1 - pa_count / (pa_count + 100.0)) * 0.315,
            3
        )                   as adj_xwoba
    from rolling
    where pa_count >= 50
)

select * from with_shrinkage
