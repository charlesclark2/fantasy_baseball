# Totals v1 — Calibration & Reliability (Story 10.4)

- **Window:** 2021–2025 regular season · env=`prod`
- **Scored games:** 12148 (106 consensus-fallback excluded from headline)
- **Calibration set (Bovada-line, settled):** 8250

## Calibration
- **ECE:** 0.0312 (gate ≤ 0.05) → **PASS**
- **Brier:** 0.2146 vs naive-0.50 0.2500 (beats naive) · vs Bovada de-vig 0.2476 (beats Bovada)
- **σ ↔ CI-width corr:** 0.878 (positive ⇒ wider CIs on higher-σ/low-coverage games — the 9.3/10.3 check)

### Reliability diagram (10 bins)
| bin          |    n |   mean_pred |   frac_over |     gap |
|:-------------|-----:|------------:|------------:|--------:|
| [0.00, 0.10) |  130 |      0.0555 |      0.2923 | -0.2368 |
| [0.10, 0.20) |  392 |      0.1596 |      0.1786 | -0.0189 |
| [0.20, 0.30) |  927 |      0.2543 |      0.2244 |  0.0299 |
| [0.30, 0.40) | 1459 |      0.3534 |      0.3071 |  0.0463 |
| [0.40, 0.50) | 1612 |      0.4512 |      0.4367 |  0.0145 |
| [0.50, 0.60) | 1524 |      0.5489 |      0.5623 | -0.0135 |
| [0.60, 0.70) | 1177 |      0.6445 |      0.6822 | -0.0378 |
| [0.70, 0.80) |  697 |      0.7419 |      0.7633 | -0.0214 |
| [0.80, 0.90) |  268 |      0.8406 |      0.8284 |  0.0122 |
| [0.90, 1.00] |   64 |      0.9409 |      0.6719 |  0.2690 |

## Edge → outcome (two lenses)
### ROI proxy (realized, −110, all Bovada-line games)
| bucket                      |    n |   win_rate |     roi |
|:----------------------------|-----:|-----------:|--------:|
| strong over (edge > +0.03)  | 3280 |     0.6735 |  0.2857 |
| near-zero (|edge| <= 0.03)  | 1046 |     0.4990 | -0.0473 |
| strong under (edge < -0.03) | 3924 |     0.6967 |  0.3301 |

### True CLV vs Pinnacle close (cross-book, partial coverage)
| bucket                      |    n |   n_clv |   coverage |   mean_clv_runs |   pct_clv_pos |
|:----------------------------|-----:|--------:|-----------:|----------------:|--------------:|
| strong over (edge > +0.03)  | 3280 |    2373 |     0.7235 |          0.4701 |        0.3586 |
| near-zero (|edge| <= 0.03)  | 1046 |     703 |     0.6721 |          0.0092 |        0.2504 |
| strong under (edge < -0.03) | 3924 |    2677 |     0.6822 |          0.5241 |        0.3198 |

### Three-case agreement read
- **Both +** → strong validation: model finds good numbers *and* they win above break-even; supports scaling.
- **CLV + / ROI ≈ 0** → edge is real, outcomes noisy; be patient (ROI should converge), don't abandon.
- **ROI + / CLV ≈ 0** → profitable now but not from line-beating; suspect variance/over-fit — *not* sustainable if the market is right.

_True-CLV coverage is partial (Pinnacle pairing < 100%); interpret each bucket against its `coverage` column._

## Acceptance criteria
- [x] ECE ≤ 0.05 (else Platt applied & re-checked) — 0.0312, no Platt needed
- [x] Brier beats naive 0.50; vs Bovada de-vig documented — beats both (0.2146 < 0.2476), but in-sample (see caveat)
- [~] Reliability shows no systematic bias — middle 8 bins clean; **tail over-confidence** in `[0,0.10)` (gap −0.24) and `[0.90,1.00]` (gap +0.27)
- [x] `edge > +0.03` bucket shows positive mean CLV / ROI — yes, but ROI is in-sample (see caveat)

## ⚠️ Verdict & caveats (read before trusting these numbers)

**These metrics are IN-SAMPLE.** The `totals_v1` production artifact was refit on all
2021–2026 data, and this run scored 2021–2025 → ~100% training overlap. Consequences:

1. **ROI +28–33% is overfit, not a deployable edge.** Real OOS edges are low-single-digit %;
   the math is correct but the magnitude reflects memorized games. Do not size off these.
2. **The Brier win over Bovada (0.2146 vs 0.2476) is razor-thin (0.003) and in-sample** — it may
   not survive a true holdout. Treat as "not grossly miscalibrated," not "beats the market."
3. **Tail over-confidence is real** (small-n but >4 SE): the model is too confident exactly where
   conviction is highest — matters for Kelly sizing and high-edge buckets. Carry into 10.5/10.6.
4. **True CLV is murky:** mean `clv_runs` positive but only 32–36% of bets strictly beat the close
   → likely a structural Bovada-vs-Pinnacle line offset, not line-beating skill. Do not lean on it.

**What IS trustworthy here:** ECE/middle-bin reliability (in-sample miscalibration would still show)
and **σ↔CI-width corr 0.878** — the combiner widens CIs on low-coverage games, so the 9.3/10.3
precision-pooling switch is NOT needed. The **Brier gap over Bovada de-vig (0.2146 vs 0.2476)** is
directionally encouraging even in-sample — outperforming the market's own implied probabilities on
calibration is the right sign. **If that gap survives the OOS evaluation in 10.6, that is the real story.**

**CLV coverage is NOT high-edge-biased.** Pinnacle pairs 72.4% of strong-over games (2373/3280),
67.2% near-zero (703/1046), 68.2% strong-under (2677/3924) — the high-edge buckets are *better*
covered than near-zero, so Pinnacle is not systematically skipping unusual-line games in a way that
would bias the CLV read in either direction. (Overall 51% Pinnacle coverage is across all 12,148
scored games; on the 8,250-game Bovada-line calibration set it is ~68–72%.)

**Decision (2026-06-02):** rigorous OOS calibration is **deferred to Story 10.6**, which must use
**walk-forward held-out predictions for BOTH models** (each game scored by a model trained only on
prior seasons) — its default "2024+ holdout" is NOT truly OOS for `totals_v1` either, since the
artifact trained through 2026. **The 10.4 numbers are a necessary but not sufficient promotion gate:**
ECE 0.0312 / Brier 0.2146 confirm the model is not grossly miscalibrated (the NegBin CDF works), but
are expected to be optimistic; 10.6's walk-forward holdout, scoring each season using only
prior-season training data, is the rigorous gate before production.
