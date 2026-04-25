# NGBoost run_differential Hyperparameter Tuning (Card 4.12e)

## NGBoost run_differential Grid Search Results

Grid search over n_estimators ∈ {200, 500, 1000} and dist ∈ {Normal, LogNormal}.
Evaluation metric: mean absolute error (MAE) across temporal CV splits (min_train_seasons=3).

| n_estimators | Dist | CV MAE | Viable |
|-------------|------|--------|--------|
| 200 | Normal | 3.4370 | Yes |
| 200 | LogNormal | N/A | No |
| 500 | Normal | 3.4195 | Yes |
| 500 | LogNormal | N/A | No |
| 1000 | Normal | 3.4225 | Yes |
| 1000 | LogNormal | N/A | No |

**Best viable configuration:** n_estimators=500, dist=Normal, CV MAE=3.4195

## LogNormal Distribution Note

LogNormal is **not viable** for run_differential. The LogNormal distribution requires strictly positive support (values > 0), but run_differential contains negative values — the home team can lose by any margin, so the target ranges from large negative numbers to large positive numbers. Attempting to fit NGBoost with LogNormal on negative targets causes numerical failures or NaN predictions. All three LogNormal grid entries are recorded as `viable=false` with the note: _"LogNormal distribution requires strictly positive targets; run_differential contains negative values (home team can lose by any margin)."_

## Best NGBoost Configuration

- **best_n_estimators:** 500
- **best_dist:** Normal
- **CV MAE:** 3.4195

The Normal distribution is the only viable choice for run_differential, as it supports the full real line and can model both positive (home win) and negative (away win) margins.

## Persisted Model

The best NGBoost model was retrained on the last CV fold's training split and persisted via `save_model()` from `betting_ml.utils.model_io`.

| Target | Model Name | Eval Year | Path |
|--------|------------|-----------|------|
| run_differential | ngboost_tuned | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/run_differential/ngboost_tuned_2026.pkl` |

Model saved successfully. (persisted)
