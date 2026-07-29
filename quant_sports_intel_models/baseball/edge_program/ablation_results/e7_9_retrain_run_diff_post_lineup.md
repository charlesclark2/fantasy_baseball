# MLB Edge-E7.9 — retrain bake-off: run_diff (post_lineup)

> ⚠️ **Not an edge claim.** `best_alpha = 0`. This decides whether the MiLB-MLE-corrected feature block and the newly-joined `eb_gb_pct` earn a retrained champion; it says nothing about win rate or ROI.

**VERDICT: `INCUMBENT_STANDS`**

- Honest metric **crps** (lower = better) · 24 arms × 3 purged/embargoed folds · 11,858 rows · seed 42
- Incumbent arm `incumbent::ngboost_normal` = 2.4848
- Leader `plus_eb::glm_elasticnet` = 2.4720 (margin +0.0127; noise floor 0.02)
- PBO 0.000 (gate < 0.2) · DSR 0.724 (gate ≥ 0.95)
- Oracle-floor sanity (E2.1-r): oracle crps = 0.000234; no candidate beat it ✅

## Pre-registered gates

| gate | result |
|---|---|
| `beats_incumbent_by_more_than_noise_floor` | ❌ fail |
| `pbo_lt_0_2` | ✅ pass |
| `dsr_gt_0_at_95` | ❌ fail |
| `calibration_not_degraded` | ✅ pass |

**Reading the null honestly.** No arm clears every gate, so the served champion is unchanged and there is NO prediction backfill to run (E7.9 step 7 is conditional on a promotion). Per the E2.1-r note: if the top arms are TIED within the noise floor, a high PBO is the NULL — 'which tied arm wins is noise' — not evidence of overfitting. Check the spread in the table below before reading PBO as a failure.

## Contract variants

| variant | features | added vs incumbent |
|---|---:|---|
| `incumbent` | 13 | — (the bar) |
| `plus_gb` | 15 | `away_starter_eb_gb_pct`, `home_starter_eb_gb_pct` |
| `plus_eb` | 23 | `away_avg_eb_bb_pct`, `away_avg_eb_iso`, `away_avg_eb_k_pct`, `away_starter_eb_bb_pct`, `away_starter_eb_k_pct`, `home_avg_eb_bb_pct`, `home_avg_eb_iso`, `home_avg_eb_k_pct`, `home_starter_eb_bb_pct`, `home_starter_eb_k_pct` |
| `plus_both` | 25 | `away_avg_eb_bb_pct`, `away_avg_eb_iso`, `away_avg_eb_k_pct`, `away_starter_eb_bb_pct`, `away_starter_eb_gb_pct`, `away_starter_eb_k_pct`, `home_avg_eb_bb_pct`, `home_avg_eb_iso`, `home_avg_eb_k_pct`, `home_starter_eb_bb_pct`, `home_starter_eb_gb_pct`, `home_starter_eb_k_pct` |

## Full arm table

| arm | variant | learner | crps | PIT-KS | n |
|---|---|---|---:|---:|---:|
| `oracle_floor` | oracle_floor | - | 0.0002 | 0.5000 | 5,468 |
| `plus_eb::glm_elasticnet` | plus_eb | glm_elasticnet | 2.4720 | 0.0250 | 5,468 |
| `plus_both::glm_elasticnet` | plus_both | glm_elasticnet | 2.4724 | 0.0258 | 5,468 |
| `incumbent::glm_elasticnet` | incumbent | glm_elasticnet | 2.4780 | 0.0285 | 5,468 |
| `plus_gb::glm_elasticnet` | plus_gb | glm_elasticnet | 2.4785 | 0.0285 | 5,468 |
| `plus_eb::ngboost_normal` | plus_eb | ngboost_normal | 2.4797 | 0.0292 | 5,468 |
| `plus_both::ngboost_normal` | plus_both | ngboost_normal | 2.4818 | 0.0307 | 5,468 |
| `incumbent::ngboost_normal` | incumbent | ngboost_normal | 2.4848 | 0.0323 | 5,468 |
| `plus_gb::ngboost_normal` | plus_gb | ngboost_normal | 2.4858 | 0.0332 | 5,468 |
| `incumbent::catboost` | incumbent | catboost | 2.4894 | 0.0302 | 5,468 |
| `plus_eb::catboost` | plus_eb | catboost | 2.4948 | 0.0309 | 5,468 |
| `plus_both::catboost` | plus_both | catboost | 2.4958 | 0.0338 | 5,468 |
| `plus_gb::catboost` | plus_gb | catboost | 2.5008 | 0.0349 | 5,468 |
| `incumbent::stack_mean` | incumbent | stack_mean | 2.5087 | 0.0449 | 5,468 |
| `plus_eb::stack_mean` | plus_eb | stack_mean | 2.5131 | 0.0527 | 5,468 |
| `plus_gb::stack_mean` | plus_gb | stack_mean | 2.5131 | 0.0484 | 5,468 |
| `plus_both::stack_mean` | plus_both | stack_mean | 2.5135 | 0.0556 | 5,468 |
| `incumbent::xgboost` | incumbent | xgboost | 2.5278 | 0.0463 | 5,468 |
| `plus_gb::xgboost` | plus_gb | xgboost | 2.5289 | 0.0467 | 5,468 |
| `plus_both::xgboost` | plus_both | xgboost | 2.5309 | 0.0586 | 5,468 |
| `plus_eb::xgboost` | plus_eb | xgboost | 2.5330 | 0.0545 | 5,468 |
| `incumbent::lightgbm` | incumbent | lightgbm | 2.6032 | 0.0913 | 5,468 |
| `plus_gb::lightgbm` | plus_gb | lightgbm | 2.6221 | 0.1031 | 5,468 |
| `plus_eb::lightgbm` | plus_eb | lightgbm | 2.6389 | 0.1151 | 5,468 |
| `plus_both::lightgbm` | plus_both | lightgbm | 2.6449 | 0.1256 | 5,468 |

