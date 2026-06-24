-- E13.4 SILENT-DEGENERATE GUARD — Candidate B2 (bullpen-fatigue × short-leash).
--
-- Same lift-study-integrity contract as assert_tto_splits_xwoba_not_zeroed: a candidate
-- feature that silently collapses to a constant / all-zero / all-null column would record a
-- FALSE "no edge" in the incremental-lift study. B2 is a ratio
-- (bullpen_pitches_prev_3d / starter_avg_ip_last_3), so the classic `::numeric`=NUMBER(38,0)
-- scale-0 truncation footgun (the B1 TTO bug) — or an all-NULL avg_ip join, or a 0/0 collapse
-- — must fail loudly here, not flow into a verdict.
--
-- TWO failure modes (both return rows ⇒ fail), checked per season:
--   (1) VALUE collapse — the non-null interaction goes constant (stddev = 0) or near-zero
--       (mean < 1.0). A well-populated MLB season's mean bullpen-pitches-prev-3d is ~30–120
--       over a starter's ~5–6 IP, so the interaction's per-season MEAN sits in single-to-low-
--       double digits with strictly positive STDDEV.
--   (2) COVERAGE collapse — the interaction is NULL for ~the whole season while its PARENT
--       input (bullpen_pitches_prev_3d) is populated. This is the incremental-not-full-refreshed
--       signature (2026-06-23): an `incremental` model only repopulated the 7-day lookback, so the
--       new column was NULL across all history → the per-side LightGBM saw a constant column,
--       dropped it, and produced byte-identical (false-null) lift. The original test missed this
--       because it only inspected NON-NULL rows. We now compare output coverage to parent coverage:
--       if the parent is well-populated (>200 games) but the interaction covers <50% of those rows,
--       the feature is not built across the eval window and any lift verdict on it is INVALID.
--
-- Aggregate/grain check, so per-row early-season zeros (pen not yet used) can't trip it. Pairs with
-- the harness-side incremental_lift_eval.candidate_is_degenerate (which also now flags low
-- eval-set coverage) at eval time.

with per_side as (
    select game_year,
           home_bullpen_fatigue_short_leash as v,
           home_bullpen_pitches_prev_3d     as parent
    from {{ ref('feature_pregame_game_features') }}
    union all
    select game_year,
           away_bullpen_fatigue_short_leash as v,
           away_bullpen_pitches_prev_3d     as parent
    from {{ ref('feature_pregame_game_features') }}
),

by_season as (
    select
        game_year,
        count(parent) as parent_nonnull,
        count(v)      as v_nonnull,
        avg(v)        as v_mean,
        stddev(v)     as v_std
    from per_side
    group by game_year
)

select
    game_year,
    parent_nonnull,
    v_nonnull,
    round(v_mean, 4)                                       as avg_interaction,
    round(coalesce(v_std, 0), 4)                           as std_interaction,
    round(100.0 * v_nonnull / nullif(parent_nonnull, 0), 1) as pct_coverage_vs_parent
from by_season
where parent_nonnull > 200
  and (
        -- (2) COVERAGE collapse: parent populated but interaction barely/never built
        v_nonnull < 0.5 * parent_nonnull
        -- (1) VALUE collapse: built but constant / near-zero
        or v_mean < 1.0
        or coalesce(v_std, 0) = 0
      )
