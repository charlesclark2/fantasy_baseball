# MH2.6 — MLB game-model calibration audit (`total_runs` + `home_win`)

**Verdict: `STANDING_MISCALIBRATION`** — a statistic sits outside its calibrated null but did NOT move between windows — a property of the champion, not drift.

`best_alpha = 0` · deploy-held · Phase 2 fires: **NO**

> **What this study is.** A calibration audit of the rows the app ACTUALLY SERVED, against realized outcomes. It says nothing about win rate, edge or ROI — at `best_alpha = 0` no bet rode on either model during the window. Pre-registration: [`mh2_6_preregistration.md`](mh2_6_preregistration.md), committed before any statistic was computed.

## Population

| | |
|---|---|
| champion | E13.11 bundle (`v6` post_lineup / `pre_lineup_v6` morning) |
| era | 2026-06-23 → 2026-08-14 (anchor = newest date carrying finals) |
| served rows, post_lineup | 649 (RECENT 390 / EARLIER 259) |
| totals rows | 634 (⛔ 15 dropped: priced by the rolled-back MH2.1 challenger) |
| trigger cohort | 2026-08-13, 2026-08-14 |

Every served row post-dates the champion's fit (E13.11, 2026-06-23), so **the whole era is out of sample** — MH2.1's "split at the incumbent's fit date" rule holds by construction, which is what makes the RECENT vs EARLIER contrast admissible.

---

## 1. ⭐ The stratifier validation — published BEFORE any `Var(z)` is read

This is the exact step whose absence caused the MH2.1 rollback: *a conditional-calibration result is a property of its stratifier*. Bars are MH2.5's, imported not re-declared.

### FULL · `incumbent_sigma` (PRIMARY — the story's ask)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 64 | 4.068 | 3.989 | 0.353 | 3.243 |
| 1 | 63 | 4.201 | 4.608 | 0.411 | 3.601 |
| 2 | 63 | 4.260 | 4.596 | 0.409 | 3.584 |
| 3 | 64 | 4.308 | 3.659 | 0.323 | 3.077 |
| 4 | 63 | 4.338 | 5.043 | 0.449 | 3.874 |
| 5 | 63 | 4.369 | 4.256 | 0.379 | 3.620 |
| 6 | 64 | 4.402 | 4.627 | 0.409 | 3.558 |
| 7 | 63 | 4.459 | 4.437 | 0.395 | 3.703 |
| 8 | 63 | 4.542 | 4.510 | 0.402 | 3.750 |
| 9 | 64 | 4.820 | 5.171 | 0.457 | 4.344 |

ρ = 0.382 (bar 0.3) · endpoints 2.05 SE apart (bar 2.0) → ✅ VALIDATED

### FULL · `incumbent_mean` (SECONDARY)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 64 | 8.234 | 4.453 | 0.394 | 3.490 |
| 1 | 63 | 8.521 | 4.410 | 0.393 | 3.521 |
| 2 | 63 | 8.678 | 4.498 | 0.401 | 3.637 |
| 3 | 64 | 8.787 | 3.725 | 0.329 | 2.959 |
| 4 | 63 | 8.873 | 3.706 | 0.330 | 3.118 |
| 5 | 63 | 8.941 | 4.294 | 0.383 | 3.564 |
| 6 | 64 | 9.021 | 4.818 | 0.426 | 3.695 |
| 7 | 63 | 9.123 | 5.650 | 0.503 | 4.631 |
| 8 | 63 | 9.302 | 4.679 | 0.417 | 3.836 |
| 9 | 64 | 10.192 | 4.756 | 0.420 | 3.905 |

ρ = 0.552 (bar 0.3) · endpoints 0.53 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### RECENT · `incumbent_sigma` (PRIMARY — the story's ask)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 63 | 4.134 | 4.173 | 0.372 | 3.349 |
| 1 | 62 | 4.256 | 4.604 | 0.413 | 3.615 |
| 2 | 63 | 4.320 | 4.141 | 0.369 | 3.502 |
| 3 | 62 | 4.371 | 4.172 | 0.375 | 3.484 |
| 4 | 62 | 4.444 | 4.516 | 0.406 | 3.740 |
| 5 | 63 | 4.687 | 5.126 | 0.457 | 4.175 |

ρ = 0.371 (bar 0.3) · endpoints 1.62 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### RECENT · `incumbent_mean` (SECONDARY)

| bin | n | mean stratifier | realized SD | ± SE | mean abs resid |
|---:|---:|---:|---:|---:|---:|
| 0 | 63 | 8.324 | 4.858 | 0.433 | 3.933 |
| 1 | 62 | 8.643 | 4.456 | 0.400 | 3.568 |
| 2 | 63 | 8.814 | 3.875 | 0.345 | 3.219 |
| 3 | 62 | 8.934 | 3.334 | 0.299 | 2.921 |
| 4 | 62 | 9.088 | 4.984 | 0.448 | 4.366 |
| 5 | 63 | 9.737 | 4.861 | 0.433 | 3.858 |

ρ = 0.371 (bar 0.3) · endpoints 0.01 SE apart (bar 2.0) → ⛔ **DISQUALIFIED**

> ⛔ No `Var(z)` may be read off this partition. A failed validation is a finding, not a licence to read the number anyway.

### ⭐ Is the partition WRONG, or merely UNDER-POWERED? — stated in games

The served σ barely varies: **CV 0.0481**, extreme-decile ratio 1.186. A `k`-quantile partition separates realized dispersion by ≈`(r−1)·√(n/k)` SE, so clearing the pre-registered bar of 2.0 SE needs **≈1,155 served games** at `k = 10` — and that is the OPTIMISTIC case, since a partition of σ cannot separate realized dispersion by more than σ's own range without the model being accidentally right.

⇒ the σ-conditional instrument is **not available at this sample size**, and the remedy is served games, not a different statistic. This is a POWER statement about the instrument — ⛔ it is **not** evidence that σ is fine.

---

## 2. `total_runs` — the calibrated-null placement

Outcomes re-drawn from the served predictive itself, `n` and per-game μ/σ held fixed: *would a perfectly calibrated served model produce a window that looks this rough?*

### FULL (n = 634)

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `pit_mdd` | 0.0420 | 0.0215 | [0.0117, 0.0356] | 0.008 | ⚠️ **OUTSIDE** |
| `pit_ks` | 0.0863 | 0.0329 | [0.0187, 0.0554] | 0.001 | ⚠️ **OUTSIDE** |
| `cov80` | 0.7918 | 0.7997 | [0.7697, 0.8297] | 0.639 | inside |
| `cov50` | 0.4748 | 0.5000 | [0.4606, 0.5379] | 0.224 | inside |
| `bias` | 0.0085 | 0.0022 | [-0.3227, 0.3256] | 0.970 | inside |
| `rmse` | 4.5205 | 4.3904 | [4.1448, 4.6332] | 0.287 | inside |
| `crps` | 2.5338 | 2.4747 | [2.3392, 2.6149] | 0.394 | inside |
| `var_z_pooled` | 1.0648 | 1.0042 | [0.8961, 1.1160] | 0.282 | inside |
| `rms_var_z_sigma` | 0.1763 | 0.1728 | [0.1020, 0.2596] | 0.934 | inside |
| `rms_var_z_mean` | 0.2497 | 0.1731 | [0.1034, 0.2614] | 0.083 | inside |

### RECENT (n = 375)

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `pit_mdd` | 0.0600 | 0.0280 | [0.0147, 0.0467] | 0.005 | ⚠️ **OUTSIDE** |
| `pit_ks` | 0.1076 | 0.0422 | [0.0245, 0.0748] | 0.001 | ⚠️ **OUTSIDE** |
| `cov80` | 0.8053 | 0.8000 | [0.7573, 0.8400] | 0.878 | inside |
| `cov50` | 0.4373 | 0.4987 | [0.4480, 0.5520] | 0.013 | ⚠️ **OUTSIDE** |
| `bias` | -0.2034 | -0.0021 | [-0.4168, 0.4313] | 0.346 | inside |
| `rmse` | 4.4602 | 4.3848 | [4.0782, 4.7000] | 0.628 | inside |
| `crps` | 2.5222 | 2.4735 | [2.2979, 2.6571] | 0.584 | inside |
| `var_z_pooled` | 1.0368 | 1.0043 | [0.8703, 1.1547] | 0.668 | inside |
| `rms_var_z_sigma` | 0.1171 | 0.1686 | [0.0778, 0.2884] | 0.280 | inside |
| `rms_var_z_mean` | 0.2622 | 0.1696 | [0.0799, 0.2919] | 0.126 | inside |

### TRIGGER (n = 23)

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `pit_mdd` | 0.0739 | 0.1174 | [0.0739, 0.2043] | 0.394 | inside |
| `pit_ks` | 0.1439 | 0.1661 | [0.0947, 0.2991] | 0.651 | inside |
| `cov80` | 0.7826 | 0.8261 | [0.6087, 0.9565] | 0.997 | inside |
| `cov50` | 0.3478 | 0.4783 | [0.3043, 0.6957] | 0.217 | inside |
| `bias` | -0.5634 | 0.0019 | [-1.7818, 1.6975] | 0.570 | inside |
| `rmse` | 4.8140 | 4.2672 | [3.1106, 5.6427] | 0.425 | inside |
| `crps` | 2.8390 | 2.4148 | [1.8197, 3.2433] | 0.297 | inside |
| `var_z_pooled` | 1.2937 | 0.9728 | [0.4990, 1.6951] | 0.348 | inside |
| `rms_var_z_sigma` | 0.4261 | 0.4611 | [0.1461, 1.1150] | 0.863 | inside |
| `rms_var_z_mean` | 0.7743 | 0.4577 | [0.1491, 1.1392] | 0.233 | inside |

### ⚠️ POST-HOC — what shape the flagged non-uniformity actually has

`pit_mdd`/`pit_ks` are pre-registered and say the PIT is not uniform; they do not say in what shape. This decomposition is **post-hoc**, is excluded from the verdict family, and changes no verdict — it exists so the flag is actionable rather than merely alarming.

| decile | 0.0–0.1 | 0.1–0.2 | 0.2–0.3 | 0.3–0.4 | 0.4–0.5 | 0.5–0.6 | 0.6–0.7 | 0.7–0.8 | 0.8–0.9 | 0.9–1.0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| observed | 0.085 | 0.136 | 0.109 | 0.142 | 0.101 | 0.074 | 0.068 | 0.068 | 0.095 | 0.123 |
| dev from 0.100 | -0.015 | +0.036 | +0.009 | +0.042 | +0.001 | -0.026 | -0.032 | -0.032 | -0.005 | +0.023 |

- realized `z` **skew 0.735**, excess kurtosis 0.588 — the served predictive is a **symmetric Normal** and realized total runs are **right-skewed** (a blow-up inning has no left-hand mirror). It is a SHAPE error, not a level or scale error: `bias` and `Var(z)` are both inside their nulls.
- ⭐ **mass below the predictive median = 0.573** against a nominal 0.500 — 3.7 SE out. For a right-skewed target the mean sits above the median, and a Normal puts them in the same place, so the served median runs high.
- **Why this is the serving-relevant number:** the product prints `P(total > line)`, a CDF read near the middle. At a line sitting at the model's own mean the model says 0.500 while realized frequency is 0.427 — an over-statement of `P(over)` of about **7 percentage points** at that point. ⚠️ Measured at the model's own mean, NOT at the actual posted lines, so it bounds the shape error rather than the served error.

### ⭐ Positive controls — the test is proven able to FIRE at this n

- **sigma_x1.25** → fires on: `bias`, `cov80`, `pit_mdd`, `rms_var_z_sigma`, `var_z_pooled`
- **mu_plus_0.75** → fires on: `bias`, `cov80`, `pit_mdd`

---

## 3. `home_win` — the calibrated-null placement

⚠️ Served `p̂` SD = **0.0363** on the full era. The registry records v6 `home_win` as a confirmed THIN-SIGNAL target (calibrated spread ≈0.035), so a flat reliability curve is the EXPECTED shape, not a defect — stated in the pre-registration so it cannot be mistaken for a finding.

### FULL (n = 649)

mean `p̂` 0.5046 vs realized home rate 0.5208 · Brier 0.2456 = reliability 0.0046 − resolution 0.0081 + uncertainty 0.2496

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `cil` | -0.0162 | -0.0008 | [-0.0378, 0.0392] | 0.452 | inside |
| `brier` | 0.2456 | 0.2486 | [0.2460, 0.2513] | 0.025 | ⚠️ **OUTSIDE** |
| `reliability` | 0.0046 | 0.0036 | [0.0013, 0.0076] | 0.551 | inside |
| `ece` | 0.0526 | 0.0485 | [0.0284, 0.0732] | 0.746 | inside |
| `log_loss` | 0.6843 | 0.6903 | [0.6851, 0.6958] | 0.025 | ⚠️ **OUTSIDE** |

### RECENT (n = 390)

mean `p̂` 0.5053 vs realized home rate 0.5436 · Brier 0.2454 = reliability 0.0038 − resolution 0.0060 + uncertainty 0.2481

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `cil` | -0.0383 | -0.0024 | [-0.0486, 0.0489] | 0.146 | inside |
| `brier` | 0.2454 | 0.2487 | [0.2453, 0.2522] | 0.063 | inside |
| `reliability` | 0.0038 | 0.0034 | [0.0008, 0.0090] | 0.840 | inside |
| `ece` | 0.0419 | 0.0479 | [0.0227, 0.0805] | 0.655 | inside |
| `log_loss` | 0.6839 | 0.6905 | [0.6836, 0.6977] | 0.062 | inside |

### TRIGGER (n = 23)

mean `p̂` 0.4960 vs realized home rate 0.4783 · Brier 0.2580 = reliability 0.0538 − resolution 0.0446 + uncertainty 0.2495

| statistic | observed | calibrated-null median | null 95% band | p (2-sided) | verdict |
|---|---:|---:|---:|---:|---|
| `cil` | 0.0178 | 0.0178 | [-0.1996, 0.1917] | 1.000 | inside |
| `brier` | 0.2580 | 0.2496 | [0.2406, 0.2589] | 0.076 | inside |
| `reliability` | 0.0538 | 0.0257 | [0.0023, 0.0948] | 0.340 | inside |
| `ece` | 0.2109 | 0.1370 | [0.0411, 0.2787] | 0.302 | inside |
| `log_loss` | 0.7092 | 0.6923 | [0.6743, 0.7110] | 0.076 | inside |

### ⭐ Positive control

- **p_plus_0.05** → fires on: **nothing**

---

## 4. Drift — RECENT vs EARLIER (both out of sample, same champion, same pipeline)

### `total_runs`

| statistic | RECENT − EARLIER | 95% CI | verdict |
|---|---:|---:|---|
| `bias` | -0.5343 | [-1.2884, 0.1981] | no move |
| `rmse` | -0.1427 | [-0.7361, 0.4238] | no move |
| `crps` | -0.0288 | [-0.3455, 0.2601] | no move |
| `pit_mdd` | -0.0156 | [-0.0621, 0.0269] | no move |
| `cov80` | 0.0049 | [-0.0586, 0.0717] | no move |
| `var_z_pooled` | -0.0630 | [-0.3476, 0.1970] | no move |
| `rms_var_z_sigma` | -0.0470 | [-0.3250, 0.1827] | no move |
| `sigma_sd` | -0.0333 | [-0.0909, 0.0179] | no move |

### `home_win`

| statistic | RECENT − EARLIER | 95% CI | verdict |
|---|---:|---:|---|
| `cil` | -0.0546 | [-0.1335, 0.0228] | no move |
| `brier` | -0.0005 | [-0.0060, 0.0053] | no move |
| `ece` | -0.0112 | [-0.0740, 0.0476] | no move |
| `reliability` | -0.0027 | [-0.0174, 0.0094] | no move |
| `p_sd` | 0.0003 | [-0.0042, 0.0050] | no move |

### Declared sensitivity — median-date split at 2026-07-22

`total_runs`:

| statistic | RECENT − EARLIER | 95% CI | verdict |
|---|---:|---:|---|
| `bias` | -0.7040 | [-1.4241, -0.0193] | ⚠️ **moved** |
| `rmse` | -0.1379 | [-0.6885, 0.4089] | no move |
| `crps` | -0.0023 | [-0.2893, 0.2791] | no move |
| `var_z_pooled` | -0.0501 | [-0.3145, 0.2040] | no move |

`home_win`:

| statistic | RECENT − EARLIER | 95% CI | verdict |
|---|---:|---:|---|
| `cil` | -0.0280 | [-0.1082, 0.0495] | no move |
| `brier` | -0.0015 | [-0.0072, 0.0041] | no move |
| `ece` | -0.0030 | [-0.0620, 0.0582] | no move |

---

## 5. ⭐ Power — what this window could and could not have detected

A null verdict means "no defect **larger than the MDE**". Stating it is the difference between a measured null and a shrug.

### RECENT (n = 375 games)

**σ mis-scale** (detected via pooled `Var(z)`):

| σ × factor | detection rate |
|---:|---:|
| 1.02 | 0.08 |
| 1.05 | 0.22 |
| 1.08 | 0.53 |
| 1.1 | 0.70 |
| 1.15 | 0.95 |
| 1.2 | 0.99 |
| 1.25 | 1.00 |
| 1.3 | 1.00 |
| 1.4 | 1.00 |
| 1.5 | 1.00 |

**MDE at 80% power: 1.15**

**μ level shift** (detected via `bias`):

| runs | detection rate |
|---:|---:|
| 0.1 | 0.08 |
| 0.2 | 0.14 |
| 0.3 | 0.28 |
| 0.4 | 0.47 |
| 0.5 | 0.60 |
| 0.6 | 0.79 |
| 0.75 | 0.91 |
| 1 | 1.00 |
| 1.25 | 1.00 |
| 1.5 | 1.00 |

**MDE at 80% power: 0.75**

**`p̂` shift** (detected via calibration-in-the-large):

| probability | detection rate |
|---:|---:|
| 0.01 | 0.06 |
| 0.02 | 0.09 |
| 0.03 | 0.22 |
| 0.04 | 0.30 |
| 0.05 | 0.48 |
| 0.06 | 0.62 |
| 0.08 | 0.85 |
| 0.1 | 0.97 |
| 0.12 | 0.99 |
| 0.15 | 1.00 |

**MDE at 80% power: 0.08**

### TRIGGER (n = 23 games)

**σ mis-scale** (detected via pooled `Var(z)`):

| σ × factor | detection rate |
|---:|---:|
| 1.02 | 0.06 |
| 1.05 | 0.08 |
| 1.08 | 0.12 |
| 1.1 | 0.15 |
| 1.15 | 0.23 |
| 1.2 | 0.33 |
| 1.25 | 0.42 |
| 1.3 | 0.50 |
| 1.4 | 0.69 |
| 1.5 | 0.80 |

**MDE at 80% power: 1.5**

**μ level shift** (detected via `bias`):

| runs | detection rate |
|---:|---:|
| 0.1 | 0.04 |
| 0.2 | 0.06 |
| 0.3 | 0.06 |
| 0.4 | 0.07 |
| 0.5 | 0.07 |
| 0.6 | 0.13 |
| 0.75 | 0.15 |
| 1 | 0.21 |
| 1.25 | 0.30 |
| 1.5 | 0.42 |

**MDE at 80% power: **NOT REACHED on the grid****

**`p̂` shift** (detected via calibration-in-the-large):

| probability | detection rate |
|---:|---:|
| 0.01 | 0.02 |
| 0.02 | 0.02 |
| 0.03 | 0.03 |
| 0.04 | 0.04 |
| 0.05 | 0.03 |
| 0.06 | 0.06 |
| 0.08 | 0.06 |
| 0.1 | 0.11 |
| 0.12 | 0.15 |
| 0.15 | 0.26 |

**MDE at 80% power: **NOT REACHED on the grid****

---

## 5b. ⭐ The instrument's OWN measured operating characteristics

A verdict label means nothing until you know how often it appears on a **healthy** model. Measured on 40 synthetic frames drawn from a perfectly calibrated predictive, at the same reps this run used (`--acceptance`):

| label | rate on CALIBRATED data | 95% CI |
|---|---:|---:|
| any non-`WITHIN_NOISE` | 5/40 = 0.125 | [0.042, 0.268] |
| `STANDING_MISCALIBRATION` | 3/40 = 0.075 | [0.016, 0.204] |
| `WITHIN_NOISE_WITH_MOVEMENT` | 2/40 = 0.050 | [0.006, 0.169] |
| ⭐ `DRIFT` — **the only label that fires Phase 2** | **0/40 = 0.000** | [0.000, 0.088] |

Detection on known defects at the same settings: σ×1.35 **8/8**, σ×0.70 **8/8**, μ+1.5 **8/8**, `p̂`+0.12 **8/8**, σ×1.15 **5/8**.

⚠️ **Read the verdict through this table.** `STANDING_MISCALIBRATION` carries a ~7.5% false-positive rate on healthy data, so a single flagged statistic is weak on its own — which is why what matters below is that the SAME statistic is flagged independently in two nested windows and has a coherent mechanism, not that it tripped a threshold.

---

## 6. Verdict

**`STANDING_MISCALIBRATION`** — a statistic sits outside its calibrated null but did NOT move between windows — a property of the champion, not drift.

- outside the calibrated null, RECENT: totals ['pit_mdd'], h2h none
- outside the calibrated null, FULL era: totals ['pit_mdd'], h2h none
- RECENT−EARLIER difference excludes zero: totals none, h2h none

- ⛔ `rms_var_z_sigma` DROPPED from the RECENT verdict family — the primary stratifier failed its validation, so no Var(z) may be read off it

**Phase 2 fires: NO.** ⛔ No retrain, no recalibration, no registry edit, no deploy.

### Why Phase 2 does not fire, and what would be needed if it ever did

The pre-registered rule separates two things the trigger conflated, and the separation is the whole result:

1. **The two days are not the story.** Nothing moved between windows, and every statistic on the trigger cohort sits inside its calibrated null. §5 shows that cohort could not have detected even a gross defect, so it carries no information either way.
2. **There IS a standing property of the champion**, present just as strongly in the earlier window as in the recent one. Being standing, it is by definition not what changed over two days.

⚠️ **Neither Phase-2 branch this story pre-scoped is the right instrument for it.** The scoped branches were σ dynamic range (the MH2.5 target) and level/mean drift (a wide-window retrain). The flagged defect is neither: the level is unbiased, the pooled variance is inside its null, and the σ-conditional partition is DISQUALIFIED so no σ claim can be made at all. Firing a scoped branch at an unscoped defect would be fitting to noise with extra steps.

A successor, if the operator wants one, is a **distributional-shape** study — a skew-aware predictive against the served symmetric Normal, on the §0.5 discipline, with the shape claim pre-registered and a matched foil that isolates skew from scale. ⛔ That is a new pre-registration, not a continuation of this one, and this study does **not** claim such a change would improve the served number.
