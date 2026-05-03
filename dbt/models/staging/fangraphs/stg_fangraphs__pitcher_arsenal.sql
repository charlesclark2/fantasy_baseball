{{
    config(
        materialized='table'
    )
}}

-- Grain: one row per fg_pitcher_id × pitch_type × season
-- Unpivots the wide FanGraphs Stuff+ raw payload into per-pitch-type rows.
-- The pfx tracking system uses 'FA' for 4-seam usage/velocity while the sp
-- (Stuff+) scoring system uses 'FF'. This model normalises both to 'FF'.

with source as (
    select * from {{ source('fangraphs', 'fg_stuff_plus_raw') }}
),

pitch_types as (

    -- FF (4-seam fastball)
    -- Usage key in pfx system is 'FA'; Stuff+ key in sp system is 'FF'
    select
        fg_pitcher_id,
        pitcher_name,
        season,
        'FF'                              as pitch_type,
        raw_json['pfxFA%']::float         as pitch_usage_pct,
        raw_json['sp_s_FF']::float        as stuff_plus,
        raw_json['sp_l_FF']::float        as location_plus,
        raw_json['sp_p_FF']::float        as pitching_plus,
        raw_json['pfxvFA']::float         as avg_velocity_mph,
        raw_json['pfxFA-X']::float        as avg_h_break_in,
        raw_json['pfxFA-Z']::float        as avg_v_break_in,
        ingestion_ts,
        load_id
    from source
    where raw_json['pfxFA%']::float is not null

    union all

    -- SI (sinker)
    select
        fg_pitcher_id, pitcher_name, season,
        'SI',
        raw_json['pfxSI%']::float,
        raw_json['sp_s_SI']::float,
        raw_json['sp_l_SI']::float,
        raw_json['sp_p_SI']::float,
        raw_json['pfxvSI']::float,
        raw_json['pfxSI-X']::float,
        raw_json['pfxSI-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxSI%']::float is not null

    union all

    -- FC (cutter)
    select
        fg_pitcher_id, pitcher_name, season,
        'FC',
        raw_json['pfxFC%']::float,
        raw_json['sp_s_FC']::float,
        raw_json['sp_l_FC']::float,
        raw_json['sp_p_FC']::float,
        raw_json['pfxvFC']::float,
        raw_json['pfxFC-X']::float,
        raw_json['pfxFC-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxFC%']::float is not null

    union all

    -- SL (slider)
    select
        fg_pitcher_id, pitcher_name, season,
        'SL',
        raw_json['pfxSL%']::float,
        raw_json['sp_s_SL']::float,
        raw_json['sp_l_SL']::float,
        raw_json['sp_p_SL']::float,
        raw_json['pfxvSL']::float,
        raw_json['pfxSL-X']::float,
        raw_json['pfxSL-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxSL%']::float is not null

    union all

    -- CU (curveball)
    select
        fg_pitcher_id, pitcher_name, season,
        'CU',
        raw_json['pfxCU%']::float,
        raw_json['sp_s_CU']::float,
        raw_json['sp_l_CU']::float,
        raw_json['sp_p_CU']::float,
        raw_json['pfxvCU']::float,
        raw_json['pfxCU-X']::float,
        raw_json['pfxCU-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxCU%']::float is not null

    union all

    -- KC (knuckle-curve; tracked separately from CU in FanGraphs data)
    select
        fg_pitcher_id, pitcher_name, season,
        'KC',
        raw_json['pfxKC%']::float,
        raw_json['sp_s_KC']::float,
        raw_json['sp_l_KC']::float,
        raw_json['sp_p_KC']::float,
        raw_json['pfxvKC']::float,
        raw_json['pfxKC-X']::float,
        raw_json['pfxKC-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxKC%']::float is not null

    union all

    -- CH (changeup)
    select
        fg_pitcher_id, pitcher_name, season,
        'CH',
        raw_json['pfxCH%']::float,
        raw_json['sp_s_CH']::float,
        raw_json['sp_l_CH']::float,
        raw_json['sp_p_CH']::float,
        raw_json['pfxvCH']::float,
        raw_json['pfxCH-X']::float,
        raw_json['pfxCH-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxCH%']::float is not null

    union all

    -- FS (splitter)
    select
        fg_pitcher_id, pitcher_name, season,
        'FS',
        raw_json['pfxFS%']::float,
        raw_json['sp_s_FS']::float,
        raw_json['sp_l_FS']::float,
        raw_json['sp_p_FS']::float,
        raw_json['pfxvFS']::float,
        raw_json['pfxFS-X']::float,
        raw_json['pfxFS-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxFS%']::float is not null

    union all

    -- ST (sweeper; newer pitch type added ~2022)
    select
        fg_pitcher_id, pitcher_name, season,
        'ST',
        raw_json['pfxST%']::float,
        raw_json['sp_s_ST']::float,
        raw_json['sp_l_ST']::float,
        raw_json['sp_p_ST']::float,
        raw_json['pfxvST']::float,
        raw_json['pfxST-X']::float,
        raw_json['pfxST-Z']::float,
        ingestion_ts, load_id
    from source
    where raw_json['pfxST%']::float is not null

)

select
    fg_pitcher_id,
    pitcher_name,
    season,
    pitch_type,
    pitch_usage_pct,
    stuff_plus,
    location_plus,
    pitching_plus,
    avg_velocity_mph,
    avg_h_break_in,
    avg_v_break_in,
    ingestion_ts,
    load_id
from pitch_types
qualify row_number() over (
    partition by fg_pitcher_id, season, pitch_type
    order by ingestion_ts desc
) = 1
