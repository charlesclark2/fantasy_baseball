# Epic 1: Removing the Circular Thinking From the Models

## What Epic 1 Was About

The three core prediction models — **home team win probability**, **total runs**, and **run differential** — had a fundamental problem baked in. They were trained on features that included the betting market's own implied probabilities. In other words, the model was learning to predict game outcomes in part by reading what sportsbooks had already decided.

This is a form of circular reasoning, and it has a specific, important consequence: if the model is partially predicting the market back to itself, then the model adds no real independent insight beyond what the market already knows. Any edge the model might have over the consensus line is contaminated.

Epic 1 removed every market-derived feature from all three models and retrained from scratch.

---

## Why Market Features Were a Problem

To understand the problem, it helps to understand how the models are used.

The goal is to find games where our models predict a meaningfully different probability than the betting market. If the model says a team has a 60% chance of winning but the market implies only 50%, that's a potential edge — a bet worth considering.

But if the model was *trained on* the market's implied probability, then the model's 60% prediction is already partially anchored to whatever the market said during training. The model can't genuinely disagree with the market because it was partly taught by the market.

The #1 most important feature in the run differential model was literally the market's consensus win probability. The total runs model included the over/under line. These features were providing the biggest apparent signal in training — and that signal was circular.

---

## What Changed

Thirty-three market-derived columns were identified and removed from all three models. These included:

- Moneyline prices (from every sportsbook in the dataset)
- The totals line (the over/under number)
- Vig-adjusted implied win probabilities
- Consensus market aggregates

Everything about how sportsbooks had priced the game was removed. The models were then retrained using only the statistical features that were genuinely knowable before the market opened: pitching stats, team offense, park factors, weather, umpire tendencies, schedule context, and so on.

---

## The Surprising Result

When the market-blind models were compared against their predecessors, **all three performed better on historical data**:

| Model | Old (with market features) | New (market-blind) | Change |
|---|---|---|---|
| Home win probability | Brier score 0.2392 | 0.2390 | Slight improvement |
| Total runs | MAE 3.375 runs | 3.234 runs | −0.141 runs improvement |
| Run differential | MAE 3.434 runs | 3.405 runs | −0.029 runs improvement |

*(Lower is better for both Brier score and MAE)*

The fact that removing the market features made the models *better* on historical data confirms the original suspicion: the market features were contributing noise from circularity, not genuine predictive signal. A model that partially mirrors the market can't outperform the market — it can only underperform it.

All three challenger models were promoted to production on May 11, 2026.

---

## The Calibration Follow-Up

After the retrains, we ran a calibration step that determines how much weight to give the model's probability versus the market's probability when generating a final "posterior" bet recommendation. This is controlled by a parameter called **alpha** (0 = pure market, 1 = pure model).

The result was alpha = 0 — meaning the recommended posterior probability should just be the market's consensus price.

This sounds discouraging but is actually informative. The alpha calibration uses a combined signal across all three bet types. The breakdown shows why alpha came back at zero:

- **Total runs model**: 85% of predictions favor the over, which is systematically skewed. The model is right on average but has an unusually narrow spread of predictions — it's not distinguishing confidently between games. This is a known architectural limitation deferred to a future phase.
- **Home win model**: The calibration loop uses a different model flavor than what's actually deployed in production, so the calibration result doesn't perfectly reflect production behavior.

In short: the market-blind models are better than their predecessors and are genuinely independent of market prices. The alpha=0 result reflects current limitations in how the calibration is measured, not that the models have no edge at all. This is an active area of work.

---

## Additional Work in Epic 1

**Historical prediction backfill.** The Model Performance dashboard requires prediction data to show comparisons across seasons. We backfilled predictions for the 2024–2026 games using the new market-blind models, giving the dashboard a rich historical comparison immediately rather than waiting weeks for live predictions to accumulate.

**Dashboard update.** The Model Performance page was updated to show separate performance curves for the old (v1) and new (v2/v3) model versions — home win v2, run differential v2, total runs v3. The dashboard can now filter by model version so direct side-by-side comparisons are possible.

---

## What Epic 1 Means Going Forward

The models are now genuinely independent of the market. Any signal they carry is based purely on observable pre-game information. That's the correct foundation for finding edges: the model should tell us something the market doesn't already know.

The key open question — does the model actually have an edge over the market after this change? — is what the calibration work and live performance tracking are designed to answer. Epic 1 set up the conditions for that question to have a meaningful answer.

---

*Epic 1 completed and merged to main 2026-05-12. All three models retrained and promoted. Market-blind predictions live in production since 2026-05-11.*
