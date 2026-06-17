# Story 12.10′ — Pinnacle sharp-money lift (OPEN vs CLOSE framing)

Population: 2026 live morning-edge ⋈ Bovada line movement. n=834 (Pinnacle+steam, moved). clv_up rate=0.574. Label = Bovada open→close move direction. Gate ≥ +0.01 on OPEN (actionable).

| Model | CV AUC | Lift vs BASE |
|---|---|---|
| BASE (morning edge) | 0.6204 ± 0.0387 | — |
| BASE + OPEN (actionable) | 0.6299 ± 0.0394 | **+0.0095** |
| BASE + CLOSE (leaky) | 0.9756 ± 0.0106 | +0.3552 |

**Actionable (OPEN) verdict: ❌ below gate — drop** (lift +0.0095 vs gate +0.01).
**Leakage check:** CLOSE−OPEN lift gap = +0.3457 (most apparent lift is mechanical close co-movement).

Per-feature univariate AUC (direction-agnostic) + logistic coef:

*OPEN framing:*
  - morning_edge               uni-AUC=0.621  coef=+0.301
  - pin_open_devig             uni-AUC=0.588  coef=-0.018
  - bovada_open_vs_pin_open    uni-AUC=0.605  coef=-0.747
  - an_handle_ticket_div       uni-AUC=0.556  coef=+0.173

*CLOSE framing:*
  - morning_edge               uni-AUC=0.621  coef=+0.389
  - pin_close_devig            uni-AUC=0.570  coef=-0.085
  - pin_steam                  uni-AUC=0.953  coef=+8.279
  - bovada_close_vs_pin_close  uni-AUC=0.595  coef=+4.344
  - an_handle_ticket_div       uni-AUC=0.556  coef=+0.068
