# Time-Decay Training Weighting — Impact Report

## Method

Exponential decay: `weight_i = exp(-lambda * days_since_game_i)`, `lambda = ln(2)/162`.
Half-life = 162 games (≈ one MLB regular season, ~182 days).
Weights normalized to sum to n (preserves effective sample size for regularization scaling).
Unweighted baselines sourced from `model_registry.yaml`.

## CV Metric Comparison

| Target           | Metric | Unweighted | Weighted | Delta   | Improved? |
|------------------|--------|------------|----------|---------|-----------|
| home_win         | Brier  | 0.2422     | 0.2508   | +0.0086 | No      |
| total_runs       | MAE    | 3.5107     | 3.5267   | +0.0160 | No      |
| run_differential | MAE    | 3.4724     | 3.4799   | +0.0075 | No      |

## Artifacts

- **home_win**: `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/home_win/elasticnet_decay_weighted.pkl` — saved (not promoted — weighted metric did not improve)
- **total_runs**: `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/total_runs/ngboost_decay_weighted_v3_unweighted.pkl` — saved (not promoted — weighted metric did not improve)
- **run_differential**: `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/run_differential/ngboost_decay_weighted_v3_unweighted.pkl` — saved (not promoted — weighted metric did not improve)

## Conclusion

Time-decay weighting did not improve CV metrics on any target in this run. Weighted artifacts saved to `*_decay_weighted.pkl` paths but not promoted. The feature set may already capture temporal structure adequately, or the half-life parameter may need tuning.

All weighted artifacts remain available for manual champion-challenger comparison.
