# E7.15 H4 — regressing the TARGET toward true talent (batter side)

_generated 2026-08-02T05:12:56.508375+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> ⚠️ **H4 CHANGES THE ESTIMAND — the one thing H1 deliberately did not do.** The change is confined to the TRAINING target; every arm is scored against the SAME untouched realized held-out rate, asserted per fold. A winner here still costs board/betting comparability and cannot ship without re-running E7.5b's batter gate (or BUILDING the pitcher one, which does not exist) — readiness lock 6.

> 🪤 **The central hazard, named before the run:** MAE against a noisy label REWARDS SHRINKAGE PER SE, and here the mechanism IS shrinkage — so the inversion would look exactly like success. The field carries its own degenerate (`A_shrink_full`, a constant training target) and its own level-matched foil (`A_shrink_constant`, same average compression, zero per-player content).


## Verdicts

| metric   | verdict   | winner   | BH-FDR   |   PBO(eligible) | DSR(eligible)   |
|:---------|:----------|:---------|:---------|----------------:|:----------------|
| woba     | DROP      | L0_foil  | False    |        0.457143 |                 |
| k_pct    | DROP      | L0_foil  | False    |        0.228571 |                 |
| bb_pct   | DROP      | L0_foil  | False    |        0.171429 |                 |
| iso      | DROP      | L0_foil  | False    |        0.128571 |                 |

## ⭐ The inversion probe and the per-player content

`full_shrink_lift` is what a model trained on a CONSTANT target scores. If it is positive, MAE on this cohort rewards compression rather than translation quality and the whole family is measuring the inversion. `per_player_content` is the real arm MINUS the constant-shrink foil: it is the part of any gain that is genuinely per-player rather than a global rescale.

| metric   |   full_shrink_lift_pct |   per_player_content_pct |
|:---------|-----------------------:|-------------------------:|
| woba     |               -100.205 |                   -1.567 |
| k_pct    |                -77.642 |                   -0.273 |
| bb_pct   |                -45.059 |                   -0.609 |
| iso      |                -38.791 |                   -0.841 |

## woba

_shipped foil: `levelenv` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| A_shrink_constant  | anchor | False        | True     | 0.0285072 |           0.983931 |        0.727273 |      0.130614 |           100    |          0.4905 |            0.4905 |
| L0_foil            | foil   | False        | True     | 0.0287905 |           0        |        0        |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0287905 |           0        |        0        |    nan        |             0    |          1      |            1      |
| R3_shrink_to_level | target | True         | True     | 0.0288789 |          -0.307013 |        0.454545 |      0.638149 |            98.53 |          0.4217 |            0.4442 |
| R1_eb_shrink       | target | True         | True     | 0.0289585 |          -0.583478 |        0.454545 |      0.676363 |           100    |          0.4217 |            0.394  |
| A_degenerate_mean  | anchor | False        | True     | 0.0290349 |          -0.848671 |        0.363636 |      0.753329 |             0    |          1      |            1      |
| R2_eb_shrink_2k    | target | True         | True     | 0.0292989 |          -1.76581  |        0.545455 |      0.778052 |           100    |          0.2753 |            0.2576 |
| A_shrink_full      | anchor | False        | True     | 0.05764   |        -100.205    |        0.181818 |      0.863701 |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.4217, "r_p05": 0.2552, "r_p95": 0.6511, "target_sd_ratio": 0.394}, "R2_eb_shrink_2k": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.2753, "r_p05": 0.1462, "r_p95": 0.4828, "target_sd_ratio": 0.2576}, "R3_shrink_to_level": {"n_rows": 68, "pct_rows_moved": 98.53, "mean_shrink_r": 0.4217, "r_p05": 0.2552, "r_p95": 0.6511, "target_sd_ratio": 0.4442}, "A_target_identity": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.4905, "r_p05": 0.4905, "r_p95": 0.4905, "target_sd_ratio": 0.4905}, "A_shrink_full": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                               100 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                               100 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                               100 |       26.3 |     27.5 |       25.2 |       21   |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `R1_eb_shrink`) — `A_shrink_constant` (CONSTANT shrink — identical average compression, no per-player content) systematically beat `R1_eb_shrink` (9/11 folds, p=0.016). The gain is a global rescale of the target, which the regression's own slope already absorbs — not a per-player de-noising. The stated mechanism is refuted. That arm is disqualified from selection; other arms on this metric are untouched.
- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.02888 vs foil 0.02879 (-0.31%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## k_pct

_shipped foil: `park:exposure+levelenv+rel:0.5k` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| A_shrink_constant  | anchor | False        | True     | 0.0383601 |          0.193719  |        0.636364 |      0.311106 |           100    |          0.8709 |            0.8709 |
| L0_foil            | foil   | False        | True     | 0.0384346 |          0         |        0        |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0384346 |          0         |        0        |    nan        |             0    |          1      |            1      |
| R1_eb_shrink       | target | True         | True     | 0.0384652 |         -0.0795516 |        0.454545 |      0.562276 |           100    |          0.8372 |            0.8127 |
| R3_shrink_to_level | target | True         | True     | 0.0385916 |         -0.408492  |        0.454545 |      0.776148 |            98.53 |          0.8372 |            0.8313 |
| R2_eb_shrink_2k    | target | True         | True     | 0.0389896 |         -1.44419   |        0.363636 |      0.943044 |           100    |          0.7254 |            0.6946 |
| A_degenerate_mean  | anchor | False        | True     | 0.0499488 |        -29.9579    |        0        |      0.999999 |             0    |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.0682758 |        -77.6416    |        0        |      0.94177  |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.8372, "r_p05": 0.7285, "r_p95": 0.9359, "target_sd_ratio": 0.8127}, "R2_eb_shrink_2k": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7254, "r_p05": 0.573, "r_p95": 0.8796, "target_sd_ratio": 0.6946}, "R3_shrink_to_level": {"n_rows": 68, "pct_rows_moved": 98.53, "mean_shrink_r": 0.8372, "r_p05": 0.7285, "r_p95": 0.9359, "target_sd_ratio": 0.8313}, "A_target_identity": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.8709, "r_p05": 0.8709, "r_p95": 0.8709, "target_sd_ratio": 0.8709}, "A_shrink_full": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                               100 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                               100 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                               100 |       26.3 |     27.5 |       25.2 |       21   |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `R1_eb_shrink`) — `A_shrink_constant` (CONSTANT shrink — identical average compression, no per-player content) systematically beat `R1_eb_shrink` (6/11 folds, p=0.091). The gain is a global rescale of the target, which the regression's own slope already absorbs — not a per-player de-noising. The stated mechanism is refuted. That arm is disqualified from selection; other arms on this metric are untouched.
- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.03859 vs foil 0.03843 (-0.41%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## bb_pct

_shipped foil: `park:exposure+levelenv+rel:2k` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| L0_foil            | foil   | False        | True     | 0.0179573 |           0        |       0         |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0179573 |           0        |       0         |    nan        |             0    |          1      |            1      |
| A_shrink_constant  | anchor | False        | True     | 0.0180088 |          -0.286926 |       0.363636  |      0.631597 |           100    |          0.7763 |            0.7763 |
| R1_eb_shrink       | target | True         | True     | 0.0181183 |          -0.896262 |       0.181818  |      0.801399 |           100    |          0.7254 |            0.6945 |
| R3_shrink_to_level | target | True         | True     | 0.0182102 |          -1.4083   |       0.181818  |      0.917951 |            98.53 |          0.7254 |            0.7204 |
| R2_eb_shrink_2k    | target | True         | True     | 0.0183824 |          -2.36731  |       0.181818  |      0.920895 |           100    |          0.5781 |            0.5438 |
| A_degenerate_mean  | anchor | False        | True     | 0.0207667 |         -15.645    |       0.0909091 |      0.999826 |             0    |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.0260487 |         -45.0589   |       0         |      0.987953 |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7254, "r_p05": 0.573, "r_p95": 0.8796, "target_sd_ratio": 0.6945}, "R2_eb_shrink_2k": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.5781, "r_p05": 0.4015, "r_p95": 0.7851, "target_sd_ratio": 0.5438}, "R3_shrink_to_level": {"n_rows": 68, "pct_rows_moved": 98.53, "mean_shrink_r": 0.7254, "r_p05": 0.573, "r_p95": 0.8796, "target_sd_ratio": 0.7204}, "A_target_identity": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7763, "r_p05": 0.7763, "r_p95": 0.7763, "target_sd_ratio": 0.7763}, "A_shrink_full": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                               100 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                               100 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                               100 |       26.3 |     27.5 |       25.2 |       21   |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `R1_eb_shrink`) — `A_shrink_constant` (CONSTANT shrink — identical average compression, no per-player content) systematically beat `R1_eb_shrink` (9/11 folds, p=0.008). The gain is a global rescale of the target, which the regression's own slope already absorbs — not a per-player de-noising. The stated mechanism is refuted. That arm is disqualified from selection; other arms on this metric are untouched.
- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.01821 vs foil 0.01796 (-1.41%, fold win rate 18%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## iso

_shipped foil: `park:exposure+levelenv+rel:2k` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| A_shrink_constant  | anchor | False        | True     | 0.0383114 |           0.411574 |       0.636364  |      0.282679 |           100    |          0.7254 |            0.7254 |
| L0_foil            | foil   | False        | True     | 0.0384697 |           0        |       0         |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0384697 |           0        |       0         |    nan        |             0    |          1      |            1      |
| R1_eb_shrink       | target | True         | True     | 0.0386348 |          -0.429154 |       0.454545  |      0.669261 |           100    |          0.6677 |            0.6466 |
| R3_shrink_to_level | target | True         | True     | 0.0388147 |          -0.896881 |       0.454545  |      0.820092 |            98.53 |          0.6677 |            0.6911 |
| R2_eb_shrink_2k    | target | True         | True     | 0.0391422 |          -1.74814  |       0.363636  |      0.895182 |           100    |          0.5112 |            0.4904 |
| A_degenerate_mean  | anchor | False        | True     | 0.0431384 |         -12.1362   |       0.0909091 |      0.999271 |             0    |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.0533926 |         -38.7913   |       0.0909091 |      0.931892 |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.6677, "r_p05": 0.5016, "r_p95": 0.8457, "target_sd_ratio": 0.6466}, "R2_eb_shrink_2k": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.5112, "r_p05": 0.3347, "r_p95": 0.7327, "target_sd_ratio": 0.4904}, "R3_shrink_to_level": {"n_rows": 68, "pct_rows_moved": 98.53, "mean_shrink_r": 0.6677, "r_p05": 0.5016, "r_p95": 0.8457, "target_sd_ratio": 0.6911}, "A_target_identity": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7254, "r_p05": 0.7254, "r_p95": 0.7254, "target_sd_ratio": 0.7254}, "A_shrink_full": {"n_rows": 68, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 68, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                               100 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                               100 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                               100 |       26.3 |     27.5 |       25.2 |       21   |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `R1_eb_shrink`) — `A_shrink_constant` (CONSTANT shrink — identical average compression, no per-player content) systematically beat `R1_eb_shrink` (7/11 folds, p=0.010). The gain is a global rescale of the target, which the regression's own slope already absorbs — not a per-player de-noising. The stated mechanism is refuted. That arm is disqualified from selection; other arms on this metric are untouched.
- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.03881 vs foil 0.03847 (-0.90%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)

**Binding constraint: BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing**

| metric   | arm                |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind                                                             |   folds_have | folds_needed_BH   | folds_needed_DSR   | unreachable_gates   | extra_seasons_needed   |
|:---------|:-------------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-----------------------------------------------------------------|-------------:|:------------------|:-------------------|:--------------------|:-----------------------|
| woba     | R3_shrink_to_level |            -0.307  |        0.454545 |      0.638149 | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |                   |                    | []                  |                        |
| k_pct    | R1_eb_shrink       |            -0.0796 |        0.454545 |      0.562276 | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |                   |                    | []                  |                        |
| bb_pct   | R1_eb_shrink       |            -0.8963 |        0.181818 |      0.801399 | False        | False             | True         | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |                   |                    | []                  |                        |
| iso      | R1_eb_shrink       |            -0.4292 |        0.454545 |      0.669261 | False        | False             | True         | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |                   |                    | []                  |                        |

## Registered but NOT run — the 'more data, not more statistics' alternative

The other way to de-noise a label is a LONGER label window (3-4 MLB seasons instead of 2). It is excluded for a stated reason rather than overlooked: a longer window changes the LABELLED POPULATION (the newest cohorts no longer have a complete label), so the arms would be scored on different players and the comparison would not be an ablation. Doing it honestly needs a pairs rebuild per window plus a population intersection — a separate slice with its own operator build.


- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

