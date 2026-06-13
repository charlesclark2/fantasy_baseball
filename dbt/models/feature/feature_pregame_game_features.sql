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

{{ config(materialized='table') }}

{%- set cc = contact_quality_columns() -%}

select
    raw.*,
    {%- for c in cc %}
    coalesce(
        (raw.{{ c }} - b.{{ c }}__mu) / nullif(b.{{ c }}__sd, 0),
        0
    ) as {{ c }}_seasonnorm{{ "," if not loop.last }}
    {%- endfor %}
from {{ ref('feature_pregame_game_features_raw') }} raw
left join {{ ref('feature_league_contact_baseline') }} b
    on  b.game_year = raw.game_year
    and b.game_date = raw.game_date
