-- =============================================================================
-- mart_eb_park_factors.sql
-- Grain: one row per (venue_id, season)
-- Purpose: Expose Empirical Bayes smoothed park run factors written by
--          betting_ml/scripts/eb_priors/fit_park_priors.py.
--
-- The source table is MERGE-upserted daily; this model is a thin passthrough
-- so the feature layer can reference it via ref() with no business logic here.
--
-- Leakage note: features join on game_year - 1 (see feature_pregame_park_features),
-- so a 2026 game uses the season=2025 EB estimate — same guard as the raw
-- park_run_factor_3yr it replaces.
-- =============================================================================

-- E11.1-W5 dual-branch lakehouse model (W4-deferred Group B). DuckDB branch reads the
-- eb_park_factors_raw S3 parquet (exported by scripts/export_w5_raw_to_s3.py); Snowflake
-- branch is a thin view over the lakehouse_ext external table. fit_park_priors.py KEEPS
-- its Snowflake MERGE-upsert into eb_park_factors_raw — this reads the one-time/opt-in S3
-- mirror. Thin passthrough, value-identical.
{{ config(materialized='view', tags=['w5_lakehouse']) }}

{% if target.name == 'duckdb' %}

select
    venue_id,
    season,
    eb_park_run_factor,
    eb_park_run_factor_uncertainty,
    n_games,
    raw_park_run_factor,
    shrinkage_factor,
    prior_mean,
    prior_variance,
    fit_date,
    run_id

from read_parquet('{{ lakehouse_loc("eb_park_factors_raw") }}**/*.parquet', union_by_name=true)

{% else %}

select * from baseball_data.lakehouse_ext.mart_eb_park_factors

{% endif %}
