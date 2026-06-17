# Closing-Line Head-1 — Line-Movement Regression (Epic E3.1)

NGBoost-Normal predicting Bovada's Δ(open→close), under the E1.1 purged walk-forward CV. Target is the book the user bets (the CLV Story-12.5 measures). Pinnacle sharp-open + Layer-2 baseball anchor are 2026-only enrichments (NULL pre-2026 ⇒ they help only the 2026 fold for now). **E3.1 gate: beat BOTH no-move and drift on pooled OOS MAE AND directional-accuracy CI lower bound > 0.5.** Passing is necessary, not sufficient — go-live still needs E1.4 PBO<0.2 + DSR>0 + ≥100 forward live games positive CLV.

| market | n games | MAE model | MAE no-move | MAE drift | dir-acc | dir CI lo | E3.1 gate |
|---|---|---|---|---|---|---|---|
| h2h | 8769 | 0.0224 | 0.0209 | 0.0208 | 0.590 | 0.578 | ❌ no edge |
| totals | 7682 | 0.3251 | 0.2899 | 0.3037 | 0.567 | 0.551 | ❌ no edge |

_Pooled across the 2024/2025/2026 eval folds. `dir-acc` over moved games only._

## h2h — target `h2h_line_movement`

- features (9): `open_home_win_prob, ml_implied_prob_std, ml_implied_prob_range, sharp_soft_ml_spread, n_books_available, consensus_win_prob, pinnacle_open_prob, anchor_gap_h2h, sharp_gap_h2h`

| season | n eval | MAE model | no-move | drift | beats? | dir-acc [90% CI] |
|---|---|---|---|---|---|---|
| 2024 | 1743 | 0.0180 | 0.0184 | 0.0183 | nm✓ dr✓ | 0.597 [0.578,0.617] |
| 2025 | 1817 | 0.0172 | 0.0178 | 0.0178 | nm✓ dr✓ | 0.605 [0.585,0.623] |
| 2026 | 1030 | 0.0391 | 0.0306 | 0.0304 | nm✗ dr✗ | 0.552 [0.527,0.579] |

## totals — target `total_line_movement`

- features (8): `open_total_line, totals_line_std, totals_line_range, n_books_available, pred_total_runs, pinnacle_open_line, anchor_gap_tot, sharp_gap_tot`

| season | n eval | MAE model | no-move | drift | beats? | dir-acc [90% CI] |
|---|---|---|---|---|---|---|
| 2024 | 1718 | 0.3132 | 0.2867 | 0.3011 | nm✗ dr✗ | 0.602 [0.575,0.630] |
| 2025 | 1813 | 0.2916 | 0.2521 | 0.2773 | nm✗ dr✗ | 0.532 [0.502,0.559] |
| 2026 | 966 | 0.4093 | 0.3665 | 0.3871 | nm✗ dr✗ | 0.565 [0.525,0.603] |
