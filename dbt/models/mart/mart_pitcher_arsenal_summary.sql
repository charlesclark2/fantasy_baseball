-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- registered DuckDB views of its refs; the Snowflake branch is a thin view over
-- the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

-- Grain: pitcher_id × game_year
-- Per-pitcher-season arsenal vector for k-means clustering (Card 7.K).
-- Combines Statcast physical pitch characteristics with FanGraphs Stuff+
-- from fct_fangraphs_pitcher_arsenal_wide via mlbam_pitcher_id crosswalk.
--
-- Data availability: Statcast pitch-level movement data is available from 2015+.
-- FanGraphs Stuff+ and MLB arm_angle tracking are both only available from 2020+;
-- those columns will be NULL for 2015-2019 seasons (LEFT join produces NULL).
-- Stratum-A features (velocity, movement, pitch mix, outcomes) are used for clustering;
-- stratum-B features (stuff_plus, arm_angle) are recorded but excluded from k-means.
-- Minimum threshold: 200 pitches (~5 quality starts).

{% if target.name == 'duckdb' %}

with pitch_chars as (
    select
        pitcher_id,
        game_year,
        pitch_category,
        count(*)                               as pitch_count,
        avg(release_speed_mph)                 as avg_velocity,
        avg(pitch_movement_x_ft)               as avg_hmov,
        avg(pitch_movement_z_ft)               as avg_vmov,
        avg(release_spin_rate_rpm)             as avg_spin,
        avg(release_pos_z_ft)                  as avg_release_height,
        avg(release_pos_x_ft)                  as avg_release_side,
        avg(release_extension_ft)              as avg_extension,
        avg(pitcher_arm_angle_degrees)         as avg_arm_angle
    from mart_pitch_characteristics
    where pitch_category in ('fastball', 'breaking', 'offspeed')
      and game_year >= 2015
    group by 1, 2, 3
),

pitch_totals as (
    select pitcher_id, game_year, sum(pitch_count) as total_pitches
    from pitch_chars
    group by 1, 2
),

pitch_pct as (
    select
        pc.pitcher_id,
        pc.game_year,
        pc.pitch_category,
        pc.pitch_count,
        pc.pitch_count / pt.total_pitches      as family_pct,
        pc.avg_velocity,
        pc.avg_hmov,
        pc.avg_vmov,
        pc.avg_spin,
        pc.avg_release_height,
        pc.avg_release_side,
        pc.avg_extension,
        pc.avg_arm_angle
    from pitch_chars pc
    join pitch_totals pt using (pitcher_id, game_year)
),

-- Pivot to wide: one row per pitcher × game_year
arsenal_wide as (
    select
        pitcher_id,
        game_year,
        sum(pitch_count)                       as total_pitches,
        sum(case when pitch_category = 'fastball' then family_pct else 0 end)
                                               as fastball_pct_statcast,
        sum(case when pitch_category = 'breaking' then family_pct else 0 end)
                                               as breaking_pct_statcast,
        sum(case when pitch_category = 'offspeed' then family_pct else 0 end)
                                               as offspeed_pct_statcast,

        -- Velocity per family (null if not thrown)
        max(case when pitch_category = 'fastball' then avg_velocity end)
                                               as fb_avg_velocity,
        max(case when pitch_category = 'breaking' then avg_velocity end)
                                               as brk_avg_velocity,
        max(case when pitch_category = 'offspeed' then avg_velocity end)
                                               as os_avg_velocity,

        -- Horizontal movement per family (pfx_x in feet, catcher's POV)
        max(case when pitch_category = 'fastball' then avg_hmov end)
                                               as fb_avg_hmov,
        max(case when pitch_category = 'breaking' then avg_hmov end)
                                               as brk_avg_hmov,

        -- Vertical movement per family
        max(case when pitch_category = 'fastball' then avg_vmov end)
                                               as fb_avg_vmov,
        max(case when pitch_category = 'breaking' then avg_vmov end)
                                               as brk_avg_vmov,

        -- Spin per family
        max(case when pitch_category = 'fastball' then avg_spin end)
                                               as fb_avg_spin,
        max(case when pitch_category = 'breaking' then avg_spin end)
                                               as brk_avg_spin,

        -- Release point and arm slot (fastball only — most stable signal)
        max(case when pitch_category = 'fastball' then avg_release_height end)
                                               as fb_release_height,
        max(case when pitch_category = 'fastball' then avg_release_side end)
                                               as fb_release_side,
        max(case when pitch_category = 'fastball' then avg_extension end)
                                               as fb_extension,
        max(case when pitch_category = 'fastball' then avg_arm_angle end)
                                               as fb_arm_angle

    from pitch_pct
    group by 1, 2
),

-- Join FanGraphs Stuff+ via mlbam_pitcher_id crosswalk from Card 7.F
with_stuff as (
    select
        a.*,
        s.overall_stuff_plus,
        s.fastball_stuff_plus,
        s.slider_stuff_plus,
        s.curveball_stuff_plus,
        s.changeup_stuff_plus,
        -- Use FanGraphs pitch mix if available, else fall back to Statcast
        coalesce(s.fastball_pct, a.fastball_pct_statcast) as fastball_pct,
        coalesce(s.breaking_pct, a.breaking_pct_statcast) as breaking_pct,
        coalesce(s.offspeed_pct, a.offspeed_pct_statcast) as offspeed_pct
    from arsenal_wide a
    left join fct_fangraphs_pitcher_arsenal_wide s
        -- mlbam_pitcher_id in fct table is the MLBAM bam_id crosswalk
        on  s.mlbam_pitcher_id = a.pitcher_id
        and s.season           = a.game_year
)

select * from with_stuff
where total_pitches >= 200

{% else %}

select * from baseball_data.lakehouse_ext.mart_pitcher_arsenal_summary

{% endif %}
