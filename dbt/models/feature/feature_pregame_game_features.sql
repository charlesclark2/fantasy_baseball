-- =============================================================================
-- feature_pregame_game_features.sql
-- Grain: one row per game_pk (regular season games only)
-- Purpose: Master pre-game ML feature surface (public name — direct ML input,
--          read by training, prod predict_today, the app and the pipeline).
--
-- Story 27.7: this model is now a THIN wrapper. The heavy assembly lives in
-- feature_pregame_game_features_raw; here we pass every raw column through
-- UNCHANGED and ADD a season-normalized version of each contact-quality
-- feature (suffix `_seasonnorm`). Splitting the assembly out keeps the public
-- name + every existing consumer stable while computing the expensive as-of
-- joins exactly once.
--
-- Season-normalization (the contact->runs CONVERSION regime fix, Story 27.6/27.7):
--   <col>_seasonnorm = (raw <col> - asof league mean) / asof league std
-- where the mean/std come from feature_league_contact_baseline — a STRICTLY-
-- PRIOR, AS-OF current-season league baseline (no same-day/future leakage),
-- shrunk toward the prior season early. Raw columns are RETAINED so the raw vs
-- normalized contracts can be compared. NULL/zero-variance baselines coalesce
-- the z-score to 0 (an average, regime-neutral matchup).
-- =============================================================================

-- E11.9-T2 — incremental, mirroring feature_pregame_game_features_raw. This thin
-- wrapper passes raw.* through and adds the _seasonnorm columns; both the upstream
-- _raw and this wrapper are rebuilt together by every feature-rebuild op, so the
-- same N-day window keeps the served slate (today + recent) fresh. delete+insert
-- by game_pk; weekly full-refresh net corrects drift.
-- E11.1-W8b (serving-aggregator wave): dual-branch. DuckDB branch (real compute → S3,
-- run_w1_lakehouse special-cases this macro/for-loop model in a Python builder — extract_duckdb_sql
-- can't render the contact_quality_columns() loop) reads the migrated feature_pregame_game_features_raw
-- + feature_league_contact_baseline (registered DuckDB views). The Snowflake (else) branch MERGEs from
-- the lakehouse_ext external table; at cutover the operator DROPs+rebuilds this incremental (it inherits
-- the raw's home_win_rate_trailing_3yr NUMBER→FLOAT flip via raw.*). The _seasonnorm ::double pin is
-- preserved in the DuckDB branch (test_type_contract_guard.py::test_public_wrapper_pins_seasonnorm_double).
{% if target.name == 'duckdb' %}

{{ config(
    materialized='incremental',
    unique_key='game_pk',
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns',
    tags=['w8b_lakehouse']
) }}

{%- set cc = contact_quality_columns() -%}

-- INC-19 DURABLE TYPE-PIN (2026-06-29): raw.* inherits the explicit ::double types
-- pinned in feature_pregame_game_features_raw's TYPE-PIN block, and each _seasonnorm
-- column is cast ::double here, so every FLOAT column of this public surface is
-- type-stable against any upstream NUMBER<->FLOAT drift. The _seasonnorm pin is
-- contract-checked by betting_ml/tests/test_type_contract_guard.py. ::double (not
-- ::float = 32-bit) is value-preserving and a no-op against the current table.
-- 🩸 KNOWN DEFECT — A MISSING RAW FEATURE IS SERVED AS A FABRICATED 0.0.
--    Diagnosed by E9.53 (2026-07-30); the FIX IS DEFERRED TO E1.12, which retrains.
--    ⛔ Do NOT "fix" this in isolation — see the retrain requirement at the bottom.
--
-- The bare `coalesce(..., 0)` below cannot distinguish two different things:
--   (a) a missing/zero-variance BASELINE  → z = 0 is CORRECT and intended ("an average,
--       regime-neutral matchup" — the documented behaviour, keep it); and
--   (b) a missing RAW FEATURE             → z = 0 is a FABRICATION. It means "exactly
--       league average", a perfectly plausible value, served in place of "we don't know".
--
-- Two live consequences measured in E9.53, both currently backstopped elsewhere:
--   * The _seasonnorm column reads 100% NOT-NULL straight through a TOTAL outage of its
--     own block, while its raw twin reads 100% NULL. That is why the 2026-07-22..28
--     team_sequential outage LOOKED like the raw and _seasonnorm columns came from
--     different paths (the INC-31 mirror shape) — they do not; THIS COALESCE IS THE
--     ENTIRE DIFFERENCE. ⇒ a not-null-rate coverage probe on a _seasonnorm column can
--     never detect anything; check_feature_block_coverage.py REFUSES to be configured
--     with one, and asserts on the RAW columns instead.
--   * predict_today's discriminative_coverage counts imputed CORE features from the
--     pre-imputation matrix, and _seasonnorm variants of core discriminative blocks ARE
--     in the served contracts — feature_columns_v6_total_runs_pre_lineup_served.json
--     carries away_bp_eb_xwoba_seasonnorm + away_team_sequential_bullpen_xwoba_seasonnorm
--     + home_bp_eb_xwoba_seasonnorm = 3 of its 7 core features. A never-NULL column can
--     never be flagged imputed, so it only ever DILUTES that denominator: a total
--     bullpen_eb / team_sequential outage is invisible to is_degraded on that model.
--     ⇒ until E1.12, the store-level per-DATE check in check_feature_block_coverage.py is
--     the detector for this class, NOT discriminative_coverage.
--
-- WHY THE FIX NEEDS E1.12 (a retrain), not a one-line edit: emitting NULL here changes a
-- SERVED model input. The champion pickles were fit on data where these rows carried 0.0;
-- flipping to NULL routes them through the imputer instead. The shift is small (0 is the
-- mean of a z-score) but it is a train/serve change, so it belongs with the retrain that
-- re-fits on an honestly-NULL store. E1.12 should: (1) apply the `case when raw.<c> is
-- null then null else coalesce(...) end` form HERE **and** in the byte-equivalent Python
-- port `scripts/run_w1_lakehouse.py::_game_features_wrapper_sql` (that port, not this
-- file, is what builds the SERVED parquet — see the ⚠️ note there), (2) rebuild the store,
-- (3) retrain, and (4) re-baseline the is_degraded rate, which will rise once genuinely
-- missing core features stop being counted as present.
-- Parity of the two copies is enforced by betting_ml/tests/test_w8b_wrapper_seasonnorm_parity.py.
select
    raw.*,
    {%- for c in cc %}
    coalesce(
        (raw.{{ c }} - b.{{ c }}__mu) / nullif(b.{{ c }}__sd, 0),
        0
    )::double as {{ c }}_seasonnorm{{ "," if not loop.last }}
    {%- endfor %}
from {{ ref('feature_pregame_game_features_raw') }} raw
left join {{ ref('feature_league_contact_baseline') }} b
    on  b.game_year = raw.game_year
    and b.game_date = raw.game_date
{% if is_incremental() %}
-- E11.9-T2 — match the _raw incremental scope so we only re-derive _seasonnorm for
-- the games _raw re-materialized this run.
where raw.game_date::date >= dateadd('day', -{{ var('pregame_incremental_lookback_days', 7) }}, current_date)
{% endif %}

{% else %}

-- E11.24 TARGET-6 SUCCESSOR (2026-08-08) — incremental → VIEW, in lockstep with the _raw model
-- it wraps (see the full rationale there). On Snowflake this branch is a pure COPY of its own
-- external table — the _seasonnorm derivation runs in the DuckDB branch — so a `delete+insert`
-- incremental here is a temp CTAS + DELETE + INSERT per intraday tick that RESUMES COMPUTE_WH,
-- where `create or replace view` is metadata-only.
--
-- CONTENT-NEUTRAL, MEASURED 2026-08-08 on MONITOR_WH: 26,969 = 26,969 rows with zero game_dates
-- differing in count, and 790 = 790 columns with zero data_type mismatches. The two models MUST
-- move together — leaving the wrapper an incremental over a view-ified _raw would keep the exact
-- write this flip removes, on the one of the pair every serving reader actually names.
{{ config(materialized='view') }}

select * from baseball_data.lakehouse_ext.feature_pregame_game_features

{% endif %}
