# What We Built: Starter Suppression Model (Epics 5, 5A & 5D)

**Last updated:** June 1, 2026

---

## The Problem We Were Solving

The single biggest driver of whether a game goes over or under a run total is who is pitching. A Clayton Kershaw start looks nothing like a spot-starter's first outing. Our models had no systematic way to quantify how much a given starter suppresses offense — they were relying on the same rolling stats the market already prices in.

The goal of these epics was to build a clean, independent pre-game read on each starter: how well will they suppress the opposing lineup, and for how long? Both questions feed directly into our run-total and run-differential predictions.

---

## Epic 5A — Teaching the Model to Handle Small Samples (Empirical Bayes)

Before we could train the main model, we had to solve an early-season problem: starting pitcher stats are extremely noisy through April.

### The core problem: early-season starts are almost meaningless

A pitcher who has a 2.00 ERA after three starts looks elite — but three starts is roughly 60 batters faced, which is barely enough data to distinguish skill from luck. A rookie's first five starts look completely different from a veteran's first five starts after an IL return, even if the raw numbers are similar.

**Empirical Bayes (EB)** solves this by blending each pitcher's current-season numbers with a sensible expectation based on pitchers like them — specifically grouped by age band (under 25, 25–29, 30–32, 33+) because pitching aging curves are well-documented and age meaningfully predicts true talent.

The logic: a 23-year-old in his second MLB season should be shrunk toward a very different population baseline than a 34-year-old returning from a hamstring IL stint. EB handles both cases automatically, and releases the shrinkage as the season progresses and real data accumulates.

### What we built

**Prior fitting (5A.1):** For each season from 2016 onward, we fit statistical distributions for three key metrics — xwOBA-against (the primary quality measure), strikeout rate, and walk rate — broken out by age band. We used only "qualified" starters (10+ starts or 150+ batters faced in the season) so the priors aren't contaminated by spot-starters and relievers. Each (metric × age band × season) cell gets its own prior.

**Posterior estimates (5A.2):** For every starter-game from 2016 through today, we computed a shrinkage estimate using Normal-Normal conjugate updating — the mathematically correct way to blend prior and observed data when both are approximately Normal. The key features:
- At 0 batters faced (debut): estimate = prior mean for that age band
- IL-return handling: pitchers with many prior-season starts but 0–2 current-season starts get a 50/50 blend of current sparse data and their prior-season history — the right behavior for players who were good last year and just returned from injury
- By late summer with 400+ batters faced: the prior has almost no influence and the observed rate dominates

**Feature integration (5A.3):** These EB estimates were added to our starter feature table in the data warehouse — 47,287 starter-game records with zero missing values across the full 2016–2026 window.

**How much more stable is EB in April?** The standard deviation of EB xwOBA estimates in April is 0.016, compared to 0.066 for raw 30-day rolling xwOBA. EB is **4× more stable** when it matters most — exactly the behavior we designed for.

**Ablation test (5A.4):** We ran the full model with and without EB features. The result confirms EB's value: EB xwOBA ranked **#1 in feature importance** in the final model, and EB ISO ranked **#2**. The model strongly preferred the stabilized estimates over raw rolling stats.

---

## Epic 5 — The Starter Suppression Model (v1)

With stable, well-calibrated starter quality estimates in hand, we trained the core model.

### What the model does

The target is **xwOBA-against**: a pitch-by-pitch quality measure of how much offensive contact a pitcher allows. A pitcher allowing an xwOBA of 0.280 is elite (close to historic great season territory). One allowing 0.360 is getting hit hard. The model predicts this number for each starter in each game, before the game happens, from pre-game features only.

### What we built

**Training dataset (5.1):** We built a training set of 45,107 pitcher-game records spanning 2016–2026, with 11 full MLB seasons of data. Each row is one start, with the full pre-game feature set available at the time of prediction — no future information leaks in.

**Model training (5.2):** We compared three candidates:
- **NGBoost Normal** — a distributional boosting framework that learns both the predicted mean and the uncertainty around it simultaneously
- **LightGBM + Normal sigma** — gradient-boosted trees predict the mean; the uncertainty is estimated separately from model errors
- **GLM baseline** — a simple statistical floor used as the minimum bar

We used 4-fold walk-forward cross-validation (evaluating on 2023, 2024, 2025, and 2026 separately, training only on prior seasons for each). This is the most honest evaluation approach for a time-series problem.

| Candidate | NLL Score | Calibration | Result |
|---|---|---|---|
| GLM baseline | -0.9917 | — | Floor |
| LightGBM + sigma | -0.9889 | 81.4% | Runner-up |
| **NGBoost (tuned)** | **-0.9991** | **81.6%** | **Champion** |

NGBoost won. After Optuna hyperparameter tuning (60 total trials), the final CV score was NLL **-0.9991** with 81.6% calibration (81.6% of actual xwOBA values fell within the model's 80% prediction interval — within rounding of the target).

The model is stored as `starter_v1.pkl` and registered in MLflow with full trial history.

**Signal generation (5.3):** We scored the champion model over every game from 2020 through today and stored four signals per pitcher per game:

| Signal | What it means |
|---|---|
| `starter_suppression_mu` | Predicted mean xwOBA-against for this starter |
| `starter_suppression_sigma` | How uncertain we are about that prediction |
| `starter_suppression_signal` | How this starter compares to league average (negative = better suppressor) |
| `uncertainty` | The width of the 80% confidence interval |

27,817 records were backfilled covering 2020–2026.

**Ablation test (5.5):** We tested whether adding starter suppression signals improves our existing game-totals and run-differential predictions. The results were decisive: starter suppression mu ranked **#1 out of 582 features** in the totals model and **#2 out of 582** in the run-differential model. Both models improved when starter signals were added (−0.0028 and −0.0067 MAE respectively). The gate cleared easily.

---

## Epic 5D — How Long Will the Starter Pitch? (IP Depth Model)

After building the "how well will this starter pitch?" model in Epic 5, we tackled the second question: **how long will they pitch?**

These are related but not the same. A dominant pitcher might still exit early due to a pitch count limit or a roster situation. A mediocre innings-eater might grind through six innings regardless of results. Both questions matter because the bullpen's expected run contribution depends directly on how deep the starter goes.

### Why we built a separate model

Innings pitched (IP) and xwOBA-against are predicted by partly different features and have fundamentally different statistical properties. xwOBA is a rate (approximately Normal, symmetric). IP is a count (discrete, bounded at 0 and 27 outs, with a right skew — many starts end at 3–4 innings when things go wrong, few reach 8 innings). Forcing them into one model would require a complicated multi-output architecture. Two clean single-output models are easier to train, evaluate, and audit.

### The distribution family

We express innings pitched as **outs recorded** (0–27, where 27 = complete game), which avoids fractional-inning arithmetic and produces integer-valued predictions. The historical distribution of outs recorded (mean = 14.89 outs, or about 4⅔ innings) has more variance than a Poisson model would predict — confirmed across all feature subgroups. This is classic **Negative Binomial** territory: count data that's more spread out than chance alone would explain.

### What we built (5D.1–5D.2)

**Training dataset:** 27,489 pitcher-game records (2020–2026) with outs recorded as the target. We confirmed overdispersion in every feature subgroup before committing to NegBin.

**Model training:** We compared LightGBM + NegBin dispersion fitting against an NGBoost NegBin baseline. LightGBM won:
- CV NLL: **2.720**
- 80% calibration: **89.5%** (meaning 89.5% of actual outs recorded fell within the model's predicted 80% interval — meaningfully better than the gate requirement)
- CV MAE: **2.688 outs** (~0.9 innings)

One notable limitation: the model underperforms on very short starts (< 12 outs), where a starter is knocked out early due to an unexpected blowup. This was flagged and documented — it's a known failure mode, not a surprise, and doesn't block production use.

**Signal generation (5D.3):** We scored the model over every 2020–2026 game and stored six signals per pitcher per game — including both the expected outs and the pessimistic 20th-percentile estimate (`starter_ip_p20_outs_v1`). That pessimistic estimate is the key input the bullpen model uses: it tells us how many outs the bullpen might need to cover in a worst-case (but realistic) scenario.

27,584 records inserted. 100% availability for 2020–2026 games with confirmed starters.

**Integration (5D.4–5D.5):** All IP signals were added to the main feature view downstream models read from. Eight new columns, 100% non-null for 2020+ games, dbt build green.

### Why this mattered for the bullpen model

The starter IP depth signals directly unblocked the most sophisticated version of the bullpen model (Epic 6D Candidate B). Without a pre-game read on how deep the starter goes, the bullpen model had no way to scale its predictions based on expected workload. With `starter_ip_p20_outs_v1` available, the bullpen model can now adjust its expected run contribution based on the pessimistic starter depth estimate — a more principled approach that turned out to win the head-to-head comparison.

---

## What This Means Going Forward

We now have two independent reads on each starter available for every game since 2020:

- **Quality** (`starter_suppression_mu`, `starter_suppression_sigma`): How much offense will this starter allow per batter faced?
- **Depth** (`starter_ip_mu_v1`, `starter_ip_p20_outs_v1`): How many innings will this starter throw, and what's the pessimistic scenario?

Both are market-blind. Both are distributional — they give us a full probability curve, not just a single number. And both proved their value by passing ablation tests against our existing totals and run-differential models.

In Epic 9 (the stacked model), these signals will be combined with run environment, offensive quality, and bullpen signals into a joint distribution over total runs — which we compare directly against Bovada's implied probabilities to find edges.

---

## Summary of Outputs

| Deliverable | What It Is |
|---|---|
| `starter_v1.pkl` (S3) | NGBoost Normal champion — predicts starter xwOBA-against with uncertainty |
| `starter_ip_v1.pkl` (S3) | LightGBM + NegBin champion — predicts starter outs recorded with uncertainty |
| `eb_starter_posteriors` (Snowflake) | EB shrinkage estimates for every starter-game, 2016–2026 |
| `starter_suppression_signals` (Snowflake) | 27,817 rows: mu, sigma, signal, uncertainty per starter-game (2020–2026) |
| `starter_ip_signals` (Snowflake) | 27,584 rows: mu, p20, p80, signal, uncertainty per starter-game (2020–2026) |
| `feature_pregame_starter_features` (Snowflake) | Starter feature table with EB columns, zero nulls, 2016–2026 |
| `feature_pregame_sub_model_signals` (Snowflake) | Game-level view exposing all starter v1 and IP v1 signals for downstream models |
| `starter_priors_{year}.json` | Statistical priors per age band × season, 2016–2026 |
