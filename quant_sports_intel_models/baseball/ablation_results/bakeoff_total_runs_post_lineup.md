# Model-Class Bake-off — total_runs (post_lineup)  [E1.9 step 1]

- Honest metric: **crps** (lower=better) · 13 feats · 3 purged folds · seed 42
- **Winner: `glm_elasticnet`** (tie within 0.02 noise floor among 3 → broke on calibration)
- PBO across slate (CSCV, E1.4): **0.070**  ✅ < 0.2

| rank | candidate | crps | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `floor_market` | 2.4182 | 2.8872 | 3.4055 | — | ✅ |
| 2 | `ngboost_normal` | 2.4201 | 2.8865 | 3.4264 | 0.0629 |  |
| 3 | `ngboost_lognormal` | 2.4244 | 2.8963 | 3.4340 | 0.0677 |  |
| 4 | `glm_elasticnet` | 2.4298 | 2.8867 | 3.4447 | 0.0575 |  |
| 5 | `catboost` | 2.4621 | 2.9032 | 3.4927 | 0.0727 |  |
| 6 | `stack_mean` | 2.4743 | 2.9304 | 3.4893 | 0.0903 |  |
| 7 | `floor_no_skill` | 2.4807 | 2.9065 | 3.5124 | 0.1081 | ✅ |
| 8 | `xgboost` | 2.5053 | 2.9448 | 3.5298 | 0.0948 |  |
| 9 | `lightgbm` | 2.6181 | 3.1371 | 3.5961 | 0.1327 |  |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.