-- ncaaf_nfl_rookie_projections — the NCAAF-P1A college→NFL translation output (the NFL feeder).
--
-- GRAIN: one row per NFL player (`gsis_id`) — their leakage-safe projected early-career NFL
-- outcome, translated from their PRE-DRAFT college body of work + combine + recruiting pedigree,
-- fit on STRICTLY-PRIOR draft classes. This is the feeder the NFL vertical consumes: N1.2 (rookie
-- prop pricing) and N1.3 / fantasy-dynasty boards, a market that is otherwise priors-only.
--
-- ⚠️ NOT COMPUTED IN dbt. A read-only view over the parquet that
-- `models/run_college_nfl_translation.py` writes to the lake (`ncaaf/derived/nfl_rookie_projections`).
-- The estimator is a §0.5 bake-off (partial-pooling / stratified-OLS / GBM / null-floor, with a
-- draft-slot benchmark) under leave-one-draft-class-out expanding-window CV — not expressible in
-- SQL and should not be.
--
-- 🚨 BUILD ORDER (the INC-25 lesson): the P1.1 marts + xref + ncaaf_draft_college_production_pairs
-- must be built, THEN run_college_nfl_translation.py, THEN this view. Building it in the same pass
-- that produces its inputs serves the previous run's projections. Excluded from the default build
-- via the `ncaaf_p1a` tag until the script has run once.
--
-- ⚠️ UNCERTAINTY SEMANTICS: `projected_nfl_z_sd` is PARAMETER uncertainty (a RELATIVE confidence
-- signal), NOT a calibrated predictive interval — N1.2 (pricing) MUST recalibrate on held-out data
-- (the E13.6 pattern). Use `projected_nfl_z` as a POINT prior and the sd for ranking only.
--
-- ⚠️ box_production_available = false (OL / specialists): a combine/pedigree-only projection — those
-- positions log no college box stat line, so it is a talent signal, NOT a validated production
-- projection. is_udfa = true: no NFL-outcome training label — a college-only projection, lower conf.
-- best_alpha = 0 — a prior feeding the NFL vertical, NOT an edge claim.
{{ config(materialized='table', tags=['ncaaf_p1a']) }}

with src as (
    select * from {{ ncaaf_delta('nfl_rookie_projections', tier='derived') }}
)

select
    'ncaaf'                                              as sport,
    gsis_id,                                             -- ⭐ the NFL-vertical join key
    college_athlete_id,
    player_name,
    gsis_id                                             as nfl_rookie_projection_key,  -- grain contract

    position_group,
    nfl_position,
    college,
    draft_year,
    draft_overall,
    draft_round,
    is_udfa,
    match_confidence,

    -- ⭐ the feeder output: projected early-career NFL outcome, standardized within (position, class)
    projected_nfl_z,
    projected_nfl_z_sd,                      -- PARAMETER uncertainty — relative confidence only
    target_metric,                           -- which NFL outcome was translated to (default w_av)
    box_production_available,                -- false ⇒ combine/pedigree-only (OL / ST), not validated
    has_college_prod,                        -- false ⇒ no P1.1 college production bridged (thin join)

    -- provenance: how many strictly-prior classes the map was fit on (down-weight a thin one)
    n_prior_classes,
    n_prior_pairs,
    model_version

from src
