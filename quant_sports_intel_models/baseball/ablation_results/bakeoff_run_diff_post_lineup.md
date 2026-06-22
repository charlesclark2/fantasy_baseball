# Model-Class Bake-off — run_diff (post_lineup)  [E1.9 step 1]

- Honest metric: **crps** (lower=better) · 13 feats · 3 purged folds · seed 42
- **Winner: `ngboost_normal`** (tie within 0.02 noise floor among 2 → broke on calibration)
- PBO across slate (CSCV, E1.4): **0.000**  ✅ < 0.2

| rank | candidate | crps | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `ngboost_normal` | 2.3841 | 2.8620 | 3.3603 | 0.0314 |  |
| 2 | `catboost` | 2.4001 | 2.8920 | 3.3642 | 0.0324 |  |
| 3 | `stack_mean` | 2.4153 | 2.9145 | 3.3727 | 0.0460 |  |
| 4 | `glm_elasticnet` | 2.4191 | 2.8906 | 3.3844 | 0.0287 |  |
| 5 | `xgboost` | 2.4361 | 2.9431 | 3.3943 | 0.0481 |  |
| 6 | `floor_no_skill` | 2.5080 | 2.9246 | 3.5610 | 0.1104 | ✅ |
| 7 | `lightgbm` | 2.5333 | 3.1882 | 3.4323 | 0.0971 |  |

Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.