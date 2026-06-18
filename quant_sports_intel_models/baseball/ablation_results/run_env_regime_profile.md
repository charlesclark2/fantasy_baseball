# Cross-Era Run-Environment Regime Profile (Story E1.6)

- Target (current) regime: **2026** · trailing centroid = seasons [2024, 2025] · Gaussian bandwidth 1.5
- Distance/weight axes: scoring **level** + game-total **spread**; league offensive **xwOBA** shown as *informational only* (the contact→runs conversion regime is corrected at the feature level by season-normalization, Story 27.7 — including it here would double-count and destabilize the centroid)

**Regime is NOT time-ordered** — the `regime_weight` is the soft `sample_weight` Story E1.6 uses to extend training history without a hard year cutoff. Older on-regime seasons keep ~full weight; off-regime seasons (e.g. 2019 peak juiced ball) are down-weighted even though recent seasons like 2023 may sit further from the current regime.

| season | R/G | spread | league xwOBA *(info)* | regime dist | weight | band |
|---|---|---|---|---|---|---|
| 2026 | 8.94 | 4.48 | 0.319 | 0.40 | 1.000 | ✅ on-regime |
| 2016 | 8.96 | 4.49 | 0.315 | 0.46 | 0.990 | ✅ on-regime |
| 2018 | 8.90 | 4.53 | 0.315 | 0.71 | 0.927 | ✅ on-regime |
| 2021 | 9.06 | 4.52 | 0.316 | 0.88 | 0.871 | ✅ on-regime |
| 2022 | 8.57 | 4.39 | 0.310 | 0.99 | 0.835 | ✅ on-regime |
| 2015 | 8.50 | 4.40 | 0.308 | 1.14 | 0.779 | ✅ on-regime |
| 2024 | 8.79 | 4.31 | 0.313 | 1.25 | 0.733 | ✅ on-regime |
| 2025 | 8.89 | 4.59 | 0.324 | 1.25 | 0.733 | ✅ on-regime |
| 2017 | 9.29 | 4.53 | 0.319 | 1.52 | 0.619 | 🟡 partial |
| 2020 | 9.29 | 4.55 | 0.321 | 1.63 | 0.573 | 🟡 partial |
| 2023 | 9.23 | 4.58 | 0.320 | 1.65 | 0.566 | 🟡 partial |
| 2019 | 9.66 | 4.76 | 0.319 | 3.68 | 0.051 | 🔴 off-regime |

## How to use (E1.6)
Pass `--regime-weight --min-year 2016` to `promotion_gate_eval.py` (with an E1.3 slim contract via `--challenger-contract`): each fold weights its training games by regime similarity to that fold's eval season, multiplied with the E1.2 uniqueness weight. The question it answers: *does regime-aware extra history (2016+) make the slim model more accurate/robust than the 2021-only version, and does it cut the 2025 over-bias?*

_JSON: `betting_ml/evaluation/regime/run_env_regime_profile.json`_