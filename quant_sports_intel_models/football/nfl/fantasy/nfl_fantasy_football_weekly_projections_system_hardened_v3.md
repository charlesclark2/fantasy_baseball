# NFL Fantasy Football Weekly Projections System

The strongest design is **not one model that directly predicts fantasy points**. Build a probabilistic system that models:

1. **Will the player be active?**
2. **How much will the player play?**
3. **What opportunities will the player receive?**
4. **What will happen on those opportunities?**
5. **How do those events translate into fantasy scoring?**

That decomposition gives you better interpretability, more realistic uncertainty, and the ability to adjust projections rapidly when injuries, depth charts, weather, or betting markets change.

> **Product constraint — honest analytics (`best_alpha = 0`)**
>
> User-facing outputs describe calibrated probabilities, ranges, assumptions, and data freshness. They must never be framed as betting edges, guaranteed advantages, market-beating claims, or instructions to place wagers or lineups. Historical decision metrics may appear only as clearly labeled backtest context.

> **Buildability constraint**
>
> No feature is part of the production architecture until its source, license, historical depth, publication lag, refresh cadence, timestamp semantics, and fallback have been audited. Features that cannot be obtained legally and reliably at the projection timestamp are aspirational.


## 1. Recommended Modeling Architecture

A useful structure is:

\[
\text{Fantasy Points}
=
f(\text{Playing Time},\text{Opportunity},\text{Efficiency},\text{TDs},\text{Scoring Rules})
\]

For each player-week, generate a **posterior predictive distribution**, not merely a point estimate:

\[
p(Y_{i,w} \mid X_{i,w}, \mathcal{D})
\]

where:

- \(Y_{i,w}\) is player \(i\)'s fantasy score in week \(w\)
- \(X_{i,w}\) contains matchup, role, team, injury, weather, and market features
- \(\mathcal{D}\) is historical information
- The output is a distribution of possible fantasy scores

A practical pipeline:

```text
Game environment
      ↓
Team play volume and scoring
      ↓
Player availability and snap share
      ↓
Player opportunity share
      ↓
Opportunity efficiency
      ↓
Touchdown allocation
      ↓
Fantasy scoring simulation
```

## 2. Model the Game Environment First

Before projecting individual players, estimate the overall offensive environment. Every sub-model is a **pre-registered bake-off**, not a hardcoded distributional decision.

### 2.1 Common Bake-Off Protocol

For every target:

- Pre-register at least three structurally different model classes.
- Include a direct-learned foil predicting the same target or downstream fantasy distribution.
- Pre-register feature groups and ablations.
- Use purged, embargoed, forward-chaining time-series cross-validation.
- Select primarily on out-of-sample CRPS.
- Require the layer-specific calibration gates in §10.
- Apply a multiple-testing or deflation guard.
- Preserve a locked final holdout period.

Suitable guards include nested time-series CV, White's Reality Check, Hansen's SPA test, bootstrap confidence intervals on candidate-minus-foil CRPS, and a minimum practical improvement threshold.

### 2.2 Team Play Volume

Targets include offensive plays, drives, dropbacks, rush attempts, red-zone plays, goal-line opportunities, sacks allowed, and team touchdowns.

**Pre-registered candidates:**

1. Poisson or quasi-Poisson GLM.
2. Negative-binomial or generalized-Poisson hierarchical model.
3. Distributional gradient boosting.
4. Bayesian additive regression trees or another nonlinear Bayesian model.
5. Direct-learned foil predicting the full team-volume vector or final player fantasy distribution.

A negative-binomial model is a reasonable overdispersion hypothesis, not a decision to hardcode.

### 2.3 Pass Rate and Rush Rate

Candidate inputs include neutral pass rate, pass rate over expectation, score differential, expected game script, quarterback, coordinator, opponent tendencies, line availability, and weather.

**Pre-registered candidates:**

1. Binomial logistic hierarchical model.
2. Beta-binomial or logistic-normal rate model.
3. Multinomial pass/designed-rush/scramble/sack model.
4. Distributional gradient boosting.
5. Direct-learned attempts or fantasy-points foil.

A candidate formulation is:

\[
\text{PassAttempts}_g \sim \text{Binomial}(\text{DropbackOpportunities}_g,p_g)
\]

\[
\text{logit}(p_g)=X_g\beta+u_{\text{team}}+u_{\text{coach}}+u_{\text{QB}}
\]

It must win out of sample rather than being assumed correct.

## 3. Model Player Availability and Playing Time

This is one of the largest sources of weekly projection error.

Distinguish:

- Probability of being active
- Probability of starting
- Expected snap share conditional on playing
- Route participation
- Backfield participation
- Possibility of an in-game workload limitation

For an injured player:

\[
p(Y)
=
P(\text{inactive})p(Y\mid\text{inactive})
+
P(\text{active})p(Y\mid\text{active})
\]

Because \(Y=0\) when inactive:

\[
p(Y)
=
[1-P(\text{active})]\delta_0
+
P(\text{active})p(Y\mid\text{active})
\]

A questionable player with a 70% probability of playing and 16 expected points if active does not have the same risk profile as a healthy player projected for 11.2 points, even though both have approximately the same unconditional mean.

### Playing-Time Features

- Snap share over the last 1, 3, 5, and 8 games
- Route participation
- Routes per team dropback
- First-read participation
- Two-minute offense participation
- Third-down participation
- Red-zone participation
- Goal-line participation
- Personnel grouping usage
- Formation and alignment
- Depth-chart position
- Teammate injuries
- Practice participation
- Days since injury
- Historical workload after similar injury designations

Roles change faster than talent. Recent utilization should usually receive more weight than recent fantasy scoring.

## 4. Model Player Opportunity by Position

### Quarterbacks

Model:

- Dropbacks
- Pass attempts
- Completions
- Passing yards
- Passing touchdowns
- Interceptions
- Scrambles
- Designed rushes
- Rushing yards
- Rushing touchdowns
- Sacks and fumbles, depending on scoring

Useful features:

- Team implied points
- Spread
- Neutral pass rate
- Pace
- Offensive line pass-blocking performance
- Pressure rate allowed
- Opponent pressure rate
- Opponent man/zone rate
- Blitz rate
- Coverage shell
- Receiver separation or receiving talent
- Quarterback depth of target
- Completion percentage over expectation
- Scramble rate under pressure
- Designed-run rate
- Red-zone pass/run tendencies

Quarterback rushing should be modeled independently from passing.

### Running Backs

Model:

- Carries
- Targets
- Receptions
- Rushing yards
- Receiving yards
- Red-zone carries
- Goal-line carries
- Touchdowns

Key features:

- Snap share
- Carry share
- Target share
- Route participation
- Short-yardage role
- Goal-line role
- Two-minute role
- Third-down role
- Team rushing volume
- Expected game script
- Offensive line run-blocking
- Yards before contact
- Box counts
- Defensive front quality
- Teammate availability
- Coach rotation tendencies

Do not treat "RB1" as a sufficient description. A player may be the early-down back, passing-down back, goal-line back, or two-minute back.

### Wide Receivers and Tight Ends

Model:

- Routes
- Targets
- Receptions
- Air yards
- Receiving yards
- End-zone targets
- Touchdowns

Natural hierarchy:

\[
\text{Routes}
\rightarrow
\text{Targets}
\rightarrow
\text{Receptions}
\rightarrow
\text{Yards}
\rightarrow
\text{Touchdowns}
\]

Important features:

- Route participation
- Target share
- Targets per route run
- First-read target share
- Air-yard share
- Average depth of target
- End-zone target share
- Red-zone target share
- Slot versus perimeter alignment
- Motion rate
- Man versus zone splits
- Coverage matchup
- Cornerback alignment
- Defensive coverage tendencies
- Quarterback accuracy by target depth
- Receiver separation and contested-catch ability
- Teammate injuries
- Double-team or bracket rates, where available

For tight ends, blocking responsibilities can materially alter route participation.


## 4A. Kickers and Team Defense/Special Teams

Kickers and team defense/special teams are first-class projection targets. They are starting roster slots in most standard formats and have distinct data-generating processes.

### 4A.1 Kicker Model

Model kicker scoring through:

```text
Team drives → drive outcomes → field-goal opportunities
→ attempt distance band → distance-conditional make probability
→ extra-point opportunities → misses → league scoring
```

Targets:

- Field-goal attempts
- Field goals made by distance band
- Extra-point attempts and makes
- Misses
- Longest field goal where relevant
- Kicker fantasy points

Retain exact kick distance, then map it to each league's scoring bands.

Candidate features include team drives, red-zone entry and touchdown conversion, fourth-down aggressiveness, score differential, stadium, surface, wind, temperature, kicker historical make rate by distance, opponent drive suppression, and team field-goal decision tendencies.

#### Kicker Bake-Offs

Field-goal attempt volume:

1. Poisson or negative-binomial count model.
2. Hurdle count model.
3. Distributional gradient boosting.
4. Hierarchical drive-outcome model.
5. Direct kicker-points foil.

Distance-band allocation:

1. Multinomial logistic.
2. Logistic-normal composition.
3. Sequential field-position model.
4. Gradient-boosted multiclass model.
5. Direct band-count foil.

Make probability:

1. Hierarchical binomial by distance.
2. GAM with distance and weather.
3. Gradient-boosted classifier.
4. Dynamic kicker-skill model.
5. League-average distance curve foil.

Extra points receive a separate candidate set.

### 4A.2 Team Defense/Special Teams Model

Model:

- Sacks
- Interceptions
- Fumble recoveries
- Defensive touchdowns
- Special-teams touchdowns
- Safeties
- Blocked kicks
- Points allowed
- Yards allowed

Candidate features include opponent dropbacks, sack and turnover tendencies, quarterback availability, offensive-line injuries, defensive efficiency, pace, game script, weather, and return-unit information where available.

#### DST Bake-Offs

Sacks and takeaways:

1. Poisson/negative-binomial hierarchical model.
2. Zero-inflated or hurdle count model.
3. Distributional gradient boosting.
4. Shared latent pressure/turnover model.
5. Direct DST-points foil.

Defensive/special-teams touchdowns:

1. Bernoulli or zero-inflated count model.
2. Hierarchical rare-event logistic model.
3. Gradient-boosted rare-event classifier.
4. Compound model conditional on takeaways/returns.
5. Historical base-rate foil.

Safeties and blocks:

1. Hierarchical rare-event model.
2. Team/opponent empirical Bayes.
3. Gradient-boosted classifier if sample permits.
4. League-average foil.

### 4A.3 Exact Tier Scoring

Points-allowed and yards-allowed scoring are step functions. Never project a point estimate and pass it through a tier table.

Model bucket probabilities:

\[
P(B^{PA}=b \mid X), \qquad P(B^{YA}=b \mid X)
\]

Then apply the exact league table:

\[
E[S^{PA}] = \sum_b s_b^{PA}P(B^{PA}=b)
\]

\[
E[S^{YA}] = \sum_b s_b^{YA}P(B^{YA}=b)
\]

Candidate bucket models:

1. Ordered logistic/probit.
2. Multinomial logistic.
3. Full points/yards distribution integrated over bucket boundaries.
4. Distributional gradient boosting.
5. Direct bucket classifier.
6. Direct DST-points foil.

The simulator retains actual simulated points and yards so any league's tier table can be applied exactly.

### 4A.4 Data Tiers

Most K and DST V1 inputs are Tier 0 from play-by-play, game stats, weather, and the existing team/opponent model.

Paid enhancements include detailed pressure attribution, blocking grades, return-unit charting, and special-teams personnel quality. These are optional later-tier features, not V1 requirements.

## 5. Use Joint Opportunity Modeling Where It Earns Its Complexity

Player opportunities are dependent, but no compositional family is presumed correct.

**Pre-registered candidates:**

1. Dirichlet-multinomial allocation.
2. Logistic-normal multinomial allocation.
3. Hierarchical sequential allocation: team volume → participation → opportunity probability.
4. Multivariate distributional boosting with reconciliation constraints.
5. Independent player models followed by deterministic or probabilistic reconciliation.
6. Direct fantasy-points foil that bypasses the share layer.

A Dirichlet candidate is:

\[
(\pi_1,\ldots,\pi_K)\sim\text{Dirichlet}(\alpha_1,\ldots,\alpha_K)
\]

\[
(T_1,\ldots,T_K)\sim\text{Multinomial}(T_{\text{team}},\pi)
\]

Apply the same bake-off discipline to targets, carries, red-zone carries, goal-line carries, end-zone targets, touchdowns, and uncertain quarterback usage.

## 6. Feature Engineering Framework


### Data-Tier Gating

- **Tier 0 — free/public:** nflverse play-by-play, schedules, rosters, public depth-chart snapshots, weekly/player stats, public snap counts where available, public injury reports, public weather, and internally derived metrics.
- **Tier 1 — self-service paid:** archived odds, production weather forecast archives, and exports whose licenses permit product use.
- **Tier 2 — contracted charting/tracking:** FTN Data API, PFF B2B, Sports Info Solutions, Sportradar subjective statistics, Genius/NFL Next Gen Stats licensing, or equivalent.
- **Tier 3 — proprietary derived tracking:** internally created features from licensed raw tracking or film charting.

The following features **gate V2/V3** and are not assumed available from free play-by-play:

- Route participation and routes per dropback
- Targets per route run when routes are unavailable
- First-read target share
- Reliable air-yard share and aDOT
- Coverage shell, two-high rate, man/zone, and bracket/double-team rate
- Detailed pressure and blocking attribution
- Defensive box counts
- YAC over expectation
- Full CPOE/tracking-derived completion difficulty
- Receiver separation
- Detailed personnel, formation, motion, alignment, and assignment charting

Without an executed vendor agreement or a legally reviewed internal charting process, these are aspirational and cannot gate V1.


Organize the feature store into six families.

### Player Ability

- Targets per route run
- Yards per route run
- Reception probability
- Yards after catch over expectation
- Air yards per target
- Rushing yards over expectation
- Yards after contact
- Missed tackles forced
- Success rate
- EPA per opportunity
- Quarterback completion percentage over expectation
- Pressure-to-sack rate
- Scramble rate
- Touchdown conversion ability

Apply empirical Bayes or partial pooling for small samples.

### Recent Role and Usage

Use recency-weighted features:

\[
x_t^{EWMA}
=
\lambda x_t+(1-\lambda)x_{t-1}^{EWMA}
\]

Build multiple decay rates:

- Fast-decay utilization
- Medium-decay form
- Slow-decay talent

Examples:

- Snap share EWMA
- Route share EWMA
- Target share EWMA
- Carry share EWMA
- Red-zone share EWMA
- Two-minute participation EWMA

### Team Environment

- Pace
- Situation-neutral pace
- Pass rate over expectation
- No-huddle rate
- Seconds per snap
- Early-down pass rate
- Fourth-down aggressiveness
- Red-zone efficiency
- Offensive line continuity
- Team EPA
- Drive success
- Coordinator and play-caller identity
- Coaching changes
- Home/away
- Travel and rest

### Opponent Matchup

Prefer opponent-adjusted, shrinkage-based features over raw fantasy points allowed by position:

- Defensive EPA by play type
- Success rate allowed
- Pressure rate
- Blitz rate
- Man/zone rate
- Two-high coverage rate
- Explosive-play rate allowed
- Defensive aDOT allowed
- Yards after catch allowed
- Rush EPA by gap or direction
- Light-box frequency
- Red-zone touchdown rate
- Pace induced on opponents

### Game Environment and Markets

- Game total
- Team implied total
- Point spread
- Moneyline
- Movement from opening line
- Player props
- Passing-yard props
- Rushing-yard props
- Receiving-yard props
- Reception props
- Anytime touchdown odds

Use only the market information available at the exact projection timestamp.

Player props can be treated as model features, informative priors, a benchmark ensemble member, or a calibration anchor.

### Context and Availability

- Injury designation
- Practice participation
- Injury type
- Days since injury
- Teammate injuries
- Offensive line injuries
- Weather
- Dome/outdoor
- Wind
- Temperature
- Precipitation
- Surface
- Rest days
- Short week
- International game
- Travel distance

Wind should interact with target depth and kicking rather than applying a uniform penalty to every offensive player.

## 7. Bayesian Modeling Opportunities

Bayesian inference is especially valuable because fantasy football data is sparse, hierarchical, nonstationary, highly conditional, and affected by uncertain availability.

### Hierarchical Player Effects

For receiver target rate:

\[
\text{Targets}_{i,g}
\sim
\text{Binomial}(\text{Routes}_{i,g},p_{i,g})
\]

\[
\text{logit}(p_{i,g})
=
X_{i,g}\beta
+
\alpha_i
+
\gamma_{\text{team}}
+
\eta_{\text{QB}}
\]

\[
\alpha_i
\sim
N(\mu_{\text{position}},\sigma_{\text{position}})
\]

A receiver with 20 career routes is pulled strongly toward the population mean. A receiver with 2,000 routes is driven primarily by his own evidence.

Possible hierarchy:

```text
League
 └── Position
      └── Archetype
           └── Player
```

### Dynamic Latent Ability

\[
\theta_{i,t}
\sim
N(\theta_{i,t-1},\sigma_{\text{evolution}})
\]

\[
y_{i,t}
\sim
p(y\mid \theta_{i,t},X_{i,t})
\]

This permits gradual development or decline while avoiding overreaction to one game.

### Informative Priors

Potential sources:

- Previous-season performance
- Multi-year player ability
- Draft capital
- Age
- Position
- Combine metrics
- Prospect models
- Coaching history
- Vegas props
- Expert consensus projections

### Bayesian Updating During the Week

```text
Monday:
Prior based on long-term ability and expected role

Wednesday:
Update for initial practice status

Friday:
Update for final practice participation and injury designation

Sunday morning:
Update for inactive lists, weather and betting markets
```

## 8. Generate Probability-Based Outcomes Through Simulation

For each simulated game:

1. Sample whether each player is active.
2. Sample team play volume.
3. Sample pass/rush allocation.
4. Sample player snap and route participation.
5. Allocate carries and targets.
6. Sample completions, yards, touchdowns, turnovers, and bonuses.
7. Apply league scoring.
8. Store every player's fantasy score.

Repeat 10,000-50,000 times per slate.

Outputs:

- Mean projection
- Median projection
- Standard deviation
- 10th, 25th, 75th, and 90th percentiles
- Probability of exceeding 10, 15, 20, or 25 points
- Probability of finishing as QB1, RB1, WR1, and so forth
- Probability of beating another player
- Probability of beating consensus
- Floor and ceiling estimates
- Conditional projection if active
- Unconditional projection including inactive risk

Example:

```json
{
  "player": "Example WR",
  "mean": 16.8,
  "median": 15.1,
  "p10": 5.4,
  "p25": 9.8,
  "p75": 21.7,
  "p90": 29.6,
  "prob_15_plus": 0.51,
  "prob_20_plus": 0.31,
  "prob_top_12_wr": 0.38,
  "prob_active": 0.94
}
```

## 9. Preserve Correlations


### 9.1 Joint-Distribution Validation

Marginal CRPS and PIT cannot validate correlation. The joint distribution must be tested for:

- QB–WR and QB–TE stacks
- WR–WR and RB–RB competition
- QB–opposing receiver bring-backs
- Game-script relationships
- DST–opposing offense
- Kicker–team offense
- Same-game and full-lineup totals

Required diagnostics:

- Realized versus simulated joint exceedance probabilities
- Pairwise covariance and correlation error
- Conditional distributions such as \(P(Y_{WR}>20 \mid Y_{QB}>25)\)
- Energy score
- Variogram score
- Multivariate rank histograms
- Pairwise and lineup-level credible-region coverage
- Tail-dependence diagnostics
- Lineup-total CRPS

The latent game variable \(z_g\) must be checked against realized game-level residuals in plays, scoring, passing volume, and same-game covariance.

V3 advances only when marginal gates pass and joint scores improve over independent sampling and empirical covariance foils.


Player outcomes in the same game are correlated:

- QB and WR scores are positively correlated.
- QB and opposing QB may be positively correlated in shootouts.
- RB and opposing passing volume may be positively related through game script.
- Two receivers competing for the same targets may be negatively correlated.
- A defense and opposing offensive players are generally negatively correlated.

Generate all players from a shared game state.

A latent game variable can help:

\[
z_g \sim N(0,1)
\]

where \(z_g\) represents an unexpectedly strong or weak offensive environment.

## 10. Composite-System Calibration and the Permanent Direct Foil

The component chain compounds error:

```text
Environment → volume → pass/rush allocation → availability → playing time
→ opportunity share → efficiency → touchdowns → fantasy scoring
```

### 10.1 Per-Layer Calibration Gates

Before composition, each layer must satisfy:

- Out-of-sample CRPS improvement against pre-registered baselines.
- Randomized-PIT flatness for discrete/count layers.
- Reliability, Brier decomposition, and calibration slope/intercept for binary/rate layers.
- Required empirical interval-coverage floors.
- Sharpness comparison only among candidates satisfying coverage floors.
- An oracle anchor that receives realized upstream input.
- All-zero, all-mean, and historical-rate degenerate anchors.
- Feature-family and source-family ablations.
- Stability by season, position, projection day, injury state, and usage tier.

A layer that fails its own gate cannot be promoted because one aggregate result looks attractive.


### 10.1A Joint Calibration Gate

Required foils:

- Independent marginal sampling
- Empirical same-game covariance baseline
- Direct multivariate or lineup-total model
- Shared-game-state component simulation

The selected method must improve joint scores and pairwise calibration without degrading marginal CRPS beyond a pre-registered tolerance. A marginally calibrated but correlation-misspecified simulator is rejected.


### 10.2 End-to-End Recalibration

After composing out-of-fold posterior samples:

1. Evaluate the complete fantasy distribution.
2. Fit recalibration only on prior-fold residual information.
3. Re-score CRPS, randomized PIT, threshold Brier scores, and interval floors.
4. Re-test by position, projection timestamp, and availability state.

Candidate recalibrators include isotonic distributional regression, quantile mapping, beta calibration for thresholds, and Bayesian residual correction.

### 10.3 Permanent Direct Fantasy-Points Foil

The direct model is permanent, not a discarded V1 stepping-stone. Candidate foils include distributional CatBoost/LightGBM, quantile boosting, Bayesian additive regression trees, mixture-density models, and hurdle models.

The composite must beat the direct model out of sample on CRPS, meet the same calibration floors, and justify its complexity through transparency or scenario value. If it cannot, that is a finding. The direct model may remain primary while the component system supports explanation and simulation.

## 11. Distributional Candidate Sets and Sanity Checks

Fantasy outcomes are often zero-inflated, skewed, heavy-tailed, and multimodal. For every target, pre-register at least three families plus a direct-learned foil.

### Count Targets

- Poisson or generalized Poisson
- Negative binomial
- Zero-inflated or hurdle count model
- Conway-Maxwell-Poisson
- Distributional boosting
- Direct count-distribution foil

### Rate and Share Targets

- Binomial logistic
- Beta-binomial
- Logistic-normal
- Hierarchical multinomial
- Distributional boosting
- Direct rate foil

### Positive Continuous Targets

- Gamma
- Lognormal
- Student-\(t\) on a transformed scale
- Tweedie
- Quantile regression
- Mixture-density model

### Touchdowns

Candidates include team-score allocation, red-zone conversion, end-zone/goal-line conversion, zero-inflated counts, direct conditional touchdown probability, and the direct fantasy-points foil.

No family is selected on theoretical appeal alone; all must pass §10.

## 12. Validation, Selection, and Honest Decision Evaluation

### 12.1 Primary Selection Metric

**CRPS is the primary model-selection metric.** It evaluates both location and spread for the zero-inflated, skewed posterior target.

MAE and RMSE are diagnostics only because they may reward pessimistic, mean-collapsed, or zero-heavy predictions.

Every run must score:

- All-zero predictor
- All-mean predictor
- Position/week historical-average predictor
- Simple public or consensus baseline where licensing permits
- Permanent direct fantasy-points foil

These are tripwires. If a candidate loses materially to all-zero or all-mean, investigate target construction, the availability mixture, weighting, timestamp leakage, and metric implementation.

### 12.2 Calibration Metrics

Use randomized PIT for discrete/count outcomes, PIT for continuous outcomes, Brier and reliability for thresholds, calibration slope/intercept, empirical interval coverage, and sharpness.

**Coverage is a floor, never the optimization target.** Among models meeting the floor, compare CRPS and sharpness.

### 12.3 Purged and Embargoed Time-Series CV

Use forward-chaining folds with purging of overlapping feature/target windows, an embargo between train and validation, separate Tuesday/Friday/Sunday evaluations, locked model-selection and final periods, and guards against rolling features crossing fold boundaries.

### 12.4 Multiple-Testing Guard

Apply nested time-series CV, pre-declared candidate-family caps, bootstrap-adjusted confidence intervals or deflated scores, White Reality Check or Hansen SPA for broad searches, a minimum practical CRPS improvement, and stability requirements across seasons and positions.

### 12.5 Diagnostic Metrics

Report MAE, RMSE, median absolute error, bias by projection band, rank correlation, top-\(N\) accuracy, and value-over-replacement rank diagnostics—but do not select primarily on them.

### 12.6 Honest Decision Layer (`best_alpha = 0`)

User-facing outputs must be uncertainty statements:

- Probability Player A outscores Player B
- Probability a player exceeds a user-selected threshold
- Probability of finishing within a positional tier
- Team-score distribution under alternative lineup choices
- Expected difference and uncertainty between start/sit options
- Probability a waiver addition becomes startable within a horizon
- Sensitivity to injury, weather, and role assumptions

Start/sit win rate, DFS lineup ROI, rank improvement, or “beat consensus” rates are **historical backtest context only**. Whenever shown, label the dates, scoring format, decision rule, sample size, assumptions, confidence interval, and the fact that past results are not a promise.

Never tell users “we beat the market,” “place this lineup,” “winning play,” “guaranteed edge,” “expected profit,” or provide wagering instructions.


## 12A. Entity Resolution and Cross-Vendor Identity Control

Entity resolution is a maintained production service.

All nflverse, PFF, FTN, SIS, Next Gen Stats, Sportradar, SportsDataIO, odds-provider, and name-only prop records map to one canonical player, team, and game ID.

Canonical crosswalk fields:

```text
canonical_player_id
source_name
source_player_id
source_player_name
normalized_name
team_id
position
effective_start_timestamp
effective_end_timestamp
match_method
match_confidence
review_status
last_verified_timestamp
```

The service must handle rookies, duplicate names, suffixes, roster churn, trades, practice-squad promotions, and vendor-specific abbreviations.

Match order:

1. Stable vendor-ID mapping.
2. Reviewed crosswalk.
3. Exact normalized name + team + position.
4. Constrained fuzzy match.
5. Manual review.

Name-only props cannot be joined on fuzzy name alone.

Monitor:

```text
unmatched_rate
low_confidence_rate
high_value_unmatched_count
silent_drop_count
```

`silent_drop_count` must equal zero.

An unmatched high-value feature must:

1. Fall back to the lower data tier.
2. Be flagged as source-degraded.
3. Be recorded in QA.
4. Never be silently set to zero or silently dropped.

Builds may fail closed when unmatched rates exceed pre-registered thresholds or expected starters are affected.


### 12.7 Joint and Correlation Metrics

For lineup, stack, best-ball, and same-game simulation, report energy score, variogram score, covariance error, joint-threshold Brier scores, multivariate rank calibration, lineup-total CRPS, stack/bring-back frequencies, and tail-dependence diagnostics.

V3 requires both marginal and joint gates.



## 12B. Label Integrity and Stat-Correction Versioning

The evaluation label is itself point-in-time data.

`actual_fantasy_result` must never be stored as one mutable final value because:

- Official NFL statistics may be corrected after the game.
- Fantasy platforms may apply corrections on different schedules.
- Platforms may assign receptions, fumbles, sacks, defensive scores, and return statistics differently.
- League scoring rules may interpret the same official event differently.
- Recomputing historical evaluations against a later label silently changes model rankings.

### 12B.1 Canonical Label Policy

Every league/scoring format must specify:

```text
label_provider
provider_scoring_version
league_scoring_rule_id
stat_source
stat_correction_policy
label_as_of_timestamp
label_version
```

The canonical label is not universal. It is canonical **for a specific scoring configuration and platform policy**.

Examples:

- ESPN PPR scoring under ESPN's final weekly corrections.
- Yahoo half-PPR under Yahoo's stat-assignment rules.
- Sleeper custom scoring using official NFL statistics and the stored league configuration.
- Internal canonical scoring derived from a pinned official-stat snapshot.

### 12B.2 Immutable Label Snapshots

Store each observed label revision:

```text
player_id
game_id
scoring_system_id
platform_id
label_value
label_as_of_timestamp
source_stat_version
label_version
correction_reason
is_current
```

Recommended snapshots:

- Initial postgame label.
- Tuesday evaluation label.
- Platform-final weekly label.
- Later official correction label.
- Final research label after the correction window closes.

No prior label snapshot is overwritten.

### 12B.3 Evaluation Pinning

Every CRPS, PIT, calibration, coverage, MAE, RMSE, and decision-analysis result must reference:

```text
evaluation_label_version
evaluation_label_as_of_timestamp
scoring_system_id
platform_id
```

A model leaderboard compares candidates only when they were scored against the same pinned label version.

If a later correction materially changes results:

1. Preserve the original evaluation.
2. Create a new evaluation run against the later label.
3. Attribute the difference to label revision.
4. Do not silently replace the earlier leaderboard.

### 12B.4 Label-Reconciliation Monitoring

Track:

- Number of corrected player-games.
- Absolute fantasy-point change.
- Corrections by event type.
- Corrections by platform.
- Evaluation-metric change caused by corrections.
- Models whose ranking changes under the final label.

A correction-sensitive model comparison should be flagged when candidate ordering changes across reasonable label versions.

## 13. Point-in-Time Integrity and Leakage Guards

Potential leakage includes final inactive status in an earlier projection, closing lines in a Tuesday model, future usage, revised depth charts, later props, later injury news, target-game opponent stats, and vendor files overwritten without snapshotting.

Required keys:

```text
player_id
game_id
projection_timestamp
feature_timestamp
source_timestamp
capture_timestamp
vendor_release_timestamp
ingestion_timestamp
```

### Fail-Closed Enforcement

Reject the build when:

- `feature_timestamp > projection_timestamp`
- `source_timestamp > projection_timestamp`
- `capture_timestamp > projection_timestamp`
- Point-in-time provenance is missing
- Revised vendor data replaced the original captured record
- A closing line or late prop joins to an earlier projection
- A rolling window contains the target or future game

Every market and prop record must be timestamped at capture and the raw payload retained immutably. A Tuesday model may use only snapshots captured on or before Tuesday's projection timestamp. Unit and integration tests must deliberately construct leakage cases and require rejection.


## 13A. In-Season Calibration-Drift Monitoring

Passing preseason and historical release gates does not guarantee in-season calibration.

Potential regime changes include:

- Coaching or coordinator changes.
- Quarterback changes.
- Rule or officiating changes.
- Usage-pattern shifts.
- Injury clusters.
- Weather-regime changes.
- Vendor definition changes.
- Feature latency or missingness changes.
- Changes in lineup, personnel, or play-calling behavior.

### 13A.1 Weekly Monitoring Schedule

After each completed week and pinned label snapshot, calculate rolling diagnostics by:

- Position, including K and DST.
- Projection day: Tuesday, Friday, and Sunday.
- Active/inactive designation.
- Projection band.
- Usage tier.
- Data-source tier.
- Model version.
- Scoring format.

Monitor:

- Rolling CRPS.
- CRPS relative to the permanent direct foil.
- Randomized PIT and PIT histograms.
- 50%, 80%, and 90% empirical coverage.
- Calibration intercept and slope.
- Brier scores for user-facing thresholds.
- Bias.
- Sharpness.
- Joint scores for the V3 correlated simulator.
- Entity-resolution degradation.
- Missing-feature and fallback rates.
- Label-correction sensitivity.

Use multiple windows, such as:

```text
last_2_weeks
last_4_weeks
season_to_date
same_weeks_prior_seasons
```

Short windows are alerts, not standalone proof. Longer windows determine release action.

### 13A.2 Pre-Registered Drift Triggers

Thresholds must be set before the season and stored with the release.

A model enters `DRIFT_WARNING` when one or more occur:

- Rolling CRPS exceeds its release-floor tolerance.
- CRPS loses materially to the permanent direct foil.
- PIT non-uniformity exceeds the registered test threshold.
- Coverage falls below the required floor.
- Calibration slope/intercept leaves its allowed range.
- Joint calibration loses to the independent or empirical-covariance foil.
- Missing or fallback rates exceed their allowed limits.
- A source-definition change is detected.

A model enters `ROLLBACK_REQUIRED` when:

- A severe threshold is breached in one validated window.
- A warning persists for the pre-registered number of weeks.
- Data integrity, label integrity, or entity resolution fails.
- The direct foil materially outperforms the served model for the registered persistence period.

### 13A.3 Response Policy

The response is deterministic:

```text
HEALTHY
  → continue serving

DRIFT_WARNING
  → increase monitoring
  → freeze optional feature additions
  → run shadow refit
  → retain current served model unless severe trigger fires

ROLLBACK_REQUIRED
  → serve registered fallback
  → preserve prior outputs
  → investigate root cause
  → require full re-promotion gate before restoration
```

The registered fallback should be the most recent healthy version or the permanent direct foil.

### 13A.4 Refit Policy

Refitting is not automatically accepted because recent data exists.

A refit must:

- Use the same purged/embargoed validation discipline.
- Include prior seasons and current-season data according to a registered weighting policy.
- Re-run degenerate tripwires.
- Re-run marginal and joint calibration gates.
- Compare against the currently served model and direct foil.
- Be promoted only through the standard release process.

Emergency data corrections may restore a prior known-good model without a new model-selection exercise, but the incident must be logged.

## 14. Practical Implementation Roadmap

### V0: Data-Source Audit and Point-in-Time Feasibility

V0 occurs before modeling.

Deliverables:

1. Feature inventory mapped to named sources.
2. Licensing and redistribution review.
3. Historical-depth audit.
4. Projection-time lag and refresh audit.
5. Immutable capture design.
6. Canonical cross-vendor entity-resolution service, confidence policy, and unmatched-rate monitoring.
7. Missing-data/vendor-outage fallback plan.
8. Free-data minimum-viable feature set.
9. Go/no-go decision for charting-dependent features.
10. Costed vendor options.
11. Synthetic as-of backtest recreating historical Tuesday, Friday, and Sunday builds only where true historical snapshots exist.


#### Historical Backtest Fidelity Is Data-Gated

An as-of backtest can reconstruct only features with true historical point-in-time snapshots.

- Free play-by-play and internally derived features usually have the strongest reconstruction fidelity.
- Depth-chart consistency varies.
- Archived forecast availability varies.
- Historical props are shallow.
- Market snapshots may begin only in the mid-2020s.
- Paid charting feeds may provide current data without historical release-time snapshots.
- A backfilled table is not equivalent to what was known on a historical Tuesday, Friday, or Sunday.

V2 must label each feature as:

```text
retrospectively validated
prospectively shadow-validated
not point-in-time validated
```

The incremental value of paid charting may need to be proven prospectively rather than through a long historical backtest.


#### Free/Public Minimum-Viable Feature Set

V1 can use nflverse play-by-play and weekly stats; schedules, rosters, public depth charts and snap counts where reliable; public injury reports; derived plays, drives, attempts, carries, targets, yards, touchdowns, red-zone events, game state, pace, PROE, EPA, success rate, explosive rates, and red-zone tendencies; weather forecasts captured from an API; teammate availability and rolling shares; and draft/combine/age priors.

V1 cannot honestly depend on route participation, first-read share, coverage shells, separation, detailed pressure attribution, box counts, or YAC-over-expectation without licensed data.

### V1: Free-Data Baseline and Permanent Foils

Build bake-offs for team volume, pass/rush allocation, availability, participation proxies, carries/targets, yards/TDs, and direct fantasy points.

Every target requires at least three model classes plus direct foil, feature ablations, purged/embargoed CV, CRPS-primary selection, degenerate tripwires, multiple-testing guard, layer gates, and locked holdout.

### V2: Licensed Opportunity and Charting Layer

Proceed only after V0 secures source and product-use rights. Candidate additions include route participation, TPRR, first-read share, air-yard share/aDOT, personnel/alignment/coverage, pressure/blocking, box counts, separation, YAC-over-expectation, and expanded CPOE.

The paid tier must prove incremental out-of-sample CRPS and calibration value after cost and reliability are considered.

### V3: Dynamic Bayesian and Correlated Simulation

Add time-varying talent, hierarchical low-sample priors, intraweek Bayesian updates, joint opportunity allocation, shared game states, teammate/opponent correlations, injury-state mixtures, and end-to-end recalibration. V3 is gated on the joint-distribution tests in §9.1 and §10.1A.

### V4: Honest User Decision and Explanation Layer

Expose calibrated start/sit probabilities, thresholds, positional tiers, lineup distributions, waiver-horizon probabilities, conditional/unconditional projections, assumption sensitivity, projection-change attribution, data freshness, and source-tier disclosures.

Historical win-rate, ROI, or consensus comparisons remain labeled backtest context only.

## 15. Recommended Core Data Model

```text
dim_player
dim_team
dim_game
dim_stadium
dim_scoring_system
dim_data_source
dim_vendor_license
dim_model_version
dim_canonical_entity
dim_vendor_entity_crosswalk

player_game_participation
player_game_opportunity
player_game_efficiency
team_game_environment
player_injury_snapshot
practice_report_snapshot
depth_chart_snapshot
roster_snapshot
snap_count_snapshot
betting_market_snapshot
weather_forecast_snapshot
projection_feature_snapshot
projection_snapshot
simulation_output
actual_fantasy_result
actual_fantasy_result_version
label_reconciliation_result
model_evaluation_result
calibration_gate_result
in_season_drift_monitor_result
model_rollback_event
serving_policy_result
data_source_audit_result
entity_resolution_result
entity_match_exception
```

Required provenance columns:

```text
source_name
source_record_id
source_timestamp
capture_timestamp
vendor_release_timestamp
ingestion_timestamp
feature_timestamp
projection_timestamp
license_tier
model_version
data_version
label_version
label_as_of_timestamp
```

Projection and label tables are versioned throughout the week. Every evaluation is pinned to a label version. Appendix A maps the features to sources and fallbacks.


## 16. Production Serving and Blend Policy

The served projection is determined by registered out-of-sample evidence.

### 16.1 Default Decision Rule

- If the component system materially beats the direct foil on CRPS and passes all marginal and joint gates, it may serve as the primary model.
- If the component system ties the direct foil within the pre-registered practical-equivalence margin, the **direct model serves the primary numerical distribution** and the component system is used for explanations, conditional scenarios, and decomposition.
- If a learned ensemble materially improves proper scores and calibration, the ensemble may serve.
- If the component system loses, the direct model serves and the result is recorded.

Complexity is not a tie-breaker in favor of the component system.

### 16.2 Learned Ensemble Policy

An ensemble is itself a fitted model.

Candidate blend forms include:

- Convex linear pool.
- Logarithmic pool.
- Stacking using out-of-fold predictive densities.
- Regime-specific mixture by position or projection day.
- Bayesian model averaging where assumptions are defensible.

Blend weights must be learned using:

- Out-of-fold predictions only.
- Purged and embargoed time-series CV.
- The same locked holdout.
- CRPS or log-score selection.
- Weight regularization.
- A multiple-testing/deflation guard.
- Stability tests by season and position.

No weight may be fit on the final holdout or updated ad hoc from recent results.

### 16.3 Serving Metadata

Every served response should retain:

```text
served_model_type
served_model_version
component_model_version
direct_foil_version
ensemble_version
blend_weights_version
calibration_version
fallback_status
projection_timestamp
```

When the component model is explanation-only, the UI must not imply that its decomposed mean is the served numerical projection.

## Central Design Principle

Estimate:

\[
P(\text{Fantasy Points} \mid
\text{active},
\text{role},
\text{team volume},
\text{matchup},
\text{game environment})
\]

while integrating over uncertainty:

\[
P(Y)
=
\int P(Y\mid A,R,V,M,G)
P(A,R,V,M,G)\,dA\,dR\,dV\,dM\,dG
\]

Instead of saying:

> This receiver will score 16.8 points.

Say:

> His expected score is 16.8, his median is 15.1, he has a 31% chance to exceed 20, and an 18% chance to finish below 8. Most of his uncertainty comes from target share and touchdown probability.

That is where a Bayesian, simulation-based system can meaningfully differentiate the product from deterministic projection providers.

# Appendix A — Feature-to-Source Provenance Table

Costs are planning estimates, not vendor quotes. Enterprise feeds may restrict redistribution or display of raw/derived data. Written license approval is required.

`GATED` means V2/V3 depends on a paid charting/tracking contract.

| Feature(s) | Named source | Access / rough cost | Projection-time availability | Training history | Cadence | Fallback / judgment |
|---|---|---|---|---|---|---|
| Schedules, teams, game IDs, stadium, home/away | nflverse schedules/PBP; Sportradar alternative | Free/public; enterprise quote | Days/months ahead; snapshot changes | ~2000+ depending table | Daily/game-time | ESPN/NFL capture. V1-safe. |
| Play-by-play | nflverse PBP | Free/public; verify upstream terms | Postgame/in-game timing must be audited | ~1999/2000+ | In-game/postgame | Sportradar/SportsDataIO. V1-safe for historical features. |
| Weekly/player stats | nflverse player stats | Free/public | After each game | Multi-season/decades by field | Weekly | Derive from PBP. |
| Rosters, positions, age, IDs | nflverse rosters/ID mappings | Free/public | Available preseason and through transactions | Multi-season | Daily/weekly | Paid roster feed/manual mapping. |
| Depth charts | nflverse depth charts; Sportradar | Free but source-fragile; paid enterprise | nflverse updates daily; use timestamped snapshots | Historical loader roughly 2001+, consistency varies | Daily | Team depth charts. Weak evidence only. |
| Injury designation/practice status | Official reports; nflverse where functioning; Sportradar/SportsDataIO | Public/manual or paid | Wed-Fri; final status later | Public continuity uneven | Daily game week | Manual capture. V0 must prove reliability. |
| Inactives | Official inactive lists; paid feeds | Public/manual or paid | ~90 minutes pre-kickoff | Historical if captured/vendor | Once pregame | Team/NFL capture. Only Sunday model can use. |
| Snap counts/share | nflverse snap counts historically sourced from PFR; SIS/PFF | Free historical research, licensing audit needed; paid alternative | Postgame | Several seasons | Weekly | PBP participation proxy. |
| Plays, drives, dropbacks, attempts, rushes | Derived nflverse PBP | Free/public | Prior games after completion | ~2000+ | Postgame | Paid feed. V1-safe. |
| Completions, yards, TDs, INTs, sacks, fumbles | nflverse PBP/stats | Free/public | Postgame | ~2000+ | Postgame | Box score/paid feed. |
| Scrambles/designed QB rushes | nflverse PBP classifier | Free/public | Postgame | Modern PBP | Postgame | Rule-based text classifier. |
| Carries, targets, receptions, rush/receiving yards | nflverse PBP | Free/public | Postgame | ~2000+ | Postgame | Weekly stats. |
| Red-zone/goal-line opportunities | nflverse yard line/play type | Free/public | Postgame | ~2000+ | Postgame | Box-score summaries. |
| End-zone targets | nflverse target location approximation; FTN/PFF | Free proxy; paid charting preferred | Postgame | Modern PBP/vendor-dependent | Postgame | Approximate and disclose uncertainty. |
| Third-down, short-yardage, two-minute role | PBP + participation; FTN/PFF/SIS | Partial free; paid for reliable on-field detail | Postgame | Limited by participation history | Weekly | Event-share proxies. |
| Route participation/routes per dropback | FTN Data API, PFF B2B, SIS | `GATED`; custom API quote; SIS DataHub self-service roughly $100/mo, API rights separate | Usually postgame/weekly; SLA contractual | Vendor-dependent recent seasons | Postgame/weekly | No reliable free substitute. |
| Targets per route run | FTN/PFF/SIS | `GATED` | After route data release | Vendor-dependent | Weekly | Targets per snap/dropback proxy. |
| First-read target share | FTN/PFF/SIS/proprietary charting | `GATED` | Postgame; exact lag contractual | Recent charted seasons | Weekly | Exclude V1. |
| Air-yard share/aDOT | nflverse air_yards; FTN/PFF audit source | Free partial; paid preferred | Postgame | Modern PBP | Postgame | Derive with completeness flags. |
| Personnel, formation, motion, alignment | FTN/PFF/SIS/Sportradar subjective stats | `GATED`, paid | Vendor-dependent postgame/real-time | Vendor-dependent | Play-level/weekly | Exclude V1. |
| Coverage shell/two-high/man-zone/brackets | PFF/FTN/SIS/licensed NGS | `GATED`, enterprise/custom | Mostly postgame; do not assume real time | Recent charted/tracking era | Weekly | Opponent efficiency proxies only. |
| Pressure rate | nflverse/PFR advanced partial; PFF/SIS/FTN | Partial free; paid preferred | Postgame | Public history varies | Weekly | Sack rate and PBP proxies. |
| Pass/run blocking quality | PFF/SIS/FTN; limited ESPN aggregates | `GATED` for stable feed | Postgame | Vendor-dependent | Weekly | Line continuity, sack rate, YBC proxies. |
| Box counts/light-box rate | NGS/PFF/FTN/SIS | `GATED` | Postgame/contractual | Recent era | Weekly | Exclude V1. |
| Receiver separation | Licensed NGS/Genius; public NGS aggregates | `GATED` for stable API/full history | Public aggregates postgame | Recent NGS era | Weekly | Target/catch/aDOT proxies. |
| YAC over expectation | Licensed NGS/public aggregate | `GATED` for product feed | Postgame | Recent NGS era | Weekly | Raw YAC or internally derived proxy. |
| CPOE | nflverse public NGS aggregates; NFL/ESPN | Public aggregate, production terms audit | Postgame | Recent NGS era | Weekly | Public difficulty-adjusted proxy. |
| Player ability: TPRR/YPRR | TPRR requires routes from paid source; YPRR same | `GATED` | Postgame | Vendor-dependent | Weekly | Targets/yards per snap or dropback. |
| Reception probability | Derived public PBP; NGS for richer version | Free baseline; paid tracking enrichment | Postgame | Modern PBP | Weekly | Logistic model from depth/location/context. |
| YAC over expectation | NGS/FTN/PFF | `GATED` | Postgame | Recent seasons | Weekly | Raw YAC. |
| Air yards per target | nflverse | Free/public | Postgame | Modern PBP | Weekly | None. |
| Rushing yards over expectation | NGS licensed/public aggregates | `GATED` for production feed | Postgame | Recent NGS era | Weekly | Rush yards after contact/YBC proxies. |
| Yards after contact/missed tackles | FTN/PFF/SIS | `GATED` | Postgame | Vendor-dependent | Weekly | Yards after first contact unavailable; use rushing success/YBC proxy. |
| Success rate/EPA per opportunity | nflverse PBP | Free/public | Postgame | Modern PBP | Weekly | Recompute internally. |
| Pressure-to-sack/scramble rate | nflverse PBP plus pressure source | Partial free | Postgame | Modern seasons | Weekly | Sack/dropback and scramble/dropback. |
| Touchdown conversion ability | nflverse red-zone/goal-line events | Free/public | Postgame | ~2000+ | Weekly | Hierarchical shrinkage. |
| EWMA usage features | Internal from source snapshots | Internal | As of build time | From source history | Every build | Short/medium/long windows. |
| Pace, neutral pace, PROE, no-huddle, seconds/snap | nflverse PBP | Free/public | Prior games postgame | Modern PBP | Weekly | None. |
| Early-down pass rate/fourth-down aggressiveness | nflverse PBP | Free/public | Postgame | Modern PBP | Weekly | None. |
| Red-zone efficiency, drive success, team EPA | nflverse PBP | Free/public | Postgame | Modern PBP | Weekly | None. |
| Coordinator/play-caller/coaching changes | Team sites/manual dimension; paid news feeds | Manual/free or paid | Offseason/event-driven | Curated | Event-driven | Team fixed effects. Maintenance burden. |
| Offensive-line continuity | Rosters/depth/injuries/snaps; PFF/SIS | Partial free | Weekly | Depends on snap history | Daily/weekly | Returning-starter count and team proxies. |
| Defensive EPA/success/explosive rate by play type | nflverse PBP | Free/public | Postgame | Modern PBP | Weekly | None. |
| Blitz rate | nflverse/PFR advanced partial; PFF/SIS | Partial free/paid | Postgame | Recent seasons | Weekly | Pressure/sack proxies. |
| Defensive aDOT and YAC allowed | nflverse PBP | Free/public | Postgame | Modern PBP | Weekly | None. |
| Rush EPA by gap/direction | nflverse coarse run-location fields; PFF/SIS charting | Partial free; paid detailed | Postgame | Modern PBP | Weekly | Overall/direction-level only. |
| Spread, total, moneyline, implied total | The Odds API; Sportradar Odds; SportsDataIO | Self-service paid; enterprise alternatives | Days ahead; capture continuously | Featured markets mid-2020+, snapshots 5–10 min by era | Minutes | Omit from free V1 or capture permitted consensus. |
| Player props | The Odds API/Sportradar Player Props/SportsDataIO | Paid; coverage varies | Often 1–5 days ahead and sparse early | Shallower than game odds | Minutes | Omit V1; never backfill closing props. |
| Wind, temperature, precipitation | Visual Crossing or OpenWeather | Free tier; low-cost self-service to enterprise | Forecast 7–15 days; capture each build | ~50/47 years observations; archived forecasts vary | Hourly | NOAA/METAR observation fallback; use archived forecasts in backtests. |
| Dome/outdoor, surface, altitude | Stadium dimension/manual | Free/manual | Known before season | Long history | Rare | Manual table. |
| Rest, short week, travel, international | Derived schedules/geocodes | Free/public | Known at schedule release | Full schedule history | On schedule change | None. |
| Market movement | Timestamped Odds API snapshots | Paid history | Only after snapshots are captured | Mid-2020+ featured markets | Minutes | Omit feature. |
| Injury type/days since injury | Public reports/news plus manual taxonomy; paid feed | Manual/free or paid | As reported | Uneven | Daily | Designation-only model. |
| Teammate injuries/availability | Derived from injury and roster snapshots | Internal | As of build | Source-dependent | Every build | Depth-chart change proxy. |
| Scoring rules | User/platform configuration | Internal | At request | N/A | On change | Standard presets. |
| Projection, feature, weather, market, depth, injury snapshots | Internal immutable store | Internal | At every build/capture | From launch | Event-driven | Mandatory. |
| Simulation output/posteriors | Internal model service | Internal | At build completion | From launch | Every build | Mandatory. |
| Actual fantasy result/stat corrections | Official/public stats + scoring engine | Free/paid | Postgame, then corrections | Source history | Postgame/correction | Version corrections. |
| Evaluation/calibration gate results | Internal ML registry | Internal | Every run | From V0 | Every run | Mandatory promotion evidence. |
| Data-source/license audit | Internal governance table | Internal | Before activation | From V0 | On source/contract change | Disable feature if audit expires. |

| Kicker attempts, makes, misses, distance, XP | nflverse PBP | Free/public | Postgame | Modern PBP | Postgame | Official gamebooks. Tier-0 V1. |
| DST sacks, takeaways, TDs, safeties, blocks | nflverse PBP | Free/public | Postgame | Modern PBP | Postgame | Official gamebooks. Tier-0 V1. |
| DST points/yards allowed | nflverse PBP/game stats | Free/public | Postgame | Modern PBP | Postgame | Official box score. |
| Cross-vendor player IDs | nflverse mappings + vendor IDs | Free/internal plus vendor feeds | At ingest | From onboarding | Every ingest | Canonical crosswalk + review queue. |
| Name-only prop identities | Odds-provider payload + roster snapshots | Paid/source-dependent | At capture | Retained-payload history only | Minutes | Never fuzzy-join alone; fallback and flag. |

| Fantasy scoring labels and stat corrections | Platform API or internal scoring engine + pinned official-stat snapshot | Platform/internal | Initial postgame through final correction window | From retained snapshots | Postgame and correction cycle | Immutable label versions; never overwrite. |
| Live calibration monitoring | Internal evaluation pipeline | Internal | Weekly after pinned labels | From launch | Weekly | Registered warning/refit/rollback triggers. |
| Served blend weights | Internal model registry | Internal | At release | From ensemble introduction | Per release | Fit only from purged/embargoed OOF predictions. |

## A.1 Vendor Reality Check

- nflverse is the Tier-0 foundation, but individual datasets have different upstream sources and lags.
- NFL Next Gen Stats captures raw tracking at 10 Hz; raw tracking is not a general free production API.
- A consumer PFF+ subscription does not include API access; product use requires PFF B2B.
- FTN advertises charting and API access, but commercial terms require a quote.
- SIS offers self-service DataHub pricing, while API and redistribution rights may be separate.
- Sportradar, SportsDataIO, and Genius are enterprise contractual feeds.
- Odds and weather backtests must use snapshots/forecasts known at the projection timestamp, not closing values or realized conditions.

# Appendix B — Bake-Off Registration Template

```yaml
target:
projection_timestamp:
candidate_family:
candidate_id:
direct_foil_id:
feature_set_id:
ablation_groups:
training_window:
purge_window:
embargo_window:
cv_folds:
primary_metric: CRPS
secondary_diagnostics:
  - randomized_PIT
  - calibration_intercept
  - calibration_slope
  - interval_coverage_floor
  - sharpness
  - MAE
  - RMSE
degenerate_tripwires:
  - all_zero
  - all_mean
  - historical_position_week_mean
multiple_testing_guard:
minimum_practical_improvement:
locked_holdout:
promotion_decision:
```

# Appendix C — Gap-Closure Addendum

This revision adds:

- First-class kicker and DST models.
- Exact expected bucket scoring for points and yards allowed.
- Joint-distribution and correlation calibration.
- A V3 joint-calibration release gate.
- Canonical cross-vendor entity resolution.
- Unmatched-rate and silent-drop monitoring.
- Explicit limits on historical as-of backtest fidelity.

# Appendix D — Production Governance Addendum

This revision adds:

- Canonical scoring-provider and platform-specific label policies.
- Immutable stat-correction label snapshots.
- Label-version-pinned CRPS and calibration evaluations.
- Weekly in-season calibration-drift monitoring.
- Pre-registered warning, refit, and rollback triggers.
- An explicit production serving and ensemble policy.
