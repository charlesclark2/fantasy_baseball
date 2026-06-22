# Model-Class Bake-off — total_runs (pre_lineup)  [E1.9 step 1]

- Honest metric: **crps** (lower=better) · 87 feats · 3 purged folds · seed 42
- **Winner: `glm_elasticnet`** (tie within 0.02 noise floor among 4 → broke on calibration)
- PBO across slate (CSCV, E1.4): **0.543**  ⚠️ ≥ 0.2 (selection may be overfit)

| rank | candidate | crps | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `ngboost_normal` | 2.3745 | 2.8689 | 3.3601 | 0.0654 |  |
| 2 | `ngboost_lognormal` | 2.3768 | 2.8752 | 3.3598 | 0.0667 |  |
| 3 | `glm_elasticnet` | 2.3781 | 2.8678 | 3.3663 | 0.0583 |  |
| 4 | `catboost` | 2.3800 | 2.8951 | 3.3483 | 0.0753 |  |
| 5 | `stack_mean` | 2.4131 | 2.9820 | 3.3490 | 0.1081 |  |
| 6 | `floor_market` | 2.4182 | 2.8872 | 3.4055 | — | ✅ |
| 7 | `xgboost` | 2.4468 | 3.0246 | 3.3797 | 0.1109 |  |
| 8 | `floor_no_skill` | 2.4807 | 2.9065 | 3.5124 | 0.1081 | ✅ |
| 9 | `lightgbm` | 2.6191 | 4.0115 | 3.3834 | 0.2030 |  |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.