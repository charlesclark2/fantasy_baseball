{{
    config(
        materialized='table'
    )
}}

with source as (
    select * from {{ source('fangraphs', 'fg_zips_hitting_raw') }}
),

extracted as (
    select
        fg_batter_id,
        batter_name,
        season,
        projection_type,
        raw_json['wRC+']::float                                         as proj_wrc_plus,
        raw_json:OBP::float                                             as proj_obp,
        raw_json:SLG::float                                             as proj_slg,
        raw_json:AVG::float                                             as proj_avg,
        raw_json['K%']::float                                           as proj_k_pct,
        raw_json['BB%']::float                                          as proj_bb_pct,
        raw_json:PA::float                                              as proj_pa,
        raw_json:HR::float                                              as proj_hr,
        raw_json:WAR::float                                             as proj_war,
        raw_json:ISO::float                                             as proj_iso,
        raw_json:wOBA::float                                            as proj_woba,
        raw_json:MLBAMID::varchar                                       as mlbam_batter_id,
        ingestion_ts,
        load_id,
        row_number() over (
            partition by fg_batter_id, season, projection_type
            order by ingestion_ts desc
        ) as _rn
    from source
)

select
    fg_batter_id,
    batter_name,
    season,
    projection_type,
    proj_wrc_plus,
    proj_obp,
    proj_slg,
    proj_avg,
    proj_k_pct,
    proj_bb_pct,
    proj_pa,
    proj_hr,
    proj_war,
    proj_iso,
    proj_woba,
    mlbam_batter_id,
    ingestion_ts,
    load_id
from extracted
where _rn = 1
