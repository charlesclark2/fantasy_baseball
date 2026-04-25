# XGBoost run_differential Hyperparameter Tuning — Card 4.12b

Optuna TPE sampler (seed=42), direction=minimize, n_trials=20.

## XGBoost run_differential Hyperparameter Search Results

| Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |
|---|---|---|---|---|
| MAE | 3.4887 | 3.4074 | -2.33% ✓ | 20 |

### Best Hyperparameter Values

- **colsample_bytree:** 0.6105835555603716
- **learning_rate:** 0.01041118707020302
- **max_depth:** 4
- **n_estimators:** 380
- **reg_alpha:** 0.7406074869536907
- **reg_lambda:** 1.5468473873318191
- **subsample:** 0.743006532444217

## Optuna Trial Convergence

**run_differential** (MAE=3.4074): Best value first achieved at Trial 12 of 20 — mid-search convergence — moderate exploration before best found.

## Best Hyperparameter Configuration

```json
{
  "max_depth": 4,
  "learning_rate": 0.01041118707020302,
  "n_estimators": 380,
  "subsample": 0.743006532444217,
  "colsample_bytree": 0.6105835555603716,
  "reg_alpha": 0.7406074869536907,
  "reg_lambda": 1.5468473873318191
}
```

## Persisted Model

| Target | Model Name | Eval Year | Path |
|---|---|---|---|
| run_differential | xgb_tuned | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/run_differential/xgb_tuned_2026.pkl` |

Model confirmed persisted successfully via save_model().
