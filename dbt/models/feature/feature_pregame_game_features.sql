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
{{ config(
    materialized='incremental',
    unique_key='game_pk',
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}

{%- set cc = contact_quality_columns() -%}

-- INC-19 DURABLE TYPE-PIN (2026-06-29): raw.* inherits the explicit ::double types
-- pinned in feature_pregame_game_features_raw's TYPE-PIN block, and each _seasonnorm
-- column is cast ::double here, so every FLOAT column of this public surface is
-- type-stable against any upstream NUMBER<->FLOAT drift. The _seasonnorm pin is
-- contract-checked by betting_ml/tests/test_type_contract_guard.py. ::double (not
-- ::float = 32-bit) is value-preserving and a no-op against the current table.
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
