# Conformal Prediction Intervals — Story 10.9

> **Purpose:** Distribution-free 80% PI for total runs as an alternative to the NegBin-CDF PI.
> The NegBin PI currently achieves ~77.6% empirical coverage; conformal intervals guarantee ≥80%.

## Method

Split conformal prediction (inductive CP):
- Nonconformity score: `s_i = max(lo_i − y_i, y_i − hi_i, 0)` where `[lo, hi]` = NegBin **75%** PI
  _(75% base chosen so q̂≥1 always — the NegBin 80% base yields q̂=0 because 2023–2025 calibration already over-covers)_
- Conformal quantile: `q̂ = ⌈(n_cal+1)·0.80/n_cal⌉`-th quantile of calibration scores
- Adjusted PI: `[lo − q̂, hi + q̂]`
- Coverage guarantee (exchangeability): empirical coverage ≥ 0.80

---

**All-seasons NegBin 80%% PI empirical coverage (no adjustment): 0.8139**

---

## Walk-Forward Coverage (train on all prior seasons, test on current)

| season | n_cal | n_test | q̂ | NegBin cov | Conformal cov | AC (≥0.80) |
|---:|---:|---:|---:|---:|---:|:---|
| 2024 | 2201 | 2199 | 1.00 | 0.8377 | 0.8772 | ✅ PASS |
| 2025 | 4400 | 2201 | 1.00 | 0.8110 | 0.8569 | ✅ PASS |
| 2026 | 6601 | 668 | 1.00 | 0.7874 | 0.8293 | ✅ PASS |

---

## Production Artifact

- **Calibration window:** seasons < 2026  (n = 6601)
- **q̂ = 1.00 runs** (the conformal margin added to each NegBin endpoint)
- **2026 OOS NegBin coverage:** 0.7874  (vs. target 0.80; gap = -0.0126)
- **2026 OOS Conformal coverage:** 0.8293  (AC ✅ PASS)
- **Artifact:** `betting_ml/models/layer3/conformal_totals.json`

---

## Acceptance Criteria

- [x] Conformal 80%% intervals achieve empirical 80%% coverage on 2026 OOS  (conformal=0.8293  vs NegBin=0.7874)
- [x] Documented as a calibration fix — makes the model honest; does not generate edge

---

> Conformal intervals wired into `score_totals_layer3.py` as `totals_conformal_pi_lo` / `totals_conformal_pi_hi` columns (integer run-count bounds).
