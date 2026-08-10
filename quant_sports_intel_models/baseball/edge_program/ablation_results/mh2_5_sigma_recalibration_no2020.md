# MH2.5 — make the served totals model's per-game σ generalize and widen its dynamic range

> ⚠️ **Not an edge claim.** `best_alpha = 0`, `bet_paused = true`. A pricing/calibration study; it says nothing about win rate, edge or ROI.

> 💸 **Snowflake-free and network-free** — reads only the local training-matrix parquet MH2.1's bake-off already cached, and HALTs rather than pulling if it is absent.

**VERDICT: `INCUMBENT_STANDS`**

⚪ **INCUMBENT_STANDS** — `var_glm` is the best candidate at RMS |Var(z)−1| 0.0336 against the served σ's 0.2239 (level-only foil 0.1647, flat null 0.0589), and the gate(s) ['pbo_pass', 'dsr_pass'] did not clear. The null is classified `DSR_UNREACHABLE`.

- `total_runs` / `post_lineup` · window **2016–2026** · **7 purged/embargoed folds** · 19,508 rows (13,435 out-of-fold eval rows) · 13-column served contract · **seasons excluded: [2020]**
- Field: **9 pre-registered arms** (declared, not discovered) — `incumbent`, `level_only`, `flat_sigma`, `over_disperse`, `under_disperse`, `power_widen`, `iso_widen`, `var_glm`, `var_glm_plus_sigma`
- Diagnostic anchors, ⛔ **excluded from `n_trials`, from DSR's `V` and from PBO** (MH2.1 (a) — a diagnostic anchor is never a trial): `oracle_power`, `oracle_iso`, `oracle_var_glm`, `oracle_var_glm_plus_sigma`, `oracle_bin`, `perm_sigma`

⚠️ **NOT POINT-IN-TIME — every number here is a CEILING.** `load_features` reads each game's row as it exists NOW (post-game backfilled and dense); the live serve only ever saw the sparse pre-game row. The honest live figure comes from scoring the ACTUALLY-SERVED predictions, never from this matrix. This binds the LEVELS; the arm-to-arm COMPARISON is unaffected because every arm reads the identical matrix.

## 0. The premise test — does the widener want to widen?

> MH2.5 (from mh2_1_rollback.md §3): the served per-game σ UNDER-expresses heteroscedasticity, so its dynamic range should be WIDENED.

`power_widen` is a WIDENER by construction: γ is free over [0.0, 3.0], **γ = 1 reproduces the served σ exactly, γ > 1 widens its dynamic range, γ < 1 narrows it.** So which side of 1 the in-fold NLL fit lands on tests the premise directly, with no interpretation and nothing to argue about.

**Fitted γ̂ landed BELOW 1 — i.e. the widener chose to NARROW — in 7 of 7 folds** (γ̂ = 0.71, 0.77, 0.25, 0.03, 0.15, 0.36, 0.01). The **peeking** oracle, which is allowed to see the answer, chose γ < 1 in 7 of 7 and lands lower still (0.29, 0.40, 0.00, 0.21, 0.01, 0.81, 0.00).

Independently, the per-fold dispersion match (σ's own range ÷ the realized-SD range across the same bins) exceeds 1 — meaning σ's dynamic range is **WIDER** than the dispersion it can resolve — in **7 of 7 folds** (1.10, 1.17, 1.65, 1.23, 1.28, 1.02, 1.29).

**⇒ PREMISE REFUTED — the widener chose to NARROW.**

### 0b. 🪤 How much of σ's spread is fit noise?

`NGBRegressor(random_state=...)` seeds NGBoost's own minibatching and line search — **it does NOT seed the base learner.** The default base is a `DecisionTreeRegressor` built with `random_state=None`, so it breaks split ties off numpy's GLOBAL RNG. Two fits of the identical class on the identical rows with the identical `seed` therefore disagree.

Measured on the last fold (1,440 games), seeds 42 vs 43, everything else held fixed:

- per-game **run-to-run SD of σ: 0.0091** (max single-game disagreement **0.302**)
- **cross-game SD of σ: 0.2461** — i.e. how much σ actually varies between games
- ⇒ **noise-to-signal 0.037**

⭐ **HYPOTHESIS REFUTED BY ITS OWN MEASUREMENT, and recorded as such.** The obvious explanation for §1 — "σ's dynamic range is mostly refit noise, so of course it cannot order games by volatility" — is WRONG here: refit noise is only **3.7%** of σ's cross-game spread. The served σ genuinely varies between games; it simply varies in a way that does not track realized dispersion out of fold. That is a harder and more interesting finding than a noise story, and it is why this was measured rather than argued.

⚠️ **A SMOKE-SCALE PROBE WOULD HAVE SUPPORTED THE WRONG CONCLUSION.** The same check at 120 estimators on 4,000 rows (the scale a `--smoke` harness check runs at) put the max single-game disagreement at **0.39** — ~9% of σ — which reads as "σ is mostly noise". At the real 400 estimators on 14,594 rows it is **0.302**. Refit noise is capacity- and n-dependent, so a reproducibility figure must be quoted at the FITTING SCALE THAT SHIPS.

⚠️ **Not local to MH2.5** — every NGBoost bake-off in this repo inherits it, and any recorded per-game σ figure produced without seeding the global RNG is not re-derivable. This harness seeds `np.random.seed(seed)` immediately before each fit; the run above is reproducible, earlier MH2.x/E7.9/E1.9 σ figures are not.

## 1. The method lock — the stratifier is validated BEFORE any Var(z) is read

MH2.1 was rolled back because a conditional-calibration result was read off a partition nobody had checked. A σ-CV floor, a matched foil and a permutation null were all present and none of them asks the load-bearing question: **do these bins actually separate realized dispersion?** So that table comes first here, and a partition that fails its pre-registered bar (ρ ≥ 0.3 and endpoints ≥ 2.0 SE apart) is DISQUALIFIED — no number is read off it.

### `incumbent_sigma` — ✅ VALID · **PRE-REGISTERED PRIMARY**

realized dispersion rises across the bins

- Spearman ρ(bin, realized SD) = **0.842** · endpoints **3.08 SE** apart
- ⭐ **Dynamic range:** the stratifier moves **×1.516** across its bins while realized SD moves **×1.088** — a match ratio of **1.393** (1.000 = the stratifier expresses exactly as much dispersion as there is; **< 1 = UNDER-expressed**, **> 1 = OVER-expressed**, i.e. a σ whose dynamic range is wider than the dispersion it can actually resolve).

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,344 | 3.555 | 4.344 | 0.084 | 3.416 |
| 1 | 1,343 | 3.965 | 4.384 | 0.085 | 3.470 |
| 2 | 1,344 | 4.098 | 4.569 | 0.088 | 3.606 |
| 3 | 1,343 | 4.185 | 4.348 | 0.084 | 3.465 |
| 4 | 1,344 | 4.260 | 4.537 | 0.088 | 3.577 |
| 5 | 1,343 | 4.330 | 4.406 | 0.085 | 3.493 |
| 6 | 1,343 | 4.400 | 4.538 | 0.088 | 3.565 |
| 7 | 1,344 | 4.498 | 4.604 | 0.089 | 3.680 |
| 8 | 1,343 | 4.676 | 4.706 | 0.091 | 3.721 |
| 9 | 1,344 | 5.389 | 4.726 | 0.091 | 3.759 |

### `incumbent_mean` — ✅ VALID · pre-registered secondary

realized dispersion rises across the bins

- Spearman ρ(bin, realized SD) = **0.927** · endpoints **5.94 SE** apart
- ⭐ **Dynamic range:** the stratifier moves **×1.455** across its bins while realized SD moves **×1.177** — a match ratio of **1.236** (1.000 = the stratifier expresses exactly as much dispersion as there is; **< 1 = UNDER-expressed**, **> 1 = OVER-expressed**, i.e. a σ whose dynamic range is wider than the dispersion it can actually resolve).

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,344 | 7.712 | 4.215 | 0.081 | 3.353 |
| 1 | 1,343 | 8.284 | 4.433 | 0.086 | 3.501 |
| 2 | 1,344 | 8.504 | 4.286 | 0.083 | 3.358 |
| 3 | 1,343 | 8.686 | 4.440 | 0.086 | 3.508 |
| 4 | 1,344 | 8.854 | 4.383 | 0.085 | 3.453 |
| 5 | 1,343 | 9.031 | 4.498 | 0.087 | 3.586 |
| 6 | 1,343 | 9.224 | 4.507 | 0.087 | 3.583 |
| 7 | 1,344 | 9.454 | 4.656 | 0.090 | 3.692 |
| 8 | 1,343 | 9.857 | 4.618 | 0.089 | 3.667 |
| 9 | 1,344 | 11.220 | 4.962 | 0.096 | 4.051 |

### `incumbent_sigma_within_fold` — ✅ VALID · ⚠️ **POST-HOC — diagnostic only, cannot ship**

realized dispersion rises across the bins

- Spearman ρ(bin, realized SD) = **0.891** · endpoints **3.08 SE** apart
- ⭐ **Dynamic range:** realized SD moves **×1.088** across these bins. (This stratifier is RANK-valued, so it has no meaningful range ratio of its own and no dispersion-match figure is quoted.)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 1,344 | 0.050 | 4.340 | 0.084 | 3.404 |
| 1 | 1,343 | 0.150 | 4.470 | 0.086 | 3.538 |
| 2 | 1,344 | 0.250 | 4.445 | 0.086 | 3.547 |
| 3 | 1,343 | 0.350 | 4.362 | 0.084 | 3.459 |
| 4 | 1,344 | 0.450 | 4.426 | 0.085 | 3.517 |
| 5 | 1,343 | 0.550 | 4.510 | 0.087 | 3.528 |
| 6 | 1,343 | 0.650 | 4.537 | 0.088 | 3.602 |
| 7 | 1,344 | 0.750 | 4.665 | 0.090 | 3.655 |
| 8 | 1,343 | 0.850 | 4.713 | 0.091 | 3.774 |
| 9 | 1,344 | 0.950 | 4.721 | 0.091 | 3.727 |

### The same validation, PER FOLD (quintiles) — pooled failure vs per-fold failure

A pooled partition can fail because the SIGNAL is absent or because the POOLING mixes eras. Only the per-fold tables tell those apart, and the pre-registration did not ask for them — they are reported here because the pooled primary failed.

| eval year | n | ρ | endpoints (SE) | σ range | realized-SD range | dispersion match |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 1,999 | +0.900 | +2.94 | ×1.273 | ×1.159 | 1.099 |
| 2021 | 1,951 | +0.700 | +2.15 | ×1.310 | ×1.115 | 1.175 |
| 2022 | 2,008 | -0.100 | -1.50 | ×1.533 | ×0.928 | 1.652 |
| 2023 | 2,011 | +0.900 | +2.25 | ×1.374 | ×1.119 | 1.228 |
| 2024 | 2,001 | -0.100 | -0.64 | ×1.244 | ×0.969 | 1.285 |
| 2025 | 2,025 | +0.900 | +3.20 | ×1.197 | ×1.174 | 1.020 |
| 2026 | 1,440 | +0.400 | +0.13 | ×1.304 | ×1.008 | 1.294 |

## 2. Pooled out-of-fold scores on the scoring partition (`incumbent_sigma`)

**RMS |Var(z) − 1| is the selection metric** and it is anchored on the ANALYTIC truth `Var(z) = 1`, never on the incumbent — an incumbent-relative metric inverts whenever the incumbent is the defective one and can only ever say *different*, never *better* (MH2.1 (b)). CRPS and PIT-KS are reported as sanity and are structurally BLIND here: CRPS is mean-dominated and every arm shares the identical mean, and PIT-KS is marginal, so a model that over-covers the calm games exactly as much as it under-covers the volatile ones passes it while being badly miscalibrated conditionally.

⚠️ The metric's own **noise floor at these bin sizes is 0.0386** — the RMS a PERFECTLY calibrated model posts here. A difference smaller than that is not a measurement.

| arm | RMS &#124;Var(z)−1&#124; | pooled Var(z) | Winkler | cov@80% | CRPS | PIT-KS | mean σ | σ CV | σ p90/p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **`var_glm`** | 0.0336 | 0.9930 | 15.769 | 0.8164 | 2.5300 | 0.0529 | 4.559 | 0.0844 | 1.216 |
| `power_widen` | 0.0395 | 1.0033 | 15.712 | 0.8125 | 2.5282 | 0.0525 | 4.521 | 0.0519 | 1.107 |
| `var_glm_plus_sigma` | 0.0513 | 1.0035 | 15.804 | 0.8171 | 2.5315 | 0.0530 | 4.559 | 0.0974 | 1.239 |
| `flat_sigma` | 0.0589 | 1.0014 | 15.710 | 0.8130 | 2.5281 | 0.0528 | 4.521 | 0.0268 | 1.080 |
| `iso_widen` | 0.1013 | 1.0264 | 15.745 | 0.8087 | 2.5300 | 0.0523 | 4.502 | 0.0895 | 1.150 |
| `level_only` | 0.1647 | 0.9900 | 15.843 | 0.8205 | 2.5337 | 0.0529 | 4.614 | 0.1144 | 1.264 |
| `incumbent` | 0.2239 | 1.1221 | 15.815 | 0.7890 | 2.5331 | 0.0562 | 4.336 | 0.1149 | 1.252 |
| `over_disperse` | 0.5652 | 0.4400 | 18.958 | 0.9523 | 2.6841 | 0.1256 | 6.921 | 0.1144 | 1.264 |
| `under_disperse` | 1.2800 | 2.2275 | 17.181 | 0.6173 | 2.6014 | 0.1135 | 3.076 | 0.1144 | 1.264 |
| *— diagnostics below: NOT trials —* | | | | | | | | | |
| `oracle_power` | 0.0385 | 0.9927 | 15.692 | 0.8131 | 2.5273 | 0.0528 | 4.535 | 0.0463 | 1.134 |
| `oracle_iso` | 0.0534 | 0.9960 | 15.668 | 0.8127 | 2.5262 | 0.0527 | 4.528 | 0.0709 | 1.154 |
| `oracle_var_glm` | 0.0315 | 0.9929 | 15.671 | 0.8168 | 2.5248 | 0.0525 | 4.540 | 0.0971 | 1.266 |
| `oracle_var_glm_plus_sigma` | 0.0296 | 0.9932 | 15.667 | 0.8172 | 2.5246 | 0.0525 | 4.540 | 0.0991 | 1.272 |
| `oracle_bin` | 0.0000 | 1.0013 | 15.687 | 0.8135 | 2.5272 | 0.0527 | 4.516 | 0.0296 | 1.086 |
| `perm_sigma` | 0.0540 | 0.9981 | 15.901 | 0.8193 | 2.5361 | 0.0535 | 4.614 | 0.1144 | 1.264 |

### Robustness — the same metric on the independent second partition

A result that holds on the incumbent's predicted MEAN as well as on its σ cannot be a property of any one σ model's ordering.

| arm | RMS &#124;Var(z)−1&#124; on `incumbent_mean` |
|---|---:|
| `level_only` | 0.0389 |
| `var_glm` | 0.0398 |
| `var_glm_plus_sigma` | 0.0416 |
| `iso_widen` | 0.0505 |
| `power_widen` | 0.0585 |
| `flat_sigma` | 0.0777 |
| `incumbent` | 0.1209 |
| `over_disperse` | 0.5632 |
| `under_disperse` | 1.2148 |

| arm | RMS &#124;Var(z)−1&#124; on `incumbent_sigma_within_fold` |
|---|---:|
| `power_widen` | 0.0339 |
| `var_glm` | 0.0359 |
| `var_glm_plus_sigma` | 0.0512 |
| `flat_sigma` | 0.0590 |
| `iso_widen` | 0.0984 |
| `level_only` | 0.1564 |
| `incumbent` | 0.2138 |
| `over_disperse` | 0.5643 |
| `under_disperse` | 1.2768 |

## 3. The anchors — read these BEFORE the leader's number

A metric a degenerate WINS cannot select anything, and an arm that beats a peeking version of its own form means the metric is inverted, not that the arm is good. Both are checked here and both are two-sided.

- ⭐ **THE INVERSION GATE — `oracle_bin`, the CONSTRUCTION floor.** Each bin is given its own REALIZED SD as σ on the very partition the headline is scored over, so it is conditionally calibrated by construction rather than by fitting. It scores **0.0000** against the analytic noise floor **0.0386** — i.e. this is how small a difference is even MEASURABLE here. Respected by every arm = **True**.

- **PER-FORM peeking arms — a HEADROOM diagnostic, ⛔ NOT a gate.** One per candidate, because the forms NEST and a single ceiling would veto a legitimately-better nested form (NF-D16 g‴). ⚠️ **Beating one is NOT an inversion**: a peeking oracle is a floor only at matched FAMILY *and* matched SAMPLE (NF1.7 (b)), and matched sample is often unobtainable here — an oracle can only be fitted on eval rows, of which there are fewer than the calibration split in most folds. NF-D14: *a winner can legitimately beat a peeking oracle at unmatched n.* Positive headroom = the design left achievable widening on the table.

| arm | its score | same form, PEEKING | headroom |
|---|---:|---:|---:|
| `power_widen` | 0.0395 | 0.0385 | +0.0010 |
| `iso_widen` | 0.1013 | 0.0534 | +0.0478 |
| `var_glm` | 0.0336 | 0.0315 | +0.0021 |
| `var_glm_plus_sigma` | 0.0513 | 0.0296 | +0.0217 |

- **Degenerates must LOSE** (NF1.8 (3), two-sided): `over_disperse` ✅ · `under_disperse` ✅. A *constraint* a degenerate satisfies is fine; a *criterion* a degenerate wins is fatal.
- ⚠️ **The flat-σ NULL TO BEAT** (MH2.1's rolled-back winner shape — ⛔ do NOT carry its claim that it beat the incumbent): the leader beats it.
- **Permutation anchor** — permuting σ destroys the σ↔dispersion link while preserving σ's marginal, so `perm_sigma` was registered in advance to degrade to roughly `flat_sigma`. Measured: `perm_sigma` 0.0540 vs `flat_sigma` 0.0589 ⇒ degraded as registered = **True**.

## 3b. ⚠️ The two pre-registered readings do not want the same σ

`RMS |Var(z) − 1|` is a **second-moment** target. Central-80% coverage and the Winkler score are **bulk/quantile** targets. On a Normal they coincide; on a fat-tailed residual they do not — the variance is inflated by the tails while the 80% interval is set by the middle — so the σ that makes `Var(z) = 1` is WIDER than the σ that makes coverage 0.80.

- Excess kurtosis of the served model's `z`: **+0.786** (a Normal is 0)
- σ multiplier that sets **Var(z) = 1**: **×1.0593**
- σ multiplier that sets **coverage = 0.80**: **×1.0251**

⭐ **This matters for what a fix would mean operationally.** Served `P(over)` at a line is a CDF read NEAR THE MIDDLE of the predictive, i.e. it lives in the quantile regime, not the second-moment regime. A rescale chosen to satisfy the primary metric is therefore not automatically an improvement to the number the product actually serves, and this study does not claim it is. Reported because the primary and secondary readings DISAGREED in this run — the E2.1-r discipline applied to the gap between two metrics rather than to one of them.

## 4. Does σ GENERALIZE? — in-fold vs out-of-fold

The other half of the target. An arm that widens its σ but only fits the fold it was calibrated on reproduces the defect instead of fixing it; the gap below is the diagnostic. In-fold = the held-out calibration split each recalibrator was fitted on; out-of-fold = the purged eval rows.

| arm | in-fold RMS | out-of-fold RMS | gap |
|---|---:|---:|---:|
| `power_widen` | 0.1114 | 0.1287 | +0.0172 |
| `var_glm` | 0.1174 | 0.1318 | +0.0144 |
| `var_glm_plus_sigma` | 0.1132 | 0.1617 | +0.0486 |
| `iso_widen` | 0.0949 | 0.1666 | +0.0717 |
| `level_only` | 0.1889 | 0.2117 | +0.0228 |
| `incumbent` | 0.2553 | 0.2727 | +0.0174 |

## 5. Each arm on ITS OWN σ — a diagnostic, ⛔ never the criterion

"Does your σ mean what you say it means?" A flat-σ arm induces **no partition at all**, so an own-σ reading would be vacuously perfect — which is exactly why this can never be the selection metric (it is a criterion the degenerate wins outright, NF1.8).

| arm | own-σ partition valid | ρ | σ range | realized-SD range | dispersion match | RMS on own σ |
|---|:--:|---:|---:|---:|---:|---:|
| `incumbent` | ✅ | 0.842 | ×1.516 | ×1.088 | 1.393 | 0.2239 |
| `level_only` | ⛔ | 0.745 | ×1.512 | ×1.050 | 1.441 | 0.1770 |
| `flat_sigma` | ✅ | 0.539 | ×1.080 | ×1.074 | 1.006 | 0.0561 |
| `over_disperse` | ⛔ | 0.745 | ×1.512 | ×1.050 | 1.441 | 0.5657 |
| `under_disperse` | ⛔ | 0.745 | ×1.512 | ×1.050 | 1.441 | 1.2891 |
| `power_widen` | ✅ | 0.927 | ×1.193 | ×1.077 | 1.108 | 0.0545 |
| `iso_widen` | ⛔ | 0.782 | ×1.343 | ×1.043 | 1.288 | 0.1376 |
| `var_glm` | ✅ | 0.648 | ×1.341 | ×1.150 | 1.167 | 0.1081 |
| `var_glm_plus_sigma` | ✅ | 0.830 | ×1.407 | ×1.110 | 1.268 | 0.1388 |
| `oracle_power` | ✅ | 0.818 | ×1.167 | ×1.153 | 1.012 | 0.0335 |
| `oracle_iso` | ✅ | 0.988 | ×1.257 | ×1.220 | 1.030 | 0.0307 |
| `oracle_var_glm` | ✅ | 0.988 | ×1.400 | ×1.263 | 1.109 | 0.0564 |
| `oracle_var_glm_plus_sigma` | ✅ | 0.952 | ×1.412 | ×1.288 | 1.096 | 0.0583 |
| `oracle_bin` | ✅ | 0.988 | ×1.088 | ×1.088 | 1.000 | 0.0006 |
| `perm_sigma` | ⛔ | 0.479 | ×1.512 | ×1.003 | 1.508 | 0.2052 |

## 6. The pre-registered decision rule

Leader = **`var_glm`**. Every clause below was fixed in source before any arm scored.

| gate | requirement | measured | pass |
|---|---|---:|:--:|
| material gain vs the SERVED σ | > 0.05 RMS | +0.1903 | ✅ |
| ⭐ material gain vs the LEVEL-ONLY matched foil | > 0.05 RMS | +0.1311 | ✅ |
| beats the flat-σ NULL | — | 0.0589 vs 0.0336 | ✅ |
| beats BOTH degenerates | — | — | ✅ |
| PBO | < 0.2 | 0.2500 | ⛔ |
| DSR (fixed convention, measured V) | ≥ 0.95 | 0.0000 | ⛔ |
| BH-FDR over the 4 real candidates | q = 0.05 | — | ✅ |
| central-80% coverage FLOOR (⛔ never a target) | ≥ incumbent − 0.01 | 0.8164 vs 0.7890 | ✅ |

- Fold consistency (reported, not a gate here): the leader beats the served σ in **7/7** folds.
- DSR detail — observed per-fold Sharpe **1.509** vs bar **SR0 = 5.649** at 9 trials; measured cross-trial dispersion V = 13.7959. The incumbent is the REFERENCE and is excluded from V (its skill-vs-itself series is identically zero); `n_trials` stays the full field.

### ⭐ Deflation sensitivity — is the DSR failure EVIDENTIAL or ARITHMETIC?

⛔ **NON-BINDING AND NOT A RESCUE.** The gate above stands exactly as pre-registered. This block exists so the record can say WHY it failed, and so a successor can pre-register the convention rather than discover it (MH2.2).

Measured per-arm trial Sharpes: `[1.2145, 1.3177, -3.2342, -8.8201, 1.4522, 1.0538, 1.5092, 1.3355]`. The two entries at `[-3.2342, -8.8201]` are the pre-registered DEGENERATES — arms that exist to LOSE. Because `SR0 = √V·z(N)` scales with the cross-trial Sharpe **dispersion**, an arm that loses hugely and CONSISTENTLY inflates the bar just as effectively as one that wins hugely:

| | V | SR0 | observed SR | DSR |
|---|---:|---:|---:|---:|
| **as gated** (full declared field) | 13.796 | 5.649 | 1.509 | 1.351e-27 |
| V excluding the designed losers | 0.027 | 0.250 | 1.509 | 0.9995 |

⭐ **This is MH2.1 (a) mirrored.** There, a DIAGNOSTIC anchor leaked into the trial field and set the gate's own bar. Here, a pre-registered degenerate — which correctly IS a trial for MULTIPLICITY — sets the bar through **V**, by losing consistently. `dsr_gate`'s existing guard does not catch it (it flags |Sharpe| > 10). The two rules that collide are each right on their own: NF1.8/NF1.7 require degenerates in the field to prove the metric is two-sided, and MH2 §a requires the full declared field in `n_trials`. ⭐ Note the repo ALREADY resolves this same tension for the reference arm — `dsr_gate` keeps the incumbent in `n_trials` while excluding it from `V`, on the grounds that a designed-constant skill series is not evidence about dispersion. Extending that to lose-by-construction anchors is the same argument, not a new one.

- PBO as gated (whole declared field): **0.2500** · PBO over CONTENDERS only (degenerates dropped, NF1.8): **0.3500**
- Whole-field spread **1.2464** vs contender (top-quartile) spread **0.0059** — NF1.8: a spread computed over a field that CONTAINS its own nulls measures the nulls.
- Per-fold winner counts (the cheap flip statistic): `{'var_glm': 2, 'flat_sigma': 2, 'iso_widen': 1, 'level_only': 1, 'power_widen': 1}` — mass on a single arm is a stable pick; mass spread thinly over unrelated arms is a search that learnt nothing.

### BH-FDR, paired across folds against the served σ

| arm | mean per-fold gain | p (one-sided) | BH cutoff | passes |
|---|---:|---:|---:|:--:|
| `var_glm` | +0.14083 | 0.0036 | 0.0125 | ✅ |
| `power_widen` | +0.14397 | 0.0043 | 0.0250 | ✅ |
| `var_glm_plus_sigma` | +0.11092 | 0.0062 | 0.0375 | ✅ |
| `iso_widen` | +0.10606 | 0.0158 | 0.0500 | ✅ |

## 7. What KIND of null this is (`cv_power.classify_null`)

**`DSR_UNREACHABLE`** — `crps`: the winner's per-fold Sharpe 1.509 sits at or BELOW the 9-arm field's deflated benchmark SR0 5.649, so DSR is unreachable at ANY fold count — `n` scales a positive gap, it cannot create one. The remedy is a SMALLER, pre-registered field, not more seasons.

- Re-test trigger: **NOT rescuable by field size either — even a 2-arm field does not clear at this fold count and dispersion, so the only lever left is a lower-variance design (more rows per fold / a sharper metric)**
- ⚠️⚠️ **THIS CLASSIFICATION INHERITS THE SAME `V` ARTIFACT AND MUST NOT BE QUOTED BARE.** `classify_null` is handed the binding `var_trials_sr`, which the lose-by-construction degenerates inflate (13.796 vs 0.0271 without them). Its `DSR_UNREACHABLE` label — and in particular its "not rescuable by field size, the only lever left is a lower-variance design" remedy — is therefore a statement about the anchor arithmetic, NOT about the evidence. Read it beside §6's sensitivity table. This is the third member of the MH2.2 family: **the instrument's own remedy text is only as trustworthy as the quantity it was handed.**
- ⚠️ **THE INSTRUMENT'S OWN REMEDY IS SUSPECT HERE (MH2.2).** `classify_null` sees only a TRIAL COUNT and cannot tell a DECLARED narrow family from a DISCOVERED one, so a "re-test at a field of ≤0" trigger would prescribe shrinking BELOW this story's pre-registered 9-arm family — which re-commits the very selection bias DSR exists to deflate. ⛔ Do not act on it.
- Detail: `{"n_folds": 7, "n_arms": 9, "observed_sr": 1.5092, "sr0": 5.6486, "required_per_fold_sr_at_measured_V": 10.839, "fold_skill_sd": 0.09331, "min_detectable_crps_lift": 1.01138, "pre_registered_meaningful_crps_lift": 0.02}`

## 8. Per-fold detail

| eval year | inner-train | cal split | eval | fitted γ̂ (power) | peeking oracle γ |
|---:|---:|---:|---:|---:|---:|
| 2019 | 4,550 | 1,137 | 1,999 | 0.710 | 0.292 |
| 2021 | 6,157 | 1,539 | 1,951 | 0.772 | 0.401 |
| 2022 | 7,732 | 1,933 | 2,008 | 0.255 | 0.000 |
| 2023 | 9,322 | 2,330 | 2,011 | 0.033 | 0.205 |
| 2024 | 10,935 | 2,734 | 2,001 | 0.153 | 0.013 |
| 2025 | 12,550 | 3,138 | 2,025 | 0.361 | 0.812 |
| 2026 | 14,157 | 3,539 | 1,440 | 0.010 | 0.000 |

γ̂ is the fitted exponent of the widener `σ' = a·σ̄·(σ/σ̄)^γ`. **γ = 1 is the incumbent, γ = 0 is the flat null, γ > 1 WIDENS.** The peeking oracle's γ (fitted on the eval fold itself) is the value that would have been optimal with hindsight — the gap between the two is how much of the widening the design could actually learn in advance.

| eval year | `incumbent` | `level_only` | `flat_sigma` | `over_disperse` | `under_disperse` | `power_widen` | `iso_widen` | `var_glm` | `var_glm_plus_sigma` |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 0.3306 | 0.1785 | 0.1033 | 0.5321 | 1.4443 | 0.1114 | 0.3237 | 0.0982 | 0.2528 |
| 2021 | 0.1955 | 0.1642 | 0.1451 | 0.6009 | 1.0780 | 0.1474 | 0.1743 | 0.1460 | 0.1552 |
| 2022 | 0.3406 | 0.3266 | 0.1422 | 0.6056 | 1.2962 | 0.1674 | 0.2131 | 0.1478 | 0.1888 |
| 2023 | 0.2271 | 0.1616 | 0.1188 | 0.5665 | 1.2701 | 0.1139 | 0.0914 | 0.1261 | 0.1206 |
| 2024 | 0.2093 | 0.2034 | 0.1135 | 0.5893 | 1.1937 | 0.1186 | 0.1162 | 0.1114 | 0.1227 |
| 2025 | 0.1890 | 0.1072 | 0.1825 | 0.5217 | 1.4358 | 0.1426 | 0.1357 | 0.1532 | 0.1524 |
| 2026 | 0.4165 | 0.3403 | 0.0998 | 0.5759 | 1.4654 | 0.0995 | 0.1118 | 0.1402 | 0.1398 |

## 9. Contract coverage by season (MH2.1 Lock 2 — per COLUMN, not a pooled mean)

MH2.1 (c): report per-column ABSENCE, not a pooled coverage mean — "missing" and "NEVER EXISTED" are different findings, and a structurally absent column means the early folds evaluate a DIFFERENT contract rather than a sparser one. This BOUNDS what a wide window can certify; it is not a reason to trim folds (the handicap is identical across arms).

| season | rows | mean coverage | structurally absent columns |
|---:|---:|---:|---|
| 2016 | 2,004 | 0.839 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2017 | 1,936 | 0.840 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2018 | 2,133 | 0.841 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
| 2019 | 1,999 | 0.840 | `away_lineup_bat_speed_vs_starter_velo`, `home_starter_proj_fip` |
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
