# MLB Edge-E7.9 — retrain bake-off: total_runs (post_lineup)

> ⚠️ **Not an edge claim.** `best_alpha = 0`. This decides whether the MiLB-MLE-corrected feature block and the newly-joined `eb_gb_pct` earn a retrained champion; it says nothing about win rate or ROI.

**VERDICT: `INCUMBENT_STANDS`**

- Honest metric **crps** (lower = better) · 28 arms × 3 purged/embargoed folds · 11,858 rows · seed 42
- Incumbent arm `incumbent::ngboost_normal` = 2.4921
- Leader `plus_both::glm_elasticnet` = 2.4714 (margin +0.0206; noise floor 0.02)
- PBO 0.000 (gate < 0.2) · DSR 0.842 (gate ≥ 0.95)
- Oracle-floor sanity (E2.1-r): oracle crps = 0.000234; no candidate beat it ✅

## Pre-registered gates

| gate | result |
|---|---|
| `beats_incumbent_by_more_than_noise_floor` | ✅ pass |
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
| `plus_both::glm_elasticnet` | plus_both | glm_elasticnet | 2.4714 | 0.0599 | 5,468 |
| `plus_eb::glm_elasticnet` | plus_eb | glm_elasticnet | 2.4715 | 0.0601 | 5,468 |
| `plus_gb::glm_elasticnet` | plus_gb | glm_elasticnet | 2.4768 | 0.0552 | 5,468 |
| `incumbent::glm_elasticnet` | incumbent | glm_elasticnet | 2.4768 | 0.0549 | 5,468 |
| `plus_both::ngboost_normal` | plus_both | ngboost_normal | 2.4806 | 0.0629 | 5,468 |
| `plus_eb::ngboost_normal` | plus_eb | ngboost_normal | 2.4814 | 0.0639 | 5,468 |
| `plus_gb::ngboost_normal` | plus_gb | ngboost_normal | 2.4888 | 0.0650 | 5,468 |
| `plus_both::catboost` | plus_both | catboost | 2.4909 | 0.0677 | 5,468 |
| `plus_eb::catboost` | plus_eb | catboost | 2.4914 | 0.0715 | 5,468 |
| `incumbent::ngboost_normal` | incumbent | ngboost_normal | 2.4921 | 0.0646 | 5,468 |
| `plus_both::ngboost_lognormal` | plus_both | ngboost_lognormal | 2.4944 | 0.0620 | 5,468 |
| `plus_eb::ngboost_lognormal` | plus_eb | ngboost_lognormal | 2.4972 | 0.0605 | 5,468 |
| `incumbent::ngboost_lognormal` | incumbent | ngboost_lognormal | 2.5049 | 0.0665 | 5,468 |
| `plus_gb::ngboost_lognormal` | plus_gb | ngboost_lognormal | 2.5052 | 0.0669 | 5,468 |
| `plus_gb::catboost` | plus_gb | catboost | 2.5122 | 0.0724 | 5,468 |
| `incumbent::catboost` | incumbent | catboost | 2.5173 | 0.0717 | 5,468 |
| `plus_eb::stack_mean` | plus_eb | stack_mean | 2.5200 | 0.0910 | 5,468 |
| `plus_both::stack_mean` | plus_both | stack_mean | 2.5267 | 0.0936 | 5,468 |
| `plus_eb::xgboost` | plus_eb | xgboost | 2.5312 | 0.0923 | 5,468 |
| `plus_gb::stack_mean` | plus_gb | stack_mean | 2.5316 | 0.0897 | 5,468 |
| `incumbent::stack_mean` | incumbent | stack_mean | 2.5361 | 0.0915 | 5,468 |
| `plus_both::xgboost` | plus_both | xgboost | 2.5499 | 0.1008 | 5,468 |
| `plus_gb::xgboost` | plus_gb | xgboost | 2.5650 | 0.0944 | 5,468 |
| `incumbent::xgboost` | incumbent | xgboost | 2.5685 | 0.0968 | 5,468 |
| `plus_gb::lightgbm` | plus_gb | lightgbm | 2.6453 | 0.1348 | 5,468 |
| `incumbent::lightgbm` | incumbent | lightgbm | 2.6526 | 0.1269 | 5,468 |
| `plus_eb::lightgbm` | plus_eb | lightgbm | 2.6622 | 0.1493 | 5,468 |
| `plus_both::lightgbm` | plus_both | lightgbm | 2.6696 | 0.1517 | 5,468 |

