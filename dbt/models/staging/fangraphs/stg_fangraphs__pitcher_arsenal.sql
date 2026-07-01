-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- fg_stuff_plus_raw S3 parquet (flattening the VARCHAR raw_json); the Snowflake
-- branch is a thin view over the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

-- Grain: one row per fg_pitcher_id × pitch_type × season
-- Unpivots the wide FanGraphs Stuff+ raw payload into per-pitch-type rows.
-- The pfx tracking system uses 'FA' for 4-seam usage/velocity while the sp
-- (Stuff+) scoring system uses 'FF'. This model normalises both to 'FF'.

{% if target.name == 'duckdb' %}

with source as (
    -- E11.1-W11 read-repoint: reads the live-writer raw mirror (lakehouse_raw/, dual-written by
    -- ingest_fangraphs_stuff_plus.py under W11_RAW_WRITE_MODE) instead of the SF-sourced W4 snapshot.
    select * from read_parquet('{{ lakehouse_raw_loc("fg_stuff_plus_raw") }}**/*.parquet', union_by_name=true)
),

pitch_types as (

    -- FF (4-seam fastball)
    -- Usage key in pfx system is 'FA'; Stuff+ key in sp system is 'FF'
    select
        fg_pitcher_id,
        pitcher_name,
        season,
        'FF'                                             as pitch_type,
        json_extract_string(raw_json, '$."pfxFA%"')::float   as pitch_usage_pct,
        json_extract_string(raw_json, '$."sp_s_FF"')::float  as stuff_plus,
        json_extract_string(raw_json, '$."sp_l_FF"')::float  as location_plus,
        json_extract_string(raw_json, '$."sp_p_FF"')::float  as pitching_plus,
        json_extract_string(raw_json, '$."pfxvFA"')::float   as avg_velocity_mph,
        json_extract_string(raw_json, '$."pfxFA-X"')::float  as avg_h_break_in,
        json_extract_string(raw_json, '$."pfxFA-Z"')::float  as avg_v_break_in,
        ingestion_ts,
        load_id
    from source
    where json_extract_string(raw_json, '$."pfxFA%"')::float is not null

    union all

    -- SI (sinker)
    select
        fg_pitcher_id, pitcher_name, season,
        'SI',
        json_extract_string(raw_json, '$."pfxSI%"')::float,
        json_extract_string(raw_json, '$."sp_s_SI"')::float,
        json_extract_string(raw_json, '$."sp_l_SI"')::float,
        json_extract_string(raw_json, '$."sp_p_SI"')::float,
        json_extract_string(raw_json, '$."pfxvSI"')::float,
        json_extract_string(raw_json, '$."pfxSI-X"')::float,
        json_extract_string(raw_json, '$."pfxSI-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxSI%"')::float is not null

    union all

    -- FC (cutter)
    select
        fg_pitcher_id, pitcher_name, season,
        'FC',
        json_extract_string(raw_json, '$."pfxFC%"')::float,
        json_extract_string(raw_json, '$."sp_s_FC"')::float,
        json_extract_string(raw_json, '$."sp_l_FC"')::float,
        json_extract_string(raw_json, '$."sp_p_FC"')::float,
        json_extract_string(raw_json, '$."pfxvFC"')::float,
        json_extract_string(raw_json, '$."pfxFC-X"')::float,
        json_extract_string(raw_json, '$."pfxFC-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxFC%"')::float is not null

    union all

    -- SL (slider)
    select
        fg_pitcher_id, pitcher_name, season,
        'SL',
        json_extract_string(raw_json, '$."pfxSL%"')::float,
        json_extract_string(raw_json, '$."sp_s_SL"')::float,
        json_extract_string(raw_json, '$."sp_l_SL"')::float,
        json_extract_string(raw_json, '$."sp_p_SL"')::float,
        json_extract_string(raw_json, '$."pfxvSL"')::float,
        json_extract_string(raw_json, '$."pfxSL-X"')::float,
        json_extract_string(raw_json, '$."pfxSL-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxSL%"')::float is not null

    union all

    -- CU (curveball)
    select
        fg_pitcher_id, pitcher_name, season,
        'CU',
        json_extract_string(raw_json, '$."pfxCU%"')::float,
        json_extract_string(raw_json, '$."sp_s_CU"')::float,
        json_extract_string(raw_json, '$."sp_l_CU"')::float,
        json_extract_string(raw_json, '$."sp_p_CU"')::float,
        json_extract_string(raw_json, '$."pfxvCU"')::float,
        json_extract_string(raw_json, '$."pfxCU-X"')::float,
        json_extract_string(raw_json, '$."pfxCU-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxCU%"')::float is not null

    union all

    -- KC (knuckle-curve; tracked separately from CU in FanGraphs data)
    select
        fg_pitcher_id, pitcher_name, season,
        'KC',
        json_extract_string(raw_json, '$."pfxKC%"')::float,
        json_extract_string(raw_json, '$."sp_s_KC"')::float,
        json_extract_string(raw_json, '$."sp_l_KC"')::float,
        json_extract_string(raw_json, '$."sp_p_KC"')::float,
        json_extract_string(raw_json, '$."pfxvKC"')::float,
        json_extract_string(raw_json, '$."pfxKC-X"')::float,
        json_extract_string(raw_json, '$."pfxKC-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxKC%"')::float is not null

    union all

    -- CH (changeup)
    select
        fg_pitcher_id, pitcher_name, season,
        'CH',
        json_extract_string(raw_json, '$."pfxCH%"')::float,
        json_extract_string(raw_json, '$."sp_s_CH"')::float,
        json_extract_string(raw_json, '$."sp_l_CH"')::float,
        json_extract_string(raw_json, '$."sp_p_CH"')::float,
        json_extract_string(raw_json, '$."pfxvCH"')::float,
        json_extract_string(raw_json, '$."pfxCH-X"')::float,
        json_extract_string(raw_json, '$."pfxCH-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxCH%"')::float is not null

    union all

    -- FS (splitter)
    select
        fg_pitcher_id, pitcher_name, season,
        'FS',
        json_extract_string(raw_json, '$."pfxFS%"')::float,
        json_extract_string(raw_json, '$."sp_s_FS"')::float,
        json_extract_string(raw_json, '$."sp_l_FS"')::float,
        json_extract_string(raw_json, '$."sp_p_FS"')::float,
        json_extract_string(raw_json, '$."pfxvFS"')::float,
        json_extract_string(raw_json, '$."pfxFS-X"')::float,
        json_extract_string(raw_json, '$."pfxFS-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxFS%"')::float is not null

    union all

    -- ST (sweeper; newer pitch type added ~2022)
    select
        fg_pitcher_id, pitcher_name, season,
        'ST',
        json_extract_string(raw_json, '$."pfxST%"')::float,
        json_extract_string(raw_json, '$."sp_s_ST"')::float,
        json_extract_string(raw_json, '$."sp_l_ST"')::float,
        json_extract_string(raw_json, '$."sp_p_ST"')::float,
        json_extract_string(raw_json, '$."pfxvST"')::float,
        json_extract_string(raw_json, '$."pfxST-X"')::float,
        json_extract_string(raw_json, '$."pfxST-Z"')::float,
        ingestion_ts, load_id
    from source
    where json_extract_string(raw_json, '$."pfxST%"')::float is not null

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

{% else %}

select * from baseball_data.lakehouse_ext.stg_fangraphs__pitcher_arsenal

{% endif %}
