# Epic 3A: Better Park Factor Estimates for Unusual Venues

## What Epic 3A Was About

The run environment model relies on a **park run factor** — a number that captures how run-friendly a specific ballpark is relative to the league average. For well-established major league parks like Coors Field or Petco Park, this number is reliable: there are hundreds of games of historical data to calculate it from.

The problem appears with unusual venues:

- **Sutter Health Park** in Sacramento, where the Oakland A's played their first season (2025) while waiting for a permanent home
- **Tokyo Dome**, used for the international series
- **Neutral-site and spring training crossover games**

These venues have little or no prior history in the dataset. The previous solution was a blunt one: if we don't have data on a venue, assume it's average. Insert the league mean and move on.

This works as a stopgap, but it's not ideal. A stadium that has hosted even 20 games has *some* information worth using — and a brand-new stadium probably isn't exactly average. Epic 3A replaced the hard "use the league average" rule with a statistically principled approach called **Empirical Bayes smoothing**.

---

## The Core Idea: Let the Evidence Speak, But Don't Overweight It

The intuition behind Empirical Bayes is simple: when you have limited evidence, don't discard it and fall back to a default — but also don't overweight it. Instead, blend the actual observations with the overall baseline in proportion to how much data you have.

Think of it like judging a new restaurant. If you've eaten there 200 times and it's consistently excellent, you're confident it's excellent. If you've eaten there twice and it was great both times, you're cautiously optimistic — but you're not ready to call it the best restaurant in the city because two meals isn't enough to be sure. You hedge: "it seems good, but it might just be luck."

Empirical Bayes formalizes this intuition:

- For a park with **many seasons of data** (like Coors Field with 240+ games in the rolling window): the model trusts the observed run factor almost entirely. The prior has almost no influence. **Shrinkage ≈ 11%.**
- For a park with **very few games** (like TD Ballpark with 21 games in its first season): the model pulls the estimate heavily toward the league mean. The observed data is noisy, so the prior dominates. **Shrinkage ≈ 58%.**
- For a park with **one full season** (like Sutter Health with 81 games): the model gives meaningful weight to the observations but still pulls toward the mean somewhat. **Shrinkage ≈ 27%.**
- For a venue with **no data at all**: the estimate is simply the league mean. No imputation needed — the Bayesian framework handles this case naturally.

The result: the park run factor is now **non-null for every single game in the dataset**, including Tokyo Dome, neutral-site games, and any future unusual venue. The hard imputation step is gone.

---

## What Was Built

The implementation had three parts:

**A Python script that computes the EB estimates.** It pulls the historical park run factors, fits the cross-park statistical distribution (the "prior"), and then for each venue and season computes the posterior estimate along with a shrinkage factor. Results are written to Snowflake.

**A dbt model that surfaces the estimates.** The Snowflake table is exposed as `mart_eb_park_factors` — one row per venue per season, with the smoothed run factor, the raw run factor, the number of games it's based on, and the shrinkage factor.

**An update to the park features table.** The `feature_pregame_park_features` table that the run environment model reads now includes `eb_park_run_factor` and `shrinkage_factor` as columns, joined from the new mart using the prior-season leakage guard (the same guard used for all park factor joins — never using current-season data in a pre-game feature).

---

## Results

**Statistical verification:**

| Venue | Games in window | Shrinkage | Raw factor | EB estimate |
|---|---|---|---|---|
| Coors Field (2025) | 241 | 0.109 (11%) | 11.33 | 11.07 |
| Sutter Health (2025, first year) | 81 | 0.267 (27%) | pulled toward mean | closer to mean |
| TD Ballpark (2021, first year) | 21 | 0.584 (58%) | 11.14 | 9.86 |

Coors Field's extreme run-friendliness is respected — 241 games of data are enough to be confident in the estimate. New venues are appropriately hedged toward the league mean based on how little data exists.

**Model impact:**

The EB park run factor is the **#2 most important feature** in the run environment model by SHAP value (0.151), just behind temperature. The feature is working as intended.

When we retrained the v3 model using the EB park factor instead of the raw factor, the MAE was essentially unchanged (3.509 vs. 3.510). This is expected — EB smoothing affects only the ~2% of games at non-standard venues, which isn't enough to move the aggregate metric much. The value of the improvement is in *correctness* for those unusual games, not in average-case accuracy.

---

## What the "Deprecated" Label Means

When the updated model ran through its comparison against the previous version, it didn't clear the strict 0.05-run improvement threshold required for promotion. The model was labeled "deprecated" in the registry.

This is a slightly confusing bit of terminology. The model isn't being thrown away — it's still generating signals, and the EB park factor is still the feature the signal generation pipeline uses. "Deprecated" in the registry context means "this version didn't clear the promotion gate to become the official champion," not "this model is unusable."

The signals in the database are labeled `run_env_v3` because that's the artifact that generated them — accurate provenance, regardless of the promotion gate outcome.

---

## What Epic 3A Means Going Forward

The most immediate impact: **no more hard imputation for unusual venues**. The Oakland A's situation — a team spending one or more seasons at a minor league park — is now handled gracefully. Any future unusual venue will automatically receive a sensible estimate rather than a generic league-average plug.

Epic 3A also established the code pattern for Empirical Bayes smoothing in this project. The same approach — fit a prior over the cross-population distribution, compute posteriors based on sample size — will be reused for **batter and pitcher rate stabilization** in a future epic (Epic 4A). That application will smooth individual player stats (like strikeout rate, walk rate, wOBA) that are noisy at the start of a season or career.

---

*Epic 3A completed 2026-05-27. EB park factors backfilled and live. Feature table updated. v3 model retrained with EB features.*
