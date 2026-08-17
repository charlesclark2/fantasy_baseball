# MH2.10 — morning-tier (`pre_lineup_v6`) served-calibration audit

**Verdict: `POWER_LIMITED`** — nothing survives the correction, but the observed σ gap (ĉ = 1.0553) is SMALLER than the smallest σ deviation this window could detect at 80% power (MDE σ × 1.08) — the instrument could not have found an effect of the size it measured, so this is NOT a clean null.

`best_alpha = 0` · deploy-held · Phase 2 fires: **NO**

> **What this study is.** A calibration audit of the MORNING rows the app ACTUALLY SERVED — the whole slate, before lineups post — against realized outcomes. It says nothing about win rate, edge or ROI; at `best_alpha = 0` no bet rode on this model. Pre-registration: [`mh2_10_preregistration.md`](mh2_10_preregistration.md), committed before any statistic was computed on this population.

## Population

| | |
|---|---|
| champion | `pre_lineup_v6` (E13.11 morning tier) |
| era | 2026-06-24 → 2026-08-15 (49 dates) |
| served rows | **655** (RECENT 409 / EARLIER 246) |
| totals rows | 655 (dropped rolled-back stamp: 0) |
| primary window | **FULL** — the question is a STANDING property |

Every served row post-dates the champion's fit (E13.11, 2026-06-23), so **the whole era is out of sample** — MH2.1's "split at the incumbent's fit date" rule holds by construction.

---

## 1. ⭐ The stratifier validation — published BEFORE any `Var(z)` is read

The exact step whose absence caused the MH2.1 rollback: *a conditional-calibration result is a property of its stratifier*. Bars are MH2.5's, imported not re-declared.

### FULL · `incumbent_sigma` (PRIMARY)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 66 | 3.838 | 5.053 | 0.440 | 4.190 |
| 1 | 65 | 4.005 | 4.692 | 0.412 | 3.602 |
| 2 | 66 | 4.134 | 3.667 | 0.319 | 2.952 |
| 3 | 65 | 4.210 | 4.021 | 0.353 | 3.390 |
| 4 | 66 | 4.283 | 3.552 | 0.309 | 3.018 |
| 5 | 65 | 4.342 | 5.209 | 0.457 | 3.841 |
| 6 | 65 | 4.393 | 4.588 | 0.402 | 3.847 |
| 7 | 66 | 4.438 | 4.773 | 0.415 | 3.614 |
| 8 | 65 | 4.492 | 4.632 | 0.406 | 3.990 |
| 9 | 66 | 4.781 | 4.426 | 0.385 | 3.730 |

ρ = -0.042 (bar 0.3) · endpoints -1.07 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### FULL · `incumbent_mean` (SECONDARY)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 66 | 8.041 | 4.388 | 0.382 | 3.492 |
| 1 | 65 | 8.478 | 4.867 | 0.427 | 3.438 |
| 2 | 66 | 8.776 | 3.996 | 0.348 | 3.519 |
| 3 | 65 | 8.873 | 3.783 | 0.332 | 2.965 |
| 4 | 66 | 8.944 | 4.300 | 0.374 | 3.432 |
| 5 | 65 | 9.038 | 4.909 | 0.431 | 3.815 |
| 6 | 65 | 9.151 | 4.091 | 0.359 | 3.743 |
| 7 | 66 | 9.277 | 4.992 | 0.434 | 4.007 |
| 8 | 65 | 9.468 | 4.555 | 0.399 | 3.783 |
| 9 | 66 | 9.935 | 4.794 | 0.417 | 3.964 |

ρ = 0.333 (bar 0.3) · endpoints 0.72 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### RECENT · `incumbent_sigma` (PRIMARY)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 68 | 3.858 | 5.224 | 0.448 | 4.287 |
| 1 | 68 | 4.107 | 4.088 | 0.351 | 3.209 |
| 2 | 69 | 4.230 | 3.985 | 0.339 | 3.480 |
| 3 | 67 | 4.331 | 3.666 | 0.317 | 3.232 |
| 4 | 68 | 4.414 | 4.599 | 0.394 | 3.597 |
| 5 | 69 | 4.565 | 4.546 | 0.387 | 3.923 |

ρ = -0.143 (bar 0.3) · endpoints -1.15 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### RECENT · `incumbent_mean` (SECONDARY)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 68 | 8.153 | 4.798 | 0.411 | 3.802 |
| 1 | 68 | 8.747 | 3.822 | 0.328 | 3.261 |
| 2 | 69 | 8.912 | 4.153 | 0.354 | 3.358 |
| 3 | 67 | 9.078 | 4.260 | 0.368 | 3.627 |
| 4 | 68 | 9.251 | 4.767 | 0.409 | 3.833 |
| 5 | 69 | 9.662 | 4.720 | 0.402 | 3.857 |

ρ = 0.086 (bar 0.3) · endpoints -0.14 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### Is the partition WRONG, or merely UNDER-POWERED? — stated in games

The served morning σ barely varies: **CV 0.0644**, extreme-decile ratio 1.247 ⇒ clearing the pre-registered 2.0 SE bar needs **≈654 served games** at `k = 10`.

⚠️ ⭐ **But under-power is not this partition's problem.** A merely under-powered partition has the RIGHT SIGN and too little of it. Read the rank correlation above: it is **negative**, i.e. in this sample the morning model's σ orders realized dispersion slightly BACKWARDS. ⇒ the morning σ carries **no usable dynamic-range information**, and the premise's strongest-looking flag — `rms_var_z_sigma`, p = 0.003 — is **INADMISSIBLE**, exactly as the pre-registration said it expected to be.

---

## 2. `total_runs` — the calibrated-null placement (the PRIMARY, Normal null)

### FULL (n = 655)

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `pit_mdd` | 0.0389 | 0.0221 | [0.0115, 0.0359] | 0.026 | ⚠️ **OUTSIDE** |
| `pit_ks` | 0.0890 | 0.0319 | [0.0185, 0.0576] | 0.001 | ⚠️ **OUTSIDE** |
| `cov80` | 0.7908 | 0.8000 | [0.7710, 0.8305] | 0.586 | inside |
| `cov50` | 0.4626 | 0.4992 | [0.4626, 0.5374] | 0.059 | inside |
| `bias` | -0.0882 | 0.0080 | [-0.3248, 0.3393] | 0.582 | inside |
| `rmse` | 4.4946 | 4.3148 | [4.0843, 4.5379] | 0.116 | inside |
| `crps` | 2.5256 | 2.4284 | [2.3001, 2.5577] | 0.150 | inside |
| `var_z_pooled` | 1.1136 | 1.0061 | [0.9026, 1.1140] | 0.052 | inside |
| `rms_var_z_sigma` | 0.3265 | 0.1693 | [0.1021, 0.2534] | 0.003 | ⚠️ **OUTSIDE** |
| `rms_var_z_mean` | 0.2091 | 0.1699 | [0.0975, 0.2541] | 0.350 | inside |

### RECENT (n = 409)

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `pit_mdd` | 0.0491 | 0.0267 | [0.0144, 0.0443] | 0.016 | ⚠️ **OUTSIDE** |
| `pit_ks` | 0.1080 | 0.0401 | [0.0227, 0.0712] | 0.002 | ⚠️ **OUTSIDE** |
| `cov80` | 0.7775 | 0.7995 | [0.7628, 0.8362] | 0.273 | inside |
| `cov50` | 0.4499 | 0.5012 | [0.4548, 0.5452] | 0.034 | ⚠️ **OUTSIDE** |
| `bias` | -0.2938 | -0.0052 | [-0.3941, 0.4081] | 0.175 | inside |
| `rmse` | 4.4356 | 4.2686 | [3.9790, 4.5334] | 0.233 | inside |
| `crps` | 2.5163 | 2.4037 | [2.2486, 2.5598] | 0.158 | inside |
| `var_z_pooled` | 1.1094 | 1.0053 | [0.8761, 1.1337] | 0.113 | inside |
| `rms_var_z_sigma` | 0.3643 | 0.1618 | [0.0783, 0.2732] | 0.001 | ⚠️ **OUTSIDE** |
| `rms_var_z_mean` | 0.2214 | 0.1612 | [0.0755, 0.2707] | 0.246 | inside |

### EARLIER (n = 246)

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `pit_mdd` | 0.0382 | 0.0350 | [0.0187, 0.0585] | 0.841 | inside |
| `pit_ks` | 0.0644 | 0.0519 | [0.0291, 0.0947] | 0.478 | inside |
| `cov80` | 0.8089 | 0.8008 | [0.7520, 0.8455] | 0.792 | inside |
| `cov50` | 0.4878 | 0.5000 | [0.4390, 0.5610] | 0.762 | inside |
| `bias` | 0.2537 | -0.0065 | [-0.5268, 0.5302] | 0.373 | inside |
| `rmse` | 4.5911 | 4.3772 | [3.9912, 4.7778] | 0.285 | inside |
| `crps` | 2.5412 | 2.4640 | [2.2513, 2.6875] | 0.494 | inside |
| `var_z_pooled` | 1.1157 | 1.0029 | [0.8366, 1.1936] | 0.220 | inside |
| `rms_var_z_sigma` | 0.2356 | 0.1654 | [0.0632, 0.3108] | 0.297 | inside |
| `rms_var_z_mean` | 0.2296 | 0.1645 | [0.0569, 0.3051] | 0.354 | inside |

⚠️ **These are UNCORRECTED α = 0.05 marks.** The verdict reads them through BH at q = 0.05 over the declared family — see §5.

### ⭐ Positive controls — the test is proven able to FIRE at this n

- **sigma_x1.25** → fires on: ['pit_mdd', 'cov80', 'bias', 'var_z_pooled', 'rms_var_z_sigma']
- **mu_plus_0.75** → fires on: ['pit_mdd', 'bias']

---

## 3. ⭐ SCALE vs SHAPE — the discriminator this study exists to run

### 3a. The σ-scale estimand, in the actionable unit

| | |
|---|---|
| `ĉ = √Var(z)` | **1.0553** |
| the morning σ is too small by | **5.53%** |
| bootstrap 95% CI on `ĉ` | [0.9883, 1.1230] |
| CI excludes 1.0 | ⛔ **no** |
| `\|Var(z) − 1\|` | 0.1136 vs the MH2.5 materiality bar 0.05 → MATERIAL |

The CI is a **row-resampling bootstrap**, which makes no distributional assumption at all — deliberately, because the whole scale-vs-shape question is about whether a distributional assumption is doing the work.

### 3b. ⭐ The shape-matched null — why a Normal null is the wrong yardstick here

Realized standardized residuals on this population: **skew 0.750**, **excess kurtosis 0.708**. The sampling variance of a *variance* statistic depends on the FOURTH moment (`Var(s²) = σ⁴·(2/(n−1) + κ/n)`), so a null drawn from a symmetric **Normal** is systematically **too narrow** for `var_z_pooled` whenever the truth is leptokurtic — i.e. **a SHAPE defect mechanically manufactures apparent SCALE flags**.

The shape-matched null redraws `y* = μ + σ·ε*` with `ε*` resampled from the observed standardized residuals **re-scaled to variance exactly 1**, so its null hypothesis is precisely *"the σ scale is correct"*, with the SHAPE carried over as a nuisance. ⛔ It is applied to the VARIANCE statistics only — using it on the PIT statistics would build the very shape defect being tested into the null.

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `var_z_pooled` | 1.1136 | 0.9994 | [0.8784, 1.1341] | 0.100 | inside |
| `rms_var_z_sigma` | 0.3265 | 0.1951 | [0.1189, 0.3088] | 0.027 | ⚠️ **OUTSIDE** |
| `rms_var_z_mean` | 0.2091 | 0.1961 | [0.1140, 0.2941] | 0.774 | inside |

**Declared sensitivity — a parametric (skew-normal) shape instead of the resampled one:**

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `var_z_pooled` | 1.1136 | 0.9997 | [0.8815, 1.1198] | 0.070 | inside |
| `rms_var_z_sigma` | 0.3265 | 0.1897 | [0.1137, 0.2992] | 0.014 | ⚠️ **OUTSIDE** |
| `rms_var_z_mean` | 0.2091 | 0.1920 | [0.1123, 0.2924] | 0.735 | inside |

**Null-band width, Normal vs shape-matched** — how much of the Normal null's verdict was an artefact of assuming the wrong shape:

| statistic | Normal null width | shape-matched width | ratio |
|---|---:|---:|---:|
| `var_z_pooled` | 0.2113 | 0.2557 | 1.21× |
| `rms_var_z_sigma` | 0.1513 | 0.1899 | 1.26× |
| `rms_var_z_mean` | 0.1566 | 0.1801 | 1.15× |

### ⭐ The shape-matched null is proven able to FIRE (it is conservative, not broken)

- **sigma_x1.25** → fires on: ['var_z_pooled', 'rms_var_z_sigma', 'rms_var_z_mean']
- **sigma_x1.15** → fires on: ['var_z_pooled']

### 3c. The honest out-of-sample read of the multiplier

An in-sample `ĉ` is BY CONSTRUCTION the value that zeroes its own target — a CEILING, never a shippable estimate (the MH2.8 oracle discipline). Fitted on EARLIER, applied to RECENT:

| | |
|---|---|
| `ĉ` fitted on EARLIER (n = 246) | 1.0562 |
| `Var(z)` on RECENT (n = 409) before | 1.1094 |
| `Var(z)` on RECENT after applying `ĉ` | 0.9944 |
| gap to 1.0 closed? | ✅ yes (0.1094 → 0.0056) |

---

## 4. `home_win` — the calibrated-null placement

⚠️ **Stated in the pre-registration so it cannot be mistaken for a finding:** the registry records v6 `home_win` as a confirmed THIN-SIGNAL target (served spread ≈ 0.035), so a flat reliability curve is the EXPECTED shape, not a defect.

### FULL (n = 655)

served `p̂` SD **0.0371** · mean `p̂` 0.5080 vs realized home rate 0.5191 · Brier 0.2461 = reliability 0.0077 − resolution 0.0111 + uncertainty 0.2496

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `cil` | -0.0111 | -0.0004 | [-0.0386, 0.0378] | 0.625 | inside |
| `brier` | 0.2461 | 0.2485 | [0.2458, 0.2515] | 0.097 | inside |
| `reliability` | 0.0077 | 0.0035 | [0.0013, 0.0079] | 0.063 | inside |
| `ece` | 0.0727 | 0.0485 | [0.0294, 0.0736] | 0.059 | inside |
| `log_loss` | 0.6853 | 0.6901 | [0.6847, 0.6962] | 0.096 | inside |

### RECENT (n = 409)

served `p̂` SD **0.0368** · mean `p̂` 0.5090 vs realized home rate 0.5355 · Brier 0.2469 = reliability 0.0034 − resolution 0.0047 + uncertainty 0.2487

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `cil` | -0.0265 | 0.0004 | [-0.0485, 0.0469] | 0.290 | inside |
| `brier` | 0.2469 | 0.2485 | [0.2451, 0.2523] | 0.363 | inside |
| `reliability` | 0.0034 | 0.0032 | [0.0007, 0.0085] | 0.943 | inside |
| `ece` | 0.0440 | 0.0470 | [0.0218, 0.0791] | 0.836 | inside |
| `log_loss` | 0.6870 | 0.6901 | [0.6832, 0.6978] | 0.363 | inside |

---

## 5. ⭐ The multiplicity correction — what actually survives

The declared verdict family, BH-corrected at q = 0.05 across the union, in the primary window **FULL**:

- totals family: ['pit_mdd', 'bias', 'var_z_pooled']
- h2h family: ['cil', 'ece']

- ⛔ `rms_var_z_sigma` DROPPED from the FULL verdict family — the primary stratifier failed its validation (ρ = -0.042), so no Var(z) may be read off it

**Survivors: totals none, h2h none.**

| clause | value |
|---|---|
| `var_z_pooled` survives BH in the Normal null | ⛔ no |
| `var_z_pooled` outside the SHAPE-MATCHED null | ⛔ no |
| `ĉ` CI excludes 1.0 | ⛔ no |
| gap clears the MH2.5 materiality bar | ✅ yes |
| ⭐ observed gap vs the MDE | `\|ĉ − 1\|` = 0.0553 vs MDE − 1 = 0.0800 → **BELOW the MDE — undetectable here** |

---

## 6. Descriptive — morning vs post_lineup on the SAME games (⛔ VERDICT-INERT)

⛔ **Not an anchor** — post_lineup is not a known-correct reference, merely a model MH2.6 measured inside its null, and MH2.1 (b) forbids an incumbent-relative anchor. ⛔ **Not an information-monotonicity claim** — the two served contracts **do not nest** (16 vs 15 served columns, 7 shared), so the law-of-total-variance argument that would license one does not apply. It is reported because `σ_morning − σ_post` involves **no outcome at all**, so it names a mechanism at zero inferential cost.

| | morning | post_lineup |
|---|---:|---:|
| mean σ | 4.2928 | 4.3775 |
| mean σ² | 18.5043 | 19.2058 |
| σ CV | 0.0644 | 0.0476 |
| `Var(z)` | 1.1182 | 1.0257 |

On the **649** games both tiers priced (realized SD 4.5036), the morning model — which does not see the posted lineup — emits a **narrower** σ than the post-lineup model on **60.4%** of them.

---

## 7. ⭐ Power — what this window could and could not have detected

A null verdict means "no defect **larger than the MDE**". MH2.6 never computed power for this tier.

### At the served morning n = 655

**σ mis-scale** (detected via pooled `Var(z)`):

| σ × factor | detection rate |
|---:|---:|
| 1.02 | 0.12 |
| 1.05 | 0.49 |
| 1.08 | 0.83 |
| 1.1 | 0.94 |
| 1.15 | 1.00 |
| 1.2 | 1.00 |
| 1.25 | 1.00 |
| 1.3 | 1.00 |

**MDE at 80% power: 1.08**

**μ level shift** (detected via `bias`):

| runs | detection rate |
|---:|---:|
| 0.1 | 0.07 |
| 0.2 | 0.20 |
| 0.3 | 0.44 |
| 0.4 | 0.65 |
| 0.5 | 0.83 |
| 0.6 | 0.94 |
| 0.75 | 1.00 |
| 1 | 1.00 |

**MDE at 80% power: 0.5**

**`p̂` shift** (detected via calibration-in-the-large):

| probability | detection rate |
|---:|---:|
| 0.01 | 0.07 |
| 0.02 | 0.17 |
| 0.03 | 0.31 |
| 0.04 | 0.50 |
| 0.05 | 0.70 |
| 0.06 | 0.86 |
| 0.08 | 0.98 |
| 0.1 | 1.00 |

**MDE at 80% power: 0.06**

### ⭐ `games_needed` — the margin in the unit that GROWS

At the OBSERVED magnitude (`ĉ = 1.0553`), the rate at which the pooled σ test clears **the BH threshold it must actually clear** (`q/m = 0.0100` at a family of 5) — not an uncorrected α = 0.05, which is the premise's error:

| served games | detection rate |
|---:|---:|
| 655 | 0.34 |
| 900 | 0.41 |
| 1,200 | 0.53 |
| 1,600 | 0.69 |
| 2,200 | 0.85 |
| 3,000 | 0.91 |
| 4,000 | 0.99 |

**Games needed at 80% power: ≈2,200** — against 655 served today. At this era's rate of 13.4 morning games/day that is ≈165 days of serving in total, i.e. **≈116 more days**.

---

## 8. ⭐ The instrument's OWN measured operating characteristics

A verdict label means nothing until you know how often it appears on a **healthy** model. Every replicate below runs the WHOLE harness and reads the **verdict label Phase 2 keys on** — MH2.8's lesson that a negative control must apply the ship rule's threshold, not a bare "who looks closest".

### Negative control — 40 clean frames at n = 655, σ exactly right

| label | count | rate |
|---|---:|---:|
| `POWER_LIMITED` | 40 | 1.000 |

any defect label 0.000 (bar 0.15) · ⭐ `SIGMA_SCALE_DEFECT` 0.000 (bar 0.05) → ✅ PASSED

⭐⭐ **READ THE VERDICT THROUGH THIS ROW — it is the sharpest thing this study measured.** A **perfectly calibrated** morning model at this `n` returns `POWER_LIMITED` **40 times in 40** — the same label the SERVED model got. ⇒ **the verdict LABEL does not distinguish the served morning model from a flawless one at 655 games.** That is not a failure of the instrument: it is the instrument correctly refusing to certify anything at a sample size where an 8% σ error would go undetected. Two consequences, and both cut against over-reading this study in EITHER direction — ⛔ the label may not be quoted as reassurance about the morning σ, and ⛔ it may not be quoted as suspicion either. The only quantity carrying information about the served model is the MAGNITUDE (`ĉ` = 1.0553, against ≈1.00 for a clean frame), and its CI still includes 1.

### ⭐ The scale/shape discriminator control — 40 frames, σ **exactly right** but the truth SKEWED (α = 3.2)

This is the control that licenses any scale-vs-shape attribution at all: a correctly scaled but skewed world must **not** be reported as a σ-scale defect.

| label | count | rate |
|---|---:|---:|
| `OTHER_MISCALIBRATION` | 2 | 0.050 |
| `POWER_LIMITED` | 26 | 0.650 |
| `SHAPE_DEFECT` | 12 | 0.300 |

`SIGMA_SCALE_DEFECT` 0.000 (bar 0.05) → ✅ PASSED

### Detection on KNOWN σ defects at the same settings

| corruption | `SIGMA_SCALE_DEFECT` rate | any-flag rate |
|---|---:|---:|
| sigma_x1.25 | 1.00 | 1.00 |
| sigma_x1.15 | 1.00 | 1.00 |
| sigma_x0.85 | 1.00 | 1.00 |

### ⭐ Is the scale/shape boundary in the right PLACE? (`--reachability`, t-df 5 — heavy-tailed AND genuinely mis-scaled)

The clause-isolation guard proves `SHAPE_ARTIFACT` binds alone at the decision-rule level. That is necessary but not sufficient: a discriminator can be reachable in principle and still sit at a useless threshold. What must be shown is a **monotone hand-over** — the verdict moving from `SHAPE_ARTIFACT` to `SIGMA_SCALE_DEFECT` as the TRUE scale error grows past what the tail can account for. A machine answering `SHAPE_ARTIFACT` at every scale error could never blame σ, which is the mirror image of the premise's error and just as wrong.

| true σ error | labels | `SHAPE_ARTIFACT` | `SIGMA_SCALE_DEFECT` |
|---|---|---:|---:|
| × 1.06 | `OTHER_MISCALIBRATION` 3, `SHAPE_DEFECT` 1, `WITHIN_NOISE` 4 | 0.00 | 0.00 |
| × 1.08 | `SHAPE_ARTIFACT` 6, `SIGMA_SCALE_DEFECT` 2 | 0.75 | 0.25 |

both branches reached: ✅ · hand-over monotone in the true scale error: ✅

---

## 9. Verdict

**`POWER_LIMITED`** — nothing survives the correction, but the observed σ gap (ĉ = 1.0553) is SMALLER than the smallest σ deviation this window could detect at 80% power (MDE σ × 1.08) — the instrument could not have found an effect of the size it measured, so this is NOT a clean null.

**Phase 2 fires: NO.** ⛔ No retrain, no recalibration, no registry edit, no deploy.

### ⚠️ This is NOT a clean null, and the difference is the whole result

Read the two facts together:

1. The measured σ gap is **5.53%** and it is **MATERIAL** by MH2.5's bar — bigger than one coverage point.
2. The smallest σ error this window could have DECLARED at 80% power is **8%**. The effect is smaller than the instrument's resolution, so a non-detection here carries **no information against it**.

⭐ **And that MDE is the OPTIMISTIC one, so this label is the conservative call.** The MDE curve is measured against the UNCORRECTED two-sided null band, while the verdict requires clearing **BH** over the declared family — a strictly higher bar. The true BH-corrected MDE is therefore LARGER than the figure quoted, which puts the observed effect even further below resolution. Using the optimistic MDE makes `POWER_LIMITED` *harder* to declare, not easier.

⛔ Reporting that as "the morning σ is fine" would be false. ⛔ Reporting it as "the morning σ is too small" would be equally false — the pre-registered test does not support it. The honest statement is the third one: **the effect is real-looking, consistent, material in size, and NOT DECLARABLE at 655 served games.**

**What "real-looking" rests on — three readings that are not the pre-registered test, and do not substitute for it:**

1. **Same sign and near-identical size in two INDEPENDENT out-of-sample windows** — `Var(z)` = FULL 1.1136, RECENT 1.1094, EARLIER 1.1157. A noise artefact has no reason to reproduce to the third decimal across a disjoint split.
2. **The multiplier GENERALISES.** Fitted on EARLIER alone (`ĉ` = 1.0562) and applied to RECENT, it moves `Var(z)` 1.1094 → 0.9944. That is an out-of-sample read, not the in-sample ceiling.
3. **A coherent mechanism** — §6: on the games both tiers priced, the morning model emits a NARROWER σ than the post-lineup model, which MH2.6 measured inside its null.

⚠️ ⭐ **None of the three is a pre-registered test, and they are recorded as context, not as evidence that survived a gate.** Reading them as a finding would be the exact post-hoc promotion this lineage keeps punishing (E2.1-r); the pre-registered answer is the one above it, and it is `POWER_LIMITED`.

⭐ **The trigger is REACHABLE BY ACCUMULATION, which makes it a live re-test rather than a future note (MH2).** ≈2,200 served morning games at the observed magnitude — ≈116 more days of serving. ⛔ No new modelling, no wider field, no different statistic is needed — only games.

⚠️ **But say the calendar part out loud, because "reachable" is doing a lot of work.** ≈116 serving days is longer than the remainder of a regular season, so this re-test **crosses an off-season** — it is reachable, but not THIS year. And it is **conditional on `pre_lineup_v6` still being the served morning champion**: any retrain resets the era and the count starts again, because the population is defined by the champion, not by the calendar. ⇒ the honest trigger is *"re-run when the served morning era reaches ≈2,200 games"*, ⛔ never *"re-run in 116 days"*.

### What a Phase 2 would have to be, if the re-test ever declares it

⛔ **Not fired by this study.** Recorded so a successor does not have to re-derive it:

- a σ-widening on the **`pre_lineup` model only** — it is a DIFFERENT model from post_lineup with a DIFFERENT, non-nesting contract, and MH2.6 measured post_lineup's variance inside its null. ⛔ post_lineup is not touched.
- ⚠️ **a per-game σ fix is NOT available on this tier and that is a measured fact, not an oversight** — §1 shows the served morning σ orders realized dispersion with a NEGATIVE rank correlation, so there is no validated partition to condition a dynamic-range fix on. The only admissible shape of fix today is a **global scale multiplier**.
- the fix must beat **flat-σ as a null-to-beat** (MH2.1's rollback demoted flat-σ from a proven improvement to a null), carry a matched heteroscedastic foil, and be scored on CRPS plus the conditional instrument — on a stratifier that has passed its validation first.

⛔ **Deploy-held regardless.** Any promotion carries the MH2.1 landmines: a one-target swap breaks bundle-assuming consumers (`daily_model_predictions.model_version` is stamped from `home_win`; `mart_clv_labeled_games` hardcodes `v6`; the backfill idempotency key is `(game_pk, model_version, retrain_tag)`); serve the **validated object**, never a re-derivation; and **a registry change ships with the box image on merge to `main` — merging IS the deploy, with no gate between merge and serve.** `best_alpha = 0`.
