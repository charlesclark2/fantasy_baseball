# Model Performance History

Track of CV metrics across major retrain events. Use this to verify whether
feature additions and architectural changes are improving or degrading model
quality over time.

---

## Baseline: Card 7.F (2026-05-03) — Stuff+ Arsenal Features

The Card 7.F retrain is the v1 pre-expansion baseline: first retrain on the
`game_year >= 2021` training cutoff (10,243 rows, 267 features). All three
Phase 7 feature expansion cards after 7.F (umpires, injury, matchup, cluster,
bullpen, pythagorean) are NOT included in this baseline.

| Model | Architecture | Metric | CV Score | Training rows | Features | Notes |
|---|---|---|---|---|---|---|
| home_win | XGBoost + Platt | Brier (↓ better) | 0.2443 | 10,243 | 267 | Calibrator ECE 0.0614→0.0370 |
| total_runs | NGBoost Normal | MAE (↓ better) | 3.4856 | 10,243 | 267 | LogNormal also tested |
| run_differential | NGBoost Normal | MAE (↓ better) | 3.4586 | 10,243 | 267 | LogNormal excluded (neg values) |

Calibrator (Card 7.C, refit post-7.F): Platt scaling, ECE 0.0614 → 0.0370.
Calibrator note in registry: "Calibrator fitted on prior model — refit recommended."

**Feature groups included at 7.F baseline:**
- Statcast rolling (Phase 2/4): batting, pitching, platoon splits, bullpen base
- Park factors, venue dimensions, weather (temp_f, wind, humidity)
- Stuff+ / arsenal features (Card 7.F): 13 retained
- Weather columns from 7.B (temp_f, wind_component_mph, humidity_pct, etc.)

**Feature groups NOT included (added after 7.F, deferred to 7.MA):**
- Umpire tendencies (Card 7.H): ump_runs_per_game_zscore, ump_accuracy_zscore
- Injury / lineup status (Card 7.I): home/away_injured_player_count, injury_adj_woba
- Pitch archetype matchup (Card 7.J): lineup_woba/xwoba/k_pct/iso_vs_starter_archetype
- Pitcher cluster matchup (Card 7.K): lineup_avg_woba/xwoba_vs_cluster
- Batter archetype matchup (Card 7.K2): lineup_archetype_avg_woba/xwoba
- Bullpen fatigue IP (Card 7.Q): bullpen_ip_prev_1d/2d, pitchers_used_prev_2d
- Pythagorean win expectation (Card 7.R): pythagorean_win_exp, pythagorean_win_exp_diff

---

## Feature Coverage Audit (2021+, run 2026-05-03 pre-7.MA retrain)

Query run via Snowflake MCP on `feature_pregame_game_features WHERE game_year >= 2021`.

| Year | Rows | Weather | Stuff+ | Umpire | Injury | Archetype | Cluster | Pythagorean | Bullpen IP |
|---|---|---|---|---|---|---|---|---|---|
| 2021 | 2,429 | **0.0%** | 99.8% | 100.0% | 100.0% | 80.7% | **60.6%** | 90.7% | 99.0% |
| 2022 | 2,430 | 96.6% | 99.8% | 99.9% | 100.0% | 85.8% | 85.8% | 90.4% | 99.3% |
| 2023 | 2,430 | 95.4% | 99.9% | 96.6% | 100.0% | 83.0% | 85.3% | 90.7% | 99.2% |
| 2024 | 2,429 | 94.4% | 99.9% | 99.3% | 100.0% | 80.8% | 84.8% | 90.7% | 99.3% |
| 2025 | 2,430 | 94.0% | 99.9% | 98.6% | 100.0% | 83.0% | 98.6% | 93.8% | 99.5% |
| 2026 | 497  | 81.5% | 100.0% | 96.4% | 100.0% | 91.3% | 96.0% | **69.8%** | 99.8% |

**Flagged (null rate > 25%):**
- Weather / 2021: 0% coverage — weather ingestion did not backfill 2021 games.
  Imputation will substitute training-set mean for all 2021 weather features.
- Cluster / 2021: 60.6% coverage (39.4% null rate) — 2020 pitcher clusters used
  as `game_year - 1` prior; 2020 had sparse arsenal data. Bayesian fallback applies.
- Pythagorean / 2026: 69.8% — expected; partial season, early games < 10 GP gate.

These flags are documented for CV interpretation only. Retrain proceeds.

---

## Card 7.MA Retrain (2026-05-04) — Full Phase 7 Feature Set

Joint retrain of all three models on the complete Phase 7 feature set.
Training data: 10,256 rows, 6 seasons (2021–2026), 292 retained features.
See [v1_retrain_impact.md](v1_retrain_impact.md) for full analysis.

| Model | Architecture | Metric | 7.F CV | 7.MA CV | Delta | Decision |
|---|---|---|---|---|---|---|
| home_win | XGBoost + Platt | Brier (↓ better) | 0.2443 | **0.2439** | −0.17% | ✓ improved |
| total_runs | NGBoost LogNormal | MAE (↓ better) | 3.4856 | **3.5190** | +0.96% | keep (within CV noise) |
| run_differential | NGBoost Normal | MAE (↓ better) | 3.4586 | **3.4724** | +0.40% | keep (within CV noise) |
| Calibrator ECE | Platt on 2026 | ECE (↓ better) | 0.0370 | **0.0420** | +13.5% | ⚠ see note |

**Calibrator note:** Raw XGBoost model ECE is 0.0247 — already better than the previous
calibrated model (0.0370). Platt scaling degraded ECE to 0.0420 on the 2026 eval set.
The raw model is the best-calibrated artifact; calibrator saved but monitor before relying on it.

**Feature groups added in 7.MA (all absent from 7.F baseline):**
- Umpire tendencies (Card 7.H): ump_runs_per_game_zscore, ump_accuracy_zscore
- Injury / lineup status (Card 7.I): home/away_injured_player_count, injury_adj_woba
- Pitch archetype matchup (Card 7.J): lineup_woba/xwoba/k_pct/iso_vs_starter_archetype
- Pitcher cluster matchup (Card 7.K): lineup_avg_woba/xwoba_vs_cluster
- Batter archetype matchup (Card 7.K2): lineup_archetype_avg_woba/xwoba
- Bullpen fatigue IP (Card 7.Q): bullpen_ip_prev_1d/2d, pitchers_used_prev_2d
- Pythagorean win expectation (Card 7.R): pythagorean_win_exp, pythagorean_win_exp_diff

**Feature count:** 267 (7.F) → 292 retained + 2 pipeline-generated = **294 total model inputs**

---
