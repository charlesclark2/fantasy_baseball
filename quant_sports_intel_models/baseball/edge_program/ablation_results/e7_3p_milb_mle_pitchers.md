# MLB Edge-E7.3p — PITCHER MiLB → MLB translation factors (MLEs) — PRE-REGISTRATION

**Model:** `milb_mle_pitcher_v1` · **status:** ⏳ harness code-complete, pre-registered 2026-07-27 —
**awaiting the operator's real S3 run** (`run_milb_mle_pitchers.py` OVERWRITES this file with the
real leaderboards/verdicts when it completes).

> ⚠️ **This is an MLB-equivalent PRIOR/projection, not an edge claim** (`best_alpha = 0`). The
> pitcher sibling of the E7.3 batter MLE — the SAME shared harness (`milb_mle.py` +
> `betting_ml/utils/hierarchical.py`), a pitcher config on top. Uncertainty is PARAMETER
> uncertainty; the starter-EB wiring story (the E7.5 pitcher sibling) MUST recalibrate before
> pricing (E13.6).

## Pre-registered design (fixed BEFORE the real-data run)

**Grain:** one row per (pitcher, level) — the pre-debut MiLB pitching line at a level (strictly
before the MLB debut date, the as-of guard), joined to the realized early-career MLB line
(TBF-weighted over the first 2 MLB seasons, `min_mlb_tbf=150`). `debut_cohort` = first MLB season =
the CV fold unit. `minor_pa` = TBF (`min_minor_pa=150` floor). Prospects (no debut) are emitted
flagged, never trained on.

**Metrics (each its OWN bake-off, per-TBF):**

| metric | minor feature (E7.1 box / E7.2 statcast) | MLB label | prior expectation |
|---|---|---|---|
| `k_pct` | SO/TBF | mart per-game sums, SO/TBF | STRONG (whiff/command is stable — E7.3 batter K% corr 0.64) |
| `bb_pct` | BB/TBF | mart per-game sums, BB/TBF | STRONG |
| `hr_rate` | HR/TBF | mart per-game sums, HR/TBF | noisy/weak (HR outcomes are BABIP-adjacent) |
| `gb_pct` | ground-OUT share GO/(GO+AO) — all the box offers | Statcast GB/BIP (`stg_batter_pitches`) — ⚠️ CROSS-DEFINITION, the regression learns the rescale | moderate (batted-ball tilt is a stable skill; the proxy may cost signal) |
| `xwoba_against` | E7.2 AAA-Statcast summary ONLY (AAA 2022+; few cohorts → honest skip allowed) | mart TBF-weighted xwOBA-against | weakest / possibly null (the run-value composite — E7.3's wOBA precedent) |

**Candidates (every config counts toward PBO/DSR):** `partial_pool@{2.0,4.0}` (the shared
mixed-effects solver — per-LEVEL intercept+slope, per-LEAGUE intercept, boundary-avoiding Gamma(2,·)
tau + multi-start, the E7.3-proven lead) · `multiplicative` (EB-shrunk Davenport/James
level×league factor foil) · `gbm@{300-2-0.03, 500-3-0.02}(+sc)` (reads the AAA stuff/velo/spin adds
+ `minor_start_share` role feature, impute-flagged) · `level_mean` NULL FLOOR · reported-not-
selectable: `identity_no_translation` + `archetype_prior` (the generic prior a rookie starter gets
today — the thing to beat).

**Selection:** leave-one-MLB-debut-cohort-out expanding-window CV on held-out MAE of the raw MLB
rate; PBO<0.2 / DSR≥0.95 reported honestly (E2.1-r — robust-but-weak is a VALID feeder);
oracle-floor sanity enforced.

**Deliverables:** per-(pitcher, level) MLB-equivalent line + parameter sd →
`baseball/milb/derived/mle_projections_pitchers` (the E8.0 board's pitcher column) + the documented
starter-EB rookie-prior path (report §3, written by the runner).

## Synthetic harness smoke (2026-07-27, planted-signal — NOT real data)

All 5 metrics ran end-to-end on a synthetic universe: gates green, winner beat the level-mean null
on every metric with a planted translation, oracle floor held, data-thin skip path exercised.
Fast-gate tests: `betting_ml/tests/test_milb_mle_pitcher.py` (13) — incl. the variance-collapse
pinning, cohort-leakage tamper pair, and a batter-defaults regression guard (E7.3/E7.5 untouched).

## ⏭️ Operator run-order (real data — see the session handoff)

1. `uv run python -m betting_ml.scripts.milb_mle.build_graduated_pairs_pitchers --season-floor 2015 --s3`
2. `uv run python -m betting_ml.scripts.milb_mle.run_milb_mle_pitchers --pairs quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3p_artifacts/mle_graduated_pairs_pitchers.parquet --s3`
