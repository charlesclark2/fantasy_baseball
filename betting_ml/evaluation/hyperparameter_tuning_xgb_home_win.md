# XGBoost home_win Hyperparameter Tuning (Optuna TPE)

Optuna TPE sampler (seed=42), direction=minimize, n_trials=50.
Platt calibration (sigmoid) applied within each CV fold via LogisticRegression.

## XGBoost home_win Hyperparameter Search Results

Note that scores are Brier scores (lower is better).

| Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |
|--------|-------------------|----------------|-----------------|--------|
| Brier Score | 0.2443 | 0.2443 | +0.01% ✓ | 50 |

Baseline sourced from Snowflake table `baseball_data.betting_ml.cv_results_win_outcome` (model='xgb_platt').

**Best hyperparameter values:**

- `max_depth`: 4
- `learning_rate`: 0.033342
- `n_estimators`: 161
- `subsample`: 0.9044
- `colsample_bytree`: 0.7850
- `reg_alpha`: 0.2189
- `reg_lambda`: 1.0764

## Optuna Trial Convergence

The best Brier score of 0.2443 was first achieved at trial number 17 (out of 50 total trials).

Convergence required extended search beyond the first 10 trials, indicating a more complex hyperparameter landscape for this target.

## Best Hyperparameter Configuration

```python
best_params = {
    "max_depth": 4,
    "learning_rate": 0.033342,
    "n_estimators": 161,
    "subsample": 0.9044,
    "colsample_bytree": 0.7850,
    "reg_alpha": 0.2189,
    "reg_lambda": 1.0764,
}
```

## Persisted Model

The tuned Platt-calibrated XGBoost classifier was retrained on the last CV fold's training split (Platt calibrator fitted on eval split) and persisted via `save_model()` from `betting_ml.utils.model_io`. The persisted object is a `PlattCalibratedXGBClassifier` wrapper containing the XGBClassifier and the fitted Platt (sigmoid) calibrator (LogisticRegression).

| Target | Model Name | Eval Year | Path |
|--------|------------|-----------|------|
| home_win | xgb_classifier_tuned | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl` |

Model saved successfully. ✓ (persisted)
