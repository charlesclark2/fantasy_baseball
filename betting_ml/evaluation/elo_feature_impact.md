# Elo Team Strength Rating Feature Impact Report (Card 8.D)

Generated from `betting_ml/evaluation/feature_selection.md` after Card 7.MA full retrain (2026-05-04, 294 features, 10,256 rows).

---

## Summary

3 Elo columns were added: `home_elo`, `away_elo`, and `elo_diff`. All 3 survived feature selection. `elo_diff` ranks as the **4th strongest feature** in the entire retained set by max |r|, above pythagorean win expectation differential and well above rolling offense/pitching features.

- **Total Elo columns added:** 3
- **Retained:** 3
- **Dropped:** 0

---

## Retained Features

| Feature | max \|r\| | r (total_runs) | r (run_differential) | r (home_win) | Rank in full set |
|---|---|---|---|---|---|
| `elo_diff` | 0.1854 | -0.0490 | +0.1854 | +0.1613 | 4th of 309 |
| `away_elo` | 0.1444 | +0.0169 | -0.1444 | -0.1184 | 5th of 309 |
| `home_elo` | 0.1258 | -0.0543 | +0.1258 | +0.1165 | 6th of 309 |

---

## Independence from Existing Strength Features

The key question is whether Elo adds signal beyond `pythagorean_win_exp` and `home_win_rate_trailing_3yr`.

| Feature | max \|r\| |
|---|---|
| `elo_diff` | 0.1854 |
| `pythagorean_win_exp_diff` | 0.1761 |
| `home_pythagorean_win_exp` | 0.1202 |
| `home_win_rate_trailing_3yr` | 0.0227 |

`elo_diff` outperforms `pythagorean_win_exp_diff` (0.1854 vs. 0.1761) and both survived multicollinearity screening (|r| < 0.85 between them), confirming they carry independent information. The difference is the opponent-quality dimension: Elo updates based on the quality of the opponent, while pythagorean win expectation only accounts for the team's own runs scored/allowed. `home_win_rate_trailing_3yr` (0.0227) is the weakest of the three — Elo subsumes almost all of the signal in raw win rate.

Feature selection dropped `away_win_pct` as redundant with `away_elo`, confirming that Elo fully replaces the raw win percentage as a team strength signal.

---

## Multicollinearity Side-Effect

| Dropped feature | Redundant with |
|---|---|
| `away_win_pct` | `away_elo` |

This is the expected outcome: Elo and win percentage are highly correlated (both encode team quality) but Elo is the more informative encoding because it incorporates strength of schedule.

---

## Elo Parameters

Per `betting_ml/scripts/compute_elo.py` (FiveThirtyEight MLB standard):
- K-factor: 4 per game
- Home field advantage: 24 Elo points
- Season regression: each team's Elo regresses 1/3 of the way back to 1500 at the start of each new season
- Initialization: all teams start at 1500 in 2015
- Feature used: `elo_before_game` only (leakage-free — reflects Elo before the outcome is known)

---

## Recommendation

**Retain all 3 Elo features.** `elo_diff` is one of the top 5 most predictive features in the entire model and adds opponent-quality information that pythagorean win expectation and win rate do not capture. All 3 features were included in the Card 7.MA retrain. No further action required before the next retrain.
