# E7.15 H1 — the within-player level-translation ladder (batter side)

_generated 2026-08-02T03:33:57.869347+00:00 · foil = the SHIPPED E7.12-slice-1 configuration · `best_alpha = 0`_

> ⚠️ **A projection, not an edge claim.** H1 asks one question: does learning the LEVEL part of the MiLB→MLB translation from within-player minor→minor transitions — a substrate with no MLB label, no promotion selection, and 4–7× the rows of the labelled per-level cohort — translate better than learning it from graduates alone? An arm that does not clear its deflated gate is **DROPPED, not shipped**.

## 0. Pre-registration (written before the run)

- **Foil.** Every arm is measured against `L0_foil` = the configuration LIVE on the board today (the shipped slice-1 `ContextSpec` per metric), with the learner and its `weight_col` held FIXED. The only thing that varies is the feature (E7.9: 54–77% of a bake-off margin can be the learner swap).

- **Four ladder formulations**, not one: `L1_chain_ols`, `L2_chain_paweighted` (L1's matched pair for the weighting), `L3_direct_to_ref` (one-step maps, which avoid the chain's threefold attenuation compounding), `L4_ladder_delta` (NESTS the foil at coefficient 0). Plus `L1p_chain_purged` as a registered calendar-leakage sensitivity. A single architecture missing its gate is not a trustworthy null; the whole set missing it is.

- **Anchors.** `A_ladder_identity` must be a BYTE no-op; `A_ladder_meanshift` (the matched level-only foil) and `A_ladder_shuffled` (the within-player link destroyed) must LOSE; `A_degenerate_mean` must LOSE. A MISSING anchor BLOCKS — it is not a pass.

- **Gate for an ADD** (all must hold): strict OOS MAE improvement over the foil in ≥60% of held-out debut cohorts; the ladder MOVED >1.0% of rows; every anchor holds; PBO(eligible) < 0.2; DSR(eligible) ≥ 0.95; Benjamini-Hochberg over the metric family at α=0.1; and — for a board metric — a non-negative lift in the LOWEST promotion-propensity tercile.

- **Estimand preserved.** Same target, same labelled population, same emitted meaning, so the E8.0 board and the E7.5b betting prior stay comparable. Asserted per fold.

## 1. ⭐ The transition census — REPORTED BEFORE ANY SCORE

The n-multiplication is H1's entire premise, so the counts come first. `pct_never_mlb` is the share of transitions whose source player NEVER reached MLB — the population a graduates-only fit structurally cannot see, and the population the draft board is served on.


**woba**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2204 |              1727 |            78.4 |            372   |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1494 |               977 |            65.4 |            397.7 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             695 |               314 |            45.2 |            345.8 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2102 |              1361 |            64.7 |            423.3 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             982 |               439 |            44.7 |            365.6 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1314 |               577 |            43.9 |            437   |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   38 |                      6 |
|   2017 |                  327 |                      0 |
|   2018 |                  854 |                      0 |
|   2019 |                 1653 |                      0 |
|   2020 |                 2831 |                      0 |
|   2021 |                 2850 |                      0 |
|   2022 |                 3535 |                      0 |
|   2023 |                 4515 |                      0 |
|   2024 |                 5359 |                      0 |
|   2025 |                 6189 |                      0 |
|   2026 |                 7179 |                      0 |

**k_pct**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2204 |              1727 |            78.4 |            372   |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1494 |               977 |            65.4 |            397.7 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             695 |               314 |            45.2 |            345.8 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2102 |              1361 |            64.7 |            423.3 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             982 |               439 |            44.7 |            365.6 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1314 |               577 |            43.9 |            437   |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   38 |                      6 |
|   2017 |                  327 |                      0 |
|   2018 |                  854 |                      0 |
|   2019 |                 1653 |                      0 |
|   2020 |                 2831 |                      0 |
|   2021 |                 2850 |                      0 |
|   2022 |                 3535 |                      0 |
|   2023 |                 4515 |                      0 |
|   2024 |                 5359 |                      0 |
|   2025 |                 6189 |                      0 |
|   2026 |                 7179 |                      0 |

**bb_pct**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2204 |              1727 |            78.4 |            372   |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1494 |               977 |            65.4 |            397.7 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             695 |               314 |            45.2 |            345.8 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2102 |              1361 |            64.7 |            423.3 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             982 |               439 |            44.7 |            365.6 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1314 |               577 |            43.9 |            437   |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   38 |                      6 |
|   2017 |                  327 |                      0 |
|   2018 |                  854 |                      0 |
|   2019 |                 1653 |                      0 |
|   2020 |                 2831 |                      0 |
|   2021 |                 2850 |                      0 |
|   2022 |                 3535 |                      0 |
|   2023 |                 4515 |                      0 |
|   2024 |                 5359 |                      0 |
|   2025 |                 6189 |                      0 |
|   2026 |                 7179 |                      0 |

**iso**

| rung                 | level_src   | level_dst   | adjacent   | to_reference   |   n_transitions |   n_never_mlb_src |   pct_never_mlb |   median_pair_pa |
|:---------------------|:------------|:------------|:-----------|:---------------|----------------:|------------------:|----------------:|-----------------:|
| Single-A -> High-A   | Single-A    | High-A      | True       | False          |            2204 |              1727 |            78.4 |            372   |
| Single-A -> Double-A | Single-A    | Double-A    | False      | False          |            1494 |               977 |            65.4 |            397.7 |
| Single-A -> Triple-A | Single-A    | Triple-A    | False      | True           |             695 |               314 |            45.2 |            345.8 |
| High-A -> Double-A   | High-A      | Double-A    | True       | False          |            2102 |              1361 |            64.7 |            423.3 |
| High-A -> Triple-A   | High-A      | Triple-A    | False      | True           |             982 |               439 |            44.7 |            365.6 |
| Double-A -> Triple-A | Double-A    | Triple-A    | True       | True           |            1314 |               577 |            43.9 |            437   |

_evaluable debut cohorts: [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]; labelled rows scored per fold are E7.3's._


Calendar-PURGED transitions available per fold (the sensitivity arm's cost — the substrate starts in 2015, so the early folds see almost nothing):

|   fold |   n_transitions_used |   n_identity_fallbacks |
|-------:|---------------------:|-----------------------:|
|   2016 |                   38 |                      6 |
|   2017 |                  327 |                      0 |
|   2018 |                  854 |                      0 |
|   2019 |                 1653 |                      0 |
|   2020 |                 2831 |                      0 |
|   2021 |                 2850 |                      0 |
|   2022 |                 3535 |                      0 |
|   2023 |                 4515 |                      0 |
|   2024 |                 5359 |                      0 |
|   2025 |                 6189 |                      0 |
|   2026 |                 7179 |                      0 |

## 2. Verdict by metric

| metric   | verdict   | winner   | best_arm         |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | BH-FDR   |   PBO(eligible) |   DSR(eligible) |   low_tercile_lift_% |
|:---------|:----------|:---------|:-----------------|-------------------:|----------------:|--------------:|:---------|----------------:|----------------:|---------------------:|
| woba     | DROP      | L0_foil  | L3_direct_to_ref |             -0.039 |        0.454545 |      0.898641 | False    |        0.442857 |       0.0242823 |            0.472072  |
| k_pct    | DROP      | L0_foil  | L3_direct_to_ref |             -0.037 |        0.363636 |      0.805074 | False    |        0.628571 |       0.160942  |           -1.18198   |
| bb_pct   | DROP      | L0_foil  | L1p_chain_purged |              0.517 |        0.727273 |      0.162348 | False    |        0.514286 |       0.843985  |            0.0463513 |
| iso      | DROP      | L0_foil  | L3_direct_to_ref |              0.052 |        0.727273 |      0.104257 | False    |        0.7      |       0.704483  |            0.423212  |

`PBO(eligible)` and `DSR(eligible)` are computed over the ELIGIBLE arms — the search the selection actually ran — not over every arm scored; the whole-field figures are in the JSON. A field that CONTAINS its own anchors has a huge dispersion, and a deflation statistic computed over it measures the anchors (NF-D14). The eligible-set figure is the one pre-registered to bind.


## 3.woba — the arm set (`partial_pool@4`, context `levelenv`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| L0_foil             | foil        | True     |  0.028791 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.028791 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_meanshift  | anchor      | True     |  0.028797 |          -0.022736 |        0.272727 |      0.936182 |            76.75 |              0.009036 |
| L3_direct_to_ref    | ladder      | True     |  0.028802 |          -0.038518 |        0.454545 |      0.898641 |            77.54 |              0.032638 |
| L1p_chain_purged    | sensitivity | True     |  0.028814 |          -0.079898 |        0.454545 |      0.759004 |            77.54 |              0.035007 |
| L4_ladder_delta     | ladder      | True     |  0.02882  |          -0.103238 |        0.454545 |      0.829274 |            77.54 |              0.035007 |
| L1_chain_ols        | ladder      | True     |  0.028831 |          -0.138985 |        0.363636 |      0.847722 |            77.54 |              0.035007 |
| L2_chain_paweighted | ladder      | True     |  0.028832 |          -0.144864 |        0.363636 |      0.802785 |            77.54 |              0.037271 |
| A_ladder_shuffled   | anchor      | True     |  0.028962 |          -0.596319 |        0.454545 |      0.775439 |            77.54 |              0.054115 |
| A_degenerate_mean   | anchor      | True     |  0.029035 |          -0.848671 |        0.363636 |      0.753329 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |         a |        b | source                              |
|:--------------------|:---------|----------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A |  0.295594 | 0.098359 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   |  0.260691 | 0.212584 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A |  0.170927 | 0.502323 | chain:fitted                        |
| L1_chain_ols        | Triple-A |  0        | 1        | reference                           |
| L2_chain_paweighted | Single-A |  0.30341  | 0.077877 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   |  0.274474 | 0.172364 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A |  0.191731 | 0.438109 | chain:fitted                        |
| L2_chain_paweighted | Triple-A |  0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A |  0.234012 | 0.303574 | direct                              |
| L3_direct_to_ref    | High-A   |  0.222359 | 0.343874 | direct                              |
| L3_direct_to_ref    | Double-A |  0.191731 | 0.438109 | direct                              |
| L3_direct_to_ref    | Triple-A |  0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | -0.020918 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | -0.008828 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A |  0.004336 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A |  0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              48.1 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              56.9 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              61.2 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -1.835 |             -3.353 |              0.177 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.131 |              0.012 |             -0.069 |
| A_ladder_shuffled   |             -1.264 |             -4.011 |              0.864 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.66  |             -0.248 |             -0.087 |
| L1p_chain_purged    |              0.304 |             -0.24  |              0.04  |
| L2_chain_paweighted |              0.762 |             -0.393 |             -0.014 |
| L3_direct_to_ref    |              0.472 |              0.089 |             -0.104 |
| L4_ladder_delta     |             -0.001 |              0.073 |             -0.197 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -6.296 |             -2.32  |              1.269 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.095 |              0.003 |             -0.066 |
| A_ladder_shuffled   |             -0.928 |             -3.031 |              0.734 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.382 |             -0.241 |             -0.171 |
| L1p_chain_purged    |              0.162 |             -0.226 |             -0.058 |
| L2_chain_paweighted |              0.441 |             -0.356 |             -0.122 |
| L3_direct_to_ref    |              0.317 |              0.047 |             -0.124 |
| L4_ladder_delta     |             -0.003 |              0.052 |             -0.152 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.44285714285714284` · Bailey OS degradation `0.0882%` (p90 `0.3351%`) · contender spread `0.08%` · whole-field spread `0.145%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L0_foil             |            221 |   0.478 |        0.02879 |         0     |
| L4_ladder_delta     |             74 |   0.16  |        0.02882 |         0.103 |
| L2_chain_paweighted |             66 |   0.143 |        0.02883 |         0.145 |
| L1p_chain_purged    |             51 |   0.11  |        0.02881 |         0.08  |
| L3_direct_to_ref    |             50 |   0.108 |        0.0288  |         0.039 |

**Reading**

- 🟡 no arm clears: best eligible `L3_direct_to_ref` MAE 0.02880 vs foil 0.02879 (-0.04%, fold win rate 45%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.k_pct — the arm set (`partial_pool@2`, context `park:exposure+levelenv+rel:0.5k`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| A_ladder_meanshift  | anchor      | True     |  0.038417 |           0.045618 |        0.454545 |      0.255883 |            77.61 |              0.008274 |
| L0_foil             | foil        | True     |  0.038435 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.038435 |           0        |        0        |    nan        |             0    |              0        |
| L3_direct_to_ref    | ladder      | True     |  0.038449 |          -0.036659 |        0.363636 |      0.805074 |            77.61 |              0.010411 |
| L4_ladder_delta     | ladder      | True     |  0.038452 |          -0.046168 |        0.454545 |      0.886782 |            77.61 |              0.013898 |
| L1p_chain_purged    | sensitivity | True     |  0.03846  |          -0.066343 |        0.363636 |      0.818802 |            77.61 |              0.013898 |
| L2_chain_paweighted | ladder      | True     |  0.038472 |          -0.097916 |        0.454545 |      0.829852 |            77.61 |              0.013396 |
| L1_chain_ols        | ladder      | True     |  0.038477 |          -0.111153 |        0.454545 |      0.838932 |            77.61 |              0.013898 |
| A_ladder_shuffled   | anchor      | True     |  0.044622 |         -16.0973   |        0        |      0.999663 |            77.61 |              0.038689 |
| A_degenerate_mean   | anchor      | True     |  0.049949 |         -29.9579   |        0        |      0.999999 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |        a |        b | source                              |
|:--------------------|:---------|---------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A | 0.12277  | 0.501244 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   | 0.088821 | 0.629668 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A | 0.050732 | 0.775564 | chain:fitted                        |
| L1_chain_ols        | Triple-A | 0        | 1        | reference                           |
| L2_chain_paweighted | Single-A | 0.118806 | 0.51346  | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   | 0.085487 | 0.640009 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A | 0.047377 | 0.78978  | chain:fitted                        |
| L2_chain_paweighted | Triple-A | 0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A | 0.073507 | 0.675988 | direct                              |
| L3_direct_to_ref    | High-A   | 0.066319 | 0.704101 | direct                              |
| L3_direct_to_ref    | Double-A | 0.047377 | 0.78978  | direct                              |
| L3_direct_to_ref    | Triple-A | 0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | 0.018281 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | 0.010208 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A | 0.002413 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A | 0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              48.1 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              56.9 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              61.2 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -41.538 |            -26.367 |            -26.202 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.111 |              0.117 |              0.046 |
| A_ladder_shuffled   |            -21.719 |            -20.457 |            -19.284 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |             -2.439 |             -0.001 |              0.209 |
| L1p_chain_purged    |             -1.856 |              0.183 |              0.148 |
| L2_chain_paweighted |             -2.384 |              0.026 |              0.201 |
| L3_direct_to_ref    |             -1.182 |              0.061 |              0.082 |
| L4_ladder_delta     |             -0.201 |             -0.135 |              0.049 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -39.789 |            -31.162 |            -27.516 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |              0.105 |              0.049 |              0.014 |
| A_ladder_shuffled   |            -14.929 |            -15.339 |            -15.128 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |             -1.641 |             -0.047 |              0.13  |
| L1p_chain_purged    |             -1.227 |              0.046 |              0.067 |
| L2_chain_paweighted |             -1.607 |             -0.017 |              0.128 |
| L3_direct_to_ref    |             -0.8   |              0.044 |              0.052 |
| L4_ladder_delta     |             -0.131 |             -0.118 |              0.027 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.6285714285714286` · Bailey OS degradation `0.0201%` (p90 `0.217%`) · contender spread `0.046%` · whole-field spread `0.111%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L0_foil             |            303 |   0.656 |        0.03843 |         0     |
| L1p_chain_purged    |             49 |   0.106 |        0.03846 |         0.066 |
| L2_chain_paweighted |             32 |   0.069 |        0.03847 |         0.098 |
| L1_chain_ols        |             31 |   0.067 |        0.03848 |         0.111 |
| L4_ladder_delta     |             30 |   0.065 |        0.03845 |         0.046 |
| L3_direct_to_ref    |             17 |   0.037 |        0.03845 |         0.037 |

**Reading**

- 🟡 no arm clears: best eligible `L3_direct_to_ref` MAE 0.03845 vs foil 0.03843 (-0.04%, fold win rate 36%; the pre-registered bar is a strict OOS improvement in ≥60% of folds). DROPPED.

## 3.bb_pct — the arm set (`partial_pool@4`, context `park:exposure+levelenv+rel:2k`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| L1p_chain_purged    | sensitivity | True     |  0.017864 |           0.517301 |        0.727273 |      0.162348 |            77.61 |              0.00657  |
| L3_direct_to_ref    | ladder      | True     |  0.017918 |           0.216588 |        0.727273 |      0.342053 |            77.61 |              0.005313 |
| L2_chain_paweighted | ladder      | True     |  0.017928 |           0.164587 |        0.727273 |      0.398988 |            77.61 |              0.006447 |
| L1_chain_ols        | ladder      | True     |  0.017929 |           0.157421 |        0.727273 |      0.404865 |            77.61 |              0.00657  |
| L4_ladder_delta     | ladder      | True     |  0.017949 |           0.043814 |        0.727273 |      0.445439 |            77.61 |              0.00657  |
| L0_foil             | foil        | True     |  0.017957 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.017957 |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_meanshift  | anchor      | True     |  0.017986 |          -0.161332 |        0.545455 |      0.900355 |            77.61 |              0.003978 |
| A_ladder_shuffled   | anchor      | True     |  0.019565 |          -8.9508   |        0.090909 |      0.99948  |            77.61 |              0.009834 |
| A_degenerate_mean   | anchor      | True     |  0.020767 |         -15.645    |        0.090909 |      0.999826 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |         a |        b | source                              |
|:--------------------|:---------|----------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A |  0.073959 | 0.202534 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   |  0.061589 | 0.345828 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A |  0.03993  | 0.580989 | chain:fitted                        |
| L1_chain_ols        | Triple-A |  0        | 1        | reference                           |
| L2_chain_paweighted | Single-A |  0.071291 | 0.223506 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   |  0.058928 | 0.369093 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A |  0.038212 | 0.595382 | chain:fitted                        |
| L2_chain_paweighted | Triple-A |  0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A |  0.051451 | 0.429334 | direct                              |
| L3_direct_to_ref    | High-A   |  0.048143 | 0.483476 | direct                              |
| L3_direct_to_ref    | Double-A |  0.038212 | 0.595382 | direct                              |
| L3_direct_to_ref    | Triple-A |  0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | -0.009874 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | -0.003627 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A | -0.001223 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A |  0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              48.1 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              56.9 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              61.2 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -38.075 |            -18.202 |             -9.614 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |             -2.205 |             -0.109 |              0.076 |
| A_ladder_shuffled   |            -34.315 |            -15.556 |             -8.674 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |             -1.659 |              0.723 |              0.303 |
| L1p_chain_purged    |              0.046 |              1.217 |              0.369 |
| L2_chain_paweighted |             -1.216 |              0.689 |              0.283 |
| L3_direct_to_ref    |              1.442 |              0.401 |              0.165 |
| L4_ladder_delta     |              0.852 |             -0.257 |              0.041 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -36.99  |            -23.685 |            -10.633 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |             -1.375 |             -0.075 |              0.039 |
| A_ladder_shuffled   |            -21.926 |            -11.735 |             -6.922 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |             -0.996 |              0.566 |              0.207 |
| L1p_chain_purged    |              0.071 |              0.938 |              0.261 |
| L2_chain_paweighted |             -0.709 |              0.542 |              0.189 |
| L3_direct_to_ref    |              0.975 |              0.318 |              0.107 |
| L4_ladder_delta     |              0.535 |             -0.192 |              0.017 |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.5142857142857142` · Bailey OS degradation `0.6314%` (p90 `1.2967%`) · contender spread `0.355%` · whole-field spread `0.52%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L1p_chain_purged    |            207 |   0.448 |        0.01786 |         0     |
| L4_ladder_delta     |            126 |   0.273 |        0.01795 |         0.476 |
| L1_chain_ols        |             61 |   0.132 |        0.01793 |         0.362 |
| L0_foil             |             35 |   0.076 |        0.01796 |         0.52  |
| L2_chain_paweighted |             18 |   0.039 |        0.01793 |         0.355 |
| L3_direct_to_ref    |             15 |   0.032 |        0.01792 |         0.302 |

**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.514 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.355% and the in-sample halves split across arms a fraction of a percent apart (L1p_chain_purged 45% (+0.000%), L4_ladder_delta 27% (+0.476%), L1_chain_ols 13% (+0.362%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 3.iso — the arm set (`partial_pool@2`, context `park:exposure+levelenv+rel:2k`, learner held fixed)

| arm                 | kind        | active   |   oos_mae |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided |   pct_rows_moved |   mean_abs_delta_feat |
|:--------------------|:------------|:---------|----------:|-------------------:|----------------:|--------------:|-----------------:|----------------------:|
| L3_direct_to_ref    | ladder      | True     |  0.03845  |           0.05163  |        0.727273 |      0.104257 |            77.42 |              0.018372 |
| L0_foil             | foil        | True     |  0.03847  |           0        |        0        |    nan        |             0    |              0        |
| A_ladder_identity   | anchor      | False    |  0.03847  |           0        |        0        |    nan        |             0    |              0        |
| L4_ladder_delta     | ladder      | True     |  0.038473 |          -0.009197 |        0.545455 |      0.648063 |            77.42 |              0.019172 |
| A_ladder_meanshift  | anchor      | True     |  0.038478 |          -0.022126 |        0.363636 |      0.664467 |            77.42 |              0.012024 |
| L2_chain_paweighted | ladder      | True     |  0.038488 |          -0.046858 |        0.454545 |      0.592272 |            77.42 |              0.018583 |
| L1p_chain_purged    | sensitivity | True     |  0.038491 |          -0.05601  |        0.363636 |      0.633551 |            77.42 |              0.019172 |
| L1_chain_ols        | ladder      | True     |  0.038492 |          -0.058211 |        0.454545 |      0.612811 |            77.42 |              0.019172 |
| A_ladder_shuffled   | anchor      | True     |  0.041142 |          -6.94616  |        0.090909 |      0.996361 |            77.42 |              0.026329 |
| A_degenerate_mean   | anchor      | True     |  0.043138 |         -12.1362   |        0.090909 |      0.999271 |             0    |              0        |

**Composed level → reference maps** (`rate_ref = a + b · rate_level`) for the lead chain and direct arms — the compounding-attenuation hazard is visible here as a much smaller composed `b` for the chain than for the one-step direct fit:

| arm                 | level    |        a |        b | source                              |
|:--------------------|:---------|---------:|---------:|:------------------------------------|
| L1_chain_ols        | Single-A | 0.128739 | 0.198388 | chain:fitted,fitted,fitted          |
| L1_chain_ols        | High-A   | 0.108011 | 0.345295 | chain:fitted,fitted                 |
| L1_chain_ols        | Double-A | 0.070191 | 0.613636 | chain:fitted                        |
| L1_chain_ols        | Triple-A | 0        | 1        | reference                           |
| L2_chain_paweighted | Single-A | 0.126651 | 0.209117 | chain:fitted,fitted,fitted          |
| L2_chain_paweighted | High-A   | 0.105259 | 0.360182 | chain:fitted,fitted                 |
| L2_chain_paweighted | Double-A | 0.066766 | 0.633307 | chain:fitted                        |
| L2_chain_paweighted | Triple-A | 0        | 1        | reference                           |
| L3_direct_to_ref    | Single-A | 0.093779 | 0.485497 | direct                              |
| L3_direct_to_ref    | High-A   | 0.081377 | 0.550624 | direct                              |
| L3_direct_to_ref    | Double-A | 0.066766 | 0.633307 | direct                              |
| L3_direct_to_ref    | Triple-A | 0        | 1        | reference                           |
| A_ladder_meanshift  | Single-A | 0.018862 | 1        | chain:meanshift,meanshift,meanshift |
| A_ladder_meanshift  | High-A   | 0.013714 | 1        | chain:meanshift,meanshift           |
| A_ladder_meanshift  | Double-A | 0.013557 | 1        | chain:meanshift                     |
| A_ladder_meanshift  | Triple-A | 0        | 1        | reference                           |

**Anchors**

- identity byte no-op: `None` (max |Δ| = None)
- `meanshift_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `shuffled_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None
- `degenerate_vs_best_ladder`: challenger wins None/None folds, p=None, violated=None

**⚠️ What the propensity terciles actually CONTAIN** — read this before reading the tercile lifts. E7.12 slice 2 introduced these terciles as "the observable proxy for the un-promoted prospects we serve" and H5 inherited that reading; on the labelled cohort it runs the other way. The LOW-propensity tercile is the one RICHEST in **Triple-A** rows and POOREST in Single-A rows — it selects late-arriving graduates, not low-level prospects — and a Triple-A row is the ladder's REFERENCE level, so its delta is identically 0 and it cannot be moved at all:

|   stratum |   n_rows |   pct_rows_the_mechanism_can_move |   Double-A |   High-A |   Single-A |   Triple-A |
|----------:|---------:|----------------------------------:|-----------:|---------:|-----------:|-----------:|
|         0 |      162 |                              48.1 |       47.5 |     11.7 |        4.3 |       36.4 |
|         1 |      570 |                              56.9 |       37.9 |     25.8 |       10   |       26.3 |
|         2 |      962 |                              61.2 |       26.3 |     27.5 |       25.2 |       21   |

**Per promotion-propensity tercile — rows the ladder CAN move (⭐ what the H5 gate reads)** (stratum 0 = LOWEST propensity; a reference-level row contributes exactly zero lift by construction, so including it averages the mechanism over rows it structurally cannot touch):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |             -5.945 |            -17.315 |            -10.145 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |             -0.066 |              0.05  |             -0.152 |
| A_ladder_shuffled   |             -8.048 |            -11.2   |             -9.206 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              1.025 |             -0.624 |              0.012 |
| L1p_chain_purged    |              0.832 |             -0.405 |             -0.078 |
| L2_chain_paweighted |              1.015 |             -0.588 |              0.021 |
| L3_direct_to_ref    |              0.423 |             -0.161 |              0.075 |
| L4_ladder_delta     |              0.315 |             -0.16  |             -0.004 |

**Per promotion-propensity tercile — ALL scored rows** (stratum 0 = LOWEST propensity; published beside the gated view, because changing which population a gate reads without showing both is how a gate quietly starts measuring something else):

| arm                 |   tercile_0_lift_% |   tercile_1_lift_% |   tercile_2_lift_% |
|:--------------------|-------------------:|-------------------:|-------------------:|
| A_degenerate_mean   |            -13.306 |            -18.39  |            -10.636 |
| A_ladder_identity   |              0     |              0     |              0     |
| A_ladder_meanshift  |             -0.091 |              0.076 |             -0.065 |
| A_ladder_shuffled   |             -5.436 |             -8.157 |             -7.113 |
| L0_foil             |              0     |              0     |              0     |
| L1_chain_ols        |              0.721 |             -0.458 |             -0.006 |
| L1p_chain_purged    |              0.559 |             -0.296 |             -0.04  |
| L2_chain_paweighted |              0.713 |             -0.432 |              0.002 |
| L3_direct_to_ref    |              0.272 |             -0.086 |              0.087 |
| L4_ladder_delta     |              0.221 |             -0.117 |             -0     |

**Deflation** — PBO alone cannot separate 'my pick is unstable' from 'my pick is tied' (NF1.8), so all four numbers:

- PBO(eligible) `0.7` · Bailey OS degradation `0.1265%` (p90 `0.3222%`) · contender spread `0.061%` · whole-field spread `0.11%`

Flip distribution (which arm wins the in-sample halves):

| config              |   IS_half_wins |   share |   mean_oos_mae |   pct_vs_best |
|:--------------------|---------------:|--------:|---------------:|--------------:|
| L3_direct_to_ref    |            235 |   0.509 |        0.03845 |         0     |
| L2_chain_paweighted |            100 |   0.216 |        0.03849 |         0.099 |
| L0_foil             |             51 |   0.11  |        0.03847 |         0.052 |
| L1p_chain_purged    |             45 |   0.097 |        0.03849 |         0.108 |
| L4_ladder_delta     |             18 |   0.039 |        0.03847 |         0.061 |
| L1_chain_ols        |             13 |   0.028 |        0.03849 |         0.11  |

**Reading**

- ⛔ DEFLATION — PBO over the ELIGIBLE set is 0.700 ≥ 0.2. ⭐ READ IT AS A **TIE**, NOT AS OVERFITTING: the contender spread is 0.061% and the in-sample halves split across arms a fraction of a percent apart (L3_direct_to_ref 51% (+0.000%), L2_chain_paweighted 22% (+0.099%), L0_foil 11% (+0.052%)). Which tied arm wins is noise — exactly what a trustworthy learner-null looks like (E2.1-r). The honest record is 'no candidate robustly beats the shipped configuration', so the shipped configuration is now PROVEN rather than assumed. Either way it does not ship.

## 3b. ⭐ Reading the null honestly — is it the data, or is it my gate?

**Does the null rest on the gate choice?** Re-deciding the entire run with the deflation gates REMOVED — no PBO ceiling, no DSR floor — leaves survivors: **NONE**. ⇒ BH-FDR multiplicity — no arm's p clears the strictest rung, so removing the deflation gates changes nothing (family of 4; the strictest Benjamini-Hochberg rung is p ≤ 0.025).

**The margin in the unit that GROWS.** Folds here ARE seasons — one held-out MLB debut cohort each — so an underpowered effect converts to a calendar re-test date, and a best arm that does not beat the foil ON AVERAGE is a genuine absence that no sample size rescues. The two are different kinds of null and are not recorded as the same thing (NF-D15 g″):

| metric   | arm              |   pct_lift_vs_foil |   fold_win_rate |   p_one_sided | beats_foil   | clears_fold_bar   | clears_PBO   | clears_DSR   | clears_BH_rank1   | kind                                                             |   folds_have |   folds_needed_BH |   folds_needed_DSR |   extra_seasons_needed |
|:---------|:-----------------|-------------------:|----------------:|--------------:|:-------------|:------------------|:-------------|:-------------|:------------------|:-----------------------------------------------------------------|-------------:|------------------:|-------------------:|-----------------------:|
| woba     | L3_direct_to_ref |            -0.0385 |        0.454545 |      0.898641 | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan |                    nan |
| k_pct    | L3_direct_to_ref |            -0.0367 |        0.363636 |      0.805074 | False        | False             | False        | False        | False             | genuine absence — the best arm does not beat the foil on average |           11 |               nan |                nan |                    nan |
| bb_pct   | L1p_chain_purged |             0.5173 |        0.727273 |      0.162348 | True         | True              | False        | False        | False             | underpowered                                                     |           11 |                42 |                 35 |                     31 |
| iso      | L3_direct_to_ref |             0.0516 |        0.727273 |      0.104257 | True         | True              | False        | False        | False             | underpowered                                                     |           11 |                26 |                 37 |                     26 |

## 4. What was applied

_Nothing. No metric cleared its deflated gate, so the shipped E7.12-slice-1 emission stands verbatim. A null add is DROPPED, never shipped — that is the correct outcome for a null bake-off, not a failure._


## 5. Limitations

- **The chain composes attenuation.** Each rung regression is attenuated by measurement error in its source rate; composing three attenuates three times, so a Single-A line is shrunk harder by the chain than a single-step fit would shrink it. `L3_direct_to_ref` exists precisely to bound that, and the composed-`b` table above is the measurement.

- **The final rung still carries survivorship.** H1 confines the promotion-selection problem (E7.12 slice 2) to AAA→MLB — it does not remove it. Every number here remains conditional on the graduated population, and the per-tercile table is the honest read of who benefits.

- **A level stint is aggregated, not seasonal.** The pairs grain is (player, level), so a transition is 'his whole High-A line → his whole Double-A line'. A player who yo-yos is one temporally-ordered pair, not several; that is a real coarseness of the substrate.

- **The emission ladder is fitted over the whole substrate** while the evaluation ladder excluded each held-out player. The gate is therefore the conservative number.

- **`best_alpha = 0`** — a Dynasty/board projection and a betting prior, never a market bet.

