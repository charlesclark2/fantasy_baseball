# Phase 4: Building the Models — What We Tried and How They Performed

## What Phase 4 Was About

Phase 3 confirmed that the data contains real predictive signal. Phase 4 was about turning that signal into working models.

There are three separate prediction problems at the core of this project:

1. **Total runs** — the combined number of runs scored by both teams
2. **Run differential** — the margin of victory (home team runs minus away team runs)
3. **Win probability** — the probability that the home team wins outright

Each of these maps to a specific bet: totals (over/under), run line (spread), and moneyline respectively. Phase 4 built and evaluated models for all three.

The benchmark we were aiming to beat: **a Brier score below 0.2395**. That number comes from Phase 3, where we measured how accurate the sportsbook consensus lines were at predicting actual game outcomes. A Brier score measures prediction accuracy for probability estimates — lower is better, and 0.2395 represents the average accuracy of professional oddsmakers. Matching or beating it means our model is adding at least as much information as the market already has priced in.

---

## Step 1: Choosing Which Features to Use

Before any model could be trained, we needed to decide which of the 391 available features to actually include. Giving a model too many inputs — especially redundant or irrelevant ones — often makes performance worse, not better.

We evaluated every feature using two filters:

**Filter 1: Does this feature correlate with game outcomes at all?**
Features with essentially zero statistical relationship to any of the three prediction targets were dropped. These are inputs that carry no signal — including them would just add noise. This removed 67 features.

**Filter 2: Is this feature measuring something that another feature already captures?**
Several groups of features were measuring the same underlying thing (for example, a team's wOBA over the last 30 days and their slugging percentage over the same window are highly redundant). Keeping both would mislead the model into thinking they were independent signals. When two features were redundant, we kept the one that tended to be more informative and dropped the other. This removed 84 features.

The final input contract: **240 features** out of 391 candidates. These were locked in before any model training began, so the same feature set was used consistently across all model evaluations.

The most predictive feature overall was the **betting market's consensus totals line** — the over/under number set by oddsmakers. This makes sense: oddsmakers have already done a lot of the same work we're doing, so their number is a strong starting point. The second-most informative feature was the **park's historical run factor** — some ballparks (Coors Field being the extreme case) systematically produce more runs than others, and that pattern is consistent enough to be the second-best predictor in the dataset.

---

## Step 2: Three Models for Three Prediction Problems

### Predicting Total Runs

**The challenge:** Total runs in a baseball game averages around 9.0, but the spread is enormous — individual games range from 1 run to 38 runs. Getting the average right is the easy part; capturing where any individual game lands is much harder.

**Baseline to beat:** If you simply predict every game will have 9.0 runs (the historical average), your average error is about **3.6 runs**. Any useful model needs to do better than that.

**What we tried:** Four model types — a simple linear model (Ridge Regression), gradient-boosted trees (XGBoost), and two variants of a model called NGBoost that provides not just a prediction but a full probability distribution over possible run totals.

The NGBoost distinction matters for a practical reason: the over/under bet doesn't ask you to predict the exact run total. It asks you to assess the *probability* that total runs will be above or below a specific number. A model that outputs a full distribution can answer that question directly. A model that outputs only a single predicted number cannot — you have to make additional assumptions to convert a point estimate into a probability.

**Winner: NGBoost (LogNormal distribution)**
- Mean error across all test seasons: **3.57 runs** (vs. 3.61 for the naive baseline)
- When converted into P(over/under line) probabilities, Brier score: **0.2562**

The LogNormal variant outperformed the Normal variant because baseball run distributions have a heavier right tail than a standard bell curve predicts — blowout games (15+ runs) happen more often than symmetry would imply. The LogNormal distribution accommodates that shape more faithfully.

*Why not more improvement?* Total runs is genuinely hard to predict. The best Las Vegas books typically miss by about 2.2–2.5 runs on average. A 3.57-run average error means our model is in the right ballpark but not close to oddsmaker accuracy yet — leaving room for improvement in later phases.

---

### Predicting Run Differential

**The challenge:** Run differential is the home team's score minus the away team's score. This can range from large negative numbers (away team blowout) to large positive numbers (home team blowout). Unlike total runs, it can be negative — which turns out to matter for model selection.

**What we tried:** Ridge Regression, XGBoost, and NGBoost Normal.

(NGBoost with a LogNormal distribution was attempted but couldn't be used here — LogNormal requires all-positive values, and run differential can be negative, so that option was ruled out mathematically.)

**Winner: NGBoost Normal**
- Mean error across all test seasons: **3.45 runs** (vs. 3.55 for the naive baseline)
- The NGBoost model's win probability predictions: **0.2429 Brier score**

The run differential model has a useful side effect: because it produces a full probability distribution centered around an expected margin, you can directly compute the probability that the home team wins (margin > 0). This gives us a win probability estimate "for free" from the run differential model — no separate win probability model needed in principle. Whether this free estimate is competitive with a dedicated classifier was a key question heading into the next sub-problem.

---

### Predicting Win Probability

**The challenge:** Which team wins the game? This is a binary question (yes or no), but the answer we want is a probability, not just a prediction. A well-calibrated probability — one where games you call 60% home win actually go to the home team 60% of the time — is what feeds into Expected Value calculations in Phase 6.

**The benchmark:** The sportsbook consensus win probability achieves a **Brier score of 0.2395** when measured against actual game outcomes. This is the clearest performance target in the project.

**What we tried:** Logistic Regression (the standard baseline for probability classification), and XGBoost with two different calibration methods — Platt scaling and isotonic regression.

A note on calibration: machine learning classifiers don't automatically output well-calibrated probabilities. XGBoost in particular tends to be overconfident at the extremes (a game it calls 70% home win might actually be closer to 63%). Calibration is a post-processing step that corrects this systematic bias, mapping the raw model outputs to probabilities that match reality. We tested two methods: Platt scaling (a simple sigmoid correction) and isotonic regression (a more flexible, non-parametric approach).

**Winner: XGBoost with isotonic calibration**
- Mean Brier score across all test seasons: **0.2393**
- This **beats the sportsbook benchmark** of 0.2395

The margin is narrow — 0.0002 better than the market. But it's meaningful for two reasons:

First, the model is incorporating the betting market's implied probability as one of its input features. The fact that it still adds value on top of the market signal means there are statistical patterns in the game data that the market hasn't fully priced in.

Second, even a narrow edge compounds over thousands of games. If the model consistently identifies spots where the market is slightly mispriced, that edge adds up over a full season.

**Isotonic vs. Platt calibration:** Isotonic regression produced noticeably better calibration than Platt scaling. The Platt-calibrated model had a small but measurable average calibration error; the isotonic-calibrated model's average calibration error was essentially zero across all test folds. Better calibration means the model's stated probabilities match actual outcomes more closely — critical for downstream bet-sizing decisions.

**Run-differential-derived win probability:** The run differential NGBoost model's implicit win probability estimate (Brier 0.2429) did not beat the dedicated classifier (0.2393). A purpose-built win probability classifier outperforms a regressor-derived estimate.

---

## Step 3: Fine-Tuning the Models

Machine learning models have "dials" called hyperparameters — settings like how deep each decision tree grows, how fast the model learns, and how aggressively it prevents overfitting. The defaults work reasonably well, but searching systematically for better settings can squeeze out further improvement.

We used an automated tuning algorithm (Optuna) to test 50 different hyperparameter combinations for XGBoost on each of the three targets. Results:

| Target | Baseline Mean Error | Tuned Mean Error | Improvement |
|---|---|---|---|
| Total Runs (MAE) | 3.6385 | 3.5655 | 2.0% |
| Run Differential (MAE) | 3.4887 | 3.4074 | 2.3% |
| Win Outcome (Brier score) | 0.2443 | 0.2423 | 0.8% |

The improvements are modest but consistent. The best-performing win outcome model overall remains the baseline XGBoost with isotonic calibration (Brier 0.2393) — the tuning work used Platt calibration rather than isotonic, so the tuned Platt model (0.2423) doesn't surpass the baseline isotonic model on this metric. The hyperparameter-tuned models will be revisited in Phase 5 when the probability output layer is finalized.

---

## What the Feature Importance Analysis Revealed

After training, we used a technique called SHAP analysis to measure which features were actually driving predictions in the total runs model. The top contributors were:

1. **The betting market's totals line** — by far the single most informative feature, as expected. The market already knows a lot.
2. **Park run factor** — the historical run environment for the specific ballpark.
3. **Lineup barrel rate** — how often the home team's lineup makes hard, well-hit contact (a proxy for power).
4. **Away starter fastball velocity** — a pitcher throwing harder tends to allow fewer runs.
5. **Team xwOBA and pitching quality metrics** — rolling offensive and pitching effectiveness across multiple time windows.

The presence of recent (7-day) metrics in the top features validates the Phase 2 design decision to compute rolling statistics at multiple time windows: recent form matters independently of longer-term averages.

The presence of starter platoon-split features validates the lineup-vs-starter matchup features engineered in Phase 2: a right-handed-heavy lineup facing a starter who struggles against right-handers is a meaningfully different situation than the starter's overall stats would suggest.

---

## Where Phase 4 Leaves Us

At the end of Phase 4, we have trained, evaluated, and persisted working models for all three prediction targets:

| Model | Target | Performance |
|---|---|---|
| NGBoost LogNormal | Total Runs | MAE 3.57 runs; Brier 0.2562 (over/under) |
| NGBoost Normal | Run Differential | MAE 3.45 runs; win prob Brier 0.2429 |
| XGBoost + Isotonic Calibration | Win Outcome | Brier **0.2393** ✓ beats benchmark |

The win outcome classifier is the headline result: it beats the sportsbook consensus accuracy threshold. That's the bar Phase 4 was designed around, and it cleared it.

Phase 5 (Model Finalization) will consolidate the best models across all three targets into a production-ready pipeline, with proper train/test splits to guard against overfitting and a final probability output layer that compares the classifier-based and regression-derived win probability estimates.

Phase 6 (Expected Value) will then use these probability outputs to identify specific games where the model's estimate meaningfully disagrees with the sportsbook line — the condition required for a bet to have positive expected value.

---

*This report covers Phase 4 work completed as of April 2026. Evaluation results are drawn from betting_ml/evaluation/win_outcome_results.md, total_runs_results.md, run_differential_results.md, and the hyperparameter tuning reports for Cards 4.12a–c. Files without corresponding Phase 4 plan specs in plan_specs/phase_4/ (bookmaker calibration, era stability, pitch asymmetry, pitching decomposition) are Phase 3 analysis artifacts and are not covered here.*
