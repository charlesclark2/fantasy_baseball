-- =============================================================================
-- stg_ref_players.sql
-- Source: baseball_data.savant.ref_players  (~25.9k rows — player-name dimension)
-- Grain: one row per MLB player (mlb_bam_id)
-- Purpose: Make the ref_players name dimension resolvable on BOTH the Snowflake
--          and the duckdb/S3 lakehouse target, so the duckdb-built mart_pitch_*
--          name-enrichment marts (hitter/pitcher profile) don't compile to the
--          Snowflake FQN `baseball_data.savant.ref_players` (which fails on duckdb
--          with "Catalog baseball_data does not exist").
--
-- E11.1-W1 duckdb target: reads the Parquet exported by
-- scripts/export_ref_players_to_s3.py. Run that export once before the first
-- duckdb build. Snowflake target: passthrough view over the source.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view') }}

-- Read-through view over S3 Parquet (output of scripts/export_ref_players_to_s3.py).
select
    mlb_bam_id,
    first_name,
    last_name,
    player_name,
    mlb_played_first,
    mlb_played_last
from read_parquet('{{ lakehouse_loc("stg_ref_players") }}**/*.parquet', union_by_name=true)

{% else %}

{{ config(materialized='view') }}

select
    mlb_bam_id,
    first_name,
    last_name,
    player_name,
    mlb_played_first,
    mlb_played_last
from {{ source('savant', 'ref_players') }}

{% endif %}
