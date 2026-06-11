# Story 28.6a — Conviction Gate Real-Book ROI (Bovada American odds)

Strategy: games where `|p_classifier − p_run_diff| ≤ 0.02` (ensemble w=0.25); bet the model's
favored side. ROI on **actual Bovada American H2H odds** (load_devig_home_prob_bovada), profit per 1u =
(decimal−1) on a win, −1 on a loss. Bootstrap B=10000. 2026 OOS.

`n_with_real_odds/n_decisions` = bets that had a real Bovada price (rest dropped — no priced market).

## VERDICT
GO — real-book ROI 95% lower-CI +0.1575 > 0 on the operational threshold bets (n=65). Combined with the ≥2-adjacent-cap plateau, proceed to 28.6b shadow forward test.

| view | n bets | priced/total | real-book ROI | ROI 95% CI | P(ROI>0) |
|---|--:|--:|--:|--:|--:|
| threshold bets (operational) | 65 | 65/65 | +0.5352 | [+0.1575, +1.0196] | 99.9% |
| all agreeing games | 85 | 85/85 | +0.3989 | [+0.0942, +0.7734] | 99.8% |

## Context (from the local robustness preview)
- The model-vs-market **Brier** edge at cap 0.02 is within noise: gap −0.0102, 95% CI [−0.053, +0.032],
  ~68% bootstrap confidence. The edge is a real point-estimate plateau (caps 0.01 & 0.02) but NOT significant
  on n=85. This real-book ROI is the second, independent read on the same finding.
- Pre-committed go/no-go for 28.6b forward test: real-book ROI 95% lower-CI > 0 (primary = threshold bets).
- Reminder: roi_devig (vig-free) reported +0.68 in 28.2 — the gap between that and the real-book number here
  is exactly the vig the 28.3 magnitude work warned about.
