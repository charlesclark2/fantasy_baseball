# MLB Quantitative Intelligence — Implementation Guide

Version: Draft 0.4
Status: In Progress — Epic 0 bridge update complete (0.8); line movement staging (0.9) next
Companion to: `refined_architecture_proposal.md`

---

# Overview

This guide breaks the architecture proposal into epics and tasks suitable for sprint planning.

Each epic maps to a meaningful deliverable. Tasks within each epic are sequenced where dependencies exist. Epics themselves have sequencing dependencies documented in the **Sequencing** section at the end.

---

# Sequencing Summary

```
Epic 0   (Parlay API Migration)        — Immediate. Hard deadline: 2026-06-01.
  Story order: 0.1✅ → 0.2✅ → 0.3✅ → 0.4✅ → 0.5✅ → 0.6✅ → 0.8✅ (bridge) → 0.9✅ (line movement) → 0.10✅ (canonical events) → 0.7 (cutover)
Epic 0.5 (Dagster Orchestration)       — After Epic 0 cutover passes; before Epic 1 ships to production.
Epic 1   (Market-Blind Retrains)       — Immediate. Unblocked now (run in parallel with Epic 0).
Epic 2   (Sub-Model Infrastructure)    — Start in parallel with Epic 1.
Epic 3   (Run Environment Model)       — Can start after Epic 2.
Epic 4   (Offensive Quality Model)     — Can start after Epic 2.
Epic 5   (Starter Suppression Model)   — Can start after Epic 2.
Epic 6   (Bullpen State Model)         — Can start after Epic 2.
Epic 7   (Archetype Clustering)        — Prerequisite for Epic 8.
Epic 8   (Matchup Model)               — Requires Epic 7.
Epic 9   (Signal Integration & Ablation) — Requires Epics 3–6 to have at least one signal.
Epic 10  (Totals Distribution Model)   — Requires Epics 3–6 signals; builds on Epic 9.
Epic 11  (H2H Model Retrain w/ Signals) — Requires Epic 1 complete; builds on Epic 9.
Epic 12  (CLV Meta-Model)              — Gated on 500+ live CLV games.
Epic 13  (Temporal Data Platform)      — Long-horizon infrastructure; begin Phase 10.
```

---

# Epic 0 — Parlay API Migration (Phase 0)

**Goal:** Replace The Odds API as the primary live odds data source with Parlay API before June 1, 2026. Retain all historical Odds API data in place — no deletions or schema changes to existing tables.

**Hard deadline:** 2026-06-01. Odds API credits expire 2026-05-23; cease live ingestion by then but keep the pipeline runnable in case credits are extended.

**Docs:** https://parlay-api.com/docs

---

### 0.1 — Parlay API endpoint mapping ✅

**Goal:** Map every Odds API endpoint currently in use to its Parlay API equivalent. Identify any gaps or new capabilities available.

**Output:** `quant_sports_intel_models/parlay_api_endpoint_mapping.md`

Tasks:
- [x] Document current Odds API endpoint usage: `events` and `odds` run daily via GitHub Actions; `historical-events` and `historical-odds` are manual-only backfill subcommands
- [x] Review Parlay API docs and map each endpoint to its equivalent — URL-surface compatible; base URL change only for core live endpoints
- [x] Document Parlay API capabilities not in Odds API: `/consensus`, `/ev`, `/props`, `/arbitrage`, `/live` — see Section 4 of mapping doc
- [x] Document gaps: historical endpoint path unverified (assumed same); starter-key dual-key pattern not applicable; `commenceTimeFrom` params unverified on historical

**Key findings (updated after live endpoint testing 2026-05-09):**
- Migration scope is minimal: change base URL, swap API key env var, remove dual-key fallback, update `source_system` metadata — existing Snowflake write logic is unchanged
- **Tier selected: Business plan** (1,000,000 credits/month) — sufficient for daily automated use, historical backfills, and line-movement daily ingestion (~2,250 credits/month total with line-movement enabled)
- Live endpoints (`/events`, `/odds`) verified compatible — identical response schema; adds `canonical_event_id` field
- Historical `/events` path does not exist — replaced by `/matches` endpoint with a different flat schema (scores, results, `has_odds` flag)
- Historical `/odds` verified compatible — same bookmakers/markets structure; requires `oddsFormat=american`
- Credit headers (`x-requests-used`, `x-requests-remaining`) are not present in Parlay API responses — use call-count logging in ingestion script instead
- **`/line-movement` endpoint verified** — provides full opening-to-close price history, but **player props only** (zero h2h/totals/spreads confirmed via live testing 2026-05-10); original assessment as "highest-value new capability for CLV" is revised — see Deep Endpoint Evaluation section
- `/ev` and `/consensus` worth evaluating post-migration as additional CLV inputs
- See `quant_sports_intel_models/parlay_api_endpoint_mapping.md` for full details

**Pipeline snapshot awareness note:**
Any pipeline consuming `parlayapi.mlb_line_movement_raw` must account for the nested `snapshots[]` array in `raw_json`. Each top-level record represents one (event × book × market) combination; `snapshots` is an arbitrary-length array of timestamped price changes. Decide before building any staging model whether to explode snapshots for time-series features or summarize to opening/closing price only. Do not assume a flat row-per-event schema.

---

### Parlay API — Deep Endpoint Evaluation (2026-05-10)

Full hands-on evaluation of all endpoints tested via direct API calls using the Business-tier key. This section is the authoritative reference for what the API actually delivers vs. what the docs describe. Updated findings here supersede any earlier assumptions in Story 0.1 or the endpoint mapping doc.

---

#### Temporal model (applies to all live endpoints)

- `commence_time` in `/events` and `/odds` responses is always `19:00:00Z` — a per-date slate placeholder, not a real game time. It is useful only as a date bucket.
- `bookmaker_last_update` (on the bookmaker object) is the authoritative signal for when a line actually moved. Use this — not `ingestion_ts` and not `commence_time` — to reason about the age of a price at capture time.
- `market_last_update` (on the market object) is more granular — a book may update their h2h line without touching totals.
- **Real per-game start times are only available from `/events/canonical`** (see below). The live `/events` and `/odds` endpoints do not carry them.
- `stg_parlayapi_odds` schema.yml has been updated to reflect these semantics on `ingestion_ts`, `bookmaker_last_update`, and `market_last_update`.

---

#### `/v1/sports/baseball_mlb/events/canonical`

**Status: Works. High-value ancillary endpoint.**

Returns one record per upcoming game with:
- `canonical_event_id` — a stable 16-char hex ID that is consistent across all bookmaker sources (e.g., `4953d9e905ba1241`). Already ingested into `mlb_events_raw.canonical_event_id`.
- `commence_time` — **actual per-game scheduled start time** (e.g., `2026-05-10T20:10Z`), not a placeholder. This is the only Parlay API endpoint that returns real start times.
- `sources` — a dictionary mapping each bookmaker key to their raw team name strings. Useful for normalization auditing; confirms that most major books already use canonical team names (no translation needed beyond our existing "Oakland Athletics" → "Athletics" case).
- `source_count` — number of books covering this game.

**Observations (24 events on 2026-05-10):**
- Some events have an empty `commence_time` — appears on games without a confirmed start time (e.g., second-game doubleheader slots, or late-add games).
- Includes events for upcoming days (2026-05-11, 2026-05-12) in addition to today's games.
- Auth requires `apiKey` query param — the `X-API-Key` header is **not** accepted on this endpoint (unlike the live odds endpoint which accepts both).

**Action item:** Evaluate whether to call this endpoint during daily ingestion and store `commence_time` in `mlb_events_raw`. It is the only way to get real game start times without Stats API.

---

#### `/v1/sports/baseball_mlb/line-movement`

**Status: Works, but limited scope — player props only.**

Tested with today's ARI vs NYM event ID (`891b1925afceb099a2d27776e0aa1b97`). Response: 155 records. **All 155 are `player_*` market keys (player props).** Zero h2h, totals, or spreads.

This contradicts the endpoint's documentation positioning as a general line-movement feed. In practice:
- **Player props**: full opening-to-close snapshot history available ✓
- **H2H (moneyline)**: not present ✗
- **Totals**: not present ✗
- **F5 / first half**: not present ✗

**Impact on Epic 12 (CLV meta-model):** Story 0.1 identified `/line-movement` as "highest-value new capability" for CLV tracking. That assessment must be revised. For h2h and totals CLV, the Parlay API `/line-movement` endpoint contributes nothing. Our own snapshot-based tracking via `odds_snapshot.yml` (~15 snapshots/game-day) remains the **only viable path** for h2h/totals line movement. The line-movement endpoint is valuable only for player-prop CLV if that use case is added in future.

**`mlb_events_raw` design note:** The table is append-only (not overwritten daily). The `resolve_event_ids` function uses a 26-hour rolling window to find event IDs for the line-movement call — but old rows persist indefinitely. No pre-2026-05-10 Parlay API event IDs exist because ingestion only started that date; the historical matches endpoint does not expose event IDs.

---

#### `/v1/historical/sports/baseball_mlb/period_markets`

**Status: No data. Not usable.**

Documented as "Durable per-distinct-state archive of period market line movement" at 5 credits/call. Tested with every parameter combination:
- With/without `matchId` (using both Parlay event IDs and canonical event IDs)
- With/without `dateFrom`/`dateTo` (tested 2025-09-01 through 2026-05-10)
- All period values: `FT`, `F5`, `1H`, `2H`, `all`
- With no filters at all

**Every call returns `count: 0, results: []`.** No error — the endpoint is accessible and our Business tier has no restrictions — but it has zero MLB data.

Valid period keys confirmed from API error response: `1H`, `2H`, `F5`, `F7`, `FT`, `OT`, `P1`, `P2`, `P3`, `Q1`, `Q2`, `Q3`, `Q4`. The `match_id` field referenced in the docs does not correspond to any ID exposed by other Parlay API endpoints (`event_id`, `canonical_event_id`, and historical `match` records all return zero results when used as `matchId`).

**Likely explanation:** The endpoint is designed for sports with timed periods (basketball, hockey, football). MLB has no populated data pipeline for this endpoint. Do not plan any architecture around it.

---

#### `/v1/historical/sports/baseball_mlb/closing-odds`

**Status: Works, but narrow coverage.**

Returns Pinnacle closing ML lines. Tested 2026-05-07 through 2026-05-09:
- **Bookmakers:** Pinnacle only
- **Market:** H2H moneyline only — no totals, no F5, no spreads
- **Coverage:** ~3-4 games/day (not full slate — roughly 30-40% of games)
- **Scores:** `result` is empty, `home_score`/`away_score` are null even for completed games (no game result data)
- **Schema:** `game_date`, `home_team`, `away_team`, `bookmaker`, `home_odds`, `away_odds`, `draw_odds` (always null for MLB)

This is effectively the same data as `source=pinnacle` in the historical matches endpoint, just in a cleaner flat schema. The spotty per-game coverage makes it unreliable as a standalone closing-line source. Pinnacle closing lines from the historical matches endpoint (`mlb_matches_raw`) are the better path since that endpoint covers more games per date.

---

#### `/v1/historical/sports/baseball_mlb/matches`

**Status: Works. Primary historical odds source.**

The correct historical equivalent of the Odds API historical endpoints. Key characteristics:
- Returns one record per (game, source) — e.g., one row for `bet365_an`, one for `draftkings_an`, one for `pinnacle`, one for `pinnacle_open`, etc.
- `pinnacle_open` = Pinnacle's opening line; `pinnacle` = Pinnacle's closing line. The pair together gives opening vs. closing movement for Pinnacle.
- ML odds are nested inside an `odds` object: `odds.home_ml`, `odds.away_ml` — not top-level fields.
- **No `event_id` field** in any record. Cannot use to look up Parlay API event IDs for historical games.
- Coverage spotty for some sources/dates; Pinnacle coverage is most consistent.

---

#### Summary table

| Endpoint | Status | What it delivers | Gaps |
|---|---|---|---|
| `/events` | ✓ Works | Today's event IDs, bookmakers, markets | `commence_time` is a placeholder (19:00:00Z) |
| `/odds` | ✓ Works | Live snapshot of all book ML/totals/props | `commence_time` placeholder; no real start times |
| `/events/canonical` | ✓ Works | Real game start times; stable cross-source ID; per-book team name map | Auth requires `apiKey` param (not header) |
| `/historical/matches` | ✓ Works | Closing ML by source per game; Pinnacle open/close pair | ML only; no totals/F5; no event_id; spotty coverage |
| `/historical/closing-odds` | ✓ Works | Pinnacle closing ML | Pinnacle only; ML only; ~3-4 games/day; no scores |
| `/line-movement` | ⚠ Partial | Full snapshot history for player props | Zero h2h / totals / F5 — player props only |
| `/historical/period_markets` | ✗ No data | Nothing — 0 results for all param combinations | No MLB data pipeline; `match_id` not discoverable |

---

### 0.2 — Parlay API raw table DDL ✅

**Goal:** Create new Snowflake raw tables for Parlay API data. Do NOT modify existing `baseball_data.oddsapi` tables — keep them append-only and intact.

**Output:** `scripts/ddl/parlayapi_raw_tables.sql`

Tasks:
- [x] Create new schema: `baseball_data.parlayapi` — provisioned manually 2026-05-09
- [x] Design DDL for raw events table: same observability columns as `mlb_events_raw`; adds `canonical_event_id` and `call_sequence`; `x_requests_used/remaining` retained as NULL-only columns for schema symmetry
- [x] Design DDL for raw odds table: same pattern as `mlb_odds_raw`; same adjustments as events table
- [x] Design DDL for `mlb_matches_raw`: new table for `/historical/matches` endpoint (flat schema with scores, results, `has_odds`)
- [x] Design DDL for `mlb_line_movement_raw`: new table for `/line-movement` endpoint; stores full snapshots array as VARIANT; includes snapshot awareness comment
- [x] Write DDL file at `scripts/ddl/parlayapi_raw_tables.sql`
- [x] Provision tables in Snowflake — all four tables created 2026-05-09

---

### 0.3 — Parlay API ingestion script ✅

**Goal:** Build `scripts/parlay_api_ingestion.py` mirroring the structure of `odds_api_ingestion.py`.

**Output:** `scripts/parlay_api_ingestion.py`

Tasks:
- [x] Support `events` and `odds` subcommands (live daily ingestion)
- [x] Support `historical-odds` subcommand — iterates calendar days with `date=YYYY-MM-DD` param; idempotent by (game_date, market); `--force` to re-fetch
- [x] Support `historical-matches` subcommand — one row per date, full response as VARIANT; includes scores, results, `has_odds` flag
- [x] Support `line-movement` subcommand — one call per event_id; auto-resolves event IDs from mlb_events_raw or accepts `--event-ids`; stores full snapshots array as VARIANT
- [x] Preserve same append-only pattern: every run inserts new rows with shared `load_id`
- [x] Use same Snowflake auth pattern (private key preferred, password fallback)
- [x] Six env var overrides for target tables (PARLAY_TARGET_DATABASE, PARLAY_TARGET_SCHEMA, PARLAY_EVENTS_TABLE, PARLAY_ODDS_TABLE, PARLAY_MATCHES_TABLE, PARLAY_LINE_MOVEMENT_TABLE)
- [x] Single-key auth via `X-API-Key` header; no credit headers — call_sequence counter logged instead
- [x] Historical backfill defaults to 90 days prior to run date (Business plan data limit)
- [x] **90-day historical backfill complete** — `historical-odds` and `historical-matches` executed for 2026-02-08 → 2026-05-09
- [x] **Tested against live tables** — deployed to prod via GitHub Actions 2026-05-10; `events` and `odds` running daily

**Post-backfill data quality notes (2026-05-10):**
- `mlb_matches_raw`: 25 rows for dates 2026-02-09 to 2026-03-05 contained stale 1000-record arrays from an earlier broken run; the idempotency check protected them from being overwritten. Deleted via:
  ```sql
  DELETE FROM baseball_data.parlayapi.mlb_matches_raw
  WHERE game_date BETWEEN '2026-02-09' AND '2026-03-05';
  ```
  These are spring training dates — data not needed for models. No re-fetch required.
- `mlb_events_raw`: table was accidentally truncated after backfill. Recovered via Snowflake Time Travel at `AT (offset => -3600)` — 1 row recovered (live events ingested 2026-05-10T05:11:51; 15 events). Table is append-only from live daily runs only; no historical events endpoint exists in Parlay API.
- `mlb_odds_raw`: coverage confirmed 2026-02-08 → 2026-05-09, 90 rows, correct record counts (40–105 per day for regular-season dates; pre-season dates have lower counts).

---

### 0.4 — dbt staging model for Parlay API odds ✅

**Goal:** Add a `stg_parlayapi_odds` staging model that produces the same output schema as `stg_oddsapi_odds`, enabling all downstream dbt models and mart joins to consume both sources without changes.

Tasks:
- [x] Create `dbt/models/staging/stg_parlayapi_odds.sql` — three-level lateral flatten: bookmakers[] → markets[] → outcomes[]
- [x] Match column names and types to `stg_oddsapi_odds` exactly
- [x] Add `source_system = 'parlay_api'` discriminator column
- [x] Add `canonical_event_id` column (Parlay API cross-source stable ID; null for historical rows)
- [x] Add `game_date` convenience column (`commence_time::date`)
- [x] Add `doubleheader_ambiguous` boolean flag (left join to `stg_statsapi_games` on game_date + team names; true when `double_header IN ('Y','S')`)
- [x] Add source entry (`parlayapi`) to `dbt/models/sources.yml` with table descriptions and not_null tests
- [x] Add full column documentation to `dbt/models/staging/schema.yml` — all 19 output columns documented with descriptions and tests
- [x] All 15 schema tests passing — `dbtf build --select stg_parlayapi_odds` green

**Implementation notes:**
- No deduplication CTE needed — Parlay API has no dual-region overlap (unlike Odds API's us/us2 pattern)
- `outcome_price_decimal` CASE expression includes a `when outcome_price_american = 0 then null` guard to prevent division by zero on malformed data
- **Snowflake VARIANT null bug fixed:** Parlay API sends explicit JSON `null` for some away-side prices (confirmed: Caesars, Bovada, others). In Snowflake, JSON null in a VARIANT field is a VARIANT null — it passes `IS NOT NULL` but produces SQL NULL on `::integer` cast. The WHERE filter was changed from `where out.value:price is not null` to `where out.value:price::integer is not null` to catch both missing keys and explicit JSON nulls.

**Blocking investigation — doubleheader disambiguation (RESOLVED 2026-05-10, support ticket open):**

**Finding: Parlay API collapses doubleheaders into a single odds line.** Both the `/events` endpoint and `/historical/odds` endpoint return only one event per (date, home_team, away_team) matchup regardless of how many games were played. The second game of a doubleheader does not appear as a separate event ID in any response.

Confirmed against three known 2026 doubleheader dates (sourced from `baseball_data.betting.stg_statsapi_games` where `double_header IN ('Y','S')`):
- 2026-04-05: Cleveland Guardians vs Chicago Cubs — StatsAPI: 2 games; Parlay API: 1 event (`id=607c7a2cc9eb6711`, `commence_time=19:00:00Z`)
- 2026-04-26: New York Mets vs Colorado Rockies — StatsAPI: 2 games; Parlay API: 1 event
- 2026-04-30: Baltimore Orioles vs Houston Astros — StatsAPI: 2 games; Parlay API: 1 event

Additional findings from live API testing 2026-05-10:
- `commence_time` is a slate placeholder (`19:00:00Z`) for every game on every date — not the actual scheduled start time. This applies to both `/events`, `/odds`, and `/historical/odds`.
- `dateFormat=unix` has no effect on historical endpoints — always returns ISO strings.
- `canonical_event_id` is `null` in historical odds responses; only populated in live `/events` responses.

**Impact on staging model design:**
- `(date, home_team, away_team)` cannot be a reliable join key to `stg_statsapi_games` — on doubleheader days it will produce a 1:2 fan-out (one Parlay odds row joining to two StatsAPI game rows).
- There is no field in the Parlay API response that distinguishes game 1 from game 2 of a doubleheader.
- Support ticket filed with Parlay API requesting: (1) separate event IDs for each game of a doubleheader, and (2) accurate per-game `commence_time` values. **Do not finalize staging model join key until ticket is resolved.**

**Interim approach until ticket is resolved:** In `stg_parlayapi_odds`, flag any (date, home_team, away_team) combination where `stg_statsapi_games` shows `double_header IN ('Y','S')` with a `doubleheader_ambiguous = true` column. Downstream mart joins should exclude or caveat these rows until the API issue is fixed.

---

### 0.5 — Update downstream mart joins to union both sources ✅

**Goal:** Any mart that joins `stg_oddsapi_odds` should be able to consume `stg_parlayapi_odds` for dates after the cutover without breaking historical data.

Tasks:
- [x] Audit which dbt marts currently join `stg_oddsapi_odds` — single choke point is `mart_odds_outcomes`; all downstream models (`mart_odds_consensus`, `mart_bookmaker_disagreement` live path, `mart_odds_line_movement`, `mart_closing_line_value`, `feature_pregame_odds_features`) flow through it
- [x] Decided on single change point: UNION ALL both staging models inside `mart_odds_outcomes` rather than a new intermediate — all downstream models inherit the union automatically with zero changes to those files
- [x] Updated `mart_odds_outcomes.sql` — UNION ALL `stg_oddsapi_odds` and `stg_parlayapi_odds`; added `source_system` discriminator ('odds_api' | 'parlay_api') and `doubleheader_ambiguous` column to output schema; Odds API side gets `'odds_api'::varchar` and `false::boolean` literals for the new columns
- [x] Updated `mart/schema.yml` — rewrote `mart_odds_outcomes` description and all column docs to reflect unified source; added `source_system` not_null + accepted_values tests; updated `doubleheader_ambiguous`, `commence_time`, `bookmaker_key`, and `outcome_price_decimal` descriptions with Parlay-specific caveats
- [x] All 22 `mart_odds_outcomes` tests passing; all 17 downstream model tests passing
- [x] Verified in Snowflake: 733,731 Odds API rows + 11,509 Parlay API rows; 60 doubleheader-ambiguous Parlay rows correctly flagged

**Implementation notes:**
- `mart_bookmaker_disagreement` has a separate historical path (2021–2025) that reads `baseball_data.oddsapi.mlb_odds_raw` directly — no change needed there
- During the parallel overlap period, Parlay API rows in `mart_odds_outcomes` are effectively orphaned at the mart level because `mart_game_odds_bridge` only maps Odds API event_ids to `game_pk`. The bridge fix is Story 0.8.
- After Odds API cutover, the live path in `mart_bookmaker_disagreement`, `mart_odds_line_movement`, and `feature_pregame_odds_features` will stop receiving data for new games until the bridge is updated (Story 0.8 blocks cutover validation).

---

### 0.6 — Update GitHub Actions workflow for daily ingestion ✅

**Goal:** Wire the new Parlay API ingestion script into the daily GitHub Actions workflow that currently runs `odds_api_ingestion.py`.

Tasks:
- [x] Added two steps to `.github/workflows/daily_ingestion.yml`: `parlay_api_ingestion.py events` and `parlay_api_ingestion.py odds` — run in parallel with Odds API steps during overlap period
- [x] Added comment on Odds API steps: "DISABLE after 2026-05-23 (credits expire). Do not delete..."
- [x] Added `PARLAY_API_KEY` secret to GitHub Actions repository secrets — deployed 2026-05-10
- [ ] Verify daily dbt refresh still completes correctly after the workflow change — will be confirmed as part of 0.7 parallel ingestion monitoring

---

### 0.8 — Update mart_game_odds_bridge to include Parlay API event_ids ✅

**Goal:** `mart_game_odds_bridge` currently maps `game_pk → event_id` using only Odds API events. After the cutover, new 2026 games will have no Odds API event_id and `has_odds` will be false for all of them, breaking the entire live-path feature pipeline. Add Parlay API event_ids as a second source and prioritize them in the coalesced `event_id` column.

**Blocks:** Story 0.7 (cutover validation). Must be complete before Odds API ingestion is disabled.

Tasks:
- [x] Added `odds_api_event_id` and `parlay_api_event_id` as separate output columns — preserves both source identifiers for auditing and avoids information loss
- [x] Sourced Parlay API events directly from `stg_parlayapi_odds` — no separate staging model needed; used `ROW_NUMBER() OVER (PARTITION BY game_date, home_team, away_team ORDER BY ingestion_ts DESC) = 1` to get one canonical Parlay event_id per matchup per date
- [x] Applied same team name normalization to Parlay API events as exists for Odds API events ("Cleveland Indians" → "Cleveland Guardians", "Oakland Athletics" → "Athletics") — applied defensively on both sides
- [x] Coalesced `event_id` column = `COALESCE(parlay_api_event_id, odds_api_event_id)` — Parlay API takes priority when both exist (overlap period), falls back to Odds API for historical games (2021–2025)
- [x] Updated `has_odds` = `COALESCE(parlay_api_event_id, odds_api_event_id) IS NOT NULL`
- [x] Updated `mart/schema.yml` — rewrote bridge description and added docs for `odds_api_event_id`, `parlay_api_event_id`, and updated `event_id` and `has_odds` descriptions
- [x] All 10 bridge tests passing; all 28 downstream model tests passing (mart_bookmaker_disagreement, mart_odds_line_movement, mart_closing_line_value, feature_pregame_odds_features)
- [x] Validated in Snowflake: 2026 regular season — 514 games have both sources; 74 have Odds API only (pre-backfill dates); 99.5% overall coverage

**Validation results (2026-05-10):**

| season | total games | has_odds_api | has_parlay_api | has_both | pct_coverage |
|---|---|---|---|---|---|
| 2021 | 2,429 | 1,800 | 0 | 0 | 74.1% |
| 2022 | 2,430 | 1,789 | 0 | 0 | 73.6% |
| 2023 | 2,430 | 1,802 | 0 | 0 | 74.2% |
| 2024 | 2,429 | 1,809 | 0 | 0 | 74.5% |
| 2025 | 2,430 | 1,844 | 0 | 0 | 75.9% |
| 2026 | 591 | 588 | 514 | 514 | 99.5% |

**Design notes:**
- During overlap (now → 2026-05-23): bridge resolves to Parlay event_id for 2026 games; downstream joins land on Parlay API rows in `mart_odds_outcomes`; Odds API rows for the same games are orphaned (intentional — prioritize Parlay)
- After cutover (2026-05-23+): `odds_api_event_id` stays null for new games; coalesced event_id = `parlay_api_event_id`; no disruption to downstream models
- Historical (2021–2025): `parlay_api_event_id` is null; coalesced event_id = `odds_api_event_id`; no change to historical data path
- Doubleheader limitation: for DH games the Parlay API has one event_id for both games; the bridge maps it to whichever `game_pk` matches first — the second DH game_pk will have `parlay_api_event_id = null`; not fixable until Parlay API support ticket is resolved

---

### 0.9 — Parlay API line movement staging model ✅

**Goal:** Build a dbt staging model that flattens the `snapshots[]` array inside `mlb_line_movement_raw`, then update `mart_odds_line_movement` to reflect the Parlay API as the live data source.

**Scope revision (2026-05-10):** The original goal of replacing `mart_odds_outcomes` with `stg_parlayapi_line_movement` as the live path source is not viable — the `/line-movement` endpoint is player props only (zero h2h/totals). The live path in `mart_odds_line_movement` correctly stays on the `mart_odds_outcomes` snapshot approach (Parlay API hourly captures via `odds_snapshot.yml`). The `stg_parlayapi_line_movement` staging model is built and available for future player-prop CLV work.

Tasks:
- [x] Add `line-movement` step to `.github/workflows/odds_snapshot.yml` — wired at the hourly snapshot level (runs ~15×/day alongside odds ingestion); not added to `daily_ingestion.yml` since per-event calls require today's event_ids which are populated by the events step in `odds_snapshot.yml`
- [x] Create `dbt/models/staging/stg_parlayapi_line_movement.sql` — two lateral flattens over `mlb_line_movement_raw`; grain: `(ingestion_ts, event_id, bookmaker_key, market_key, player, snapshot_ts)`; all 20+ columns including decimal conversions and market type flags
- [x] Add source entry for `mlb_line_movement_raw` to `dbt/models/sources.yml` (under the `parlayapi` source block)
- [x] Document all output columns in `dbt/models/staging/schema.yml` with not_null tests on grain columns
- [x] Updated `mart_odds_line_movement.sql` header — documents that 2026+ live path uses Parlay API hourly snapshots via `mart_odds_outcomes`; adds leakage guard caveat (commence_time = 19:00:00Z placeholder); fix deferred to Story 0.10
- [x] Verified `mart_odds_line_movement` live data: 224 games (2026-04-23 → 2026-05-09), bovada confirmed present in Parlay API rows (10,660 h2h/totals rows); snapshot_count distribution 1–31 per game
- [x] Updated `mart/schema.yml` for `mart_odds_line_movement` — updated description to reference Parlay API as 2026+ source and document the commence_time leakage guard caveat; removed "OddsAPI" from bookmaker column description

**Known limitation (deferred to 0.10):** Parlay API `commence_time` is `19:00:00Z` for all games (a date-bucket placeholder). The live path leakage guard `ingestion_ts < commence_time` therefore excludes all same-day snapshots captured after 19:00 UTC, dropping the afternoon/evening window for most evening games, while potentially allowing a narrow post-first-pitch window for afternoon starts. This will be fixed in Story 0.10 by joining to `stg_parlayapi_canonical_events` for real per-game start times.

**Design note:** `mlb_line_movement_raw` grain is one row per ingestion run per event_id; `raw_json` contains an array of `(source × market)` records, each with a nested `snapshots[]` array of timestamped price changes. The staging model requires two lateral flattens: first over the top-level records array, then over each record's `snapshots` array. See Section 2.4 of `parlay_api_endpoint_mapping.md` for the full response schema.

---

### 0.10 — Canonical events ingestion (real game start times) ✅

**Goal:** Integrate the `/events/canonical` endpoint into daily ingestion to capture real per-game scheduled start times. The live `/events` and `/odds` endpoints only return `19:00:00Z` as a placeholder — actual game times are only available from this endpoint. Real start times are needed for leakage guards in time-series features and for future display/alerting use.

**Prerequisite:** Story 0.3 (ingestion script) complete. Can run in parallel with Story 0.9.

- [x] Add `events-canonical` subcommand to `scripts/parlay_api_ingestion.py` — uses `call_parlay_api_query_auth` (apiKey query param, not X-API-Key header); stores one row per run in `mlb_canonical_events_raw`
- [x] Add DDL for `mlb_canonical_events_raw` to `scripts/ddl/parlayapi_raw_tables.sql`; provisioned in Snowflake 2026-05-10
- [x] Create `dbt/models/staging/stg_parlayapi_canonical_events.sql` — grain: one row per `(ingestion_ts, canonical_event_id)` (no `event_id` — endpoint does not return the ephemeral Parlay id); output columns: `canonical_event_id`, `commence_time`, `game_date`, `source_count`, `ingestion_ts`
- [x] Add source entry for `mlb_canonical_events_raw` to `dbt/models/sources.yml`
- [x] Document all output columns in `dbt/models/staging/schema.yml` with not_null test on `canonical_event_id`
- [x] Add `events-canonical` step to `.github/workflows/daily_ingestion.yml` after the `events` step
- [x] Wire real `commence_time` into `mart_odds_line_movement.sql` live_raw leakage guard — added `event_canonical_bridge` CTE (from `stg_parlayapi_odds`, which has both `event_id` and `canonical_event_id`) then `canonical_times` CTE joining through it; `coalesce(ct.commence_time, o.commence_time)` ensures graceful fallback to placeholder when canonical data is absent

**Confirmed 2026-05-10 (live test):**
- API call succeeds; 25 canonical events returned for today's slate
- Real game times confirmed (e.g., ARI vs NYM 20:10Z, CIN vs HOU 17:40Z, KC vs DET 23:20Z — not 19:00:00Z)
- `commence_time` is empty string `""` (converted to null via NULLIF) for games not yet confirmed
- `game_date` field present in response and reliable even when `commence_time` is null
- Response does NOT include Parlay's ephemeral `event_id` — join to `stg_parlayapi_odds` on `canonical_event_id` required to bridge back to `event_id`

**Scope revision note:** The KNOWN LIMITATION in `mart_odds_line_movement.sql` (19:00:00Z leakage guard) is now fixed. The mart header and `mart/schema.yml` updated accordingly.

---

### 0.7 — Cutover validation and monitoring

Tasks:
- [ ] Run parallel ingestion for at least 3–5 days: ingest from both APIs simultaneously, compare event coverage and odds values
- [ ] Verify that `mart_bookmaker_disagreement` consensus line and bookmaker spread are consistent across sources for the overlap period
- [ ] Confirm `feature_pregame_game_features.has_odds` flag fires correctly from Parlay API data after Story 0.8 bridge update
- [ ] After validation: disable Odds API ingestion steps in GitHub Actions (2026-05-23 target, no later than 2026-06-01)
- [ ] Document which date range is covered by each source in `baseball_data_mart_inventory.md`

---

# Epic 0.5 — Orchestration: Decision Point (Revisit After Epic 3)

**Status: Deferred.** Do not build now.

**Context:** GitHub Actions is the current orchestrator and is working. A proper pipeline orchestrator (Dagster, Prefect) becomes genuinely useful once cross-epic asset dependencies materialize — i.e., once at least one sub-model (Epic 3+) is producing signals that downstream models consume. That complexity does not exist yet.

**Why deferred:** Dagster Cloud minimum cost is $10/month. Prefect Cloud has a functional free tier but weaker asset-lineage model. Self-hosted Dagster on a small VM (~$5–6/month Hetzner/DO) preserves the asset-centric model at low cost but adds maintenance burden. None of these trade-offs are worth taking on before the pipeline complexity that justifies them actually exists.

**Revisit trigger:** After Epic 3 (Run Environment Model) ships and the first sub-model signal is flowing into a downstream feature matrix. At that point, evaluate whether GitHub Actions dependency chaining is causing real pain. If yes, choose between:
- **Prefect Cloud free tier** — managed server/UI, no infra, weaker asset model
- **Self-hosted Dagster on Hetzner CX11** (~$5/mo) — stronger asset/lineage model, minor ops overhead

**Do not revisit sooner than Epic 3.**

---

# Epic 1 — Market-Blind Retrains

**Goal:** Remove market-derived features from all three production models and retrain. This is the single highest-priority improvement to live CLV performance and the direct fix for the market circularity problem identified in Phase 8.

**Target date:** ~2026-05-22 (waiting on in-season data accumulation).

---

### 1.1 — home_win market-blind retrain

**Status:** `_MARKET_COLS_TO_EXCLUDE` already populated in `train_elasticnet_prod.py`.

Tasks:
- [ ] Confirm `_MARKET_COLS_TO_EXCLUDE` list is complete (run feature importance analysis, verify all top market-correlated features are excluded)
- [ ] Run `train_elasticnet_prod.py` with exclusion list active
- [ ] Evaluate: CV Brier, ECE, calibration curve
- [ ] Gate: must beat or match current production Brier (0.2422)
- [ ] Update `model_registry.yaml` with new artifact path, feature columns, and wave gate results
- [ ] Update `.gitignore` exception if new `.pkl` artifact is to be tracked in git

---

### 1.2 — total_runs market-blind retrain

Tasks:
- [ ] Add `_MARKET_COLS_TO_EXCLUDE` equivalent to NGBoost training script (`train_ngboost_totals.py` or equivalent)
- [ ] Identify and drop the 4 noise features flagged in Phase 8 (`mean_imp <= 0`)
- [ ] Run retrain
- [ ] Evaluate: CV MAE, std(predicted values), mean residual, quantile calibration
- [ ] Gate: CV MAE must beat current 3.5107; std(pred) improvement over 0.77 is desired but not blocking
- [ ] Update `model_registry.yaml`

---

### 1.3 — run_diff market-blind retrain

Tasks:
- [ ] Switch training from `feature_columns.json` (294-feature pre-Phase 8 set) to `load_features()` full feature set
- [ ] Add market exclusion equivalent to `_MARKET_COLS_TO_EXCLUDE`
- [ ] Run retrain
- [ ] Evaluate: CV MAE vs current 3.4724; calibration; feature importance analysis to confirm market features are gone
- [ ] Gate: CV MAE within 1% of current; confirm `home_win_prob_consensus` no longer in top-20 features
- [ ] Update `model_registry.yaml`

---

### 1.4 — Post-retrain smoke test

Tasks:
- [ ] Run `predict_today.py` with all three new model artifacts against today's games
- [ ] Confirm prediction coverage for all confirmed-lineup games
- [ ] Spot-check that no market-derived features appear in model output feature sets

---

# Epic 2 — Sub-Model Infrastructure

**Goal:** Establish the storage interface, versioning pattern, and shared tooling that all sub-models will use. Do this before building any sub-model to avoid rework.

---

### 2.1 — Define sub-model output storage schema

Tasks:
- [ ] Decide on storage pattern (new `feature_pregame_sub_model_signals` mart vs. a `mart_sub_model_signals` wide table)
- [ ] Design schema: `game_pk`, `side`, `signal_name`, `signal_value`, `uncertainty`, `sub_model_version`, `computed_at`
- [ ] Write DDL and create table in Snowflake
- [ ] Create corresponding dbt model for the mart

---

### 2.2 — Sub-model versioning convention

Tasks:
- [ ] Define naming convention for sub-model version tags (e.g., `offensive_v1`, `run_env_v1`)
- [ ] Document convention in a `sub_model_registry.yaml` (mirrors structure of `model_registry.yaml`)
- [ ] Add `sub_model_version` tracking to `DAILY_MODEL_PREDICTIONS` or a dedicated audit table

---

### 2.3 — Sub-model evaluation harness

Tasks:
- [ ] Create `evaluate_sub_model.py` script that accepts a signal name and runs:
  - Temporal CV (rolling forward windows)
  - Correlation with outcome residuals
  - Incremental Brier/MAE contribution when added to base model
  - Feature importance rank in augmented model
- [ ] Integrate output into a `sub_model_ablation_report.md` template

---

### 2.4 — Add `computed_at` timestamps to all new feature marts

Tasks:
- [ ] Add `computed_at` (materialization timestamp) as a standard column to all new dbt feature marts going forward
- [ ] Document this as a dbt convention in the project README or CLAUDE.md

---

# Epic 3 — Run Environment Model

**Goal:** Build the first sub-model. Run environment is the best starting point: the target (total runs) is self-contained, the features (park, weather, umpire) are all already ingested, and the signal doesn't depend on any other sub-model.

---

### 3.1 — Define training dataset

Tasks:
- [ ] Query: park factor features, weather features, umpire tendency features, opponent quality controls, total runs scored
- [ ] Training window: 2016+ where weather backfill is available; 2021+ otherwise
- [ ] Validate: no future leakage, no market features

---

### 3.2 — Train run environment model (v1)

Tasks:
- [ ] Build feature matrix (park factors, temperature, wind, roof, umpire ERA+, day/night, elevation)
- [ ] Include opponent quality as training controls (team offensive ratings, starter quality)
- [ ] Train: Ridge regression or NGBoost as initial candidates
- [ ] Evaluate: MAE on total runs, calibration by ballpark bucket, calibration by temperature band
- [ ] Document: training window, feature list, target, metrics in `sub_model_registry.yaml`

---

### 3.3 — Generate and store run environment signals

Tasks:
- [ ] Write prediction script to generate: `run_environment_signal`, `weather_run_modifier`, `umpire_run_modifier`, `environment_volatility_signal`
- [ ] Store in sub-model output mart (from Epic 2)
- [ ] Backfill signals for 2021–2026 training window

---

### 3.4 — Ablation test

Tasks:
- [ ] Add run environment signals to existing totals model feature matrix
- [ ] Run temporal CV with and without the signals
- [ ] Report: incremental MAE improvement, calibration change, feature importance rank
- [ ] Gate: proceed to production integration only if signals show positive incremental value

---

# Epic 4 — Offensive Quality Model

**Goal:** Build a pre-game lineup quality signal that is independent of market data.

---

### 4.1 — Define training dataset

Tasks:
- [ ] Identify lineup feature columns already in the feature store (wRC+, OBP, SLG, wOBA, batting order position, handedness)
- [ ] Target: team runs scored, with opponent quality controls (Version 1 approach per architecture doc)
- [ ] Training window: 2016+

---

### 4.2 — Train offensive quality model (v1)

Tasks:
- [ ] Build feature matrix (projected lineup quality, lineup depth, platoon composition, park-adjusted batting metrics)
- [ ] Train: Ridge regression or gradient boosted trees
- [ ] Evaluate: residual correlation with actual runs scored, season stability of signal
- [ ] Document in `sub_model_registry.yaml`

---

### 4.3 — Generate and store offensive quality signals

Tasks:
- [ ] Generate: `lineup_run_creation_signal`, `lineup_depth_score`, `top_3_lineup_strength`, `bottom_3_lineup_strength`, `lineup_uncertainty_score`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 4.4 — Ablation test

Tasks:
- [ ] Add offensive signals to H2H and totals feature matrices
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 5 — Starter Suppression Model

**Goal:** Build a pre-game starter quality signal that captures stuff, command, and expected depth.

---

### 5.1 — Define training dataset

Tasks:
- [ ] Identify starter feature columns: Stuff+, CSW%, arsenal drift, velocity trend, recent workload, FIP, xFIP
- [ ] Primary target: starter xwOBA allowed in game (cleaner than runs allowed)
- [ ] Auxiliary targets: K%, BB%, innings pitched
- [ ] Training window: 2021+ (Stuff+ coverage-dependent)

---

### 5.2 — Train starter suppression model (v1)

Tasks:
- [ ] Build feature matrix (rolling Stuff+, CSW% last 3 starts, velocity delta, arsenal drift, workload)
- [ ] Train separate signals for: run suppression, expected depth, strikeout quality
- [ ] Evaluate: correlation with in-game xwOBA, K%, IP
- [ ] Document in `sub_model_registry.yaml`

---

### 5.3 — Generate and store starter suppression signals

Tasks:
- [ ] Generate: `starter_run_suppression_signal`, `starter_expected_ip_signal`, `starter_command_signal`, `starter_uncertainty_score`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 5.4 — Ablation test

Tasks:
- [ ] Add signals to H2H and totals feature matrices
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 6 — Bullpen State Model

**Goal:** Build a pre-game bullpen availability/fatigue signal. Version 1 targets arm state, not in-game runs allowed.

---

### 6.1 — Define training dataset

Tasks:
- [ ] Query: bullpen IP last 1/2/3 days, high-leverage appearances, closer rest days, reliever ERA/xwOBA rolling
- [ ] Target (v1): bullpen availability index — derived from workload features, not game-day runs allowed
- [ ] Training window: 2016+

---

### 6.2 — Build bullpen state index (v1)

Tasks:
- [ ] Define bullpen availability index formula (weighted sum of leverage-adjusted IP last 3 days)
- [ ] Validate index against known high-fatigue games (check correlation with next-game bullpen performance)
- [ ] Consider: simple rules-based index first vs. trained model second
- [ ] Document decision in `sub_model_registry.yaml`

---

### 6.3 — Train bullpen quality model (v1)

Tasks:
- [ ] Features: rolling bullpen xwOBA, K/BB, recent usage patterns
- [ ] Target: next-game bullpen xwOBA (not runs allowed, to avoid leverage-context conflation)
- [ ] Evaluate: correlation with out-of-sample bullpen performance
- [ ] Document in `sub_model_registry.yaml`

---

### 6.4 — Generate and store bullpen signals

Tasks:
- [ ] Generate: `bullpen_fatigue_signal`, `bullpen_quality_signal`, `high_leverage_availability_proxy`, `late_game_volatility_signal`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 6.5 — Ablation test

Tasks:
- [ ] Add signals to totals feature matrix
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 7 — Archetype Clustering (Prerequisite for Epic 8)

**Goal:** Define batter archetypes and pitcher archetypes as cluster labels that can be used in the matchup model.

---

### 7.1 — Batter archetype clustering

Tasks:
- [ ] Feature selection: contact rate, walk rate, ISO, pull%, hard-hit%, sprint speed, groundball rate
- [ ] Training window: 2021+ (requires Statcast coverage)
- [ ] Cluster algorithm: k-means or UMAP + HDBSCAN (evaluate 4–8 clusters)
- [ ] Assign cluster labels to all batters in training window
- [ ] Validate clusters are interpretable (e.g., "power/flyball", "contact/groundball", "patient/walk-heavy")
- [ ] Store batter archetype labels in a new dbt mart: `mart_batter_archetypes`
- [ ] Document cluster definitions

---

### 7.2 — Pitcher archetype clustering

Tasks:
- [ ] Feature selection: pitch mix (FB%, SL%, CH%, CB%), velocity, spin rate, extension, movement profile
- [ ] Training window: 2021+
- [ ] Cluster: 4–8 clusters (evaluate)
- [ ] Validate: clusters should map to recognizable pitcher types (e.g., "power FB", "command/soft", "high-spin breaking ball")
- [ ] Store labels in `mart_pitcher_archetypes`
- [ ] Document cluster definitions

---

### 7.3 — Historical archetype label backfill

Tasks:
- [ ] Assign archetype labels to all historical batter-pitcher appearances in training window
- [ ] Validate temporal stability: do cluster assignments shift significantly year-to-year? (Expected: yes for developing players — handle appropriately)

---

# Epic 8 — Matchup Model

**Depends on:** Epic 7 (archetype clustering)

**Goal:** Build a lineup-vs-starter matchup quality signal using archetype × archetype interaction history.

---

### 8.1 — Define training dataset

Tasks:
- [ ] Build batter archetype × pitcher archetype interaction matrix from historical PA data
- [ ] Target: wOBA/xwOBA by archetype pair, K%, BB%, hard-hit%
- [ ] Training window: 2021+

---

### 8.2 — Train matchup model (v1)

Tasks:
- [ ] Feature matrix: lineup archetype composition vs. starter archetype, handedness splits, bat tracking vs. velocity (optional block, 2023-07+)
- [ ] Train: gradient boosted model or interaction regression
- [ ] Evaluate: correlation of matchup signal with same-game offensive output
- [ ] Document in `sub_model_registry.yaml`

---

### 8.3 — Generate and store matchup signals

Tasks:
- [ ] Generate: `matchup_advantage_signal`, `matchup_k_pressure_signal`, `matchup_power_signal`, `matchup_volatility_signal`
- [ ] Store in sub-model output mart
- [ ] Backfill for 2021–2026

---

### 8.4 — Ablation test

Tasks:
- [ ] Add matchup signals to H2H and totals feature matrices
- [ ] Temporal CV comparison
- [ ] Gate before production integration

---

# Epic 9 — Signal Integration & Ablation Testing

**Depends on:** At least one of Epics 3–8 complete.

**Goal:** Establish a systematic process for evaluating sub-model signals and integrating promoted signals into production models.

---

### 9.1 — Build signal evaluation pipeline

Tasks:
- [ ] Script: query sub-model signal mart, join to training data, run ablation CV
- [ ] Metrics: incremental Brier (for H2H), incremental MAE (for totals), calibration shift, feature importance rank
- [ ] Output: `signal_ablation_report.md` per signal group

---

### 9.2 — Promote first round of signals

Tasks:
- [ ] For each sub-model that clears ablation gate: add signals to `load_features()` in `preprocessing.py`
- [ ] Add corresponding imputation rules for any missing-value cases
- [ ] Update feature column JSON files for affected models
- [ ] Re-run temporal CV after each signal group is added

---

### 9.3 — Document signal promotion decisions

Tasks:
- [ ] For each signal: record in `sub_model_registry.yaml` whether it was promoted, rejected, or deferred
- [ ] Note the incremental metric value and the gate threshold used
- [ ] Record which production model version first consumed the signal

---

# Epic 10 — Totals Distribution Model

**Depends on:** Epics 3–6 (at least some signals promoted into feature store); Epic 9 (signal integration baseline established).

**Goal:** Build a totals model that directly addresses the variance-shrinkage failure (current std(pred) = 0.77 vs. threshold 2.0) and produces calibrated run distribution outputs.

---

### 10.1 — Design distribution model architecture

Tasks:
- [ ] Evaluate: NGBoost Normal (current), LightGBM Quantile (Phase 8 challenger), Negative Binomial regression, Quantile regression forest
- [ ] Define evaluation gates: std(pred), quantile calibration, over/under Brier, MAE
- [ ] Confirm: no market features in training matrix

---

### 10.2 — Train totals distribution model

Tasks:
- [ ] Training matrix: Phase 8 features + promoted sub-model signals (from Epic 9), no market features
- [ ] Evaluate all candidate architectures against gates
- [ ] Select champion model
- [ ] Document in `model_registry.yaml`

---

### 10.3 — Generate distribution outputs

Tasks:
- [ ] Produce: `expected_total_runs`, `total_run_variance`, quantile features
- [ ] Store as additional columns in prediction output
- [ ] Smoke test against recent games

---

# Epic 11 — H2H Model Retrain with Sub-Model Signals

**Depends on:** Epic 1 (market-blind retrain complete); Epic 9 (signals promoted).

**Goal:** Retrain the H2H win probability model with market features excluded and with promoted sub-model signals as additional inputs.

---

### 11.1 — Build retrain feature matrix

Tasks:
- [ ] Start from market-blind elasticnet feature set (Epic 1)
- [ ] Add promoted sub-model signals
- [ ] Confirm: no market features present

---

### 11.2 — Retrain H2H model

Tasks:
- [ ] Run full CV sweep over same candidate models as Phase 8 (elasticnet, XGBoost, LightGBM)
- [ ] Evaluate: CV Brier, ECE, calibration curve
- [ ] Gate: must beat market-blind baseline from Epic 1
- [ ] Document in `model_registry.yaml`

---

### 11.3 — CLV evaluation

Tasks:
- [ ] Run live predictions for 2-4 weeks post-promotion
- [ ] Compute mean CLV for new model vs. market-blind baseline
- [ ] Gate for long-term production: mean CLV > 0 sustained over 30+ games

---

# Epic 12 — CLV Meta-Model

**Gate:** Do NOT begin production training until 500+ live CLV-labeled games are available.

**Current status:** ~41 games as of May 2026. Realistically unblocked late July or August 2026.

---

**Historical CLV path — Odds API is the only viable source for 2021–2025.**

The Parlay API does not provide a usable historical line movement source for h2h or totals:
- `/historical/period_markets` returns zero MLB data for all parameter combinations (confirmed via exhaustive testing 2026-05-10) — do not plan around this endpoint
- `/line-movement` covers player props only — zero h2h, totals, or F5 records; cannot be used for game-level CLV
- `/historical/matches` and `/historical/closing-odds` provide Pinnacle closing ML only — no opening lines for most books, no totals/F5, spotty game coverage (~30-40% of slate)

**Practical approach:**
- **2021–2025 historical CLV:** Use Odds API historical odds (`baseball_data.oddsapi.mlb_odds_raw`) for opening lines paired with Odds API closing snapshots. This is the existing `mart_closing_line_value` historical path — no new data source needed.
- **2026+ live CLV (h2h/totals):** Our own snapshot-based tracking via `odds_snapshot.yml` (~15 snapshots/game-day, operational from 2026-05-10) is the only viable source for h2h and totals line movement. The Parlay API contributes nothing here.
- **Player-prop CLV:** Feasible in future using Parlay API `/line-movement` data (props only). Not a current priority — defer until player-prop model infrastructure exists.
- **Meta-model training matrix:** When building Story 12.2, the "line movement" feature group must be sourced from our snapshot pipeline, not Parlay API's line-movement endpoint. Budget ~15 snapshots/game-day as the resolution ceiling for any line-movement feature.

---

### 12.1 — CLV monitoring (pre-threshold)

Tasks:
- [ ] Weekly: check live CLV game count in `mart_prediction_clv`
- [ ] Monthly: run descriptive CLV analysis (mean by game type, team, model edge bucket)
- [ ] Track: rate of positive CLV games, CLV distribution by edge size
- [ ] Log findings in a running `clv_monitoring_log.md`

---

### 12.2 — Exploratory meta-model (500+ games)

Tasks:
- [ ] Build training matrix: model edge, market disagreement, uncertainty, timing signals, public betting, line movement
- [ ] Target: binary positive CLV indicator
- [ ] Train: logistic regression first (interpretable)
- [ ] Evaluate: AUC, calibration, signal consistency
- [ ] Output: exploratory report only — do not promote to production

---

### 12.3 — Production meta-model (1000+ games)

Tasks:
- [ ] Temporal CV across at least 2 seasons of live data
- [ ] Evaluate: AUC, CLV calibration, ROI in backtest
- [ ] Gate: must demonstrate positive mean CLV in holdout period
- [ ] Document in `model_registry.yaml` as Layer 4 model

---

### 12.4 — Risk and portfolio layer

Tasks:
- [ ] Implement uncertainty-adjusted Kelly sizing
- [ ] Implement exposure caps by game and daily bankroll
- [ ] Integrate meta-model confidence score into sizing formula

---

# Epic 13 — Temporal Data Platform

**Scope:** Long-horizon infrastructure. Begin Phase 10. Not a Phase 9 deliverable.

**Goal:** Evolve the dbt/Snowflake data platform toward point-in-time correctness, SCD Type-2 entities, and historical CLV reconstruction.

---

### 13.1 — Temporal audit (Phase 9 preparatory)

Tasks:
- [ ] Audit all existing feature marts for leakage risk (finalized-season stats, non-temporal joins)
- [ ] Prioritize tables by leakage risk and frequency of use
- [ ] Document in `temporal_audit.md`

---

### 13.2 — Add timestamps to new marts (Phase 9)

Tasks:
- [ ] All new dbt models created in Phase 9 must include a `computed_at` column
- [ ] Enforce in dbt model review checklist

---

### 13.3 — SCD Type-2 for highest-priority entities (Phase 10)

Tasks:
- [ ] Implement SCD Type-2 for: projected starting pitchers, lineup projections, bullpen availability
- [ ] Update downstream feature marts to use point-in-time joins
- [ ] Validate: historical model reconstruction produces same features as original run

---

### 13.4 — Historical CLV reconstruction infrastructure (Phase 10+)

Tasks:
- [ ] Design: `prediction_snapshots` table with full feature version metadata
- [ ] Design: `odds_snapshots` with accurate opening/closing timestamps
- [ ] Implement: historical replay script that reconstructs predictions from stored feature snapshots
- [ ] Validate: spot-check reconstructed predictions against original `DAILY_MODEL_PREDICTIONS` rows

---

# Infrastructure Considerations

This section documents cross-cutting infrastructure concerns that are not tied to a single epic. Each item includes a **trigger** — the point at which it becomes worth acting on — to avoid premature investment.

---

## I1 — ML Training Compute

**Problem:** NGBoost retrains already take >1 hour locally. As sub-models are added (Epics 3–6), the full retrain suite will be several hours. GitHub Actions free tier caps jobs at 6 hours with 2 vCPUs, which will not be sufficient for NGBoost or ensemble training at scale.

**Current state:** Local machine. Works for now.

**Trigger:** When any single training job exceeds 2 hours, or when the total suite (all models + sub-models) can no longer complete in a single GitHub Actions job.

**Options when trigger hits:**
- **GitHub Actions larger runners** — paid, ~$0.008/min for 4-core. Low friction, no new infra.
- **Modal** — serverless GPU/CPU compute, pay-per-second, free tier available. Strong fit for bursty ML training workloads.
- **Spot instance (AWS/GCP/Hetzner)** — cheapest per-compute-minute but requires manual provisioning or scripting.

**Recommendation:** Modal is the cleanest path — call `modal run train_ngboost.py` from GitHub Actions, pay only for training time, no infra to maintain.

---

## I2 — Model Artifact Storage

**Problem:** Production `.pkl` files are tracked in git (with explicit `.gitignore` exceptions). This works for 3 artifacts but will break down as versioned sub-models are added — git is not designed for binary artifact versioning.

**Current state:** 3 `.pkl` files explicitly whitelisted in `.gitignore`. `model_registry.yaml` tracks metadata.

**Trigger:** When a second version of any sub-model is trained (Epic 3+), or when total artifact storage in git exceeds ~50MB.

**Options when trigger hits:**
- **S3 / GCS** — cheap object storage (~$0.023/GB/month S3). Store artifacts keyed by `{model_name}/{version}.pkl`. `model_registry.yaml` holds the S3 path instead of a local path.
- **Git LFS** — easier migration from current state, GitHub charges for storage beyond 1GB.
- **MLflow Tracking Server** — more overhead; not worth it unless you need a full experiment tracking UI.

**Recommendation:** S3 with path stored in `model_registry.yaml`. Minimal code change — just update the artifact load/save path in training and inference scripts.

---

## I3 — Pipeline Failure Alerting

**Problem:** If daily ingestion fails (Parlay API error, Snowflake timeout, dbt model failure), there is currently no proactive alert. You find out when you notice predictions are stale.

**Current state:** GitHub Actions sends email on workflow failure, but only if you notice the email.

**Trigger:** Now. This is a gap that costs nothing to fix and has direct betting impact — a silent ingestion failure means you're betting on stale data.

**Options:**
- **GitHub Actions → Slack webhook** — add a single `actions/slack-notify` step to `daily_ingestion.yml` on failure. Free.
- **`check_data_freshness.py` → alert** — wire the existing freshness check script to send a Slack message or email if any source is stale beyond threshold. Already partially built.
- **Snowflake query alert** — Snowflake has native alerting on query results; can trigger if `DAILY_MODEL_PREDICTIONS` hasn't been written today.

**Recommendation:** Add a Slack webhook failure notification to `daily_ingestion.yml` first (30-minute task). Then wire `check_data_freshness.py` to send a proactive alert if freshness check fails, regardless of whether the pipeline appeared to succeed.

---

## I4 — Secrets Management

**Problem:** API keys and credentials are spread across `.env` files (local), GitHub Actions secrets, and Snowflake. As Parlay API is added and sub-model infrastructure grows, the number of secrets will increase.

**Current state:** `.env` gitignored locally; GitHub Actions secrets for CI. No centralized audit trail.

**Trigger:** When more than ~5 distinct secrets exist across environments, or when onboarding a second team member requires secrets provisioning.

**Options when trigger hits:**
- **Doppler** — free tier covers 1 project/5 secrets. Syncs to GitHub Actions, local `.env`, and CI automatically. Very low friction.
- **AWS Secrets Manager** — more robust, ~$0.40/secret/month. Overkill until you have cloud infra.
- **1Password Secrets Automation** — if already using 1Password personally.

**Recommendation:** Doppler when the trigger hits. Until then, the current `.env` + GitHub Actions secrets pattern is fine.

---

## I5 — Data Observability / Freshness Monitoring

**Problem:** The feature store has 400+ columns derived from 8+ source schemas. Silent data quality failures (stale source, schema change from upstream API, null explosion in a mart) can cause model degradation that isn't immediately visible from CLV metrics.

**Current state:** `check_data_freshness.py` exists. dbt schema tests exist on some models. No systematic coverage.

**Trigger:** After Epic 2 (sub-model infrastructure), when the feature store is actively used for daily predictions. Any gap in feature quality directly affects live bets.

**Options:**
- **dbt tests** — already partially in place. Expand `not_null`, `accepted_values`, and `relationships` tests to all feature mart key columns. Free.
- **Elementary** — dbt-native observability package. Generates anomaly detection and data health reports as a dbt model. Free, open source. Requires a dashboard host (elementary Cloud free tier or self-hosted).
- **Great Expectations** — heavier, more configuration. Not worth it over expanded dbt tests for this use case.

**Recommendation:** Expand dbt tests coverage first (low cost, immediate value). Add Elementary after Epic 2 if dbt tests feel insufficient — it adds distribution-shift detection that pure schema tests miss.

---

## I6 — Snowflake Cost Monitoring

**Problem:** Snowflake costs can spike silently — a bad query, a runaway loop in a script, or a large dbt full-refresh can consume significant credits.

**Current state:** Unknown — no documented budget alert.

**Trigger:** Now. Set a budget alert before costs are a problem, not after.

**Action:** Set a Snowflake resource monitor with a monthly credit cap and an email alert at 75% and 100% utilization. 15-minute task via Snowflake UI.

---

# Acceptance Criteria Summary

| Epic | Gate / Exit Criterion |
|---|---|
| 1 — Market-blind retrains | All three models pass their metric gates; no market features in top-20 importance |
| 2 — Sub-model infrastructure | Output table created; versioning convention documented; evaluation harness working |
| 3 — Run environment | Ablation shows incremental improvement in totals CV MAE |
| 4 — Offensive quality | Ablation shows incremental improvement in H2H and/or totals CV |
| 5 — Starter suppression | Ablation shows incremental improvement in H2H and/or totals CV |
| 6 — Bullpen state | Ablation shows incremental improvement in totals CV |
| 7 — Archetype clustering | Clusters interpretable; labels stable year-over-year; stored in mart |
| 8 — Matchup model | Ablation shows incremental improvement in H2H CV |
| 9 — Signal integration | Promoted signals show positive incremental value; no calibration regressions |
| 10 — Totals distribution | std(pred) > 1.5; quantile calibration pass; MAE ≤ current baseline |
| 11 — H2H with signals | CV Brier beats market-blind baseline; mean CLV positive over 30+ live games |
| 12 — Meta-model | 1000+ CLV games; AUC > 0.55; positive mean CLV in holdout |
| 13 — Temporal platform | Point-in-time joins validated; historical reconstruction matches original predictions |
