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

    -- E11.1-W11 read-repoint: live-writer raw mirror (lakehouse_raw/, dual-written by
    -- ingest_sprint_speed.py under W11_RAW_WRITE_MODE); max(snapshot_date) wins latest.
    select * from read_parquet('{{ lakehouse_raw_loc("sprint_speed_raw") }}**/*.parquet', union_by_name=true)

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
        -- E11.1-W11: the raw mirror is written from a dtype=str CSV (ingest_sprint_speed reads every
        -- column as a string; the SF table coerced them to INTEGER/FLOAT on INSERT, so the old W4/W5
        -- snapshot was typed). Reading lakehouse_raw directly yields VARCHAR numerics → cast at the
        -- use-site (INC-23 pattern). try_cast → NULL on an empty/non-numeric string, matching SF's
        -- coercion (so `where sprint_speed_fts is not null` / `competitive_runs > 0` behave identically).
        try_cast(s.sprint_speed_fts as double)             as sprint_speed_fts,
        try_cast(s.competitive_runs as integer)            as competitive_runs,
        try_cast(s.hp_to_1b as double)                     as hp_to_1b_sec,
        try_cast(s.hp_to_2b as double)                     as hp_to_2b_sec,
        try_cast(s.age as integer)                         as age,
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
