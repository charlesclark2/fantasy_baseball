# Model-Class Bake-off — home_win (post_lineup)  [E1.9 step 1]

- Honest metric: **brier** (lower=better) · 19 feats · 3 purged folds · seed 42
- **Auto-winner: `xgboost`** — tie within 0.002 noise floor among 4 (glm_elasticnet, stack_mean, catboost, xgboost) → picked on best calibration; primary-leader=glm_elasticnet, simplest=glm_elasticnet
  - ⚖️ **Tie set** (within 0.002 noise floor): `glm_elasticnet`, `stack_mean`, `catboost`, `xgboost`. **Primary leader** = `glm_elasticnet`; **simplest** = `glm_elasticnet`. The auto-pick used calibration — **operator/PM may override toward the primary-leader or simplest class before HPO** (all are statistically tied here).
  - Winner margin vs floors (>0 ⇒ winner better): vs market +0.0022, vs no_skill +0.0091  _(noise floor 0.002)_
- PBO across slate (CSCV, E1.4): **0.046**  ✅ < 0.2

| rank | candidate | brier | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `glm_elasticnet` | 0.2380 | 0.6685 | 0.4788 | 0.0190 |  |
| 2 | `stack_mean` | 0.2382 | 0.6690 | 0.4811 | 0.0210 |  |
| 3 | `catboost` | 0.2399 | 0.6723 | 0.4818 | 0.0188 |  |
| 4 | `xgboost` | 0.2400 | 0.6727 | 0.4818 | 0.0168 |  |
| 5 | `lightgbm` | 0.2407 | 0.6741 | 0.4826 | 0.0169 |  |
| 6 | `floor_market` | 0.2422 | 0.6771 | 0.4841 | 0.0215 | ✅ |
| 7 | `floor_no_skill` | 0.2491 | 0.6914 | 0.4980 | 0.0088 | ✅ |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.