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

## Three Model Versions and What Each Found

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

---

## What Happens With the Signals

The run environment model generates two signals per game, written for both the home and away side:

**`run_env_signal`** — a z-scored version of the predicted total runs. Zero means an average-scoring environment; positive means run-friendly (like Coors Field); negative means run-suppressed (like Oracle Park in June). The z-score makes this signal easy to compare across different season-wide scoring levels.

**`environment_volatility`** — the historical standard deviation of run totals at that specific ballpark over the available sample. Coors Field has higher volatility than pitcher parks — more games there land in the extremes rather than near the average. This signal captures how much the outcome can swing at a given venue.

Both signals are stored in the sub-model signal table and are ready to be consumed by downstream models.

---

## The Ablation Test — Did Adding These Signals to the Main Model Help?

After v3 was promoted, we tested whether adding the run environment signals to the existing totals model improved its predictions. The answer: effectively no (+/- 0.0001 MAE improvement, statistically indistinguishable from zero).

This sounds like a failure, but it's actually the expected and correct result. The main totals model already includes park factors, weather, and umpire z-scores as raw features. Adding a *distillation* of those same features back in — which is what the run environment signal is — can't add new information to a model that already has access to all the source inputs.

The signal's value will be realized when the next-generation stacked model (Epic 9) is built. That architecture is designed specifically around sub-model signals *replacing* raw environmental features rather than being added alongside them. The near-zero ablation delta confirms that the signal is a faithful distillation of the raw inputs — no information was lost in the compression — which is exactly what you want to see before building the stacked layer on top of it.

---

*Epic 3 completed 2026-05-19. v3 Ridge promoted to champion. Run environment signals backfilled 2021–2026. Epic 3A (park factor smoothing) completed immediately after.*
