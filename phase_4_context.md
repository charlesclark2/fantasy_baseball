# Phase 4 Context: Baseline Prediction Models

This document provides focused context for Phase 4 (ML Pipeline) of the baseball betting prediction system. It is written for agents and collaborators working in `betting_ml/` who need the full picture of goals, constraints, current state, and outstanding work without reading the entire `project_context.md`.

For full architecture details, see [`project_context.md`](project_context.md). For daily ingestion and dbt commands, see [`README.md`](README.md).

---

## Mission

Predict three outcomes for each MLB regular-season game, given only information available **before first pitch**:

| Target | Type | Primary Metric | Baseline to Beat |
|---|---|---|---|
| **Total runs scored** | Regression | MAE; P(over/under) Brier score | MAE ~3.5 runs (global mean) |
| **Run differential** (`home - away`) | Regression | MAE; derived win-prob Brier score | — |
| **Binary home win** | Classification | Brier score, log loss, calibration curve | Market-implied Brier |

The regression models produce predictive distributions (not just point estimates), enabling `P(total_runs > line)` directly comparable to bookmaker implied probabilities.

---

## Data Foundation

### Feature Store

All Phase 4 ML inputs come from `baseball_data.betting_features.feature_pregame_game_features` — a single wide row per game assembled by six dbt feature models. Phase 2 is complete.

| Model | Grain | Description |
|---|---|---|
| `feature_pregame_lineup_features` | Game × side | Aggregated batter rolling stats + prior-season platoon splits across all 9 lineup slots |
| `feature_pregame_starter_features` | Game × starter | Rolling pitcher K%, xwOBA, days rest, platoon splits, IP depth |
| `feature_pregame_team_features` | Game × team | Rolling offense + pitching, bullpen workload + effectiveness, season record, schedule context |
| `feature_pregame_park_features` | Game | Park dimensions, elevation, surface, roof type, prior-season empirical run factors |
| `feature_pregame_odds_features` | Game | Bookmaker moneyline + totals prices, vig-adjusted implied probabilities (leakage guard: `ingestion_ts < commence_time`) |
| `feature_pregame_game_features` | Game | Master assembly — joins all five tables into a single wide ML input row |

**Training set size:** 25,146 regular-season rows total; `has_full_data = true` selects ~23,444 data-complete rows (2016–2025 complete seasons). Exclude 2020 (COVID season — structural confounders).

**No-leakage rule:** Every rolling stat uses `< game_date` (not `<=`). Platoon splits and park factors use `game_year - 1` (prior season only). Season record uses `game_date - 1`. Odds features require `ingestion_ts < commence_time`. Audit documented in `data_quality/leakage_audit.md`.

### Canonical Join Keys

| Grain | Key | Description |
|---|---|---|
| **Game** | `game_pk` | MLB Stats API integer; present in Statcast and Stats API sources |
| **Pitch** | `pitch_sk` | MD5 surrogate on `game_pk + at_bat_number + pitch_number + batter_id + pitcher_id + inning + inning_half` |
| **Player** | `batter_id` / `pitcher_id` | Statcast/BAM integer player IDs |

### Data Sources Used in Phase 4

| Source | Snowflake Location | Phase 4 Use |
|---|---|---|
| Statcast pitch data | `baseball_data.savant.batter_pitches` | Powers all rolling batter/pitcher/team stats in mart layer |
| MLB Stats API schedule | `baseball_data.statsapi.monthly_schedule` | Lineups, probable pitchers, game metadata |
| MLB Stats API venues | `baseball_data.statsapi.venues_raw` | Park dimensions, elevation, surface, roof |
| The Odds API | `baseball_data.oddsapi.mlb_events_raw`, `mlb_odds_raw` | Bookmaker moneyline + totals for market comparison layer |
| Seeds | `baseball_data.betting.ref_teams` | Team reference (abbreviation normalization) |

---

## Phase 4 Current State

| Card | Title | Status |
|---|---|---|
| 4.1 | Delta/momentum features (team offense + starter K% 7d−30d/std) | ✓ Complete (2026-04-23) |
| 4.2 | Lineup-vs-starter handedness matchup features | ✓ Complete (2026-04-23) |
| 4.3 | Rolling window reliability flags (games-played per window) | ✓ Complete (2026-04-23) |
| 4.4 | Starter expected depth (avg IP last 3 starts, season avg IP) | ✓ Complete (2026-04-23) |
| 4.5 | Game context and era flags (day/night, series position, time-varying home win rate, `post_2022_rules`) | ✓ Complete (2026-04-23) |
| 4.6 | ML pipeline foundation (data loader, temporal CV splits, preprocessing/shrinkage) | ✓ Complete |
| 4.8 | Feature selection and model serialization convention | Queued — plan spec drafted |
| 4.9 | Baseline regression: total runs (Ridge, XGBoost, NGBoost) | Queued — plan spec drafted |
| 4.10 | Baseline regression: run differential + derived win probability | Queued — plan spec drafted |
| 4.11 | Baseline classification: win outcome (Logistic, XGBoost calibrated) | Queued — plan spec drafted |
| 4.12 | Hyperparameter optimization (Optuna, 50 trials per model) | Queued — plan spec drafted |
| 4.13 | Probability output layer + Bayesian market update | Queued — plan spec drafted |
| 4.B1 | [Backlog] Weather feature integration | Blocked — no data source |
| 4.B2 | [Backlog] Umpire tendency features | Blocked — no data source |

### What Is Built (`betting_ml/utils/`)

**`data_loader.py`** — Snowflake → pandas loader. Queries `feature_pregame_game_features` joined to `mart_game_results` (targets: `home_score + away_score`, `home_score - away_score`, `home_win`). Applies `has_full_data = true` and `min_games_played ≥ 15` filter. Uses same RSA key as EDA notebooks.

**`cv_splits.py`** — Temporal leave-one-season-out CV splits. Train on seasons N−k through N−1, evaluate on season N. No shuffled k-fold — chronological order is strictly preserved. Default: train 2016–2024, evaluate 2025.

**`preprocessing.py`** — Imputation pipeline + Bayesian shrinkage. Handles all six null groups identified in EDA Notebook 02:
- Starter platoon splits: add `has_starter_platoon_data` flag; impute with prior-season league-average split by pitcher hand × batter hand
- Park run factor: cascade 3yr → 1yr → league average; add `is_new_venue` indicator
- Opening Day win%, days rest: fill with 0.500 and 4 days respectively
- Bullpen effectiveness early-season: fill with prior-season league-average xwOBA
- Bayesian shrinkage for early-season rolling stats: weight = `n / (n + k)` where k=15 (tunable); targets the 10–30 game transitional bucket

---

## Design Constraints (from EDA)

These constraints are locked-in decisions derived from EDA Notebooks 01–07 and Cards 3.8/3.9 analysis scripts. Do not re-litigate them in Phase 4 unless new evidence warrants it.

| Constraint | Decision | Source |
|---|---|---|
| Training set filter | `min(home_games_played, away_games_played) ≥ 15` — removes early-season noise (5.5% of rows, retains 85% of data) | NB03 |
| Primary feature window — pitcher metrics | Season-to-date (`_std`) — strongest correlation; K%, xwOBA | NB03 |
| Primary feature window — team offense | 30-day (`_30d`) — equivalent to STD; more robust to roster changes | NB03 |
| 7d rolling windows | **Include 7d windows directly** — add ΔR²=0.043–0.047 over 30d/STD-only baseline. Use raw 7d columns, not delta encoding. | NB03, NB07 |
| 14d standalone features | **Drop** — redundant with 30-day; no independent signal | NB04, NB07 |
| 2020 season | **Exclude** from training — COVID bubble, structural confounders | NB01 |
| Era feature | Include `game_year` integer + `post_2022_rules` boolean (`game_year >= 2023`); 2022→2023 shift ban + pitch clock caused ~0.64-run structural mean shift | NB01 |
| Home win rate | Use time-varying `home_win_rate_trailing_3yr`; declined 0.548 (2020) → 0.519 (2023); static 0.529 is wrong for recent seasons | NB01 |
| Odds features | **Exclude from primary model** (100% null in training window); add as optional enrichment block for live 2026 games and once historical backfill is complete | NB02 |
| Starter platoon splits null handling | Add `has_starter_platoon_data` indicator; impute nulls with prior-season league-average split by pitcher hand × batter hand | NB02 |
| Total runs distribution shape | Right tail — blowout games exceed Gaussian; evaluate LogNormal in addition to Normal for NGBoost | NB01 |
| Weakest training bucket | 10–30 game window (not just 0–10); Bayesian shrinkage targets this transitional zone | NB03 |
| xwOBA vs. raw wOBA | Prefer xwOBA within any given window — more stable (park-adjusted); drop raw wOBA where both exist for the same window | NB04 |
| `total_matchup_quality_30d` | **Drop** — r=0.005 with total_runs; no value over components | NB04 |
| `matchup_advantage_30d` | **Retain for totals model only** (r=0.050); directional confound makes it invalid for run_differential / moneyline targets | NB04 |
| Park factor + elevation | **Include both** — `park_run_factor_3yr` (r=0.122, strongest predictor); `elevation_ft` (r=0.111, partially independent) | NB05 |
| Schedule features | Include `home_days_rest`, `away_days_rest`, `home_tz_changed`, `away_tz_changed` as cheap flags; r<0.023; ΔR² < 0.002 from adding all four | NB05 |
| Bat tracking (`bat_speed`, `swing_length`) | **Exclude from Phase 4 primary model** — 26.8% sub-sample; max |r| = 0.022 (vs. 0.088 park factor); OLS ΔR² < 0.001 | NB06 |
| Delta/momentum features (`*_7d_minus_30d`) | **Prefer raw 7d windows over delta encoding** — individual delta |r| < 0.022; ΔR²=0.043–0.047 reflects 7d recency lift, not momentum direction | NB07 |
| Lineup-vs-starter handedness matchup | **Validated low-signal — exclude from primary model** — ΔR²=0.001–0.002; signal already captured by starter xwOBA and K% | NB07 |
| Starter vs. bullpen xwOBA (Card 3.8) | **Keep both as independent features** — home r=0.169, away r=0.164 (no high collinearity); mean incremental R²=0.0041 (above 0.002 threshold); workload features max incremental R²=0.0005 (exclude) | Card 3.8 script |
| Home/away pitching asymmetry (Card 3.9) | **Include both home and away pitching features** — partial r of away pitching vs. total_runs = 0.0122 (park does not absorb it); asymmetry is total_runs-specific; era flag required; apply regularization | Card 3.9 script |

---

## Model Approach

### Model Families (A/B/C per target)

| Target | Model A | Model B | Model C | Primary Metric |
|---|---|---|---|---|
| Total runs (regression) | Ridge/Lasso | XGBoost + residual distribution | NGBoost (Normal vs. LogNormal) | MAE vs. ~3.5 baseline; P(over) Brier score |
| Run differential (regression) | Ridge/Lasso | XGBoost + residual distribution | NGBoost | MAE; derived win-prob Brier score |
| Win outcome (classification) | Logistic Regression | XGBoost + Platt/isotonic calibration | — | Log loss, Brier score, calibration curve |

**NGBoost** outputs a full parametric distribution per prediction — `P(total_runs > any_line)` is directly computable without post-hoc distribution fitting, making it the most natural bridge to bookmaker implied probability comparison.

### Temporal Cross-Validation

Leave-one-season-out: train on 2016–2024, evaluate on 2025. Future folds can extend to walk-forward evaluation by year. No shuffled k-fold — temporal order must be preserved throughout. Defined in `betting_ml/utils/cv_splits.py`.

### Feature Groups in Phase 4 Feature Matrix

In priority order (by expected signal strength):

1. **Park context** — `park_run_factor_3yr`, `elevation_ft`, `surface`, `roof_type` (highest r with total_runs)
2. **Starting pitcher stats** — `home_starter_xwoba_against_std`, `away_starter_xwoba_against_std`, `home_starter_k_pct_std`, `away_starter_k_pct_std`, `*_days_rest`, prior-season platoon splits, `*_avg_ip_last_3`
3. **Bullpen effectiveness** — `home_bp_xwoba_against_30d`, `away_bp_xwoba_against_30d` (independent of starter — Card 3.8 verdict)
4. **Team rolling offense (7d + 30d)** — wOBA, xwOBA, runs scored, K%, BB%
5. **Team rolling pitching (7d + 30d)** — xwOBA against, K%, BB%
6. **Lineup features** — aggregated batter wOBA + handedness composition (9 slots)
7. **Season record** — team win% as overall quality proxy
8. **Era and context flags** — `post_2022_rules`, `game_year`, `home_win_rate_trailing_3yr`, `is_day_game`, `series_game_number`
9. **Schedule flags** — `home_days_rest`, `away_days_rest`, `home_tz_changed`, `away_tz_changed`
10. **Rolling window reliability flags** — `home_games_played_30d`, `home_starter_appearances_30d` (for Bayesian shrinkage weighting, not as direct predictors)

**Exclude from primary model:** 14d standalone features, delta/momentum encoding (use raw 7d instead), lineup-vs-starter handedness matchup, bat tracking features, workload features (`bullpen_pitches_prev_3d`, `pitchers_used_prev_7d`).

### Probability Output and Market Comparison (Card 4.13)

For games where `has_odds = true`, the Bayesian posterior blends model and market in log-odds space:

```
log_odds_posterior = α × log_odds_model + (1 − α) × log_odds_market
```

where α is tuned via CV (start at 0.5). Edge signal: `edge = model_prob − market_implied_prob`. Output includes `model_prob`, `market_implied_prob`, `posterior_prob`, `edge`, and `implied_kelly_fraction` per game per market.

---

## Outstanding Work (Cards 4.8–4.13)

### Card 4.8 — Feature Selection and Model Serialization
- Build `utils/feature_selection.py`: drop near-zero correlation features (|r| < 0.02), resolve high-multicollinearity pairs (|r| > 0.85). Unconditionally retain `post_2022_rules`, `game_year`, `home_win_rate_trailing_3yr`.
- Persist canonical feature list to `betting_ml/evaluation/feature_selection.md` — this is the input contract for Cards 4.9–4.11.
- Build `utils/model_io.py`: `save_model(model, target, model_name, eval_year)` / `load_model(...)` using joblib. Path: `betting_ml/models/{target}/{model_name}_{eval_year}.pkl`.
- **Blocked by:** Card 4.6 (data loader). NB04 preferred but not required.

### Card 4.9 — Baseline Regression: Total Runs
- Ridge, XGBoost, NGBoost (Normal + LogNormal) on temporal CV splits.
- Primary: MAE vs. ~3.5 baseline; P(over) Brier for `has_odds = true` games.
- SHAP importance to verify delta and lineup-vs-starter features contribute non-zero signal.
- Results → `betting_ml/evaluation/total_runs_results.md`.
- **Blocked by:** Cards 4.6, 4.8.

### Card 4.10 — Baseline Regression: Run Differential
- Same three-model structure as Card 4.9, target = `home_score − away_score`.
- Win probability derived from NGBoost: `P(home win) = P(run_diff > 0) = 1 − Φ((0 − μ) / σ)`.
- Compare derived win probability to Card 4.11 classifier — should be within 0.05 Brier score.
- Era feature ablation: verify `post_2022_rules` reduces 2022→2023 prediction error.
- Results → `betting_ml/evaluation/run_differential_results.md`.
- **Blocked by:** Cards 4.6, 4.8.

### Card 4.11 — Baseline Classification: Win Outcome
- Logistic Regression + XGBoost with Platt scaling and isotonic calibration (compare both).
- Calibration is the primary concern — outputs feed Phase 6 EV calculations.
- Evaluate home-team bias in 2023–2025; verify `home_win_rate_trailing_3yr` reduces it.
- Results → `betting_ml/evaluation/win_outcome_results.md`.
- **Blocked by:** Cards 4.6, 4.8.

### Card 4.12 — Hyperparameter Optimization
- Optuna TPE sampler; 50 trials per XGBoost model (total runs, run differential, win outcome).
- Search space: `max_depth` 3–8, `learning_rate` 0.01–0.3, `n_estimators` 100–1000, `subsample` 0.6–1.0, `colsample_bytree` 0.5–1.0, `reg_alpha` 0–1, `reg_lambda` 0.5–2.
- NGBoost: grid search over `n_estimators` and distribution type (Normal vs. LogNormal).
- Results → `betting_ml/evaluation/hyperparameter_tuning.md`. Models persisted via Card 4.8 `model_io.py` with `_tuned` suffix.
- **Blocked by:** Cards 4.9, 4.10, 4.11, 4.8.

### Card 4.13 — Probability Output Layer and Bayesian Market Update
- Bayesian posterior blend (log-odds space) with tunable mixing weight α.
- Output: `model_prob`, `market_implied_prob`, `posterior_prob`, `edge`, `implied_kelly_fraction` per game per market.
- Currently applicable to live 2026 games only (`has_odds = true`); becomes more powerful once historical odds backfill completes.
- **Blocked by:** Cards 4.9, 4.10, 4.11, 4.12.

---

## File Reference (Phase 4)

| Path | Purpose |
|---|---|
| `betting_ml/utils/data_loader.py` | Snowflake → pandas; applies `has_full_data=true` and `min_games_played ≥ 15` filter |
| `betting_ml/utils/cv_splits.py` | Temporal leave-one-season-out CV splits; no shuffled k-fold |
| `betting_ml/utils/preprocessing.py` | Imputation + Bayesian shrinkage pipeline; handles all 6 null groups from NB02 |
| `betting_ml/utils/feature_selection.py` | **Not yet built (Card 4.8)** — correlation-based drop + multicollinearity resolution |
| `betting_ml/utils/model_io.py` | **Not yet built (Card 4.8)** — joblib save/load with standard path convention |
| `betting_ml/scripts/analyze_pitching_decomp.py` | Card 3.8 — starter vs. bullpen xwOBA decomposition analysis |
| `betting_ml/scripts/analyze_home_away_pitch_asymmetry.py` | Card 3.9 — home/away pitching asymmetry root-cause analysis |
| `betting_ml/evaluation/pitching_decomp_results.json` | Card 3.8 results — cross-correlation, partial correlations, OLS R², design recommendation |
| `betting_ml/evaluation/home_away_pitch_asymmetry_results.json` | Card 3.9 results — partial correlations, quartile analysis, era-split, design recommendation |
| `betting_ml/evaluation/feature_selection.md` | **Not yet written (Card 4.8)** — canonical retained/dropped feature list |
| `betting_ml/evaluation/total_runs_results.md` | **Not yet written (Card 4.9)** — per-model MAE/RMSE/Brier per held-out season |
| `betting_ml/evaluation/run_differential_results.md` | **Not yet written (Card 4.10)** — per-model results + win probability derivation |
| `betting_ml/evaluation/win_outcome_results.md` | **Not yet written (Card 4.11)** — per-model Brier/log loss/calibration per held-out season |
| `betting_ml/evaluation/hyperparameter_tuning.md` | **Not yet written (Card 4.12)** — Optuna trials, best params, CV scores per model |
| `betting_ml/models/` | Serialized model files (Card 4.8+ path convention: `{target}/{model_name}_{eval_year}.pkl`) |
| `betting_ml/tests/test_cv_splits.py` | Unit tests for CV split logic |
| `betting_ml/tests/test_preprocessing.py` | Unit tests for imputation and Bayesian shrinkage |
| `plan_specs/phase_4/6_ml_pipeline_foundation_plan.yaml` | PlanSpec for Card 4.6 (complete) |
| `plan_specs/phase_4/8_feature_selection_plan.yaml` | PlanSpec for Card 4.8 |
| `plan_specs/phase_4/9_base_reg_model_tot_runs.yaml` | PlanSpec for Card 4.9 |
| `plan_specs/phase_4/10_base_reg_model_run_diff.yaml` | PlanSpec for Card 4.10 |
| `plan_specs/phase_4/11_base_class_model_win_outcome.yaml` | PlanSpec for Card 4.11 |
| `plan_specs/phase_4/12_hyperparameter_optimization.yaml` | PlanSpec for Card 4.12 |
| `plan_specs/phase_4/13_bayes_prob_layer.yaml` | PlanSpec for Card 4.13 |
| `exploratory_data_analysis/betting_model_findings.md` | Cumulative EDA findings — sections 01–09 complete; Phase 4 feature constraints source |
| `data_quality/leakage_audit.md` | Full no-leakage code review checklist and Snowflake spot-check results |
| `data_quality/data_availability_windows.md` | Verified first-available dates per feature group; odds coverage per season |

---

## Success Criteria for Phase 4 Completion

Phase 4 is complete when:

1. A feature selection module (`utils/feature_selection.py`) with a documented canonical feature list exists
2. Baseline models for all three targets (Ridge, XGBoost, NGBoost/Logistic) are trained on temporal CV splits and evaluated on a held-out season
3. All three model families beat their respective baselines (MAE < ~3.5 for total runs; Brier score below naive market-implied baseline for win outcome)
4. NGBoost produces a calibrated predictive distribution for total runs and run differential from which `P(over/under line)` can be computed directly
5. XGBoost models are hyperparameter-optimized via Optuna with tuning logs persisted
6. A probability output layer blends model predictions with bookmaker implied probabilities for live `has_odds = true` games
7. All models are serialized via `utils/model_io.py` with consistent path conventions

What Phase 4 does **not** require:
- Weather or umpire features (Phase 5 backlog)
- Bat tracking features (re-evaluate in Phase 5 with per-batter aggregations)
- Lineup-vs-starter handedness matchup as a primary feature (validated low-signal in NB07)
- Historical odds backfill for training (odds features are excluded from the primary model)
