-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- fg_zips_hitting_raw S3 parquet (flattening the VARCHAR raw_json); the Snowflake
-- branch is a thin view over the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

with source as (
    select * from read_parquet('{{ lakehouse_loc("fg_zips_hitting_raw") }}**/*.parquet', union_by_name=true)
),

extracted as (
    select
        fg_batter_id,
        batter_name,
        season,
        projection_type,
        json_extract_string(raw_json, '$."wRC+"')::float               as proj_wrc_plus,
        json_extract_string(raw_json, '$.OBP')::float                  as proj_obp,
        json_extract_string(raw_json, '$.SLG')::float                  as proj_slg,
        json_extract_string(raw_json, '$.AVG')::float                  as proj_avg,
        json_extract_string(raw_json, '$."K%"')::float                 as proj_k_pct,
        json_extract_string(raw_json, '$."BB%"')::float                as proj_bb_pct,
        json_extract_string(raw_json, '$.PA')::float                   as proj_pa,
        json_extract_string(raw_json, '$.HR')::float                   as proj_hr,
        json_extract_string(raw_json, '$.WAR')::float                  as proj_war,
        json_extract_string(raw_json, '$.ISO')::float                  as proj_iso,
        json_extract_string(raw_json, '$.wOBA')::float                 as proj_woba,
        json_extract_string(raw_json, '$.MLBAMID')::varchar            as mlbam_batter_id,
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

{% else %}

select * from baseball_data.lakehouse_ext.stg_fangraphs__zips_hitting

{% endif %}
