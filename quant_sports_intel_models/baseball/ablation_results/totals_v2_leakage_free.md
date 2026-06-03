# Totals (Epic 9 Stacking Combiner) — Leakage-Free Re-Evaluation (Phase 2c)

_The Epic 9 pseudo-BMA stacking combiner (bullpen/offense/run_env → LTV (mu, sigma) → NB2 P(over)) evaluated on the leakage-free walk-forward matrix (`build_oos_matrix`). Per-signal mu→total_runs Poisson + NB2 sigma are fit walk-forward per fold (prior seasons only); weights from `stacking_weights.json`._

- Combiner weights (total_runs): bullpen=0.337, offense=0.332, run_env=0.331.
- Market: de-vigged Bovada P(over) on games with a Bovada line + both prices; non-push outcomes only. Gate: market Brier ≤ 0.240 (looser than h2h's 0.235 — totals are balanced-by-design so self-Brier ≈0.25 even when sharp).

## Per-season head-to-head (model vs market, identical games)

| season | n | model Brier | market Brier | Δ (mkt−mdl) | over-rate | mkt quality | beats mkt |
|---|---|---|---|---|---|---|---|
| 2024 | 1549 | 0.2578 | 0.2439 | -0.0139 | 0.464 | ⚠️ degraded | ❌ |
| 2025 | 1591 | 0.2508 | 0.2480 | -0.0028 | 0.469 | ⚠️ degraded | ❌ |
| 2026 | 593 | 0.3029 | 0.2279 | -0.0750 | 0.449 | credible | ❌ |
| **pooled** | 3733 | **0.2620** | **0.2431** | -0.0189 | — | — | ❌ |

> **Season inclusion (user decision 2026-06-03):** the 2024-25 historical totals lines are credible (no quality cliff vs 2026, well-calibrated de-vigged P(over)), so all three seasons are reported. 2026 (Parlay API) is the single cleanest reference. Any season the gate flags ⚠️ degraded is excluded from the operational verdict.

## Verdict

- Credible-baseline seasons: [2026]; model beats credible market in: **none**.
- Model beats market in (all seasons reported): **none**.
- **Bottom line: NO EDGE in any season — the cleaner version of the Epic 10 finding; the totals Layer 3 architecture does not beat a credible market.**

## Diagnostics — why 2026 loses by 0.075 (two compounding effects)

The 2026 model Brier **0.3029 is worse than a 0.5-flat prediction (0.25)** — the combiner is *confidently wrong*, not merely unskilled. Two diagnosable causes:

1. **Run-environment regime miss (bias).** Combiner μ̄ = 9.06 runs, but the 0.449 over-rate at ~8.5-9 lines implies actual mean ≈8.7. The per-signal mu→total_runs mapping, fit on 2022-2025, expects more offense than 2026 delivers → systematic over-prediction. This is a genuine signal-quality/regime story, not variance.
2. **Overconfident P(over) (calibration artifact).** The LTV `combined_sigma` (mean of single-feature GLM sigmas + near-zero across-signal disagreement — all three signals say ~9) understates the true spread, pushing P(over) toward the extremes and inflating Brier. There is NO calibration step on the combiner's P(over) (unlike the h2h LightGBM+Platt).

**Robustness:** a walk-forward calibration pass on P(over) could narrow the 2024/2025 near-ties (Δ −0.014 / −0.003), but those are *degraded-market* seasons (Brier >0.240) excluded from the operational verdict; and it cannot close the 2026 gap (−0.075) to beat 0.228. So the verdict is robust to calibration: **on the only credible market season, the combiner loses decisively.** (Optional follow-ups, neither expected to flip 2026: (a) walk-forward isotonic/Platt calibration of P(over); (b) recompute the stacking weights walk-forward on the OOS signals — current weights are from the contaminated matrix but near-uniform/stable so negligible.)

## Architecture implication

Combined with the H2H verdict (see `h2h_v2_leakage_free.md`): **neither the H2H nor the totals Layer 3 model beats a credible market on clean 2026 data.** This is no longer a single-epic question — the static sub-model→pseudo-BMA-combiner stack does not clear a sharp market on the current season. Strengthens the case for [[project_epic16_status]] sequential posteriors (dynamic, in-season belief updating) over the static Layer 3 stack.

_2026 is the most important single number (cleanest market + current season). 2024-25 distinguish a 2026-specific regime problem from a broader signal-quality problem — here the bias appears in 2026 specifically (regime), while 2024-25 are near-ties on degraded lines. Cross-ref [[project_epic10_totals_verdict]], [[project_layer3_signal_leakage]]._
