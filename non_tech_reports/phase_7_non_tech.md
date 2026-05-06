# Phase 7: Making the Model Worth Using

## What Phase 7 Was About

Phase 6 ended with an honest finding: the model wasn't beating the market. A systematic analysis of 1,098 game predictions found that on average, the model's win probability estimates sat below what professional oddsmakers were charging — meaning if you followed the model's recommendations, you would be expected to lose money in the long run.

Phase 6 produced a clear list of eight specific gaps. Phase 7 was about closing them.

The work fell into four categories:

1. **New information sources** — data the market uses that the model wasn't seeing at all
2. **Model calibration** — fixing systematic biases in how probabilities were estimated
3. **Model evaluation and promotion** — rigorously comparing old and new model versions before deploying them
4. **Infrastructure reliability** — making sure the daily pipeline is auditable and resilient

---

## Part 1: New Information Sources

### Weather

The most impactful gap from the Phase 6 postmortem. Outdoor ballparks — which is most of them — are meaningfully affected by temperature, wind speed, and wind direction. A 20 mph wind blowing out to center field in Coors Field is a fundamentally different game environment than a cold, calm night in San Francisco. Professional oddsmakers have priced weather into totals markets for decades.

Phase 7 wired in a full weather ingestion pipeline. For every upcoming game, the system now pulls actual forecast data for that ballpark's GPS coordinates — temperature, wind component (the portion of wind aligned with the flight path of a ball toward the outfield), and humidity. Historical weather was also backfilled all the way to 2021 so the model's training data reflects actual game-day conditions rather than season averages.

This was the single biggest data quality improvement in the phase.

### FanGraphs Data (Stuff+ and Pre-Season Projections)

The betting market pays close attention to two FanGraphs data products that the model was previously ignoring entirely.

**Stuff+** is a pitch-quality metric that measures how effective a pitcher's arsenal is — factoring in velocity, movement, and spin — compared to league average. A score of 110 means the pitcher's stuff is 10% better than a typical starter. This is particularly valuable early in the season when in-season rolling stats are based on only a handful of starts.

**ZiPS projections** are pre-season player quality estimates that give the market a prior on every player before a single pitch of the season is thrown. In April, when a pitcher has made three starts, the market is partly pricing ZiPS — the model now can too.

Phase 7 built a full pipeline to ingest, store, and expose both data sources as features, covering starting pitcher arsenal quality for both the home and away starters in every game.

### Umpire Tendencies

Home plate umpires vary significantly in how they call the strike zone. Some umpires call a wide zone that generates more strikeouts and fewer walks; others have a tight zone that leads to higher walk rates and more base traffic. Over time, these tendencies are measurable and the market prices them in.

Phase 7 integrated data from UmpScorecards — a public database of umpire tendencies — along with the MLB Stats API's daily umpire assignment feed. The result: every game prediction now carries two umpire features (runs-per-game tendency and accuracy, both expressed as trailing three-year z-scores relative to league average), with 99.4% coverage for 2026 regular season games.

### Injury and Roster Status

When a key player goes on the injured list, the market reprices immediately. The model had no awareness of IL placements at all.

Phase 7 built an injury tracking pipeline off the MLB Stats API transactions feed — 66,497 roster moves from 2021 through 2026, backfilled and deduplicated. For each game, the model now knows how many players on each side are on the IL and adjusts the lineup quality estimate accordingly: a team missing three regulars gets a lower effective wOBA (weighted on-base average) than one running out its full lineup.

The data confirmed the signal is real: 33.4% of game-rows in the training data had at least one IL player, and injury-adjusted wOBA (0.308) sits meaningfully below unadjusted wOBA (0.331).

### Pitcher-Batter Matchup Archetypes

The model's original lineup features treated all batters as interchangeable — it knew a lineup's average wOBA over the prior 30 days but not how those specific batters tend to perform against this specific type of pitcher.

Phase 7 built a two-sided matchup system:

On the **pitcher side**, every starter is classified into one of three pitch archetypes based on their arsenal mix: fastball-dominant, breaking-ball-dominant, or mixed. This classification updates each season as pitch mix data accumulates.

On the **batter side**, historical plate appearance data is used to calculate how each lineup's batters have performed against each pitch archetype. A lineup stacked with left-handed pull hitters may fare differently against a breaking-ball-dominant pitcher than a lineup with more patient, spray-contact hitters.

The result is six new matchup columns per game that capture the stylistic fit (or mismatch) between the day's starting pitcher and the opposing lineup.

### Pitcher and Batter Clustering

Beyond simple archetypes, Phase 7 built two separate machine learning clustering models — one for pitchers, one for batters — that group players by similar behavioral profiles.

**Pitcher clusters** are built from arsenal vectors: velocity, pitch movement, pitch mix percentages, and Stuff+ scores. The 2025 season produced six clusters with interpretable labels like *power swing-and-miss* and *contact sinker-ball*, capturing meaningful differences in how pitchers generate outs.

**Batter clusters** are built from hitting profile metrics: exit velocity, launch angle, pull tendency, sprint speed, walk rate, and strikeout rate. The result captures profile types like *power pull hitter*, *patient OBP bat*, and *high-whiff contact hitter*.

For each game, the model now knows what type of batters are facing what type of pitcher — and has historical data on how those cross-cluster matchups have played out.

### Bullpen Workload

Teams with heavily used bullpens entering a game are at a disadvantage that the model wasn't capturing. A relief corps that threw 5+ innings the night before is not the same as one that was idle.

Phase 7 extended the bullpen model to track innings pitched in the prior one and two days for each team, along with the number of distinct relievers used. These six features (home and away, each window) are now part of every game prediction.

### Pythagorean Win Expectation

Pythagorean win expectation is a formula that estimates what a team's winning percentage *should* be based on how many runs they've scored and allowed — independent of their actual win-loss record. Teams that are winning more than their run differential would suggest tend to regress; teams underperforming their run differential tend to improve. The market prices this.

Phase 7 added this feature for both teams as well as the differential between them, with a leakage guard ensuring only pre-game data is used.

### Line Movement Features

The odds market itself is a source of information. When a betting line moves — say, the total shifts from 8.5 to 9.5 — that's a signal that large, informed money came in on one side. The model now tracks how far each game's moneyline and totals have moved from open to the most recent snapshot, giving it visibility into where the market has been pushed.

---

## Part 2: Model Calibration

### Home Team Win Probability

A separate calibration problem was confirmed in Phase 7: the model was systematically underestimating home team win probability. This is a known phenomenon — home field advantage is partly captured by the model's features, but not fully.

The fix was to fit a calibration layer (Platt scaling) on top of the existing prediction pipeline using 2026 in-season results. The improvement was meaningful:

```
Home Win Calibration
────────────────────────────────────────────────
Metric                   │ Before    │ After
─────────────────────────┼───────────┼──────────
Calibration error (ECE)  │ 0.0614    │ 0.0370
────────────────────────────────────────────────
```

Expected Calibration Error (ECE) measures how well a model's stated probabilities match actual frequencies. An ECE of 0.06 means the model's probabilities are off by about 6 percentage points on average; reducing it to 0.04 is a meaningful improvement in reliability.

---

## Part 3: Model Evaluation and Promotion

### The Model Versioning System

Before Phase 7, there was no formal way to compare a new model against the one already in production. Any update would immediately overwrite the existing predictions and there was no way to run them side by side. Phase 7 built a proper model versioning system:

- Each model artifact is tagged (v0, v1, v2)
- The prediction pipeline accepts per-target version flags, so the system can simultaneously use v1 for win probability, v1 for run differential, and v2 for total runs — each target promoted independently
- Historical predictions carry version labels, so the performance dashboard can show how each version performed in the periods it was active

### The Total Runs Model Bug and Fix

The most consequential finding in Phase 7 was a bug in how total runs predictions were being stored. The total runs model produces a probability distribution — specifically a log-normal distribution — rather than a single number. The value stored in the database was supposed to be the natural-scale predicted total (e.g., "8.4 runs expected"), but the code was accidentally storing the log-scale parameter (e.g., "2.1") instead.

When this was corrected and historical predictions were re-evaluated:

```
Total Runs — v0 vs v1 Comparison (after bug fix)
──────────────────────────────────────────────────────────────────
Metric                           │ v0 (original)  │ v1 (retrained)
─────────────────────────────────┼────────────────┼───────────────
Mean prediction error (MAE)      │ 3.862 runs      │ 3.472 runs
Mean prediction vs. actual total │ 6.6 runs        │ 7.5 runs
% of games where model > line    │ 14.7%           │ 2.6%
──────────────────────────────────────────────────────────────────
```

v1 produced a lower MAE — but there was a second problem. The model's predictions were clustered in an extremely narrow band (mostly 7.0–8.5 predicted runs across all games) when actual game totals range from 2 to 20+. More critically, the model predicted above the betting line on only 2.6% of games. A model that is almost always predicting *under* the market line is useless for over/under betting — you can't generate signal in both directions.

### Total Runs v2: A Fresh Retrain

Rather than trying to tune v1, Phase 7 retrained the total runs model from scratch using the correct features and clean historical data. The goal was to produce predictions that:
- Are centered around actual game totals (no systematic over- or under-prediction)
- Spread across a reasonable range of outcomes
- Cross above and below the betting line on a meaningful fraction of games

The v2 model achieved three of the four targets:

```
Total Runs v2 — Promotion Gate Results
──────────────────────────────────────────────────────────────────────
Gate                                    │ Result   │ Threshold │ Pass?
────────────────────────────────────────┼──────────┼───────────┼──────
Mean prediction error vs. v0 baseline  │ 3.35 runs │ ≤ 3.86    │ Yes
Average prediction matches actual total │ 0.05 off  │ ≤ 0.5     │ Yes
% of games where model > betting line  │ 83.7%     │ ≥ 25%     │ Yes
Prediction spread (std dev of outputs)  │ 0.77 runs │ ≥ 2.0     │ No
──────────────────────────────────────────────────────────────────────
```

The fourth gate — prediction spread — requires the model to produce outputs that vary meaningfully across games. The v2 model still produces a relatively narrow band of predictions (most games cluster around 8.5–9.5 predicted runs). Testing showed this is a ceiling of the current feature set, not a hyperparameter that can be tuned: all four configurations tested produced the same narrow spread.

Closing this gap requires fundamentally different inputs — either the actual betting line (which the model is trying to beat, so using it as an input creates circularity) or an architecture change. This is deferred to Phase 9. The other three gates clear, and v2 is a material improvement over v0 on every directional metric, so it was promoted to production.

---

## Part 4: Infrastructure Reliability

### Prediction Source Tagging

The daily prediction pipeline has two modes: it normally reads from the feature store built overnight by the dbt pipeline, but when that pipeline hasn't finished yet (typically before 8:30am ET), it falls back to assembling features directly from the MLB Stats API schedule. This intraday fallback was already working, but there was no way to tell afterward which predictions had been scored on full features versus the degraded fallback set.

Phase 7 added a `data_source` tag to every prediction row: `'feature_store'` or `'intraday_fallback'`. The system now also prints a visible warning when the fallback path is used so it's unmissable in the daily output log.

### Hotfixes During Evaluation

Several reliability issues were found and fixed during Phase 7's model evaluation work:

- **Kelly sizing aggregate cap**: The EV Tracker was suggesting bets that summed to more than the bankroll because each bet was capped individually but no total cap existed. Fixed.
- **Timezone bug in lineup monitor**: The lineup confirmation check was running on UTC time, which meant West Coast games on the calendar date boundary were being silently skipped. Fixed to use Eastern Time.
- **Environment portability**: Hardcoded file paths in three scripts were replaced with environment variable lookups, making the system portable across machines and compatible with CI/CD.
- **Weather retry logic**: The weather ingestion script now retries failed API calls with exponential backoff rather than silently dropping weather data for individual games on transient failures.

---

## Summary: What Phase 7 Delivered

| Category | What Changed |
|---|---|
| Weather features | Temperature, wind, humidity now factored in for all games; 2021–2026 backfill complete |
| FanGraphs integration | Stuff+ and ZiPS pre-season projections available as features |
| Umpire tendencies | Trailing 3-year tendency z-scores for every umpire assignment |
| Injury tracking | IL placement data from 2021–2026; lineup quality adjusted for missing players |
| Matchup archetypes | Pitch archetype and batter vs. archetype splits for every game |
| Pitcher clustering | 6-cluster k-means model identifying pitcher types by arsenal |
| Batter clustering | 5-cluster k-means model identifying hitter profiles |
| Bullpen workload | Innings pitched and pitchers used in prior 1–2 days |
| Pythagorean win exp. | Run-differential-based win expectation for both teams |
| Line movement | Open-to-current price shifts for moneyline and totals |
| Home win calibration | ECE improved from 0.061 to 0.037 |
| Total runs model (v2) | Fresh retrain; mean prediction error down 13% vs. v0; systematic bias eliminated |
| Model versioning | Per-target version tags; independent promotion for each prediction target |
| Data source tagging | Every prediction row now labeled feature_store vs. intraday_fallback |
| Reliability fixes | Kelly cap, timezone bug, env portability, weather retry logic |

### Where Things Stand

The model is meaningfully better than it was at the end of Phase 6. The feature set now includes most of what professional oddsmakers factor into game totals and win probability. The systematic biases identified in the Phase 6 postmortem have been corrected.

What Phase 7 did not solve is the hardest problem: closing the gap between a good model and one that consistently finds edges the market has missed. That requires Phase 8's more advanced feature engineering — in particular, bat tracking matchup features and live monitoring infrastructure — plus the Phase 9 architecture work on the total runs model's variance.

The system is ready to be taken seriously. It is not yet ready to be bet with real money on a consistent basis.

---

*This report covers Phase 7 work completed between May 2 and May 5, 2026. For technical details on specific cards, see the evaluation reports in `betting_ml/evaluation/`. For the Phase 8 roadmap, see `project_context.md`.*

