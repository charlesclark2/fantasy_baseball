# XGBoost total_runs Hyperparameter Tuning (Card 4.12a)

## XGBoost total_runs Hyperparameter Search Results

Optuna TPE sampler with 50 trials; baseline MAE sourced from Snowflake table `baseball_data.betting_ml.cv_results_tot_runs` (model='xgboost').

| Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |
|--------|-------------------|----------------|-----------------|--------|
| MAE | 3.6385 | 3.5655 | +2.01% | 50 |

**Best hyperparameters:**

- `max_depth`: 3
- `learning_rate`: 0.015252
- `n_estimators`: 238
- `subsample`: 0.7534
- `colsample_bytree`: 0.7629
- `reg_alpha`: 0.2155
- `reg_lambda`: 1.6832

## Optuna Trial Convergence

The best MAE of 3.5655 was first achieved at trial number 22 (out of 50 total trials).

Convergence required extended search beyond the first 10 trials, indicating a more complex hyperparameter landscape for this target.

## Best Hyperparameter Configuration

```python
best_params = {
    "max_depth": 3,
    "learning_rate": 0.015252,
    "n_estimators": 238,
    "subsample": 0.7534,
    "colsample_bytree": 0.7629,
    "reg_alpha": 0.2155,
    "reg_lambda": 1.6832,
}
```

## Persisted Model

The tuned XGBoost model was retrained on the last CV fold's training split and persisted via `save_model()` from `betting_ml.utils.model_io`.

| Target | Model Name | Eval Year | Path |
|--------|------------|-----------|------|
| total_runs | xgb_tuned | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/total_runs/xgb_tuned_2026.pkl` |

Model saved successfully. ✓ (persisted)
