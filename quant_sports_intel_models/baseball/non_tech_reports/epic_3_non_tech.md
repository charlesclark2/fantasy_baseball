# Epic 3 & 3A: The Run Environment Model and Park Factor Estimation

## What This Epic Was About

Epic 3 built the first of the specialized prediction sub-models: the **run environment model**. The question it answers: *before the game starts, how many total runs should we expect to be scored today?*

This isn't about picking a winner — it's about characterizing the scoring environment. A game at Coors Field on a hot afternoon against an umpire who calls a wide strike zone is a very different run environment than a game at Oracle Park in June fog. The run environment model translates those contextual factors into a numeric signal.

Epic 3A extended that foundation by improving the quality of the park factor inputs the model relies on — first by replacing blunt imputation with statistically principled estimates for unusual venues, then by breaking a single aggregate run factor into granular, per-event-type factors.

---

## What the Model Uses as Inputs

Seventeen features, organized into four groups:

**Park:** How run-friendly is this ballpark historically? What's the elevation? How far is it to center field? Is there a roof?

**Weather:** What's the temperature? Wind direction and strength relative to the field? Humidity?

**Umpire:** Is today's home plate umpire known for calling more runs than average? Does this umpire tend to suppress or inflate scoring?

**Opponent quality controls:** How good are the two teams' offenses and starters? These features are included to make sure the model isn't conflating "good teams tend to score more" with "this park is run-friendly."

---

## Four Model Versions and What Each Found

### Version 1 (Ridge Regression) — Baseline

The first model used a Ridge regression — a linear model. Walk-forward cross-validation produced a baseline CV MAE of **3.51 runs**. For reference: a naive guess of "every game will have 9 runs" also misses by about 3.5 runs. The model was starting right around the naive baseline.

The key finding: **park factors and temperature are far and away the two strongest predictors**. Where the game is played and how hot it is account for most of the signal the model can capture. Umpire effects are measurable but secondary.

### Version 2 (XGBoost Tree Model) — Deprecated

We tested whether a tree-based model (XGBoost, which can capture non-linear relationships) could improve on the linear baseline.

Result: **no meaningful improvement** (CV MAE 3.513 vs. 3.510). The tree model also showed a persistent negative bias — consistently underpredicting total runs by an average of 0.56 runs per game, with 2023 particularly bad at −1.23 runs/game.

The cause: MLB introduced the pitch clock, the shift ban, and larger bases at the start of the 2023 season. Without features representing those rule changes, the model applied 2021 expectations to a 2023 environment. XGBoost was deprecated.

### Version 3 (Ridge with Era Features) — Champion

The fix: add features representing MLB rules changes.

Four new features were added:
- A flag for the universal DH era (started 2022)
- A flag for the pitch clock + shift ban era (started 2023)
- The league-wide average runs per game from the *prior* season (a forward-looking measure that automatically captures future rule changes without requiring manual flags)

Two umpire features that contributed zero predictive signal in both prior models were removed.

**Net effect:** MAE improvement was minimal (3.509 vs. 3.510), but the **systematic bias was eliminated** — the mean prediction error went from −0.56 runs/game to essentially zero (+0.02). A model that correctly centers its predictions is fundamentally more useful than one with a known systematic lean, even if the raw error magnitude is similar. v3 was promoted on the bias fix.

### Version 4 (Ridge + Negative Binomial) — Current Champion

v3 predicted a single number. v4 predicts a **full probability distribution** over possible run totals: instead of saying "we expect 9.1 runs," v4 says "we expect 9.1 runs on average, and there's an 80% chance the true total falls between 5 and 15."

The statistical family used is the **Negative Binomial distribution**, which is the mathematically correct choice for count data (whole numbers, always ≥ 0) that is "overdispersed" — meaning games vary more than a simple model would predict. Baseball run scoring is demonstrably overdispersed: some days you get 2-1 games, other days 14-7 blowouts, and the tails are fatter than a standard Poisson model handles.

Three architectures competed:

- **Candidate A (NGBoost + NegBin):** A gradient boosted model for the conditional mean, with dispersion fitted separately. NLL = 2.93. Notably worse — NGBoost struggles with this sample size and feature count.
- **Candidate B (Ridge + NegBin):** The same Ridge regression from v3 for the conditional mean, dispersion fitted by maximum likelihood on residuals. NLL = **2.8522**. Simpler beats more complex because the mean prediction problem is already mostly linear — as v2's tree model already showed. Adding NegBin converts a good point estimate into a good distributional estimate.
- **Candidate C (NegBin GLM, reference):** A pure statistical Negative Binomial GLM. Failed to converge in all 5 folds, falling back to intercept-only predictions. NLL = 2.86. Exists to confirm the winning model is genuinely learning — Candidate B's 2.8522 beats the GLM floor.

**Winner: Candidate B (Ridge + NegBin).** Gate results: NLL beats the GLM floor ✓; 82.9% of observed run totals fell within the model's stated 80% prediction interval ✓ (target ≥ 80%); MAE 3.52 — unchanged from v3 ✓. Final dispersion r = 7.445.

---

## What Happens With the Signals

The v4 model generates three signals per game:

**`run_env_mu`** — the Negative Binomial predicted mean total runs. An 8.5 means we expect 8.5 total runs on average; a 10.2 means a high-scoring environment.

**`run_env_dispersion`** — the fitted Negative Binomial r parameter (7.445 for the current model). This is constant across all games for a given model version — it's a property of how much run-scoring varies in general. Stored per row so downstream models can reconstruct the full distribution without looking up the model artifact separately.

**`run_env_signal`** — a z-scored version of `run_env_mu`: how many standard deviations above or below average this game's predicted scoring is. Retained from v3 for backwards compatibility.

All three signals carry an **`uncertainty`** value — the width of the 80% predictive interval for this specific game.

---

## Epic 3A: Better Park Factor Estimates

### Part 1 — Handling Unusual Venues (EB Smoothing)

The run environment model relies on a **park run factor** — a number capturing how run-friendly a ballpark is relative to league average. For well-established parks like Coors Field, this number is reliable. The problem appears with unusual venues:

- **Sutter Health Park** in Sacramento (Oakland A's' temporary home in 2025)
- **Tokyo Dome** (international series)
- **Neutral-site and spring training crossover games**

These venues have little or no prior history. The previous solution: if we don't have data on a venue, assume it's average. Insert the league mean and move on.

This works as a stopgap, but a stadium that has hosted even 20 games has *some* information worth using. Epic 3A replaced the hard "use the league average" rule with **Empirical Bayes smoothing**.

The intuition: when you have limited evidence, don't discard it — but don't overweight it either. Blend actual observations with the baseline in proportion to how much data you have. Think of it like judging a new restaurant. Two excellent meals makes you cautiously optimistic, not certain.

| Venue | Games in window | Shrinkage | Effect |
|---|---|---|---|
| Coors Field (2025) | 241 | 11% | Estimate stays close to observed — data is abundant |
| Sutter Health (2025, first year) | 81 | 27% | Pulled meaningfully toward league mean |
| TD Ballpark (2021, first year) | 21 | 58% | Prior dominates — very little data |
| Venue with no data | 0 | 100% | Estimate is simply the league mean |

The result: the park run factor is now **non-null for every single game in the dataset**. The hard imputation step is gone.

The EB park run factor ranked as the **#2 most important feature** in the run environment model by SHAP value (0.151), just behind temperature.

### Part 2 — Granular Park Factors (HR, 2B/3B, SO, BB splits)

The aggregate run factor answers "does this park produce more or fewer total runs?" — but that single number hides a lot of structural variation in *how* parks shape scoring.

Coors Field is the canonical example: at 5,280 feet, the thin air carries everything. The park inflates home runs, doubles, and triples dramatically. But it also reduces strikeouts slightly because pitchers can't rely as heavily on breaking balls that don't break as sharply at altitude. A single aggregate run factor captures the net effect, but misses this internal structure.

Epic 3A.2 added per-event-type park factors sourced from Baseball Savant's park factor data — separate factors for home runs, doubles/triples, singles, walks, strikeouts, and wOBA. Each uses the same Empirical Bayes shrinkage framework as the aggregate factor: large-sample venues converge to their observed rates; small-sample venues are pulled toward the league mean.

**What the data shows:**

*Coors Field HR factor (2016–2025):*

| Season | HR Factor |
|---|---|
| 2016 | 1.274 |
| 2018 | 1.165 |
| 2021 | 1.116 |
| 2022 | 1.078 |
| 2025 | 1.048 |

The systematic decline is the humidor effect — Colorado introduced ball humidification in 2002 and progressively expanded it. The data captures this structural change automatically: the 3-year rolling window adapts to the new ballistic environment without manual intervention.

*Coors Field doubles/triples factor:* consistently 1.49–1.61 across all eleven seasons. Altitude drives this independently of the humidor — thin air carries batted balls farther regardless of ball moisture, so gap hits that would die at sea level keep rolling.

These factors are stored as ratios (1.0 = league average, 1.274 = 27.4% more HR than average), applied to the prior season only (same leakage guard as all park factors), and are now live in the pregame feature table. Non-null coverage across the feature table: 93–99% of games depending on season.

---

## Why Distributional Outputs Matter

Both v3 and v4 predict the same quantity (expected total runs), and their MAE is nearly identical. So why bother with v4?

Building a betting edge requires estimating the *probability* that total runs falls above or below a given line — "what's the probability of going over 8.5?" A point estimate of 9.1 can't answer that rigorously. You need to know how uncertain that estimate is, expressed in a form consistent with the betting line's structure.

The Negative Binomial distribution gives you that directly: given `run_env_mu = 9.1` and `run_env_dispersion = 7.4`, the probability of going over 8.5 is `1 - NegBin_CDF(8, mu=9.1, r=7.4)` — a number you can compute exactly and compare to the implied probability in the betting line to identify edge.

This is the architecture the entire sub-model pipeline is working toward. Every subsequent Epic (4, 5, 6, 8) produces distributional outputs in the same form. Epic 9 then combines them into a joint probability model over game outcomes.

---

*Epic 3 (v1–v3) completed 2026-05-19. Epic 3A.1 (EB aggregate run factor) completed 2026-05-27. Epic 3D (v4 NegBin distributional) completed 2026-05-28. Epic 3A.2 (granular park factors) completed 2026-05-29. Run environment signals backfilled 2021–2026. Granular park factors backfilled 2016–2026.*
