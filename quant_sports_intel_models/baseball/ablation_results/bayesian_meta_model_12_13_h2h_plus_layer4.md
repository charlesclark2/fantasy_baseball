# Story 12.4 — Bayesian sequential CLV meta-model — H2H (featureset=plus_layer4)

**Population:** 911 moved 2026 live-morning games ⋈ Bovada open→close H2H movement (snapshot_count>1; 968 paired, flat dropped). Label CLV+ = close moved toward the morning model's side; base rate **0.602**.

**Feature set (plus_layer4):** base 3 features (market-specific derivation) + Story 12.13 extra(s): direction_flip.
- `edge_mag` = |centered morning H2H edge| (model_home_prob − open_home_win_prob) — primary signal
- `pub_align` = public (money%−ticket%) × model_side — sharp money on our side
- `open_extremity` = |open_home_win_prob − 0.5| — mean-reversion control
- `direction_flip` = 1 if the model fades the market favorite (model & open on opposite sides of 0.5) — Story 12.13, +0.11/+0.06 CLV+ lift validated beyond edge_mag

## Convergence gates
| Gate | Value | Threshold | Pass |
|---|---|---|---|
| 1. max R-hat | 1.0000 | < 1.01 | ✅ |
| 2. mean CI width | 0.0857 | < 0.25 | ✅ |
| 3. top−bottom quartile CLV+ rate | +0.1711 (0.697 vs 0.526) | ≥ 0.05 | ✅ |

**Verdict: ✅ ALL GATES PASS — v0 converged** (in-sample AUC 0.578; temporal-split freq. AUC 0.588 — honest generalization sanity, not a gate).

## Coefficient posteriors (mean [94% credible interval], standardized features)
- `b0` = **+0.422** [+0.295, +0.551]
- `b_edge_mag` = **+0.132** [-0.031, +0.307]
- `b_pub_align` = **+0.071** [-0.053, +0.201]
- `b_open_extremity` = **-0.182** [-0.332, -0.030]
- `b_direction_flip` = **+0.081** [-0.083, +0.242]

## Notes
- Trace: `betting_ml/models/meta_model/ablation_plus_layer4/bayesian_meta_trace_0911.nc`; scaler/feature-spec sidecar `meta_model_scaler_0911.json`.
- In-sample gates are correct for a sequential model (the edge↔CLV signal is already OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.
- base rate 0.602 (moved games; line moved toward the model's side).
- **Honest discrimination check: temporal AUC 0.588 vs in-sample 0.578.** Temporal ≥ in-sample ⇒ the features generalize.
