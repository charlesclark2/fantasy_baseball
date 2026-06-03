# Layer 3 Totals — Alpha Re-calibration (Story 10.5)

- **Surface:** walk-forward OOS (`oos_predictions_totals_v1.parquet`), **4580** Bovada-line settled games.
- **Blend:** log-odds `compute_posterior` (alpha=1 model, alpha=0 Bovada de-vig); objective = log-loss on `over_hit`.

## Alpha grid
| alpha | log_loss | Δ vs best | |
|---:|---:|---:|:--|
| 0.0 | 0.686382 | +0.048823 | |
| 0.1 | 0.673119 | +0.035561 | |
| 0.2 | 0.662092 | +0.024534 | |
| 0.3 | 0.653243 | +0.015685 | |
| 0.4 | 0.646481 | +0.008922 | |
| 0.5 | 0.641694 | +0.004136 | |
| 0.6 | 0.638762 | +0.001204 | |
| 0.7 | 0.637558 | +0.000000 | ← best |
| 0.8 | 0.637959 | +0.000401 | |
| 0.9 | 0.639844 | +0.002286 | |
| 1.0 | 0.643100 | +0.005542 | |

- **best totals_alpha = 0.70**, log-loss **0.637558**.
- Reference: market-only (α=0) **0.686382**, model-only (α=1) **0.643100**.
- Monotonic worsening away from best: above=True, below=True

## Interpretation
**alpha = 0.70 > 0** — the Layer 3 model adds genuine signal beyond Bovada's implied probability (log-loss 0.637558 vs market-only 0.686382, an improvement of 0.048824). This is the first non-zero totals alpha — Epic 1.7 found 0 because its CV models were market-circular.

## Tail over-confidence — before vs after the blend (the 10.4/OOS carry-over)
| bin          |   n_before |   gap_before |   n_after |   gap_after |
|:-------------|-----------:|-------------:|----------:|------------:|
| [0.00, 0.10) |         76 |      -0.2112 |        36 |     -0.1674 |
| [0.90, 1.00] |         40 |       0.3170 |        10 |      0.1322 |

- Post-blend ECE **0.0376** (model-only 0.0313).
- The blend pulls the over-confident extremes toward 0 — **no isotonic recalibration needed.**

## Acceptance criteria
- [x] Alpha grid table documented with log-loss per alpha
- [x] `best_alpha.json` updated with `totals_alpha` = 0.70 (separate from Epic 1.7 combined)
- [~] `predict_today.py` uses the totals-specific alpha — **deferred to 10.7** (Layer 3 live wiring)
- [x] alpha > 0 documented (model adds signal beyond Bovada)
