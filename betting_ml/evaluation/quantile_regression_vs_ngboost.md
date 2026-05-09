# Quantile Regression vs. NGBoost v2 — Total Runs

## Method

LightGBM quantile regression (`objective='quantile'`) at 5 alpha levels: [0.1, 0.25, 0.5, 0.75, 0.9].
Trained on the same temporal CV splits as NGBoost v2 (`all_season_splits`, `min_train_seasons=3`).
Same retained feature set and `build_imputation_pipeline()` preprocessing.
Half-life decay sample_weights: not applied.

## Promotion Gates

| Gate | Threshold | LightGBM q50 | NGBoost v2 | Pass? |
|------|-----------|--------------|------------|-------|
| CV MAE (q50) | ≤ 3.5107 | 3.4791 | 3.5107 | Y ✓ |
| std(pred_q50) | ≥ 1.5 | 0.9325 | 0.77 | N ✗ |
| abs(mean_residual) | ≤ 0.5 | 0.5951 | — | N ✗ |

**pct_pred_q50 > total_line_consensus**: 0.408

## Per-Fold CV Results

| Eval Year | Train N | Eval N | MAE(q50) |
|-----------|---------|--------|----------|
| 2024 | 5,976 | 2,002 | 3.3645 |
| 2025 | 7,978 | 2,025 | 3.5892 |
| 2026 | 10,003 | 314 | 3.5000 |

**Mean CV MAE (q50)**: 3.4791  |  **std(OOF pred_q50)**: 0.9325  |  **mean_residual**: -0.5951

## All-Quantile Coverage

| Alpha | OOF Coverage Rate | Expected |
|-------|------------------|----------|
| 0.10 | 0.129 | 0.10 |
| 0.25 | 0.282 | 0.25 |
| 0.50 | 0.490 | 0.50 |
| 0.75 | 0.729 | 0.75 |
| 0.90 | 0.864 | 0.90 |

*(Coverage rate = fraction of actuals below the predicted quantile. Should match alpha if well-calibrated.)*

## Conclusion

Gate(s) failed: **std, residual** — NGBoost v2 remains in production for total_runs. LightGBM quantile artifacts archived to `models/total_runs/archive/`.
