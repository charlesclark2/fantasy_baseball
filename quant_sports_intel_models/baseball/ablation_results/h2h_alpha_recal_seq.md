# H2H Alpha Re-calibration — Sequential Champion (Story 28.1)

_Run: 2026-06-10 18:12 UTC_  
_Source: `oos_predictions_h2h_v2.parquet`, season 2026, market-covered (628 games)_

## Alpha Grid (log-loss objective)

| α | Log-Loss | Δ vs best |
|--:|--:|--:|
| 0.0 | 0.528698 | 0.002051 |
| 0.1 | 0.526647 | 0.000000 ⭐ |
| 0.2 | 0.526963 | 0.000316 |
| 0.3 | 0.529873 | 0.003226 |
| 0.4 | 0.535607 | 0.008961 |
| 0.5 | 0.544390 | 0.017743 |
| 0.6 | 0.556415 | 0.029769 |
| 0.7 | 0.571833 | 0.045186 |
| 0.8 | 0.590728 | 0.064081 |
| 0.9 | 0.613111 | 0.086465 |
| 1.0 | 0.638923 | 0.112276 |

**Best α = 0.1** (log-loss = 0.526647)

## Interpretation

**α = 0.1 → technically blended, but the magnitude signal collapses.**

The posterior blend `sigmoid(α·logodds(model) + (1-α)·logodds(market))` with
α=0.1 is 90% market + 10% model. It lowers global log-loss by a marginal
**Δ=0.002** vs α=0 — a negligible calibration gain. However, because the blend
pulls the posterior so close to the market price, the mean magnitude gap
(`|posterior − market_p|`) collapses from **0.1997 → 0.0170 (−91.5%)**.

This destroys the Layer-4 selective strategy: at every threshold the blended
sweep produces fewer than 50 bets (unreliable), and Layer-4 verdict = **False**.
The raw-model magnitude path (Layer-4 verdict = **True**, n_bets=343,
roi_devig=+0.179) survives only because it uses the raw model probabilities before
any market blend.

**Consequence for Story 28.3:**
- `h2h_seq_alpha=0.1` is the calibration-layer value (minimal improvement, stored
  for completeness).
- The magnitude kill-criterion in 28.3 **must evaluate on raw `model_p_home_win`**
  (not the α=0.1 blend), because the blend erases the signal entirely.
- Operationally, the H2H model is effectively a **market mirror at α=0** for the
  purpose of the magnitude selective strategy. The live deploy path is:
  use raw model output to compute `|model_p − market_p|`; gate on threshold ≥ 0.20;
  the α blend should NOT be applied before computing the magnitude gap.
- If Story 28.3 confirms positive roi_devig survives on live data, the recommended
  alpha for the magnitude-gated live path is **α=0.0** (i.e., compare raw model
  directly to the market).

## Layer-4 Attribution (blended α=0.1)

Mean magnitude gap: raw = 0.1997, blended = 0.0170 (91.5% shrinkage)

### Threshold sweep — blended probabilities

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 26 | 0.041 | 0.500 | -0.0455 | +0.0042 | ⚠️ |
| 1.00 | 0.08 | 24 | 0.038 | 0.500 | -0.0455 | +0.0360 | ⚠️ |
| 1.00 | 0.10 | 24 | 0.038 | 0.500 | -0.0455 | +0.0360 | ⚠️ |
| 1.00 | 0.12 | 24 | 0.038 | 0.500 | -0.0455 | +0.0360 | ⚠️ |
| 1.00 | 0.15 | 24 | 0.038 | 0.500 | -0.0455 | +0.0360 | ⚠️ |
| 1.00 | 0.20 | 24 | 0.038 | 0.500 | -0.0455 | +0.0360 | ⚠️ |

**Layer-4 verdict (blended): passed=False**  

### Threshold sweep — raw model probabilities (baseline)

_Gate metric: **roi_devig** (⭐ = optimal by gate)._

| totals_thr | h2h_thr | n_bets | bet_rate | win_rate | roi_110 | roi_devig | reliable |
|---:|---:|---:|---:|---:|---:|---:|:--:|
| 1.00 | 0.05 | 557 | 0.887 | 0.630 | +0.2030 | +0.1573 | ✅ |
| 1.00 | 0.08 | 515 | 0.820 | 0.614 | +0.1714 | +0.1499 | ✅ |
| 1.00 | 0.10 | 484 | 0.771 | 0.607 | +0.1597 | +0.1572 | ✅ |
| 1.00 | 0.12 | 463 | 0.737 | 0.603 | +0.1504 | +0.1648 | ✅ |
| 1.00 | 0.15 | 417 | 0.664 | 0.588 | +0.1216 | +0.1751 | ✅ |
| 1.00 | 0.20 | 343 ⭐ | 0.546 | 0.557 | +0.0631 | +0.1799 | ✅ |

**Layer-4 verdict (raw): passed=True**  
optimal h2h_threshold=0.2, n_bets=343, roi_devig=0.1799
