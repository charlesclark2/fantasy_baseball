-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch rebuilds from the
-- player_profiles_raw S3 parquet (flat typed columns — no raw_json); the Snowflake
-- branch is a thin view over the lakehouse_ext external table.
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

WITH ranked AS (
    SELECT
        player_id,
        full_name,
        -- E5.10 follow-up: authoritative StatsAPI name PARTS (never split from full_name).
        -- NULL on rows written before the ingest captured them; the ref_players dimension
        -- coalesces to its frozen archive meanwhile. union_by_name in the read below means a
        -- pre-change parquet file simply yields NULL rather than failing the build.
        first_name,
        last_name,
        birth_date,
        height_inches,
        weight_lbs,
        primary_position_code,
        active,
        last_fetched_at,
        ROW_NUMBER() OVER (
            PARTITION BY player_id
            ORDER BY last_fetched_at DESC
        ) AS rn
    FROM read_parquet('{{ lakehouse_loc("player_profiles_raw") }}**/*.parquet', union_by_name=true)
)

SELECT
    player_id,
    full_name,
    first_name,
    last_name,
    birth_date,
    -- Coerce out-of-range StatsAPI bio values to NULL (placeholder/zero rows from new
    -- player records). accepted_range skips NULLs; downstream clustering imputes.
    -- INC-6 (2026-06-21): a zero-height row exit-1'd the Sunday dbtf build.
    CASE WHEN height_inches BETWEEN 60 AND 84 THEN height_inches END AS height_inches,
    CASE WHEN weight_lbs BETWEEN 130 AND 375 THEN weight_lbs END AS weight_lbs,
    primary_position_code,
    active,
    last_fetched_at
FROM ranked
WHERE rn = 1

{% else %}

select * from baseball_data.lakehouse_ext.stg_statsapi_player_profiles

{% endif %}
