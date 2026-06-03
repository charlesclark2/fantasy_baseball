# Totals — Bayesian Three-Layer Evaluation (Epic 10.6 re-run)

- **Shared OOS set:** 560 games (2026 Bovada-line, settled), identical `game_pk` set for both models.
- **Blend:** alpha=0.70 (totals_alpha, log-odds posterior toward Bovada) applied to BOTH models for the deployable number.
- **Prior predictive:** NegBin(mu=8.921, r=7.074) from the 2021–25 training marginal; prior-naive over-rate = 0.456.

## Comparison table
| Metric | v4 Champion | Layer 3 Challenger | Baseline |
|---|---:|---:|:--|
| **L1 NLL** (PMF) | 2.9426 | 2.8928 | prior-predictive **2.8893** (must beat) |
| **L2 coverage@50%** | 0.425 | 0.493 | nominal 0.50 |
| **L2 coverage@80%** (calib_80) | 0.775 | 0.777 | nominal 0.80 (gate 0.75–0.85) |
| **L2 coverage@90%** | 0.880 | 0.879 | nominal 0.90 |
| **L2 mean 80% PI width** | 10.433 | 9.586 | sharpness (lower=tighter) |
| **L3 Brier (blended α=0.70)** | 0.2801 | 0.2786 | prior-naive **0.2479** · market **0.2281** · coin 0.2500 |
| **L3 mean P(over) blended** | 0.520 | 0.506 | actual 0.454 · market 0.457 |

_Caveat: the challenger's NegBin is DISCRETE, so its central intervals over-cover at low nominal levels (≈0.57 at 50%); the effect shrinks by 80–90%. The champion's Normal is continuous (near-nominal throughout). Compare coverage with this in mind — the calib_80 gate (80%) is the least affected._

## L3 edge-bucket ROI (blended posterior, −110)
- **Champion:** strong_over: n=308 win=0.435 roi=-0.169 · near_zero: n=89 win=0.517 roi=-0.013 · strong_under: n=163 win=0.503 roi=-0.040
- **Challenger:** strong_over: n=280 win=0.443 roi=-0.155 · near_zero: n=79 win=0.557 roi=+0.063 · strong_under: n=201 win=0.532 roi=+0.016

## Decision rules (reported separately — a model can win the head-to-head yet fail the operational gate)

### A. Must-pass gates (each model independently)
| Gate | v4 Champion | Layer 3 Challenger |
|---|:--:|:--:|
| NLL < prior | ❌ | ❌ |
| calib_80 in [0.75,0.85] | ✅ | ✅ |
| Brier(blended) < prior-naive | ❌ | ❌ |

### B. Head-to-head (challenger vs champion)
| Gate | Result |
|---|:--:|
| challenger NLL < champion | ✅ |
| challenger calib_80 closer to 0.80 | ✅ |
| challenger Brier(blended) < champion | ✅ |

### C. Operational gates (production deployment)
| Gate | v4 Champion | Layer 3 Challenger |
|---|:--:|:--:|
| Brier(blended) < market | ❌ | ❌ |
| strong-over ROI > 0 | ❌ | ❌ |
| strong-under ROI > 0 | ❌ | ✅ |

## Read
- **Layer 1:** **NEITHER model beats the prior predictive NLL** — the covariates add no information over the training marginal; do not deploy either.
- **Operational vs head-to-head are separate:** the head-to-head names the better *model*; the operational gates (Brier(blended) < market AND edge-bucket ROI > 0) decide whether ANY totals model should bet. Passing B without C still means no production deployment.
