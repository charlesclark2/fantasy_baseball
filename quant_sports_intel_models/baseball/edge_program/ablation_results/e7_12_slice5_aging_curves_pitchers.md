# E7.12 slice 5 — prospect aging curves (pitchers)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "same as the batter report \u2014 no stored artifact survives for slice5 (pitcher side).",
 "schema": 1,
 "source_artifact": null,
 "status": "unrecoverable",
 "verdict": null
}
-->


> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.**

## 🛑 This slice is not "add age"

`age` has been an unpenalized fixed main effect in `PartialPoolProjector` since E7.3. The question here is whether age changes the **slope** of the translation — whether a 20-year-old and a 25-year-old posting the same Double-A line should have that line read differently — and, separately, whether the age main effect is mis-specified as **linear**.


### The two channels are separate arms on purpose

| channel | arms | the claim it can support |
|---|---|---|
| **slope** | `Y1_age_slope`, `Y2_rel_slope`, `Y4`, `Y5` | *youth changes how much the line MEANS* — the actual aging-curve hypothesis |
| **intercept** | `Y3_age_growth_prior`, `Y3b_rel_growth_prior` | *the linear age main effect is the wrong shape* — real, but a different finding |


`Y3b` is simultaneously a ladder arm and the **matched foil** for `Y2`: identical bucketing, the claimed channel removed. If both win by the same margin the honest report is the intercept one — a win is not self-attributing (NF-D15 g′).


### ⚠️ Confounded with S2 by construction, and handled as a matched pair

A young player who did NOT develop never gets promoted, so he is in none of these training rows. **"Young players' lines translate better" is exactly what survivorship bias manufactures out of nothing.** `V_ipw_Y0` / `V_ipw_Y2` re-run the baseline and the interaction under S2's `T1b_ipw_odds` inverse-odds weights, which tilt the graduate sample toward the un-promoted population the board actually scores. The second difference — re-weighted lift over unweighted lift — is the `survivorship` block below. The IPW re-weighting appears on BOTH sides of that difference, so it cannot be mistaken for the mechanism.

Retention floor: **50%** of the unweighted lift must survive, pre-registered before the run.


### The ceiling probe

`R_gbm_age` / `R_gbm_noage` are a matched pair of gradient-boosted learners differing ONLY in whether age is visible. A tree ensemble can express any age × line interaction it likes, so their paired gap bounds how much age structure is exploitable here **at all**, independent of whether our prescribed bucketing is the right shape. Neither is selectable: E7.9 measured that 54-77% of every apparent margin in this program was the learner swap, and a GBM win here would report a learner change as an aging-curve finding.


## Verdicts

| metric        | shipped_baseline                       | verdict   | winner     |   folds | age_lift_retention_under_IPW   | BH-FDR@0.10   |
|:--------------|:---------------------------------------|:----------|:-----------|--------:|:-------------------------------|:--------------|
| k_pct         | baseline                               | DROP      | Y0_shipped |      11 |                                |               |
| bb_pct        | park:exposure+levelenv+rel:1k+w:mlb_pa | DROP      | Y0_shipped |      11 |                                |               |
| hr_rate       | park:exposure+levelenv+rel:1k+w:mlb_pa | DROP      | Y0_shipped |      11 |                                |               |
| gb_pct        | baseline                               | DROP      | Y0_shipped |      11 |                                |               |
| xwoba_against | baseline                               | DROP      | Y0_shipped |       4 |                                |               |

---

## `k_pct` (baseline = `baseline`, prior_scale = 4.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| V_ipw_Y0              | sensitivity | True         |  0.035514 | V_ipw_Y0    |          0        |        0        |    nan        |
| A_bucket_placebo      | anchor      | False        |  0.035605 | Y0_shipped  |          0.044111 |        0.818182 |      0.4112   |
| Y0_shipped            | ladder      | True         |  0.035621 | Y0_shipped  |          0        |        0        |    nan        |
| Y5_linear_interaction | ladder      | True         |  0.035666 | Y0_shipped  |         -0.128143 |        0.454545 |      0.904937 |
| Y2_rel_slope          | ladder      | True         |  0.035692 | Y0_shipped  |         -0.200702 |        0.636364 |      0.64959  |
| Y1_age_slope          | ladder      | True         |  0.035795 | Y0_shipped  |         -0.489859 |        0.636364 |      0.780615 |
| V_ipw_Y2              | sensitivity | True         |  0.035807 | V_ipw_Y0    |         -0.827063 |        0.636364 |      0.792215 |
| Y3_age_growth_prior   | ladder      | True         |  0.035832 | Y0_shipped  |         -0.591959 |        0.272727 |      0.967799 |
| Y3b_rel_growth_prior  | ladder      | True         |  0.035978 | Y0_shipped  |         -1.00347  |        0.181818 |      0.982627 |
| Y4_rel_slope_prior    | ladder      | True         |  0.036248 | Y0_shipped  |         -1.75957  |        0.272727 |      0.948851 |
| R_gbm_age             | reference   | False        |  0.036579 | Y0_shipped  |         -2.68908  |        0.272727 |      0.955493 |
| R_gbm_noage           | reference   | False        |  0.03662  | Y0_shipped  |         -2.80395  |        0.272727 |      0.964036 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -7.149173867029278e-05,
  "reweighted_lift": -0.00029371982123010514,
  "retention": null,
  "survives_reweighting": false,
  "retention_floor": 0.5,
  "reading": "no positive unweighted lift to retain \u2014 the survivorship question does not arise"
}
```

### Anchors

```
{
  "placebo_vs_rel_slope": {
    "available": true,
    "challenger": "A_bucket_placebo",
    "defender": "Y2_rel_slope",
    "mean_gap": -8.720435808295073e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.3291789916043128,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": 0.0002859523173171211,
    "challenger_fold_wins": 3,
    "n_folds": 11,
    "p_challenger_better": 0.8638548689142288,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -2.5846281619061227e-05,
    "challenger_fold_wins": 4,
    "n_folds": 11,
    "p_challenger_better": 0.4374611858941388,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.035692320595999756,
  "placebo_mae": 0.0356051162379168,
  "intercept_only_mae": 0.03597827291331688,
  "free_learner_age_value": {
    "mean_mae_gap": 4.09151306495776e-05,
    "pct_of_gbm_mae": 0.1119,
    "folds_age_helps": 5,
    "n_folds": 11,
    "note": "positive \u21d2 removing age HURTS the free learner \u21d2 age structure exists to find"
  }
}
```

### Deflation

```
{
  "n_configs": 9,
  "n_folds": 11,
  "pbo": 0.3142857142857143,
  "os_gap_pct": 0.164,
  "os_gap_p90_pct": 1.9122,
  "contender_spread_pct": 0.43,
  "full_spread_pct": 2.067,
  "flips": [
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 320,
      "share": 0.693,
      "mean_oos_mae": 0.03551,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 61,
      "share": 0.132,
      "mean_oos_mae": 0.03581,
      "pct_vs_best": 0.827
    },
    {
      "config": "Y1_age_slope",
      "IS_half_wins": 41,
      "share": 0.089,
      "mean_oos_mae": 0.0358,
      "pct_vs_best": 0.793
    },
    {
      "config": "Y2_rel_slope",
      "IS_half_wins": 34,
      "share": 0.074,
      "mean_oos_mae": 0.03569,
      "pct_vs_best": 0.503
    },
    {
      "config": "Y0_shipped",
      "IS_half_wins": 6,
      "share": 0.013,
      "mean_oos_mae": 0.03562,
      "pct_vs_best": 0.302
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.24285714285714285,
    "os_gap_pct": 0.5413,
    "os_gap_p90_pct": 1.9145,
    "contender_spread_pct": 0.302,
    "full_spread_pct": 3.114,
    "flips": [
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 258,
        "share": 0.558,
        "mean_oos_mae": 0.03551,
        "pct_vs_best": 0.0
      },
      {
        "config": "A_bucket_placebo",
        "IS_half_wins": 81,
        "share": 0.175,
        "mean_oos_mae": 0.03561,
        "pct_vs_best": 0.258
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 55,
        "share": 0.119,
        "mean_oos_mae": 0.03581,
        "pct_vs_best": 0.827
      },
      {
        "config": "Y1_age_slope",
        "IS_half_wins": 34,
        "share": 0.074,
        "mean_oos_mae": 0.0358,
        "pct_vs_best": 0.793
      },
      {
        "config": "Y2_rel_slope",
        "IS_half_wins": 33,
        "share": 0.071,
        "mean_oos_mae": 0.03569,
        "pct_vs_best": 0.503
      },
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.03662,
        "pct_vs_best": 3.114
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       |  64 |
| age_bucket  | 20-21.5    | 198 |
| age_bucket  | 21.5-23    | 585 |
| age_bucket  | 23-24.5    | 665 |
| age_bucket  | 24.5-26    | 344 |
| age_bucket  | 26+        | 179 |
| rel_bucket  | <=-1.5     | 988 |
| rel_bucket  | -1.5..-0.5 | 416 |
| rel_bucket  | -0.5..0.5  | 306 |
| rel_bucket  | 0.5..1.5   | 180 |
| rel_bucket  | 1.5+       | 145 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `bb_pct` (baseline = `park:exposure+levelenv+rel:1k+w:mlb_pa`, prior_scale = 4.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| Y0_shipped            | ladder      | True         |  0.019071 | Y0_shipped  |          0        |        0        |    nan        |
| Y5_linear_interaction | ladder      | True         |  0.019075 | Y0_shipped  |         -0.022005 |        0.454545 |      0.551004 |
| A_bucket_placebo      | anchor      | False        |  0.019095 | Y0_shipped  |         -0.126368 |        0.454545 |      0.652069 |
| V_ipw_Y0              | sensitivity | True         |  0.019096 | V_ipw_Y0    |          0        |        0        |    nan        |
| Y3b_rel_growth_prior  | ladder      | True         |  0.019162 | Y0_shipped  |         -0.47629  |        0.363636 |      0.776787 |
| Y3_age_growth_prior   | ladder      | True         |  0.019166 | Y0_shipped  |         -0.497749 |        0.272727 |      0.899629 |
| Y2_rel_slope          | ladder      | True         |  0.019214 | Y0_shipped  |         -0.748148 |        0.545455 |      0.892068 |
| V_ipw_Y2              | sensitivity | True         |  0.019237 | V_ipw_Y0    |         -0.738412 |        0.545455 |      0.868429 |
| Y4_rel_slope_prior    | ladder      | True         |  0.019335 | Y0_shipped  |         -1.38185  |        0.363636 |      0.887553 |
| Y1_age_slope          | ladder      | True         |  0.019367 | Y0_shipped  |         -1.55176  |        0.454545 |      0.887354 |
| R_gbm_noage           | reference   | False        |  0.019563 | Y0_shipped  |         -2.57769  |        0.454545 |      0.911433 |
| R_gbm_age             | reference   | False        |  0.019579 | Y0_shipped  |         -2.6637   |        0.181818 |      0.964765 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -0.000142680149297025,
  "reweighted_lift": -0.00014100411249454915,
  "retention": null,
  "survives_reweighting": false,
  "retention_floor": 0.5,
  "reading": "no positive unweighted lift to retain \u2014 the survivorship question does not arise"
}
```

### Anchors

```
{
  "placebo_vs_rel_slope": {
    "available": true,
    "challenger": "A_bucket_placebo",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00011858031092233152,
    "challenger_fold_wins": 8,
    "n_folds": 11,
    "p_challenger_better": 0.13472542234525048,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": -5.184643392841684e-05,
    "challenger_fold_wins": 6,
    "n_folds": 11,
    "p_challenger_better": 0.34878431963830553,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00013848364799882111,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.15437489760517123,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.019213781780761066,
  "placebo_mae": 0.019095201469838733,
  "intercept_only_mae": 0.01916193534683265,
  "free_learner_age_value": {
    "mean_mae_gap": -1.6404398100885757e-05,
    "pct_of_gbm_mae": -0.0838,
    "folds_age_helps": 3,
    "n_folds": 11,
    "note": "positive \u21d2 removing age HURTS the free learner \u21d2 age structure exists to find"
  }
}
```

### Deflation

```
{
  "n_configs": 9,
  "n_folds": 11,
  "pbo": 0.2714285714285714,
  "os_gap_pct": 0.4843,
  "os_gap_p90_pct": 2.6075,
  "contender_spread_pct": 0.128,
  "full_spread_pct": 1.552,
  "flips": [
    {
      "config": "Y5_linear_interaction",
      "IS_half_wins": 161,
      "share": 0.348,
      "mean_oos_mae": 0.01908,
      "pct_vs_best": 0.022
    },
    {
      "config": "Y3b_rel_growth_prior",
      "IS_half_wins": 90,
      "share": 0.195,
      "mean_oos_mae": 0.01916,
      "pct_vs_best": 0.476
    },
    {
      "config": "Y0_shipped",
      "IS_half_wins": 77,
      "share": 0.167,
      "mean_oos_mae": 0.01907,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 32,
      "share": 0.069,
      "mean_oos_mae": 0.0191,
      "pct_vs_best": 0.128
    },
    {
      "config": "Y3_age_growth_prior",
      "IS_half_wins": 32,
      "share": 0.069,
      "mean_oos_mae": 0.01917,
      "pct_vs_best": 0.498
    },
    {
      "config": "Y1_age_slope",
      "IS_half_wins": 27,
      "share": 0.058,
      "mean_oos_mae": 0.01937,
      "pct_vs_best": 1.552
    },
    {
      "config": "Y2_rel_slope",
      "IS_half_wins": 22,
      "share": 0.048,
      "mean_oos_mae": 0.01921,
      "pct_vs_best": 0.748
    },
    {
      "config": "Y4_rel_slope_prior",
      "IS_half_wins": 20,
      "share": 0.043,
      "mean_oos_mae": 0.01933,
      "pct_vs_best": 1.382
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 1,
      "share": 0.002,
      "mean_oos_mae": 0.01924,
      "pct_vs_best": 0.868
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.35714285714285715,
    "os_gap_pct": 0.6448,
    "os_gap_p90_pct": 3.0447,
    "contender_spread_pct": 0.126,
    "full_spread_pct": 2.664,
    "flips": [
      {
        "config": "Y5_linear_interaction",
        "IS_half_wins": 133,
        "share": 0.288,
        "mean_oos_mae": 0.01908,
        "pct_vs_best": 0.022
      },
      {
        "config": "A_bucket_placebo",
        "IS_half_wins": 107,
        "share": 0.232,
        "mean_oos_mae": 0.0191,
        "pct_vs_best": 0.126
      },
      {
        "config": "Y3b_rel_growth_prior",
        "IS_half_wins": 67,
        "share": 0.145,
        "mean_oos_mae": 0.01916,
        "pct_vs_best": 0.476
      },
      {
        "config": "Y0_shipped",
        "IS_half_wins": 32,
        "share": 0.069,
        "mean_oos_mae": 0.01907,
        "pct_vs_best": 0.0
      },
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 30,
        "share": 0.065,
        "mean_oos_mae": 0.0191,
        "pct_vs_best": 0.128
      },
      {
        "config": "Y3_age_growth_prior",
        "IS_half_wins": 30,
        "share": 0.065,
        "mean_oos_mae": 0.01917,
        "pct_vs_best": 0.498
      },
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 25,
        "share": 0.054,
        "mean_oos_mae": 0.01956,
        "pct_vs_best": 2.578
      },
      {
        "config": "Y1_age_slope",
        "IS_half_wins": 21,
        "share": 0.045,
        "mean_oos_mae": 0.01937,
        "pct_vs_best": 1.552
      },
      {
        "config": "Y4_rel_slope_prior",
        "IS_half_wins": 13,
        "share": 0.028,
        "mean_oos_mae": 0.01933,
        "pct_vs_best": 1.382
      },
      {
        "config": "Y2_rel_slope",
        "IS_half_wins": 3,
        "share": 0.006,
        "mean_oos_mae": 0.01921,
        "pct_vs_best": 0.748
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.01924,
        "pct_vs_best": 0.868
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       |  64 |
| age_bucket  | 20-21.5    | 198 |
| age_bucket  | 21.5-23    | 585 |
| age_bucket  | 23-24.5    | 665 |
| age_bucket  | 24.5-26    | 344 |
| age_bucket  | 26+        | 179 |
| rel_bucket  | <=-1.5     | 988 |
| rel_bucket  | -1.5..-0.5 | 416 |
| rel_bucket  | -0.5..0.5  | 306 |
| rel_bucket  | 0.5..1.5   | 180 |
| rel_bucket  | 1.5+       | 145 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `hr_rate` (baseline = `park:exposure+levelenv+rel:1k+w:mlb_pa`, prior_scale = 4.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| V_ipw_Y0              | sensitivity | True         |  0.009759 | V_ipw_Y0    |          0        |        0        |    nan        |
| V_ipw_Y2              | sensitivity | True         |  0.00976  | V_ipw_Y0    |         -0.015238 |        0.454545 |      0.548618 |
| Y0_shipped            | ladder      | True         |  0.009774 | Y0_shipped  |          0        |        0        |    nan        |
| Y5_linear_interaction | ladder      | True         |  0.009777 | Y0_shipped  |         -0.030671 |        0.454545 |      0.916618 |
| Y2_rel_slope          | ladder      | True         |  0.009779 | Y0_shipped  |         -0.049995 |        0.545455 |      0.637333 |
| A_bucket_placebo      | anchor      | False        |  0.009836 | Y0_shipped  |         -0.62836  |        0.454545 |      0.956383 |
| Y1_age_slope          | ladder      | True         |  0.009841 | Y0_shipped  |         -0.681498 |        0.363636 |      0.927737 |
| Y3_age_growth_prior   | ladder      | True         |  0.009883 | Y0_shipped  |         -1.11223  |        0.181818 |      0.977603 |
| Y3b_rel_growth_prior  | ladder      | True         |  0.009895 | Y0_shipped  |         -1.23038  |        0.363636 |      0.917653 |
| Y4_rel_slope_prior    | ladder      | True         |  0.009962 | Y0_shipped  |         -1.92321  |        0.363636 |      0.883249 |
| R_gbm_noage           | reference   | False        |  0.010103 | Y0_shipped  |         -3.36295  |        0.181818 |      0.97089  |
| R_gbm_age             | reference   | False        |  0.010132 | Y0_shipped  |         -3.65621  |        0.272727 |      0.953201 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -4.886664007001088e-06,
  "reweighted_lift": -1.4870537074076662e-06,
  "retention": null,
  "survives_reweighting": false,
  "retention_floor": 0.5,
  "reading": "no positive unweighted lift to retain \u2014 the survivorship question does not arise"
}
```

### Anchors

```
{
  "placebo_vs_rel_slope": {
    "available": true,
    "challenger": "A_bucket_placebo",
    "defender": "Y2_rel_slope",
    "mean_gap": 5.653151455084114e-05,
    "challenger_fold_wins": 4,
    "n_folds": 11,
    "p_challenger_better": 0.9672280086270127,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": 0.00011537545182736618,
    "challenger_fold_wins": 3,
    "n_folds": 11,
    "p_challenger_better": 0.9383408095759064,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -1.8887895791641251e-06,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.4411663421619495,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.009779254067546468,
  "placebo_mae": 0.009835785582097308,
  "intercept_only_mae": 0.009894629519373834,
  "free_learner_age_value": {
    "mean_mae_gap": -2.8665040673696423e-05,
    "pct_of_gbm_mae": -0.2829,
    "folds_age_helps": 8,
    "n_folds": 11,
    "note": "positive \u21d2 removing age HURTS the free learner \u21d2 age structure exists to find"
  }
}
```

### Deflation

```
{
  "n_configs": 9,
  "n_folds": 11,
  "pbo": 0.0,
  "os_gap_pct": 0.0831,
  "os_gap_p90_pct": 0.2005,
  "contender_spread_pct": 0.16,
  "full_spread_pct": 2.086,
  "flips": [
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 235,
      "share": 0.509,
      "mean_oos_mae": 0.00976,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 212,
      "share": 0.459,
      "mean_oos_mae": 0.00976,
      "pct_vs_best": 0.015
    },
    {
      "config": "Y0_shipped",
      "IS_half_wins": 15,
      "share": 0.032,
      "mean_oos_mae": 0.00977,
      "pct_vs_best": 0.16
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.0,
    "os_gap_pct": 0.0843,
    "os_gap_p90_pct": 0.2043,
    "contender_spread_pct": 0.16,
    "full_spread_pct": 3.822,
    "flips": [
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 233,
        "share": 0.504,
        "mean_oos_mae": 0.00976,
        "pct_vs_best": 0.0
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 209,
        "share": 0.452,
        "mean_oos_mae": 0.00976,
        "pct_vs_best": 0.015
      },
      {
        "config": "Y0_shipped",
        "IS_half_wins": 15,
        "share": 0.032,
        "mean_oos_mae": 0.00977,
        "pct_vs_best": 0.16
      },
      {
        "config": "R_gbm_age",
        "IS_half_wins": 4,
        "share": 0.009,
        "mean_oos_mae": 0.01013,
        "pct_vs_best": 3.822
      },
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.0101,
        "pct_vs_best": 3.528
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       |  64 |
| age_bucket  | 20-21.5    | 198 |
| age_bucket  | 21.5-23    | 585 |
| age_bucket  | 23-24.5    | 665 |
| age_bucket  | 24.5-26    | 344 |
| age_bucket  | 26+        | 179 |
| rel_bucket  | <=-1.5     | 988 |
| rel_bucket  | -1.5..-0.5 | 416 |
| rel_bucket  | -0.5..0.5  | 306 |
| rel_bucket  | 0.5..1.5   | 180 |
| rel_bucket  | 1.5+       | 145 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `gb_pct` (baseline = `baseline`, prior_scale = 2.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| Y5_linear_interaction | ladder      | True         |  0.047829 | Y0_shipped  |          0.013328 |        0.545455 |      0.413366 |
| V_ipw_Y0              | sensitivity | True         |  0.047833 | V_ipw_Y0    |          0        |        0        |    nan        |
| Y0_shipped            | ladder      | True         |  0.047835 | Y0_shipped  |          0        |        0        |    nan        |
| V_ipw_Y2              | sensitivity | True         |  0.047907 | V_ipw_Y0    |         -0.155933 |        0.454545 |      0.785639 |
| Y2_rel_slope          | ladder      | True         |  0.047943 | Y0_shipped  |         -0.225163 |        0.363636 |      0.862848 |
| A_bucket_placebo      | anchor      | False        |  0.047949 | Y0_shipped  |         -0.23912  |        0.636364 |      0.724704 |
| Y3b_rel_growth_prior  | ladder      | True         |  0.047989 | Y0_shipped  |         -0.32254  |        0.454545 |      0.85744  |
| Y3_age_growth_prior   | ladder      | True         |  0.04803  | Y0_shipped  |         -0.406756 |        0.272727 |      0.920166 |
| Y1_age_slope          | ladder      | True         |  0.048059 | Y0_shipped  |         -0.467724 |        0.181818 |      0.990097 |
| Y4_rel_slope_prior    | ladder      | True         |  0.048065 | Y0_shipped  |         -0.480865 |        0.272727 |      0.88283  |
| R_gbm_age             | reference   | False        |  0.048941 | Y0_shipped  |         -2.31281  |        0.363636 |      0.906537 |
| R_gbm_noage           | reference   | False        |  0.04895  | Y0_shipped  |         -2.33135  |        0.272727 |      0.930032 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -0.00010770681370608896,
  "reweighted_lift": -7.458677662442534e-05,
  "retention": null,
  "survives_reweighting": false,
  "retention_floor": 0.5,
  "reading": "no positive unweighted lift to retain \u2014 the survivorship question does not arise"
}
```

### Anchors

```
{
  "placebo_vs_rel_slope": {
    "available": true,
    "challenger": "A_bucket_placebo",
    "defender": "Y2_rel_slope",
    "mean_gap": 6.6763765184051205e-06,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.511342357507151,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": 4.658019578763924e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.6232326117613052,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00011408211635715518,
    "challenger_fold_wins": 7,
    "n_folds": 11,
    "p_challenger_better": 0.12997538299038858,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.04794276255535362,
  "placebo_mae": 0.04794943893187202,
  "intercept_only_mae": 0.047989342751141244,
  "free_learner_age_value": {
    "mean_mae_gap": 8.870375855045156e-06,
    "pct_of_gbm_mae": 0.0181,
    "folds_age_helps": 4,
    "n_folds": 11,
    "note": "positive \u21d2 removing age HURTS the free learner \u21d2 age structure exists to find"
  }
}
```

### Deflation

```
{
  "n_configs": 9,
  "n_folds": 11,
  "pbo": 0.5857142857142857,
  "os_gap_pct": 0.2328,
  "os_gap_p90_pct": 0.9756,
  "contender_spread_pct": 0.013,
  "full_spread_pct": 0.494,
  "flips": [
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 158,
      "share": 0.342,
      "mean_oos_mae": 0.04783,
      "pct_vs_best": 0.008
    },
    {
      "config": "Y5_linear_interaction",
      "IS_half_wins": 130,
      "share": 0.281,
      "mean_oos_mae": 0.04783,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 48,
      "share": 0.104,
      "mean_oos_mae": 0.04791,
      "pct_vs_best": 0.164
    },
    {
      "config": "Y3b_rel_growth_prior",
      "IS_half_wins": 33,
      "share": 0.071,
      "mean_oos_mae": 0.04799,
      "pct_vs_best": 0.336
    },
    {
      "config": "Y3_age_growth_prior",
      "IS_half_wins": 29,
      "share": 0.063,
      "mean_oos_mae": 0.04803,
      "pct_vs_best": 0.42
    },
    {
      "config": "Y0_shipped",
      "IS_half_wins": 28,
      "share": 0.061,
      "mean_oos_mae": 0.04784,
      "pct_vs_best": 0.013
    },
    {
      "config": "Y4_rel_slope_prior",
      "IS_half_wins": 26,
      "share": 0.056,
      "mean_oos_mae": 0.04807,
      "pct_vs_best": 0.494
    },
    {
      "config": "Y2_rel_slope",
      "IS_half_wins": 10,
      "share": 0.022,
      "mean_oos_mae": 0.04794,
      "pct_vs_best": 0.239
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.7714285714285715,
    "os_gap_pct": 0.6293,
    "os_gap_p90_pct": 1.3366,
    "contender_spread_pct": 0.013,
    "full_spread_pct": 2.345,
    "flips": [
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 127,
        "share": 0.275,
        "mean_oos_mae": 0.04783,
        "pct_vs_best": 0.008
      },
      {
        "config": "A_bucket_placebo",
        "IS_half_wins": 113,
        "share": 0.245,
        "mean_oos_mae": 0.04795,
        "pct_vs_best": 0.252
      },
      {
        "config": "Y5_linear_interaction",
        "IS_half_wins": 63,
        "share": 0.136,
        "mean_oos_mae": 0.04783,
        "pct_vs_best": 0.0
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 48,
        "share": 0.104,
        "mean_oos_mae": 0.04791,
        "pct_vs_best": 0.164
      },
      {
        "config": "R_gbm_age",
        "IS_half_wins": 34,
        "share": 0.074,
        "mean_oos_mae": 0.04894,
        "pct_vs_best": 2.326
      },
      {
        "config": "Y0_shipped",
        "IS_half_wins": 19,
        "share": 0.041,
        "mean_oos_mae": 0.04784,
        "pct_vs_best": 0.013
      },
      {
        "config": "Y4_rel_slope_prior",
        "IS_half_wins": 18,
        "share": 0.039,
        "mean_oos_mae": 0.04807,
        "pct_vs_best": 0.494
      },
      {
        "config": "Y3b_rel_growth_prior",
        "IS_half_wins": 15,
        "share": 0.032,
        "mean_oos_mae": 0.04799,
        "pct_vs_best": 0.336
      },
      {
        "config": "Y3_age_growth_prior",
        "IS_half_wins": 15,
        "share": 0.032,
        "mean_oos_mae": 0.04803,
        "pct_vs_best": 0.42
      },
      {
        "config": "Y2_rel_slope",
        "IS_half_wins": 5,
        "share": 0.011,
        "mean_oos_mae": 0.04794,
        "pct_vs_best": 0.239
      },
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 5,
        "share": 0.011,
        "mean_oos_mae": 0.04895,
        "pct_vs_best": 2.345
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       |  64 |
| age_bucket  | 20-21.5    | 198 |
| age_bucket  | 21.5-23    | 585 |
| age_bucket  | 23-24.5    | 665 |
| age_bucket  | 24.5-26    | 344 |
| age_bucket  | 26+        | 179 |
| rel_bucket  | <=-1.5     | 988 |
| rel_bucket  | -1.5..-0.5 | 416 |
| rel_bucket  | -0.5..0.5  | 306 |
| rel_bucket  | 0.5..1.5   | 180 |
| rel_bucket  | 1.5+       | 145 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `xwoba_against` (baseline = `baseline`, prior_scale = 2.0)

folds [2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| Y5_linear_interaction | ladder      | True         |  0.026214 | Y0_shipped  |          0.100003 |            0.5  |      0.247236 |
| V_ipw_Y0              | sensitivity | True         |  0.026219 | V_ipw_Y0    |          0        |            0    |    nan        |
| Y0_shipped            | ladder      | True         |  0.02624  | Y0_shipped  |          0        |            0    |    nan        |
| A_bucket_placebo      | anchor      | False        |  0.026319 | Y0_shipped  |         -0.301352 |            0.5  |      0.593345 |
| Y1_age_slope          | ladder      | True         |  0.02664  | Y0_shipped  |         -1.52191  |            0.5  |      0.862464 |
| V_ipw_Y2              | sensitivity | True         |  0.026764 | V_ipw_Y0    |         -2.07717  |            0.5  |      0.748064 |
| Y2_rel_slope          | ladder      | True         |  0.026779 | Y0_shipped  |         -2.05129  |            0.5  |      0.793147 |
| Y3b_rel_growth_prior  | ladder      | True         |  0.026984 | Y0_shipped  |         -2.83364  |            0.25 |      0.827186 |
| R_gbm_noage           | reference   | False        |  0.027208 | Y0_shipped  |         -3.68773  |            0    |      0.841224 |
| Y4_rel_slope_prior    | ladder      | True         |  0.027684 | Y0_shipped  |         -5.50001  |            0.25 |      0.92001  |
| Y3_age_growth_prior   | ladder      | True         |  0.027854 | Y0_shipped  |         -6.1477   |            0    |      0.921273 |
| R_gbm_age             | reference   | False        |  0.028026 | Y0_shipped  |         -6.80491  |            0.25 |      0.884067 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 4,
  "unweighted_lift": -0.0005382656289897765,
  "reweighted_lift": -0.000544611231401918,
  "retention": null,
  "survives_reweighting": false,
  "retention_floor": 0.5,
  "reading": "no positive unweighted lift to retain \u2014 the survivorship question does not arise"
}
```

### Anchors

```
{
  "placebo_vs_rel_slope": {
    "available": true,
    "challenger": "A_bucket_placebo",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00045918976923948075,
    "challenger_fold_wins": 2,
    "n_folds": 4,
    "p_challenger_better": 0.31435716037216455,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": 0.0002052906505731894,
    "challenger_fold_wins": 2,
    "n_folds": 4,
    "p_challenger_better": 0.5712187829146251,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.0005645068001587806,
    "challenger_fold_wins": 3,
    "n_folds": 4,
    "p_challenger_better": 0.19847161283107248,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.026778634449542857,
  "placebo_mae": 0.026319444680303377,
  "intercept_only_mae": 0.026983925100116046,
  "free_learner_age_value": {
    "mean_mae_gap": -0.0008179599748782069,
    "pct_of_gbm_mae": -2.9186,
    "folds_age_helps": 1,
    "n_folds": 4,
    "note": "positive \u21d2 removing age HURTS the free learner \u21d2 age structure exists to find"
  }
}
```

### Deflation

```
{
  "n_configs": 9,
  "n_folds": 4,
  "pbo": 0.5,
  "os_gap_pct": 1.3555,
  "os_gap_p90_pct": 5.0734,
  "contender_spread_pct": 0.1,
  "full_spread_pct": 6.254,
  "flips": [
    {
      "config": "Y5_linear_interaction",
      "IS_half_wins": 2,
      "share": 0.333,
      "mean_oos_mae": 0.02621,
      "pct_vs_best": 0.0
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 2,
      "share": 0.333,
      "mean_oos_mae": 0.02676,
      "pct_vs_best": 2.096
    },
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 2,
      "share": 0.333,
      "mean_oos_mae": 0.02622,
      "pct_vs_best": 0.018
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 4,
    "pbo": 0.5,
    "os_gap_pct": 2.8962,
    "os_gap_p90_pct": 5.721,
    "contender_spread_pct": 0.1,
    "full_spread_pct": 6.912,
    "flips": [
      {
        "config": "Y5_linear_interaction",
        "IS_half_wins": 2,
        "share": 0.333,
        "mean_oos_mae": 0.02621,
        "pct_vs_best": 0.0
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 2,
        "share": 0.333,
        "mean_oos_mae": 0.02676,
        "pct_vs_best": 2.096
      },
      {
        "config": "A_bucket_placebo",
        "IS_half_wins": 2,
        "share": 0.333,
        "mean_oos_mae": 0.02632,
        "pct_vs_best": 0.402
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       |   0 |
| age_bucket  | 20-21.5    |   0 |
| age_bucket  | 21.5-23    |  15 |
| age_bucket  | 23-24.5    |  58 |
| age_bucket  | 24.5-26    |  60 |
| age_bucket  | 26+        |  50 |
| rel_bucket  | <=-1.5     |  30 |
| rel_bucket  | -1.5..-0.5 |  46 |
| rel_bucket  | -0.5..0.5  |  38 |
| rel_bucket  | 0.5..1.5   |  39 |
| rel_bucket  | 1.5+       |  30 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE