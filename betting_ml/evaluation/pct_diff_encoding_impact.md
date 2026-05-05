# Pct-Diff Feature Encoding Impact Report (Card 8.A)

Generated from `betting_ml/evaluation/feature_selection.md` after Card 7.MA full retrain (2026-05-04, 294 features, 10,256 rows).

---

## Summary

8 percentage-difference columns were added to `feature_pregame_game_features` covering the five feature groups in the Card 8.A spec. 7 of 8 survived feature selection; 1 was dropped as multicollinear with an existing difference feature.

- **Total pct-diff columns added:** 8
- **Retained:** 7
- **Dropped (multicollinearity):** 1

---

## Retained Features

| Feature | max \|r\| | r (total_runs) | r (run_differential) | r (home_win) |
|---|---|---|---|---|
| `home_away_off_xwoba_30d_pct_diff` | 0.1128 | -0.0012 | +0.1128 | +0.0998 |
| `home_away_off_woba_30d_pct_diff` | 0.0988 | +0.0131 | +0.0988 | +0.0880 |
| `home_away_starter_k_pct_std_pct_diff` | 0.0956 | -0.0255 | +0.0956 | +0.0739 |
| `home_away_starter_xwoba_against_std_pct_diff` | 0.0909 | +0.0225 | -0.0909 | -0.0689 |
| `home_away_bp_xwoba_against_30d_pct_diff` | 0.0848 | +0.0393 | -0.0847 | -0.0848 |
| `home_away_off_k_pct_30d_pct_diff` | 0.0522 | +0.0033 | -0.0522 | -0.0506 |
| `home_away_injury_adj_avg_woba_30d_pct_diff` | 0.0251 | +0.0122 | +0.0251 | +0.0220 |

## Dropped — Multicollinearity

| Feature | Redundant with |
|---|---|
| `home_away_pythagorean_win_exp_pct_diff` | `pythagorean_win_exp_diff` |

The pythagorean pct-diff is highly correlated with the absolute difference version already in the model (|r| > 0.85). This is expected — pythagorean win expectation is bounded [0,1] so pct-diff and absolute difference carry near-identical information.

---

## Cross-Correlation with Raw/Absolute-Diff Equivalents

The top two pct-diff survivors compare favorably against their raw absolute-value counterparts:

| pct-diff feature | max \|r\| | Best raw equivalent | max \|r\| |
|---|---|---|---|
| `home_away_off_xwoba_30d_pct_diff` | 0.1128 | `away_off_xwoba_std` | 0.0937 |
| `home_away_off_woba_30d_pct_diff` | 0.0988 | `away_off_runs_per_game_std` | 0.0937 |
| `home_away_starter_k_pct_std_pct_diff` | 0.0956 | `away_pit_k_pct_std` | 0.1097 |
| `home_away_starter_xwoba_against_std_pct_diff` | 0.0909 | `away_pit_xwoba_against_std` | 0.1073 |

The offense pct-diff features (`off_xwoba`, `off_woba`) outperform their raw home/away counterparts, confirming the Cui (2020) finding on this dataset. Starter pct-diff features are marginally weaker than their raw counterparts, likely because starting pitcher quality varies on an absolute scale in ways that raw values already capture.

---

## Recommendation

**Retain all 7 surviving pct-diff features in the next scheduled retrain.** The offense pct-diff columns carry independent signal above the raw home/away values. All 7 were included in the Card 7.MA retrain (294 features, 10,256 rows). No further action required.
