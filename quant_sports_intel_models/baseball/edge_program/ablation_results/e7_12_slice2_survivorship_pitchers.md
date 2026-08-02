# E7.12 slice 2 — promotion-selection (survivorship) correction (pitchers)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "same as the batter report \u2014 no stored artifact survives for slice2 (pitcher side).",
 "schema": 1,
 "source_artifact": null,
 "status": "unrecoverable",
 "verdict": null
}
-->


> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.**

This slice asks whether correcting for the fact that the MLE is FIT ON GRADUATES and SERVED ON PROSPECTS improves the translation. Two distinct mechanisms are registered separately because they address different problems:

- **IPW** targets the ESTIMAND — re-weighting training toward the served population. It does **not** fix bias; selection on an observed covariate leaves `E[Y|X]` unbiased.

- **Heckman** (inverse-Mills ratio) targets SELECTION ON UNOBSERVABLES — scout judgement, health, organisational need — which is the only channel that can actually bias the translation.


The baseline is the **SHIPPED slice-1 configuration per metric**, not a bare E7.3 incumbent, and an IPW weight MULTIPLIES the shipped label-precision weight rather than replacing it — otherwise the comparison would confound adding IPW with removing label weighting.


## Synthetic-truth recovery — this slice's oracle floor

The live gate can only score players who WERE promoted, so it measures *"does modelling selection improve prediction ON GRADUATES"* — strictly weaker than *"removes the bias"*. A live null is therefore ambiguous between **no bias** and **the correction cannot be validated on the observable population**. This check plants a KNOWN selection-on-unobservables process and scores against the true `E[Y|X]` over the FULL population, including the un-promoted — the quantity the live gate cannot see.

```
{
  "uncorrected": 1.423972508427122,
  "ipw": 1.4054476433576435,
  "heckman": 0.8031566447874389,
  "joint": 1.4434216922171863,
  "heckman_mills_carried_into_predict": 1.4427186105561591,
  "promotion_rate": 0.12,
  "rho_unobserved": 0.8,
  "best_correction": "heckman",
  "recovers_planted_bias": true,
  "pct_bias_removed": 43.6,
  "reading": "\u2705 the machinery RECOVERS a planted selection bias (heckman cuts the error against the true population translation by 43.6%), so a null on live data is a REAL null \u2014 evidence that selection on unobservables is not materially biasing this translation."
}
```

**✅ the machinery RECOVERS a planted selection bias (heckman cuts the error against the true population translation by 43.6%), so a null on live data is a REAL null — evidence that selection on unobservables is not materially biasing this translation.**


## Verdicts

| metric        | shipped_baseline    | verdict   | winner       |   pct_lift |   fold_win_rate | BH-FDR@0.10   |   PBO(eligible) |
|:--------------|:--------------------|:----------|:-------------|-----------:|----------------:|:--------------|----------------:|
| k_pct         | S0_baseline         | DROP      | T0_shipped   |      0     |            0    | False         |           0.086 |
| bb_pct        | S5_full_labelweight | DROP      | T0_shipped   |      0     |            0    |               |           0.1   |
| hr_rate       | S5_full_labelweight | ADD       | T1b_ipw_odds |      0.159 |            0.82 | True          |           0.171 |
| gb_pct        | S0_baseline         | DROP      | T0_shipped   |      0     |            0    |               |           0.971 |
| xwoba_against | S0_baseline         | DROP      | T0_shipped   |      0     |            0    |               |           0     |

---

## `k_pct` (baseline = `S0_baseline`, prior scale 4.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T1b_ipw_odds         | ladder      | True         |  0.035514 |         0.000107 |         0.301024 |        0.636364 |      0.132253 |            0.973327 |              0      |
| T1_ipw               | ladder      | True         |  0.035532 |         8.9e-05  |         0.248882 |        0.636364 |      0.132212 |            0.984918 |              0      |
| V_ipw_clip_tight     | sensitivity | True         |  0.035532 |         8.9e-05  |         0.248882 |        0.636364 |      0.132212 |            0.985736 |             13.0909 |
| T3_joint             | ladder      | True         |  0.035582 |         3.8e-05  |         0.107651 |        0.545455 |      0.319954 |            0.984918 |              0      |
| T0_shipped           | ladder      | True         |  0.035621 |         0        |         0        |        0        |    nan        |          nan        |            nan      |
| A_uniform_weight     | anchor      | False        |  0.035621 |         0        |         0        |        0        |    nan        |          nan        |            nan      |
| T2_heckman           | ladder      | True         |  0.035644 |        -2.3e-05  |        -0.06546  |        0.545455 |      0.735212 |          nan        |            nan      |
| A_mills_placebo      | anchor      | False        |  0.035662 |        -4.1e-05  |        -0.116209 |        0.272727 |      0.903495 |          nan        |            nan      |
| A_propensity_placebo | anchor      | False        |  0.035743 |        -0.000123 |        -0.344194 |        0.454545 |      0.845923 |            0.984918 |              0      |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 394 | 0.0386 |           -0.1484 |
| A_mills_placebo      |         1 | 725 | 0.0362 |           -0.0281 |
| A_mills_placebo      |         2 | 855 | 0.0346 |           -0.1468 |
| A_propensity_placebo |         0 | 394 | 0.0388 |           -0.7595 |
| A_propensity_placebo |         1 | 725 | 0.0363 |           -0.2352 |
| A_propensity_placebo |         2 | 855 | 0.0345 |           -0.0843 |
| A_uniform_weight     |         0 | 394 | 0.0385 |            0      |
| A_uniform_weight     |         1 | 725 | 0.0362 |            0      |
| A_uniform_weight     |         2 | 855 | 0.0345 |            0      |
| T0_shipped           |         0 | 394 | 0.0385 |            0      |
| T0_shipped           |         1 | 725 | 0.0362 |            0      |
| T0_shipped           |         2 | 855 | 0.0345 |            0      |
| T1_ipw               |         0 | 394 | 0.0384 |            0.4239 |
| T1_ipw               |         1 | 725 | 0.0361 |            0.0949 |
| T1_ipw               |         2 | 855 | 0.0344 |            0.1908 |
| T1b_ipw_odds         |         0 | 394 | 0.0383 |            0.4645 |
| T1b_ipw_odds         |         1 | 725 | 0.0361 |            0.0962 |
| T1b_ipw_odds         |         2 | 855 | 0.0344 |            0.2618 |
| T2_heckman           |         0 | 394 | 0.0384 |            0.2555 |
| T2_heckman           |         1 | 725 | 0.0362 |           -0.0262 |
| T2_heckman           |         2 | 855 | 0.0346 |           -0.1527 |
| T3_joint             |         0 | 394 | 0.0383 |            0.6884 |
| T3_joint             |         1 | 725 | 0.0361 |            0.0754 |
| T3_joint             |         2 | 855 | 0.0346 |           -0.1448 |
| V_ipw_clip_tight     |         0 | 394 | 0.0384 |            0.4239 |
| V_ipw_clip_tight     |         1 | 725 | 0.0361 |            0.0949 |
| V_ipw_clip_tight     |         2 | 855 | 0.0344 |            0.1908 |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 0.00021125875983026577,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.8554337572665834,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": 1.8077280968745926e-05,
    "challenger_fold_wins": 6,
    "n_folds": 11,
    "p_challenger_better": 0.6329444844368806,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.03574343363595647,
  "ipw_mae": 0.03553217487612622,
  "mills_placebo_mae": 0.035662223415593504,
  "heckman_mae": 0.03564414613462475,
  "concentration": {
    "T1_ipw": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.4239,
      "high_propensity_lift_pct": 0.1908,
      "gradient_high_minus_low_pct": -0.2331,
      "mid_propensity_lift_pct": 0.0949
    },
    "T1b_ipw_odds": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.4645,
      "high_propensity_lift_pct": 0.2618,
      "gradient_high_minus_low_pct": -0.2027,
      "mid_propensity_lift_pct": 0.0962
    },
    "T2_heckman": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.2555,
      "high_propensity_lift_pct": -0.1527,
      "gradient_high_minus_low_pct": -0.4082,
      "mid_propensity_lift_pct": -0.0262
    },
    "T3_joint": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.6884,
      "high_propensity_lift_pct": -0.1448,
      "gradient_high_minus_low_pct": -0.8332,
      "mid_propensity_lift_pct": 0.0754
    },
    "V_ipw_clip_tight": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.4239,
      "high_propensity_lift_pct": 0.1908,
      "gradient_high_minus_low_pct": -0.2331,
      "mid_propensity_lift_pct": 0.0949
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.891
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9164
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9169
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9277
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9394
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9451
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9546
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9567

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.08571428571428572,
  "os_gap_pct": 0.0,
  "os_gap_p90_pct": 0.3864,
  "contender_spread_pct": 0.052,
  "full_spread_pct": 0.368,
  "flips": [
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 386,
      "share": 0.835,
      "mean_oos_mae": 0.03551,
      "pct_vs_best": 0.0
    },
    {
      "config": "T0_shipped",
      "IS_half_wins": 30,
      "share": 0.065,
      "mean_oos_mae": 0.03562,
      "pct_vs_best": 0.302
    },
    {
      "config": "T1_ipw",
      "IS_half_wins": 26,
      "share": 0.056,
      "mean_oos_mae": 0.03553,
      "pct_vs_best": 0.052
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 16,
      "share": 0.035,
      "mean_oos_mae": 0.03564,
      "pct_vs_best": 0.368
    },
    {
      "config": "T3_joint",
      "IS_half_wins": 4,
      "share": 0.009,
      "mean_oos_mae": 0.03558,
      "pct_vs_best": 0.194
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.14285714285714285,
    "os_gap_pct": 0.0,
    "os_gap_p90_pct": 0.8725,
    "contender_spread_pct": 0.052,
    "full_spread_pct": 0.647,
    "flips": [
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 369,
        "share": 0.799,
        "mean_oos_mae": 0.03551,
        "pct_vs_best": 0.0
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 44,
        "share": 0.095,
        "mean_oos_mae": 0.03574,
        "pct_vs_best": 0.647
      },
      {
        "config": "A_mills_placebo",
        "IS_half_wins": 21,
        "share": 0.045,
        "mean_oos_mae": 0.03566,
        "pct_vs_best": 0.418
      },
      {
        "config": "T1_ipw",
        "IS_half_wins": 11,
        "share": 0.024,
        "mean_oos_mae": 0.03553,
        "pct_vs_best": 0.052
      },
      {
        "config": "T2_heckman",
        "IS_half_wins": 11,
        "share": 0.024,
        "mean_oos_mae": 0.03564,
        "pct_vs_best": 0.368
      },
      {
        "config": "T3_joint",
        "IS_half_wins": 4,
        "share": 0.009,
        "mean_oos_mae": 0.03558,
        "pct_vs_best": 0.194
      },
      {
        "config": "T0_shipped",
        "IS_half_wins": 2,
        "share": 0.004,
        "mean_oos_mae": 0.03562,
        "pct_vs_best": 0.302
      }
    ]
  }
}
```

### Notes

- ⛔ FDR-DOWNGRADED — did not survive Benjamini-Hochberg at alpha=0.10 across the metrics tested in this run

---

## `bb_pct` (baseline = `S5_full_labelweight`, prior scale 4.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| A_propensity_placebo | anchor      | False        |  0.019045 |          2.6e-05 |         0.137699 |        0.636364 |      0.077215 |            0.984918 |              0      |
| T0_shipped           | ladder      | True         |  0.019071 |          0       |         0        |        0        |    nan        |          nan        |            nan      |
| A_uniform_weight     | anchor      | False        |  0.019071 |          0       |         0        |        0        |    nan        |          nan        |            nan      |
| V_ipw_clip_tight     | sensitivity | True         |  0.019084 |         -1.3e-05 |        -0.066419 |        0.363636 |      0.764661 |            0.985736 |             13.0909 |
| T1_ipw               | ladder      | True         |  0.019084 |         -1.3e-05 |        -0.066419 |        0.363636 |      0.764661 |            0.984918 |              0      |
| A_mills_placebo      | anchor      | False        |  0.01909  |         -1.9e-05 |        -0.101426 |        0.181818 |      0.973705 |          nan        |            nan      |
| T1b_ipw_odds         | ladder      | True         |  0.019096 |         -2.4e-05 |        -0.128392 |        0.363636 |      0.828007 |            0.973327 |              0      |
| T2_heckman           | ladder      | True         |  0.019128 |         -5.7e-05 |        -0.298438 |        0.272727 |      0.941475 |          nan        |            nan      |
| T3_joint             | ladder      | True         |  0.019181 |         -0.00011 |        -0.576986 |        0.181818 |      0.947138 |            0.984918 |              0      |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 394 | 0.0186 |            0.0413 |
| A_mills_placebo      |         1 | 725 | 0.0187 |           -0.1829 |
| A_mills_placebo      |         2 | 855 | 0.019  |           -0.0565 |
| A_propensity_placebo |         0 | 394 | 0.0186 |            0.1681 |
| A_propensity_placebo |         1 | 725 | 0.0187 |            0.2355 |
| A_propensity_placebo |         2 | 855 | 0.019  |            0.0089 |
| A_uniform_weight     |         0 | 394 | 0.0186 |            0      |
| A_uniform_weight     |         1 | 725 | 0.0187 |            0      |
| A_uniform_weight     |         2 | 855 | 0.019  |            0      |
| T0_shipped           |         0 | 394 | 0.0186 |            0      |
| T0_shipped           |         1 | 725 | 0.0187 |            0      |
| T0_shipped           |         2 | 855 | 0.019  |            0      |
| T1_ipw               |         0 | 394 | 0.0187 |           -0.2795 |
| T1_ipw               |         1 | 725 | 0.0187 |           -0.0655 |
| T1_ipw               |         2 | 855 | 0.019  |           -0.0025 |
| T1b_ipw_odds         |         0 | 394 | 0.0187 |           -0.3731 |
| T1b_ipw_odds         |         1 | 725 | 0.0187 |           -0.1335 |
| T1b_ipw_odds         |         2 | 855 | 0.019  |           -0.0563 |
| T2_heckman           |         0 | 394 | 0.0187 |           -0.4868 |
| T2_heckman           |         1 | 725 | 0.0187 |           -0.2266 |
| T2_heckman           |         2 | 855 | 0.019  |           -0.2576 |
| T3_joint             |         0 | 394 | 0.0189 |           -1.355  |
| T3_joint             |         1 | 725 | 0.0188 |           -0.4205 |
| T3_joint             |         2 | 855 | 0.019  |           -0.329  |
| V_ipw_clip_tight     |         0 | 394 | 0.0187 |           -0.2795 |
| V_ipw_clip_tight     |         1 | 725 | 0.0187 |           -0.0655 |
| V_ipw_clip_tight     |         2 | 855 | 0.019  |           -0.0025 |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": -3.892754592851183e-05,
    "challenger_fold_wins": 8,
    "n_folds": 11,
    "p_challenger_better": 0.11706563055592925,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": -3.7572340052999884e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.15232590745102453,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.0190448409322353,
  "ipw_mae": 0.019083768478163815,
  "mills_placebo_mae": 0.019090444643055957,
  "heckman_mae": 0.019128016983108957,
  "concentration": {
    "T1_ipw": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.2795,
      "high_propensity_lift_pct": -0.0025,
      "gradient_high_minus_low_pct": 0.277,
      "mid_propensity_lift_pct": -0.0655
    },
    "T1b_ipw_odds": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.3731,
      "high_propensity_lift_pct": -0.0563,
      "gradient_high_minus_low_pct": 0.3168,
      "mid_propensity_lift_pct": -0.1335
    },
    "T2_heckman": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.4868,
      "high_propensity_lift_pct": -0.2576,
      "gradient_high_minus_low_pct": 0.2292,
      "mid_propensity_lift_pct": -0.2266
    },
    "T3_joint": {
      "verdict": "anti",
      "low_propensity_lift_pct": -1.355,
      "high_propensity_lift_pct": -0.329,
      "gradient_high_minus_low_pct": 1.026,
      "mid_propensity_lift_pct": -0.4205
    },
    "V_ipw_clip_tight": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.2795,
      "high_propensity_lift_pct": -0.0025,
      "gradient_high_minus_low_pct": 0.277,
      "mid_propensity_lift_pct": -0.0655
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.891
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9164
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9169
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9277
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9394
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9451
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9546
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9567

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.1,
  "os_gap_pct": 0.0165,
  "os_gap_p90_pct": 0.1801,
  "contender_spread_pct": 0.066,
  "full_spread_pct": 0.577,
  "flips": [
    {
      "config": "T0_shipped",
      "IS_half_wins": 325,
      "share": 0.703,
      "mean_oos_mae": 0.01907,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_clip_tight",
      "IS_half_wins": 108,
      "share": 0.234,
      "mean_oos_mae": 0.01908,
      "pct_vs_best": 0.066
    },
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 15,
      "share": 0.032,
      "mean_oos_mae": 0.0191,
      "pct_vs_best": 0.128
    },
    {
      "config": "T1_ipw",
      "IS_half_wins": 12,
      "share": 0.026,
      "mean_oos_mae": 0.01908,
      "pct_vs_best": 0.066
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 2,
      "share": 0.004,
      "mean_oos_mae": 0.01913,
      "pct_vs_best": 0.298
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.02857142857142857,
    "os_gap_pct": 0.0,
    "os_gap_p90_pct": 0.2892,
    "contender_spread_pct": 0.138,
    "full_spread_pct": 0.716,
    "flips": [
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 392,
        "share": 0.848,
        "mean_oos_mae": 0.01904,
        "pct_vs_best": 0.0
      },
      {
        "config": "V_ipw_clip_tight",
        "IS_half_wins": 40,
        "share": 0.087,
        "mean_oos_mae": 0.01908,
        "pct_vs_best": 0.204
      },
      {
        "config": "T0_shipped",
        "IS_half_wins": 24,
        "share": 0.052,
        "mean_oos_mae": 0.01907,
        "pct_vs_best": 0.138
      },
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 5,
        "share": 0.011,
        "mean_oos_mae": 0.0191,
        "pct_vs_best": 0.266
      },
      {
        "config": "A_mills_placebo",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.01909,
        "pct_vs_best": 0.239
      }
    ]
  }
}
```

### Notes

- no S2 arm beat the shipped configuration in ≥60% of held-out cohorts

---

## `hr_rate` (baseline = `S5_full_labelweight`, prior scale 4.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T1b_ipw_odds         | ladder      | True         |  0.009759 |          1.6e-05 |         0.159266 |        0.818182 |      0.042289 |            0.973327 |              0      |
| T1_ipw               | ladder      | True         |  0.009763 |          1.2e-05 |         0.120871 |        0.818182 |      0.024707 |            0.984918 |              0      |
| V_ipw_clip_tight     | sensitivity | True         |  0.009763 |          1.2e-05 |         0.120871 |        0.818182 |      0.024707 |            0.985736 |             13.0909 |
| T3_joint             | ladder      | True         |  0.00977  |          4e-06   |         0.043505 |        0.545455 |      0.387985 |            0.984918 |              0      |
| T0_shipped           | ladder      | True         |  0.009774 |          0       |         0        |        0        |    nan        |          nan        |            nan      |
| A_uniform_weight     | anchor      | False        |  0.009774 |          0       |         0        |        0        |    nan        |          nan        |            nan      |
| A_propensity_placebo | anchor      | False        |  0.009774 |         -0       |        -0.000567 |        0.545455 |      0.502961 |            0.984918 |              0      |
| A_mills_placebo      | anchor      | False        |  0.009779 |         -5e-06   |        -0.05052  |        0.454545 |      0.75198  |          nan        |            nan      |
| T2_heckman           | ladder      | True         |  0.009788 |         -1.3e-05 |        -0.135724 |        0.181818 |      0.817057 |          nan        |            nan      |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 394 | 0.0097 |           -0.0602 |
| A_mills_placebo      |         1 | 725 | 0.01   |            0.092  |
| A_mills_placebo      |         2 | 855 | 0.0094 |           -0.1851 |
| A_propensity_placebo |         0 | 394 | 0.0097 |            0.0951 |
| A_propensity_placebo |         1 | 725 | 0.01   |           -0.2377 |
| A_propensity_placebo |         2 | 855 | 0.0094 |            0.0645 |
| A_uniform_weight     |         0 | 394 | 0.0097 |            0      |
| A_uniform_weight     |         1 | 725 | 0.01   |            0      |
| A_uniform_weight     |         2 | 855 | 0.0094 |            0      |
| T0_shipped           |         0 | 394 | 0.0097 |            0      |
| T0_shipped           |         1 | 725 | 0.01   |            0      |
| T0_shipped           |         2 | 855 | 0.0094 |            0      |
| T1_ipw               |         0 | 394 | 0.0097 |            0.3571 |
| T1_ipw               |         1 | 725 | 0.01   |            0.0013 |
| T1_ipw               |         2 | 855 | 0.0094 |            0.082  |
| T1b_ipw_odds         |         0 | 394 | 0.0097 |            0.4946 |
| T1b_ipw_odds         |         1 | 725 | 0.01   |           -0.0337 |
| T1b_ipw_odds         |         2 | 855 | 0.0094 |            0.1265 |
| T2_heckman           |         0 | 394 | 0.0098 |           -0.6308 |
| T2_heckman           |         1 | 725 | 0.01   |            0.0279 |
| T2_heckman           |         2 | 855 | 0.0094 |           -0.0751 |
| T3_joint             |         0 | 394 | 0.0097 |            0.06   |
| T3_joint             |         1 | 725 | 0.01   |            0.0287 |
| T3_joint             |         2 | 855 | 0.0094 |           -0.0152 |
| V_ipw_clip_tight     |         0 | 394 | 0.0097 |            0.3571 |
| V_ipw_clip_tight     |         1 | 725 | 0.01   |            0.0013 |
| V_ipw_clip_tight     |         2 | 855 | 0.0094 |            0.082  |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 1.1869786958301922e-05,
    "challenger_fold_wins": 4,
    "n_folds": 11,
    "p_challenger_better": 0.9064766111190348,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": -8.328171889643299e-06,
    "challenger_fold_wins": 6,
    "n_folds": 11,
    "p_challenger_better": 0.30524826480708445,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.009774422804400816,
  "ipw_mae": 0.009762553017442516,
  "mills_placebo_mae": 0.009779305373993756,
  "heckman_mae": 0.0097876335458834,
  "concentration": {
    "T1_ipw": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.3571,
      "high_propensity_lift_pct": 0.082,
      "gradient_high_minus_low_pct": -0.2751,
      "mid_propensity_lift_pct": 0.0013
    },
    "T1b_ipw_odds": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.4946,
      "high_propensity_lift_pct": 0.1265,
      "gradient_high_minus_low_pct": -0.3681,
      "mid_propensity_lift_pct": -0.0337
    },
    "T2_heckman": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.6308,
      "high_propensity_lift_pct": -0.0751,
      "gradient_high_minus_low_pct": 0.5558,
      "mid_propensity_lift_pct": 0.0279
    },
    "T3_joint": {
      "verdict": "flat",
      "low_propensity_lift_pct": 0.06,
      "high_propensity_lift_pct": -0.0152,
      "gradient_high_minus_low_pct": -0.0752,
      "mid_propensity_lift_pct": 0.0287
    },
    "V_ipw_clip_tight": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.3571,
      "high_propensity_lift_pct": 0.082,
      "gradient_high_minus_low_pct": -0.2751,
      "mid_propensity_lift_pct": 0.0013
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.891
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9164
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9169
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9277
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9394
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9451
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9546
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9567

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.17142857142857143,
  "os_gap_pct": 0.0,
  "os_gap_p90_pct": 0.259,
  "contender_spread_pct": 0.038,
  "full_spread_pct": 0.295,
  "flips": [
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 310,
      "share": 0.671,
      "mean_oos_mae": 0.00976,
      "pct_vs_best": 0.0
    },
    {
      "config": "T3_joint",
      "IS_half_wins": 85,
      "share": 0.184,
      "mean_oos_mae": 0.00977,
      "pct_vs_best": 0.116
    },
    {
      "config": "T1_ipw",
      "IS_half_wins": 61,
      "share": 0.132,
      "mean_oos_mae": 0.00976,
      "pct_vs_best": 0.038
    },
    {
      "config": "T0_shipped",
      "IS_half_wins": 6,
      "share": 0.013,
      "mean_oos_mae": 0.00977,
      "pct_vs_best": 0.16
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.17142857142857143,
    "os_gap_pct": 0.0049,
    "os_gap_p90_pct": 0.3166,
    "contender_spread_pct": 0.038,
    "full_spread_pct": 0.295,
    "flips": [
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 290,
        "share": 0.628,
        "mean_oos_mae": 0.00976,
        "pct_vs_best": 0.0
      },
      {
        "config": "T3_joint",
        "IS_half_wins": 85,
        "share": 0.184,
        "mean_oos_mae": 0.00977,
        "pct_vs_best": 0.116
      },
      {
        "config": "T1_ipw",
        "IS_half_wins": 45,
        "share": 0.097,
        "mean_oos_mae": 0.00976,
        "pct_vs_best": 0.038
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 37,
        "share": 0.08,
        "mean_oos_mae": 0.00977,
        "pct_vs_best": 0.16
      },
      {
        "config": "T0_shipped",
        "IS_half_wins": 4,
        "share": 0.009,
        "mean_oos_mae": 0.00977,
        "pct_vs_best": 0.16
      },
      {
        "config": "A_mills_placebo",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.00978,
        "pct_vs_best": 0.21
      }
    ]
  }
}
```

---

## `gb_pct` (baseline = `S0_baseline`, prior scale 2.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T1_ipw               | ladder      | True         |  0.047831 |          4e-06   |         0.008277 |        0.545455 |      0.470298 |            0.984918 |              0      |
| V_ipw_clip_tight     | sensitivity | True         |  0.047831 |          4e-06   |         0.008277 |        0.545455 |      0.470298 |            0.985736 |             13.0909 |
| T1b_ipw_odds         | ladder      | True         |  0.047833 |          2e-06   |         0.005003 |        0.545455 |      0.485676 |            0.973327 |              0      |
| T0_shipped           | ladder      | True         |  0.047835 |          0       |         0        |        0        |    nan        |          nan        |            nan      |
| A_uniform_weight     | anchor      | False        |  0.047835 |          0       |         0        |        0        |    nan        |          nan        |            nan      |
| T3_joint             | ladder      | True         |  0.047869 |         -3.4e-05 |        -0.071992 |        0.454545 |      0.643004 |            0.984918 |              0      |
| A_propensity_placebo | anchor      | False        |  0.047878 |         -4.3e-05 |        -0.08985  |        0.454545 |      0.86406  |            0.984918 |              0      |
| T2_heckman           | ladder      | True         |  0.047882 |         -4.7e-05 |        -0.098757 |        0.545455 |      0.765297 |          nan        |            nan      |
| A_mills_placebo      | anchor      | False        |  0.047923 |         -8.7e-05 |        -0.182908 |        0.272727 |      0.973028 |          nan        |            nan      |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 394 | 0.0486 |           -0.1599 |
| A_mills_placebo      |         1 | 725 | 0.0475 |            0.0423 |
| A_mills_placebo      |         2 | 855 | 0.0497 |           -0.3469 |
| A_propensity_placebo |         0 | 394 | 0.0486 |           -0.2531 |
| A_propensity_placebo |         1 | 725 | 0.0476 |           -0.2182 |
| A_propensity_placebo |         2 | 855 | 0.0495 |            0.0802 |
| A_uniform_weight     |         0 | 394 | 0.0485 |            0      |
| A_uniform_weight     |         1 | 725 | 0.0475 |            0      |
| A_uniform_weight     |         2 | 855 | 0.0495 |            0      |
| T0_shipped           |         0 | 394 | 0.0485 |            0      |
| T0_shipped           |         1 | 725 | 0.0475 |            0      |
| T0_shipped           |         2 | 855 | 0.0495 |            0      |
| T1_ipw               |         0 | 394 | 0.0485 |            0.0229 |
| T1_ipw               |         1 | 725 | 0.0475 |            0.0444 |
| T1_ipw               |         2 | 855 | 0.0495 |            0.0368 |
| T1b_ipw_odds         |         0 | 394 | 0.0485 |            0.0356 |
| T1b_ipw_odds         |         1 | 725 | 0.0474 |            0.0664 |
| T1b_ipw_odds         |         2 | 855 | 0.0495 |            0.0367 |
| T2_heckman           |         0 | 394 | 0.0485 |            0.0384 |
| T2_heckman           |         1 | 725 | 0.0475 |            0.0407 |
| T2_heckman           |         2 | 855 | 0.0497 |           -0.2984 |
| T3_joint             |         0 | 394 | 0.0484 |            0.1365 |
| T3_joint             |         1 | 725 | 0.0475 |            0.0197 |
| T3_joint             |         2 | 855 | 0.0496 |           -0.1939 |
| V_ipw_clip_tight     |         0 | 394 | 0.0485 |            0.0229 |
| V_ipw_clip_tight     |         1 | 725 | 0.0475 |            0.0444 |
| V_ipw_clip_tight     |         2 | 855 | 0.0495 |            0.0368 |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 4.6938925482377756e-05,
    "challenger_fold_wins": 4,
    "n_folds": 11,
    "p_challenger_better": 0.7807136647544187,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": 4.025386353487574e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.6645910299477875,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.04787803536269844,
  "ipw_mae": 0.047831096437216065,
  "mills_placebo_mae": 0.047922550021312314,
  "heckman_mae": 0.047882296157777435,
  "concentration": {
    "T1_ipw": {
      "verdict": "flat",
      "low_propensity_lift_pct": 0.0229,
      "high_propensity_lift_pct": 0.0368,
      "gradient_high_minus_low_pct": 0.0139,
      "mid_propensity_lift_pct": 0.0444
    },
    "T1b_ipw_odds": {
      "verdict": "flat",
      "low_propensity_lift_pct": 0.0356,
      "high_propensity_lift_pct": 0.0367,
      "gradient_high_minus_low_pct": 0.0011,
      "mid_propensity_lift_pct": 0.0664
    },
    "T2_heckman": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.0384,
      "high_propensity_lift_pct": -0.2984,
      "gradient_high_minus_low_pct": -0.3368,
      "mid_propensity_lift_pct": 0.0407
    },
    "T3_joint": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.1365,
      "high_propensity_lift_pct": -0.1939,
      "gradient_high_minus_low_pct": -0.3304,
      "mid_propensity_lift_pct": 0.0197
    },
    "V_ipw_clip_tight": {
      "verdict": "flat",
      "low_propensity_lift_pct": 0.0229,
      "high_propensity_lift_pct": 0.0368,
      "gradient_high_minus_low_pct": 0.0139,
      "mid_propensity_lift_pct": 0.0444
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.891
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9164
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9169
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9277
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9394
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9451
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9546
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9567

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.9714285714285714,
  "os_gap_pct": 0.1575,
  "os_gap_p90_pct": 0.3481,
  "contender_spread_pct": 0.003,
  "full_spread_pct": 0.107,
  "flips": [
    {
      "config": "T0_shipped",
      "IS_half_wins": 168,
      "share": 0.364,
      "mean_oos_mae": 0.04784,
      "pct_vs_best": 0.008
    },
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 133,
      "share": 0.288,
      "mean_oos_mae": 0.04783,
      "pct_vs_best": 0.003
    },
    {
      "config": "T3_joint",
      "IS_half_wins": 87,
      "share": 0.188,
      "mean_oos_mae": 0.04787,
      "pct_vs_best": 0.08
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 41,
      "share": 0.089,
      "mean_oos_mae": 0.04788,
      "pct_vs_best": 0.107
    },
    {
      "config": "T1_ipw",
      "IS_half_wins": 32,
      "share": 0.069,
      "mean_oos_mae": 0.04783,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_clip_tight",
      "IS_half_wins": 1,
      "share": 0.002,
      "mean_oos_mae": 0.04783,
      "pct_vs_best": 0.0
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.9142857142857143,
    "os_gap_pct": 0.1794,
    "os_gap_p90_pct": 0.3734,
    "contender_spread_pct": 0.003,
    "full_spread_pct": 0.191,
    "flips": [
      {
        "config": "T0_shipped",
        "IS_half_wins": 140,
        "share": 0.303,
        "mean_oos_mae": 0.04784,
        "pct_vs_best": 0.008
      },
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 130,
        "share": 0.281,
        "mean_oos_mae": 0.04783,
        "pct_vs_best": 0.003
      },
      {
        "config": "T3_joint",
        "IS_half_wins": 87,
        "share": 0.188,
        "mean_oos_mae": 0.04787,
        "pct_vs_best": 0.08
      },
      {
        "config": "T2_heckman",
        "IS_half_wins": 41,
        "share": 0.089,
        "mean_oos_mae": 0.04788,
        "pct_vs_best": 0.107
      },
      {
        "config": "T1_ipw",
        "IS_half_wins": 30,
        "share": 0.065,
        "mean_oos_mae": 0.04783,
        "pct_vs_best": 0.0
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 24,
        "share": 0.052,
        "mean_oos_mae": 0.04788,
        "pct_vs_best": 0.098
      },
      {
        "config": "A_mills_placebo",
        "IS_half_wins": 9,
        "share": 0.019,
        "mean_oos_mae": 0.04792,
        "pct_vs_best": 0.191
      },
      {
        "config": "V_ipw_clip_tight",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.04783,
        "pct_vs_best": 0.0
      }
    ]
  }
}
```

### Notes

- no S2 arm beat the shipped configuration in ≥60% of held-out cohorts

---

## `xwoba_against` (baseline = `S0_baseline`, prior scale 2.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T3_joint             | ladder      | True         |  0.025773 |         0.000468 |         1.78183  |            1    |      0.003741 |            0.966    |                   0 |
| T2_heckman           | ladder      | True         |  0.025779 |         0.000462 |         1.75984  |            1    |      0.000773 |          nan        |                 nan |
| T1b_ipw_odds         | ladder      | True         |  0.026219 |         2.1e-05  |         0.081581 |            0.5  |      0.406248 |            0.939675 |                   0 |
| T1_ipw               | ladder      | True         |  0.026226 |         1.4e-05  |         0.053033 |            0.5  |      0.415437 |            0.966    |                   0 |
| V_ipw_clip_tight     | sensitivity | True         |  0.026226 |         1.4e-05  |         0.053033 |            0.5  |      0.415437 |            0.966    |                   0 |
| T0_shipped           | ladder      | True         |  0.02624  |         0        |         0        |            0    |    nan        |          nan        |                 nan |
| A_uniform_weight     | anchor      | False        |  0.02624  |         0        |         0        |            0    |    nan        |          nan        |                 nan |
| A_propensity_placebo | anchor      | False        |  0.026276 |        -3.5e-05  |        -0.134188 |            0.25 |      0.672231 |            0.966    |                   0 |
| A_mills_placebo      | anchor      | False        |  0.026482 |        -0.000241 |        -0.919322 |            0    |      0.975016 |          nan        |                 nan |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 |  58 | 0.0253 |           -2.7849 |
| A_mills_placebo      |         1 |  60 | 0.0238 |            0.0564 |
| A_mills_placebo      |         2 |  33 | 0.0251 |            1.0918 |
| A_propensity_placebo |         0 |  58 | 0.0246 |            0.1263 |
| A_propensity_placebo |         1 |  60 | 0.0238 |           -0.1186 |
| A_propensity_placebo |         2 |  33 | 0.0256 |           -0.9339 |
| A_uniform_weight     |         0 |  58 | 0.0246 |            0      |
| A_uniform_weight     |         1 |  60 | 0.0238 |            0      |
| A_uniform_weight     |         2 |  33 | 0.0254 |            0      |
| T0_shipped           |         0 |  58 | 0.0246 |            0      |
| T0_shipped           |         1 |  60 | 0.0238 |            0      |
| T0_shipped           |         2 |  33 | 0.0254 |            0      |
| T1_ipw               |         0 |  58 | 0.0246 |            0.181  |
| T1_ipw               |         1 |  60 | 0.0238 |           -0.1793 |
| T1_ipw               |         2 |  33 | 0.0255 |           -0.4029 |
| T1b_ipw_odds         |         0 |  58 | 0.0246 |            0.2516 |
| T1b_ipw_odds         |         1 |  60 | 0.0238 |           -0.2864 |
| T1b_ipw_odds         |         2 |  33 | 0.0255 |           -0.454  |
| T2_heckman           |         0 |  58 | 0.0246 |            0.2676 |
| T2_heckman           |         1 |  60 | 0.0231 |            2.875  |
| T2_heckman           |         2 |  33 | 0.0246 |            2.9467 |
| T3_joint             |         0 |  58 | 0.0245 |            0.5373 |
| T3_joint             |         1 |  60 | 0.0232 |            2.5478 |
| T3_joint             |         2 |  33 | 0.0247 |            2.6426 |
| V_ipw_clip_tight     |         0 |  58 | 0.0246 |            0.181  |
| V_ipw_clip_tight     |         1 |  60 | 0.0238 |           -0.1793 |
| V_ipw_clip_tight     |         2 |  33 | 0.0255 |           -0.4029 |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 4.912740447984582e-05,
    "challenger_fold_wins": 1,
    "n_folds": 4,
    "p_challenger_better": 0.8159219592801047,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": 0.0007030215718020786,
    "challenger_fold_wins": 0,
    "n_folds": 4,
    "p_challenger_better": 0.9968808963023703,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.02627558019461758,
  "ipw_mae": 0.02622645279013773,
  "mills_placebo_mae": 0.026481602174577082,
  "heckman_mae": 0.025778580602775006,
  "concentration": {
    "T1_ipw": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.181,
      "high_propensity_lift_pct": -0.4029,
      "gradient_high_minus_low_pct": -0.5839,
      "mid_propensity_lift_pct": -0.1793
    },
    "T1b_ipw_odds": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.2516,
      "high_propensity_lift_pct": -0.454,
      "gradient_high_minus_low_pct": -0.7056,
      "mid_propensity_lift_pct": -0.2864
    },
    "T2_heckman": {
      "verdict": "anti",
      "low_propensity_lift_pct": 0.2676,
      "high_propensity_lift_pct": 2.9467,
      "gradient_high_minus_low_pct": 2.6792,
      "mid_propensity_lift_pct": 2.875
    },
    "T3_joint": {
      "verdict": "anti",
      "low_propensity_lift_pct": 0.5373,
      "high_propensity_lift_pct": 2.6426,
      "gradient_high_minus_low_pct": 2.1054,
      "mid_propensity_lift_pct": 2.5478
    },
    "V_ipw_clip_tight": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.181,
      "high_propensity_lift_pct": -0.4029,
      "gradient_high_minus_low_pct": -0.5839,
      "mid_propensity_lift_pct": -0.1793
    }
  }
}
```

### Censoring guard (per fold)

- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9394
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9451
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9546
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9567

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 4,
  "pbo": 0.0,
  "os_gap_pct": 0.0773,
  "os_gap_p90_pct": 0.271,
  "contender_spread_pct": 1.731,
  "full_spread_pct": 1.814,
  "flips": [
    {
      "config": "T3_joint",
      "IS_half_wins": 4,
      "share": 0.667,
      "mean_oos_mae": 0.02577,
      "pct_vs_best": 0.0
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 2,
      "share": 0.333,
      "mean_oos_mae": 0.02578,
      "pct_vs_best": 0.022
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 4,
    "pbo": 0.0,
    "os_gap_pct": 0.0773,
    "os_gap_p90_pct": 0.271,
    "contender_spread_pct": 1.731,
    "full_spread_pct": 2.75,
    "flips": [
      {
        "config": "T3_joint",
        "IS_half_wins": 4,
        "share": 0.667,
        "mean_oos_mae": 0.02577,
        "pct_vs_best": 0.0
      },
      {
        "config": "T2_heckman",
        "IS_half_wins": 2,
        "share": 0.333,
        "mean_oos_mae": 0.02578,
        "pct_vs_best": 0.022
      }
    ]
  }
}
```

### Notes

- ⛔ INELIGIBLE (anti-concentrated) — T3_joint lifts +0.537% at the LOW-propensity end vs +2.643% at the HIGH end; T2_heckman lifts +0.268% at the LOW-propensity end vs +2.947% at the HIGH end. A selection correction must help where the served population lives; prospects are low-propensity by construction. A benefit that GROWS with propensity is the fit reallocating attention toward the players it already handled best — the opposite of the stated mechanism — so these arms are removed from the field before the pick, not vetoed after it.
- every arm that cleared the fold gate was anti-concentrated ⇒ the shipped configuration stands