# NCAAF-P1.4 — NCAAF game-model bake-off (H2H · spread · total from the joint distribution)

_Decided 2026-07-22 · 23 configs · 32 CV buckets_

## Verdict

**REFERENCE_STANDS** — the strength-prior reference `ridge__strength_only__gaussian` carries; the full matrix does not robustly beat it.

- reference passes calib_80 floor: **YES**
- full-search PBO `0.483` (FAIL < 0.2)
- best DSR `0.109`

## Selection metric

sum over {margin, total} of PIT max-decile-dev (lower better); calib_80 ≥ 0.80 a FLOOR not a target (inclusive-integer coverage is inflated — an oracle covers > 0.80); h2h Brier secondary

## Leaderboard

| config | form | score | calib_80 (margin) | calib_80 (total) | h2h Brier | floor |
|---|---|---|---|---|---|---|
| `lgbm__full__student_t` | student_t | 0.02150 | 0.797 | 0.801 | 0.1841 | ✅ |
| `lgbm__clustered__gaussian` | gaussian | 0.02170 | 0.804 | 0.803 | 0.1838 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02290 | 0.801 | 0.805 | 0.1840 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02300 | 0.802 | 0.801 | 0.1831 | ✅ |
| `xgb__clustered__gaussian` | gaussian | 0.02310 | 0.800 | 0.802 | 0.1824 | ✅ |
| `lgbm__top_k__gaussian` | gaussian | 0.02410 | 0.794 | 0.810 | 0.1848 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02420 | 0.801 | 0.804 | 0.1818 | ✅ |
| `ridge__strength_only__gaussian` | gaussian | 0.02420 | 0.800 | 0.803 | 0.1816 | ✅ |
| `catboost__clustered__gaussian` | gaussian | 0.02490 | 0.798 | 0.805 | 0.1813 | ✅ |
| `catboost__top_k__gaussian` | gaussian | 0.02550 | 0.797 | 0.808 | 0.1819 | ✅ |
| `xgb__strength_only__gaussian` | gaussian | 0.02550 | 0.800 | 0.809 | 0.1851 | ✅ |
| `lgbm__strength_only__gaussian` | gaussian | 0.02590 | 0.800 | 0.806 | 0.1863 | ✅ |
| `xgb__top_k__gaussian` | gaussian | 0.02650 | 0.797 | 0.806 | 0.1827 | ✅ |
| `ridge__strength_only__strength_posterior` | strength_posterior | 0.02690 | 0.798 | 0.803 | 0.1816 | ✅ |
| `catboost__strength_only__gaussian` | gaussian | 0.02830 | 0.804 | 0.810 | 0.1835 | ✅ |
| `ridge__top_k__gaussian` | gaussian | 0.03200 | 0.798 | 0.804 | 0.1821 | ✅ |
| `lgbm__full__count` | count | 0.06240 | 0.864 | 0.862 | 0.1849 | ✅ |
| `ridge__full__gaussian` | gaussian | 0.07460 | 0.825 | 0.827 | 0.1853 | ✅ |
| `ngboost_normal__top_k__native` | native | 0.08020 | 0.725 | 0.733 | 0.1834 | ❌ |
| `ngboost_normal__strength_only__native` | native | 0.08090 | 0.735 | 0.731 | 0.1841 | ❌ |
| `ridge__clustered__gaussian` | gaussian | 0.08760 | 0.824 | 0.827 | 0.1857 | ✅ |
| `ngboost_normal__full__native` | native | 0.08770 | 0.723 | 0.717 | 0.1835 | ❌ |
| `ngboost_normal__clustered__native` | native | 0.09070 | 0.721 | 0.715 | 0.1838 | ❌ |

## Honest framing

A market-BLIND joint (margin, total) distribution is **product value** — calibrated H2H / spread / total probabilities — NOT an edge claim (`best_alpha = 0`). Whether it beats a closing line is the vs-close CLV leg (`--stage finalize`), 2020–2025, under PBO/DSR deflation. Market-blind CONTRACT-GUARD held on every contract.
