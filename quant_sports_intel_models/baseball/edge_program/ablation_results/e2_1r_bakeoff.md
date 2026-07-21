# E2.1-r — Per-side count-model bake-off (revisit of the single-architecture E2.1)

_Decided 2026-07-20 · 16 configs · 20 CV buckets_

## Verdict

**PROMOTE_MINIMAL_FIX** — winner `lgbm_poisson__full__heldout` vs incumbent `lgbm_poisson__full__train`, downstream gain `+0.10930`.

- incumbent passes calib_80 floor: **NO — DISQUALIFIED**
- full-search PBO `0.233` (FAIL < 0.2) — high ⇒ the learner choice is a tied cluster (a learner NULL), not overfitting
- minimal-fix DSR `1.000` (PASS > 0) — same learner, dispersion switched only
- E2.5 / E2.6 re-run required: **YES**

## Selection metric

sum over {total, home_total, away_total} of PIT max decile dev (lower is better); calib_80 ≥ 0.80 enforced as a FLOOR not a target (discreteness inflates coverage — an oracle covers ~0.82-0.86, so |calib_80-0.80| would reward under-dispersion); run_diff measured but excluded (E2.2/E2.3: dropped dependence)

## Leaderboard

| config | score | calib_80 (total) | PIT maxdev (total) | per-side NegBin NLL | floor |
|---|---|---|---|---|---|
| `glm_poisson__top_k__heldout` | 0.02470 | 0.832 | 0.0049 | 2.4425 | ✅ |
| `catboost_poisson__top_k__heldout` | 0.02490 | 0.831 | 0.0057 | 2.4376 | ✅ |
| `xgb_poisson__full__heldout` | 0.02500 | 0.835 | 0.0044 | 2.4387 | ✅ |
| `catboost_poisson__full__heldout` | 0.02550 | 0.833 | 0.0060 | 2.4381 | ✅ |
| `lgbm_poisson__full__heldout` | 0.02570 | 0.835 | 0.0047 | 2.4381 | ✅ |
| `lgbm_poisson__top_k__heldout` | 0.02580 | 0.832 | 0.0059 | 2.4386 | ✅ |
| `xgb_poisson__clustered__heldout` | 0.02610 | 0.834 | 0.0052 | 2.4395 | ✅ |
| `xgb_poisson__top_k__heldout` | 0.02710 | 0.834 | 0.0064 | 2.4394 | ✅ |
| `glm_poisson__full__heldout` | 0.02820 | 0.836 | 0.0079 | 2.4519 | ✅ |
| `lgbm_poisson__clustered__heldout` | 0.02860 | 0.834 | 0.0058 | 2.4389 | ✅ |
| `catboost_poisson__clustered__heldout` | 0.02880 | 0.833 | 0.0071 | 2.4382 | ✅ |
| `glm_poisson__clustered__heldout` | 0.03470 | 0.836 | 0.0107 | 2.4533 | ✅ |
| `ngboost_normal__top_k__native` | 0.08960 | 0.803 | 0.0260 | 2.4497 | ✅ |
| `ngboost_normal__full__native` | 0.09710 | 0.803 | 0.0295 | 2.4503 | ✅ |
| `ngboost_normal__clustered__native` | 0.09750 | 0.803 | 0.0294 | 2.4510 | ✅ |
| `lgbm_poisson__full__train` | 0.13500 | 0.778 | 0.0416 | 2.4643 | ❌ |

## Honest framing

This is a **calibration** result, not an edge claim. A better-calibrated per-side marginal makes the convolved total / team-total distributions honest; it does not establish a market edge (`best_alpha = 0`). Market-blind CONTRACT-GUARD held on every contract in the search.
