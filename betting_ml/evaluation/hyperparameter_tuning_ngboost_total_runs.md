# NGBoost total_runs Hyperparameter Tuning (Card 4.12d)

## NGBoost total_runs Grid Search Results

Grid search over n_estimators ∈ {200, 500} and dist ∈ {Normal, LogNormal}.
Evaluation metric: mean absolute error (MAE) across temporal CV splits (min_train_seasons=3).

| n_estimators | Dist | CV MAE | Viable |
|-------------|------|--------|--------|
| 200 | Normal | 3.5212 | Yes |
| 200 | LogNormal | 3.5224 | Yes |
| 500 | Normal | 3.5316 | Yes |
| 500 | LogNormal | 3.5190 | Yes |

**Best viable configuration:** n_estimators=500, dist=LogNormal, CV MAE=3.5190

## Best NGBoost Configuration

- **best_n_estimators:** 500
- **best_dist:** LogNormal
- **CV MAE:** 3.5190

## Persisted Model

The best NGBoost model was retrained on the last CV fold's training split and persisted via `save_model()` from `betting_ml.utils.model_io`.

| Target | Model Name | Eval Year | Path |
|--------|------------|-----------|------|
| total_runs | ngboost_tuned | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/total_runs/ngboost_tuned_2026.pkl` |

Model saved successfully. ✓ (persisted)

## Notes on Distribution Choice

LogNormal outperformed Normal (best MAE: 3.5190 vs 3.5212). This is expected since total_runs is a non-negative count — LogNormal's support over (0, ∞) is a natural fit for run totals and avoids predicting negative values.
