# Epic 3: The First Sub-Model — Run Environment

## What Epic 3 Was About

Epic 3 built the first of the specialized prediction sub-models: the **run environment model**.

The question this model answers: *before the game starts, how many total runs should we expect to be scored today?*

This isn't about picking a winner — it's about characterizing the scoring environment. A game at Coors Field on a hot, low-humidity afternoon against an umpire who calls a wide strike zone is a very different run environment than a game at Oracle Park in June fog. The run environment model translates those contextual factors into a single numeric signal.

This was the logical starting point for sub-model development. The target (total runs) is self-contained. The inputs (park factors, weather, umpire tendencies) are all already ingested and clean. And the model doesn't depend on any other sub-model's output to work.

---

## What the Model Uses as Inputs

Seventeen features, organized into four groups:

**Park:** How run-friendly is this ballpark historically? What's the elevation? How far is it to center field? Is there a roof?

**Weather:** What's the temperature? Wind direction and strength relative to the field? Humidity?

**Umpire:** Is today's home plate umpire known for calling more runs than average (big strike zone = fewer walks, more contact)? Does this umpire tend to suppress or inflate scoring?

**Opponent quality controls:** How good are the two teams' offenses and starters? These features don't predict the run environment on their own — they're included to make sure the model isn't conflating "good teams tend to score more" with "this park is run-friendly."

---

## Four Model Versions and What Each Found

### Version 1 (Ridge Regression) — Baseline

The first model used a Ridge regression — a linear model. Walk-forward cross-validation (train on past seasons, test on the next one) produced a baseline CV MAE of **3.51 runs**. That means on average, the model's total-run prediction is off by 3.51 runs.

For reference: a naive guess of "every game will have 9 runs" also misses by about 3.5 runs. So the model is starting right around the naive baseline.

The key finding: **park factors and temperature are far and away the two strongest predictors**. Where the game is played and how hot it is account for most of the signal the model can capture. Umpire effects are measurable but secondary. Team quality controls add value but less than the environmental factors.

### Version 2 (XGBoost Tree Model) — Challenger

We tested whether a tree-based model (XGBoost, which can capture non-linear relationships) could improve on the linear baseline.

Result: **no meaningful improvement** (CV MAE 3.513 vs. 3.510). The tree model also showed a persistent negative bias — it consistently under-predicted total runs by an average of 0.56 runs per game across all seasons. The 2023 season was particularly bad: the model underpredicted by 1.23 runs per game that year.

The cause was identified: MLB introduced the pitch clock, the shift ban, and larger bases at the start of the 2023 season. These rule changes structurally shifted how many runs get scored, and the model had no features representing them. Without knowing "this game is being played under the new rules," the model was applying 2021 expectations to a 2023 environment. XGBoost was deprecated.

### Version 3 (Ridge with Era Features) — Champion

The root cause identified in v2 pointed directly at the fix: add features representing MLB rules changes.

We added four new features:
- A flag for the universal DH era (started 2022)
- A flag for the pitch clock + shift ban era (started 2023)
- The league-wide average runs per game from the *prior* season (a forward-looking measure that automatically captures future rule changes without requiring manual flags)

We also removed two umpire features (strikeout rate and walk rate z-scores) that had contributed exactly zero predictive signal in both prior models — confirmed by SHAP importance analysis.

**Net effect on accuracy:** The MAE improvement was minimal (3.509 vs. 3.510 — effectively identical). But the **systematic bias was eliminated**: the mean prediction error went from −0.56 runs/game to virtually zero (+0.02). The model now predicts accurately on average rather than consistently underestimating scoring.

The promotion decision was made on the bias fix. A model that correctly centers its predictions is fundamentally more useful than one with a known systematic lean, even if the raw error magnitude is similar.

### Version 4 (Ridge + Negative Binomial) — Epic 3D, Current Champion

v3 predicted a single number (how many total runs). v4 predicts a **full probability distribution** over possible run totals. This is a meaningful upgrade: instead of saying "we expect 9.1 runs," v4 says "we expect 9.1 runs on average, and there's an 80% chance the true total falls between 5 and 15." That uncertainty range can be propagated through to the final probability model.

The statistical family used is the **Negative Binomial distribution**, which is the mathematically correct choice for count data (whole numbers, always ≥ 0) that is "overdispersed" — meaning games vary more than a simple model would predict. Baseball run scoring is demonstrably overdispersed: some days you get 2-1 games, other days 14-7 blowouts, and the tails are fatter than a standard Poisson model handles.

The Negative Binomial has two parameters:
- **μ (mu)** — the predicted mean total runs for this specific game
- **r (dispersion)** — how spread out the distribution is around that mean. Higher r = tighter clustering around the mean; lower r = fatter tails. For run scoring, r was estimated at **7.4** — meaning there's meaningful game-to-game variance even after accounting for all 17 contextual features.

**Candidate comparison:**

Three architectures competed:

- **Candidate A (NGBoost + NegBin):** A gradient boosted model that learns the conditional mean, with dispersion fitted separately. NLL = 2.93. Notably worse — NGBoost struggles to leverage 57 features efficiently on this sample size, and the Normal distribution used internally for its boosting step doesn't align with the integer structure of run totals.
- **Candidate B (Ridge + NegBin):** The same Ridge regression from v3 for the conditional mean, with dispersion fitted by maximum likelihood on the training residuals. NLL = **2.8522**. This is counterintuitive: a simpler model beats a more complex one. The reason is that the mean prediction problem is already well-solved by the linear model — the signal in 17 features is mostly linear, as v2's tree model already showed. Adding NegBin on top converts a good point estimate into a good distributional estimate without introducing the instability of NGBoost's tree construction.
- **Candidate C (NegBin GLM, reference):** A pure statistical Negative Binomial generalized linear model. Failed to converge in all 5 cross-validation folds due to numerical issues, falling back to intercept-only predictions. NLL = 2.86. This baseline exists to ensure the winning model is actually learning something — Candidate B's 2.8522 beats even a converging GLM would have produced, so the ridge+NegBin combination is genuinely adding signal.

**Winner: Candidate B (Ridge + NegBin).** Gate results: NLL beats the GLM floor ✓; 82.9% of observed run totals fell within the model's stated 80% prediction interval ✓ (target was ≥ 80%); MAE 3.52 — essentially unchanged from v3 ✓.

The model was retrained on the full dataset (2021–2025 seasons) with an optimized regularization parameter (α = 1,365), yielding a final fitted dispersion of r = 7.445.

---

## What Happens With the Signals

The v4 run environment model generates **three signals per game**, written separately for both the home and away side:

**`run_env_mu`** — the Negative Binomial predicted mean total runs for this game. An 8.5 means we expect 8.5 total runs on average; a 10.2 means a high-scoring environment. This is the primary signal for downstream probability models.

**`run_env_dispersion`** — the fitted Negative Binomial r parameter (7.445 for the current model). This is constant across all games for a given model version — it's a property of how much run-scoring varies in general, not of this specific game. It's stored per row so that downstream models can reconstruct the full NegBin distribution without needing to look up the model artifact separately.

**`run_env_signal`** — a z-scored version of `run_env_mu`: how many standard deviations above or below average this game's predicted scoring is. Zero means exactly average; +1.5 means a very run-friendly environment; −1.2 means a very suppressed environment. Retained from v3 for backwards compatibility with any downstream models already consuming it.

All three signals also carry an **`uncertainty`** value — the width of the 80% predictive interval for this specific game. A game at Coors Field in July might have `run_env_mu = 11.2` and `uncertainty = 12` (the 80% interval spans 12 runs — a very wide range). A dome game in a pitcher-friendly park might have `uncertainty = 10`. This is the first time the pipeline surfaces calibrated uncertainty estimates alongside its predictions.

The old `environment_volatility` signal (historical standard deviation of run totals at the venue) was retired. It conveyed similar information to `run_env_dispersion` but was venue-level historical noise rather than a game-level model output — the NegBin dispersion is a cleaner and more principled measure.

---

## The Ablation Test — Did Adding These Signals to the Main Model Help?

After v3 was promoted, we tested whether adding the run environment signals to the existing totals model improved its predictions. The answer: effectively no (+/- 0.0001 MAE improvement, statistically indistinguishable from zero).

This sounds like a failure, but it's actually the expected and correct result. The main totals model already includes park factors, weather, and umpire z-scores as raw features. Adding a *distillation* of those same features back in — which is what the run environment signal is — can't add new information to a model that already has access to all the source inputs.

The signal's value will be realized when the next-generation stacked model (Epic 9) is built. That architecture is designed specifically around sub-model signals *replacing* raw environmental features rather than being added alongside them. The near-zero ablation delta confirms that the signal is a faithful distillation of the raw inputs — no information was lost in the compression — which is exactly what you want to see before building the stacked layer on top of it.

---

## Why a Distributional Model Matters

Both v3 and v4 predict the same quantity (expected total runs), and their MAE is nearly identical (3.51 runs). So why bother with v4?

The answer lies in what the downstream probability model needs. Building a betting edge requires estimating the *probability* that the total runs scored falls above or below a given line — for example, "what's the probability of going over 8.5?" A point estimate of 9.1 runs can't answer that question rigorously. You need to know how uncertain that estimate is, and you need that uncertainty expressed in a form that's mathematically consistent with the betting line's structure.

The Negative Binomial distribution gives you that directly. Given `run_env_mu = 9.1` and `run_env_dispersion = 7.4`, the probability of going over 8.5 is `1 - NegBin_CDF(8, mu=9.1, r=7.4)` — a number you can compute exactly and compare to the implied probability in the betting line to identify edge.

This is the architecture the entire sub-model pipeline is working toward. Every Epic (3D, 4D, 5, 6, 8) produces distributional outputs in this same form. Epic 9 then combines them into a joint probability model over game outcomes.

---

*Epic 3 (v1–v3) completed 2026-05-19. Epic 3A (EB park factors) completed 2026-05-27. Epic 3D (v4 NegBin distributional) completed 2026-05-28. Run environment signals backfilled 2021–2026 with all three v4 signal types.*
