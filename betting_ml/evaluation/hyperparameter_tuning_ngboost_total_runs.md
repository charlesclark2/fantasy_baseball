# NGBoost total_runs Hyperparameter Tuning (Card 4.12d)

## NGBoost total_runs Grid Search Results

Grid search over n_estimators ∈ {200, 500} and dist ∈ {Normal, LogNormal}.
Evaluation metric: mean absolute error (MAE) across temporal CV splits (min_train_seasons=3).

| n_estimators | Dist | CV MAE | Viable |
|-------------|------|--------|--------|
| 200 | Normal | 3.4353 | Yes |
| 200 | LogNormal | 3.4801 | Yes |
| 500 | Normal | 3.4008 | Yes |
| 500 | LogNormal | 3.4469 | Yes |

**Best viable configuration:** n_estimators=500, dist=Normal, CV MAE=3.4008

## Best NGBoost Configuration

- **best_n_estimators:** 500
- **best_dist:** Normal
- **CV MAE:** 3.4008

## Persisted Model

The best NGBoost model was retrained on the last CV fold's training split and persisted via `save_model()` from `betting_ml.utils.model_io`.

| Target | Model Name | Eval Year | Path |
|--------|------------|-----------|------|
| total_runs | ngboost_tuned | 2026 | `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/total_runs/ngboost_tuned_2026.pkl` |

Model saved successfully. ✓ (persisted)

## Notes on Distribution Choice

Normal slightly outperformed LogNormal (best MAE: 3.4008 vs 3.4469). Despite total_runs being non-negative (a natural fit for LogNormal), the Normal distribution performed comparably, suggesting the target distribution is well-approximated by a Gaussian in this feature space.
