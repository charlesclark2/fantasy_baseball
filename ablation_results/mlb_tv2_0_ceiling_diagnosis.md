# MLB-TV2-0 — the totals-ceiling diagnosis: **SHAPE-BOUND**

> ## ⭐ ROUTING: TV2-2 (mixture-density head) funded first

`best_alpha = 0` · `bet_paused = true` · **market-blind** · **nothing serves** · deploy-held

> **What this study is.** An ORACLE diagnosis of the SERVED totals predictive. It bounds what each of the epic's two candidate levers could AT MOST deliver and triggers a decision rule registered before any statistic was computed on a realized outcome. It builds neither fix. It says nothing about win rate, edge, ROI or CLV — at `best_alpha = 0` no bet rode on this model. Pre-registration: [`mlb_tv2_0_prereg.md`](mlb_tv2_0_prereg.md); the node-2 amendment is its §12.

## Population

| | |
|---|---|
| champion | E13.11 (`v6` / `pre_lineup_v6`), fit 2026-06-23 |
| era | 2026-06-23 → 2026-08-23 — the whole era is OUT OF SAMPLE by construction |
| PRIMARY tier | `post_lineup` — n = **758** (date blocks [147, 157, 147, 160, 147]) |
| SECONDARY tier | `morning` — n = **765** |
| folds | 5 contiguous DATE blocks, cross-fit |
| calibrated null | 2000 replicates, seed 42 |
| CRPS grid vs the Normal closed form | \|Δ\| = 1.90e-05 (tol 0.001) |

---

## 1. ⭐ The positive controls — run BEFORE any realized outcome was read

A diagnosis whose legs cannot separate PLANTED causes cannot separate real ones. **The first design FAILED these** — and the failure is the most useful thing this story measured; see §6 and prereg §12.

Each control is a DETECTION RATE over 20 replicates, not a single draw (prereg §12, amendment 2).

| control | planted | expected route | route rate (bar) | wrong-lever rate (bar) | median `closed_shape` | median `closed_feature` | ✓ |
|---|---|---|---:|---:|---:|---:|---|
| `PC_clean` | *nothing — the model is correct* | `NO_MEASURABLE_DEFECT` | **0.90** (0.90) | 0.00 (0.10) | 0.000 | 0.000 | ✅ |
| `PC_dispersion` | {'sigma_cv': 0.35} | `FEATURE-BOUND` | **0.90** (0.80) | 0.00 (0.10) | 0.000 | 1.006 | ✅ |
| `PC_shape` | {'skew_alpha': 4.0} | `SHAPE-BOUND` | **0.90** (0.80) | 0.00 (0.10) | 1.015 | 0.000 | ✅ |
| `PC_both` | {'sigma_cv': 0.35, 'skew_alpha': 4.0} | `BOTH` | **0.60** (0.80) | 0.00 (0.10) | 1.006 | 0.612 | ⛔ |

Outcome distribution per control: `PC_clean` {'NO_MEASURABLE_DEFECT': 18, 'IRREDUCIBLE': 2} · `PC_dispersion` {'NO_MEASURABLE_DEFECT': 1, 'IRREDUCIBLE': 1, 'FEATURE-BOUND': 18} · `PC_shape` {'NO_MEASURABLE_DEFECT': 1, 'IRREDUCIBLE': 1, 'SHAPE-BOUND': 18} · `PC_both` {'NO_MEASURABLE_DEFECT': 1, 'SHAPE-BOUND': 7, 'BOTH': 12}

**All controls passed: ⛔ NO**

### MDE — the smallest PLANTED deficit the rule routes correctly

A null is *"no lever larger than this"*, never a shrug (NF1.8).

| planted σ-CV | routes `FEATURE-BOUND` | | planted skew α | routes `SHAPE-BOUND` |
|---:|---:|---|---:|---:|
| 0.05 | 0.00 | | 0.5 | 0.00 |
| 0.10 | 0.12 | | 1.0 | 0.00 |
| 0.20 | 0.00 | | 2.0 | 0.38 |
| 0.35 | 0.75 | | 4.0 | 0.88 |
| 0.50 | 0.62 | | 6.0 | 1.00 |

---

## 2. The battery on the real served folds (PRIMARY tier)

⛔ = an ORACLE or a CONTROL. **Nothing here competes to ship**, and an oracle ceiling is what a lever could AT MOST deliver — never what it will. Every arm holds `μ` EXACTLY at the served value.

| arm | `crps` | `pit_ks` | `pit_mdd` | `p_over_stated` | `p_over_realized` | `p_over_gap` | `cov80` | `cov50` | `var_z_pooled` | `z_skew` | `z_excess_kurtosis` | `scale_mean` | `scale_cv` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `incumbent` | 2.5301 | 0.0891 | 0.0491 | 0.5000 | 0.4274 | 0.0726 | 0.8100 | 0.4736 | 1.0645 | 0.7494 | 0.5790 | 4.3764 | 0.0476 |
| `A1_sigma_level` | 2.5300 | 0.0869 | 0.0412 | 0.5000 | 0.4274 | 0.0726 | 0.8179 | 0.4789 | 1.0023 | 0.7522 | 0.5947 | 4.5135 | 0.0484 |
| `A2_sigma_mu_binned` | 2.5338 | 0.0845 | 0.0412 | 0.5000 | 0.4274 | 0.0726 | 0.8153 | 0.4802 | 1.0439 | 0.6915 | 0.4393 | 4.4633 | 0.1256 |
| `A3_sigma_scalemix` ⛔ | 2.5300 | 0.0869 | 0.0412 | 0.5000 | 0.4274 | 0.0726 | 0.8179 | 0.4789 | 1.0023 | 0.7522 | 0.5947 | 4.5135 | 0.0484 |
| `A_ctrl_permuted` ⛔ | 2.5300 | 0.0869 | 0.0412 | 0.5000 | 0.4274 | 0.0726 | 0.8179 | 0.4789 | 1.0023 | 0.7522 | 0.5947 | 4.5135 | 0.0484 |
| `B1_shape_skewnormal` | 2.5313 | 0.0853 | 0.0438 | 0.4969 | 0.4274 | 0.0695 | 0.8193 | 0.4763 | 1.0645 | 0.7494 | 0.5790 | 4.3764 | 0.0476 |
| `B2_shape_empirical` ⛔ | 2.5114 | 0.0149 | 0.0161 | 0.4272 | 0.4274 | -0.0002 | 0.8061 | 0.5026 | 1.0645 | 0.7494 | 0.5790 | 4.3764 | 0.0476 |
| `C1_combined` ⛔ | 2.5120 | 0.0145 | 0.0161 | 0.4272 | 0.4274 | -0.0002 | 0.8021 | 0.5026 | 1.0023 | 0.7522 | 0.5947 | 4.5135 | 0.0484 |

Scale-mixture components chosen by BIC, out of block: **[1, 1, 1, 1, 1]**  ⟵ ⭐ **`K = 1` on every block: the oracle that is allowed to see the answer finds NO per-game σ signal at all.**

Un-gated BIC (before the symmetry gate): **[1, 1, 1, 1, 1]** — the gate closed on 0 of 5 blocks.

Skew-normal `α` by block (`B1`, reported): [0.025, 0.012, -0.002, -0.004, -0.003] — **5 of 5 blocks COLLAPSED onto the Normal foil** (|α| < 0.05). See §3.5.

### The yardstick — one primary PER LEVER (prereg §12)

| statistic | role | incumbent | calibrated-null median (the FLOOR) | null 95% band | gap | outside the band? | MC p |
|---|---|---:|---:|---:|---:|---|---:|
| `crps` | **DISPERSION lever's primary** — a PER-GAME proper score | 2.5301 | 2.4735 | [2.3481, 2.5935] | 0.0566 | ⛔ no | 0.377 |
| `p_over_gap_abs` | **ARCHITECTURE lever's primary** — the ASYMMETRY the product prints | 0.0726 | 0.0119 | [0.0000, 0.0409] | 0.0607 | ✅ yes | 0.001 |
| `pit_ks` | safeguard — overall distributional fidelity | 0.0891 | 0.0300 | [0.0169, 0.0524] | 0.0591 | ✅ yes | 0.001 |

⭐ **The instrument checks itself here.** `pit_ks`'s calibrated-null floor is **0.0300** and the distribution-free CONSTRUCTION floor at this `n` — the KS statistic of `n` iid uniforms, which involves no model at all — is **0.0305**. They agree because `round(Normal)` read with a continuity-corrected randomized PIT is EXACTLY uniform. A statistic INSIDE its null band is **inactive**: there is no measurable failure for a lever to close, and a closure share computed against a `gap` that is itself noise is the NF1.7 (a) vacuous anchor.

No oracle landed below an active statistic's floor lower tail.

---

## 3. ⭐ THE LEVERS, BOUNDED

| channel | construction | statistic | paired lift (95% CI) | material | in play? | share of the JOINT CEILING |
|---|---|---|---:|---|---|---:|
| **calibrator** — a global scale (a RECALIBRATOR can do this) | `imp(A1) − imp(incumbent)` | `crps` | 0.0001 [-0.0019, 0.0025] | no | ⛔ no | 0.007 |
|  |  | `p_over_gap_abs` | 0.0000 [0.0000, 0.0000] | no | ⛔ no | 0.000 |
|  |  | `pit_ks` *(reported; not a lever statistic)* | 0.0022 [0.0002, 0.0043] | yes | ⛔ no | 0.029 |
| ⭐ **calibrator — LEVER SHARE** | max over admissible, in-play statistics | | | | ⛔ not in play | **0.000** |
| **ARCHITECTURE lever** — `TV2-2`'s CEILING | `imp(B2) − imp(A1)` | `crps` | 0.0185 [-0.0003, 0.0368] | no | ⛔ no | 1.025 |
|  |  | `p_over_gap_abs` | 0.0724 [0.0010, 0.0731] | yes | ✅ **yes** | 1.000 |
|  |  | `pit_ks` *(reported; not a lever statistic)* | 0.0720 [-0.0014, 0.0777] | no | ⛔ no | 0.965 |
| ⭐ **shape — LEVER SHARE** | max over admissible, in-play statistics | | | | ✅ **IN PLAY** | **1.003** |
| **FEATURE lever** — `TV2-1`'s CEILING | `imp(C1) − imp(B2)` | `crps` | -0.0006 [-0.0014, 0.0003] | no | ⛔ no | -0.032 |
|  |  | `p_over_gap_abs` ⛔ *inadmissible — the arm cannot move this statistic* | 0.0000 [0.0000, 0.0000] | no | ⛔ no | 0.000 |
|  |  | `pit_ks` *(reported; not a lever statistic)* | 0.0004 [-0.0025, 0.0019] | no | ⛔ no | 0.005 |
| ⭐ **feature — LEVER SHARE** | max over admissible, in-play statistics | | | | ⛔ not in play | **0.000** |
| *(the feature lever, read directly)* | `imp(A3) − imp(A1)` | `crps` | 0.0000 [0.0000, 0.0000] | no | ⛔ no | 0.000 |
|  |  | `p_over_gap_abs` ⛔ *inadmissible — the arm cannot move this statistic* | 0.0000 [0.0000, 0.0000] | no | ⛔ no | 0.000 |
|  |  | `pit_ks` *(reported; not a lever statistic)* | 0.0000 [0.0000, 0.0000] | no | ⛔ no | 0.000 |
| ⭐ **feature_direct — LEVER SHARE** | max over admissible, in-play statistics | | | | ⛔ not in play | **0.000** |

### ⭐ The ASYMMETRY channel — the error on the number the product prints

Read as a MOVEMENT of the stated probability, in which the realized over-rate cancels EXACTLY, gated on the incumbent's gap being materially non-zero (prereg §12.2.3).

| | |
|---|---:|
| incumbent signed `p_over_gap` at its own mean | **0.0726** |
| its paired 95% CI | [0.0369, 0.1095] |
| gap materially non-zero? (the channel's precondition) | ✅ yes |
| `B2`'s movement of the stated probability | 0.0728 [0.0724, 0.0732] |
| movement is toward zero? | ✅ yes |
| channel in play | ✅ **yes** |
| share of the printed error it closes | **1.003** |

### The joint ceiling and the row-blind control

| | statistic | paired lift (95% CI) | material |
|---|---|---:|---|
| **JOINT ceiling** `imp(C1) − imp(incumbent)` | `crps` | 0.0181 [0.0002, 0.0365] | yes |
| **JOINT ceiling** `imp(C1) − imp(incumbent)` | `p_over_gap_abs` | 0.0724 [0.0010, 0.0731] | yes |
| ⛔ **row-blind matched control** `imp(A_ctrl) − imp(A1)` — must be INERT | `crps` | 0.0000 [0.0000, 0.0000] | no ✅ |
| ⛔ **row-blind matched control** `imp(A_ctrl) − imp(A1)` — must be INERT | `p_over_gap_abs` | 0.0000 [0.0000, 0.0000] | no ✅ |

Bars, registered forward: majority **0.5**, in-play **0.2**. A lever counts only if its PAIRED 95% CI excludes 0 — every arm scores the same outcomes, so the decision-relevant noise is the noise of the DIFFERENCE. Demonstrable ≠ material (NF-W6).

⭐ **The decomposition is HIERARCHICAL and deliberately conservative toward the expensive lever.** The architecture lever is scored beyond a plain recalibrator; the feature lever — the one that needs a whole new data product — must prove it adds **beyond the best marginal shape**. Shared credit goes to the cheaper mechanism.

**Fidelity safeguard on `pit_ks`: `WITHIN_NOISE`** — the winning lever's overall-fidelity lift is 0.0720. Only a materially NEGATIVE lift demotes; a within-noise one is recorded, never scored as a pass (NF1.7 (a)).

Per-arm closure, by statistic:

| arm | `crps` | `p_over_gap_abs` | `pit_ks` |
|---|---:|---:|---:|
| `A1_sigma_level` | 0.002 | 0.000 | 0.037 |
| `A2_sigma_mu_binned` | -0.066 | 0.000 | 0.077 |
| `A3_sigma_scalemix` | 0.002 | 0.000 | 0.037 |
| `A_ctrl_permuted` | 0.002 | 0.000 | 0.037 |
| `B1_shape_skewnormal` | -0.021 | 0.051 | 0.064 |
| `B2_shape_empirical` | 0.330 | 1.192 | 1.257 |
| `C1_combined` | 0.319 | 1.192 | 1.263 |

---

## 3.5 ⭐ Reading the verdict — and three things it does NOT say

**The architecture lever closes 100.3% of the error the product prints.** The served predictive states `P(over) = 0.5000` at its own mean against a realized 0.4274; the marginal-shape oracle moves the stated probability by +0.0728 and lands the gap at -0.0002. It is **not** a coverage-for-accuracy trade: the same arm also improves the proper score (2.5301 → 2.5114 CRPS) and overall fidelity (0.0891 → 0.0149 `pit_ks`).

**The feature lever is INACTIVE, not merely small.** The scale-mixture oracle — which is ALLOWED TO SEE THE ANSWER — returns `K = 1` on every one of the 5 blocks, so `A3` is BYTE-IDENTICAL to a plain global rescale and the per-game σ channel has nothing in it to recover. On top of the best marginal shape the lever's CRPS lift is **-0.0006 — NEGATIVE**. `TV2-1`'s premise (*that nothing carries dispersion*) is confirmed in the strongest available form: on this population there is no per-game dispersion structure for a feature to carry.

⭐ **The `PC_both` caveat does NOT bind on this data, and that is checkable.** §1 records that when both deficits are present the battery routes `SHAPE-BOUND` about 35% of the time instead of `BOTH` — so a `SHAPE-BOUND` verdict does not IN GENERAL exclude a co-present dispersion component. But the MECHANISM of that failure is the symmetry gate closing on a mixed sample, and here **the gate never engaged**: the UN-GATED BIC also returned `K = 1` on every block ([1, 1, 1, 1, 1]; the gate closed on 0 of 5). The verdict is not resting on the gate.

### The three things it does NOT say

1. ⚠️ **It does not say the model's DISCRIMINATION is fixable.** §4's location probe is the number to carry: `Var(μ)/Var(y) = 0.0142` — the location channel explains 1.4% of outcome variance, and `STDDEV(pred_total_runs) = 0.544` against the V2 gate's **≥ 2.0**. **Neither lever touches it** — every arm holds `μ` fixed. `TV2-2` will fix the probability the product PRINTS; it will not make the model better at telling a high-scoring game from a low-scoring one. Whether **2.0** is even attainable for a totals model is not something this market-blind study could measure.
2. ⚠️ **It does not say a naive skew fit will work.** `B1_shape_skewnormal` — a 3-parameter skew-normal MLE — collapsed onto its Normal foil on **5 of 5 blocks** (α = [0.025, 0.012, -0.002, -0.004, -0.003]) even though the realized `z` skew is **0.749**. This reproduces MH2.8's boundary-degenerate finding: the skew-normal likelihood is FLAT at α = 0, so a fitter started near symmetry reports *no skew, converged successfully* on obviously skewed data. ⇒ **`TV2-2`'s head must not be fitted by a naive MLE from a symmetric start**, and its bake-off needs a tie-with-foil guard: a nested form's near-zero margin is a TIE, not a shape finding.
3. ⚠️ **It does not license the CURRENT contract's own heteroscedasticity.** `A2_sigma_mu_binned` — per-game σ keyed on the served `μ`, i.e. what the contract already implies — closes -0.066 of the CRPS gap: it makes the proper score **worse**. There is no free dispersion signal sitting in the existing features either.

---

## 4. ⚠️ FLAGGED BINDING CLAUSE — `std_pred`, and the LOCATION channel

The spec asks how much of the **`std_pred`**/PIT failure a σ fix closes. `std_pred` names TWO different statistics in this repo, and **the `0.773 vs ≥2.0` figure the spec cites is the MEAN-SPREAD one** (`STDDEV(pred_total_runs)`, `validate_v2_gates.py:34`) — a property of `μ`. Every arm here holds `μ` fixed, so **no leg can move it, by construction**. Registering a leg against a statistic it cannot move would ship a gate that is décor (NF-MARGIN2). It is therefore reported as a LOCATION diagnostic and is **not** in the decision rule. Flagged for the PM, **not edited**.

| reading | value | bar | |
|---|---:|---:|---|
| `std_pred_meanspread` = `STDDEV(pred_total_runs)` — the V2 gate's reading | **0.544** | ≥ 2.0 | ⛔ **FAILS** |
| `std_pred_predictive_sd` = `mean(σ)` — Story 10.2's reading | 4.376 | — | |
| realized `SD(y)` | 4.560 | — | |
| `Var(μ)/Var(y)` — the share of outcome variance the LOCATION channel explains | **0.0142** | — | |
| served `σ` CV — how much per-game DISPERSION the model expresses AT ALL | 0.0476 | — | |

Null state, **hand-recorded** per the `cv_power` card's interim rule: **`INACTIVE (structural)`** — the mechanism structurally cannot act on this statistic. ⛔ It is NOT rendered as a fold/season re-test trigger (NF-D18): no number of additional served games can make a σ leg move `SD(μ)`.

### `classify_null` on each lever whose reading is a NULL

| lever | state | re-test trigger | reason |
|---|---|---|---|
| `feature` | **`INACTIVE`** | a population on which the mechanism can act at all | the scale-mixture oracle returned K = 1 on all 5 blocks — an oracle with the answer in hand finds NO per-game scale structure, so a dispersion FEATURE has nothing to carry |
| `shape` | **`NOT_A_NULL`** | ⛔ **none** — see reason | the lever is IN PLAY — see §3. |
| `std_pred_meanspread` | **`INACTIVE`** *(hand-recorded — the `cv_power` card's interim rule)* | ⛔ **none** — see reason | ARM-INVARIANT by construction: every arm holds mu EXACTLY at the served value, so no leg can move STDDEV(pred_total_runs). `classify_null` has no input that expresses 'the statistic cannot be moved by any arm in the field', so this is hand-recorded per the cv_power card's interim rule. |

⛔ An `INACTIVE` null gets **no** fold/season re-test trigger: the remedy is a different population, never more served games (NF-D18 / E7.15).

---

## 5. SECONDARY tier replication (`morning` / `pre_lineup_v6`)

Declared in advance as a replication that is REPORTED but does **not** change the verdict — so the primary cannot be swapped for whichever tier gives the nicer answer (E2.1-r).

| | primary (`post_lineup`) | secondary (`morning`) |
|---|---:|---:|
| outcome | **`SHAPE-BOUND`** | `SHAPE-BOUND` |
| a failure outside its null band? | True | True |
| `closed_calibrator` | 0.000 | 0.000 |
| `closed_shape` (`p_over_gap_abs`) | 1.003 | 1.002 |
| `closed_feature` (`crps`) | 0.000 | 0.000 |
| mixture `K` by block | [1, 1, 1, 1, 1] | [1, 1, 1, 1, 1] |
| `std_pred_meanspread` | 0.544 | 0.530 |

Tiers agree: **✅ YES**

---

## 6. What this study cannot say

- Nothing about **edge, win rate, ROI or CLV**. `best_alpha = 0`; no bet rode on this model, and `bet_paused` stays `true`.
- An oracle ceiling is what a lever could **at most** deliver, never what it will. A large ceiling licenses **funding a story**; it is not evidence of a shipped improvement.
- The verdict is about the **served `post_lineup`** rows in a **2-month** window under **one** champion. It does not generalise to a different champion.
- MH2.8's skew-normal DSR failure is **cited as evidence, never re-scored** here.
- `p_over_gap_abs` is structurally near-blind to a per-game σ deficit and `crps` is comparatively coarse on a marginal shape defect (§1, measured). That is exactly why each lever is scored on its own statistic — and it is a caution for anyone reading a single number off this table.
