# Minor League Dynasty Projection System
## Appendix B — Modeling, Translation Validation, and Calibration Protocol

**Policy:** `best_alpha = 0`

## 1. Pre-Registration Requirement

Every predictive component must define before fitting:

```yaml
target:
population:
supported_levels:
forecast_horizon:
candidate_classes:
direct_foil:
feature_groups:
ablations:
purge_window:
embargo_window:
cv_folds:
primary_score:
translation_correlation_gate:
calibration_floors:
degenerate_baselines:
multiple_testing_guard:
locked_holdout:
null_behavior:
selection_estimand:
selection_correction_candidates:
selection_sensitivity_rule:
```

No candidate may be added after inspecting holdout results without opening a new experiment family.

---

## 2. Time-Series Cross-Validation

Use forward-chaining, purged, embargoed folds.

Purging must remove:

- Overlapping player-season windows.
- Transition observations whose source period overlaps validation.
- Rolling features reaching across fold boundaries.
- Ranking snapshots published after the projection date.
- Park or league factors fit using the target period.

Embargo must account for:

- Stat corrections.
- Delayed promotions/transactions.
- Future-level observations used in target construction.
- Career outcome labels that mature later.

Evaluate separately by:

- Hitter/pitcher.
- Ladder step.
- Age band.
- Level.
- Forecast horizon.
- FV availability.
- Sample-size band.

---

## 3. Candidate Sets

### 3.1 K% and BB% translation

At least:

1. Hierarchical beta-binomial.
2. Regularized GAM.
3. CatBoost/LightGBM.
4. Dynamic state-space model.
5. Direct next-level empirical Bayes foil.

### 3.2 ISO translation

At least:

1. Hierarchical transformed Student-\(t\).
2. Tweedie/compound-count model.
3. Quantile gradient boosting.
4. Distributional boosting.
5. Fixed ladder foil.

### 3.3 SB attempt propensity

At least:

1. Hierarchical binomial opportunity model.
2. Regularized rate model.
3. Gradient-boosted rate model.
4. State-space model.
5. Direct fixed translation foil.

Preserve the existing 12-candidate bake-off as the evidence base.

### 3.4 SB success rate

Retain the existing null unless a new experiment clears all gates.

A presentation fallback may show:

- Observed success rate.
- League/level empirical interval.
- No translated stable-skill estimate.

### 3.5 Promotion and arrival

At least:

1. Discrete-time hazard model.
2. Gradient-boosted survival.
3. Random survival forest.
4. Competing-risk multi-state model.
5. Direct horizon classifier.

### 3.6 Starter probability

At least:

1. Hierarchical logistic usage model.
2. Gradient boosting.
3. Multi-state role transition.
4. Sequence model.
5. Direct classifier.

### 3.7 Career simulation foil

At least:

1. Fixed MLE + FV + CatBoost simulator.
2. Component posterior simulator.
3. Direct career-outcome distributional model.
4. Historical nearest-neighbor cohort model.

---

## 4. Translation Evidence Gate

For each component and ladder step, report:

- Out-of-sample Pearson and Spearman correlation.
- Attenuation-corrected correlation only as a secondary research statistic.
- CRPS or proper log score.
- Calibration intercept/slope.
- Randomized PIT.
- Improvement over all-mean, level-mean, and fixed-ladder baselines.
- Confidence interval on improvement.
- Stability across seasons.
- Sensitivity to promotion-selection correction.

A component is projected only when:

```text
proper_score_improvement > preregistered_minimum
AND translation_correlation_lower_bound > threshold
AND calibration_floor_passed
AND multiple_testing_adjusted_result_passed
AND selection_sensitivity_acceptable
```

Otherwise:

```text
UNPROJECTED_NULL
```

The threshold may differ by component, but it must be specified before evaluating the final holdout.

---

## 5. Primary Metrics

### 5.1 Distribution selection

Primary:

- CRPS for continuous or mixed distributions.
- Log predictive density / negative log likelihood where the likelihood is trustworthy.
- Brier score for discrete threshold events.

Diagnostics only:

- MAE.
- RMSE.
- Median absolute error.
- Rank correlation.

MAE and RMSE may reward a zero or mean collapse on highly skewed targets and cannot be the principal selector.

### 5.2 Mandatory degenerate ceiling

Every run scores:

- All-zero.
- All-mean.
- Level/age mean.
- No-development fixed ladder.
- FV-only base-rate model.
- Permanent CatBoost baseline.

If the candidate loses to a degenerate model, stop promotion. Do not relabel the failure as conservatism.

### 5.3 Coverage

Coverage is a floor.

Required examples:

- 50% interval meets minimum empirical coverage.
- 80% interval meets minimum empirical coverage.
- 90% interval meets minimum empirical coverage.

A model does not win by widening intervals indefinitely. Among models satisfying floors, compare CRPS and sharpness.

---

## 6. Multiple-Testing and Deflation

Use one or more:

- Nested time-series CV.
- Hansen SPA.
- White Reality Check.
- Bootstrap-adjusted confidence intervals.
- Deflated performance statistics based on trial count and correlation.
- Candidate-family limits.
- Minimum practical improvement.

Report the complete experiment count, including failed and abandoned candidates.

---

## 7. Per-Layer Calibration Gates

### Development layer

- Skill-change PIT.
- Age/level bias.
- Horizon variance growth.
- Oracle comparison using observed next-level skill.

### Promotion layer

- Time-dependent Brier score.
- Survival calibration.
- Competing-risk calibration.
- Oracle using actual current skill.

### MLB-arrival layer

- Horizon-specific reliability.
- Calibration by FV and level.
- Base-rate comparison.

### MLE layer

- CRPS.
- Translation correlation.
- PIT.
- Fixed-ladder comparison.

### Playing-time layer

- Zero-mass calibration.
- Conditional PA/IP distribution calibration.
- Hurdle decomposition.

### Dynasty-value layer

- End-to-end CRPS where outcomes have matured.
- Rank/tier stability as secondary diagnostics.
- Wide-horizon calibration.

No downstream success may excuse a failed upstream calibration gate.

---

## 8. Compounding-Error Tests

Run:

1. **Oracle upstream test:** Replace one upstream draw with realized truth.
2. **Frozen-baseline test:** Hold one layer at the simple baseline.
3. **Variance attribution:** Quantify posterior variance from each layer.
4. **Horizon inflation test:** Verify uncertainty grows with years.
5. **Null-component test:** Remove unvalidated components.
6. **Level-distance test:** Verify Single-A estimates are wider than Triple-A.
7. **FV ablation:** Quantify how much the board depends on FV.
8. **Box-score-only ablation:** Verify claims possible without FV.

---


### 8.1 Promotion-Selection Bias Diagnostic

For each component and ladder step, compare:

1. Promoted-only translation.
2. Inverse-probability-weighted translation.
3. Joint promotion-performance model.
4. Heckman/control-function correction where identification is defensible.
5. Minimum viable frontier-distance variance inflation.

Report:

- Difference in translated mean.
- Difference in translated variance.
- Difference in CRPS.
- Difference in translation correlation.
- Effective sample size after weighting.
- Sensitivity to weight truncation.
- Calibration by promotion-probability decile.
- Gap by age, level, FV band, and organization.
- Reclassification of null findings.

Define the selection gap:

\[
\Delta_{\text{selection}}
=
E[\hat Y^{\text{corrected}}-\hat Y^{\text{promoted-only}}]
\]

and report its distribution, not only its mean.

A component with a large or unstable selection gap must:

- Widen its posterior.
- Receive a lower trust classification.
- Avoid a strong “does not translate” interpretation.
- Remain unprojected if no corrected candidate clears the gate.

Null classifications:

```text
NULL_AFTER_SELECTION_CORRECTION
NULL_PROMOTED_SAMPLE_ONLY
INCONCLUSIVE_SELECTION_SENSITIVE
```

## 9. Mandatory Foil Ladder

At every version gate:

1. League-average prior.
2. Level/age base rate.
3. Fixed MLE.
4. Third-party FV/ranking only.
5. Fixed MLE + FV.
6. Fixed MLE + FV + CatBoost career simulator.
7. Full posterior.
8. For debut tests: MLB-only model after observed MLB sample.

A full posterior that fails to improve is not promoted.

---

## 10. End-to-End Recalibration

Use only out-of-fold predictions.

Candidate recalibrators:

- Quantile mapping.
- Isotonic distributional regression.
- Bayesian residual layer.
- Horizon-specific variance inflation.
- Level-specific mixture calibration.

The recalibrator itself is evaluated in a nested fold.

---


## 10A. FV Validation Fidelity

FanGraphs FV is evaluated retrospectively only when a contemporaneous snapshot exists.

Every fold records:

```text
fv_snapshot_timestamp
fv_snapshot_version
fv_validation_class
```

If no historical snapshot exists:

- The fold excludes FV.
- The FV-assisted model is evaluated only prospectively.
- Current FV is never substituted.
- The release report separates retrospective box-score performance from prospective FV-assisted performance.

## 11. Experiment Registry

Required tables:

```text
experiment
candidate
fold
prediction
metric
calibration_diagnostic
degenerate_comparison
translation_gate
release_decision
selection_correction_result
fv_snapshot_version
fv_validation_class
```

Every released projection can be traced to:

- Source data version.
- Feature version.
- Model version.
- Experiment family.
- Calibration version.
- Projection timestamp.
