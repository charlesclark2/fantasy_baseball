# E2.3 — Convolution → predictive distributions: calibration record

_Fit 2026-06-24 · 11,662 games · marginals = oos_purged_cv · 10,000 draws/game · independent (ρ=0) · per-side dispersion · market-blind._

## What E2.3 does
- **Convolves the two E2.1 per-side NegBin marginals INDEPENDENTLY** (E2.2: residual ρ=−0.0035 ⇒ home/away runs essentially independent; no copula).
- **Calibrates a stable PER-SIDE dispersion `r_home`/`r_away` on HELD-OUT residuals** — the lever E2.2 identified for the ~24% totals variance deficiency (E2.1 fits `r` on optimistic train-fit means → under-dispersed). Per-side (not a single shared r) because the run-diff PIT is sensitive to a home/away dispersion asymmetry the sum is blind to.
- Derives **total** (sum), **run-diff** (difference; distributional H2H), **team totals** (marginals); emits a P05…P95 quantile grid + `p_over(line)` and stores **params + grid, not raw samples**.

## Leak-guard (verified 2026-06-24)
- bp_eb_xwoba sourced from E1.7-de-leaked eb_bullpen_team_posteriors (appearance_date < game_date, equal-weight trailing-30d pool); marginals leak-clean. The within-game leak E2.1b found was fixed at the dbt layer by E1.7 (not deferred); re-deriving the marginals here reads the de-leaked channel live.

## Per-side dispersion calibration (leakage-safe expanding window)

| dispersion source | r_home | r_away |
|---|---|---|
| E2.1 train-fit (biased high, under-dispersed) | 8.527 | 8.527 |
| held-out, seasons < 2022 (leakage-safe) | 3.9967 | 3.7013 |
| held-out, seasons < 2023 (leakage-safe) | 4.0059 | 3.4776 |
| held-out, seasons < 2024 (leakage-safe) | 4.0295 | 3.5535 |
| held-out, seasons < 2025 (leakage-safe) | 4.0777 | 3.5508 |
| **global served (per-side held-out)** | **4.0645** | **3.3977** |

The held-out `r` is stable across seasons (E2.2 CV 0.054) → a **single global per-side served `r`** is correct; we do NOT condition `r` on period (E2.1's apparent drift is an estimation artifact of fitting `r` on optimistic train means).

## Calibration AC (leakage-safe walk-forward, pooled over gated seasons)

| distribution | calib_80 | PIT mean | max decile dev | PIT flat |
|---|---|---|---|---|
| total | 0.838 | 0.4957 | 0.0068 | ✅ |
| run_diff | 0.839 | 0.5035 | 0.0303 | ❌ |
| home_total | 0.863 | 0.4995 | 0.0091 | ✅ |
| away_total | 0.847 | 0.4945 | 0.0138 | ✅ |

Oracle (per-side global r_home=4.0645/r_away=3.3977): total calib_80 0.841, PIT flat ✅.

## Gate
- Full-game total calib_80 ≥ 0.80: ✅ (0.838)
- Full-game total PIT histogram flat: ✅
- Run-diff marginal PIT-calibrated: ❌
- Team-total marginals PIT-calibrated: ✅
- **Overall: NOT MET ❌**

> The fix for the totals variance deficiency is the **dispersion calibration**, not a copula (E2.2). The served distribution is honest calibration — NOT an edge claim (the main-line total is efficient per E13.8; the derivative-edge question is E2.6).
