# E7.15 H3 — player-level structure (pitcher side)

_generated 2026-08-02T05:12:30.528285+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> Pre-registration (written before any arm was scored): `e7_15_h3_preregistration.md`.

> ⚠️ **A projection, not an edge claim.**

## 1. The premise, measured before any score

The training matrix is one row per (player, level) and **every one of a player's rows carries the same MLB label**, so the fit treats a four-level player as four independent observations.

|   n_rows |   n_players |   mean_rows_per_player | rows_per_player_hist             |   pct_rows_poolable |   pct_players_poolable | effective_n_is_players_not_rows               |   pct_weight_from_top_42pct_players |   n_cohorts |
|---------:|------------:|-----------------------:|:---------------------------------|--------------------:|-----------------------:|:----------------------------------------------|------------------------------------:|------------:|
|     3031 |        1048 |                  2.892 | {1: 166, 2: 199, 3: 265, 4: 418} |               94.52 |                  84.16 | 1048 players vs 3031 rows (2.89x replication) |                               57.34 |          12 |

⚠️ **This is an EFFICIENCY question, not a leakage bug.** Folds are MLB debut cohorts and `debut_cohort` is a per-PLAYER join, so all of a player's rows share one fold and no player straddles the train/test boundary. What is at stake is only whose line the coefficients are fitted to.


## 2. Verdicts

| metric        | verdict   | winner   | best_arm       |   pct_lift_vs_foil | BH-FDR   |   PBO(eligible) | DSR(eligible)   |
|:--------------|:----------|:---------|:---------------|-------------------:|:---------|----------------:|:----------------|
| k_pct         | DROP      | L0_foil  | P4_re_dedup    |              1.713 | False    |       0.0571429 |                 |
| bb_pct        | DROP      | L0_foil  | P4_re_dedup    |              0.438 | False    |       0.914286  |                 |
| hr_rate       | DROP      | L0_foil  | P4_re_dedup    |              0.107 | False    |       0.771429  |                 |
| gb_pct        | DROP      | L0_foil  | T1_traj_ladder |              1.209 | False    |       0         |                 |
| xwoba_against | BLOCKED   | L0_foil  | P4_re_dedup    |              0.773 | False    |       0.833333  |                 |

## 3. ⭐ The decomposition — where does the incumbent's skill live?

`P3_player_re` was **pre-registered to lose**: with a label constant within a player, a player intercept absorbs the between-player variation and leaves the fixed effects identified by within-player contrasts alone, which is the variation H1 already found null. Its margin is therefore a MEASUREMENT, not a miss.

| metric        |   P3_lift_vs_foil_pct |   shuffled_minus_true_pct |   ladder_contribution_to_traj_pct |
|:--------------|----------------------:|--------------------------:|----------------------------------:|
| k_pct         |                 1.686 |                    -5.721 |                             0.138 |
| bb_pct        |                -0.027 |                    -4.486 |                             0.214 |
| hr_rate       |                 0.021 |                    -5.4   |                            -0.209 |
| gb_pct        |                -6.222 |                     5.232 |                             0.062 |
| xwoba_against |                 0.656 |                     0     |                             0     |

- **`shuffled_minus_true`** > 0 means the SHUFFLED grouping scored better than the true one — i.e. whatever a player block buys is block-width regularization, not 'players'.

- **`ladder_contribution_to_traj`** > 0 means H1's ladder made the within-player difference more informative than the raw difference. H1's null was about the ladder as a FEATURE ADJUSTMENT; this is a different use of it and is re-tested here rather than inherited.


## k_pct

_shipped foil: `baseline` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| P4_re_dedup       | player | True         | True     | 0.0350106 |         1.71299    |       0.818182  |     0.0467305 |           100    |               872 |           0.767442 |            1.53488 |
| P3_player_re      | player | True         | True     | 0.0350202 |         1.68613    |       0.909091  |     0.056318  |            90.22 |               872 |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.0356208 |         0          |       0         |   nan         |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0356208 |         0          |       0         |   nan         |             0    |               nan |           1        |            1       |
| P2_dedup_sqrt     | player | True         | True     | 0.0356225 |        -0.00464894 |       0.545455  |     0.515007  |           100    |               nan |           0.89046  |            1.2593  |
| P1_dedup          | player | True         | True     | 0.0356458 |        -0.070132   |       0.454545  |     0.620028  |           100    |               nan |           0.767442 |            1.53488 |
| A_traj_shuffled   | anchor | False        | True     | 0.0356542 |        -0.0936699  |       0.454545  |     0.743198  |            68.89 |               nan |         nan        |          nan       |
| T1_traj_ladder    | player | True         | True     | 0.0357124 |        -0.257138   |       0.545455  |     0.692596  |            68.89 |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.0357617 |        -0.395572   |       0.545455  |     0.758837  |            68.89 |               nan |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0358676 |        -0.692666   |       0.454545  |     0.935431  |            47.42 |               nan |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0370581 |        -4.03498    |       0.0909091 |     0.999918  |            90.22 |               872 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0373594 |        -4.88088    |       0.181818  |     0.977395  |             0    |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 2035, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.7674418604651162, "weight_ratio_p95": 1.5348837209302324, "n_rows": 2035, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.8904601219422841, "weight_ratio_p95": 1.259300781203178, "n_rows": 2035, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "P4_re_dedup": {"weight_ratio_p05": 0.7674418604651162, "weight_ratio_p95": 1.5348837209302324, "n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.035712129945037745, "traj_p95": 0.05357220318983374, "n_rows": 2035, "pct_rows_moved": 68.89}, "T2_traj_raw": {"traj_p05": -0.09766668155939646, "traj_p95": 0.0771543823335037, "n_rows": 2035, "pct_rows_moved": 68.89}, "T3_tenure": {"pct_repeated_a_level": 47.42, "n_rows": 2035, "pct_rows_moved": 47.42}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 2035, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "A_traj_shuffled": {"traj_p05": -0.062017292288184984, "traj_p95": 0.056199758815140916, "n_rows": 2035, "pct_rows_moved": 68.89}, "A_degenerate_mean": {"n_rows": 2035, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              93.1 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              93.3 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              90.3 |       29.6 |     28.7 |       24.8 |       17   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 394 | 0.0404243 |         -4.93394   |
| A_degenerate_mean |         1 | 725 | 0.0374441 |         -3.5177    |
| A_degenerate_mean |         2 | 855 | 0.0373613 |         -8.24766   |
| A_re_shuffled     |         0 | 394 | 0.0386357 |         -0.290893  |
| A_re_shuffled     |         1 | 725 | 0.0382838 |         -5.83914   |
| A_re_shuffled     |         2 | 855 | 0.0358483 |         -3.86399   |
| A_traj_shuffled   |         0 | 394 | 0.0385665 |         -0.111218  |
| A_traj_shuffled   |         1 | 725 | 0.036186  |         -0.0395773 |
| A_traj_shuffled   |         2 | 855 | 0.0345851 |         -0.20406   |
| A_weight_identity |         0 | 394 | 0.0385236 |          0         |
| A_weight_identity |         1 | 725 | 0.0361717 |          0         |
| A_weight_identity |         2 | 855 | 0.0345147 |          0         |
| L0_foil           |         0 | 394 | 0.0385236 |          0         |
| L0_foil           |         1 | 725 | 0.0361717 |          0         |
| L0_foil           |         2 | 855 | 0.0345147 |          0         |
| P1_dedup          |         0 | 394 | 0.0384935 |          0.0782604 |
| P1_dedup          |         1 | 725 | 0.0361555 |          0.0446052 |
| P1_dedup          |         2 | 855 | 0.0345063 |          0.0242154 |
| P2_dedup_sqrt     |         0 | 394 | 0.0384872 |          0.0945711 |
| P2_dedup_sqrt     |         1 | 725 | 0.0361373 |          0.0949209 |
| P2_dedup_sqrt     |         2 | 855 | 0.034509  |          0.0164477 |
| P3_player_re      |         0 | 394 | 0.038396  |          0.331296  |
| P3_player_re      |         1 | 725 | 0.0352408 |          2.57351   |
| P3_player_re      |         2 | 855 | 0.0341938 |          0.929639  |
| P4_re_dedup       |         0 | 394 | 0.0383734 |          0.389984  |
| P4_re_dedup       |         1 | 725 | 0.0352786 |          2.46911   |
| P4_re_dedup       |         2 | 855 | 0.0341356 |          1.09817   |
| T1_traj_ladder    |         0 | 394 | 0.0387002 |         -0.4583    |
| T1_traj_ladder    |         1 | 725 | 0.0361274 |          0.122334  |
| T1_traj_ladder    |         2 | 855 | 0.0346453 |         -0.378568  |
| T2_traj_raw       |         0 | 394 | 0.0387311 |         -0.538597  |
| T2_traj_raw       |         1 | 725 | 0.0361845 |         -0.0355028 |
| T2_traj_raw       |         2 | 855 | 0.0346979 |         -0.530866  |
| T3_tenure         |         0 | 394 | 0.0384653 |          0.151342  |
| T3_tenure         |         1 | 725 | 0.036567  |         -1.09296   |
| T3_tenure         |         2 | 855 | 0.0347243 |         -0.60723   |

**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.518 < 0.95 (n_trials=7). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## bb_pct

_shipped foil: `park:exposure+levelenv+rel:1k+w:mlb_pa` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| P4_re_dedup       | player | True         | True     | 0.0189875 |          0.438126  |       0.545455  |      0.327934 |           100    |               872 |           0.311761 |            2.57626 |
| P1_dedup          | player | True         | True     | 0.0190003 |          0.371056  |       0.636364  |      0.137936 |           100    |               nan |           0.311761 |            2.57626 |
| P2_dedup_sqrt     | player | True         | True     | 0.0190263 |          0.234837  |       0.636364  |      0.107294 |           100    |               nan |           0.366023 |            2.44193 |
| L0_foil           | foil   | False        | True     | 0.0190711 |          0         |       0         |    nan        |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0190711 |          0         |       0         |    nan        |             0    |               nan |           0.387543 |            2.25484 |
| P3_player_re      | player | True         | True     | 0.0190763 |         -0.0273107 |       0.454545  |      0.510564 |            90.22 |               872 |         nan        |          nan       |
| T1_traj_ladder    | player | True         | True     | 0.019135  |         -0.335158  |       0.727273  |      0.604542 |            68.89 |               nan |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0191426 |         -0.374987  |       0.363636  |      0.954144 |            47.42 |               nan |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | True     | 0.0191538 |         -0.433729  |       0.363636  |      0.870048 |            68.89 |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.0191759 |         -0.549406  |       0.818182  |      0.63245  |            68.89 |               nan |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0199319 |         -4.51368   |       0.181818  |      0.993675 |            90.22 |               872 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0212479 |        -11.414     |       0.0909091 |      0.999382 |             0    |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 2035, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.3117609090784933, "weight_ratio_p95": 2.576256814555611, "n_rows": 2035, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.36602347172563726, "weight_ratio_p95": 2.441929847704469, "n_rows": 2035, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "P4_re_dedup": {"weight_ratio_p05": 0.3117609090784933, "weight_ratio_p95": 2.576256814555611, "n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.019433630435345687, "traj_p95": 0.016917611852982174, "n_rows": 2035, "pct_rows_moved": 68.89}, "T2_traj_raw": {"traj_p05": -0.027381787430513865, "traj_p95": 0.02826338505538313, "n_rows": 2035, "pct_rows_moved": 68.89}, "T3_tenure": {"pct_repeated_a_level": 47.42, "n_rows": 2035, "pct_rows_moved": 47.42}, "A_weight_identity": {"weight_ratio_p05": 0.3875427953844386, "weight_ratio_p95": 2.2548382929959554, "n_rows": 2035, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "A_traj_shuffled": {"traj_p05": -0.017310981806480767, "traj_p95": 0.021881164950939825, "n_rows": 2035, "pct_rows_moved": 68.89}, "A_degenerate_mean": {"n_rows": 2035, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              93.1 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              93.3 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              90.3 |       29.6 |     28.7 |       24.8 |       17   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 394 | 0.0217342 |        -16.559     |
| A_degenerate_mean |         1 | 725 | 0.021142  |        -13.0728    |
| A_degenerate_mean |         2 | 855 | 0.0202762 |         -6.82573   |
| A_re_shuffled     |         0 | 394 | 0.01988   |         -6.615     |
| A_re_shuffled     |         1 | 725 | 0.0195424 |         -4.51766   |
| A_re_shuffled     |         2 | 855 | 0.0198182 |         -4.41296   |
| A_traj_shuffled   |         0 | 394 | 0.0189723 |         -1.74723   |
| A_traj_shuffled   |         1 | 725 | 0.018718  |         -0.108512  |
| A_traj_shuffled   |         2 | 855 | 0.0189679 |          0.0669212 |
| A_weight_identity |         0 | 394 | 0.0186465 |          0         |
| A_weight_identity |         1 | 725 | 0.0186977 |          0         |
| A_weight_identity |         2 | 855 | 0.0189806 |          0         |
| L0_foil           |         0 | 394 | 0.0186465 |          0         |
| L0_foil           |         1 | 725 | 0.0186977 |          0         |
| L0_foil           |         2 | 855 | 0.0189806 |          0         |
| P1_dedup          |         0 | 394 | 0.0185692 |          0.414295  |
| P1_dedup          |         1 | 725 | 0.0185782 |          0.639004  |
| P1_dedup          |         2 | 855 | 0.018945  |          0.187637  |
| P2_dedup_sqrt     |         0 | 394 | 0.0185936 |          0.283392  |
| P2_dedup_sqrt     |         1 | 725 | 0.0186317 |          0.352745  |
| P2_dedup_sqrt     |         2 | 855 | 0.0189529 |          0.145823  |
| P3_player_re      |         0 | 394 | 0.0189198 |         -1.46596   |
| P3_player_re      |         1 | 725 | 0.0188016 |         -0.555879  |
| P3_player_re      |         2 | 855 | 0.0187973 |          0.965591  |
| P4_re_dedup       |         0 | 394 | 0.0188072 |         -0.861973  |
| P4_re_dedup       |         1 | 725 | 0.0186341 |          0.340101  |
| P4_re_dedup       |         2 | 855 | 0.0187706 |          1.10667   |
| T1_traj_ladder    |         0 | 394 | 0.0189548 |         -1.65371   |
| T1_traj_ladder    |         1 | 725 | 0.0186668 |          0.165026  |
| T1_traj_ladder    |         2 | 855 | 0.0189068 |          0.388701  |
| T2_traj_raw       |         0 | 394 | 0.0190793 |         -2.32131   |
| T2_traj_raw       |         1 | 725 | 0.0186037 |          0.502657  |
| T2_traj_raw       |         2 | 855 | 0.0189523 |          0.148997  |
| T3_tenure         |         0 | 394 | 0.0187901 |         -0.770422  |
| T3_tenure         |         1 | 725 | 0.0187382 |         -0.216503  |
| T3_tenure         |         2 | 855 | 0.0190247 |         -0.232068  |

**Reasons**

- 🟡 no arm clears: best eligible `P4_re_dedup` MAE 0.01899 vs foil 0.01907 (0.44%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## hr_rate

_shipped foil: `park:exposure+levelenv+rel:1k+w:mlb_pa` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |    oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|-----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| P4_re_dedup       | player | True         | True     | 0.00976396 |          0.106521  |       0.545455  |      0.361029 |           100    |               872 |           0.311761 |            2.57626 |
| P2_dedup_sqrt     | player | True         | True     | 0.00977127 |          0.0317372 |       0.636364  |      0.386045 |           100    |               nan |           0.366023 |            2.44193 |
| P3_player_re      | player | True         | True     | 0.00977234 |          0.0207165 |       0.545455  |      0.474542 |            90.22 |               872 |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.00977309 |          0.0130464 |       0.454545  |      0.477108 |            68.89 |               nan |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.00977437 |          0         |       0         |    nan        |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.00977437 |          0         |       0         |    nan        |             0    |               nan |           0.387543 |            2.25484 |
| P1_dedup          | player | True         | True     | 0.00977975 |         -0.0550373 |       0.545455  |      0.609123 |           100    |               nan |           0.311761 |            2.57626 |
| T1_traj_ladder    | player | True         | True     | 0.0097935  |         -0.195786  |       0.454545  |      0.917935 |            68.89 |               nan |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | True     | 0.00980937 |         -0.358066  |       0.0909091 |      0.999427 |            68.89 |               nan |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.00991537 |         -1.44261   |       0.0909091 |      0.996466 |            47.42 |               nan |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.00992128 |         -1.50304   |       0.181818  |      0.975152 |             0    |               nan |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0103001  |         -5.37879   |       0.181818  |      0.998329 |            90.22 |               872 |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 2035, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.3117609090784933, "weight_ratio_p95": 2.576256814555611, "n_rows": 2035, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.36602347172563726, "weight_ratio_p95": 2.441929847704469, "n_rows": 2035, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "P4_re_dedup": {"weight_ratio_p05": 0.3117609090784933, "weight_ratio_p95": 2.576256814555611, "n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.00436034774433883, "traj_p95": 0.0023041216525962554, "n_rows": 2035, "pct_rows_moved": 68.89}, "T2_traj_raw": {"traj_p05": -0.00412468198976162, "traj_p95": 0.010895120214210085, "n_rows": 2035, "pct_rows_moved": 68.89}, "T3_tenure": {"pct_repeated_a_level": 47.42, "n_rows": 2035, "pct_rows_moved": 47.42}, "A_weight_identity": {"weight_ratio_p05": 0.3875427953844386, "weight_ratio_p95": 2.2548382929959554, "n_rows": 2035, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "A_traj_shuffled": {"traj_p05": -0.002274600254036154, "traj_p95": 0.0020451864317681616, "n_rows": 2035, "pct_rows_moved": 68.89}, "A_degenerate_mean": {"n_rows": 2035, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              93.1 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              93.3 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              90.3 |       29.6 |     28.7 |       24.8 |       17   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |        mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|-----------:|-------------------:|
| A_degenerate_mean |         0 | 394 | 0.0100812  |        -3.57601    |
| A_degenerate_mean |         1 | 725 | 0.0101173  |        -1.01357    |
| A_degenerate_mean |         2 | 855 | 0.00941977 |        -0.24116    |
| A_re_shuffled     |         0 | 394 | 0.0101906  |        -4.6996     |
| A_re_shuffled     |         1 | 725 | 0.0104533  |        -4.36776    |
| A_re_shuffled     |         2 | 855 | 0.00998684 |        -6.27572    |
| A_traj_shuffled   |         0 | 394 | 0.00980539 |        -0.742047   |
| A_traj_shuffled   |         1 | 725 | 0.010041   |        -0.251943   |
| A_traj_shuffled   |         2 | 855 | 0.00941766 |        -0.218711   |
| A_weight_identity |         0 | 394 | 0.00973317 |         0          |
| A_weight_identity |         1 | 725 | 0.0100158  |         0          |
| A_weight_identity |         2 | 855 | 0.0093971  |         0          |
| L0_foil           |         0 | 394 | 0.00973317 |         0          |
| L0_foil           |         1 | 725 | 0.0100158  |         0          |
| L0_foil           |         2 | 855 | 0.0093971  |         0          |
| P1_dedup          |         0 | 394 | 0.00974096 |        -0.0800047  |
| P1_dedup          |         1 | 725 | 0.0100032  |         0.126276   |
| P1_dedup          |         2 | 855 | 0.00942087 |        -0.2529     |
| P2_dedup_sqrt     |         0 | 394 | 0.00972887 |         0.0442169  |
| P2_dedup_sqrt     |         1 | 725 | 0.0100031  |         0.127204   |
| P2_dedup_sqrt     |         2 | 855 | 0.00940354 |        -0.0684486  |
| P3_player_re      |         0 | 394 | 0.00974609 |        -0.132703   |
| P3_player_re      |         1 | 725 | 0.0100135  |         0.022936   |
| P3_player_re      |         2 | 855 | 0.00934547 |         0.54943    |
| P4_re_dedup       |         0 | 394 | 0.00973277 |         0.00411533 |
| P4_re_dedup       |         1 | 725 | 0.00999758 |         0.181965   |
| P4_re_dedup       |         2 | 855 | 0.0093464  |         0.539594   |
| T1_traj_ladder    |         0 | 394 | 0.00981516 |        -0.842408   |
| T1_traj_ladder    |         1 | 725 | 0.010027   |        -0.111837   |
| T1_traj_ladder    |         2 | 855 | 0.00940051 |        -0.0362397  |
| T2_traj_raw       |         0 | 394 | 0.00979431 |        -0.628214   |
| T2_traj_raw       |         1 | 725 | 0.0100145  |         0.0134043  |
| T2_traj_raw       |         2 | 855 | 0.00938259 |         0.154459   |
| T3_tenure         |         0 | 394 | 0.0101403  |        -4.18294    |
| T3_tenure         |         1 | 725 | 0.0100689  |        -0.530518   |
| T3_tenure         |         2 | 855 | 0.00949095 |        -0.998633   |

**Reasons**

- 🟡 no arm clears: best eligible `P4_re_dedup` MAE 0.00976 vs foil 0.00977 (0.11%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## gb_pct

_shipped foil: `baseline` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| T1_traj_ladder    | player | True         | True     | 0.0472568 |           1.20883  |       0.818182  |     0.0961093 |            68.89 |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.0472865 |           1.14675  |       0.818182  |     0.0963243 |            68.89 |               nan |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.0478351 |           0        |       0         |   nan         |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0478351 |           0        |       0         |   nan         |             0    |               nan |           1        |            1       |
| P2_dedup_sqrt     | player | True         | True     | 0.0479522 |          -0.244991 |       0.181818  |     0.984748  |           100    |               nan |           0.89046  |            1.2593  |
| P1_dedup          | player | True         | True     | 0.048089  |          -0.530975 |       0.181818  |     0.991674  |           100    |               nan |           0.767442 |            1.53488 |
| A_traj_shuffled   | anchor | False        | True     | 0.0480963 |          -0.546192 |       0.363636  |     0.803082  |            68.89 |               nan |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0483085 |          -0.989681 |       0.181818  |     0.914294  |            90.22 |               872 |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0483876 |          -1.15517  |       0.454545  |     0.844341  |            47.42 |               nan |         nan        |          nan       |
| P4_re_dedup       | player | True         | True     | 0.0502058 |          -4.95606  |       0.0909091 |     0.996821  |           100    |               872 |           0.767442 |            1.53488 |
| P3_player_re      | player | True         | True     | 0.0508113 |          -6.22196  |       0.0909091 |     0.997974  |            90.22 |               872 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0573124 |         -19.8125   |       0         |     0.999983  |             0    |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 2035, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.7674418604651162, "weight_ratio_p95": 1.5348837209302324, "n_rows": 2035, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.8904601219422841, "weight_ratio_p95": 1.259300781203178, "n_rows": 2035, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "P4_re_dedup": {"weight_ratio_p05": 0.7674418604651162, "weight_ratio_p95": 1.5348837209302324, "n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.07769781793449801, "traj_p95": 0.08798651869563419, "n_rows": 2035, "pct_rows_moved": 68.89}, "T2_traj_raw": {"traj_p05": -0.13389761604260478, "traj_p95": 0.11706056218740342, "n_rows": 2035, "pct_rows_moved": 68.89}, "T3_tenure": {"pct_repeated_a_level": 47.42, "n_rows": 2035, "pct_rows_moved": 47.42}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 2035, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 872, "pct_rows_poolable": 90.22, "n_rows": 2035, "pct_rows_moved": 90.22}, "A_traj_shuffled": {"traj_p05": -0.11227159332156908, "traj_p95": 0.10168204719246914, "n_rows": 2035, "pct_rows_moved": 68.89}, "A_degenerate_mean": {"n_rows": 2035, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              93.1 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              93.3 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              90.3 |       29.6 |     28.7 |       24.8 |       17   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 394 | 0.0581643 |        -19.9018    |
| A_degenerate_mean |         1 | 725 | 0.0573355 |        -20.7791    |
| A_degenerate_mean |         2 | 855 | 0.0598343 |        -20.7753    |
| A_re_shuffled     |         0 | 394 | 0.0488853 |         -0.773676  |
| A_re_shuffled     |         1 | 725 | 0.048356  |         -1.86343   |
| A_re_shuffled     |         2 | 855 | 0.0500474 |         -1.02045   |
| A_traj_shuffled   |         0 | 394 | 0.0488079 |         -0.614101  |
| A_traj_shuffled   |         1 | 725 | 0.0478368 |         -0.769758  |
| A_traj_shuffled   |         2 | 855 | 0.0496487 |         -0.215793  |
| A_weight_identity |         0 | 394 | 0.04851   |          0         |
| A_weight_identity |         1 | 725 | 0.0474714 |          0         |
| A_weight_identity |         2 | 855 | 0.0495418 |          0         |
| L0_foil           |         0 | 394 | 0.04851   |          0         |
| L0_foil           |         1 | 725 | 0.0474714 |          0         |
| L0_foil           |         2 | 855 | 0.0495418 |          0         |
| P1_dedup          |         0 | 394 | 0.0488803 |         -0.763453  |
| P1_dedup          |         1 | 725 | 0.0479003 |         -0.903424  |
| P1_dedup          |         2 | 855 | 0.0496164 |         -0.150552  |
| P2_dedup_sqrt     |         0 | 394 | 0.0486713 |         -0.33254   |
| P2_dedup_sqrt     |         1 | 725 | 0.0476904 |         -0.461347  |
| P2_dedup_sqrt     |         2 | 855 | 0.0495633 |         -0.0432913 |
| P3_player_re      |         0 | 394 | 0.0518767 |         -6.94034   |
| P3_player_re      |         1 | 725 | 0.0509476 |         -7.32275   |
| P3_player_re      |         2 | 855 | 0.0524107 |         -5.79091   |
| P4_re_dedup       |         0 | 394 | 0.0511956 |         -5.53628   |
| P4_re_dedup       |         1 | 725 | 0.0502947 |         -5.94744   |
| P4_re_dedup       |         2 | 855 | 0.0517714 |         -4.50029   |
| T1_traj_ladder    |         0 | 394 | 0.0486885 |         -0.368077  |
| T1_traj_ladder    |         1 | 725 | 0.0469157 |          1.17069   |
| T1_traj_ladder    |         2 | 855 | 0.0490425 |          1.0079    |
| T2_traj_raw       |         0 | 394 | 0.0489807 |         -0.970331  |
| T2_traj_raw       |         1 | 725 | 0.0468825 |          1.24043   |
| T2_traj_raw       |         2 | 855 | 0.0489425 |          1.20981   |
| T3_tenure         |         0 | 394 | 0.0492609 |         -1.548     |
| T3_tenure         |         1 | 725 | 0.047818  |         -0.730115  |
| T3_tenure         |         2 | 855 | 0.0499497 |         -0.823202  |

**Reasons**

- ⛔ MECHANISM REFUTED (scoped to `P3_player_re`) — `A_re_shuffled` (the SHUFFLED player grouping — same block width, same group-size multiset, wrong grouping) systematically beat `P3_player_re` (11/11 folds, p=0.004). Whatever a player random intercept buys is extra regularization at that block width, not anything to do with players — so it would not transfer to a differently-shaped cohort. That arm is disqualified from selection; other mechanisms on this metric are untouched.
- ⛔ DEFLATION — DSR over the eligible trial set is 0.078 < 0.95 (n_trials=7). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## xwoba_against

_shipped foil: `baseline` · prior_scale 2.0 · 4 folds [2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| P4_re_dedup       | player | True         | True     | 0.0260375 |        0.773212    |            0.75 |      0.242796 |           100    |               183 |           0.882637 |            1.17685 |
| A_re_shuffled     | anchor | False        | False    | 0.0260683 |        0.655914    |            0.5  |      0.2391   |             0    |               183 |         nan        |          nan       |
| P3_player_re      | player | True         | False    | 0.0260683 |        0.655914    |            0.5  |      0.2391   |             0    |               183 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0261087 |        0.501599    |            0.5  |      0.367211 |             0    |               nan |         nan        |          nan       |
| P1_dedup          | player | True         | True     | 0.0261753 |        0.247911    |            0.75 |      0.298892 |           100    |               nan |           0.882637 |            1.17685 |
| P2_dedup_sqrt     | player | True         | True     | 0.0262028 |        0.143022    |            0.75 |      0.280042 |           100    |               nan |           0.943814 |            1.08982 |
| T1_traj_ladder    | player | True         | False    | 0.0262404 |        3.30545e-15 |            0.25 |      0.195501 |             0    |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | False    | 0.0262404 |        3.30545e-15 |            0.25 |      0.195501 |             0    |               nan |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | False    | 0.0262404 |        3.30545e-15 |            0.25 |      0.195501 |             0    |               nan |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.0262404 |        0           |            0    |    nan        |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0262404 |        0           |            0    |    nan        |             0    |               nan |           1        |            1       |
| T3_tenure         | player | True         | True     | 0.0265503 |       -1.1811      |            0.25 |      0.81309  |            69.95 |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 183, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.8826366559485531, "weight_ratio_p95": 1.1768488745980707, "n_rows": 183, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.943814491836561, "weight_ratio_p95": 1.0898231018538167, "n_rows": 183, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 183, "pct_rows_poolable": 0.0, "n_rows": 183, "pct_rows_moved": 0.0}, "P4_re_dedup": {"weight_ratio_p05": 0.8826366559485531, "weight_ratio_p95": 1.1768488745980707, "n_player_blocks": 183, "pct_rows_poolable": 0.0, "n_rows": 183, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": 0.0, "traj_p95": 0.0, "n_rows": 183, "pct_rows_moved": 0.0}, "T2_traj_raw": {"traj_p05": 0.0, "traj_p95": 0.0, "n_rows": 183, "pct_rows_moved": 0.0}, "T3_tenure": {"pct_repeated_a_level": 69.95, "n_rows": 183, "pct_rows_moved": 69.95}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 183, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 183, "pct_rows_poolable": 0.0, "n_rows": 183, "pct_rows_moved": 0.0}, "A_traj_shuffled": {"traj_p05": 0.0, "traj_p95": 0.0, "n_rows": 183, "pct_rows_moved": 0.0}, "A_degenerate_mean": {"n_rows": 183, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|
|         0 |       58 |                              72.7 |        100 |
|         1 |       60 |                              72.7 |        100 |
|         2 |       33 |                              72.7 |        100 |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 |  58 | 0.0249258 |       -1.17371     |
| A_degenerate_mean |         1 |  60 | 0.022893  |        3.68694     |
| A_degenerate_mean |         2 |  33 | 0.0252924 |        0.373913    |
| A_re_shuffled     |         0 |  58 | 0.0246477 |       -0.0447857   |
| A_re_shuffled     |         1 |  60 | 0.0233457 |        1.78267     |
| A_re_shuffled     |         2 |  33 | 0.0250529 |        1.31738     |
| A_traj_shuffled   |         0 |  58 | 0.0246367 |        1.16544e-14 |
| A_traj_shuffled   |         1 |  60 | 0.0237694 |       -3.89234e-15 |
| A_traj_shuffled   |         2 |  33 | 0.0253874 |       -6.62596e-15 |
| A_weight_identity |         0 |  58 | 0.0246367 |        0           |
| A_weight_identity |         1 |  60 | 0.0237694 |        0           |
| A_weight_identity |         2 |  33 | 0.0253874 |        0           |
| L0_foil           |         0 |  58 | 0.0246367 |        0           |
| L0_foil           |         1 |  60 | 0.0237694 |        0           |
| L0_foil           |         2 |  33 | 0.0253874 |        0           |
| P1_dedup          |         0 |  58 | 0.0246343 |        0.00956904  |
| P1_dedup          |         1 |  60 | 0.0236483 |        0.509721    |
| P1_dedup          |         2 |  33 | 0.0252818 |        0.415629    |
| P2_dedup_sqrt     |         0 |  58 | 0.0246342 |        0.0101217   |
| P2_dedup_sqrt     |         1 |  60 | 0.0237074 |        0.260708    |
| P2_dedup_sqrt     |         2 |  33 | 0.0253115 |        0.298671    |
| P3_player_re      |         0 |  58 | 0.0246477 |       -0.0447857   |
| P3_player_re      |         1 |  60 | 0.0233457 |        1.78267     |
| P3_player_re      |         2 |  33 | 0.0250529 |        1.31738     |
| P4_re_dedup       |         0 |  58 | 0.024627  |        0.0394472   |
| P4_re_dedup       |         1 |  60 | 0.0232745 |        2.08204     |
| P4_re_dedup       |         2 |  33 | 0.0250716 |        1.24368     |
| T1_traj_ladder    |         0 |  58 | 0.0246367 |        1.16544e-14 |
| T1_traj_ladder    |         1 |  60 | 0.0237694 |       -3.89234e-15 |
| T1_traj_ladder    |         2 |  33 | 0.0253874 |       -6.62596e-15 |
| T2_traj_raw       |         0 |  58 | 0.0246367 |        1.16544e-14 |
| T2_traj_raw       |         1 |  60 | 0.0237694 |       -3.89234e-15 |
| T2_traj_raw       |         2 |  33 | 0.0253874 |       -6.62596e-15 |
| T3_tenure         |         0 |  58 | 0.0245384 |        0.39898     |
| T3_tenure         |         1 |  60 | 0.0243618 |       -2.49238     |
| T3_tenure         |         2 |  33 | 0.0264186 |       -4.06216     |

**Reasons**

- fold 2023: ladder unavailable — trajectory arms degrade to RAW deltas
- fold 2024: ladder unavailable — trajectory arms degrade to RAW deltas
- fold 2025: ladder unavailable — trajectory arms degrade to RAW deltas
- fold 2026: ladder unavailable — trajectory arms degrade to RAW deltas
- ⛔ BLOCKED — anchor(s) ['A_re_shuffled', 'A_traj_shuffled'] RAN but moved ≤1.0% of rows, i.e. they are byte-identical to the foil. Their 'it lost' is a pass on NOTHING (NF1.7 (a)) — an inert anchor is more dangerous than a missing one because the report looks healthy. Fix the anchor before reading any verdict from this run.

## Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)

**Binding constraint: BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing**

| metric        | arm            |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind         |   folds_have |   folds_needed_BH |   folds_needed_DSR | unreachable_gates   |   extra_seasons_needed |
|:--------------|:---------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-------------|-------------:|------------------:|-------------------:|:--------------------|-----------------------:|
| k_pct         | P4_re_dedup    |             1.713  |        0.818182 |     0.0467305 | True         | True              | True         | False        | False             | underpowered |           11 |                17 |               2010 | []                  |                   1999 |
| bb_pct        | P4_re_dedup    |             0.4381 |        0.545455 |     0.327934  | True         | False             | False        | False        | False             | underpowered |           11 |               223 |                nan | ['DSR']             |                    nan |
| hr_rate       | P4_re_dedup    |             0.1065 |        0.545455 |     0.361029  | True         | False             | False        | False        | False             | underpowered |           11 |               350 |                nan | ['DSR']             |                    nan |
| gb_pct        | T1_traj_ladder |             1.2088 |        0.818182 |     0.0961093 | True         | True              | True         | False        | False             | underpowered |           11 |                27 |                nan | ['DSR']             |                    nan |
| xwoba_against | P4_re_dedup    |             0.7732 |        0.75     |     0.242796  | True         | True              | False        | False        | False             | underpowered |            4 |                30 |                nan | ['DSR']             |                    nan |

## Reading notes

- **`pct_rows_moved` is measured in EACH MECHANISM'S OWN UNITS.** H1 and H2 rewrote `minor_<metric>`, so 'did the arm act' was a feature diff. H3's weighting and random-effect arms move no feature value at all — a feature-diff activity check would report 0% for every one of them and the `must_move` guard would block the slice for the wrong reason. **The H2 inert-anchor lesson generalises: an inert-anchor guard is only as good as its activity metric.**

- **No new projector class.** The random intercept rides the slice-5 `bucket_col` machinery, which `clone_projector` already carries field-by-field. A subclass would be silently downgraded on every refit and would score AS THE FOIL under its own name (the E7.12-S5 landmine).

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

