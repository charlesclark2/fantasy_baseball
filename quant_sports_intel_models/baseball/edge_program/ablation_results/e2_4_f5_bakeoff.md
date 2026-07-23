# E2.4 — First-5-innings (F5) per-side distribution bake-off

_Decided 2026-07-23 · 192 configs · 20 CV buckets_

## Verdict

**INCUMBENT_STANDS** — reference `lgbm_poisson__full__heldout` carries.

- reference passes calib_80 floor: **YES**
- full-search PBO `0.202` (FAIL < 0.2)
- minimal-fix DSR `0.396` (PASS > 0)

## Selection metric

sum over {total, home_total, away_total} of PIT max decile dev (lower better); calib_80 ≥ 0.80 enforced as a FLOOR not a target (F5's low mean makes the inclusive-integer coverage inflation WORSE than full-game — an oracle covers ~0.82-0.86); run_diff measured but excluded (E2.2/E2.3 dropped dependence)

## Leaderboard

| config | form | score | calib_80 (total) | PIT maxdev (total) | per-side NLL | floor |
|---|---|---|---|---|---|---|
| `catboost_poisson__full__betabinom` | betabinom | 0.01300 | 0.860 | 0.0024 | 2.0478 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01340 | 0.862 | 0.0035 | 2.0492 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01500 | 0.863 | 0.0043 | 2.0468 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01500 | 0.859 | 0.0034 | 2.0488 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01510 | 0.859 | 0.0032 | 2.0482 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01510 | 0.861 | 0.0039 | 2.0478 | ✅ |
| `xgb_poisson__full__betabinom` | betabinom | 0.01510 | 0.861 | 0.0032 | 2.0477 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01570 | 0.860 | 0.0064 | 2.0499 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01580 | 0.861 | 0.0028 | 2.0473 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01590 | 0.862 | 0.0041 | 2.0471 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01620 | 0.860 | 0.0040 | 2.0487 | ✅ |
| `xgb_poisson__full__betabinom` | betabinom | 0.01620 | 0.860 | 0.0033 | 2.0487 | ✅ |
| `xgb_poisson__full__betabinom` | betabinom | 0.01650 | 0.860 | 0.0054 | 2.0495 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01680 | 0.859 | 0.0061 | 2.0488 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01680 | 0.859 | 0.0048 | 2.0525 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01680 | 0.859 | 0.0047 | 2.0490 | ✅ |
| `xgb_poisson__full__betabinom` | betabinom | 0.01680 | 0.861 | 0.0069 | 2.0481 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01690 | 0.860 | 0.0044 | 2.0496 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01690 | 0.861 | 0.0059 | 2.0496 | ✅ |
| `xgb_poisson__full__betabinom` | betabinom | 0.01690 | 0.859 | 0.0031 | 2.0491 | ✅ |
| `xgb_poisson__full__betabinom` | betabinom | 0.01690 | 0.862 | 0.0040 | 2.0481 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01700 | 0.860 | 0.0044 | 2.0474 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01700 | 0.861 | 0.0048 | 2.0479 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01700 | 0.859 | 0.0042 | 2.0493 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01700 | 0.862 | 0.0050 | 2.0483 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01700 | 0.862 | 0.0035 | 2.0488 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01720 | 0.858 | 0.0061 | 2.0504 | ✅ |
| `lgbm_poisson__full__betabinom` | betabinom | 0.01740 | 0.862 | 0.0037 | 2.0483 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01770 | 0.858 | 0.0042 | 2.0488 | ✅ |
| `catboost_poisson__full__betabinom` | betabinom | 0.01770 | 0.861 | 0.0068 | 2.0498 | ✅ |

## Honest framing

A market-BLIND F5 distribution is **product value** (an honest first-5-innings distribution), NOT an edge claim (`best_alpha = 0`). Whether F5 beats its own close is E2.6/E13.9's question under deflation. Market-blind CONTRACT-GUARD held on every contract in the search.
