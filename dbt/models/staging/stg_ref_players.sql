-- =============================================================================
-- stg_ref_players.sql
-- Grain: one row per MLB player (mlb_bam_id)
-- Purpose: the player-name dimension the duckdb-built mart_pitch_hitter_profile /
--          mart_pitch_pitcher_profile join for names.
--
-- ⭐ E5.10 FOLLOW-UP (this story) — WHERE THE DUCKDB PARQUET NOW COMES FROM.
--    This model's parquet used to be a one-shot MANUAL mirror of
--    `baseball_data.savant.ref_players` (scripts/export_ref_players_to_s3.py, "run ONCE"),
--    scheduled by nothing. It sat 53 days stale holding ZERO 2026 players and a serving
--    writer silently skipped 34 batters.
--
--    Measured while fixing it: the SNOWFLAKE SOURCE IS ITSELF DEAD — savant.ref_players has
--    NO writer anywhere in the repo and reports last_altered = 2025-10-13 (~308 days) with
--    max(mlb_played_last) = 2025. So the parquet was a faithful mirror of a dead table, and
--    merely SCHEDULING the old export would have refreshed an mtime over frozen content.
--
--    The `stg_ref_players/` prefix is now written by scripts/build_ref_players_dimension.py,
--    which layers the LIVE `player_profiles_raw` feed (weekly ingest + daily S3 mirror leaf)
--    over the frozen historical export (relocated to `stg_ref_players_archive/`). The two are
--    complementary: measured across all Statcast history, the archive misses 0 pre-2020
--    debutants while live misses 471; live misses 4 of the 1,751 2020+ players while the
--    archive misses 208. Column contract below is UNCHANGED so no consumer moved.
--
-- ⚠️ THE SNOWFLAKE BRANCH BELOW STILL READS THE DEAD SOURCE, deliberately and harmlessly:
--    both consuming marts are `enabled=(target.name == 'duckdb')` (E11.20 phase 1.5) and no
--    other dbt model refs this one, so the Snowflake branch has no consumer. It is kept as the
--    source definition rather than deleted. ⛔ DO NOT add a Snowflake-target consumer without
--    repointing this branch — it would serve 2025-vintage names.
-- =============================================================================

{% if target.name == 'duckdb' %}

{{ config(materialized='view') }}

-- Read-through view over the merged dimension parquet
-- (output of scripts/build_ref_players_dimension.py — live feed over frozen archive).
select
    mlb_bam_id,
    first_name,
    last_name,
    player_name,
    mlb_played_first,
    mlb_played_last
from read_parquet('{{ lakehouse_loc("stg_ref_players") }}**/*.parquet', union_by_name=true)

{% else %}

{{ config(materialized='table') }}

select
    mlb_bam_id,
    first_name,
    last_name,
    player_name,
    mlb_played_first,
    mlb_played_last
from {{ source('savant', 'ref_players') }}

{% endif %}
