# Line Movement Feature Impact Report

**Card:** 7.P3 — Line Movement Feature Engineering
**Date:** 2026-05-03

---

## Feature Selection: Correlation with home_win

Threshold: |r| ≥ 0.02

| Feature | Pearson r | Survived? |
|---|---|---|
| `home_h2h_line_movement` | 0.0247 | ✓ |
| `home_open_win_prob` | 0.1865 | ✓ |
| `total_line_movement` | -0.0019 | ✗ |
| `open_total_line` | -0.0330 | ✓ |

---

## CV Brier Score: Baseline vs. With Line Movement

Method: XGBoost + Platt calibration, season-forward CV (min 3 train seasons).
Hyperparameters: fixed at representative values (not tuned — full grid search at Card 7.MA).

| Model | Mean Brier | Mean h2h edge (has_odds rows) |
|---|---|---|
| Baseline (retained features) | 0.2455 | -0.0081 |
| +line movement features      | 0.2466 | -0.0085 |
| Delta                        | +0.0011 | -0.0004 |

Brier regressed by 0.0011 — line movement features may add noise.

---

## SHAP Top-20 Feature Importance

| Rank | Feature | Mean |SHAP| |
|---|---|---|
| 1 | `home_win_prob_consensus` | 0.0883 |
| 2 | `home_starter_pitcher_id` | 0.0409 |
| 3 | `away_starter_stuff_plus` | 0.0386 |
| 4 | `home_avg_woba_30d` | 0.0338 |
| 5 | `home_pit_woba_against_std` | 0.0333 |
| 6 | `away_win_pct` | 0.0300 |
| 7 | `home_open_win_prob` | 0.0299 | ← **line movement**
| 8 | `home_starter_bb_pct_std` | 0.0298 |
| 9 | `right_center_ft` | 0.0293 |
| 10 | `home_avg_woba_vs_lhp` | 0.0253 |
| 11 | `home_starter_bb_pct_14d` | 0.0237 |
| 12 | `away_starter_whiff_rate_14d` | 0.0235 |
| 13 | `home_games_last_7d` | 0.0235 |
| 14 | `away_vs_lhp_woba_30d` | 0.0232 |
| 15 | `home_win_rate_trailing_3yr` | 0.0216 |
| 16 | `away_pit_k_pct_7d` | 0.0213 |
| 17 | `home_starter_hard_hit_pct_7d` | 0.0212 |
| 18 | `home_avg_xwoba_vs_lhp` | 0.0205 |
| 19 | `away_starter_whiff_rate_vs_rhb` | 0.0194 |
| 20 | `park_run_factor_3yr` | 0.0193 |

`home_h2h_line_movement` mean |SHAP|: 0.0108

---

## Recommendation

**EXCLUDE pending Card 7.MA full retrain**

Rationale:
- `home_h2h_line_movement` passed correlation filter (r = 0.0247)
- `home_open_win_prob` passed correlation filter (r = 0.1865)
- `total_line_movement` did NOT pass correlation filter (r = -0.0019)
- `open_total_line` passed correlation filter (r = -0.0330)

Note: Full model retrain with all Phase 7 features is deferred to Card 7.MA.
This evaluation uses fixed hyperparameters and should be interpreted as directional only.
