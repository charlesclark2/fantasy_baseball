-- E13.4 SILENT-DEGENERATE GUARD — Candidate B2 (bullpen-fatigue × short-leash).
--
-- Same lift-study-integrity contract as assert_tto_splits_xwoba_not_zeroed: a candidate
-- feature that silently collapses to a constant / all-zero / all-null column would record a
-- FALSE "no edge" in the incremental-lift study. B2 is a ratio
-- (bullpen_pitches_prev_3d / starter_avg_ip_last_3), so the classic `::numeric`=NUMBER(38,0)
-- scale-0 truncation footgun (the B1 TTO bug) — or an all-NULL avg_ip join, or a 0/0 collapse
-- — must fail loudly here, not flow into a verdict.
--
-- A well-populated MLB season's mean bullpen-pitches-prev-3d is ~30–120 over a starter's
-- ~5–6 IP, so the interaction's per-season MEAN sits comfortably in single-to-low-double
-- digits and its STDDEV is strictly positive. This test returns rows (fails) whenever a season
-- with a real sample collapses toward zero (mean < 1.0) or goes constant (stddev = 0) — for ANY
-- root cause. Aggregate/grain check, so per-row early-season zeros (pen not yet used) can't trip
-- it. Pairs with the harness-side incremental_lift_eval.candidate_is_degenerate at eval time.

with unioned as (
    select game_year, home_bullpen_fatigue_short_leash as v
    from {{ ref('feature_pregame_game_features') }}
    union all
    select game_year, away_bullpen_fatigue_short_leash as v
    from {{ ref('feature_pregame_game_features') }}
)

select
    game_year,
    count(v)                  as non_null_rows,
    round(avg(v), 4)          as avg_interaction,
    round(stddev(v), 4)       as std_interaction
from unioned
where v is not null
group by game_year
having count(v) > 200
   and (avg(v) < 1.0 or coalesce(stddev(v), 0) = 0)
