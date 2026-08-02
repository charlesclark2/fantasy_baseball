# E7.15 H4 — regressing the TARGET toward true talent (pitcher side)

_generated 2026-08-02T05:02:01.520211+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> ⚠️ **H4 CHANGES THE ESTIMAND — the one thing H1 deliberately did not do.** The change is confined to the TRAINING target; every arm is scored against the SAME untouched realized held-out rate, asserted per fold. A winner here still costs board/betting comparability and cannot ship without re-running E7.5b's batter gate (or BUILDING the pitcher one, which does not exist) — readiness lock 6.

> 🪤 **The central hazard, named before the run:** MAE against a noisy label REWARDS SHRINKAGE PER SE, and here the mechanism IS shrinkage — so the inversion would look exactly like success. The field carries its own degenerate (`A_shrink_full`, a constant training target) and its own level-matched foil (`A_shrink_constant`, same average compression, zero per-player content).


## Verdicts

| metric        | verdict   | winner   | BH-FDR   |   PBO(eligible) | DSR(eligible)   |
|:--------------|:----------|:---------|:---------|----------------:|:----------------|
| k_pct         | DROP      | L0_foil  | True     |       0.2       |                 |
| bb_pct        | DROP      | L0_foil  | False    |       0.785714  |                 |
| hr_rate       | DROP      | L0_foil  | False    |       0         |                 |
| gb_pct        | DROP      | L0_foil  | False    |       0.0428571 |                 |
| xwoba_against | DROP      | L0_foil  | False    |       0.666667  |                 |

## ⭐ The inversion probe and the per-player content

`full_shrink_lift` is what a model trained on a CONSTANT target scores. If it is positive, MAE on this cohort rewards compression rather than translation quality and the whole family is measuring the inversion. `per_player_content` is the real arm MINUS the constant-shrink foil: it is the part of any gain that is genuinely per-player rather than a global rescale.

| metric        |   full_shrink_lift_pct |   per_player_content_pct |
|:--------------|-----------------------:|-------------------------:|
| k_pct         |                -64.657 |                    0.327 |
| bb_pct        |                -87.686 |                   -0.187 |
| hr_rate       |                -65.919 |                   -0.658 |
| gb_pct        |               -102.836 |                   -0.37  |
| xwoba_against |               -539.175 |                    0.045 |

## k_pct

_shipped foil: `baseline` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| R2_eb_shrink_2k    | target | True         | True     | 0.0350951 |            1.47601 |       0.909091  |    0.0144734  |           100    |          0.7642 |            0.7437 |
| R1_eb_shrink       | target | True         | True     | 0.0351945 |            1.19683 |       0.909091  |    0.00425791 |           100    |          0.862  |            0.8466 |
| R3_shrink_to_level | target | True         | True     | 0.0352332 |            1.08817 |       0.909091  |    0.00998293 |            98.36 |          0.862  |            0.8515 |
| A_shrink_constant  | anchor | False        | True     | 0.0353109 |            0.87001 |       0.909091  |    0.00933647 |           100    |          0.8969 |            0.8969 |
| L0_foil            | foil   | False        | True     | 0.0356208 |            0       |       0         |  nan          |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0356208 |            0       |       0         |  nan          |             0    |          1      |            1      |
| A_degenerate_mean  | anchor | False        | True     | 0.0373594 |           -4.88088 |       0.181818  |    0.977395   |             0    |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.0586522 |          -64.6571  |       0.0909091 |    0.943025   |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.862, "r_p05": 0.7248, "r_p95": 0.9402, "target_sd_ratio": 0.8466}, "R2_eb_shrink_2k": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7642, "r_p05": 0.5683, "r_p95": 0.8872, "target_sd_ratio": 0.7437}, "R3_shrink_to_level": {"n_rows": 61, "pct_rows_moved": 98.36, "mean_shrink_r": 0.862, "r_p05": 0.7248, "r_p95": 0.9402, "target_sd_ratio": 0.8515}, "A_target_identity": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.8969, "r_p05": 0.8969, "r_p95": 0.8969, "target_sd_ratio": 0.8969}, "A_shrink_full": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                               100 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                               100 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                               100 |       29.6 |     28.7 |       24.8 |       17   |

**Reasons**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.200 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.394% and the in-sample halves split across arms a fraction of a percent apart (R2_eb_shrink_2k 81% (+0.000%), R1_eb_shrink 14% (+0.283%), R3_shrink_to_level 5% (+0.394%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## bb_pct

_shipped foil: `park:exposure+levelenv+rel:1k+w:mlb_pa` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| A_shrink_constant  | anchor | False        | True     | 0.0190111 |           0.314432 |       0.454545  |      0.346672 |           100    |          0.8172 |            0.8172 |
| R1_eb_shrink       | target | True         | True     | 0.0190468 |           0.127408 |       0.363636  |      0.443239 |           100    |          0.7642 |            0.748  |
| R3_shrink_to_level | target | True         | True     | 0.0190494 |           0.113863 |       0.363636  |      0.447826 |            98.36 |          0.7642 |            0.7508 |
| L0_foil            | foil   | False        | True     | 0.0190711 |           0        |       0         |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0190711 |           0        |       0         |    nan        |             0    |          1      |            1      |
| R2_eb_shrink_2k    | target | True         | True     | 0.0191866 |          -0.605369 |       0.363636  |      0.673198 |           100    |          0.6301 |            0.6113 |
| A_degenerate_mean  | anchor | False        | True     | 0.0212479 |         -11.414    |       0.0909091 |      0.999382 |             0    |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.0357937 |         -87.6857   |       0         |      0.973966 |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7642, "r_p05": 0.5683, "r_p95": 0.8872, "target_sd_ratio": 0.748}, "R2_eb_shrink_2k": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.6301, "r_p05": 0.397, "r_p95": 0.7973, "target_sd_ratio": 0.6113}, "R3_shrink_to_level": {"n_rows": 61, "pct_rows_moved": 98.36, "mean_shrink_r": 0.7642, "r_p05": 0.5683, "r_p95": 0.8872, "target_sd_ratio": 0.7508}, "A_target_identity": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.8172, "r_p05": 0.8172, "r_p95": 0.8172, "target_sd_ratio": 0.8172}, "A_shrink_full": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                               100 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                               100 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                               100 |       29.6 |     28.7 |       24.8 |       17   |

**Reasons**

- 🟡 no arm clears: best eligible `R1_eb_shrink` MAE 0.01905 vs foil 0.01907 (0.13%, fold win rate 36%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## hr_rate

_shipped foil: `park:exposure+levelenv+rel:1k+w:mlb_pa` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |    oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|-----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| L0_foil            | foil   | False        | True     | 0.00977437 |           0        |       0         |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.00977437 |           0        |       0         |    nan        |             0    |          1      |            1      |
| A_shrink_constant  | anchor | False        | True     | 0.00984049 |          -0.676513 |       0.454545  |      0.909401 |           100    |          0.5372 |            0.5372 |
| R1_eb_shrink       | target | True         | True     | 0.00990477 |          -1.33411  |       0.0909091 |      0.953228 |           100    |          0.4644 |            0.3811 |
| R3_shrink_to_level | target | True         | True     | 0.00990599 |          -1.34661  |       0.0909091 |      0.956974 |            98.36 |          0.4644 |            0.3816 |
| A_degenerate_mean  | anchor | False        | True     | 0.00992128 |          -1.50304  |       0.181818  |      0.975152 |             0    |          1      |            1      |
| R2_eb_shrink_2k    | target | True         | True     | 0.0099957  |          -2.26444  |       0.0909091 |      0.957582 |           100    |          0.3132 |            0.2485 |
| A_shrink_full      | anchor | False        | True     | 0.0162176  |         -65.9193   |       0.0909091 |      0.962599 |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.4644, "r_p05": 0.2401, "r_p95": 0.6537, "target_sd_ratio": 0.3811}, "R2_eb_shrink_2k": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.3132, "r_p05": 0.1364, "r_p95": 0.4856, "target_sd_ratio": 0.2485}, "R3_shrink_to_level": {"n_rows": 61, "pct_rows_moved": 98.36, "mean_shrink_r": 0.4644, "r_p05": 0.2401, "r_p95": 0.6537, "target_sd_ratio": 0.3816}, "A_target_identity": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.5372, "r_p05": 0.5372, "r_p95": 0.5372, "target_sd_ratio": 0.5372}, "A_shrink_full": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                               100 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                               100 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                               100 |       29.6 |     28.7 |       24.8 |       17   |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `R1_eb_shrink`) — `A_shrink_constant` (CONSTANT shrink — identical average compression, no per-player content) systematically beat `R1_eb_shrink` (9/11 folds, p=0.046). The gain is a global rescale of the target, which the regression's own slope already absorbs — not a per-player de-noising. The stated mechanism is refuted. That arm is disqualified from selection; other arms on this metric are untouched.
- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.00991 vs foil 0.00977 (-1.35%, fold win rate 9%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## gb_pct

_shipped foil: `baseline` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| L0_foil            | foil   | False        | True     | 0.0478351 |           0        |        0        |    nan        |             0    |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0478351 |           0        |        0        |    nan        |             0    |          1      |            1      |
| A_shrink_constant  | anchor | False        | True     | 0.0478986 |          -0.132944 |        0.363636 |      0.654073 |           100    |          0.8683 |            0.8683 |
| R1_eb_shrink       | target | True         | True     | 0.0480757 |          -0.503079 |        0.272727 |      0.869742 |           100    |          0.8261 |            0.8126 |
| R3_shrink_to_level | target | True         | True     | 0.0481341 |          -0.625134 |        0.272727 |      0.935204 |            98.36 |          0.8261 |            0.8315 |
| R2_eb_shrink_2k    | target | True         | True     | 0.0486761 |          -1.75819  |        0.181818 |      0.98908  |           100    |          0.7125 |            0.6975 |
| A_degenerate_mean  | anchor | False        | True     | 0.0573124 |         -19.8125   |        0        |      0.999983 |             0    |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.0970268 |        -102.836    |        0        |      0.909266 |           100    |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.8261, "r_p05": 0.6639, "r_p95": 0.9219, "target_sd_ratio": 0.8126}, "R2_eb_shrink_2k": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.7125, "r_p05": 0.4969, "r_p95": 0.8551, "target_sd_ratio": 0.6975}, "R3_shrink_to_level": {"n_rows": 61, "pct_rows_moved": 98.36, "mean_shrink_r": 0.8261, "r_p05": 0.6639, "r_p95": 0.9219, "target_sd_ratio": 0.8315}, "A_target_identity": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.8683, "r_p05": 0.8683, "r_p95": 0.8683, "target_sd_ratio": 0.8683}, "A_shrink_full": {"n_rows": 61, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 61, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                               100 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                               100 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                               100 |       29.6 |     28.7 |       24.8 |       17   |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `R1_eb_shrink`) — `A_shrink_constant` (CONSTANT shrink — identical average compression, no per-player content) systematically beat `R1_eb_shrink` (10/11 folds, p=0.006). The gain is a global rescale of the target, which the regression's own slope already absorbs — not a per-player de-noising. The stated mechanism is refuted. That arm is disqualified from selection; other arms on this metric are untouched.
- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.04813 vs foil 0.04784 (-0.63%, fold win rate 27%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## xwoba_against

_shipped foil: `baseline` · prior_scale 2.0 · 4 folds [2023, 2024, 2025, 2026]_

| arm                | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_shrink_r |   target_sd_ratio |
|:-------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------:|------------------:|
| R3_shrink_to_level | target | True         | True     | 0.0259524 |           1.09724  |            0.5  |      0.299041 |              100 |          0.4613 |            0.4207 |
| R1_eb_shrink       | target | True         | True     | 0.0259524 |           1.09724  |            0.5  |      0.299041 |              100 |          0.4613 |            0.4207 |
| A_shrink_constant  | anchor | False        | True     | 0.0259643 |           1.05194  |            0.5  |      0.283006 |              100 |          0.5306 |            0.5306 |
| R2_eb_shrink_2k    | target | True         | True     | 0.0260238 |           0.825341 |            0.5  |      0.353786 |              100 |          0.3092 |            0.2722 |
| A_degenerate_mean  | anchor | False        | True     | 0.0261087 |           0.501599 |            0.5  |      0.367211 |                0 |          1      |            1      |
| L0_foil            | foil   | False        | True     | 0.0262404 |           0        |            0    |    nan        |                0 |          1      |            1      |
| A_target_identity  | anchor | False        | False    | 0.0262404 |           0        |            0    |    nan        |                0 |          1      |            1      |
| A_shrink_full      | anchor | False        | True     | 0.167722  |        -539.175    |            0.25 |      0.909383 |              100 |          0      |            0      |

**Anchors**


**Coverage (target units)**: {"L0_foil": {"n_rows": 32, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "R1_eb_shrink": {"n_rows": 32, "pct_rows_moved": 100.0, "mean_shrink_r": 0.4613, "r_p05": 0.2587, "r_p95": 0.6801, "target_sd_ratio": 0.4207}, "R2_eb_shrink_2k": {"n_rows": 32, "pct_rows_moved": 100.0, "mean_shrink_r": 0.3092, "r_p05": 0.1486, "r_p95": 0.5155, "target_sd_ratio": 0.2722}, "R3_shrink_to_level": {"n_rows": 32, "pct_rows_moved": 100.0, "mean_shrink_r": 0.4613, "r_p05": 0.2587, "r_p95": 0.6801, "target_sd_ratio": 0.4207}, "A_target_identity": {"n_rows": 32, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}, "A_shrink_constant": {"n_rows": 32, "pct_rows_moved": 100.0, "mean_shrink_r": 0.5306, "r_p05": 0.5306, "r_p95": 0.5306, "target_sd_ratio": 0.5306}, "A_shrink_full": {"n_rows": 32, "pct_rows_moved": 100.0, "mean_shrink_r": 0.0, "r_p05": 0.0, "r_p95": 0.0, "target_sd_ratio": 0.0}, "A_degenerate_mean": {"n_rows": 32, "pct_rows_moved": 0.0, "mean_shrink_r": 1.0, "r_p05": 1.0, "r_p95": 1.0, "target_sd_ratio": 1.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — level mix published beside every tercile read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|
|         0 |       58 |                               100 |        100 |
|         1 |       60 |                               100 |        100 |
|         2 |       33 |                               100 |        100 |

**Reasons**

- 🟡 no arm clears: best eligible `R3_shrink_to_level` MAE 0.02595 vs foil 0.02624 (1.10%, fold win rate 50%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)

**Binding constraint: the deflation gates — at least one arm would ship without them**

| metric        | arm                |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind                                                             |   folds_have |   folds_needed_BH |   folds_needed_DSR |   extra_seasons_needed |
|:--------------|:-------------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-----------------------------------------------------------------|-------------:|------------------:|-------------------:|-----------------------:|
| k_pct         | R2_eb_shrink_2k    |             1.476  |       0.909091  |     0.0144734 | True         | True              | False        | False        | True              | underpowered                                                     |           11 |                11 |                 14 |                      3 |
| bb_pct        | R1_eb_shrink       |             0.1274 |       0.363636  |     0.443239  | True         | False             | False        | False        | False             | underpowered                                                     |           11 |              2166 |                nan |                   2155 |
| hr_rate       | R1_eb_shrink       |            -1.3341 |       0.0909091 |     0.953228  | False        | False             | True         | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan |                    nan |
| gb_pct        | R1_eb_shrink       |            -0.5031 |       0.272727  |     0.869742  | False        | False             | True         | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan |                    nan |
| xwoba_against | R3_shrink_to_level |             1.0972 |       0.5       |     0.299041  | True         | False             | False        | False        | False             | underpowered                                                     |            4 |                52 |                 17 |                     48 |

## Registered but NOT run — the 'more data, not more statistics' alternative

The other way to de-noise a label is a LONGER label window (3-4 MLB seasons instead of 2). It is excluded for a stated reason rather than overlooked: a longer window changes the LABELLED POPULATION (the newest cohorts no longer have a complete label), so the arms would be scored on different players and the comparison would not be an ablation. Doing it honestly needs a pairs rebuild per window plus a population intersection — a separate slice with its own operator build.


- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

