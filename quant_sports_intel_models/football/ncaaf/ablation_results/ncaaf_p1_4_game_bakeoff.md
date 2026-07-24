# NCAAF-P1.4 — NCAAF game-model bake-off (H2H · spread · total from the joint distribution)

_Decided 2026-07-23 · 125 configs · 32 CV buckets_

## Verdict

**REFERENCE_STANDS** — the strength-prior reference `ridge__strength_only__gaussian` carries; the full matrix does not robustly beat it.

- reference passes calib_80 floor: **YES**
- full-search PBO `0.648` (FAIL < 0.2)
- best DSR `0.007`

## Selection metric

sum over {margin, total} of PIT max-decile-dev (lower better); calib_80 ≥ 0.80 a FLOOR not a target (inclusive-integer coverage is inflated — an oracle covers > 0.80); h2h Brier secondary

## Leaderboard

| config | form | score | calib_80 (margin) | calib_80 (total) | h2h Brier | floor |
|---|---|---|---|---|---|---|
| `xgb__full__gaussian` | gaussian | 0.01920 | 0.801 | 0.803 | 0.1846 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02010 | 0.803 | 0.805 | 0.1835 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02040 | 0.802 | 0.806 | 0.1835 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02050 | 0.799 | 0.805 | 0.1870 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02070 | 0.803 | 0.807 | 0.1845 | ✅ |
| `lgbm__full__student_t` | student_t | 0.02150 | 0.797 | 0.801 | 0.1841 | ✅ |
| `lgbm__clustered__gaussian` | gaussian | 0.02170 | 0.804 | 0.803 | 0.1838 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02170 | 0.798 | 0.805 | 0.1830 | ✅ |
| `lgbm__full__strength_posterior` | strength_posterior | 0.02180 | 0.799 | 0.804 | 0.1840 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02190 | 0.799 | 0.803 | 0.1818 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02210 | 0.799 | 0.803 | 0.1851 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02220 | 0.800 | 0.802 | 0.1894 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02240 | 0.801 | 0.806 | 0.1835 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02250 | 0.800 | 0.805 | 0.1824 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02260 | 0.802 | 0.804 | 0.1825 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02260 | 0.804 | 0.802 | 0.1833 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02260 | 0.803 | 0.808 | 0.1881 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02270 | 0.802 | 0.805 | 0.1811 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02270 | 0.804 | 0.806 | 0.1870 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02270 | 0.797 | 0.802 | 0.1812 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02270 | 0.799 | 0.804 | 0.1819 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02280 | 0.803 | 0.805 | 0.1896 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02280 | 0.803 | 0.806 | 0.1807 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02290 | 0.801 | 0.805 | 0.1840 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02290 | 0.804 | 0.810 | 0.1843 | ✅ |
| `xgb__full__gaussian` | gaussian | 0.02300 | 0.802 | 0.801 | 0.1831 | ✅ |
| `xgb__clustered__gaussian` | gaussian | 0.02310 | 0.800 | 0.802 | 0.1824 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02320 | 0.801 | 0.804 | 0.1834 | ✅ |
| `lgbm__full__gaussian` | gaussian | 0.02340 | 0.800 | 0.805 | 0.1826 | ✅ |
| `catboost__full__gaussian` | gaussian | 0.02350 | 0.801 | 0.808 | 0.1835 | ✅ |

## Honest framing

A market-BLIND joint (margin, total) distribution is **product value** — calibrated H2H / spread / total probabilities — NOT an edge claim (`best_alpha = 0`). Whether it beats a closing line is the vs-close CLV leg (`--stage finalize`), 2020–2025, under PBO/DSR deflation. Market-blind CONTRACT-GUARD held on every contract.
