# Story 12.12 — Bayesian sequential CLV meta-model — totals (featureset=base)

**Population:** 438 moved 2026 live-morning games ⋈ Bovada open→close totals movement (snapshot_count>1; 968 paired, flat dropped). Label CLV+ = close moved toward the morning model's side; base rate **0.603**.

**Feature set (base):** base 3 features (market-specific derivation).
- `edge_mag` = |centered morning totals edge| (pred_total_runs − open_total_line) — primary signal
- `pub_align` = public over (money%−ticket%) × model_side — sharp O/U money on our side
- `open_extremity` = |open_total_line − median open total| — mean-reversion control

## Convergence gates
| Gate | Value | Threshold | Pass |
|---|---|---|---|
| 1. max R-hat | 1.0000 | < 1.01 | ✅ |
| 2. mean CI width | 0.1021 | < 0.25 | ✅ |
| 3. top−bottom quartile CLV+ rate | +0.1273 (0.645 vs 0.518) | ≥ 0.05 | ✅ |

**Verdict: ✅ ALL GATES PASS — v0 converged** (in-sample AUC 0.546; temporal-split freq. AUC 0.446 — honest generalization sanity, not a gate).

## Coefficient posteriors (mean [94% credible interval], standardized features)
- `b0` = **+0.425** [+0.247, +0.608]
- `b_edge_mag` = **-0.039** [-0.232, +0.155]
- `b_pub_align` = **+0.102** [-0.072, +0.282]
- `b_open_extremity` = **+0.039** [-0.151, +0.231]

## Notes
- Trace: `betting_ml/models/meta_model/totals/bayesian_meta_trace_0438.nc`; scaler/feature-spec sidecar `meta_model_scaler_0438.json`.
- In-sample gates are correct for a sequential model (the edge↔CLV signal is already OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.
- base rate 0.603 (moved games; line moved toward the model's side).
- **Honest discrimination check: temporal AUC 0.446 vs in-sample 0.546.** Temporal < in-sample ⇒ the features do NOT generalize out-of-sample (in-sample separation is a mirage). The 3 convergence gates can still PASS — they test the sampler + in-sample quartile spread, NOT OOS skill — so treat 'ALL GATES PASS' as 'converged', not 'has edge'. A near-flat served P(CLV>0) (clustered at the base rate) is the honest signal; do not present it as conviction.
