{{
    config(
        materialized='table'
    )
}}

with source as (
    select * from {{ source('fangraphs', 'fg_zips_pitching_raw') }}
),

extracted as (
    select
        fg_pitcher_id,
        pitcher_name,
        season,
        projection_type,
        raw_json:ERA::float                                             as proj_era,
        raw_json:FIP::float                                             as proj_fip,
        raw_json:xFIP::float                                            as proj_xfip,
        raw_json['K%']::float                                           as proj_k_pct,
        raw_json['BB%']::float                                          as proj_bb_pct,
        raw_json['K/9']::float                                          as proj_k_per_9,
        raw_json['BB/9']::float                                         as proj_bb_per_9,
        raw_json:IP::float                                              as proj_ip,
        raw_json:WAR::float                                             as proj_war,
        raw_json:WHIP::float                                            as proj_whip,
        raw_json:MLBAMID::varchar                                       as mlbam_pitcher_id,
        ingestion_ts,
        load_id,
        row_number() over (
            partition by fg_pitcher_id, season, projection_type
            order by ingestion_ts desc
        ) as _rn
    from source
)

select
    fg_pitcher_id,
    pitcher_name,
    season,
    projection_type,
    proj_era,
    proj_fip,
    proj_xfip,
    proj_k_pct,
    proj_bb_pct,
    proj_k_per_9,
    proj_bb_per_9,
    proj_ip,
    proj_war,
    proj_whip,
    mlbam_pitcher_id,
    ingestion_ts,
    load_id
from extracted
where _rn = 1
