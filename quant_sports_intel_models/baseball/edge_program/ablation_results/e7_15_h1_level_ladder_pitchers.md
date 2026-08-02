# E7.15 H1 — the within-player level-translation ladder (pitcher side)

_generated 2026-08-02T03:34:21.592229+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> ⚠️ **A projection, not an edge claim.** H1 asks one question: does learning the LEVEL part of the MiLB→MLB translation from within-player minor→minor transitions — a substrate with no MLB label, no promotion selection, and 4–7× the rows of the labelled per-level cohort — translate better than learning it from graduates alone? An arm that does not clear its deflated gate is **DROPPED, not shipped**.

## 0. Pre-registration (written before the run)

- **Foil.** Every arm is measured against `L0_foil` = the configuration LIVE on the board today (the shipped slice-1 `ContextSpec` per metric), with the learner and its `weight_col` held FIXED. The only thing that varies is the feature (E7.9: 54–77% of a bake-off margin can be the learner swap).

- **Four ladder formulations**, not one: `L1_chain_ols`, `L2_chain_paweighted` (L1's matched pair for the weighting), `L3_direct_to_ref` (one-step maps, which avoid the chain's threefold attenuation compounding), `L4_ladder_delta` (NESTS the foil at coefficient 0). Plus `L1p_chain_purged` as a registered calendar-leakage sensitivity. A single architecture missing its gate is not a trustworthy null; the whole set missing it is.

- **Anchors.** `A_ladder_identity` must be a BYTE no-op; `A_ladder_meanshift` (the matched level-only foil) and `A_ladder_shuffled` (the within-player link destroyed) must LOSE; `A_degenerate_mean` must LOSE. A MISSING anchor BLOCKS — it is not a pass.

- **Gate for an ADD** (all must hold): strict OOS MAE improvement over the foil in ≥60% of held-out debut cohorts; the ladder MOVED >1.0% of rows; every anchor holds; PBO(eligible) < 0.2; DSR(eligible) ≥ 0.95; Benjamini-Hochberg over the metric family at α=0.1; and — for a board metric — a non-negative lift in the LOWEST promotion-propensity tercile.

- **Estimand preserved.** Same target, same labelled population, same emitted meaning, so the E8.0 board and the E7.5b betting prior stay comparable. Asserted per fold.

## 1. ⭐ The transition census — REPORTED BEFORE ANY SCORE

The n-multiplication is H1's entire premise, so the counts come first. `pct_never_mlb` is the share of transitions whose source player NEVER reached MLB — the population a graduates-only fit structurally cannot see, and the population the draft board is served on.


**k_pct**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2207 |              1691 |            76.6 |            311.1 |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1534 |               998 |            65.1 |            330.2 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             680 |               350 |            51.5 |            302.3 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2172 |              1399 |            64.4 |            344.9 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             983 |               493 |            50.2 |            313.1 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1367 |               714 |            52.2 |            354.5 |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   47 |                      6 |
|   2017 |                  340 |                      0 |
|   2018 |                  899 |                      0 |
|   2019 |                 1731 |                      0 |
|   2020 |                 2971 |                      0 |
|   2021 |                 3014 |                      0 |
|   2022 |                 3654 |                      0 |
|   2023 |                 4474 |                      0 |
|   2024 |                 5314 |                      0 |
|   2025 |                 6201 |                      0 |
|   2026 |                 7256 |                      0 |

**bb_pct**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2207 |              1691 |            76.6 |            311.1 |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1534 |               998 |            65.1 |            330.2 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             680 |               350 |            51.5 |            302.3 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2172 |              1399 |            64.4 |            344.9 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             983 |               493 |            50.2 |            313.1 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1367 |               714 |            52.2 |            354.5 |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   47 |                      6 |
|   2017 |                  340 |                      0 |
|   2018 |                  899 |                      0 |
|   2019 |                 1731 |                      0 |
|   2020 |                 2971 |                      0 |
|   2021 |                 3014 |                      0 |
|   2022 |                 3654 |                      0 |
|   2023 |                 4474 |                      0 |
|   2024 |                 5314 |                      0 |
|   2025 |                 6201 |                      0 |
|   2026 |                 7256 |                      0 |

**hr_rate**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2207 |              1691 |            76.6 |            311.1 |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1534 |               998 |            65.1 |            330.2 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             680 |               350 |            51.5 |            302.3 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2172 |              1399 |            64.4 |            344.9 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             983 |               493 |            50.2 |            313.1 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1367 |               714 |            52.2 |            354.5 |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   47 |                      6 |
|   2017 |                  340 |                      0 |
|   2018 |                  899 |                      0 |
|   2019 |                 1731 |                      0 |
|   2020 |                 2971 |                      0 |
|   2021 |                 3014 |                      0 |
|   2022 |                 3654 |                      0 |
|   2023 |                 4474 |                      0 |
|   2024 |                 5314 |                      0 |
|   2025 |                 6201 |                      0 |
|   2026 |                 7256 |                      0 |

**gb_pct**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2207 |              1691 |            76.6 |            311.1 |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1534 |               998 |            65.1 |            330.2 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             680 |               350 |            51.5 |            302.3 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2172 |              1399 |            64.4 |            344.9 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             983 |               493 |            50.2 |            313.1 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1367 |               714 |            52.2 |            354.5 |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   47 |                      6 |
|   2017 |                  340 |                      0 |
|   2018 |                  899 |                      0 |
|   2019 |                 1731 |                      0 |
|   2020 |                 2971 |                      0 |
|   2021 |                 3014 |                      0 |
|   2022 |                 3654 |                      0 |
|   2023 |                 4474 |                      0 |
|   2024 |                 5314 |                      0 |
|   2025 |                 6201 |                      0 |
|   2026 |                 7256 |                      0 |

**xwoba_against**

_(empty)_

_evaluable debut cohorts: [2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2023 |                    0 |                      6 |
|   2024 |                    0 |                      6 |
|   2025 |                    0 |                      6 |
|   2026 |                    0 |                      6 |

## 2. Verdict by metric

| metric        | verdict   | winner   | best_arm            |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | BH-FDR   |   PBO(eligible) |   DSR(eligible) |   low_tercile_lift_% |
|:--------------|:----------|:---------|:--------------------|-------------------:|----------------:|--------------:|:---------|----------------:|----------------:|---------------------:|
| k_pct         | DROP      | L0_foil  | L3_direct_to_ref    |              0.116 |        0.636364 |     0.0643037 | False    |        0.671429 |        0.85698  |             0.654793 |
| bb_pct        | DROP      | L0_foil  | L2_chain_paweighted |              0.298 |        0.545455 |     0.145436  | False    |        0.814286 |        0.48941  |             0.400123 |
| hr_rate       | DROP      | L0_foil  | L3_direct_to_ref    |              0.104 |        0.727273 |     0.08128   | False    |        0.142857 |        0.602113 |             0.460246 |
| gb_pct        | DROP      | L0_foil  | L3_direct_to_ref    |              0.248 |        0.545455 |     0.174722  | False    |        0.642857 |        0.371654 |             0.856319 |
| xwoba_against | DROP      | L0_foil  |                     |            nan     |      nan        |   nan         |          |        0.166667 |      nan        |             0        |

`PBO(eligible)` and `DSR(eligible)` are computed over the ELIGIBLE arms — the search the selection actually ran — not over every arm scored; the whole-field figures are in the JSON. A field that CONTAINS its own anchors has a huge dispersion, and a deflation statistic computed over it measures the anchors (NF-D14). The eligible-set figure is the one pre-registered to bind.


## 3.k_pct — the arm set (`partial_pool@4`, context `baseline`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| L3_direct_to_ref    | ladder      | True     |  0.035579 |           0.116345 |        0.636364 |      0.064304 |            79.89 |              0.035188 |
| L1_chain_ols        | ladder      | True     |  0.035607 |           0.038091 |        0.545455 |      0.36403  |            79.89 |              0.039972 |
| L2_chain_paweighted | ladder      | True     |  0.03562  |           0.002355 |        0.545455 |      0.491169 |            79.89 |              0.040263 |
| L4_ladder_delta     | ladder      | True     |  0.035621 |           0.000497 |        0.545455 |      0.480271 |            79.89 |              0.039972 |
| L0_foil             | foil        | True     |  0.035621 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.035621 |           0        |        0        |    nan        |             0    |              0        |
| L1p_chain_purged    | sensitivity | True     |  0.035643 |          -0.061329 |        0.454545 |      0.676016 |            79.89 |              0.039972 |
| A_ladder_meanshift  | anchor      | True     |  0.035709 |          -0.248868 |        0.272727 |      0.866892 |            76.51 |              0.025595 |
| A_ladder_shuffled   | anchor      | True     |  0.036096 |          -1.33497  |        0.181818 |      0.754831 |            79.89 |              0.053882 |
| A_degenerate_mean   | anchor      | True     |  0.037359 |          -4.88088  |        0.181818 |      0.977395 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |         a |        b | source                              |
|:--------------------|:---------|----------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A |  0.178268 | 0.141992 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   |  0.147916 | 0.277729 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A |  0.087134 | 0.549374 | chain:fitted                        |
| L1_chain_ols        | Triple-A |  0        | 1        | reference                           |
| L2_chain_paweighted | Single-A |  0.172037 | 0.151134 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   |  0.14188  | 0.289888 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A |  0.080923 | 0.568514 | chain:fitted                        |
| L2_chain_paweighted | Triple-A |  0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A |  0.156363 | 0.263492 | direct                              |
| L3_direct_to_ref    | High-A   |  0.126665 | 0.373601 | direct                              |
| L3_direct_to_ref    | Double-A |  0.080923 | 0.568514 | direct                              |
| L3_direct_to_ref    | Triple-A |  0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | -0.042703 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | -0.03256  | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A | -0.021153 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A |  0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              44.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              62.1 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              64.5 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -2.234 |             -2.875 |             -3.841 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |             -0.939 |             -0.28  |              0.007 |
| A_ladder_shuffled   |             -3.14  |             -2.96  |             -3.595 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.722 |             -0.335 |             -0.015 |
| L1p_chain_purged    |              0.424 |             -0.459 |             -0.021 |
| L2_chain_paweighted |              0.604 |             -0.369 |             -0.022 |
| L3_direct_to_ref    |              0.655 |              0.047 |              0.019 |
| L4_ladder_delta     |              0.003 |              0.026 |             -0.003 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -4.934 |             -3.518 |             -8.248 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |             -0.624 |             -0.271 |              0.023 |
| A_ladder_shuffled   |             -1.925 |             -2.359 |             -3.057 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.416 |             -0.315 |              0.025 |
| L1p_chain_purged    |              0.236 |             -0.42  |             -0.014 |
| L2_chain_paweighted |              0.338 |             -0.348 |              0.019 |
| L3_direct_to_ref    |              0.38  |              0.001 |              0.052 |
| L4_ladder_delta     |             -0.014 |              0.001 |              0.004 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.6714285714285714` · Bailey OS degradation `0.0283%` (p90 `0.2327%`) · contender spread `0.114%` · whole-field spread `0.178%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L3_direct_to_ref    |            307 |   0.665 |        0.03558 |         0     |
| L1_chain_ols        |            103 |   0.223 |        0.03561 |         0.078 |
| L2_chain_paweighted |             28 |   0.061 |        0.03562 |         0.114 |
| L0_foil             |             20 |   0.043 |        0.03562 |         0.116 |
| L1p_chain_purged    |              4 |   0.009 |        0.03564 |         0.178 |

**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.671 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.114% and the in-sample halves split across arms a fraction of a percent apart (L3_direct_to_ref 66% (+0.000%), L1_chain_ols 22% (+0.078%), L2_chain_paweighted 6% (+0.114%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 3.bb_pct — the arm set (`partial_pool@4`, weights=mlb_pa, context `park:exposure+levelenv+rel:1k+w:mlb_pa`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| L2_chain_paweighted | ladder      | True     |  0.019014 |           0.298076 |        0.545455 |      0.145436 |            79.89 |              0.010017 |
| L1_chain_ols        | ladder      | True     |  0.019015 |           0.295498 |        0.545455 |      0.15289  |            79.89 |              0.01066  |
| L3_direct_to_ref    | ladder      | True     |  0.01902  |           0.265486 |        0.636364 |      0.125001 |            79.89 |              0.008186 |
| L1p_chain_purged    | sensitivity | True     |  0.019032 |           0.204969 |        0.363636 |      0.208569 |            79.89 |              0.01066  |
| A_ladder_meanshift  | anchor      | True     |  0.019056 |           0.077854 |        0.545455 |      0.295262 |            79.89 |              0.010344 |
| L0_foil             | foil        | True     |  0.019071 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.019071 |           0        |        0        |    nan        |             0    |              0        |
| L4_ladder_delta     | ladder      | True     |  0.01908  |          -0.047384 |        0.454545 |      0.837296 |            79.89 |              0.01066  |
| A_ladder_shuffled   | anchor      | True     |  0.020459 |          -7.27806  |        0        |      0.999799 |            79.89 |              0.014699 |
| A_degenerate_mean   | anchor      | True     |  0.021248 |         -11.414    |        0.090909 |      0.999382 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |        a |        b | source                              |
|:--------------------|:---------|---------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A | 0.083091 | 0.234064 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   | 0.068771 | 0.380178 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A | 0.045258 | 0.607285 | chain:fitted                        |
| L1_chain_ols        | Triple-A | 0        | 1        | reference                           |
| L2_chain_paweighted | Single-A | 0.0797   | 0.260434 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   | 0.064687 | 0.414566 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A | 0.041308 | 0.641997 | chain:fitted                        |
| L2_chain_paweighted | Triple-A | 0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A | 0.060823 | 0.425409 | direct                              |
| L3_direct_to_ref    | High-A   | 0.052838 | 0.515841 | direct                              |
| L3_direct_to_ref    | Double-A | 0.041308 | 0.641997 | direct                              |
| L3_direct_to_ref    | Triple-A | 0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | 0.014958 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | 0.013718 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A | 0.0091   | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A | 0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              44.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              62.1 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              64.5 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -15.358 |            -12.764 |             -5.389 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.585 |             -0.014 |             -0.011 |
| A_ladder_shuffled   |            -15.746 |            -12.087 |             -5.399 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.383 |              0.873 |              0.04  |
| L1p_chain_purged    |              0.123 |              0.694 |              0.04  |
| L2_chain_paweighted |              0.4   |              0.884 |              0.03  |
| L3_direct_to_ref    |              0.436 |              0.777 |              0.018 |
| L4_ladder_delta     |             -0.169 |             -0.084 |              0.005 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -16.559 |            -13.073 |             -6.826 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.417 |             -0.07  |             -0     |
| A_ladder_shuffled   |             -9.67  |            -10.067 |             -4.542 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.311 |              0.633 |              0.036 |
| L1p_chain_purged    |              0.142 |              0.495 |              0.039 |
| L2_chain_paweighted |              0.314 |              0.652 |              0.027 |
| L3_direct_to_ref    |              0.315 |              0.588 |              0.015 |
| L4_ladder_delta     |             -0.098 |             -0.082 |             -0.015 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.8142857142857143` · Bailey OS degradation `0.0384%` (p90 `0.5902%`) · contender spread `0.033%` · whole-field spread `0.346%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L1_chain_ols        |            185 |   0.4   |        0.01901 |         0.003 |
| L2_chain_paweighted |            109 |   0.236 |        0.01901 |         0     |
| L3_direct_to_ref    |             88 |   0.19  |        0.01902 |         0.033 |
| L0_foil             |             79 |   0.171 |        0.01907 |         0.299 |
| L1p_chain_purged    |              1 |   0.002 |        0.01903 |         0.093 |

**Reading**

- 🟡 no arm clears: best eligible `L2_chain_paweighted` MAE 0.01901 vs foil 0.01907 (0.30%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.hr_rate — the arm set (`partial_pool@4`, weights=mlb_pa, context `park:exposure+levelenv+rel:1k+w:mlb_pa`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| A_ladder_meanshift  | anchor      | True     |  0.009761 |           0.138429 |        0.636364 |      0.10419  |            79.89 |              0.006308 |
| L3_direct_to_ref    | ladder      | True     |  0.009764 |           0.104015 |        0.727273 |      0.08128  |            79.89 |              0.0061   |
| L0_foil             | foil        | True     |  0.009774 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.009774 |           0        |        0        |    nan        |             0    |              0        |
| L4_ladder_delta     | ladder      | True     |  0.009781 |          -0.068839 |        0.454545 |      0.851429 |            79.89 |              0.006036 |
| L2_chain_paweighted | ladder      | True     |  0.009787 |          -0.125612 |        0.363636 |      0.756429 |            79.89 |              0.006308 |
| L1_chain_ols        | ladder      | True     |  0.009787 |          -0.132734 |        0.363636 |      0.766714 |            79.89 |              0.006036 |
| L1p_chain_purged    | sensitivity | True     |  0.009796 |          -0.224499 |        0.272727 |      0.903667 |            79.89 |              0.006036 |
| A_ladder_shuffled   | anchor      | True     |  0.009823 |          -0.496798 |        0.272727 |      0.963219 |            79.89 |              0.006045 |
| A_degenerate_mean   | anchor      | True     |  0.009921 |          -1.50304  |        0.181818 |      0.975152 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |        a |        b | source                              |
|:--------------------|:---------|---------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A | 0.027232 | 0.005706 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   | 0.026517 | 0.039336 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A | 0.022032 | 0.230038 | chain:fitted                        |
| L1_chain_ols        | Triple-A | 0        | 1        | reference                           |
| L2_chain_paweighted | Single-A | 0.027605 | 0.006357 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   | 0.026841 | 0.041826 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A | 0.022132 | 0.240125 | chain:fitted                        |
| L2_chain_paweighted | Triple-A | 0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A | 0.02333  | 0.228182 | direct                              |
| L3_direct_to_ref    | High-A   | 0.024279 | 0.157301 | direct                              |
| L3_direct_to_ref    | Double-A | 0.022132 | 0.240125 | direct                              |
| L3_direct_to_ref    | Triple-A | 0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | 0.010723 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | 0.007263 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A | 0.004652 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A | 0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              44.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              62.1 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              64.5 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -2.307 |             -1.37  |             -0.334 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.482 |              0.104 |              0.09  |
| A_ladder_shuffled   |              0.018 |             -0.712 |             -0.48  |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.763 |             -0.326 |             -0.133 |
| L1p_chain_purged    |              0.392 |             -0.425 |             -0.174 |
| L2_chain_paweighted |              0.772 |             -0.323 |             -0.126 |
| L3_direct_to_ref    |              0.46  |              0.058 |              0.054 |
| L4_ladder_delta     |             -0.415 |             -0.027 |             -0.009 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -3.576 |             -1.014 |             -0.241 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.322 |              0.099 |              0.063 |
| A_ladder_shuffled   |              0.066 |             -0.552 |             -0.418 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.486 |             -0.248 |             -0.134 |
| L1p_chain_purged    |              0.265 |             -0.324 |             -0.167 |
| L2_chain_paweighted |              0.498 |             -0.243 |             -0.13  |
| L3_direct_to_ref    |              0.32  |              0.061 |              0.032 |
| L4_ladder_delta     |             -0.242 |             -0.031 |             -0.003 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.14285714285714285` · Bailey OS degradation `0.0%` (p90 `0.3192%`) · contender spread `0.173%` · whole-field spread `0.329%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L3_direct_to_ref    |            407 |   0.881 |        0.00976 |         0     |
| L2_chain_paweighted |             41 |   0.089 |        0.00979 |         0.23  |
| L4_ladder_delta     |              8 |   0.017 |        0.00978 |         0.173 |
| L1_chain_ols        |              3 |   0.006 |        0.00979 |         0.237 |
| L0_foil             |              3 |   0.006 |        0.00977 |         0.104 |

**Reading**

- ⛔ DEFLATION — DSR over the eligible trial set is 0.602 < 0.95 (n_trials=5). State the shortfall in the unit that GROWS — folds and seasons, not p-decimals — before recording this as an absence (NF-D15 g″).

## 3.gb_pct — the arm set (`partial_pool@2`, context `baseline`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| L3_direct_to_ref    | ladder      | True     |  0.047716 |           0.248201 |        0.545455 |      0.174722 |            79.62 |              0.038283 |
| L2_chain_paweighted | ladder      | True     |  0.047735 |           0.209884 |        0.636364 |      0.234186 |            79.62 |              0.046506 |
| L1_chain_ols        | ladder      | True     |  0.047741 |           0.196977 |        0.545455 |      0.249986 |            79.62 |              0.048244 |
| L0_foil             | foil        | True     |  0.047835 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.047835 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_meanshift  | anchor      | True     |  0.047848 |          -0.026074 |        0.545455 |      0.739399 |            78.08 |              0.014363 |
| L1p_chain_purged    | sensitivity | True     |  0.04786  |          -0.053113 |        0.545455 |      0.828361 |            79.62 |              0.048244 |
| L4_ladder_delta     | ladder      | True     |  0.047952 |          -0.2442   |        0.454545 |      0.827017 |            79.62 |              0.048244 |
| A_ladder_shuffled   | anchor      | True     |  0.052203 |          -9.13162  |        0        |      0.99998  |            79.62 |              0.079989 |
| A_degenerate_mean   | anchor      | True     |  0.057312 |         -19.8125   |        0        |      0.999983 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |         a |        b | source                              |
|:--------------------|:---------|----------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A |  0.36932  | 0.233716 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   |  0.294007 | 0.392706 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A |  0.170168 | 0.659329 | chain:fitted                        |
| L1_chain_ols        | Triple-A |  0        | 1        | reference                           |
| L2_chain_paweighted | Single-A |  0.358966 | 0.252741 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   |  0.280401 | 0.418514 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A |  0.157739 | 0.683609 | chain:fitted                        |
| L2_chain_paweighted | Triple-A |  0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A |  0.273175 | 0.424339 | direct                              |
| L3_direct_to_ref    | High-A   |  0.22246  | 0.529925 | direct                              |
| L3_direct_to_ref    | Double-A |  0.157739 | 0.683609 | direct                              |
| L3_direct_to_ref    | Triple-A |  0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | -0.033008 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | -0.015435 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A |  0.001465 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A |  0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      394 |                              44.7 |       32.2 |     17   |       10.4 |       40.4 |
|         1 |      725 |                              62.1 |       37   |     29.1 |       14.2 |       19.7 |
|         2 |      855 |                              64.5 |       29.6 |     28.7 |       24.8 |       17   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -15.896 |            -20.062 |            -18.1   |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.075 |             -0.059 |             -0.026 |
| A_ladder_shuffled   |            -12.156 |            -11.528 |             -9.909 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.892 |              0.343 |             -0.151 |
| L1p_chain_purged    |             -0.113 |             -0.048 |             -0.088 |
| L2_chain_paweighted |              0.905 |              0.368 |             -0.134 |
| L3_direct_to_ref    |              0.856 |              0.462 |             -0.046 |
| L4_ladder_delta     |             -0.896 |             -0.325 |             -0.006 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -19.902 |            -20.779 |            -20.775 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.02  |             -0.044 |             -0.019 |
| A_ladder_shuffled   |             -7.743 |             -9.399 |             -8.457 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.466 |              0.254 |             -0.104 |
| L1p_chain_purged    |             -0.139 |             -0.054 |             -0.053 |
| L2_chain_paweighted |              0.477 |              0.277 |             -0.091 |
| L3_direct_to_ref    |              0.467 |              0.36  |             -0.023 |
| L4_ladder_delta     |             -0.573 |             -0.26  |              0.002 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.6428571428571429` · Bailey OS degradation `0.0888%` (p90 `0.8503%`) · contender spread `0.051%` · whole-field spread `0.494%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L3_direct_to_ref    |            208 |   0.45  |        0.04772 |         0     |
| L0_foil             |             96 |   0.208 |        0.04784 |         0.249 |
| L2_chain_paweighted |             76 |   0.165 |        0.04773 |         0.038 |
| L4_ladder_delta     |             47 |   0.102 |        0.04795 |         0.494 |
| L1_chain_ols        |             25 |   0.054 |        0.04774 |         0.051 |
| L1p_chain_purged    |             10 |   0.022 |        0.04786 |         0.302 |

**Reading**

- 🟡 no arm clears: best eligible `L3_direct_to_ref` MAE 0.04772 vs foil 0.04784 (0.25%, fold win rate 55%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.xwoba_against — the arm set (`partial_pool@2`, context `baseline`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| A_degenerate_mean   | anchor      | True     |  0.026109 |           0.501599 |            0.5  |      0.367211 |                0 |                     0 |
| L0_foil             | foil        | True     |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| L1_chain_ols        | ladder      | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| L2_chain_paweighted | ladder      | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| L3_direct_to_ref    | ladder      | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| L1p_chain_purged    | sensitivity | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| A_ladder_identity   | anchor      | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| A_ladder_meanshift  | anchor      | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| A_ladder_shuffled   | anchor      | False    |  0.02624  |           0        |            0    |    nan        |                0 |                     0 |
| L4_ladder_delta     | ladder      | False    |  0.02624  |          -0        |            0.25 |      0.843982 |                0 |                     0 |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |   a |   b | source                                          |
|:--------------------|:---------|----:|----:|:------------------------------------------------|
| L1_chain_ols        | Single-A |   0 |   1 | chain:identity_thin,identity_thin,identity_thin |
| L1_chain_ols        | High-A   |   0 |   1 | chain:identity_thin,identity_thin               |
| L1_chain_ols        | Double-A |   0 |   1 | chain:identity_thin                             |
| L1_chain_ols        | Triple-A |   0 |   1 | reference                                       |
| L2_chain_paweighted | Single-A |   0 |   1 | chain:identity_thin,identity_thin,identity_thin |
| L2_chain_paweighted | High-A   |   0 |   1 | chain:identity_thin,identity_thin               |
| L2_chain_paweighted | Double-A |   0 |   1 | chain:identity_thin                             |
| L2_chain_paweighted | Triple-A |   0 |   1 | reference                                       |
| L3_direct_to_ref    | Single-A |   0 |   1 | chain:identity_thin,identity_thin,identity_thin |
| L3_direct_to_ref    | High-A   |   0 |   1 | chain:identity_thin,identity_thin               |
| L3_direct_to_ref    | Double-A |   0 |   1 | chain:identity_thin                             |
| L3_direct_to_ref    | Triple-A |   0 |   1 | reference                                       |
| A_ladder_meanshift  | Single-A |   0 |   1 | chain:identity_thin,identity_thin,identity_thin |
| A_ladder_meanshift  | High-A   |   0 |   1 | chain:identity_thin,identity_thin               |
| A_ladder_meanshift  | Double-A |   0 |   1 | chain:identity_thin                             |
| A_ladder_meanshift  | Triple-A |   0 |   1 | reference                                       |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|
|         0 |       58 |                                 0 |        100 |
|         1 |       60 |                                 0 |        100 |
|         2 |       33 |                                 0 |        100 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -1.174 |              3.687 |              0.374 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0     |              0     |              0     |
| A_ladder_shuffled   |              0     |              0     |              0     |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0     |              0     |              0     |
| L1p_chain_purged    |              0     |              0     |              0     |
| L2_chain_paweighted |              0     |              0     |              0     |
| L3_direct_to_ref    |              0     |              0     |              0     |
| L4_ladder_delta     |             -0     |              0     |             -0     |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.16666666666666666` · Bailey OS degradation `0.0%` (p90 `0.0%`) · contender spread `0.0%` · whole-field spread `0.0%`

Flip distribution (which arm wins the in-sample halves):

| config   |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:---------|---------------:|--------:|---------------:|--------------:|
| L0_foil  |              6 |       1 |        0.02624 |             0 |

**Reading**

- ℹ️ INACTIVE arms (the ladder moved <1.0% of rows, so they are the foil in disguise and cannot be selected): L1_chain_ols, L2_chain_paweighted, L3_direct_to_ref, L1p_chain_purged, L4_ladder_delta. For a metric whose minor feature exists only at Triple-A this is STRUCTURAL — a mechanism that cannot act is a finding, not an omission (NF1.9).
- 🟡 no ELIGIBLE arm remains — every ladder arm is inactive. The shipped slice-1 configuration stands for this metric.

## 3b. ⭐ Reading the null honestly — is it the data, or is it my gate?

**Does the null rest on the gate choice?** Re-deciding the entire run with the deflation gates REMOVED — no PBO ceiling, no DSR floor — leaves survivors: **NONE**. ⇒ BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing (family of 4; the strictest Benjamini-Hochberg rung is p ≤ 0.025).

**The margin in the unit that GROWS.** Folds here ARE seasons — one held-out MLB debut cohort each — so an underpowered effect converts to a calendar re-test date, and a best arm that does not beat the foil ON AVERAGE is a genuine absence that no sample size rescues. The two are different kinds of null and are not recorded as the same thing (NF-D15 g″):

| metric        | arm                 |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   beats_foil |   clears_fold_bar |   clears_PBO |   clears_DSR |   clears_BH_rank1 | kind                                                    |   folds_have |   folds_needed_BH |   folds_needed_DSR |   extra_seasons_needed |
|:--------------|:--------------------|-------------------:|----------------:|--------------:|-------------:|------------------:|-------------:|-------------:|------------------:|:--------------------------------------------------------|-------------:|------------------:|-------------------:|-----------------------:|
| k_pct         | L3_direct_to_ref    |             0.1163 |        0.636364 |     0.0643037 |            1 |                 1 |            0 |            0 |                 0 | underpowered                                            |           11 |                18 |                 15 |                      7 |
| bb_pct        | L2_chain_paweighted |             0.2981 |        0.545455 |     0.145436  |            1 |                 0 |            0 |            0 |                 0 | underpowered                                            |           11 |                37 |                 35 |                     26 |
| hr_rate       | L3_direct_to_ref    |             0.104  |        0.727273 |     0.08128   |            1 |                 1 |            1 |            0 |                 0 | underpowered                                            |           11 |                22 |                 15 |                     11 |
| gb_pct        | L3_direct_to_ref    |             0.2482 |        0.545455 |     0.174722  |            1 |                 0 |            0 |            0 |                 0 | underpowered                                            |           11 |                47 |                 45 |                     36 |
| xwoba_against |                     |           nan      |      nan        |   nan         |          nan |               nan |          nan |          nan |               nan | no active arm — the mechanism cannot act on this metric |          nan |               nan |                nan |                    nan |

## 4. What was applied

_Nothing. No metric cleared its deflated gate, so the shipped E7.12-slice-1 emission stands verbatim. A null add is DROPPED, never shipped — that is the correct outcome for a null bake-off, not a failure._


## 5. Limitations

- **The chain composes attenuation.** Each rung regression is attenuated by measurement error in its source rate; composing three attenuates three times, so a Single-A line is shrunk harder by the chain than a single-step fit would shrink it. `L3_direct_to_ref` exists precisely to bound that, and the composed-`b` table above is the measurement.

- **The final rung still carries survivorship.** H1 confines the promotion-selection problem (E7.12 slice 2) to AAA→MLB — it does not remove it. Every number here remains conditional on the graduated population, and the per-tercile table is the honest read of who benefits.

- **A level stint is aggregated, not seasonal.** The pairs grain is (player, level), so a transition is 'his whole High-A line → his whole Double-A line'. A player who yo-yos is one temporally-ordered pair, not several; that is a real coarseness of the substrate.

- **The emission ladder is fitted over the whole substrate** while the evaluation ladder excluded each held-out player. The gate is therefore the conservative number.

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

