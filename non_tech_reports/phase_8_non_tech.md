# Phase 8: Building a Better Foundation

## What Phase 8 Was About

Phase 7 ended with a working system that was honest about its limitations: the model was at break-even against the market — not losing, but not finding edges consistently enough to bet with confidence. The Phase 6 postmortem identified specific gaps, and Phase 7 closed them. But even with all that work, the model's win probability estimates were still largely in line with what professional oddsmakers were charging.

Phase 8 was the next layer: a large-scale effort to give the model information it had never seen before, sharpen the infrastructure around it, and run a rigorous evaluation to understand exactly where the remaining gaps are.

The phase shipped 19 cards over roughly one week (May 3–9, 2026). It produced the largest single expansion of the feature set in the project's history and the most systematic analysis of model quality to date.

---

## Part 1: New Data the Model Had Never Seen

### Head-to-Head Pitcher-Batter History

Baseball analysts have long known that certain pitcher types give certain hitter profiles more trouble than others. A left-handed pitcher with a sharp slider is a different matchup than a right-hander with a four-seam fastball, even if both have the same season ERA.

Phase 8 built a full per-pair pitcher-batter history: for each game, the model now knows how specific batters in today's lineup have historically performed against today's starting pitcher — expressed as weighted on-base average (wOBA) and expected wOBA (xwOBA) with Bayesian shrinkage that prevents small-sample noise from dominating the estimate. The model also knows how well each team's lineup has fared against that specific pitcher's arsenal type this season, across all prior at-bats that can be matched.

### Catcher Framing

One of the quieter edges in baseball analytics is catcher framing — the ability of a catcher to receive pitches in ways that make borderline calls more likely to be ruled strikes. Elite framers can generate several runs of value per season, and the market prices this in. The model now has access to two framing metrics per game (blended framing runs saved and defensive runs) with 99.8% coverage, meaning the model almost never goes into a game without knowing the catcher situation.

### Starter Command and Swing-and-Miss Quality

Two starter quality metrics were added:

**CSW% (Called Strikes + Whiffs)** measures how often a pitcher generates a called strike or a swing-and-miss per pitch, regardless of whether it results in a strikeout. It's a faster-updating indicator of stuff quality than strikeout rate. A starter who throws 40% of pitches for called strikes or whiffs is taking the bat out of hitters' hands regardless of what the scorebook says.

**Arsenal Drift** captures how much a pitcher's pitch mix has changed from their historical baseline over the most recent five starts. Starters who suddenly start throwing more sliders and fewer fastballs may be compensating for velocity loss — or may be setting up a new weapon. Either way, it's information the market responds to.

### Public Betting and Bookmaker Disagreement

Phase 8 integrated two new data sources that track what the broader betting market is doing:

**Action Network public betting percentages** tell the model what fraction of the betting public is on the home team versus the away team for each game. When 80% of the public money is on one side, the line often doesn't fully reflect that — sharp bettors may be on the other side. The model now sees this signal for every game it can.

**Bookmaker disagreement** measures how much variation exists across different sportsbooks' lines for a given game. When five bookmakers agree that the home team is -145 and one books them at -125, something is off. Phase 8 built a daily morning snapshot of spread across sharp-book and soft-book tiers — seven disagreement features now flow into every game prediction.

### Bullpen Leverage Exhaustion

In close, high-leverage games, teams burn through their best relievers. A bullpen that used its closer and two top setup men last night is a different team today than one that used mop-up arms in a blowout. Phase 8 built a leverage-weighted bullpen exhaustion metric that tracks how much high-leverage work each team's bullpen has done in the prior one and three days, alongside a proxy for whether the closer is available.

### Pythagorean Residuals

Teams that are winning more (or fewer) games than their run differential would predict tend to regress over time. Phase 8 added each team's Pythagorean residual — the gap between their actual winning percentage and what their run differential predicts — as a feature. Teams with large positive residuals (winning more than they should) are likely to cool off. This is a staple of professional baseball analysis.

### Base-State Split Metrics and Run Scoring Sequencing

The model now knows how each team performs in specific game situations: runners on base, scoring position, late-inning scenarios. Teams differ significantly in how efficiently they convert base runners to runs — some teams with identical batting averages generate very different run totals based on how their hits cluster. Phase 8 added rolling base-state split metrics capturing this for both the offensive and pitching sides of each game.

### Bat Tracking Matchup Profiles

Since July 2023, MLB has collected bat tracking data at the individual swing level: bat speed, swing length, and attack angle for every swing. Phase 8 aggregated this into lineup-level rolling averages and matched them against starting pitcher velocity to create a bat-speed-vs-fastball-speed matchup feature. When a lineup full of slow bat speed faces a premium fastball pitcher, the model now knows it. This feature showed about twice the predictive signal of previous team-level batting averages.

---

## Part 2: Model Evaluation — What the Data Actually Showed

### The Phase 8 Batch Retrain

With all of those new features built into the system, Phase 8 ran a systematic model evaluation: retrain the models, check if they improved, and run the most rigorous quality analysis done to date.

The headline results:

```
Phase 8 Retrain — Promotion Gate Results
──────────────────────────────────────────────────────────
Target         │ Metric     │ Before    │ After     │ Pass?
───────────────┼────────────┼───────────┼───────────┼──────
home_win       │ Brier      │ 0.2439    │ 0.2422    │ Yes
home_win       │ ECE        │ —         │ 0.0053    │ Yes
total_runs     │ MAE        │ 3.5118    │ 3.5107    │ Yes
total_runs     │ Bias       │ 0.000     │ 0.048     │ Yes
run_diff       │ —          │ —         │ NOT RETRAINED │ —
──────────────────────────────────────────────────────────
```

The home_win and total_runs models cleared their gates and were promoted. Run_diff was not retrained — and the reason why turned out to be the most important finding of the phase.

### The Market Circularity Problem

The most important finding from Phase 8 was not a number — it was a structural problem in how the models had been trained.

When the evaluation team ran a feature importance analysis on each model, the results were striking:

**For total_runs:** The single most influential feature was `home_win_prob_sharp`, followed by `home_moneyline_decimal`. In other words, the model's most reliable guide to how many runs would be scored in a game was... the market's opinion of who would win the game. This means the total_runs model is largely recalculating what the market already priced in.

**For run_differential:** Even worse — the #1 permutation-importance feature was `home_win_prob_consensus`. 61% of the model's 294 features were identified as exclusion candidates (meaning shuffling them barely changes the output). And the model had zero of the 19 new Phase 8 feature groups in its training data — the entire investment in bat tracking, catcher framing, bullpen leverage, and so on had never reached this model.

**For home_win:** Three of the top-20 most influential features were direct market signals (market-derived probability and moneyline odds).

Why does this matter? The model is supposed to generate a view that's *different* from the market — that divergence is where edge comes from. When the market line is one of the model's strongest inputs, the model's output is partly a recalculation of the market price. A model that mostly echoes consensus cannot consistently beat consensus.

### The fix

The fix for all three models is the same: retrain them with market-derived columns explicitly excluded from the feature set. The goal is a model that forms its view from pitcher quality, lineup matchups, park factors, weather, and historical tendencies — independently of what the market has already priced. Then when the model's probability diverges from the market's implied probability, that divergence is a genuine signal rather than noise.

This market-blind retrain is scheduled for approximately May 22, 2026, once enough 2026 in-season data has accumulated to make the new versions meaningful.

---

## Part 3: Infrastructure

### Live Model Health Monitoring

Phase 8 wired three monitoring scripts into the daily pipeline:

- **Model health**: Every night, the system computes how well the model's probabilities matched actual outcomes over the rolling 14-day window. If the calibration error exceeds a threshold, an alert is fired.
- **Data freshness**: After each ingestion job, the system checks that every data source updated within its expected window.
- **Prediction coverage**: After the daily prediction run, the system confirms that all confirmed-lineup games were scored.

All three checks run automatically via GitHub Actions and write their results to Snowflake.

### dbt Compilation Gate

Phase 8 added a CI check that compiles the entire dbt SQL pipeline on every pull request. This catches syntax errors and broken model references before they reach production — a class of bug that had previously only been caught at runtime during the daily ingestion run.

### CLV Tracking

Phase 8 built full Closing Line Value (CLV) tracking — comparing the model's probability on each game against the final odds just before game time. This is the most important quality metric for a betting model: if the model's pre-game probability was better than the market's final consensus, it was adding value; if it was worse, it was echoing a stale view.

As of the Phase 8 evaluation, mean CLV is −0.011 (the model is 1.1 percentage points below closing odds on average for live 2026 games). This is the number the market-blind retrain is trying to flip positive.

---

## Summary: What Phase 8 Delivered

| Category | What Changed |
|---|---|
| Pitcher-batter H2H | Per-pair wOBA/xwOBA history with Bayesian shrinkage for every game matchup |
| Catcher framing | Blended framing + defensive runs; 99.8% coverage |
| Starter CSW% | Called strikes + whiffs; 3-start and season rolling windows |
| Starter arsenal drift | Pitch mix deviation from historical baseline; detects command or velocity changes |
| Bat tracking matchup | Lineup bat speed vs. starter fastball velocity; 2× prior signal strength |
| Bullpen leverage exhaustion | Leverage-weighted usage in prior 1 and 3 days; closer availability proxy |
| Public betting signals | Action Network ML and totals betting percentages; sharp signal flags |
| Bookmaker disagreement | Morning-snapshot spread across 7 tiers; stale book flag |
| Pythagorean residuals | Both teams' regression-to-mean indicators |
| Base-state splits | Run-sequencing efficiency in runners-on, scoring-position, late-inning situations |
| Live model health monitoring | 14-day ECE/Brier rolling check; data freshness; prediction coverage |
| dbt compilation gate | CI check on every pull request |
| CLV tracking | Per-game closing line value computation and trending |
| Market-blind retrain prep | `_MARKET_COLS_TO_EXCLUDE` populated; Phase 9 retrain plan documented |

### Where Things Stand

Phase 8 achieved what it set out to do: build a deep, modern feature set and run a rigorous quality evaluation. The models are meaningfully better informed than they were at the start of the phase.

The central challenge that emerged from the evaluation is market circularity — the models have been learning from the market's opinions rather than forming fully independent views. This is the central problem Phase 9 will address. The market-blind retrains are not a small fix; they're the test of whether this project's single-model approach can generate genuinely independent edge, or whether a more radical architecture change is needed.

The Bayesian inference engine cards (9.F1–9.F5) — which would make the model weight its own opinion more heavily in high-uncertainty situations — are ready to implement in principle, but only make sense once the model is no longer echo-chambering the market. They are Phase 9's second priority, after the market-blind retrains confirm or refute the single-model architecture.

The system is better than ever. Whether it can beat the market remains the open question.

---

*This report covers Phase 8 work completed between May 4 and May 9, 2026. For technical details on specific cards, see the evaluation reports in `betting_ml/evaluation/`. The key summary document is `betting_ml/evaluation/phase_8_batch_retrain_impact.md`. For the Phase 9 roadmap, see `project_context.md`.*
