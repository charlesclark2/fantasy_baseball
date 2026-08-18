# Model-Class Bake-off — total_runs (pre_lineup)  [E1.9 step 1]

- Honest metric: **crps** (lower=better) · 14 feats · 3 purged folds · seed 42
- **Auto-winner: `ngboost_normal`** — tie within 0.02 noise floor among 4 (ngboost_normal, ngboost_lognormal, catboost, glm_elasticnet) → picked on best calibration; primary-leader=ngboost_normal, simplest=glm_elasticnet
  - ⚖️ **Tie set** (within 0.02 noise floor): `ngboost_normal`, `ngboost_lognormal`, `catboost`, `glm_elasticnet`. **Primary leader** = `ngboost_normal`; **simplest** = `glm_elasticnet`. The auto-pick used calibration — **operator/PM may override toward the primary-leader or simplest class before HPO** (all are statistically tied here).
  - Winner margin vs floors (>0 ⇒ winner better): vs market +0.0408, vs no_skill +0.1033  _(noise floor 0.02)_
- PBO across slate (CSCV, E1.4): **0.144**  ✅ < 0.2

| rank | candidate | crps | nll | mae | calibration | floor? |
|---|---|---|---|---|---|---|
| 1 | `ngboost_normal` | 2.3774 | 2.8724 | 3.3585 | 0.0614 |  |
| 2 | `ngboost_lognormal` | 2.3778 | 2.8740 | 3.3696 | 0.0627 |  |
| 3 | `catboost` | 2.3902 | 2.8829 | 3.3714 | 0.0635 |  |
| 4 | `glm_elasticnet` | 2.3965 | 2.8741 | 3.3994 | 0.0676 |  |
| 5 | `stack_mean` | 2.4068 | 2.9224 | 3.3691 | 0.0797 |  |
| 6 | `floor_market` | 2.4182 | 2.8872 | 3.4055 | — | ✅ |
| 7 | `xgboost` | 2.4279 | 2.9311 | 3.3944 | 0.0771 |  |
| 8 | `floor_no_skill` | 2.4807 | 2.9065 | 3.5124 | 0.1081 | ✅ |
| 9 | `lightgbm` | 2.5313 | 3.2027 | 3.4408 | 0.1283 |  |

## ⚠️ Margin attribution — learner swap vs contract

The gate compares `pre_lineup_total_runs_reprune_ngb::ngboost_normal` against `incumbent::glm_elasticnet`, where an arm is (contract variant × learner class). That is the right PROMOTION question and the gate is unchanged — but it CONFLATES the feature effect with a learner-class swap. Split against `incumbent::ngboost_normal` (the incumbent contract under the LEADER's learner), + = better:

| component | Δ crps | share of margin |
|---|---:|---:|
| **learner swap** (→ `ngboost_normal`) | +0.0037 | — |
| **contract** (the features this study is about) | -0.0029 | — |
| **total reported margin** | +0.0007 | — |

🚩🚩 **SIGN FLIP — holding the learner fixed, the contract is WORSE, not better** (`-0.0029`). The reported `+0.0007` is a learner-class effect that more than covers a contract effect pointing the other way. Do NOT read this margin as evidence for the features.

⚠️ **The share is not a reliable proportion here:** the total margin (`0.0007`) is inside this metric's noise floor (`0.02`), so the ratio divides by a quantity the gate itself treats as noise. Read the ABSOLUTE components, not the percentages.

### Contract effect holding the LEARNER FIXED (+ = `pre_lineup_total_runs_reprune_ngb` better)

| learner | incumbent crps | pre_lineup_total_runs_reprune_ngb |
|---|---:|---:|
| `ngboost_normal` | 2.3745 | -0.0029 |
| `ngboost_lognormal` | 2.3768 | -0.0009 |
| `glm_elasticnet` | 2.3781 | -0.0184 |
| `catboost` | 2.3800 | -0.0102 |
| `stack_mean` | 2.4131 | +0.0063 |
| `xgboost` | 2.4468 | +0.0189 |
| `lightgbm` | 2.6191 | +0.0878 |


Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors (no-skill, market) are reference baselines, NOT promotable candidates. Winner feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design — the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric.