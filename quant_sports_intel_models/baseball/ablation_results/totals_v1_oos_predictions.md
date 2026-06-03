# Totals v1 — Walk-Forward OOS Predictions (10.6 task 1, unblocks 10.5)

- **OOS surface:** 7269 games, seasons [2023, 2024, 2025, 2026] (2021–22 train-only under min_train_seasons=2).
- **Bovada-line, settled calibration set:** 5256.
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
- **OOS ECE:** 0.0452
- **OOS Brier:** 0.2326 vs naive-0.50 0.2500 (beats naive) · vs Bovada de-vig 0.2448 (beats Bovada)

### OOS reliability (10 bins)
| bin          |   n |   mean_pred |   frac_over |     gap |
|:-------------|----:|------------:|------------:|--------:|
| [0.00, 0.10) | 104 |      0.0538 |      0.2981 | -0.2443 |
| [0.10, 0.20) | 257 |      0.1609 |      0.2101 | -0.0493 |
| [0.20, 0.30) | 579 |      0.2549 |      0.2746 | -0.0197 |
| [0.30, 0.40) | 805 |      0.3532 |      0.3317 |  0.0216 |
| [0.40, 0.50) | 936 |      0.4508 |      0.4380 |  0.0128 |
| [0.50, 0.60) | 948 |      0.5500 |      0.5095 |  0.0405 |
| [0.60, 0.70) | 800 |      0.6465 |      0.6238 |  0.0228 |
| [0.70, 0.80) | 537 |      0.7431 |      0.6797 |  0.0634 |
| [0.80, 0.90) | 211 |      0.8410 |      0.6777 |  0.1632 |
| [0.90, 1.00] |  79 |      0.9459 |      0.5190 |  0.4270 |

> This is a **sanity read**, not the promotion gate. The formal gate is Story 10.6,
> which adds the NGBoost champion's OOS surface (built there or via its live
> `daily_model_predictions` history) and applies the full champion-vs-challenger rubric.
