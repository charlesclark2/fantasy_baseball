# Model Artifact Selection Log (Phase 5, Card 5.1)

Selection criterion: lowest mean CV MAE across temporal folds. NGBoost is required
for regression targets — downstream `predict_today.py` and `run_probability_layer.py`
call `.pred_dist()` to produce probability distributions over game outcomes. XGBoost
cannot produce predictive distributions and is therefore not viable for production,
regardless of point-MAE ranking.

---

## target: total_runs

| Model | Type | Source | Mean CV MAE | Viable |
|---|---|---|---|---|
| ridge_2026 | Ridge | cv_results.json baselines | 3.6047 | No (no pred_dist) |
| xgboost_2026 | XGBoost | cv_results.json baselines | 3.6288 | No (no pred_dist) |
| ngboost_normal_2026 | NGBRegressor | cv_results.json baselines | 3.6464 | Yes |
| ngboost_lognormal_2026 | NGBRegressor | cv_results.json baselines | 3.6561 | Yes |
| ngboost_tuned_2026 | NGBRegressor | tuning_results_ngboost_total_runs.json | 3.5718 | Yes |
| xgb_tuned_2026 | XGBoost | tuning_results_xgb_total_runs.json | 3.5655 | No (no pred_dist) |

**Selected winner:** `ngboost_tuned_2026.pkl` (mean CV MAE = 3.5718)

Note: `xgb_tuned_2026` has the lowest MAE (3.5655) but is not viable because
`XGBRegressor.pred_dist()` does not exist. Among NGBoost candidates, `ngboost_tuned`
improves on the normal baseline (3.6464) and the lognormal baseline (3.6561) using
the tuned configuration (n_estimators=200, dist=Normal).

**_prod artifact:** `betting_ml/models/total_runs/ngboost_tuned_prod.pkl`
(additive copy of `ngboost_tuned_2026.pkl`; original retained for rollback)

---

## target: run_differential

| Model | Type | Source | Mean CV MAE | Viable |
|---|---|---|---|---|
| ridge_2026 | Ridge | run_differential_results.md baselines | 3.4559 | No (no pred_dist) |
| xgboost_2026 | XGBoost | run_differential_results.md baselines | 3.4887 | No (no pred_dist) |
| ngboost_normal_2026 | NGBRegressor | run_differential_results.md baselines | 3.4459 | Yes |
| ngboost_tuned_2026 | NGBRegressor | tuning_results_ngboost_run_diff.json | 3.4195 | Yes |
| xgb_tuned_2026 | XGBoost | tuning_results_xgb_run_diff.json | 3.4073 | No (no pred_dist) |

Note: NGBoost LogNormal is excluded — run_differential can be negative, violating
LogNormal's strictly-positive support (see run_differential_results.md).

**Selected winner:** `ngboost_tuned_2026.pkl` (mean CV MAE = 3.4195)

Among viable (NGBoost Normal) candidates, `ngboost_tuned` improves over the baseline
`ngboost_normal` (3.4459) using the tuned configuration (n_estimators=500, dist=Normal).

**_prod artifact:** `betting_ml/models/run_differential/ngboost_tuned_prod.pkl`
(additive copy of `ngboost_tuned_2026.pkl`; original retained for rollback)
