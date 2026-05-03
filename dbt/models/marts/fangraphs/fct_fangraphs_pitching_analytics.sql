{{
    config(
        materialized='view'
    )
}}

with stuff as (
    select * from {{ ref('stg_fangraphs__stuff_plus') }}
),

zips as (
    select *
    from {{ ref('stg_fangraphs__zips_pitching') }}
    where projection_type = 'zips'
)

select
    s.fg_pitcher_id,
    s.pitcher_name,
    s.season,
    -- Stuff+ arsenal quality metrics
    s.stuff_plus,
    s.location_plus,
    s.pitching_plus,
    s.primary_pitch_type,
    s.fastball_pct,
    s.breaking_pct,
    s.offspeed_pct,
    s.ip                                                                as stuff_ip,
    -- ZiPS pre-season projections (null when no ZiPS data for this pitcher/season)
    z.proj_era,
    z.proj_fip,
    z.proj_xfip,
    z.proj_k_pct,
    z.proj_bb_pct,
    z.proj_k_per_9,
    z.proj_bb_per_9,
    z.proj_ip,
    z.proj_war,
    z.proj_whip,
    z.mlbam_pitcher_id
from stuff s
left join zips z
    on  s.fg_pitcher_id = z.fg_pitcher_id
    and s.season        = z.season
