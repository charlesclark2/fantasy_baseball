# MLB Edge-E7.9 — retrain bake-off: run_diff (pre_lineup)

> ⚠️ **Not an edge claim.** `best_alpha = 0`. This decides whether the MiLB-MLE-corrected feature block and the newly-joined `eb_gb_pct` earn a retrained champion; it says nothing about win rate or ROI.

**VERDICT: `INCUMBENT_STANDS`**

- Honest metric **crps** (lower = better) · 24 arms × 3 purged/embargoed folds · 11,858 rows · seed 42
- Incumbent arm `incumbent::ngboost_normal` = 2.4789
- Leader `plus_eb::glm_elasticnet` = 2.4735 (margin +0.0053; noise floor 0.02)
- PBO 0.000 (gate < 0.2) · DSR 0.218 (gate ≥ 0.95)
- Oracle-floor sanity (E2.1-r): oracle crps = 0.000234; no candidate beat it ✅

## ⚠️ Margin attribution — the margin is NOT purely a feature effect

The gate compares leader-arm vs incumbent-arm, where an arm is (contract variant × learner class). That is the right PROMOTION question, but it CONFLATES the feature effect with a learner-class swap. Split against `incumbent::glm_elasticnet` (the incumbent contract under the LEADER's learner):

| component | Δ crps | share of margin |
|---|---:|---:|
| **learner swap** (incumbent learner → `glm_elasticnet`) | +0.0041 | 77% |
| **contract** (added features) | +0.0012 | 23% |
| **total reported margin** | +0.0053 | 100% |

🚩 **77% of this margin is the LEARNER SWAP, not the features.** Do not read `+0.0053` as what the added columns bought — that figure is `+0.0012`.

### Feature effect holding the LEARNER FIXED (+ = variant better than the incumbent contract)

| learner | incumbent crps | plus_gb | plus_eb | plus_both |
|---|---:|---:|---:|---:|
| glm_elasticnet | 2.4748 | -0.0007 | +0.0012 | +0.0006 |
| ngboost_normal | 2.4789 | -0.0007 | +0.0006 | -0.0004 |
| catboost | 2.4876 | -0.0015 | -0.0005 | -0.0042 |
| stack_mean | 2.5218 | +0.0022 | +0.0011 | +0.0034 |
| xgboost | 2.5384 | -0.0005 | -0.0034 | -0.0033 |
| lightgbm | 2.7315 | +0.0117 | +0.0057 | +0.0157 |

This table — not the headline margin — is where a FEATURE effect can be read.

## Pre-registered gates

| gate | result |
|---|---|
| `beats_incumbent_by_more_than_noise_floor` | ❌ fail |
| `pbo_lt_0_2` | ✅ pass |
| `dsr_gt_0_at_95` | ❌ fail |
| `calibration_not_degraded` | ❌ fail |

⚠️ Scored under the ORIGINAL `calibration_not_degraded` tolerance of `1e-09`, i.e. BEFORE pre-registration amendment #1 (2026-07-29). That tolerance is tight enough to trip on ROUNDING; where this gate failed, check whether the PIT-KS difference is material before reading it as a real calibration regression. **This recorded verdict is left exactly as scored** — the amendment is forward-dated and does not retro-apply.

**Reading the null honestly.** No arm clears every gate, so the served champion is unchanged and there is NO prediction backfill to run (E7.9 step 7 is conditional on a promotion). Per the E2.1-r note: if the top arms are TIED within the noise floor, a high PBO is the NULL — 'which tied arm wins is noise' — not evidence of overfitting. Check the spread in the table below before reading PBO as a failure.

## Contract variants

| variant | features | added vs incumbent |
|---|---:|---|
| `incumbent` | 124 | — (the bar) |
| `plus_gb` | 126 | `away_starter_eb_gb_pct`, `home_starter_eb_gb_pct` |
| `plus_eb` | 131 | `away_avg_eb_bb_pct`, `away_avg_eb_iso`, `away_avg_eb_k_pct`, `home_avg_eb_bb_pct`, `home_avg_eb_iso`, `home_avg_eb_k_pct`, `home_starter_eb_bb_pct` |
| `plus_both` | 133 | `away_avg_eb_bb_pct`, `away_avg_eb_iso`, `away_avg_eb_k_pct`, `away_starter_eb_gb_pct`, `home_avg_eb_bb_pct`, `home_avg_eb_iso`, `home_avg_eb_k_pct`, `home_starter_eb_bb_pct`, `home_starter_eb_gb_pct` |

## Full arm table

| arm | variant | learner | crps | PIT-KS | n |
|---|---|---|---:|---:|---:|
| `oracle_floor` | oracle_floor | - | 0.0002 | 0.5000 | 5,468 |
| `plus_eb::glm_elasticnet` | plus_eb | glm_elasticnet | 2.4735 | 0.0294 | 5,468 |
| `plus_both::glm_elasticnet` | plus_both | glm_elasticnet | 2.4742 | 0.0301 | 5,468 |
| `incumbent::glm_elasticnet` | incumbent | glm_elasticnet | 2.4748 | 0.0308 | 5,468 |
| `plus_gb::glm_elasticnet` | plus_gb | glm_elasticnet | 2.4754 | 0.0310 | 5,468 |
| `plus_eb::ngboost_normal` | plus_eb | ngboost_normal | 2.4783 | 0.0301 | 5,468 |
| `incumbent::ngboost_normal` | incumbent | ngboost_normal | 2.4789 | 0.0293 | 5,468 |
| `plus_both::ngboost_normal` | plus_both | ngboost_normal | 2.4793 | 0.0309 | 5,468 |
| `plus_gb::ngboost_normal` | plus_gb | ngboost_normal | 2.4795 | 0.0300 | 5,468 |
| `incumbent::catboost` | incumbent | catboost | 2.4876 | 0.0352 | 5,468 |
| `plus_eb::catboost` | plus_eb | catboost | 2.4881 | 0.0352 | 5,468 |
| `plus_gb::catboost` | plus_gb | catboost | 2.4891 | 0.0371 | 5,468 |
| `plus_both::catboost` | plus_both | catboost | 2.4917 | 0.0364 | 5,468 |
| `plus_both::stack_mean` | plus_both | stack_mean | 2.5185 | 0.0654 | 5,468 |
| `plus_gb::stack_mean` | plus_gb | stack_mean | 2.5197 | 0.0672 | 5,468 |
| `plus_eb::stack_mean` | plus_eb | stack_mean | 2.5208 | 0.0636 | 5,468 |
| `incumbent::stack_mean` | incumbent | stack_mean | 2.5218 | 0.0672 | 5,468 |
| `incumbent::xgboost` | incumbent | xgboost | 2.5384 | 0.0656 | 5,468 |
| `plus_gb::xgboost` | plus_gb | xgboost | 2.5389 | 0.0696 | 5,468 |
| `plus_both::xgboost` | plus_both | xgboost | 2.5418 | 0.0682 | 5,468 |
| `plus_eb::xgboost` | plus_eb | xgboost | 2.5419 | 0.0658 | 5,468 |
| `plus_both::lightgbm` | plus_both | lightgbm | 2.7159 | 0.1640 | 5,468 |
| `plus_gb::lightgbm` | plus_gb | lightgbm | 2.7198 | 0.1587 | 5,468 |
| `plus_eb::lightgbm` | plus_eb | lightgbm | 2.7258 | 0.1609 | 5,468 |
| `incumbent::lightgbm` | incumbent | lightgbm | 2.7315 | 0.1622 | 5,468 |

