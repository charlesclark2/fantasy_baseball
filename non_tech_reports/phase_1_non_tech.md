# Phase 1: Building the Foundation — What We Did and What We Found

## What Phase 1 Was About

Before we could build any prediction models, we needed to answer a simple question: **what data do we actually have, and can we trust it?**

Phase 1 was about building the data infrastructure — the organized, cleaned, and well-structured database that everything else will sit on top of. Think of it like setting up a scouting department before you start making roster decisions. You need your scouts to be filing consistent, reliable reports before you can draw meaningful conclusions from them.

---

## Where the Data Comes From

We're pulling from three main sources:

### 1. Baseball Savant (Statcast)
This is the backbone of the project. Since 2015, Statcast has tracked every single pitch thrown in Major League Baseball — not just outcomes, but the physics behind each pitch and batted ball. Our database contains **pitch-level data from April 2015 through the present day**, covering:

- Every pitch: type, velocity, spin rate, movement, release extension
- Every plate appearance result: hit, walk, strikeout, etc.
- Every batted ball: exit velocity, launch angle, distance, expected stats (xBA, xwOBA)
- Game state at the time of every pitch: count, base/out situation, score

Starting in mid-2023, Statcast also began tracking **bat metrics** — bat speed, swing length, attack angle — using Hawk-Eye sensors at every ballpark. That layer of data is newer and only available for swing events, but it's in there.

### 2. MLB Stats API
This gives us the game-level and roster information that Statcast doesn't provide on its own:

- Full game schedules and results going back to 2015
- **Confirmed pre-game batting lineups** — who is actually batting where, before first pitch
- Ballpark details: dimensions, surface type, roof type, elevation, GPS coordinates

The lineup data was a critical audit item for Phase 1. We verified that confirmed lineups are available for **100% of regular season games from 2015 through 2026**. This is a significant advantage — it means our model will have the actual game-day lineup, not a guess.

### 3. The Odds API
We added betting market data, pulling moneyline and totals lines from multiple bookmakers. Live ingestion started in April 2026, and we completed a **historical event backfill going back to the 2020 season** (~8,100 matched games across 2020–2025). This gives us the market's implied probabilities as a feature and as a benchmark to beat. Note: full odds prices (not just event linkage) are only available for a partial 2023 backfill and live 2026 ingestion due to API credit constraints.

---

## What We Built

All of this raw data gets organized into what we're calling a **data mart** — essentially a set of purpose-built summary tables that answer specific questions cleanly and efficiently.

Here are some of the key tables we built, in plain terms:

### Player Performance
- **Rolling stats for batters** (7-day, 14-day, 30-day, and season-to-date): batting average, wOBA, strikeout rate, walk rate, hard-hit percentage, barrel rate
- **Rolling stats for pitchers** (same windows): strikeout rate, walk rate, xwOBA against, hard-hit percentage, fastball velocity trend
- **Platoon splits by season**: how each batter or pitcher performs against left-handed vs. right-handed opponents

### Team-Level Context
- **Rolling team offense**: runs scored, wOBA, strikeout and walk rates, hard-hit and barrel rates
- **Rolling team pitching**: runs allowed, quality of contact allowed
- **Bullpen workload**: how hard the bullpen has been used over the past 1, 3, and 7 days (pitches thrown, relievers used)
- **Bullpen effectiveness**: how the bullpen has actually performed over the past 14 and 30 days (not just how much they've thrown, but how well)
- **Home/away splits**: separate performance tables for teams at home vs. on the road
- **Schedule fatigue**: days of rest, games played in the last 7 and 14 days, home/away streak length, and whether a team traveled across time zones

### Game and Park Context
- **Game results**: final scores, run differentials, extra innings flags, venue info
- **Park run factors**: how many runs per game are typically scored at each ballpark, calculated both for a single season and as a three-year rolling average
- **Head-to-head franchise history**: all-time and season records between every pair of teams

### Betting Market
- **Betting odds history**: full bookmaker odds snapshots for every tracked game, including moneyline and totals markets

---

## Data Quality: What We Found and Fixed

One of the main jobs in Phase 1 was running automated tests on all of this data and cleaning up issues before they contaminate any modeling. Here's a plain-English summary of the notable things we found and fixed:

**Legitimate edge cases that looked like errors:**
- A handful of pitches showed a count of 4 balls — these are real, usually from a midscount reset after an illegal pitch or similar umpire ruling. We acknowledged them rather than deleting them.
- ~400 pitches had release speeds below 40 mph. These are Eephus pitches — rare, but real. We widened our acceptable range rather than filtering them out.

**Actual errors we fixed:**
- A calculation bug in how we computed innings pitched caused fractional IP to round incorrectly (e.g., 6.2 IP showing as 6.67 instead of 6.2). Fixed.
- When the MLB Stats API returns data near month boundaries (e.g., a game on March 31st might appear in both the March and April schedule pulls), we were getting duplicate lineup records. Fixed with a dedup rule that keeps the most recent version.
- Games that were postponed and later rescheduled appeared in the schedule twice. Fixed by always preferring the final, scored record over a postponed one.
- Some batted ball tracking flags (like "was this a hard-hit ball?") were showing up as blank instead of No for sac bunts and some early Statcast seasons. Fixed by treating blanks as No.
- Similarly, fielding alignment data has gaps in early Statcast years — about 70,000 pitches across all seasons simply have no alignment record in the source data. We can't fix this (the sensor data doesn't exist), but we documented it clearly.

**Odds data discovery:**
- We found that our historical odds matched **68–79% of regular season games** from 2020–2025. The Odds API's historical data goes back to the 2020 season (the COVID year), where coverage was 67.8%; from 2021 onward it ranges from 72–76%, climbing to 78–79% in 2026 with live ingestion. The gaps are from games The Odds API simply didn't cover — not a bug. We documented the per-season match rates and added a flag to every game record indicating whether odds are available.

---

## Key Decisions Made in Phase 1

**We're using confirmed lineups, not projected ones.** The MLB Stats API gives us the actual lineup card as filed before first pitch. This is better than using projected lineups from external sites, and we confirmed 100% availability going back to 2015.

**We're filtering to regular season games only.** Spring training, playoffs, All-Star games, and Wild Card games are excluded from all rolling stats and model training. Postseason baseball is a different animal — smaller samples, roster manipulation, different pitching usage — so we're not mixing it with the regular season signal.

**Rolling stats are year-isolated.** A pitcher's November ERA does not bleed into April of the following season. We enforce this rule explicitly so that offseason transactions don't create a fake statistical connection between consecutive years.

**No "future" data is allowed in any feature.** Every rolling stat lookup and lineup reference uses data from strictly before game day. This is called the no-leakage rule — it prevents the model from accidentally "knowing" what happened in the game it's trying to predict. We did a formal audit of every feature table and verified this rule is enforced.

---

## The Training Dataset in Numbers

After Phase 1, our clean, validated training dataset covers:

| Season | Games Available |
|---|---|
| 2015 | 0 (no prior-season park factor available — required for full feature set) |
| 2016–2019 | ~9,268 |
| 2020 | 801 (COVID season — kept for reference, but excluded from model training) |
| 2021–2025 | ~11,665 |
| **Total (clean training set)** | **~23,444 regular season games** |

This is the subset where both lineups are confirmed, both starters have prior pitch history, and the ballpark has a prior-season run factor on file.

---

## What Phase 1 Means for the Rest of the Project

Phase 1 established that **the data is clean, the coverage is strong, and the foundation is trustworthy.** That's the prerequisite for everything that follows.

The most important things Phase 1 confirmed:

1. **Lineup data is not a problem.** 100% confirmed pre-game lineups for every regular season since 2015. No imputation needed.
2. **Park and ballpark context is well-represented.** Physical dimensions, surface, roof, elevation, and historical run factors are all available for every major league ballpark.
3. **The odds data is usable, but historically limited.** We have betting market event data going back to the 2020 season (67.8% coverage) and improving through 2021–2025 (72–76% coverage). Pre-2020 games won't have odds features. Full historical odds prices (not just event linkage) are only available for a partial 2023 backfill and live 2026 ingestion — completing that backfill is a future task.
4. **The 2020 COVID season is structurally different enough to exclude from training.** A 60-game season played in bubbles with universal DH and no fans is not representative of a normal season.
5. **Bat tracking metrics are available but limited.** The Hawk-Eye bat sensor data (bat speed, swing length, attack angle) only goes back to mid-2023 and only covers swing events. It's interesting data, but we're not built around it for Phase 4 modeling.

Phase 2 took this foundation and assembled it into the actual feature vectors the models will use. Phase 3 then analyzed whether those features actually carry predictive signal — and found they do.

---

*This report covers Phase 1 work completed as of April 2026. For Phase 2 (feature assembly) and Phase 3 (exploratory analysis) findings, see the corresponding non-technical reports.*
