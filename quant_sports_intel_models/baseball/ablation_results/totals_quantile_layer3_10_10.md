# Story 10.10 — Quantile-Regression Layer-3 Challenger (Totals)

**Hypothesis tested:** does dropping the NegBin `exp(β·z)` log-link remove the §10 Jensen floor (β_bullpen≈0.172 → predicted mean pinned ≥8.87 > 8.81 before any signal)?

A LightGBM quantile-regression model (q=0.10/0.25/0.50/0.75/0.90, pinball loss) predicts the conditional quantiles of `total_runs` directly — no `exp()` parameterization, so no structural floor by construction. Trained walk-forward on the Layer-3 matrix (`build_totals_dataset`, completeness ≥0.40, market-blind); P(over) interpolated DIRECTLY from the predictive quantiles (no NegBin CDF). Same 2026 leakage-free OOS surface as 27.3.

## HEADLINE — kill criterion first (May-2026 mean predicted total vs 8.81)

- **May-2026 mean predicted total (q50): 8.5314** (n=419); threshold ≤ 8.81 → **PASS**.
- May-2026 actual mean total: 8.6086.
- **Jensen floor REMOVED** — the quantile model's May-2026 mean predicted total (8.5314) is **below** the 8.81 threshold and tracks the league actual (8.6086), not pinned ≥8.87 like the log-link champion.

## 2026 OOS surface (the only leakage-free verdict surface)

- Games: 789 (settled Bovada-line: 667).
- **calib_80** (empirical [q10,q90] coverage): **0.6857** (nominal 0.80, gate 0.75–0.85) → ❌.
- Mean 80% PI width: 8.619 runs.
- MAE(q50): 3.4277 · mean residual: -0.4797 · std(q50): 1.9099.
- **Brier vs market:** model **0.3053** vs Bovada de-vig **0.2292** vs naive-0.50 0.2500 → beats market ❌, beats naive ❌.
- Mean P(over): 0.536 · actual over-rate: 0.462.

## Per-season walk-forward (2023–25 are leakage-CONTAMINATED — context only, NOT the verdict)

| Season | n | mean q50 | mean actual | MAE(q50) | calib_80 | PI80 width | Brier model | Brier market |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023 *(leakage-contam.)* | 2201 | 9.191 | 9.211 | 3.168 | 0.712 | 8.684 | 0.2273 | 0.2491 |
| 2024 *(leakage-contam.)* | 2199 | 7.944 | 8.746 | 3.026 | 0.715 | 8.221 | 0.2309 | 0.2439 |
| 2025 *(leakage-contam.)* | 2201 | 9.051 | 8.928 | 3.148 | 0.728 | 8.933 | 0.2182 | 0.2480 |
| 2026 *(OOS verdict)* | 789 | 8.539 | 9.019 | 3.428 | 0.686 | 8.619 | 0.3053 | 0.2292 |

## Decision gates

| Gate | Result |
|---|:--:|
| Kill criterion: May-2026 mean q50 ≤ 8.81 | ✅ |
| calib_80 ∈ [0.75, 0.85] | ❌ |
| Brier(P_over) < market | ❌ |
| Brier(P_over) < naive-0.50 | ❌ |

## VERDICT: **DEFER**

The quantile model does NOT clear the bar to un-pause totals. The Jensen floor IS removed (May-2026 mean ≤ 8.81), but the model does not beat the market on the 2026 OOS Brier — removing the structural floor is necessary but not sufficient; the covariates still add no deployable edge over Bovada. Totals stays paused (§11). No re-tuning to force a pass.

_Leakage guard: the verdict is computed on the 2026 OOS surface ONLY; 2023–25 Layer-3 predictions are contaminated by in-sample sub-model signal leakage and are shown for context only._

