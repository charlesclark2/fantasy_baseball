-- =============================================================================
-- mart_park_factors_granular.sql
-- Grain: one row per (venue_id, season)
-- Purpose: Expose EB-smoothed granular park factors (HR, 2B/3B, 1B, BB, SO,
--          wOBA) written by fit_granular_park_priors.py (Epic 3A.2).
--
-- Source: Baseball Savant statcast-park-factors, 3yr rolling, All bat sides.
-- All eb_* factor columns are ratios (1.0 = league average).
--
-- Leakage note: feature_pregame_park_features joins on game_year - 1, so a
-- 2026 game uses season=2025 EB estimates — same guard as mart_eb_park_factors.
-- =============================================================================

-- E11.1-W4 dual-branch (tag w4_lakehouse): the duckdb branch reads the
-- eb_park_factors_granular_raw S3 parquet written by the build-on-DuckDB path of
-- fit_granular_park_priors.py (`--s3`); the Snowflake branch is a thin view over the
-- lakehouse_ext external table. Value-identical (this mart is a pure projection).
{{ config(materialized='view', tags=['w4_lakehouse']) }}

{% if target.name == 'duckdb' %}

select
    venue_id,
    season,
    n_pa,

    -- ── Raw Savant factors (ratio; 1.0 = league average) ────────────────────
    raw_hr_factor,
    raw_doubles_triples_factor,
    raw_singles_factor,
    raw_bb_factor,
    raw_so_factor,
    raw_woba_factor,

    -- ── EB-smoothed factors ──────────────────────────────────────────────────
    eb_hr_factor,
    eb_doubles_triples_factor,
    eb_singles_factor,
    eb_bb_factor,
    eb_so_factor,
    eb_woba_factor,

    -- ── Shrinkage diagnostics ────────────────────────────────────────────────
    shrinkage_hr,
    shrinkage_doubles_triples,
    shrinkage_singles,
    shrinkage_bb,
    shrinkage_so,

    -- ── Prior params ────────────────────────────────────────────────────────
    prior_mean_hr,
    prior_variance_hr,
    prior_mean_doubles_triples,
    prior_variance_doubles_triples,

    fit_date,
    run_id

from read_parquet('{{ lakehouse_loc("eb_park_factors_granular_raw") }}**/*.parquet', union_by_name=true)

{% else %}

select * from baseball_data.lakehouse_ext.mart_park_factors_granular

{% endif %}
