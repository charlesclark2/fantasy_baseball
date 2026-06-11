# Story 28.5 — Hierarchical Bayesian Bradley-Terry H2H Model

_Reopens the H2H **architecture** after 28.4: a paired-comparison logit likelihood (no count aggregation → no Jensen floor) with partially-pooled team strength, team-specific HFA, and sub-model-signal covariates. Trained 2022–2025 (9076 games), scored leakage-free on 2026 OOS._

## Acceptance Criterion 1 — Convergence (gate FIRST)

| diagnostic | value | gate | pass |
|---|---:|---|:---:|
| max R-hat | 1.0000 | < 1.01 | ✅ |
| min ESS_bulk | 2114 | > 400 | ✅ |
| divergences | 0 | ≤ 5 | ✅ |

**Converged: ✅** 

Signal coefficients (posterior mean): `beta_off`=+0.065, `beta_bull`=-0.561, `beta_start`=-0.091, `beta_rd_sigma`=+0.001.

## Acceptance Criterion 2 — Head-to-head vs XGBoost champion (credible 2026)

- Market quality gate: 2026 Bovada/Parlay Brier = **0.1815** (credible ✅); sharp-band target ≈ 0.182.
- Identical market-covered ∩ champion games: **n = 569**. 2026 home-win base-rate = 0.521.

| layer | metric | Bradley-Terry | XGBoost champion | market |
|---|---|---:|---:|---:|
| L1 | NLL (log-loss) | 0.6396 | 0.6372 | 0.5326 |
| L2 | ECE | 0.0599 | 0.0482 | — |
| L2 | calib-in-large | -0.0083 | +0.0086 | — |
| L3 | Brier | **0.2241** | 0.2231 | 0.1815 |

- Prior baselines: Bernoulli base-rate NLL 0.6920, prior-naive Brier 0.2494.
- Isotonic-recalibrated BT (reference; production calibrator fit on champion probs): Brier 0.2246, ECE 0.0505.

### Gates

| gate | result |
|---|:---:|
| L1 NLL < Bernoulli prior | ✅ |
| Beats champion Brier (Δ = -0.0010) | ❌ |
| Closes toward market | ❌ |
| Beats market Brier (gap to mkt = +0.0426) | ❌ |
| L4 roi_devig>0 & n≥50 | ✅ |

## Verdict — PROMOTE: ❌

**DO NOT PROMOTE** — the architecture change converged but does not beat the champion on the credible 2026 surface (BT Brier 0.2241 vs champion 0.2231 vs market 0.1815). Consistent with the standing Epic 11/28 finding: no H2H edge against the sharp Parlay market.

