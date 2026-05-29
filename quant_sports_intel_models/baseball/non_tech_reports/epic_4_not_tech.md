# What We Built: Offensive Quality Model (Epics 4, 4A & 4D)

**Last updated:** May 29, 2026

---

## The Problem We Were Solving

When a betting line is set for a total (e.g., Over/Under 8.5 runs), the market is pricing in the offensive quality of both lineups. Our models had no independent way to assess lineup strength — we were relying on the same surface-level stats the market already knows.

The goal of these epics was to build a clean, systematic measure of lineup quality that we compute ourselves, independent of the market line, so we can compare our read against the market's.

---

## Epic 4A — Teaching the Model to Handle Small Samples (Empirical Bayes)

This was foundational work that had to be done before the main model could be trained properly.

### The core problem: early-season stats are noisy

In April, most batters have played only 10–20 games. A player hitting .380 through 15 plate appearances looks great, but that sample is nearly meaningless. A player hitting .200 might be in a slump or might just be unlucky. The raw stats overreact to small samples.

**Empirical Bayes (EB)** is a statistical technique that solves this by shrinking early-season numbers toward a population expectation — specifically toward what we'd expect for a player of that type (lineup role and handedness), based on how the whole population of similar batters has historically performed. As the season progresses and a player accumulates real plate appearances, we gradually let their observed stats take over.

Think of it like this: if you flip a coin 5 times and get 4 heads, you wouldn't conclude it's a biased coin. But if you flip it 500 times and get 400 heads, you'd be confident. EB applies this logic to batting stats automatically.

### What we built

**Prior fitting (4A.1):** For each season from 2015 onward, we fit statistical distributions for key batting metrics (weighted on-base average, strikeout rate, walk rate, isolated power) broken out by:
- Batting order role: top of order (slots 1–3), middle (4–6), bottom (7–9)
- Handedness: left, right, switch

This gives us a sensible expectation for any batter based on their type. A cleanup hitter should be expected to hit much better than a 9-hole placeholder — EB respects that.

**Posterior estimates (4A.2):** For every batter who appeared in a lineup from 2015 through today, we computed a shrinkage estimate: a weighted blend of their current-season stats and their prior expectation. The blend automatically adjusts based on how many plate appearances they've accumulated. Rookies with no MLB track record fall back to ZiPS projections (a reputable third-party projection system).

We stored these estimates for every game going back to 2015 — over 50,000 batter-game records.

**Feature integration (4A.3):** These EB estimates were added to our lineup feature table in the data warehouse, with full coverage from 2015 through 2026. Zero missing values across the entire history.

**Ablation test (4A.4):** We ran a head-to-head test: does using EB estimates predict run scoring better than just using raw stats? The answer was a statistical tie (+0.0001 MAE difference) for full-season data — but this is expected. The real advantage shows up in April and for lineups with many low-PA batters, where raw stats are least trustworthy. Rather than choosing one, we kept both sets of features and let the main model (LightGBM) decide which it prefers. It turned out EB wOBA ranked #1 in feature importance and EB ISO ranked #2 — the model strongly preferred the stabilized estimates.

---

## Epic 4 — The Offensive Quality Model (v1)

With the EB infrastructure in place, we trained the core model.

### What we built

**Training data (4.1):** We extended our training dataset back to 2015, giving us 10 full years of game data (roughly 50,000 game-team observations — one row per team per game). The target was simple: how many runs did this team score in this game?

**Model training (4.2):** We compared two model types:
- **Ridge regression** — a fast, interpretable linear model
- **LightGBM** — a gradient-boosted decision tree model that can capture non-linear interactions

We used 8-fold walk-forward cross-validation: train on 2015–2017, test on 2018; then train on 2015–2018, test on 2019; and so on through 2025. This is the most honest way to evaluate a time-series prediction model — you never train on future data.

LightGBM won with a mean absolute error of **2.45 runs per game-side** (vs. Ridge at 2.49). Over 8 test years, the average prediction was within about 2.45 runs of actual — a reasonable result given the inherent randomness of baseball scoring.

Key finding: The EB uncertainty score (how uncertain we are about a lineup's quality) ranked 13th out of 60 features in the LightGBM model, which is notable for a derived feature. This flags it as a potential standalone signal in future work.

**Signal generation (4.3):** We ran the trained model over every game from 2015 through today and stored two signals for each team in each game:
- **Predicted runs** (`pred_runs_raw`): the raw model output
- **Runs index** (`runs_index`): the predicted runs normalized to league average for that season (100 = league average offense; 110 = 10% better than average)

We backfilled 51,228 game-side records and built a data warehouse view that exposes these signals for downstream models to consume.

**Ablation test (4.4):** We tested whether adding these offense signals improves our existing game-totals and run-differential predictions. The result was a slight improvement (−0.008 and −0.010 MAE respectively), with the regression gate passing easily. The near-zero delta is expected at this stage — the signals are a compression of features the main model already sees. The real payoff comes in Epic 9, where sub-model outputs will *replace* raw features in a stacked architecture.

---

## Epic 4D — From a Single Number to a Full Distribution (v2)

This was an upgrade to the offensive quality model. Instead of asking "how many runs will this team score?" and getting back one number, we now ask the same question and get back a full probability curve — answering questions like "what's the chance they score 6 or more?" or "how much uncertainty is there about this lineup's output?"

### Why distributions matter for betting

A point prediction (e.g., "this team will score 4.1 runs") treats all 4.1-run predictions as equally confident. But a team with Shohei Ohtani batting cleanup in a hitter's park is a very different 4.1 than a patchwork lineup in a pitcher's park after three days of rain. The *uncertainty* around the prediction is information — and the market doesn't always price it correctly.

By modeling the full distribution, we can:
- Compute the probability that a team scores over or under any threshold (directly useful for totals and first-5 bets)
- Quantify how tight or wide our confidence interval is, which tells us when to trust a bet and when to stay out
- Combine our offensive distributions with our run environment and starter suppression distributions to build a proper joint model in Epic 9

### What the distribution looks like

We use a **Negative Binomial distribution** — a standard model for count data (how many times something happens) that handles the extra variability in baseball scoring better than simpler alternatives. Two numbers define this distribution for each game-side:

- **Mean (μ):** The center of the prediction. Typical values are 3.9–4.2 runs per game-side.
- **Dispersion (r):** How spread out the distribution is around that mean. A fitted value of r ≈ 3.48 was learned from 10 years of historical data and held constant for all predictions.

From these two numbers, we can compute the probability of any specific run total.

### What we built (4D.1 / 4D.2) — Model training

We retrained the offensive quality model using the same 60 lineup features and 8-fold walk-forward cross-validation as v1, but the scoring function changed: instead of minimizing average error, we minimized **negative log-likelihood** under the Negative Binomial distribution. This means the model is rewarded not just for getting the mean right, but for correctly shaping the probability curve.

We compared three candidates:
- **LightGBM + NegBin** (gradient-boosted trees with distributional loss)
- **NGBoost** (a distributional boosting framework)
- **GLM baseline** (a standard statistical model used as a minimum bar)

LightGBM won:
- CV NLL (log-likelihood): **2.484** — just below the GLM baseline floor of 2.487
- CV MAE: **2.459 runs** — essentially matching v1 accuracy while also producing valid uncertainty estimates

The trained model is stored as `offense_v2.pkl` on S3 and registered as the new champion, superseding v1.

### What we built (4D.3) — Signal generation

We scored the v2 model against every game from 2015 through today and stored four signals per team per game:

| Signal | What it means |
|---|---|
| `pred_runs_mu` | The predicted mean runs scored for this team in this game |
| `pred_runs_dispersion` | The dispersion parameter r (constant; tells you the distribution shape) |
| `pred_runs_raw` | Same as `pred_runs_mu` — kept for compatibility with v1 consumers |
| `uncertainty` | The width of the 80% prediction interval (e.g., 7 means there's an 80% chance the team scores within a 7-run band centered on the mean) |

51,228 game-side records were backfilled covering 2015–2026.

### What we built (4D.4) — Integration

The four v2 signals were added to the main feature view (`feature_pregame_sub_model_signals`) that all downstream models read from. Any model in the stack can now consume the full distributional output of the offensive quality model without knowing the internals.

---

## What This Means Going Forward

We now have two layers of offensive quality signals available for every game since 2015:

- **v1** (deprecated but retained): A point prediction of expected runs, bias-corrected, with a runs index normalized to league average
- **v2** (champion): A full probability distribution over run scoring, with explicit uncertainty quantification

Both are market-blind — they're built entirely from lineup composition and historical performance, not from what the line is set at.

In Epic 9 (the stacked model), these distributional signals will be combined with run environment (weather, park, umpire) and starter suppression into a joint probability model over total runs and run differential — which we'll compare directly against Bovada's implied probabilities to find edges.

---

## Summary of Outputs

| Deliverable | What It Is |
|---|---|
| `offense_v1.pkl` (S3) | LightGBM point-prediction model (deprecated; superseded by v2) |
| `offense_v2.pkl` (S3) | LightGBM + NegBin distributional model (champion) |
| `offense_v1_signals` (Snowflake) | 51,228 rows: pred_runs_raw, runs_index (2015–2026) |
| `offense_v2_signals` (Snowflake) | 51,228 rows: pred_runs_mu, pred_runs_dispersion, pred_runs_raw, uncertainty (2015–2026) |
| `lineup_priors_{year}.json` | Statistical priors for each batting role × handedness × season cell |
| `eb_batter_posteriors_raw` (Snowflake) | EB shrinkage estimates for every batter in every lineup |
| `feature_pregame_lineup_features` (Snowflake) | Lineup feature table with EB columns, zero nulls, 2015–2026 |
| `feature_pregame_sub_model_signals` (Snowflake) | Game-level view exposing all v1 and v2 offensive signals for downstream models |
