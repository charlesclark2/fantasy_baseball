-- ncaaf_freshman_priors — the P1.2b per-recruit freshman-production prior.
--
-- GRAIN: one row per (player_id, arrival_season) — a bridged recruit and their leakage-safe
-- projected first-college-season production, fit from recruiting rating on STRICTLY-PRIOR
-- classes. This is the true-freshman feature P1.3 uses to fill the gap where a player has no
-- prior college snaps.
--
-- ⚠️ NOT COMPUTED IN dbt. A read-only view over the parquet that
-- `models/run_freshman_projection.py` writes to the lake (`ncaaf/derived/freshman_priors`).
-- The estimator is a §0.5 bake-off (partial-pooling / stratified-OLS / GBM / null-floor) under
-- leave-one-class-out expanding-window CV — not expressible in SQL and should not be.
--
-- 🚨 BUILD ORDER (the INC-25 lesson, exactly as P1.2): the P1.1 marts + ncaaf_recruit_production_
-- pairs must be built, THEN run_freshman_projection.py, THEN this view. Building it in the same
-- pass that produces its inputs serves the previous run's priors. Excluded from the default
-- build via the `ncaaf_p1_2b` tag until the script has run once.
--
-- ⚠️ UNCERTAINTY SEMANTICS: `projected_production_z_sd` is PARAMETER uncertainty (a RELATIVE
-- confidence signal), NOT a calibrated predictive interval — a pricing consumer MUST recalibrate
-- on held-out data. Use `projected_production_z` as a POINT feature and the sd for ranking only.
--
-- ⚠️ `box_production_available = false` (OL / special teams): a rating-only prior — those
-- positions log no box stat line, so the projection is a talent signal, NOT a validated
-- production projection. Do not treat it as equivalent to a skill-position prior.
{{ config(materialized='table', tags=['ncaaf_p1_2b']) }}

with src as (
    select * from {{ ncaaf_delta('freshman_priors', tier='derived') }}
)

select
    'ncaaf'                                              as sport,
    player_id,
    recruit_name,
    arrival_season,
    arrival_team,
    arrival_season || '-' || player_id                  as recruit_prior_key,   -- grain contract

    position_group,
    recruit_position,
    stars,
    composite_rating,
    national_ranking,

    -- ⭐ the feature: projected first-season production, standardized within (group, class)
    projected_production_z,
    projected_production_z_sd,               -- PARAMETER uncertainty — relative confidence only
    box_production_available,                -- false ⇒ rating-only prior (OL / ST), not validated
    is_true_freshman_prior,

    -- provenance: how many strictly-prior classes the map was fit on (down-weight a thin one)
    n_prior_classes,
    n_prior_pairs,
    model_version

from src
