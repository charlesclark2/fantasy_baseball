# E5.2 — Served K model: poisson_glm_k (bake-off winner)

_Fit 2026-06-25 · seasons 2021–2026 · 26,062/26,320 eligible starts · purged walk-forward CV · market-blind._

## What is served
- **poisson_glm_k** — a Poisson GLM on the market-blind feature set (recency windows + workload + matchup), coverage-recalibrated (λ = 0.85). won the E5.2 bake-off (bakeoff_strikeouts.py) on CRPS + at-the-line ECE, PBO-deflated.
- Artifact (gitignored): `betting_ml/models/sub_models/prop_pricing_v1/strikeout_glm_v1.pkl` — `PoissonRegressor` + scaler + impute + features + λ.
- The compound Beta-Binomial is the interpretable fallback (`--model compound`).

## Calibration (purged walk-forward)

| metric | value |
|---|---|
| strikeout calib_80 (≥0.80) | 0.8104 ✅ |
| PIT max decile dev | 0.0505 |
| mean ECE at the K lines | 0.0202 |
| pitcher_outs calib_80 | 0.9016 |

Per-line ECE: {'3.5': 0.0285, '4.5': 0.0149, '5.5': 0.0162, '6.5': 0.0128, '7.5': 0.0256, '8.5': 0.0262, '9.5': 0.0169}

> best_alpha = 0 — calibration/ECE is PRODUCT value (projections), not an edge claim. The edge verdict is **E5.4** (PBO<0.2 + DSR>0 per market, multiple-comparison-corrected, + forward CLV).
