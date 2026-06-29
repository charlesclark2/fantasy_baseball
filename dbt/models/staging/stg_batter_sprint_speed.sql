-- =============================================================================
-- stg_batter_sprint_speed.sql
-- Source: baseball_data.savant.sprint_speed_raw
-- Grain: one row per player per season (latest snapshot only)
-- Purpose: Expose Statcast sprint speed (ft/s) for use in lineup features.
--          Deduplicates to the most recent snapshot_date per player × season.
--
-- E11.1-W5 dual-branch lakehouse precursor (W4-deferred Group B). DuckDB branch reads
-- the sprint_speed_raw S3 parquet (exported by scripts/export_w5_raw_to_s3.py); Snowflake
-- branch is a thin view over the lakehouse_ext external table. The Savant sprint ingest
-- KEEPS its Snowflake write — this reads the one-time/opt-in S3 mirror. Feeds the W5
-- Group-B mart_team_defense_quality_rolling.
-- =============================================================================

{{ config(materialized='view', tags=['w5_lakehouse']) }}

{% if target.name == 'duckdb' %}

with

source as (

    select * from read_parquet('{{ lakehouse_loc("sprint_speed_raw") }}**/*.parquet', union_by_name=true)

),

latest_snapshot as (

    select
        player_mlbam_id,
        season,
        max(snapshot_date) as snapshot_date
    from source
    group by 1, 2

),

deduped as (

    select
        s.player_mlbam_id,
        s.player_name,
        s.team_abbrev,
        s.season,
        s.snapshot_date,
        s.sprint_speed_fts,
        s.competitive_runs,
        s.hp_to_1b                                         as hp_to_1b_sec,
        s.hp_to_2b                                         as hp_to_2b_sec,
        s.age,
        s.position,
        s.ingestion_timestamp
    from source s
    inner join latest_snapshot ls
        on  s.player_mlbam_id = ls.player_mlbam_id
        and s.season          = ls.season
        and s.snapshot_date   = ls.snapshot_date

)

select * from deduped

{% else %}

select * from baseball_data.lakehouse_ext.stg_batter_sprint_speed

{% endif %}
