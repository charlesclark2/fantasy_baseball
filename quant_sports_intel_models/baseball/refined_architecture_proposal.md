# Quantitative Sports Intelligence Architecture Proposal
## Conceptual Architecture Document

Version: Draft 0.2
Status: Conceptual / Research Architecture
Primary Domain: MLB Pregame Betting & Sports Intelligence

---

# 1. Executive Summary

## Purpose

This document defines the conceptual architecture for the next-generation MLB quantitative betting and sports intelligence platform.

The goal of this architecture is NOT to immediately replace the current production modeling stack.

Instead, the goal is to:

- Incrementally decompose the existing monolithic game-level models into specialized baseball-mechanism signal generators
- Improve interpretability and diagnosability of model outputs
- Introduce probabilistic and uncertainty-aware reasoning into the prediction pipeline
- Improve long-term calibration and market-relative edge identification
- Create a scalable foundation for future simulation, fantasy, API, and multi-sport expansion

This document intentionally focuses on:

- conceptual architecture
- model boundaries
- modeling principles
- signal taxonomy
- research direction

This document DOES NOT attempt to define:

- production orchestration
- infrastructure deployment
- exact implementation details
- specific libraries/frameworks
- release sequencing
- staffing or operational concerns

Those concerns are addressed in the companion **Implementation Guide**.

---

# 2. Strategic Goals

## Primary Objective

Develop a market-aware probabilistic sports intelligence system capable of generating calibrated pregame MLB betting probabilities for:

- moneyline / head-to-head betting
- game totals

while improving:

- calibration
- uncertainty handling
- explainability
- CLV capture
- long-term risk-adjusted edge

---

## Secondary Objectives

The architecture should also support future expansion into:

- fantasy baseball
- probabilistic simulation APIs
- research dashboards
- sports data products
- B2B analytics
- additional sports

---

# 3. Core Architectural Principles

## Principle 1 — Baseball Mechanisms Are Modeled Separately

The system should model distinct baseball mechanisms independently whenever practical.

Examples:

- offensive quality
- starting pitcher suppression
- bullpen state
- run environment
- lineup matchup quality

The purpose of decomposition is:

- interpretability
- modular experimentation
- uncertainty isolation
- improved debugging

NOT architectural complexity for its own sake.

---

## Principle 2 — Sub-Models Generate Signals, Not Hard Deterministic Dependencies

Sub-models should initially be treated as:

- latent signal generators
- probabilistic feature generators
- uncertainty estimators

Sub-model outputs are intended to augment the existing production models incrementally.

The architecture does NOT assume:

- rigid sequential dependency chains
- immediate replacement of current production models
- mandatory downstream dependence on all sub-model outputs

This is intended to minimize:

- error propagation
- compounded variance
- overfitting risk
- architectural fragility

---

## Principle 3 — Market Signals Are Strictly Isolated

Market-derived signals must be isolated from baseball-mechanism models.

### Architectural Constraint

Market-derived signals are prohibited from:

- offensive sub-models
- starter sub-models
- bullpen sub-models
- matchup sub-models
- run environment sub-models

Market-derived signals are only permitted within:

- market-state models
- edge/meta-model layers
- CLV evaluation layers
- risk and portfolio sizing layers

The purpose of this separation is to avoid:

- market circularity
- leakage
- implicit sportsbook replication

The baseball models should attempt to estimate:

> "What is likely to happen in the game?"

The market/meta-model layers should estimate:

> "When is market disagreement historically actionable?"

---

## Principle 4 — Uncertainty Is a First-Class Output

Sub-models should eventually expose:

- central estimate
- uncertainty estimate
- effective sample size
- stabilization metrics

Examples:

- mean + variance
- confidence interval
- posterior distribution
- quantile outputs

This principle is especially important for:

- totals modeling
- rookie players
- bullpen modeling
- early-season stabilization
- injury returns

---

## Principle 5 — The Market Is a Benchmark, Not Ground Truth

The system acknowledges that sportsbook markets are highly efficient.

The purpose of the architecture is NOT merely to predict baseball games.

The purpose is to:

- identify situations where market pricing may be incomplete
- identify uncertainty the market may underprice
- identify timing windows where information incorporation lags

Examples:

- lineup releases
- bullpen exhaustion
- pitch mix changes
- weather transitions
- travel/scheduling effects

---

# 4. High-Level Conceptual Architecture

## Layer 1 — Raw Data & Context

Examples:

- Statcast
- FanGraphs
- Baseball Savant
- MLB Stats API
- lineup data
- injury/news data
- weather data
- sportsbook odds data
- umpire assignments
- schedule/travel data

---

## Layer 2 — Baseball Mechanism Models

Purpose: Generate specialized latent baseball-quality signals.

Examples:

- offensive quality model
- starter suppression model
- bullpen state model
- matchup model
- run environment model

Important: These models are NOT intended to directly place bets.

Their purpose is to estimate:

- baseball quality
- uncertainty
- latent run-generation/suppression mechanisms

---

## Layer 3 — Aggregation Models

Purpose: Combine baseball-mechanism signals into game-level probability estimates.

Examples:

- totals distribution model
- run differential model
- H2H win probability model

These models may consume:

- raw engineered features
- sub-model outputs
- uncertainty estimates

---

## Layer 4 — Market Intelligence / Meta-Models

Purpose: Estimate whether model-market disagreement is actionable.

Examples:

- expected CLV model
- edge persistence model
- market disagreement model
- timing sensitivity model

This layer is the ONLY layer permitted to consume:

- sportsbook lines
- bookmaker disagreement
- public betting signals
- line movement features
- market timing features

---

## Layer 5 — Risk & Portfolio Layer

Purpose: Translate edge estimates into bankroll decisions.

Examples:

- uncertainty-adjusted Kelly sizing
- exposure caps
- correlation-aware sizing
- portfolio optimization

---

# 5. Model Taxonomy and Training Strategy

This section defines each conceptual sub-model in terms of:

- purpose
- candidate training target
- effective training window
- Phase 9 output type
- downstream use
- market-data constraint

## Phase 9 Integration Decision

For Phase 9, the default implementation strategy is:

**Sub-models produce features/signals, not replacement probabilities.**

This means each sub-model should initially create additional model inputs such as:

- offense_signal
- starter_suppression_signal
- bullpen_state_signal
- run_environment_signal
- matchup_signal
- uncertainty_score

These features are tested in the existing modeling framework using:

- ablation tests
- temporal CV
- calibration comparison
- CLV diagnostics

A sub-model should only graduate from feature generator to probability-estimating replacement component after it demonstrates robust incremental value across multiple validation windows.

---

## 5.1 Offensive Quality Model

### Purpose
Estimate lineup-level run creation quality before first pitch.

### Candidate Training Target
Primary target:

- team runs scored in that game

Secondary / auxiliary targets:

- team wOBA in that game
- team xwOBA in that game
- team plate-appearance quality

### Training Target Considerations
Actual team runs are noisy and opponent-dependent. Two training approaches are viable:

**Option A — Opponent-controlled regression:**
Include opponent starter/bullpen quality features as controls. This estimates offensive output in context, but requires opponent features at prediction time.

**Option B — Park/opponent-adjusted offensive quality label:**
Pre-adjust the target for park and opponent quality before training. This estimates pure offensive talent, and the signal is more transferable at prediction time.

The recommended initial approach is **Option A** — it is simpler to implement and still removes the market circularity problem. Option B can be explored once a baseline is established.

### Effective Training Window
Standard Statcast/FanGraphs lineup features: 2016+.

FanGraphs projections or hitter archetypes may have narrower windows depending on data availability.

### Phase 9 Output Type
Feature generator.

Example outputs:

- lineup_run_creation_signal
- lineup_depth_score
- top_3_lineup_strength
- bottom_3_lineup_strength
- lineup_uncertainty_score

### Intended Use

- totals model
- H2H model
- future simulation engine

### Market Features Allowed?

No.

---

## 5.2 Starter Suppression Model

### Purpose
Estimate starting pitcher run suppression quality and expected depth.

### Candidate Training Target
Primary targets:

- starter runs allowed in game
- starter earned runs allowed in game
- starter outs recorded / innings pitched

Auxiliary targets (cleaner for true skill estimation):

- starter xwOBA allowed in game
- starter strikeout rate in game
- starter walk rate in game
- starter CSW% in game

### Training Target Considerations
Runs allowed are noisy and defense-dependent. xwOBA allowed, K%, BB%, and CSW% are cleaner proxies for true starter skill and are recommended for early versions.

A useful implementation trains separate signal heads for:

- run suppression
- expected depth
- command/strikeout quality

### Effective Training Window
Traditional Statcast starter features: 2016+.

Stuff+ / FanGraphs-driven features: likely 2021+ depending on coverage.

Bat-tracking interactions: July 2023+ only — treat as an optional feature block evaluated separately.

### Phase 9 Output Type
Feature generator.

Example outputs:

- starter_run_suppression_signal
- starter_expected_ip_signal
- starter_command_signal
- starter_uncertainty_score

### Intended Use

- totals model
- H2H model
- bullpen exposure model

### Market Features Allowed?

No.

---

## 5.3 Bullpen State Model

### Purpose
Estimate current bullpen availability, fatigue, quality, and late-game variance before first pitch.

### Candidate Training Target

**Version 1 — Fatigue/Availability Signal (recommended initial approach):**

The first version should predict a bullpen state index rather than game runs allowed directly. Training targets for this index:

- high-leverage reliever IP in prior 1/2/3 days
- closer availability proxy (rest days since last outing)
- high-leverage appearances in prior N days

This avoids the circularity problem in targeting game-day runs allowed (which conflates bullpen quality with game leverage, score state, and starter depth).

**Version 2 — Game-Level Runs Allowed (future):**

Once a game-state context model is available, a second version may target bullpen runs allowed conditioned on game leverage context. This is a more powerful but harder-to-train target.

### Training Target Considerations
Directly targeting "bullpen runs allowed after starter exit" is problematic because reliever usage depends heavily on score state, starter depth, and leverage context — factors determined partly by game outcomes. The Version 1 approach explicitly avoids this by treating bullpen state as an availability/fatigue index trained on pre-game workload features rather than in-game outcomes.

### Effective Training Window
2016+ for bullpen workload and effectiveness features.

Leverage-weighted features depend on availability of leverage calculations from game-state logs.

### Phase 9 Output Type
Feature generator.

Example outputs:

- bullpen_fatigue_signal
- bullpen_quality_signal
- high_leverage_availability_proxy
- late_game_volatility_signal

### Intended Use

- totals model
- H2H model
- future simulation engine

### Market Features Allowed?

No.

---

## 5.4 Matchup Model

### Purpose
Estimate lineup-vs-pitcher interaction quality.

### Prerequisite Dependency
This model requires **batter archetypes** and **pitcher archetypes** (cluster labels) to be defined and built before implementation. Archetype clustering is a prerequisite task, not an input that already exists.

### Candidate Training Target
Primary targets:

- lineup aggregate wOBA/xwOBA against the opposing starter type
- team offensive production while starter is in game
- plate-appearance outcome quality by batter archetype × pitcher archetype

Auxiliary targets:

- K% matchup outcome
- BB% matchup outcome
- ISO/power outcome
- hard-hit/barrel outcome

### Training Target Considerations
Direct batter-vs-starting-pitcher samples are too small to train at the individual matchup level. This model must use population-level groupings:

- batter archetype × pitcher cluster
- handedness × pitch mix
- bat-tracking profile × arsenal profile

Archetype clustering must be built as a prerequisite before this model can be developed.

### Effective Training Window
Traditional handedness/archetype features: likely 2021+ depending on cluster history.

Bat-tracking matchup features: July 2023+ only.

### Phase 9 Output Type
Feature generator.

Example outputs:

- matchup_advantage_signal
- matchup_k_pressure_signal
- matchup_power_signal
- matchup_volatility_signal

### Intended Use

- offense model
- totals model
- H2H model

### Market Features Allowed?

No.

---

## 5.5 Run Environment Model

### Purpose
Estimate scoring environment independent of team quality.

### Candidate Training Target

**Version 1 — Direct prediction with opponent controls:**

Primary target: total runs scored in game

Opponent quality (team offensive ratings, starter quality) included as training controls to isolate the park/weather/umpire effect. This is the recommended initial approach because it does not require a baseline model to exist first.

**Version 2 — Residual approach (future):**

Alternative target: residual total runs after subtracting a baseline team/starter/bullpen model's prediction.

Note: The residual approach requires a functioning baseline aggregation model to exist first and must be carefully implemented to avoid double-counting — the residualization step and the residual model training must use the same game-game data to avoid leakage.

### Training Target Considerations
Version 1 is simpler and avoids the chicken-and-egg problem inherent in the residual approach (which requires the baseline model to be built first). Version 2 produces a cleaner "pure environment" signal and is a natural evolution once the Layer 3 aggregation models are stable.

### Effective Training Window
Park features: 2016+.

Weather features: dependent on historical weather backfill quality.

Umpire features: dependent on umpire assignment and tendency history.

### Phase 9 Output Type
Feature generator — and a strong candidate for early implementation because the target is self-contained and doesn't depend on other sub-models.

Example outputs:

- run_environment_signal
- weather_run_modifier
- umpire_run_modifier
- environment_volatility_signal

### Intended Use

- totals model
- future simulation engine

### Market Features Allowed?

No.

---

## 5.6 Totals Distribution Model

### Purpose
Estimate game-level run distributions.

### Candidate Training Target
Primary target:

- total runs scored in game

Distribution targets:

- conditional quantiles of total runs
- probability total exceeds common betting lines
- variance / dispersion of total runs

### Training Target Considerations
This model must explicitly address the known variance-shrinkage failure in the current totals architecture (production model std(pred) = 0.77 vs. threshold 2.0). Evaluation should include not only MAE but:

- prediction spread (std of predicted values)
- quantile calibration
- over/under Brier score
- calibration by total-line bucket

Market features must not be included — if market lines are added, this becomes a Layer 4 model. The initial Phase 9 totals distribution model must be trained exclusively on baseball features.

### Effective Training Window
2016+ for non-market baseball features.

### Phase 9 Output Type
Feature/probability hybrid.

Initial output augments the existing totals model with:

- predicted mean
- predicted variance
- quantile features

Longer-term output may become a replacement totals probability model if validation supports promotion.

### Market Features Allowed?

No. Market comparison belongs downstream in Layer 4.

---

## 5.7 H2H Win Probability Model

### Purpose
Estimate game win probability.

### Candidate Training Target
Primary target:

- binary home win outcome

Alternative target:

- run differential distribution converted into win probability

### Training Target Considerations
The initial H2H model can remain close to the current production approach. The market-blind retrain (removing `_MARKET_COLS_TO_EXCLUDE`) is the first priority, not an architectural replacement. Future versions may derive win probability from simulated or distributional run outcomes.

Market prior must not be an input to this model.

### Effective Training Window
2016+ for standard baseball features.

Narrower windows apply if consuming newer sub-model features.

### Phase 9 Output Type
Initially, the existing production model remains champion. Sub-model outputs should first be tested as additional features before replacing the current H2H architecture.

### Market Features Allowed?

No.

---

## 5.8 Market Intelligence / Meta-Model Layer

### Purpose
Estimate whether model-market disagreement is historically actionable.

### Candidate Training Target
Primary target:

- positive CLV indicator

Alternative targets:

- CLV magnitude
- probability of beating close
- realized bet ROI after vig
- risk-adjusted return bucket

### Training Target Considerations
This model is data-starved until enough live CLV observations accumulate.

### Minimum Data Threshold

Do not train a production Layer 4 meta-model until:

| Stage | Minimum | Notes |
|---|---|---|
| Exploratory modeling | 500 CLV-labeled games | Descriptive analysis, signal buckets only |
| Production consideration | 1,000+ CLV-labeled games | Temporal CV, calibration, CLV gate required |

Before these thresholds, CLV should be used for monitoring, diagnostics, and descriptive research only.

### Effective Training Window
Live CLV tracking window only, unless historical CLV can be reconstructed reliably from stored odds snapshots.

### Phase 9 Output Type
Not a Phase 9 production model.

Initial output: descriptive CLV dashboards and signal bucket analysis.

### Market Features Allowed?

Yes — this is the correct and only layer for market data.

---

## 5.9 Sub-Model Output Interface

When a sub-model produces signals, they must be stored in a defined, versioned location so they can be consumed by downstream models and evaluated over time.

### Recommended Storage Pattern

Sub-model outputs should be materialized as a dedicated dbt mart, separate from the existing `feature_pregame_*` tables.

Example table name: `mart_sub_model_signals`

Schema:

```
game_pk           -- game identifier
side              -- home / away
signal_name       -- e.g. 'lineup_run_creation_signal'
signal_value      -- float
uncertainty       -- optional float
sub_model_version -- e.g. 'offensive_v1'
computed_at       -- timestamp
```

Alternatively, signals can be added as additional columns to a new `feature_pregame_sub_model_signals` mart that mirrors the structure of existing feature marts and joins cleanly at prediction time.

### Sub-Model Versioning Policy

Each sub-model must carry a version tag (e.g., `offensive_v1`). When a sub-model is retrained or its architecture changes:

- historical signal values are preserved (not overwritten)
- new values are written with an incremented version tag
- downstream model training records which sub-model version generated its features

This preserves historical model reproducibility — a requirement for valid temporal CV and CLV backtesting.

---

## 5.10 Data Window Policy

Each sub-model must explicitly document its effective training window.

| Feature Block | Effective Start | Notes |
|---|---|---|
| Standard Statcast features | 2016 | Good historical depth |
| FanGraphs Stuff+ | ~2021+ | Coverage-dependent |
| FanGraphs hitting leaderboard | ~2021+ | Coverage-dependent |
| Odds / market features | ~2021+ | Historical odds coverage varies |
| Bat tracking features | 2023-07-14 | Only treat as optional feature block |
| Weather features | Dependent | Historical backfill quality matters |
| CLV meta-model | Live window only | See Section 5.8 threshold |

Sub-models with short availability windows should be treated as optional feature blocks and evaluated separately from full-history baseline models.

---

# 6. Probabilistic Modeling Philosophy

The architecture does NOT require all models to be fully Bayesian.

The intended direction is a hybrid architecture:

- deterministic feature engineering
- deterministic baseline sub-models
- selective probabilistic modeling where uncertainty materially improves decisions

Probabilistic modeling is expected to be most useful for:

- totals distributions
- bullpen uncertainty
- rookie stabilization
- early-season modeling
- uncertainty-aware bet sizing

The architecture intentionally allows:

- deterministic implementations
- probabilistic implementations
- ensemble approaches
- simulation-based approaches

without tightly coupling the entire stack to one methodology.

---

# 7. Research Constraints & Realism

## Acknowledged Constraints

The architecture acknowledges:

- MLB sample sizes are relatively small compared to many ML domains (~10K training games)
- stacked architectures can propagate noise and frequently underperform well-tuned single models on small datasets
- CLV data accumulation will take time (current live window: ~41 games as of May 2026)
- some advanced layers (meta-model, simulation) may require multiple seasons of data
- archetype clustering is a prerequisite for the matchup model and does not yet exist
- the temporal data platform (Section 9) is a multi-phase infrastructure evolution, not achievable in a single phase

The architecture therefore prioritizes:

- incremental integration
- modular validation
- independent signal evaluation
- calibration monitoring
- CLV benchmarking

---

# 8. Validation Philosophy

All proposed models and signals should be evaluated using:

- temporal validation (walk-forward, not random splits)
- calibration metrics (ECE, reliability diagrams)
- CLV performance where live data is available
- robustness across seasons
- uncertainty quality (sharpness, coverage)

The architecture explicitly rejects:

- leakage-prone evaluation
- random train/test splits
- purely accuracy-based optimization

The primary objective is:

- market-relative edge quality
- calibration
- long-term robustness

NOT raw win-rate optimization.

---

# 9. Temporal Data Modeling and Backtesting Philosophy

## Purpose

A core architectural requirement is the ability to:

- reproduce the state of the world at a prior point in time
- prevent leakage from future information
- rerun historical predictions using only information available before first pitch
- evaluate historical CLV and model-market disagreement
- support realistic walk-forward validation and simulation

---

## Core Principle

Every feature used for modeling must answer the question:

> "What information was actually available before the game started?"

The architecture explicitly rejects:

- leakage from future games
- retroactively revised statistics
- finalized season aggregates
- future lineup or injury knowledge
- postgame feature recomputation

---

## Scope Note

The full temporal data platform described in this section represents a **multi-phase infrastructure evolution**, not a Phase 9 deliverable.

Phase 9 scope should be limited to:

- identifying which tables most urgently need SCD treatment
- adding `feature_ts` or `computed_at` timestamps to new sub-model output tables
- avoiding new leakage patterns in new feature marts

The SCD Type-2 migration, point-in-time join patterns, and historical CLV reconstruction infrastructure are Phase 10+ targets. They are documented here as the intended long-term direction.

---

## Recommended dbt Modeling Philosophy

The dbt project should evolve toward a temporal modeling architecture built around:

- append-only facts
- snapshot tables
- slowly changing dimensions (SCDs)
- point-in-time joins
- feature materialization timestamps

The goal is to make historical model reconstruction deterministic and reproducible.

---

## Slowly Changing Dimension (SCD) Guidance

### SCD Type-2 Should Be Used When:

The state of an entity changes over time and historical reconstruction matters.

Examples (priority order for Phase 10):

- projected starting pitchers
- lineup projections
- team offensive quality
- bullpen availability
- player injury status
- weather forecasts
- market odds snapshots
- bookmaker consensus lines

The purpose is to preserve `effective_start_ts`, `effective_end_ts`, `current_flag`, and state transitions over time.

---

## Point-in-Time Feature Engineering

All model feature generation should eventually support AS OF semantics:

```sql
select *
from feature_table
where feature_ts <= prediction_ts
qualify row_number() over (
    partition by entity_id
    order by feature_ts desc
) = 1
```

The modeling system should never consume features whose timestamps occur after prediction time, lineup lock, or game start depending on the evaluation window.

---

## Recommended Temporal Feature Categories

### Append-Only Event Facts
- pitch events
- plate appearances
- game logs
- bullpen appearances
- odds snapshots
- lineup announcements
- injury/news events

These tables should generally be immutable.

### Snapshot/SCD Tables
- projected lineup state
- projected bullpen state
- team form state
- market state
- weather state

### Derived Point-in-Time Features
- rolling offensive metrics
- rolling pitcher metrics
- bullpen fatigue signals
- lineup quality signals
- market movement features

---

## Historical CLV Reconstruction

A major long-term objective of the temporal architecture is the ability to reconstruct historical:

- model predictions
- market state
- recommendation timing
- closing line value

This requires storing:

```
prediction_ts
odds_at_prediction
closing_odds
lineup_state_version
feature_snapshot_id
model_version
sub_model_version (per signal)
```

---

## CLV Backtesting Goal

The long-term objective is to support:

```
Historical game state
→ recreate point-in-time features
→ rerun historical model
→ compare against historical closing line
→ estimate historical CLV
```

This is significantly more valuable than simple outcome backtesting because CLV stabilizes faster than realized ROI and better measures market-relative signal quality.

---

## Temporal Validation Constraints

All validation pipelines should enforce:

- no future leakage
- event-time-aware joins
- rolling walk-forward windows
- timestamp-aware feature generation
- historical feature reconstruction

The architecture explicitly rejects:

- finalized-season feature computation
- retroactive stat adjustments leaking into training
- non-temporal joins
- shuffled/random train-test splits

---

# 10. Long-Term Vision

The long-term goal is to evolve the system into a broader:

> "probabilistic sports intelligence platform"

Potential future outputs:

- betting intelligence
- fantasy optimization
- simulation APIs
- sports analytics dashboards
- sports data products
- B2B analytics

The architecture is therefore intentionally designed to:

- separate domain mechanisms
- expose reusable signals
- support simulation and probabilistic reasoning
- scale beyond a single monolithic prediction model

---

# 11. Summary

This architecture should be interpreted as:

- a conceptual research direction
- a modular quantitative systems framework
- an incremental decomposition strategy

It should NOT be interpreted as:

- an immediate production implementation plan
- a mandatory sequential dependency graph
- a proposal to replace the existing production system all at once

The existing production models remain the baseline system.

Sub-models are intended to:

- augment
- explain
- stabilize
- refine
- and eventually improve

market-relative predictive quality over time.
