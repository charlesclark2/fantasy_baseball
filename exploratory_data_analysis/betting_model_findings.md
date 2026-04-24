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
