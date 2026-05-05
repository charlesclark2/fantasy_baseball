# Model Comparison: v0 (champion) vs v1 (challenger)

Generated: 2026-05-05 05:09 UTC
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

## Per-Target Verdicts (2024+)


### run_diff

| Metric | v0 | v1 | Delta |
|--------|---------|---------|-------|
| RunDiff_MAE | 3.539 | 3.434 | -0.105 |

**PROMOTE** — challenger improves run_diff_mae (3.539 → 3.434).

### home_win

| Metric | v0 | v1 | Delta |
|--------|---------|---------|-------|
| Brier | 0.2412 | 0.2409 | -0.0003 |
| Pct_Positive | 40.9% | 32.2% | -8.7 pp |

**PROMOTE WITH MONITORING** — Brier improves (0.2412 → 0.2409) but Pct_Positive dropped 8.7 pp (40.9% → 32.2%). Monitor live selectivity.

### total_runs

| Metric | v0 | v1 | Delta |
|--------|---------|---------|-------|
| Tot_MAE | 3.862 | 3.472 | -0.390 |
| Pct_Over_Edge | 20.5% | 4.2% | — |

**PROMOTE WITH MONITORING** — challenger improves Tot_MAE (3.862 → 3.472) but shows directional bias: Pct_Over_Edge=4.2% (model predicts under on 95.8% of games). Investigate bias before relying on totals betting signal.
