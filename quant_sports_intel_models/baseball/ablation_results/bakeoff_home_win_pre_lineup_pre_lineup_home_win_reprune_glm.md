# Model-Class Bake-off — home_win (pre_lineup)  [E1.9 step 1]

- Honest metric: **brier** (lower=better) · 36 feats · 3 purged folds · seed 42
- **Auto-winner: `glm_elasticnet`** — tie within 0.002 noise floor among 2 (glm_elasticnet, stack_mean) → picked on best calibration; primary-leader=glm_elasticnet, simplest=glm_elasticnet
  - ⚖️ **Tie set** (within 0.002 noise floor): `glm_elasticnet`, `stack_mean`. **Primary leader** = `glm_elasticnet`; **simplest** = `glm_elasticnet`. The auto-pick used calibration — **operator/PM may override toward the primary-leader or simplest class before HPO** (all are statistically tied here).
  - Winner margin vs floors (>0 ⇒ winner better): vs market +0.0010, vs no_skill +0.0079  _(noise floor 0.002)_
- PBO across slate (CSCV, E1.4): **0.013**  ✅ < 0.2

| rank | candidate | brier | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `glm_elasticnet` | 0.2412 | 0.6751 | 0.4846 | 0.0183 |  |
| 2 | `floor_market` | 0.2422 | 0.6771 | 0.4841 | 0.0215 | ✅ |
| 3 | `stack_mean` | 0.2424 | 0.6776 | 0.4879 | 0.0221 |  |
| 4 | `catboost` | 0.2433 | 0.6794 | 0.4881 | 0.0149 |  |
| 5 | `xgboost` | 0.2441 | 0.6812 | 0.4893 | 0.0148 |  |
| 6 | `lightgbm` | 0.2446 | 0.6821 | 0.4900 | 0.0348 |  |
| 7 | `floor_no_skill` | 0.2491 | 0.6914 | 0.4980 | 0.0088 | ✅ |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.