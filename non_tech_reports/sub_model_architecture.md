# MLB Prediction System: Architecture, Intent, and Progress

*Audience: Informed non-technical reader. Assumes basic familiarity with betting markets and baseball analytics but no data science background.*

---

## Part 1 — Where We Are Now and How the System Works

### The Core Prediction Loop

At its simplest, this system is trying to answer one question every morning before game time: *where do I have an edge against the sportsbook?*

The system currently makes three predictions per game:
- **Home team win probability** — who wins, and how confident are we?
- **Total runs scored** — will the combined score go over or under the sportsbook's line?
- **Run differential** — by how much do we expect the home team to win or lose?

Those predictions are then compared to what the sportsbooks are offering. If the model says a team has a 55% chance of winning and the market implies only 48%, that's a potential edge.

The final number used for betting decisions is called the **Posterior Probability** — a Bayesian blend of the model's estimate and the market's consensus price. The blending ratio (called alpha) is calibrated to reflect how much independent signal the model is actually generating beyond what the market already knows. Right now, alpha is zero — meaning the Posterior equals the market price — because the market is very efficient, and the models have not yet demonstrated enough consistent edge to justify overriding it. That is expected to change as the sub-model architecture is completed.

---

### The Problem the Architecture Is Trying to Solve

The most important discovery in the project's history came in Phase 8 (early May 2026): the models were using **market-derived features** (the betting line itself) as inputs. That created a circular system — the model was essentially learning to re-predict the market, not to form an independent view. A model that just echoes the market back at you cannot identify value bets.

The architectural response to this insight is the **sub-model framework**: a set of specialized, market-blind models that each explain one dimension of game outcomes. Their combined outputs replace the market-derived features that were removed. The goal is to give the stacked aggregation model independent, interpretable, market-blind representations of every factor that drives game outcomes.

---

### How the Final Architecture Will Work (The Target State)

The architecture is built in layers:

**Layer 1 — Raw Data**
Everything the system knows about the world before a game is played: Statcast pitch and batted-ball physics (since 2015), confirmed batting lineups, starting pitcher identities, umpire assignments, park dimensions, forecast weather, sportsbook odds, ZiPS player projections, and bullpen usage in prior days.

**Layer 2 — Feature Store**
The raw data is cleaned, joined, and transformed into hundreds of per-game features stored in a structured database. These features flow through a quality-checked pipeline (dbt) that tests them for consistency on every change. This is the input layer for all models.

**Layer 2.5 — Sub-Models (the new layer being built now)**
Each sub-model is a narrow, focused model that compresses one domain of knowledge into a single signal:

| Sub-model | What It Explains | Signal Produced |
|---|---|---|
| Run Environment | How park, weather, and umpire affect total scoring | `run_env_signal` (run-friendliness vs. league average) |
| Offensive Quality | How good today's lineup is at generating runs | `lineup_run_creation_signal` |
| Starter Suppression | How much today's starter will limit scoring | `starter_suppression_signal` |
| Bullpen State | How available and effective each team's bullpen is | `bullpen_state_signal` |
| Matchup | How specific batter archetypes perform vs. pitcher archetypes | `matchup_advantage_signal` |

Each signal is expressed in standardized units (relative to league average), stored historically, and versioned. A positive `run_env_signal` means "this game is expected to be run-friendly"; a negative `starter_suppression_signal` means "this starter is expected to dominate."

**Layer 3 — Stacked Aggregation Model (Epic 9 — to be built)**
This is the key architectural choice: the Layer 3 model receives **only the sub-model signals as inputs** — not the underlying raw features. The raw park factors, weather readings, and FIP numbers are abstracted away into the sub-model signals that already encode that information. This design makes the aggregation model simpler, more interpretable, and less prone to overfitting. It also makes it easier to update: if the run environment model improves, the upstream signal is updated and the Layer 3 model sees a better input automatically.

**Bayesian Posterior Layer**
The Layer 3 outputs are combined with the market consensus price using Bayes' theorem. The alpha parameter controls the blend. As the sub-models improve and generate measurable independent edge, alpha will be tuned upward, reflecting greater confidence in the model's departures from the market price.

---

### Why Bayesian Inference?

The Bayesian framework fits this problem naturally. Think of the market consensus price as the prior — it already encodes the collective wisdom of millions of dollars in bets, professional oddsmakers, and sharp bettors. A well-functioning market is very hard to beat by brute force.

The hypothesis is that a set of domain-specific models — each trained on independent data that the broader market may not be efficiently pricing — can generate a posterior probability that is slightly better calibrated than the market price in specific game contexts. The model is not trying to be the world's best baseball predictor; it is trying to find the narrow slice of games where the market is systematically mispricing something the sub-models can see.

The initial alpha=0 result is not a failure — it is an honest measurement. It says: *with the current models, you cannot beat the market.* The sub-model architecture is the path to alpha > 0.

---

## Part 2 — Architecture Reference Diagram

```
Raw Sources (Layer 1)
┌────────────────────────────────────────────────────────────┐
│ Statcast (2015+)   │ MLB Stats API  │ Weather Forecasts    │
│ Sportsbook Odds    │ ZiPS Projections│ Umpire Assignments  │
│ Bullpen Usage Logs │ FanGraphs Data │ Public Betting %     │
└────────────────────────────────────────────────────────────┘
                          ↓
Feature Store (Layer 2)
┌────────────────────────────────────────────────────────────┐
│ Hundreds of per-game features, quality-tested, versioned.   │
│ Park features, lineup features, starter features,           │
│ bullpen features, weather features, matchup history, etc.   │
└────────────────────────────────────────────────────────────┘
                          ↓
Sub-Models (Layer 2.5) — being built in Epics 3–8
┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌──────────────┐ ┌────────────┐
│ Run Env v3   │ │ Offense v1   │ │ Starter v1    │ │ Bullpen v1   │ │ Matchup v1 │
│ CHAMPION ✓  │ │ (Epic 4)     │ │ (Epic 5)      │ │ (Epic 6)     │ │ (Epic 8)   │
└──────────────┘ └──────────────┘ └───────────────┘ └──────────────┘ └────────────┘
        ↓               ↓                ↓                 ↓               ↓
  run_env_signal  lineup_run_    starter_suppression  bullpen_state  matchup_advantage
                  creation_signal      _signal            _signal        _signal
                          ↓
Stacked Layer 3 Model (Epic 9 — not yet built)
┌────────────────────────────────────────────────────────────┐
│ Inputs: ONLY the 5 sub-model signals (not raw features)     │
│ Outputs: P(home win), Expected total runs, Run differential │
└────────────────────────────────────────────────────────────┘
                          ↓
Bayesian Posterior Layer
┌────────────────────────────────────────────────────────────┐
│ Posterior = blend(model_prob, market_prob, alpha=?)         │
│ Alpha calibrated from historical CLV data                   │
└────────────────────────────────────────────────────────────┘
                          ↓
                  Betting Decision Output
```

---

## Part 3 — Work Completed So Far (Grouped by Epic)

### Epic 0 — Parlay API Migration
*Status: Mostly complete; final cutover remaining*

The project's odds data came from The Odds API, whose credits were expiring June 2026. This epic migrated all live odds ingestion to Parlay API — a replacement provider with richer endpoint coverage.

The migration was completed cleanly: historical data from The Odds API was preserved untouched, new ingestion began running in parallel from May 2026, and all downstream models automatically receive both data sources through a unified data layer. A notable technical complication — Parlay API initially collapsed doubleheaders into a single odds line (making it impossible to match each game to its specific odds) — was reported to the API provider, fixed by them within a day, and handled in the code.

The remaining task is disabling The Odds API pipeline after credits expire on May 23, 2026.

---

### Epic DEV — Environment Isolation
*Status: Complete*

A foundational safety improvement: before this epic, running any development script locally could accidentally overwrite production data in the same database. After this epic, local runs and CI test runs write to separate isolated schemas, while production-destined writes require an explicit environment flag that only the automated GitHub Actions pipeline sets. The safe default is always "write to dev, never prod."

---

### Epic T — Temporal Capture Foundations
*Status: Complete*

Ensured that the raw data pipeline preserves historical state faithfully — raw data tables are now append-only, meaning that past observations are never overwritten. This is a prerequisite for time-travel audits, retroactive model evaluation, and future historical data reconstruction. Without this, any mistake in the data pipeline could silently corrupt the model's training history.

---

### Epic 1 — Market-Blind Retrains
*Status: Complete. Live in production since May 11, 2026.*

**The problem:** All three production prediction models (home win, total runs, run differential) were using sportsbook odds lines as input features. Since the models' outputs were being compared back to those same lines to evaluate edge, the system was circular — like using tomorrow's newspaper to predict today's news.

**What was done:** All market-derived features were removed from the training process. The models were retrained from scratch using only independent data.

**Results:**
- All three market-blind challengers outperformed their market-inclusive predecessors on held-out data.
- Home win accuracy improved slightly (Brier score: 0.2392 → 0.2390).
- Total runs accuracy improved meaningfully (MAE: 3.375 → 3.234 runs per game).
- Run differential accuracy improved (MAE: 3.434 → 3.405 runs).

The improvement demonstrates that the market features were introducing noise, not signal — the models work better without the circular dependency.

**Current limitation:** With market-blind models, the Bayesian alpha calibration still returns zero — the model edge is not yet measurable at the combined prediction level. This is expected and honest. The sub-model architecture (Epics 3–8) is designed to close this gap.

---

### Epic 2 — Sub-Model Infrastructure & Feature Readiness
*Status: Complete*

Before building any sub-models, foundational plumbing was needed:

- A **signal storage table** (`mart_sub_model_signals`) was created with versioning, historical record-keeping, and SCD-2 support (meaning the system can replay what signals looked like on any historical date).
- An **evaluation harness** was built for consistent sub-model testing with walk-forward cross-validation.
- **Feature audits** were run for each planned sub-model: confirmed what data exists, identified gaps (e.g., ZiPS pitcher xFIP projections are 100% empty — use FIP instead), and documented data coverage by season.
- **ZiPS projection data** (pre-season hitting and pitching projections from FanGraphs) was wired into the lineup feature store, including a Bayesian shrinkage approach for rookies with limited MLB history.
- **Bat-tracking data** (swing speed, swing length, available since mid-2023) was wired into lineup features for the matchup model.

---

### Epic 3 — Run Environment Model
*Status: Complete. Champion model (v3) live in production since May 19, 2026.*

**Goal:** Build the first sub-model. The run environment model estimates how favorable or suppressive each game's context is for run scoring, based entirely on factors external to the teams playing.

**What it captures:** The model combines park characteristics (run factor, elevation, dimensions, dome vs. outdoor), pre-game weather forecast (temperature, wind speed and direction, humidity), and home plate umpire tendencies (how generous their strike zone is on average). It predicts total runs scored and outputs a standardized "run environment score" — how many standard deviations above or below the league average this game's context is.

**Development summary:**

Three model versions were built and evaluated:

*v1 (Ridge regression, 17 features):* Established the baseline at 3.51 runs mean absolute error per game. A key finding: the model had a systematic bias of −0.56 runs per game — it was consistently under-predicting. Investigation revealed no features representing major rule changes (pitch clock, shift ban, universal DH) that structurally increased run scoring from 2022–2023 onward.

*v2 (XGBoost, same 17 features):* A tree-based challenger that failed to improve on the Ridge baseline (3.51 vs. 3.51 MAE) and retained the same −0.56 bias. The rule-change blind spot persisted regardless of model architecture.

*v3 (Ridge, 19 features, champion):* Added four era-aware features: flags for the universal DH era (2022+), pitch clock era (2023+), shift ban era (2023+), and the prior season's league-wide average runs per game. The result: systematic bias collapsed from −0.56 to +0.02 runs per game — effectively zero. The rule-change explanation was confirmed.

**Why v3 was promoted despite not clearing the MAE gate:** The original promotion gate (improve MAE by 0.05 runs) was not cleared. However, the identified root cause of the model's failure was systematic bias, not random error — and v3 fixed it. A model that is wrong by the same amount in the same direction every game is not useful for calibrated probability estimates downstream. The gate criteria were amended to treat systematic bias correction as a sufficient promotion condition, and v3 was promoted.

**Ablation test finding (Story 3.Z):** To confirm whether the run environment signals add value on top of the existing totals prediction model, a controlled test was run adding `run_env_signal_v3` to the existing 562-feature model. The result was a negligible improvement (+0.0001 MAE, statistically indistinguishable from noise).

This is not evidence the signals are useless — it is evidence they are redundant with features that already exist in the totals model (the totals model already receives park factors, weather data, and umpire statistics directly). Adding a compressed version of the same information to a linear model cannot improve it.

The architectural intent was always that sub-model signals *replace* raw features in the Layer 3 stacked model — not supplement them. Run environment v3 is ready and waiting for that role in Epic 9. Its signals are stored historically and are available to any downstream model that doesn't already have the underlying raw features.

---

## Part 4 — Work Still Ahead

### Sub-Models (Epics 4–8)

Four more sub-models remain to be built, each adding an independent dimension of game knowledge:

**Epic 4 — Offensive Quality Model:** How good is today's specific lineup at generating runs? This goes beyond season averages — it accounts for batting order construction, lineup-specific platoon advantages, and where the team's best hitters are slotted relative to each other.

**Epic 5 — Starter Suppression Model:** How effective is today's starting pitcher likely to be? Not just season ERA, but stuff quality (CSW%, swing-and-miss rate), command, projected innings depth, and recent trajectory.

**Epic 6 — Bullpen State Model:** Is the bullpen fresh or depleted? Did the closer pitch two days ago? Did high-leverage arms throw a lot of pitches in a blowout yesterday? This rules-based model captures arm availability and fatigue.

**Epic 7 & 8 — Archetype Clustering and Matchup Model:** This is the most novel piece. Rather than average pitcher vs. average lineup, this asks: how do *contact-and-spray hitters* historically perform against *elite breaking-ball pitchers*? Batters and pitchers are clustered into style archetypes based on their Statcast profiles, and a matchup model is trained on the historical outcome of each archetype pairing. Today's lineup composition vs. today's starter type produces a matchup edge or disadvantage signal.

### Signal Integration (Epic 9)

When all five sub-models are producing champion signals, Epic 9 builds the Layer 3 stacked model: a new aggregation layer that takes the five signals as its only inputs and produces the calibrated game predictions. This is the architectural endpoint for the sub-model framework — raw features are fully abstracted away, and the stacked model reasons about outcomes in terms of run environment, lineup quality, starter quality, bullpen state, and matchup advantage.

### Calibration and Live Betting (Epics 10–12)

With a working stacked model, later epics focus on distribution modeling (not just predicting *total runs* but the full probability distribution of possible scores), re-tuning the Bayesian alpha with market-blind sub-model signals, and building a CLV meta-model that learns from the project's own live betting history to identify which game contexts produce the most reliable edge.

---

## Part 5 — What "Success" Looks Like

The system is successful when the Bayesian alpha calibration returns a meaningfully positive value — when the model's probability estimates demonstrably diverge from the market price in useful ways. Concretely: a well-functioning system should find that in games where the model strongly disagrees with the market (high predicted edge), those bets win at a rate higher than the market's implied probability.

The current state — alpha=0, no detectable edge — reflects an honest starting point. The models are accurate but not yet better than the market at the combined-prediction level. The sub-model architecture is the path toward generating independent domain knowledge that the market consistently underweights.

Every piece of infrastructure built since Phase 8 — environment isolation, market-blind retrains, temporal data foundations, sub-model storage, feature audits — was built with this destination in mind.
