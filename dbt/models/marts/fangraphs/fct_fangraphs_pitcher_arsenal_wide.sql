{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per fg_pitcher_id × season
-- Pivots stg_fangraphs__pitcher_arsenal from pitcher × pitch_type × season to
-- pitcher × season (wide format) for joining into the feature layer.
-- Joins stg_fangraphs__stuff_plus for overall_stuff_plus and mlbam_pitcher_id.

with arsenal as (
    select * from {{ ref('stg_fangraphs__pitcher_arsenal') }}
),

stuff as (
    select
        fg_pitcher_id,
        season,
        stuff_plus           as overall_stuff_plus,
        mlbam_pitcher_id
    from {{ ref('stg_fangraphs__stuff_plus') }}
),

-- Rank pitches by usage to determine primary pitch type
usage_ranked as (
    select
        fg_pitcher_id,
        season,
        pitch_type,
        pitch_usage_pct,
        row_number() over (
            partition by fg_pitcher_id, season
            order by coalesce(pitch_usage_pct, 0) desc
        ) as usage_rank
    from arsenal
),

primary_pitch as (
    select fg_pitcher_id, season, pitch_type as primary_pitch_type
    from usage_ranked
    where usage_rank = 1
),

-- Conditional aggregation pivot: one row per pitcher × season
pivoted as (
    select
        fg_pitcher_id,
        season,

        -- Per-pitch Stuff+
        max(case when pitch_type = 'FF' then stuff_plus end) as ff_stuff_plus,
        max(case when pitch_type = 'SI' then stuff_plus end) as si_stuff_plus,
        max(case when pitch_type = 'FC' then stuff_plus end) as fc_stuff_plus,
        max(case when pitch_type = 'SL' then stuff_plus end) as slider_stuff_plus,
        max(case when pitch_type = 'CU' then stuff_plus end) as curveball_stuff_plus,
        max(case when pitch_type = 'CH' then stuff_plus end) as changeup_stuff_plus,

        -- Per-pitch velocity (for fastball types only — used to pick primary)
        max(case when pitch_type = 'FF' then avg_velocity_mph end) as ff_velo,
        max(case when pitch_type = 'SI' then avg_velocity_mph end) as si_velo,
        max(case when pitch_type = 'FC' then avg_velocity_mph end) as fc_velo,

        -- Per-pitch usage
        max(case when pitch_type = 'FF' then pitch_usage_pct end) as ff_pct,
        max(case when pitch_type = 'SI' then pitch_usage_pct end) as si_pct,
        max(case when pitch_type = 'FC' then pitch_usage_pct end) as fc_pct,
        max(case when pitch_type = 'SL' then pitch_usage_pct end) as sl_pct,
        max(case when pitch_type = 'CU' then pitch_usage_pct end) as cu_pct,
        max(case when pitch_type = 'KC' then pitch_usage_pct end) as kc_pct,
        max(case when pitch_type = 'ST' then pitch_usage_pct end) as st_pct,
        max(case when pitch_type = 'CH' then pitch_usage_pct end) as ch_pct,
        max(case when pitch_type = 'FS' then pitch_usage_pct end) as fs_pct,

        -- Max horizontal break across all pitch types
        max(abs(avg_h_break_in)) as max_pitch_break_in

    from arsenal
    group by fg_pitcher_id, season
)

select
    p.fg_pitcher_id,
    p.season,
    s.overall_stuff_plus,
    -- mlbam_pitcher_id as integer for joining to Stats API pitcher_id
    s.mlbam_pitcher_id::integer          as mlbam_pitcher_id,

    pr.primary_pitch_type,

    -- Pitch category usage buckets
    coalesce(p.ff_pct, 0) + coalesce(p.si_pct, 0) + coalesce(p.fc_pct, 0)
                                         as fastball_pct,
    coalesce(p.sl_pct, 0) + coalesce(p.cu_pct, 0) + coalesce(p.kc_pct, 0)
        + coalesce(p.st_pct, 0)          as breaking_pct,
    coalesce(p.ch_pct, 0) + coalesce(p.fs_pct, 0)
                                         as offspeed_pct,

    -- fastball_stuff_plus: Stuff+ of the primary fastball type (FF > SI > FC by usage)
    case
        when coalesce(p.ff_pct, 0) >= coalesce(p.si_pct, 0)
             and coalesce(p.ff_pct, 0) >= coalesce(p.fc_pct, 0)
            then p.ff_stuff_plus
        when coalesce(p.si_pct, 0) >= coalesce(p.fc_pct, 0)
            then p.si_stuff_plus
        else p.fc_stuff_plus
    end                                  as fastball_stuff_plus,

    p.slider_stuff_plus,
    p.curveball_stuff_plus,
    p.changeup_stuff_plus,

    -- avg_fastball_velo_mph: velocity of the primary fastball type
    case
        when coalesce(p.ff_pct, 0) >= coalesce(p.si_pct, 0)
             and coalesce(p.ff_pct, 0) >= coalesce(p.fc_pct, 0)
            then p.ff_velo
        when coalesce(p.si_pct, 0) >= coalesce(p.fc_pct, 0)
            then p.si_velo
        else p.fc_velo
    end                                  as avg_fastball_velo_mph,

    p.max_pitch_break_in

from pivoted p
left join stuff s
    on  s.fg_pitcher_id = p.fg_pitcher_id
    and s.season        = p.season
left join primary_pitch pr
    on  pr.fg_pitcher_id = p.fg_pitcher_id
    and pr.season        = p.season
