# MLB MH2.1 — WIDE-WINDOW retrain bake-off: total_runs (post_lineup)

> Re-run of E7.9's retrain on the **2016–2026** window (10 seasons ⇒ **7 folds**) with a **pre-registered 4-arm family**, under the FIXED DSR convention. Arm of the design: **SENSITIVITY (2020 dropped from train AND eval)**.

> ⚠️ **Not an edge claim.** `best_alpha = 0`. This decides whether the MiLB-MLE-corrected feature block and the newly-joined `eb_gb_pct` earn a retrained champion; it says nothing about win rate or ROI. A CRPS improvement on `total_runs` is a PRICING/CALIBRATION improvement, never an edge, a win rate, or an ROI.

> ⚠️ **NOT POINT-IN-TIME — every number here is a CEILING.** `load_features` reads each game's row as it exists NOW (post-game backfilled and dense); the live serve only ever saw the sparse pre-game row. Widening the window to 2016 WIDENS this exposure rather than shrinking it — the oldest rows have had the longest to be backfilled — so a wide-window score is if anything a MORE optimistic ceiling than E7.9's. The honest live figure comes from scoring the ACTUALLY-SERVED predictions (`honest_live_skill.py`), never from this matrix.

**VERDICT: `SHIP_CHALLENGER`**

- Honest metric **crps** (lower = better) · 4 arms × 7 purged/embargoed folds · 20,423 rows · seed 42
- Incumbent arm `incumbent::ngboost_normal` = 2.5225
- Leader `plus_eb::glm_elasticnet` = 2.4926 (margin +0.0299; noise floor 0.02)
- PBO 0.002 (gate < 0.2) · DSR 1.000 (gate ≥ 0.95)
- Oracle-floor sanity (E2.1-r): oracle crps = 0.000234; no candidate beat it ✅

## The design, and the bar it had to clear — both PRE-REGISTERED

- **Window** `2016–2026` — 10 seasons ⇒ **7 folds** (E7.9 ran 6 seasons ⇒ 3). Arm: **SENSITIVITY (2020 dropped from train AND eval)**. Excluded: [2020].
- **Field** 4 arms — the pre-registered family `['incumbent', 'plus_eb']` × `['ngboost_normal', 'glm_elasticnet']`, NOT E7.9's 28-arm grid. Declared in source before the run; no arm was dropped after a score was seen.

| design | folds | arms | required per-fold Sharpe for `DSR ≥ 0.95` | DSR ceiling at ANY effect | PBO evaluable |
|---|---:|---:|---:|---:|---|
| E7.9, as it ran | 3 | 28 | 7.279 | 0.9772 | False |
| **this run** | 7 | 4 | **1.314** | 0.9997 | True |

(Asymptotic `V = 1/n_obs`, the convention MH2 §7's design table used, so these are directly comparable to it. The bar at the run's MEASURED dispersion is stated in the DSR section below — it is not substituted for this one.)

## ⭐ LOCK 3 — the DSR convention, FIXED (MH2 defect 2)

E7.9 computed DSR on ~19 year-MONTH buckets and passed no `trial_sharpes`. **Both biases inflate DSR**: month-buckets inside one purged fold are not independent draws (the statistic scales with `√(n_obs−1)`), and omitting `trial_sharpes` substitutes the asymptotic `V = 1/n_obs` for the MEASURED cross-trial dispersion in `SR0 = √V·z(N)`. So **E7.9's recorded `DSR 0.842` is an OVERSTATEMENT of what that design supported** — which is exactly why a wide-window number scored the legacy way would not have been comparable to it.

| convention | observations | `n_obs` | trial dispersion `V` | DSR | binds |
|---|---|---:|---|---:|---|
| **FIXED** (per-fold + measured `trial_sharpes`) | purged folds | 7 | measured, 0.01030 | **1.000** | ✅ **YES** |
| legacy (E7.9 as recorded) | year-month buckets | 44 | asymptotic `1/n_obs` | 1.000 | no — reported only |

Leader's per-fold skill series (incumbent − leader, positive ⇒ leader better): mean `+0.02910`, SD `0.02452`, Sharpe `1.187` against a deflated benchmark `SR0 = 0.107`.

Trial Sharpes (non-reference arms — the incumbent IS the reference, so its identically-zero skill series is excluded from `V` per `h_harness.dsr_report`): `{'incumbent::glm_elasticnet': 0.9878, 'plus_eb::ngboost_normal': 1.0538, 'plus_eb::glm_elasticnet': 1.187}`.

**Sensitivity on the benchmark, so a high bar can be told from a broken one:** at the asymptotic `V = 1/n_obs` (the benchmark MH2 §7's design table used) the same series gives `SR0 = 0.398` and **DSR 1.000**, against the measured-`V` `SR0 = 0.107` / DSR 1.000. The MEASURED figure BINDS, as pre-registered — this line is disclosure, not a re-pick.

PBO is reported on BOTH surfaces: **0.002** on year-month buckets (pre-registered as binding, so the wide window stays comparable to E7.9 on this gate) and 0.000 at the coarser fold level.

## LOCK 2 — per-fold score BESIDE per-fold contract coverage

Coverage is **not uniform across the window** — the earlier folds lean harder on imputation. A lift that lives only in the thin folds is an imputation artifact, not a feature effect.

| fold | eval season | eval rows | contract coverage | contract cols STRUCTURALLY ABSENT | incumbent crps | leader crps | leader − incumbent |
|---:|---:|---:|---:|---|---:|---:|---:|
| 1 | 2019 | 2,142 | 0.835 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` | 2.5994 | 2.5888 | -0.0107 |
| 2 | 2021 | 2,090 | 0.910 | `away_lineup_bat_speed_vs_starter_velo` | 2.5348 | 2.4588 | -0.0760 |
| 3 | 2022 | 2,149 | 0.914 | `away_lineup_bat_speed_vs_starter_velo` | 2.4694 | 2.4540 | -0.0153 |
| 4 | 2023 | 2,151 | 0.950 | — | 2.5352 | 2.5163 | -0.0189 |
| 5 | 2024 | 2,146 | 0.990 | — | 2.4423 | 2.3925 | -0.0498 |
| 6 | 2025 | 2,025 | 0.995 | — | 2.5635 | 2.5432 | -0.0203 |
| 7 | 2026 | 1,362 | 0.990 | — | 2.5114 | 2.4987 | -0.0127 |

(`leader − incumbent` is NEGATIVE when the leader is better — the metric is lower-is-better.)

🚩 **A CONTRACT COLUMN IS ENTIRELY MISSING IN AT LEAST ONE EVAL FOLD: `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip`.** Those folds do NOT evaluate the served contract — the absent column imputes to a constant, so they score a structurally SMALLER model. A pooled coverage mean cannot express this, which is why the columns are named. ⚠️ Read any cross-fold difference in the light of this before attributing it to the `plus_eb` feature block: the early folds differ from the late ones in WHICH contract they are testing, not only in how noisy it is.

## ⚠️ Margin attribution — the margin is NOT purely a feature effect

The gate compares leader-arm vs incumbent-arm, where an arm is (contract variant × learner class). That is the right PROMOTION question, but it CONFLATES the feature effect with a learner-class swap. Split against `incumbent::glm_elasticnet` (the incumbent contract under the LEADER's learner):

| component | Δ crps | share of margin |
|---|---:|---:|
| **learner swap** (incumbent learner → `glm_elasticnet`) | +0.0186 | 62% |
| **contract** (added features) | +0.0113 | 38% |
| **total reported margin** | +0.0299 | 100% |

🚩 **62% of this margin is the LEARNER SWAP, not the features.** Do not read `+0.0299` as what the added columns bought — that figure is `+0.0113`.

### Feature effect holding the LEARNER FIXED (+ = variant better than the incumbent contract)

| learner | incumbent crps | plus_gb | plus_eb | plus_both |
|---|---:|---:|---:|---:|
| glm_elasticnet | 2.5039 | n/a | +0.0113 | n/a |
| ngboost_normal | 2.5225 | n/a | +0.0152 | n/a |

This table — not the headline margin — is where a FEATURE effect can be read.

## Pre-registered gates

| gate | result |
|---|---|
| `beats_incumbent_by_more_than_noise_floor` | ✅ pass |
| `pbo_lt_0_2` | ✅ pass |
| `dsr_gt_0_at_95` | ✅ pass |
| `calibration_not_degraded` | ✅ pass |

Calibration tolerance in effect: `0.00689` (pre-registration amendment #1, 2026-07-29 — max of a 0.001 absolute floor and 10% of the incumbent's PIT-KS).

**A challenger cleared every gate.** Promote per the model-promotion runbook, then run E7.9 step 7 (the historical prediction backfill) — labelled a BACKTEST, never a real-time record.

## Contract variants

| variant | features | added vs incumbent |
|---|---:|---|
| `incumbent` | 13 | — (the bar) |
| `plus_eb` | 23 | `away_avg_eb_bb_pct`, `away_avg_eb_iso`, `away_avg_eb_k_pct`, `away_starter_eb_bb_pct`, `away_starter_eb_k_pct`, `home_avg_eb_bb_pct`, `home_avg_eb_iso`, `home_avg_eb_k_pct`, `home_starter_eb_bb_pct`, `home_starter_eb_k_pct` |

## Full arm table

| arm | variant | learner | crps | PIT-KS | n |
|---|---|---|---:|---:|---:|
| `oracle_floor` | oracle_floor | - | 0.0002 | 0.5000 | 14,065 |
| `plus_eb::glm_elasticnet` | plus_eb | glm_elasticnet | 2.4926 | 0.0605 | 14,065 |
| `incumbent::glm_elasticnet` | incumbent | glm_elasticnet | 2.5039 | 0.0646 | 14,065 |
| `plus_eb::ngboost_normal` | plus_eb | ngboost_normal | 2.5073 | 0.0644 | 14,065 |
| `incumbent::ngboost_normal` | incumbent | ngboost_normal | 2.5225 | 0.0689 | 14,065 |

