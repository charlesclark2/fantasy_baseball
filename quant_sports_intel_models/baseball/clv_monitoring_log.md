# CLV Monitoring Log

Append-only log of model ablation and CLV results.

---

## 6D.5 EB Ablation — distributional NegBin (20260601T053223)

| Metric | Champion (EB, 24 feat) | No-EB (21 feat) | Delta |
|--------|------------------------|-----------------|-------|
| CV NLL | 2.05044 | 2.1409 | +0.0904 |
| calib_80 | 0.8484200000000002 | 0.8173 | -0.0312 |
| High-fatigue NLL | 1.877 | 1.7788 | -0.0982 |

**Decision:** RETAIN  
**Rationale:** EB reduces CV NLL by 0.0904 (>= 0.005 threshold)  
**File:** `betting_ml/models/sub_models/bullpen_v2/ablation_eb_bullpen_20260601T053223.json`  

---

## CLV Weekly Monitoring — 2026-06-11

Dataset: `baseball_data.betting_features.feature_pregame_meta_model_features`  
Rows: 286 | Distinct games: 150 | Date range: 2026-05-05 → 2026-06-08


### 1. Gate Threshold Tracker

| Market | Labeled games |
|--------|--------------|
| h2h | 150 |
| totals | 136 |
| **total (distinct games)** | **150** |

Recent pace: **33.0 games/week** (last 28 days)

| Gate | Threshold | Games needed | Est. weeks | Est. date |
|------|-----------|-------------|-----------|-----------|
| Epic 12.3 | ≥50 games | 0 | 0.0 | MET ✅ |
| Epic 12.4 | ≥100 games | 0 | 0.0 | MET ✅ |
| Epic 12.5 | ≥500 games | 350 | 10.6 | 2026-08-24 |
| Epic 12.6 | ≥1000 games | 850 | 25.8 | 2026-12-08 |

### 2. CLV Distribution by Market Type

| Market | n | Mean CLV | Std CLV | Pct CLV+ |
|--------|---|----------|---------|----------|
| h2h | 150 | +0.0029 | 0.0183 | 58.7% |
| totals | 136 | +0.0007 | 0.0308 | 42.6% |

### 3. Edge Bucket Analysis

Edge column: `|h2h_edge_home|` for h2h rows; `|totals_edge|` for totals rows.

| Market | Edge bucket | n | Mean CLV | Pct CLV+ |
|--------|------------|---|----------|----------|
| h2h | 0–0.02 | 37 | -0.0035 | 43.2% |
| h2h | 0.02–0.04 | 25 | +0.0014 | 52.0% |
| h2h | 0.04–0.06 | 26 | +0.0071 | 61.5% |
| h2h | 0.06+ | 61 | +0.0056 | 68.9% |
| totals | 0–0.02 | 16 | +0.0091 | 43.8% |
| totals | 0.02–0.04 | 10 | +0.0024 | 50.0% |
| totals | 0.04–0.06 | 10 | -0.0033 | 40.0% |
| totals | 0.06+ | 100 | -0.0005 | 42.0% |

### 4. Conviction Tier Analysis

| Gate signals met | n | Mean CLV | Pct CLV+ |
|-----------------|---|----------|----------|
| (no data) | — | — | — |

### 5. Bookmaker Disagreement Analysis

No rows with `bovada_vs_pinnacle_h2h` populated yet (Pinnacle mart not yet built).

This section will populate when the Pinnacle processed mart ships.

### 6. Public Betting Contrarian Signal

| Bucket | Threshold | n | Mean CLV | Pct CLV+ |
|--------|-----------|---|----------|----------|
| Public heavy (home) | > 65% | 149 | +0.0030 | 59.1% |
| Neutral | 35–65% | 0 | — | — |
| Contrarian (home fade) | < 35% | 0 | — | — |

### 7. Timing Analysis

| Hours to first pitch | n | Mean CLV | Pct CLV+ |
|---------------------|---|----------|----------|
| < 2h | 97 | +0.0040 | 51.5% |
| 2–6h | 163 | +0.0004 | 47.9% |
| 6–12h | 18 | +0.0001 | 55.6% |
| 12h+ | 8 | +0.0087 | 100.0% |

### 8. Pipeline Health (last 7 days)

| Metric | Value |
|--------|-------|
| Days audited | 7 |
| SLA compliance (≥30 min before first pitch) | **6/7 (86%)** |
| Days pipeline_status = complete | 7/7 |
| Days signal_completeness < 0.80 | 0 |
| Days feature_coverage < 0.70 | 0 |
| Mean feature_coverage_score | 0.79 |
| Days n_games_scored < scheduled | 0 |
| Mean prediction lead (min before first pitch) | 332 min |

| Date | Status | Scored/Sched | Signal | Coverage | Lead (min) | SLA |
|------|--------|-------------|--------|----------|-----------|-----|
| 2026-06-10 | complete | 15/15 | 1.00 | 0.81 | 289 | ✅ |
| 2026-06-09 | complete | 15/15 | 1.00 | 0.77 | 619 | ✅ |
| 2026-06-08 | complete | 8/8 | 1.00 | — | 619 | ✅ |
| 2026-06-07 | complete | 15/15 | 0.99 | — | 318 | ✅ |
| 2026-06-06 | complete | 15/14 | 1.00 | — | 293 | ✅ |
| 2026-06-05 | complete | 15/15 | 0.99 | — | 363 | ✅ |
| 2026-06-04 | complete | 9/9 | 1.00 | — | -176 | ❌ |

---
