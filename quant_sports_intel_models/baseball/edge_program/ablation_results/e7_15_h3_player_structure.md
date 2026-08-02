# E7.15 H3 — player-level structure (batter side)

_generated 2026-08-02T04:57:49.606003+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> Pre-registration (written before any arm was scored): `e7_15_h3_preregistration.md`.

> ⚠️ **A projection, not an edge claim.**

## 1. The premise, measured before any score

The training matrix is one row per (player, level) and **every one of a player's rows carries the same MLB label**, so the fit treats a four-level player as four independent observations.

|   n_rows |   n_players |   mean_rows_per_player | rows_per_player_hist            |   pct_rows_poolable |   pct_players_poolable | effective_n_is_players_not_rows              |   pct_weight_from_top_42pct_players |   n_cohorts |
|---------:|------------:|-----------------------:|:--------------------------------|--------------------:|-----------------------:|:---------------------------------------------|------------------------------------:|------------:|
|     2171 |         736 |                   2.95 | {1: 125, 2: 96, 3: 206, 4: 309} |               94.24 |                  83.02 | 736 players vs 2171 rows (2.95x replication) |                               56.93 |          12 |

⚠️ **This is an EFFICIENCY question, not a leakage bug.** Folds are MLB debut cohorts and `debut_cohort` is a per-PLAYER join, so all of a player's rows share one fold and no player straddles the train/test boundary. What is at stake is only whose line the coefficients are fitted to.


## 2. Verdicts

| metric   | verdict   | winner   | best_arm       |   pct_lift_vs_foil | BH-FDR   |   PBO(eligible) | DSR(eligible)   |
|:---------|:----------|:---------|:---------------|-------------------:|:---------|----------------:|:----------------|
| woba     | DROP      | L0_foil  | P3_player_re   |              0.841 | False    |       0.485714  |                 |
| k_pct    | DROP      | L0_foil  | T1_traj_ladder |              1.183 | False    |       0.171429  |                 |
| bb_pct   | DROP      | L0_foil  | T2_traj_raw    |              1.404 | True     |       0.0142857 |                 |
| iso      | DROP      | L0_foil  | T1_traj_ladder |              1.418 | True     |       0.0857143 |                 |

## 3. ⭐ The decomposition — where does the incumbent's skill live?

`P3_player_re` was **pre-registered to lose**: with a label constant within a player, a player intercept absorbs the between-player variation and leaves the fixed effects identified by within-player contrasts alone, which is the variation H1 already found null. Its margin is therefore a MEASUREMENT, not a miss.

| metric   |   P3_lift_vs_foil_pct |   shuffled_minus_true_pct |   ladder_contribution_to_traj_pct |
|:---------|----------------------:|--------------------------:|----------------------------------:|
| woba     |                 0.841 |                    -9.877 |                            -0.234 |
| k_pct    |                -2.81  |                     0.466 |                             0.069 |
| bb_pct   |                -1.505 |                    -6.41  |                            -0.177 |
| iso      |                -0.788 |                    -3.68  |                             0.071 |

- **`shuffled_minus_true`** > 0 means the SHUFFLED grouping scored better than the true one — i.e. whatever a player block buys is block-width regularization, not 'players'.

- **`ladder_contribution_to_traj`** > 0 means H1's ladder made the within-player difference more informative than the raw difference. H1's null was about the ladder as a FEATURE ADJUSTMENT; this is a different use of it and is re-tested here rather than inherited.


## woba

_shipped foil: `levelenv` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| P3_player_re      | player | True         | True     | 0.0285485 |          0.84066   |        0.636364 |      0.126808 |            94.21 |               661 |         nan        |          nan       |
| P4_re_dedup       | player | True         | True     | 0.0285549 |          0.818257  |        0.636364 |      0.133414 |           100    |               661 |           0.775301 |            1.5506  |
| L0_foil           | foil   | False        | True     | 0.0287905 |          0         |        0        |    nan        |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0287905 |          0         |        0        |    nan        |             0    |               nan |           1        |            1       |
| P2_dedup_sqrt     | player | True         | True     | 0.0288176 |         -0.0939041 |        0.545455 |      0.674102 |           100    |               nan |           0.895805 |            1.26686 |
| A_traj_shuffled   | anchor | False        | True     | 0.0288575 |         -0.232817  |        0.727273 |      0.648806 |            69.58 |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.028864  |         -0.255338  |        0.454545 |      0.693462 |            69.58 |               nan |         nan        |          nan       |
| P1_dedup          | player | True         | True     | 0.0288841 |         -0.325152  |        0.545455 |      0.791527 |           100    |               nan |           0.775301 |            1.5506  |
| T1_traj_ladder    | player | True         | True     | 0.0289315 |         -0.489738  |        0.545455 |      0.697022 |            69.58 |               nan |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0289659 |         -0.609223  |        0.454545 |      0.7026   |            41.2  |               nan |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0290349 |         -0.848671  |        0.363636 |      0.753329 |             0    |               nan |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0313921 |         -9.03613   |        0.181818 |      0.999493 |            94.21 |               661 |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 1762, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_rows": 1762, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.8958051161847487, "weight_ratio_p95": 1.2668597445516776, "n_rows": 1762, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "P4_re_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.025206007512587388, "traj_p95": 0.05043358491390914, "n_rows": 1762, "pct_rows_moved": 69.58}, "T2_traj_raw": {"traj_p05": -0.06945377805959647, "traj_p95": 0.07914629356153746, "n_rows": 1762, "pct_rows_moved": 69.58}, "T3_tenure": {"pct_repeated_a_level": 41.2, "n_rows": 1762, "pct_rows_moved": 41.2}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 1762, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "A_traj_shuffled": {"traj_p05": -0.08520783886519562, "traj_p95": 0.041892019120710694, "n_rows": 1762, "pct_rows_moved": 69.58}, "A_degenerate_mean": {"n_rows": 1762, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              93.8 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              93.4 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              91.3 |       26.3 |     27.5 |       25.2 |       21   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 162 | 0.0293231 |         -6.29602   |
| A_degenerate_mean |         1 | 570 | 0.0284659 |         -2.31955   |
| A_degenerate_mean |         2 | 962 | 0.0289721 |          1.26858   |
| A_re_shuffled     |         0 | 162 | 0.0292973 |         -6.20255   |
| A_re_shuffled     |         1 | 570 | 0.0301314 |         -8.30596   |
| A_re_shuffled     |         2 | 962 | 0.0325568 |        -10.9474    |
| A_traj_shuffled   |         0 | 162 | 0.0277999 |         -0.774371  |
| A_traj_shuffled   |         1 | 570 | 0.0277994 |          0.0762534 |
| A_traj_shuffled   |         2 | 962 | 0.0293312 |          0.0446248 |
| A_weight_identity |         0 | 162 | 0.0275863 |          0         |
| A_weight_identity |         1 | 570 | 0.0278206 |          0         |
| A_weight_identity |         2 | 962 | 0.0293443 |          0         |
| L0_foil           |         0 | 162 | 0.0275863 |          0         |
| L0_foil           |         1 | 570 | 0.0278206 |          0         |
| L0_foil           |         2 | 962 | 0.0293443 |          0         |
| P1_dedup          |         0 | 162 | 0.0276668 |         -0.291831  |
| P1_dedup          |         1 | 570 | 0.0279803 |         -0.574056  |
| P1_dedup          |         2 | 962 | 0.0294392 |         -0.323181  |
| P2_dedup_sqrt     |         0 | 162 | 0.0275939 |         -0.0274629 |
| P2_dedup_sqrt     |         1 | 570 | 0.027867  |         -0.166764  |
| P2_dedup_sqrt     |         2 | 962 | 0.0293883 |         -0.149864  |
| P3_player_re      |         0 | 162 | 0.028161  |         -2.0832    |
| P3_player_re      |         1 | 570 | 0.0279859 |         -0.594195  |
| P3_player_re      |         2 | 962 | 0.0287406 |          2.05731   |
| P4_re_dedup       |         0 | 162 | 0.0281537 |         -2.05677   |
| P4_re_dedup       |         1 | 570 | 0.0280096 |         -0.679429  |
| P4_re_dedup       |         2 | 962 | 0.0287616 |          1.98571   |
| T1_traj_ladder    |         0 | 162 | 0.0278488 |         -0.951493  |
| T1_traj_ladder    |         1 | 570 | 0.0279328 |         -0.403335  |
| T1_traj_ladder    |         2 | 962 | 0.0292625 |          0.279021  |
| T2_traj_raw       |         0 | 162 | 0.027887  |         -1.08997   |
| T2_traj_raw       |         1 | 570 | 0.0279633 |         -0.512742  |
| T2_traj_raw       |         2 | 962 | 0.0291999 |          0.492154  |
| T3_tenure         |         0 | 162 | 0.0284364 |         -3.08168   |
| T3_tenure         |         1 | 570 | 0.0280005 |         -0.646545  |
| T3_tenure         |         2 | 962 | 0.0291465 |          0.674079  |

**Reasons**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.486 ≥ 0.2. The contender spread is 0.848%, WIDE relative to the margin, and the in-sample winners are spread thinly (P3_player_re 40% (+0.000%), P4_re_dedup 34% (+0.023%), T3_tenure 13% (+1.462%)) — this is genuine instability, a search that learnt nothing, not a tie (NF1.8). Either way it does not ship.

## k_pct

_shipped foil: `park:exposure+levelenv+rel:0.5k` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| T1_traj_ladder    | player | True         | True     | 0.03798   |          1.18278   |       0.818182  |     0.0951929 |            69.58 |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.0380067 |          1.11338   |       0.818182  |     0.128824  |            69.58 |               nan |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0383719 |          0.163151  |       0.636364  |     0.393709  |            41.2  |               nan |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | True     | 0.0384294 |          0.0134277 |       0.636364  |     0.488439  |            69.58 |               nan |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.0384346 |          0         |       0         |   nan         |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0384346 |          0         |       0         |   nan         |             0    |               nan |           1        |            1       |
| P2_dedup_sqrt     | player | True         | True     | 0.0385259 |         -0.237505  |       0.454545  |     0.870349  |           100    |               nan |           0.895805 |            1.26686 |
| P1_dedup          | player | True         | True     | 0.0386649 |         -0.599209  |       0.181818  |     0.910652  |           100    |               nan |           0.775301 |            1.5506  |
| P4_re_dedup       | player | True         | True     | 0.0392049 |         -2.00437   |       0.454545  |     0.920321  |           100    |               661 |           0.775301 |            1.5506  |
| A_re_shuffled     | anchor | False        | True     | 0.0393355 |         -2.34409   |       0.0909091 |     0.986108  |            94.21 |               661 |         nan        |          nan       |
| P3_player_re      | player | True         | True     | 0.0395147 |         -2.81039   |       0.454545  |     0.943765  |            94.21 |               661 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0499488 |        -29.9579    |       0         |     0.999999  |             0    |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 1762, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_rows": 1762, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.8958051161847487, "weight_ratio_p95": 1.2668597445516776, "n_rows": 1762, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "P4_re_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.04700949562771686, "traj_p95": 0.043312966644280165, "n_rows": 1762, "pct_rows_moved": 69.58}, "T2_traj_raw": {"traj_p05": -0.05746588897825563, "traj_p95": 0.0585139784921803, "n_rows": 1762, "pct_rows_moved": 69.58}, "T3_tenure": {"pct_repeated_a_level": 41.2, "n_rows": 1762, "pct_rows_moved": 41.2}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 1762, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "A_traj_shuffled": {"traj_p05": -0.045690899411591566, "traj_p95": 0.05482127094965091, "n_rows": 1762, "pct_rows_moved": 69.58}, "A_degenerate_mean": {"n_rows": 1762, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              93.8 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              93.4 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              91.3 |       26.3 |     27.5 |       25.2 |       21   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 162 | 0.0479581 |        -39.7893    |
| A_degenerate_mean |         1 | 570 | 0.0494657 |        -31.1617    |
| A_degenerate_mean |         2 | 962 | 0.0495644 |        -27.5161    |
| A_re_shuffled     |         0 | 162 | 0.0345656 |         -0.752372  |
| A_re_shuffled     |         1 | 570 | 0.038465  |         -1.99262   |
| A_re_shuffled     |         2 | 962 | 0.0404879 |         -4.16451   |
| A_traj_shuffled   |         0 | 162 | 0.0340153 |          0.85141   |
| A_traj_shuffled   |         1 | 570 | 0.0379127 |         -0.528027  |
| A_traj_shuffled   |         2 | 962 | 0.0388911 |         -0.0565094 |
| A_weight_identity |         0 | 162 | 0.0343074 |          0         |
| A_weight_identity |         1 | 570 | 0.0377135 |          0         |
| A_weight_identity |         2 | 962 | 0.0388692 |          0         |
| L0_foil           |         0 | 162 | 0.0343074 |          0         |
| L0_foil           |         1 | 570 | 0.0377135 |          0         |
| L0_foil           |         2 | 962 | 0.0388692 |          0         |
| P1_dedup          |         0 | 162 | 0.0348186 |         -1.49009   |
| P1_dedup          |         1 | 570 | 0.037955  |         -0.640427  |
| P1_dedup          |         2 | 962 | 0.0389656 |         -0.248069  |
| P2_dedup_sqrt     |         0 | 162 | 0.034505  |         -0.575968  |
| P2_dedup_sqrt     |         1 | 570 | 0.0378014 |         -0.233001  |
| P2_dedup_sqrt     |         2 | 962 | 0.0389058 |         -0.0943139 |
| P3_player_re      |         0 | 162 | 0.0349125 |         -1.76354   |
| P3_player_re      |         1 | 570 | 0.038784  |         -2.83848   |
| P3_player_re      |         2 | 962 | 0.0401162 |         -3.2082    |
| P4_re_dedup       |         0 | 162 | 0.0347334 |         -1.24173   |
| P4_re_dedup       |         1 | 570 | 0.0383911 |         -1.79654   |
| P4_re_dedup       |         2 | 962 | 0.0396993 |         -2.13566   |
| T1_traj_ladder    |         0 | 162 | 0.0342498 |          0.167982  |
| T1_traj_ladder    |         1 | 570 | 0.0373074 |          1.07677   |
| T1_traj_ladder    |         2 | 962 | 0.0379787 |          2.29083   |
| T2_traj_raw       |         0 | 162 | 0.0341904 |          0.341171  |
| T2_traj_raw       |         1 | 570 | 0.0373979 |          0.836796  |
| T2_traj_raw       |         2 | 962 | 0.0379733 |          2.30473   |
| T3_tenure         |         0 | 162 | 0.0336901 |          1.79937   |
| T3_tenure         |         1 | 570 | 0.0383006 |         -1.55674   |
| T3_tenure         |         2 | 962 | 0.0384399 |          1.10452   |

**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.360 < 0.95 (n_trials=7). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## bb_pct

_shipped foil: `park:exposure+levelenv+rel:2k` · prior_scale 4.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| T2_traj_raw       | player | True         | True     | 0.0177052 |          1.40384   |       0.818182  |    0.00376528 |            69.58 |               nan |         nan        |          nan       |
| T1_traj_ladder    | player | True         | True     | 0.0177371 |          1.22644   |       0.909091  |    0.00393133 |            69.58 |               nan |         nan        |          nan       |
| A_traj_shuffled   | anchor | False        | True     | 0.0179539 |          0.0187547 |       0.454545  |    0.422456   |            69.58 |               nan |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.0179573 |          0         |       0         |  nan          |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0179573 |          0         |       0         |  nan          |             0    |               nan |           1        |            1       |
| P2_dedup_sqrt     | player | True         | True     | 0.0179956 |         -0.213452  |       0.454545  |    0.877965   |           100    |               nan |           0.895805 |            1.26686 |
| P1_dedup          | player | True         | True     | 0.0180476 |         -0.50275   |       0.363636  |    0.915863   |           100    |               nan |           0.775301 |            1.5506  |
| T3_tenure         | player | True         | True     | 0.0180613 |         -0.579206  |       0.454545  |    0.851406   |            41.2  |               nan |         nan        |          nan       |
| P4_re_dedup       | player | True         | True     | 0.0181798 |         -1.23924   |       0.363636  |    0.819521   |           100    |               661 |           0.775301 |            1.5506  |
| P3_player_re      | player | True         | True     | 0.0182276 |         -1.50538   |       0.363636  |    0.814313   |            94.21 |               661 |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0193786 |         -7.91508   |       0.0909091 |    0.999984   |            94.21 |               661 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0207667 |        -15.645     |       0.0909091 |    0.999826   |             0    |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 1762, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_rows": 1762, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.8958051161847487, "weight_ratio_p95": 1.2668597445516776, "n_rows": 1762, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "P4_re_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.014298912940636012, "traj_p95": 0.01833434182156876, "n_rows": 1762, "pct_rows_moved": 69.58}, "T2_traj_raw": {"traj_p05": -0.027722784294269262, "traj_p95": 0.024655420088300635, "n_rows": 1762, "pct_rows_moved": 69.58}, "T3_tenure": {"pct_repeated_a_level": 41.2, "n_rows": 1762, "pct_rows_moved": 41.2}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 1762, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "A_traj_shuffled": {"traj_p05": -0.011952486809500684, "traj_p95": 0.012527313216880415, "n_rows": 1762, "pct_rows_moved": 69.58}, "A_degenerate_mean": {"n_rows": 1762, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              93.8 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              93.4 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              91.3 |       26.3 |     27.5 |       25.2 |       21   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 162 | 0.0213478 |        -36.9897    |
| A_degenerate_mean |         1 | 570 | 0.0217226 |        -23.685     |
| A_degenerate_mean |         2 | 962 | 0.0203096 |        -10.633     |
| A_re_shuffled     |         0 | 162 | 0.017063  |         -9.49453   |
| A_re_shuffled     |         1 | 570 | 0.0190684 |         -8.57222   |
| A_re_shuffled     |         2 | 962 | 0.019659  |         -7.08868   |
| A_traj_shuffled   |         0 | 162 | 0.015535  |          0.311079  |
| A_traj_shuffled   |         1 | 570 | 0.0175452 |          0.100313  |
| A_traj_shuffled   |         2 | 962 | 0.018374  |         -0.0891038 |
| A_weight_identity |         0 | 162 | 0.0155835 |          0         |
| A_weight_identity |         1 | 570 | 0.0175629 |          0         |
| A_weight_identity |         2 | 962 | 0.0183577 |          0         |
| L0_foil           |         0 | 162 | 0.0155835 |          0         |
| L0_foil           |         1 | 570 | 0.0175629 |          0         |
| L0_foil           |         2 | 962 | 0.0183577 |          0         |
| P1_dedup          |         0 | 162 | 0.0155759 |          0.0486405 |
| P1_dedup          |         1 | 570 | 0.0177154 |         -0.868792  |
| P1_dedup          |         2 | 962 | 0.0184197 |         -0.3377    |
| P2_dedup_sqrt     |         0 | 162 | 0.0155751 |          0.0534672 |
| P2_dedup_sqrt     |         1 | 570 | 0.0176289 |         -0.375987  |
| P2_dedup_sqrt     |         2 | 962 | 0.0183793 |         -0.117689  |
| P3_player_re      |         0 | 162 | 0.0160966 |         -3.29297   |
| P3_player_re      |         1 | 570 | 0.018277  |         -4.06608   |
| P3_player_re      |         2 | 962 | 0.0185229 |         -0.899911  |
| P4_re_dedup       |         0 | 162 | 0.01595   |         -2.35191   |
| P4_re_dedup       |         1 | 570 | 0.018163  |         -3.41705   |
| P4_re_dedup       |         2 | 962 | 0.0184826 |         -0.680629  |
| T1_traj_ladder    |         0 | 162 | 0.015393  |          1.22233   |
| T1_traj_ladder    |         1 | 570 | 0.0172848 |          1.58298   |
| T1_traj_ladder    |         2 | 962 | 0.0180781 |          1.52279   |
| T2_traj_raw       |         0 | 162 | 0.0153865 |          1.26425   |
| T2_traj_raw       |         1 | 570 | 0.017258  |          1.73579   |
| T2_traj_raw       |         2 | 962 | 0.0180305 |          1.7822    |
| T3_tenure         |         0 | 162 | 0.0159768 |         -2.52393   |
| T3_tenure         |         1 | 570 | 0.0175009 |          0.352615  |
| T3_tenure         |         2 | 962 | 0.0185117 |         -0.839172  |

**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.607 < 0.95 (n_trials=7). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## iso

_shipped foil: `park:exposure+levelenv+rel:2k` · prior_scale 2.0 · 11 folds [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]_

| arm               | kind   | selectable   | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   n_player_blocks |   weight_ratio_p05 |   weight_ratio_p95 |
|:------------------|:-------|:-------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|------------------:|-------------------:|-------------------:|
| T1_traj_ladder    | player | True         | True     | 0.0379241 |           1.41832  |       0.818182  |    0.00647658 |            69.58 |               nan |         nan        |          nan       |
| T2_traj_raw       | player | True         | True     | 0.0379515 |           1.34701  |       0.818182  |    0.0124312  |            69.58 |               nan |         nan        |          nan       |
| L0_foil           | foil   | False        | True     | 0.0384697 |           0        |       0         |  nan          |             0    |               nan |         nan        |          nan       |
| A_weight_identity | anchor | False        | False    | 0.0384697 |           0        |       0         |  nan          |             0    |               nan |           1        |            1       |
| P2_dedup_sqrt     | player | True         | True     | 0.0385207 |          -0.132617 |       0.454545  |    0.752741   |           100    |               nan |           0.895805 |            1.26686 |
| A_traj_shuffled   | anchor | False        | True     | 0.0385671 |          -0.253267 |       0.272727  |    0.828503   |            69.58 |               nan |         nan        |          nan       |
| P4_re_dedup       | player | True         | True     | 0.0385696 |          -0.259631 |       0.545455  |    0.583692   |           100    |               661 |           0.775301 |            1.5506  |
| P1_dedup          | player | True         | True     | 0.0386016 |          -0.342884 |       0.454545  |    0.791992   |           100    |               nan |           0.775301 |            1.5506  |
| P3_player_re      | player | True         | True     | 0.0387728 |          -0.788008 |       0.363636  |    0.71305    |            94.21 |               661 |         nan        |          nan       |
| T3_tenure         | player | True         | True     | 0.0391883 |          -1.86813  |       0.363636  |    0.891037   |            41.2  |               nan |         nan        |          nan       |
| A_re_shuffled     | anchor | False        | True     | 0.0401884 |          -4.46781  |       0.0909091 |    0.99976    |            94.21 |               661 |         nan        |          nan       |
| A_degenerate_mean | anchor | False        | True     | 0.0431384 |         -12.1362   |       0.0909091 |    0.999271   |             0    |               nan |         nan        |          nan       |

**Anchors**


**Coverage (the mechanism's OWN units)**: {"L0_foil": {"n_rows": 1762, "pct_rows_moved": 0.0}, "P1_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_rows": 1762, "pct_rows_moved": 100.0}, "P2_dedup_sqrt": {"weight_ratio_p05": 0.8958051161847487, "weight_ratio_p95": 1.2668597445516776, "n_rows": 1762, "pct_rows_moved": 100.0}, "P3_player_re": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "P4_re_dedup": {"weight_ratio_p05": 0.7753006746846582, "weight_ratio_p95": 1.5506013493693165, "n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 100.0}, "T1_traj_ladder": {"traj_p05": -0.021611745602428893, "traj_p95": 0.035171654414088684, "n_rows": 1762, "pct_rows_moved": 69.58}, "T2_traj_raw": {"traj_p05": -0.028706384214492574, "traj_p95": 0.05622621444487493, "n_rows": 1762, "pct_rows_moved": 69.58}, "T3_tenure": {"pct_repeated_a_level": 41.2, "n_rows": 1762, "pct_rows_moved": 41.2}, "A_weight_identity": {"weight_ratio_p05": 1.0, "weight_ratio_p95": 1.0, "n_rows": 1762, "pct_rows_moved": 0.0}, "A_re_shuffled": {"n_player_blocks": 661, "pct_rows_poolable": 94.21, "n_rows": 1762, "pct_rows_moved": 94.21}, "A_traj_shuffled": {"traj_p05": -0.021053843026691537, "traj_p95": 0.01927447519218634, "n_rows": 1762, "pct_rows_moved": 69.58}, "A_degenerate_mean": {"n_rows": 1762, "pct_rows_moved": 0.0}}


**Propensity-tercile composition** (the E7.15-H1 correction — the low tercile is the one richest in Triple-A rows, so its level mix is published beside every stratified read):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              93.8 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              93.4 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              91.3 |       26.3 |     27.5 |       25.2 |       21   |

**Stratified lift, MOVED ROWS ONLY** (H5):

| arm               |   stratum |   n |       mae |   pct_lift_vs_foil |
|:------------------|----------:|----:|----------:|-------------------:|
| A_degenerate_mean |         0 | 162 | 0.044562  |         -13.3059   |
| A_degenerate_mean |         1 | 570 | 0.0432509 |         -18.3898   |
| A_degenerate_mean |         2 | 962 | 0.0431926 |         -10.6361   |
| A_re_shuffled     |         0 | 162 | 0.0388733 |           1.15845  |
| A_re_shuffled     |         1 | 570 | 0.0380303 |          -4.09949  |
| A_re_shuffled     |         2 | 962 | 0.0412077 |          -5.55194  |
| A_traj_shuffled   |         0 | 162 | 0.0394476 |          -0.30185  |
| A_traj_shuffled   |         1 | 570 | 0.0366291 |          -0.263978 |
| A_traj_shuffled   |         2 | 962 | 0.0391139 |          -0.188679 |
| A_weight_identity |         0 | 162 | 0.0393289 |           0        |
| A_weight_identity |         1 | 570 | 0.0365327 |           0        |
| A_weight_identity |         2 | 962 | 0.0390402 |           0        |
| L0_foil           |         0 | 162 | 0.0393289 |           0        |
| L0_foil           |         1 | 570 | 0.0365327 |           0        |
| L0_foil           |         2 | 962 | 0.0390402 |           0        |
| P1_dedup          |         0 | 162 | 0.0401332 |          -2.04495  |
| P1_dedup          |         1 | 570 | 0.0368493 |          -0.86683  |
| P1_dedup          |         2 | 962 | 0.0388937 |           0.375259 |
| P2_dedup_sqrt     |         0 | 162 | 0.0396815 |          -0.896617 |
| P2_dedup_sqrt     |         1 | 570 | 0.0366738 |          -0.386299 |
| P2_dedup_sqrt     |         2 | 962 | 0.0389561 |           0.215384 |
| P3_player_re      |         0 | 162 | 0.0394173 |          -0.224635 |
| P3_player_re      |         1 | 570 | 0.0380304 |          -4.09978  |
| P3_player_re      |         2 | 962 | 0.0394021 |          -0.927032 |
| P4_re_dedup       |         0 | 162 | 0.0395636 |          -0.596817 |
| P4_re_dedup       |         1 | 570 | 0.0377601 |          -3.35982  |
| P4_re_dedup       |         2 | 962 | 0.0390936 |          -0.136729 |
| T1_traj_ladder    |         0 | 162 | 0.0387743 |           1.41014  |
| T1_traj_ladder    |         1 | 570 | 0.0360368 |           1.35736  |
| T1_traj_ladder    |         2 | 962 | 0.038442  |           1.53245  |
| T2_traj_raw       |         0 | 162 | 0.0390117 |           0.806631 |
| T2_traj_raw       |         1 | 570 | 0.0362507 |           0.771701 |
| T2_traj_raw       |         2 | 962 | 0.0383532 |           1.75979  |
| T3_tenure         |         0 | 162 | 0.0409268 |          -4.06275  |
| T3_tenure         |         1 | 570 | 0.0370578 |          -1.43738  |
| T3_tenure         |         2 | 962 | 0.0394757 |          -1.11554  |

**Reasons**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.657 < 0.95 (n_trials=7). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## Null analysis — does the verdict rest on our own gate choice? (NF-D15 g″)

**Binding constraint: the deflation gates — at least one arm would ship without them**

| metric   | arm            |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind         |   folds_have |   folds_needed_BH |   folds_needed_DSR |   extra_seasons_needed |
|:---------|:---------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-------------|-------------:|------------------:|-------------------:|-----------------------:|
| woba     | P3_player_re   |             0.8407 |        0.636364 |    0.126808   | True         | True              | False        | False        | False             | underpowered |           11 |                32 |                nan |                     21 |
| k_pct    | T1_traj_ladder |             1.1828 |        0.818182 |    0.0951929  | True         | True              | True         | False        | False             | underpowered |           11 |                24 |                nan |                     13 |
| bb_pct   | T2_traj_raw    |             1.4038 |        0.818182 |    0.00376528 | True         | True              | True         | False        | True              | underpowered |           11 |                11 |                140 |                    129 |
| iso      | T1_traj_ladder |             1.4183 |        0.818182 |    0.00647658 | True         | True              | True         | False        | True              | underpowered |           11 |                11 |                120 |                    109 |

## Reading notes

- **`pct_rows_moved` is measured in EACH MECHANISM'S OWN UNITS.** H1 and H2 rewrote `minor_<metric>`, so 'did the arm act' was a feature diff. H3's weighting and random-effect arms move no feature value at all — a feature-diff activity check would report 0% for every one of them and the `must_move` guard would block the slice for the wrong reason. **The H2 inert-anchor lesson generalises: an inert-anchor guard is only as good as its activity metric.**

- **No new projector class.** The random intercept rides the slice-5 `bucket_col` machinery, which `clone_projector` already carries field-by-field. A subclass would be silently downgraded on every refit and would score AS THE FOIL under its own name (the E7.12-S5 landmine).

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

