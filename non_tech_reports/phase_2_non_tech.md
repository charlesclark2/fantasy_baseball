# Phase 2: Assembling the Pre-Game Scouting Report — What We Did and What We Found

## What Phase 2 Was About

If Phase 1 was about building and cleaning the raw data, Phase 2 was about turning it into something a model can actually use.

Before any machine learning can happen, you need to answer a deceptively simple question: **what do we know about this game before first pitch?**

That's the entire job of Phase 2. We took the 22+ data tables built in Phase 1 — rolling stats, platoon splits, bullpen data, park factors, lineup records — and assembled them into a single, comprehensive pre-game profile for every regular season game from 2015 through today. Think of it like generating a unified scouting report for each matchup: one document that consolidates everything we know about both teams heading into that game, with no information from after the game slipped in.

The result is a feature store — a clean, validated table of ~23,444 games, each one described by roughly 374 variables drawn from the five categories below.

---

## The Five Feature Groups

### 1. Lineup Features

For each team's confirmed batting lineup, we aggregated the rolling statistics of all nine hitters into a single team-level profile. This covers:

- **Offensive production**: wOBA, xwOBA, hard-hit rate, barrel rate — rolling over the past 30 days and season-to-date
- **Plate discipline**: strikeout rate, walk rate — both trailing windows
- **Handedness composition**: what percentage of the lineup bats right-handed, which matters against a left-handed starter
- **Platoon splits from the prior season**: how each lineup's hitters collectively performed against left-handed vs. right-handed pitching in the previous full season

A critical design choice here: we use the **confirmed pre-game lineup** filed with the league, not a projected lineup. As established in Phase 1, this data is available with 100% coverage going back to 2015, so there's no guesswork about who's actually in the lineup.

### 2. Starting Pitcher Features

For each starter, we built a profile based on what's known before the game begins:

- **Recent performance**: strikeout rate and xwOBA-against rolling over the past 30 days and season-to-date
- **Days of rest**: how many days since the starter's last outing
- **Prior-season platoon splits**: how the starter performed against left-handed vs. right-handed batters last season — useful context when we know the opposing lineup's handedness composition
- **Innings per start trend**: whether the starter has been going deep into games recently, which is a soft signal of how quickly the bullpen might be needed

One gap to be aware of: debut pitchers (those making their first MLB starts in a given season) have no prior-season split history. About 11–17% of games involve at least one starter in this situation. Those slots get flagged and filled with league-average estimates rather than left blank.

### 3. Team Context Features

This is the most comprehensive feature group. Beyond lineup stats, each team comes into a game carrying a broader context:

**Pitching context:**
- Rolling team pitching stats (runs allowed, xwOBA against, strikeout and walk rates) — 7-day, 30-day, and season-to-date
- Bullpen effectiveness: how the 'pen has actually pitched over the past 14 and 30 days (xwOBA against, strikeout rate, hard-hit rate)
- Bullpen workload: how hard the bullpen has been used recently — pitches thrown and relievers used over the past 1, 3, and 7 days

**Offensive context:**
- Team rolling offense (runs scored, wOBA, xwOBA, hard-hit and barrel rates) — 7-day, 30-day, and season-to-date
- Platoon splits: how the team's offense has performed against right-handed vs. left-handed starters, and how the team pitching has fared against right-handed vs. left-handed lineups
- Home/away splits: separate offensive and pitching stats for home and road environments

**Schedule and fatigue context:**
- Days of rest (or lack of it)
- Games played in the past 7 and 14 days
- Current home/away streak length
- Whether the team traveled across time zones to reach this series

**Season record:**
- The team's cumulative win-loss record and winning percentage through the day before the game

### 4. Park and Ballpark Features

Every game is played somewhere, and where matters. The park feature captures:

- **Physical dimensions**: outfield wall distances (left, center, right), wall height
- **Surface**: grass vs. artificial turf
- **Roof type**: open, dome, or retractable
- **Elevation**: feet above sea level — Coors Field is the extreme case, but elevation subtly affects ball flight everywhere
- **Empirical run factor**: how many runs per game have historically been scored at this park, relative to league average. We use the prior season's run factor so the model never "sees" runs scored in the current season.

The three-year rolling run factor is particularly useful — it smooths out year-to-year noise while still capturing parks that have changed (dimensions modified, humidor installed, etc.).

### 5. Betting Market Features

The pre-game betting line captures something that traditional stats don't: the collective judgment of professional oddsmakers who have already absorbed all publicly available information and priced the game.

To understand why this is useful, it helps to understand how betting lines actually work.

#### How the moneyline works

The moneyline is the most straightforward bet in baseball: you're simply picking which team wins the game. The price is expressed as a positive or negative number anchored to $100.

- A **negative number** means that team is favored. `-150` means you'd have to bet $150 to win $100. The bigger the number, the heavier the favorite.
- A **positive number** means that team is the underdog. `+130` means a $100 bet returns $130 profit. The bigger the number, the bigger the underdog.

If you see a game posted as Yankees -150 / Red Sox +130, the Yankees are favored: you'd bet $150 to win $100 on New York, or $100 to win $130 on Boston.

These numbers aren't arbitrary. They reflect the sportsbook's assessment of the probability that each team wins.

#### How the totals line works

The totals market — also called the over/under — doesn't ask you to pick a winner. Instead, you're betting on whether the combined run total for both teams will be higher or lower than a posted number. If the line is set at 8.5 runs and you bet the over, you win if the two teams combine for 9 or more runs. The "half run" (.5) eliminates the possibility of an exact tie.

The number itself is the oddsmakers' best estimate of how many runs will be scored, accounting for the pitching matchup, park, weather, and lineup information.

#### What "vig" means and why it matters

Here's the part that makes betting different from a coin flip: the sportsbook doesn't offer 50/50 odds on a 50/50 game. If they did, they'd break even over time and have no business. Instead, they build in a small profit margin by making both sides of the bet slightly worse than fair value. This built-in margin is called the **vig** (short for *vigorish*), also sometimes called the **juice** or the **overround**.

Consider a theoretical even matchup. A "fair" price for both sides would be +100 (bet $100, win $100 on either team). But a sportsbook might post it as -110 / -110 instead — meaning you have to risk $110 to win $100 on either side. That extra $10 is the vig. The house collects it regardless of which team wins.

The practical consequence: if you convert both sides of a moneyline into implied probabilities, they don't add up to 100% — they add up to something like 104–107%. That excess above 100% is the vig. A game posted as -150 / +130 implies the two teams have a combined "probability" of about 104%, not 100%. The extra 4% is the sportsbook's edge.

#### Stripping the vig to get a true implied probability

Because the vig inflates the raw implied probabilities, we can't use the raw numbers directly as model features. A team shown at -150 implies a ~60% win probability if you just do the math, but that includes the sportsbook's cut. Strip the vig, and the "true" implied probability is closer to 57–58%.

This adjustment — called **vig-removal** — is done by normalizing the two sides so they sum to exactly 100%. The result is the market's best estimate of each team's actual win probability, without the bookmaker's profit margin baked in. These vig-adjusted implied probabilities are what we feed into the model.

#### Why we use lowvig.ag specifically

Not all sportsbooks charge the same vig. A major retail sportsbook might post a game at -115 / -115, while a sharp market might offer it at -105 / -105. The difference seems small, but it matters: a lower-vig market is a more informative one. When the vig is thinner, the prices have to be more accurate to remain profitable — the bookmaker can't hide as much uncertainty inside the margin.

**lowvig.ag** is a reduced-juice sportsbook that consistently posts among the lowest vigs in North America, typically in the -105 to -107 range rather than the -110 to -115 range common at major retail books. We evaluated coverage and vig levels across all major sportsbooks in our dataset and selected lowvig as the primary source because it gives us the cleanest signal — prices closest to the true market consensus with the least noise introduced by overpricing.

The model features drawn from the lowvig line are:
- **Moneyline price for each team** — the raw price, as posted
- **Totals line** — the over/under number
- **Vig-adjusted implied win probability for each team** — the normalized probability after removing the vig

#### Why market features belong in the model at all

The betting market is a form of crowdsourced forecasting. Sportsbooks and sharp bettors spend significant resources on the same problem we're trying to solve — predicting game outcomes. By the time a line is posted, it has typically already been refined by professional handicappers, statistical models, and large volumes of money from sophisticated bettors who move lines toward accuracy. Using the market's implied probability as a feature means we're giving our model access to a summary of everything the market "knows," without having to replicate all the work that went into it.

In practice, the market is well-calibrated — teams implied at 60% do win roughly 60% of the time. The model's job is to find games where the statistical features suggest the market's probability is meaningfully off, not to ignore the market altogether.

**Important limitation**: betting market features are only available for games from 2020 onward, and odds prices (the actual moneyline and total numbers) are currently only fully populated for 2020–2022, 2024–2026 — the 2023 historical odds backfill was interrupted by API credit exhaustion. For games without market data, the market features are blank and the model falls back to its non-odds features. A `has_odds` flag on every game record controls this switch.

---

## The Master Game Record

All five feature groups are assembled into a single wide table — one row per game, containing everything the model needs to know about that matchup.

Key flags included in every row:

- **`has_full_data`**: both lineups confirmed, both starters have prior pitch history, and the ballpark has a prior-season run factor on file. This flag identifies the ~23,444 games usable for model training.
- **`has_odds`**: betting market features are populated (2021–2025 historical backfill + live 2026 games)

---

## The No-Leakage Guarantee

The single most important rule enforced throughout Phase 2 is that **no feature is allowed to contain any information from the day of the game or later.**

This sounds obvious, but it's easy to violate in subtle ways. For example:

- Rolling stats use data strictly from *before* game day — not including same-day games, even early-afternoon games before a night game
- Platoon splits always use the *prior season*, never the current one (which would still be in progress)
- Park run factors use the *prior season*, not the current year's running totals
- Season standings use the record as of *the previous day*
- Betting odds only use snapshots ingested *before the game's scheduled start time*

Violating any of these would mean the model was, in some sense, trained by peeking at results it was supposed to predict — producing overly optimistic training metrics that would collapse on real predictions.

We completed a formal leakage audit of all five feature tables and verified every rule was correctly enforced. The spot-check was done against a specific LAD vs. HOU game from July 4, 2025 — manually confirming that no feature for that game contained any same-day information.

---

## Additional Feature Engineering

Beyond the base features from Phase 1's data mart, Phase 2 also included a layer of engineered features designed to capture more nuanced matchup signals:

**Momentum / recent trend features:**
For key metrics like team offense wOBA and pitcher xwOBA-against, we computed the gap between the 7-day rolling average and the longer-term baseline (30-day or season-to-date). A team whose 7-day wOBA is significantly above its 30-day wOBA is trending hot going into this game — that difference is now captured explicitly as its own feature.

**Lineup-vs-starter matchup features:**
We combined the batting lineup's handedness composition with the opposing starter's platoon splits to generate an explicit matchup quality score. For example: if a lineup is 75% right-handed and the opposing starter has historically struggled against right-handed batters, that matchup produces a higher expected xwOBA number than the starter's overall stats would suggest on their own.

**Rolling window reliability flags:**
Because rolling stats for teams with fewer than ~15 games played tend to be noisy (especially early in April), we added explicit game-count fields for every rolling window. These tell the model how many games of history actually went into a given rolling stat — so that early-season figures from teams that have played 5 games can be treated with appropriate skepticism.

**Starter expected depth:**
A pitcher's recent average innings per start — a signal of whether a starter is deep into games or getting pulled early. This is relevant because a starter expected to go 5 innings creates a different bullpen demand situation than one expected to go 7.

**Era flags:**
Two fields that capture the structural shifts in run scoring over our training period:
- `game_year`: the calendar year, which captures long-run trends
- `post_2022_rules`: a binary flag for whether the game was played under the 2023+ ruleset (pitch clock, shift ban, larger bases). These rule changes caused a measurable shift in scoring patterns that needs to be accounted for.

---

## What Phase 2 Means for the Rest of the Project

At the end of Phase 2, we had a clean, validated, leakage-free feature store covering 23,444 regular season games from 2016–2025. Every feature in that store represents information that was genuinely available before first pitch was thrown.

The key findings from Phase 2 that shaped Phase 3 and beyond:

**Coverage was better than expected.** Confirmed lineup availability was 100% going back to 2015 — no gaps, no imputation needed for lineups. Park run factors were the binding constraint for the training set start date (requiring 2016+, since 2015 games have no prior-season park factor to look up).

**Most features had strong coverage.** Across 374 feature columns, fewer than 5% of values were blank for the vast majority of groups. The main exceptions were starter platoon splits (11–17% blank for debut pitchers) and the betting market features (100% blank until 2021 historical backfill was added in Phase 1).

**The debut pitcher gap was handled explicitly.** Rather than silently filling in zeros or league averages and hoping the model figures it out, we added a `has_starter_platoon_data` indicator flag. The model training pipeline can treat this as a distinct regime rather than noise.

**The feature store is the starting line for modeling, not the finish.** Phase 3 (exploratory analysis) went through every feature group and measured how much predictive signal it actually carries. Some features that seemed intuitively useful turned out to be weak; others that seemed minor turned out to be among the strongest predictors. The Phase 2 feature store provided the raw material for those findings.

---

*This report covers Phase 2 work completed as of April 23, 2026. For Phase 1 (data foundation) and Phase 3 (exploratory analysis findings), see the corresponding non-technical reports.*
