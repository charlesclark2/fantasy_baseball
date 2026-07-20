-- ncaaf_team_strength_week — the P1.2 team-strength posterior, week by week.
--
-- GRAIN: one row per (season, team_id, as_of_week) — the SAME grain as
-- rollup_ncaaf_team_week_asof, so P1.3 joins the two on `team_week_key` with no reshaping.
--
-- ⭐ WHAT THIS IS: a hierarchical partial-pooling estimate of how many points better than an
-- average FBS team each team was BEFORE week `as_of_week` kicked off, with honest posterior
-- uncertainty. Team is nested in conference, so a thin or lopsided sample is shrunk toward
-- its conference mean instead of being trusted at face value — the thing CFB's sparse
-- cross-conference schedule makes mandatory.
--
-- ⚠️ THIS MODEL IS NOT COMPUTED IN dbt. It is a read-only view over the parquet that
-- `models/run_team_strength.py` writes to the lake (`ncaaf/derived/team_strength_week`).
-- The estimator is an iterative mixed-effects fit — ~200 leakage-safe refits with a
-- variance-component optimization each — which is not expressible in SQL and should not be.
--
-- 🚨 BUILD ORDER (the INC-25 lesson, and it applies here exactly):
--     dbt run (P1.1 marts)  →  run_team_strength.py  →  dbt run (this model)
-- This model reads a parquet that a script DOWNSTREAM of the dbt build produces. If it is
-- built in the same pass that produces its inputs, it serves the PREVIOUS run's strengths —
-- a silent one-slate staleness, which is precisely how INC-25 took serving down. Whatever
-- orchestrates this must rebuild the parquet BEFORE materializing this model, in the same
-- run. Until the script has been run once, this model has nothing to read and is excluded
-- from the default build via the `ncaaf_p1_2` tag.
--
-- 🚨 SIGN CONVENTION: `strength_offense` and `strength_defense` are BOTH higher-is-better
-- (defense = points PREVENTED). A team's net strength is their SUM, not their difference.
-- `strength_offense - strength_defense` returns ~0 for every team and is the mistake this
-- comment exists to prevent. Use `strength_margin`.
--
-- NULLS: `strength_margin` is never NULL, including at as_of_week 1 where no game has been
-- played — a zero-game row is a legitimate PRESEASON POSTERIOR (conference level + the
-- pre-season covariates) carrying an honestly large `strength_margin_sd`. That is the
-- difference between this and rollup_ncaaf_team_week_asof, whose week-1 row is correctly
-- all-NULL: a rollup of nothing is unknown, a posterior with no data is the prior.
--
-- ⚠️ `hyper_n_prior_seasons` = how many prior seasons the shrinkage was calibrated on. The
-- FIRST emitted season has only one and is measurably weaker; it is disclosed here rather
-- than buried so a consumer can down-weight or drop it.
{{ config(materialized='table', tags=['ncaaf_p1_2']) }}

with src as (
    select * from {{ ncaaf_delta('team_strength_week', tier='derived') }}
)

select
    'ncaaf'                                              as sport,
    season,
    team_id,
    team,
    conference,
    as_of_week,                       -- ⭐ season_order_week, never CFBD's raw `week`
    season || '-' || team_id || '-w' || as_of_week       as team_week_key,

    -- ── sample backing this row ──────────────────────────────────────────────────────
    games_in_window,
    has_sufficient_sample,

    -- ── ⭐ the feature: neutral-field points above an average FBS team ───────────────
    strength_margin,
    strength_margin_sd,

    -- the three additive pieces of strength_margin (they sum to it exactly)
    strength_conference_component,    -- the pooling level: how strong the conference is
    strength_covariate_component,     -- what the PRE-SEASON covariates say
    strength_team_component,          -- what THIS season's games add on top

    -- pre-season covariate contribution by group — this is what makes the roster/portal
    -- signal auditable rather than a black box
    covariate_component_carryover,
    covariate_component_talent,
    covariate_component_roster_flux,
    covariate_component_coaching,
    -- what the model pays for NOT KNOWING a covariate (the `_missing` indicators). Kept
    -- SEPARATE from the four real groups on purpose: folding missingness into e.g.
    -- roster_flux made first-year FBS transition programs (whose covariates are simply
    -- absent) look like the biggest roster movers in the league.
    covariate_component_unknown,

    -- ── scoring decomposition (for totals; see the sign convention above) ────────────
    strength_offense,
    strength_offense_sd,
    strength_defense,
    strength_defense_sd,
    league_base_points,

    -- ── fit provenance ───────────────────────────────────────────────────────────────
    home_field_advantage,
    residual_sigma,
    tau_team,
    tau_conference,
    hyper_seasons,
    hyper_n_prior_seasons,
    hyper_n_games,
    model_version

from src
