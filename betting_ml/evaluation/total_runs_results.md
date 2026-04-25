# Total Runs Regression — Baseline Model Results (Card 4.9)

## Per-Season MAE/RMSE by Model

| Season | Global Mean MAE | Ridge MAE | XGBoost MAE | NGBoost Normal MAE | NGBoost LogNormal MAE | Ridge RMSE | XGBoost RMSE | NGBoost Normal RMSE | NGBoost LogNormal RMSE |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | 3.688 | 3.712 | 3.767 | **3.701** | 3.712 | 4.740 | 4.848 | 4.754 | 4.777 |
| 2021 | 3.549 | 3.598 | 3.687 | 3.560 | **3.503** | 4.529 | 4.613 | 4.478 | 4.440 |
| 2022 | 3.528 | 3.473 | 3.502 | 3.414 | **3.404** | 4.401 | 4.433 | 4.346 | 4.331 |
| 2023 | 3.618 | 3.611 | 3.616 | 3.599 | **3.592** | 4.556 | 4.548 | 4.508 | 4.511 |
| 2024 | 3.440 | 3.389 | 3.380 | **3.378** | 3.390 | 4.252 | 4.251 | 4.227 | 4.241 |
| 2025 | 3.661 | **3.611** | 3.633 | 3.613 | 3.625 | 4.565 | 4.595 | 4.551 | 4.559 |
| 2026 | 3.822 | 3.837 | 3.885 | **3.774** | 3.790 | 4.775 | 4.752 | 4.654 | 4.668 |

## Model Comparison Summary

Average MAE and RMSE across all CV folds:

| Model | Mean MAE | Mean RMSE |
|---|---|---|
| global_mean | 3.6149 | 4.5442 |
| ridge | 3.6044 | 4.5454 |
| xgboost | 3.6385 | 4.5770 |
| ngboost_normal | 3.5769 | 4.5024 |
| ngboost_lognormal | 3.5736 | 4.5040 |

**Best MAE:** ngboost_lognormal
**Best RMSE:** ngboost_normal

## NGBoost Distribution Comparison (Normal vs. LogNormal)

| Distribution | Mean Fold MAE | Mean Brier Score (odds folds) |
|---|---|---|
| Normal vs. LogNormal: Normal | 3.5769 | 0.2568 |
| LogNormal | 3.5736 | 0.2562 |

**Recommended distribution:** LogNormal. LogNormal better fits blowout-game tails: NB01 found that blowout games exceed Gaussian predictions, and the log-normal's heavier right tail accommodates the asymmetric run distribution more faithfully than a symmetric Normal.

## P(Over/Under Line) Calibration

Note: odds data is available starting 2021 per the mart_game_odds_bridge match rates documented in project_context.md.

| Model | Mean Brier Score | Folds with Odds Data |
|---|---|---|
| xgboost (residual Normal) | 0.2746 | 6 |
| ngboost_normal | 0.2568 | 6 |
| ngboost_lognormal | 0.2562 | 6 |

## SHAP Feature Importance (XGBoost, Final Fold)

Top-20 features by mean |SHAP| from `shap.TreeExplainer` on the final CV fold:

| Rank | Feature | Mean |SHAP| |
|---|---|---|
| 1 | `total_line_consensus` | 0.22463 |
| 2 | `park_run_factor_3yr` | 0.14998 |
| 3 | `home_avg_barrel_pct_std` | 0.13355 |
| 4 | `away_starter_avg_fastball_velo_14d` | 0.09985 |
| 5 | `away_avg_xwoba_std` | 0.08321 |
| 6 | `away_starter_bb_pct_vs_lhb` | 0.08020 |
| 7 | `home_off_xwoba_7d` | 0.07651 |
| 8 | `home_bp_bb_pct_30d` | 0.07574 |
| 9 | `home_pit_woba_against_30d` | 0.07484 |
| 10 | `home_pit_woba_against_std` | 0.07026 |
| 11 | `home_starter_k_pct_std` | 0.06712 |
| 12 | `away_avg_bb_pct_std` | 0.06702 |
| 13 | `home_starter_avg_fastball_velo_7d` | 0.06623 |
| 14 | `away_wins` | 0.06557 |
| 15 | `away_vs_lhp_bb_pct_30d` | 0.06495 |
| 16 | `away_pit_bb_pct_30d` | 0.06364 |
| 17 | `away_starter_whiff_rate_std` | 0.06250 |
| 18 | `home_bp_bb_pct_14d` | 0.06120 |
| 19 | `home_avg_woba_std` | 0.06040 |
| 20 | `away_starter_k_pct_std` | 0.06003 |

Starter platoon-split features in top-20: ['away_starter_bb_pct_vs_lhb', 'away_vs_lhp_bb_pct_30d']
7-day recency features in top-20 (NB07 signal carriers): ['home_off_xwoba_7d', 'home_starter_avg_fastball_velo_7d']

## Best Model Selection

**Recommended model for downstream use (Cards 4.10–4.11): `ngboost_lognormal`**

ngboost_lognormal achieves mean MAE of 3.5736 across all CV folds, improving on the global mean baseline (3.6149) by 0.0413 runs. NGBoost provides a full predictive distribution (P(over/under line) computed directly), making it the most natural bridge to bookmaker implied probability comparison in downstream cards. NGBoost training is slower than Ridge but faster than XGBoost + residual fitting, and the distributional output eliminates the need for a separate residual-sigma calibration step.
