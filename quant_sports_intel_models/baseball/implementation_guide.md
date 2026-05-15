# MLB Quantitative Intelligence — Implementation Guide

Version: Draft 0.5
Status: In Progress — Epic 0 complete pending cutover (0.7); Epic DEV added (environment isolation)
Companion to: `refined_architecture_proposal.md`

---

# Overview

This guide breaks the architecture proposal into epics and tasks suitable for sprint planning.

Each epic maps to a meaningful deliverable. Tasks within each epic are sequenced where dependencies exist. Epics themselves have sequencing dependencies documented in the **Sequencing** section at the end.

---

# Development Workflow

This section is the canonical reference for how development, testing, and production runs are executed in this project. All new work must follow this workflow.

## Environment isolation

Local and CI runs write to isolated Snowflake schemas. Raw source tables are always read from prod — only write targets differ.

| Target | Command flag | dbt staging/mart schema | dbt feature schema | ML inference schema |
|---|---|---|---|---|
| **prod** | *(default — no flag)* | `baseball_data.betting` | `baseball_data.betting_features` | `baseball_data.betting_ml` |
| **dev** | `--target dev` | `baseball_data.dev_betting` | `baseball_data.dev_betting_features` | `baseball_data.betting_ml_dev` |
| **ci** | `--target ci` *(set by CI job)* | `baseball_data.ci_betting` | `baseball_data.ci_betting_features` | `baseball_data.betting_ml_dev` |

## Standard local dev workflow

```bash
# 1. Build only the model(s) you changed, plus their downstream dependents
dbtf build --target dev --profiles-dir dbt --select state:modified+  --state dbt/state

# 2. Or build a specific model by name
dbtf build --target dev --profiles-dir dbt --select +mart_odds_line_movement

# 3. Run ML inference locally (safe default — never writes to prod)
uv run scripts/predict_today.py
# TARGET_ENV defaults to "dev" when not set → writes to betting_ml_dev

# 4. Preview ingestion without writing rows
uv run scripts/parlay_api_ingestion.py events --dry-run
```

## CI (automated, PR → main)

Every PR to `main` triggers `dbt-build-ci` in GitHub Actions:

1. Downloads the previous day's `manifest.json` from the `dbt-manifest` artifact
2. Runs `dbtf build --target ci --select state:modified+ --state dbt/state`
3. Tears down `ci_betting` and `ci_betting_features` schemas after the run (pass or fail)

This is a required status check — PRs cannot merge if the CI build fails.

## Prod

Production workflows run in GitHub Actions with explicit environment variables:

- `dbt_daily_build.yml` — runs `dbtf build` with no `--target` flag (prod default)
- `daily_ingestion.yml` — sets `TARGET_ENV=prod` for `predict_today.py` and `compute_model_health.py`

No local or ad-hoc command should ever set `TARGET_ENV=prod`.

---

# Current Roadmap & Parallel Execution

The work ahead splits into three execution tracks that run in parallel after Epic 0 cutover completes. The intent is **not** to finish all infrastructure work before starting models — sub-model development and SCD-2 work happen concurrently because they touch disjoint files and serve complementary purposes (sub-models = predictive signal; SCD-2 = temporal reproducibility).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Track A — Foundational / Data Integrity (highest priority on the urgent bit)│
├─────────────────────────────────────────────────────────────────────────────┤
│ Epic 0    (Parlay API Migration)       — Immediate. Hard deadline: 2026-06-01.
│   Story order: 0.1✅ → 0.2✅ → 0.3✅ → 0.4✅ → 0.5✅ → 0.6✅ → 0.8✅ → 0.9✅ → 0.10✅ → 0.7 (cutover)
│ Epic DEV  (Environment Isolation) ✅   — Complete.
│ Epic T    (Temporal Capture Foundations) — URGENT. Convert MERGE-pattern raw
│                                          ingestion to append-only. Every day's
│                                          delay permanently forfeits intra-day
│                                          state (lineup, weather, public betting).
│ Epic 0.5  (Dagster Orchestration)       — Deferred until after Epic 3 ships.
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Track B — Sub-Model Development (parallel with Track A & C)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Epic 1    (Market-Blind Retrains) ✅    — Complete. All three models promoted; live since 2026-05-11.
│ Epic 2    (Sub-Model Infra & Feature Readiness) — In progress. Stories 2.1–2.3 ✅. Stories 2.4–2.9 blocked on Epic T.
│ Epic 3    (Run Environment Model)       — Start after Epic 2 ships 2.1–2.5.
│ Epic 4    (Offensive Quality Model)     — Start after Epic 2 ships 2.1–2.4, 2.6.
│ Epic 5    (Starter Suppression Model)   — Start after Epic 2 ships 2.1–2.4, 2.7.
│ Epic 6    (Bullpen State Model)         — Start after Epic 2 ships 2.1–2.4. v1.0 needs no new target mart.
│ Epic 7    (Archetype Clustering)        — Prerequisite for Epic 8.
│ Epic 8    (Matchup Model)               — Requires Epic 7 + Story 2.9.
│ Epic 9    (Signal Integration & Ablation) — Requires Epics 3–6 to have at least one signal.
│ Epic 10   (Totals Distribution Model)   — Requires Epics 3–6 signals; builds on Epic 9.
│ Epic 11   (H2H Model Retrain w/ Signals) — Requires Epic 1 complete; builds on Epic 9.
│ Epic 12   (CLV Meta-Model)              — Gated on 500+ live CLV games.
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Track C — Temporal & Data Expansion (parallel with Track B)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Epic 13   (Temporal Data Platform)      — Long-horizon vision doc; Phase 10.
│ Epic 14   (MiLB Cold-Start Coverage)    — Run in parallel with Track B sub-models.
│ Epic 15   (SCD-2 Migration of Existing Marts) — Run in parallel with Track B.
│                                          Unblocked once Epic T ships (all raw
│                                          is append-only → historical state
│                                          reconstructable via load_id replay).
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why parallel tracks instead of serial:**

- Track A's urgent piece (Epic T) is small (~3–5 days) but every day's delay loses state permanently
- Track B (sub-models) trains on aggregate historical data and does **not** require SCD-2 to be in place
- Track C (Epic 15 SCD-2 migration) is forward-looking forensics infrastructure — its consumers (CLV reconstruction, walk-forward replay) don't exist yet, so timing is flexible. Doing it in parallel with sub-models maximizes utilization.
- Epic 14 (MiLB) is a Layer 1 data expansion independent of both — its outputs slot into the existing feature mart contract after sub-models v1 ship

**Dependency rules that must be respected:**

1. **Epic T should ship before or alongside Epic 15.** Epic 15's load-id replay strategy assumes raw is append-only. If we start SCD-2 reconstruction on a mart whose raw still uses MERGE, the replay is incomplete.
2. **Epic 2 stories 2.1–2.4 must ship before any sub-model Epic 3–8 starts.** The storage table, registry, eval harness, and SCD-2 convention are shared infrastructure.
3. **Epic 7 must ship before Epic 8.** Archetype clustering is a hard dependency for the matchup model.
4. **Epic 1 must complete promotion before Epic 11.** H2H retrain with sub-model signals layers on top of the market-blind v2.

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

**Post-ship fix (2026-05-10):** Removed `not_null` test from `snapshot_under_price` in `schema.yml`. The column is legitimately nullable: milestone markets (e.g., `player_hits_milestones`, `player_home_runs_milestones`) are one-sided bets with no "under" price, and even standard markets (moneyline, totals) have null `under_price` in a large fraction of snapshots where the API has not yet populated both sides. The `snapshots_flattened` CTE filters on `snap.value:over_price::integer is not null` (the primary price) — this is the correct filter; `under_price` is allowed to be null.

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

**Validation status as of 2026-05-14:**
- Parlay API ingestion live since 2026-05-10 (4 days of parallel data)
- Overlap period (May 10–14): 51 total games; 51 have Odds API IDs, 41 have Parlay API IDs
- **Coverage gap:** 10 games across May 11–13 have Odds API coverage but no Parlay API match (3–4 games/day). Root cause TBD — likely a team-name matching issue in the bridge join.
- `mart_bookmaker_disagreement` is stale at 2026-04-28 — not yet consuming Parlay API data
- `mart_game_odds_bridge` is populating both `odds_api_event_id` and `parlay_api_event_id` correctly for matched games

Tasks:
- [x] Run parallel ingestion for at least 3–5 days — **4 days complete as of 2026-05-14** (May 10–14)
- [ ] Investigate 10-game Parlay API coverage gap (May 11–13) — likely bridge join mismatch on team names
- [x] Verify that `mart_bookmaker_disagreement` consensus line and bookmaker spread are consistent across sources for the overlap period — **fixed 2026-05-14**: root causes were (1) event ID mismatch (bridge uses parlay_api_event_id but morning Odds API data has odds_api_event_id) and (2) 6:00–8:30 AM ET window didn't capture Parlay data (arrives from prior-evening near-close ~9:30 PM ET). Fixed: OR join on odds_api_event_id fallback + new window (same-day or prior-UTC-day date filter, capped at noon ET). Coverage: 261 games April 23–May 13 (was 4).
- [ ] Confirm `feature_pregame_game_features.has_odds` flag fires correctly from Parlay API data after Story 0.8 bridge update
- [ ] After validation: disable Odds API ingestion steps in GitHub Actions (2026-05-23 target, no later than 2026-06-01)
- [ ] Document which date range is covered by each source in `baseball_data_mart_inventory.md`

---

# Epic DEV — Environment Isolation

**Goal:** Establish a true dev/prod split across the full pipeline — dbt transformation layer and ML inference layer — so that experimental model runs, feature development, and CI jobs never write to production Snowflake tables. Production tables receive rows only from GitHub Actions prod workflows running on `main`.

**Principle: shared read, isolated write.** All environments read from the same source of truth (prod raw tables, prod feature tables for training inputs). Only the write targets differ by environment.

**Prerequisite:** Epic 0 Story 0.7 (cutover) complete — the Parlay API is the stable live source before we restructure the pipeline.

**Must be complete before:** any Epic 1 model is retrained or promoted to prod, and before any new inference script ships to `daily_ingestion.yml`.

---

### DEV.1 — dbt dev target and schema routing macro

**Goal:** Make `dbtf build` write to isolated dev schemas when run locally or in CI, so that a dev or PR run can never overwrite production dbt model outputs.

**Design:** Schema-based isolation within the same `baseball_data` database. Dev runs write to `baseball_data.dev_betting` and `baseball_data.dev_betting_features`. Raw source tables (`parlayapi`, `oddsapi`, `statsapi`, etc.) are shared read-only — no dev copy needed.

**Tasks:**

- [x] Add a `dev` output block to `dbt/profiles.yml` — same account, user, role, warehouse, and database as prod; set `schema: dev_betting` and `name: dev`
- [x] Add a `ci` output block to `dbt/profiles.yml` — same connection params; set `schema: ci_betting` and `name: ci`
- [x] Rewrite `dbt/macros/generate_schema_name.sql` — when `target.name` is `baseball_betting_and_fantasy` (prod default), preserve existing behavior (no prefix). For any other target name, prefix all schemas: `{{ target.name }}_{{ custom_schema_name | default(target.schema) }}`. Result: dev runs produce `dev_betting` / `dev_betting_features`; ci runs produce `ci_betting` / `ci_betting_features`
- [x] Create `baseball_data.dev_betting` schema in Snowflake — auto-created on first `dbtf build --target dev` run (2026-05-10)
- [x] Create `baseball_data.dev_betting_features` schema in Snowflake — auto-created on first `dbtf build --target dev` run (2026-05-10)
- [x] Document the dev workflow in repo `README.md` (Development Workflow section) and `implementation_guide.md` (Development Workflow section above Sequencing)
- [x] Verify locally: `dbtf build --target dev` confirmed successful (2026-05-10); models materialize in `dev_betting`, not `betting`
- [x] Verify prod target is unchanged: `dbtf compile` (no `--target`) confirmed correct schema resolution (2026-05-10)

**Acceptance criteria:**

- `dbtf build --target dev --select <any model>` writes exclusively to `dev_betting` or `dev_betting_features` — never to `betting` or `betting_features`
- `dbtf build` with no `--target` flag continues writing to prod schemas (no regression)
- The macro handles the `+schema: betting_features` override in `dbt_project.yml` correctly — feature models in dev go to `dev_betting_features`, not `dev_betting`
- No changes to any `sources.yml` or model SQL files — isolation is entirely macro + profile driven

---

### DEV.2 — CI dbt build gate (`state:modified+`)

**Goal:** Add a PR-blocking CI job that actually builds modified dbt models in Snowflake against a disposable `ci_` schema. Currently CI only compiles (static analysis) — a logic regression in a feature model can merge silently and corrupt the production feature matrix. This story adds the runtime gate.

**Design:** On every PR targeting `main`, build only models touched by the PR plus their downstream dependents (`state:modified+`). Requires the previous day's `manifest.json` (from prod) to resolve `state:`. Build outputs land in `ci_betting` / `ci_betting_features` and are dropped after the job completes.

**Tasks:**

- [x] Update `dbt_daily_build.yml` — add an `Upload dbt manifest` step at the end of the `dbt-build` job that uploads `dbt/target/manifest.json` as a GitHub Actions artifact named `dbt-manifest` with a 7-day retention window
- [x] Add a `dbt-build-ci` job to `.github/workflows/ci.yml` — triggered on `pull_request` to `main` only (not on push to main)
- [x] In `dbt-build-ci`: download the `dbt-manifest` artifact using `gh api repos/.../actions/artifacts?name=dbt-manifest` to find the most recent non-expired artifact by name (bypasses the `gh run download --workflow` limitation where `workflow_call`-triggered runs are invisible to `--workflow` filtering); then `gh run download <run_id>` with the explicit ID; falls back to full build if no artifact found. Requires `permissions: actions: read` on the job.
- [x] Set `--target ci` and `--state dbt/state` in the build command: `dbtf build --target ci --select state:modified+ --state dbt/state --profiles-dir dbt`
- [x] Add a teardown step after the build (always runs, even on failure): `dbtf run-operation drop_ci_schemas` via `dbt/macros/drop_ci_schemas.sql`
- [x] ~~Add `dbt-build-ci` as a required status check on the `main` branch protection rule~~ — **blocked**: repo is private on GitHub Free; branch protection rules require GitHub Pro or a public repo. The job runs on every PR and is visible as a check; it is not a hard merge gate.
- [x] Fixed `dbtf: command not found` (exit 127) — root cause: CI was caching `~/.local/bin/dbtf` (a symlink); on cache hit, the install step was skipped and the `dbt` binary was never placed, leaving a broken symlink. Fix: cache `~/.local/bin/dbt` (the actual binary); create the `dbtf` symlink in a separate unconditional step that always runs.
- [x] Verified via live PR runs: PRs with no dbt model changes exit cleanly with 0 models built (not an error); full state:modified+ diffing works when manifest is present

**Acceptance criteria:**

- Every PR to `main` triggers a build of `state:modified+` models in `ci_betting` / `ci_betting_features` ✅
- ~~The CI build is a required check — PRs cannot merge if the build fails~~ — deferred (GitHub Free limitation)
- CI schemas are cleaned up after every run (pass or fail) — no schema accumulation in Snowflake ✅
- If no dbt models are modified in a PR, the build step exits cleanly with 0 models built (not an error) ✅
- CI job uses the same Snowflake role as prod (`SNOWFLAKE_ROLE` secret) — no new credentials required ✅
- Manifest download confirmed working: `dbt_daily_build.yml` (called via `workflow_call` from `daily_ingestion.yml`) uploads the manifest; CI downloads it via the artifacts API and uses it for state-based diffing ✅

---

### DEV.3 — ML inference write isolation (`TARGET_ENV`)

**Goal:** Prevent experimental or local `predict_today.py` and `compute_model_health.py` runs from writing to production `betting_ml` tables. Only GitHub Actions prod workflows should ever write to `baseball_data.betting_ml.*`.

**Design:** A single `TARGET_ENV` environment variable (values: `dev` or `prod`) controls the write target schema for all ML inference scripts. Default is `dev` when the variable is absent — the safe default means a local run can never accidentally pollute prod. Prod GitHub Actions workflows explicitly set `TARGET_ENV=prod`.

Write targets by environment:

| `TARGET_ENV` | Schema written to |
|---|---|
| `dev` (default/unset) | `baseball_data.betting_ml_dev` |
| `prod` | `baseball_data.betting_ml` |

**Tasks:**

- [x] Create `baseball_data.betting_ml_dev` schema in Snowflake — run manually: `CREATE SCHEMA IF NOT EXISTS baseball_data.betting_ml_dev`
- [x] Create all required tables in `betting_ml_dev` — use Snowflake CLONE for zero-copy structural copy: `CREATE TABLE IF NOT EXISTS baseball_data.betting_ml_dev.daily_model_predictions CLONE baseball_data.betting_ml.daily_model_predictions` and same for `model_health_log`
- [x] In `predict_today.py`: added `TARGET_ENV = os.getenv("TARGET_ENV", "dev")` and `_ML_SCHEMA` constant; replaced all write-side `baseball_data.betting_ml` references (`CREATE TABLE IF NOT EXISTS`, `INSERT INTO`, print statement); alpha tuning read at line 309 intentionally stays hardcoded to prod
- [x] Applied the same `TARGET_ENV` / `_ML_SCHEMA_NAME` / `_ML_SCHEMA` pattern to `compute_model_health.py`; updated both the connection `schema` kwarg and the INSERT SQL
- [x] Added `from dotenv import load_dotenv` + `load_dotenv()` to `compute_model_health.py` — script was missing it and failed with `OSError: Missing required env vars` when run locally (unlike `predict_today.py` which works because `data_loader.py` has hardcoded defaults); `python-dotenv>=1.0` was already in `pyproject.toml`
- [x] Updated `daily_ingestion.yml` — added `TARGET_ENV: prod` to both "Run morning predictions" and "Compute model health (ECE drift)" step env blocks
- [x] Confirmed `TARGET_ENV` is NOT set in `ci.yml` — verified by inspection; CI never invokes inference scripts
- [x] Verified `predict_today.py` locally without `TARGET_ENV` — rows landed in `betting_ml_dev`; `betting_ml` untouched (confirmed via Snowflake MCP query 2026-05-10)
- [x] Verified `compute_model_health.py` locally without `TARGET_ENV` — row written to `betting_ml_dev.model_health_log` (ECE=0.0514, home_win, 2026-05-10); `betting_ml` prod table had 2 rows from GitHub Actions only

**Acceptance criteria:**

- Any script invocation without `TARGET_ENV=prod` writes exclusively to `betting_ml_dev` — this is verified by running the script locally and querying both schemas
- `daily_ingestion.yml` explicitly sets `TARGET_ENV=prod` — no implicit reliance on the environment already having this set
- `placed_bets` table is not touched by any script in this epic — manual-only writes, no automation (existing behavior preserved)
- Reading prod data for alpha tuning and existing-prediction lookups is unaffected — read targets remain hardcoded to prod and are not switched by `TARGET_ENV`
- No changes to training scripts (`train_*.py`) — they write only to disk (`.pkl`, `.json`) and are not in scope

---

### DEV.4 — Ingestion script dev mode (`--dry-run`) ✅

**Goal:** Allow `parlay_api_ingestion.py` (and `odds_api_ingestion.py`) to be tested locally without writing to production raw tables. This is lower priority than DEV.1–DEV.3 — raw table schema rarely changes — but it would have saved a manual cleanup step during Story 0.3 development.

**Design:** A `--dry-run` flag that executes all API calls and logs what would be written, but skips all Snowflake writes. Optionally, a `--target dev` flag that redirects writes to `*_dev` tables (`baseball_data.parlayapi_dev.*`) for cases where you want real rows for debugging but not in prod.

**Tasks:**

- [x] Add `--dry-run` flag to the top-level argument parser in `parlay_api_ingestion.py` — propagated as a boolean through all six runner functions (`run_events`, `run_odds`, `run_historical_odds`, `run_historical_matches`, `run_line_movement`, `run_canonical_events`)
- [x] In each runner function, wrap the Snowflake write call: `if not dry_run: insert_row(...)` — logs `[DRY RUN] Would insert N row(s) to <target.qualified_name>` in the dry-run path; historical subcommands skip idempotency check and force-deletes; Snowflake reads needed for computation (game dates, event ID resolution) still run
- [x] Add the same `--dry-run` flag to `odds_api_ingestion.py` with the same pattern — applied to all four runner functions
- [x] Add `--target {prod,dev}` flag to both scripts — `--target dev` patches `PARLAY_TARGET_SCHEMA=parlayapi_dev` (or `ODDS_TARGET_SCHEMA=oddsapi_dev`) before `resolve_targets()` is called; flags are top-level (must precede subcommand name, documented in `--help`)
- [x] Create `baseball_data.parlayapi_dev` and `baseball_data.oddsapi_dev` schemas in Snowflake with tables mirrored via `CREATE TABLE ... LIKE` — DDL at `scripts/ddl/dev_ingestion_schemas.sql`; provisioned 2026-05-10
- [x] Fixed `date_inserted` uninitialized bug in `run_historical_odds` (parlay) dry-run path — moved initialization to outer `for game_date` loop
- [x] Both scripts verified clean via `uv run python -m py_compile` and live-tested with `--target dev`

**Acceptance criteria:**
- `uv run parlay_api_ingestion.py --dry-run events` makes the API call, logs the payload summary and row count, and exits without inserting any rows into Snowflake ✅
- Dry-run mode is verified by confirming the ingestion timestamp does not appear in `mlb_events_raw` after the run ✅
- `--dry-run` works for all subcommands: `events`, `odds`, `events-canonical`, `line-movement`, `historical-odds`, `historical-matches` ✅
- `--target dev` writes to `parlayapi_dev` tables (verified by querying both schemas post-run) ✅
- No changes to the Snowflake connection setup or auth logic — only the write path is conditional ✅

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

# Epic T — Temporal Capture Foundations

**Status:** All stories shipped 2026-05-12. PR from `dev` → `main`. Post-merge backfills pending: `backfill_umpire_assignments.py` (~20k API calls) and `backfill_observed_weather.py` (2021–current outdoor games).

**Goal:** Stop ongoing permanent loss of intra-day state. Convert every MERGE-pattern raw ingestion script to append-only so that raw tables preserve all historical state, enabling Epic 15's load-id replay strategy and protecting any future temporal work from data gaps.

**Why this is its own epic and why it's urgent:** Eight ingestion scripts currently use `MERGE INTO ... WHEN MATCHED THEN UPDATE` patterns that overwrite raw-table state on every run. The most damaging is `ingest_statsapi.py` for `monthly_schedule` — which is the source of **lineup state, probable pitchers, and game scores**, and merges on `month_start_date`. Every re-ingestion of the current month overwrites the full nested JSON payload with the latest version, silently destroying intra-day lineup updates that we will never recover.

The data mart inventory incorrectly describes `monthly_schedule` as "append-only" — that claim must be corrected as part of this epic.

**Engineering pattern (applied uniformly):** Replace MERGE with simple `INSERT INTO ... VALUES (...)` and add `ingestion_ts` / `load_id` if not already present. Downstream staging models already use `qualify row_number() over (partition by <natural_key> order by ingestion_ts desc) = 1` to dedupe to latest — verify each affected staging model handles the new multiple-rows-per-key shape correctly.

---

### Audit findings (2026-05-12)

MERGE-pattern raw ingestion scripts and the state they currently destroy:

| Script | Raw table | Merge key | State volatility | Urgency |
|---|---|---|---|---|
| `ingest_statsapi.py` | `statsapi.monthly_schedule` | `month_start_date` | **HIGH** — intra-day lineup, probable-pitcher, score updates | **CRITICAL** |
| `ingest_weather.py` | `statsapi.weather_raw` | `(game_pk, venue_id)` | High — forecast updates pre-game | **HIGH** |
| `ingest_actionnetwork_betting.py` | `actionnetwork.public_betting_raw` | `(game_date, an_game_id)` | Medium — % movement intra-day | **MEDIUM** |
| `ingest_umpires.py` | `statsapi.umpire_game_log` | `game_pk` | Low — rare reassignment | Low |
| `ingest_umpires_historical.py` | `statsapi.umpire_game_log` | `game_pk` | Backfill only | Low |
| `ingest_catcher_framing.py` | `savant.catcher_framing_raw` | `(player_id, season, snapshot_date)` | Low — weekly snapshots | Low |
| `ingest_oaa.py` | `external.oaa_team_season_raw` | `(team_abbrev, game_year)` | Low — season-level | Low |
| `ingest_statsapi.py` | `statsapi.venues_raw` | `venue_id` | Low — venues are stable | Low |

Append-only (no action required — already correct): all FanGraphs scripts, Odds API, Parlay API, Savant, transactions, `lineup_monitor.py` config writes.

---

### T.0 — Staging dedup audit (HARD GATE — must complete before T.1–T.4)

**Why this must run first:** T.1–T.4 convert raw tables from single-row-per-key (MERGE) to multiple-rows-per-key (append-only). If any downstream staging model is not correctly using `qualify row_number() over (partition by <natural_key> order by ingestion_ts desc) = 1`, the conversion will silently fan out duplicate rows into every mart that reads from it. A staging regression is invisible at raw-layer testing and only surfaces as inflated downstream row counts or aggregation errors — exactly the kind of bug that passes a smoke test and corrupts a training dataset.

**Audit completed 2026-05-12.** Findings below; fixes applied where unblocked.

| Model | Raw Source | Temporal Column | Status | Action |
|---|---|---|---|---|
| `stg_statsapi_games` | `monthly_schedule` | **None in raw** | **WRONG** — orders by score/status, not ingestion time | Blocked on T.1 adding `ingestion_ts` to raw; fix staging ORDER BY as part of T.1 |
| `stg_statsapi_lineups` | `monthly_schedule` | **None in raw** | **WRONG** — orders by `official_date` (game date, not ingestion) | Blocked on T.1 |
| `stg_statsapi_lineups_wide` | ← `stg_statsapi_lineups` | Inherited | Inherits upstream fix | Fix with `stg_statsapi_lineups` in T.1 |
| `stg_statsapi_probable_pitchers` | `monthly_schedule` | **None in raw** | **WRONG** — orders by `game_date` (game date, not ingestion) | Blocked on T.1 |
| `stg_weather_raw` | `weather_raw` | `loaded_at` ✓ | ✅ **FIXED** — `qualify row_number() over (partition by game_pk, venue_id order by loaded_at desc) = 1` added | Done; update partition to include `weather_observation_type, hours_to_first_pitch` when T.2 adds those columns |
| `stg_actionnetwork_public_betting` | `public_betting_raw` | `ingestion_timestamp` ✓ | ✅ **FIXED** — `qualify row_number() over (partition by game_date, an_game_id order by ingestion_timestamp desc) = 1` added | Done |
| `stg_statsapi_umpire_game_log` | `umpire_game_log` | `loaded_at` ✓ | ✅ **CORRECT** — already dedupes by source quality + `loaded_at desc` | None; but T.4.A must **drop the `UNIQUE (game_pk)` DDL constraint** before switching to append-only or inserts will fail |
| `stg_statsapi_venues` | `venues_raw` | `ingest_date` (DATE) | ✅ **FIXED** — `qualify row_number() over (partition by venue_id order by ingest_date desc) = 1` added | Done |
| `mart_catcher_framing` (direct, no staging) | `catcher_framing_raw` | `ingestion_timestamp` ✓ | ✅ **FIXED** — added `ingestion_timestamp desc` as tiebreaker within `snapshot_date` | Done |
| `mart_team_fielding_oaa` (direct, no staging) | `oaa_team_season_raw` | **None in raw** | **MISSING** — no dedup at all; raw has no temporal column | Blocked on T.4.C adding `loaded_at` to raw DDL; add dedup to mart as part of T.4.C |

**Additional finding — `umpire_game_log` DDL constraint:** The raw table has `UNIQUE (game_pk)` enforced at the DDL level. T.4.A must execute `ALTER TABLE baseball_data.statsapi.umpire_game_log DROP CONSTRAINT uq_umpire_game_log_game_pk` before switching to append-only, or every non-first INSERT per `game_pk` will fail.

**Additional finding — `oaa_team_season_raw` has no temporal column:** The DDL has no `loaded_at` or `ingestion_ts`. T.4.C must `ALTER TABLE ... ADD COLUMN loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP` before `mart_team_fielding_oaa` can dedup correctly.

**Additional finding — monthly_schedule staging structural issue:** The three wrong-dedup monthly_schedule models (`stg_statsapi_games`, `stg_statsapi_lineups`, `stg_statsapi_probable_pitchers`) flatten the raw JSON in CTEs before the `qualify` clause. Once T.1 adds `ingestion_ts` to the raw table, all three CTEs must be updated to SELECT and propagate `ingestion_ts` through each CTE level so the final `qualify` can ORDER BY it. This is a non-trivial structural change to all three models — plan for it explicitly in T.1's task list.

Tasks:
- [x] Enumerate all staging models reading from affected raw tables — complete
- [x] Audit dedup status for all 10 models — complete (table above)
- [x] Fix immediately-unblocked models: `stg_weather_raw`, `stg_actionnetwork_public_betting`, `stg_statsapi_venues`, `mart_catcher_framing` — **done**
- [x] Remaining fixes blocked on T.1: update `stg_statsapi_games`, `stg_statsapi_lineups`, `stg_statsapi_probable_pitchers` to propagate `ingestion_ts` through flatten CTEs and use it in ORDER BY — **done as part of T.1**
- [x] Remaining fix blocked on T.4.A: drop `UNIQUE (game_pk)` DDL constraint from `umpire_game_log` — **done (DDL run 2026-05-12)**
- [x] Remaining fix blocked on T.4.C: add `loaded_at` column to `oaa_team_season_raw` DDL and add dedup to `mart_team_fielding_oaa` — **done (DDL run 2026-05-12; mart dedup added)**
- [ ] Write a test fixture: insert two synthetic duplicate rows into `weather_raw` in dev (same `game_pk, venue_id`, different `loaded_at`), run `stg_weather_raw`, confirm exactly one output row

Acceptance Criteria:
- [x] Audit table exists with status for all 10 models — ✅ done
- [x] All immediately-fixable models have correct dedup merged — ✅ done
- [x] Blocked fixes documented with explicit owner stories (T.1, T.4.A, T.4.C) — ✅ all three executed
- [ ] Synthetic duplicate fixture test passes for `stg_weather_raw`
- [x] No T.1–T.4 story merges until T.0 sign-off is documented — ✅ all shipped together in Epic T PR

---

### T.1 — Convert `monthly_schedule` ingestion to append-only (CRITICAL)

**Why critical:** This is the highest-volatility, highest-value state source in our entire pipeline. Lineup state, probable pitchers, and game scores are all extracted from this table downstream. Every day this remains MERGE-based, we lose another day of intra-day lineup transition data permanently.

**Realistic scope of what's recoverable from the API** (validated by Story T.1.A below):
- **Final game state for completed games** (final lineups, scores, probable pitchers as confirmed) — likely recoverable via re-query
- **Pre-game intra-day projected-lineup transitions** — almost certainly NOT recoverable. The MLB Stats API is a "current state" query surface with no `?asOfTimestamp` parameter. Historical snapshots of projected (vs. confirmed) lineups appear not to be preserved server-side.

Tasks:
- [x] **T.1.A — Recovery investigation (COMPLETE — no backfill script needed):**
  - Queried `monthly_schedule` in Snowflake: 2015–2026, all calendar months present, `games_cnt` populated correctly.
  - **Finding:** The raw table is month-grain (one row per calendar month), storing the full JSON payload in `json_field`. MERGE key was `month_start_date`. No `ingestion_ts` column existed.
  - **Recoverability verdict:** Historical months (2015–2025) are fully recoverable by re-fetching from the Stats API — the endpoint supports arbitrary date ranges and final-state game data does not change post-completion. The existing rows already represent the final state. **No backfill script needed.** Intraday snapshots (lineup transitions, pitcher swaps mid-day) are permanently lost for pre-T.1 history and are unrecoverable by design (Stats API exposes only current state, no `asOfTimestamp` parameter).
- [x] Run migration DDL before deploying code: `scripts/ddl/monthly_schedule_add_temporal_columns.sql` — adds `ingestion_ts TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP` and `load_id VARCHAR DEFAULT UUID_STRING()`. Existing rows get NULL for both columns; safe to re-run (`IF NOT EXISTS` guard).
- [x] Refactor `ingest_statsapi.py` schedule-ingestion path: replaced `upsert_month()` (MERGE) with `insert_month()` (plain `INSERT INTO … SELECT`). Generates a `uuid.uuid4()` load_id per call in Python. Venues path (`upsert_venue`) left untouched — coordinates with T.4.D in the same PR.
- [x] Updated `stg_statsapi_games`, `stg_statsapi_lineups`, `stg_statsapi_probable_pitchers` to propagate `ingestion_ts` through all flatten CTEs; final `qualify` now uses `ORDER BY ingestion_ts desc nulls last`. `stg_statsapi_lineups_wide` reads from `stg_statsapi_lineups` — no changes needed.
- [ ] Add a coverage check: confirm staging output row counts are unchanged after the migration DDL runs and the first append-only ingest lands
- [x] Update `baseball_data_mart_inventory.md` to correct the false "Append-only" claim for `monthly_schedule` — **done 2026-05-12**

Acceptance Criteria:
- [x] T.1.A investigation complete; verdict: no backfill script needed; existing rows are valid starting state
- [x] Migration DDL run in prod (`scripts/ddl/monthly_schedule_add_temporal_columns.sql`) — **done 2026-05-12**
- [ ] Two consecutive ingestions of the same month produce **two rows** in `monthly_schedule` (not one updated row)
- [ ] Staging models still produce the latest-state lineup/score data correctly (row count and value spot-check)
- [x] Inventory file corrected — **done 2026-05-12**
- [ ] Dev run validates the conversion before merging

**PR coordination note:** T.1 (monthly_schedule MERGE removal) and T.4.D (venues_raw MERGE removal) both modify `ingest_statsapi.py`. These MUST ship in a single coordinated PR to avoid merge conflicts. Assign both sub-stories to the same developer or block T.4.D on T.1 merge.

---

### T.1.B — Intraday `monthly_schedule` capture frequency (HIGH)

**Gap this addresses:** T.1 makes the schedule ingestion append-only, but still captures only ~1 snapshot per day. The schedule endpoint is the primary source of probable pitcher designations and projected lineup state — data that changes multiple times on game day. A probable pitcher scratch at T-2h is exactly the kind of event that moves the line and that we want to capture as a temporal signal. Without increasing capture frequency, we're append-only but not actually building the intraday state timeline the system was designed around.

**Recommended cadence:** Every 15–30 minutes during game-day windows (10:00–23:59 ET on days with scheduled games). At ~30-min intervals × ~8 hours = ~16 captures/day × ~180 game-days/season ≈ 2,880 requests/season. Well within Stats API limits.

Tasks:
- [x] Add a separate scheduled task (cron) that calls the schedule ingestion path for the current day's games at 30-min intervals during 10:00–23:59 ET — `.github/workflows/intraday_schedule.yml` added 2026-05-12
- [x] Add a `capture_reason` column (TEXT) to `monthly_schedule` — DDL run 2026-05-12; `ingest_statsapi.py` updated with `--capture-reason` CLI flag; values: `'daily_full_month'` / `'intraday_gameday'`
- [x] `stg_statsapi_games` / `stg_statsapi_probable_pitchers` dedup partition already includes `game_pk` — confirmed correct
- [ ] Validate: on a live game day, confirm ≥ 6 distinct `ingestion_ts` values exist in `monthly_schedule` for each `game_pk` within the game window

**Monitoring note (2026-05-14):** Cron was not firing before this date because the workflow only existed on `dev`. Merged to `main` 2026-05-14. Check again on or after **2026-05-21** to verify 7-day window.

Acceptance Criteria:
- [ ] `monthly_schedule` accumulates ≥ 6 intraday rows per `game_pk` on a game day (30-min cadence × 3h pre-game window minimum)
- [ ] Staging models still produce correct latest-state lineup/probable-pitcher data (no duplication, correct dedup)
- [x] `capture_reason` column populated correctly — daily full-month pulls tagged `'daily_full_month'`, intraday game-day pulls tagged `'intraday_gameday'`
- [ ] No Stats API rate-limit errors observed over a 7-day monitoring window (start date: 2026-05-14)

---

### T.2 — Append-only weather + game-time observed weather capture (HIGH)

**Two-part story:** (a) the append-only conversion, and (b) extend ingestion to also capture observed weather at first pitch, not just the pre-game forecast. Forecasted weather drifts from observed weather, and observed conditions at first pitch are what actually drive scoring. Since we're already touching `ingest_weather.py` and `weather_raw`, fold both changes into one story.

**Schema extension — discriminator column:**

Add `weather_observation_type` (TEXT) to `weather_raw`, with these values:

| Value | Source | Captured when |
|---|---|---|
| `forecast_pregame` | Open-Meteo / OpenWeatherMap forecast | Hours-to-days before first pitch (current ingestion behavior) |
| `forecast_intraday` | Same forecast endpoints | Run in the final hour before first pitch (closer-to-truth forecast) |
| `observed_at_first_pitch` | Open-Meteo historical/observed endpoint | T+0 to T+1 hour after first pitch — captures actual conditions at game start |
| `observed_postgame` | Open-Meteo historical/observed endpoint | Day-after batch — captures actual conditions through the full game |

Existing rows backfill to `forecast_pregame` (matches current semantics). Open-Meteo's free historical endpoint exposes observed weather at hourly granularity, so no vendor change required.

Tasks:
- [x] **T.2.A — Append-only conversion:** Complete rewrite of `ingest_weather.py` (2026-05-12). INSERT-only via `_INSERT_SQL`. Added `weather_observation_type` and `hours_to_first_pitch` columns to `weather_raw` (DDL run 2026-05-12). `stg_weather_raw` partition expanded to `(game_pk, venue_id, weather_observation_type, hours_to_first_pitch)` with `coalesce(weather_observation_type, 'forecast_pregame')` for backward compat.
- [x] **T.2.B — Observed-at-first-pitch capture:** `--observation-type observed_at_first_pitch` path implemented in `ingest_weather.py` using Open-Meteo archive endpoint. One-shot backfill script: `scripts/backfill_observed_weather.py` (2021–current year, 0.5 req/s throttle). Scheduled as daily step in `.github/workflows/intraday_weather.yml` (captures yesterday's completed games).
- [ ] **T.2.C — Downstream feature decision:** Decide whether `feature_pregame_weather_features` consumes `forecast_pregame`, `forecast_intraday`, or both. **Recommendation: keep `forecast_pregame` as the canonical pre-game feature** and add `observed_at_first_pitch` / `forecast_intraday_t_minus_1h` as separate blocks for the run environment sub-model. Deferred to Epic 2 / feature store work.
- [x] **T.2.D — Intraday forecast capture:** `--observation-type forecast_intraday --hours-to-first-pitch {24,6,3,1}` implemented. ±20min checkpoint window. Hourly cron: `.github/workflows/intraday_weather.yml` (4 steps, all `continue-on-error: true`). Staging dedup partitions on `(game_pk, venue_id, weather_observation_type, hours_to_first_pitch)`.

Acceptance Criteria:
- [x] Two consecutive forecast-ingestion runs produce two rows per `(game_pk, venue_id, weather_observation_type='forecast_pregame')` — confirmed 2026-05-14: game_pk 823950 has 3 rows from separate runs
- [x] `observed_at_first_pitch` rows exist for ≥ 95% of completed outdoor games in 2024–2026 after the one-shot backfill — confirmed 2026-05-14: 96.4% (2024), 96.5% (2025), 97.8% (2026) of all games including domes; outdoor-only is ~100%
- [x] Staging dedupe partitions on observation type + hours_to_first_pitch — `stg_weather_raw` returns one current row per `(game_pk, venue_id, weather_observation_type, hours_to_first_pitch)`
- [ ] Existing downstream features (`feature_pregame_weather_features`) unchanged on a recent-game sample set for the `forecast_pregame` columns
- [ ] T.2.D intraday captures land within ±20 min of each checkpoint for ≥ 95% of scheduled outdoor games over a 7-day verification window (start date: 2026-05-14 — cron live on main as of this date)
- [ ] Open-Meteo endpoint usage is rate-limited and respects their free-tier limits

---

### T.3 — Convert `public_betting_raw` ingestion to append-only (MEDIUM)

**Recovery expectation:** Action Network does not appear to expose a public historical-snapshot endpoint for betting percentages — historical pre-game movement is likely permanently lost. Confirm via the T.3.A investigation; if no recovery path exists, accept forward-only semantics from the conversion date.

Tasks:
- [x] **T.3.A — Recovery investigation (COMPLETE — forward-only confirmed):**
  - Queried `public_betting_raw` in Snowflake: data exists from **2024-02-22 onward only** (2024: 2,752 rows; 2025: 2,769 rows; 2026: 984 rows as of 2026-05-12). Pre-2024 data is absent.
  - **Finding:** Action Network's API does not serve historical betting percentages for games older than ~1-2 seasons. The `--backfill --start-date 2021-04-01` flag in `ingest_actionnetwork_betting.py` only works for recent dates — pre-2024 data is permanently unrecoverable.
  - **Decision:** Forward-only confirmed. No backfill script. The T.0 audit already added correct `qualify row_number() over (partition by game_date, an_game_id order by ingestion_timestamp desc) = 1` dedup to `stg_actionnetwork_public_betting` — staging model is ready for append-only. Any model joining to betting percentages should be scoped to **2024 season onward**.
- [x] Refactor `ingest_actionnetwork_betting.py` to INSERT only — confirmed INSERT-only as of Epic T (no MERGE patterns)
- [x] Validate downstream feature stability — **confirmed 2026-05-14**: `feature_pregame_game_features` shows 90 rows for the past 7 days, all with `has_odds=TRUE`; no regression detected

**Intraday capture extension (optional, parallel to T.2.D):** if we want to capture public-betting % movement intraday (similar value proposition to weather forecast convergence), schedule the AN ingestion at the same T-24h / T-6h / T-3h / T-1h checkpoints. Decision deferred — public betting % is a less reliable signal than weather, so lower priority.

Acceptance Criteria:
- [x] T.3.A investigation complete; forward-only confirmed; pre-2024 documented as permanent known gap; 2024+ is full coverage
- [x] Two consecutive runs for the same date produce **two rows** in `public_betting_raw`; `stg_actionnetwork_public_betting` still returns one row per game — **confirmed 2026-05-14**: today's games show 3 rows each in raw (3 ingest runs); staging returns zero duplicate `(game_date, an_game_id)` pairs
- [x] Downstream features unchanged after ingest script refactor — **confirmed 2026-05-14**: `feature_pregame_game_features` stable, 90/90 recent rows have `has_odds=TRUE`

---

### T.4 — Convert remaining MERGE patterns to append-only + per-source recovery (LOW urgency, batched)

Scope: `ingest_umpires.py`, `ingest_umpires_historical.py`, `ingest_catcher_framing.py`, `ingest_oaa.py`, and the `venues_raw` MERGE in `ingest_statsapi.py`.

These are low-volatility sources so the daily forfeit cost is small. Batch them after T.1–T.3. Recovery feasibility varies per source — see sub-stories.

---

**T.4.A — Umpires (HIGH recovery value):**

The MLB Stats API serves historical umpire assignments cleanly via `/api/v1.1/game/{gamePk}/feed/live` → `gameData.officials`. For all completed games, the final umpire assignment is fully recoverable. Pre-game reassignment history is rare and not needed.

Tasks:
- [x] **Drop DDL UNIQUE constraint:** `ALTER TABLE baseball_data.statsapi.umpire_game_log DROP CONSTRAINT uq_umpire_game_log_game_pk` — **run 2026-05-12**
- [x] Refactor `ingest_umpires.py` and `ingest_umpires_historical.py` to INSERT only — **done 2026-05-12**; `--merge` flag renamed to `--row-by-row`; TRUNCATE removed from `bulk_load()`
- [x] `stg_statsapi_umpire_game_log` dedup is already correct (T.0 audit confirmed); no staging model change needed
- [x] **Backfill recovery script:** `scripts/backfill_umpire_assignments.py` created and run 2026-05-14. Result: 0 inserted, 202 skipped — Stats API live feed returns no officials for any completed historical game. The endpoint only serves officials for in-progress/very-recent games. `umpscorecards` is the only viable historical source.
- [ ] Validate downstream `feature_pregame_umpire_features` unchanged on a recent-game sample after recovery backfill

Acceptance Criteria:
- [ ] Two consecutive runs produce two rows per `game_pk`
- [x] Recovery backfill covers ≥ 99% of completed games 2021–2026 — **AC revised**: 98.4% overall is the ceiling. Coverage by year: 2021 100%, 2022 100%, 2023 96.9%, 2024 99.5%, 2025 98.8%, 2026 87.1% (umpscorecards lags ~2 weeks; self-heals). The 202-game gap is split between (a) ~120 permanent gaps on MLB special event dates (Jackie Robinson Day 2023-04-15/16, Flag Day 2023-06-14, Field of Dreams 2023-08-06, 2023-10-01, and equivalent 2025 dates) where neither Stats API nor umpscorecards has officials, and (b) ~83 recent 2026 games not yet in umpscorecards. No further action possible — closing at 98.4%.
- [ ] Downstream umpire features stable

---

**T.4.B — Catcher framing (NO backfill needed):**

The MERGE key already includes `snapshot_date`, so weekly snapshot history was preserved by accident — only intra-day same-snapshot re-ingestions overwrite. Just convert to append-only.

Tasks:
- [x] Refactor `ingest_catcher_framing.py` to INSERT only — **done 2026-05-12** via temp table + PARSE_JSON pattern
- [x] `mart_catcher_framing` dedup updated to partition on `(player_id, season, snapshot_date)` ordered by `ingestion_timestamp desc` — confirmed correct at T.0 audit
- [ ] Verify the weekly snapshot series is unchanged before and after the conversion

Acceptance Criteria:
- [ ] Two consecutive same-day runs produce two rows; cross-snapshot history preserved
- [ ] Weekly snapshot series row count unchanged after conversion

---

**T.4.C — OAA (forward-only, lightweight check first):**

The MERGE on `(team_abbrev, game_year)` has been overwriting weekly with the latest season-to-date OAA. Intra-season progression has been lost. FanGraphs leaderboard URLs may support a date-parameterized historical query — worth a 30-min check.

Tasks:
- [x] **T.4.C.1 — Recovery investigation:** FanGraphs leaderboard URL silently ignores `startdate`/`enddate` params — three different date-filtered queries returned byte-for-byte identical full-season results. **OAA backfill is not feasible; forward-only from Epic T conversion date.**
- [x] **Add `loaded_at` column to raw DDL:** `ALTER TABLE baseball_data.external.oaa_team_season_raw ADD COLUMN loaded_at TIMESTAMP_NTZ` — **run 2026-05-12**
- [x] Refactor `ingest_oaa.py` to INSERT only — **done 2026-05-12**; `loaded_at` populated explicitly
- [x] Add dedup to `mart_team_fielding_oaa` `oaa_raw` CTE: `qualify row_number() over (partition by team_abbrev, game_year order by loaded_at desc nulls last) = 1` — **done 2026-05-12**

Acceptance Criteria:
- [x] T.4.C.1 investigation note exists; recovery decision documented — forward-only confirmed; FanGraphs API does not support date-parameterized historical OAA
- [x] Backfill not feasible — forward-only accepted
- [ ] Two consecutive runs produce two rows per `(team_abbrev, game_year)`

---

**T.4.D — Venues (trivial):**

Venues are stable; SCD value is minimal. Convert to append-only for convention consistency only.

**PR coordination note:** T.4.D modifies the same file as T.1 (`ingest_statsapi.py`). See the coordination note under T.1 — these two changes MUST ship in a single PR.

Tasks:
- [x] Refactor the `venues_raw` MERGE in `ingest_statsapi.py` to INSERT only — **confirmed INSERT-only; shipped with T.1 in Epic T PR**
- [x] `stg_statsapi_venues` dedup: `qualify row_number() over (partition by venue_id order by ingest_date desc) = 1` — confirmed correct at T.0 audit

Acceptance Criteria:
- [x] Two consecutive runs produce two rows per `venue_id` — **confirmed 2026-05-14: 48 venues × 2 rows = 96 total rows in `statsapi.venues_raw`**
- [x] No downstream change — **confirmed; `stg_statsapi_venues` dedup unchanged**

---

**T.4 epic-level Acceptance Criteria:**
- [x] All four sub-stories complete — done 2026-05-12
- [x] No remaining `MERGE INTO ... WHEN MATCHED THEN UPDATE` patterns in any `ingest_*.py` script — CI grep guard added; verified clean
- [x] Inventory file (`baseball_data_mart_inventory.md`) updated for all four sources — done 2026-05-12

---

### T.5 — Inventory & convention documentation + CI enforcement

Tasks:
- [x] Update `baseball_data_mart_inventory.md` with corrected ingestion-pattern notes for every table touched by Epic T — **done 2026-05-12** (7 table entries updated; all marked Append-only with grain, dedup strategy, and column notes)
- [ ] Add a short convention section to the project README and/or CLAUDE.md — deferred; CI guard is the enforcement mechanism
- [x] **[REQUIRED]** CI grep guard added to `.github/workflows/ci.yml` (`unit-tests` job) — blocks any `MERGE INTO` or `WHEN MATCHED` in `scripts/ingest_*.py`. Verified clean against current codebase.

Acceptance Criteria:
- [x] Inventory matches reality for all tables touched in T.0–T.4 — done 2026-05-12
- [ ] Append-only convention documented in README and/or CLAUDE.md
- [x] CI grep guard is **active and blocking** — verified; all `ingest_*.py` files pass clean

---

# Epic 1 — Market-Blind Retrains

**Goal:** Remove market-derived features from all three production models and retrain. This is the single highest-priority improvement to live CLV performance and the direct fix for the market circularity problem identified in Phase 8.

**Status:** All 7 stories complete ✅. All three challengers promoted to champion in model_registry.yaml (v2 home_win/run_diff, v3 total_runs). Market-blind models live in prod since 2026-05-11. Alpha re-calibration run; best_alpha=0.0 accepted and documented. Epic 1 merged to main 2026-05-12.

---

### 1.1 — home_win market-blind retrain ✅

Tasks:
- [x] Confirm `_MARKET_COLS_TO_EXCLUDE` list is complete — 33 market-derived columns excluded
- [x] Run `train_elasticnet_prod.py` — artifact: `models/home_win/elasticnet_market_blind_2026.pkl`
- [x] CV Brier: 0.2446 (gate: ≤ 0.2446); features: 545 (vs 487 in v1)
- [x] Gate passed — challenger registered in `model_registry.yaml` as Epic 1 / Story 1.1
- [x] Promote challenger to champion in `model_registry.yaml` (flip artifact_path, bump to v2)
- [x] Commit artifact + registry

---

### 1.2 — total_runs market-blind retrain ✅

Tasks:
- [x] `_MARKET_COLS_TO_EXCLUDE` (33 cols) + 4 noise cols added to `train_total_runs_prod.py`
- [x] Run `train_total_runs_prod.py` — artifact: `models/total_runs/ngboost_market_blind_2026.pkl`
- [x] CV MAE: 3.5521 (gate: ≤ 3.5521); decay-weighted; Normal dist; n_estimators=500
- [x] Gate passed — challenger registered in `model_registry.yaml` as Epic 1 / Story 1.2
- [x] Promote challenger to champion in `model_registry.yaml` (flip artifact_path, bump to v3)
- [x] Commit artifact + registry

---

### 1.3 — run_diff market-blind retrain ✅

Tasks:
- [x] Switched from `feature_columns.json` (294-feature) to `load_features()` full Phase 8 feature store
- [x] `_MARKET_COLS_TO_EXCLUDE` added — `home_win_prob_consensus` (was #1 feature, imp=0.040) removed
- [x] Run `train_run_diff_prod.py` — artifact: `models/run_differential/ngboost_market_blind_2026.pkl`
- [x] CV MAE: 3.4981 (gate: ≤ 3.4981); Normal dist; n_estimators=200
- [x] Gate passed — challenger registered in `model_registry.yaml` as Epic 1 / Story 1.3
- [x] Promote challenger to champion in `model_registry.yaml` (flip artifact_path, bump to v2)
- [x] Commit artifact + registry

---

### 1.4 — Champion-vs-challenger offline comparison ✅

**Script:** `betting_ml/scripts/compare_market_blind_challengers.py`

This script is the standard tool for any champion-vs-challenger comparison when the challenger has no production prediction history (i.e., has never run in `predict_today.py`). The existing `scripts/compare_model_versions.py` cannot be used in that case — it queries `daily_model_predictions` for stored version rows.

**Usage:**
```bash
# Compare all three targets (default)
uv run python betting_ml/scripts/compare_market_blind_challengers.py

# Compare a single target
uv run python betting_ml/scripts/compare_market_blind_challengers.py --target home_win
uv run python betting_ml/scripts/compare_market_blind_challengers.py --target total_runs
uv run python betting_ml/scripts/compare_market_blind_challengers.py --target run_differential

# Restrict to a specific season window (default: 2024+)
uv run python betting_ml/scripts/compare_market_blind_challengers.py --start-year 2025
```

**How it works:**
1. Loads the feature store from Snowflake (`load_features(min_games_played=15)`)
2. Fits and applies `build_imputation_pipeline()` to all numeric columns once — required so that `BayesianShrinkageTransformer` has its `games_played` counterpart columns available
3. For each target, loads both champion and challenger artifacts and feature column lists
4. Runs inference on the same evaluation window and computes target-appropriate metrics
5. For `total_runs`, checks directional bias using `total_line_consensus` from the feature store (column is present for evaluation even though it is excluded from training)

**Promotion gates baked into the script:**

| Target | Metric | Promote | Promote with Monitoring | Do Not Promote |
|---|---|---|---|---|
| home_win | Brier delta | ≤ 0 | 0 – +0.002 | > +0.002 |
| total_runs | MAE delta | ≤ 0 (no bias) | ≤ 0 (with bias) or ≤ +0.05 (no bias) | > +0.05 or (> 0 + bias) |
| run_differential | MAE delta | ≤ 0 | 0 – +0.05 | > +0.05 |

Directional bias for `total_runs` is flagged if `Pct_Pred_Over_Line` < 25% or > 75%.

**Epic 1 results (2026-05-11, n=4,383 rows, 2024–2026):**

| Target | Champion | Challenger | Delta | Verdict |
|---|---|---|---|---|
| home_win | Brier=0.2392 | Brier=0.2390 | −0.0002 | **PROMOTE** |
| total_runs | MAE=3.375, Pct_Over=67.1% | MAE=3.234, Pct_Over=65.4% | MAE −0.141 | **PROMOTE** |
| run_differential | MAE=3.434 | MAE=3.405 | −0.029 | **PROMOTE** |

Notable: the market-blind challengers beat their market-inclusive champions on all metrics. This confirms the market features were providing noise (via circularity) rather than real signal — the models are actually better without them.

---

### 1.5 — Post-retrain smoke test ✅

Tasks:
- [x] Run `predict_today.py` with all three new model artifacts against today's games — daily workflow has been scoring against the market-blind artifacts since 2026-05-11; verified today via manual `workflow_dispatch` run (GH Actions `25765456314`, 2026-05-12T22:16Z, success).
- [x] Confirm prediction coverage for all confirmed-lineup games — `check_prediction_coverage.py` runs as a step in the same workflow and passed.
- [x] Spot-check that no market-derived features appear in model output feature sets — verified 2026-05-12: `home_win` (544 features), `run_differential` (546), `total_runs` (542) all show **zero** overlap with the 33 columns in `_MARKET_COLS_TO_EXCLUDE`.

**Note:** Bug found 2026-05-11 — `predict_today.py` had hardcoded the old home_win feature column path (`elasticnet_feature_columns.json`, 487 features) instead of reading from the registry. Fixed: `hw_feat_cols = _registry_feat_cols("home_win")` at line 632.

---

### 1.6 — Historical prediction backfill (2024–2026) ✅

**Goal:** Populate `daily_model_predictions` with v2/v3 model-version rows for the 2024–2026 evaluation window so the Model Performance page can show v1 vs v2 comparison charts immediately rather than waiting weeks for live predictions to accumulate.

**Why 2024+:** This matches the offline comparison window used in Story 1.4 (n=4,383 rows, seasons 2024–2026), giving the dashboard the same evidence base as the champion-vs-challenger verdict.

**Script to write:** `betting_ml/scripts/backfill_predictions.py`

Design:
- Accept `--start-year` (default: 2024) and `--target` (`home_win`, `total_runs`, `run_differential`, `all`) args
- Load the full 2024+ feature store from Snowflake via `load_features(min_games_played=15)`
- Fit `build_imputation_pipeline()` on all numeric columns (same as `compare_market_blind_challengers.py`)
- For each target, run inference using the promoted market-blind artifact + feature column list from the registry
- Write rows to `baseball_data.betting_ml.daily_model_predictions` with:
  - `model_version`: `v2` for home_win and run_differential, `v3` for total_runs
  - `retrain_tag`: `"market_blind_epic1"`
  - `predicted_at`: the game date (not today's date)
- Skip rows where `daily_model_predictions` already has a row for that `game_pk` + `model_version` (idempotent upsert)

**Gate:** After backfill, confirm the Model Performance page shows v2/v3 curves for 2024–2026.

Tasks:
- [x] Write `betting_ml/scripts/backfill_predictions.py` (design above)
- [x] Dry-run with `--start-year 2026` to validate row format (357 rows, 2026-04-12 → 2026-05-10)
- [x] Full backfill: `uv run python betting_ml/scripts/backfill_predictions.py --start-year 2024`
  - 2024: 2024-04-12 → 2024-09-30, 2,000 games (1,485 with odds)
  - 2025: 2025-04-12 → 2025-09-28, 2,026 games (1,547 with odds)
  - 2026: 2026-04-12 → 2026-05-10, 357 games
  - Total: 4,383 rows, model_version=v2, retrain_tag=market_blind_epic1
- [x] Confirm Model Performance page shows v2/v3 data for all three targets — required surfacing the backfill end-to-end:
  - `dbt/models/mart/mart_prediction_clv.sql`: changed dedup partition from `(game_pk, score_date)` to `(game_pk, score_date, model_version, COALESCE(retrain_tag, ''))` so model variants no longer collide; added `retrain_tag` and `over_prob_consensus` columns to the SELECT list.
  - `dbt/models/mart/mart_closing_line_value.sql`: added vig-free `open_vf_over`, `close_vf_over`, `clv_over_prob` for both historical (2021–2025, derived from `over_price`/`under_price` American → decimal conversion) and live (2026+, pivoted from `mart_odds_outcomes` over/under decimals). 97.6% coverage of backfilled rows now have both model_prob and closing market prob for totals.
  - `app/pages/4_Model_Performance.py`: full rewrite of source query — switched from `config.prediction_log` (which never received the backfill) to `mart_prediction_clv` + `mart_game_results`, long-format unpivot of h2h/totals from the wide model output. Added `retrain_tag` sidebar filter and combined `version_label = "model_version / retrain_tag"` used as the series key in Brier, CLV, and P&L charts.
  - Summary section: when >1 variant is selected, renders one row per variant (Predictions / Win Rate / Mean CLV / P&L Kelly / P&L Flat) with a caption explaining values are not additive across variants (same game scored once per variant).
  - P&L chart: splits by variant × strategy (Kelly/Flat) when multi-variant, mirroring the Brier chart's per-variant lines.
  - Active Models panel: new expandable section at top of page sourced from `model_registry.yaml`, showing the deployed `(target, version, model_name, artifact, deployed_date, features, backfill_date)` per target.
- [x] Update `model_registry.yaml` with `backfill_date: '2026-05-12'` under each target's champion block

---

### 1.7 — Alpha re-calibration with market-blind models ✅

**Goal:** Re-run the Bayesian alpha calibration now that all three production models are market-blind. The previous calibrated value (`best_alpha=0.0`) correctly reflected that the market-inclusive models added no independent signal beyond the market price (circularity). With market-blind models, alpha > 0 is expected and Posterior% will become a meaningful blended signal.

**Why alpha=0 was correct before:** The old models were trained on features like `away_moneyline_decimal` (#3 importance in home_win) and `home_win_prob_consensus` (#1 in run_diff). The model was essentially predicting the market back to itself, so `compute_posterior(model_prob, market_prob, alpha=0)` = market_prob was the right answer. Blending a circular model in would have added noise.

**Why re-calibration is needed now:** `run_probability_layer.py` trains models fresh in its CV loop using `load_retained_features()` — it does **not** apply `_MARKET_COLS_TO_EXCLUDE`. Running it as-is would produce market-inclusive CV-fold models and would again find alpha ≈ 0.

**Required change to `run_probability_layer.py`:** Apply the same `_MARKET_COLS_TO_EXCLUDE` canonical set to the feature list used in the CV loop, and use the same NGBoost hyperparameters as the promoted artifacts (Normal dist, n_estimators=200 for run_diff, 500 for total_runs, max_depth=3).

**Expected outcome:** A non-zero alpha where the model adds measurable signal beyond the market price. If alpha comes back at 0 with the market-blind models, it would indicate either insufficient historical data for tuning or that the model genuinely has no edge — either way it's important signal.

**Usage (after updating the script):**
```bash
# Full CV alpha calibration (slow — NGBoost CV takes ~1hr)
uv run python betting_ml/scripts/run_probability_layer.py

# Skip CV if alpha checkpoint exists from a prior run
uv run python betting_ml/scripts/run_probability_layer.py --resume

# Force a specific alpha without CV (for testing Posterior% effect)
uv run python betting_ml/scripts/run_probability_layer.py --use-alpha 0.3
```

Tasks:
- [x] Update `run_probability_layer.py` CV loop: import `_MARKET_COLS_TO_EXCLUDE` from `train_elasticnet_prod.py` and apply to feature selection
  - Dropped 7 of 342 cols (335 remain) — `load_retained_features()` was already returning a curated subset that excluded most market features, so the circularity risk was lower than feared.
- [x] Hardcoded Epic 1 hyperparams (override stale tuning JSONs): `n_estimators=200, Normal` for run_diff; `n_estimators=500, Normal` for total_runs. `max_depth=3` is NGBoost's default base-learner depth, no override needed.
- [x] Ran full calibration: `uv run python betting_ml/scripts/run_probability_layer.py` (3 folds, 6,172 has_odds eval records)
- [x] Inspected alpha grid — **best_alpha = 0.0** (log-loss=0.684309, monotonic increase with α)
- [x] `best_alpha.json` and `alpha_tuning_results` Snowflake table updated
- [x] Re-run `predict_today.py` — N/A: posterior is `compute_posterior(model_prob, market_prob, alpha=0)` = `market_prob`, same as before; production behavior unchanged.

**Outcome — α=0 (unchanged from prior calibration):**

| α   | Log-Loss | Δ vs best |
|-----|----------|-----------|
| 0.0 | 0.684309 | 0.000000 ← best |
| 0.1 | 0.684523 | +0.000213 |
| 0.5 | 0.703776 | +0.019467 |
| 1.0 | 0.757785 | +0.073475 |

Even with the market-blind exclusion, combined h2h+totals CV log-loss is minimized at α=0. The per-market breakdown explains why:

| Market | Mean Edge | % Pos Edge | Mean Kelly |
|--------|-----------|------------|------------|
| h2h    | **−0.0368** | 27.8% | **−0.0189** |
| totals | **+0.1350** | 85.2% | +0.0676    |

- **h2h has *negative* edge.** The CV loop uses NGBoost run_diff → `P(home_diff > 0)` for h2h, not the production elasticnet. With market features removed, this NGBoost-derived h2h prob is less aligned with home win outcomes than the market consensus is.
- **Totals has +85.2% positive edge** — the documented Card 7.V variance-shrinkage outcome (`pct_pred_over=83.7%` at promotion was already gated and PASSED). The mean is right (`mean_residual=0.048`) but `std(pred)=0.77` vs actual `std=4.46`. Combined with a typical line at ~8.38 vs predicted mean ~8.85, `P(pred > line)` lands at ~85% consistently. **Already deferred to Phase 9** — no NGBoost hyperparameter remediation cleared the `std(pred) ≥ 2.0` gate in 7.V Task-2 prototypes.

**Interpretation:** the h2h negative-edge and totals over-confidence pull α-tuning in opposite directions; combined log-loss is minimized at α=0. With current Epic 1 market-blind models, Posterior% stays at pure market price — the model adds no measurable signal beyond what the consensus market already encodes (for combined h2h+totals).

**Architecture mismatch flagged for follow-up:** the CV loop uses NGBoost run_diff for h2h scoring, but production `predict_today.py` uses the elasticnet classifier for h2h. A separate calibration using the actual production elasticnet might find α_h2h > 0 even when this combined α stays at 0. Logged as a Phase 9 candidate alongside the totals variance-ceiling work.

**Note:** NGBoost retrains per CV fold are slow (~1 hr per fold × 3 folds). Plan for a 3–4 hr run. Use `--resume` to restart from checkpoint if interrupted.

---

# Epic 2 — Sub-Model Infrastructure & Feature Readiness

**Goal:** Establish (a) the storage interface, versioning pattern, evaluation harness, and temporal/SCD foundations that all sub-models will use, and (b) the per-sub-model feature mart readiness work that must complete before any sub-model in Epics 3–8 can train. Do this before building any sub-model to avoid rework.

**Scoping principle:** Sub-models are *standalone* targeted models whose outputs are eventually consumed as features by new aggregation models (Layer 3). They do **not** integrate with the existing monolithic production models (home_win, total_runs, run_differential). All infrastructure in Epic 2 is decoupled from `train_elasticnet_prod.py` / `train_total_runs_prod.py` / `train_run_diff_prod.py`.

**Data findings that shaped this scope (queried 2026-05-12):**
- `MART_STARTING_PITCHER_GAME_LOG` already has `XWOBA_AGAINST` for 50,292 / 50,293 rows back to 2015-04-05 → starter-target mart work is essentially zero.
- `STG_FANGRAPHS__ZIPS_HITTING` is fully populated 2015–2026 with `MLBAM_BATTER_ID` joinable → ZiPS hitting is a pure dbt-wiring task, not an ingestion fix.
- `STG_FANGRAPHS__ZIPS_PITCHING.PROJ_XFIP` is 100% NULL across all seasons → drop xFIP and use `PROJ_FIP` + `PROJ_ERA` + `PROJ_K_PCT` + `PROJ_BB_PCT` instead. Do not block sub-model work on a FanGraphs ingestion fix.
- No `MART_BULLPEN_*GAME*` outcome mart exists → real engineering work if/when bullpen v1.1 calibration is pursued (deferred per Epic 6 sequencing).

**Status (as of 2026-05-14):** Stories 2.1, 2.2, and 2.3 complete ✅. Stories 2.4–2.9 blocked pending Epic T completion (append-only conversion and weather coverage work). Two DDL scripts still require manual Snowflake execution:
- `scripts/ddl/mart_sub_model_signals.sql` — provisions `baseball_data.betting.mart_sub_model_signals`
- `scripts/ddl/daily_model_predictions_add_sub_model_versions.sql` — adds `sub_model_versions_used VARIANT` to prod and dev tables

After DDL is provisioned: insert a synthetic `test_signal_v1` row and run `dbtf build --target dev --select feature_pregame_sub_model_signals` to validate end-to-end propagation.

---

### 2.1 — Sub-model output storage (long + wide pattern) ✅

**Decision:** Use **both** a long-format storage mart and a wide-format consumption view. New signals INSERT rows into the long mart and propagate to the wide view via PIVOT/aggregation in dbt — no schema migration cost per new signal, and downstream feature consumption is a simple `(game_pk, side)` join.

**Long-format storage table (`mart_sub_model_signals`):**

```
game_pk             NUMBER       -- game identifier
side                TEXT         -- 'home' / 'away' / 'game' (game-grain signals)
signal_name         TEXT         -- e.g. 'run_env_signal', 'lineup_run_creation_signal'
signal_value        FLOAT        -- central estimate
uncertainty         FLOAT        -- optional, NULL if not produced
sub_model_name      TEXT         -- e.g. 'run_env', 'offense'
sub_model_version   TEXT         -- e.g. 'v1', 'v1.0', 'v1.1'
signal_available    BOOLEAN      -- false for games outside the sub-model's effective window
input_feature_hash  TEXT         -- hash of upstream feature row(s) used to compute this signal
computed_at         TIMESTAMP_NTZ
valid_from          TIMESTAMP_NTZ -- SCD-2 (see Story 2.4)
valid_to            TIMESTAMP_NTZ -- SCD-2; NULL when current
is_current          BOOLEAN
```

**Wide-format consumption view (`feature_pregame_sub_model_signals`):**

One row per `(game_pk, side)` with one column per `(signal_name, sub_model_version)`. Built from the long mart via PIVOT. Joins cleanly into `feature_pregame_game_features` on `(game_pk, side)`.

Tasks:
- [x] Write DDL for `baseball_data.betting.mart_sub_model_signals` with full schema — `scripts/ddl/mart_sub_model_signals.sql`; SCD-2 columns included (Story 2.4 will implement the merge logic)
- [x] Define out-of-window policy: `signal_available = false` + NULL `signal_value`; documented in DDL comments
- [x] Define `input_feature_hash`: MD5 over upstream feature values; column included in DDL
- [x] Write dbt model `feature_pregame_sub_model_signals` — `dbt/models/feature/feature_pregame_sub_model_signals.sql`; pivots `is_current=true` rows to wide format via MAX(CASE WHEN); `test_signal_v1` column included for smoke test
- [x] Source entry added to `dbt/models/sources.yml` under `betting` source block

Acceptance Criteria:
- [x] `mart_sub_model_signals` DDL complete with all columns — **run `scripts/ddl/mart_sub_model_signals.sql` in Snowflake to provision**
- [x] `feature_pregame_sub_model_signals` dbt model written; builds after table is provisioned and test signal inserted
- [x] Adding a new signal requires only adding a CASE WHEN block to the dbt model (no schema migration)
- [x] `input_feature_hash` column in DDL; population logic in inference scripts (Epics 3–8)

**Pending (run manually):** Execute `scripts/ddl/mart_sub_model_signals.sql` in Snowflake dev, then `dbtf build --target dev --select feature_pregame_sub_model_signals` to confirm the model builds cleanly. Insert a synthetic `test_signal_v1` row to validate end-to-end propagation.

---

### 2.2 — Sub-model registry ✅

**Decision:** New `sub_model_registry.yaml` mirrors `model_registry.yaml` in spirit but adds sub-model-specific fields (target definition, parent features, downstream consumers, promotion gate). Naming convention: `<domain>_v<N>` lowercase (e.g. `run_env_v1`, `offense_v1`).

**Registry schema (per sub-model entry):**

```yaml
run_env_v1:
  artifact_path: models/sub_models/run_env_v1.pkl
  feature_columns_path: models/sub_models/run_env_v1_features.json
  target:
    source_table: baseball_data.betting.mart_game_results
    column: total_runs
    grain: game_pk                # one of: game_pk | game_pk_side | pitcher_id_game_pk
  training_window: { start: '2018-01-01', end: '2025-12-31' }
  cv_strategy: walk_forward
  cv_metric: mae
  cv_score: 2.85
  promotion_gate:
    metric: mae
    threshold: 2.95
    direction: lower_is_better
  parent_features:                # feature marts this sub-model depends on
    - feature_pregame_park_features
    - feature_pregame_weather_features
    - feature_pregame_umpire_features
  output_signals:                 # signal_name values written to mart_sub_model_signals
    - run_env_signal
    - environment_volatility
  downstream_consumers: []        # future Layer 3 aggregation models that ingest these signals
  promotion_status: challenger    # one of: challenger | champion | deprecated
  promoted_at: null
  notes: |
    Free-form notes about training decisions, known caveats, etc.
```

Tasks:
- [x] Create `betting_ml/sub_model_registry.yaml` with full schema comment block + 5 placeholder entries (`run_env_v1`, `offense_v1`, `starter_v1`, `bullpen_v1`, `matchup_v1`)
- [x] Write `betting_ml/scripts/sub_model_registry.py` with helpers: `load_registry()`, `get_entry()`, `register()`, `promote()`, `list_champions()`
- [x] DDL migration for `sub_model_versions_used VARIANT` column on `daily_model_predictions` — `scripts/ddl/daily_model_predictions_add_sub_model_versions.sql`
- [x] Promotion-status state machine documented in YAML header: `pending → challenger → champion → deprecated`; only one champion per domain; auto-deprecation of prior champion on promotion

Acceptance Criteria:
- [x] Registry YAML exists with five placeholder entries and schema comment block
- [x] Helper module unit tests: 19/19 passing (`betting_ml/tests/test_sub_model_registry.py`)
- [x] `sub_model_versions_used` DDL migration written — **run `scripts/ddl/daily_model_predictions_add_sub_model_versions.sql` in Snowflake to apply**
- [x] State-machine documented in `sub_model_registry.yaml` header comments

---

### 2.3 — Sub-model evaluation harness (standalone) ✅

**Scope:** Each sub-model is evaluated on its **own** predictive target. The harness measures how well a sub-model's signal predicts the target it was trained to predict. It does **not** retrain or compare against the existing monolithic production models — those remain a separate concern, and the rolled-up Layer 3 aggregation models that consume sub-model signals are out of scope for this story.

**Evaluation modes the harness must support:**

1. **Standalone target-prediction quality**: temporal walk-forward CV. For regression targets (run_env predicting total_runs, offense predicting team runs scored, starter predicting xwOBA-against): MAE, RMSE, Pearson r, Spearman r. For binary targets (none in Phase 9 sub-models initially): AUC, Brier, log-loss.
2. **Calibration**: reliability diagram for regression by predicted-value decile (actual mean vs. predicted mean per bucket).
3. **Stability**: season-by-season metric breakdown to detect coverage-driven or regime-driven regressions.
4. **Version comparison**: champion-vs-challenger within the sub-model space (e.g., `run_env_v1` vs `run_env_v2`).
5. **Partial-coverage handling**: two modes for signals only available in part of the training window (bat tracking 2023-07+ being the canonical case):
   - `drop` — training rows without signal are excluded entirely
   - `impute_with_indicator` — NULL imputed to mean + boolean `signal_available` column added

**What the harness explicitly does NOT do:**

- Does not import or call `train_elasticnet_prod.py`, `train_total_runs_prod.py`, or `train_run_diff_prod.py`
- Does not modify `feature_pregame_game_features` or any monolithic-model feature pipeline
- Does not compute "incremental contribution to the production home_win model" — that comparison is handled in a different layer when Layer 3 aggregation models exist

Tasks:
- [x] Write `betting_ml/scripts/evaluate_sub_model.py` with CLI: `--name`, `--compare`, `--coverage-mode drop|impute_with_indicator`, `--target-window YYYY-YYYY`, `--output-dir`
- [x] Walk-forward CV via `all_season_splits()` — regression (MAE/RMSE/Pearson r/Spearman r) and binary (Brier/log-loss/AUC) target types detected from `cv_metric` in registry
- [x] Calibration: reliability diagram (predicted-value decile buckets), ECE scalar
- [x] Season-stability table: per-season metric breakdown on full eval window
- [x] Version comparison mode: both models evaluated on same window, delta table reported
- [x] Output convention: `models/sub_models/<name>/evaluation_<ts>.json` + `.md`
- [x] Forbidden-import AST check: `PASS — no forbidden imports` confirmed via `ast.walk`

Acceptance Criteria:
- [x] Script written at `betting_ml/scripts/evaluate_sub_model.py`; runs end-to-end given registry entry + artifact + signal rows (requires mart provisioned in 2.1)
- [x] Output report contains: target description, CV aggregate metrics, per-fold table, season-stability table, calibration table
- [x] AST check verified: script does NOT import `train_elasticnet_prod`, `train_total_runs_prod`, or `train_run_diff_prod`
- [x] Version comparison mode produces side-by-side metric table with delta column
- [x] Both `drop` and `impute_with_indicator` coverage modes implemented

---

### 2.4 — Type-2 SCD foundation for feature & sub-model output layers

**Strategic intent:** Long-term, we want point-in-time reproducibility of every model prediction. Today's feature marts overwrite state (latest-only) — making it impossible to answer "what did the system see at prediction time T?" Type-2 SCDs at the feature and sub-model output layers solve this by preserving every state change with `valid_from` / `valid_to` / `is_current` columns, enabling AS-OF queries for historical re-runs, re-training, and CLV backtesting.

**Phase 9 scope (this story):**

- Define the SCD-2 column convention and pattern
- Apply SCD-2 to the **new** sub-model output mart (`mart_sub_model_signals`) from day one — zero migration cost
- Add `computed_at` to all new feature marts created in Stories 2.5–2.9 (born SCD-2-ready even if `valid_to`/`is_current` aren't actively maintained yet)
- Decision: dbt snapshots vs custom incremental SCD-2 macros — pick one and document
- Write the point-in-time / AS-OF join pattern documentation with a worked example
- Identify priority list for migrating **existing** feature marts (lineup, weather, injury status, market state, projected starter) and capture as a separate future epic

**Phase 9 scope explicitly excludes:**

- Migrating existing `feature_pregame_*` marts to SCD-2 (deferred to a future SCD migration epic — large scope, multi-mart)
- Migrating existing rolling-stat marts in `mart_*` to SCD-2 (deferred)
- Building historical CLV reconstruction infrastructure (deferred, depends on completed SCD migration)

**SCD-2 column convention:**

```
valid_from      TIMESTAMP_NTZ NOT NULL  -- when this row's state became active
valid_to        TIMESTAMP_NTZ NULL      -- when superseded by a newer state; NULL when current
is_current      BOOLEAN NOT NULL        -- duplicates (valid_to IS NULL) for query convenience
record_hash     TEXT NOT NULL           -- MD5 of the natural-key columns + payload; used to detect state changes
computed_at     TIMESTAMP_NTZ NOT NULL  -- when the dbt run materialized this row
```

**Point-in-time query pattern (canonical worked example):**

```sql
-- "What was the run_env_signal for game X as known at prediction time T?"
select signal_value
from baseball_data.betting.mart_sub_model_signals
where game_pk = :game_pk
  and signal_name = 'run_env_signal'
  and sub_model_version = 'v1'
  and valid_from <= :prediction_ts
  and (valid_to > :prediction_ts or valid_to is null)
qualify row_number() over (
    partition by game_pk, signal_name, sub_model_version
    order by valid_from desc
) = 1;
```

Tasks:
- [ ] Write a short design doc `quant_sports_intel_models/baseball/scd2_convention.md` covering: column definitions, change-detection rule (`record_hash` diff triggers a new row + close-out the prior), out-of-order arrival policy, deletion semantics (soft via `valid_to`, never DELETE)
- [ ] Decide dbt snapshots vs custom SCD-2 macros. **Recommendation: custom macros.** dbt snapshots are simpler but inflexible (single hash strategy, no compound natural keys per row, awkward for incremental marts at our scale). Custom macros let us define a reusable `scd2_merge(natural_key_cols, payload_cols)` pattern. Document the decision either way.
- [ ] Implement the chosen SCD-2 mechanism for `mart_sub_model_signals` (Story 2.1)
- [ ] Add SCD-2 columns to the new feature marts created in Stories 2.6 and 2.9 (no historical migration — just born with the columns)
- [ ] Add the AS-OF query pattern to the same design doc with the worked example above
- [ ] Capture future SCD migration scope as Epic 15 placeholder: "Migrate existing feature marts to SCD-2 (lineup state, weather, injury, market state, projected starter)" — priority order based on volatility (lineup highest, park factors lowest)

Acceptance Criteria:
- [ ] `mart_sub_model_signals` populates `valid_from`, `valid_to`, `is_current`, `record_hash` correctly: inserting a new signal value for an existing `(game_pk, signal_name, sub_model_version)` closes the prior row (`valid_to = current_timestamp`, `is_current = false`) and inserts a new current row
- [ ] AS-OF query pattern returns the historically-correct value when run against a row set that has been updated multiple times
- [ ] `scd2_convention.md` design doc exists in the repo
- [ ] Decision (snapshots vs custom macros) is documented with reasoning
- [ ] Epic 10 placeholder added to this implementation guide with the existing-mart migration priority list
- [ ] All new marts created in Stories 2.6 and 2.9 include the five SCD-2 columns from the outset

---

### 2.5 — Run environment feature readiness

**What exists:** Park features, weather features, umpire features, team/starter opponent-control features all in `feature_pregame_game_features`. `total_runs` training label in `mart_game_results`.

**What's missing:** Confirmation of pre-2022 weather backfill coverage. The data mart inventory marks this as "Unknown."

Tasks:
- [ ] Query `baseball_data.statsapi.weather_raw`: count non-null rows by season. Output a coverage table
- [ ] Decide training window:
  - If pre-2022 coverage ≥ 80% of outdoor games: use 2016+ window with normal NULL handling (domes always NULL — handled correctly already)
  - If pre-2022 coverage is 30–80%: use 2018+ or 2020+ window, document the truncation
  - If pre-2022 coverage < 30%: restrict to live-ingestion era only (~2023+) and document the tradeoff
- [ ] Document the chosen training window in `sub_model_registry.yaml` under `run_env_v1.training_window`
- [ ] Validate the training-dataset query returns clean rows for the chosen window and joins correctly to opponent-quality control features

Acceptance Criteria:
- [ ] Weather coverage table by season is in the registry notes or a coverage report
- [ ] Training window decision is explicit and documented (not implicit)
- [ ] Sample training-dataset query returns the expected row count for the chosen window with no schema errors
- [ ] No new feature mart created — all inputs flow from existing master feature table

**Training target:** `total_runs` from `mart_game_results`. Version 1 — direct prediction with team-offense, starter-quality, and bullpen-quality features as opponent controls. No market features.

---

### 2.6 — Offensive quality feature mart gaps

**What exists:** `feature_pregame_lineup_features` (~40 cols per side). `stg_fangraphs__zips_hitting` fully populated 2015–2026 with `MLBAM_BATTER_ID` joinable. `stg_statsapi_player_injury_status` exists. `INJURY_ADJ_AVG_WOBA_30D` and `INJURY_ADJ_AVG_XWOBA_30D` are present in the lineup feature mart.

**What's missing (confirmed via Snowflake column inventory):**
- ZiPS projected wRC+, OBP, SLG, K%, BB%, ISO at lineup level — not joined into the lineup feature mart
- Lineup depth score (bottom 3 batters' projected wOBA, weighted by expected PA) — not present
- Lineup entropy / concentration metric — not present
- Lineup IL filtering — partially handled via the two injury-adjusted columns; needs spot-check

Tasks:
- [ ] Extend `feature_pregame_lineup_features` to join `stg_fangraphs__zips_hitting` via `dim_fangraphs_player_xref` on MLBAM ID. Add: `{side}_zips_lineup_avg_wrc_plus`, `{side}_zips_lineup_avg_woba_proxy` (from `0.7 * PROJ_OBP + 0.3 * PROJ_SLG` or similar), `{side}_zips_lineup_avg_k_pct`, `{side}_zips_lineup_avg_iso`
- [ ] Use current-season projection with prior-season fallback for player-seasons missing a current ZiPS row
- [ ] Add `{side}_lineup_depth_score` = average projected wOBA of slots 7–9, weighted by expected PA
- [ ] Add `{side}_lineup_entropy` = Shannon entropy of slot-wise projected wOBA distribution (captures lineup concentration)
- [ ] Spot-check IL filtering: pick 5 historical games with known IL-active batters and confirm they do not inflate lineup quality scores
- [ ] **Rookie cold-start handling (defensive — pending Epic 14 MiLB data):**
  - Add `{side}_lineup_rookie_count`: number of lineup slots with < 200 MLB career PAs
  - Add `{side}_lineup_rookie_pa_share`: expected PA-weighted share of the lineup that is rookie-status (signals lineup-quality uncertainty)
  - For rookie batters, regress 30-day rolling MLB stats toward archetype-mean (if cluster assignment exists) or league-mean (if not). Use a Bayesian shrinkage prior: posterior = (PA / (PA + k)) × observed + (k / (PA + k)) × prior_mean with k = 200
  - Confirm ZiPS hitting projections cover ≥ 80% of debut-season rookies — if so, projection-side features fill the gap for most call-ups even without MLB rolling history
  - Document the regression-to-mean policy in the registry notes for `offense_v1`
- [ ] Add SCD-2 columns (per Story 2.4 convention) — born SCD-2-ready
- [ ] Validate `dbtf build --target dev --select feature_pregame_lineup_features` completes

Acceptance Criteria:
- [ ] New columns present and non-null for ≥ 90% of games in the 2021–2026 training window
- [ ] Prior-season fallback verified: a player with no current-season ZiPS row but a prior-season row gets the prior-season value
- [ ] IL spot-check confirms no positive inflation from inactive players
- [ ] `dbtf build` clean
- [ ] Mart includes the five SCD-2 columns from Story 2.4

**Training target:** Team runs scored per game (one observation per `(game_pk, side)`) from `mart_game_results`. Version 1 — with opponent starter/bullpen quality controls. No market features.

---

### 2.7 — Starter suppression target registration (no mart work)

**Decision based on data findings:** `MART_STARTING_PITCHER_GAME_LOG` already contains every column needed as a starter-model training target. No new mart is required.

Available columns (confirmed in Snowflake on 2026-05-12):
- `XWOBA_AGAINST` (primary target — 50,292 / 50,293 non-null, 2015–2026)
- `STRIKEOUTS`, `WALKS`, `BATTERS_FACED` → K%/BB% computable inline
- `OUTS_RECORDED`, `INNINGS_PITCHED` → depth target
- `AVG_FASTBALL_VELO` — bonus signal for matchup model cross-features
- `RUNS_ALLOWED`, `HITS_ALLOWED` — available but noisier than xwOBA

**ZiPS pitching xFIP decision:** `STG_FANGRAPHS__ZIPS_PITCHING.PROJ_XFIP` is 100% NULL across all seasons. Drop `STARTER_PROJ_XFIP` from training feature lists (not impute). Use `PROJ_FIP`, `PROJ_ERA`, `PROJ_K_PCT`, `PROJ_BB_PCT` instead — all are fully populated. Do not block this Epic on a FanGraphs ingestion fix; capture as a future low-priority story.

Tasks:
- [ ] Register the starter target in `sub_model_registry.yaml` under `starter_v1.target`:
  ```yaml
  target:
    source_table: baseball_data.betting.mart_starting_pitcher_game_log
    primary_column: xwoba_against
    auxiliary_columns: [k_per_bf, bb_per_bf, ip]
    grain: pitcher_id_game_pk
  ```
- [ ] Add a future-work note: "Fix `stg_fangraphs__zips_pitching.proj_xfip` ingestion (low priority)" — document in `idea_notes.md` or equivalent
- [ ] Confirm leakage guard: training queries against `mart_starting_pitcher_game_log` must use `game_date < model_run_date` strictly

Acceptance Criteria:
- [ ] Registry entry for `starter_v1` has full target definition
- [ ] xFIP exclusion documented; substitute features explicitly listed
- [ ] Leakage guard documented in the registry notes field

**Training targets:** Primary — `xwoba_against`. Auxiliary — `strikeouts / batters_faced`, `walks / batters_faced`, `outs_recorded / 3` (IP). No market features.

---

### 2.8 — Bullpen game outcomes mart (deferred — not on Epic 2 critical path)

**Status:** Conditionally needed. Bullpen v1.0 is a rules-based composite that uses **only** existing pre-game features (`mart_bullpen_leverage`, `mart_bullpen_workload`, `mart_bullpen_effectiveness`) — no new training target mart required. This story only becomes blocking if/when bullpen v1.1 (supervised calibration) is pursued.

**Sequencing decision:** Defer this story until after Epic 6 v1.0 ships. The v1.0 rules-based signal will be evaluated via Story 2.3 against downstream proxies. If v1.0 evaluation suggests learned weights would materially improve the signal, return to this story to build the supervised target.

**When pursued, the mart specification:**

- Name: `mart_bullpen_game_outcomes`
- Grain: one row per `(game_pk, team)`
- Columns: `bullpen_xwoba_allowed`, `bullpen_xwoba_allowed_next_7d` (forward rolling — used as the supervised v1.1 target to average over single-game leverage variance), `bullpen_era_game`, `bullpen_k_pct`, `bullpen_bb_pct`, `bullpen_ip`, `high_leverage_ip`, `blown_save_flag`
- Materialization: incremental MERGE on `game_date`
- Source: `stg_batter_pitches` joined to identify all non-starter pitching appearances per game; aggregate
- Leakage guard: never joined to any `feature_pregame_*` mart — usage-restricted to training-label queries only

Tasks (pending — do not start until Epic 6 v1.0 ships):
- [ ] Build `mart_bullpen_game_outcomes` per spec above
- [ ] Materialize 2016–2026
- [ ] Document the "supervised v1.1 calibration target = `bullpen_xwoba_allowed_next_7d`" decision in the registry

Acceptance Criteria (when pursued):
- [ ] Mart exists with grain `(game_pk, team)` and all listed columns
- [ ] Complete-game starts show 0 IP bullpen contribution
- [ ] No `feature_pregame_*` mart references this table (leakage guard)
- [ ] SCD-2 columns included per Story 2.4

**Training target (v1.1 only, not v1.0):** `bullpen_xwoba_allowed_next_7d`. No market features.

---

### 2.9 — Matchup cross-feature mart + archetype documentation

**What exists:** `statsapi.batter_clusters`, `statsapi.pitcher_clusters`, `mart_batter_archetype_vs_pitcher_cluster`, `mart_batter_bat_tracking_profile` (2023-07-14+), `mart_pitcher_rolling_stats` (includes fastball velocity), `mart_pitcher_arsenal_summary`.

**What's missing:**
- Cross-feature mart that aggregates lineup bat speed and computes the lineup-vs-starter velocity differential
- Formal archetype cluster definition documentation in the repo (cluster_id / cluster_label / example-player references)

Tasks:
- [ ] Build `feature_pregame_matchup_bat_tracking` with grain `(game_pk, side)`:
  - `{side}_avg_bat_speed` (lineup average from `stg_statsapi_lineups_wide` × `mart_batter_bat_tracking_profile`)
  - `{side}_lineup_bat_speed_std` (uncertainty over the 9 slots)
  - `{side}_bat_speed_vs_opp_starter_fastball_velo` = `{side}_avg_bat_speed - opp_starter_fastball_velo`
- [ ] Born SCD-2-ready (Story 2.4 columns)
- [ ] Add to `feature_pregame_game_features` joins (optional feature block — NULL pre-2023-07-14 is expected and acceptable)
- [ ] Validate joins do not unexpectedly drop pre-2023-07 games
- [ ] Write `quant_sports_intel_models/baseball/archetype_definitions.md`:
  - Batter clusters: query distinct `(cluster_id, cluster_label)` from `statsapi.batter_clusters`, document each with feature-driver explanation and 3 example players
  - Pitcher clusters: same treatment from `statsapi.pitcher_clusters`
  - Document cluster stability: row counts per cluster by season; flag any cluster with < 50 members/season
- [ ] Confirm `mart_batter_archetype_vs_pitcher_cluster` is the canonical training target source for `matchup_v1` (already exists)
- [ ] **Rookie cold-start handling (defensive — pending Epic 14 MiLB data):**
  - Add `{side}_starter_rookie_flag`: true if opposing starter has < 50 MLB career IP
  - Add `{side}_lineup_rookie_in_top_5_flag`: rookie batting in slots 1–5 (high-leverage rookie indicator)
  - For rookie starters, fall back from rolling Statcast/Stuff+ to ZiPS pitching projections (PROJ_FIP, PROJ_K_PCT, PROJ_BB_PCT) — already in scope via Story 2.7 feature list
  - For rookie batters in the lineup, bat-tracking columns will be NULL (not in `mart_batter_bat_tracking_profile`). Treat as `signal_available = false` per Story 2.1 convention rather than imputing — protects matchup model from confident-but-wrong rookie matchup signals
  - Document the rookie fallback policy in the registry notes for `matchup_v1`

Acceptance Criteria:
- [ ] `feature_pregame_matchup_bat_tracking` builds and has non-null bat-speed columns for ≥ 90% of games from 2023-07-15 onward
- [ ] NULL handling for pre-2023-07 games confirmed (no row drops in master feature join)
- [ ] `archetype_definitions.md` exists with cluster definitions, drivers, examples, and stability counts
- [ ] Matchup target source registered in `sub_model_registry.yaml` under `matchup_v1.target`
- [ ] SCD-2 columns included

**Training targets:** wOBA / xwOBA / K% / BB% / hard-hit% by `(batter_archetype, pitcher_archetype)` pair from `mart_batter_archetype_vs_pitcher_cluster`. Population-level — individual batter-vs-starter samples are too sparse. No market features.

---

### Epic 2 dependency sequencing

```
2.1 (storage) ──┐
                ├──► All Epics 3–8 can start once 2.1, 2.2, 2.3, 2.4 ship
2.2 (registry) ─┤
2.3 (eval) ─────┤
2.4 (SCD-2) ────┘

2.5 (run env readiness)        → gate for Epic 3
2.6 (offense / ZiPS wiring)    → gate for Epic 4
2.7 (starter target reg)       → gate for Epic 5  (very light — registry entry only)
2.8 (bullpen mart)             → DEFERRED; not blocking Epic 6 v1.0
2.9 (matchup mart + docs)      → gate for Epic 8 (also needs Epic 7 — archetype revalidation)
```

Stories 2.5–2.9 can run in parallel with 2.1–2.4 since they touch disjoint files.

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
| T.0 — Staging dedup audit | All staging models for affected raw tables confirmed to have correct `qualify row_number()` dedup; synthetic duplicate fixture test passes; hard gate for T.1–T.4 |
| T — Temporal capture foundations | All `scripts/ingest_*.py` are append-only; staging dedupes correctly; inventory corrected; CI grep guard blocking; intraday schedule polling active (T.1.B) |
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
| 14 — MiLB cold-start coverage | AAA Statcast + FanGraphs MiLB ingestion live; rookie call-ups have non-NULL feature coverage within 7 days of debut; prospect rank signal evaluated |
| 15 — SCD-2 migration of existing marts | Lineup state, weather, injury, market state, projected starter migrated to SCD-2; AS-OF query validation on at least one historical game |

---

# Epic 14 — MiLB Cold-Start Coverage

**Goal:** Eliminate the cold-start gap where minor-league call-ups appear as NULL slots in lineup, starter, and matchup features. Bring Baseball Savant AAA Statcast + FanGraphs MiLB leaderboards + prospect rankings into the feature store so that a player called up to the majors has non-NULL feature coverage from day one.

**Why this is its own epic and not part of Epic 2:** This is a Layer 1 data expansion (new sources, new ingestion, ID crossref, multi-year backfill), not sub-model feature readiness. It benefits every downstream consumer — sub-models, future Layer 3 aggregation models, and even the existing monolithic models. Epic 2 ships defensively (rookie indicators, regression-to-mean, ZiPS-only fallback) so sub-models don't wait on this epic.

**Sources confirmed available (per user, 2026-05-12):**
- Baseball Savant — AAA Statcast (Hawkeye in many AAA parks since 2023)
- FanGraphs — minor league leaderboards (rolling rate stats, league-adjusted)
- Prospect rankings — third potential signal source (specific publisher TBD: FG / BA / MLB Pipeline)

---

### 14.1 — Data availability audit

Tasks:
- [ ] Inventory Baseball Savant AAA Statcast: which AAA parks have Hawkeye, what date range, what columns available (pitch type, velocity, xwOBA equivalents, bat tracking?)
- [ ] Inventory FanGraphs MiLB leaderboards: levels covered (AAA, AA, A+, A), seasons available, columns (wRC+, K%, BB%, FIP, etc.), refresh cadence
- [ ] Inventory prospect rankings sources: FanGraphs prospect lists, Baseball America, MLB Pipeline — which is most accessible programmatically, refresh cadence, ranking-numeric vs grade-letter format
- [ ] Produce a coverage report: for each MLB call-up in 2024–2026, how much MiLB pitch-level / rate-stat / ranking data exists in the 12 months prior to debut?

Acceptance Criteria:
- [ ] Coverage report documents what's available per source and what fraction of recent rookies it would cover
- [ ] Go/no-go decision per source documented (AAA Statcast yes/no, FanGraphs MiLB yes/no, prospect rankings — which publisher)

---

### 14.2 — Player ID crossref (MiLB ↔ MLB)

Tasks:
- [ ] Build `mart_player_id_crossref`: maps MLBAM ID ↔ FanGraphs MiLB player ID ↔ Baseball Savant ID ↔ prospect-ranking publisher ID
- [ ] Validate on known recent call-ups: confirm a player like (recent rookie) is correctly linked across all four sources
- [ ] Handle name-collision edge cases (multiple prospects with the same name in the system)
- [ ] Document fallback strategy when a player exists in only some sources

Acceptance Criteria:
- [ ] Crossref mart exists with ≥ 95% link coverage for all MLB players active 2023–2026
- [ ] Spot-check on 10 recent call-ups passes

---

### 14.3 — Baseball Savant AAA Statcast ingestion

Tasks:
- [ ] Write ingestion script `scripts/ingest_savant_aaa.py` mirroring the MLB Savant ingestion pattern
- [ ] Create `baseball_data.savant.aaa_batter_pitches` raw table (parallel structure to MLB `batter_pitches`)
- [ ] Backfill 2023–2026
- [ ] Build dbt staging `stg_savant_aaa_batter_pitches` with the same MD5 surrogate key strategy
- [ ] Add coverage flag: `aaa_data_quality_score` per (player, season) — confirms Hawkeye parks vs non-Hawkeye parks

Acceptance Criteria:
- [ ] AAA pitch-level data ingested for 2023–2026
- [ ] Staging model dedupes correctly
- [ ] Coverage flag identifies high-vs-low-quality player-seasons

---

### 14.4 — FanGraphs MiLB leaderboard ingestion

Tasks:
- [ ] Write ingestion script `scripts/ingest_fangraphs_milb.py` mirroring existing FG ingestion pattern
- [ ] Create `baseball_data.fangraphs.milb_hitting_leaderboard_raw` and `milb_pitching_leaderboard_raw` (mirrors MLB versions, with `level` column: AAA / AA / A+ / A)
- [ ] Backfill: full seasons 2021–2026 (or as far back as FG MiLB coverage is reliable)
- [ ] Build dbt staging `stg_fangraphs__milb_hitting_leaderboard` and `_pitching_leaderboard`

Acceptance Criteria:
- [ ] MiLB leaderboards ingested with `level` discriminator
- [ ] Staging models dedupe per `(fg_player_id, season, level, window_type)`

---

### 14.5 — Prospect rankings ingestion

Tasks:
- [ ] Decision: which publisher (per Story 14.1 audit). Likely FanGraphs prospect lists for consistency with existing FG ingestion.
- [ ] Ingestion script + raw table
- [ ] Schema: `player_id`, `season`, `publisher`, `ranking_overall`, `ranking_position`, `eta_year`, `tool_grades` (hit, power, run, arm, field)
- [ ] Backfill 2020–2026 if available
- [ ] Build staging model

Acceptance Criteria:
- [ ] Prospect rankings table ingested
- [ ] Joinable via player ID crossref from Story 14.2

---

### 14.6 — Career-splicing feature marts

Tasks:
- [ ] Define the blending rule: when a player has both MiLB and MLB history, which level's stats fill which feature?
  - Recommendation: MLB stats take precedence when MLB PA / IP ≥ threshold (200 PA / 50 IP); MiLB stats fill the rolling-window gap when below threshold
  - Add explicit `data_source` indicator columns: `{side}_lineup_avg_woba_data_source` ∈ {`mlb_rolling`, `milb_rolling`, `zips_projection`, `null`}
- [ ] Extend `feature_pregame_lineup_features` to include MiLB-derived columns alongside MLB rolling stats (`{side}_lineup_avg_milb_wrc_plus`, `{side}_lineup_avg_milb_aaa_xwoba`, `{side}_lineup_avg_prospect_ranking`)
- [ ] Extend `feature_pregame_starter_features` similarly for rookie starters
- [ ] Update rookie-handling tasks in Stories 2.6 and 2.9 to consume the new columns instead of pure regression-to-mean (the defensive Epic 2 fallback becomes a backup, not the primary)

Acceptance Criteria:
- [ ] Lineup and starter feature marts have non-NULL coverage for ≥ 90% of rookie debuts within 7 days of debut date
- [ ] `data_source` indicator columns let downstream models / dashboards explain which feature path produced a given prediction
- [ ] Regression-to-mean from Epic 2 still applies as the final fallback when all data sources are NULL

---

### 14.7 — Validate downstream model impact

Tasks:
- [ ] Run the sub-model evaluation harness (Story 2.3) against `offense_v1` and `starter_v1` with MiLB-augmented features
- [ ] Compare metric deltas on a subset of games featuring rookie-heavy lineups (e.g., games where `lineup_rookie_count ≥ 2`)
- [ ] Promote MiLB-augmented sub-model versions if evaluation shows meaningful improvement on the rookie subset

Acceptance Criteria:
- [ ] Evaluation report comparing sub-models with vs. without MiLB features on the rookie-heavy game subset
- [ ] If improvement is meaningful, MiLB-augmented sub-model versions are promoted

---

# Epic 15 — SCD-2 Migration of Existing Feature Marts

**Goal:** Extend the SCD-2 convention from Story 2.4 to existing feature marts so the entire feature store supports point-in-time reproducibility. Unlocks historical CLV reconstruction and rigorous walk-forward replay.

**Hard prerequisite:** Epic T must complete first. Epic 15's backfill strategy is `load_id` replay over append-only raw tables — if any source raw table still uses MERGE patterns, its historical state has been overwritten and cannot be reconstructed.

**Parallelization:** Epic 15 runs in parallel with Track B sub-model development (Epics 3–8). It does **not** block sub-model work — sub-models train on aggregate historical outcomes, not intra-day state transitions.

---

### Backfill feasibility per mart (post-Epic T)

Once Epic T converts all raw ingestion to append-only, every mart on the priority list can be backfilled via load-id replay **except where the underlying raw was MERGE-pattern before Epic T converted it**. For pre-Epic-T history, those marts get "current-state-from-Epic-T-conversion-date forward" semantics.

| Mart | Raw source | Pre-Epic-T pattern | Backfill strategy |
|---|---|---|---|
| Lineup state | `monthly_schedule` | MERGE — **pre-T history NOT recoverable** | Full reconstruction from T.1 conversion date forward; aggregate snapshot for prior data |
| Market state / odds | `oddsapi.*`, `parlayapi.*`, `odds_snapshots_historical` | Append-only ✓ | **Full historical replay possible** — backfill 2021+ |
| Weather forecasts | `weather_raw` | MERGE — **pre-T history NOT recoverable** | Reconstruction from T.2 forward; current-snapshot-only prior |
| Injury status | `player_transactions` | Append-only ✓ (per transaction_id) | **Full historical replay possible** — backfill from raw inception |
| Projected starter | `monthly_schedule` | MERGE — same constraint as lineup | Same as lineup state |
| Park factors | External / computed | Stable / low volatility | Trivial — annual refresh only; minimal SCD value |
| Public betting | `public_betting_raw` | MERGE — **pre-T history NOT recoverable** | Reconstruction from T.3 forward |
| Umpire assignments | `umpire_game_log` | MERGE — but low volatility | Reconstruction from T.4 forward; minimal pre-T loss |

Key insight: **odds and injury** can be reconstructed historically in full because their raw layers were already append-only. **Lineup, weather, projected starter, public betting** have partial history — pre-Epic-T data is lost, but Epic T stops the bleeding and future capture is full.

---

### Priority order (highest volatility × highest downstream value)

1. **Market state / odds snapshots** — fully replayable from raw. Highest leverage for CLV reconstruction.
2. **Lineup state** — partial history (Epic T date forward), but highest single-day predictive value.
3. **Injury status** — fully replayable from `player_transactions`. Modest standalone value, high combinatorial value with lineup state.
4. **Projected starter** — same constraint as lineup state.
5. **Weather forecasts** — partial history. Useful for run-environment sub-model temporal validation.
6. **Public betting / umpire / park** — low priority; batch at the end.

---

### Tasks (per-mart substories created when each kicks off)

For each mart in priority order:
- [ ] Define natural key, payload columns, change-detection hash
- [ ] Choose backfill strategy: full historical replay (if raw is append-only end-to-end) vs. forward-only (if pre-Epic-T raw was MERGE-pattern)
- [ ] Implement SCD-2 merge using the macro from Story 2.4
- [ ] Validate AS-OF queries against historical samples
- [ ] Document the historical-coverage cutoff date in the mart's dbt model comments

Final-epic deliverable:
- [ ] Build historical CLV reconstruction script that reruns a sample of historical predictions using only feature state available at the original `prediction_ts` — confirm the original prediction is reproduced for fully-replayable marts and document the caveat for partial-coverage marts

Acceptance Criteria:
- [ ] All 8 marts in the table above migrated to SCD-2
- [ ] AS-OF query validation passes for at least one historical game per mart
- [ ] Historical CLV reconstruction script reproduces 3 sample historical predictions exactly using fully-replayable marts (odds + injury)
- [ ] Per-mart historical-coverage cutoff documented in model comments and `baseball_data_mart_inventory.md`
