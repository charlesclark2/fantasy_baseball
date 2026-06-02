# Proxy CLV Analysis — Epic 12 Story 12.3

**Run date:** 2026-06-02

**Known limitations of this analysis:**
- (a) CLV signal: Pinnacle open→close where ≥2 snapshots (~48 games); consensus multi-book average otherwise. Not a pure sharp-money signal.
- (b) Backfilled predictions (2021–2025), not real-time intraday runs.
- (c) Public betting, CI-width, and bookmaker-disagreement features unavailable for historical backfill; excluded from regression and classified as coverage-limited.

---
## 1. Dataset Overview

- Total rows: 1,334  |  Distinct games: 1,334
- Rows with `proxy_clv_positive` defined: 1,334
- Base rate `proxy_clv_positive`: 33.9%
- CLV source — Pinnacle: 2 games | Consensus: 1332 games

**By year:**

| Year | Games |
|------|-------|
| 2021 | 318 |
| 2022 | 285 |
| 2023 | 205 |
| 2024 | 255 |
| 2025 | 271 |

## 2. Logistic Regression (proxy_clv_positive)

- n = 1,321 complete rows
- Features used (≥50% coverage): h2h_edge (100%), totals_edge (99%), h2h_market_implied_prob (100%)
- CV AUC (5-fold): **0.548**
- In-sample AUC: 0.564
- Brier score: 0.2209

**Feature coefficients (standardised):**

| Feature | Coefficient | Classification |
|---------|-------------|----------------|
| totals_edge | -0.168 | informative |
| h2h_edge | +0.102 | informative |
| h2h_market_implied_prob | -0.072 | weak |

**Calibration (5 bins):**

| Predicted | Actual |
|-----------|--------|
| 0.196 | 1.000 |
| 0.326 | 0.327 |
| 0.429 | 0.410 |

**Coverage-limited features (excluded from regression):**

| Feature | Reason |
|---------|--------|
| `game_conviction_score` | 0% non-null — below 50% threshold |
| `gate_signals_met` | 0% non-null — below 50% threshold |
| `win_prob_ci_width` | Live 2026+ only |
| `totals_p_over_ci_width` | Live 2026+ only |
| `home_ml_money_pct` | Action Network 2024+ only |
| `over_money_pct` | Action Network 2024+ only |
| `bovada_vs_pinnacle_h2h` | Pinnacle processed mart not yet built |
| `hours_to_first_pitch_at_prediction` | Backfill lacks precise insertion timestamps |

## 3. Power Analysis

Bootstrap-based estimate of 80% CI half-width on `h2h_edge` coefficient
as a function of live-data sample size. Target: CI half-width ≤ 0.15.

| n games | 80% CI half-width | Meets target? |
|---------|-------------------|---------------|
| 50 | ±0.490 | ❌ |
| 100 | ±0.382 | ❌ |
| 150 | ±0.318 | ❌ |
| 200 | ±0.229 | ❌ |
| 300 | ±0.207 | ❌ |
| 500 | ±0.145 | ✅ |
| 750 | ±0.091 | ✅ |
| 1000 | ±0.056 | ✅ |

**Conclusion:** ~500 live CLV-labeled games needed for 80% CI to narrow to ±0.15 on the `h2h_edge` coefficient.

## 4. Coverage Bias (Pinnacle vs Consensus source)

Pinnacle-sourced: 2 games | Consensus-sourced: 1332 games

| Feature | Pinnacle mean | Consensus mean | Δ |
|---------|--------------|----------------|---|
| h2h_edge | -0.0300 | -0.0084 | -0.0216 |
| game_conviction_score | nan | nan | +nan |
| proxy_clv_h2h | -0.0175 | 0.0017 | -0.0192 |

- `proxy_clv_positive` rate — Pinnacle: 100.0% | Consensus: 33.8%

_If Pinnacle mean h2h_edge or proxy_clv_positive differs substantially from_
_consensus, Pinnacle coverage is non-random and results should be treated with_
_extra skepticism for those ~48 games._

## 5. Feature Classification Summary

Classifications inform prior means for Story 12.4 Bayesian model.
Uninformative → tighten prior toward 0. Informative → use proxy coefficient.

| Feature | Classification | Note |
|---------|---------------|------|
| h2h_edge | **informative** | coef=+0.102 |
| totals_edge | **informative** | coef=-0.168 |
| game_conviction_score | **coverage_limited** | — |
| gate_signals_met | **coverage_limited** | — |
| h2h_market_implied_prob | **weak** | coef=-0.072 |
| win_prob_ci_width | **coverage_limited** | Not in historical backfill |
| totals_p_over_ci_width | **coverage_limited** | Not in historical backfill |
| home_ml_money_pct | **coverage_limited** | Not in historical backfill |
| over_money_pct | **coverage_limited** | Not in historical backfill |
| bovada_vs_pinnacle_h2h | **coverage_limited** | Not in historical backfill |
| hours_to_first_pitch_at_prediction | **coverage_limited** | Not in historical backfill |