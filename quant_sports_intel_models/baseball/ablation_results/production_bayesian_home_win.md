# home_win — Production Bayesian Three-Layer Evaluation (sequential retrain)

- **OOS set:** 660 games (2026 fold; trained 2021–25 → genuine OOS).
- **Champion = faithful 369-feature no-sequential reproduction** (the documented production-champion spec). The deployed S3 `*_eb_enriched` binaries drifted from every record (needed ≥374 features vs. documented 369) and are unrecoverable; this nonseq retrain reproduces the documented contract AND is the clean ablation baseline.
- **Challenger present:** yes (sequential-enriched).

- **Layer 1 prior-predictive:** Bernoulli base-rate 0.533 → log-loss **0.6937** (must beat).
- **L3 baselines:** prior-naive Brier **0.2502** · market Brier **0.1820** (credible; gate ≤0.235) · alpha 0.00 · n_market 621.
- _Note: calib_80 (interval coverage) is undefined for a Bernoulli model; Layer 2 uses ECE and calibration-in-the-large instead._

| Metric | champion | challenger |
|---|---:|---:|
| L1 log-loss | 0.5906 | 0.5958 |
| L2 ECE | 0.0635 | 0.0430 |
| calib-in-large | +0.0029 | +0.0029 |
| L3 Brier(blended) | 0.1820 | 0.1820 |
| Brier(model raw) | 0.2015 | 0.2044 |

## Layer 4 — Selective Strategy

_Edge on the bet-triggered subset only (not all games). Layer 4 does NOT replace L1–L3: a model failing L1/L3 but passing L4 is **selective-edge-only** — informative for manual selection, not automated deployment. Passing all four => deployable at the optimal threshold. ⚠️ rows have n_bets < 50 (statistically unreliable)._

_**Gate metric:** totals → **roi_110** (totals settle at -110 both sides). H2H → **roi_devig** (each bet priced at de-vigged fair odds) — flat -110 misprices moneyline favorites/underdogs. roi_devig is vig-free (optimistic upper bound)._

### champion

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 546 | 0.879 | 0.670 | +0.2797 | +0.2002 | ✅ |
| 1.00 | 0.08 | 506 | 0.815 | 0.670 | +0.2790 | +0.2123 | ✅ |
| 1.00 | 0.10 | 478 | 0.770 | 0.663 | +0.2661 | +0.2176 | ✅ |
| 1.00 | 0.12 | 448 | 0.721 | 0.656 | +0.2528 | +0.2208 | ✅ |
| 1.00 | 0.15 | 400 | 0.644 | 0.640 | +0.2218 | +0.2315 | ✅ |
| 1.00 | 0.20 | 321 ⭐ | 0.517 | 0.604 | +0.1538 | +0.2459 | ✅ |

- **Verdict: ✅ PASS** (gate=roi_devig) — optimal h2h 0.20: n_bets 321, win_rate 0.604, roi_devig +0.2459.

- @default 0.12 — direction_flip: n=207 roi -0.1607 · magnitude: n=241 roi +0.6081.
- No-bet (n=173): model Brier 0.1834 vs market 0.1804.

### challenger

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 547 | 0.881 | 0.675 | +0.2879 | +0.1971 | ✅ |
| 1.00 | 0.08 | 492 | 0.792 | 0.667 | +0.2727 | +0.2008 | ✅ |
| 1.00 | 0.10 | 460 | 0.741 | 0.667 | +0.2741 | +0.2129 | ✅ |
| 1.00 | 0.12 | 437 | 0.704 | 0.654 | +0.2494 | +0.2052 | ✅ |
| 1.00 | 0.15 | 386 | 0.622 | 0.635 | +0.2117 | +0.2122 | ✅ |
| 1.00 | 0.20 | 322 ⭐ | 0.519 | 0.615 | +0.1739 | +0.2356 | ✅ |

- **Verdict: ✅ PASS** (gate=roi_devig) — optimal h2h 0.20: n_bets 322, win_rate 0.615, roi_devig +0.2356.

- @default 0.12 — direction_flip: n=206 roi -0.1659 · magnitude: n=231 roi +0.6198.
- No-bet (n=184): model Brier 0.1904 vs market 0.1898.


## Gates
### champion
| Gate | Result |
|---|:--:|
| L1 NLL < prior (base-rate) | ✅ |
| L2 ECE <= 0.05 | ❌ |
| L3 Brier(blended) < prior-naive | ✅ |
| L3 Brier(blended) < market | ❌ |
| L4 selective roi_devig>0 & n>=50 | ✅ |

### challenger
| Gate | Result |
|---|:--:|
| L1 NLL < prior (base-rate) | ✅ |
| L2 ECE <= 0.05 | ✅ |
| L3 Brier(blended) < prior-naive | ✅ |
| L3 Brier(blended) < market | ❌ |
| L4 selective roi_devig>0 & n>=50 | ✅ |

### market_quality
| Gate | Result |
|---|:--:|
| Bovada market Brier <= 0.235 | ✅ |

### head_to_head
| Gate | Result |
|---|:--:|
| challenger NLL < champion | ❌ |
| challenger Brier(blended) < champion | ❌ |

