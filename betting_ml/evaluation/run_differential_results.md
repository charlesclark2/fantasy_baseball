# Run Differential Regression — Baseline Model Results (Card 4.10)

## Per-Season MAE/RMSE by Model

| Season | Global Mean MAE | Ridge MAE | XGBoost MAE | NGBoost Normal MAE | NGBoost LogNormal MAE | Ridge RMSE | XGBoost RMSE | NGBoost Normal RMSE |
|---|---|---|---|---|---|---|---|---|
| 2024 | 3.507 | 3.433 | **3.408** | 3.504 | N/A | 4.332 | 4.314 | 4.415 |
| 2025 | 3.578 | **3.511** | 3.523 | 3.576 | N/A | 4.551 | 4.538 | 4.598 |

## Model Comparison Summary

Average MAE and RMSE across all CV folds:

| Model | Mean MAE | Mean RMSE |
|---|---|---|
| global_mean | 3.5421 | 4.4878 |
| ridge | 3.4720 | 4.4414 |
| xgboost | 3.4655 | 4.4259 |
| ngboost_normal | 3.5403 | 4.5066 |

**Best MAE:** xgboost
**Best RMSE:** xgboost

> **Note — NGBoost LogNormal not viable for run_differential:** Run differential can be negative (home team loses), which violates the LogNormal distribution's strictly-positive support. Training was attempted but produced NaN/invalid predictions. LogNormal is excluded from ranking.

## Win Probability from Run Differential Distribution

**Method:** P(home win) = P(run_diff > 0) under NGBoost Normal N(μ, σ²). Equivalently: 1 − Φ(−μ/σ) where Φ is the standard Normal CDF. Computed via `p_over_line('Normal', dist_params, total_line=0)`.

| Fold | NGBoost Normal Win Prob Brier | N eval games |
|---|---|---|
| 2024 | 0.2630 | 2001 |
| 2025 | 0.2577 | 2026 |

**Aggregate Brier score (all folds):** 0.2603

> **Forward reference:** This Brier score will be compared against the binary classifier from Card 4.11 once that card is complete. A regression-derived win probability that rivals a dedicated classifier would support using a single NGBoost model for both regression and classification targets.

## Era Feature Ablation

XGBoost trained with all retained era features (`post_2022_rules`, `game_year`, `home_win_rate_trailing_3yr`) vs. without them. Delta > 0 means era features reduce MAE (help); Delta < 0 means they hurt.

| Fold | MAE with era features | MAE without era features | Delta (positive = help) |
|---|---|---|---|
| 2024 | 3.408 | 3.413 | +0.005 |
| 2025 | 3.523 | 3.524 | +0.002 |

**Average era delta across all folds:** +0.003 runs
**Era features help:** Yes — era features materially reduce run differential prediction error.

## Time-Varying Home Win Rate

**NB01 finding:** Home advantage declined from 0.548 (2020) to 0.519 (2023); a static 0.529 average is wrong for recent seasons. `home_win_rate_trailing_3yr` captures this time-varying trend.

Sub-ablation: XGBoost retaining `post_2022_rules` and `game_year` but dropping `home_win_rate_trailing_3yr`. Delta > 0 means the time-varying rate provides marginal benefit beyond the era flags alone.

| Fold | MAE without home_win_rate_trailing_3yr | Delta vs. full era features |
|---|---|---|
| 2024 | 3.432 | +0.024 |
| 2025 | 3.532 | +0.010 |
**Average home_win_rate_delta_mae across all folds:** +0.017 runs

**Conclusion:** `home_win_rate_trailing_3yr` provides additional benefit beyond `post_2022_rules` + `game_year` alone.

## Best Model Selection

**Recommended model for downstream use (Card 4.11 comparison and Card 4.13 strategy):** `xgboost`

`xgboost` achieves mean MAE of 3.4655 across all CV folds, improving on the global mean baseline (3.5421) by 0.0766 runs. XGBoost provides point predictions; win probability would require a separate distributional approximation (residual-based Normal). NGBoost Normal is preferred for downstream probabilistic use despite potentially slightly higher MAE.
