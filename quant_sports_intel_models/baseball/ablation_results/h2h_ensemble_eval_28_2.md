# 28.2 — run_diff × Classifier Ensemble + Disagreement Gate

_Epic 28, Story 28.2. Eval-only (no retrain). Tests the ensemble of two genuinely-independent H2H estimators and `|p_classifier − p_run_diff|` as a conviction filter._

- **OOS year:** 2026
- **n_ensemble:** 593 games (classifier ∩ run_diff ∩ market coverage)
- **Base rate (train ≤2025):** 0.5332  → prior NLL 0.6909
- **Market Brier (2026 Bovada):** 0.1790 (credible ✅)
- **Mix weights swept:** w ∈ {0=pure_run_diff, 0.25, 0.50, 0.75, 1.0=pure_classifier}

---

## Three-Layer Summary per Mix Weight

| w (classifier weight) | L1 NLL | beats prior? | L2 ECE | calib_large | L3 model Brier | vs market | best_w? |
|---:|---:|:---:|---:|---:|---:|:---:|:---:|
| 0 (pure run_diff) | 0.6040 | ✅ | 0.0297 | -0.0120 | 0.2090 | ❌ | ❌ |
| w=0.25 ⭐ | 0.6046 | ✅ | 0.0584 | -0.0045 | 0.2089 | ❌ | ✅ |
| w=0.50 | 0.6095 | ✅ | 0.0561 | +0.0029 | 0.2110 | ❌ | ❌ |
| w=0.75 | 0.6191 | ✅ | 0.0383 | +0.0104 | 0.2154 | ❌ | ❌ |
| 1 (pure classifier) | 0.6343 | ✅ | 0.0490 | +0.0179 | 0.2219 | ❌ | ❌ |

_Best w = **0.25** (lowest model Brier on market-covered games)._

---

## Layer 4 Threshold Sweep — Best Ensemble (w=0.25)

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 516 | 0.870 | 0.655 | +0.2505 | +0.1540 | ✅ |
| 1.00 | 0.08 | 475 | 0.801 | 0.659 | +0.2580 | +0.1762 | ✅ |
| 1.00 | 0.10 | 446 ⭐ | 0.752 | 0.655 | +0.2499 | +0.1778 | ✅ |
| 1.00 | 0.12 | 423 | 0.713 | 0.645 | +0.2321 | +0.1709 | ✅ |
| 1.00 | 0.15 | 387 | 0.653 | 0.628 | +0.1987 | +0.1592 | ✅ |
| 1.00 | 0.20 | 313 | 0.528 | 0.591 | +0.1284 | +0.1448 | ✅ |

- **Layer 4: ✅ PASS** (gate=roi_devig) — h2h_thr=0.10: n_bets=446, win_rate=0.655, roi_devig=+0.1778.

**@default h2h_threshold=0.12:**
- direction_flip: n=200 roi_110=-0.2555 roi_devig=+0.0869
- magnitude:      n=223 roi_110=+0.6694 roi_devig=+0.2463
- no-bet (n=170): model Brier 0.1992 vs market 0.2027

---

## Layer 4 Sweep — All Mix Weights

### w=0.00

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 520 | 0.877 | 0.658 | +0.2556 | +0.1601 | ✅ |
| 1.00 | 0.08 | 472 | 0.796 | 0.667 | +0.2741 | +0.1861 | ✅ |
| 1.00 | 0.10 | 446 ⭐ | 0.752 | 0.668 | +0.2756 | +0.1983 | ✅ |
| 1.00 | 0.12 | 427 | 0.720 | 0.660 | +0.2608 | +0.1928 | ✅ |
| 1.00 | 0.15 | 392 | 0.661 | 0.643 | +0.2273 | +0.1835 | ✅ |
| 1.00 | 0.20 | 333 | 0.562 | 0.619 | +0.1810 | +0.1771 | ✅ |
- **✅ PASS** roi_devig=+0.1983 (n_bets=446)

### w=0.25

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 516 | 0.870 | 0.655 | +0.2505 | +0.1540 | ✅ |
| 1.00 | 0.08 | 475 | 0.801 | 0.659 | +0.2580 | +0.1762 | ✅ |
| 1.00 | 0.10 | 446 ⭐ | 0.752 | 0.655 | +0.2499 | +0.1778 | ✅ |
| 1.00 | 0.12 | 423 | 0.713 | 0.645 | +0.2321 | +0.1709 | ✅ |
| 1.00 | 0.15 | 387 | 0.653 | 0.628 | +0.1987 | +0.1592 | ✅ |
| 1.00 | 0.20 | 313 | 0.528 | 0.591 | +0.1284 | +0.1448 | ✅ |
- **✅ PASS** roi_devig=+0.1778 (n_bets=446)

### w=0.50

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 522 | 0.880 | 0.659 | +0.2581 | +0.1795 | ✅ |
| 1.00 | 0.08 | 482 | 0.813 | 0.654 | +0.2476 | +0.1820 | ✅ |
| 1.00 | 0.10 | 452 | 0.762 | 0.646 | +0.2333 | +0.1841 | ✅ |
| 1.00 | 0.12 | 417 | 0.703 | 0.643 | +0.2269 | +0.1951 | ✅ |
| 1.00 | 0.15 | 377 ⭐ | 0.636 | 0.631 | +0.2052 | +0.1987 | ✅ |
| 1.00 | 0.20 | 306 | 0.516 | 0.588 | +0.1230 | +0.1943 | ✅ |
- **✅ PASS** roi_devig=+0.1987 (n_bets=377)

### w=0.75

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 521 | 0.879 | 0.656 | +0.2532 | +0.1824 | ✅ |
| 1.00 | 0.08 | 480 | 0.809 | 0.646 | +0.2330 | +0.1794 | ✅ |
| 1.00 | 0.10 | 450 | 0.759 | 0.649 | +0.2388 | +0.1980 | ✅ |
| 1.00 | 0.12 | 424 | 0.715 | 0.639 | +0.2202 | +0.1993 | ✅ |
| 1.00 | 0.15 | 374 | 0.631 | 0.631 | +0.2047 | +0.2164 | ✅ |
| 1.00 | 0.20 | 305 ⭐ | 0.514 | 0.597 | +0.1392 | +0.2250 | ✅ |
- **✅ PASS** roi_devig=+0.2250 (n_bets=305)

### w=1.00

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 526 | 0.887 | 0.635 | +0.2122 | +0.1653 | ✅ |
| 1.00 | 0.08 | 486 | 0.820 | 0.619 | +0.1824 | +0.1604 | ✅ |
| 1.00 | 0.10 | 455 | 0.767 | 0.613 | +0.1706 | +0.1688 | ✅ |
| 1.00 | 0.12 | 435 | 0.734 | 0.607 | +0.1586 | +0.1748 | ✅ |
| 1.00 | 0.15 | 392 | 0.661 | 0.594 | +0.1347 | +0.1912 | ✅ |
| 1.00 | 0.20 | 320 ⭐ | 0.540 | 0.562 | +0.0739 | +0.1959 | ✅ |
- **✅ PASS** roi_devig=+0.1959 (n_bets=320)

---

## Disagreement Gate (Conviction Filter)

_Filter to games where `|p_classifier − p_run_diff| ≤ d` (both models agree within d)._
_Best ensemble w=0.25 used throughout. Market Brier on full set = 0.1790._

| disagree_cap | n_kept | pct_kept | n_bets (L4 sweep) | roi_devig | model Brier | market Brier | beats market? |
|---:|---:|---:|---:|---:|---:|---:|:---:|
| ≤0.02 | 85 | 14.3% | 57 | +0.6812 | 0.1793 | 0.1895 | ✅ |
| ≤0.05 | 193 | 32.5% | 93 | +0.3845 | 0.2026 | 0.1764 | ❌ |
| ≤0.08 | 295 | 49.7% | 148 | +0.2808 | 0.1986 | 0.1728 | ❌ |
| ≤0.10 | 343 | 57.8% | 226 | +0.2622 | 0.2005 | 0.1691 | ❌ |
| ≤0.15 | 444 | 74.9% | 339 | +0.2198 | 0.2023 | 0.1758 | ❌ |
| ≤0.20 | 526 | 88.7% | 397 | +0.1860 | 0.2058 | 0.1763 | ❌ |

**Conviction filter verdict:** ✅ **ADOPT as conviction filter** — at disagree_cap=0.02 (14.3% of games), model Brier 0.1793 < market 0.1895. n_bets=57, roi_devig=+0.6812.

---

## Overall Verdict

- **Best ensemble (w=0.25) Brier:** 0.2089 vs market 0.1790 (does NOT beat market ❌)
- **Pure classifier (w=1.0) Brier:** 0.2219
- **Pure run_diff  (w=0.0) Brier:** 0.2090
- **Ensemble improvement over pure classifier:** +0.0131 (positive = ensemble better)

**The disagreement gate is the primary deliverable (Story 28.2 AC).**
Conviction filter: ✅ **ADOPT as conviction filter** — at disagree_cap=0.02 (14.3% of games), model Brier 0.1793 < market 0.1895. n_bets=57, roi_devig=+0.6812.

