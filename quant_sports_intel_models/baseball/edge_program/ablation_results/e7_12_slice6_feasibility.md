# E7.12 slice 6 — AAA-Statcast FEASIBILITY MEMO (batters)

> ⚠️ **This is a feasibility memo, not a bake-off.** `best_alpha = 0`.

## Verdict: **STOP — RECORD THE CEILING**

- 🚧 **STRUCTURAL — THIS IS THE BINDING CONSTRAINT.** 3 usable fold(s) < 4: CSCV/PBO is UNDEFINED at this fold count (`deflation_report` returns `pbo=None` and says so), so the §0.5 deflation requirement cannot be EVALUATED — not failed, undefined. No effect size and no choice of gate fixes this; only more debut cohorts do.
- 📉 POWER — under the pre-registered (conservative) gate the minimum detectable lift is also implausibly large: 11.952% on covered rows, against a slice-1 best-ever delivered lift of ~3.5%.
- ⚖️ HONEST QUALIFICATION: under the MOST GENEROUS gate (no multiplicity penalty) the minimum detectable lift falls to 5.976% on covered rows, so the POWER argument alone would be arguable rather than decisive. **The stop rests on the STRUCTURAL blocker above, not on the power calculation** — stated because an argument that quietly leans on its weaker half is how a stale conclusion survives.

⭐ **A bake-off that cannot detect its own effect is NOT a null — it is an unpowered test, and recording it as a null would retire a live mechanism on no evidence.** That is why this slice was gated, and it is why the point estimate below is reported with an interval and explicitly marked uninterpretable rather than being turned into a verdict.


## (a) Coverage — labelled rows carrying the `sc_*` block

Block: `sc_xwoba, sc_barrels_per_pa_percent, sc_hardhit_percent, sc_avg_exit_velocity_mph, sc_avg_bat_speed_mph`


### By level

| level    |   covered |   labelled |   pct |
|:---------|----------:|-----------:|------:|
| Double-A |         0 |        607 |   0   |
| High-A   |         0 |        513 |   0   |
| Single-A |         0 |        405 |   0   |
| Triple-A |       259 |        646 |  40.1 |


The block is **Triple-A only** by construction — AAA is the only minor level with Hawk-Eye tracking — so any S6 arm is inherently level-gated, and the ceiling below is a property of the data source rather than of our ingest.


### By debut cohort

|   debut_cohort |   covered |   labelled |   pct |
|---------------:|----------:|-----------:|------:|
|           2015 |         0 |        146 |   0   |
|           2016 |         0 |        129 |   0   |
|           2017 |         0 |        153 |   0   |
|           2018 |         0 |        175 |   0   |
|           2019 |         0 |        196 |   0   |
|           2020 |         0 |        130 |   0   |
|           2021 |         0 |        177 |   0   |
|           2022 |        69 |        308 |  22.4 |
|           2023 |        59 |        237 |  24.9 |
|           2024 |        52 |        214 |  24.3 |
|           2025 |        59 |        226 |  26.1 |
|           2026 |        20 |         80 |  25   |

## (b) Fold viability

A fold Y trains on cohorts `< Y` and scores cohort Y, so it needs covered rows on BOTH sides: without covered TRAINING rows the arm is byte-identical to the baseline and scores `delta = 0`, which the `d > 0` fold test counts as a LOSS. **Scoring a mechanism on folds where it provably cannot act is not a stricter test, it is a broken one** — the S4 lesson, where exactly this capped an achievable fold-win-rate at 0.636 against a 0.60 gate.

|   fold |   covered_train |   covered_test |   labelled_test |   pct_test_covered | status                                                              |
|-------:|----------------:|---------------:|----------------:|-------------------:|:--------------------------------------------------------------------|
|   2016 |               0 |              0 |             129 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2017 |               0 |              0 |             153 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2018 |               0 |              0 |             175 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2019 |               0 |              0 |             196 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2020 |               0 |              0 |             130 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2021 |               0 |              0 |             177 |                0   | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2022 |               0 |             69 |             308 |               22.4 | INERT (no covered TRAINING row — arm is byte-identical to baseline) |
|   2023 |              69 |             59 |             237 |               24.9 | USABLE                                                              |
|   2024 |             128 |             52 |             214 |               24.3 | USABLE                                                              |
|   2025 |             180 |             59 |             226 |               26.1 | USABLE                                                              |
|   2026 |             239 |             20 |              80 |               25   | THIN (<30 covered held-out rows)                                    |

**Usable folds: [2023, 2024, 2025] (3 of 11 evaluable cohorts).**


## (c) Power — is the design able to detect the effect worth chasing? (`iso`)

Simulated against **the gate as it is actually coded** — fold-win-rate ≥ 0.60 AND a positive mean lift AND a one-sided paired t surviving BH-FDR — not against a generic power formula. Each clause fails differently at small n (the fold clause is coarse; the t clause has fat tails at low df), so any single-clause formula would flatter the design.


### Measured noise

```
{
  "n_folds": 3,
  "base_mae": 0.03362991318622943,
  "fold_delta_sd": 0.00030632618199119094,
  "fold_delta_sd_pct_of_mae": 0.9109,
  "point_estimate_pct": 1.4724,
  "ci95_pct": [
    -0.7903,
    3.7352
  ],
  "point_estimate_is_uninterpretable": true,
  "why": "reported for completeness, NOT as a result \u2014 at this fold count the interval spans both a large positive and a large negative lift, which is the definition of an unpowered design. Reading a sign off it would be the exact failure this memo exists to prevent."
}
```

### Power curve

|   true_lift_pct |   power_fold_gate |   power_bh |   power_full_rule |
|----------------:|------------------:|-----------:|------------------:|
|            0    |            0.4968 |     0.0248 |            0.0248 |
|            0.25 |            0.6645 |     0.0455 |            0.0455 |
|            0.5  |            0.7955 |     0.0862 |            0.0862 |
|            0.75 |            0.888  |     0.1335 |            0.1335 |
|            1    |            0.9467 |     0.197  |            0.197  |
|            1.25 |            0.9788 |     0.2732 |            0.2732 |
|            1.5  |            0.9912 |     0.359  |            0.359  |
|            1.75 |            0.9978 |     0.4373 |            0.4373 |
|            2    |            0.999  |     0.5383 |            0.5383 |
|            2.25 |            1      |     0.617  |            0.617  |
|            2.5  |            1      |     0.6903 |            0.6903 |
|            2.75 |            1      |     0.746  |            0.746  |
|            3    |            1      |     0.81   |            0.81   |
|            3.25 |            1      |     0.843  |            0.843  |
|            3.5  |            1      |     0.882  |            0.882  |
|            3.75 |            1      |     0.919  |            0.919  |
|            4    |            1      |     0.9413 |            0.9413 |
|            4.25 |            1      |     0.9617 |            0.9617 |
|            4.5  |            1      |     0.9695 |            0.9695 |
|            4.75 |            1      |     0.9828 |            0.9828 |
|            5    |            1      |     0.9888 |            0.9888 |
|            5.25 |            1      |     0.991  |            0.991  |
|            5.5  |            1      |     0.9968 |            0.9968 |
|            5.75 |            1      |     0.9955 |            0.9955 |
|            6    |            1      |     0.9988 |            0.9988 |
|            6.25 |            1      |     0.9995 |            0.9995 |
|            6.5  |            1      |     0.9992 |            0.9992 |
|            6.75 |            1      |     0.9995 |            0.9995 |
|            7    |            1      |     0.9998 |            0.9998 |
|            7.25 |            1      |     0.9998 |            0.9998 |
|            7.5  |            1      |     1      |            1      |
|            7.75 |            1      |     1      |            1      |
|            8    |            1      |     1      |            1      |
|            8.25 |            1      |     1      |            1      |
|            8.5  |            1      |     1      |            1      |
|            8.75 |            1      |     1      |            1      |
|            9    |            1      |     1      |            1      |
|            9.25 |            1      |     1      |            1      |
|            9.5  |            1      |     1      |            1      |
|            9.75 |            1      |     1      |            1      |
|           10    |            1      |     1      |            1      |
|           10.25 |            1      |     1      |            1      |
|           10.5  |            1      |     1      |            1      |
|           10.75 |            1      |     1      |            1      |
|           11    |            1      |     1      |            1      |
|           11.25 |            1      |     1      |            1      |
|           11.5  |            1      |     1      |            1      |
|           11.75 |            1      |     1      |            1      |
|           12    |            1      |     1      |            1      |

### Minimum detectable lift

```
{
  "target_power": 0.8,
  "mde_fold_level_pct": 3.0,
  "mde_on_covered_rows_pct": 11.952,
  "covered_frac_of_test_rows": 0.251,
  "note": "the fold statistic averages over ALL held-out rows while the arm can only move the covered ones, so the effect the MECHANISM must produce is the fold-level MDE divided by the covered fraction",
  "unreachable": false,
  "sensitivity_no_multiplicity_penalty": {
    "target_power": 0.8,
    "mde_fold_level_pct": 1.5,
    "mde_on_covered_rows_pct": 5.976,
    "covered_frac_of_test_rows": 0.251,
    "note": "the fold statistic averages over ALL held-out rows while the arm can only move the covered ones, so the effect the MECHANISM must produce is the fold-level MDE divided by the covered fraction",
    "unreachable": false
  },
  "conclusion_survives_generous_gate": false,
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
  "typical_covered_rows_per_cohort": 59,
  "condition": "re-run when 1 more debut cohort(s) clear 30 covered held-out rows. The cohorts listed as THIN are in-progress seasons, not permanently short \u2014 a completed season has been running ~59 covered rows, comfortably over the threshold, so each completed season should convert one THIN fold to USABLE.",
  "how": "re-run this script; if `usable_folds_now` reaches the PBO minimum, the gate re-opens"
}
```

## 🚨 For whoever eventually runs the bake-off — a landmine in the plumbing

`PartialPoolProjector._design` calls `s.transform(df)[0]`: it takes `_Scaler`'s standardized VALUE and **discards the missing flag returned beside it**. So passing the `sc_*` columns through `extra_cols` alone gives every uncovered row `z = 0` — the mean OF THE COVERED SUBSET — which is a fabricated neutral asserted about ~88% of rows, and precisely what the story prompt forbids ("never fabricate a zero"). The arm must carry an explicit missing indicator per column so the model can offset the imputation instead of believing it; `_with_missing_indicators` in this module is the reference. Without it the bake-off would be measuring an assertion about uncovered players, not a Statcast effect.
