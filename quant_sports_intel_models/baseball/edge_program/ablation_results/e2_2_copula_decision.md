# E2.2 — Dependence structure (Gaussian copula): decision record

_Fit 2026-06-22 · 11,659 games · marginals = oos_purged_cv · market-blind._

## ρ estimate
- **Residual Gaussian-copula ρ = -0.0035** (normal-scores of the distributional transform under each side's conditional NegBin — the discrete-marginal-correct estimator; this is the ρ E2.3 uses).
- Kendall-τ implied ρ = -0.0046 (rank cross-check, V-noise-free).
- Naive raw-pairs Pearson = +0.0002 — **contrast only.** Using it would double-count the shared park/weather/ump coupling the E2.1 conditional means already carry.

## Conditioning decision (ρ and dispersion r)
- **ρ → global.** No bucket scheme is both significant (|z|≥2) and materially different (max|Δρ|≥0.04); a single global ρ is the simplest fit.
- **r → single global held-out-calibrated r ≈ 3.71 (held-out r is STABLE across folds, spread 0.53 / CV 0.054; the E2.1 train-fit r-drift 9.3-wide is an ESTIMATION ARTIFACT of fitting r on optimistic train means, NOT temporal non-stationarity → do NOT condition r on period)**

## AC validation

| stat | empirical | copula ρ | independent ρ=0 |
|---|---|---|---|
| corr(home, away) | +0.0002 | -0.0014 | +0.0021 |
| mean(total) | 8.888 | 8.934 | 8.925 |
| var(total) | 19.994 | 15.146 | 15.176 |
| tail-L1 P(total≥t) | — | 0.02582 | 0.02534 |

Analytic var(total) decomposition: within-game 14.253 + between-game-means 0.894; the 2·cov copula coupling contributes -0.050 → ρ total 15.147 vs ρ=0 total 15.197.

## Dispersion diagnostic — where the variance gap actually is

The E2.1 marginal fits its NegBin dispersion `r` on **train-fit means** (optimistic residuals → `r` biased high → under-dispersed). Re-fitting `r` on **held-out residuals** tests whether a better-calibrated dispersion — not a copula — closes the total-variance gap:

| dispersion source | mean r | var(total) | rel err vs empirical |
|---|---|---|---|
| r on TRAIN-fit means (E2.1) | 8.541 | 15.146 | 0.2425 |
| r on HELD-OUT residuals | 3.714 | 20.761 | 0.0382 ✅ closes the gap |

Per-fold `r_train` → `r_oos`: 2021 15.0→3.9, 2022 8.7→3.6, 2023 7.0→3.9, 2024 6.2→3.8, 2025 5.7→3.4.

**Held-out `r` is STABLE across folds** (spread 0.53, CV 0.054) while train-fit `r` drifts 9.3-wide → **the E2.1 'r non-stationary 33→8' reading is an ESTIMATION ARTIFACT** (train residuals tighten as the train set grows), not real dispersion drift. E2.3 should use a single stable held-out-calibrated `r ≈ 3.71`, not a per-period r.

## Finding
- **Dependence:** home/away runs essentially independent (ρ≈0) → Gaussian copula unnecessary; independent convolution adequate for the dependence.
- **Variance gap is marginal dispersion:** YES.
- **→ E2.3 recommendation:** Calibrate the per-side NegBin dispersion on HELD-OUT residuals (E2.1 fits r on optimistic train-fit means → under-dispersed → ~24% total-variance shortfall that the copula cannot fix). Skip the copula coupling (ρ≈0).

## Gate
- Reproduces empirical correlation: ✅
- Reproduces realized total-runs variance: ❌
- Independent (ρ=0) insufficient on the tails: ❌ (when ρ≈0 this AC *cannot* pass — there is no dependence to capture; the copula is confirmed unnecessary, not wrong)
- **Overall: NOT MET ❌ — honest finding (see numbers above)**

> ρ≈0 ⇒ independent convolution is adequate for the *dependence*; the totals variance deficiency > (Story 29.1) lives in the **marginal dispersion** (E2.1/E2.3), and an OOS-calibrated `r` closes it. > Do not force a coupling the data does not support.
