# Layer 3 Totals — Architecture Comparison (Story 10.2)

- Games: **11661**; walk-forward folds: **4** (min_train_seasons=2); consistency needed: **3/4**.
- Target overdispersion var/mean = **2.26** (NegBin justified).
- Gates: NLL < C(GLM) floor; calib_80 ≥ 0.8; MAE ≤ 3.55 (NGBoost v3 champion).

## Head-to-head (mean CV)

| Candidate | NLL | MAE | calib_80 | std_pred |
|---|---|---|---|---|
| A — LightGBM+NegBin | 2.7850 | 3.226 | 0.804 | 3.731 |
| B — Ridge+NegBin | 2.9663 | 3.403 | 0.819 | 4.040 |
| C — NegBin GLM (floor) | 2.8503 | 3.401 | — | — |

**Winner: Candidate A LightGBM+NegBin** — tuned params: `{"n_estimators": 499, "learning_rate": 0.008401517819293084, "num_leaves": 15, "min_child_samples": 59, "subsample": 0.6946917707105881, "colsample_bytree": 0.61115107840185}`.

_std(pred) target ≥ 1.5 (variance-shrinkage fix; the failing NGBoost model was 0.77). Formal head-to-head vs. the live champion is Story 10.6._

## Candidate A folds

| eval year | n | NLL | MAE | calib_80 | std_pred | r |
|---|---|---|---|---|---|---|
| 2023 | 2201 | 2.7760 | 3.172 | 0.793 | 3.724 | 19.03 |
| 2024 | 2199 | 2.7180 | 3.007 | 0.830 | 3.607 | 17.19 |
| 2025 | 2201 | 2.7795 | 3.249 | 0.814 | 3.813 | 16.21 |
| 2026 | 668 | 2.8666 | 3.476 | 0.777 | 3.779 | 15.06 |

## Candidate B folds

| eval year | n | NLL | MAE | calib_80 | std_pred | r |
|---|---|---|---|---|---|---|
| 2023 | 2201 | 2.8040 | 3.332 | 0.819 | 4.153 | 10.92 |
| 2024 | 2199 | 2.7449 | 3.126 | 0.854 | 3.964 | 10.86 |
| 2025 | 2201 | 2.8032 | 3.367 | 0.829 | 4.125 | 10.96 |
| 2026 | 668 | 3.5132 | 3.789 | 0.772 | 3.917 | 10.64 |
