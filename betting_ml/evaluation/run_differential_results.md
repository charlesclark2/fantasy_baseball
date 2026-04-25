# Run Differential Regression — Baseline Model Results (Card 4.10)

## Per-Season MAE/RMSE by Model

| Season | Global Mean MAE | Ridge MAE | XGBoost MAE | NGBoost Normal MAE | NGBoost LogNormal MAE | Ridge RMSE | XGBoost RMSE | NGBoost Normal RMSE |
|---|---|---|---|---|---|---|---|---|
| 2019 | 3.698 | **3.541** | 3.609 | 3.554 | N/A | 4.549 | 4.662 | 4.597 |
| 2021 | 3.552 | 3.496 | 3.526 | **3.463** | N/A | 4.494 | 4.569 | 4.475 |
| 2022 | 3.474 | **3.336** | 3.393 | 3.341 | N/A | 4.316 | 4.381 | 4.321 |
| 2023 | 3.492 | 3.458 | 3.470 | **3.419** | N/A | 4.433 | 4.440 | 4.384 |
| 2024 | 3.504 | **3.403** | 3.414 | 3.410 | N/A | 4.313 | 4.337 | 4.314 |
| 2025 | 3.576 | 3.502 | 3.520 | **3.487** | N/A | 4.522 | 4.547 | 4.514 |

## Model Comparison Summary

Average MAE and RMSE across all CV folds:

| Model | Mean MAE | Mean RMSE |
|---|---|---|
| global_mean | 3.5492 | 4.5161 |
| ridge | 3.4559 | 4.4378 |
| xgboost | 3.4887 | 4.4894 |
| ngboost_normal | 3.4459 | 4.4341 |

**Best MAE:** ngboost_normal
**Best RMSE:** ngboost_normal

> **Note — NGBoost LogNormal not viable for run_differential:** Run differential can be negative (home team loses), which violates the LogNormal distribution's strictly-positive support. Training was attempted but produced NaN/invalid predictions. LogNormal is excluded from ranking.

## Win Probability from Run Differential Distribution

**Method:** P(home win) = P(run_diff > 0) under NGBoost Normal N(μ, σ²). Equivalently: 1 − Φ(−μ/σ) where Φ is the standard Normal CDF. Computed via `p_over_line('Normal', dist_params, total_line=0)`.

| Fold | NGBoost Normal Win Prob Brier | N eval games |
|---|---|---|
| 2019 | 0.2387 | 1999 |
| 2021 | 0.2445 | 1953 |
| 2022 | 0.2395 | 2007 |
| 2023 | 0.2460 | 2013 |
| 2024 | 0.2442 | 2002 |
| 2025 | 0.2448 | 2026 |

**Aggregate Brier score (all folds):** 0.2429

> **Forward reference:** This Brier score will be compared against the binary classifier from Card 4.11 once that card is complete. A regression-derived win probability that rivals a dedicated classifier would support using a single NGBoost model for both regression and classification targets.

## Era Feature Ablation

XGBoost trained with all retained era features (`post_2022_rules`, `game_year`, `home_win_rate_trailing_3yr`) vs. without them. Delta > 0 means era features reduce MAE (help); Delta < 0 means they hurt.

| Fold | MAE with era features | MAE without era features | Delta (positive = help) |
|---|---|---|---|
| 2019 | 3.609 | 3.582 | -0.027 |
| 2021 | 3.526 | 3.524 | -0.001 |
| 2022 | 3.393 | 3.385 | -0.008 |
| 2023 ← 2022 rule-change effect | 3.470 | 3.478 | +0.008 |
| 2024 | 3.414 | 3.418 | +0.004 |
| 2025 | 3.520 | 3.541 | +0.020 |

**2023 fold era delta:** +0.008 runs — motivated by NB01 finding of a ~0.64-run structural mean shift from the 2022 shift ban and pitch clock rule changes.
**Average era delta across all folds:** -0.001 runs
**Era features help:** No — era features do not consistently reduce prediction error across folds.

## Time-Varying Home Win Rate

**NB01 finding:** Home advantage declined from 0.548 (2020) to 0.519 (2023); a static 0.529 average is wrong for recent seasons. `home_win_rate_trailing_3yr` captures this time-varying trend.

Sub-ablation: XGBoost retaining `post_2022_rules` and `game_year` but dropping `home_win_rate_trailing_3yr`. Delta > 0 means the time-varying rate provides marginal benefit beyond the era flags alone.

| Fold | MAE without home_win_rate_trailing_3yr | Delta vs. full era features |
|---|---|---|
| 2019 | 3.595 | -0.014 |
| 2021 | 3.549 | +0.023 |
| 2022 | 3.391 | -0.002 |
| 2023 | 3.470 | +0.000 |
| 2024 | 3.395 | -0.019 |
| 2025 | 3.540 | +0.020 |

**2023 fold home_win_rate_delta_mae:** +0.000 runs
**Average home_win_rate_delta_mae across all folds:** +0.001 runs

**Conclusion:** `home_win_rate_trailing_3yr` marginal benefit is largely absorbed by `post_2022_rules` + `game_year`. The era flag and calendar year already capture most of the home advantage trend.

## Best Model Selection

**Recommended model for downstream use (Card 4.11 comparison and Card 4.13 strategy):** `ngboost_normal`

`ngboost_normal` achieves mean MAE of 3.4459 across all CV folds, improving on the global mean baseline (3.5492) by 0.1034 runs. NGBoost provides a full predictive distribution: P(home win) = P(run_diff > 0) is computed directly from the Normal CDF, eliminating the need for a separate calibration step. The derived win probability Brier score (see above) indicates whether this single model can substitute for a dedicated binary classifier (Card 4.11).
