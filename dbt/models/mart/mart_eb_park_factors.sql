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

{{ config(materialized='table') }}

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

from {{ source('betting', 'eb_park_factors_raw') }}
