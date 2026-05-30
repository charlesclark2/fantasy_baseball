{{
    config(
        materialized = 'incremental',
        unique_key   = ['batter_cluster_label', 'pitcher_cluster_label', 'game_date']
    )
}}

-- Grain: batter_cluster_label × pitcher_cluster_label × game_date (anchor)
-- Population-level rolling soft-weighted wOBA for each batter-archetype × pitcher-archetype pair.
--
-- Soft-assignment weighting (Epic 7A.3):
--   Each PA contributes fractionally to all 25 cells with weight p_batter_b × p_pitcher_p,
--   drawn from mart_player_archetype_posteriors using the latest snapshot before game_date.
--   pa_weight (sum of joint weights in 180-day window) replaces the old hard pa_count.
--
-- Leakage guard: posteriors joined on as_of_date < game_date (strict less-than).
--
-- Rolling window: 180-day preceding (population stats benefit from larger sample).
--
-- Shrinkage toward league average (wOBA=0.320, xwOBA=0.315):
--   shrink_weight = pa_weight / (pa_weight + 100)
--
-- Gate: emit rows where pa_weight >= 50.
-- Availability: posteriors begin 2021; effective from 2021 games.

with
{% if is_incremental() %}
max_anchor as (
    select max(game_date) as max_date from {{ this }}
),
{% endif %}

pa_events as (
    select
        ppe.game_date,
        ppe.game_year,
        ppe.batter_id,
        ppe.pitcher_id,
        ppe.woba_value,
        ppe.woba_denom,
        ppe.xwoba
    from {{ ref('mart_pitch_play_event') }} ppe
    where ppe.plate_appearance_event is not null
      and ppe.game_year >= 2021
    {% if is_incremental() %}
      and ppe.game_date > (select max_date from max_anchor)
    {% endif %}
),

pa_batter_dates as (
    select distinct batter_id, game_date, game_year from pa_events
),

pa_pitcher_dates as (
    select distinct pitcher_id, game_date, game_year from pa_events
),

-- Latest batter posterior as_of_date strictly before each game_date in window
batter_latest as (
    select
        pd.batter_id,
        pd.game_date,
        pd.game_year,
        max(bap.as_of_date) as latest_as_of
    from pa_batter_dates pd
    join baseball_data.betting.mart_player_archetype_posteriors bap
        on  bap.player_id   = pd.batter_id
        and bap.player_type = 'batter'
        and bap.season      = pd.game_year
        and bap.as_of_date  < pd.game_date
    group by pd.batter_id, pd.game_date, pd.game_year
),

-- Flatten batter cluster probs: (batter_id, game_date) × 5 cluster labels
batter_probs as (
    select
        bl.batter_id,
        bl.game_date,
        f.key::varchar as batter_cluster_label,
        f.value::float as p_batter
    from batter_latest bl
    join baseball_data.betting.mart_player_archetype_posteriors bap
        on  bap.player_id   = bl.batter_id
        and bap.player_type = 'batter'
        and bap.season      = bl.game_year
        and bap.as_of_date  = bl.latest_as_of,
    lateral flatten(input => bap.cluster_probs) f
),

-- Latest pitcher posterior as_of_date strictly before each game_date
pitcher_latest as (
    select
        pd.pitcher_id,
        pd.game_date,
        pd.game_year,
        max(pap.as_of_date) as latest_as_of
    from pa_pitcher_dates pd
    join baseball_data.betting.mart_player_archetype_posteriors pap
        on  pap.player_id   = pd.pitcher_id
        and pap.player_type = 'pitcher'
        and pap.season      = pd.game_year
        and pap.as_of_date  < pd.game_date
    group by pd.pitcher_id, pd.game_date, pd.game_year
),

-- Flatten pitcher cluster probs: (pitcher_id, game_date) × 5 cluster labels
pitcher_probs as (
    select
        pl.pitcher_id,
        pl.game_date,
        f.key::varchar as pitcher_cluster_label,
        f.value::float as p_pitcher
    from pitcher_latest pl
    join baseball_data.betting.mart_player_archetype_posteriors pap
        on  pap.player_id   = pl.pitcher_id
        and pap.player_type = 'pitcher'
        and pap.season      = pl.game_year
        and pap.as_of_date  = pl.latest_as_of,
    lateral flatten(input => pap.cluster_probs) f
),

-- Join PA events × batter probs × pitcher probs
-- Each PA expands to 25 rows (5 batter clusters × 5 pitcher clusters)
pa_weighted as (
    select
        pe.game_date,
        bp.batter_cluster_label,
        pp.pitcher_cluster_label,
        pe.woba_value,
        pe.woba_denom,
        pe.xwoba,
        bp.p_batter * pp.p_pitcher as joint_weight
    from pa_events pe
    join batter_probs bp
        on  bp.batter_id = pe.batter_id
        and bp.game_date = pe.game_date
    join pitcher_probs pp
        on  pp.pitcher_id = pe.pitcher_id
        and pp.game_date  = pe.game_date
),

-- Daily soft-weighted aggregation per (batter_cluster, pitcher_cluster, game_date)
daily_weighted as (
    select
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        sum(joint_weight)                                             as daily_weight,
        sum(woba_value * joint_weight)                               as daily_woba_num,
        sum(woba_denom * joint_weight)                               as daily_woba_denom,
        sum(case when xwoba is not null
                 then xwoba * joint_weight else 0 end)               as daily_xwoba_num,
        sum(case when xwoba is not null
                 then joint_weight else 0 end)                       as daily_xwoba_weight
    from pa_weighted
    group by 1, 2, 3
),

-- 180-day rolling window, excluding same day (1 day preceding gap)
rolling as (
    select
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        sum(daily_weight) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as pa_weight,
        sum(daily_woba_num) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as woba_num,
        sum(daily_woba_denom) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as woba_denom,
        sum(daily_xwoba_num) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as xwoba_num,
        sum(daily_xwoba_weight) over (
            partition by batter_cluster_label, pitcher_cluster_label
            order by game_date
            range between interval '180 days' preceding and interval '1 day' preceding
        )                                                             as xwoba_weight
    from daily_weighted
),

with_shrinkage as (
    select
        batter_cluster_label,
        pitcher_cluster_label,
        game_date,
        pa_weight,
        round(woba_num / nullif(woba_denom, 0), 3)                   as raw_woba,
        round(xwoba_num / nullif(xwoba_weight, 0), 3)                as raw_xwoba,
        pa_weight / (pa_weight + 100.0)                              as shrink_weight,
        round(
            (pa_weight / (pa_weight + 100.0))
                * coalesce(woba_num / nullif(woba_denom, 0), 0.320)
            + (1 - pa_weight / (pa_weight + 100.0)) * 0.320,
            3
        )                                                            as adj_woba,
        round(
            (pa_weight / (pa_weight + 100.0))
                * coalesce(xwoba_num / nullif(xwoba_weight, 0), 0.315)
            + (1 - pa_weight / (pa_weight + 100.0)) * 0.315,
            3
        )                                                            as adj_xwoba
    from rolling
    where pa_weight >= 50
)

select * from with_shrinkage
