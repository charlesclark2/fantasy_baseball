# Epic 0: Switching Data Providers Before the Deadline

## What Epic 0 Was About

Every day, the prediction system pulls in live betting odds — the prices that sportsbooks are posting for each game. For the past year, we've been using a service called **The Odds API** as our live data source. In May 2026, that service's subscription was expiring and not being renewed. We had until **June 1, 2026** to switch to a replacement provider — **Parlay API** — without any gap in live data.

Epic 0 was the migration. The requirement was simple in principle: replace one data source with another while keeping every historical record intact and without breaking any downstream reports, models, or prediction logic.

---

## What We Were Replacing and Why

The Odds API had served us well, but a few factors made a migration worthwhile beyond just the subscription expiration:

- Parlay API provides **real per-game start times** (The Odds API only returned a placeholder "7pm" for every game regardless of actual start time — a meaningful gap for any time-sensitive analysis)
- Parlay API has **lower credit costs** per call, making intraday snapshots more economical
- Parlay API was positioning itself as the better long-run partner for what we're building

The hard constraint: **all historical Odds API data had to stay untouched**. We weren't replacing the archive — we were adding a new live source going forward.

---

## What We Built

### A New Raw Data Table

We created a separate database schema (`baseball_data.parlayapi`) for Parlay API data, with four new tables:

- **Live events**: today's scheduled games with bookmaker IDs
- **Live odds**: snapshots of all sportsbook prices for each game
- **Historical matches**: closing-line results for past games
- **Line movement**: opening-to-close price history (more on this below)

Importantly, we did not modify or delete anything in the existing Odds API tables. The historical data from 2021–2025 is fully preserved and still queryable.

### An Ingestion Script

We wrote `parlay_api_ingestion.py` to handle all Parlay API calls. Like its predecessor, it follows an **append-only** pattern — every run adds new rows rather than overwriting old ones. This means we have a timestamped record of every pull, which makes debugging and auditing straightforward.

### Seamless Downstream Integration

All the models and dashboards that consume odds data read from a single unified mart (`mart_odds_outcomes`). We updated that mart to automatically pull from **both** data sources — Odds API for historical games, Parlay API for current games — so every downstream consumer got the new data automatically with no individual changes required.

---

## Key Discoveries Along the Way

The migration surfaced several things that weren't obvious from the documentation.

**The line movement endpoint was a dead end for our use case.** The Parlay API advertises a `/line-movement` endpoint that we expected to use for tracking how moneylines and totals prices shifted throughout the day. When we actually called it, every record came back as a player prop (home run odds, strikeout props, etc.) — zero moneyline or totals data. This was a significant surprise. Our own hourly snapshot approach — capturing odds prices at ~15 windows throughout the day — turns out to be the only viable method for tracking line movement on game bets.

**Doubleheaders were collapsed into a single odds record.** When two teams play twice in a day, sportsbooks post separate odds for each game. The Parlay API was initially returning only one record for both games — making it impossible to tell which odds applied to which game. We flagged this to Parlay API support, and they deployed a fix: each game in a doubleheader now gets a distinct ID and a real start time. We then had to write additional logic to correctly route each game's data to the right record in our system.

**Real game start times are only available from one specific endpoint.** Most Parlay API responses return `7:00 PM` as a placeholder for every game regardless of actual start time. The `/events/canonical` endpoint is the only one that returns accurate per-game start times. We wired that into our daily ingestion and used it to fix a leakage guard in our line movement tracking that had been inadvertently dropping post-7pm snapshots for many games.

**The historical period markets endpoint has no MLB data.** One endpoint we evaluated was supposed to serve detailed historical period-level data (first-half totals, etc.). Every query returned zero results. The likely explanation is that this endpoint was built for basketball and hockey — it simply has no MLB data pipeline behind it.

---

## How the Cutover Went

We ran both data sources in parallel for **16 days** (May 10–25, 2026) before fully cutting over. During that window, we verified that:

- Coverage of game odds was consistent between the two sources
- The `has_odds` flag on every game record was firing correctly
- Downstream reports and the prediction pipeline were reading the right data
- A handful of early coverage gaps traced to pipeline instability during the initial deployment — not systemic Parlay API issues

On May 26, 2026, we disabled the Odds API ingestion steps. The code remains in place (in case credits are ever extended) but is marked `disabled` in the workflow.

**Source date ranges after cutover:**

| Source | Covers |
|---|---|
| The Odds API | 2021 season through May 25, 2026 (historical archive, read-only) |
| Parlay API | May 10, 2026 onward (live source) |

---

## What Epic 0 Means Going Forward

The data pipeline is now on a stable, well-priced provider with better real-time data (actual game start times, player props availability). The historical Odds API archive is preserved in full and continues to power the 2021–2025 backtesting and CLV analysis.

Downstream models and reports see no change — the unified mart abstracts away which source the data came from. The main thing to be aware of going forward: **doubleheader odds coverage requires Parlay API's fixed endpoint**, and **line movement tracking for moneylines and totals remains our own snapshot-based system** — the Parlay API's native line movement endpoint covers only player props.

---

*Epic 0 completed 2026-05-26 (cutover confirmed). Historical Odds API data retained. Parlay API live since 2026-05-10.*
