# Model-Class Bake-off — run_diff (pre_lineup)  [E1.9 step 1]

- Honest metric: **crps** (lower=better) · 124 feats · 3 purged folds · seed 42
- **Auto-winner: `glm_elasticnet`** — tie within 0.02 noise floor among 3 candidates. _(This run predates the recorded `winner_reason` field; the tie-break is the harness's standing rule — best calibration — not a string this run stored.)_
- PBO across slate (CSCV, E1.4): **0.000**  ✅ < 0.2

| rank | candidate | crps | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `ngboost_normal` | 2.4478 | 2.9049 | 3.4458 | 0.0333 |  |
| 2 | `glm_elasticnet` | 2.4496 | 2.9030 | 3.4379 | 0.0311 |  |
| 3 | `catboost` | 2.4540 | 2.9264 | 3.4437 | 0.0384 |  |
| 4 | `stack_mean` | 2.4969 | 3.0303 | 3.4589 | 0.0705 |  |
| 5 | `floor_no_skill` | 2.5080 | 2.9246 | 3.5610 | 0.1104 | ✅ |
| 6 | `xgboost` | 2.5236 | 3.0648 | 3.4882 | 0.0769 |  |
| 7 | `lightgbm` | 2.7270 | 4.1842 | 3.5071 | 0.1753 |  |

## ⚠️ Margin attribution — learner swap vs contract

_Not available — this run scores a single contract, so it has NO contract axis — its margins are learner-vs-floor on fixed features and none of them is a feature effect to attribute._


Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.