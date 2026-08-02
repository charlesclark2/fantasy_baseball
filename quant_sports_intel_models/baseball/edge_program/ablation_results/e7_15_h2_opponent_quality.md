# E7.15 H2 — the opponent / competition-quality adjustment (batter side)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": "leave-one-MLB-debut-cohort-out (n_cohorts)",
 "gates": null,
 "n_arms": 4,
 "n_folds": 11,
 "per_metric": [
  {
   "dsr": 0.2527384109963111,
   "fold_win_rate": 0.6363636363636364,
   "metric": "woba",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.4857142857142857,
   "verdict": "DROP"
  },
  {
   "dsr": 0.2265436986176793,
   "fold_win_rate": 0.5454545454545454,
   "metric": "k_pct",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.4857142857142857,
   "verdict": "DROP"
  },
  {
   "dsr": 0.6310296279230753,
   "fold_win_rate": 0.6363636363636364,
   "metric": "bb_pct",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.7714285714285715,
   "verdict": "DROP"
  },
  {
   "dsr": 0.34856890330823664,
   "fold_win_rate": 0.7272727272727273,
   "metric": "iso",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.6,
   "verdict": "DROP"
  }
 ],
 "primary_contrast": "paired-t",
 "reason": null,
 "schema": 1,
 "source_artifact": "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts/e7_15_h2_summary.json",
 "status": "recovered",
 "verdict": "woba=DROP, k_pct=DROP, bb_pct=DROP, iso=DROP"
}
-->


_generated 2026-08-02T04:05:04.665173+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> ⚠️ **A projection, not an edge claim.** H2 tests an assertion that has been sitting untested under a shipped feature: `build_park_context.py` says the park factor's residual is "the park (plus the opponent mix, **which averages out** over a 3-season window)". This slice measures the player-level version of that claim and only then asks whether correcting for it helps.

> ⚠️ **Whose claim, precisely.** The park docstring's parenthesis is about the PARK bucket's opponent mix. H2 measures the PLAYER's strength of schedule — the sibling quantity, and the one that could actually bias a translation. They are not the same claim and are not reported as if they were.

## 1. ⭐ The measurement — does the competition a prospect faced actually vary?

This is the primary deliverable and it is worth having whichever way the bake-off lands.


**Observed spread of the per-player opponent factor**

| metric   |   n_players |     p5 |    p50 |    p95 |   p95_minus_p5_pct |   sd_pct |   pct_players_beyond_1pct |   pct_players_beyond_3pct |
|:---------|------------:|-------:|-------:|-------:|-------------------:|---------:|--------------------------:|--------------------------:|
| woba     |       20573 | 0.977  | 0.9993 | 1.0212 |               4.41 |    1.448 |                      32.3 |                       5.4 |
| k_pct    |       20573 | 0.9645 | 0.9978 | 1.0306 |               6.61 |    2.173 |                      49.3 |                      12   |
| bb_pct   |       20573 | 0.948  | 0.9962 | 1.0436 |               9.56 |    3.131 |                      64.4 |                      23.1 |
| iso      |       20573 | 0.943  | 0.9958 | 1.0491 |              10.61 |    3.475 |                      67.5 |                      26.6 |

**Is that spread real, or is it the estimator?** Split-half reliability: the player's opponents are split into two halves, a factor is built on each, and the halves are correlated across players (Spearman-Brown to full length).

| metric   |   n_players |   half_corr |   reliability_spearman_brown |   signal_share_of_sd | level    | variant                             | player_type   |   window |
|:---------|------------:|------------:|-----------------------------:|---------------------:|:---------|:------------------------------------|:--------------|---------:|
| woba     |        3981 |     -0.0002 |                      -0.0004 |               0      | Triple-A | league_normalised (headline)        | batter        |        1 |
| k_pct    |        3981 |     -0.0295 |                      -0.0609 |               0      | Triple-A | league_normalised (headline)        | batter        |        1 |
| bb_pct   |        3981 |     -0.0657 |                      -0.1407 |               0      | Triple-A | league_normalised (headline)        | batter        |        1 |
| iso      |        3981 |      0.0192 |                       0.0376 |               0.194  | Triple-A | league_normalised (headline)        | batter        |        1 |
| woba     |        3981 |      0.5035 |                       0.6697 |               0.8184 | Triple-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| k_pct    |        3981 |      0.7385 |                       0.8496 |               0.9217 | Triple-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| bb_pct   |        3981 |      0.0866 |                       0.1594 |               0.3992 | Triple-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| iso      |        3981 |      0.5557 |                       0.7144 |               0.8452 | Triple-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| woba     |        4569 |     -0.1528 |                      -0.3606 |               0      | Double-A | league_normalised (headline)        | batter        |        1 |
| k_pct    |        4569 |     -0.1565 |                      -0.3712 |               0      | Double-A | league_normalised (headline)        | batter        |        1 |
| bb_pct   |        4569 |     -0.2088 |                      -0.5277 |               0      | Double-A | league_normalised (headline)        | batter        |        1 |
| iso      |        4569 |     -0.1315 |                      -0.3028 |               0      | Double-A | league_normalised (headline)        | batter        |        1 |
| woba     |        4569 |      0.2438 |                       0.3921 |               0.6261 | Double-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| k_pct    |        4569 |      0.2168 |                       0.3564 |               0.597  | Double-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| bb_pct   |        4569 |      0.2325 |                       0.3773 |               0.6143 | Double-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| iso      |        4569 |      0.2282 |                       0.3717 |               0.6096 | Double-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| woba     |        4898 |     -0.1315 |                      -0.3028 |               0      | High-A   | league_normalised (headline)        | batter        |        1 |
| k_pct    |        4898 |     -0.1923 |                      -0.4763 |               0      | High-A   | league_normalised (headline)        | batter        |        1 |
| bb_pct   |        4898 |     -0.2782 |                      -0.7708 |               0      | High-A   | league_normalised (headline)        | batter        |        1 |
| iso      |        4898 |     -0.1026 |                      -0.2288 |               0      | High-A   | league_normalised (headline)        | batter        |        1 |
| woba     |        4898 |      0.4122 |                       0.5838 |               0.7641 | High-A   | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| k_pct    |        4898 |      0.4472 |                       0.6181 |               0.7862 | High-A   | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| bb_pct   |        4898 |      0.0502 |                       0.0957 |               0.3093 | High-A   | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| iso      |        4898 |      0.6674 |                       0.8006 |               0.8947 | High-A   | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| woba     |        5581 |     -0.2685 |                      -0.734  |               0      | Single-A | league_normalised (headline)        | batter        |        1 |
| k_pct    |        5581 |     -0.2424 |                      -0.64   |               0      | Single-A | league_normalised (headline)        | batter        |        1 |
| bb_pct   |        5581 |     -0.2355 |                      -0.6161 |               0      | Single-A | league_normalised (headline)        | batter        |        1 |
| iso      |        5581 |     -0.2505 |                      -0.6684 |               0      | Single-A | league_normalised (headline)        | batter        |        1 |
| woba     |        5581 |      0.2795 |                       0.4369 |               0.661  | Single-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| k_pct    |        5581 |     -0.0272 |                      -0.0559 |               0      | Single-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| bb_pct   |        5581 |      0.2215 |                       0.3627 |               0.6022 | Single-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |
| iso      |        5581 |      0.3193 |                       0.4841 |               0.6958 | Single-A | level_normalised (POSITIVE CONTROL) | batter        |        1 |

⚠️ **This estimator has a KNOWN DOWNWARD BIAS and is a ONE-SIDED instrument.** A league plays a roughly BALANCED schedule, so a player's two halves are mechanically ANTI-correlated when there is no real signal — which is why the league-normalised readings come back NEGATIVE rather than 0. The negativity is itself the fingerprint of a balanced schedule. It can support "there is no LARGE within-league component"; it cannot be quoted as a precise reliability.


**The POSITIVE CONTROL** is what makes the near-zero reading mean anything (NF1.7 (a)): the SAME estimator on the SAME rows reads high for the LEVEL-normalised factor, whose large between-league component is shared by both halves and so escapes the fixed-sum constraint.


**How much of the factor is a LEAGUE effect the model already has?** E7.3 fits a per-league random intercept, so any part of the factor that is constant within a league is NOT new information — it is a re-encoding of a shipped feature, and a lift on it would be unattributable to opponent quality. This table is why the headline arm is league-normalised.

| metric   | variant                      |   total_sd_pct |   between_league_sd_pct |   within_league_sd_pct |   between_league_share_pct | player_type   |
|:---------|:-----------------------------|---------------:|------------------------:|-----------------------:|---------------------------:|:--------------|
| woba     | level_normalised             |          2.191 |                   1.383 |                  1.7   |                       39.8 | batter        |
| woba     | league_normalised (headline) |          1.445 |                   0.103 |                  1.442 |                        0.5 | batter        |
| k_pct    | level_normalised             |          3.728 |                   2.384 |                  2.866 |                       40.9 | batter        |
| k_pct    | league_normalised (headline) |          2.181 |                   0.216 |                  2.17  |                        1   | batter        |
| bb_pct   | level_normalised             |          4.174 |                   1.84  |                  3.747 |                       19.4 | batter        |
| bb_pct   | league_normalised (headline) |          3.131 |                   0.264 |                  3.12  |                        0.7 | batter        |
| iso      | level_normalised             |          6.058 |                   3.884 |                  4.649 |                       41.1 | batter        |
| iso      | league_normalised (headline) |          3.481 |                   0.187 |                  3.476 |                        0.3 | batter        |

## 2. Verdict by metric

| metric   | verdict   | winner   | best_arm         |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | BH-FDR   |   PBO(eligible) |   DSR(eligible) |
|:---------|:----------|:---------|:-----------------|-------------------:|----------------:|--------------:|:---------|----------------:|----------------:|
| woba     | DROP      | L0_foil  | O2_opp_levelnorm |              0.039 |        0.636364 |      0.404852 | False    |        0.485714 |        0.252738 |
| k_pct    | DROP      | L0_foil  | O4_opp_extra     |              0.065 |        0.545455 |      0.143183 | False    |        0.485714 |        0.226544 |
| bb_pct   | DROP      | L0_foil  | O2_opp_levelnorm |              0.255 |        0.636364 |      0.205445 | False    |        0.771429 |        0.63103  |
| iso      | DROP      | L0_foil  | O4_opp_extra     |              0.036 |        0.727273 |      0.337638 | False    |        0.6      |        0.348569 |

## 2b. ⭐ Reading the null honestly — is it the data, or is it my gate?

Re-deciding the entire run with the deflation gates REMOVED — no PBO ceiling, no DSR floor — leaves survivors: **NONE**. ⇒ BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing (family of 4; strictest BH rung p ≤ 0.025).

| metric   | arm              |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind         |   folds_have |   folds_needed_BH |   folds_needed_DSR |   extra_seasons_needed |
|:---------|:-----------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-------------|-------------:|------------------:|-------------------:|-----------------------:|
| woba     | O2_opp_levelnorm |             0.0393 |        0.636364 |      0.404852 | True         | True              | False        | False        | False             | underpowered |           11 |               694 |               1231 |                   1220 |
| k_pct    | O4_opp_extra     |             0.0652 |        0.545455 |      0.143183 | True         | False             | False        | False        | False             | underpowered |           11 |                36 |                 38 |                     27 |
| bb_pct   | O2_opp_levelnorm |             0.2553 |        0.636364 |      0.205445 | True         | True              | False        | False        | False             | underpowered |           11 |                60 |                 70 |                     59 |
| iso      | O4_opp_extra     |             0.0359 |        0.727273 |      0.337638 | True         | True              | False        | False        | False             | underpowered |           11 |               230 |                348 |                    337 |

## 3.woba — the arm set (`partial_pool@4`, context `levelenv`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| O2_opp_levelnorm  | opponent | True     |  0.028779 |           0.039317 |        0.636364 |      0.404852 |            96.84 |      0.96525 |      1.03551 |
| L0_foil           | foil     | True     |  0.028791 |           0        |        0        |    nan        |             0    |      1       |      1       |
| A_opp_placebo     | anchor   | True     |  0.028803 |          -0.042742 |        0.454545 |      0.697899 |            96.71 |      0.97705 |      1.02113 |
| O4_opp_extra      | opponent | True     |  0.028824 |          -0.114602 |        0.363636 |      0.832673 |            96.64 |      0.97705 |      1.02113 |
| A_opp_noloo       | anchor   | True     |  0.028829 |          -0.134051 |        0.454545 |      0.869809 |            96.68 |      0.97722 |      1.02152 |
| O1_opp_leaguenorm | opponent | True     |  0.028843 |          -0.183767 |        0.363636 |      0.935502 |            96.64 |      0.97705 |      1.02113 |
| O3_opp_window3    | opponent | True     |  0.028848 |          -0.201218 |        0.363636 |      0.945704 |            96.67 |      0.97671 |      1.02144 |
| A_degenerate_mean | anchor   | True     |  0.029035 |          -0.848671 |        0.363636 |      0.753329 |             0    |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 4/11 folds, p=0.7705623194258079, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 3/11 folds, p=0.6964915620737449, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 3/11 folds, p=0.8841782151266371, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              85.7 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              85.7 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              85.7 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |             -6.296 |             -2.32  |              1.269 |
| A_opp_noloo       |             -0.045 |             -0.101 |             -0.032 |
| A_opp_placebo     |              0.291 |              0.296 |             -0.34  |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.172 |             -0.141 |             -0.082 |
| O2_opp_levelnorm  |              0.003 |              0.277 |              0.051 |
| O3_opp_window3    |             -0.174 |             -0.161 |             -0.105 |
| O4_opp_extra      |              0.034 |             -0.383 |             -0.054 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |             -6.296 |             -2.32  |              1.269 |
| A_opp_noloo       |             -0.045 |             -0.101 |             -0.032 |
| A_opp_placebo     |              0.291 |              0.296 |             -0.34  |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.172 |             -0.141 |             -0.082 |
| O2_opp_levelnorm  |              0.003 |              0.277 |              0.051 |
| O3_opp_window3    |             -0.174 |             -0.161 |             -0.105 |
| O4_opp_extra      |              0.034 |             -0.383 |             -0.054 |

**Deflation** — PBO(eligible) `0.4857142857142857` · Bailey OS degradation `0.127%` · contender spread `0.154%` · whole-field spread `0.241%`


**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.486 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.154% and the in-sample halves split across arms a fraction of a percent apart (O2_opp_levelnorm 56% (+0.000%), L0_foil 32% (+0.039%), O4_opp_extra 12% (+0.154%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 3.k_pct — the arm set (`partial_pool@2`, context `park:exposure+levelenv+rel:0.5k`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| O4_opp_extra      | opponent | True     |  0.03841  |           0.065186 |        0.545455 |      0.143183 |              100 |      0.96444 |      1.03046 |
| L0_foil           | foil     | True     |  0.038435 |           0        |        0        |    nan        |                0 |      1       |      1       |
| O2_opp_levelnorm  | opponent | True     |  0.038436 |          -0.0028   |        0.545455 |      0.502769 |              100 |      0.9428  |      1.05742 |
| A_opp_noloo       | anchor   | True     |  0.038499 |          -0.166821 |        0.272727 |      0.879612 |              100 |      0.96491 |      1.02991 |
| O1_opp_leaguenorm | opponent | True     |  0.038525 |          -0.235106 |        0.181818 |      0.964885 |              100 |      0.96444 |      1.03046 |
| O3_opp_window3    | opponent | True     |  0.038536 |          -0.26471  |        0.363636 |      0.98026  |              100 |      0.96413 |      1.03096 |
| A_opp_placebo     | anchor   | True     |  0.038605 |          -0.442688 |        0.363636 |      0.983726 |              100 |      0.96444 |      1.03046 |
| A_degenerate_mean | anchor   | True     |  0.049949 |         -29.9579   |        0        |      0.999999 |                0 |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 0/11 folds, p=0.9999985625554062, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 4/11 folds, p=0.990590247765317, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 4/11 folds, p=0.8872036680328557, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              85.7 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              85.7 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              85.7 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -39.789 |            -31.162 |            -27.516 |
| A_opp_noloo       |             -0.163 |              0.086 |             -0.381 |
| A_opp_placebo     |             -1.293 |              0.194 |             -0.637 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.406 |              0.069 |             -0.433 |
| O2_opp_levelnorm  |             -0.349 |              0.202 |             -0.02  |
| O3_opp_window3    |             -0.573 |              0.058 |             -0.439 |
| O4_opp_extra      |              0.034 |             -0.054 |              0.135 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -39.789 |            -31.162 |            -27.516 |
| A_opp_noloo       |             -0.163 |              0.086 |             -0.381 |
| A_opp_placebo     |             -1.293 |              0.194 |             -0.637 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.406 |              0.069 |             -0.433 |
| O2_opp_levelnorm  |             -0.349 |              0.202 |             -0.02  |
| O3_opp_window3    |             -0.573 |              0.058 |             -0.439 |
| O4_opp_extra      |              0.034 |             -0.054 |              0.135 |

**Deflation** — PBO(eligible) `0.4857142857142857` · Bailey OS degradation `0.2775%` · contender spread `0.068%` · whole-field spread `0.33%`


**Reading**

- 🟡 no arm clears: best eligible `O4_opp_extra` MAE 0.03841 vs foil 0.03843 (0.07%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.bb_pct — the arm set (`partial_pool@4`, context `park:exposure+levelenv+rel:2k`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| A_opp_noloo       | anchor   | True     |  0.017884 |           0.408611 |        0.545455 |      0.047742 |              100 |      0.94844 |      1.04402 |
| O2_opp_levelnorm  | opponent | True     |  0.017911 |           0.255299 |        0.636364 |      0.205445 |              100 |      0.92989 |      1.06439 |
| O1_opp_leaguenorm | opponent | True     |  0.017923 |           0.192713 |        0.545455 |      0.187404 |              100 |      0.94802 |      1.04342 |
| O3_opp_window3    | opponent | True     |  0.017935 |           0.122546 |        0.545455 |      0.298092 |              100 |      0.94759 |      1.04414 |
| L0_foil           | foil     | True     |  0.017957 |           0        |        0        |    nan        |                0 |      1       |      1       |
| O4_opp_extra      | opponent | True     |  0.017971 |          -0.074816 |        0.636364 |      0.56321  |              100 |      0.94802 |      1.04342 |
| A_opp_placebo     | anchor   | True     |  0.01802  |          -0.35133  |        0.181818 |      0.764439 |              100 |      0.94802 |      1.04342 |
| A_degenerate_mean | anchor   | True     |  0.020767 |         -15.645    |        0.090909 |      0.999826 |                0 |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 1/11 folds, p=0.9997995782628578, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 4/11 folds, p=0.8759362693478564, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 7/11 folds, p=0.29001067552839693, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              85.7 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              85.7 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              85.7 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -36.99  |            -23.685 |            -10.633 |
| A_opp_noloo       |              0.359 |              0.489 |              0.307 |
| A_opp_placebo     |             -0.951 |             -0.006 |             -0.472 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.363 |              0.254 |              0.214 |
| O2_opp_levelnorm  |             -0.676 |              0.504 |              0.444 |
| O3_opp_window3    |             -0.358 |              0.2   |              0.167 |
| O4_opp_extra      |             -1.968 |              0.144 |              0.133 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -36.99  |            -23.685 |            -10.633 |
| A_opp_noloo       |              0.359 |              0.489 |              0.307 |
| A_opp_placebo     |             -0.951 |             -0.006 |             -0.472 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.363 |              0.254 |              0.214 |
| O2_opp_levelnorm  |             -0.676 |              0.504 |              0.444 |
| O3_opp_window3    |             -0.358 |              0.2   |              0.167 |
| O4_opp_extra      |             -1.968 |              0.144 |              0.133 |

**Deflation** — PBO(eligible) `0.7714285714285715` · Bailey OS degradation `0.2898%` · contender spread `0.133%` · whole-field spread `0.331%`


**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.771 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.133% and the in-sample halves split across arms a fraction of a percent apart (O2_opp_levelnorm 50% (+0.000%), O4_opp_extra 21% (+0.331%), O1_opp_leaguenorm 16% (+0.063%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 3.iso — the arm set (`partial_pool@2`, context `park:exposure+levelenv+rel:2k`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| O4_opp_extra      | opponent | True     |  0.038456 |           0.035912 |        0.727273 |      0.337638 |            99.63 |      0.94312 |      1.04907 |
| L0_foil           | foil     | True     |  0.03847  |           0        |        0        |    nan        |             0    |      1       |      1       |
| A_opp_noloo       | anchor   | True     |  0.038548 |          -0.203507 |        0.363636 |      0.884055 |            99.63 |      0.94317 |      1.04801 |
| O2_opp_levelnorm  | opponent | True     |  0.038564 |          -0.244704 |        0.363636 |      0.706921 |            99.63 |      0.90791 |      1.10344 |
| O3_opp_window3    | opponent | True     |  0.038568 |          -0.256723 |        0.272727 |      0.834784 |            99.63 |      0.94222 |      1.04964 |
| O1_opp_leaguenorm | opponent | True     |  0.038595 |          -0.325791 |        0.181818 |      0.909491 |            99.63 |      0.94312 |      1.04907 |
| A_opp_placebo     | anchor   | True     |  0.038756 |          -0.744674 |        0.272727 |      0.950496 |            99.63 |      0.94312 |      1.04907 |
| A_degenerate_mean | anchor   | True     |  0.043138 |         -12.1362   |        0.090909 |      0.999271 |             0    |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 1/11 folds, p=0.9993033899235519, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 2/11 folds, p=0.954466349968596, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 4/11 folds, p=0.8428777022459404, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              85.7 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              85.7 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              85.7 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -13.306 |            -18.39  |            -10.636 |
| A_opp_noloo       |              0.816 |             -0.1   |             -0.371 |
| A_opp_placebo     |             -0.098 |             -0.067 |             -1.152 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |              1.007 |             -0.246 |             -0.641 |
| O2_opp_levelnorm  |              0.199 |             -0.167 |             -0.337 |
| O3_opp_window3    |              1.224 |             -0.271 |             -0.606 |
| O4_opp_extra      |             -0.359 |             -0.146 |              0.17  |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -13.306 |            -18.39  |            -10.636 |
| A_opp_noloo       |              0.816 |             -0.1   |             -0.371 |
| A_opp_placebo     |             -0.098 |             -0.067 |             -1.152 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |              1.007 |             -0.246 |             -0.641 |
| O2_opp_levelnorm  |              0.199 |             -0.167 |             -0.337 |
| O3_opp_window3    |              1.224 |             -0.271 |             -0.606 |
| O4_opp_extra      |             -0.359 |             -0.146 |              0.17  |

**Deflation** — PBO(eligible) `0.6` · Bailey OS degradation `0.2988%` · contender spread `0.281%` · whole-field spread `0.362%`


**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.600 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.281% and the in-sample halves split across arms a fraction of a percent apart (O4_opp_extra 49% (+0.000%), O2_opp_levelnorm 27% (+0.281%), O3_opp_window3 13% (+0.293%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 4. Limitations

- **The reliability instrument is one-sided.** The balanced-schedule fixed-sum constraint biases split-half reliability DOWN for the within-league factor, so the noise-corrected spread is a LOWER bound on the noise share, not a point estimate.

- **Opponent quality is measured at TEAM-SEASON grain**, not per-pitcher-faced. A prospect who happened to face a team's ace three times is scored as having faced that team. Per-pitcher matchup data exists in the logs and would be a finer instrument; it is not what a team-strength adjustment needs, and it is a different (larger) story.

- **The LOO is at GAME level**, so it removes the focal player's teammates' lines from his opponents' buckets too. Conservative, and the only form that works identically on both sides.

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

