-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- fg_stuff_plus_raw S3 parquet (flattening the VARCHAR raw_json); the Snowflake
-- branch is a thin view over the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

with source as (
    select * from read_parquet('{{ lakehouse_loc("fg_stuff_plus_raw") }}**/*.parquet', union_by_name=true)
),

extracted as (
    select
        fg_pitcher_id,
        pitcher_name,
        season,
        json_extract_string(raw_json, '$.IP')::float                    as ip,
        json_extract_string(raw_json, '$.sp_stuff')::float              as stuff_plus,
        json_extract_string(raw_json, '$.sp_location')::float           as location_plus,
        json_extract_string(raw_json, '$.sp_pitching')::float           as pitching_plus,
        -- Pitch arsenal usage percentages (pfx = PitchF/X tracking system)
        json_extract_string(raw_json, '$."pfxFA%"')::float              as _fb_fa_pct,
        json_extract_string(raw_json, '$."pfxSI%"')::float              as _fb_si_pct,
        json_extract_string(raw_json, '$."pfxFC%"')::float              as _fb_fc_pct,
        json_extract_string(raw_json, '$."pfxSL%"')::float              as _brk_sl_pct,
        json_extract_string(raw_json, '$."pfxCU%"')::float              as _brk_cu_pct,
        json_extract_string(raw_json, '$."pfxCH%"')::float              as _off_ch_pct,
        json_extract_string(raw_json, '$."pfxFS%"')::float              as _off_fs_pct,
        json_extract_string(raw_json, '$.xMLBAMID')::varchar            as mlbam_pitcher_id,
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

{% else %}

select * from baseball_data.lakehouse_ext.stg_fangraphs__stuff_plus

{% endif %}
