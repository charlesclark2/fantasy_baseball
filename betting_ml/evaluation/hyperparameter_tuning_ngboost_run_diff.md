# NGBoost run_differential Hyperparameter Tuning (Card 4.12e)

## NGBoost run_differential Grid Search Results

Grid search over n_estimators ∈ {200, 500, 1000}, dist = Normal only.
LogNormal excluded: run_differential can be negative, causing log(Y) divide-by-zero.
Evaluation metric: mean absolute error (MAE) across temporal CV splits (min_train_seasons=3).

| n_estimators | Dist | CV MAE |
|-------------|------|--------|
| 200 | Normal | 3.1126 |
| 500 | Normal | 3.0660 |
| 1000 | Normal | 3.0623 |

**Best configuration:** n_estimators=1000, dist=Normal, CV MAE=3.0623

## Best NGBoost Configuration

- **best_n_estimators:** 1000
- **best_dist:** Normal
- **CV MAE:** 3.0623

The Normal distribution is the only viable choice for run_differential, as it supports the full real line and can model both positive (home win) and negative (away win) margins.

## Persisted Model

The best NGBoost model was retrained on the last CV fold's training split and persisted via `save_model()` from `betting_ml.utils.model_io`.

| Target | Model Name | Eval Year | Path |
|--------|------------|-----------|------|
| run_differential | ngboost_tuned_seasonnorm | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/run_differential/ngboost_tuned_seasonnorm_2026.pkl` |

Model saved successfully. (persisted)
