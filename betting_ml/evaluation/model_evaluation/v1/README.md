# model_evaluation/v1 — 7.MA Production Baseline Snapshot

Snapshotted 2026-05-08 before Card 8.W batch retrain.

These files represent the 7.MA retrain (2026-05-04) — the last joint retrain
before Phase 8 feature engineering landed. They are the fold-level ground truth
for every comparison report written against the current production models.

## Artifact inventory

| File | Contents |
|---|---|
| `features_fold_{2022..2025}.parquet` | Full feature matrix per CV fold (294 columns) |
| `targets_fold_{2022..2025}.parquet` | Target labels (home_win, total_runs, run_differential) per fold |
| `results_*.parquet` | Fold-level CV results for each candidate architecture |
| `feature_importance_v1.parquet` | SHAP / gain importance for the promoted home_win v1 model |
| `shap_importance_fold2025.png` | SHAP beeswarm for 2025 holdout fold |
| `results_calibration.parquet` | Calibration grid results (Platt, isotonic) |

## Production models this snapshot corresponds to

| Target | Artifact | CV metric |
|---|---|---|
| home_win | `home_win/elasticnet_2026.pkl` (v1) | Brier 0.2422 |
| total_runs | `total_runs/ngboost_decay_weighted.pkl` (v2) | MAE 3.5107 (decay-weighted) |
| run_differential | `run_differential/ngboost_decay_weighted.pkl` (v1) | MAE 3.4724 |

Training-loop note: The total_runs and run_differential artifacts were retrained
under the 8.N decay-weighted sample weights (half_life=162). The fold-level
features/targets files here do NOT include the sample weights used at fit time —
those were computed inline by `sample_weights.py`. Recompute via
`betting_ml/utils/sample_weights.py` if fold-level weighted comparison is needed.
