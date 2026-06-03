# Totals — Champion (v4) vs Challenger (totals_v1) — OOS Promotion Gate (Story 10.6)

## VERDICT: **PROMOTE_WITH_MONITORING**

- **Shared OOS set:** 560 games — 2026 fold (Bovada-line, settled), the same `game_pk` set for both.
- **Champion surface:** v4 inference-scored on the 2026 OOS fold (v4 trained 2021–2025 per registry `eval_year: 2026` / `training_rows: 10264`; 2026 is post-training → genuine OOS, not in-sample re-scoring). Deviation from live-history-only justified: v4 has ~0 live history (deployed 2026-06-02) and this is the largest clean OOS sample for the actual current champion.
- **NLL is pmf-vs-pmf:** champion Normal discretized over [y±0.5] to match the challenger's NegBin.

## Head-to-head
| Metric | Champion v4 | Challenger v1 | Δ (ch−champ) | gate |
|---|---:|---:|---:|:--|
| MAE | 3.6138 | 3.5482 | -0.0656 | lower better |
| NLL (pmf, discretized) | 2.9426 | 2.8928 | -0.0498 | lower better |
| **std(pred-MEANS)** ⟵ variance gate | 1.3553 | 1.6325 | +0.2772 | challenger ≥1.5 & > champ (game differentiation) |
| mean per-game σ (context) | 4.0703 | 3.7817 | -0.2886 | tail width, not the gate |
| calib_80 | 0.7750 | 0.7661 | -0.0089 | ≥0.80 (both miss → relative) |
| Brier vs actual | 0.3129 | 0.3091 | -0.0038 | lower better; market baseline 0.2281 |
| p_over agreement w/ market | 0.0696 | 0.0744 | +0.0048 | agreement, NOT skill |
| AVG(pred) | 8.7564 | 8.9343 | +0.1779 | AVG(actual)=8.950 |
| Pct_Over_Line % | 59.6429 | 63.7500 | +4.1071 | healthy 25–75% |

### CLV / ROI by edge bucket (realized, −110)
- **Champion:** strong_over: n=322, win=0.441, roi=-0.158 · near_zero: n=62, win=0.484, roi=-0.076 · strong_under: n=176, win=0.511, roi=-0.024
- **Challenger:** strong_over: n=293, win=0.447, roi=-0.146 · near_zero: n=56, win=0.589, roi=+0.125 · strong_under: n=211, win=0.526, roi=+0.004

## Rubric axes
| Axis | Verdict |
|---|---|
| MAE delta | PROMOTE |
| NLL delta | PROMOTE |
| std(pred-means) | PROMOTE |
| calib_80 | MONITOR |
| Directional bias | PROMOTE |
| CLV (edge>+0.03) | DO_NOT_PROMOTE |

- ΔMAE -0.0656, ΔNLL -0.0498.
- **Decision rule:** PROMOTE only if MAE does not regress AND NLL improves AND the variance gate passes AND no new directional bias; any single ambiguous axis → PROMOTE_WITH_MONITORING; a regression on MAE/NLL/variance → DO_NOT_PROMOTE.

## Notes
- **Variance gate (spread of predicted MEANS = game differentiation):** challenger 1.632 vs champion 1.355 (Δ +0.277). The challenger clears the ≥1.5 bar and edges the champion, so the axis passes — **but the Epic 10 premise is partly stale:** v4's std-of-means (1.355) is WELL above the legacy NGBoost ~0.77 shrinkage the epic was built to fix. v4 already largely fixed the discrimination problem, so the challenger's variance edge here is **modest, not the night-and-day fix the framing implied.** (Both have wide per-game σ — champion 4.070, challenger 3.782 — so neither is tail-shrunk.)
- **⚠️ Neither model has betting skill on 2026:** Bovada's de-vigged P(over) scores Brier **0.2281** vs actual — far better than challenger 0.3091 or champion 0.3129, and both are also worse than naive-0.50 (0.2500). calib_80 < 0.80 for both, high-conviction bins are over-confident, and strong-over CLV is unprofitable for both. The challenger **wins the model-vs-model comparison** (MAE, NLL, discrimination) but **cannot yet beat the market or a coin flip on 2026 over/under** — so the shadow window must demonstrate real live betting value before any production flip.
- 10.7 integration proceeds only on PROMOTE (or after a successful shadow window on PROMOTE_WITH_MONITORING). DO_NOT_PROMOTE leaves v4 as the production totals source.
