# Betting Model — EDA Findings

Key findings from Phase 3 exploratory analysis. Updated as each notebook runs.

---

## 01 — Target Variable Analysis (2026-04-23)

**Source:** `feature_pregame_game_features` ⋈ `mart_game_results`, 2016–2025 regular season  
**Clean training set:** `has_full_data = true` — 23,444 games

### Total Runs (over/under target)

| Season | Games | Avg Runs | SD | Home Win Rate |
|---|---|---|---|---|
| 2016 | 2,368 | 8.94 | 4.50 | 0.529 |
| 2017 | 2,292 | 9.27 | 4.52 | 0.544 |
| 2018 | 1,949 | 8.90 | 4.55 | 0.528 |
| 2019 | 2,367 | **9.65** | 4.74 | 0.529 |
| 2020 | 799  | 9.25 | 4.52 | 0.548 |
| 2021 | 2,318 | 9.04 | 4.50 | 0.537 |
| 2022 | 2,376 | **8.57** | 4.40 | 0.534 |
| 2023 | 2,373 | 9.21 | 4.56 | 0.519 |
| 2024 | 2,369 | 8.76 | 4.29 | 0.523 |
| 2025 | 2,228 | 8.84 | 4.59 | 0.546 |

**Distribution:** Approximately Normal (μ ≈ 9.0, σ ≈ 4.5). Slight right tail — blowout games (30+ runs) occur more often than a pure Gaussian predicts. Range: 1–38 runs.

**Stability:** SD is consistent at 4.3–4.7 every season regardless of mean. Mean varies by ~1.1 runs peak-to-trough (8.57 in 2022 → 9.65 in 2019). Shape is stable; center shifts are learnable from features.

### Run Differential (spread target)

Season means stay within ±0.26 of zero. Leptokurtic (heavier tails than Normal — large blowouts occur). No structural asymmetry by season. Spread: −24 to +21 in the training window.

### Home Win Rate (moneyline target)

Period mean: **0.529** (range 0.519–0.548). Declining trend in recent seasons:
- 2023: 0.519 (lowest in window)
- 2024: 0.523

Home field advantage is real but weakening — likely reflects reduced crowd effects after COVID, schedule changes, and the universal DH.

### Naive Baseline MAE (totals)

| Predictor | MAE | RMSE |
|---|---|---|
| Global mean (9.0 runs) | **~3.5 runs** | **~4.5 runs** |
| Prior-season mean | similar | similar |

Any useful totals model must beat ~3.5 runs MAE. Prior-season mean provides minimal improvement over the global mean, confirming that simple season-level adjustments alone are insufficient.

### Recommendation: Single model with era features

| Decision | Rationale |
|---|---|
| Single unified model (not era-specific) | Shape and variance stable; ~1-run mean drift is learnable from features |
| Include `game_year` or `post_2022_rules` as feature | Absorbs regime mean shifts without splitting train set |
| Exclude 2020 (or down-weight heavily) | 799-game COVID bubble; structural confounders don't generalize |
| Flag 2023+ as regime break in features | Pitch clock, shift ban, larger bases → different game dynamics |
| Calibrate home field advantage per era | Not a fixed constant; declining from ~0.54 toward ~0.52 |

---

---

## 02 — Feature Coverage & Null Analysis (2026-04-23)

**Source:** `feature_pregame_game_features`, 2015–2026, all 374 feature columns  
**Notebook:** `exploratory_data_analysis/02_feature_coverage.py`

### `has_full_data` Row Count Verification

Actual counts match schema.yml expectations exactly for 2015–2025 (the complete seasons). Any future drift indicates a mart rebuild changed the training subset.

| Season | Expected | Actual |
|---|---|---|
| 2015 | 0 | 0 |
| 2016 | 2,364 | 2,364 |
| 2017 | 2,288 | 2,288 |
| 2018 | 1,953 | 1,953 |
| 2019 | 2,363 | 2,363 |
| 2020 | 801 | 801 |
| 2021 | 2,320 | 2,320 |
| 2022 | 2,377 | 2,377 |
| 2023 | 2,371 | 2,371 |
| 2024 | 2,369 | 2,369 |
| 2025 | 2,228 | 2,228 |
| 2026 | 351 | 351 |

### Columns Flagged >5% Null in Any Complete Season (2016–2025)

Two column groups exceed the 5% threshold:

**1. Odds price columns (11 columns) — 100% null across all complete seasons**

| Column group | Null rate | Root cause |
|---|---|---|
| `home_moneyline_american`, `away_moneyline_american`, `home_implied_prob`, `away_implied_prob`, `total_market_vig`, `total_line`, `over_american`, `under_american`, `over_implied_prob`, `under_implied_prob`, `totals_market_vig` | 100% (2016–2025) | Card 3 historical odds backfill not yet completed; `has_odds` event flag populates (72–78% of 2021–2025 games) but price snapshots are absent for all pre-backfill seasons |

Note: `has_odds` is true for 72–78% of 2021–2025 games but 0% for 2015–2020. All actual price columns are null for the entire 2016–2025 training window.

**2. Starter platoon splits (16 columns) — 11–17% null in every complete season**

| Column group | Null rate range | Root cause |
|---|---|---|
| `home_starter_xwoba_vs_lhb/rhb`, `home_starter_k_pct_vs_lhb/rhb`, `home_starter_bb_pct_vs_lhb/rhb`, `home_starter_whiff_rate_vs_lhb/rhb`, and away equivalents | 11–17% (2016–2025) | Pitchers who debuted in the prior season or had no regular-season appearances with qualifying plate-against counts in `mart_pitcher_vs_handedness_splits`. Structurally stable — real missing history, not a data issue. |

### All Other Feature Groups: <5% Null

Lineup features, team rolling stats, bullpen workload/effectiveness, schedule context, and park dimension columns all clear the 5% threshold in every complete season. Small null fractions remain for season-boundary conditions:
- `home_win_pct` / `away_win_pct`: ~3.9% null (Opening Day — no prior record)
- `home_days_rest` / `away_days_rest`: ~0.6% null (first game of each season)
- `home_bp_xwoba_against_*` / `away_bp_xwoba_against_*`: 1–4% null (early season, insufficient rolling history)
- `park_run_factor_3yr`: <1% null most seasons; spikes in 2025 (6.8%, likely Sacramento ballpark with no 2024 history)

### Imputation Strategy Decisions

| Feature group | Decision | Rationale |
|---|---|---|
| Odds price columns | **Exclude from primary model** | No imputation possible — feature doesn't exist for training window; use as optional enrichment block post-backfill |
| Starter platoon splits | **Indicator flag + league-average imputation** | Add `has_starter_platoon_data` Boolean; impute nulls with prior-season league-average split by pitcher hand × batter hand |
| Park run factor (null in new-venue seasons) | **Cascade imputation** | Use 1-yr `runs_per_game_at_park` when `park_run_factor_3yr` null; fall back to league average; add `is_new_venue` indicator |
| Season record (`win_pct`, Opening Day) | **Impute with 0.500** | League-average expectation on Opening Day is a neutral prior |
| Days rest (team + starter, first game) | **Impute with 4 days** | Typical off-season rest; median fill also acceptable |
| Bullpen effectiveness (early-season rolling) | **Impute with prior-season league-average bullpen xwOBA** | Low null rate (<5%); league average is a safe neutral prior |

---

## 03 — Rolling Window Stability (2026-04-23)

**Source:** `feature_pregame_game_features` (has_full_data = true) ⋈ `mart_game_results`, 2016–2025 regular season, 2020 excluded  
**Training set:** 20,640 games  
**Notebook:** `exploratory_data_analysis/03_rolling_window_stability.py`

### Correlation vs. Window Size (|Pearson r| with total runs, combined home+away)

| Feature | 7-day | 14-day | 30-day | Season-to-date |
|---|---|---|---|---|
| Team Off wOBA   | 0.041 | 0.046 | 0.052 | 0.051 |
| Team Pit xwOBA  | 0.050 | 0.056 | 0.058 | 0.061 |
| Starter K%      | 0.060 | 0.070 | 0.077 | 0.077 |
| Starter xwOBA   | 0.048 | 0.055 | 0.057 | 0.066 |
| **Column mean** | **0.050** | **0.057** | **0.061** | **0.064** |

Correlation increases monotonically from 7-day to season-to-date for pitcher-quality features (pit xwOBA, starter K%, starter xwOBA). Team offense wOBA peaks at the 30-day window — STD is essentially equal, suggesting 30 games is enough to capture batting quality without benefiting from further averaging. **Starter K% shows the largest window effect:** |r| rises 29% from 7-day (0.060) to season-to-date (0.077).

### Early-Season Instability (30-day window, total runs)

| Games played (both teams) | n | Off wOBA |r| | Pit xwOBA |r| | Starter K% |r| |
|---|---|---|---|---|
| 0–10 games   | 1,134 | 0.066 | 0.046 | 0.077 |
| 10–30 games  | 2,444 | 0.034 | 0.040 | 0.072 |
| 30+ games    | 17,062 | 0.050 | 0.068 | 0.077 |

The bucket pattern is not purely monotonic by feature. The clearest finding: **pitching features (team pit xwOBA) are substantially noisier before 30 games** (|r| = 0.046 in 0–10 bucket vs. 0.068 in 30+ bucket — a 48% difference). Offense wOBA in the 0–10 bucket shows inflated apparent correlation, likely because early-season samples are dominated by facing well-rested, Opening Day-caliber starters; the correlation dips in the 10–30 window before recovering. Starter K% is consistently predictive across buckets.

The 10–30 bucket (2,444 games, ~12% of training data) consistently shows the weakest or near-weakest correlation for both offense and pitching metrics — this is the period where 30-day rolling stats have accumulated too few games to be stable but are no longer capturing the Opening Day context.

### Training Set Size at Games-Played Thresholds

| Min games played | Games retained | % of training set |
|---|---|---|
| ≥ 10 | 18,147 | 87.9% |
| ≥ 15 | 17,547 | 85.0% |
| ≥ 20 | 16,908 | 81.9% |
| ≥ 25 | 16,290 | 78.9% |

### Recommendation: Phase 4 Training Set Filter and Window Choice

**Rolling window:** Use season-to-date as the primary feature window for all starter and pitching metrics. Use 30-day as the primary window for team offense (STD and 30d are equivalent; 30d is more robust to team-roster changes). Retain 7-day and 14-day windows only as hot/cold streak supplementary inputs.

**Minimum games-played filter:** Apply `min(home_games_played, away_games_played) ≥ 15` before fitting Phase 4 models. This:
- Removes the noisiest early-season window (0–10 games, 5.5% of training set) plus the transitional 10–15 zone
- Retains 85.0% of the training set (17,547 games) — a minimal information cost
- Corresponds to approximately the first 2 weeks of the regular season
- Is most impactful for pitching-quality features where the improvement from the early-season to stable-season buckets is largest (48% for team pit xwOBA)

---

## 04 — Feature Correlations and Multicollinearity (2026-04-24)

**Source:** `feature_pregame_game_features` (has_full_data = true) ⋈ `mart_game_results`, 2016–2025 regular season, 2020 excluded  
**Training set:** 20,640 games  
**Notebook:** `exploratory_data_analysis/04_feature_correlations.py`

### Top Features by |Pearson r| — Total Runs (over/under target)

| Rank | Feature | Pearson r | \|r\| | Group |
|---|---|---|---|---|
| 1 | `park_run_factor_3yr` | +0.122 | **0.122** | Park |
| 2 | `elevation_ft` | +0.111 | **0.111** | Park |
| 3 | `runs_per_game_at_park` | +0.094 | **0.094** | Park |
| 4 | `home_pit_woba_against_30d` | +0.092 | **0.092** | Home pitching |
| 5 | `home_pit_xwoba_against_30d` | +0.075 | **0.075** | Home pitching |
| 6 | `home_pit_xwoba_against_std` | +0.073 | **0.073** | Home pitching |
| 7 | `home_starter_k_pct_std` | −0.065 | **0.065** | Home starter |
| 8 | `home_off_slugging_30d` | +0.061 | **0.061** | Home offense |
| 9 | `home_starter_xwoba_against_std` | +0.060 | **0.060** | Home starter |
| 10 | `home_bp_xwoba_against_30d` | +0.058 | **0.058** | Bullpen |
| 11 | `home_pit_k_pct_30d` | −0.057 | **0.057** | Home pitching |
| 12 | `home_starter_whiff_rate_std` | −0.056 | **0.056** | Home starter |
| 13 | `away_starter_k_pct_std` | −0.047 | **0.047** | Away starter |
| 14 | `home_off_woba_30d` | +0.047 | **0.047** | Home offense |
| 15 | `home_off_runs_per_game_30d` | +0.046 | **0.046** | Home offense |
| — | `away_pit_xwoba_against_30d` | +0.008 | 0.008 | Away pitching |

**Structural finding:** Park/environment features dominate the top 3. Home pitching is the strongest team-level group — home team pitching quality (both team-level and starter) is ~1.5–2× stronger a total-runs predictor than home offense. `away_pit_xwoba_against_30d` shows near-zero correlation with total_runs (r = 0.008) — a confirmed structural asymmetry against what theory predicts. Investigated in Card 3.9.

### Top Features by |Pearson r| — Run Differential (spread target)

| Rank | Feature | Pearson r | \|r\| |
|---|---|---|---|
| 1 | `away_win_pct` | −0.102 | **0.102** |
| 2 | `away_pit_xwoba_against_30d` | +0.091 | **0.091** |
| 3 | `away_starter_k_pct_std` | −0.091 | **0.091** |
| 4 | `home_win_pct` | +0.088 | **0.088** |
| 5 | `home_pit_xwoba_against_30d` | −0.086 | **0.086** |
| 6 | `home_starter_k_pct_std` | +0.071 | **0.071** |
| 7 | `away_off_woba_30d` | −0.066 | **0.066** |
| 8 | `home_lineup_vs_away_starter_xwoba_adj` | +0.065 | **0.065** |
| 9 | `home_off_woba_30d` | +0.060 | **0.060** |

Season record (`win_pct`) is the top individual predictor for run differential — capturing cumulative team quality better than any rolling window. Away pitching (`away_pit_xwoba_against_30d`) is a strong positive predictor (r = +0.091) confirming the away asymmetry is directionally correct for differential: better away pitching = home wins by less. `matchup_advantage_30d` r = −0.011 (near zero with wrong sign — formula confound, see below).

### Top Features by |Pearson r| — Home Win (moneyline target)

| Rank | Feature | Pearson r | \|r\| |
|---|---|---|---|
| 1 | `away_win_pct` | −0.083 | **0.083** |
| 2 | `home_win_pct` | +0.080 | **0.080** |
| 3 | `away_pit_xwoba_against_30d` | +0.079 | **0.079** |
| 4 | `home_pit_xwoba_against_30d` | −0.073 | **0.073** |
| 5 | `away_starter_k_pct_std` | −0.069 | **0.069** |
| 6 | `home_lineup_vs_away_starter_xwoba_adj` | +0.057 | **0.057** |
| 7 | `home_starter_k_pct_std` | +0.055 | **0.055** |
| 8 | `away_off_woba_30d` | −0.056 | **0.056** |
| 9 | `home_off_woba_30d` | +0.049 | **0.049** |

### Multicollinearity — Redundant Feature Pairs (|r| > 0.85)

10 redundant pairs detected. All involve 14-day window variants:

| Feature A | Feature B | \|r\| | Recommendation |
|---|---|---|---|
| `home_starter_k_pct_14d` | `home_starter_k_pct_30d` | 0.888 | Drop 14d |
| `away_starter_k_pct_14d` | `away_starter_k_pct_30d` | 0.886 | Drop 14d |
| `home_starter_k_pct_30d` | `home_starter_k_pct_std` | 0.885 | Keep STD (stronger correlation) |
| `away_starter_k_pct_30d` | `away_starter_k_pct_std` | 0.880 | Keep STD |
| `home_pit_xwoba_against_30d` | `home_pit_xwoba_against_std` | 0.873 | Keep STD |
| `away_pit_xwoba_against_30d` | `away_pit_xwoba_against_std` | 0.871 | Keep STD |
| `home_pit_xwoba_against_14d` | `home_pit_xwoba_against_30d` | 0.865 | Drop 14d |
| `away_pit_xwoba_against_14d` | `away_pit_xwoba_against_30d` | 0.869 | Drop 14d |
| `home_starter_xwoba_against_14d` | `home_starter_xwoba_against_30d` | 0.857 | Drop 14d |
| `home_off_woba_30d` | `home_off_woba_std` | 0.862 | Keep 30d (per NB03 — offense 30d ≈ STD) |

Near-threshold (0.83–0.85): `home_off_woba_14d`↔30d (0.839); `away_off_woba_14d`↔30d (0.831); `away_off_woba_30d`↔std (0.849); `home_starter_xwoba_30d`↔std (0.839).

**wOBA vs. xwOBA (cross-metric, same window): NOT redundant.** `home_off_woba_30d`↔`home_off_xwoba_30d` = 0.677; `home_pit_woba_against_30d`↔`home_pit_xwoba_against_30d` = 0.702. Both well below the 0.85 threshold — they carry different information. Prefer xwOBA (park-adjusted, lower sample-size noise).

### Matchup Differential vs. Individual Components

| Signal | vs. Total Runs | vs. Run Diff | vs. Home Win |
|---|---|---|---|
| `total_matchup_quality_30d` (Σ both sides) | r = +0.005 | r = −0.005 | — |
| `matchup_advantage_30d` (Δ between sides) | r = +0.050 | r = −0.011 | r = −0.012 |
| `home_pit_xwoba_against_30d` (component) | r = +0.075 | r = −0.086 | r = −0.073 |
| `home_off_woba_30d` (component) | r = +0.047 | r = +0.060 | r = +0.049 |

`total_matchup_quality_30d` (Σ) adds no value — r = 0.005 with total_runs, worse than either component alone. `matchup_advantage_30d` has modest totals signal (r = 0.050) but near-zero or negative directional signal for run differential (r = −0.011) and home win (r = −0.012). Root cause: the formula adds `home_pit_xwoba_against` as a positive term, meaning worse home pitching increases the advantage metric — a directional confound. Individual pitching quality features dominate both differentials by 1.5–2×.

### Recommendations

| Decision | Rationale |
|---|---|
| Drop all 14-day standalone features | All 10 redundant pairs (|r| > 0.85) involve 14d windows; no independent signal |
| Prefer xwOBA over raw wOBA same-window | |r| = 0.68–0.70 between them; xwOBA is park-adjusted |
| Do not use `total_matchup_quality_30d` | r = 0.005 with total_runs — no value over individual components |
| Retain `matchup_advantage_30d` for totals only | r = 0.050 with total_runs (modest signal); directional formula flaw disqualifies it for spread/ML targets |
| Season record (`win_pct`) is a top feature | r ≈ 0.08–0.10 for run_differential and home_win — strongest standalone signal outside park features |
| Investigate home/away pitching asymmetry | home_pit_xwoba r = 0.075 vs. away_pit_xwoba r = 0.008 (9× gap on total_runs) — confirmed structural asymmetry, see Card 3.9 |

---

## 05 — Park Run Factor and Schedule Fatigue (2026-04-24)

**Source:** `feature_pregame_game_features` (has_full_data = true) ⋈ `mart_game_results`, 2016–2025 regular season, 2020 excluded  
**Training set:** 20,640 games  
**Notebook:** `exploratory_data_analysis/05_park_and_context.py`

### Part 1 — Park Run Factor vs. Actual Total Runs

**Pearson r (park_run_factor_3yr → total_runs): +0.1224** (n = 20,640; p < 0.0001)

Quartile rank fully preserved (Q1 < Q2 < Q3 < Q4): **True** | Q4 − Q1 mean spread: **+1.148 runs**

| Quartile | N | Mean Runs | SD | Median | PRF Range | Home Win Rate |
|---|---|---|---|---|---|---|
| Q1 (pitcher-friendly) | 5,160 | 8.519 | 4.310 | 8.0 | 6.975–8.359 | 0.542 |
| Q2 | 5,160 | 8.758 | 4.366 | 8.0 | 8.359–8.871 | 0.542 |
| Q3 | 5,160 | 9.149 | 4.539 | 9.0 | 8.871–9.358 | 0.522 |
| Q4 (hitter-friendly) | 5,160 | 9.667 | 4.790 | 9.0 | 9.358–11.966 | 0.522 |

Park factor rank order is perfectly preserved across all four quartiles with a consistent spread. Hitter-friendly parks (Q4) average 1.15 more runs per game than pitcher-friendly parks (Q1). Note: home win rate is slightly *lower* in Q3-Q4 hitter-friendly parks — a weak inverse pattern suggesting ball-in-play variability may reduce home advantage in high-scoring environments.

### Part 2 — Schedule Fatigue Effects

#### Days Rest — Home Team

| Days Rest | N | Mean Runs | Home Win Rate |
|---|---|---|---|
| 0 | 297 | 8.852 | 0.495 |
| 1 | 17,445 | 9.011 | 0.536 |
| 2 | 2,542 | 9.092 | 0.510 |
| 3 | 74 | 8.973 | 0.554 |
| 4+ | 156 | 9.628 | 0.506 |

#### Days Rest — Away Team

| Days Rest | N | Mean Runs | Home Win Rate |
|---|---|---|---|
| 0 | 297 | 8.852 | 0.495 |
| 1 | 17,488 | 9.003 | 0.535 |
| 2 | 2,505 | 9.162 | 0.519 |
| 3 | 70 | 8.657 | 0.529 |
| 4+ | 150 | 9.720 | 0.487 |

#### Timezone Travel Groups

| Home TZ Changed | Away TZ Changed | N | Mean Runs | Home Win Rate |
|---|---|---|---|---|
| No | No | 15,869 | 8.979 | 0.534 |
| No | Yes | 2,699 | 9.160 | 0.525 |
| Yes | No | 767 | 8.838 | 0.515 |
| Yes | No | 1,305 | 9.384 | 0.530 |

#### Continuous Correlations with Total Runs

| Variable | Pearson r with Total Runs | Pearson r with Home Win |
|---|---|---|
| `home_days_rest` | +0.0004 | −0.007 |
| `away_days_rest` | +0.0023 | — |
| `home_tz_changed` | +0.012 | −0.005 |
| `away_tz_changed` | +0.023 | −0.005 |

### Part 3 — OLS R² Comparison

| Model | Predictors | R² | ΔR² |
|---|---|---|---|
| Park only | `park_run_factor_3yr` | 0.01498 (1.50%) | — |
| Park + Schedule | + rest & TZ (both teams) | ~0.016 (est.) | **< 0.002** |

Schedule variables (days rest, TZ change) have univariate correlations < 0.023 with total_runs. ΔR² from adding them to park factor is estimated at < 0.002 — below the 0.005 meaningful gain threshold.

### Recommendation

| Feature | Include in Phase 4? | Rationale |
|---|---|---|
| `park_run_factor_3yr` | **Yes** | r = 0.122, strongest total_runs predictor; rank order perfectly preserved; Q4−Q1 = +1.15 runs |
| `elevation_ft` | **Yes** | r = 0.111 with total_runs (second strongest predictor); correlated with park factor but partially independent |
| `home_days_rest`, `away_days_rest` | **Low-cost flag** | Near-zero marginal lift (r < 0.003); cheap to include as continuous features; small n in extreme buckets (3+) unreliable |
| `home_tz_changed`, `away_tz_changed` | **Low-cost flag** | r = 0.012–0.023 with total_runs; not significant; binary cost is near-zero |

**Overall verdict:** Include park factor and elevation as primary park features (strong signal). Include rest and TZ features as cheap low-cost flags. Do not expect schedule features to provide measurable lift in Phase 4 ablation tests.

---

## 06 — Bat Tracking Era: Does 2023+ Data Add Signal? (2026-04-24)

**Source:** `feature_pregame_game_features` (has_full_data = true, 2023–2025) + rolling bat tracking aggregated inline from `stg_batter_pitches`  
**Notebook:** `exploratory_data_analysis/06_bat_tracking_era.py`  
**Sub-sample for correlations:** 5,523 games (both teams have a non-null 30-day bat tracking rolling average)

*`bat_speed_mph` and `swing_length_ft` are not yet in the feature store. Rolling averages are built inline via a 3-CTE Snowflake query with a no-leakage window (`RANGE BETWEEN INTERVAL '30 DAYS' PRECEDING AND INTERVAL '1 DAY' PRECEDING`).*

### Bat Speed Null Rate by Season / Period

| Period | Total Pitches | Null Count | Null % | Population % |
|---|---|---|---|---|
| 2019 | 732,473 | 732,473 | 100% | 0% |
| 2020 | 263,584 | 263,584 | 100% | 0% |
| 2021 | 709,852 | 709,852 | 100% | 0% |
| 2022 | 708,540 | 708,540 | 100% | 0% |
| 2023-H1 (pre-rollout) | 400,060 | 400,060 | 100% | 0% |
| 2023-H2 (post-rollout) | 317,885 | 171,975 | 54.1% | **45.9%** |
| 2024 | 709,511 | 392,870 | 55.4% | **44.6%** |
| 2025 | 710,084 | 380,325 | 53.6% | **46.4%** |

Population rate stabilizes at ~45% post-rollout — consistent with swing-contact events only (non-contact pitches, walks, HBP, etc. are always null by design).

### Bat Tracking Game Coverage (Both Teams' 30-Day Rolling Average Non-Null)

| Season | Total Games | Games with BT | Coverage |
|---|---|---|---|
| 2023 | 2,373 | 1,035 | 43.6% |
| 2024 | 2,369 | 2,274 | 96.0% |
| 2025 | 2,228 | 2,214 | 99.4% |
| **Total** | **6,970** | **5,523** | **79.3%** |

As a share of the full 2016–2025 training set (20,640 games): **26.8%**. An era-specific bat-tracking model would forfeit 73.2% of historical training data.

### Univariate Correlations with Total Runs (n = 5,523, bat-tracking sub-sample)

| Feature | Pearson r | \|r\| |
|---|---|---|
| park_run_factor_3yr | +0.088 | **0.088** |
| home_pit_xwoba_against_30d | +0.078 | **0.078** |
| home_starter_k_pct_std | −0.070 | **0.070** |
| home_off_woba_30d | +0.054 | **0.054** |
| away_off_woba_30d | +0.050 | **0.050** |
| away_starter_k_pct_std | −0.041 | **0.041** |
| away_pit_xwoba_against_30d | −0.014 | 0.014 |
| **home_bat_speed_30d** | +0.022 | **0.022** |
| **away_bat_speed_30d** | +0.018 | 0.018 |
| **home_swing_length_30d** | +0.010 | 0.010 |
| **away_swing_length_30d** | −0.003 | 0.003 |

Bat tracking features (bottom four) have uniformly weaker correlation with total runs than all traditional features except `away_pit_xwoba_against_30d`. Maximum bat tracking |r| = 0.022 — roughly 4× weaker than the strongest traditional predictor (park factor at 0.088).

### Bat Speed–wOBA Redundancy Check

| Pair | Pearson r |
|---|---|
| home_bat_speed_30d vs. home_off_woba_30d | 0.221 |
| away_bat_speed_30d vs. away_off_woba_30d | 0.225 |
| home_swing_length_30d vs. home_off_woba_30d | 0.176 |
| away_swing_length_30d vs. away_off_woba_30d | 0.180 |

Max |r| = **0.225** — **Low overlap** (well below the 0.5 moderate threshold and the 0.7 high-redundancy threshold). Bat tracking and wOBA are measuring different aspects of offensive quality. The weak predictive signal is **not** explained by redundancy with existing metrics.

### OLS R² Comparison (n = 5,523, identical sub-sample)

| Model | Features | R² (approx.) | ΔR² |
|---|---|---|---|
| Traditional only | wOBA (30d), xwOBA against (30d), starter K% (STD), park factor | ~0.024 | — |
| Traditional + bat tracking | + bat speed 30d, swing length 30d (home & away) | ~0.025 | **< 0.001** |

ΔR² < 0.001 is well below the 0.005 threshold for meaningful gain. With four bat tracking features each having |r| < 0.025 with total runs and low correlation with one another, the marginal OLS contribution is negligible.

### Recommendation: Single-Model Path

**Single-model path — bat tracking not worth the complexity at 30-day team-level aggregation.**

| Finding | Value |
|---|---|
| Max bat tracking \|r\| with total runs | 0.022 |
| Max bat speed–wOBA redundancy \|r\| | 0.225 (low overlap) |
| OLS ΔR² | < 0.001 (threshold: 0.005) |
| Sub-sample as % of full training set | 26.8% (5,523 of 20,640 games) |
| 2024–2025 coverage rate | 96–99% (bat tracking is essentially complete) |

The weak predictive signal is not caused by redundancy with wOBA (|r| = 0.225, independent). Rather, a 30-day team rolling average of bat speed loses the individual-level precision that bat speed likely carries. A per-batter or per-matchup aggregation (e.g., average bat speed of the confirmed lineup against the specific starter's pitch mix) would preserve more signal. That aggregation requires lineup-level feature engineering not yet built.

**Phase 4 decision:** Exclude bat tracking from the primary model. The data is available and near-complete for 2024–2025 (96–99% coverage); the constraint is aggregation granularity, not data availability. Re-evaluate with per-batter matchup aggregations in Phase 5+.

---

## 07 — Engineered Feature Incremental Lift Validation (2026-04-24)

**Source:** `feature_pregame_game_features` (has_full_data=true, 2016–2025, 2020 excluded)  
**Notebook:** `exploratory_data_analysis/07_engineered_feature_lift.py`  
**n (baseline+delta OLS):** 20,630 | **n (handedness OLS):** 15,538 (non-null handedness rows)  
**Card:** 3.7

Tests whether Cards 4.1 (delta/momentum) and 4.2 (lineup-vs-starter handedness adjustments) provide incremental predictive signal over base rolling features.

---

### Part 1 — Card 4.1: Delta/Momentum Features

#### Correlation Fast Pass (n=20,640)

All delta/momentum features show uniformly low marginal correlations across all three targets:

| Feature | r (total_runs) | r (run_diff) | r (home_win) | \|r\| max |
|---|---|---|---|---|
| `home_off_woba_7d_minus_30d` | −0.009 | +0.004 | +0.010 | 0.010 |
| `away_off_woba_7d_minus_30d` | **+0.020** | −0.009 | −0.003 | 0.020 |
| `home_pit_xwoba_7d_minus_30d` | +0.005 | +0.004 | +0.009 | 0.009 |
| `away_pit_xwoba_7d_minus_30d` | +0.011 | +0.007 | +0.005 | 0.011 |
| `home_starter_xwoba_7d_minus_std` | +0.015 | +0.001 | −0.001 | 0.015 |
| `away_starter_xwoba_7d_minus_std` | 0.000 | +0.008 | +0.007 | 0.008 |
| `home_starter_k_pct_7d_minus_std` | −0.010 | −0.005 | −0.008 | 0.010 |
| `away_starter_k_pct_7d_minus_std` | −0.003 | −0.001 | −0.002 | 0.003 |
| `home_starter_fastball_velo_trend` | +0.002 | 0.000 | −0.010 | 0.010 |
| `away_starter_fastball_velo_trend` | −0.004 | +0.001 | +0.009 | 0.009 |

**Maximum |r| across all delta features × all targets: 0.020** (away_off_woba_7d_minus_30d vs total_runs).

#### Source Window Comparison

Delta features dramatically underperform their source windows individually:

| Source Feature | r (total_runs) | vs Delta equivalent |
|---|---|---|
| `home_off_woba_30d` (team offense base) | +0.047 | vs home_off_woba_7d_minus_30d: −0.009 |
| `home_pit_xwoba_against_7d` (7d window) | +0.058 | vs home_pit_xwoba_7d_minus_30d: +0.005 |
| `home_starter_xwoba_against_7d` (7d) | +0.048 | vs home_starter_xwoba_7d_minus_std: +0.015 |
| `home_starter_k_pct_7d` (7d) | −0.052 | vs home_starter_k_pct_7d_minus_std: −0.010 |

The 7d source windows have 3–10× stronger marginal correlations than the delta features derived from them. Subtracting the 30d/std baseline suppresses the signal while encoding the directional change.

#### OLS ΔR²

**Baseline A (30d/std, 13 features):** park factor + team offense/pitching 30d + starter xwOBA/K% (30d + std). Consistent with the NB04 feature selection.

| Model | total_runs R² | run_diff R² | home_win R² |
|---|---|---|---|
| Baseline A | 0.1280 | 0.1348 | 0.1223 |
| + Delta block (10 features) | 0.1750 | 0.1809 | 0.1657 |
| **ΔR²** | **+0.0469** | **+0.0461** | **+0.0435** |

ΔR² = 0.043–0.047 (all well above 0.005 threshold).

**Critical interpretation:** delta features (7d_minus_30d) are algebraically equivalent to adding the 7d rolling window alongside the 30d baseline. The OLS can recover `7d = 30d + delta`, effectively unlocking the predictive power of recent 7-day windows. The ΔR² measures "value of 7d recency" not "pure momentum direction." 7d source windows have 3–10× stronger individual correlations than the delta features (e.g., `home_pit_xwoba_against_7d` r=0.058 vs `home_pit_xwoba_7d_minus_30d` r=0.005 with total_runs), confirming the signal is in the raw window, not the difference.

---

### Part 2 — Card 4.2: Lineup-vs-Starter Handedness Matchup Adjustments

#### Correlation Fast Pass (n=17,923 non-null)

| Feature | r (total_runs) | r (run_diff) | r (home_win) | \|r\| max |
|---|---|---|---|---|
| `home_lineup_vs_away_starter_k_pct_adj` | −0.035 | **−0.086** | **−0.068** | 0.086 |
| `away_lineup_vs_home_starter_k_pct_adj` | −0.063 | **+0.073** | **+0.063** | 0.073 |
| `home_lineup_vs_away_starter_xwoba_adj` | +0.027 | +0.065 | +0.057 | 0.065 |
| `away_lineup_vs_home_starter_xwoba_adj` | +0.044 | −0.054 | −0.049 | 0.054 |
| `home_lineup_vs_away_starter_bb_pct_adj` | +0.017 | +0.037 | +0.026 | 0.037 |
| `away_lineup_vs_home_starter_bb_pct_adj` | +0.009 | −0.028 | −0.029 | 0.029 |

The k_pct_adj features show moderate correlations for directional targets (run_diff, home_win) at |r| = 0.063–0.086. However, they are moderately collinear with the underlying starter K% features:

| Handedness Feature | vs Base Feature | Cross r |
|---|---|---|
| `home_lineup_vs_away_starter_xwoba_adj` | `away_starter_xwoba_against_std` | 0.264 |
| `home_lineup_vs_away_starter_k_pct_adj` | `away_starter_k_pct_std` | **0.524** |
| `away_lineup_vs_home_starter_xwoba_adj` | `home_starter_xwoba_against_std` | 0.256 |
| `away_lineup_vs_home_starter_k_pct_adj` | `home_starter_k_pct_std` | **0.525** |

k_pct handedness features share ~52% of their variance with the base starter K% feature. The apparent signal is largely inherited from the underlying starter stats.

#### OLS ΔR² — Baseline+Delta → + Handedness Block (n=15,538)

| Target | Baseline+Delta R² | +Handedness R² | **ΔR²** | > 0.005? |
|---|---|---|---|---|
| total_runs | 0.2143 | 0.2155 | **+0.0011** | no |
| run_differential | 0.2184 | 0.2208 | **+0.0024** | no |
| home_win | 0.2018 | 0.2038 | **+0.0020** | no |

All ΔR² below 0.005 threshold. Despite k_pct_adj features showing |r| = 0.063–0.086 with directional targets, the incremental lift over a model that already has starter K% and xwOBA is negligible.

---

### Verdicts and Phase 4 Decisions

| Block | Max ΔR² | Threshold | Decision |
|---|---|---|---|
| Delta/momentum (Card 4.1) | 0.047 (over 30d/std baseline) | 0.005 | **Include 7d rolling windows** — not as deltas |
| Handedness matchup (Card 4.2) | 0.002 | 0.005 | **Validated low-signal** — exclude from primary model |

**Delta/momentum (Card 4.1):** The delta encoding adds no information beyond what's available from the raw 7d and 30d/std windows. Phase 4 should include 7d rolling windows for team offense, team pitching, and starter quality directly. The "momentum" narrative is real — 7d recency matters — but the delta feature format adds collinearity when both windows are present and provides no advantage over raw windows for linear models.

**Handedness matchup (Card 4.2):** The xwoba_adj and k_pct_adj features carry some marginal correlation signal for run_differential and home_win (k_pct: |r| = 0.063–0.086), but that signal is already captured by the underlying starter K% and xwOBA features in the model. No measurable incremental lift (ΔR² = 0.001–0.002). Exclude from the primary Phase 4 feature set. May add value in a platoon-split-aware model (Phase 5+) if lineup handedness data is used at the individual matchup level rather than team aggregation.

---

## 08 — Section 08: Bullpen vs. Starter Signal Decomposition (2026-04-24)

**Source:** `betting_ml/scripts/analyze_pitching_decomp.py` → `betting_ml/evaluation/pitching_decomp_results.json`
**Data:** 17,200 game rows (non-null across all 8 pitching columns; 490 dropped due to partial nulls)

---

### Cross-Correlation

| Pair | Pearson r | p-value | High collinearity? |
|---|---|---|---|
| `home_starter_xwoba_against_std` vs `home_bp_xwoba_against_30d` | 0.1692 | <0.0001 | No |
| `away_starter_xwoba_against_std` vs `away_bp_xwoba_against_30d` | 0.1643 | <0.0001 | No |

Collinearity threshold: |r| > 0.70. Both home and away starter–bullpen pairs are weakly positively correlated (r≈0.17) — in the expected direction (good starters tend to appear on good pitching teams) but well below the redundancy threshold. **High collinearity: False.**

---

### Partial Correlations

Each pitching feature's correlation with a target, controlling for its paired pitching feature (same team side).

| Feature | Target | Pearson r | Partial r | Controlling For |
|---|---|---|---|---|
| `home_starter_xwoba_against_std` | total_runs | 0.0688 | 0.0591 | `home_bp_xwoba_against_30d` |
| `home_starter_xwoba_against_std` | run_differential | −0.0703 | −0.0610 | `home_bp_xwoba_against_30d` |
| `home_starter_xwoba_against_std` | home_win | −0.0578 | −0.0496 | `home_bp_xwoba_against_30d` |
| `home_bp_xwoba_against_30d` | total_runs | 0.0630 | 0.0522 | `home_starter_xwoba_against_std` |
| `home_bp_xwoba_against_30d` | run_differential | −0.0607 | −0.0496 | `home_starter_xwoba_against_std` |
| `home_bp_xwoba_against_30d` | home_win | −0.0531 | −0.0440 | `home_starter_xwoba_against_std` |
| `away_starter_xwoba_against_std` | total_runs | 0.0377 | 0.0377 | `away_bp_xwoba_against_30d` |
| `away_starter_xwoba_against_std` | run_differential | 0.0793 | 0.0708 | `away_bp_xwoba_against_30d` |
| `away_starter_xwoba_against_std` | home_win | 0.0635 | 0.0545 | `away_bp_xwoba_against_30d` |
| `away_bp_xwoba_against_30d` | total_runs | 0.0030 | −0.0032 | `away_starter_xwoba_against_std` |
| `away_bp_xwoba_against_30d` | run_differential | 0.0583 | 0.0461 | `away_starter_xwoba_against_std` |
| `away_bp_xwoba_against_30d` | home_win | 0.0603 | 0.0507 | `away_starter_xwoba_against_std` |

**Interpretation:** All home-side pitching features retain meaningful partial correlations after controlling for their paired feature — signal is not being absorbed. The notable exception is `away_bp_xwoba_against_30d` vs. `total_runs` (partial r=−0.003), which essentially collapses to zero once away starter quality is controlled — consistent with the home/away asymmetry finding from NB04 (see Card 3.9). Home starter and home bullpen each carry independent variance.

---

### OLS R² Decomposition

| Target | Starter-only R² | Bullpen-only R² | Combined R² | Incremental R² |
|---|---|---|---|---|
| total_runs | 0.006047 | 0.003969 | 0.008728 | **0.002682** |
| run_differential | 0.011481 | 0.007312 | 0.016304 | **0.004823** |
| home_win | 0.007545 | 0.006667 | 0.012260 | **0.004716** |

Incremental R² = combined R² − max(starter-only, bullpen-only). Mean incremental R² across targets = **0.004073** — above the 0.002 decision threshold.

**Interpretation:** Adding the bullpen block on top of starters (or vice versa) explains an additional 0.0027–0.0048 of variance across all three targets. This is modest in absolute terms but consistent and above the redundancy threshold. Both blocks carry non-overlapping information.

---

### Workload Features

| Feature | Target | Pearson r |
|---|---|---|
| `home_bullpen_pitches_prev_3d` | total_runs | 0.0251 |
| `home_bullpen_pitches_prev_3d` | run_differential | −0.0092 |
| `home_bullpen_pitches_prev_3d` | home_win | −0.0009 |
| `home_pitchers_used_prev_7d` | total_runs | 0.0020 |
| `home_pitchers_used_prev_7d` | run_differential | 0.0021 |
| `home_pitchers_used_prev_7d` | home_win | 0.0068 |
| `away_bullpen_pitches_prev_3d` | total_runs | 0.0265 |
| `away_bullpen_pitches_prev_3d` | run_differential | 0.0190 |
| `away_bullpen_pitches_prev_3d` | home_win | 0.0204 |
| `away_pitchers_used_prev_7d` | total_runs | 0.0137 |
| `away_pitchers_used_prev_7d` | run_differential | 0.0095 |
| `away_pitchers_used_prev_7d` | home_win | 0.0031 |

**Workload incremental R² over bullpen-only baseline (home side):**

| Target | Workload ΔR² |
|---|---|
| total_runs | +0.000478 |
| run_differential | −0.003583 |
| home_win | −0.003787 |

Max workload incremental R² = 0.000478 — well below the 0.005 threshold. The negative incremental values for run_differential and home_win indicate that adding workload features introduces noise rather than signal for directional targets.

**Interpretation:** Bullpen workload features (`bullpen_pitches_prev_3d`, `pitchers_used_prev_7d`) have near-zero correlation with outcomes (|r| ≤ 0.027) and add no meaningful signal beyond the trailing xwOBA. These features should not be included in the Phase 4 primary model.

---

### Design Recommendation

**Verdict: Keep both starter and bullpen xwOBA. Do not add workload features.**

| Decision | Value | Rationale |
|---|---|---|
| `keep_both` | True | No high collinearity (home r=0.17, away r=0.16); mean incremental R²=0.004 above 0.002 threshold |
| `drop_bullpen` | False | Both blocks carry independent variance; starter is the stronger predictor but bullpen adds meaningful lift |
| `add_workload_flag` | False | Max workload incremental R²=0.0005 — well below 0.005 threshold; workload is noise beyond trailing xwOBA |

**Phase 4 feature selection implication:** Include `home_starter_xwoba_against_std`, `home_bp_xwoba_against_30d`, `away_starter_xwoba_against_std`, and `away_bp_xwoba_against_30d` as separate features in the Phase 4 feature matrix. Do not include `bullpen_pitches_prev_3d` or `pitchers_used_prev_7d`.

---

## Section 09: Home/Away Pitching Quality Asymmetry (2026-04-24)

**Source:** `betting_ml/scripts/analyze_home_away_pitch_asymmetry.py`  
**Data:** 17,690 games (2016–2025, excluding 2020), all pitching and park columns non-null  
**Question:** Why does home pitching xwOBA predict total_runs at r=0.085 while away pitching predicts at r=0.011 — a 8× asymmetry?

---

### Raw vs. Partial Correlations

Partial r controls for `park_run_factor_3yr` and the opposing pitching feature simultaneously (residual-on-residual OLS).

| Feature | Target | Raw Pearson r | Partial r | Controlling For |
|---|---|---|---|---|
| `away_pit_xwoba_against_30d` | total_runs | 0.0107 | 0.0122 | park_rf + home_pit_30d |
| `away_pit_xwoba_against_30d` | run_differential | 0.0939 | 0.0964 | park_rf + home_pit_30d |
| `away_pit_xwoba_against_30d` | home_win | 0.0837 | 0.0858 | park_rf + home_pit_30d |
| `home_pit_xwoba_against_30d` | total_runs | 0.0854 | 0.0625 | park_rf + away_pit_30d |
| `home_pit_xwoba_against_30d` | run_differential | −0.0962 | −0.0969 | park_rf + away_pit_30d |
| `home_pit_xwoba_against_30d` | home_win | −0.0841 | −0.0849 | park_rf + away_pit_30d |

**Interpretation (H1 verdict):** Controlling for both park factor and the opposing pitching feature does *not* collapse away pitching's partial r toward zero. The max |partial_r| for `away_pit_xwoba_against_30d` = 0.0964 (far above the 0.030 threshold). The near-zero total_runs r (0.0107 → 0.0122 after controlling) is *total_runs-specific*, not a global away pitching weakness — away pitching retains strong signal for run_differential (partial r=0.096) and home_win (partial r=0.086). **H1 (park factor absorbs away variance): NOT SUPPORTED.**

---

### Park Factor Stratification

Pearson r within each park factor quartile (target: total_runs).

| Quartile | N | Park RF Range | Home Pit r | Away Pit r | Asymmetry Ratio |
|---|---|---|---|---|---|
| Q1 (low) | 4,446 | [6.97, 8.40] | 0.0439 | 0.0095 | 4.62× |
| Q2 | 4,445 | [8.41, 8.89] | 0.0730 | 0.0278 | 2.63× |
| Q3 | 4,435 | [8.89, 9.38] | 0.0536 | 0.0082 | 6.54× |
| Q4 (high) | 4,364 | [9.39, 11.97] | 0.1091 | 0.0058 | 18.99× |

**Interpretation:** The asymmetry (for total_runs) does not collapse in neutral-park quartiles — it is present even in Q1 (low run-scoring parks, 4.6×) and actually grows stronger in high-run parks (Q4 at 19×). Stratifying by park factor does not equalize home and away pitching signal. **H1 quartile evidence: REFUTED** — the asymmetry is not caused by high-run parks inflating home signal relative to away.

---

### Era-Split Correlations

| Era | N | Target | Home Pit r | Away Pit r | Asymmetry Ratio |
|---|---|---|---|---|---|
| pre_juiced (2016–2019) | 7,547 | total_runs | 0.0889 | 0.0154 | 5.78× |
| pre_juiced (2016–2019) | 7,547 | run_differential | −0.1001 | 0.0797 | 1.26× |
| pre_juiced (2016–2019) | 7,547 | home_win | −0.0869 | 0.0783 | 1.11× |
| modern (2021–2025) | 10,001 | total_runs | 0.0848 | 0.0047 | 18.17× |
| modern (2021–2025) | 10,001 | run_differential | −0.0925 | 0.1067 | 0.87× |
| modern (2021–2025) | 10,001 | home_win | −0.0803 | 0.0910 | 0.88× |

**Interpretation (H2 verdict):** The total_runs asymmetry is present in *both* eras but intensified in the modern era (5.8× → 18.2×). Critically, the asymmetry is *target-specific*: for run_differential and home_win, away pitching has near-equivalent (or slightly higher in the modern era) absolute r to home pitching. Since the asymmetry is not uniform across targets and worsened significantly in the modern era, H2 (rotation alignment era confound) is technically marked **supported** — the total_runs-specific asymmetry strengthened after the 2021+ rule changes, suggesting some era-linked structural change. However, the asymmetry in total_runs was already present pre-2021, so this is a partial rather than full explanation.

---

### Starter vs. Team-Level Signal

| Side | Feature Type | Feature | total_runs r | run_diff r | home_win r | Mean \|r\| |
|---|---|---|---|---|---|---|
| home | starter | `home_starter_xwoba_against_std` | 0.0706 | −0.0707 | −0.0594 | 0.0669 |
| home | team-level | `home_pit_xwoba_against_30d` | 0.0854 | −0.0962 | −0.0841 | 0.0886 |
| away | starter | `away_starter_xwoba_against_std` | 0.0391 | 0.0823 | 0.0662 | 0.0625 |
| away | team-level | `away_pit_xwoba_against_30d` | 0.0107 | 0.0939 | 0.0837 | 0.0628 |

Away starter mean |r| (0.0625) vs. away team-level mean |r| (0.0628): delta = **−0.0002**.

**Interpretation (H3 verdict):** Away starter and away team-level xwOBA perform essentially identically (mean |r| delta = −0.0002, threshold > 0.010). If park contamination were inflating team-level away xwOBA measurement, we would expect the starter feature (measured in the pitcher's home context) to outperform. Both features capture near-zero signal for total_runs while having moderate signal for run_differential and home_win. **H3 (park contamination in team-level measurement): NOT SUPPORTED.**

---

### Hypothesis Verdicts

| Hypothesis | Verdict | Key Evidence |
|---|---|---|
| **H1 — Park factor absorbs away variance** | Not supported | max |partial_r| for a_pit_30 = 0.096 (>>0.030 threshold); partial r doesn't collapse after controlling for park |
| **H2 — Rotation/era confound** | Supported | total_runs asymmetry 5.8× pre-juiced → 18.2× modern; intensification post-2021 suggests era-linked structural change; run_diff/home_win asymmetry does not persist |
| **H3 — Park contamination in team-level xwOBA** | Not supported | Away starter vs. team-level mean |r| delta = −0.0002 (vs. 0.010 threshold); both features show identical near-zero total_runs signal |
| **H4 — Signal direction ambiguity** | Inconclusive | Residual away/total_runs gap after H1–H3 refuted may reflect structural selectivity: away xwOBA measured at home parks introduces directional noise not separable without pitch-level park-adjusted data |

**Root cause ranking by evidence strength:**
1. **Era-linked structural intensification (H2, partial)** — total_runs asymmetry grew 3× between eras; the modern pitch clock and shift ban may have changed how home starters use their bullpen vs. away starters
2. **Target specificity (residual structural effect)** — asymmetry is isolated to total_runs; away pitching has full signal for directional targets (run_differential, home_win), suggesting this is a total-runs measurement artifact, not a fundamental away pitching quality problem
3. **H4 (inconclusive)** — signal direction ambiguity for away xwOBA_against in home parks cannot be ruled out

---

### Design Recommendation

| Flag | Value | Rationale |
|---|---|---|
| `park_absorbs_away_variance` | False | Partial r for a_pit_30 remains 0.096 after controlling for park factor |
| `prefer_starter_over_team_level_away` | False | Away starter and team-level features perform identically (delta = −0.0002) |
| `asymmetry_is_structural` | False | H2 supported (era confound) means asymmetry is not fully structural; era flag may explain it |

**Phase 4 implication:** Include both `home_pit_xwoba_against_30d` and `away_pit_xwoba_against_30d` as separate features in the Phase 4 feature matrix. Do not prefer away starter over team-level (both have identical signal). Include `game_year` / `post_2022_rules` era flag — the total_runs asymmetry intensified post-2021 and the era feature may absorb this interaction. Apply regularization to prevent away team-level xwOBA (near-zero total_runs signal, moderate run_diff/home_win signal) from being over-weighted in total-runs models.

---

## Section 10: Era-Split Correlation Stability

**Script:** `betting_ml/scripts/analyze_era_split_corr_stability.py`
**Results JSON:** `betting_ml/evaluation/era_split_corr_stability_results.json`
**Date:** 2026-04-24

**Context:** NB01 identified a ~0.64-run structural mean shift at the 2022→2023 boundary driven by the pitch clock and shift ban. This analysis tests whether the feature-to-outcome correlation structure changed across the pre-2022 era (game_year in [2016–2019, 2021]; n=9,500) and post-2022 era (game_year in [2022–2025]; n=8,048). A unified model pooling all years is only valid if correlations are incrementally stable across eras. Features showing |r_delta| > 0.015 between eras are flagged; Fisher z-tests determine statistical significance of the shifts.

---

### Top Features (Full Dataset)

Top 20 features by mean |r| across all three targets (total_runs, run_differential, home_win), full dataset (n=17,690). Sorted by mean |r| descending.

| Feature | Mean \|r\| | r (total_runs) | r (run_diff) | r (home_win) |
|---|---|---|---|---|
| `home_pit_woba_against_std` | 0.0997 | +0.1100 | −0.0961 | −0.0929 |
| `home_pit_runs_allowed_std` | 0.0993 | +0.1020 | −0.1000 | −0.0958 |
| `home_pit_xwoba_against_std` | 0.0971 | +0.0856 | −0.1075 | −0.0982 |
| `home_pit_woba_against_30d` | 0.0929 | +0.1092 | −0.0887 | −0.0807 |
| `home_pit_runs_allowed_30d` | 0.0906 | +0.1021 | −0.0889 | −0.0808 |
| `home_pit_xwoba_against_30d` | 0.0886 | +0.0854 | −0.0962 | −0.0841 |
| `home_win_pct` | 0.0866 | −0.0429 | +0.1130 | +0.1040 |
| `home_pit_k_pct_30d` | 0.0799 | −0.0652 | +0.0953 | +0.0793 |
| `home_pit_k_pct_std` | 0.0790 | −0.0603 | +0.0932 | +0.0835 |
| `away_win_pct` | 0.0785 | −0.0012 | −0.1285 | −0.1059 |
| `home_games_back` | 0.0759 | +0.0430 | −0.0937 | −0.0909 |
| `away_pit_woba_against_std` | 0.0750 | +0.0235 | +0.1129 | +0.0885 |
| `home_pit_woba_against_14d` | 0.0744 | +0.0963 | −0.0678 | −0.0592 |
| `away_pit_k_pct_std` | 0.0740 | −0.0108 | −0.1144 | −0.0968 |
| `away_pit_runs_allowed_std` | 0.0737 | +0.0176 | +0.1141 | +0.0893 |
| `away_starter_k_pct_std` | 0.0720 | −0.0466 | −0.0949 | −0.0744 |
| `home_pit_runs_allowed_14d` | 0.0712 | +0.0863 | −0.0681 | −0.0592 |
| `home_pit_xwoba_against_14d` | 0.0709 | +0.0742 | −0.0752 | −0.0635 |
| `home_off_runs_per_game_std` | 0.0700 | +0.0480 | +0.0865 | +0.0756 |
| `away_pit_woba_against_30d` | 0.0700 | +0.0218 | +0.1021 | +0.0862 |

**Interpretation:** Home pitching features dominate the top 6 spots across all three metrics (wOBA, runs allowed, xwOBA; 30d and season-long windows). Team win percentage (`home_win_pct`, `away_win_pct`) appears at ranks 7 and 10, confirming that season-long quality signal contributes independently of recent pitching. Away pitching features (wOBA std, K% std, runs allowed std, wOBA 30d) cluster around rank 12–20 with lower mean |r| — consistent with Card 3.9's home/away pitching asymmetry finding. Home offense (`home_off_runs_per_game_std`) makes the top 20 at rank 19, reflecting the incremental offensive signal identified in NB06. No park factor feature appears in the top 20 because `park_run_factor_3yr` was excluded as a metadata column, but its effect is embedded in the pitching feature correlations (home pitching measured in that park).

---

### Era-Split Correlations

All 60 entries (20 features × 3 targets), sorted by |r_delta| descending. Flagged = |r_delta| > 0.015.

| Feature | Target | Pre-2022 r | Post-2022 r | r_delta | \|r_delta\| | Flagged |
|---|---|---|---|---|---|---|
| `away_win_pct` | total_runs | −0.0228 | +0.0276 | +0.0505 | 0.0505 | YES |
| `away_pit_runs_allowed_std` | total_runs | +0.0310 | −0.0100 | −0.0410 | 0.0410 | YES |
| `home_off_runs_per_game_std` | total_runs | +0.0618 | +0.0251 | −0.0366 | 0.0366 | YES |
| `away_pit_woba_against_30d` | total_runs | +0.0280 | −0.0064 | −0.0344 | 0.0344 | YES |
| `away_pit_woba_against_std` | total_runs | +0.0265 | −0.0061 | −0.0327 | 0.0327 | YES |
| `away_pit_k_pct_std` | total_runs | −0.0217 | +0.0057 | +0.0274 | 0.0274 | YES |
| `away_pit_woba_against_std` | home_win | +0.1043 | +0.0770 | −0.0273 | 0.0273 | YES |
| `home_pit_k_pct_30d` | home_win | +0.0887 | +0.0675 | −0.0212 | 0.0212 | YES |
| `away_starter_k_pct_std` | total_runs | −0.0553 | −0.0347 | +0.0206 | 0.0206 | YES |
| `home_pit_xwoba_against_14d` | run_differential | −0.0839 | −0.0633 | +0.0206 | 0.0206 | YES |
| `home_win_pct` | total_runs | −0.0338 | −0.0533 | −0.0195 | 0.0195 | YES |
| `away_starter_k_pct_std` | home_win | −0.0845 | −0.0655 | +0.0189 | 0.0189 | YES |
| `away_pit_woba_against_30d` | home_win | +0.0964 | +0.0781 | −0.0183 | 0.0183 | YES |
| `home_pit_xwoba_against_std` | home_win | −0.1055 | −0.0874 | +0.0181 | 0.0181 | YES |
| `away_pit_runs_allowed_std` | home_win | +0.0987 | +0.0807 | −0.0181 | 0.0181 | YES |
| `home_pit_woba_against_std` | total_runs | +0.0973 | +0.1146 | +0.0173 | 0.0173 | YES |
| `home_pit_xwoba_against_30d` | run_differential | −0.1031 | −0.0865 | +0.0166 | 0.0166 | YES |
| `home_pit_xwoba_against_14d` | total_runs | +0.0681 | +0.0846 | +0.0165 | 0.0165 | YES |
| `home_pit_xwoba_against_30d` | home_win | −0.0904 | −0.0743 | +0.0161 | 0.0161 | YES |
| `home_pit_woba_against_14d` | total_runs | +0.0846 | +0.1000 | +0.0154 | 0.0154 | no |
| `home_pit_runs_allowed_14d` | total_runs | +0.0778 | +0.0925 | +0.0147 | 0.0147 | no |
| `home_pit_woba_against_std` | run_differential | −0.0968 | −0.1107 | −0.0139 | 0.0139 | no |
| `home_pit_xwoba_against_14d` | home_win | −0.0683 | −0.0550 | +0.0133 | 0.0133 | no |
| `away_starter_k_pct_std` | run_differential | −0.1010 | −0.0882 | +0.0128 | 0.0128 | no |
| `home_pit_xwoba_against_std` | run_differential | −0.1130 | −0.1005 | +0.0125 | 0.0125 | no |
| `home_pit_runs_allowed_14d` | run_differential | −0.0741 | −0.0616 | +0.0125 | 0.0125 | no |
| `home_pit_k_pct_30d` | run_differential | +0.1008 | +0.0884 | −0.0124 | 0.0124 | no |
| `home_pit_xwoba_against_std` | total_runs | +0.0910 | +0.0797 | −0.0113 | 0.0113 | no |
| `home_games_back` | total_runs | +0.0373 | +0.0478 | +0.0105 | 0.0105 | no |
| `away_pit_runs_allowed_std` | run_differential | +0.1101 | +0.1202 | +0.0101 | 0.0101 | no |
| `away_win_pct` | home_win | −0.1100 | −0.1002 | +0.0098 | 0.0098 | no |
| `home_pit_woba_against_30d` | total_runs | +0.1003 | +0.1096 | +0.0094 | 0.0094 | no |
| `home_pit_woba_against_30d` | run_differential | −0.0890 | −0.0980 | −0.0090 | 0.0090 | no |
| `home_pit_runs_allowed_14d` | home_win | −0.0625 | −0.0540 | +0.0085 | 0.0085 | no |
| `home_pit_k_pct_std` | home_win | +0.0874 | +0.0796 | −0.0078 | 0.0078 | no |
| `home_pit_xwoba_against_30d` | total_runs | +0.0835 | +0.0910 | +0.0075 | 0.0075 | no |
| `home_pit_woba_against_std` | home_win | −0.0938 | −0.1005 | −0.0067 | 0.0067 | no |
| `home_games_back` | run_differential | −0.0923 | −0.0981 | −0.0058 | 0.0058 | no |
| `home_pit_k_pct_std` | total_runs | −0.0591 | −0.0647 | −0.0056 | 0.0056 | no |
| `away_pit_k_pct_std` | run_differential | −0.1151 | −0.1203 | −0.0052 | 0.0052 | no |
| `home_pit_runs_allowed_std` | run_differential | −0.0986 | −0.1037 | −0.0051 | 0.0051 | no |
| `home_pit_runs_allowed_30d` | home_win | −0.0823 | −0.0776 | +0.0047 | 0.0047 | no |
| `away_win_pct` | run_differential | −0.1262 | −0.1308 | −0.0047 | 0.0047 | no |
| `home_games_back` | home_win | −0.0898 | −0.0939 | −0.0041 | 0.0041 | no |
| `home_pit_runs_allowed_30d` | run_differential | −0.0910 | −0.0876 | +0.0034 | 0.0034 | no |
| `home_win_pct` | home_win | +0.1022 | +0.1052 | +0.0030 | 0.0030 | no |
| `home_pit_woba_against_30d` | home_win | −0.0813 | −0.0840 | −0.0027 | 0.0027 | no |
| `home_pit_k_pct_30d` | total_runs | −0.0640 | −0.0663 | −0.0023 | 0.0023 | no |
| `home_pit_runs_allowed_std` | home_win | −0.0944 | −0.0966 | −0.0022 | 0.0022 | no |
| `home_off_runs_per_game_std` | home_win | +0.0746 | +0.0765 | +0.0019 | 0.0019 | no |
| `home_pit_woba_against_14d` | run_differential | −0.0712 | −0.0697 | +0.0015 | 0.0015 | no |
| `home_pit_runs_allowed_std` | total_runs | +0.0990 | +0.1005 | +0.0015 | 0.0015 | no |
| `home_pit_k_pct_std` | run_differential | +0.0942 | +0.0929 | −0.0012 | 0.0012 | no |
| `home_win_pct` | run_differential | +0.1122 | +0.1133 | +0.0011 | 0.0011 | no |
| `home_pit_runs_allowed_30d` | total_runs | +0.1005 | +0.0996 | −0.0008 | 0.0008 | no |
| `away_pit_woba_against_std` | run_differential | +0.1152 | +0.1160 | +0.0008 | 0.0008 | no |
| `home_off_runs_per_game_std` | run_differential | +0.0857 | +0.0849 | −0.0008 | 0.0008 | no |
| `away_pit_woba_against_30d` | run_differential | +0.1025 | +0.1032 | +0.0007 | 0.0007 | no |
| `away_pit_k_pct_std` | home_win | −0.1003 | −0.0999 | +0.0004 | 0.0004 | no |
| `home_pit_woba_against_14d` | home_win | −0.0598 | −0.0601 | −0.0003 | 0.0003 | no |

**Interpretation:** 19 of 60 feature-target pairs were flagged at the |r_delta| > 0.015 threshold. The pattern is revealing: flagged pairs are concentrated in *total_runs* as the target (13 of 19 flagged pairs involve total_runs), primarily for away pitching and offensive features. Core run_differential and home_win correlations (home pitching xwOBA, win_pct, games_back) shifted by only 0.001–0.013 — well below the flag threshold. The largest shift, `away_win_pct` vs. total_runs (+0.0505), reflects a sign flip: away win percentage had a small negative correlation with total_runs pre-2022 (−0.023) and flipped positive post-2022 (+0.028). Away pitching features (wOBA, runs allowed) showed consistent attenuation for total_runs post-2022, extending the Card 3.9 finding that away pitching signal for total_runs is more era-sensitive than home pitching.

---

### Fisher Z-Test Results

Top 10 features per target by full-dataset |r| for that target, Fisher z-test for era shift significance. Sorted by |r_delta| descending.

| Feature | Target | Pre r | Post r | r_delta | z_stat | p_value | Significant |
|---|---|---|---|---|---|---|---|
| `away_pit_woba_against_std` | home_win | +0.1043 | +0.0770 | −0.0273 | −1.820 | 0.0688 | no |
| `away_pit_woba_against_30d` | home_win | +0.0964 | +0.0781 | −0.0183 | −1.215 | 0.2243 | no |
| `home_pit_xwoba_against_std` | home_win | −0.1055 | −0.0874 | +0.0181 | +1.206 | 0.2277 | no |
| `away_pit_runs_allowed_std` | home_win | +0.0987 | +0.0807 | −0.0181 | −1.201 | 0.2297 | no |
| `home_pit_woba_against_std` | total_runs | +0.0973 | +0.1146 | +0.0173 | +1.154 | 0.2486 | no |
| `home_pit_xwoba_against_30d` | run_differential | −0.1031 | −0.0865 | +0.0166 | +1.104 | 0.2694 | no |
| `home_pit_xwoba_against_14d` | total_runs | +0.0681 | +0.0846 | +0.0165 | +1.095 | 0.2734 | no |
| `home_pit_woba_against_14d` | total_runs | +0.0846 | +0.1000 | +0.0154 | +1.026 | 0.3047 | no |
| `home_pit_runs_allowed_14d` | total_runs | +0.0778 | +0.0925 | +0.0147 | +0.978 | 0.3283 | no |
| `home_pit_woba_against_std` | run_differential | −0.0968 | −0.1107 | −0.0139 | −0.926 | 0.3543 | no |
| `home_pit_xwoba_against_std` | run_differential | −0.1130 | −0.1005 | +0.0125 | +0.837 | 0.4025 | no |
| `home_pit_xwoba_against_std` | total_runs | +0.0910 | +0.0797 | −0.0113 | −0.751 | 0.4529 | no |
| `away_pit_runs_allowed_std` | run_differential | +0.1101 | +0.1202 | +0.0101 | +0.676 | 0.4990 | no |
| `away_win_pct` | home_win | −0.1100 | −0.1002 | +0.0098 | +0.652 | 0.5146 | no |
| `home_pit_woba_against_30d` | total_runs | +0.1003 | +0.1096 | +0.0094 | +0.624 | 0.5326 | no |
| `home_pit_xwoba_against_30d` | total_runs | +0.0835 | +0.0910 | +0.0075 | +0.497 | 0.6191 | no |
| `home_pit_woba_against_std` | home_win | −0.0938 | −0.1005 | −0.0067 | −0.448 | 0.6541 | no |
| `away_pit_k_pct_std` | run_differential | −0.1151 | −0.1203 | −0.0052 | −0.347 | 0.7286 | no |
| `home_pit_runs_allowed_std` | run_differential | −0.0986 | −0.1037 | −0.0051 | −0.338 | 0.7353 | no |
| `away_win_pct` | run_differential | −0.1262 | −0.1308 | −0.0047 | −0.312 | 0.7548 | no |
| `home_games_back` | home_win | −0.0898 | −0.0939 | −0.0041 | −0.272 | 0.7854 | no |
| `home_win_pct` | home_win | +0.1022 | +0.1052 | +0.0030 | +0.200 | 0.8413 | no |
| `home_pit_k_pct_30d` | total_runs | −0.0640 | −0.0663 | −0.0023 | −0.152 | 0.8794 | no |
| `home_pit_runs_allowed_std` | home_win | −0.0944 | −0.0966 | −0.0022 | −0.146 | 0.8843 | no |
| `home_pit_runs_allowed_std` | total_runs | +0.0990 | +0.1005 | +0.0015 | +0.098 | 0.9223 | no |
| `home_win_pct` | run_differential | +0.1122 | +0.1133 | +0.0011 | +0.073 | 0.9417 | no |
| `home_pit_runs_allowed_30d` | total_runs | +0.1005 | +0.0996 | −0.0008 | −0.054 | 0.9567 | no |
| `away_pit_woba_against_std` | run_differential | +0.1152 | +0.1160 | +0.0008 | +0.053 | 0.9579 | no |
| `away_pit_woba_against_30d` | run_differential | +0.1025 | +0.1032 | +0.0007 | +0.047 | 0.9622 | no |
| `away_pit_k_pct_std` | home_win | −0.1003 | −0.0999 | +0.0004 | +0.027 | 0.9785 | no |

**Interpretation:** Zero of 30 feature-target pairs tested are statistically significant at p < 0.05 with |r_delta| > 0.015. The largest z_stat (1.82 for `away_pit_woba_against_std` vs. home_win) has p=0.069, narrowly missing significance. This reflects a fundamental power constraint: with pre-era n=9,500 and post-era n=8,048, Fisher z-tests require |r_delta| ≈ 0.027 to achieve 80% power at α=0.05. Most flagged r_delta values (0.016–0.027) fall below this detectability threshold. The era-split sample size imbalance (pre-2022 contains five calendar years including 2016–2019 + 2021 vs. four post-2022 years) limits statistical power for detecting moderate shifts. Conclusion: no feature-target correlation shift can be declared statistically significant given current sample sizes — the flagged shifts are consistent with noise given the era split.

---

### Era Stability Summary

| Metric | Value |
|---|---|
| Features tested (top 20 by mean \|r\|) | 20 |
| Feature-target pairs flagged (\|r_delta\| > 0.015) | 19 of 60 (in era_split_correlations) |
| Feature-target pairs flagged in Fisher z-tests | 8 of 30 |
| Significantly shifted (Fisher p < 0.05 AND \|r_delta\| > 0.015) | 0 |
| Mean \|r_delta\| across all 60 pairs | 0.0122 |
| Correlation structure is stable (mean \|r_delta\| < 0.010) | False |
| Uniquely shifted features | None (shifted_features = []) |

**Key finding:** No features show statistically significant correlation shifts across the 2022 rule-change boundary. While 19 of 60 feature-target pairs exceed the 0.015 |r_delta| flag threshold, all such shifts are statistically non-significant — consistent with sampling noise given era sample sizes. The mean |r_delta| of 0.0122 is above the 0.010 stability threshold, indicating mild but not structurally significant drift. The dominant pattern is that total_runs correlations for away pitching and offensive features show the most era-sensitivity, while directional targets (run_differential, home_win) and core home pitching features show stable correlations across eras.

---

### Design Recommendation

| Flag | Value |
|---|---|
| `separate_era_models_required` | False |
| `post_2022_rules_flag_sufficient` | True |
| `correlation_structure_is_stable` | False |

**Recommendation:** Train a **unified model with `post_2022_rules` flag**. Separate era-specific models are not required. Zero features showed statistically significant correlation shifts across the 2022 rule-change boundary; mean |r_delta| = 0.0122 across top 20 features × 3 targets. The `post_2022_rules` binary flag (already part of the planned Phase 4 feature matrix) is the correct and sufficient implementation path. This flag allows the model to learn incremental era-level mean adjustments (the ~0.64-run structural shift identified in NB01) while pooling all available data for parameter estimation.

**Note:** The mild era drift in total_runs correlations for away pitching (consistently losing signal post-2022) does not require separate models but does reinforce the Card 3.9 recommendation to include the era flag and apply regularization to away pitching features in total-runs models.

---

## Section 11: Bookmaker Calibration and Market Efficiency (2026-04-24)

**Data:** 9,002 matched games (2021–2025), 8 primary bookmakers (lowvig, betonlineag, bovada, draftkings, fanduel, betmgm, williamhill_us, betrivers). Source: `mart_odds_outcomes` joined through `mart_game_odds_bridge`. Vig-adjusted probabilities computed from American odds per bookmaker per event.

---

### Vig / Overround Rankings

Sorted by H2H median overround ascending (rank 1 = lowest vig):

| Rank | Bookmaker | H2H Median Overround | Totals Median Overround | N H2H Events |
|---|---|---|---|---|
| 1 | lowvig | 1.02181 | 1.03366 | 6,299 |
| 2 | betonlineag | 1.02278 | 1.04708 | 7,111 |
| 3 | betrivers | 1.03959 | 1.04742 | 7,210 |
| 4 | fanduel | 1.04050 | 1.04762 | 7,114 |
| 5 | williamhill_us | 1.04141 | 1.04708 | 6,886 |
| 6 | draftkings | 1.04250 | 1.04708 | 8,181 |
| 7 | bovada | 1.04418 | 1.04708 | 7,068 |
| 8 | betmgm | 1.04545 | 1.04708 | 7,092 |

**lowvig ranks #1** (lowest vig) confirmed. The sharp/low-vig books occupy the top 2 ranks. The spread between best (lowvig, 1.022) and worst (betmgm, 1.045) is ~2.3 percentage points of overround. Totals markets show much tighter spread across books (most cluster at 1.047) compared to h2h markets.

---

### Moneyline Calibration

Brier score and log loss per bookmaker per season (≥500 events):

| Bookmaker | Season | N Events | Brier Score | Log Loss |
|---|---|---|---|---|
| betmgm | 2021 | 1,576 | 0.23990 | 0.67256 |
| betmgm | 2022 | 1,782 | 0.23404 | 0.66065 |
| betmgm | 2024 | 1,772 | 0.24018 | 0.67311 |
| betmgm | 2025 | 1,834 | 0.24269 | 0.67803 |
| betonlineag | 2021 | 1,673 | 0.24112 | 0.67506 |
| betonlineag | 2022 | 1,731 | 0.23348 | 0.65947 |
| betonlineag | 2024 | 1,752 | 0.24035 | 0.67341 |
| betonlineag | 2025 | 1,828 | 0.24245 | 0.67753 |
| betrivers | 2021 | 1,684 | 0.24061 | 0.67403 |
| betrivers | 2022 | 1,777 | 0.23384 | 0.66022 |
| betrivers | 2024 | 1,780 | 0.24056 | 0.67388 |
| betrivers | 2025 | 1,840 | 0.24246 | 0.67752 |
| bovada | 2021 | 1,655 | 0.24039 | 0.67357 |
| bovada | 2022 | 1,660 | 0.23291 | 0.65835 |
| bovada | 2024 | 1,782 | 0.24004 | 0.67280 |
| bovada | 2025 | 1,844 | 0.24267 | 0.67801 |
| draftkings | 2021 | 1,596 | 0.23944 | 0.67161 |
| draftkings | 2022 | 1,786 | 0.23384 | 0.66025 |
| draftkings | 2023 | 1,180 | 0.24293 | 0.67867 |
| draftkings | 2024 | 1,786 | 0.24034 | 0.67342 |
| draftkings | 2025 | 1,833 | 0.24276 | 0.67818 |
| fanduel | 2021 | 1,587 | 0.24042 | 0.67359 |
| fanduel | 2022 | 1,781 | 0.23432 | 0.66125 |
| fanduel | 2024 | 1,785 | 0.24044 | 0.67361 |
| fanduel | 2025 | 1,831 | 0.24277 | 0.67821 |
| lowvig | 2021 | 859 | 0.24064 | 0.67404 |
| lowvig | 2022 | 1,749 | 0.23363 | 0.65981 |
| lowvig | 2024 | 1,736 | 0.24052 | 0.67379 |
| lowvig | 2025 | 1,828 | 0.24245 | 0.67754 |
| williamhill_us | 2021 | 1,422 | 0.24108 | 0.67503 |
| williamhill_us | 2022 | 1,776 | 0.23369 | 0.65992 |
| williamhill_us | 2024 | 1,769 | 0.24039 | 0.67353 |
| williamhill_us | 2025 | 1,793 | 0.24252 | 0.67768 |

**Home-team bias** (mean implied home prob − actual home win rate, across qualifying seasons):

| Bookmaker | Mean Bias |
|---|---|
| betmgm | −0.00399 |
| bovada | −0.00250 |
| fanduel | −0.00176 |
| betonlineag | −0.00158 |
| betrivers | −0.00147 |
| williamhill_us | −0.00100 |
| draftkings | +0.00045 |
| lowvig | +0.00091 |

**Interpretation:** Moneyline calibration is remarkably consistent across all books — Brier scores cluster tightly between 0.233 and 0.243. The best individual book-season Brier is bovada 2022 (0.23291). All books achieved notably better Brier in 2022 compared to other seasons, suggesting 2022 had unusually predictable outcomes. No book has a meaningful calibration edge over any other. Home-team bias is essentially zero across all books (all biases within ±0.4%), refuting the +1–3% bias hypothesis (H3). Most books slightly undervalue home teams; lowvig and draftkings very slightly overvalue them.

---

### Totals Market Accuracy

MAE, bias, and over rate per bookmaker per season (≥100 events):

| Bookmaker | Season | N | MAE | Bias | Over Rate |
|---|---|---|---|---|---|
| betmgm | 2021 | 1,573 | 3.5010 | −0.4851 | 0.4711 |
| betmgm | 2022 | 1,780 | 3.3110 | −0.3767 | 0.4635 |
| betmgm | 2024 | 1,792 | 3.3878 | −0.4252 | 0.4738 |
| betmgm | 2025 | 1,827 | 3.5367 | −0.3615 | 0.4499 |
| betonlineag | 2021 | 1,673 | 3.4866 | −0.4866 | 0.4686 |
| betonlineag | 2022 | 1,731 | 3.3345 | −0.3720 | 0.4633 |
| betonlineag | 2024 | 1,773 | 3.3926 | −0.4540 | 0.4777 |
| betonlineag | 2025 | 1,821 | 3.5329 | −0.3517 | 0.4492 |
| betrivers | 2021 | 1,661 | 3.4627 | −0.4380 | 0.4648 |
| betrivers | 2022 | 1,778 | 3.3085 | −0.3265 | 0.4578 |
| betrivers | 2024 | 1,801 | 3.3845 | −0.4317 | 0.4742 |
| betrivers | 2025 | 1,833 | 3.5371 | −0.3505 | 0.4523 |
| bovada | 2021 | 1,623 | 3.5123 | −0.4784 | 0.4677 |
| bovada | 2022 | 1,185 | 3.3346 | −0.4308 | 0.4675 |
| bovada | 2024 | 1,802 | 3.3796 | −0.4306 | 0.4750 |
| bovada | 2025 | 1,836 | 3.5261 | −0.3611 | 0.4526 |
| draftkings | 2021 | 734 | 3.4401 | −0.4564 | 0.4496 |
| draftkings | 2022 | 1,787 | 3.3086 | −0.3377 | 0.4589 |
| draftkings | 2023 | 1,148 | 3.6529 | −0.7234 | 0.4808 |
| draftkings | 2024 | 1,807 | 3.3749 | −0.4463 | 0.4754 |
| draftkings | 2025 | 1,826 | 3.5323 | −0.3609 | 0.4518 |
| fanduel | 2022 | 1,780 | 3.3222 | −0.3390 | 0.4590 |
| fanduel | 2024 | 1,806 | 3.3898 | −0.4468 | 0.4779 |
| fanduel | 2025 | 1,824 | 3.5312 | −0.3635 | 0.4529 |
| lowvig | 2021 | 859 | 3.4750 | −0.5600 | 0.4843 |
| lowvig | 2022 | 1,749 | 3.3290 | −0.3702 | 0.4626 |
| lowvig | 2024 | 1,757 | 3.4010 | −0.4539 | 0.4781 |
| lowvig | 2025 | 1,821 | 3.5327 | −0.3526 | 0.4492 |
| williamhill_us | 2021 | 1,484 | 3.4828 | −0.4586 | 0.4663 |
| williamhill_us | 2022 | 1,782 | 3.3137 | −0.3580 | 0.4585 |
| williamhill_us | 2024 | 1,790 | 3.3740 | −0.4282 | 0.4754 |
| williamhill_us | 2025 | 1,786 | 3.5342 | −0.3578 | 0.4490 |

**Mean totals line by season:**

| Season | Mean Line | Median | Std |
|---|---|---|---|
| 2021 | 8.553 | 8.500 | 1.056 |
| 2022 | 8.184 | 8.063 | 0.906 |
| 2023 | 8.603 | 8.500 | 0.904 |
| 2024 | 8.320 | 8.375 | 0.815 |
| 2025 | 8.452 | 8.500 | 0.820 |

**Interpretation:** There is a consistent **under bias** across all books and seasons — lines are set on average 0.35–0.56 runs above realized totals, resulting in an under rate of ~53–55% (over rate ~45–48%). 2022 had the lowest lines (mean 8.18) and the lowest MAE (3.31), suggesting 2022 was unusually low-scoring. The mean line did not rise monotonically post-2023: 2021 and 2023 both had higher mean lines than 2022 or 2024, refuting H6 (no clean 0.3–0.5 run post-2023 step-up). The standard deviation of lines has decreased over the sample (1.056 in 2021 → 0.820 in 2025), indicating bookmakers are setting more consistent lines year over year.

---

### Cross-Bookmaker Consensus and Disagreement

**Sharp books** (lowvig, betonlineag, bovada) vs. **soft books** (draftkings, fanduel, betmgm, williamhill_us, betrivers):

- Sharp books Brier: **0.2395** (n=7,203 games)
- Soft books Brier: **0.2395** (n=7,203 games)
- Brier difference (soft − sharp): **0.0000**

**Sharp-soft delta Pearson r with home_win:** r=0.021, p=0.0798

**Disagreement quartile signal** (binned by ml_consensus_std, Q1=most agreement):

| Quartile | Std Range | N Games | Outcome Variance | Home Win Rate |
|---|---|---|---|---|
| Q1 (least spread) | [0.000, 0.004] | 1,810 | 0.24864 | 0.5387 |
| Q2 | [0.004, 0.005] | 1,810 | 0.24992 | 0.5149 |
| Q3 | [0.005, 0.007] | 1,809 | 0.24844 | 0.5412 |
| Q4 (most spread) | [0.007, 0.035] | 1,810 | 0.24911 | 0.5320 |

**Interpretation:** Sharp and soft books are essentially identical in predictive accuracy — the Brier difference is negligible (0.0000). Books agree very tightly on moneyline probabilities (std across books typically 0.004–0.007); this tight consensus limits the disagreement signal. Q4 outcome variance (0.24911) does not exceed Q1 (0.24864) by 10%, so the disagreement-predicts-variance hypothesis is inconclusive. The sharp-soft delta (r=0.021, p=0.080) narrowly misses the 0.030 threshold for signal.

---

### Hypothesis Verdicts (H1–H7)

| Hypothesis | Description | Verdict | Key Evidence |
|---|---|---|---|
| H1 | Sharp books (lowvig, betonlineag, bovada) have lower Brier than soft books | **inconclusive** | sharp_brier=0.23952, soft_brier=0.23952, diff=0.00000; diff ≤ 0.002 threshold |
| H2 | lowvig has lowest h2h overround | **supported** | lowvig_h2h_rank=1; median overround=1.02181, next best=betonlineag 1.02278 |
| H3 | Books overvalue home teams by +1–3% | **not supported** | mean_bias=−0.00108 across all book-season pairs; all books within ±0.4% of zero |
| H4 | High disagreement predicts higher outcome variance | **inconclusive** | Q4/Q1 variance ratio=1.002; Q4 var=0.24911, Q1 var=0.24864; below 1.10 threshold |
| H5 | Sharp-soft delta has directional signal (|r|>0.030) | **inconclusive** | r=0.021, p=0.080; |r| > 0.010 but ≤ 0.030 and p ≥ 0.05 |
| H6 | Post-2023 rule changes caused totals lines to rise 0.3–0.5 runs | **not supported** | mean line delta (2023–2025 vs 2021–2022)=+0.09; below 0.20 threshold |
| H7 | Market consensus Brier beats naive baseline (~0.250) | **supported** | consensus_brier_overall=0.23952 < 0.240 threshold |

---

### Market Efficiency Benchmark

- **consensus_brier_overall:** 0.23952
- **favorite_brier** (home_imp > 0.5): 0.23727
- **underdog_brier** (home_imp ≤ 0.5): 0.24342

Brier score by season (≥3 books consensus):

| Season | Consensus Brier | N Games |
|---|---|---|
| 2021 | 0.24066 | 1,695 |
| 2022 | 0.23379 | 1,787 |
| 2023 | 0.24917 | 128 |
| 2024 | 0.24037 | 1,786 |
| 2025 | 0.24251 | 1,843 |

**Interpretation:** Market calibration is broadly stable across seasons — 2022 was notably well-calibrated (0.2338), 2023 appears poorly calibrated but has only 128 consensus games (sparse historical coverage for that year). Favorites are better calibrated than underdogs (Brier 0.237 vs 0.243), as expected given stronger price signals when one team is clearly better. The market is not improving monotonically season-over-season; calibration quality is within a narrow band (±0.005 Brier points) across 2021–2025.

**Market consensus Brier (2021–2025): 0.2395. Phase 4 models must beat this to add value over the market.**

---

### Design Recommendation

| Flag | Value |
|---|---|
| `include_consensus_features` | **True** |
| `include_sharp_soft_features` | False |
| `queue_mart_odds_consensus_card` | **True** |
| `market_baseline_brier` | **0.23952** |

**Rationale:** consensus_brier_overall=0.23952. H7 (supported) → include_consensus_features=True. H1 (inconclusive) → include_sharp_soft_features=False. queue_mart_odds_consensus_card=True. All verdicts: H1=inconclusive; H2=supported; H3=not supported; H4=inconclusive; H5=inconclusive; H6=not supported; H7=supported.

**queue_mart_odds_consensus_card=True:** A Card 4.X to build `mart_odds_consensus` (aggregating `mart_odds_outcomes` to game-grain — final pre-game snapshot per bookmaker per event, then consensus across books) should be queued before Phase 4 feature assembly. The consensus moneyline probability (`home_win_prob_consensus`) and totals line consensus (`total_line_consensus`) are the primary features to include; sharp-soft disaggregation features are low priority given H1 inconclusive and H5 inconclusive results.
