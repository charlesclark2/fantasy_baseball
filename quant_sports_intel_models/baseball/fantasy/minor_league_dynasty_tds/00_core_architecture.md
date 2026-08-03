# Minor League Dynasty Projection System
## Technical Design Specification — Core Architecture

**Status:** Hardened design specification  
**Modeling policy:** `best_alpha = 0`  
**Production substrate:** S3 + Delta Lake + DuckDB  
**Current data boundary:** Affiliated Single-A through Triple-A box-score data from the MLB Stats API, plus admin-gated FanGraphs Future Value  
**Explicitly out of scope for V1:** Complex leagues, Dominican Summer League, and assumed access to non-public MiLB tracking data

---

## 1. Purpose

This system produces transparent probability distributions for minor-league dynasty players. It is not a recommendation engine and does not claim an edge, expected profit, or superior win rate.

The single source of truth is a versioned **latent player-skill posterior**. That posterior can support:

1. Dynasty prospect distributions.
2. Major League Equivalent distributions.
3. Promotion and MLB-arrival distributions.
4. Future-season playing-time and fantasy distributions.
5. A separately gated MLB-debut prior for downstream models.

The production architecture begins with the data that actually exists:

- MLB Stats API box-score statistics.
- A learned translation ladder from Single-A through Triple-A.
- FanGraphs Future Value, currently admin-gated.
- K%, BB%, ISO, stolen-base attempt propensity, and related box-score-derived features.
- S3/Delta Lake and DuckDB.

Tracking-derived concepts remain future candidates, not assumed inputs.

---

## 2. Product and Scientific Principles

### 2.1 Honest analytics

All user-facing numbers must expose uncertainty.

Allowed framing:

- “Estimated probability of reaching MLB: 42%, with a wide uncertainty interval.”
- “The posterior shifted upward after a promotion and improved strikeout translation.”
- “The model does not currently project stolen-base success rate because it failed the translation gate.”

Disallowed framing:

- “Draft this player.”
- “We have an edge.”
- “This player will beat consensus.”
- “Guaranteed breakout.”
- Any wagering or expected-profit claim.

### 2.2 A null is a result

A component is projected only when measured out-of-sample evidence supports translation.

If the strongest candidate ties or loses to the degenerate baseline, the component remains **unprojected**. The system records:

- Target tested.
- Candidate set.
- Evaluation period.
- Best proper score.
- Translation correlation.
- Degenerate comparison.
- Null conclusion.
- Next reconsideration date.

The existing stolen-base result is the canonical example:

- Attempt propensity translates.
- Success rate does not.
- The output should project opportunity and preserve uncertainty around efficiency rather than inventing a stable success-rate skill.

### 2.3 Trust varies by level

Projection trust is not uniform.

| Level | Relative trust | Reason |
|---|---:|---|
| Triple-A | Highest | Shortest MLB extrapolation; larger samples; closest competition |
| Double-A | High to moderate | Stronger prospect signal; still a meaningful translation step |
| High-A | Moderate | More development and role uncertainty |
| Single-A | Low to moderate | Longer horizon; thinner signal; more physical development |
| Complex / DSL | Lowest | Not currently ingested; longest extrapolation; weakest box-score signal |

V1 does **not** emit confident Complex/DSL dynasty values. Until those levels are ingested and independently validated, they should be labeled unsupported or scouting-only.

---

## 3. System Boundary

### 3.1 V1 supported cohort

- Affiliated Single-A
- High-A
- Double-A
- Triple-A
- Hitters and pitchers with valid player identity and sufficient box-score history
- FanGraphs FV range currently represented in the board: approximately 37–50

### 3.2 Unsupported or limited cohort

- Complex leagues
- Dominican Summer League
- Players without stable cross-season identity
- Players whose only evidence is an unlicensed or transient ranking
- Tracking-only attributes without an acquired source
- Very small samples that fail minimum posterior-information requirements

Unsupported players may appear with:

- Source-only scouting grade.
- “Insufficient statistical evidence.”
- Wide ordinal tier.
- No precise dynasty-value number.

---

## 4. High-Level Architecture

```text
MLB Stats API box-score facts
        +
FanGraphs FV snapshot
        +
Player / level / age / park context
        ↓
Point-in-time feature snapshot
        ↓
Translation bake-offs by component and ladder step
        ↓
Validated latent component posteriors
        ↓
Promotion / arrival / role posteriors
        ↓
Future-season career simulation
        ↓
Dynasty distribution and transparent explanations
```

The live betting integration is not part of the dynasty-serving path through V3.

```text
Dynasty posterior snapshots
        ↓
V4 shadow adapter
        ↓
Held-out debut validation
        ↓
Only after gate approval:
MLB debut prior in downstream serving
```

---

## 5. Canonical Latent State

### 5.1 Hitter state

```text
plate_discipline:
  strikeout_tendency
  walk_tendency

impact:
  isolated_power
  extra_base_hit tendency

running:
  stolen_base_attempt_propensity
  stolen_base_success_uncertainty

path:
  promotion_hazard
  mlb_arrival_hazard
  playing_time probability

context:
  level
  age_relative_to_level
  park
  organization
  FV
```

Contact rate, chase rate, exit velocity, launch angle, bat speed, sprint speed, and batted-ball shape are not production state variables until sourced and validated.

### 5.2 Pitcher state

V1 box-score state may contain:

```text
strikeout_tendency
walk_tendency
home_run_or_extra_base_damage proxy
starter_usage proxy
innings / workload distribution
promotion_hazard
mlb_arrival_hazard
FV
```

Pitch shape, velocity, spin, IVB, horizontal break, release traits, and command-location distributions require tracking or scouting data that is not currently available consistently.

---

## 6. Translation Ladder

The existing learned ladder remains the operational foundation:

```text
Single-A → High-A → Double-A → Triple-A → MLB
```

A direct Single-A-to-MLB model may be included as a foil, but no ladder step is assumed to work.

For component \(k\) and transition \(l \rightarrow l+1\):

\[
p(\theta_{i,l+1,k}\mid X_{i,l}, D_{\le t})
\]

is fitted only with information available at the historical projection timestamp.

### 6.1 Translation gates

A component advances only when all are true:

1. Best candidate improves out-of-sample CRPS or log score over degenerate baselines.
2. Translation correlation clears a pre-registered minimum and confidence interval.
3. Calibration floors are met.
4. Performance is not concentrated in one season or organization.
5. Purged/embargoed CV remains positive.
6. Multiple-testing adjustment does not erase the result.
7. The feature is available at the actual projection timestamp.

Otherwise:

```text
translation_status = UNPROJECTED_NULL
```

### 6.2 Lowest-minor caution

Signal attenuation should be modeled explicitly. A translated estimate from Single-A must have wider posterior variance than an otherwise equivalent Triple-A estimate.

Potential structure:

\[
\sigma^2_{\text{posterior}}
=
\sigma^2_{\text{sampling}}
+
\sigma^2_{\text{translation}}
+
\sigma^2_{\text{development}}
+
\sigma^2_{\text{level distance}}
\]

---


## 6A. Translation Estimand and Promotion-Selection Bias

The observed ladder-step translation sample is selected.

For a transition such as Double-A → Triple-A, next-level outcomes are observed only for players who were actually promoted. Therefore, the naive estimand is:

\[
p(Y_{i,l+1}\mid X_{i,l},\text{Promoted}_{i,l\rightarrow l+1}=1)
\]

The production use case is different:

\[
p(Y_{i,l+1}\mid X_{i,l})
\]

for a population that includes players who have not yet been promoted.

This distinction must be stated plainly:

> **The raw translation estimate is conditional on promotion but is applied to an unpromoted population.**

Purged and embargoed cross-validation prevents temporal leakage. It does not remove this selection bias.

### 6A.1 Why It Matters

Promotion depends on information that may overlap with or exceed the modeled box-score features:

- Underlying talent.
- Defense.
- Health.
- Scouting information.
- Organization depth.
- Player-development judgment.
- 40-man and roster constraints.
- Work ethic or makeup information not present in the dataset.
- Unobserved tracking or internal club data.

Consequences include:

- Translation slopes may be biased.
- Posterior means may be too optimistic near the lower tail.
- Posterior variance may be too narrow.
- A “does not translate” result may partly reflect selection into the observed sample.
- Effects may differ by level because the promotion frontier is different at Single-A, Double-A, and Triple-A.

The current stolen-base success-rate null should remain the operational result, but future research must test whether selection correction changes the conclusion before interpreting the null as purely biological or skill-based non-translation.

### 6A.2 Approved Correction Strategies

At least one correction strategy must be evaluated for every ladder step.

#### Joint promotion-performance model

Preferred when computationally practical:

\[
P(S_i=1\mid X_i,U_i)
\]

\[
p(Y_{i,l+1}\mid X_i,U_i,S_i=1)
\]

where \(S_i\) is promotion and \(U_i\) is a shared latent factor influencing both promotion and next-level performance.

This can be implemented as:

- Shared-random-effect Bayesian model.
- Joint multi-state development model.
- Selection model with correlated promotion and performance residuals.
- Competing-risk transition model with conditional next-level outcomes.

#### Inverse-probability-of-promotion weighting

Estimate:

\[
\hat p_i=P(S_i=1\mid X_i)
\]

and weight promoted observations by:

\[
w_i=\frac{1}{\hat p_i}
\]

Use stabilized and truncated weights to avoid extreme variance. Report effective sample size and sensitivity to truncation.

This approach addresses selection only under measured confounding assumptions. It does not solve selection on unobserved club information.

#### Heckman-style or control-function correction

Model promotion selection and include a correction term in the next-level outcome model.

This is appropriate only when identification assumptions are documented and plausible. Any proposed exclusion restriction must be defended rather than assumed.

#### Minimum viable sensitivity correction

If none of the above is credible for a component:

1. Quantify distance from the promotion frontier.
2. Compare the prospect with promoted and non-promoted peers.
3. Inflate posterior variance as frontier distance increases.
4. Label the estimate as conditional-on-promotion extrapolation.
5. Avoid precise point estimates for cohorts far from observed promoted players.

### 6A.3 Operational Output

Every translated component stores:

```text
translation_estimand
selection_correction_method
promotion_model_version
promotion_probability
selection_gap_estimate
selection_sensitivity_status
variance_inflation_factor
```

Allowed `selection_sensitivity_status` values:

- `LOW`
- `MODERATE`
- `HIGH`
- `UNIDENTIFIED`

A high or unidentified selection gap should widen the posterior and reduce the displayed trust tier.

### 6A.4 Null Interpretation

A failed translation gate remains a valid operational null, but the research conclusion must distinguish:

- `NULL_AFTER_SELECTION_CORRECTION`
- `NULL_PROMOTED_SAMPLE_ONLY`
- `INCONCLUSIVE_SELECTION_SENSITIVE`

Only the first supports a strong claim that the component itself does not translate.

## 7. Component Candidate Sets

Every predictive target uses at least three candidate classes plus a direct foil. Detailed registration appears in the validation document.

### 7.1 K% and BB%

Candidates:

1. Hierarchical beta-binomial or binomial-logit model.
2. Regularized generalized additive model.
3. CatBoost or LightGBM rate model.
4. Dynamic state-space model.
5. Direct next-level rate foil.

### 7.2 ISO / power proxy

Candidates:

1. Hierarchical transformed-normal or Student-\(t\) model.
2. Tweedie or compound-count formulation.
3. Quantile gradient boosting.
4. Distributional CatBoost.
5. Direct next-level ISO foil.

### 7.3 Stolen-base attempt propensity

Candidates should preserve the existing 12-candidate work and its validated result. Attempt propensity may be translated if it continues to clear gates.

### 7.4 Stolen-base success rate

Current status:

```text
UNPROJECTED_NULL
```

The model may expose league-average or empirical uncertainty conditional on attempts, but it must not present success rate as a stable translated skill until new evidence overturns the null.

### 7.5 Promotion and MLB-arrival hazard

Candidates:

1. Discrete-time logistic hazard.
2. Gradient-boosted survival model.
3. Random survival forest.
4. Multi-state Markov or competing-risk model.
5. Direct “MLB by horizon” classifier foil.

### 7.6 Starter probability

Candidates:

1. Hierarchical logistic model using starts, innings, and workload.
2. Gradient-boosted classifier.
3. Multi-state starter/reliever transition model.
4. Sequence model over appearances.
5. Direct future-role classifier.

With box-score data alone, this is a usage projection, not a pitch-quality projection.

---

## 8. Development and Career Simulation

For each posterior draw:

1. Sample current translated skill.
2. Sample component-specific development.
3. Sample next-level transition.
4. Sample promotion, demotion, injury interruption, release, or persistence.
5. Sample MLB arrival.
6. Sample role and playing time.
7. Generate season-level fantasy categories.
8. Apply league-specific eligibility and retention rules.
9. Preserve the full trajectory.

The simulator must retain dependence between:

- Arrival and playing time.
- Playing time and counting stats.
- Power and strikeout uncertainty.
- Level and translation variance.
- Role and workload.
- League retention and organization changes.

---

## 9. Layer Calibration and Compounding-Error Controls

The forecast chain compounds error across both layers and years:

```text
development → promotion → arrival → MLE → playing time
→ dynasty scoring → future seasons
```

Each layer must pass its own gate before composition.

### 9.1 Per-layer gates

- CRPS or proper log score improvement.
- Randomized-PIT diagnostics for counts/discrete distributions.
- Calibration intercept and slope.
- Coverage as a floor.
- Sharpness conditional on the floor.
- Oracle anchor using realized upstream information.
- All-zero, all-mean, and simple historical degenerate anchors.
- Stability by level, age band, position, and horizon.

### 9.2 Horizon degradation

Calibration is evaluated separately for:

- Rest of current season.
- One year.
- Two years.
- Three years.
- Four-plus years.

Long-horizon uncertainty must widen. A model that preserves narrow intervals at four years because its mean is stable fails the design.

### 9.3 End-to-end recalibration

The composed career simulation is recalibrated using only out-of-fold predictions. Candidate methods include:

- Quantile mapping.
- Isotonic distributional regression.
- Bayesian residual correction.
- Horizon-specific variance inflation.
- Mixture recalibration by level.

---

## 10. Permanent Baseline Foil

The permanent baseline is:

```text
fixed learned MLE ladder
+ FanGraphs FV
+ box-score context
+ CatBoost career simulation
```

This baseline is never retired. Every Bayesian or component-rich version must beat or meaningfully complement it out of sample.

Mandatory foil ladder:

1. Degenerate all-zero / all-mean.
2. Level/age historical base rate.
3. Fixed MLE.
4. Fixed MLE + FanGraphs FV.
5. Fixed MLE + FV + CatBoost career simulation.
6. Full posterior system.

If the full posterior does not improve proper scores, calibration, or materially useful transparency, the baseline remains primary.

---

## 11. User-Facing Dynasty Outputs

Every point estimate must appear with distribution context.

### 11.1 Required display structure

```json
{
  "probability_reaches_mlb": {
    "median_estimate": 0.42,
    "credible_interval_80": [0.22, 0.63],
    "data_trust": "moderate",
    "supported_level": "Double-A"
  },
  "mlb_debut": {
    "median_season": 2028,
    "probability_by_season": {
      "2027": 0.11,
      "2028": 0.34,
      "2029": 0.51
    }
  },
  "peak_hr": {
    "median": 17,
    "p10": 4,
    "p90": 30,
    "conditional_on_500_pa": true
  }
}
```

### 11.2 Precision rules

- Percentages may be rounded to whole points for low-trust cohorts.
- Dates should be seasons or broad windows unless upper-minors evidence supports greater precision.
- Peak-category outputs must state whether they are conditional on MLB arrival and playing time.
- Expected dynasty value must include median, interval, and probability of positive value.
- Complex/DSL players do not receive precise box-score-derived values in V1.
- Any output whose translation is null must state “not currently projected.”

### 11.3 Probability-shift explanations

Explanations attribute changes; they do not recommend actions.

Allowed:

> “The probability of reaching MLB increased from 31% to 38%. The largest contributors were promotion to Double-A, a lower translated K% distribution, and a newer FV snapshot.”

Not allowed:

> “The model says to draft him now.”

Every explanation should identify:

- Previous posterior.
- Current posterior.
- Data timestamp.
- Major attribution factors.
- Remaining uncertainty.
- Whether the movement came from performance, FV, level, or model-version change.

---

## 12. Version Roadmap

### V0 — Data-source audit

Before new modeling:

- Reproduce every current feature from source.
- Verify point-in-time availability.
- Retain immutable raw captures.
- Audit player IDs and level mappings.
- Measure missingness by level and season.
- Document FanGraphs acquisition and usage rights.
- Determine whether true historical point-in-time FanGraphs Board/FV snapshots exist for each backtest period.
- Classify FV as `RETROSPECTIVELY_VALIDATED`, `PROSPECTIVELY_SHADOW_VALIDATED`, or `NOT_VALIDATED`.
- Prohibit joining current FV into historical rows when a contemporaneous snapshot does not exist.
- Identify unsupported fields.
- Build a feature registry with activation status.

### V1 — Existing production baseline hardened

- Single-A through Triple-A only.
- Box-score + FV minimum viable set.
- Learned ladder translations.
- Bake-off discipline for every component.
- CRPS-primary validation.
- Degenerate tripwires.
- Null outputs where translation fails.
- Permanent CatBoost baseline.

### V2 — Expanded box-score posterior

- Dynamic partial pooling.
- Competing-risk promotions.
- Role and playing-time mixtures.
- Horizon-specific calibration.
- Better park/league/year context.
- No assumed tracking.

### V3 — Standalone dynasty board

- Full career simulations.
- League-specific dynasty valuation.
- Honest UI distributions.
- Explanation and data-trust layer.
- Production board remains independent of live betting serving.

### V4 — Separately gated MLB-debut prior

- Shadow-only adapter.
- Held-out debut evaluation.
- Mandatory foil ladder.
- Distribution widening for sparse/no MLB evidence.
- No serving activation until the V4 release gate is approved.

---

## 13. Infrastructure

### 13.1 Storage and compute

- Amazon S3 as durable object storage.
- Delta Lake for versioned bronze, silver, gold, feature, posterior, and evaluation tables.
- DuckDB for local development, validation, and analytical workloads.
- Polars for feature engineering.
- Dagster for orchestration.
- dbt where SQL transformation ownership is useful.
- PyMC, Stan, NumPyro, or empirical-Bayes implementations for posterior models.
- CatBoost/LightGBM for permanent foils.
- ArviZ for posterior diagnostics.
- MLflow or a Delta-backed model registry for versioning.

Snowflake is not part of the target state.

### 13.2 Required temporal columns

```text
player_id
source_name
source_record_id
source_timestamp
capture_timestamp
feature_timestamp
projection_timestamp
model_version
data_version
license_status
fv_snapshot_version
selection_correction_version
```

The pipeline fails closed when a feature lacks point-in-time provenance.

---

## 14. Release Criteria

A version may ship only if:

- All activated features pass V0 provenance, including point-in-time FV availability.
- All predictive components have registered candidate sets.
- CRPS/proper-score evaluation is complete.
- Degenerate tripwires are passed.
- Null translations are preserved and labeled for selection sensitivity.
- Layer calibration floors are met.
- Full system is compared with the permanent baseline.
- Selection-bias diagnostics are completed for each activated ladder step.
- User-facing outputs meet precision and language rules.
- No unsupported tracking field is silently imputed as observed.
