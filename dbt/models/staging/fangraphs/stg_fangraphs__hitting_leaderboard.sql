{{
    config(
        materialized='table'
    )
}}

with source as (
    select * from {{ source('fangraphs', 'fg_hitting_leaderboard_raw') }}
),

extracted as (
    select
        raw_json:playerid::varchar                                      as fg_batter_id,
        raw_json:PlayerName::varchar                                    as batter_name,
        season,
        window_type,
        window_start,
        window_end,
        raw_json['wRC+']::float                                         as wrc_plus,
        raw_json:OBP::float                                             as obp,
        raw_json:SLG::float                                             as slg,
        raw_json:AVG::float                                             as avg,
        raw_json['K%']::float                                           as k_pct,
        raw_json['BB%']::float                                          as bb_pct,
        raw_json:PA::float                                              as pa,
        raw_json:HR::float                                              as hr,
        raw_json:WAR::float                                             as war,
        raw_json:xMLBAMID::varchar                                      as mlbam_batter_id,
        ingestion_ts,
        load_id,
        row_number() over (
            partition by raw_json:playerid::varchar, season, window_type, window_start
            order by ingestion_ts desc
        ) as _rn
    from source
)

select
    fg_batter_id,
    batter_name,
    season,
    window_type,
    window_start,
    window_end,
    wrc_plus,
    obp,
    slg,
    avg,
    k_pct,
    bb_pct,
    pa,
    hr,
    war,
    mlbam_batter_id,
    ingestion_ts,
    load_id
from extracted
where _rn = 1
