# Story 12.4 — Bayesian sequential CLV meta-model — H2H (featureset=base)

**Population:** 911 moved 2026 live-morning games ⋈ Bovada open→close H2H movement (snapshot_count>1; 968 paired, flat dropped). Label CLV+ = close moved toward the morning model's side; base rate **0.602**.

**Feature set (base):** base 3 features (market-specific derivation).
- `edge_mag` = |centered morning H2H edge| (model_home_prob − open_home_win_prob) — primary signal
- `pub_align` = public (money%−ticket%) × model_side — sharp money on our side
- `open_extremity` = |open_home_win_prob − 0.5| — mean-reversion control

## Convergence gates
| Gate | Value | Threshold | Pass |
|---|---|---|---|
| 1. max R-hat | 1.0000 | < 1.01 | ✅ |
| 2. mean CI width | 0.0757 | < 0.25 | ✅ |
| 3. top−bottom quartile CLV+ rate | +0.1535 (0.675 vs 0.522) | ≥ 0.05 | ✅ |

**Verdict: ✅ ALL GATES PASS — v0 converged** (in-sample AUC 0.579; temporal-split freq. AUC 0.595 — honest generalization sanity, not a gate).

## Coefficient posteriors (mean [94% credible interval], standardized features)
- `b0` = **+0.422** [+0.296, +0.551]
- `b_edge_mag` = **+0.179** [+0.042, +0.324]
- `b_pub_align` = **+0.074** [-0.053, +0.199]
- `b_open_extremity` = **-0.216** [-0.353, -0.081]

## Notes
- Trace: `betting_ml/models/meta_model/bayesian_meta_trace_0911.nc`; scaler/feature-spec sidecar `meta_model_scaler_0911.json`.
- In-sample gates are correct for a sequential model (the edge↔CLV signal is already OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.
- base rate 0.602 (moved games; line moved toward the model's side).
- **Honest discrimination check: temporal AUC 0.595 vs in-sample 0.579.** Temporal ≥ in-sample ⇒ the features generalize.
