-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- registered DuckDB views of its refs; the Snowflake branch is a thin view over
-- the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

-- Grain: batter_id × game_year
-- One-row-per-batter-season hitting vector for k-means batter archetype clustering (Card 7.K2).
--
-- Statcast batted-ball metrics (gb_pct, fb_pct, ld_pct, pull_pct, hard_hit_pct, barrel_pct,
-- avg_exit_velocity) require batted_ball_type, exit_velocity_mph, hit_location_fielder, and
-- batter_hand, which are not exposed in mart_pitch_play_event. stg_batter_pitches is joined
-- via pitch_sk to supply those columns while mart_pitch_play_event anchors the PA-level events
-- and provides xwoba.
--
-- K%, BB%, and ISO are derived from plate_appearance_event (Statcast terminal events).
-- FanGraphs ZiPS projected k_pct / bb_pct (proj_k_pct, proj_bb_pct) are joined as
-- supplementary plate-discipline signals when available.
--
-- Pull-side derivation:
--   RHH pulls to left side of field → hit_location_fielder in (5=3B, 6=SS, 7=LF)
--   LHH pulls to right side of field → hit_location_fielder in (3=1B, 4=2B, 9=RF)
--
-- Leakage: this mart is built per-season from same-season data.
-- Leakage prevention is enforced in downstream cluster joins (game_year - 1 = season).
--
-- Minimum 100 PA gate filters part-time / short-season samples.

{% if target.name == 'duckdb' %}

with statcast_pa as (
    -- Aggregate Statcast PA-level events from mart_pitch_play_event.
    -- Join stg_batter_pitches for batted ball columns not present in the mart.
    select
        ppe.batter_id,
        ppe.game_year,
        count(*)                                                        as pa_count,
        avg(ppe.xwoba)                                                  as avg_xwoba,
        avg(bp.exit_velocity_mph)                                       as avg_exit_velocity,

        -- Batted ball type percentages (denominator: balls in play only)
        sum(case when bp.batted_ball_type = 'ground_ball'  then 1 else 0 end)::float
            / nullif(count(case when bp.batted_ball_type is not null then 1 end), 0)
                                                                        as gb_pct,
        sum(case when bp.batted_ball_type = 'fly_ball'     then 1 else 0 end)::float
            / nullif(count(case when bp.batted_ball_type is not null then 1 end), 0)
                                                                        as fb_pct,
        sum(case when bp.batted_ball_type = 'line_drive'   then 1 else 0 end)::float
            / nullif(count(case when bp.batted_ball_type is not null then 1 end), 0)
                                                                        as ld_pct,

        -- Pull tendency: proportion of balls in play hit to pull side
        sum(case
            when bp.batter_hand = 'R' and bp.hit_location_fielder in (5, 6, 7) then 1
            when bp.batter_hand = 'L' and bp.hit_location_fielder in (3, 4, 9) then 1
            else 0
        end)::float
            / nullif(count(case when bp.batted_ball_type is not null then 1 end), 0)
                                                                        as pull_pct,

        -- Hard-hit rate: exit velocity >= 95 mph over all PA
        sum(case when bp.exit_velocity_mph >= 95 then 1 else 0 end)::float
            / nullif(count(*), 0)                                       as hard_hit_pct,

        -- Barrel rate: exit velocity >= 98 mph and launch angle 26–30°
        sum(case
            when bp.exit_velocity_mph >= 98
             and bp.launch_angle_degrees between 26 and 30 then 1
            else 0
        end)::float / nullif(count(*), 0)                              as barrel_pct,

        -- Strikeout rate
        sum(case when bp.plate_appearance_event in (
            'strikeout', 'strikeout_double_play'
        ) then 1 else 0 end)::float / nullif(count(*), 0)              as k_pct,

        -- Walk rate
        sum(case when bp.plate_appearance_event in (
            'walk', 'intent_walk'
        ) then 1 else 0 end)::float / nullif(count(*), 0)              as bb_pct,

        -- ISO = extra bases per at-bat
        -- Extra bases: double=1, triple=2, HR=3 (singles add 0, outs add 0)
        sum(case
            when bp.plate_appearance_event = 'double'   then 1
            when bp.plate_appearance_event = 'triple'   then 2
            when bp.plate_appearance_event = 'home_run' then 3
            else 0
        end)::float / nullif(
            count(case when bp.plate_appearance_event not in (
                'walk', 'intent_walk', 'hit_by_pitch',
                'sac_fly', 'sac_fly_double_play',
                'sac_bunt', 'sac_bunt_double_play',
                'catcher_interf'
            ) then 1 end),
            0
        )                                                               as iso

    from mart_pitch_play_event ppe
    join stg_batter_pitches bp
        on  bp.pitch_sk = ppe.pitch_sk
    where ppe.plate_appearance_event is not null
      and ppe.game_year >= 2015
    group by 1, 2
),

fg_hitting as (
    select
        mlbam_batter_id  as batter_id,
        season           as game_year,
        proj_k_pct,
        proj_bb_pct
    from fct_fangraphs_hitting_analytics
    where season >= 2015
      and mlbam_batter_id is not null
)

select
    s.batter_id,
    s.game_year,
    s.pa_count,
    s.avg_exit_velocity,
    s.gb_pct,
    s.fb_pct,
    s.ld_pct,
    s.pull_pct,
    s.hard_hit_pct,
    s.barrel_pct,
    s.avg_xwoba,
    s.k_pct,
    s.bb_pct,
    s.iso,
    f.proj_k_pct,
    f.proj_bb_pct
from statcast_pa s
left join fg_hitting f
    on  f.batter_id = s.batter_id
    and f.game_year = s.game_year
where s.pa_count >= 100

{% else %}

select * from baseball_data.lakehouse_ext.mart_batter_profile_summary

{% endif %}
