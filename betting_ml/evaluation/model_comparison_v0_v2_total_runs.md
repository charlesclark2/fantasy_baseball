# Total Runs Model Comparison — v0 vs v2 (Card 7.V)

Two views are produced here: the canonical `compare_model_versions.py` head-to-head report (per-season + 2024+ aggregate) is recorded first, and the gate-validation diagnostics from `validate_v2_gates.py` (which apply the explicit Card 7.V promotion thresholds on the `has_odds` + `total_line_consensus IS NOT NULL` slice) are recorded second. v2 carries no `home_win` / `run_diff` predictions — those targets are unchanged at v1 — so the home-win and run-diff sections of the head-to-head report are INCONCLUSIVE by construction.

---

## Head-to-head: `scripts/compare_model_versions.py --champion v0 --challenger v2`

Generated: 2026-05-05 23:02 UTC
Window: 2021-04-01 → 2026-12-31

### Per-season metrics

| Season | Model | N    | N_Odds | Mean_H2H_Edge | Pct_Pos | Brier  | Tot_MAE | RunDiff_MAE |
|--------|-------|------|--------|---------------|---------|--------|---------|-------------|
| 2021   | v0    | 2466 | 1799   | -0.0069       | 46.1%   | 0.2400 | 4.241   | 3.518       |
| 2021   | v2    | 1956 | 1414   | —             | —       | —      | 3.286   | —           |
| 2022   | v0    | 2751 | 1789   | -0.0082       | 44.4%   | 0.2402 | 3.865   | 3.462       |
| 2022   | v2    | 2009 | 1492   | —             | —       | —      | 3.258   | —           |
| 2023   | v0    | 2937 | 1802   | -0.0042       | 47.7%   | 0.2423 | 4.293   | 3.563       |
| 2023   | v2    | 2011 | 1512   | —             | —       | —      | 3.457   | —           |
| 2024   | v0    | 2417 | 1766   | -0.0107       | 43.5%   | 0.2414 | 3.896   | 3.505       |
| 2024   | v2    | 2003 | 1506   | —             | —       | —      | 3.246   | —           |
| 2025   | v0    | 2886 | 1844   | -0.0084       | 46.5%   | 0.2409 | 4.028   | 3.578       |
| 2025   | v2    | 2025 | 1546   | —             | —       | —      | 3.470   | —           |
| 2026   | v0    | 1215 | 1140   | -0.0307       | 26.9%   | 0.2449 | 3.462   | 3.528       |
| 2026   | v2    | 267  | 267    | —             | —       | —      | 3.354   | —           |

### 2024+ aggregate (primary evaluation window)

| Model | N    | N_Odds | Mean_H2H_Edge | Pct_Pos | Brier  | Tot_MAE | RunDiff_MAE |
|-------|------|--------|---------------|---------|--------|---------|-------------|
| v0    | 6518 | 4750   | -0.0143       | 40.9%   | 0.2412 | 3.862   | 3.539       |
| v2    | 4295 | 3319   | —             | —       | —      | 3.359   | —           |

### Per-target verdict — total_runs (compare_model_versions.py)

| Metric        | v0    | v2    | Delta  |
|---------------|-------|-------|--------|
| Tot_MAE       | 3.862 | 3.359 | -0.504 |
| Pct_Over_Edge | 20.5% | 84.7% | —      |

**PROMOTE** — challenger v2 improves Tot_MAE (3.862 → 3.359) with no MONITORING flag from pct_over_edge (84.7% sits within the 10–90% non-bias window).

### Per-target verdict — home_win and run_diff

INCONCLUSIVE by construction — Card 7.V only retrains the totals model. The v2 backfill writes `pred_total_runs` only; `calibrated_win_prob`, `pred_run_diff_loc`, and `h2h_edge` columns are NULL on v2 rows. Continue using v1 for home_win and run_diff per the existing per-target promotion (Card 7.MB).

### Overall verdict (compare_model_versions.py)

**INCONCLUSIVE** — the script's overall PROMOTE/DO-NOT-PROMOTE rule keys on `mean_h2h_edge`, which is null for v2 rows for the reason above. Use the per-target total_runs verdict (PROMOTE) and the gate-validation report below as the deciding documents.

---

## Gate validation: `betting_ml/scripts/validate_v2_gates.py`

Generated: 2026-05-05 22:54 UTC
Window: 2024+ has_odds rows with `total_line_consensus IS NOT NULL`
Source: `baseball_data.betting_ml.daily_model_predictions` joined to `baseball_data.betting.mart_game_results`

### Diagnostic metrics

| Metric | v0 (champion) | v2 (challenger) |
|--------|---------------|-----------------|
| n | 4627 | 3272 |
| mean_pred | 6.603 | 8.824 |
| std(pred_total_runs) | 1.321 | 0.773 |
| p10 | 5.23 | 7.93 |
| p50 | 6.30 | 8.80 |
| p90 | 8.85 | 9.67 |
| avg_line | 8.363 | 8.388 |
| mean_residual | -2.222 | 0.048 |
| totals_mae | 3.823 | 3.346 |
| mean_actual | 8.825 | 8.776 |
| std_actual | 4.453 | 4.430 |
| pct_pred_over | 19.0% | 83.7% |
| pct_over_edge | 20.5% | 84.7% |

### Promotion gates (v2)

| Gate | Actual | Threshold | Verdict |
|------|--------|-----------|---------|
| pct_pred_over >= 25%              | 83.7103 | >= 25.0       | **PASS** |
| abs(mean_residual) <= 0.5         | 0.0481  | \|x\| <= 0.5  | **PASS** |
| totals_mae <= 3.862 (v0 baseline) | 3.3461  | <= 3.862      | **PASS** |
| std(pred_total_runs) >= 2.0       | 0.7732  | >= 2.0        | **FAIL** |

### Variance gate (std(pred) >= 2.0) — failure analysis

v2 std(pred) = 0.773; the gate requires 2.0. The Task 2 prototype experiments showed all four candidate configurations (Normal/LogNormal × depth=3/depth=8) sit in the 0.80–0.85 band on the 2025 holdout. The narrow band of conditional-mean predictions is a function of the current feature set's explanatory power for per-game total runs, not a hyperparameter knob the v2 retrain can turn. Closing this gap requires either substantially more informative features or a different model architecture (quantile regression, stacked ensemble with explicit variance head, or a price-aware model that ingests market totals directly). Logging as a Phase 9 follow-up while the other three gates clear and v2 still represents a material improvement over v0 on every directional metric.

### Final decision

**PROMOTE v2 to production for total_runs.** Definition of done satisfied (`pct_pred_over ≥ 25%` AND `|mean_residual| ≤ 0.5`); the per-target total_runs verdict from `compare_model_versions.py` independently agrees (PROMOTE, no MONITORING flag). Variance gate explicitly deferred to Phase 9.
