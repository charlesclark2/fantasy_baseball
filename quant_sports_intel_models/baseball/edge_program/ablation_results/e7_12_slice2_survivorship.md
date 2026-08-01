# E7.12 slice 2 — promotion-selection (survivorship) correction (batters)

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

| metric   | shipped_baseline   | verdict   | winner       |   pct_lift |   fold_win_rate | BH-FDR@0.10   |   PBO(eligible) |
|:---------|:-------------------|:----------|:-------------|-----------:|----------------:|:--------------|----------------:|
| woba     | S2_level_env       | DROP      | T0_shipped   |       0    |            0    |               |           0.7   |
| k_pct    | S4_park_env_rel0.5 | ADD       | T1b_ipw_odds |       0.19 |            0.82 | True          |           0.286 |
| bb_pct   | S4_park_env_rel2.0 | DROP      | T0_shipped   |       0    |            0    |               |           0.257 |
| iso      | S4_park_env_rel2.0 | DROP      | T0_shipped   |       0    |            0    |               |           0.386 |

---

## `woba` (baseline = `S2_level_env`, prior scale 4.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T0_shipped           | ladder      | True         |  0.028791 |         0        |         0        |        0        |    nan        |          nan        |          nan        |
| A_uniform_weight     | anchor      | False        |  0.028791 |         0        |         0        |        0        |    nan        |          nan        |          nan        |
| T1_ipw               | ladder      | True         |  0.028811 |        -2.1e-05  |        -0.07278  |        0.363636 |      0.712411 |            0.971618 |            0        |
| V_ipw_clip_tight     | sensitivity | True         |  0.028811 |        -2.1e-05  |        -0.07278  |        0.363636 |      0.712411 |            0.971673 |            0.818182 |
| T1b_ipw_odds         | ladder      | True         |  0.028825 |        -3.5e-05  |        -0.121225 |        0.363636 |      0.745904 |            0.946855 |            0        |
| A_mills_placebo      | anchor      | False        |  0.028837 |        -4.7e-05  |        -0.162969 |        0.363636 |      0.934506 |          nan        |          nan        |
| A_propensity_placebo | anchor      | False        |  0.028839 |        -4.9e-05  |        -0.168886 |        0.545455 |      0.905122 |            0.971618 |            0        |
| T2_heckman           | ladder      | True         |  0.028888 |        -9.8e-05  |        -0.338751 |        0.363636 |      0.740727 |          nan        |          nan        |
| T3_joint             | ladder      | True         |  0.028969 |        -0.000178 |        -0.61984  |        0.363636 |      0.769748 |            0.971618 |            0        |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 162 | 0.0278 |           -0.7737 |
| A_mills_placebo      |         1 | 570 | 0.0279 |           -0.2275 |
| A_mills_placebo      |         2 | 962 | 0.0293 |            0.0487 |
| A_propensity_placebo |         0 | 162 | 0.0277 |           -0.391  |
| A_propensity_placebo |         1 | 570 | 0.0279 |           -0.2128 |
| A_propensity_placebo |         2 | 962 | 0.0294 |           -0.0623 |
| A_uniform_weight     |         0 | 162 | 0.0276 |            0      |
| A_uniform_weight     |         1 | 570 | 0.0278 |            0      |
| A_uniform_weight     |         2 | 962 | 0.0293 |            0      |
| T0_shipped           |         0 | 162 | 0.0276 |            0      |
| T0_shipped           |         1 | 570 | 0.0278 |            0      |
| T0_shipped           |         2 | 962 | 0.0293 |            0      |
| T1_ipw               |         0 | 162 | 0.0277 |           -0.4201 |
| T1_ipw               |         1 | 570 | 0.028  |           -0.5479 |
| T1_ipw               |         2 | 962 | 0.0293 |            0.2941 |
| T1b_ipw_odds         |         0 | 162 | 0.0278 |           -0.6461 |
| T1b_ipw_odds         |         1 | 570 | 0.028  |           -0.7654 |
| T1b_ipw_odds         |         2 | 962 | 0.0292 |            0.3905 |
| T2_heckman           |         0 | 162 | 0.028  |           -1.5613 |
| T2_heckman           |         1 | 570 | 0.0279 |           -0.1902 |
| T2_heckman           |         2 | 962 | 0.0293 |            0.244  |
| T3_joint             |         0 | 162 | 0.0284 |           -2.8844 |
| T3_joint             |         1 | 570 | 0.0281 |           -0.9823 |
| T3_joint             |         2 | 962 | 0.0292 |            0.6423 |
| V_ipw_clip_tight     |         0 | 162 | 0.0277 |           -0.4201 |
| V_ipw_clip_tight     |         1 | 570 | 0.028  |           -0.5479 |
| V_ipw_clip_tight     |         2 | 962 | 0.0293 |            0.2941 |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 2.7669232066510315e-05,
    "challenger_fold_wins": 3,
    "n_folds": 11,
    "p_challenger_better": 0.7232314664747661,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": -5.0608494627779985e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.3486674934832274,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.028839139276048496,
  "ipw_mae": 0.028811470043981987,
  "mills_placebo_mae": 0.028837435947046675,
  "heckman_mae": 0.028888044441674456,
  "concentration": {
    "T1_ipw": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.4201,
      "high_propensity_lift_pct": 0.2941,
      "gradient_high_minus_low_pct": 0.7143,
      "mid_propensity_lift_pct": -0.5479
    },
    "T1b_ipw_odds": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.6461,
      "high_propensity_lift_pct": 0.3905,
      "gradient_high_minus_low_pct": 1.0365,
      "mid_propensity_lift_pct": -0.7654
    },
    "T2_heckman": {
      "verdict": "anti",
      "low_propensity_lift_pct": -1.5613,
      "high_propensity_lift_pct": 0.244,
      "gradient_high_minus_low_pct": 1.8053,
      "mid_propensity_lift_pct": -0.1902
    },
    "T3_joint": {
      "verdict": "anti",
      "low_propensity_lift_pct": -2.8844,
      "high_propensity_lift_pct": 0.6423,
      "gradient_high_minus_low_pct": 3.5267,
      "mid_propensity_lift_pct": -0.9823
    },
    "V_ipw_clip_tight": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.4201,
      "high_propensity_lift_pct": 0.2941,
      "gradient_high_minus_low_pct": 0.7143,
      "mid_propensity_lift_pct": -0.5479
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.8982
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9076
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.899
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9027
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9151
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9192
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9297
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.932

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.7,
  "os_gap_pct": 0.3706,
  "os_gap_p90_pct": 1.5102,
  "contender_spread_pct": 0.073,
  "full_spread_pct": 0.62,
  "flips": [
    {
      "config": "T0_shipped",
      "IS_half_wins": 228,
      "share": 0.494,
      "mean_oos_mae": 0.02879,
      "pct_vs_best": 0.0
    },
    {
      "config": "T3_joint",
      "IS_half_wins": 104,
      "share": 0.225,
      "mean_oos_mae": 0.02897,
      "pct_vs_best": 0.62
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 56,
      "share": 0.121,
      "mean_oos_mae": 0.02889,
      "pct_vs_best": 0.339
    },
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 45,
      "share": 0.097,
      "mean_oos_mae": 0.02883,
      "pct_vs_best": 0.121
    },
    {
      "config": "T1_ipw",
      "IS_half_wins": 29,
      "share": 0.063,
      "mean_oos_mae": 0.02881,
      "pct_vs_best": 0.073
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.6714285714285714,
    "os_gap_pct": 0.3857,
    "os_gap_p90_pct": 1.5102,
    "contender_spread_pct": 0.073,
    "full_spread_pct": 0.62,
    "flips": [
      {
        "config": "T0_shipped",
        "IS_half_wins": 206,
        "share": 0.446,
        "mean_oos_mae": 0.02879,
        "pct_vs_best": 0.0
      },
      {
        "config": "T3_joint",
        "IS_half_wins": 102,
        "share": 0.221,
        "mean_oos_mae": 0.02897,
        "pct_vs_best": 0.62
      },
      {
        "config": "T2_heckman",
        "IS_half_wins": 54,
        "share": 0.117,
        "mean_oos_mae": 0.02889,
        "pct_vs_best": 0.339
      },
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 45,
        "share": 0.097,
        "mean_oos_mae": 0.02883,
        "pct_vs_best": 0.121
      },
      {
        "config": "T1_ipw",
        "IS_half_wins": 28,
        "share": 0.061,
        "mean_oos_mae": 0.02881,
        "pct_vs_best": 0.073
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 27,
        "share": 0.058,
        "mean_oos_mae": 0.02884,
        "pct_vs_best": 0.169
      }
    ]
  }
}
```

### Notes

- no S2 arm beat the shipped configuration in ≥60% of held-out cohorts

---

## `k_pct` (baseline = `S4_park_env_rel0.5`, prior scale 2.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T3_joint             | ladder      | True         |  0.038188 |         0.000246 |         0.641306 |        0.818182 |      0.098739 |            0.971618 |            0        |
| T2_heckman           | ladder      | True         |  0.038202 |         0.000233 |         0.605633 |        0.818182 |      0.120089 |          nan        |          nan        |
| A_mills_placebo      | anchor      | False        |  0.038344 |         9.1e-05  |         0.236742 |        0.727273 |      0.120852 |          nan        |          nan        |
| T1b_ipw_odds         | ladder      | True         |  0.038361 |         7.3e-05  |         0.19042  |        0.818182 |      0.054156 |            0.946855 |            0        |
| T1_ipw               | ladder      | True         |  0.03838  |         5.4e-05  |         0.140919 |        0.727273 |      0.060453 |            0.971618 |            0        |
| V_ipw_clip_tight     | sensitivity | True         |  0.03838  |         5.4e-05  |         0.140919 |        0.727273 |      0.060453 |            0.971673 |            0.818182 |
| T0_shipped           | ladder      | True         |  0.038435 |         0        |         0        |        0        |    nan        |          nan        |          nan        |
| A_uniform_weight     | anchor      | False        |  0.038435 |         0        |         0        |        0        |    nan        |          nan        |          nan        |
| A_propensity_placebo | anchor      | False        |  0.038479 |        -4.5e-05  |        -0.116759 |        0.545455 |      0.648604 |            0.971618 |            0        |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 162 | 0.0344 |           -0.2153 |
| A_mills_placebo      |         1 | 570 | 0.0376 |            0.2325 |
| A_mills_placebo      |         2 | 962 | 0.0388 |            0.2039 |
| A_propensity_placebo |         0 | 162 | 0.0345 |           -0.6129 |
| A_propensity_placebo |         1 | 570 | 0.0378 |           -0.1338 |
| A_propensity_placebo |         2 | 962 | 0.0388 |            0.2207 |
| A_uniform_weight     |         0 | 162 | 0.0343 |            0      |
| A_uniform_weight     |         1 | 570 | 0.0377 |            0      |
| A_uniform_weight     |         2 | 962 | 0.0389 |            0      |
| T0_shipped           |         0 | 162 | 0.0343 |            0      |
| T0_shipped           |         1 | 570 | 0.0377 |            0      |
| T0_shipped           |         2 | 962 | 0.0389 |            0      |
| T1_ipw               |         0 | 162 | 0.0342 |            0.4098 |
| T1_ipw               |         1 | 570 | 0.0377 |            0.135  |
| T1_ipw               |         2 | 962 | 0.0389 |            0.042  |
| T1b_ipw_odds         |         0 | 162 | 0.0341 |            0.5395 |
| T1b_ipw_odds         |         1 | 570 | 0.0376 |            0.1786 |
| T1b_ipw_odds         |         2 | 962 | 0.0388 |            0.0664 |
| T2_heckman           |         0 | 162 | 0.0344 |           -0.167  |
| T2_heckman           |         1 | 570 | 0.0375 |            0.4587 |
| T2_heckman           |         2 | 962 | 0.0384 |            1.3065 |
| T3_joint             |         0 | 162 | 0.0343 |            0.1509 |
| T3_joint             |         1 | 570 | 0.0375 |            0.6462 |
| T3_joint             |         2 | 962 | 0.0384 |            1.1946 |
| V_ipw_clip_tight     |         0 | 162 | 0.0342 |            0.4098 |
| V_ipw_clip_tight     |         1 | 570 | 0.0377 |            0.135  |
| V_ipw_clip_tight     |         2 | 962 | 0.0389 |            0.042  |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 9.903739186146189e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.7643309274975087,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": 0.0001417817244493735,
    "challenger_fold_wins": 3,
    "n_folds": 11,
    "p_challenger_better": 0.763426485370085,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.03847945440743391,
  "ipw_mae": 0.038380417015572446,
  "mills_placebo_mae": 0.03834358773806485,
  "heckman_mae": 0.03820180601361548,
  "concentration": {
    "T1_ipw": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.4098,
      "high_propensity_lift_pct": 0.042,
      "gradient_high_minus_low_pct": -0.3678,
      "mid_propensity_lift_pct": 0.135
    },
    "T1b_ipw_odds": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.5395,
      "high_propensity_lift_pct": 0.0664,
      "gradient_high_minus_low_pct": -0.4731,
      "mid_propensity_lift_pct": 0.1786
    },
    "T2_heckman": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.167,
      "high_propensity_lift_pct": 1.3065,
      "gradient_high_minus_low_pct": 1.4735,
      "mid_propensity_lift_pct": 0.4587
    },
    "T3_joint": {
      "verdict": "anti",
      "low_propensity_lift_pct": 0.1509,
      "high_propensity_lift_pct": 1.1946,
      "gradient_high_minus_low_pct": 1.0437,
      "mid_propensity_lift_pct": 0.6462
    },
    "V_ipw_clip_tight": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.4098,
      "high_propensity_lift_pct": 0.042,
      "gradient_high_minus_low_pct": -0.3678,
      "mid_propensity_lift_pct": 0.135
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.8982
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9076
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.899
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9027
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9151
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9192
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9297
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.932

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.2857142857142857,
  "os_gap_pct": 0.0991,
  "os_gap_p90_pct": 1.1394,
  "contender_spread_pct": 0.454,
  "full_spread_pct": 0.645,
  "flips": [
    {
      "config": "T3_joint",
      "IS_half_wins": 214,
      "share": 0.463,
      "mean_oos_mae": 0.03819,
      "pct_vs_best": 0.0
    },
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 126,
      "share": 0.273,
      "mean_oos_mae": 0.03836,
      "pct_vs_best": 0.454
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 122,
      "share": 0.264,
      "mean_oos_mae": 0.0382,
      "pct_vs_best": 0.036
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.4714285714285714,
    "os_gap_pct": 0.1505,
    "os_gap_p90_pct": 1.3884,
    "contender_spread_pct": 0.407,
    "full_spread_pct": 0.763,
    "flips": [
      {
        "config": "T3_joint",
        "IS_half_wins": 203,
        "share": 0.439,
        "mean_oos_mae": 0.03819,
        "pct_vs_best": 0.0
      },
      {
        "config": "T2_heckman",
        "IS_half_wins": 118,
        "share": 0.255,
        "mean_oos_mae": 0.0382,
        "pct_vs_best": 0.036
      },
      {
        "config": "A_mills_placebo",
        "IS_half_wins": 54,
        "share": 0.117,
        "mean_oos_mae": 0.03834,
        "pct_vs_best": 0.407
      },
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 46,
        "share": 0.1,
        "mean_oos_mae": 0.03836,
        "pct_vs_best": 0.454
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 41,
        "share": 0.089,
        "mean_oos_mae": 0.03848,
        "pct_vs_best": 0.763
      }
    ]
  }
}
```

### Notes

- ⛔ INELIGIBLE (anti-concentrated) — T3_joint lifts +0.151% at the LOW-propensity end vs +1.195% at the HIGH end; T2_heckman lifts -0.167% at the LOW-propensity end vs +1.306% at the HIGH end. A selection correction must help where the served population lives; prospects are low-propensity by construction. A benefit that GROWS with propensity is the fit reallocating attention toward the players it already handled best — the opposite of the stated mechanism — so these arms are removed from the field before the pick, not vetoed after it.

---

## `bb_pct` (baseline = `S4_park_env_rel2.0`, prior scale 4.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T1b_ipw_odds         | ladder      | True         |  0.017896 |          6.1e-05 |         0.338996 |        0.545455 |      0.088818 |            0.946855 |            0        |
| T1_ipw               | ladder      | True         |  0.01791  |          4.8e-05 |         0.26596  |        0.545455 |      0.068284 |            0.971618 |            0        |
| V_ipw_clip_tight     | sensitivity | True         |  0.01791  |          4.8e-05 |         0.26596  |        0.545455 |      0.068284 |            0.971673 |            0.818182 |
| A_propensity_placebo | anchor      | False        |  0.017943 |          1.4e-05 |         0.080088 |        0.636364 |      0.252189 |            0.971618 |            0        |
| T0_shipped           | ladder      | True         |  0.017957 |          0       |         0        |        0        |    nan        |          nan        |          nan        |
| A_uniform_weight     | anchor      | False        |  0.017957 |          0       |         0        |        0        |    nan        |          nan        |          nan        |
| A_mills_placebo      | anchor      | False        |  0.018053 |         -9.6e-05 |        -0.533715 |        0.363636 |      0.940559 |          nan        |          nan        |
| T3_joint             | ladder      | True         |  0.018053 |         -9.6e-05 |        -0.534667 |        0.454545 |      0.970823 |            0.971618 |            0        |
| T2_heckman           | ladder      | True         |  0.018077 |         -0.00012 |        -0.666989 |        0.363636 |      0.991164 |          nan        |          nan        |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 162 | 0.0156 |            0.1943 |
| A_mills_placebo      |         1 | 570 | 0.0177 |           -0.6557 |
| A_mills_placebo      |         2 | 962 | 0.0184 |           -0.4085 |
| A_propensity_placebo |         0 | 162 | 0.0156 |            0.1805 |
| A_propensity_placebo |         1 | 570 | 0.0176 |            0.0276 |
| A_propensity_placebo |         2 | 962 | 0.0183 |            0.1809 |
| A_uniform_weight     |         0 | 162 | 0.0156 |            0      |
| A_uniform_weight     |         1 | 570 | 0.0176 |            0      |
| A_uniform_weight     |         2 | 962 | 0.0184 |            0      |
| T0_shipped           |         0 | 162 | 0.0156 |            0      |
| T0_shipped           |         1 | 570 | 0.0176 |            0      |
| T0_shipped           |         2 | 962 | 0.0184 |            0      |
| T1_ipw               |         0 | 162 | 0.0156 |            0.0617 |
| T1_ipw               |         1 | 570 | 0.0175 |            0.3461 |
| T1_ipw               |         2 | 962 | 0.0183 |            0.2213 |
| T1b_ipw_odds         |         0 | 162 | 0.0156 |           -0.0158 |
| T1b_ipw_odds         |         1 | 570 | 0.0175 |            0.4349 |
| T1b_ipw_odds         |         2 | 962 | 0.0183 |            0.3134 |
| T2_heckman           |         0 | 162 | 0.0154 |            1.0746 |
| T2_heckman           |         1 | 570 | 0.0176 |           -0.355  |
| T2_heckman           |         2 | 962 | 0.0185 |           -1.019  |
| T3_joint             |         0 | 162 | 0.0155 |            0.515  |
| T3_joint             |         1 | 570 | 0.0176 |           -0.1241 |
| T3_joint             |         2 | 962 | 0.0185 |           -0.8281 |
| V_ipw_clip_tight     |         0 | 162 | 0.0156 |            0.0617 |
| V_ipw_clip_tight     |         1 | 570 | 0.0175 |            0.3461 |
| V_ipw_clip_tight     |         2 | 962 | 0.0183 |            0.2213 |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": 3.337756559631646e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.8612271511381902,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": -2.3932455611412575e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.3237534964201481,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.017942932048214278,
  "ipw_mae": 0.01790955448261796,
  "mills_placebo_mae": 0.01805315457822973,
  "heckman_mae": 0.018077087033841144,
  "concentration": {
    "T1_ipw": {
      "verdict": "anti",
      "low_propensity_lift_pct": 0.0617,
      "high_propensity_lift_pct": 0.2213,
      "gradient_high_minus_low_pct": 0.1596,
      "mid_propensity_lift_pct": 0.3461
    },
    "T1b_ipw_odds": {
      "verdict": "anti",
      "low_propensity_lift_pct": -0.0158,
      "high_propensity_lift_pct": 0.3134,
      "gradient_high_minus_low_pct": 0.3292,
      "mid_propensity_lift_pct": 0.4349
    },
    "T2_heckman": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 1.0746,
      "high_propensity_lift_pct": -1.019,
      "gradient_high_minus_low_pct": -2.0936,
      "mid_propensity_lift_pct": -0.355
    },
    "T3_joint": {
      "verdict": "concentrated",
      "low_propensity_lift_pct": 0.515,
      "high_propensity_lift_pct": -0.8281,
      "gradient_high_minus_low_pct": -1.3432,
      "mid_propensity_lift_pct": -0.1241
    },
    "V_ipw_clip_tight": {
      "verdict": "anti",
      "low_propensity_lift_pct": 0.0617,
      "high_propensity_lift_pct": 0.2213,
      "gradient_high_minus_low_pct": 0.1596,
      "mid_propensity_lift_pct": 0.3461
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.8982
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9076
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.899
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9027
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9151
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9192
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9297
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.932

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.2571428571428571,
  "os_gap_pct": 0.0,
  "os_gap_p90_pct": 0.1676,
  "contender_spread_pct": 0.073,
  "full_spread_pct": 1.009,
  "flips": [
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 361,
      "share": 0.781,
      "mean_oos_mae": 0.0179,
      "pct_vs_best": 0.0
    },
    {
      "config": "T1_ipw",
      "IS_half_wins": 67,
      "share": 0.145,
      "mean_oos_mae": 0.01791,
      "pct_vs_best": 0.073
    },
    {
      "config": "T0_shipped",
      "IS_half_wins": 34,
      "share": 0.074,
      "mean_oos_mae": 0.01796,
      "pct_vs_best": 0.34
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.18571428571428572,
    "os_gap_pct": 0.0,
    "os_gap_p90_pct": 0.5312,
    "contender_spread_pct": 0.073,
    "full_spread_pct": 1.009,
    "flips": [
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 336,
        "share": 0.727,
        "mean_oos_mae": 0.0179,
        "pct_vs_best": 0.0
      },
      {
        "config": "T1_ipw",
        "IS_half_wins": 57,
        "share": 0.123,
        "mean_oos_mae": 0.01791,
        "pct_vs_best": 0.073
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 56,
        "share": 0.121,
        "mean_oos_mae": 0.01794,
        "pct_vs_best": 0.26
      },
      {
        "config": "T0_shipped",
        "IS_half_wins": 13,
        "share": 0.028,
        "mean_oos_mae": 0.01796,
        "pct_vs_best": 0.34
      }
    ]
  }
}
```

### Notes

- no S2 arm beat the shipped configuration in ≥60% of held-out cohorts

---

## `iso` (baseline = `S4_park_env_rel2.0`, prior scale 2.0)

| arm                  | kind        | selectable   |   oos_mae |   mae_lift_vs_T0 |   pct_lift_vs_T0 |   fold_win_rate |   p_one_sided |   mean_ess_fraction |   mean_rows_trimmed |
|:---------------------|:------------|:-------------|----------:|-----------------:|-----------------:|----------------:|--------------:|--------------------:|--------------------:|
| T2_heckman           | ladder      | True         |  0.038415 |         5.4e-05  |         0.141453 |        0.727273 |      0.383386 |          nan        |          nan        |
| T3_joint             | ladder      | True         |  0.038423 |         4.7e-05  |         0.121595 |        0.636364 |      0.418228 |            0.971618 |            0        |
| T0_shipped           | ladder      | True         |  0.03847  |         0        |         0        |        0        |    nan        |          nan        |          nan        |
| A_uniform_weight     | anchor      | False        |  0.03847  |         0        |         0        |        0        |    nan        |          nan        |          nan        |
| A_mills_placebo      | anchor      | False        |  0.038509 |        -4e-05    |        -0.102707 |        0.363636 |      0.756863 |          nan        |          nan        |
| A_propensity_placebo | anchor      | False        |  0.038512 |        -4.2e-05  |        -0.109432 |        0.363636 |      0.797764 |            0.971618 |            0        |
| T1_ipw               | ladder      | True         |  0.038556 |        -8.7e-05  |        -0.225501 |        0.181818 |      0.921272 |            0.971618 |            0        |
| V_ipw_clip_tight     | sensitivity | True         |  0.038556 |        -8.7e-05  |        -0.225501 |        0.181818 |      0.921272 |            0.971673 |            0.818182 |
| T1b_ipw_odds         | ladder      | True         |  0.038588 |        -0.000119 |        -0.308369 |        0.181818 |      0.911123 |            0.946855 |            0        |

### Propensity-stratified lift — the directional falsification

A real selection correction concentrates in the LOW-propensity tercile (stratum 0), the only observable proxy for the un-promoted prospects we serve. Flat lift across terciles = generic re-weighting, not a selection correction.

| arm                  |   stratum |   n |    mae |   pct_lift_vs_ref |
|:---------------------|----------:|----:|-------:|------------------:|
| A_mills_placebo      |         0 | 162 | 0.0389 |            1.0373 |
| A_mills_placebo      |         1 | 570 | 0.0366 |           -0.2494 |
| A_mills_placebo      |         2 | 962 | 0.0391 |           -0.1533 |
| A_propensity_placebo |         0 | 162 | 0.0394 |           -0.1907 |
| A_propensity_placebo |         1 | 570 | 0.0366 |           -0.0882 |
| A_propensity_placebo |         2 | 962 | 0.0391 |           -0.083  |
| A_uniform_weight     |         0 | 162 | 0.0393 |            0      |
| A_uniform_weight     |         1 | 570 | 0.0365 |            0      |
| A_uniform_weight     |         2 | 962 | 0.039  |            0      |
| T0_shipped           |         0 | 162 | 0.0393 |            0      |
| T0_shipped           |         1 | 570 | 0.0365 |            0      |
| T0_shipped           |         2 | 962 | 0.039  |            0      |
| T1_ipw               |         0 | 162 | 0.0399 |           -1.5067 |
| T1_ipw               |         1 | 570 | 0.0367 |           -0.5804 |
| T1_ipw               |         2 | 962 | 0.039  |            0.149  |
| T1b_ipw_odds         |         0 | 162 | 0.0401 |           -1.9967 |
| T1b_ipw_odds         |         1 | 570 | 0.0368 |           -0.7708 |
| T1b_ipw_odds         |         2 | 962 | 0.039  |            0.195  |
| T2_heckman           |         0 | 162 | 0.0398 |           -1.2457 |
| T2_heckman           |         1 | 570 | 0.0366 |           -0.1511 |
| T2_heckman           |         2 | 962 | 0.0389 |            0.4552 |
| T3_joint             |         0 | 162 | 0.0405 |           -2.9243 |
| T3_joint             |         1 | 570 | 0.0368 |           -0.6668 |
| T3_joint             |         2 | 962 | 0.0387 |            0.9607 |
| V_ipw_clip_tight     |         0 | 162 | 0.0399 |           -1.5067 |
| V_ipw_clip_tight     |         1 | 570 | 0.0367 |           -0.5804 |
| V_ipw_clip_tight     |         2 | 962 | 0.039  |            0.149  |

### Anchors

```
{
  "propensity_placebo_vs_ipw": {
    "available": true,
    "challenger": "A_propensity_placebo",
    "defender": "T1_ipw",
    "mean_gap": -4.4651440684508806e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.28595892229505426,
    "violated": false,
    "alpha": 0.1
  },
  "mills_placebo_vs_heckman": {
    "available": true,
    "challenger": "A_mills_placebo",
    "defender": "T2_heckman",
    "mean_gap": 9.392730254213494e-05,
    "challenger_fold_wins": 3,
    "n_folds": 11,
    "p_challenger_better": 0.6692349458982724,
    "violated": false,
    "alpha": 0.1
  },
  "uniform_weight_max_abs_gap": 0.0,
  "uniform_weight_is_a_noop": true,
  "placebo_mae": 0.03851178126167076,
  "ipw_mae": 0.038556432702355266,
  "mills_placebo_mae": 0.038509194193300206,
  "heckman_mae": 0.03841526689075806,
  "concentration": {
    "T1_ipw": {
      "verdict": "anti",
      "low_propensity_lift_pct": -1.5067,
      "high_propensity_lift_pct": 0.149,
      "gradient_high_minus_low_pct": 1.6557,
      "mid_propensity_lift_pct": -0.5804
    },
    "T1b_ipw_odds": {
      "verdict": "anti",
      "low_propensity_lift_pct": -1.9967,
      "high_propensity_lift_pct": 0.195,
      "gradient_high_minus_low_pct": 2.1917,
      "mid_propensity_lift_pct": -0.7708
    },
    "T2_heckman": {
      "verdict": "anti",
      "low_propensity_lift_pct": -1.2457,
      "high_propensity_lift_pct": 0.4552,
      "gradient_high_minus_low_pct": 1.7009,
      "mid_propensity_lift_pct": -0.1511
    },
    "T3_joint": {
      "verdict": "anti",
      "low_propensity_lift_pct": -2.9243,
      "high_propensity_lift_pct": 0.9607,
      "gradient_high_minus_low_pct": 3.885,
      "mid_propensity_lift_pct": -0.6668
    },
    "V_ipw_clip_tight": {
      "verdict": "anti",
      "low_propensity_lift_pct": -1.5067,
      "high_propensity_lift_pct": 0.149,
      "gradient_high_minus_low_pct": 1.6557,
      "mid_propensity_lift_pct": -0.5804
    }
  }
}
```

### Censoring guard (per fold)

- fold **2016**: fired=`True` flagged=[2015] incomplete_followup=100.0% mature o/e None
- fold **2017**: fired=`True` flagged=[2015, 2016] incomplete_followup=100.0% mature o/e None
- fold **2018**: fired=`True` flagged=[2015, 2016, 2017] incomplete_followup=100.0% mature o/e None
- fold **2019**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.8982
- fold **2020**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9076
- fold **2021**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.899
- fold **2022**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9027
- fold **2023**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9151
- fold **2024**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9192
- fold **2025**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.9297
- fold **2026**: fired=`False` flagged=[] incomplete_followup=0.0% mature o/e 0.932

### Deflation

```
{
  "n_configs": 6,
  "n_folds": 11,
  "pbo": 0.38571428571428573,
  "os_gap_pct": 0.414,
  "os_gap_p90_pct": 0.9291,
  "contender_spread_pct": 0.142,
  "full_spread_pct": 0.45,
  "flips": [
    {
      "config": "T3_joint",
      "IS_half_wins": 182,
      "share": 0.394,
      "mean_oos_mae": 0.03842,
      "pct_vs_best": 0.02
    },
    {
      "config": "T0_shipped",
      "IS_half_wins": 168,
      "share": 0.364,
      "mean_oos_mae": 0.03847,
      "pct_vs_best": 0.142
    },
    {
      "config": "T2_heckman",
      "IS_half_wins": 109,
      "share": 0.236,
      "mean_oos_mae": 0.03842,
      "pct_vs_best": 0.0
    },
    {
      "config": "T1b_ipw_odds",
      "IS_half_wins": 3,
      "share": 0.006,
      "mean_oos_mae": 0.03859,
      "pct_vs_best": 0.45
    }
  ],
  "whole_field": {
    "n_configs": 9,
    "n_folds": 11,
    "pbo": 0.5,
    "os_gap_pct": 0.5124,
    "os_gap_p90_pct": 1.0083,
    "contender_spread_pct": 0.142,
    "full_spread_pct": 0.45,
    "flips": [
      {
        "config": "T3_joint",
        "IS_half_wins": 173,
        "share": 0.374,
        "mean_oos_mae": 0.03842,
        "pct_vs_best": 0.02
      },
      {
        "config": "T2_heckman",
        "IS_half_wins": 104,
        "share": 0.225,
        "mean_oos_mae": 0.03842,
        "pct_vs_best": 0.0
      },
      {
        "config": "T0_shipped",
        "IS_half_wins": 82,
        "share": 0.177,
        "mean_oos_mae": 0.03847,
        "pct_vs_best": 0.142
      },
      {
        "config": "A_mills_placebo",
        "IS_half_wins": 77,
        "share": 0.167,
        "mean_oos_mae": 0.03851,
        "pct_vs_best": 0.245
      },
      {
        "config": "A_propensity_placebo",
        "IS_half_wins": 23,
        "share": 0.05,
        "mean_oos_mae": 0.03851,
        "pct_vs_best": 0.251
      },
      {
        "config": "T1b_ipw_odds",
        "IS_half_wins": 3,
        "share": 0.006,
        "mean_oos_mae": 0.03859,
        "pct_vs_best": 0.45
      }
    ]
  }
}
```

### Notes

- ⛔ INELIGIBLE (anti-concentrated) — T2_heckman lifts -1.246% at the LOW-propensity end vs +0.455% at the HIGH end; T3_joint lifts -2.924% at the LOW-propensity end vs +0.961% at the HIGH end. A selection correction must help where the served population lives; prospects are low-propensity by construction. A benefit that GROWS with propensity is the fit reallocating attention toward the players it already handled best — the opposite of the stated mechanism — so these arms are removed from the field before the pick, not vetoed after it.
- every arm that cleared the fold gate was anti-concentrated ⇒ the shipped configuration stands