# Quantile Regression vs. NGBoost v2 — Total Runs

## Method

LightGBM quantile regression (`objective='quantile'`) at 5 alpha levels: [0.1, 0.25, 0.5, 0.75, 0.9].
Trained on the same temporal CV splits as NGBoost v2 (`all_season_splits`, `min_train_seasons=3`).
Same retained feature set and `build_imputation_pipeline()` preprocessing.
Half-life decay sample_weights: not applied.

## Promotion Gates

| Gate | Threshold | LightGBM q50 | NGBoost v2 | Pass? |
|------|-----------|--------------|------------|-------|
| CV MAE (q50) | ≤ 3.3251 | 3.3289 | 3.3251 | N ✗ |
| std(pred_q50) | ≥ 1.5 | 1.3932 | 0.77 | N ✗ |
| abs(mean_residual) | ≤ 0.5 | 0.2584 | — | Y ✓ |

**pct_pred_q50 > total_line_consensus**: 0.549

## Per-Fold CV Results

| Eval Year | Train N | Eval N | MAE(q50) |
|-----------|---------|--------|----------|
| 2024 | 5,970 | 2,002 | 3.2249 |
| 2025 | 7,972 | 2,026 | 3.4453 |
| 2026 | 9,998 | 792 | 3.2941 |

**Mean CV MAE (q50)**: 3.3289  |  **std(OOF pred_q50)**: 1.3932  |  **mean_residual**: -0.2584

## All-Quantile Coverage

| Alpha | OOF Coverage Rate | Expected |
|-------|------------------|----------|
| 0.10 | 0.136 | 0.10 |
| 0.25 | 0.309 | 0.25 |
| 0.50 | 0.519 | 0.50 |
| 0.75 | 0.746 | 0.75 |
| 0.90 | 0.878 | 0.90 |

*(Coverage rate = fraction of actuals below the predicted quantile. Should match alpha if well-calibrated.)*

## Conclusion

Gate(s) failed: **MAE, std** — NGBoost v2 remains in production for total_runs. LightGBM quantile artifacts archived to `models/total_runs/archive/`.
