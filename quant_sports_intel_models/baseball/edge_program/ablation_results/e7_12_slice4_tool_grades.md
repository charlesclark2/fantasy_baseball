# E7.12 slice 4 — 20-80 scouting grades as component priors (batters)

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
|           2015 |        146 |        0 |   0        | False            |
|           2016 |        129 |        0 |   0        | False            |
|           2017 |        153 |        0 |   0        | False            |
|           2018 |        175 |        0 |   0        | False            |
|           2019 |        196 |      130 |   0.663265 | False            |
|           2020 |        130 |      106 |   0.815385 | True             |
|           2021 |        177 |      138 |   0.779661 | True             |
|           2022 |        308 |      213 |   0.691558 | True             |
|           2023 |        237 |      194 |   0.818565 | True             |
|           2024 |        214 |      165 |   0.771028 | True             |
|           2025 |        226 |      171 |   0.756637 | True             |
|           2026 |         80 |       72 |   0.9      | True             |

## Verdicts

| metric   | mapped_grade             | shipped_baseline                | verdict   | winner     |   active_folds |   inert_folds |   pct_test_graded | BH-FDR@0.10   |
|:---------|:-------------------------|:--------------------------------|:----------|:-----------|---------------:|--------------:|------------------:|:--------------|
| woba     | grade_hit                | levelenv                        | DROP      | G0_shipped |              7 |             4 |             78.23 |               |
| k_pct    | grade_hit                | park:exposure+levelenv+rel:0.5k | DROP      | G0_shipped |              7 |             4 |             78.23 |               |
| bb_pct   | — (no scouting analogue) | park:exposure+levelenv+rel:2k   | DROP      | G0_shipped |              7 |             4 |             78.23 |               |
| iso      | grade_game_pwr           | park:exposure+levelenv+rel:2k   | DROP      | G0_shipped |              7 |             4 |             78.23 | False         |

---

## `woba` (grade = `grade_hit`, baseline = `levelenv`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 78.23% of held-out rows carry a grade

| arm             | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:----------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| A_flag_only     | anchor | False        |  0.028156 |         0.217606 |        0.571429 |               0.714286 |      0.403599 |
| G0_shipped      | ladder | True         |  0.028217 |         0        |        0        |               0        |    nan        |
| A_grade_placebo | anchor | False        |  0.028287 |        -0.249087 |        0.571429 |               0.571429 |      0.581098 |
| G1_grade        | ladder | True         |  0.028289 |        -0.253306 |        0.428571 |               0.571429 |      0.598741 |
| G3_fv_only      | ladder | True         |  0.028422 |        -0.725575 |        0.428571 |               0.571429 |      0.71023  |
| G2_grade_fv     | ladder | True         |  0.02851  |        -1.03722  |        0.428571 |               0.428571 |      0.862009 |
| G4_all_grades   | ladder | True         |  0.028736 |        -1.8401   |        0.285714 |               0.285714 |      0.812242 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 78.23% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm             | graded   |   n |    mae |   pct_lift_vs_ref |
|:----------------|:---------|----:|-------:|------------------:|
| A_flag_only     | False    | 244 | 0.0301 |           -4.3632 |
| A_flag_only     | True     | 877 | 0.0273 |            2.0906 |
| A_grade_placebo | False    | 244 | 0.03   |           -4.324  |
| A_grade_placebo | True     | 877 | 0.0274 |            1.6904 |
| G0_shipped      | False    | 244 | 0.0288 |            0      |
| G0_shipped      | True     | 877 | 0.0279 |            0      |
| G1_grade        | False    | 244 | 0.0301 |           -4.4646 |
| G1_grade        | True     | 877 | 0.0275 |            1.1695 |
| G2_grade_fv     | False    | 244 | 0.0306 |           -6.2212 |
| G2_grade_fv     | True     | 877 | 0.0276 |            0.8323 |
| G3_fv_only      | False    | 244 | 0.0306 |           -6.2255 |
| G3_fv_only      | True     | 877 | 0.0275 |            1.2113 |
| G4_all_grades   | False    | 244 | 0.0305 |           -6.0666 |
| G4_all_grades   | True     | 877 | 0.0277 |            0.5746 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": true,
    "challenger": "A_grade_placebo",
    "defender": "G1_grade",
    "mean_gap": -1.190568312923131e-06,
    "challenger_fold_wins": 3,
    "n_folds": 7,
    "p_challenger_better": 0.498018077619938,
    "violated": false,
    "alpha": 0.1
  },
  "flag_only_vs_grade": {
    "available": true,
    "challenger": "A_flag_only",
    "defender": "G1_grade",
    "mean_gap": -0.00013287804080431575,
    "challenger_fold_wins": 4,
    "n_folds": 7,
    "p_challenger_better": 0.1657742318022561,
    "violated": false,
    "alpha": 0.1
  },
  "grade_mae": 0.028288642772952347,
  "placebo_mae": 0.028287452204639428,
  "flag_only_mae": 0.028155764732148036,
  "fv_only_mae": 0.028421903617298235,
  "graded_rows_lift_pct": 1.1695,
  "ungraded_rows_lift_pct": -4.4646,
  "movement_is_mostly_the_shared_refit": true
}
```

### Deflation

```
{
  "n_configs": 5,
  "n_folds": 7,
  "pbo": 0.65,
  "os_gap_pct": 1.6656,
  "os_gap_p90_pct": 4.0718,
  "contender_spread_pct": 0.726,
  "full_spread_pct": 1.84,
  "flips": [
    {
      "config": "G0_shipped",
      "IS_half_wins": 13,
      "share": 0.371,
      "mean_oos_mae": 0.02822,
      "pct_vs_best": 0.0
    },
    {
      "config": "G1_grade",
      "IS_half_wins": 9,
      "share": 0.257,
      "mean_oos_mae": 0.02829,
      "pct_vs_best": 0.253
    },
    {
      "config": "G3_fv_only",
      "IS_half_wins": 8,
      "share": 0.229,
      "mean_oos_mae": 0.02842,
      "pct_vs_best": 0.726
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 5,
      "share": 0.143,
      "mean_oos_mae": 0.02874,
      "pct_vs_best": 1.84
    }
  ],
  "whole_field": {
    "n_configs": 7,
    "n_folds": 7,
    "pbo": 0.65,
    "os_gap_pct": 1.3342,
    "os_gap_p90_pct": 4.311,
    "contender_spread_pct": 0.468,
    "full_spread_pct": 2.062,
    "flips": [
      {
        "config": "G0_shipped",
        "IS_half_wins": 11,
        "share": 0.314,
        "mean_oos_mae": 0.02822,
        "pct_vs_best": 0.218
      },
      {
        "config": "A_flag_only",
        "IS_half_wins": 6,
        "share": 0.171,
        "mean_oos_mae": 0.02816,
        "pct_vs_best": 0.0
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 5,
        "share": 0.143,
        "mean_oos_mae": 0.02874,
        "pct_vs_best": 2.062
      },
      {
        "config": "G1_grade",
        "IS_half_wins": 5,
        "share": 0.143,
        "mean_oos_mae": 0.02829,
        "pct_vs_best": 0.472
      },
      {
        "config": "A_grade_placebo",
        "IS_half_wins": 4,
        "share": 0.114,
        "mean_oos_mae": 0.02829,
        "pct_vs_best": 0.468
      },
      {
        "config": "G3_fv_only",
        "IS_half_wins": 4,
        "share": 0.114,
        "mean_oos_mae": 0.02842,
        "pct_vs_best": 0.945
      }
    ]
  }
}
```

### Notes

- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `k_pct` (grade = `grade_hit`, baseline = `park:exposure+levelenv+rel:0.5k`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 78.23% of held-out rows carry a grade

| arm             | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:----------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G0_shipped      | ladder | True         |  0.038499 |         0        |        0        |               0        |    nan        |
| A_grade_placebo | anchor | False        |  0.038574 |        -0.195181 |        0.571429 |               0.571429 |      0.59937  |
| G4_all_grades   | ladder | True         |  0.03859  |        -0.23543  |        0.428571 |               0.571429 |      0.613931 |
| A_flag_only     | anchor | False        |  0.038611 |        -0.29062  |        0.571429 |               0.571429 |      0.656339 |
| G3_fv_only      | ladder | True         |  0.038638 |        -0.359866 |        0.571429 |               0.571429 |      0.685064 |
| G1_grade        | ladder | True         |  0.03873  |        -0.598773 |        0.571429 |               0.571429 |      0.722353 |
| G2_grade_fv     | ladder | True         |  0.038833 |        -0.866673 |        0.285714 |               0.428571 |      0.811316 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 78.23% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm             | graded   |   n |    mae |   pct_lift_vs_ref |
|:----------------|:---------|----:|-------:|------------------:|
| A_flag_only     | False    | 244 | 0.0401 |            0.3137 |
| A_flag_only     | True     | 877 | 0.0373 |           -0.14   |
| A_grade_placebo | False    | 244 | 0.0401 |            0.3006 |
| A_grade_placebo | True     | 877 | 0.0372 |           -0.0026 |
| G0_shipped      | False    | 244 | 0.0402 |            0      |
| G0_shipped      | True     | 877 | 0.0372 |            0      |
| G1_grade        | False    | 244 | 0.0401 |            0.2417 |
| G1_grade        | True     | 877 | 0.0373 |           -0.1258 |
| G2_grade_fv     | False    | 244 | 0.0402 |            0.2122 |
| G2_grade_fv     | True     | 877 | 0.0374 |           -0.4481 |
| G3_fv_only      | False    | 244 | 0.0401 |            0.2902 |
| G3_fv_only      | True     | 877 | 0.0373 |           -0.2583 |
| G4_all_grades   | False    | 244 | 0.0402 |            0.2111 |
| G4_all_grades   | True     | 877 | 0.0373 |           -0.0211 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": true,
    "challenger": "A_grade_placebo",
    "defender": "G1_grade",
    "mean_gap": -0.00015537888759337544,
    "challenger_fold_wins": 4,
    "n_folds": 7,
    "p_challenger_better": 0.17529245146212313,
    "violated": false,
    "alpha": 0.1
  },
  "flag_only_vs_grade": {
    "available": true,
    "challenger": "A_flag_only",
    "defender": "G1_grade",
    "mean_gap": -0.00011863561299299552,
    "challenger_fold_wins": 3,
    "n_folds": 7,
    "p_challenger_better": 0.2402208196095715,
    "violated": false,
    "alpha": 0.1
  },
  "grade_mae": 0.038729540675509225,
  "placebo_mae": 0.038574161787915846,
  "flag_only_mae": 0.03861090506251623,
  "fv_only_mae": 0.038637564036771814,
  "graded_rows_lift_pct": -0.1258,
  "ungraded_rows_lift_pct": 0.2417,
  "movement_is_mostly_the_shared_refit": true
}
```

### Deflation

```
{
  "n_configs": 5,
  "n_folds": 7,
  "pbo": 0.75,
  "os_gap_pct": 0.8959,
  "os_gap_p90_pct": 1.5448,
  "contender_spread_pct": 0.36,
  "full_spread_pct": 0.867,
  "flips": [
    {
      "config": "G0_shipped",
      "IS_half_wins": 18,
      "share": 0.514,
      "mean_oos_mae": 0.0385,
      "pct_vs_best": 0.0
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 9,
      "share": 0.257,
      "mean_oos_mae": 0.03859,
      "pct_vs_best": 0.235
    },
    {
      "config": "G1_grade",
      "IS_half_wins": 5,
      "share": 0.143,
      "mean_oos_mae": 0.03873,
      "pct_vs_best": 0.599
    },
    {
      "config": "G3_fv_only",
      "IS_half_wins": 3,
      "share": 0.086,
      "mean_oos_mae": 0.03864,
      "pct_vs_best": 0.36
    }
  ],
  "whole_field": {
    "n_configs": 7,
    "n_folds": 7,
    "pbo": 0.8,
    "os_gap_pct": 0.922,
    "os_gap_p90_pct": 1.3915,
    "contender_spread_pct": 0.235,
    "full_spread_pct": 0.867,
    "flips": [
      {
        "config": "G0_shipped",
        "IS_half_wins": 16,
        "share": 0.457,
        "mean_oos_mae": 0.0385,
        "pct_vs_best": 0.0
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 8,
        "share": 0.229,
        "mean_oos_mae": 0.03859,
        "pct_vs_best": 0.235
      },
      {
        "config": "A_grade_placebo",
        "IS_half_wins": 6,
        "share": 0.171,
        "mean_oos_mae": 0.03857,
        "pct_vs_best": 0.195
      },
      {
        "config": "G1_grade",
        "IS_half_wins": 3,
        "share": 0.086,
        "mean_oos_mae": 0.03873,
        "pct_vs_best": 0.599
      },
      {
        "config": "G3_fv_only",
        "IS_half_wins": 2,
        "share": 0.057,
        "mean_oos_mae": 0.03864,
        "pct_vs_best": 0.36
      }
    ]
  }
}
```

### Notes

- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `bb_pct` (grade = `none`, baseline = `park:exposure+levelenv+rel:2k`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 78.23% of held-out rows carry a grade

| arm           | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:--------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G0_shipped    | ladder | True         |  0.017335 |         0        |        0        |               0        |    nan        |
| A_flag_only   | anchor | False        |  0.017366 |        -0.181293 |        0.285714 |               0.285714 |      0.943245 |
| G4_all_grades | ladder | True         |  0.017418 |        -0.477255 |        0.428571 |               0.428571 |      0.653179 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 78.23% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm           | graded   |   n |    mae |   pct_lift_vs_ref |
|:--------------|:---------|----:|-------:|------------------:|
| A_flag_only   | False    | 244 | 0.0182 |           -0.2064 |
| A_flag_only   | True     | 877 | 0.0171 |           -0.1652 |
| G0_shipped    | False    | 244 | 0.0182 |            0      |
| G0_shipped    | True     | 877 | 0.0171 |            0      |
| G4_all_grades | False    | 244 | 0.0182 |           -0.3739 |
| G4_all_grades | True     | 877 | 0.0172 |           -1.1414 |

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
  "flag_only_mae": 0.017366455267598096,
  "fv_only_mae": NaN
}
```

### Deflation

```
{
  "n_configs": 2,
  "n_folds": 7,
  "pbo": 0.7,
  "os_gap_pct": 0.7268,
  "os_gap_p90_pct": 1.8705,
  "contender_spread_pct": 0.477,
  "full_spread_pct": 0.477,
  "flips": [
    {
      "config": "G0_shipped",
      "IS_half_wins": 24,
      "share": 0.686,
      "mean_oos_mae": 0.01734,
      "pct_vs_best": 0.0
    },
    {
      "config": "G4_all_grades",
      "IS_half_wins": 11,
      "share": 0.314,
      "mean_oos_mae": 0.01742,
      "pct_vs_best": 0.477
    }
  ],
  "whole_field": {
    "n_configs": 3,
    "n_folds": 7,
    "pbo": 0.7,
    "os_gap_pct": 0.7268,
    "os_gap_p90_pct": 1.8705,
    "contender_spread_pct": 0.477,
    "full_spread_pct": 0.477,
    "flips": [
      {
        "config": "G0_shipped",
        "IS_half_wins": 24,
        "share": 0.686,
        "mean_oos_mae": 0.01734,
        "pct_vs_best": 0.0
      },
      {
        "config": "G4_all_grades",
        "IS_half_wins": 11,
        "share": 0.314,
        "mean_oos_mae": 0.01742,
        "pct_vs_best": 0.477
      }
    ]
  }
}
```

### Notes

- no scouting grade maps to this component — the tool-grade arms are UNSELECTABLE no-ops here rather than a fabricated neutral (the slice-1p `xwoba_against` precedent). Only the kitchen-sink and flag arms ran.
- no grade arm beat the shipped configuration in >=60% of ACTIVE cohorts

---

## `iso` (grade = `grade_game_pwr`, baseline = `park:exposure+levelenv+rel:2k`)

active folds [2020, 2021, 2022, 2023, 2024, 2025, 2026] · **inert (excluded, mechanism cannot act): [2016, 2017, 2018, 2019]** · 78.23% of held-out rows carry a grade

| arm             | kind   | selectable   |   oos_mae |   pct_lift_vs_G0 |   fold_win_rate |   graded_fold_win_rate |   p_one_sided |
|:----------------|:-------|:-------------|----------:|-----------------:|----------------:|-----------------------:|--------------:|
| G4_all_grades   | ladder | True         |  0.036032 |         1.14363  |        0.571429 |               0.571429 |      0.34955  |
| G2_grade_fv     | ladder | True         |  0.036194 |         0.698005 |        0.714286 |               0.714286 |      0.323463 |
| G1_grade        | ladder | True         |  0.036262 |         0.512908 |        0.714286 |               0.714286 |      0.36083  |
| G0_shipped      | ladder | True         |  0.036449 |         0        |        0        |               0        |    nan        |
| A_flag_only     | anchor | False        |  0.037114 |        -1.82531  |        0.285714 |               0.285714 |      0.93407  |
| G3_fv_only      | ladder | True         |  0.037263 |        -2.2344   |        0.285714 |               0.285714 |      0.940868 |
| A_grade_placebo | anchor | False        |  0.037306 |        -2.35282  |        0.142857 |               0.142857 |      0.905285 |

⚠️ `graded_fold_win_rate` is the SAME fold test restricted to the 78.23% of held-out rows that carry a grade — a **power diagnostic, deliberately NOT part of the gate**. With 7 active folds the gate has no resolution between 4/7 = 0.571 and 5/7 = 0.714, so an arm that wins on the graded rows but loses overall is being diluted by the ungraded fallback rather than failing on the mechanism. That distinction is the difference between a clean null and an underpowered one, and only the first retires a mechanism.


### Graded vs ungraded held-out rows

The overall number is the SHIPPING number and is diluted by the ungraded rows that fall back to the incumbent; the graded number is what the mechanism can do. **An arm that moves the UNGRADED rows is re-fitting the whole model, not applying scouting information.**

| arm             | graded   |   n |    mae |   pct_lift_vs_ref |
|:----------------|:---------|----:|-------:|------------------:|
| A_flag_only     | False    | 244 | 0.0379 |            1.8133 |
| A_flag_only     | True     | 877 | 0.0365 |           -2.6469 |
| A_grade_placebo | False    | 244 | 0.0379 |            1.8667 |
| A_grade_placebo | True     | 877 | 0.0367 |           -3.1196 |
| G0_shipped      | False    | 244 | 0.0386 |            0      |
| G0_shipped      | True     | 877 | 0.0355 |            0      |
| G1_grade        | False    | 244 | 0.039  |           -1.0812 |
| G1_grade        | True     | 877 | 0.035  |            1.4789 |
| G2_grade_fv     | False    | 244 | 0.0388 |           -0.536  |
| G2_grade_fv     | True     | 877 | 0.035  |            1.4941 |
| G3_fv_only      | False    | 244 | 0.0382 |            0.9733 |
| G3_fv_only      | True     | 877 | 0.0366 |           -2.9298 |
| G4_all_grades   | False    | 244 | 0.0392 |           -1.4978 |
| G4_all_grades   | True     | 877 | 0.0349 |            1.8698 |

### Anchors

```
{
  "grade_placebo_vs_grade": {
    "available": true,
    "challenger": "A_grade_placebo",
    "defender": "G1_grade",
    "mean_gap": 0.0010445221318891099,
    "challenger_fold_wins": 1,
    "n_folds": 7,
    "p_challenger_better": 0.9880322212452924,
    "violated": false,
    "alpha": 0.1
  },
  "flag_only_vs_grade": {
    "available": true,
    "challenger": "A_flag_only",
    "defender": "G1_grade",
    "mean_gap": 0.0008522506375194547,
    "challenger_fold_wins": 2,
    "n_folds": 7,
    "p_challenger_better": 0.9820532097037767,
    "violated": false,
    "alpha": 0.1
  },
  "grade_mae": 0.036261825947964635,
  "placebo_mae": 0.037306348079853745,
  "flag_only_mae": 0.03711407658548409,
  "fv_only_mae": 0.03726318428543622,
  "graded_rows_lift_pct": 1.4789,
  "ungraded_rows_lift_pct": -1.0812,
  "movement_is_mostly_the_shared_refit": false
}
```

### Deflation

```
{
  "n_configs": 5,
  "n_folds": 7,
  "pbo": 0.85,
  "os_gap_pct": 1.8035,
  "os_gap_p90_pct": 4.5692,
  "contender_spread_pct": 0.638,
  "full_spread_pct": 3.417,
  "flips": [
    {
      "config": "G4_all_grades",
      "IS_half_wins": 18,
      "share": 0.514,
      "mean_oos_mae": 0.03603,
      "pct_vs_best": 0.0
    },
    {
      "config": "G0_shipped",
      "IS_half_wins": 8,
      "share": 0.229,
      "mean_oos_mae": 0.03645,
      "pct_vs_best": 1.157
    },
    {
      "config": "G2_grade_fv",
      "IS_half_wins": 6,
      "share": 0.171,
      "mean_oos_mae": 0.03619,
      "pct_vs_best": 0.451
    },
    {
      "config": "G1_grade",
      "IS_half_wins": 3,
      "share": 0.086,
      "mean_oos_mae": 0.03626,
      "pct_vs_best": 0.638
    }
  ],
  "whole_field": {
    "n_configs": 7,
    "n_folds": 7,
    "pbo": 0.55,
    "os_gap_pct": 1.8035,
    "os_gap_p90_pct": 4.5692,
    "contender_spread_pct": 0.638,
    "full_spread_pct": 3.537,
    "flips": [
      {
        "config": "G4_all_grades",
        "IS_half_wins": 18,
        "share": 0.514,
        "mean_oos_mae": 0.03603,
        "pct_vs_best": 0.0
      },
      {
        "config": "G0_shipped",
        "IS_half_wins": 8,
        "share": 0.229,
        "mean_oos_mae": 0.03645,
        "pct_vs_best": 1.157
      },
      {
        "config": "G2_grade_fv",
        "IS_half_wins": 6,
        "share": 0.171,
        "mean_oos_mae": 0.03619,
        "pct_vs_best": 0.451
      },
      {
        "config": "G1_grade",
        "IS_half_wins": 3,
        "share": 0.086,
        "mean_oos_mae": 0.03626,
        "pct_vs_best": 0.638
      }
    ]
  }
}
```

### Notes

- ⛔ FDR-DOWNGRADED — did not survive Benjamini-Hochberg at alpha=0.10 across the metrics tested in this run