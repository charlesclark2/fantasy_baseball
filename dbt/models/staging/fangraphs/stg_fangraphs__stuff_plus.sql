{{
    config(
        materialized='table'
    )
}}

with source as (
    select * from {{ source('fangraphs', 'fg_stuff_plus_raw') }}
),

extracted as (
    select
        fg_pitcher_id,
        pitcher_name,
        season,
        raw_json:IP::float                                              as ip,
        raw_json:sp_stuff::float                                        as stuff_plus,
        raw_json:sp_location::float                                     as location_plus,
        raw_json:sp_pitching::float                                     as pitching_plus,
        -- Pitch arsenal usage percentages (pfx = PitchF/X tracking system)
        raw_json['pfxFA%']::float                                       as _fb_fa_pct,
        raw_json['pfxSI%']::float                                       as _fb_si_pct,
        raw_json['pfxFC%']::float                                       as _fb_fc_pct,
        raw_json['pfxSL%']::float                                       as _brk_sl_pct,
        raw_json['pfxCU%']::float                                       as _brk_cu_pct,
        raw_json['pfxCH%']::float                                       as _off_ch_pct,
        raw_json['pfxFS%']::float                                       as _off_fs_pct,
        raw_json:xMLBAMID::varchar                                      as mlbam_pitcher_id,
        ingestion_ts,
        load_id,
        row_number() over (
            partition by fg_pitcher_id, season
            order by ingestion_ts desc
        ) as _rn
    from source
)

select
    fg_pitcher_id,
    pitcher_name,
    season,
    ip,
    stuff_plus,
    location_plus,
    pitching_plus,
    coalesce(_fb_fa_pct, 0) + coalesce(_fb_si_pct, 0) + coalesce(_fb_fc_pct, 0) as fastball_pct,
    coalesce(_brk_sl_pct, 0) + coalesce(_brk_cu_pct, 0)                          as breaking_pct,
    coalesce(_off_ch_pct, 0) + coalesce(_off_fs_pct, 0)                           as offspeed_pct,
    case
        when (coalesce(_fb_fa_pct, 0) + coalesce(_fb_si_pct, 0) + coalesce(_fb_fc_pct, 0))
             >= greatest(
                    coalesce(_brk_sl_pct, 0) + coalesce(_brk_cu_pct, 0),
                    coalesce(_off_ch_pct, 0) + coalesce(_off_fs_pct, 0)
                )
            then 'fastball'
        when (coalesce(_brk_sl_pct, 0) + coalesce(_brk_cu_pct, 0))
             >= (coalesce(_off_ch_pct, 0) + coalesce(_off_fs_pct, 0))
            then 'breaking'
        else 'offspeed'
    end                                                                            as primary_pitch_type,
    mlbam_pitcher_id,
    ingestion_ts,
    load_id
from extracted
where _rn = 1
