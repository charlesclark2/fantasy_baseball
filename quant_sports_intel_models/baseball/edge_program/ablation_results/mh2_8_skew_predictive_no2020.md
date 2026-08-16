# MH2.8 — a SKEW-CAPABLE `total_runs` predictive vs the served symmetric Normal

**Verdict: `INCUMBENT_STANDS`** · `best_alpha = 0` · **deploy-held**

> **What this study is.** A distributional-SHAPE bake-off against the defect MH2.6 measured on the SERVED rows. It says nothing about win rate, edge or ROI — at `best_alpha = 0` no bet rides on this model. Pre-registration: [`mh2_8_preregistration.md`](mh2_8_preregistration.md), committed BEFORE this harness computed anything.

## Population

| | |
|---|---|
| window | 2016–2026 (10 seasons) |
| folds | 7 purged + embargoed (3d) |
| rows | 20,588 (14,232 out-of-fold eval rows) |
| contract | 13-column served contract |
| field | 8 declared trials + 3 diagnostics (⛔ not trials) |
| ⚠️ sensitivity | seasons [2020] dropped from BOTH train and eval |

⚠️ **LOCK 1b — declared deviation, stated before any arm was scored.** The two E1 de-leak swaps are NOT applied: `_swap_stuff_plus_deleaked` needs Snowflake (forbidden here) and touches **no contract column** — a provable no-op, pinned by a guard test — while `_swap_bullpen_v3` touches 2 of the 13 and needs gitignored per-reliever caches absent from this worktree. ⇒ absolute LEVELS are **not** comparable to MH2.5's; the arm-to-arm comparison is unaffected because every arm reads the identical matrix.

## 1. ⭐ The design bar, stated BEFORE any fit

- required per-fold Sharpe at asymptotic `V`: **1.547**
- PBO evaluable at 7 folds × 8 arms: **True**
- DSR ceiling at ANY effect size: **0.9997**
- fold-consistency clause: **6 of 7 wins** required (calibrated, not a bare 60% — MH2 H8)

This is a statement about the DESIGN that no result can contaminate.

## 2. ⭐ The construction floor — the only thing nothing may beat

Under a correctly specified predictive the randomised PIT is EXACTLY uniform, so the attainable `pit_mdd` at n = 14,232 is the MDD of that many iid uniforms: median **0.0045**, 95% band [0.0025, 0.0074], 0.1st percentile **0.0016**. It is a CONSTRUCTION, not a fit, so an arm below its extreme lower tail is mathematically impossible.

- arms below the floor: **none** ✅

## 3. The leaderboard (pooled out of fold)

`pit_mdd` and `p_over_gap` are the PRIMARIES; CRPS is a **constraint**, never a criterion; coverage is a **FLOOR**, never a target.

| arm | role | `pit_mdd` | `p_over_gap` | stated / realized | CRPS | cov80 | cov50 | z skew |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `incumbent` | **THE BAR** | 0.0332 | 0.0571 | 0.500 / 0.443 | 2.5196 | 0.790 | 0.477 | 0.736 |
| `normal_recal` | ⭐ matched foil | 0.0318 | 0.0514 | 0.500 / 0.449 | 2.5194 | 0.816 | 0.499 | 0.738 |
| `climo` | ⚠️ nihilist | 0.0219 | -0.0040 | 0.397 / 0.401 | 2.5176 | 0.812 | 0.509 | 0.764 |
| `overskew` | degenerate | 0.0280 | -0.0237 | 0.427 / 0.451 | 2.5093 | 0.788 | 0.513 | 0.739 |
| `ngb_lognormal` | candidate | 0.0295 | -0.0454 | 0.392 / 0.438 | 2.5147 | 0.812 | 0.504 | 0.778 |
| `ngb_gamma` | candidate | 0.0145 | -0.0067 | 0.431 / 0.438 | 2.6045 | 0.806 | 0.505 | 0.746 |
| `lgbm_quantile` | candidate | 0.0388 | 0.0127 | 0.461 / 0.448 | 2.5266 | 0.733 | 0.447 | 0.756 |
| `skewnorm_recal` | candidate | 0.0074 | -0.0057 | 0.445 / 0.451 | 2.5033 | 0.797 | 0.499 | 0.739 |
| `oracle_skewnorm` | ⛔ diagnostic | 0.0049 | -0.0041 | 0.448 / 0.452 | 2.4914 | 0.802 | 0.503 | 0.742 |
| `oracle_lgbm_quantile` | ⛔ diagnostic | 0.0087 | 0.0042 | 0.462 / 0.458 | 1.7295 | 0.804 | 0.495 | 0.552 |
| `perm_shape` | ⛔ diagnostic | 0.0452 | 0.0109 | 0.461 / 0.450 | 2.5896 | 0.723 | 0.438 | 0.752 |

CRPS is computed IDENTICALLY for every arm on the shared 499-level quantile grid (`CRPS = 2∫pinball`). Validation against the Normal closed form on the incumbent: grid 2.5196 vs closed 2.5196 (|Δ| 0.00002).

### ⭐ Did the nihilist do what it was registered to do?

`climo` ignores every feature. Registered IN ADVANCE to WIN both primaries and LOSE CRPS — measured: `pit_mdd` 0.0219 vs the incumbent's 0.0332, `p_over_gap` -0.0040 vs 0.0571, CRPS 2.5176 vs 2.5196.

- nihilist cleared the full ship rule: **⛔** ✅ the sharpness constraint held

## 4. The fitted skew, per fold

| fold | eval | inner | cal | eval n | α̂ | a | b | peeking α |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2019 | 4,776 | 1,194 | 2,141 | 3.529 | -0.216 | 1.072 | 2.486 |
| 2 | 2021 | 6,475 | 1,619 | 2,091 | 3.098 | 0.415 | 1.090 | 3.187 |
| 3 | 2022 | 8,165 | 2,041 | 2,148 | 3.283 | -0.401 | 1.041 | 3.476 |
| 4 | 2023 | 9,864 | 2,466 | 2,151 | 3.109 | -0.300 | 1.029 | 2.985 |
| 5 | 2024 | 11,591 | 2,898 | 2,146 | 3.528 | -0.086 | 1.021 | 3.207 |
| 6 | 2025 | 13,322 | 3,330 | 2,025 | 3.175 | 0.217 | 1.034 | 3.753 |
| 7 | 2026 | 14,949 | 3,737 | 1,530 | 3.035 | -0.287 | 1.051 | 2.659 |

## 5. ⭐ The stratifier validation — published BEFORE any `Var(z)` is read

The exact step whose absence caused the MH2.1 rollback. Bars imported from MH2.5 verbatim.

- `incumbent_sigma` (PRIMARY): ρ = 0.612 (bar 0.3) · endpoints 1.92 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**
- `incumbent_mean` (SECONDARY): ρ = 0.721 (bar 0.3) · endpoints 4.56 SE apart (bar 2.0) → ✅ VALIDATED

> ⛔ No `Var(z)` is read off the primary partition. **This was pre-registered as the EXPECTED outcome** (MH2.5 found it fails when pooled across eras; MH2.6 found it fails on the served window) and it carries **no information about the skew hypothesis** — `Var(z)` is a SCALE instrument and this study is about SHAPE.

## 6. ⭐ The vacuity floor — the instrument is proven able to produce the OTHER answer

### Negative control — clean data must NOT flag

Outcomes redrawn from the incumbent's OWN per-fold predictive (40 replicates), the selection re-run each time. A harness that picks a skew arm on Normal data has not found skew in the real data — it has found its own preference.

- winner distribution: `{'incumbent': 22, 'normal_recal': 3, 'overskew': 2, 'skewnorm_recal': 13}`
- clean rate (`incumbent` or `normal_recal` selected): **0.625** against a pre-stated bar of 0.9 → ⛔

### Positive control — a KNOWN skew must be found AND selected

- true α = 3.0, 10 replicates → `skewnorm_recal` selected **1.000** of the time; winners `{'skewnorm_recal': 10}`

### MDE — what this design could and could not have detected

A null verdict means *"no shape defect larger than the MDE"*. Stating it is the difference between a measured null and a shrug (NF1.8).

| true α | detection rate |
|---:|---:|
| 0.0 | 0.23 |
| 0.5 | 0.25 |
| 1.0 | 0.84 |
| 1.5 | 1.00 |
| 2.0 | 1.00 |
| 2.5 | 1.00 |
| 3.0 | 1.00 |
| 4.0 | 1.00 |
| 5.0 | 1.00 |
| 6.0 | 1.00 |

**MDE at 80% power: α = 1.0**, at n = 14,232 out-of-fold games.

### Multiplicity and the MC-p floor

- BH at q = 0.05 across the declared verdict family (MH2.6 measured that omitting this drove the family-wise error to ≈50% and produced two wrong verdicts on CLEAN frames).
- MC null reps used **2,000** against a required minimum of **80** — so the smallest attainable p clears its own BH cutoff and no test is vacuous.

## 7. The deflation gates

- leader among the candidates: **`skewnorm_recal`**
- **PBO** 0.000 (bar < 0.2)
- **DSR** 0.3734 (bar ≥ 0.95) · binds: `degenerate_excluded_whole_field` · whole-field figure 0.6063
- DSR-CONV: degenerates `['climo', 'overskew']` are in `n_trials` (we DID try them) and OUT of `V` — **declared before the run**, because the exclusion is non-monotone and an arm qualifies BY DESIGN, never by declaration (MH2.5 / DSR-CONV).
- fold consistency: 7 wins of 7 against a required 6 → ✅

## 8. ⭐ The SERVED-ROW gate — MH2.1's rollback rule, as code

Served population: **634 rows**, 2026-06-23 → 2026-08-14, tier `post_lineup`. Every row post-dates the champion's fit, so the whole window is out of sample — MH2.1's "split at the incumbent's fit date" rule holds by construction.

The recalibration applied is the **last CV fold's** (`α = 3.035`, `a = -0.287`, `b = 1.051`), whose calibration split ends before the 2026 season — i.e. strictly BEFORE the served era. This is a PROSPECTIVE read.

| arm | `pit_mdd` | `p_over_gap` @ own mean | stated / realized | CRPS | cov80 | cov50 |
|---|---:|---:|---:|---:|---:|---:|
| `incumbent` | 0.0420 | 0.0662 | 0.500 / 0.434 | 2.5338 | 0.792 | 0.475 |
| `skewnorm_recal` | 0.0341 | -0.0079 | 0.448 / 0.456 | 2.5195 | 0.814 | 0.502 |
| `skew_only` | 0.0353 | 0.0142 | 0.448 / 0.434 | 2.5161 | 0.790 | 0.475 |
| `normal_recal` | 0.0483 | 0.0442 | 0.500 / 0.456 | 2.5285 | 0.822 | 0.491 |
| `overskew` | 0.0420 | -0.0281 | 0.428 / 0.456 | 2.5279 | 0.806 | 0.519 |
| `in_sample_ceiling` | 0.0325 | -0.0011 | 0.439 / 0.440 | 2.5148 | 0.804 | 0.486 |

MH2.6's calibrated-null band for `pit_mdd` was [0.0117, 0.0356]; the construction floor at this n is median 0.0215, 95% band [0.0117, 0.0353].

### ⭐ `P(over)` AT THE ACTUAL POSTED LINE — the served error, not the shape bound

MH2.6 could only measure this at the model's own mean and flagged the gap in its own §2. It is pre-registered here, so it is a planned read and not a post-hoc addition.


**`consensus` line** (line present on 0.995 of served rows)

| arm | stated `P(over)` | realized | gap |
|---|---:|---:|---:|
| `incumbent` | 0.5314 | 0.4754 | 0.0560 |
| `skewnorm_recal` | 0.4553 | 0.4754 | -0.0202 |
| `skew_only` | 0.4815 | 0.4754 | 0.0061 |
| `normal_recal` | 0.5053 | 0.4754 | 0.0299 |
| `overskew` | 0.4347 | 0.4754 | -0.0407 |
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
| `normal_recal` | 0.0013 | 0.0056 | -0.0002 |
| `climo` | 0.0112 | 0.0531 | -0.0020 |
| `overskew` | 0.0052 | 0.0334 | -0.0103 |
| `ngb_lognormal` | 0.0037 | 0.0116 | -0.0049 |
| `ngb_gamma` | 0.0187 | 0.0504 | 0.0849 |
| `lgbm_quantile` | -0.0056 | 0.0443 | 0.0069 |
| `skewnorm_recal` | 0.0258 | 0.0514 | -0.0163 |

## 10. Verdict

**`INCUMBENT_STANDS`**

- null state: **`DSR_UNREACHABLE`**
- reason: `pit_mdd`: the winner's per-fold Sharpe 2.296 sits at or BELOW the 8-arm field's deflated benchmark SR0 2.517, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, PRE-REGISTERED field, not more seasons — and ⛔ only if such a field was pre-registered; this is NOT a licence to re-cut a field you have already scored (MH2.7). `V` is DSR-CONV-correct (measured EXCLUDING the pre-registered lose-by-construction degenerates, which remain in `n_trials`), so the field-size reading below is about the EVIDENCE.
- detail: {'n_folds': 7, 'n_arms': 8, 'observed_sr': 2.296, 'sr0': 2.5165, 'var_trials_sr': 2.975027795002632, 'degenerates_excluded_from_v': True, 'declared_field_size': 8, 'declared_field_size_source': 'stated', 'field_remedy_admissible': False}
- field_remedy_admissible: False

⭐ **`field_remedy_admissible` is the MACHINE FLAG and it is what is read here, never the prose** (MH2.7). Its three states are distinct and only one of them is a lever:

- **`False` — the arithmetic sits BELOW the declared family.** The ≤N figure survives as arithmetic and the IMPERATIVE is REFUSED: this field's 8 arms ARE the declared minimum, and re-cutting a field you have already scored is the selection bias DSR exists to deflate (MH2.2).

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
uv run python betting_ml/scripts/mh2_8_skew_predictive.py --exclude-seasons 2020
```
