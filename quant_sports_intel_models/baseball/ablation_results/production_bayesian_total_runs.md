# total_runs — Production Bayesian Three-Layer Evaluation (sequential retrain)

- **OOS set:** 660 games (2026 fold; trained 2021–25 → genuine OOS).
- **Champion = faithful 369-feature no-sequential reproduction** (the documented production-champion spec). The deployed S3 `*_eb_enriched` binaries drifted from every record (needed ≥374 features vs. documented 369) and are unrecoverable; this nonseq retrain reproduces the documented contract AND is the clean ablation baseline.
- **Challenger present:** yes (sequential-enriched).

- **Layer 1 prior-predictive:** NegBin(mu=8.916, r=7.132) → NLL **2.8608** (must beat).

- **L3 baselines:** prior-naive Brier **0.2470** (over-rate 0.456) · market Brier **0.2297** · actual over-rate 0.444 · alpha 0.70 · n_market 610.

| Metric | champion | challenger |
|---|---:|---:|
| L1 NLL (PMF) | 2.8566 | 2.8588 |
| L2 calib_80 | 0.811 | 0.808 |
| mean pred | 9.037 | 9.076 |
| L3 Brier(blended) | 0.2697 | 0.2702 |
| L3 mean P(over) | 0.539 | 0.541 |
| pct pred>line | 66.6% | 67.2% |

## Layer 4 — Selective Strategy

_Edge on the bet-triggered subset only (not all games). Layer 4 does NOT replace L1–L3: a model failing L1/L3 but passing L4 is **selective-edge-only** — informative for manual selection, not automated deployment. Passing all four => deployable at the optimal threshold. ⚠️ rows have n_bets < 50 (statistically unreliable)._

_**Gate metric:** totals → **roi_110** (totals settle at -110 both sides). H2H → **roi_devig** (each bet priced at de-vigged fair odds) — flat -110 misprices moneyline favorites/underdogs. roi_devig is vig-free (optimistic upper bound)._

### champion

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 478 | 0.724 | 0.521 | -0.0055 | — | ✅ |
| 0.75 | 0.12 | 425 | 0.644 | 0.513 | -0.0207 | — | ✅ |
| 1.00 | 0.12 | 373 | 0.565 | 0.507 | -0.0327 | — | ✅ |
| 1.25 | 0.12 | 330 | 0.500 | 0.503 | -0.0397 | — | ✅ |
| 1.50 | 0.12 | 300 | 0.455 | 0.500 | -0.0455 | — | ✅ |
| 2.00 | 0.12 | 234 | 0.355 | 0.491 | -0.0618 | — | ✅ |

- **Verdict: ❌ FAIL** (gate=roi_110) — no threshold with roi_110>0 AND n_bets≥50.

- @default 1.0 run — over: n=265 roi -0.0779 · under: n=108 roi +0.0783.
- No-bet (n=275): uncertainty-zone |μ−line|<0.5 frac 0.415 (rest = view-below-threshold) · model Brier 0.2481 vs market 0.2423.

### challenger

_Gate metric: **roi_110** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 0.50 | 0.12 | 476 | 0.721 | 0.521 | -0.0053 | — | ✅ |
| 0.75 | 0.12 | 423 | 0.641 | 0.506 | -0.0342 | — | ✅ |
| 1.00 | 0.12 | 372 | 0.564 | 0.511 | -0.0249 | — | ✅ |
| 1.25 | 0.12 | 336 | 0.509 | 0.506 | -0.0341 | — | ✅ |
| 1.50 | 0.12 | 300 | 0.455 | 0.503 | -0.0391 | — | ✅ |
| 2.00 | 0.12 | 237 | 0.359 | 0.494 | -0.0575 | — | ✅ |

- **Verdict: ❌ FAIL** (gate=roi_110) — no threshold with roi_110>0 AND n_bets≥50.

- @default 1.0 run — over: n=269 roi -0.0561 · under: n=103 roi +0.0565.
- No-bet (n=274): uncertainty-zone |μ−line|<0.5 frac 0.423 (rest = view-below-threshold) · model Brier 0.2498 vs market 0.2420.


## Gates
### champion
| Gate | Result |
|---|:--:|
| L1 NLL < prior | ✅ |
| L2 calib_80 in [0.75,0.85] | ✅ |
| L3 Brier(blended) < prior-naive | ❌ |
| L3 Brier(blended) < market | ❌ |
| L4 selective roi_110>0 & n>=50 | ❌ |

### challenger
| Gate | Result |
|---|:--:|
| L1 NLL < prior | ✅ |
| L2 calib_80 in [0.75,0.85] | ✅ |
| L3 Brier(blended) < prior-naive | ❌ |
| L3 Brier(blended) < market | ❌ |
| L4 selective roi_110>0 & n>=50 | ❌ |

### head_to_head
| Gate | Result |
|---|:--:|
| challenger NLL < champion | ❌ |
| challenger Brier(blended) < champion | ❌ |

