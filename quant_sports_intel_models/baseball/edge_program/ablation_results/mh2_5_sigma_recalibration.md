# MH2.5 — make the served totals model's per-game σ generalize and widen its dynamic range

> ⚠️ **Not an edge claim.** `best_alpha = 0`, `bet_paused = true`. A pricing/calibration study; it says nothing about win rate, edge or ROI.

> 💸 **Snowflake-free and network-free** — reads only the local training-matrix parquet MH2.1's bake-off already cached, and HALTs rather than pulling if it is absent.

**VERDICT: `INCUMBENT_STANDS`**

⚪ **INCUMBENT_STANDS** — `var_glm_plus_sigma` is the best candidate at RMS |Var(z)−1| 0.0568 against the served σ's 0.1309 (level-only foil 0.0411, flat null 0.0905), and the gate(s) ['beats_matched_foil_materially', 'pbo_pass', 'dsr_pass', 'bh_pass'] did not clear. The null is classified `DSR_UNREACHABLE`.

- `total_runs` / `post_lineup` · window **2016–2026** · **8 purged/embargoed folds** · 20,055 rows (13,982 out-of-fold eval rows) · 13-column served contract
- Field: **9 pre-registered arms** (declared, not discovered) — `incumbent`, `level_only`, `flat_sigma`, `over_disperse`, `under_disperse`, `power_widen`, `iso_widen`, `var_glm`, `var_glm_plus_sigma`
- Diagnostic anchors, ⛔ **excluded from `n_trials`, from DSR's `V` and from PBO** (MH2.1 (a) — a diagnostic anchor is never a trial): `oracle_power`, `oracle_iso`, `oracle_var_glm`, `oracle_var_glm_plus_sigma`, `oracle_bin`, `perm_sigma`

⚠️ **NOT POINT-IN-TIME — every number here is a CEILING.** `load_features` reads each game's row as it exists NOW (post-game backfilled and dense); the live serve only ever saw the sparse pre-game row. The honest live figure comes from scoring the ACTUALLY-SERVED predictions, never from this matrix. This binds the LEVELS; the arm-to-arm COMPARISON is unaffected because every arm reads the identical matrix.

## 0. The premise test — does the widener want to widen?

> MH2.5 (from mh2_1_rollback.md §3): the served per-game σ UNDER-expresses heteroscedasticity, so its dynamic range should be WIDENED.

`power_widen` is a WIDENER by construction: γ is free over [0.0, 3.0], **γ = 1 reproduces the served σ exactly, γ > 1 widens its dynamic range, γ < 1 narrows it.** So which side of 1 the in-fold NLL fit lands on tests the premise directly, with no interpretation and nothing to argue about.

**Fitted γ̂ landed BELOW 1 — i.e. the widener chose to NARROW — in 8 of 8 folds** (γ̂ = 0.71, 0.77, 0.63, 0.24, 0.11, 0.21, 0.25, 0.19). The **peeking** oracle, which is allowed to see the answer, chose γ < 1 in 8 of 8 and lands lower still (0.29, 0.08, 0.13, 0.00, 0.35, 0.13, 0.49, 0.02).

Independently, the per-fold dispersion match (σ's own range ÷ the realized-SD range across the same bins) exceeds 1 — meaning σ's dynamic range is **WIDER** than the dispersion it can resolve — in **8 of 8 folds** (1.10, 1.43, 1.31, 1.63, 1.31, 1.17, 1.10, 1.17).

**⇒ PREMISE REFUTED — the widener chose to NARROW.**

### 0b. 🪤 How much of σ's spread is fit noise?

`NGBRegressor(random_state=...)` seeds NGBoost's own minibatching and line search — **it does NOT seed the base learner.** The default base is a `DecisionTreeRegressor` built with `random_state=None`, so it breaks split ties off numpy's GLOBAL RNG. Two fits of the identical class on the identical rows with the identical `seed` therefore disagree.

Measured on the last fold (1,440 games), seeds 42 vs 43, everything else held fixed:

- per-game **run-to-run SD of σ: 0.0090** (max single-game disagreement **0.299**)
- **cross-game SD of σ: 0.2455** — i.e. how much σ actually varies between games
- ⇒ **noise-to-signal 0.037**

⭐ **HYPOTHESIS REFUTED BY ITS OWN MEASUREMENT, and recorded as such.** The obvious explanation for §1 — "σ's dynamic range is mostly refit noise, so of course it cannot order games by volatility" — is WRONG here: refit noise is only **3.7%** of σ's cross-game spread. The served σ genuinely varies between games; it simply varies in a way that does not track realized dispersion out of fold. That is a harder and more interesting finding than a noise story, and it is why this was measured rather than argued.

⚠️ **A SMOKE-SCALE PROBE WOULD HAVE SUPPORTED THE WRONG CONCLUSION.** The same check at 120 estimators on 4,000 rows (the scale a `--smoke` harness check runs at) put the max single-game disagreement at **0.39** — ~9% of σ — which reads as "σ is mostly noise". At the real 400 estimators on 14,594 rows it is **0.299**. Refit noise is capacity- and n-dependent, so a reproducibility figure must be quoted at the FITTING SCALE THAT SHIPS.

⚠️ **Not local to MH2.5** — every NGBoost bake-off in this repo inherits it, and any recorded per-game σ figure produced without seeding the global RNG is not re-derivable. This harness seeds `np.random.seed(seed)` immediately before each fit; the run above is reproducible, earlier MH2.x/E7.9/E1.9 σ figures are not.

## 1. The method lock — the stratifier is validated BEFORE any Var(z) is read

MH2.1 was rolled back because a conditional-calibration result was read off a partition nobody had checked. A σ-CV floor, a matched foil and a permutation null were all present and none of them asks the load-bearing question: **do these bins actually separate realized dispersion?** So that table comes first here, and a partition that fails its pre-registered bar (ρ ≥ 0.3 and endpoints ≥ 2.0 SE apart) is DISQUALIFIED — no number is read off it.

### `incumbent_sigma` — ⛔ DISQUALIFIED · **PRE-REGISTERED PRIMARY**

FAILS the pre-registered bar (ρ=0.648 vs 0.3, endpoints 0.90 SE apart vs 2.0) — DISQUALIFIED, no Var(z) may be read off this partition

- Spearman ρ(bin, realized SD) = **0.648** · endpoints **0.90 SE** apart
- ⭐ **Dynamic range:** the stratifier moves **×1.554** across its bins while realized SD moves **×1.024** — a match ratio of **1.517** (1.000 = the stratifier expresses exactly as much dispersion as there is; **< 1 = UNDER-expressed**, **> 1 = OVER-expressed**, i.e. a σ whose dynamic range is wider than the dispersion it can actually resolve).

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,399 | 3.548 | 4.455 | 0.084 | 3.478 |
| 1 | 1,398 | 3.944 | 4.447 | 0.084 | 3.522 |
| 2 | 1,398 | 4.086 | 4.441 | 0.084 | 3.488 |
| 3 | 1,398 | 4.177 | 4.487 | 0.085 | 3.550 |
| 4 | 1,398 | 4.258 | 4.475 | 0.085 | 3.541 |
| 5 | 1,398 | 4.332 | 4.555 | 0.086 | 3.620 |
| 6 | 1,398 | 4.404 | 4.402 | 0.083 | 3.488 |
| 7 | 1,398 | 4.498 | 4.703 | 0.089 | 3.801 |
| 8 | 1,398 | 4.669 | 4.763 | 0.090 | 3.755 |
| 9 | 1,399 | 5.514 | 4.563 | 0.086 | 3.659 |

### `incumbent_mean` — ✅ VALID · pre-registered secondary

realized dispersion rises across the bins

- Spearman ρ(bin, realized SD) = **0.879** · endpoints **6.41 SE** apart
- ⭐ **Dynamic range:** the stratifier moves **×1.472** across its bins while realized SD moves **×1.188** — a match ratio of **1.239** (1.000 = the stratifier expresses exactly as much dispersion as there is; **< 1 = UNDER-expressed**, **> 1 = OVER-expressed**, i.e. a σ whose dynamic range is wider than the dispersion it can actually resolve).

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,399 | 7.767 | 4.229 | 0.080 | 3.324 |
| 1 | 1,398 | 8.334 | 4.275 | 0.081 | 3.409 |
| 2 | 1,398 | 8.544 | 4.457 | 0.084 | 3.486 |
| 3 | 1,398 | 8.715 | 4.270 | 0.081 | 3.408 |
| 4 | 1,398 | 8.877 | 4.470 | 0.085 | 3.505 |
| 5 | 1,398 | 9.068 | 4.445 | 0.084 | 3.531 |
| 6 | 1,398 | 9.282 | 4.700 | 0.089 | 3.735 |
| 7 | 1,398 | 9.538 | 4.603 | 0.087 | 3.659 |
| 8 | 1,398 | 9.940 | 4.606 | 0.087 | 3.661 |
| 9 | 1,399 | 11.435 | 5.025 | 0.095 | 4.184 |

### `incumbent_sigma_within_fold` — ⛔ DISQUALIFIED · ⚠️ **POST-HOC — diagnostic only, cannot ship**

FAILS the pre-registered bar (ρ=0.758 vs 0.3, endpoints 1.66 SE apart vs 2.0) — DISQUALIFIED, no Var(z) may be read off this partition

- Spearman ρ(bin, realized SD) = **0.758** · endpoints **1.66 SE** apart
- ⭐ **Dynamic range:** realized SD moves **×1.045** across these bins. (This stratifier is RANK-valued, so it has no meaningful range ratio of its own and no dispersion-match figure is quoted.)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,399 | 0.050 | 4.424 | 0.084 | 3.465 |
| 1 | 1,398 | 0.150 | 4.392 | 0.083 | 3.497 |
| 2 | 1,398 | 0.250 | 4.366 | 0.083 | 3.407 |
| 3 | 1,398 | 0.350 | 4.538 | 0.086 | 3.611 |
| 4 | 1,398 | 0.450 | 4.380 | 0.083 | 3.484 |
| 5 | 1,398 | 0.550 | 4.663 | 0.088 | 3.695 |
| 6 | 1,398 | 0.650 | 4.551 | 0.086 | 3.629 |
| 7 | 1,398 | 0.750 | 4.614 | 0.087 | 3.663 |
| 8 | 1,398 | 0.850 | 4.767 | 0.090 | 3.768 |
| 9 | 1,399 | 0.950 | 4.625 | 0.087 | 3.685 |

### The same validation, PER FOLD (quintiles) — pooled failure vs per-fold failure

A pooled partition can fail because the SIGNAL is absent or because the POOLING mixes eras. Only the per-fold tables tell those apart, and the pre-registration did not ask for them — they are reported here because the pooled primary failed.

| eval year | n | ρ | endpoints (SE) | σ range | realized-SD range | dispersion match |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 1,999 | +0.900 | +2.94 | ×1.273 | ×1.159 | 1.099 |
| 2020 | 547 | +0.100 | +0.36 | ×1.481 | ×1.035 | 1.431 |
| 2021 | 1,951 | +0.800 | +0.67 | ×1.351 | ×1.035 | 1.306 |
| 2022 | 2,008 | -0.900 | -2.32 | ×1.453 | ×0.890 | 1.632 |
| 2023 | 2,011 | +1.000 | +3.00 | ×1.522 | ×1.162 | 1.310 |
| 2024 | 2,001 | +0.000 | +0.73 | ×1.215 | ×1.037 | 1.172 |
| 2025 | 2,025 | +0.900 | +2.01 | ×1.215 | ×1.105 | 1.100 |
| 2026 | 1,440 | +0.600 | +0.59 | ×1.215 | ×1.035 | 1.174 |

## ⛔ EVERYTHING BELOW IS NON-BINDING

The PRE-REGISTERED primary partition (`incumbent_sigma`) was DISQUALIFIED above, so **nothing in this run can ship, whatever the gates say.** The scores below are computed on `incumbent_mean` — reported because a disqualified headline is not a reason to withhold the diagnostic a successor needs, and short-circuited in code so no amount of downstream green can launder it. Read them as *what a successor would pre-register*, never as a result.

## 2. Pooled out-of-fold scores on the scoring partition (`incumbent_mean`  — ⛔ NON-BINDING)

**RMS |Var(z) − 1| is the selection metric** and it is anchored on the ANALYTIC truth `Var(z) = 1`, never on the incumbent — an incumbent-relative metric inverts whenever the incumbent is the defective one and can only ever say *different*, never *better* (MH2.1 (b)). CRPS and PIT-KS are reported as sanity and are structurally BLIND here: CRPS is mean-dominated and every arm shares the identical mean, and PIT-KS is marginal, so a model that over-covers the calm games exactly as much as it under-covers the volatile ones passes it while being badly miscalibrated conditionally.

⚠️ The metric's own **noise floor at these bin sizes is 0.0378** — the RMS a PERFECTLY calibrated model posts here. A difference smaller than that is not a measurement.

| arm | RMS &#124;Var(z)−1&#124; | pooled Var(z) | Winkler | cov@80% | CRPS | PIT-KS | mean σ | σ CV | σ p90/p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `level_only` | 0.0411 | 1.0028 | 15.898 | 0.8195 | 2.5435 | 0.0575 | 4.604 | 0.1289 | 1.265 |
| **`var_glm_plus_sigma`** | 0.0568 | 0.9989 | 15.894 | 0.8186 | 2.5435 | 0.0576 | 4.607 | 0.1160 | 1.286 |
| `var_glm` | 0.0602 | 1.0022 | 15.803 | 0.8146 | 2.5393 | 0.0574 | 4.556 | 0.0842 | 1.215 |
| `power_widen` | 0.0753 | 1.0120 | 15.771 | 0.8130 | 2.5378 | 0.0568 | 4.522 | 0.0538 | 1.110 |
| `iso_widen` | 0.0776 | 1.0405 | 15.815 | 0.8095 | 2.5402 | 0.0566 | 4.504 | 0.0886 | 1.150 |
| `flat_sigma` | 0.0905 | 1.0025 | 15.755 | 0.8150 | 2.5371 | 0.0571 | 4.532 | 0.0267 | 1.078 |
| `incumbent` | 0.1309 | 1.1301 | 15.871 | 0.7889 | 2.5434 | 0.0606 | 4.343 | 0.1302 | 1.258 |
| `over_disperse` | 0.5586 | 0.4457 | 18.945 | 0.9507 | 2.6903 | 0.1221 | 6.906 | 0.1289 | 1.265 |
| `under_disperse` | 1.2394 | 2.2564 | 17.287 | 0.6133 | 2.6140 | 0.1184 | 3.069 | 0.1289 | 1.265 |
| *— diagnostics below: NOT trials —* | | | | | | | | | |
| `oracle_power` | 0.0786 | 0.9885 | 15.741 | 0.8158 | 2.5365 | 0.0572 | 4.560 | 0.0468 | 1.130 |
| `oracle_iso` | 0.0576 | 0.9903 | 15.715 | 0.8153 | 2.5348 | 0.0569 | 4.552 | 0.0734 | 1.168 |
| `oracle_var_glm` | 0.0481 | 0.9895 | 15.719 | 0.8159 | 2.5335 | 0.0563 | 4.563 | 0.1016 | 1.273 |
| `oracle_var_glm_plus_sigma` | 0.0478 | 0.9895 | 15.717 | 0.8163 | 2.5334 | 0.0564 | 4.562 | 0.1030 | 1.277 |
| `oracle_bin` | 0.0000 | 1.0094 | 15.698 | 0.8098 | 2.5343 | 0.0568 | 4.508 | 0.0506 | 1.179 |
| `perm_sigma` | 0.0988 | 1.0069 | 15.937 | 0.8138 | 2.5458 | 0.0575 | 4.604 | 0.1289 | 1.265 |

## 3. The anchors — read these BEFORE the leader's number

A metric a degenerate WINS cannot select anything, and an arm that beats a peeking version of its own form means the metric is inverted, not that the arm is good. Both are checked here and both are two-sided.

- ⭐ **THE INVERSION GATE — `oracle_bin`, the CONSTRUCTION floor.** Each bin is given its own REALIZED SD as σ on the very partition the headline is scored over, so it is conditionally calibrated by construction rather than by fitting. It scores **0.0000** against the analytic noise floor **0.0378** — i.e. this is how small a difference is even MEASURABLE here. Respected by every arm = **True**.

- **PER-FORM peeking arms — a HEADROOM diagnostic, ⛔ NOT a gate.** One per candidate, because the forms NEST and a single ceiling would veto a legitimately-better nested form (NF-D16 g‴). ⚠️ **Beating one is NOT an inversion**: a peeking oracle is a floor only at matched FAMILY *and* matched SAMPLE (NF1.7 (b)), and matched sample is often unobtainable here — an oracle can only be fitted on eval rows, of which there are fewer than the calibration split in most folds. NF-D14: *a winner can legitimately beat a peeking oracle at unmatched n.* Positive headroom = the design left achievable widening on the table.

| arm | its score | same form, PEEKING | headroom |
|---|---:|---:|---:|
| `power_widen` | 0.0753 | 0.0786 | -0.0033 |
| `iso_widen` | 0.0776 | 0.0576 | +0.0199 |
| `var_glm` | 0.0602 | 0.0481 | +0.0121 |
| `var_glm_plus_sigma` | 0.0568 | 0.0478 | +0.0090 |

- **Degenerates must LOSE** (NF1.8 (3), two-sided): `over_disperse` ✅ · `under_disperse` ✅. A *constraint* a degenerate satisfies is fine; a *criterion* a degenerate wins is fatal.
- ⚠️ **The flat-σ NULL TO BEAT** (MH2.1's rolled-back winner shape — ⛔ do NOT carry its claim that it beat the incumbent): the leader beats it.
- **Permutation anchor** — permuting σ destroys the σ↔dispersion link while preserving σ's marginal, so `perm_sigma` was registered in advance to degrade to roughly `flat_sigma`. Measured: `perm_sigma` 0.0988 vs `flat_sigma` 0.0905 ⇒ degraded as registered = **True**.

## 3b. ⚠️ The two pre-registered readings do not want the same σ

`RMS |Var(z) − 1|` is a **second-moment** target. Central-80% coverage and the Winkler score are **bulk/quantile** targets. On a Normal they coincide; on a fat-tailed residual they do not — the variance is inflated by the tails while the 80% interval is set by the middle — so the σ that makes `Var(z) = 1` is WIDER than the σ that makes coverage 0.80.

- Excess kurtosis of the served model's `z`: **+0.939** (a Normal is 0)
- σ multiplier that sets **Var(z) = 1**: **×1.0630**
- σ multiplier that sets **coverage = 0.80**: **×1.0224**

⭐ **This matters for what a fix would mean operationally.** Served `P(over)` at a line is a CDF read NEAR THE MIDDLE of the predictive, i.e. it lives in the quantile regime, not the second-moment regime. A rescale chosen to satisfy the primary metric is therefore not automatically an improvement to the number the product actually serves, and this study does not claim it is. Reported because the primary and secondary readings DISAGREED in this run — the E2.1-r discipline applied to the gap between two metrics rather than to one of them.

## 4. Does σ GENERALIZE? — in-fold vs out-of-fold

The other half of the target. An arm that widens its σ but only fits the fold it was calibrated on reproduces the defect instead of fixing it; the gap below is the diagnostic. In-fold = the held-out calibration split each recalibrator was fitted on; out-of-fold = the purged eval rows.

| arm | in-fold RMS | out-of-fold RMS | gap |
|---|---:|---:|---:|
| `power_widen` | 0.1086 | 0.1630 | +0.0543 |
| `level_only` | 0.1575 | 0.1660 | +0.0084 |
| `var_glm` | 0.1159 | 0.1788 | +0.0629 |
| `iso_widen` | 0.0936 | 0.1919 | +0.0983 |
| `var_glm_plus_sigma` | 0.1147 | 0.2015 | +0.0868 |
| `incumbent` | 0.2256 | 0.2290 | +0.0035 |

## 5. Each arm on ITS OWN σ — a diagnostic, ⛔ never the criterion

"Does your σ mean what you say it means?" A flat-σ arm induces **no partition at all**, so an own-σ reading would be vacuously perfect — which is exactly why this can never be the selection metric (it is a criterion the degenerate wins outright, NF1.8).

| arm | own-σ partition valid | ρ | σ range | realized-SD range | dispersion match | RMS on own σ |
|---|:--:|---:|---:|---:|---:|---:|
| `incumbent` | ⛔ | 0.648 | ×1.554 | ×1.024 | 1.517 | 0.2478 |
| `level_only` | ⛔ | 0.758 | ×1.543 | ×1.015 | 1.520 | 0.1863 |
| `flat_sigma` | ✅ | 0.503 | ×1.079 | ×1.082 | 0.997 | 0.0600 |
| `over_disperse` | ⛔ | 0.758 | ×1.543 | ×1.015 | 1.520 | 0.5612 |
| `under_disperse` | ⛔ | 0.758 | ×1.543 | ×1.015 | 1.520 | 1.3206 |
| `power_widen` | ⛔ | 0.685 | ×1.205 | ×1.019 | 1.183 | 0.0831 |
| `iso_widen` | ⛔ | 0.794 | ×1.362 | ×1.017 | 1.339 | 0.1801 |
| `var_glm` | ✅ | 0.830 | ×1.343 | ×1.155 | 1.163 | 0.0967 |
| `var_glm_plus_sigma` | ✅ | 0.842 | ×1.502 | ×1.087 | 1.382 | 0.1693 |
| `oracle_power` | ✅ | 0.915 | ×1.175 | ×1.171 | 1.003 | 0.0217 |
| `oracle_iso` | ✅ | 0.976 | ×1.276 | ×1.263 | 1.010 | 0.0281 |
| `oracle_var_glm` | ✅ | 0.952 | ×1.422 | ×1.303 | 1.091 | 0.0617 |
| `oracle_var_glm_plus_sigma` | ✅ | 0.988 | ×1.428 | ×1.318 | 1.084 | 0.0545 |
| `oracle_bin` | ✅ | 1.000 | ×1.082 | ×1.082 | 1.000 | 0.0005 |
| `perm_sigma` | ⛔ | 0.539 | ×1.543 | ×1.050 | 1.469 | 0.1851 |

## 6. The pre-registered decision rule

Leader = **`var_glm_plus_sigma`**. Every clause below was fixed in source before any arm scored.

| gate | requirement | measured | pass |
|---|---|---:|:--:|
| material gain vs the SERVED σ | > 0.05 RMS | +0.0741 | ✅ |
| ⭐ material gain vs the LEVEL-ONLY matched foil | > 0.05 RMS | -0.0157 | ⛔ |
| beats the flat-σ NULL | — | 0.0905 vs 0.0568 | ✅ |
| beats BOTH degenerates | — | — | ✅ |
| PBO | < 0.2 | 0.6429 | ⛔ |
| DSR (fixed convention, measured V) | ≥ 0.95 | 0.0000 | ⛔ |
| BH-FDR over the 4 real candidates | q = 0.05 | — | ⛔ |
| central-80% coverage FLOOR (⛔ never a target) | ≥ incumbent − 0.01 | 0.8186 vs 0.7889 | ✅ |

- Fold consistency (reported, not a gate here): the leader beats the served σ in **4/8** folds.
- DSR detail — observed per-fold Sharpe **0.347** vs bar **SR0 = 4.390** at 9 trials; measured cross-trial dispersion V = 8.3314. The incumbent is the REFERENCE and is excluded from V (its skill-vs-itself series is identically zero); `n_trials` stays the full field.

### ⭐ Deflation sensitivity — is the DSR failure EVIDENTIAL or ARITHMETIC?

⛔ **NON-BINDING AND NOT A RESCUE.** The gate above stands exactly as pre-registered. This block exists so the record can say WHY it failed, and so a successor can pre-register the convention rather than discover it (MH2.2).

Measured per-arm trial Sharpes: `[0.6343, 0.4626, -1.3589, -7.6353, 0.5613, 0.826, 0.5803, 0.3469]`. The two entries at `[-1.3589, -7.6353]` are the pre-registered DEGENERATES — arms that exist to LOSE. Because `SR0 = √V·z(N)` scales with the cross-trial Sharpe **dispersion**, an arm that loses hugely and CONSISTENTLY inflates the bar just as effectively as one that wins hugely:

| | V | SR0 | observed SR | DSR |
|---|---:|---:|---:|---:|
| **as gated** (full declared field) | 8.331 | 4.390 | 0.347 | 7.177e-27 |
| V excluding the designed losers | 0.026 | 0.246 | 0.347 | 0.6047 |

⭐ **This is MH2.1 (a) mirrored.** There, a DIAGNOSTIC anchor leaked into the trial field and set the gate's own bar. Here, a pre-registered degenerate — which correctly IS a trial for MULTIPLICITY — sets the bar through **V**, by losing consistently. `dsr_gate`'s existing guard does not catch it (it flags |Sharpe| > 10). The two rules that collide are each right on their own: NF1.8/NF1.7 require degenerates in the field to prove the metric is two-sided, and MH2 §a requires the full declared field in `n_trials`. ⭐ Note the repo ALREADY resolves this same tension for the reference arm — `dsr_gate` keeps the incumbent in `n_trials` while excluding it from `V`, on the grounds that a designed-constant skill series is not evidence about dispersion. Extending that to lose-by-construction anchors is the same argument, not a new one.

- PBO as gated (whole declared field): **0.6429** · PBO over CONTENDERS only (degenerates dropped, NF1.8): **0.7286**
- Whole-field spread **1.1983** vs contender (top-quartile) spread **0.0157** — NF1.8: a spread computed over a field that CONTAINS its own nulls measures the nulls.
- Per-fold winner counts (the cheap flip statistic): `{'power_widen': 1, 'flat_sigma': 1, 'iso_widen': 2, 'incumbent': 3, 'level_only': 1}` — mass on a single arm is a stable pick; mass spread thinly over unrelated arms is a search that learnt nothing.

### BH-FDR, paired across folds against the served σ

| arm | mean per-fold gain | p (one-sided) | BH cutoff | passes |
|---|---:|---:|---:|:--:|
| `iso_widen` | +0.03717 | 0.0261 | 0.0125 | ⛔ |
| `var_glm` | +0.05028 | 0.0724 | 0.0250 | ⛔ |
| `power_widen` | +0.06607 | 0.0782 | 0.0375 | ⛔ |
| `var_glm_plus_sigma` | +0.02753 | 0.1796 | 0.0500 | ⛔ |

## 7. What KIND of null this is (`cv_power.classify_null`)

**`DSR_UNREACHABLE`** — `crps`: the winner's per-fold Sharpe 0.347 sits at or BELOW the 9-arm field's deflated benchmark SR0 4.390, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons.

- Re-test trigger: **NOT rescuable by field size either — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)**
- ⚠️⚠️ **THIS CLASSIFICATION INHERITS THE SAME `V` ARTIFACT AND MUST NOT BE QUOTED BARE.** `classify_null` is handed the binding `var_trials_sr`, which the lose-by-construction degenerates inflate (8.331 vs 0.0262 without them). Its `DSR_UNREACHABLE` label — and in particular its "not rescuable by field size, the only lever left is a lower-variance design" remedy — is therefore a statement about the anchor arithmetic, NOT about the evidence. Read it beside §6's sensitivity table. This is the third member of the MH2.2 family: **the instrument's own remedy text is only as trustworthy as the quantity it was handed.**
- ⚠️ **THE INSTRUMENT'S OWN REMEDY IS SUSPECT HERE (MH2.2).** `classify_null` sees only a TRIAL COUNT and cannot tell a DECLARED narrow family from a DISCOVERED one, so a "re-test at a field of ≤0" trigger would prescribe shrinking BELOW this story's pre-registered 9-arm family — which re-commits the very selection bias DSR exists to deflate. ⛔ Do not act on it.
- Detail: `{"n_folds": 8, "n_arms": 9, "observed_sr": 0.3469, "sr0": 4.3896, "required_per_fold_sr_at_measured_V": 7.931, "fold_skill_sd": 0.07938, "min_detectable_crps_lift": 0.62956, "pre_registered_meaningful_crps_lift": 0.02}`

## 8. Per-fold detail

| eval year | inner-train | cal split | eval | fitted γ̂ (power) | peeking oracle γ |
|---:|---:|---:|---:|---:|---:|
| 2019 | 4,550 | 1,137 | 1,999 | 0.710 | 0.292 |
| 2020 | 6,157 | 1,539 | 547 | 0.772 | 0.079 |
| 2021 | 6,603 | 1,651 | 1,951 | 0.626 | 0.129 |
| 2022 | 8,170 | 2,042 | 2,008 | 0.241 | 0.000 |
| 2023 | 9,759 | 2,440 | 2,011 | 0.108 | 0.354 |
| 2024 | 11,373 | 2,843 | 2,001 | 0.209 | 0.127 |
| 2025 | 12,988 | 3,247 | 2,025 | 0.251 | 0.486 |
| 2026 | 14,594 | 3,649 | 1,440 | 0.192 | 0.023 |

γ̂ is the fitted exponent of the widener `σ' = a·σ̄·(σ/σ̄)^γ`. **γ = 1 is the incumbent, γ = 0 is the flat null, γ > 1 WIDENS.** The peeking oracle's γ (fitted on the eval fold itself) is the value that would have been optimal with hindsight — the gap between the two is how much of the widening the design could actually learn in advance.

| eval year | `incumbent` | `level_only` | `flat_sigma` | `over_disperse` | `under_disperse` | `power_widen` | `iso_widen` | `var_glm` | `var_glm_plus_sigma` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 0.3212 | 0.1697 | 0.1858 | 0.5334 | 1.4310 | 0.1668 | 0.2119 | 0.1750 | 0.2063 |
| 2020 | 0.6819 | 0.4286 | 0.2676 | 0.4680 | 1.9815 | 0.3636 | 0.6205 | 0.4685 | 0.5362 |
| 2021 | 0.1999 | 0.1654 | 0.1749 | 0.6043 | 1.0576 | 0.1682 | 0.1520 | 0.2048 | 0.2968 |
| 2022 | 0.0789 | 0.1245 | 0.1136 | 0.6019 | 1.0320 | 0.1084 | 0.0991 | 0.0888 | 0.0875 |
| 2023 | 0.1382 | 0.1044 | 0.1287 | 0.5560 | 1.2795 | 0.1178 | 0.1031 | 0.1230 | 0.1128 |
| 2024 | 0.0778 | 0.0938 | 0.0964 | 0.5824 | 1.1309 | 0.0907 | 0.0853 | 0.0863 | 0.0880 |
| 2025 | 0.2061 | 0.1101 | 0.1591 | 0.5231 | 1.4316 | 0.1430 | 0.1319 | 0.1353 | 0.1351 |
| 2026 | 0.1285 | 0.1313 | 0.1525 | 0.5801 | 1.1709 | 0.1454 | 0.1313 | 0.1485 | 0.1496 |

## 9. Contract coverage by season (MH2.1 Lock 2 — per COLUMN, not a pooled mean)

MH2.1 (c): report per-column ABSENCE, not a pooled coverage mean — "missing" and "NEVER EXISTED" are different findings, and a structurally absent column means the early folds evaluate a DIFFERENT contract rather than a sparser one. This BOUNDS what a wide window can certify; it is not a reason to trim folds (the handicap is identical across arms).

| season | rows | mean coverage | structurally absent columns |
|---:|---:|---:|---|
| 2016 | 2,004 | 0.839 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2017 | 1,936 | 0.840 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2018 | 2,133 | 0.841 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2019 | 1,999 | 0.840 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2020 | 547 | 0.913 | `away_lineup_bat_speed_vs_starter_velo` |
| 2021 | 1,951 | 0.915 | `away_lineup_bat_speed_vs_starter_velo` |
| 2022 | 2,008 | 0.919 | `away_lineup_bat_speed_vs_starter_velo` |
| 2023 | 2,011 | 0.955 | — |
| 2024 | 2,001 | 0.995 | — |
| 2025 | 2,025 | 0.995 | — |
| 2026 | 1,440 | 0.989 | — |

---

## Reproduction

```bash
# LAPTOP. Snowflake-free; requires betting_ml/data/cache/edge_e1_training_from2016.parquet
uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py
uv run python betting_ml/scripts/mh2_5_sigma_recalibration.py --exclude-seasons 2020
```
