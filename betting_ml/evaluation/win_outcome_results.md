# Win Outcome Classification — Baseline Model Results (Card 4.11)

## Per-Season Metrics by Model

| Season | Naive Log Loss | Logistic Log Loss | XGB Platt Log Loss | XGB Isotonic Log Loss | Logistic Brier | XGB Platt Brier | Logistic AUC | XGB Platt AUC |
|---|---|---|---|---|---|---|---|---|
| 2024 | 0.6917 | 0.6772 | 0.6812 | **0.6748** | 0.2422 | 0.2441 | 0.5965 | 0.5829 |
| 2025 | 0.6905 | 0.6810 | 0.6815 | **0.6756** | 0.2442 | 0.2442 | 0.5757 | 0.5742 |
| 2026 | 0.6937 | 0.7023 | 0.6916 | **0.6733** | 0.2542 | 0.2492 | 0.5051 | 0.5313 |

## Model Comparison Summary

Average log loss, Brier score, and AUC-ROC across all CV folds:

| Model | Mean Log Loss | Mean Brier Score | Mean AUC-ROC |
|---|---|---|---|
| naive_baseline | 0.6920 | 0.2494 | 0.5000 |
| logistic | 0.6868 | 0.2469 | 0.5591 |
| xgb_platt | 0.6848 | 0.2459 | 0.5628 |
| xgb_isotonic | 0.6746 | 0.2412 | 0.5848 |

**Best log loss:** xgb_isotonic (mean=0.6746)
**Best Brier score:** xgb_isotonic (mean=0.2412)
**Best AUC-ROC:** xgb_isotonic

## Calibration Analysis

Calibration curves are computed by binning predicted probabilities into 10 equal-width [0, 1] buckets, then comparing mean predicted probability against actual home win rate per bin. Expected Calibration Error (ECE) is the weighted mean of |mean_pred_prob − actual_win_rate| across non-empty bins, weighted by the fraction of games in each bin. Smaller ECE indicates better calibration.

| Fold | XGB Uncalibrated ECE | XGB Platt ECE | XGB Isotonic ECE | Logistic ECE |
|---|---|---|---|---|
| 2024 | 0.0692 | 0.0096 | 0.0000 | 0.0170 |
| 2025 | 0.0567 | 0.0074 | 0.0000 | 0.0311 |
| 2026 | 0.1012 | 0.0040 | 0.0000 | 0.0542 |

**Better calibration method: isotonic**
- Platt scaling average ECE: 0.0070
- Isotonic regression average ECE: 0.0000

XGBoost raw (uncalibrated) predictions typically show overconfidence in high-probability bins (predicted >0.6 but actual rate lower) and underconfidence in mid-range bins. Post-calibration with either Platt or isotonic regression corrects this systematic bias, producing ECE values closer to those of Logistic Regression.

## Home Team Bias Analysis

NB01 finding: home advantage declined from 0.548 (2020) to 0.519 (2023). A model using a static home win rate will systematically overprice home teams in recent seasons. The feature `home_win_rate_trailing_3yr` was designed to capture this trend by using a rolling 3-year home win rate rather than a fixed historical baseline.

| Season | Log Loss with HWRT | Log Loss without HWRT | Brier with HWRT | Brier without HWRT | Home Bias Direction |
|---|---|---|---|---|---|
| 2024 | 0.6812 | 0.6810 | 0.2441 | 0.2440 | neutral |
| 2025 | 0.6815 | 0.6850 | 0.2442 | 0.2460 | neutral |

`home_win_rate_trailing_3yr` **does not materially reduce** the home team overpricing bias in 2023–2025 seasons.
Home bias directions by season: 2024:neutral, 2025:neutral.

## Best Model Selection

**Recommended model for downstream EV calculations (Phase 6): `xgb_isotonic`**

Calibration quality is the primary criterion because probability outputs feed directly into EV calculations in Phase 6. `xgb_isotonic` achieves the best overall ECE with isotonic calibration (mean ECE = 0.0000).

On point metrics, `xgb_isotonic` achieves the best mean log loss (0.6746) and `xgb_isotonic` achieves the best mean Brier score (0.2412).

The marginal ECE difference between Platt and isotonic calibration (Platt=0.0070 vs. isotonic=0.0000) favors isotonic regression. The additional complexity of isotonic regression is justified by its improved ECE, which directly benefits EV accuracy in Phase 6.

Forward reference: in Card 4.13 probability output layer, this classifier's win probability output will be compared against the regression-derived win probability from NGBoost Normal (Card 4.10); the better-calibrated model should anchor the downstream EV calculation.
