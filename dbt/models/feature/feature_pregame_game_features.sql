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
-- ✅ E1.13 (2026-08-14) — THE E9.53 SEASONNORM NULL CURE IS APPLIED (was the "KNOWN
--    DEFECT / deferred to E1.12" block; E1.12 was renumbered E1.13).
--
-- The old bare `coalesce(..., 0)` could not distinguish two different things:
--   (a) a missing/zero-variance BASELINE  → z = 0 is CORRECT and intended ("an average,
--       regime-neutral matchup" — the documented Story 27.7 behaviour, KEPT); and
--   (b) a missing RAW FEATURE             → z = 0 was a FABRICATION ("exactly league
--       average" served in place of "we don't know").
-- The `case when raw.<c> is null then null else coalesce(...) end` form below carries the
-- real NULL through for (b) while keeping the coalesce-to-0 for (a). Consequences:
--   * a _seasonnorm column is now genuinely NULLABLE — a whole-block outage is visible in
--     it rather than masked (the E9.53 07-22..28 signature cannot recur invisibly). The
--     check_feature_block_coverage.py rule that probes RAW columns only remains correct
--     and unchanged (raw stays the sharper detector).
--   * predict_today's discriminative_coverage now counts a genuinely-missing core
--     _seasonnorm feature as imputed (feature_columns_v6_total_runs_pre_lineup_served.json
--     carries 3 _seasonnorm of its 7 core features) ⇒ the is_degraded rate RISES.
--     Re-baseline it after the --full-refresh rebuild.
--   * This is a HISTORICAL correction (every row whose raw was absent, all seasons), so
--     the rebuild must be --full-refresh, NOT an incremental lookback.
-- Train/serve note: the v6 champion pickles were fit on data where these rows carried the
-- fabricated 0.0; the served NULL now routes through the imputer. The E1.13 revalidation
-- measured the exposure + ran the §0.5 retrain-vs-incumbent decision (see
-- ablation_results/e1_13_injury_seasonnorm_revalidation.md).
-- Parity of the two copies is enforced by betting_ml/tests/test_w8b_wrapper_seasonnorm_parity.py.
select
    raw.*,
    {%- for c in cc %}
    (case when raw.{{ c }} is null then null
        else coalesce(
            (raw.{{ c }} - b.{{ c }}__mu) / nullif(b.{{ c }}__sd, 0),
            0
        )
    end)::double as {{ c }}_seasonnorm{{ "," if not loop.last }}
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
