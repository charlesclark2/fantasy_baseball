# Win Outcome Classification — Baseline Model Results (Card 4.11)

## Per-Season Metrics by Model

| Season | Naive Log Loss | Logistic Log Loss | XGB Platt Log Loss | XGB Isotonic Log Loss | Logistic Brier | XGB Platt Brier | Logistic AUC | XGB Platt AUC |
|---|---|---|---|---|---|---|---|---|
| 2019 | 0.6919 | 0.6745 | 0.6739 | **0.6686** | 0.2408 | 0.2405 | 0.6043 | 0.6064 |
| 2021 | 0.6898 | **0.6744** | 0.6836 | 0.6790 | 0.2408 | 0.2453 | 0.5974 | 0.5609 |
| 2022 | 0.6903 | 0.6748 | 0.6782 | **0.6715** | 0.2409 | 0.2426 | 0.5994 | 0.5864 |
| 2023 | 0.6928 | 0.6870 | 0.6893 | **0.6841** | 0.2469 | 0.2481 | 0.5653 | 0.5429 |
| 2024 | 0.6918 | 0.6816 | 0.6821 | **0.6771** | 0.2443 | 0.2446 | 0.5787 | 0.5771 |
| 2025 | 0.6905 | 0.6859 | 0.6847 | **0.6792** | 0.2465 | 0.2458 | 0.5530 | 0.5594 |
| 2026 | 0.6898 | 0.6961 | 0.6797 | **0.6231** | 0.2514 | 0.2433 | 0.4965 | 0.5972 |

## Model Comparison Summary

Average log loss, Brier score, and AUC-ROC across all CV folds:

| Model | Mean Log Loss | Mean Brier Score | Mean AUC-ROC |
|---|---|---|---|
| naive_baseline | 0.6910 | 0.2489 | 0.5000 |
| logistic | 0.6820 | 0.2445 | 0.5707 |
| xgb_platt | 0.6816 | 0.2443 | 0.5758 |
| xgb_isotonic | 0.6689 | 0.2393 | 0.5912 |

**Best log loss:** xgb_isotonic (mean=0.6689)
**Best Brier score:** xgb_isotonic (mean=0.2393)
**Best AUC-ROC:** xgb_isotonic

## Calibration Analysis

Calibration curves are computed by binning predicted probabilities into 10 equal-width [0, 1] buckets, then comparing mean predicted probability against actual home win rate per bin. Expected Calibration Error (ECE) is the weighted mean of |mean_pred_prob − actual_win_rate| across non-empty bins, weighted by the fraction of games in each bin. Smaller ECE indicates better calibration.

| Fold | XGB Uncalibrated ECE | XGB Platt ECE | XGB Isotonic ECE | Logistic ECE |
|---|---|---|---|---|
| 2019 | 0.0742 | 0.0069 | 0.0000 | 0.0227 |
| 2021 | 0.0899 | 0.0163 | 0.0000 | 0.0133 |
| 2022 | 0.0540 | 0.0102 | 0.0000 | 0.0115 |
| 2023 | 0.0765 | 0.0072 | 0.0000 | 0.0296 |
| 2024 | 0.0479 | 0.0092 | 0.0000 | 0.0089 |
| 2025 | 0.0573 | 0.0092 | 0.0000 | 0.0238 |
| 2026 | 0.0742 | 0.0242 | 0.0000 | 0.0423 |

**Better calibration method: isotonic**
- Platt scaling average ECE: 0.0119
- Isotonic regression average ECE: 0.0000

XGBoost raw (uncalibrated) predictions typically show overconfidence in high-probability bins (predicted >0.6 but actual rate lower) and underconfidence in mid-range bins. Post-calibration with either Platt or isotonic regression corrects this systematic bias, producing ECE values closer to those of Logistic Regression.

## Home Team Bias Analysis

NB01 finding: home advantage declined from 0.548 (2020) to 0.519 (2023). A model using a static home win rate will systematically overprice home teams in recent seasons. The feature `home_win_rate_trailing_3yr` was designed to capture this trend by using a rolling 3-year home win rate rather than a fixed historical baseline.

| Season | Log Loss with HWRT | Log Loss without HWRT | Brier with HWRT | Brier without HWRT | Home Bias Direction |
|---|---|---|---|---|---|
| 2023 | 0.6893 | 0.6887 | 0.2481 | 0.2478 | neutral |
| 2024 | 0.6821 | 0.6827 | 0.2446 | 0.2448 | neutral |
| 2025 | 0.6847 | 0.6834 | 0.2458 | 0.2452 | neutral |

`home_win_rate_trailing_3yr` **does not materially reduce** the home team overpricing bias in 2023–2025 seasons.
Home bias directions by season: 2023:neutral, 2024:neutral, 2025:neutral.

## Best Model Selection

**Recommended model for downstream EV calculations (Phase 6): `xgb_isotonic`**

Calibration quality is the primary criterion because probability outputs feed directly into EV calculations in Phase 6. `xgb_isotonic` achieves the best overall ECE with isotonic calibration (mean ECE = 0.0000).

On point metrics, `xgb_isotonic` achieves the best mean log loss (0.6689) and `xgb_isotonic` achieves the best mean Brier score (0.2393).

The marginal ECE difference between Platt and isotonic calibration (Platt=0.0119 vs. isotonic=0.0000) favors isotonic regression. The additional complexity of isotonic regression is justified by its improved ECE, which directly benefits EV accuracy in Phase 6.

Forward reference: in Card 4.13 probability output layer, this classifier's win probability output will be compared against the regression-derived win probability from NGBoost Normal (Card 4.10); the better-calibrated model should anchor the downstream EV calculation.
