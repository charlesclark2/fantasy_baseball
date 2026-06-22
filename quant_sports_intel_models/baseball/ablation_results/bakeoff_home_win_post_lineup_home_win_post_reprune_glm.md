# Model-Class Bake-off — home_win (post_lineup)  [E1.9 step 1]

- Honest metric: **brier** (lower=better) · 42 feats · 3 purged folds · seed 42
- **Auto-winner: `glm_elasticnet`** — tie within 0.002 noise floor among 4 (glm_elasticnet, stack_mean, catboost, xgboost) → picked on best calibration; primary-leader=glm_elasticnet, simplest=glm_elasticnet
  - ⚖️ **Tie set** (within 0.002 noise floor): `glm_elasticnet`, `stack_mean`, `catboost`, `xgboost`. **Primary leader** = `glm_elasticnet`; **simplest** = `glm_elasticnet`. The auto-pick used calibration — **operator/PM may override toward the primary-leader or simplest class before HPO** (all are statistically tied here).
  - Winner margin vs floors (>0 ⇒ winner better): vs market +0.0051, vs no_skill +0.0120  _(noise floor 0.002)_
- PBO across slate (CSCV, E1.4): **0.233**  ⚠️ ≥ 0.2 (selection may be overfit)

| rank | candidate | brier | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `glm_elasticnet` | 0.2371 | 0.6665 | 0.4771 | 0.0169 |  |
| 2 | `stack_mean` | 0.2375 | 0.6674 | 0.4796 | 0.0221 |  |
| 3 | `catboost` | 0.2381 | 0.6686 | 0.4787 | 0.0175 |  |
| 4 | `xgboost` | 0.2389 | 0.6701 | 0.4796 | 0.0184 |  |
| 5 | `lightgbm` | 0.2405 | 0.6735 | 0.4822 | 0.0162 |  |
| 6 | `floor_market` | 0.2422 | 0.6771 | 0.4841 | 0.0215 | ✅ |
| 7 | `floor_no_skill` | 0.2491 | 0.6914 | 0.4980 | 0.0088 | ✅ |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.