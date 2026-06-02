# What We Built: Bullpen Model (Epics 6, 6A & 6D)

**Last updated:** June 1, 2026

---

## The Problem We Were Solving

Starters don't finish games anymore. On an average MLB night, the bullpen throws roughly 3–4 innings per game — sometimes more, sometimes all nine. Whether a bullpen is rested, depleted, loaded with high-leverage arms, or relying on mop-up relievers is one of the biggest variables in whether a game goes over or under a run total. The market prices this in, but imperfectly — especially for series-final games and day games following a late-night affair.

The goal of these epics was to build a systematic pre-game bullpen read: how fatigued are the key arms, how good is this bullpen's quality, how many runs should we expect them to allow, and how uncertain are we about all of it?

---

## Epic 6A — Teaching the Model to Handle Small Samples (Empirical Bayes)

Individual reliever stats are even noisier than starter stats. Closers might appear in only 2–3 games per week. Setup arms cycle in and out. A reliever who was dominant last season but has thrown in 8 of the last 10 games is a very different proposition than the same pitcher fully rested.

### The core problem

Rolling reliever xwOBA over the last 14 days is too noisy to trust, especially early in a season or after an injury return. A reliever who's allowed 3 runs in his last 4 appearances looks terrible — but was he pitching in blowouts (leverage-independent) or protecting a 1-run lead (high-stakes)? The raw numbers don't distinguish.

**Empirical Bayes (EB)** solves the sample-size problem by shrinking each reliever's current-season stats toward the population expectation for their role. We stratify by leverage role (closer/high-leverage setup, middle relief, low-leverage/mop-up) and age band, because a 24-year-old middle reliever and a 34-year-old high-leverage arm should have very different prior expectations.

### What we built

**Prior fitting (6A.1):** For each season from 2016 onward, we fit priors for key reliever metrics — xwOBA-against, strikeout rate, walk rate — broken out by leverage role and age band. Role is determined by each reliever's prior-season average leverage index (aLI), which is a standard measure of how often they pitch in high-stakes situations.

**Posterior estimates (6A.2):** For every reliever-game from 2016 through today, we computed a shrinkage estimate using the same Normal-Normal conjugate update as the starter model. Relievers who have faced very few batters (early season or IL return) lean heavily on their role-and-age prior. Veterans with 200+ batters faced in-season get almost no shrinkage.

**Feature integration (6A.3):** EB bullpen estimates were added to the bullpen feature table in the data warehouse. Every game from 2016 onward now has EB-stabilized reliever quality estimates available.

**Ablation test (6A.4):** Does EB help? We tested by running the bullpen model with and without EB features and comparing predictions against actual outcomes across 5 walk-forward folds. The EB version improved MAE by **−0.0045 runs** on all 5 folds — consistent improvement even if the absolute magnitude is small. The gate passed, and EB features were retained as inputs to the full model.

---

## Epic 6 — The Bullpen State Model (v1)

With stabilized reliever quality estimates in place, we built the core bullpen model.

### What the model does

The target is **bullpen xwOBA** — the expected quality of contact the bullpen allows per batter faced in this game. Rather than predicting runs directly (which depends on leverage context, runners on base, and other in-game factors we can't fully observe pre-game), we predict contact quality, which is the more stable and more predictable pre-game signal.

The model also generates a **bullpen availability index**: a rules-based composite of how much each team's bullpen has been used over the last 1–3 days, weighted by the leverage of those appearances. This captures the fatigue angle — a bullpen that threw 7 innings yesterday in a 14-inning marathon is materially different from one that rested while the starter went 8.

### What we built

**Training dataset (6.1):** 45,947 team-game rows spanning 2016–2026 (11 full seasons), including rolling bullpen xwOBA, strikeout/walk rates, high-leverage appearance counts, closer rest days, and the EB posterior quality estimates from 6A.

**Model training (6.3):** We compared NGBoost Normal (a distributional boosting framework) against LightGBM with separately fitted uncertainty. NGBoost won on every fold:

| Candidate | NLL Score | Calibration | Result |
|---|---|---|---|
| LightGBM + sigma | -0.6357 | — | Runner-up (lost all 10 folds) |
| NGBoost (initial) | -0.7602 | 76.7% | Starting point |
| **NGBoost (Optuna-tuned)** | **-0.8579** | **76.7%** | **Champion** |

After Optuna tuning (optimizing the number of trees, learning rate, and minibatch fraction), the final NLL improved from -0.7602 to **-0.8579** — a meaningful gain. The Wilcoxon p-value comparing NGBoost vs. LightGBM across 10 folds was 0.002, confirming the result isn't noise.

The calibration (76.7%) is below the 80% ideal, but this was flagged as expected for Case 1 (first champion, no prior baseline) and does not block advancement. The distributional retrofit in Epic 6D directly addresses calibration.

**Signal generation (6.4):** We scored the champion model over every game from 2021 through today and stored 7 signals per team per game — covering fatigue, quality, high-leverage arm availability, and late-game volatility:

- **180,551 signal rows** (25,793 team-games × 7 signals) backfilled for 2021–2026

**Ablation test (6.5):** We tested whether adding bullpen signals improves our existing game-totals predictions. Adding the signals reduced MAE from **3.5191 to 3.4726** (improvement of 0.0465 runs), with all 3 test folds improving. Gate cleared.

---

## Epic 6D — From a Signal to a Full Distribution (v2)

With a working bullpen quality signal in place, we upgraded from a single-number prediction to a full probability distribution over expected bullpen runs allowed.

### Why distributions matter more for bullpen than for any other sub-model

Bullpen run contribution is the most volatile component of any game. A starter who gets knocked out in the third inning suddenly turns a 3-inning bullpen appearance into an 8-inning marathon. A closer blowing a lead in the ninth can double the expected bullpen runs in a single at-bat. The *spread* of outcomes is not just interesting — it's the primary thing the market struggles to price correctly in live betting.

By modeling the full distribution, we can:
- Compute the probability that the bullpen allows more than any specific number of runs
- Quantify how much uncertainty exists around the prediction
- Combine this with our starter depth model to produce a joint picture of total expected runs

### Why Negative Binomial?

The bullpen's run contribution is count data: 0 runs, 1 run, 2 runs, etc. Unlike total game runs, bullpen runs allowed have even higher overdispersion — the variance is much larger than the mean. This is because bullpen usage is leverage-dependent: the same bullpen that allows 0 runs closing out a 7-3 lead would allow many more in a high-leverage, bases-loaded situation. The **Negative Binomial distribution** is built for exactly this pattern: it models count data where variance systematically exceeds the mean.

### Candidate A vs. Candidate B — the head-to-head

We evaluated two architectures before selecting the champion:

**Candidate A** (simpler): Wrap the Epic 6 NGBoost champion's point prediction with a NegBin distribution. Estimate the dispersion parameter r from training errors. Fast; no new dependencies.

**Candidate B** (more principled): Two-stage model. Stage 1 uses the starter IP depth signal from Epic 5D to estimate how many outs the starter will actually record, and therefore how many outs the bullpen must cover. Stage 2 scales the bullpen's predicted runs based on that exposure estimate. When starters are likely to exit early, the bullpen exposure increases and the expected runs increase proportionally.

This was the right question to ask. Candidate B couldn't be evaluated until Epic 5D (the starter IP model) was complete — it required the 20th-percentile starter IP estimate as an input. Once that became available, we ran a direct head-to-head comparison on the same 5-fold recent window:

| Metric | Candidate A | Candidate B |
|---|---|---|
| CV NLL (5 recent folds, 2022–2026) | 1.8940 | **1.8852** |
| 80% calibration | — | **92.5%** |
| Final dispersion r | 1.4474 | **1.4853** |

**Candidate B won** — NLL 1.8852 vs. 1.8940, a difference of 0.0088 nats, and 92.5% of actual outcomes fell within the model's 80% prediction interval (well above the 80% requirement). Candidate B is the champion.

### How Candidate B's exposure scaling works

The core insight: if the starter is predicted to exit after only 10 outs (about 3⅓ innings), the bullpen needs to cover 17 outs (roughly 5⅔ innings). If the starter is predicted to go 18 outs (6 IP), the bullpen only needs 9 outs. The predicted bullpen runs scale proportionally.

Specifically: `adjusted_mu = base_mu × (27 − pessimistic_starter_outs) / league_average_bullpen_outs`

The pessimistic starter outs estimate (20th percentile — meaning the starter is likely to go *at least* this many outs 80% of the time) comes from Epic 5D. The league average bullpen exposure (15.268 outs, fitted from 2021–2026 data) provides the normalization.

Games without a confirmed probable pitcher, or games before 2020, fall back gracefully: scale = 1.0, same as Candidate A behavior.

### Signal generation and backfill

We scored the Candidate B model over every 2021–2026 game and stored 4 signals per team per game:

| Signal | What it means |
|---|---|
| `bullpen_mu_v2` | Expected bullpen runs allowed (exposure-adjusted) |
| `bullpen_dispersion_v2` | NegBin r = 1.4853; tells you how spread out the distribution is |
| `bullpen_fatigue_adjusted_mu_v2` | `bullpen_mu_v2` further adjusted by EB bullpen quality estimate |
| `bullpen_uncertainty_v2` | Width of the 80% prediction interval |

**103,412 rows** across 25,853 game-sides. After the Candidate B re-run (which corrected the earlier Candidate A backfill), the Snowflake verification confirmed:
- Average `bullpen_mu_v2`: **2.059 runs** — matches the historical mean from the overdispersion audit
- Average `bullpen_dispersion_v2`: **1.4853** — exact match to the Candidate B fitted r
- Zero nulls across all 4 signals for availability = TRUE rows

---

## What This Means Going Forward

We now have three layers of bullpen intelligence available for every game since 2021:

- **Fatigue and availability** (Epic 6, rules-based): How much has this bullpen worked recently, and at what leverage?
- **Quality signal** (Epic 6, NGBoost): What contact quality should we expect this bullpen to allow?
- **Full distributional output** (Epic 6D, Candidate B): How many runs should we expect, what's the uncertainty, and how does that change based on how deep the starter goes?

All three are market-blind. All use EB-stabilized reliever quality estimates from Epic 6A. The distributional output is the one that flows into Epic 9.

In Epic 9, the bullpen distribution will be combined with the starter suppression distribution, run environment, and offensive quality into a joint model over total runs — giving us an independent, distributional read on every game that we can compare against Bovada's implied probabilities to find edges.

---

## Summary of Outputs

| Deliverable | What It Is |
|---|---|
| `bullpen_quality_v1.pkl` (S3) | NGBoost Normal champion — predicts bullpen xwOBA-against with uncertainty |
| `bullpen_v2.pkl` (S3) | LightGBM + NegBin (Candidate B) — predicts bullpen runs allowed with starter-IP exposure scaling |
| `eb_bullpen_posteriors` (Snowflake) | EB shrinkage estimates for every reliever-game, 2016–2026 |
| `mart_sub_model_signals` (Snowflake) | 180,551 rows: 7 v1 signals per team-game (fatigue, quality, leverage, volatility) |
| `mart_sub_model_signals` (Snowflake) | 103,412 rows: 4 v2 (6D) signals per team-game (mu, dispersion, fatigue-adj, uncertainty) |
| `feature_pregame_sub_model_signals` (Snowflake) | Game-level feature view exposing all bullpen v1 and v2 signals for downstream models |
| `bullpen_6D_architecture.md` | Architecture decision record with Candidate A vs. B comparison table |
