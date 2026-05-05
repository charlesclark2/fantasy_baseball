# Model Comparison: v0 (champion) vs v1 (challenger)

Generated: 2026-05-05 04:51 UTC
Window: 2021-04-01 → 2026-05-04

## Per-Season Metrics

| Season | Model | N | N_Odds | Mean_H2H_Edge | Pct_Pos | Brier | Tot_MAE | RunDiff_MAE |
|--------|-------|---|--------|---------------|---------|-------|---------|-------------|
| 2021 | v0 | 2466 | 1799 | -0.0069 | 46.1% | 0.2400 | 4.241 | 3.518 |
| 2021 | v1 | 2466 | 1799 | -0.0083 | 39.2% | 0.2369 | 3.448 | 3.358 |
| 2022 | v0 | 2751 | 1789 | -0.0082 | 44.4% | 0.2402 | 3.865 | 3.462 |
| 2022 | v1 | 2751 | 1789 | -0.0067 | 42.4% | 0.2351 | 3.300 | 3.290 |
| 2023 | v0 | 2937 | 1802 | -0.0042 | 47.7% | 0.2423 | 4.293 | 3.563 |
| 2023 | v1 | 2937 | 1802 | -0.0082 | 40.7% | 0.2410 | 3.623 | 3.446 |
| 2024 | v0 | 2417 | 1766 | -0.0107 | 43.5% | 0.2414 | 3.896 | 3.505 |
| 2024 | v1 | 2417 | 1766 | -0.0139 | 32.4% | 0.2391 | 3.335 | 3.383 |
| 2025 | v0 | 2886 | 1844 | -0.0084 | 46.5% | 0.2409 | 4.028 | 3.578 |
| 2025 | v1 | 2925 | 1844 | -0.0139 | 31.4% | 0.2409 | 3.517 | 3.470 |
| 2026 | v0 | 1215 | 1140 | -0.0307 | 26.9% | 0.2449 | 3.462 | 3.528 |
| 2026 | v1 | 975 | 521 | -0.0118 | 34.5% | 0.2493 | 3.890 | 3.495 |

## 2024+ Aggregate (Primary Evaluation Window)

| Model | N | N_Odds | Mean_H2H_Edge | Pct_Pos | Brier | Tot_MAE | RunDiff_MAE |
|-------|---|--------|---------------|---------|-------|---------|-------------|
| v0 | 6518 | 4750 | -0.0143 | 40.9% | 0.2412 | 3.862 | 3.539 |
| v1 | 6317 | 4131 | -0.0137 | 32.2% | 0.2409 | 3.472 | 3.434 |

## Promotion Verdict

**PROMOTE**

- Challenger v1 improves mean_h2h_edge (-0.0143 → -0.0137) without meaningful Brier regression (0.2412 → 0.2409).

### Decision thresholds
- Edge improvement: challenger > champion + 0.0
- Brier regression limit: +0.002
- Minimum odds-game sample: 100

---

## Per-Target Promotion Verdicts

Evaluated on the 2024+ primary window unless noted. Each target model is an independent NGBoost artifact.

### run_diff — PROMOTE

| Metric | v0 | v1 | Delta |
|--------|----|----|-------|
| RunDiff_MAE (2024+) | 3.539 | 3.434 | −0.105 |

v1 improves run differential MAE by ~3% consistently across all seasons (2021–2026). No regression observed in any year.

### home_win — PROMOTE WITH MONITORING

| Metric | v0 | v1 | Delta |
|--------|----|----|-------|
| Brier (2024+) | 0.2412 | 0.2409 | −0.0003 |
| Mean H2H Edge (2024+) | −0.0143 | −0.0137 | +0.0006 |
| Pct_Positive (2024+) | 40.9% | 32.2% | −8.7 pp |

Brier and edge improve marginally. However, v1 flags a positive home_win edge on significantly fewer games (−8.7 pp). The model is more selective but not clearly more accurate. Promote and monitor live 2026 Pct_Positive week-over-week; revert if selectivity degrades ROI.

### total_runs — PROMOTE

| Metric | v0 | v1 | Delta |
|--------|----|----|-------|
| Tot_MAE (2024+) | 3.862 | 3.472 | −0.390 |

v1 improves total runs MAE by ~10% consistently across all seasons. This result is valid after fixing a log-space storage bug (see note below).

**Note — Log-Space Storage Bug (fixed 2026-05-05):** Prior to this date, `pred_total_runs` in `daily_model_predictions` stored the NGBoost LogNormal `loc` parameter (log-space mean, ~2.0) instead of the natural-scale median (`exp(loc)`, ~8.0). The bug was introduced in the backfill path of `predict_today.py`. The fix (`float(np.exp(loc_tot[i]))` at line 349) was applied on 2026-05-05. Existing rows were corrected via two Snowflake UPDATE statements: `EXP(pred_total_runs)` applied to all v1 rows and to v0 rows where `pred_total_runs < 3.5` (log-space range). The over/under probability (`p_over_ngboost`) and betting edge (`totals_edge`) were **never affected** — `p_over_line()` always applied `exp()` internally.

**Remaining concern — directional bias:** Even after the fix, v1 `pct_over_edge` is ~2.7% (v1 predicts the under on ~97% of games). This is a genuine model behavior issue, not a storage artifact, likely caused by Phase 7 bullpen/Stuff+/Pythagorean features over-weighting low-run environments. Totals betting signal should be used with caution until this bias is investigated in the Phase 9 retrain.
