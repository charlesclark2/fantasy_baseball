# MH2.8 — a SKEW-CAPABLE `total_runs` predictive vs the served symmetric Normal

**Verdict: `INCUMBENT_STANDS`** · `best_alpha = 0` · **deploy-held**

> **What this study is.** A distributional-SHAPE bake-off against the defect MH2.6 measured on the SERVED rows. It says nothing about win rate, edge or ROI — at `best_alpha = 0` no bet rides on this model. Pre-registration: [`mh2_8_preregistration.md`](mh2_8_preregistration.md), committed BEFORE this harness computed anything.

## Population

| | |
|---|---|
| window | 2016–2026 (11 seasons) |
| folds | 8 purged + embargoed (3d) |
| rows | 21,169 (14,813 out-of-fold eval rows) |
| contract | 13-column served contract |
| field | 8 declared trials + 3 diagnostics (⛔ not trials) |

⚠️ **LOCK 1b — declared deviation, stated before any arm was scored.** The two E1 de-leak swaps are NOT applied: `_swap_stuff_plus_deleaked` needs Snowflake (forbidden here) and touches **no contract column** — a provable no-op, pinned by a guard test — while `_swap_bullpen_v3` touches 2 of the 13 and needs gitignored per-reliever caches absent from this worktree. ⇒ absolute LEVELS are **not** comparable to MH2.5's; the arm-to-arm comparison is unaffected because every arm reads the identical matrix.

## 1. ⭐ The design bar, stated BEFORE any fit

- required per-fold Sharpe at asymptotic `V`: **1.386**
- PBO evaluable at 8 folds × 8 arms: **True**
- DSR ceiling at ANY effect size: **0.9999**
- fold-consistency clause: **6 of 8 wins** required (calibrated, not a bare 60% — MH2 H8)

This is a statement about the DESIGN that no result can contaminate.

## 2. ⭐ The construction floor — the only thing nothing may beat

Under a correctly specified predictive the randomised PIT is EXACTLY uniform, so the attainable `pit_mdd` at n = 14,813 is the MDD of that many iid uniforms: median **0.0045**, 95% band [0.0025, 0.0074], 0.1st percentile **0.0015**. It is a CONSTRUCTION, not a fit, so an arm below its extreme lower tail is mathematically impossible.

- arms below the floor: **none** ✅

## 3. The leaderboard (pooled out of fold)

`pit_mdd` and `p_over_gap` are the PRIMARIES; CRPS is a **constraint**, never a criterion; coverage is a **FLOOR**, never a target.

| arm | role | `pit_mdd` | `p_over_gap` | stated / realized | CRPS | cov80 | cov50 | z skew |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `incumbent` | **THE BAR** | 0.0300 | 0.0586 | 0.500 / 0.441 | 2.5374 | 0.793 | 0.484 | 0.743 |
| `normal_recal` | ⭐ matched foil | 0.0317 | 0.0536 | 0.500 / 0.446 | 2.5376 | 0.819 | 0.504 | 0.739 |
| `climo` | ⚠️ nihilist | 0.0216 | -0.0046 | 0.397 / 0.402 | 2.5175 | 0.811 | 0.509 | 0.773 |
| `overskew` | degenerate | 0.0264 | -0.0211 | 0.427 / 0.449 | 2.5272 | 0.791 | 0.519 | 0.739 |
| `ngb_lognormal` | candidate | 0.0283 | -0.0465 | 0.391 / 0.438 | 2.5220 | 0.813 | 0.508 | 0.810 |
| `ngb_gamma` | candidate | 0.0120 | -0.0049 | 0.431 / 0.436 | 2.6073 | 0.803 | 0.505 | 0.787 |
| `lgbm_quantile` | candidate | 0.0392 | 0.0124 | 0.458 / 0.446 | 2.5241 | 0.736 | 0.452 | 0.763 |
| `skewnorm_recal` | candidate | 0.0087 | -0.0026 | 0.446 / 0.449 | 2.5213 | 0.799 | 0.505 | 0.739 |
| `oracle_skewnorm` | ⛔ diagnostic | 0.0082 | -0.0050 | 0.448 / 0.453 | 2.5063 | 0.801 | 0.503 | 0.741 |
| `oracle_lgbm_quantile` | ⛔ diagnostic | 0.0087 | 0.0030 | 0.461 / 0.458 | 1.7168 | 0.808 | 0.502 | 0.562 |
| `perm_shape` | ⛔ diagnostic | 0.0447 | 0.0087 | 0.458 / 0.450 | 2.5884 | 0.727 | 0.439 | 0.772 |

CRPS is computed IDENTICALLY for every arm on the shared 499-level quantile grid (`CRPS = 2∫pinball`). Validation against the Normal closed form on the incumbent: grid 2.5374 vs closed 2.5374 (|Δ| 0.00002).

### ⭐ Did the nihilist do what it was registered to do?

`climo` ignores every feature. Registered IN ADVANCE to WIN both primaries and LOSE CRPS — measured: `pit_mdd` 0.0216 vs the incumbent's 0.0300, `p_over_gap` -0.0046 vs 0.0586, CRPS 2.5175 vs 2.5374.

- nihilist cleared the full ship rule: **⛔** ✅ the sharpness constraint held

## 4. The fitted skew, per fold

| fold | eval | inner | cal | eval n | α̂ | a | b | peeking α |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2019 | 4,776 | 1,194 | 2,141 | 3.529 | -0.216 | 1.072 | 2.486 |
| 2 | 2020 | 6,475 | 1,619 | 581 | 3.098 | 0.415 | 1.090 | 3.332 |
| 3 | 2021 | 6,954 | 1,738 | 2,091 | 2.475 | 0.343 | 1.113 | 2.924 |
| 4 | 2022 | 8,630 | 2,157 | 2,148 | 3.554 | -0.457 | 1.043 | 3.790 |
| 5 | 2023 | 10,329 | 2,582 | 2,151 | 3.391 | -0.405 | 1.024 | 3.028 |
| 6 | 2024 | 12,056 | 3,014 | 2,146 | 3.377 | -0.091 | 1.017 | 3.074 |
| 7 | 2025 | 13,786 | 3,447 | 2,025 | 3.222 | 0.241 | 1.045 | 3.705 |
| 8 | 2026 | 15,414 | 3,853 | 1,530 | 3.165 | -0.328 | 0.996 | 2.626 |

## 5. ⭐ The stratifier validation — published BEFORE any `Var(z)` is read

The exact step whose absence caused the MH2.1 rollback. Bars imported from MH2.5 verbatim.

- `incumbent_sigma` (PRIMARY): ρ = 0.467 (bar 0.3) · endpoints 2.75 SE apart (bar 2.0) → ✅ VALIDATED
- `incumbent_mean` (SECONDARY): ρ = 0.806 (bar 0.3) · endpoints 6.92 SE apart (bar 2.0) → ✅ VALIDATED

## 6. ⭐ The vacuity floor — the instrument is proven able to produce the OTHER answer

### Negative control — clean data must NOT flag

Outcomes redrawn from the incumbent's OWN per-fold predictive (40 replicates), the selection re-run each time. A harness that picks a skew arm on Normal data has not found skew in the real data — it has found its own preference.

- winner distribution: `{'incumbent': 16, 'normal_recal': 10, 'overskew': 1, 'skewnorm_recal': 13}`
- clean rate (`incumbent` or `normal_recal` selected): **0.650** against a pre-stated bar of 0.9 → ⛔

### Positive control — a KNOWN skew must be found AND selected

- true α = 3.0, 10 replicates → `skewnorm_recal` selected **1.000** of the time; winners `{'skewnorm_recal': 10}`

### MDE — what this design could and could not have detected

A null verdict means *"no shape defect larger than the MDE"*. Stating it is the difference between a measured null and a shrug (NF1.8).

| true α | detection rate |
|---:|---:|
| 0.0 | 0.25 |
| 0.5 | 0.31 |
| 1.0 | 0.82 |
| 1.5 | 1.00 |
| 2.0 | 1.00 |
| 2.5 | 1.00 |
| 3.0 | 1.00 |
| 4.0 | 1.00 |
| 5.0 | 1.00 |
| 6.0 | 1.00 |

**MDE at 80% power: α = 1.0**, at n = 14,813 out-of-fold games.

### Multiplicity and the MC-p floor

- BH at q = 0.05 across the declared verdict family (MH2.6 measured that omitting this drove the family-wise error to ≈50% and produced two wrong verdicts on CLEAN frames).
- MC null reps used **2,000** against a required minimum of **80** — so the smallest attainable p clears its own BH cutoff and no test is vacuous.

## 7. The deflation gates

- leader among the candidates: **`skewnorm_recal`**
- **PBO** 0.057 (bar < 0.2)
- **DSR** 0.0020 (bar ≥ 0.95) · binds: `degenerate_excluded_whole_field` · whole-field figure 0.0090
- DSR-CONV: degenerates `['climo', 'overskew']` are in `n_trials` (we DID try them) and OUT of `V` — **declared before the run**, because the exclusion is non-monotone and an arm qualifies BY DESIGN, never by declaration (MH2.5 / DSR-CONV).
- fold consistency: 7 wins of 8 against a required 6 → ✅

## 8. ⭐ The SERVED-ROW gate — MH2.1's rollback rule, as code

Served population: **634 rows**, 2026-06-23 → 2026-08-14, tier `post_lineup`. Every row post-dates the champion's fit, so the whole window is out of sample — MH2.1's "split at the incumbent's fit date" rule holds by construction.

The recalibration applied is the **last CV fold's** (`α = 3.165`, `a = -0.328`, `b = 0.996`), whose calibration split ends before the 2026 season — i.e. strictly BEFORE the served era. This is a PROSPECTIVE read.

| arm | `pit_mdd` | `p_over_gap` @ own mean | stated / realized | CRPS | cov80 | cov50 |
|---|---:|---:|---:|---:|---:|---:|
| `incumbent` | 0.0420 | 0.0662 | 0.500 / 0.434 | 2.5338 | 0.792 | 0.475 |
| `skewnorm_recal` | 0.0306 | -0.0127 | 0.446 / 0.459 | 2.5208 | 0.774 | 0.470 |
| `skew_only` | 0.0353 | 0.0125 | 0.446 / 0.434 | 2.5160 | 0.790 | 0.475 |
| `normal_recal` | 0.0467 | 0.0410 | 0.500 / 0.459 | 2.5284 | 0.787 | 0.478 |
| `overskew` | 0.0338 | -0.0315 | 0.427 / 0.459 | 2.5289 | 0.781 | 0.491 |
| `in_sample_ceiling` | 0.0325 | -0.0011 | 0.439 / 0.440 | 2.5148 | 0.804 | 0.486 |

MH2.6's calibrated-null band for `pit_mdd` was [0.0117, 0.0356]; the construction floor at this n is median 0.0215, 95% band [0.0117, 0.0353].

### ⭐ `P(over)` AT THE ACTUAL POSTED LINE — the served error, not the shape bound

MH2.6 could only measure this at the model's own mean and flagged the gap in its own §2. It is pre-registered here, so it is a planned read and not a post-hoc addition.


**`consensus` line** (line present on 0.995 of served rows)

| arm | stated `P(over)` | realized | gap |
|---|---:|---:|---:|
| `incumbent` | 0.5314 | 0.4754 | 0.0560 |
| `skewnorm_recal` | 0.4507 | 0.4754 | -0.0248 |
| `skew_only` | 0.4798 | 0.4754 | 0.0044 |
| `normal_recal` | 0.5020 | 0.4754 | 0.0266 |
| `overskew` | 0.4317 | 0.4754 | -0.0437 |
| `in_sample_ceiling` | 0.4676 | 0.4754 | -0.0078 |
- `bovada`: ⛔ not evaluable — only 0 rows carry a line (reported as UNVERIFIED, never scored healthy).

⛔ **`in_sample_ceiling` is a CEILING, not a result** — its α (3.979) was fitted ON the served rows and therefore sees the answer. It bounds what the mechanism could achieve; it may not be cited as evidence of what it WILL achieve.

⚠️ **PRE-REGISTERED ASYMMETRY.** Only arms that are a function of the served (μ, σ) can be read here: `['incumbent', 'normal_recal', 'skewnorm_recal', 'overskew']`. The learned families (`ngb_lognormal`, `ngb_gamma`, `lgbm_quantile`) would need a re-score from features, and the offline matrix is NOT point-in-time (MH2.5 Lock 9) — a re-score would be a CEILING, not the served number, which is the exact substitution MH2.1's rollback punished. ⇒ they are **`SERVED_UNVALIDATABLE` and cannot ship.**

## 9. The ship rule, clause by clause

| arm | `1` | `2` | `3` | `4` | `5` | `6` | `7` | `8` | `9` | `10` | ships |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `incumbent` | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `normal_recal` | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `climo` | ✅ | ✅ | ⛔ | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `overskew` | ✅ | ✅ | ⛔ | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `ngb_lognormal` | ✅ | ✅ | ⛔ | ⛔ | ✅ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `ngb_gamma` | ✅ | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `lgbm_quantile` | ✅ | ✅ | ⛔ | ✅ | ⛔ | ✅ | ⛔ | ⛔ | ✅ | ⛔ | ⛔ |
| `skewnorm_recal` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⛔ | ✅ | ✅ | ⛔ |

Legend — 1 nihilist did not clear · 2 no inversion · 3 beats incumbent on `pit_mdd` by ≥ 0.012 · 4 closes `|p_over_gap|` by ≥ 0.02 · 5 beats the MATCHED FOIL on both primaries · 6 CRPS non-inferior within 0.02 · 7 coverage floors (0.75/0.45) · 8 PBO+DSR · 9 fold consistency · 10 the SERVED-ROW gate.

### Margins vs the incumbent

| arm | `pit_mdd` gain | `|p_over_gap|` closed | CRPS Δ (− is better) |
|---|---:|---:|---:|
| `incumbent` | 0.0000 | 0.0000 | 0.0000 |
| `normal_recal` | -0.0018 | 0.0051 | 0.0002 |
| `climo` | 0.0083 | 0.0541 | -0.0199 |
| `overskew` | 0.0035 | 0.0376 | -0.0102 |
| `ngb_lognormal` | 0.0016 | 0.0122 | -0.0154 |
| `ngb_gamma` | 0.0180 | 0.0538 | 0.0698 |
| `lgbm_quantile` | -0.0092 | 0.0462 | -0.0134 |
| `skewnorm_recal` | 0.0213 | 0.0560 | -0.0162 |

## 10. Verdict

**`INCUMBENT_STANDS`**

- null state: **`DSR_UNREACHABLE`**
- reason: `pit_mdd`: the winner's per-fold Sharpe 0.460 sits at or BELOW the 8-arm field's deflated benchmark SR0 1.962, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- detail: {'n_folds': 8, 'n_arms': 8, 'observed_sr': 0.4602, 'sr0': 1.9617, 'var_trials_sr': 1.8078318660046049, 'degenerates_excluded_from_v': True, 'declared_field_size': 8, 'declared_field_size_source': 'stated', 'field_remedy_admissible': None}

⭐ **`field_remedy_admissible` is the MACHINE FLAG and it is what is read here, never the prose** (MH2.7). Its three states are distinct and only one of them is a lever:

- **`None` — FIELD SIZE IS NO LEVER AT ALL.** Not even a 2-arm field clears at this evidence, so there is nothing for a smaller field to be admissible ABOUT. ⛔ Do NOT read this as "re-run with fewer arms".

`declared_field_size_source` = `stated` — a claim about a DOCUMENT, not about the data. The document is `mh2_8_preregistration.md` §2, committed before this harness computed anything.

## 11. ⛔ Promotion is DEPLOY-HELD — the MH2.1 landmines, restated

- A ONE-TARGET SWAP BREAKS BUNDLE-ASSUMING CONSUMERS — `daily_model_predictions.model_version` is stamped from `registry['home_win']` only, the backfill idempotency key is `(game_pk, model_version, retrain_tag)`, and `mart_clv_labeled_games` hardcodes `v6`.
- SERVE THE OBJECT THAT WAS VALIDATED, NOT A RE-DERIVATION — a skew layer is a DIFFERENT distributional family, not a re-parameterisation; `predict_today`/the backfill call NGBoost's `pred_dist(X).params` verbatim, so whatever ships must persist exactly what was scored here.
- A MODEL-REGISTRY CHANGE SHIPS WITH THE BOX IMAGE ON MERGE TO `main` (`orchestration_cd.yml` `COPY . .`) — MERGING **IS** THE DEPLOY, with no gate between merge and serve.
- `best_alpha = 0` — no bet rides on this model, which is what made MH2.1's rollback cost one registry edit.

This harness never writes a registry entry, a pickle or a serving artifact. If an arm clears every clause the record hands the operator a DECISION, not a fait accompli.

## Reproduce

```bash
# LAPTOP. Snowflake-free (DuckDB over S3); requires AWS creds + the .env in this worktree.
uv run python betting_ml/scripts/mh2_8_skew_predictive.py
```
