# Phase 3: What the Data Actually Tells Us — Exploratory Analysis Findings

## What Phase 3 Was About

Phases 1 and 2 built the database and assembled the pre-game feature set. Phase 3 asked the harder question: **does any of this actually predict what happens in a game?**

This phase consisted of eleven analysis notebooks and scripts, each tackling a specific question about the data — from "how hard is it to predict total runs at all?" to "do sportsbooks show a home-team bias?" Every analysis concluded with a concrete decision that shaped how the Phase 4 models were designed.

The key mindset shift: in Phase 3, we weren't building anything. We were listening. The goal was to let the historical data tell us what matters, what doesn't, and where we should expect the model to struggle.

---

## Analysis 1: What Are We Actually Trying to Predict?

The first question was foundational: before worrying about features, how hard are these prediction problems?

We're building models for three distinct betting-relevant targets:

1. **Total runs scored** — the over/under number
2. **Run differential** — the margin of victory, which drives spread bets
3. **Home team win probability** — the moneyline

### How Runs Are Distributed

Looking at 23,444 regular season games from 2016–2025, total runs follows a roughly bell-curve-shaped distribution centered around 9.0 runs per game, but with a noticeable right tail — blowout games (15+ runs) happen more often than a pure bell curve would predict.

```
Total Runs Distribution (2016–2025)
─────────────────────────────────────────────────────────────
Runs  │ Games
──────┼──────────────────────────────────────────────────────
1–3   │ ██░ (rare)
4–5   │ ████████░
6–7   │ ████████████████░
8–9   │ █████████████████████░  ← peak zone
10–11 │ ████████████████░
12–13 │ ████████░
14–15 │ ████░
16+   │ ██░  (blowouts — more common than a pure bell curve)
──────┴──────────────────────────────────────────────────────
Mean: ~9.0 runs  |  SD: ~4.5 runs  |  Range: 1–38
```

The standard deviation is consistently around 4.5 runs every season — what varies is the *average*, not the spread. That means a season with a lot of offense (like 2019, the "juiced ball" year) looks like a slight rightward shift of the same bell curve.

### How the Average Has Shifted by Era

One of the clearest findings in the entire project: there's a structural mean shift at the 2022→2023 boundary, when MLB introduced the pitch clock, banned the shift, and enlarged the bases.

```
Average Total Runs Per Game by Season
─────────────────────────────────────────────────
2016 │ ████████████████████████████░  8.94
2017 │ █████████████████████████████░  9.27
2018 │ ████████████████████████████░  8.90
2019 │ ██████████████████████████████░  9.65  ← juiced ball peak
2020 │ █████████████████████████████░  9.25  (60-game COVID season)
2021 │ ████████████████████████████░  9.04
2022 │ ███████████████████████████░  8.57  ← deadened ball, pre-rules
2023 │ █████████████████████████████░  9.21  ← pitch clock era begins
2024 │ ███████████████████████████░  8.76
2025 │ ████████████████████████████░  8.84
─────────────────────────────────────────────────
Note: all complete seasons; 2020 excluded from model training
```

The ~0.64-run jump from 2022 to 2023 is real and structural — it's not statistical noise. The shift ban kept more balls in play, the larger bases encouraged running, and the pitch clock changed how games were managed. This matters for modeling: a single model trained on 2016–2025 without acknowledging this boundary will systematically over-predict scoring for 2022 and under-predict for 2023+.

**Decision made:** Add an explicit "post-2022 rules" flag to all models. Do not build separate era-specific models — the rule change is captured by a flag.

### The Baseline We Need to Beat

If you predict every game will have exactly 9.0 runs (the all-time average), your average error is about **3.5 runs**. That's the naive baseline any useful model needs to improve upon.

For comparison: the best Las Vegas totals lines typically miss by about 2.2–2.5 runs. Closing that gap is the target.

### Home Field Advantage Is Weakening

Home teams win about 52.9% of regular season games historically. But that advantage has been declining:

```
Home Win Rate by Season
─────────────────────────────────────────────────
2016 │ ████████████████████████████░  52.9%
2017 │ █████████████████████████████░  54.4%
2018 │ ████████████████████████████░  52.8%
2019 │ ████████████████████████████░  52.9%
2020 │ █████████████████████████████░  54.8%  (COVID bubble)
2021 │ █████████████████████████████░  53.7%
2022 │ █████████████████████████████░  53.4%
2023 │ ██████████████████████████░  51.9%  ← lowest on record
2024 │ ███████████████████████████░  52.3%
2025 │ █████████████████████████████░  54.6%
─────────────────────────────────────────────────
```

2023 saw the lowest home win rate in the dataset — 51.9%. Using a static "home teams win 53% of the time" assumption in a model would introduce a systematic error in recent seasons. The model accounts for this with a trailing 3-year home win rate that updates each season.

---

## Analysis 2: Feature Coverage Check

Before diving into which features predict outcomes, we confirmed that the data is actually populated. Out of 374 feature columns across ~23,000 games:

- **Lineup stats, team rolling stats, park features, bullpen workload:** All below 5% missing in every season. Lineup data is 100% complete going back to 2015.
- **Starter platoon splits:** 11–17% missing in every season. The reason is simple: pitchers making their first full season don't have a track record against left-handed and right-handed batters from the prior year. This isn't a data problem — it's a real limitation. New pitchers are handled with a flag and league-average fill-ins.
- **Betting market prices:** 100% missing for 2016–2020 (historical data wasn't available until Phase 1 completed the backfill). Available for 72–78% of games from 2021 onward.

---

## Analysis 3: How Many Games Before Stats Are Reliable?

This question matters because every April, rolling statistics are built on just a handful of games. Are early-season stats signal or noise?

The short answer: **they're mostly noise for the first two weeks.**

### How Correlation Strengthens as the Season Progresses

We compared how strongly different statistics predicted game outcomes depending on whether they were computed over a 7-day, 14-day, 30-day, or full-season-to-date window:

```
Correlation With Total Runs — By Rolling Window (|Pearson r|)
──────────────────────────────────────────────────────────────
                     7-day   14-day   30-day   Season-to-date
──────────────────────────────────────────────────────────────
Team Offense wOBA    0.041    0.046    0.052       0.051
Team Pitching xwOBA  0.050    0.056    0.058       0.061
Starter K%           0.060    0.070    0.077       0.077  ← biggest gain
Starter xwOBA        0.048    0.055    0.057       0.066
──────────────────────────────────────────────────────────────
Column Mean          0.050    0.057    0.061       0.064
──────────────────────────────────────────────────────────────
```

Starter strikeout rate shows the biggest improvement from short to long windows — a 29% jump from 7-day to season-to-date. Team offense flattens out around 30 days. The takeaway: for pitchers, more history is better. For offense, a month of data captures most of the available signal.

### Early-Season Noise by Games Played

We looked at how predictive power varied depending on how many games each team had actually played:

```
Pitching Quality (Team xwOBA) Correlation — By Games Played
─────────────────────────────────────────────────────────────
 0–10 games played  │ ████████░  0.046   ← weakest
10–30 games played  │ ███████░░  0.040   ← transitional zone (worst!)
30+ games played    │ █████████████░  0.068  ← stable
─────────────────────────────────────────────────────────────
```

Note that the 10–30 game range is actually *weaker* than 0–10. This is the transitional zone where rolling stats have accumulated too few games to be stable but Opening Day effects have already worn off. This band covers roughly the first two weeks of a season.

**Decision made:** Only use games where both teams have played at least 15 games. This removes about 5.5% of training data — a small price for a much cleaner signal.

---

## Analysis 4: What Actually Predicts Game Outcomes?

This was the most important analysis in Phase 3. We measured how strongly each of the 374 features in our dataset correlates with each of our three prediction targets.

### What Predicts Total Runs (the Over/Under)

The results were clear and somewhat counterintuitive:

```
Top Predictors of Total Runs — |Pearson r|
─────────────────────────────────────────────────────────
Park Run Factor (3yr)      │ ████████████░  0.122  ← #1
Ballpark Elevation         │ ███████████░  0.111  ← #2
Runs Per Game at Park      │ █████████░  0.094
Home Team Pitching xwOBA   │ ████████░  0.075–0.092
Home Starter K% (season)   │ ██████░  0.065
Home Offense Slugging      │ ██████░  0.061
Home Starter xwOBA         │ ██████░  0.060
Home Bullpen xwOBA         │ █████░  0.058
Away Starter K%            │ █████░  0.047
Home Offense wOBA          │ █████░  0.047
─────────────────────────────────────────────────────────
Away Team Pitching xwOBA   │ █░  0.008   ← nearly zero!
─────────────────────────────────────────────────────────
```

**The park effect is the strongest predictor of total runs, stronger than any individual team or pitching stat.** Where the game is played — Coors Field vs. Petco Park — is more predictive of total scoring than who's on the mound. This makes intuitive sense when you think about it: park environment is a constant for the entire game, while individual performance varies.

The other striking finding: **home team pitching quality predicts total runs about 9 times more strongly than away team pitching quality** (r=0.075 vs. r=0.008). This odd asymmetry was surprising enough that we ran a dedicated follow-up investigation (see Analysis 8 below).

### What Predicts Run Differential (the Spread)

When it comes to predicting *who wins by how much*, the picture shifts considerably:

```
Top Predictors of Run Differential — |Pearson r|
─────────────────────────────────────────────────────────
Away Team Win %            │ ██████████░  0.102  ← overall quality
Away Pitching xwOBA (30d)  │ █████████░  0.091  ← now full-strength!
Away Starter K% (season)   │ █████████░  0.091
Home Team Win %            │ ████████░  0.088
Home Pitching xwOBA (30d)  │ ████████░  0.086
Home Starter K% (season)   │ ███████░  0.071
Away Offense wOBA (30d)    │ ██████░  0.066
Home Offense wOBA (30d)    │ ██████░  0.060
─────────────────────────────────────────────────────────
```

Season win percentage is the single strongest predictor of run differential — overall team quality, built up over 100+ games, is the best signal for who wins by how much. And notably, away team pitching is now *equally predictive* as home team pitching. The asymmetry that dominated the total runs rankings disappears for run differential.

### What Predicts Wins (the Moneyline)

Win probability predictions look very similar to run differential, with team win percentage and pitching quality leading the way. No feature is individually dominant; this is fundamentally a harder prediction problem.

### Key Lesson: Pitching Quality Beats Offensive Stats ~2-to-1

Across all three prediction targets, pitcher-quality features consistently outperform offensive-quality features with similar correlations. A team's expected contact quality against their pitching staff is more predictive than that team's offensive output. This reinforces a well-understood principle in baseball: **pitching carries games.**

### What Doesn't Work: Redundant Features

We also identified features that were too similar to each other to include separately. The main finding: **14-day rolling windows add nothing beyond 7-day and 30-day windows**. Every pair of redundant features (where two stats tracked essentially the same thing) involved 14-day variants.

Meanwhile, wOBA (raw weighted on-base average) and xwOBA (expected, park-adjusted version) are *not* redundant — they correlate with each other around r=0.68–0.70, meaning they each carry genuinely different information. When we have to choose between them, xwOBA is preferred because it's park-adjusted.

---

## Analysis 5: Does Where You Play Really Matter That Much?

We already knew park factor was the #1 predictor of total runs. This analysis dug deeper into the magnitude and verified it wasn't a coincidence.

### The Park Factor Quartile Test

We split all parks into four tiers — from the most pitcher-friendly (Q1) to the most hitter-friendly (Q4) — and measured actual scoring in each tier:

```
Average Total Runs by Park Factor Tier
───────────────────────────────────────────────────────────────────────
Q1 — Pitcher Friendly │ ████████████████████████████░  8.52 runs/game
   (Petco, Oracle)    │ [Parks with run factor 7.0–8.4]
                      │
Q2                    │ █████████████████████████████░  8.76 runs/game
                      │ [Parks with run factor 8.4–8.9]
                      │
Q3                    │ ██████████████████████████████░  9.15 runs/game
                      │ [Parks with run factor 8.9–9.4]
                      │
Q4 — Hitter Friendly  │ ████████████████████████████████░  9.67 runs/game
   (Coors, Great      │ [Parks with run factor 9.4–12.0]
    American, etc.)   │
───────────────────────────────────────────────────────────────────────
Q4 − Q1 gap: +1.15 runs per game
```

The ordering is perfectly preserved — Q1 < Q2 < Q3 < Q4 without exception — and the gap is 1.15 runs per game between the most pitcher-friendly and most hitter-friendly environments. This is a real, consistent, and substantial effect.

Elevation adds another dimension: ballpark altitude (feet above sea level) is the second-strongest predictor of total runs after the run factor itself, partially independent. The ball carries differently at altitude, and this shows up consistently in the data.

### Does Fatigue Matter? (Rest, Travel, Schedule)

We also tested whether team rest, back-to-back scheduling, and cross-country travel affect game outcomes. The findings were underwhelming:

```
Schedule Feature Correlations with Total Runs
──────────────────────────────────────────────────────────
Days of rest (home team)    │ ░  r = 0.0004  ← essentially zero
Days of rest (away team)    │ ░  r = 0.0023
Timezone change (home)      │ ░  r = 0.012
Timezone change (away)      │ ░  r = 0.023
──────────────────────────────────────────────────────────
For reference:
Park run factor             │ ████████████░  r = 0.122
──────────────────────────────────────────────────────────
```

Schedule fatigue shows correlations barely above zero. A team on no rest and a team with a full week off score essentially the same number of runs on average. These features are kept in the model because adding them costs nothing, but we're not expecting them to improve predictions meaningfully.

---

## Analysis 6: Does the New Bat Speed Data Add Anything?

Starting in mid-2023, Statcast began tracking bat speed and swing length using Hawk-Eye sensors at every stadium. This felt potentially exciting — bat speed is a more fundamental measure of a hitter's ability than traditional stats.

### The Coverage Problem

```
Bat Tracking Data Availability
─────────────────────────────────────────────────
2019–2022     │ ░░░░░░░░░░  0% coverage
2023 (H1)     │ ░░░░░░░░░░  0% (pre-rollout)
2023 (H2)     │ ████░░░░░░  46% (partial rollout)
2024          │ ████████░░  45% (swing events only)
2025          │ ████████░░  46% (swing events only)
─────────────────────────────────────────────────
As a share of our full 2016–2025 training set: 27%
```

Bat tracking only covers about 27% of the training data (2023-half through 2025), and within those seasons only covers pitches where a swing was actually made.

### Does It Actually Predict Anything?

More importantly, even on the sub-sample where we *do* have bat tracking data:

```
Predictive Strength Comparison (same sub-sample, |r| with total runs)
──────────────────────────────────────────────────────────────
Park Run Factor             │ █████████░  0.088   ← traditional
Home Pitching xwOBA         │ ████████░  0.078   ← traditional
Home Starter K%             │ ███████░  0.070   ← traditional
──────────────────────────────────────────────────────────────
Home Bat Speed (30d avg)    │ ██░  0.022   ← bat tracking
Away Bat Speed (30d avg)    │ ██░  0.018   ← bat tracking
Home Swing Length (30d avg) │ █░  0.010   ← bat tracking
Away Swing Length (30d avg) │ ░  0.003   ← bat tracking
──────────────────────────────────────────────────────────────
```

Bat speed is about 4–5 times weaker a predictor than park factor, and below every traditional stat shown here.

**Why?** The problem isn't that bat speed is meaningless — it's that we're averaging it across an entire team's 30 days of swings. The interesting signal in bat speed probably lives at the individual matchup level: this specific batter's bat speed against this specific pitcher's stuff. Aggregating to a team-level monthly average loses that precision.

**Decision made:** Exclude bat tracking from Phase 4 models. Revisit in Phase 5 when per-batter matchup aggregations can be built.

---

## Analysis 7: Do Recent Hot and Cold Streaks Matter?

We built "momentum" features — statistics measuring how much a team or pitcher's recent form (last 7 days) diverges from their longer-term baseline (last 30 days or season-to-date). The idea: a pitcher on a hot streak should be treated differently from one reverting to their mean.

### The Surprising Finding

Individual momentum features had very weak correlations with outcomes. The maximum correlation of any single momentum feature with total runs was r = 0.020 — barely detectable. But when we tested whether *having 7-day rolling stats at all* improved predictions versus only having 30-day and season-to-date stats, the answer was yes:

```
Improvement in Model Explanatory Power (ΔR²)
──────────────────────────────────────────────────────────────
Model with only 30-day and season-to-date features   │ baseline
                                                     │
Add 7-day rolling windows directly                   │ +0.043–0.047
                                                     │
Add momentum (7d minus 30d) delta features instead   │ essentially same
──────────────────────────────────────────────────────────────
```

The 7-day rolling windows add real predictive lift — but the improvement is because **recent form matters**, not because the *direction of change* matters. A pitcher who had a 2.50 ERA over the last 7 days is predictive regardless of whether that's better or worse than their season average. The "momentum" framing (positive vs. negative trend) added nothing.

**Decision made:** Include 7-day rolling windows directly as features. Drop the delta/momentum calculations.

### What About Lineup-vs-Starter Handedness Matchups?

We also tested whether explicitly calculating how a lineup's left/right-handed composition matched up against the opposing starter's platoon splits added signal over just having the starter's overall stats.

Answer: mostly no. The matchup calculation captured some correlation with run differential and win probability (r up to 0.086), but when you already have the starter's overall strikeout rate and xwOBA in the model, the specific lineup-vs-handedness adjustment added less than 0.002 additional explained variance — below the threshold where it's worth the complexity.

---

## Analysis 8: The Puzzling Home/Away Pitching Asymmetry

One of the most interesting findings in Phase 3 required a dedicated investigation.

When we measured how predictive pitching quality was for total runs, we found something odd:

```
Pitching Quality vs. Total Runs (|r|)
──────────────────────────────────────────────────────────────
Home team pitching (xwOBA against, 30d)  │ ████████░  0.085
Away team pitching (xwOBA against, 30d)  │ █░  0.011
──────────────────────────────────────────────────────────────
Asymmetry ratio: ~9×
```

Why would home team pitching quality predict total runs 9 times more strongly than away team pitching quality? Theory says both should matter equally — each team's pitching staff faces the opposing lineup.

We tested four possible explanations:

**H1: Park factor is absorbing the away team signal.** Maybe pitching quality measured at home parks is getting "credit" for the park environment, while away team stats are park-neutral. We controlled for the park factor statistically and the asymmetry persisted unchanged. **Refuted.**

**H2: It's an era artifact.** The asymmetry was present before the 2021 rule changes (5.8× ratio) but got significantly worse afterward (18.2× ratio). This suggests the pitch clock and shift ban changed something about how home and away starters use their bullpens differently. **Partially supported.**

**H3: Away pitching stats measured at home parks are contaminated.** If away teams' numbers are inflated because they're being measured at run-friendly home parks, the stats would be unreliable. We compared away starter stats (measured in their own home context) vs. away team-level stats — they were identical. **Refuted.**

**The critical insight:** The asymmetry is *specific to total runs*. When we look at run differential or win probability instead of total runs, away pitching quality is just as predictive as home pitching quality:

```
Away Pitching Quality Correlation by Target
──────────────────────────────────────────────────────────────
Total runs          │ █░  0.011   ← near-zero
Run differential    │ █████████░  0.094   ← full-strength
Win probability     │ ████████░  0.084   ← full-strength
──────────────────────────────────────────────────────────────
```

Away pitching *does* matter — it's just expressed differently in total runs vs. directional outcomes. The best current explanation is that total run scoring is dominated by park environment and home pitching decisions in ways that don't symmetrically apply to the visiting team's context. The asymmetry intensified post-2021, suggesting pitch clock and shift ban changed game management patterns asymmetrically for home vs. away starters.

**Decision made:** Keep both home and away pitching features in the model. Include era flags to account for the intensifying asymmetry.

---

## Analysis 9: Do the 2023 Rule Changes Require Separate Models?

We formally tested whether the pre-2022 and post-2022 eras needed to be treated as entirely different modeling problems.

The test: take the 20 strongest-performing features and measure whether their correlation with game outcomes changed significantly between the two eras (2016–2021 vs. 2022–2025).

**Result:** Zero features showed a statistically significant shift. While 8 out of 20 features showed correlations that changed by more than 0.015 between eras, none of those changes held up to statistical testing on our sample sizes. The rule changes shifted the *average* scoring level but didn't fundamentally change *which features predict outcomes*.

```
Era Comparison: Pre- vs. Post-2022 Rule Changes
──────────────────────────────────────────────────────────────
Features tested              │ 20
Features with apparent shift │ 8
Statistically significant    │ 0  ← none
──────────────────────────────────────────────────────────────
Verdict: One unified model with a "post-2022 rules" flag is sufficient.
No need for separate era-specific models.
```

**Decision made:** Train one unified model. The `post_2022_rules` flag already in the feature set is the right way to handle the 2022→2023 boundary.

---

## Analysis 10: How Good Are Sportsbooks? And Can We Beat Them?

Before treating sportsbook implied probabilities as model features, we asked: **how accurate are they in the first place?**

We tested eight major sportsbooks against historical results from 2021–2025 (~7,000–8,000 matched games). The primary accuracy metric is called the Brier score — lower is better, 0.25 is the baseline for coin-flip predictions.

```
Sportsbook Accuracy (Moneyline — lower Brier = better)
──────────────────────────────────────────────────────────────
Best threshold (pure coin flip): 0.2500

Market consensus (avg across all books): 0.2395  ← the benchmark

All major books scored nearly identically: 0.238–0.241
──────────────────────────────────────────────────────────────
```

The books are good. The consensus prediction across all sportsbooks is more accurate than any single book — and crucially, **the "sharp" books (lowvig, Betfair, betonlineag, bovada) are no more accurate than the "retail" books (DraftKings, FanDuel, BetMGM).**

### Surprising Findings About Sportsbooks

**No home-team bias.** The conventional wisdom that sportsbooks pad home-team lines to attract square bettors was **not supported**. Home-team implied probability bias was essentially zero across all books and all seasons. The books are pricing home advantage correctly.

**Consistent underlines on totals.** Every book, every season, showed the same pattern: the actual over rate was only 45–48%, meaning totals lines were consistently set slightly high (by about 0.4–0.5 runs). This is a subtle, consistent pattern across all books — not one book being miscalibrated, but a structural feature of how totals markets work.

**The rule changes didn't move the lines.** We tested whether the 2023 pitch clock and shift ban caused sportsbooks to update their totals lines higher. They didn't — or at least not in a clean, detectable way.

**The benchmark is clear:** Our Phase 4 models need to achieve a Brier score below 0.2395 to add value over simply following the consensus market line. The market has already absorbed most of the publicly available signal.

---

## Summary: What Phase 3 Decided

Phase 3 produced a definitive set of design decisions for how the Phase 4 models are built:

| Question | Answer |
|---|---|
| Should we use one model or separate era models? | One unified model with a `post_2022_rules` flag |
| Which rolling window is most predictive for pitchers? | Season-to-date |
| Which rolling window for team offense? | 30-day |
| Are 7-day short windows worth including? | Yes — include them directly, not as "momentum" differences |
| Are 14-day windows worth including? | No — fully redundant with 30-day |
| Do park factors matter? | Yes — the single strongest predictor of total runs |
| Does ballpark elevation matter separately from park factors? | Yes — second-strongest predictor, partially independent |
| Does schedule rest/travel matter? | Barely — include as cheap flags but expect minimal lift |
| Should we include bat tracking data? | Not yet — only 27% coverage and weak signal at team-aggregation level |
| Should we use wOBA or xwOBA? | xwOBA (park-adjusted, more stable) |
| Should we include lineup-vs-starter handedness matchups? | No — negligible incremental value |
| Should starter and bullpen pitching be treated separately? | Yes — each carries independent predictive signal |
| Does bullpen workload (pitches thrown, relievers used) matter? | No — near-zero value beyond trailing quality stats |
| What's the benchmark to beat? | Brier score < 0.2395 (sportsbook consensus accuracy) |
| Are there games we should filter out of training? | Yes — games where either team has fewer than 15 games played |

---

*This report covers Phase 3 work completed as of April 24, 2026. For context on how the data was built, see the Phase 1 and Phase 2 non-technical reports. For how these findings were applied in modeling, see the Phase 4 non-technical report.*
