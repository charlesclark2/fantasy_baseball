# E7.15 H2 — the opponent / competition-quality adjustment (pitcher side)

<!-- MH2-DESIGN-BLOCK
{
 "fold_rule": "leave-one-MLB-debut-cohort-out (n_cohorts)",
 "gates": null,
 "n_arms": 4,
 "n_folds": 11,
 "per_metric": [
  {
   "dsr": 0.38483354906946476,
   "fold_win_rate": 0.5454545454545454,
   "metric": "k_pct",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.9857142857142858,
   "verdict": "DROP"
  },
  {
   "dsr": 0.18975639929748594,
   "fold_win_rate": 0.2727272727272727,
   "metric": "bb_pct",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.5857142857142857,
   "verdict": "DROP"
  },
  {
   "dsr": 0.8000743709905515,
   "fold_win_rate": 0.7272727272727273,
   "metric": "hr_rate",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.6285714285714286,
   "verdict": "DROP"
  },
  {
   "dsr": 0.33498944274814685,
   "fold_win_rate": 0.45454545454545453,
   "metric": "gb_pct",
   "n_arms": 4,
   "n_folds": 11,
   "pbo": 0.4142857142857143,
   "verdict": "DROP"
  }
 ],
 "primary_contrast": "paired-t",
 "reason": null,
 "schema": 1,
 "source_artifact": "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts/e7_15_h2_pitchers_summary.json",
 "status": "recovered",
 "verdict": "k_pct=DROP, bb_pct=DROP, hr_rate=DROP, gb_pct=DROP"
}
-->


_generated 2026-08-02T04:06:05.831348+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> ⚠️ **A projection, not an edge claim.** H2 tests an assertion that has been sitting untested under a shipped feature: `build_park_context.py` says the park factor's residual is "the park (plus the opponent mix, **which averages out** over a 3-season window)". This slice measures the player-level version of that claim and only then asks whether correcting for it helps.

> ⚠️ **Whose claim, precisely.** The park docstring's parenthesis is about the PARK bucket's opponent mix. H2 measures the PLAYER's strength of schedule — the sibling quantity, and the one that could actually bias a translation. They are not the same claim and are not reported as if they were.

## 1. ⭐ The measurement — does the competition a prospect faced actually vary?

This is the primary deliverable and it is worth having whichever way the bake-off lands.


**Observed spread of the per-player opponent factor**

| metric   |   n_players |     p5 |    p50 |    p95 |   p95_minus_p5_pct |   sd_pct |   pct_players_beyond_1pct |   pct_players_beyond_3pct |
|:---------|------------:|-------:|-------:|-------:|-------------------:|---------:|--------------------------:|--------------------------:|
| k_pct    |       23867 | 0.9607 | 0.9983 | 1.035  |               7.43 |    2.488 |                      54.5 |                      14.7 |
| bb_pct   |       23867 | 0.9514 | 0.997  | 1.0488 |               9.74 |    3.213 |                      63   |                      22.1 |
| hr_rate  |       23867 | 0.8861 | 0.9863 | 1.0918 |              20.57 |    6.861 |                      83.3 |                      54   |
| gb_pct   |       23867 | 0.978  | 0.9991 | 1.0194 |               4.15 |    1.405 |                      31.2 |                       5.1 |

**Is that spread real, or is it the estimator?** Split-half reliability: the player's opponents are split into two halves, a factor is built on each, and the halves are correlated across players (Spearman-Brown to full length).

| metric   |   n_players |   half_corr |   reliability_spearman_brown |   signal_share_of_sd | level    | variant                             | player_type   |   window |
|:---------|------------:|------------:|-----------------------------:|---------------------:|:---------|:------------------------------------|:--------------|---------:|
| k_pct    |        4091 |     -0.1437 |                      -0.3355 |               0      | Triple-A | league_normalised (headline)        | pitcher       |        1 |
| bb_pct   |        4091 |     -0.1673 |                      -0.402  |               0      | Triple-A | league_normalised (headline)        | pitcher       |        1 |
| hr_rate  |        4091 |     -0.1466 |                      -0.3437 |               0      | Triple-A | league_normalised (headline)        | pitcher       |        1 |
| gb_pct   |        4091 |     -0.1016 |                      -0.2263 |               0      | Triple-A | league_normalised (headline)        | pitcher       |        1 |
| k_pct    |        4091 |      0.7036 |                       0.826  |               0.9089 | Triple-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| bb_pct   |        4091 |      0.0006 |                       0.0012 |               0.0347 | Triple-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| hr_rate  |        4091 |      0.2739 |                       0.43   |               0.6557 | Triple-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| gb_pct   |        4091 |      0.3472 |                       0.5155 |               0.718  | Triple-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| k_pct    |        4741 |     -0.2758 |                      -0.7615 |               0      | Double-A | league_normalised (headline)        | pitcher       |        1 |
| bb_pct   |        4741 |     -0.3042 |                      -0.8744 |               0      | Double-A | league_normalised (headline)        | pitcher       |        1 |
| hr_rate  |        4741 |     -0.2313 |                      -0.6019 |               0      | Double-A | league_normalised (headline)        | pitcher       |        1 |
| gb_pct   |        4741 |     -0.2696 |                      -0.7383 |               0      | Double-A | league_normalised (headline)        | pitcher       |        1 |
| k_pct    |        4741 |      0.0868 |                       0.1598 |               0.3998 | Double-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| bb_pct   |        4741 |      0.2344 |                       0.3798 |               0.6163 | Double-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| hr_rate  |        4741 |      0.139  |                       0.2441 |               0.4941 | Double-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| gb_pct   |        4741 |     -0.0166 |                      -0.0337 |               0      | Double-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| k_pct    |        6054 |     -0.2821 |                      -0.7859 |               0      | High-A   | league_normalised (headline)        | pitcher       |        1 |
| bb_pct   |        6054 |     -0.2834 |                      -0.7911 |               0      | High-A   | league_normalised (headline)        | pitcher       |        1 |
| hr_rate  |        6054 |     -0.1473 |                      -0.3455 |               0      | High-A   | league_normalised (headline)        | pitcher       |        1 |
| gb_pct   |        6054 |     -0.2465 |                      -0.6543 |               0      | High-A   | league_normalised (headline)        | pitcher       |        1 |
| k_pct    |        6054 |      0.3091 |                       0.4722 |               0.6872 | High-A   | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| bb_pct   |        6054 |      0.0425 |                       0.0815 |               0.2855 | High-A   | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| hr_rate  |        6054 |      0.4953 |                       0.6625 |               0.8139 | High-A   | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| gb_pct   |        6054 |      0.0635 |                       0.1194 |               0.3455 | High-A   | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| k_pct    |        6898 |     -0.2493 |                      -0.6641 |               0      | Single-A | league_normalised (headline)        | pitcher       |        1 |
| bb_pct   |        6898 |     -0.1422 |                      -0.3315 |               0      | Single-A | league_normalised (headline)        | pitcher       |        1 |
| hr_rate  |        6898 |     -0.2076 |                      -0.5239 |               0      | Single-A | league_normalised (headline)        | pitcher       |        1 |
| gb_pct   |        6898 |     -0.2601 |                      -0.7031 |               0      | Single-A | league_normalised (headline)        | pitcher       |        1 |
| k_pct    |        6898 |     -0.1139 |                      -0.257  |               0      | Single-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| bb_pct   |        6898 |      0.299  |                       0.4604 |               0.6785 | Single-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| hr_rate  |        6898 |      0.1218 |                       0.2172 |               0.466  | Single-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |
| gb_pct   |        6898 |      0.1314 |                       0.2322 |               0.4819 | Single-A | level_normalised (POSITIVE CONTROL) | pitcher       |        1 |

⚠️ **This estimator has a KNOWN DOWNWARD BIAS and is a ONE-SIDED instrument.** A league plays a roughly BALANCED schedule, so a player's two halves are mechanically ANTI-correlated when there is no real signal — which is why the league-normalised readings come back NEGATIVE rather than 0. The negativity is itself the fingerprint of a balanced schedule. It can support "there is no LARGE within-league component"; it cannot be quoted as a precise reliability.


**The POSITIVE CONTROL** is what makes the near-zero reading mean anything (NF1.7 (a)): the SAME estimator on the SAME rows reads high for the LEVEL-normalised factor, whose large between-league component is shared by both halves and so escapes the fixed-sum constraint.


**How much of the factor is a LEAGUE effect the model already has?** E7.3 fits a per-league random intercept, so any part of the factor that is constant within a league is NOT new information — it is a re-encoding of a shipped feature, and a lift on it would be unattributable to opponent quality. This table is why the headline arm is league-normalised.

| metric   | variant                      |   total_sd_pct |   between_league_sd_pct |   within_league_sd_pct |   between_league_share_pct | player_type   |
|:---------|:-----------------------------|---------------:|------------------------:|-----------------------:|---------------------------:|:--------------|
| k_pct    | level_normalised             |          3.951 |                   2.359 |                  3.17  |                       35.6 | pitcher       |
| k_pct    | league_normalised (headline) |          2.502 |                   0.104 |                  2.5   |                        0.2 | pitcher       |
| bb_pct   | level_normalised             |          4.267 |                   1.795 |                  3.871 |                       17.7 | pitcher       |
| bb_pct   | league_normalised (headline) |          3.205 |                   0.127 |                  3.202 |                        0.2 | pitcher       |
| hr_rate  | level_normalised             |         10.139 |                   5.248 |                  8.675 |                       26.8 | pitcher       |
| hr_rate  | league_normalised (headline) |          6.934 |                   0.463 |                  6.918 |                        0.4 | pitcher       |
| gb_pct   | level_normalised             |          1.803 |                   0.785 |                  1.623 |                       19   | pitcher       |
| gb_pct   | league_normalised (headline) |          1.408 |                   0.052 |                  1.407 |                        0.1 | pitcher       |

## 2. Verdict by metric

| metric   | verdict   | winner   | best_arm          |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | BH-FDR   |   PBO(eligible) |   DSR(eligible) |
|:---------|:----------|:---------|:------------------|-------------------:|----------------:|--------------:|:---------|----------------:|----------------:|
| k_pct    | DROP      | L0_foil  | O1_opp_leaguenorm |              0.078 |        0.545455 |     0.318308  | False    |        0.985714 |        0.384834 |
| bb_pct   | DROP      | L0_foil  | O1_opp_leaguenorm |             -0.106 |        0.272727 |     0.753494  | False    |        0.585714 |        0.189756 |
| hr_rate  | DROP      | L0_foil  | O3_opp_window3    |              0.147 |        0.727273 |     0.0882573 | False    |        0.628571 |        0.800074 |
| gb_pct   | DROP      | L0_foil  | O2_opp_levelnorm  |              0.049 |        0.454545 |     0.358892  | False    |        0.414286 |        0.334989 |

## 2b. ⭐ Reading the null honestly — is it the data, or is it my gate?

Re-deciding the entire run with the deflation gates REMOVED — no PBO ceiling, no DSR floor — leaves survivors: **NONE**. ⇒ BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing (family of 4; strictest BH rung p ≤ 0.025).

| metric   | arm               |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind                                                             |   folds_have |   folds_needed_BH |   folds_needed_DSR |   extra_seasons_needed |
|:---------|:------------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-----------------------------------------------------------------|-------------:|------------------:|-------------------:|-----------------------:|
| k_pct    | O1_opp_leaguenorm |             0.0775 |        0.545455 |     0.318308  | True         | False             | False        | False        | False             | underpowered                                                     |           11 |               181 |                247 |                    236 |
| bb_pct   | O1_opp_leaguenorm |            -0.1064 |        0.272727 |     0.753494  | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan |                    nan |
| hr_rate  | O3_opp_window3    |             0.147  |        0.727273 |     0.0882573 | True         | True              | False        | False        | False             | underpowered                                                     |           11 |                23 |                 42 |                     31 |
| gb_pct   | O2_opp_levelnorm  |             0.049  |        0.454545 |     0.358892  | True         | False             | False        | False        | False             | underpowered                                                     |           11 |               309 |                496 |                    485 |

## 3.k_pct — the arm set (`partial_pool@4`, context `baseline`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| O1_opp_leaguenorm | opponent | True     |  0.035593 |           0.07752  |        0.545455 |      0.318308 |            94.61 |      0.96079 |      1.0349  |
| O3_opp_window3    | opponent | True     |  0.035594 |           0.075589 |        0.454545 |      0.320132 |            94.61 |      0.9603  |      1.03525 |
| A_opp_noloo       | anchor   | True     |  0.035596 |           0.069503 |        0.545455 |      0.340101 |            94.61 |      0.96049 |      1.03465 |
| A_opp_placebo     | anchor   | True     |  0.035605 |           0.045393 |        0.545455 |      0.409896 |            94.27 |      0.96079 |      1.0349  |
| L0_foil           | foil     | True     |  0.035621 |           0        |        0        |    nan        |             0    |      1       |      1       |
| O2_opp_levelnorm  | opponent | True     |  0.035633 |          -0.03474  |        0.636364 |      0.540783 |            94.61 |      0.93594 |      1.06125 |
| O4_opp_extra      | opponent | True     |  0.035734 |          -0.317227 |        0.363636 |      0.850116 |            94.61 |      0.96079 |      1.0349  |
| A_degenerate_mean | anchor   | True     |  0.037359 |          -4.88088  |        0.181818 |      0.977395 |             0    |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 2/11 folds, p=0.974751965546441, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 6/11 folds, p=0.5514897816567262, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 6/11 folds, p=0.7689122945417644, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              85.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              85.7 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              85.7 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |             -4.934 |             -3.518 |             -8.248 |
| A_opp_noloo       |              0.362 |              0.2   |             -0.082 |
| A_opp_placebo     |              0.013 |              0.09  |              0.002 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |              0.37  |              0.21  |             -0.078 |
| O2_opp_levelnorm  |              0.179 |              0.134 |             -0.397 |
| O3_opp_window3    |              0.34  |              0.219 |             -0.077 |
| O4_opp_extra      |             -0.357 |             -0.137 |             -0.235 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |             -4.934 |             -3.518 |             -8.248 |
| A_opp_noloo       |              0.362 |              0.2   |             -0.082 |
| A_opp_placebo     |              0.013 |              0.09  |              0.002 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |              0.37  |              0.21  |             -0.078 |
| O2_opp_levelnorm  |              0.179 |              0.134 |             -0.397 |
| O3_opp_window3    |              0.34  |              0.219 |             -0.077 |
| O4_opp_extra      |             -0.357 |             -0.137 |             -0.235 |

**Deflation** — PBO(eligible) `0.9857142857142858` · Bailey OS degradation `0.3418%` · contender spread `0.078%` · whole-field spread `0.395%`


**Reading**

- 🟡 no arm clears: best eligible `O1_opp_leaguenorm` MAE 0.03559 vs foil 0.03562 (0.08%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.bb_pct — the arm set (`partial_pool@4`, context `park:exposure+levelenv+rel:1k+w:mlb_pa`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| L0_foil           | foil     | True     |  0.019071 |           0        |        0        |    nan        |             0    |      1       |      1       |
| A_opp_noloo       | anchor   | True     |  0.019088 |          -0.090894 |        0.363636 |      0.720178 |            99.62 |      0.95211 |      1.05029 |
| O1_opp_leaguenorm | opponent | True     |  0.019091 |          -0.106417 |        0.272727 |      0.753494 |            99.62 |      0.95144 |      1.04873 |
| O3_opp_window3    | opponent | True     |  0.019094 |          -0.119007 |        0.454545 |      0.754918 |            99.62 |      0.95094 |      1.04918 |
| O2_opp_levelnorm  | opponent | True     |  0.019114 |          -0.224701 |        0.181818 |      0.802038 |            99.62 |      0.93011 |      1.06707 |
| O4_opp_extra      | opponent | True     |  0.019125 |          -0.284826 |        0.272727 |      0.864026 |            99.62 |      0.95144 |      1.04873 |
| A_opp_placebo     | anchor   | True     |  0.019252 |          -0.947388 |        0.090909 |      0.997272 |            99.24 |      0.95144 |      1.04873 |
| A_degenerate_mean | anchor   | True     |  0.021248 |         -11.414    |        0.090909 |      0.999382 |             0    |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 1/11 folds, p=0.9993227626945993, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 1/11 folds, p=0.9903866397748798, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 8/11 folds, p=0.26319550262179936, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              85.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              85.7 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              85.7 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -16.559 |            -13.073 |             -6.826 |
| A_opp_noloo       |             -0.607 |              0.235 |             -0.189 |
| A_opp_placebo     |             -1.081 |             -1.098 |             -0.877 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.614 |              0.219 |             -0.226 |
| O2_opp_levelnorm  |             -0.706 |             -0.069 |             -0.449 |
| O3_opp_window3    |             -0.803 |              0.212 |             -0.156 |
| O4_opp_extra      |              0.287 |             -0.651 |             -0.243 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -16.559 |            -13.073 |             -6.826 |
| A_opp_noloo       |             -0.607 |              0.235 |             -0.189 |
| A_opp_placebo     |             -1.081 |             -1.098 |             -0.877 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.614 |              0.219 |             -0.226 |
| O2_opp_levelnorm  |             -0.706 |             -0.069 |             -0.449 |
| O3_opp_window3    |             -0.803 |              0.212 |             -0.156 |
| O4_opp_extra      |              0.287 |             -0.651 |             -0.243 |

**Deflation** — PBO(eligible) `0.5857142857142857` · Bailey OS degradation `0.1765%` · contender spread `0.119%` · whole-field spread `0.285%`


**Reading**

- 🟡 no arm clears: best eligible `O1_opp_leaguenorm` MAE 0.01909 vs foil 0.01907 (-0.11%, fold win rate 27%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.hr_rate — the arm set (`partial_pool@4`, context `park:exposure+levelenv+rel:1k+w:mlb_pa`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| O3_opp_window3    | opponent | True     |  0.00976  |           0.147046 |        0.727273 |      0.088257 |            99.62 |      0.88525 |      1.09339 |
| O2_opp_levelnorm  | opponent | True     |  0.00976  |           0.142436 |        0.636364 |      0.217839 |            99.62 |      0.83996 |      1.15441 |
| O1_opp_leaguenorm | opponent | True     |  0.009762 |           0.122073 |        0.727273 |      0.119935 |            99.62 |      0.88641 |      1.09164 |
| A_opp_noloo       | anchor   | True     |  0.009763 |           0.117721 |        0.727273 |      0.126128 |            99.62 |      0.88613 |      1.09351 |
| O4_opp_extra      | opponent | True     |  0.009771 |           0.033795 |        0.727273 |      0.340103 |            99.62 |      0.88641 |      1.09164 |
| L0_foil           | foil     | True     |  0.009774 |           0        |        0        |    nan        |             0    |      1       |      1       |
| A_opp_placebo     | anchor   | True     |  0.009811 |          -0.378751 |        0.363636 |      0.855895 |            99.24 |      0.88641 |      1.09164 |
| A_degenerate_mean | anchor   | True     |  0.009921 |          -1.50304  |        0.181818 |      0.975152 |             0    |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 3/11 folds, p=0.9836918345326562, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 3/11 folds, p=0.9493506092248977, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 4/11 folds, p=0.856835316839559, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              85.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              85.7 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              85.7 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |             -3.576 |             -1.014 |             -0.241 |
| A_opp_noloo       |              0.047 |              0.286 |              0.032 |
| A_opp_placebo     |             -0.968 |             -0.203 |             -0.207 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |              0.068 |              0.285 |              0.033 |
| O2_opp_levelnorm  |              0.258 |              0.442 |             -0.033 |
| O3_opp_window3    |              0.145 |              0.263 |              0.065 |
| O4_opp_extra      |              0.025 |              0.028 |              0.055 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |             -3.576 |             -1.014 |             -0.241 |
| A_opp_noloo       |              0.047 |              0.286 |              0.032 |
| A_opp_placebo     |             -0.968 |             -0.203 |             -0.207 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |              0.068 |              0.285 |              0.033 |
| O2_opp_levelnorm  |              0.258 |              0.442 |             -0.033 |
| O3_opp_window3    |              0.145 |              0.263 |              0.065 |
| O4_opp_extra      |              0.025 |              0.028 |              0.055 |

**Deflation** — PBO(eligible) `0.6285714285714286` · Bailey OS degradation `0.1009%` · contender spread `0.025%` · whole-field spread `0.147%`


**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.629 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.025% and the in-sample halves split across arms a fraction of a percent apart (O2_opp_levelnorm 48% (+0.005%), O3_opp_window3 37% (+0.000%), L0_foil 8% (+0.147%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 3.gb_pct — the arm set (`partial_pool@2`, context `baseline`, learner held fixed)

| arm               | kind     | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   factor_p05 |   factor_p95 |
|:------------------|:---------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|-------------:|-------------:|
| O2_opp_levelnorm  | opponent | True     |  0.047812 |           0.04902  |        0.454545 |      0.358892 |            96.23 |      0.97147 |      1.0283  |
| L0_foil           | foil     | True     |  0.047835 |           0        |        0        |    nan        |             0    |      1       |      1       |
| A_opp_placebo     | anchor   | True     |  0.047844 |          -0.019535 |        0.454545 |      0.54896  |            95.82 |      0.97801 |      1.01933 |
| A_opp_noloo       | anchor   | True     |  0.047848 |          -0.02749  |        0.545455 |      0.577585 |            96.27 |      0.97787 |      1.01913 |
| O1_opp_leaguenorm | opponent | True     |  0.047855 |          -0.040814 |        0.636364 |      0.617971 |            96.26 |      0.97801 |      1.01933 |
| O3_opp_window3    | opponent | True     |  0.047871 |          -0.074879 |        0.454545 |      0.744035 |            96.26 |      0.97773 |      1.0197  |
| O4_opp_extra      | opponent | True     |  0.047992 |          -0.328589 |        0.545455 |      0.913406 |            96.26 |      0.97801 |      1.01933 |
| A_degenerate_mean | anchor   | True     |  0.057312 |         -19.8125   |        0        |      0.999983 |             0    |      1       |      1       |

**Anchors**

- `A_degenerate_mean` (the DEGENERATE CEILING — predict the population mean): challenger wins 0/11 folds, p=0.9999851165994074, violated=False
- `A_opp_placebo` (the PLACEBO — opponent factors permuted within level): challenger wins 5/11 folds, p=0.716988121820789, violated=False
- `A_opp_noloo` (the NON-LOO factor — the player's own games left in his opponents' bucket): challenger wins 5/11 folds, p=0.7739918895023109, violated=False

**⚠️ What the propensity terciles actually CONTAIN** (see H1 — the low tercile is the one richest in Triple-A rows, not low-level prospects):

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              85.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              85.7 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              85.7 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the adjustment CAN move (what the H5 gate reads)** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -19.902 |            -20.779 |            -20.775 |
| A_opp_noloo       |             -0.104 |             -0.195 |              0.196 |
| A_opp_placebo     |             -0.104 |             -0.401 |              0.211 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.139 |             -0.209 |              0.169 |
| O2_opp_levelnorm  |              0.123 |             -0.039 |              0.036 |
| O3_opp_window3    |             -0.093 |             -0.223 |              0.096 |
| O4_opp_extra      |             -0.991 |             -0.107 |             -0.133 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity):

| arm               |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean |            -19.902 |            -20.779 |            -20.775 |
| A_opp_noloo       |             -0.104 |             -0.195 |              0.196 |
| A_opp_placebo     |             -0.104 |             -0.401 |              0.211 |
| L0_foil           |              0     |              0     |              0     |
| O1_opp_leaguenorm |             -0.139 |             -0.209 |              0.169 |
| O2_opp_levelnorm  |              0.123 |             -0.039 |              0.036 |
| O3_opp_window3    |             -0.093 |             -0.223 |              0.096 |
| O4_opp_extra      |             -0.991 |             -0.107 |             -0.133 |

**Deflation** — PBO(eligible) `0.4142857142857143` · Bailey OS degradation `0.1156%` · contender spread `0.09%` · whole-field spread `0.378%`


**Reading**

- 🟡 no arm clears: best eligible `O2_opp_levelnorm` MAE 0.04781 vs foil 0.04784 (0.05%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 4. Limitations

- **The reliability instrument is one-sided.** The balanced-schedule fixed-sum constraint biases split-half reliability DOWN for the within-league factor, so the noise-corrected spread is a LOWER bound on the noise share, not a point estimate.

- **Opponent quality is measured at TEAM-SEASON grain**, not per-pitcher-faced. A prospect who happened to face a team's ace three times is scored as having faced that team. Per-pitcher matchup data exists in the logs and would be a finer instrument; it is not what a team-strength adjustment needs, and it is a different (larger) story.

- **The LOO is at GAME level**, so it removes the focal player's teammates' lines from his opponents' buckets too. Conservative, and the only form that works identically on both sides.

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

