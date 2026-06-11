# Story 29.1 — Totals Point-Accuracy Benchmark (RMSE/MAE-to-actual)

**Surface:** leakage-free 2026 OOS. **Honest panel = Bovada-source line only** (n=695);
secondary panel = any available line incl. consensus_fallback (n=745).
**Eval only — no training.** Predictors: `model_q50` (10.10 quantile median), `model_v4_mu`
(NGBoost v4 champion mean), `bovada_line` (market posted total), `naive` (expanding season-to-date
2026 league mean, leakage-safe, seeded by 2025 mean = 8.9278).

`bias` = mean(pred − actual): positive over-predicts. RMSE penalizes large misses (mean-optimal);
MAE/MedAE are median-optimal, so `model_q50` (a median) is most fairly read on MAE/MedAE.

## VERDICT
DOWNGRADE — best model (model_v4_mu) RMSE 4.2596 >> Bovada line 3.7298 (gap +0.5297). No central-estimate edge; 29.3 downgraded, totals stay product-only.

(RMSE gap +0.5297, MAE gap +0.7404; best model = model_v4_mu.)

## Honest panel — Bovada-source line only

**2026 (all)**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 695 | 4.3688 | 3.4368 | 2.8445 | -0.5144 |
| model_v4_mu | 695 | 4.2596 | 3.3879 | 2.9227 | +0.0486 |
| bovada_line | 695 | 3.7298 | 2.6475 | 1.5000 | -0.6835 |
| naive | 695 | 4.4988 | 3.6373 | 3.2134 | +0.2783 |

**2026 Apr**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 215 | 4.8474 | 3.7360 | 3.0647 | -1.1843 |
| model_v4_mu | 215 | 4.6056 | 3.6058 | 3.0907 | -0.6212 |
| bovada_line | 215 | 4.5904 | 3.5721 | 3.0000 | -1.2186 |
| naive | 215 | 4.6382 | 3.8294 | 3.5034 | +0.2971 |

**2026 May**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 392 | 4.0747 | 3.2754 | 2.8517 | -0.0119 |
| model_v4_mu | 392 | 4.0668 | 3.2925 | 2.9614 | +0.5664 |
| bovada_line | 392 | 2.9054 | 1.9592 | 1.0000 | -0.2934 |
| naive | 392 | 4.4212 | 3.5887 | 3.2129 | +0.5072 |

**2026 Jun**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 88 | 4.4012 | 3.4253 | 2.6567 | -1.1159 |
| model_v4_mu | 88 | 4.2187 | 3.2807 | 2.6237 | -0.6213 |
| bovada_line | 88 | 4.5590 | 3.4545 | 2.5000 | -1.1136 |
| naive | 88 | 4.4957 | 3.3846 | 2.9378 | -0.7872 |

## Secondary panel — any available line (bovada + consensus_fallback)

**2026 (all)**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 745 | 4.4102 | 3.4654 | 2.8861 | -0.5081 |
| model_v4_mu | 745 | 4.3048 | 3.4185 | 2.9361 | +0.0308 |
| bovada_line | 745 | 3.8191 | 2.7022 | 1.5000 | -0.7110 |
| naive | 745 | 4.5340 | 3.6375 | 3.2023 | +0.2289 |

**2026 Apr**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 215 | 4.8474 | 3.7360 | 3.0647 | -1.1843 |
| model_v4_mu | 215 | 4.6056 | 3.6058 | 3.0907 | -0.6212 |
| bovada_line | 215 | 4.5904 | 3.5721 | 3.0000 | -1.2186 |
| naive | 215 | 4.6382 | 3.8294 | 3.5034 | +0.2971 |

**2026 May**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 403 | 4.0828 | 3.2802 | 2.8527 | -0.0521 |
| model_v4_mu | 403 | 4.0824 | 3.3041 | 2.9472 | +0.5173 |
| bovada_line | 403 | 2.9908 | 2.0096 | 1.5000 | -0.3443 |
| naive | 403 | 4.4319 | 3.5930 | 3.2124 | +0.4614 |

**2026 Jun**

| predictor | n | RMSE | MAE | MedAE | bias |
|---|--:|--:|--:|--:|--:|
| model_q50 | 127 | 4.6284 | 3.5949 | 2.8741 | -0.8102 |
| model_v4_mu | 127 | 4.4626 | 3.4643 | 2.7903 | -0.4093 |
| bovada_line | 127 | 4.6373 | 3.4275 | 2.5000 | -1.0153 |
| naive | 127 | 4.6738 | 3.4539 | 2.0971 | -0.6244 |

## Notes
- A sharp -110/-110 line is the market's own point estimate, so `bovada_line` is the benchmark to beat
  on RMSE/MAE; `naive` is the floor any model must clear to claim *any* point-prediction signal.
- The line's own `bias` row quantifies how well-centered the 2026 market was (vs the model's bias).
- Monthly split exposes regime shifts (the Apr→May→Jun scoring-environment move).
