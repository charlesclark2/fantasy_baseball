# Model-Class Bake-off — home_win (pre_lineup)  [E1.9 step 1]

- Honest metric: **brier** (lower=better) · 154 feats · 3 purged folds · seed 42
- **Auto-winner: `lightgbm`** — tie within 0.002 noise floor among 5 (stack_mean, glm_elasticnet, lightgbm, xgboost, catboost) → picked on best calibration; primary-leader=stack_mean, simplest=glm_elasticnet
  - ⚖️ **Tie set** (within 0.002 noise floor): `stack_mean`, `glm_elasticnet`, `lightgbm`, `xgboost`, `catboost`. **Primary leader** = `stack_mean`; **simplest** = `glm_elasticnet`. The auto-pick used calibration — **operator/PM may override toward the primary-leader or simplest class before HPO** (all are statistically tied here).
  - Winner margin vs floors (>0 ⇒ winner better): vs market -0.0013, vs no_skill +0.0056  _(noise floor 0.002)_
- PBO across slate (CSCV, E1.4): **0.052**  ✅ < 0.2

| rank | candidate | brier | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `floor_market` | 0.2422 | 0.6771 | 0.4841 | 0.0215 | ✅ |
| 2 | `stack_mean` | 0.2426 | 0.6781 | 0.4882 | 0.0211 |  |
| 3 | `glm_elasticnet` | 0.2433 | 0.6794 | 0.4880 | 0.0171 |  |
| 4 | `lightgbm` | 0.2435 | 0.6800 | 0.4880 | 0.0134 |  |
| 5 | `xgboost` | 0.2437 | 0.6804 | 0.4886 | 0.0171 |  |
| 6 | `catboost` | 0.2442 | 0.6814 | 0.4898 | 0.0141 |  |
| 7 | `floor_no_skill` | 0.2491 | 0.6914 | 0.4980 | 0.0088 | ✅ |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.