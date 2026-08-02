# E7.12 slice 5 — prospect aging curves (batters)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": null,
 "gates": null,
 "n_arms": null,
 "n_folds": null,
 "per_metric": null,
 "primary_contrast": null,
 "reason": "no `*_summary.json` (or any other JSON) exists for slice5. run_e7_12_slice5.py still exists.",
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

| metric   | shipped_baseline                | verdict   | winner     |   folds | age_lift_retention_under_IPW   | BH-FDR@0.10   |
|:---------|:--------------------------------|:----------|:-----------|--------:|:-------------------------------|:--------------|
| woba     | levelenv                        | DROP      | Y0_shipped |      11 |                                |               |
| k_pct    | park:exposure+levelenv+rel:0.5k | DROP      | Y0_shipped |      11 |                                |               |
| bb_pct   | park:exposure+levelenv+rel:2k   | DROP      | Y0_shipped |      11 |                                |               |
| iso      | park:exposure+levelenv+rel:2k   | DROP      | Y0_shipped |      11 |                                |               |

---

## `woba` (baseline = `levelenv`, prior_scale = 4.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| Y0_shipped            | ladder      | True         |  0.028791 | Y0_shipped  |          0        |        0        |    nan        |
| Y5_linear_interaction | ladder      | True         |  0.028794 | Y0_shipped  |         -0.012618 |        0.545455 |      0.611822 |
| R_gbm_noage           | reference   | False        |  0.028807 | Y0_shipped  |         -0.058789 |        0.545455 |      0.517725 |
| Y1_age_slope          | ladder      | True         |  0.028818 | Y0_shipped  |         -0.096629 |        0.454545 |      0.597139 |
| V_ipw_Y0              | sensitivity | True         |  0.028825 | V_ipw_Y0    |          0        |        0        |    nan        |
| Y2_rel_slope          | ladder      | True         |  0.028896 | Y0_shipped  |         -0.366197 |        0.454545 |      0.834818 |
| A_bucket_placebo      | anchor      | False        |  0.02891  | Y0_shipped  |         -0.415725 |        0.363636 |      0.844507 |
| V_ipw_Y2              | sensitivity | True         |  0.028987 | V_ipw_Y0    |         -0.560403 |        0.545455 |      0.884966 |
| Y3b_rel_growth_prior  | ladder      | True         |  0.029038 | Y0_shipped  |         -0.858859 |        0.363636 |      0.886867 |
| Y3_age_growth_prior   | ladder      | True         |  0.029107 | Y0_shipped  |         -1.09804  |        0.363636 |      0.934901 |
| Y4_rel_slope_prior    | ladder      | True         |  0.029136 | Y0_shipped  |         -1.20041  |        0.363636 |      0.894008 |
| R_gbm_age             | reference   | False        |  0.029201 | Y0_shipped  |         -1.42654  |        0.545455 |      0.771339 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -0.00010543012888694731,
  "reweighted_lift": -0.00016153841016466034,
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
    "mean_gap": 1.4259208376811124e-05,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.5370640161999065,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": 0.00014183981074521464,
    "challenger_fold_wins": 2,
    "n_folds": 11,
    "p_challenger_better": 0.7732680940185959,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00010179724309444142,
    "challenger_fold_wins": 6,
    "n_folds": 11,
    "p_challenger_better": 0.16159176182433674,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.02889594637957393,
  "placebo_mae": 0.028910205587950745,
  "intercept_only_mae": 0.02903778619031914,
  "free_learner_age_value": {
    "mean_mae_gap": -0.0003937831789180046,
    "pct_of_gbm_mae": -1.3485,
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
  "pbo": 0.6714285714285714,
  "os_gap_pct": 0.4449,
  "os_gap_p90_pct": 1.5369,
  "contender_spread_pct": 0.097,
  "full_spread_pct": 1.2,
  "flips": [
    {
      "config": "Y0_shipped",
      "IS_half_wins": 134,
      "share": 0.29,
      "mean_oos_mae": 0.02879,
      "pct_vs_best": 0.0
    },
    {
      "config": "Y1_age_slope",
      "IS_half_wins": 133,
      "share": 0.288,
      "mean_oos_mae": 0.02882,
      "pct_vs_best": 0.097
    },
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 53,
      "share": 0.115,
      "mean_oos_mae": 0.02883,
      "pct_vs_best": 0.121
    },
    {
      "config": "Y2_rel_slope",
      "IS_half_wins": 48,
      "share": 0.104,
      "mean_oos_mae": 0.0289,
      "pct_vs_best": 0.366
    },
    {
      "config": "Y5_linear_interaction",
      "IS_half_wins": 38,
      "share": 0.082,
      "mean_oos_mae": 0.02879,
      "pct_vs_best": 0.013
    },
    {
      "config": "Y3b_rel_growth_prior",
      "IS_half_wins": 19,
      "share": 0.041,
      "mean_oos_mae": 0.02904,
      "pct_vs_best": 0.859
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 14,
      "share": 0.03,
      "mean_oos_mae": 0.02899,
      "pct_vs_best": 0.682
    },
    {
      "config": "Y4_rel_slope_prior",
      "IS_half_wins": 13,
      "share": 0.028,
      "mean_oos_mae": 0.02914,
      "pct_vs_best": 1.2
    },
    {
      "config": "Y3_age_growth_prior",
      "IS_half_wins": 10,
      "share": 0.022,
      "mean_oos_mae": 0.02911,
      "pct_vs_best": 1.098
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.8142857142857143,
    "os_gap_pct": 1.3319,
    "os_gap_p90_pct": 2.5629,
    "contender_spread_pct": 0.059,
    "full_spread_pct": 1.427,
    "flips": [
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 190,
        "share": 0.411,
        "mean_oos_mae": 0.02881,
        "pct_vs_best": 0.059
      },
      {
        "config": "Y1_age_slope",
        "IS_half_wins": 96,
        "share": 0.208,
        "mean_oos_mae": 0.02882,
        "pct_vs_best": 0.097
      },
      {
        "config": "Y0_shipped",
        "IS_half_wins": 45,
        "share": 0.097,
        "mean_oos_mae": 0.02879,
        "pct_vs_best": 0.0
      },
      {
        "config": "Y5_linear_interaction",
        "IS_half_wins": 31,
        "share": 0.067,
        "mean_oos_mae": 0.02879,
        "pct_vs_best": 0.013
      },
      {
        "config": "A_bucket_placebo",
        "IS_half_wins": 28,
        "share": 0.061,
        "mean_oos_mae": 0.02891,
        "pct_vs_best": 0.416
      },
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 24,
        "share": 0.052,
        "mean_oos_mae": 0.02883,
        "pct_vs_best": 0.121
      },
      {
        "config": "Y3b_rel_growth_prior",
        "IS_half_wins": 13,
        "share": 0.028,
        "mean_oos_mae": 0.02904,
        "pct_vs_best": 0.859
      },
      {
        "config": "R_gbm_age",
        "IS_half_wins": 12,
        "share": 0.026,
        "mean_oos_mae": 0.0292,
        "pct_vs_best": 1.427
      },
      {
        "config": "Y3_age_growth_prior",
        "IS_half_wins": 8,
        "share": 0.017,
        "mean_oos_mae": 0.02911,
        "pct_vs_best": 1.098
      },
      {
        "config": "Y4_rel_slope_prior",
        "IS_half_wins": 7,
        "share": 0.015,
        "mean_oos_mae": 0.02914,
        "pct_vs_best": 1.2
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 4,
        "share": 0.009,
        "mean_oos_mae": 0.02899,
        "pct_vs_best": 0.682
      },
      {
        "config": "Y2_rel_slope",
        "IS_half_wins": 4,
        "share": 0.009,
        "mean_oos_mae": 0.0289,
        "pct_vs_best": 0.366
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       | 164 |
| age_bucket  | 20-21.5    | 350 |
| age_bucket  | 21.5-23    | 565 |
| age_bucket  | 23-24.5    | 421 |
| age_bucket  | 24.5-26    | 188 |
| age_bucket  | 26+        |  74 |
| rel_bucket  | <=-1.5     | 523 |
| rel_bucket  | -1.5..-0.5 | 341 |
| rel_bucket  | -0.5..0.5  | 410 |
| rel_bucket  | 0.5..1.5   | 285 |
| rel_bucket  | 1.5+       | 203 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `k_pct` (baseline = `park:exposure+levelenv+rel:0.5k`, prior_scale = 2.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| V_ipw_Y0              | sensitivity | True         |  0.038361 | V_ipw_Y0    |          0        |        0        |    nan        |
| R_gbm_noage           | reference   | False        |  0.038426 | Y0_shipped  |          0.023309 |        0.454545 |      0.490243 |
| Y0_shipped            | ladder      | True         |  0.038435 | Y0_shipped  |          0        |        0        |    nan        |
| Y3b_rel_growth_prior  | ladder      | True         |  0.03845  | Y0_shipped  |         -0.04095  |        0.272727 |      0.5872   |
| Y5_linear_interaction | ladder      | True         |  0.038462 | Y0_shipped  |         -0.070198 |        0.454545 |      0.844335 |
| V_ipw_Y2              | sensitivity | True         |  0.038516 | V_ipw_Y0    |         -0.40183  |        0.363636 |      0.896515 |
| Y2_rel_slope          | ladder      | True         |  0.038561 | Y0_shipped  |         -0.32886  |        0.272727 |      0.822725 |
| Y4_rel_slope_prior    | ladder      | True         |  0.038629 | Y0_shipped  |         -0.50533  |        0.363636 |      0.832717 |
| A_bucket_placebo      | anchor      | False        |  0.038668 | Y0_shipped  |         -0.6067   |        0.363636 |      0.909337 |
| Y3_age_growth_prior   | ladder      | True         |  0.038848 | Y0_shipped  |         -1.07627  |        0.363636 |      0.959463 |
| Y1_age_slope          | ladder      | True         |  0.038899 | Y0_shipped  |         -1.20893  |        0.272727 |      0.875911 |
| R_gbm_age             | reference   | False        |  0.038984 | Y0_shipped  |         -1.43027  |        0.454545 |      0.860908 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -0.00012639595337780074,
  "reweighted_lift": -0.00015414766923994375,
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
    "mean_gap": 0.00010678655840949775,
    "challenger_fold_wins": 5,
    "n_folds": 11,
    "p_challenger_better": 0.7117134106344604,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00011065696883787672,
    "challenger_fold_wins": 6,
    "n_folds": 11,
    "p_challenger_better": 0.17881349865244425,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -9.941562375801189e-05,
    "challenger_fold_wins": 8,
    "n_folds": 11,
    "p_challenger_better": 0.22228717006090337,
    "violated": false,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.03856097463835977,
  "placebo_mae": 0.03866776119676926,
  "intercept_only_mae": 0.03845031766952189,
  "free_learner_age_value": {
    "mean_mae_gap": -0.0005586791602586416,
    "pct_of_gbm_mae": -1.4331,
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
  "pbo": 0.4,
  "os_gap_pct": 0.101,
  "os_gap_p90_pct": 2.5169,
  "contender_spread_pct": 0.232,
  "full_spread_pct": 1.402,
  "flips": [
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 297,
      "share": 0.643,
      "mean_oos_mae": 0.03836,
      "pct_vs_best": 0.0
    },
    {
      "config": "Y1_age_slope",
      "IS_half_wins": 48,
      "share": 0.104,
      "mean_oos_mae": 0.0389,
      "pct_vs_best": 1.402
    },
    {
      "config": "Y3b_rel_growth_prior",
      "IS_half_wins": 41,
      "share": 0.089,
      "mean_oos_mae": 0.03845,
      "pct_vs_best": 0.232
    },
    {
      "config": "Y4_rel_slope_prior",
      "IS_half_wins": 41,
      "share": 0.089,
      "mean_oos_mae": 0.03863,
      "pct_vs_best": 0.697
    },
    {
      "config": "Y2_rel_slope",
      "IS_half_wins": 17,
      "share": 0.037,
      "mean_oos_mae": 0.03856,
      "pct_vs_best": 0.52
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 10,
      "share": 0.022,
      "mean_oos_mae": 0.03852,
      "pct_vs_best": 0.402
    },
    {
      "config": "Y0_shipped",
      "IS_half_wins": 5,
      "share": 0.011,
      "mean_oos_mae": 0.03843,
      "pct_vs_best": 0.191
    },
    {
      "config": "Y3_age_growth_prior",
      "IS_half_wins": 3,
      "share": 0.006,
      "mean_oos_mae": 0.03885,
      "pct_vs_best": 1.269
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.45714285714285713,
    "os_gap_pct": 0.838,
    "os_gap_p90_pct": 1.7643,
    "contender_spread_pct": 0.191,
    "full_spread_pct": 1.624,
    "flips": [
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 203,
        "share": 0.439,
        "mean_oos_mae": 0.03836,
        "pct_vs_best": 0.0
      },
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 190,
        "share": 0.411,
        "mean_oos_mae": 0.03843,
        "pct_vs_best": 0.167
      },
      {
        "config": "Y3b_rel_growth_prior",
        "IS_half_wins": 26,
        "share": 0.056,
        "mean_oos_mae": 0.03845,
        "pct_vs_best": 0.232
      },
      {
        "config": "Y1_age_slope",
        "IS_half_wins": 22,
        "share": 0.048,
        "mean_oos_mae": 0.0389,
        "pct_vs_best": 1.402
      },
      {
        "config": "Y4_rel_slope_prior",
        "IS_half_wins": 11,
        "share": 0.024,
        "mean_oos_mae": 0.03863,
        "pct_vs_best": 0.697
      },
      {
        "config": "Y2_rel_slope",
        "IS_half_wins": 6,
        "share": 0.013,
        "mean_oos_mae": 0.03856,
        "pct_vs_best": 0.52
      },
      {
        "config": "R_gbm_age",
        "IS_half_wins": 4,
        "share": 0.009,
        "mean_oos_mae": 0.03898,
        "pct_vs_best": 1.624
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       | 164 |
| age_bucket  | 20-21.5    | 350 |
| age_bucket  | 21.5-23    | 565 |
| age_bucket  | 23-24.5    | 421 |
| age_bucket  | 24.5-26    | 188 |
| age_bucket  | 26+        |  74 |
| rel_bucket  | <=-1.5     | 523 |
| rel_bucket  | -1.5..-0.5 | 341 |
| rel_bucket  | -0.5..0.5  | 410 |
| rel_bucket  | 0.5..1.5   | 285 |
| rel_bucket  | 1.5+       | 203 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `bb_pct` (baseline = `park:exposure+levelenv+rel:2k`, prior_scale = 4.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| V_ipw_Y0              | sensitivity | True         |  0.017896 | V_ipw_Y0    |          0        |        0        |    nan        |
| Y3b_rel_growth_prior  | ladder      | True         |  0.017924 | Y0_shipped  |          0.186838 |        0.363636 |      0.230227 |
| Y0_shipped            | ladder      | True         |  0.017957 | Y0_shipped  |          0        |        0        |    nan        |
| Y5_linear_interaction | ladder      | True         |  0.017994 | Y0_shipped  |         -0.201898 |        0.545455 |      0.756817 |
| A_bucket_placebo      | anchor      | False        |  0.01806  | Y0_shipped  |         -0.572372 |        0.454545 |      0.804758 |
| V_ipw_Y2              | sensitivity | True         |  0.018136 | V_ipw_Y0    |         -1.3385   |        0.181818 |      0.979007 |
| Y4_rel_slope_prior    | ladder      | True         |  0.018141 | Y0_shipped  |         -1.02248  |        0.181818 |      0.982314 |
| Y3_age_growth_prior   | ladder      | True         |  0.018158 | Y0_shipped  |         -1.1203   |        0.363636 |      0.958538 |
| Y2_rel_slope          | ladder      | True         |  0.018174 | Y0_shipped  |         -1.2065   |        0.272727 |      0.976477 |
| Y1_age_slope          | ladder      | True         |  0.018378 | Y0_shipped  |         -2.34482  |        0        |      0.950777 |
| R_gbm_noage           | reference   | False        |  0.018548 | Y0_shipped  |         -3.28714  |        0.272727 |      0.93248  |
| R_gbm_age             | reference   | False        |  0.018791 | Y0_shipped  |         -4.64002  |        0.181818 |      0.947936 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -0.0002166549810078026,
  "reweighted_lift": -0.00023954411330760666,
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
    "mean_gap": -0.0001138724278627962,
    "challenger_fold_wins": 7,
    "n_folds": 11,
    "p_challenger_better": 0.2068562949248606,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00025020611354708807,
    "challenger_fold_wins": 8,
    "n_folds": 11,
    "p_challenger_better": 0.024285095553783276,
    "violated": true,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.00018039944635398815,
    "challenger_fold_wins": 7,
    "n_folds": 11,
    "p_challenger_better": 0.030014304286882537,
    "violated": true,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.018173968757062904,
  "placebo_mae": 0.01806009632920011,
  "intercept_only_mae": 0.017923762643515816,
  "free_learner_age_value": {
    "mean_mae_gap": -0.0002429413409477227,
    "pct_of_gbm_mae": -1.2929,
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
  "pbo": 0.04285714285714286,
  "os_gap_pct": 0.2799,
  "os_gap_p90_pct": 0.7017,
  "contender_spread_pct": 0.34,
  "full_spread_pct": 2.693,
  "flips": [
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 282,
      "share": 0.61,
      "mean_oos_mae": 0.0179,
      "pct_vs_best": 0.0
    },
    {
      "config": "Y3b_rel_growth_prior",
      "IS_half_wins": 159,
      "share": 0.344,
      "mean_oos_mae": 0.01792,
      "pct_vs_best": 0.153
    },
    {
      "config": "Y5_linear_interaction",
      "IS_half_wins": 18,
      "share": 0.039,
      "mean_oos_mae": 0.01799,
      "pct_vs_best": 0.543
    },
    {
      "config": "Y0_shipped",
      "IS_half_wins": 3,
      "share": 0.006,
      "mean_oos_mae": 0.01796,
      "pct_vs_best": 0.34
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.014285714285714285,
    "os_gap_pct": 0.3114,
    "os_gap_p90_pct": 1.0601,
    "contender_spread_pct": 0.34,
    "full_spread_pct": 4.996,
    "flips": [
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 264,
        "share": 0.571,
        "mean_oos_mae": 0.0179,
        "pct_vs_best": 0.0
      },
      {
        "config": "Y3b_rel_growth_prior",
        "IS_half_wins": 151,
        "share": 0.327,
        "mean_oos_mae": 0.01792,
        "pct_vs_best": 0.153
      },
      {
        "config": "A_bucket_placebo",
        "IS_half_wins": 28,
        "share": 0.061,
        "mean_oos_mae": 0.01806,
        "pct_vs_best": 0.914
      },
      {
        "config": "Y5_linear_interaction",
        "IS_half_wins": 17,
        "share": 0.037,
        "mean_oos_mae": 0.01799,
        "pct_vs_best": 0.543
      },
      {
        "config": "Y0_shipped",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.01796,
        "pct_vs_best": 0.34
      },
      {
        "config": "R_gbm_age",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.01879,
        "pct_vs_best": 4.996
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       | 164 |
| age_bucket  | 20-21.5    | 350 |
| age_bucket  | 21.5-23    | 565 |
| age_bucket  | 23-24.5    | 421 |
| age_bucket  | 24.5-26    | 188 |
| age_bucket  | 26+        |  74 |
| rel_bucket  | <=-1.5     | 523 |
| rel_bucket  | -1.5..-0.5 | 341 |
| rel_bucket  | -0.5..0.5  | 410 |
| rel_bucket  | 0.5..1.5   | 285 |
| rel_bucket  | 1.5+       | 203 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE

---

## `iso` (baseline = `park:exposure+levelenv+rel:2k`, prior_scale = 2.0)

folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]

| arm                   | kind        | selectable   |   oos_mae | reference   |   pct_lift_vs_ref |   fold_win_rate |   p_one_sided |
|:----------------------|:------------|:-------------|----------:|:------------|------------------:|----------------:|--------------:|
| Y0_shipped            | ladder      | True         |  0.03847  | Y0_shipped  |          0        |        0        |    nan        |
| Y5_linear_interaction | ladder      | True         |  0.038545 | Y0_shipped  |         -0.195013 |        0.363636 |      0.840641 |
| V_ipw_Y0              | sensitivity | True         |  0.038588 | V_ipw_Y0    |          0        |        0        |    nan        |
| A_bucket_placebo      | anchor      | False        |  0.038715 | Y0_shipped  |         -0.637491 |        0.454545 |      0.975872 |
| Y1_age_slope          | ladder      | True         |  0.038808 | Y0_shipped  |         -0.878888 |        0.272727 |      0.833431 |
| Y2_rel_slope          | ladder      | True         |  0.039016 | Y0_shipped  |         -1.41895  |        0.181818 |      0.969362 |
| V_ipw_Y2              | sensitivity | True         |  0.039112 | V_ipw_Y0    |         -1.3562   |        0.272727 |      0.969107 |
| Y3_age_growth_prior   | ladder      | True         |  0.039133 | Y0_shipped  |         -1.72447  |        0.181818 |      0.971369 |
| Y3b_rel_growth_prior  | ladder      | True         |  0.039258 | Y0_shipped  |         -2.04793  |        0.363636 |      0.973978 |
| R_gbm_noage           | reference   | False        |  0.039362 | Y0_shipped  |         -2.31846  |        0.363636 |      0.929402 |
| Y4_rel_slope_prior    | ladder      | True         |  0.039724 | Y0_shipped  |         -3.2616   |        0.272727 |      0.978916 |
| R_gbm_age             | reference   | False        |  0.039776 | Y0_shipped  |         -3.396    |        0.454545 |      0.955354 |

⚠️ `pct_lift_vs_ref` compares each SENSITIVITY arm to `V_ipw_Y0`, not to the unweighted incumbent — comparing a re-weighted arm to an unweighted baseline would fold the re-weighting into the mechanism's margin.


### Survivorship (the S2 confound)

```
{
  "available": true,
  "n_folds": 11,
  "unweighted_lift": -0.000545864691366161,
  "reweighted_lift": -0.0005233337795100151,
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
    "mean_gap": -0.00030062396290049027,
    "challenger_fold_wins": 8,
    "n_folds": 11,
    "p_challenger_better": 0.1238263956152893,
    "violated": false,
    "alpha": 0.1
  },
  "intercept_only_vs_rel_slope": {
    "available": true,
    "challenger": "Y3b_rel_growth_prior",
    "defender": "Y2_rel_slope",
    "mean_gap": 0.00024196796309242918,
    "challenger_fold_wins": 4,
    "n_folds": 11,
    "p_challenger_better": 0.7633428124009042,
    "violated": false,
    "alpha": 0.1
  },
  "linear_vs_bucketed": {
    "available": true,
    "challenger": "Y5_linear_interaction",
    "defender": "Y2_rel_slope",
    "mean_gap": -0.000470843765367452,
    "challenger_fold_wins": 8,
    "n_folds": 11,
    "p_challenger_better": 0.024018868980294122,
    "violated": true,
    "alpha": 0.1
  },
  "rel_slope_mae": 0.03901554791431676,
  "placebo_mae": 0.038714923951416264,
  "intercept_only_mae": 0.03925751587740919,
  "free_learner_age_value": {
    "mean_mae_gap": -0.0004145265823447084,
    "pct_of_gbm_mae": -1.0421,
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
  "pbo": 0.04285714285714286,
  "os_gap_pct": 0.1946,
  "os_gap_p90_pct": 1.9185,
  "contender_spread_pct": 0.308,
  "full_spread_pct": 3.262,
  "flips": [
    {
      "config": "Y0_shipped",
      "IS_half_wins": 277,
      "share": 0.6,
      "mean_oos_mae": 0.03847,
      "pct_vs_best": 0.0
    },
    {
      "config": "Y1_age_slope",
      "IS_half_wins": 98,
      "share": 0.212,
      "mean_oos_mae": 0.03881,
      "pct_vs_best": 0.879
    },
    {
      "config": "Y5_linear_interaction",
      "IS_half_wins": 39,
      "share": 0.084,
      "mean_oos_mae": 0.03854,
      "pct_vs_best": 0.195
    },
    {
      "config": "V_ipw_Y0",
      "IS_half_wins": 33,
      "share": 0.071,
      "mean_oos_mae": 0.03859,
      "pct_vs_best": 0.308
    },
    {
      "config": "Y3b_rel_growth_prior",
      "IS_half_wins": 11,
      "share": 0.024,
      "mean_oos_mae": 0.03926,
      "pct_vs_best": 2.048
    },
    {
      "config": "V_ipw_Y2",
      "IS_half_wins": 3,
      "share": 0.006,
      "mean_oos_mae": 0.03911,
      "pct_vs_best": 1.669
    },
    {
      "config": "Y2_rel_slope",
      "IS_half_wins": 1,
      "share": 0.002,
      "mean_oos_mae": 0.03902,
      "pct_vs_best": 1.419
    }
  ],
  "whole_field": {
    "n_configs": 12,
    "n_folds": 11,
    "pbo": 0.11428571428571428,
    "os_gap_pct": 0.2937,
    "os_gap_p90_pct": 2.0662,
    "contender_spread_pct": 0.308,
    "full_spread_pct": 3.396,
    "flips": [
      {
        "config": "Y0_shipped",
        "IS_half_wins": 266,
        "share": 0.576,
        "mean_oos_mae": 0.03847,
        "pct_vs_best": 0.0
      },
      {
        "config": "Y1_age_slope",
        "IS_half_wins": 97,
        "share": 0.21,
        "mean_oos_mae": 0.03881,
        "pct_vs_best": 0.879
      },
      {
        "config": "Y5_linear_interaction",
        "IS_half_wins": 37,
        "share": 0.08,
        "mean_oos_mae": 0.03854,
        "pct_vs_best": 0.195
      },
      {
        "config": "R_gbm_noage",
        "IS_half_wins": 26,
        "share": 0.056,
        "mean_oos_mae": 0.03936,
        "pct_vs_best": 2.318
      },
      {
        "config": "V_ipw_Y0",
        "IS_half_wins": 21,
        "share": 0.045,
        "mean_oos_mae": 0.03859,
        "pct_vs_best": 0.308
      },
      {
        "config": "Y3b_rel_growth_prior",
        "IS_half_wins": 8,
        "share": 0.017,
        "mean_oos_mae": 0.03926,
        "pct_vs_best": 2.048
      },
      {
        "config": "R_gbm_age",
        "IS_half_wins": 5,
        "share": 0.011,
        "mean_oos_mae": 0.03978,
        "pct_vs_best": 3.396
      },
      {
        "config": "V_ipw_Y2",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.03911,
        "pct_vs_best": 1.669
      },
      {
        "config": "Y2_rel_slope",
        "IS_half_wins": 1,
        "share": 0.002,
        "mean_oos_mae": 0.03902,
        "pct_vs_best": 1.419
      }
    ]
  }
}
```

### Bucket support (labelled rows, last fold's bucketing)

An almost-empty bucket is not a bug, but a mechanism inert in the cell it was designed for has to be visible rather than inferred.

| bucketing   | bucket     |   n |
|:------------|:-----------|----:|
| age_bucket  | <=20       | 164 |
| age_bucket  | 20-21.5    | 350 |
| age_bucket  | 21.5-23    | 565 |
| age_bucket  | 23-24.5    | 421 |
| age_bucket  | 24.5-26    | 188 |
| age_bucket  | 26+        |  74 |
| rel_bucket  | <=-1.5     | 523 |
| rel_bucket  | -1.5..-0.5 | 341 |
| rel_bucket  | -0.5..0.5  | 410 |
| rel_bucket  | 0.5..1.5   | 285 |
| rel_bucket  | 1.5+       | 203 |

### Notes

- no age arm both beat the shipped configuration in >=60% of cohorts AND improved mean OOS MAE