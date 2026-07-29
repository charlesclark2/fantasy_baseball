# MLB Edge-E7.9 — retrain bake-off: CONSOLIDATED VERDICT (all targets/tiers)

> ⚠️ **Not an edge claim.** `best_alpha = 0`. Operator runs 2026-07-28, laptop, S3-native matrix (11,858 rows × 792 cols, 2021-04-18 → 2026-07-27).

## **ALL THREE: `INCUMBENT_STANDS`.** No champion changes ⇒ E7.9 step 7 (historical prediction
backfill) **never fires** — no re-score, no touching the `model_version` pin, live history untouched.

| target / tier | arms | leader | margin (floor 0.02) | PBO | DSR (≥0.95) | verdict |
|---|---:|---|---:|---:|---:|---|
| run_diff / pre_lineup | 24 | `plus_eb::glm_elasticnet` | +0.0053 ❌ | 0.000 | 0.218 | INCUMBENT_STANDS |
| run_diff / post_lineup | 24 | `plus_eb::glm_elasticnet` | +0.0127 ❌ | 0.000 | 0.724 | INCUMBENT_STANDS |
| total_runs / post_lineup | 28 | `plus_both::glm_elasticnet` | +0.0206 ✅ | 0.000 | 0.842 | INCUMBENT_STANDS |

Oracle-floor sanity (E2.1-r) passed on all three — no candidate beat an oracle that sees the target,
so the selection metric is not inverted.

## ⚠️ The margin is mostly the LEARNER, not the features

Decomposing each leader against the SAME learner on the incumbent contract:

| target / tier | total margin | learner swap (ngboost→glm) | contract |
|---|---:|---:|---:|
| total_runs / post_lineup | +0.0206 | +0.0153 (74%) | +0.0053 |
| run_diff / post_lineup | +0.0127 | +0.0068 (53%) | +0.0059 |
| run_diff / pre_lineup | +0.0053 | +0.0041 (77%) | +0.0012 |

⚠️ **Read the margin correctly.** The gate compares leader-arm vs incumbent-arm, so it CONFLATES the
contract change with the learner-class change. `+0.0206` on total_runs is NOT 'the features bought
0.0206' — 74% of it is `ngboost_normal → glm_elasticnet`, which E7.9 was not chartered to change.
A future harness revision should report the variant effect holding the learner fixed, in-report.

## The two feature findings, holding learner fixed

**`eb_gb_pct` (the E7.9 join) — CLEAN NULL, target-dependent sign.** Weakly POSITIVE for total_runs
(6 of 7 learners, max +0.0073) and NEGATIVE for run_diff (all 6 learners, post_lineup). The sign flip
is mechanistically sensible — ground-ball rate suppresses home runs, which moves a TOTAL more than a
DIFFERENTIAL — but every magnitude is ≤ a quarter of the noise floor. **E7.3p's −23% cold-start MAE
lift on GB% itself is real; it does NOT propagate to game-level skill.** The join was still correct to
build: the lift had to be given a path to a prediction before the null could be attributed to the
feature rather than to missing plumbing.

**`plus_eb` (the MiLB-MLE-corrected EB block) — the stronger of the two, still sub-threshold.**
Clearly positive for total_runs (+0.0373 xgboost, +0.0259 catboost, +0.0107 ngboost), mixed for
run_diff. Same mechanism: batter K%/BB%/ISO and starter K%/BB% are rate stats that predict RUNS
SCORED, whereas run differential is largely absorbed by `elo_diff` / `pythagorean_win_exp_diff`,
which the incumbent contract already carries.

## PM adjudication (second read, 2026-07-29) — binding

All 8 second-read questions were ruled. **No verdict changed and nothing was re-fit.** Two in-session
fixes were applied; everything else is record-and-defer:

- **Q1 (applied)** — the margin-attribution section above was added to every recorded report, derived
  from the stored arm table. The **gate is unchanged** ("is any (contract × learner) configuration
  better?" is the right promotion question); only the reporting was defective. A re-run with a
  learner-fixed gate was explicitly **declined** — the feature effects are all sub-floor, so a
  cleaner gate returns the same nulls at hours of cost.
- **Q2 (applied, FORWARD-DATED)** — pre-registration amendment #1 (2026-07-29) replaces the
  misspecified `1e-9` calibration tolerance with `max(1e-3, 10% of the incumbent's PIT-KS)`,
  **effective for the NEXT run**. E7.9's three 2026-07-28 verdicts stand exactly as scored; a guard
  test fails if the amendment ever retro-applies, and any future run that passes *only* because of
  it must say so in its own report.
- **Q3 — PARK** total_runs/post_lineup for a natural auto-retest as folds accrue; no powered story
  today. Re-tests together with Q4 if totals-calibration is prioritized.
- **Q4 — NOTE ONLY, do not act.** Any future learner re-selection must select on the
  calibration/pricing metric, fully deflated, **not** on CRPS (E2.1-r: NGBoost was chosen to price).
- **Q5 — closed** as a clean null; lesson recorded in `sport_data_platform.md`.
- **Q6 — keep** `eb_gb_pct` in the feature block.
- **Q7 — do not build** the old-prior counterfactual; the analytical bound stands as the record.
- **Q8 — `home_win` deliberately out of scope**, deferred; the harness is not extended to
  classification. Ties to Q6: home_win's next natural retrain *is* that test. A known deferred gap,
  not a coverage failure.

## Pre-registered follow-ups (NOT acted on here — post-hoc action is the overfit move)

1. **A learner re-bake-off.** `glm_elasticnet` beats the incumbent `ngboost_normal` on ALL THREE
   targets with equal-or-better PIT-KS. E1.9 chose NGBoost for these; the matrix has since changed
   (de-leak swaps, 11,858 rows, the wider S3 surface). ⚠️ E2.1-r caveat: NGBoost was selected for
   PRICING CALIBRATION — a discrimination win does not automatically justify the swap.
2. **`plus_eb` on total_runs specifically, properly powered.** DSR 0.842 vs a 0.95 gate on the
   strongest case is what an UNDER-POWERED real effect looks like, not what a dead one looks like.

## Power / validity caveats (binding)

- **3 purged folds** (5,468 eval rows). This can rule out a LARGE effect, not a small one.
- The offline matrix is **NOT point-in-time** (`load_features`: each game's row is read as it exists
  NOW, post-backfill and dense). Every number here is a CEILING, not an achievable live figure.
- `calibration_not_degraded` fired on run_diff/pre_lineup at PIT-KS 0.0294 vs 0.0293 — a 1e-4
  difference against a 1e-9 tolerance, i.e. it tripped on rounding. It did NOT change that verdict
  (the margin gate had already failed decisively). **Deliberately NOT loosened after seeing results**
  — that is pre-registration laundering. Change it, if at all, BEFORE a future run.
