-- E11.1-W11-FG dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- registered DuckDB views of its refs (stg_fangraphs__stuff_plus + stg_fangraphs__zips_pitching);
-- the Snowflake branch is a thin view over the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

with stuff as (
    select * from stg_fangraphs__stuff_plus
),

zips as (
    select *
    from stg_fangraphs__zips_pitching
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

{% else %}

select * from baseball_data.lakehouse_ext.fct_fangraphs_pitching_analytics

{% endif %}
