-- E11.1-W11-FG dual-branch (tag w4_lakehouse). THREE branches, gated so the model is SAFE to deploy
-- BEFORE the S3 ext table exists (Defect B / the "deployed before the box artifacts exist" runtime-gate
-- miss): (1) duckdb → rebuild from the fg_zips_pitching_raw S3 snapshot; (2) Snowflake + W11FG_LAKEHOUSE_S3=1
-- → thin view over the lakehouse_ext external table (post-cutover); (3) Snowflake default → the ORIGINAL
-- SF-native VARIANT flatten (unchanged), so the daily dbt build stays GREEN until the operator flips the
-- flag AFTER --w4 has built the parquet and the ext table is created + validated.
-- ⚠️ The flag branch is NESTED inside the outer else-branch on purpose: run_w1_lakehouse.extract_duckdb_sql
--    captures up to the FIRST else, so a flat elif would leak the ext-table read into the DuckDB build.
--    Keep it nested. (No Jinja statement tags in this comment — fusion lexes tags BEFORE stripping comments.)
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

with source as (
    -- E11.1-W11-FG: reads the W4 export-bridge SNAPSHOT (lakehouse/fg_zips_pitching_raw/, written by
    -- export_w4_raw_to_s3.py from the whole SF table) — the SAME path + cadence as the already-migrated
    -- zips_hitting sibling. ZiPS pitching is pre-season-static CSV data (the 'zips' rows fct uses come
    -- from the SF-only CSV loader), so there is NO in-season live writer; freshness = re-run the bridge
    -- after an annual CSV load. (Contrast: the in-season stuff_plus stg reads the lakehouse_raw/ live mirror.)
    select * from read_parquet('{{ lakehouse_loc("fg_zips_pitching_raw") }}**/*.parquet', union_by_name=true)
),

extracted as (
    select
        fg_pitcher_id,
        pitcher_name,
        season,
        projection_type,
        json_extract_string(raw_json, '$.ERA')::float                   as proj_era,
        json_extract_string(raw_json, '$.FIP')::float                   as proj_fip,
        json_extract_string(raw_json, '$.xFIP')::float                  as proj_xfip,
        json_extract_string(raw_json, '$."K%"')::float                  as proj_k_pct,
        json_extract_string(raw_json, '$."BB%"')::float                 as proj_bb_pct,
        json_extract_string(raw_json, '$."K/9"')::float                 as proj_k_per_9,
        json_extract_string(raw_json, '$."BB/9"')::float                as proj_bb_per_9,
        json_extract_string(raw_json, '$.IP')::float                    as proj_ip,
        json_extract_string(raw_json, '$.WAR')::float                   as proj_war,
        json_extract_string(raw_json, '$.WHIP')::float                  as proj_whip,
        json_extract_string(raw_json, '$.MLBAMID')::varchar             as mlbam_pitcher_id,
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

{% else %}
{% if env_var('W11FG_LAKEHOUSE_S3', '0') == '1' %}

select * from baseball_data.lakehouse_ext.stg_fangraphs__zips_pitching

{% else %}

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

{% endif %}
{% endif %}
