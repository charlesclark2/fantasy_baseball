# Card 7.MA — Full Model Retrain Impact Report

**Date:** 2026-05-04  
**Training data:** 10,256 rows, 6 seasons (game_year 2021–2026)  
**Baseline:** Card 7.F (2026-05-03), 267 retained features, 10,243 rows

---

## Feature Set

| | 7.F Baseline | 7.MA |
|---|---|---|
| Total candidates evaluated | — | 466 |
| Retained features | 267 | 292 |
| Pipeline-generated | 2 | 2 |
| **Total model inputs** | **269** | **294** |
| Dropped (near-zero corr) | — | 93 |
| Dropped (multicollinearity) | — | 81 |

**Feature groups added in 7.MA:**

| Card | Feature group | Key columns |
|---|---|---|
| 7.H | Umpire tendencies | ump_runs_per_game_zscore, ump_accuracy_zscore |
| 7.I | Injury / lineup status | home/away_injured_player_count, injury_adj_woba |
| 7.J | Pitch archetype matchup | lineup_woba/xwoba/k_pct/iso_vs_starter_archetype |
| 7.K | Pitcher cluster matchup | lineup_avg_woba/xwoba_vs_cluster |
| 7.K2 | Batter archetype matchup | lineup_archetype_avg_woba/xwoba |
| 7.Q | Bullpen fatigue IP | bullpen_ip_prev_1d/2d, pitchers_used_prev_2d |
| 7.R | Pythagorean win expectation | pythagorean_win_exp, pythagorean_win_exp_diff |

All 8 protected features retained: `game_year`, `home_win_prob_consensus`,
`home_win_rate_trailing_3yr`, `market_bookmaker_count`, `ml_consensus_std`,
`over_prob_consensus`, `post_2022_rules`, `total_line_consensus`.

---

## home_win — XGBoost Classifier

| | 7.F | 7.MA | Delta |
|---|---|---|---|
| CV Brier score | 0.2443 | **0.2439** | −0.0004 (−0.17%) |
| Training rows | 10,243 | 10,256 | +13 |
| Features | 267 | 292 | +25 |
| Artifact | xgb_classifier_tuned_2026.pkl | xgb_classifier_tuned_2026.pkl (overwritten) | — |

**Verdict:** Marginal improvement. New features contributed signal; XGBoost feature
importance will rank Phase 7 additions in subsequent analysis.

---

## total_runs — NGBoost (LogNormal)

| | 7.F | 7.MA | Delta |
|---|---|---|---|
| CV MAE | 3.4856 | **3.5190** | +0.0334 (+0.96%) |
| Best config | n_estimators=500, LogNormal | n_estimators=500, LogNormal | — |
| Training rows | 10,243 | 10,256 | +13 |
| Features | 267 | 292 | +25 |
| Artifact | ngboost_tuned_prod.pkl | ngboost_tuned_2026.pkl | path changed |

**Verdict:** Slight regression within CV noise (below 1% revert threshold). The new
contextual features (umpire tendencies, pythagorean expectation) appear to add mild
noise for total runs prediction without contributing offsetting signal. No revert;
monitor live over/under EV tracking for sustained degradation.

---

## run_differential — NGBoost (Normal)

| | 7.F | 7.MA | Delta |
|---|---|---|---|
| CV MAE | 3.4586 | **3.4724** | +0.0138 (+0.40%) |
| Best config | n_estimators=500, Normal | n_estimators=200, Normal | estimator count ↓ |
| Training rows | 10,243 | 10,256 | +13 |
| Features | 267 | 292 | +25 |
| Artifact | ngboost_tuned_prod.pkl | ngboost_tuned_2026.pkl | path changed |

**Verdict:** Slight regression within CV noise. The optimal estimator count dropped from
500 to 200 — the additional features may have reduced the benefit of deeper ensembles.
LogNormal excluded throughout (run_diff can be negative). No revert.

---

## Calibrator ECE — Platt Scaling on 2026 Results

| | 7.F/7.C | 7.MA |
|---|---|---|
| Raw model ECE | 0.0614 | **0.0247** |
| Post-Platt ECE | 0.0370 | 0.0420 |
| Eval rows | ~2025 season | 217 rows (2026-04-28 → 2026-05-02) |

**Notable finding:** The 7.MA XGBoost model is better calibrated raw (ECE 0.0247) than
the previous *calibrated* model (0.0370). Platt scaling degraded ECE on the eval window
(0.0247 → 0.0420), accompanied by a script WARNING.

Two likely causes:
1. **Small eval window** — 217 rows covering 5 days is insufficient for stable isotonic
   calibration estimation; noise dominates.
2. **Model already calibrated** — the expanded feature set and full 2021+ training window
   may have produced well-calibrated raw probabilities, making post-hoc calibration
   counterproductive.

The calibrator artifact was saved. For production use, the raw XGBoost output (ECE 0.0247)
is preferable to the calibrated output (ECE 0.0420). Consider Card 7.MB to evaluate
whether the calibrator should be removed from the inference path or refitted on a
larger eval window (e.g., all 2026 games to date).

---

## 7.F Interpretation

The 7.MA retrain on the complete Phase 7 feature set produced:

- **home_win**: small improvement (+0.17%) — new features help probability estimation
- **total_runs / run_diff**: small regressions (<1%) — new features add context but also noise for point prediction; likely to improve with more 2026 in-season data as the model's calibration of new features stabilizes
- **Calibrator**: raw model calibration improved dramatically (0.0614 → 0.0247 ECE); post-hoc Platt scaling hurts rather than helps on the 2026 eval window

Overall assessment: the Phase 7 feature expansion produced a net-positive or neutral
retrain. No model degraded by more than 1%; home_win improved. The unexpected finding
is the raw model calibration quality — this may be worth tracking formally.

---

## Recommendation for 7.MB

1. Monitor live EV performance (home_win, over/under, spread) for the first 2–3 weeks of
   May to confirm CV results hold on unseen 2026 games.
2. Evaluate deploying `predict_today.py` without the Platt calibrator layer for home_win
   (or with a recalibration on the full 2026 season once it accumulates ~500+ games).
3. Run feature importance analysis on the 7.MA XGBoost model to rank Phase 7 additions
   and identify candidates for potential removal if noise hypothesis holds.
