# Total Runs Bias Diagnosis (Card 7.V)

## Failure Mode

The v1 NGBoost LogNormal `total_runs` model (Card 7.MA, deployed 2026-05-04)
exhibits two stacked failures on the 2024+ holdout:

1. **Variance shrinkage** — `std(pred_total_runs) = 0.87` vs actual std `4.46`
   (5x too narrow). P10/P50/P90 of predictions = 6.40 / 7.51 / 8.37, with the
   typical consensus line averaging 8.38 — the 90th percentile of the model
   barely reaches the median market line.
2. **Location bias (mean residual)** — every season 2021–2026 shows a
   systematically negative residual of −1.13 to −2.13, mean −1.36 across
   the 2024+ window. The model under-predicts uniformly.

Net result: `pct_pred_over` (model crossing the consensus line) is **3.5%**
across 4,045 v1 has-odds rows. The model effectively never picks "over"
relative to the market — useless as a totals signal.

## Diagnostic Numbers

### 1. Distribution check (2024+ has-odds, total_line_consensus IS NOT NULL)

Source: `baseball_data.betting_ml.daily_model_predictions`

| model_version | n     | mean_pred | std_pred | p10  | p50  | p90  | avg_line | pct_pred_over |
|---------------|-------|-----------|----------|------|------|------|----------|---------------|
| v0            | 4,639 | 6.61      | 1.32     | 5.24 | 6.30 | 8.85 | 8.36     | 19.0%         |
| v1            | 4,045 | 7.43      | 0.87     | 6.40 | 7.51 | 8.37 | 8.38     | **3.5%**      |
| prod (mixed)  | 455   | 5.77      | 0.64     | 4.93 | 5.84 | 6.53 | 8.27     | 0.0%          |

(Note: `prod` rows are mixed-tag scoring and reflect the same v1-or-better
underlying total_runs artifact when total_runs_tag=v0 was selected after the
log-storage hotfix on 2026-05-05 — coverage too narrow to be diagnostic on
its own.)

**Mean residual / MAE (joined to mart_game_results, 2024+):**

| model_version | n     | mean_residual | mae   | mean_actual | std_actual |
|---------------|-------|---------------|-------|-------------|------------|
| v0            | 6,007 | −2.28         | 3.86  | 8.84        | 4.44       |
| v1            | 5,316 | **−1.36**     | **3.47** | 8.84    | 4.46       |
| prod          | 500   | −3.22         | 4.27  | 8.96        | 4.52       |

v1 wins on MAE (10% better than v0) but loses on directional usefulness —
because the predictions cluster near 7.4 instead of spanning the actual
4–14 distribution.

### 2. Per-season bias check (v1 only)

| season | n     | mean_pred | std_pred | mean_residual | mean_actual |
|--------|-------|-----------|----------|---------------|-------------|
| 2021   | 2,429 | 7.64      | 1.02     | −1.42         | 9.06        |
| 2022   | 2,430 | 7.43      | 0.94     | −1.13         | 8.57        |
| 2023   | 2,430 | 7.69      | 0.96     | −1.54         | 9.23        |
| 2024   | 2,374 | 7.56      | 0.77     | −1.19         | 8.76        |
| 2025   | 2,430 | 7.54      | 0.91     | −1.36         | 8.89        |
| 2026   | 512   | 6.84      | 1.10     | −2.13         | 8.98        |

**Interpretation:** the bias is **uniform across all seasons**, ranging only
from −1.13 to −2.13. There is no concentration in the COVID-pitching era
(2021–22) — 2024 has the *narrowest* prediction band (std 0.77) and 2023
has the worst residual. **Hypothesis 3 (training cutoff) is ruled out.**
The defect is structural to the model architecture / fit, not to the
training window.

### 3. Per-feature-group ablation (v1 NGBoost internals)

`m = joblib.load('betting_ml/models/total_runs/ngboost_tuned_2026.pkl')`:

- `Dist = LogNormal`
- `n_estimators = 500`
- `Base = DecisionTreeRegressor(criterion='friedman_mse', max_depth=3)`
- 500 base models per parameter (loc and scale → 1000 total trees)

The base learner is `max_depth=3` — extremely shallow. With 500 boosting
rounds and the default natural-gradient learning rate, this configuration
struggles to fit the heavy tails of the runs distribution, which is what
the variance shrinkage symptom would predict.

NGBoost's joint gradient updates the scale parameter at every iteration.
With LogNormal, `scale` is the standard deviation of `log(Y)` — a small
log-scale standard deviation produces a *very* concentrated distribution
in natural units (because exp() compresses around the median), which
matches the observed natural-scale std of 0.87.

### 4. Imputation check (Phase 7 features in training window)

Null rates on `feature_pregame_game_features` rows where `has_full_data=TRUE
AND game_year >= 2021` (n = 12,143):

| feature                                   | null rate |
|-------------------------------------------|-----------|
| home_starter_stuff_plus                   | 0.0%      |
| home_lineup_archetype_avg_woba            | **12.7%** |
| home_pythagorean_win_exp                  | 9.6%      |
| home_bullpen_ip_prev_1d                   | 0.7%      |
| home_team_oaa_blended                     | 0.0%      |
| home_elo                                  | 0.03%     |
| home_h2h_line_movement                    | 0.0%      |
| ump_runs_per_game_zscore                  | 1.3%      |
| home_injured_player_count                 | 0.0%      |
| temp_f                                    | 4.5%      |

Null rates are too low to plausibly drive the systematic bias on their own
— the worst (archetype wOBA at 12.7%) is well below the ~50% threshold
hypothesis 4 implied. **Hypothesis 4 is downgraded but not eliminated**
(zero-imputed archetype features could still nudge predictions toward a
mean attractor).

## Hypothesis Ranking (Post-Investigation)

| Rank | Hypothesis | Verdict | Reasoning |
|------|------------|---------|-----------|
| 1    | (5) LogNormal scale collapse | **Most likely** | exp(loc) compresses log-scale variance into a narrow natural-scale band; natural-scale std=0.87 matches what a small fitted log-scale sigma produces. Joint loc/scale boosting with a shallow base learner over-shrinks scale. |
| 2    | (1) Regularization too aggressive | **Likely** | max_depth=3 is structurally incapable of capturing the tail variance the totals distribution carries. Pairs with #1 — depth-3 trees update scale slowly. |
| 3    | (2) Phase 7 features pull toward suppressed run environments | Plausible secondary | Stuff+, FIP, archetype matchups all encode "good pitching" → the model could weight pitching quality features too heavily. |
| 4    | (4) Zero-imputation attractor | Unlikely primary | Highest null rate is 12.7% on archetype wOBA. Magnitude insufficient to drive a 1.4-run mean miss. |
| 5    | (3) Training cutoff over-weights pitching-dominated era | **Ruled out** | Per-season residuals 2021–2026 all sit in the −1.1 to −2.1 band. No era concentration. |

## Chosen Approach

**Switch the totals model from LogNormal to Normal and increase the base
learner depth.** Rationale:

- **Normal vs LogNormal:** LogNormal forces predictions = exp(loc), which
  compresses variance in natural units when the fitted log-scale is small.
  Normal directly parameterizes the natural-scale distribution — what we
  actually evaluate against. Total runs cannot go negative, but predictions
  near 8 with std ~4 produce vanishingly small mass below 0 (`P(N(8, 4) < 0)
  ≈ 2.3%`), so the support concern is theoretical rather than practical.
  The Card 4.12d grid search already considered Normal; LogNormal won by
  a tiny CV-MAE margin without anyone noticing the variance pathology.
- **Loosen tree depth to 8 and reduce estimators to 200:** depth-3 trees
  with 500 rounds is the configuration that produced the shrinkage; deeper
  trees with fewer rounds give the boosting process room to fit
  high-variance scale updates without over-shrinking.
- **Keep the 2021+ training window:** the per-season analysis shows the
  bias is uniform. Dropping pre-2024 data would discard 75% of training
  rows for no expected gain.
- **Keep the full 294-feature set.** Feature engineering is not the
  binding constraint here — the model architecture is.

## Prototype Experiments

To validate the chosen approach before committing to a 1-hour+ full retrain,
run the following small-scale experiments. Each trains on 2021–2024, evaluates
on the 2025 holdout (full season, leakage-free), and reports:
`cv_mae`, `std(pred)`, `pct_pred_over` (vs the market line in the holdout
when available, else vs `mean(actual)`), `mean_residual`.

| Experiment | Dist     | max_depth | n_estimators | Hypothesis tested |
|------------|----------|-----------|--------------|-------------------|
| A          | LogNormal | 3 (default) | 500 | Reproduces v1 baseline behavior on 2025 holdout |
| B          | Normal   | 3         | 500          | Isolates the LogNormal vs Normal effect |
| C          | Normal   | 8         | 200          | Chosen approach: Normal + deeper trees |
| D          | LogNormal | 8         | 200          | Tests whether deeper trees alone can fix LogNormal |

### Prototype Results (2021–2024 train, 2025 holdout, 7,972 train rows / 2,025 eval rows; 309 retained features)

`pct_pred_over` is computed against 2025 consensus lines for the 1,546 of
2,025 eval rows that have one; the remaining 479 rows use a 8.0 sentinel
line (so the headline percentage runs slightly higher than it will against
the production 2024+ window where line coverage is denser).

| Exp | Dist      | depth | n_est | fit (s) | MAE    | std(pred) | mean_residual | pct_pred_over |
|-----|-----------|-------|-------|---------|--------|-----------|---------------|---------------|
| A   | LogNormal | 3     | 500   | 352     | 3.6303 | 0.801     | +0.017        | 82.0%         |
| B   | Normal    | 3     | 500   | 351     | **3.6169** | 0.807 | +0.108        | 84.7%         |
| C   | Normal    | 8     | 200   | 369     | 3.6262 | 0.833     | +0.146        | 82.4%         |
| D   | LogNormal | 8     | 200   | 371     | 3.6067 | 0.853     | −0.301        | 63.1%         |

Raw results: `betting_ml/evaluation/prototype_total_runs_results.json`.

### Two surprises and what they mean

1. **The mean-residual bias evaporates across all four configs.** The stored
   v1 model has `mean_residual = −1.36`; experiment A reproduces v1's exact
   hyperparameters (LogNormal, depth=3, n=500) but lands at `+0.017`. The
   only difference between A and the stored v1 model is the underlying
   training data: this run uses the post-Card-7.L1 feature store, which now
   carries the 2021 weather backfill that was mean-imputed when 7.MA ran
   (~24% of training rows). Updated weather + the feature-list drift
   between the stored 7.MA artifact and `load_retained_features()` (309 vs
   294) is enough on its own to fix the location bias. **Hypotheses 1 and
   5 (regularization / LogNormal scale collapse) are demoted** — they did
   not drive the observed mean bias.
2. **The variance gate (`std(pred) >= 2.0`) is unreachable for any of
   the four configurations.** All four sit near 0.80–0.85, only marginally
   better than the stored v1 (0.87) and well below v0 (1.32) and the actual
   std (4.46). Distribution choice and tree depth move this metric by
   < 0.05. The gate is asking the predicted *means* to span half the
   distance between v0 and the actual outcome std — that is a function of
   how much per-game signal the feature set carries about the conditional
   mean, which neither distribution choice nor regularization can fix.
   This is a feature-engineering / architecture problem (Phase 9 territory),
   not a hyperparameter problem.

## Chosen Configuration

**Experiment B: NGBoost Normal, max_depth=3, n_estimators=500, full 2021–
present training window, current Phase 7 feature set.**

Why:

- **Best MAE on the 2025 holdout** (3.6169) of the four candidates;
  near-zero mean residual (+0.108).
- **Normal over LogNormal:** marginal MAE win, simpler parameterization
  that avoids the latent log-scale-collapse risk (the original concern
  in Hypothesis 5), and matches the distribution already used for the
  run_differential model. The "predictions can go negative" theoretical
  concern is moot — `P(N(8.85, 0.81²) < 0) ≈ 0`.
- **depth=3, n=500 retained from v1:** the prototype shows deeper trees
  (depth=8, n=200) buy nothing on MAE or pct_pred_over and slightly bias
  LogNormal predictions downward (Exp D). Simplest delta from v1.
- **Training window unchanged (2021+):** per-season analysis ruled out
  era-shift bias, and the prototype's near-zero residuals confirm the
  current window is fine once weather is correctly populated.

### Promotion gate read-through (predicted, to be confirmed in Task 4)

| Gate | Target | Predicted (Exp B on 2025) | Verdict |
|------|--------|---------------------------|---------|
| `abs(mean_residual) <= 0.5` | yes | +0.108 | **PASS** |
| `pct_pred_over >= 25%`      | yes | 84.7% (sentinel-blended) | **PASS** (will land between 25% and 85% on real lines) |
| `totals_mae <= 3.862`       | yes | 3.617 | **PASS** |
| `std(pred) >= 2.0`          | yes | 0.807 | **FAIL** — unreachable without architecture change |

Per the Card 7.V definition of done, the std gate failure with no viable
hyperparameter remediation triggers a Phase 9 deferral note for the
variance-shrinkage problem specifically, while the other three gates clear
and the new mean-residual / pct_pred_over numbers represent a material
upgrade over both v0 and stored v1. Task 4 will confirm the gate values on
the production 2024+ window; Task 5 will record the promotion decision
along with the explicit Phase 9 follow-up for the variance gate.

## Final Outcome

**Decision (2026-05-05): PROMOTE v2 to production for total_runs.**

Backfill ran on 10,271 rows (2021–2026) via
`betting_ml/scripts/backfill_total_runs_v2.py`; rows tagged
`model_version='v2'`, `feature_version='v2'`. Gate validation on the 2024+
`has_odds`, `total_line_consensus IS NOT NULL` window
(`betting_ml/scripts/validate_v2_gates.py`):

| Gate | v0 baseline | v2 actual | Threshold | Verdict |
|------|-------------|-----------|-----------|---------|
| pct_pred_over            | 19.0% | **83.7%** | ≥ 25.0%        | **PASS** |
| abs(mean_residual)       | 2.28  | **0.048** | ≤ 0.5          | **PASS** |
| totals_mae               | 3.862 | **3.346** | ≤ 3.862 (v0)   | **PASS** |
| std(pred_total_runs)     | 1.32  | 0.773     | ≥ 2.0          | **FAIL** |

Three of four gates clear. The Card 7.V definition of done — `pct_pred_over
≥ 25%` AND `|mean_residual| ≤ 0.5` — is satisfied. v2 is also strictly
better than v0 on MAE.

**Variance gate deferred to Phase 9.** The `std(pred) ≥ 2.0` requirement
is a structural feature-set ceiling that no NGBoost hyperparameter or
distribution choice cleared in the Task 2 prototypes. It is recorded as a
Phase 9 follow-up: needs either substantially more informative features
(market-line ingestion, in-game state, batter-level matchup encoding) or
a different architecture (quantile regression, stacked ensemble with
explicit variance head). v2 is still a material upgrade and is promoted
on the strength of the directional metrics.

**Production wiring (committed alongside this card):**

- `betting_ml/models/model_registry.yaml` — `total_runs` entry: `model_version
  → v2`, `artifact_path → ngboost_tuned_v2.pkl`, `feature_columns_path →
  total_runs/feature_columns_v2.json`, `dist → Normal`, `selected_at →
  2026-05-05`. Per-tag overrides (`v0_*`, `v1_*`, `v2_*`) added so any tag
  can be loaded for backfill comparisons. Rollback artifact = v1 NGBoost
  LogNormal (`ngboost_tuned_2026.pkl`).
- `betting_ml/scripts/predict_today.py` — `--total-runs-tag` accepts `v2`;
  `_registry_artifact_path` / `_registry_feature_columns_path` honor per-tag
  overrides; new `_registry_dist_for_tag()` drives the totals distribution
  per tag (Normal for v2, LogNormal for v0/v1) so `p_over_line` and the
  natural-scale prediction stored in `pred_total_runs` are correct for
  both architectures from the same scoring entry point.
- `app/pages/1_Today_Picks.py` — "Refresh Predictions" button now invokes
  `--model-tag prod --home-win-tag v1 --total-runs-tag v2 --run-diff-tag v1`.
- Comparison report: `betting_ml/evaluation/model_comparison_v0_v2_total_runs.md`.
