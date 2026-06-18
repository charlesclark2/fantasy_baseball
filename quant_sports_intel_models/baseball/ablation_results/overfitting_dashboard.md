# Overfitting Dashboard (Epic E1.4)

Regenerated whenever a strategy is proposed (E1.4). Gate thresholds: **ship→shadow PBO < 0.5**; **shadow→live PBO < 0.2 AND DSR ≥ 0.95 AND live-CLV.**

| Strategy | Stage | PBO | DSR | live-CLV | Verdict | Notes |
|---|---|---|---|---|---|---|
| E3.1 Head-1 line-movement (h2h) | proposed | 0.227 | 0.611 | no | 🟡 SHADOW-eligible | OOS-best by MAE=drift (model_wins_MAE=False); dir-lift over drift +0.036; DSR-excess 0.611 (raw drift-contaminated 1.000) — no robust edge |
| E3.1 Head-1 line-movement (totals) | proposed | 0.000 | 0.008 | no | 🟡 SHADOW-eligible | OOS-best by MAE=no_move (model_wins_MAE=False); dir-lift over drift -0.008; DSR-excess 0.008 (raw drift-contaminated 0.942) — no robust edge |

_PBO = P(in-sample-best config underperforms the OOS median) via CSCV (AFML §11.4). DSR = P(true Sharpe > deflated benchmark) accounting for trial count + non-normality (AFML §14)._