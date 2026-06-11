# Totals v1 — Walk-Forward OOS Predictions (10.6 task 1, unblocks 10.5)

- **OOS surface:** 7390 games, seasons [2023, 2024, 2025, 2026] (2021–22 train-only under min_train_seasons=2).
- **Bovada-line, settled calibration set:** 5330.
- Each game scored by a model trained ONLY on prior seasons — this is the honest
  out-of-sample surface 10.5 (alpha) and 10.6 (champion-vs-challenger) consume.

## Per-fold OOS metrics (should track the champion in-sample CV ~NLL 2.78 / MAE 3.22 / calib 0.80)
|   season |    n |   oos_nll |   oos_mae |   oos_calib_80 |   oos_std_pred |
|---------:|-----:|----------:|----------:|---------------:|---------------:|
|     2023 | 2201 |    2.7827 |    3.2013 |         0.7928 |         3.6878 |
|     2024 | 2199 |    2.717  |    3.0019 |         0.8304 |         3.5593 |
|     2025 | 2201 |    2.7793 |    3.2475 |         0.8019 |         3.787  |
|     2026 |  789 |    2.8401 |    3.3734 |         0.7795 |         3.777  |

## OOS calibration (the honest version of 10.4)
- **OOS ECE:** 0.0489
- **OOS Brier:** 0.2334 vs naive-0.50 0.2500 (beats naive) · vs Bovada de-vig 0.2448 (beats Bovada)

### OOS reliability (10 bins)
| bin          |   n |   mean_pred |   frac_over |     gap |
|:-------------|----:|------------:|------------:|--------:|
| [0.00, 0.10) | 102 |      0.0522 |      0.2941 | -0.2419 |
| [0.10, 0.20) | 275 |      0.1588 |      0.2400 | -0.0812 |
| [0.20, 0.30) | 569 |      0.2531 |      0.2267 |  0.0264 |
| [0.30, 0.40) | 812 |      0.3511 |      0.3584 | -0.0073 |
| [0.40, 0.50) | 903 |      0.4500 |      0.4286 |  0.0215 |
| [0.50, 0.60) | 975 |      0.5498 |      0.5118 |  0.0380 |
| [0.60, 0.70) | 834 |      0.6520 |      0.6271 |  0.0249 |
| [0.70, 0.80) | 514 |      0.7454 |      0.6790 |  0.0664 |
| [0.80, 0.90) | 257 |      0.8469 |      0.6654 |  0.1816 |
| [0.90, 1.00] |  89 |      0.9433 |      0.5506 |  0.3927 |

> This is a **sanity read**, not the promotion gate. The formal gate is Story 10.6,
> which adds the NGBoost champion's OOS surface (built there or via its live
> `daily_model_predictions` history) and applies the full champion-vs-challenger rubric.
