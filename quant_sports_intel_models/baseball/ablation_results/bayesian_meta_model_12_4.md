# Story 12.4 — Bayesian sequential CLV meta-model (v0)

**Population:** 911 moved 2026 live-morning games ⋈ Bovada open→close movement (snapshot_count>1; 968 paired, flat dropped). Label CLV+ = close moved toward the morning model's side; base rate **0.602**.

**Honest feature set** (spec's conviction / gate-signals / CI-width / Epic-16 posteriors are NULL at morning; Pinnacle killed in 12.10′):
- `edge_mag` = |centered morning H2H edge| — primary signal
- `pub_align` = AN (money%−ticket%) × model_side — public sharp money on our side
- `open_extremity` = |open_home_win_prob − 0.5| — mean-reversion control

## Convergence gates
| Gate | Value | Threshold | Pass |
|---|---|---|---|
| 1. max R-hat | 1.0000 | < 1.01 | ✅ |
| 2. mean CI width | 0.0757 | < 0.25 | ✅ |
| 3. top−bottom quartile CLV+ rate | +0.1535 (0.675 vs 0.522) | ≥ 0.05 | ✅ |

**Verdict: ✅ ALL GATES PASS — v0 converged** (in-sample AUC 0.579; temporal-split freq. AUC 0.596 — honest generalization sanity, not a gate).

## Coefficient posteriors (mean [94% credible interval], standardized features)
- `b0` = **+0.422** [+0.296, +0.551]
- `b_edge_mag` = **+0.179** [+0.042, +0.324]
- `b_pub_align` = **+0.074** [-0.053, +0.199]
- `b_open_extremity` = **-0.216** [-0.353, -0.081]

## Notes
- Trace: `betting_ml/models/meta_model/bayesian_meta_trace_0911.nc`; scaler/feature-spec sidecar `meta_model_scaler_0911.json`.
- In-sample gates are correct for a sequential model (the edge↔CLV signal is already OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.
- Deferred to integration (overlaps 12.5): Dagster weekly asset, predict_today columns, Streamlit posterior plots, MLflow CI-width tracker, S3 weekly traces, 2-week convergence confirm.
