# E7.12 slice 4 — 20-80 scouting grades as component priors (pitchers)

> ⚠️ **A projection, not an edge claim — `best_alpha = 0`.**

The 20-80 grade is the only input this program carries that is **not derived from the minor-league line** — every mechanism tried so far (park, run environment, reliability, label weights) has been a re-expression of the same box score.


## 🚨 Read this before the leaderboard — the fold set is RESTRICTED

`the_board` begins 2018-07-01 and the as-of guard admits only snapshots STRICTLY BEFORE a player's debut season, so the earliest debut cohorts have **structurally zero** grade coverage and their folds carry no graded training row at all. The grade arm is byte-identical to the baseline in those folds, scoring `delta = 0`, which the `d > 0` fold test counts as a LOSS — capping the achievable fold-win-rate at 7/11 = 0.636 against a 0.60 gate. **A perfect grade signal would clear by one fold.** So the gate runs over ACTIVE folds only (>= 2020); the inert folds are listed per metric, not hidden.

⚠️ **S4 fold counts are therefore NOT comparable to slice 1/2's eleven.**


### Pre-registered asymmetry (E7.8)

FV **complements** our pitcher line and **substitutes** for our hitter line ⇒ grades should ADD on PITCHERS and be ~NULL on HITTERS. **A hitter null is the PREDICTED result, not a failure.** A uniform lift on both sides would be the shrinkage confound in a scouting costume.


### ⚠️ A graded player is a SELECTED player — this slice interacts with S2

Grade coverage rises monotonically with S2's promotion propensity (batters 38.0 / 58.1 / 68.1%, pitchers 21.7 / 40.3 / 53.7% across the low/mid/high terciles), so **the tool grade is least available exactly where S2 showed the model most needs help.** `A_flag_only` — the 'was this player RANKED' indicator carrying no grade value — is the arm that keeps the slice from crediting selection to scouting, and it is a DISQUALIFIER, not a footnote.


### As-of grade coverage on the labelled population

|   debut_cohort |   labelled |   graded |   coverage | fold_is_active   |
|---------------:|-----------:|---------:|-----------:|:-----------------|
|           2015 |        243 |        0 |   0        | False            |
|           2016 |        255 |        0 |   0        | False            |
|           2017 |        265 |        0 |   0        | False            |
|           2018 |        338 |        0 |   0        | False            |
|           2019 |        251 |      120 |   0.478088 | False            |
|           2020 |        215 |      117 |   0.544186 | True             |
|           2021 |        312 |      197 |   0.63141  | True             |
|           2022 |        257 |      119 |   0.463035 | True             |
|           2023 |        287 |      200 |   0.696864 | True             |
|           2024 |        307 |      215 |   0.700326 | True             |
|           2025 |        245 |      157 |   0.640816 | True             |
|           2026 |         56 |       44 |   0.785714 | True             |

## Verdicts

| metric        | mapped_grade             | shipped_baseline                       | verdict   | winner     |   active_folds |   inert_folds |   pct_test_graded | BH-FDR@0.10   |
|:--------------|:-------------------------|:---------------------------------------|:----------|:-----------|---------------:|--------------:|------------------:|:--------------|
| k_pct         | grade_fb                 | baseline                               | DROP      | G0_shipped |              7 |             4 |             63.99 |               |
| bb_pct        | grade_cmd                | park:exposure+levelenv+rel:1k+w:mlb_pa | DROP      | G0_shipped |              7 |             4 |             63.99 |               |
| hr_rate       | — (no scouting analogue) | park:exposure+levelenv+rel:1k+w:mlb_pa | DROP      | G0_shipped |              7 |             4 |             63.99 |               |
| gb_pct        | — (no scouting analogue) | baseline                               | DROP      | G0_shipped |              7 |             4 |             63.99 |               |
| xwoba_against | — (no scouting analogue) | baseline                               | DROP      | G0_shipped |              4 |             0 |             68.87 |               |

---

## `k_pct` (grade = `grade_fb`, baseline = `baseline`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 63.99% of held-out rows carry a grade

| arm             | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:----------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G2_grade_fv     | ladder | True         |  0.03506  |         0.260385 |        0.428571 |               0.428571 |      0.388604 |
| G1_grade        | ladder | True         |  0.035079 |         0.207792 |        0.571429 |               0.571429 |      0.421012 |
| G0_shipped      | ladder | True         |  0.035152 |         0        |        0        |               0        |    nan        |
| G4_all_grades   | ladder | True         |  0.035188 |        -0.103309 |        0.571429 |               0.571429 |      0.526267 |
| A_flag_only     | anchor | False        |  0.035228 |        -0.215976 |        0.428571 |               0.428571 |      0.794189 |
| A_grade_placebo | anchor | False        |  0.035242 |        -0.255127 |        0.571429 |               0.428571 |      0.792339 |
| G3_fv_only      | ladder | True         |  0.035379 |        -0.646759 |        0.285714 |               0.285714 |      0.910997 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 63.99% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm             | graded   |   n |    mae |   pct_lift_vs_ref |
|:----------------|:---------|----:|-------:|------------------:|
| A_flag_only     | False    | 421 | 0.0378 |           -0.0661 |
| A_flag_only     | True     | 748 | 0.0341 |           -0.2027 |
| A_grade_placebo | False    | 421 | 0.0379 |           -0.0904 |
| A_grade_placebo | True     | 748 | 0.0341 |           -0.1326 |
| G0_shipped      | False    | 421 | 0.0378 |            0      |
| G0_shipped      | True     | 748 | 0.034  |            0      |
| G1_grade        | False    | 421 | 0.0378 |           -0.0086 |
| G1_grade        | True     | 748 | 0.0337 |            1.0366 |
| G2_grade_fv     | False    | 421 | 0.0378 |            0.0286 |
| G2_grade_fv     | True     | 748 | 0.0338 |            0.6669 |
| G3_fv_only      | False    | 421 | 0.0378 |           -0.0624 |
| G3_fv_only      | True     | 748 | 0.0342 |           -0.6371 |
| G4_all_grades   | False    | 421 | 0.0378 |            0.1702 |
| G4_all_grades   | True     | 748 | 0.0345 |           -1.4657 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": true,
    "challenger": "A_grade_placebo",
    "defender": "G1_grade",
    "mean_gap": 0.00016272458841714834,
    "challenger_fold_wins": 3,
    "n_folds": 7,
    "p_challenger_better": 0.6917403326065983,
    "violated": false,
    "alpha": 0.1
  },
  "flag_only_vs_grade": {
    "available": true,
    "challenger": "A_flag_only",
    "defender": "G1_grade",
    "mean_gap": 0.0001489621458364327,
    "challenger_fold_wins": 2,
    "n_folds": 7,
    "p_challenger_better": 0.6799357869868556,
    "violated": false,
    "alpha": 0.1
  },
  "grade_mae": 0.03507878841900168,
  "placebo_mae": 0.035241513007418825,
  "flag_only_mae": 0.035227750564838116,
  "fv_only_mae": 0.03537917882327174,
  "graded_rows_lift_pct": 1.0366,
  "ungraded_rows_lift_pct": -0.0086,
  "movement_is_mostly_the_shared_refit": false
}
```

### Deflation

```
{
  "n_configs": 5,
  "n_folds": 7,
  "pbo": 0.95,
  "os_gap_pct": 1.5225,
  "os_gap_p90_pct": 2.7607,
  "contender_spread_pct": 0.261,
  "full_spread_pct": 0.91,
  "flips": [
    {
      "config": "G1_grade",
      "IS_half_wins": 13,
      "share": 0.371,
      "mean_oos_mae": 0.03508,
      "pct_vs_best": 0.053
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 13,
      "share": 0.371,
      "mean_oos_mae": 0.03519,
      "pct_vs_best": 0.365
    },
    {
      "config": "G0_shipped",
      "IS_half_wins": 5,
      "share": 0.143,
      "mean_oos_mae": 0.03515,
      "pct_vs_best": 0.261
    },
    {
      "config": "G2_grade_fv",
      "IS_half_wins": 4,
      "share": 0.114,
      "mean_oos_mae": 0.03506,
      "pct_vs_best": 0.0
    }
  ],
  "whole_field": {
    "n_configs": 7,
    "n_folds": 7,
    "pbo": 0.8,
    "os_gap_pct": 1.5225,
    "os_gap_p90_pct": 2.7607,
    "contender_spread_pct": 0.261,
    "full_spread_pct": 0.91,
    "flips": [
      {
        "config": "G1_grade",
        "IS_half_wins": 13,
        "share": 0.371,
        "mean_oos_mae": 0.03508,
        "pct_vs_best": 0.053
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 13,
        "share": 0.371,
        "mean_oos_mae": 0.03519,
        "pct_vs_best": 0.365
      },
      {
        "config": "G0_shipped",
        "IS_half_wins": 5,
        "share": 0.143,
        "mean_oos_mae": 0.03515,
        "pct_vs_best": 0.261
      },
      {
        "config": "G2_grade_fv",
        "IS_half_wins": 4,
        "share": 0.114,
        "mean_oos_mae": 0.03506,
        "pct_vs_best": 0.0
      }
    ]
  }
}
```

### Notes

- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `bb_pct` (grade = `grade_cmd`, baseline = `park:exposure+levelenv+rel:1k+w:mlb_pa`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 63.99% of held-out rows carry a grade

| arm             | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:----------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| A_flag_only     | anchor | False        |  0.019026 |         0.022364 |        0.857143 |               0.714286 |      0.425056 |
| G3_fv_only      | ladder | True         |  0.019027 |         0.021361 |        0.571429 |               0.428571 |      0.436583 |
| G0_shipped      | ladder | True         |  0.019031 |         0        |        0        |               0        |    nan        |
| G1_grade        | ladder | True         |  0.019041 |        -0.056091 |        0.428571 |               0.428571 |      0.57406  |
| G2_grade_fv     | ladder | True         |  0.019063 |        -0.169827 |        0.285714 |               0.285714 |      0.72733  |
| A_grade_placebo | anchor | False        |  0.019067 |        -0.192062 |        0.428571 |               0.428571 |      0.733626 |
| G4_all_grades   | ladder | True         |  0.0195   |        -2.46854  |        0.142857 |               0.142857 |      0.983599 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 63.99% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm             | graded   |   n |    mae |   pct_lift_vs_ref |
|:----------------|:---------|----:|-------:|------------------:|
| A_flag_only     | False    | 421 | 0.0174 |            0.1794 |
| A_flag_only     | True     | 748 | 0.019  |           -0.0184 |
| A_grade_placebo | False    | 421 | 0.0174 |            0.185  |
| A_grade_placebo | True     | 748 | 0.019  |           -0.311  |
| G0_shipped      | False    | 421 | 0.0174 |            0      |
| G0_shipped      | True     | 748 | 0.019  |            0      |
| G1_grade        | False    | 421 | 0.0174 |            0.3291 |
| G1_grade        | True     | 748 | 0.0191 |           -0.4601 |
| G2_grade_fv     | False    | 421 | 0.0174 |            0.316  |
| G2_grade_fv     | True     | 748 | 0.0191 |           -0.6424 |
| G3_fv_only      | False    | 421 | 0.0174 |            0.1955 |
| G3_fv_only      | True     | 748 | 0.019  |           -0.0231 |
| G4_all_grades   | False    | 421 | 0.0174 |            0.1788 |
| G4_all_grades   | True     | 748 | 0.0198 |           -4.2615 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": true,
    "challenger": "A_grade_placebo",
    "defender": "G1_grade",
    "mean_gap": 2.5876167296167073e-05,
    "challenger_fold_wins": 3,
    "n_folds": 7,
    "p_challenger_better": 0.689358182023347,
    "violated": false,
    "alpha": 0.1
  },
  "flag_only_vs_grade": {
    "available": true,
    "challenger": "A_flag_only",
    "defender": "G1_grade",
    "mean_gap": -1.4930376639044657e-05,
    "challenger_fold_wins": 3,
    "n_folds": 7,
    "p_challenger_better": 0.3918557594524596,
    "violated": false,
    "alpha": 0.1
  },
  "grade_mae": 0.019041266810498236,
  "placebo_mae": 0.019067142977794403,
  "flag_only_mae": 0.019026336433859193,
  "fv_only_mae": 0.01902652731480774,
  "graded_rows_lift_pct": -0.4601,
  "ungraded_rows_lift_pct": 0.3291,
  "movement_is_mostly_the_shared_refit": false
}
```

### Deflation

```
{
  "n_configs": 5,
  "n_folds": 7,
  "pbo": 0.9,
  "os_gap_pct": 0.2285,
  "os_gap_p90_pct": 0.4703,
  "contender_spread_pct": 0.077,
  "full_spread_pct": 2.49,
  "flips": [
    {
      "config": "G3_fv_only",
      "IS_half_wins": 13,
      "share": 0.371,
      "mean_oos_mae": 0.01903,
      "pct_vs_best": 0.0
    },
    {
      "config": "G1_grade",
      "IS_half_wins": 13,
      "share": 0.371,
      "mean_oos_mae": 0.01904,
      "pct_vs_best": 0.077
    },
    {
      "config": "G0_shipped",
      "IS_half_wins": 9,
      "share": 0.257,
      "mean_oos_mae": 0.01903,
      "pct_vs_best": 0.021
    }
  ],
  "whole_field": {
    "n_configs": 7,
    "n_folds": 7,
    "pbo": 0.9,
    "os_gap_pct": 0.3338,
    "os_gap_p90_pct": 0.5531,
    "contender_spread_pct": 0.022,
    "full_spread_pct": 2.491,
    "flips": [
      {
        "config": "G1_grade",
        "IS_half_wins": 11,
        "share": 0.314,
        "mean_oos_mae": 0.01904,
        "pct_vs_best": 0.078
      },
      {
        "config": "G3_fv_only",
        "IS_half_wins": 7,
        "share": 0.2,
        "mean_oos_mae": 0.01903,
        "pct_vs_best": 0.001
      },
      {
        "config": "G0_shipped",
        "IS_half_wins": 7,
        "share": 0.2,
        "mean_oos_mae": 0.01903,
        "pct_vs_best": 0.022
      },
      {
        "config": "A_grade_placebo",
        "IS_half_wins": 6,
        "share": 0.171,
        "mean_oos_mae": 0.01907,
        "pct_vs_best": 0.214
      },
      {
        "config": "A_flag_only",
        "IS_half_wins": 4,
        "share": 0.114,
        "mean_oos_mae": 0.01903,
        "pct_vs_best": 0.0
      }
    ]
  }
}
```

### Notes

- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `hr_rate` (grade = `none`, baseline = `park:exposure+levelenv+rel:1k+w:mlb_pa`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 63.99% of held-out rows carry a grade

| arm           | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:--------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G4_all_grades | ladder | True         |  0.009527 |         0.308115 |        0.285714 |               0.428571 |      0.441391 |
| G0_shipped    | ladder | True         |  0.009556 |         0        |        0        |               0        |    nan        |
| A_flag_only   | anchor | False        |  0.009635 |        -0.825719 |        0.142857 |               0        |      0.981586 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 63.99% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm           | graded   |   n |    mae |   pct_lift_vs_ref |
|:--------------|:---------|----:|-------:|------------------:|
| A_flag_only   | False    | 421 | 0.0102 |           -0.1626 |
| A_flag_only   | True     | 748 | 0.0091 |           -1.3512 |
| G0_shipped    | False    | 421 | 0.0101 |            0      |
| G0_shipped    | True     | 748 | 0.009  |            0      |
| G4_all_grades | False    | 421 | 0.0102 |           -0.1197 |
| G4_all_grades | True     | 748 | 0.0092 |           -1.5441 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": false,
    "violated": false,
    "note": "anchor arm absent from this run"
  },
  "flag_only_vs_grade": {
    "available": false,
    "violated": false,
    "note": "anchor arm absent from this run"
  },
  "grade_mae": NaN,
  "placebo_mae": NaN,
  "flag_only_mae": 0.009635174645195952,
  "fv_only_mae": NaN
}
```

### Deflation

```
{
  "n_configs": 2,
  "n_folds": 7,
  "pbo": 0.9,
  "os_gap_pct": 1.5356,
  "os_gap_p90_pct": 2.7439,
  "contender_spread_pct": 0.309,
  "full_spread_pct": 0.309,
  "flips": [
    {
      "config": "G0_shipped",
      "IS_half_wins": 18,
      "share": 0.514,
      "mean_oos_mae": 0.00956,
      "pct_vs_best": 0.309
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 17,
      "share": 0.486,
      "mean_oos_mae": 0.00953,
      "pct_vs_best": 0.0
    }
  ],
  "whole_field": {
    "n_configs": 3,
    "n_folds": 7,
    "pbo": 0.9,
    "os_gap_pct": 1.5356,
    "os_gap_p90_pct": 2.7439,
    "contender_spread_pct": 1.137,
    "full_spread_pct": 1.137,
    "flips": [
      {
        "config": "G0_shipped",
        "IS_half_wins": 18,
        "share": 0.514,
        "mean_oos_mae": 0.00956,
        "pct_vs_best": 0.309
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 17,
        "share": 0.486,
        "mean_oos_mae": 0.00953,
        "pct_vs_best": 0.0
      }
    ]
  }
}
```

### Notes

- no scouting grade maps to this component — the tool-grade arms are UNSELECTABLE no-ops here rather than a fabricated neutral (the slice-1p `xwoba_against` precedent). Only the kitchen-sink and flag arms ran.
- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `gb_pct` (grade = `none`, baseline = `baseline`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 63.99% of held-out rows carry a grade

| arm           | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:--------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G0_shipped    | ladder | True         |  0.047143 |         0        |        0        |               0        |    nan        |
| A_flag_only   | anchor | False        |  0.047199 |        -0.118802 |        0.142857 |               0.142857 |      0.872951 |
| G4_all_grades | ladder | True         |  0.048855 |        -3.63106  |        0.428571 |               0.428571 |      0.878733 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 63.99% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm           | graded   |   n |    mae |   pct_lift_vs_ref |
|:--------------|:---------|----:|-------:|------------------:|
| A_flag_only   | False    | 421 | 0.0493 |            0.1017 |
| A_flag_only   | True     | 748 | 0.0474 |           -0.2598 |
| G0_shipped    | False    | 421 | 0.0494 |            0      |
| G0_shipped    | True     | 748 | 0.0473 |            0      |
| G4_all_grades | False    | 421 | 0.0492 |            0.4353 |
| G4_all_grades | True     | 748 | 0.0503 |           -6.3721 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": false,
    "violated": false,
    "note": "anchor arm absent from this run"
  },
  "flag_only_vs_grade": {
    "available": false,
    "violated": false,
    "note": "anchor arm absent from this run"
  },
  "grade_mae": NaN,
  "placebo_mae": NaN,
  "flag_only_mae": 0.047199134399622235,
  "fv_only_mae": NaN
}
```

### Deflation

```
{
  "n_configs": 2,
  "n_folds": 7,
  "pbo": 0.1,
  "os_gap_pct": 0.0,
  "os_gap_p90_pct": 6.5002,
  "contender_spread_pct": 3.631,
  "full_spread_pct": 3.631,
  "flips": [
    {
      "config": "G0_shipped",
      "IS_half_wins": 30,
      "share": 0.857,
      "mean_oos_mae": 0.04714,
      "pct_vs_best": 0.0
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 5,
      "share": 0.143,
      "mean_oos_mae": 0.04885,
      "pct_vs_best": 3.631
    }
  ],
  "whole_field": {
    "n_configs": 3,
    "n_folds": 7,
    "pbo": 0.4,
    "os_gap_pct": 0.0,
    "os_gap_p90_pct": 6.5002,
    "contender_spread_pct": 3.631,
    "full_spread_pct": 3.631,
    "flips": [
      {
        "config": "G0_shipped",
        "IS_half_wins": 24,
        "share": 0.686,
        "mean_oos_mae": 0.04714,
        "pct_vs_best": 0.0
      },
      {
        "config": "A_flag_only",
        "IS_half_wins": 6,
        "share": 0.171,
        "mean_oos_mae": 0.0472,
        "pct_vs_best": 0.119
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 5,
        "share": 0.143,
        "mean_oos_mae": 0.04885,
        "pct_vs_best": 3.631
      }
    ]
  }
}
```

### Notes

- no scouting grade maps to this component — the tool-grade arms are UNSELECTABLE no-ops here rather than a fabricated neutral (the slice-1p `xwoba_against` precedent). Only the kitchen-sink and flag arms ran.
- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `xwoba_against` (grade = `none`, baseline = `baseline`)

active folds [2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): []** · 68.87% of held-out rows carry a grade

| arm           | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:--------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G0_shipped    | ladder | True         |  0.02624  |         0        |            0    |                    0   |    nan        |
| G4_all_grades | ladder | True         |  0.026242 |        -0.007148 |            0.25 |                    0.5 |      0.50072  |
| A_flag_only   | anchor | False        |  0.02685  |        -2.32165  |            0.25 |                    0.5 |      0.881346 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 68.87% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 4 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm           | graded   |   n |    mae |   pct_lift_vs_ref |
|:--------------|:---------|----:|-------:|------------------:|
| A_flag_only   | False    |  47 | 0.0282 |          -13.6333 |
| A_flag_only   | True     | 104 | 0.0239 |            1.8431 |
| G0_shipped    | False    |  47 | 0.0248 |            0      |
| G0_shipped    | True     | 104 | 0.0243 |            0      |
| G4_all_grades | False    |  47 | 0.0283 |          -13.976  |
| G4_all_grades | True     | 104 | 0.0238 |            2.1219 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": false,
    "violated": false,
    "note": "anchor arm absent from this run"
  },
  "flag_only_vs_grade": {
    "available": false,
    "violated": false,
    "note": "anchor arm absent from this run"
  },
  "grade_mae": NaN,
  "placebo_mae": NaN,
  "flag_only_mae": 0.026849579042261835,
  "fv_only_mae": NaN
}
```

### Deflation

```
{
  "n_configs": 2,
  "n_folds": 4,
  "pbo": 1.0,
  "os_gap_pct": 3.7629,
  "os_gap_p90_pct": 4.7296,
  "contender_spread_pct": 0.007,
  "full_spread_pct": 0.007,
  "flips": [
    {
      "config": "G0_shipped",
      "IS_half_wins": 3,
      "share": 0.5,
      "mean_oos_mae": 0.02624,
      "pct_vs_best": 0.0
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 3,
      "share": 0.5,
      "mean_oos_mae": 0.02624,
      "pct_vs_best": 0.007
    }
  ],
  "whole_field": {
    "n_configs": 3,
    "n_folds": 4,
    "pbo": 1.0,
    "os_gap_pct": 3.7629,
    "os_gap_p90_pct": 4.7296,
    "contender_spread_pct": 2.322,
    "full_spread_pct": 2.322,
    "flips": [
      {
        "config": "G0_shipped",
        "IS_half_wins": 3,
        "share": 0.5,
        "mean_oos_mae": 0.02624,
        "pct_vs_best": 0.0
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 3,
        "share": 0.5,
        "mean_oos_mae": 0.02624,
        "pct_vs_best": 0.007
      }
    ]
  }
}
```

### Notes

- no scouting grade maps to this component — the tool-grade arms are UNSELECTABLE no-ops here rather than a fabricated neutral (the slice-1p `xwoba_against` precedent). Only the kitchen-sink and flag arms ran.
- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts