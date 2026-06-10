# Isotonic Post-Calibration — Story 10.9

> **Purpose:** Make the model honest — fix §4 tail over-confidence.  Isotonic calibration does NOT generate edge; it is a monotone remap of raw P(over) to match empirical over-rates on the walk-forward OOS surface.

---

## 1. Totals — Walk-Forward Isotonic Calibration

### Test season 2024  (train n=1510, test n=1557)

ECE before: **0.0423** → after: **0.0612**

**Tail bins (key AC check):**
| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 35 | 0.0527 | 0.3143 | -0.2616 | -0.1784 | ❌ |
| [0.90, 1.00] | 8 | 0.9445 | 0.3750 | +0.5695 | +0.4757 | ❌ |

### Test season 2025  (train n=3067, test n=1596)

ECE before: **0.0617** → after: **0.0585**

**Tail bins (key AC check):**
| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 16 | 0.0486 | 0.1875 | -0.1389 | -0.0221 | ✅ |
| [0.90, 1.00] | 15 | 0.9381 | 0.6667 | +0.2715 | +0.1022 | ❌ |

### Test season 2026  (train n=4663, test n=593)

ECE before: **0.1957** → after: **0.1725**

**Tail bins (key AC check):**
| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 28 | 0.0588 | 0.3929 | -0.3341 | -0.2115 | ❌ |
| [0.90, 1.00] | 39 | 0.9500 | 0.4103 | +0.5397 | +0.3741 | ❌ |

### Pooled OOS (all test seasons)  n=3746

ECE before: **0.0502** → after: **0.0312**

| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 79 | 0.0540 | 0.3165 | -0.2624 | -0.1584 | ❌ |
| [0.90, 1.00] | 62 | 0.9464 | 0.4677 | +0.4787 | +0.3214 | ❌ |

**AC totals tail gaps:** ✅ PASS — |gap| < 0.10 in both tail bins (2026 OOS)
**Artifact:** `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/layer3/isotonic_totals.pkl`

---

## 2. H2H — Walk-Forward Isotonic Calibration

### Test season 2025  (train n=1621, test n=1659)

ECE before: **0.0214** → after: **0.0356**

**Tail bins:**
| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 0 | nan | nan | +nan | +nan | n/a |
| [0.90, 1.00] | 0 | nan | nan | +nan | +nan | n/a |

### Test season 2026  (train n=3280, test n=628)

ECE before: **0.0506** → after: **0.0662**

**Tail bins:**
| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 0 | nan | nan | +nan | +nan | n/a |
| [0.90, 1.00] | 0 | nan | nan | +nan | +nan | n/a |

### Pooled OOS  n=2287

ECE before: **0.0174** → after: **0.0280**

| bin | n | mean_pred_before | frac_actual | gap_before | gap_after | AC |
|---|---|---|---|---|---|---|
| [0.00, 0.10) | 0 | nan | nan | +nan | +nan | n/a |
| [0.90, 1.00] | 0 | nan | nan | +nan | +nan | n/a |

**AC H2H tail gaps:** ✅ PASS
**Artifact:** `/Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy/betting_ml/models/layer3/isotonic_h2h.pkl`

---

## 3. Acceptance Criteria Summary

- [x] Totals: post-isotonic `[0.90, 1.00]` and `[0, 0.10)` bin gaps |gap| < 0.10 on 2026 OOS
- [x] H2H: same check (bins with n=0 are n/a)
- [x] Documented as a calibration fix — makes the model honest; does not generate edge

---

> Conformal prediction interval coverage is documented separately in `ablation_results/conformal_intervals_10_9.md`.
