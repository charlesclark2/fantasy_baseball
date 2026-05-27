# Epic T: Stopping the Silent Destruction of Historical Data

## What Epic T Was About

Every day, about a dozen ingestion scripts run and pull fresh data from various APIs — game schedules, lineups, umpire assignments, weather, batting stats. Before Epic T, eight of those scripts were **overwriting** the previous version of their data on every run. When a new version of the data arrived, the old version was permanently deleted.

This sounds harmless until you realize what it was destroying:

- **Lineup updates throughout the day** — when a starting player was scratched after the original lineup was posted, the old version was gone. You couldn't reconstruct what the lineup looked like at 10 AM vs. what it looked like at 2 PM.
- **Umpire assignments** — if an umpire change happened before game time, only the final version survived. The original assignment was lost.
- **Weather data** — only the most recent forecast remained. The pre-game forecast from the night before, the forecast from two hours before first pitch — all overwritten.
- **Team defensive stats, fielding metrics, catcher framing** — only the latest weekly snapshot survived. Week-over-week progression was gone.

The consequence: if we ever need to reconstruct exactly what the system "knew" at prediction time (for auditing, backtesting, or diagnosing past decisions), we can't — because the historical state no longer exists.

Epic T fixed this by converting every affected script to **append-only** — every run adds new rows instead of overwriting old ones.

---

## The Root Problem: MERGE Instead of INSERT

The technical cause was straightforward: the scripts were using a database operation called `MERGE`, which finds existing matching records and updates them in place. We replaced this with simple `INSERT`, which adds a new row on every run and preserves everything that came before.

Downstream queries that needed "the most recent version" of any record were already written to handle multiple rows — they just select the most recently inserted one. So the change in behavior was zero for anything reading the data; the change was entirely in what got preserved.

After the conversion, a CI (automated testing) guard was added to block any future script from accidentally reintroducing the MERGE pattern. Any pull request that adds a MERGE to an ingestion script fails the automated check.

---

## The Stories Within Epic T

### T.1 — Game Schedules and Lineups

This was the most urgent. The schedule/lineup table is the source of truth for who's starting and what the final score was. Every re-ingestion of the current month was silently overwriting all lineup updates made since the start of the month.

After conversion: every lineup state that arrives — 10 AM confirmed lineup, 1 PM scratched player, 7 PM final verified lineup — now gets its own timestamped row.

### T.2 — Weather Data

Weather was converted to append-only, and we also extended what gets captured. Previously, we only stored a single pre-game forecast for each game. Now we capture:

| Type | When | Why |
|---|---|---|
| Pre-game forecast | The night before or morning of | Original prediction baseline |
| Intraday forecast | 6h, 3h, 1h before first pitch | Closer-to-truth forecast as game approaches |
| Observed at first pitch | T+0 to T+1 hour after start | What the weather actually was when the game began |
| Observed post-game | Day after | Full observed conditions through the game |

The difference between a forecast from the night before and actual observed conditions at first pitch can be several degrees, significant wind shifts, or unexpected rain. Capturing the observed weather gives the run environment model a more accurate picture of what actually drove scoring.

**Coverage results after backfill:**
- 96.4% of 2024 outdoor games have observed-at-first-pitch weather
- 96.5% of 2025 outdoor games
- 97.8% of 2026 outdoor games (live, no backfill needed)

### T.3 — Public Betting Percentages

The Action Network betting percentage data (what fraction of bets are on each side) was also running on a MERGE pattern. We converted it to append-only.

One discovery during this investigation: **Action Network's API doesn't serve historical betting data before 2024.** Pre-2024 betting percentage data is simply not available and never will be. Any analysis using public betting % data should be scoped to the 2024 season forward.

### T.4 — Umpires, Fielding Stats, and Venues

Several lower-frequency data sources were also converted:

- **Umpires**: converted to append-only; backfill attempted but the Stats API doesn't serve officials for completed historical games. We recovered what we could via umpscorecards.com (98.4% coverage) and documented the permanent gaps.
- **Catcher framing and OAA**: converted to append-only. OAA (outs above average, a fielding metric) was overwriting season-to-date weekly snapshots — intra-season progression is now preserved going forward, though historical progression before the conversion is gone.
- **Venues (ballpark data)**: trivial conversion — venue dimensions rarely change, but the append-only pattern keeps things consistent.

---

## Why This Matters

Epic T is infrastructure work — it doesn't directly improve any model's accuracy today. What it enables:

**Reconstruction of past state.** When we eventually ask "what did the system predict for a specific game, and what data was it based on?", the answer will now be fully reconstructable. Every piece of input data is preserved with a timestamp. Before Epic T, this was impossible for the most important data sources.

**Better weather features for future sub-models.** The run environment model and weather-sensitive features can now use observed conditions rather than just pre-game forecasts. This is particularly valuable for afternoon games that were forecast under one set of conditions but played under another.

**Protection against future accidents.** The CI guard means the append-only pattern is now enforced automatically. Any developer who accidentally writes a MERGE to an ingestion script will see their pull request fail before the code ever gets anywhere near production.

---

*Epic T completed 2026-05-12. All append-only conversions shipped. Post-merge backfills (weather observed, umpire assignments) completed. T.2.D intraday timing verified 2026-05-26.*
