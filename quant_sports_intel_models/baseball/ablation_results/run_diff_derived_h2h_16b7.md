# 16B.7 — Run-Diff-Derived H2H Evaluation

_Epic 16B, Story 16B.7 (parallel, no training). Tests whether the NGBoost Normal `run_differential` posterior (μ, σ) → P(home_win) = Φ(μ/σ) can match or beat the direct `home_win` XGBoost champion (xgb_classifier_tuned_2026.pkl) and the 2026 Bovada market._

- **D4 sign convention (locked 2026-06-04):** run_differential = home_score − away_score; P(home_win) = 1 − Normal.cdf(0; μ, σ) = Φ(μ/σ); μ > 0 ⇒ home favored.
- **OOS set:** 660 games (2026 fold; trained 2021–25 → genuine OOS).
- **Market gate:** Bovada de-vigged P(home win); ≤0.235 = credible; n_market = 621.
- **Market Brier (2026):** 0.1820 (credible ✅).
- **Layer 1 prior:** Bernoulli base-rate 0.533 → log-loss 0.6937 (must beat).
- **L3 baselines:** prior-naive Brier 0.2502 · market Brier 0.1820.
- **Alpha note:** ⚠️ alpha=0.00: blended posterior = market exactly (compute_posterior(p, mkt, 0) = mkt). Brier(blended) = market_brier for all games — L3-vs-market gate uses **raw model Brier** instead.

## Three-Layer H2H Metrics

| Metric | run_diff_derived | home_win_champion |
|---|---:|---:|
| L1 log-loss | 0.6023 | 0.5957 |
| L2 ECE | 0.0250 | 0.0430 |
| L2 calib-in-large | -0.0090 | +0.0029 |
| L3 Brier(blended) | 0.1820 | 0.1820 |
| Brier(model raw) | 0.2089 | 0.2044 |
| mean P(home) | 0.5032 | 0.5150 |

## Gates

| Gate | run_diff_derived | home_win_champion |
|---|:---:|:---:|
| L1 log-loss < prior | ✅ | ✅ |
| L3 raw Brier < market* | ❌ | ❌ |
| L3 Brier(blended) < prior-naive | ✅ | ✅ |
| Market credible (≤0.235) | ✅ | ✅ |
| L4 roi_devig>0 & n≥50 | ✅ | ✅ |

_* alpha=0.00 → blended=market; raw Brier < market is the honest L3 test (blended=market makes Brier(blended)<market trivially False)._

**Head-to-head (run_diff_derived vs home_win_champion):**
- NLL: 0.6023 vs 0.5957 (home_win wins ❌)
- Brier(raw): 0.2089 vs 0.2044 (home_win wins ❌)
- ECE: 0.0250 vs 0.0430 (run_diff wins ✅)

## Layer 4 — run_diff_derived

_Gate metric: roi_devig (de-vigged fair-odds ROI; vig-free upper bound). Gate: roi_devig > 0 AND n_bets ≥ 50._

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 545 | 0.878 | 0.659 | +0.2575 | +0.1682 | ✅ |
| 1.00 | 0.08 | 498 | 0.802 | 0.671 | +0.2804 | +0.1983 | ✅ |
| 1.00 | 0.10 | 471 ⭐ | 0.758 | 0.671 | +0.2808 | +0.2094 | ✅ |
| 1.00 | 0.12 | 449 | 0.723 | 0.666 | +0.2713 | +0.2092 | ✅ |
| 1.00 | 0.15 | 411 | 0.662 | 0.652 | +0.2449 | +0.2068 | ✅ |
| 1.00 | 0.20 | 349 | 0.562 | 0.628 | +0.1980 | +0.1997 | ✅ |

- **Verdict: ✅ PASS** — optimal h2h_threshold=0.10: n_bets=471, win_rate=0.671, roi_devig=+0.2094.

- @default h2h_threshold=0.12 — direction_flip: n=213 roi_110=-0.1754 roi_devig=+0.1575 · magnitude: n=236 roi_110=+0.6745 roi_devig=+0.2558.
- No-bet (n=172): model Brier 0.2051 vs market 0.2063.

## Layer 4 — home_win_champion

_Gate metric: roi_devig (de-vigged fair-odds ROI; vig-free upper bound). Gate: roi_devig > 0 AND n_bets ≥ 50._

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 547 | 0.881 | 0.675 | +0.2879 | +0.1971 | ✅ |
| 1.00 | 0.08 | 492 | 0.792 | 0.667 | +0.2727 | +0.2008 | ✅ |
| 1.00 | 0.10 | 460 | 0.741 | 0.667 | +0.2741 | +0.2129 | ✅ |
| 1.00 | 0.12 | 437 | 0.704 | 0.654 | +0.2494 | +0.2052 | ✅ |
| 1.00 | 0.15 | 386 | 0.622 | 0.635 | +0.2117 | +0.2122 | ✅ |
| 1.00 | 0.20 | 322 ⭐ | 0.519 | 0.615 | +0.1739 | +0.2356 | ✅ |

- **Verdict: ✅ PASS** — optimal h2h_threshold=0.20: n_bets=322, win_rate=0.615, roi_devig=+0.2356.

- @default h2h_threshold=0.12 — direction_flip: n=206 roi_110=-0.1659 roi_devig=+0.1784 · magnitude: n=231 roi_110=+0.6198 roi_devig=+0.2290.
- No-bet (n=184): model Brier 0.1903 vs market 0.1898.

## Supplementary — Run-Diff Model Intrinsic Quality

_How well the NGBoost Normal model predicts `run_differential` itself (not derived P(home_win)). L1 uses discretized-PMF NLL; L2 uses calib_80 (central-80% interval coverage, gate [0.75, 0.85])._

- Prior: Normal(μ=0.042, σ=4.482) → NLL 2.9334
- Model NLL (PMF): **2.7612** (beats prior ✅)
- Model calib_80: **0.776** (gate [0.75, 0.85]: ✅)
- Mean predicted μ: -0.019  (n=660)

## Verdict

- **vs champion (xgb_classifier_tuned_2026):** run_diff_derived loses to home_win_champion on NLL+Brier (NLL 0.6023 vs 0.5957; Brier 0.2089 vs 0.2044).
- **vs 2026 Bovada market (Brier 0.1820):** run_diff_derived does NOT close the gap (rd=0.2089 hw=0.2044 mkt=0.1820).
- **16B.7 verdict: **NO CHANGE** — run_diff-derived P(home_win) is informative (beats Bernoulli prior) but does NOT beat the 2026 Bovada market on L3 Brier. Consistent with Epic 11 finding: no H2H edge against a sharp market.**

