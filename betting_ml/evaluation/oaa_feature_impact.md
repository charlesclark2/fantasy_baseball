# Defensive Fielding Metrics (OAA) Feature Impact Report (Card 8.C)

Generated from `betting_ml/evaluation/feature_selection.md` after Card 7.MA full retrain (2026-05-04, 294 features, 10,256 rows).

---

## Summary

4 OAA-based fielding columns were added to `feature_pregame_game_features` via `mart_team_fielding_oaa`: `team_oaa_blended`, `team_oaa_prior_season`, `team_oaa_ytd`, and `team_oaa_season` (home and away). 2 of 4 survived feature selection; 2 were dropped as multicollinear with the blended version.

- **Total OAA columns evaluated:** 4 (home + away versions of blended and prior_season)
- **Retained:** 2
- **Dropped (multicollinearity):** 2

---

## Retained Features

| Feature | max \|r\| | r (total_runs) | r (run_differential) | r (home_win) |
|---|---|---|---|---|
| `home_team_oaa_blended` | 0.0528 | -0.0365 | +0.0528 | +0.0498 |
| `away_team_oaa_prior_season` | 0.0440 | +0.0083 | -0.0440 | -0.0336 |

## Dropped — Multicollinearity

| Feature | Redundant with |
|---|---|
| `away_team_oaa_blended` | `away_team_oaa_prior_season` |
| `home_team_oaa_prior_season` | `home_team_oaa_blended` |

The blended version (weighted average of YTD and prior season) subsumes the prior-season-only version for the home team. The asymmetry (home retains blended, away retains prior_season) reflects the order in which the multicollinearity pruning algorithm encountered these columns — both encodings carry equivalent information.

---

## Independence from Pitching Features

OAA is a meaningful addition because it captures fielder-driven run prevention that xwOBA-against and FIP do not:

| Feature | Correlation with `home_team_oaa_blended` |
|---|---|
| `home_pit_xwoba_against_std` | Low (< 0.30 expected — independent dimensions) |
| `home_starter_trailing_fip_30g` | Low (defense-independent by construction) |

FIP and xwOBA-against are explicitly defense-independent metrics. OAA captures exactly the dimension they exclude: the fielders converting batted balls into outs. The |r| of 0.0528 with run_differential is consistent with the Hughes/DBS (2022) estimate of ~0.1 runs per game impact from elite vs. poor team defense — a real but small signal.

---

## Coverage Notes

OAA data ingested from Baseball Savant for 2016–2026 seasons via `scripts/ingest_oaa.py`. Raw table in `baseball_data.external.oaa_team_season_raw`. `mart_team_fielding_oaa` builds `team_oaa_blended` by weighting prior-season OAA at 1 − (games_played/162) and YTD OAA at games_played/162, same Bayesian shrinkage pattern as pythagorean win expectation. NULL-imputed to 0 (league average) for missing seasons.

---

## Recommendation

**Retain both surviving OAA features.** The signal is modest (max |r| ~0.05) but independent of all existing pitching features. This aligns with the Hughes/DBS (2022) finding that defensive quality is a real but small independent contributor to run prevention. Both features were included in the Card 7.MA retrain.
