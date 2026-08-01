# E7.12 slice 6 — AAA-Statcast FEASIBILITY MEMO (pitchers)

> ⚠️ **This is a feasibility memo, not a bake-off.** `best_alpha = 0`.

## Verdict: **STOP — RECORD THE CEILING**

- 🚧 **STRUCTURAL — THIS IS THE BINDING CONSTRAINT.** 3 usable fold(s) < 4: CSCV/PBO is UNDEFINED at this fold count (`deflation_report` returns `pbo=None` and says so), so the §0.5 deflation requirement cannot be EVALUATED — not failed, undefined. No effect size and no choice of gate fixes this; only more debut cohorts do.
- 📉 POWER — under the pre-registered (conservative) gate the minimum detectable lift is also implausibly large: None% on covered rows, against a slice-1 best-ever delivered lift of ~3.5%.

⭐ **A bake-off that cannot detect its own effect is NOT a null — it is an unpowered test, and recording it as a null would retire a live mechanism on no evidence.** That is why this slice was gated, and it is why the point estimate below is reported with an interval and explicitly marked uninterpretable rather than being turned into a verdict.


## (a) Coverage — labelled rows carrying the `sc_*` block

Block: `sc_xwoba_against, sc_swing_miss_percent, sc_avg_pitch_velocity_mph, sc_avg_spin_rate_rpm, sc_avg_release_extension_ft, sc_hardhit_percent_against`


### By level

| level    |   covered |   labelled |   pct |
|:---------|----------:|-----------:|------:|
| Double-A |         0 |        858 |   0   |
| High-A   |         0 |        731 |   0   |
| Single-A |         0 |        557 |   0   |
| Triple-A |       277 |        885 |  31.3 |


The block is **Triple-A only** by construction — AAA is the only minor level with Hawk-Eye tracking — so any S6 arm is inherently level-gated, and the ceiling below is a property of the data source rather than of our ingest.


### By debut cohort

|   debut_cohort |   covered |   labelled |   pct |
|---------------:|----------:|-----------:|------:|
|           2015 |         0 |        243 |   0   |
|           2016 |         0 |        255 |   0   |
|           2017 |         0 |        265 |   0   |
|           2018 |         0 |        338 |   0   |
|           2019 |         0 |        251 |   0   |
|           2020 |         0 |        215 |   0   |
|           2021 |         0 |        312 |   0   |
|           2022 |        54 |        257 |  21   |
|           2023 |        71 |        287 |  24.7 |
|           2024 |        76 |        307 |  24.8 |
|           2025 |        62 |        245 |  25.3 |
|           2026 |        14 |         56 |  25   |

## (b) Fold viability

A fold Y trains on cohorts `< Y` and scores cohort Y, so it needs covered rows on BOTH sides: without covered TRAINING rows the arm is byte-identical to the baseline and scores `delta = 0`, which the `d > 0` fold test counts as a LOSS. **Scoring a mechanism on folds where it provably cannot act is not a stricter test, it is a broken one** — the S4 lesson, where exactly this capped an achievable fold-win-rate at 0.636 against a 0.60 gate.

|   fold |   covered_train |   covered_test |   labelled_test |   pct_test_covered | status                                                              |
|-------:|----------------:|---------------:|----------------:|-------------------:|:--------------------------------------------------------------------|
|   2016 |               0 |              0 |             255 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2017 |               0 |              0 |             265 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2018 |               0 |              0 |             338 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2019 |               0 |              0 |             251 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2020 |               0 |              0 |             215 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2021 |               0 |              0 |             312 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2022 |               0 |             54 |             257 |               21   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2023 |              54 |             71 |             287 |               24.7 | USABLE                                                              |
|   2024 |             125 |             76 |             307 |               24.8 | USABLE                                                              |
|   2025 |             201 |             62 |             245 |               25.3 | USABLE                                                              |
|   2026 |             263 |             14 |              56 |               25   | THIN (<30 covered held-out rows)                                    |

**Usable folds: [2023, 2024, 2025] (3 of 11 evaluable cohorts).**


## (c) Power — is the design able to detect the effect worth chasing? (`xwoba_against`)

Simulated against **the gate as it is actually coded** — fold-win-rate ≥ 0.60 AND a positive mean lift AND a one-sided paired t surviving BH-FDR — not against a generic power formula. Each clause fails differently at small n (the fold clause is coarse; the t clause has fat tails at low df), so any single-clause formula would flatter the design.


### Measured noise

```
{
  "n_folds": 3,
  "base_mae": 0.02399647523236083,
  "fold_delta_sd": 0.0012097086868373772,
  "fold_delta_sd_pct_of_mae": 5.0412,
  "point_estimate_pct": 0.5566,
  "ci95_pct": [
    -11.9664,
    13.0796
  ],
  "point_estimate_is_uninterpretable": true,
  "why": "reported for completeness, NOT as a result \u2014 at this fold count the interval spans both a large positive and a large negative lift, which is the definition of an unpowered design. Reading a sign off it would be the exact failure this memo exists to prevent."
}
```

### Power curve

|   true_lift_pct |   power_fold_gate |   power_bh |   power_full_rule |
|----------------:|------------------:|-----------:|------------------:|
|            0    |            0.4968 |     0.0192 |            0.0192 |
|            0.25 |            0.5238 |     0.0203 |            0.0203 |
|            0.5  |            0.5555 |     0.023  |            0.023  |
|            0.75 |            0.5927 |     0.0283 |            0.0283 |
|            1    |            0.6088 |     0.0335 |            0.0335 |
|            1.25 |            0.654  |     0.042  |            0.042  |
|            1.5  |            0.6683 |     0.0372 |            0.0372 |
|            1.75 |            0.706  |     0.0425 |            0.0425 |
|            2    |            0.7262 |     0.0558 |            0.0558 |
|            2.25 |            0.755  |     0.0615 |            0.0615 |
|            2.5  |            0.7762 |     0.0628 |            0.0628 |
|            2.75 |            0.775  |     0.0665 |            0.0665 |
|            3    |            0.8107 |     0.08   |            0.08   |
|            3.25 |            0.8325 |     0.083  |            0.083  |
|            3.5  |            0.8508 |     0.0917 |            0.0917 |
|            3.75 |            0.8672 |     0.0953 |            0.0953 |
|            4    |            0.8875 |     0.0978 |            0.0978 |
|            4.25 |            0.8938 |     0.113  |            0.113  |
|            4.5  |            0.9155 |     0.1245 |            0.1245 |
|            4.75 |            0.918  |     0.1328 |            0.1328 |
|            5    |            0.9313 |     0.144  |            0.144  |
|            5.25 |            0.9407 |     0.1497 |            0.1497 |
|            5.5  |            0.9405 |     0.169  |            0.169  |
|            5.75 |            0.9523 |     0.1805 |            0.1805 |
|            6    |            0.9607 |     0.1817 |            0.1817 |
|            6.25 |            0.9633 |     0.1913 |            0.1913 |
|            6.5  |            0.9735 |     0.2208 |            0.2208 |
|            6.75 |            0.9755 |     0.2293 |            0.2293 |
|            7    |            0.9802 |     0.24   |            0.24   |
|            7.25 |            0.984  |     0.2557 |            0.2557 |
|            7.5  |            0.9888 |     0.26   |            0.26   |
|            7.75 |            0.99   |     0.2797 |            0.2797 |
|            8    |            0.9898 |     0.2697 |            0.2697 |
|            8.25 |            0.9898 |     0.2915 |            0.2915 |
|            8.5  |            0.995  |     0.3292 |            0.3292 |
|            8.75 |            0.9952 |     0.3327 |            0.3327 |
|            9    |            0.996  |     0.3335 |            0.3335 |
|            9.25 |            0.9985 |     0.3485 |            0.3485 |
|            9.5  |            0.9972 |     0.3733 |            0.3733 |
|            9.75 |            0.9978 |     0.3825 |            0.3825 |
|           10    |            0.9988 |     0.396  |            0.396  |
|           10.25 |            0.9982 |     0.3942 |            0.3942 |
|           10.5  |            0.9995 |     0.44   |            0.44   |
|           10.75 |            0.9995 |     0.4313 |            0.4313 |
|           11    |            0.9995 |     0.4497 |            0.4497 |
|           11.25 |            0.9995 |     0.4615 |            0.4615 |
|           11.5  |            0.9995 |     0.4793 |            0.4793 |
|           11.75 |            1      |     0.5138 |            0.5138 |
|           12    |            1      |     0.5192 |            0.5192 |

### Minimum detectable lift

```
{
  "target_power": 0.8,
  "mde_fold_level_pct": null,
  "mde_on_covered_rows_pct": null,
  "covered_frac_of_test_rows": 0.2493,
  "note": "the fold statistic averages over ALL held-out rows while the arm can only move the covered ones, so the effect the MECHANISM must produce is the fold-level MDE divided by the covered fraction",
  "unreachable": true,
  "sensitivity_no_multiplicity_penalty": {
    "target_power": 0.8,
    "mde_fold_level_pct": 8.25,
    "mde_on_covered_rows_pct": 33.088,
    "covered_frac_of_test_rows": 0.2493,
    "note": "the fold statistic averages over ALL held-out rows while the arm can only move the covered ones, so the effect the MECHANISM must produce is the fold-level MDE divided by the covered fraction",
    "unreachable": false
  },
  "conclusion_survives_generous_gate": true,
  "fold_gate_false_fire_at_zero_lift": 0.4968
}
```

⚠️ **At this fold count the fold-win-rate clause is close to a coin flip: it fires 49.7% of the time on a TRUE lift of ZERO.** With 3 folds "≥60% of folds" collapses to "≥2 of 3", which a null clears about half the time — so essentially all of the discrimination is coming from the paired-t/BH clause, on 2 degrees of freedom. This is the same weakness E7.12-S5 hit from the other side, where a permuted-bucket placebo cleared the same clause 9/11.


## Re-open trigger

Stated as a DATA condition rather than a date, and mechanical: re-run this script.

```
{
  "usable_folds_now": 3,
  "folds_needed_for_pbo": 4,
  "additional_usable_folds_required": 1,
  "thin_folds_one_season_from_usable": [
    2026
  ],
  "typical_covered_rows_per_cohort": 71,
  "condition": "re-run when 1 more debut cohort(s) clear 30 covered held-out rows. The cohorts listed as THIN are in-progress seasons, not permanently short \u2014 a completed season has been running ~71 covered rows, comfortably over the threshold, so each completed season should convert one THIN fold to USABLE.",
  "how": "re-run this script; if `usable_folds_now` reaches the PBO minimum, the gate re-opens"
}
```

## 🚨 For whoever eventually runs the bake-off — a landmine in the plumbing

`PartialPoolProjector._design` calls `s.transform(df)[0]`: it takes `_Scaler`'s standardized VALUE and **discards the missing flag returned beside it**. So passing the `sc_*` columns through `extra_cols` alone gives every uncovered row `z = 0` — the mean OF THE COVERED SUBSET — which is a fabricated neutral asserted about ~88% of rows, and precisely what the story prompt forbids ("never fabricate a zero"). The arm must carry an explicit missing indicator per column so the model can offset the imputation instead of believing it; `_with_missing_indicators` in this module is the reference. Without it the bake-off would be measuring an assertion about uncovered players, not a Statcast effect.
