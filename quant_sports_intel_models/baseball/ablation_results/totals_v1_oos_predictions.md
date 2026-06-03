# Totals v1 — Walk-Forward OOS Predictions (10.6 task 1, unblocks 10.5)

- **OOS surface:** 7269 games, seasons [2023, 2024, 2025, 2026] (2021–22 train-only under min_train_seasons=2).
- **Bovada-line, settled calibration set:** 4580.
- Each game scored by a model trained ONLY on prior seasons — this is the honest
  out-of-sample surface 10.5 (alpha) and 10.6 (champion-vs-challenger) consume.

## Per-fold OOS metrics (should track the champion in-sample CV ~NLL 2.78 / MAE 3.22 / calib 0.80)
|   season |    n |   oos_nll |   oos_mae |   oos_calib_80 |   oos_std_pred |
|---------:|-----:|----------:|----------:|---------------:|---------------:|
|     2023 | 2201 |    2.7812 |    3.1873 |         0.796  |         3.6856 |
|     2024 | 2199 |    2.7146 |    2.9985 |         0.8327 |         3.5925 |
|     2025 | 2201 |    2.7763 |    3.2431 |         0.8092 |         3.8216 |
|     2026 |  668 |    2.8616 |    3.4627 |         0.7769 |         3.7855 |

## OOS calibration (the honest version of 10.4)
- **OOS ECE:** 0.0313
- **OOS Brier:** 0.2230 vs naive-0.50 0.2500 (beats naive) · vs Bovada de-vig 0.2469 (beats Bovada)

### OOS reliability (10 bins)
| bin          |   n |   mean_pred |   frac_over |     gap |
|:-------------|----:|------------:|------------:|--------:|
| [0.00, 0.10) |  76 |      0.0520 |      0.2632 | -0.2112 |
| [0.10, 0.20) | 224 |      0.1606 |      0.1786 | -0.0180 |
| [0.20, 0.30) | 521 |      0.2546 |      0.2610 | -0.0064 |
| [0.30, 0.40) | 714 |      0.3529 |      0.3193 |  0.0336 |
| [0.40, 0.50) | 835 |      0.4504 |      0.4359 |  0.0144 |
| [0.50, 0.60) | 833 |      0.5498 |      0.4970 |  0.0528 |
| [0.60, 0.70) | 710 |      0.6470 |      0.6465 |  0.0005 |
| [0.70, 0.80) | 462 |      0.7427 |      0.7143 |  0.0284 |
| [0.80, 0.90) | 165 |      0.8393 |      0.7576 |  0.0818 |
| [0.90, 1.00] |  40 |      0.9420 |      0.6250 |  0.3170 |

> This is a **sanity read**, not the promotion gate. The formal gate is Story 10.6,
> which adds the NGBoost champion's OOS surface (built there or via its live
> `daily_model_predictions` history) and applies the full champion-vs-challenger rubric.
