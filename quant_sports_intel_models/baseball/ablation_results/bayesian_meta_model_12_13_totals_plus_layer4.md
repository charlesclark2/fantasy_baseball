# Story 12.12 — Bayesian sequential CLV meta-model — totals (featureset=plus_layer4)

**Population:** 438 moved 2026 live-morning games ⋈ Bovada open→close totals movement (snapshot_count>1; 968 paired, flat dropped). Label CLV+ = close moved toward the morning model's side; base rate **0.603**.

**Feature set (plus_layer4):** base 3 features (market-specific derivation) + Story 12.13 extra(s): edge_sigma.
- `edge_mag` = |centered morning totals edge| (pred_total_runs − open_total_line) — primary signal
- `pub_align` = public over (money%−ticket%) × model_side — sharp O/U money on our side
- `open_extremity` = |open_total_line − median open total| — mean-reversion control
- `edge_sigma` = |centered totals edge| / pred_total_runs_scale (edge in model-σ units) — Story 12.13 candidate

## Convergence gates
| Gate | Value | Threshold | Pass |
|---|---|---|---|
| 1. max R-hat | 1.0000 | < 1.01 | ✅ |
| 2. mean CI width | 0.1099 | < 0.25 | ✅ |
| 3. top−bottom quartile CLV+ rate | +0.1545 (0.636 vs 0.482) | ≥ 0.05 | ✅ |

**Verdict: ✅ ALL GATES PASS — v0 converged** (in-sample AUC 0.571; temporal-split freq. AUC 0.448 — honest generalization sanity, not a gate).

## Coefficient posteriors (mean [94% credible interval], standardized features)
- `b0` = **+0.423** [+0.245, +0.607]
- `b_edge_mag` = **+0.030** [-0.181, +0.246]
- `b_pub_align` = **+0.114** [-0.064, +0.289]
- `b_open_extremity` = **+0.040** [-0.150, +0.233]
- `b_edge_sigma` = **-0.159** [-0.385, +0.051]

## Notes
- Trace: `betting_ml/models/meta_model/totals/ablation_plus_layer4/bayesian_meta_trace_0438.nc`; scaler/feature-spec sidecar `meta_model_scaler_0438.json`.
- In-sample gates are correct for a sequential model (the edge↔CLV signal is already OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.
- base rate 0.603 (moved games; line moved toward the model's side).
- **Honest discrimination check: temporal AUC 0.448 vs in-sample 0.571.** Temporal < in-sample ⇒ the features do NOT generalize out-of-sample (in-sample separation is a mirage). The 3 convergence gates can still PASS — they test the sampler + in-sample quartile spread, NOT OOS skill — so treat 'ALL GATES PASS' as 'converged', not 'has edge'. A near-flat served P(CLV>0) (clustered at the base rate) is the honest signal; do not present it as conviction.
