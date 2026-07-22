-- ncaaf_team_freshman_prior — the P1.2b freshman prior rolled up to the P1.3 join grain.
--
-- ⭐ THE P1.3 JOIN CONTRACT. GRAIN: one row per (season, team). The per-recruit prior is a
-- PRE-SEASON constant (it prices players with no snaps), so it is emitted here at (season, team)
-- and P1.3 BROADCASTS it to every `as_of_week` of that season by joining on
--     (season = arrival_season, team = arrival_team)
-- to its (season, team, as_of_week) feature matrix. `team_season_key` = `<season>-<team>` is the
-- grain contract. A team with NO bridged incoming class is simply ABSENT — P1.3 LEFT JOINs and
-- reads the absence as zero projected freshman contribution (NOT unknown; a class with no bridged
-- recruits genuinely projects nothing measurable here).
--
-- ⚠️ NOT COMPUTED IN dbt — a read-only view over `ncaaf/derived/team_freshman_prior`, written by
-- run_freshman_projection.py alongside the per-recruit priors. Same INC-25 build-order + the
-- `ncaaf_p1_2b` tag as ncaaf_freshman_priors.
{{ config(materialized='table', tags=['ncaaf_p1_2b']) }}

with src as (
    select * from {{ ncaaf_delta('team_freshman_prior', tier='derived') }}
)

select
    'ncaaf'                                              as sport,
    season,
    team,
    season || '-' || team                               as team_season_key,      -- grain contract

    n_incoming_freshmen,
    -- ⭐ the team-level features (all projected, pre-season, leakage-safe)
    freshman_class_projected_production,        -- Σ projected_production_z over the incoming class
    freshman_class_avg_projected_production,    -- mean over the class
    freshman_class_top_projected_production,    -- the single highest-projected freshman
    freshman_class_avg_rating,                  -- mean 247 composite of the incoming class
    blue_chip_count,                            -- incoming freshmen with stars >= 4

    model_version

from src
