-- E11.1-W11-FG dual-branch (tag w4_lakehouse). THREE branches, gated so the model is SAFE to deploy
-- BEFORE the S3 ext table exists (Defect B): (1) duckdb → rebuild from the registered stg views;
-- (2) Snowflake + W11FG_LAKEHOUSE_S3=1 → thin view over lakehouse_ext (post-cutover); (3) Snowflake
-- default → the ORIGINAL SF-native join (unchanged), so the daily dbt build stays GREEN until the
-- operator flips the flag AFTER --w4 builds the parquet + the ext table is created + validated.
-- ⚠️ Flag branch NESTED inside the outer else-branch (see stg_fangraphs__zips_pitching header) so
--    run_w1_lakehouse.extract_duckdb_sql never sees the ext-table read. No Jinja tags in this comment.
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
{% if env_var('W11FG_LAKEHOUSE_S3', '0') == '1' %}

select * from baseball_data.lakehouse_ext.fct_fangraphs_pitching_analytics

{% else %}

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

{% endif %}
{% endif %}
