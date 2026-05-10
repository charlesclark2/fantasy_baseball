# Parlay API Endpoint Mapping
### Epic 0, Task 0.1 — Migration from The Odds API

Status: Complete (live-tested 2026-05-09)
Produced: 2026-05-09
References: [implementation_guide.md](baseball/implementation_guide.md), [Parlay API Docs](https://parlay-api.com/docs)

---

## 1. Current Odds API Usage

### 1.1 Daily automated (GitHub Actions `daily_ingestion.yml`)

| Step | Subcommand | Endpoint | Markets | Regions | Credits/run |
|---|---|---|---|---|---|
| Ingest Odds API events | `events` | `/v4/sports/baseball_mlb/events` | — | — | 1 |
| Ingest Odds API odds | `odds` | `/v4/sports/baseball_mlb/odds` | `h2h`, `totals` | `us`, `us2` | 4 (2 markets × 2 regions) |

**Daily automated total: ~5 credits/day → ~150 credits/month**

### 1.2 Manual only (not in any workflow)

| Subcommand | Endpoint | Purpose | Credits/call |
|---|---|---|---|
| `historical-events` | `/v4/historical/sports/baseball_mlb/events` | Backfill event records for a date range | 1 per date |
| `historical-odds` | `/v4/historical/sports/baseball_mlb/odds` | Backfill historical odds snapshots | 1 per (date × market) |

These subcommands exist in `odds_api_ingestion.py` and have been used for one-time backfills. They are not scheduled.

### 1.3 Script constants (current)

```python
ODDS_API_BASE_URL    = "https://api.the-odds-api.com/v4"
EVENTS_ENDPOINT      = "/sports/baseball_mlb/events"
ODDS_ENDPOINT        = "/sports/baseball_mlb/odds"
HIST_EVENTS_ENDPOINT = "/historical/sports/baseball_mlb/events"
HIST_ODDS_ENDPOINT   = "/historical/sports/baseball_mlb/odds"

DEFAULT_MARKETS      = ["h2h", "totals"]
DEFAULT_REGIONS      = ["us", "us2"]
DEFAULT_ODDS_FORMAT  = "american"
```

Auth: `?apiKey=KEY` query parameter. Script also supports a `ODDS_API_STARTER_KEY` fallback for the live endpoints (starter tier does not support `/historical/`).

Response credit headers used: `x-requests-used`, `x-requests-remaining`.

---

## 2. Parlay API Endpoint Mapping

### 2.1 Migration compatibility

**Parlay API is URL-surface compatible with The Odds API for core endpoints.**

```
Old base: https://api.the-odds-api.com/v4
New base: https://parlay-api.com/v1
```

The endpoint paths (`/sports/baseball_mlb/events`, `/sports/baseball_mlb/odds`, `/historical/...`) are the same. A client that changes only the base URL and API key should work for the core live endpoints.

### 2.2 Live endpoint mapping (daily automated)

| Odds API endpoint | Parlay API equivalent | Path change | Credits | Verified compatible |
|---|---|---|---|---|
| `/v4/sports/baseball_mlb/events` | `/v1/sports/baseball_mlb/events` | Base URL only | 1 | ✅ Tested — identical response shape |
| `/v4/sports/baseball_mlb/odds` | `/v1/sports/baseball_mlb/odds` | Base URL only | 1 per call | ✅ Tested — identical bookmakers/markets structure; adds `canonical_event_id` field |

**Live odds response note:** Parlay API adds a `canonical_event_id` field not present in the Odds API response. The `bookmakers → markets → outcomes` nesting is identical. American odds format requires `?oddsFormat=american` (same param name).

**Known data quality issue — `commence_time` in `/events` response (tested 2026-05-10):** All games in a daily slate are returned with the same `commence_time` value regardless of actual game start times. Verified against a 15-game slate where real start times ranged from 11:15 AM CDT to 6:20 PM CDT — all returned as `2026-05-10T19:00:00Z`. Do not use `commence_time` from `mlb_events_raw` for scheduling logic or as a reliable game start time. Use `stg_statsapi_games.game_datetime` as the authoritative source. The `ingestion_ts` date is a safe proxy for "games of this date" in any query that auto-resolves event IDs.

### 2.3 Historical endpoint mapping (manual backfills)

> **Tested 2026-05-09** — results differ significantly from Odds API behavior. Read carefully before building historical backfill logic.

| Odds API endpoint | Parlay API equivalent | Schema compatible | Notes |
|---|---|---|---|
| `/v4/historical/sports/baseball_mlb/events` | ❌ **Path does not exist** | N/A | Returns 404. Replaced by `/v1/historical/sports/baseball_mlb/matches` (different schema — see below) |
| `/v4/historical/sports/baseball_mlb/odds` | `/v1/historical/sports/baseball_mlb/odds` | ✅ Compatible | Tested. Same bookmakers/markets structure as live odds. Requires `oddsFormat=american`. `last_update` is set to game `commence_time`, not the actual snapshot timestamp. |

#### Historical `/matches` endpoint (replaces `/events`)

Path: `/v1/historical/sports/baseball_mlb/matches?date=YYYY-MM-DD`

Returns a **flat, per-bookmaker-source array** — one row per game per book. Schema is completely different from the Odds API historical events endpoint and from `mlb_events_raw`. Fields include:

```json
{
  "game_date": "2026-05-09",
  "sport_key": "baseball_mlb",
  "home_team": "Arizona Diamondbacks",
  "away_team": "New York Mets",
  "source": "bet365_an",
  "home_score": null,
  "away_score": null,
  "result": "",
  "season": "2026",
  "has_odds": true,
  "odds": {
    "home_ml": 110,
    "away_ml": -135,
    "draw_ml": null,
    "home_decimal": 2.10,
    "away_decimal": 1.74,
    "draw_decimal": null
  }
}
```

**Key differences from Odds API `/historical/events`:**
- Flat per-source rows instead of nested bookmakers array
- Includes `home_score`, `away_score`, `result`, `has_odds` (useful — replaces our join to Retrosheet for results)
- `source` suffix `_an` indicates ActionNetwork feed; book names differ from live odds keys (e.g., `bet365_an` vs `bet365`)
- ML-only odds in the `odds` object — no totals line in this endpoint
- `has_odds` boolean flag built-in (matches our `feature_pregame_game_features.has_odds` concept)

**Migration decision:** `/historical/matches` is not a drop-in replacement for our existing historical events ingestion. Ingest it to a separate raw table (`parlayapi.mlb_matches_raw`) and consider it an additional enrichment source (scores + results + ML history) rather than a structural replacement.

### 2.4 Line-Movement Endpoint (New — No Odds API Equivalent)

Path: `/v1/sports/baseball_mlb/line-movement?eventId={event_id}`

Credits: 5 per call. No `markets` filter — returns all markets for the event.

**Response shape:**

```json
{
  "event_id": "9d21fc08f3c42b863af6c89b1b15b7c5",
  "home_team": "Miami Marlins",
  "away_team": "Washington Nationals",
  "source": "fanduel",
  "player": "Daylen Lile",
  "market_key": "moneyline",
  "line": 0.0,
  "count": 26,
  "opening_over": -130,
  "current_over": -135,
  "over_movement": -5,
  "opening_under": 110,
  "current_under": 115,
  "hours_tracked": 0.65,
  "snapshots": [
    {
      "timestamp_ms": 1778363284959,
      "time": "2026-05-09T21:48:04.959000+00:00",
      "over_price": -130,
      "under_price": 110,
      "line": 0.0
    }
  ]
}
```

**Market keys observed (live test):** `moneyline` (= h2h), `player_to_hit_a_home_run`, `player_strikeouts`, `player_total_bases`, and 20+ player prop keys. One row per (source × market × player).

**Why this matters for CLV (Epic 12):** The endpoint provides `opening_over` / `current_over` / `over_movement` at the top level — opening and closing line in a single response without a second API call. The `snapshots` array provides the full intraday price history for model features (e.g., "did sharp money move this line in the 4 hours before game?"). This is the most valuable new Parlay API capability for the CLV meta-model.

**Usage consideration:** At 5 credits/call and 15 games/day, fetching line-movement for all daily games costs ~75 credits/day (~2,250/month). This exceeds the Free tier (1,000/month); Starter ($5/mo, 20,000 credits) covers it comfortably.

### 2.5 Auth differences

| Property | The Odds API | Parlay API |
|---|---|---|
| Auth method | `?apiKey=KEY` query param | `X-API-Key: KEY` header (recommended) or `?apiKey=KEY` |
| Dual-key pattern | Yes — starter key + main key fallback | No — single key per tier |
| Credit exhaustion response | HTTP 429 | HTTP 403 |
| Credit headers | `x-requests-used`, `x-requests-remaining` in response headers | `x-request-id`, `x-response-time` in headers only — **no credit counter headers exposed** |

**Credit header correction (tested):** Parlay API does NOT return `x-requests-used` or `x-requests-remaining` in response headers, contrary to initial docs assumption. Only `x-request-id` (trace ID) and `x-response-time` are returned. Credit tracking must be done via the API dashboard or by counting calls in the ingestion script.

**Migration impact on `odds_api_ingestion.py`:**
- `?apiKey=` query param still works — no breaking change
- Switch to `headers={"X-API-Key": key}` (recommended style)
- Remove the starter-key / main-key fallback logic (not applicable to Parlay API)
- Update `source_system` metadata value from `'the_odds_api'` to `'parlay_api'`
- Update base URL constant and env var name (`PARLAY_API_KEY`)
- Remove `x-requests-used/remaining` header parsing — replace with call counter logging

---

## 3. Pricing Comparison

| Tier | Odds API (approx.) | Parlay API | Credits/month |
|---|---|---|---|
| Free | None | $0 | 1,000 |
| Entry | ~$10–20/mo | $5/mo (Starter) | 20,000 |
| Mid | ~$50/mo | $20/mo (Pro) | 100,000 |
| High | ~$99+/mo | $40/mo (Business) | 1,000,000 |

**Our usage at Free tier:** ~150 credits/month for daily automated runs. Free tier covers this with 850 credits/month remaining for manual backfills and testing. **Starter tier ($5/mo) is the safe choice** — 20,000 credits/month provides ample headroom for historical backfills and any expanded market fetching.

---

## 4. New Parlay API Capabilities (Not in The Odds API)

These endpoints are not currently used and are not required for the migration. Documented here as future opportunities.

| Endpoint | Credits | Description | Relevant Epic |
|---|---|---|---|
| `/sports/{key}/line-movement?eventId={id}` | 5 | Full opening-to-current price history per book per market; `opening_over/under`, `over_movement`, snapshots array | **Epic 12 (CLV)** — highest priority new capability |
| `/sports/{key}/props` | 3 | Player props from 13+ books including DFS platforms (PrizePicks, Underdog, Betr) | Fantasy integration (Phase 10+) |
| `/consensus` | 3–10 | Best/worst prices and median odds per market across all books | Could augment `mart_bookmaker_disagreement` — evaluate after migration |
| `/ev` | 3–10 | EV edge percentage vs. Pinnacle baseline | Directly relevant to Epic 12 (CLV meta-model); revisit when 500+ CLV games exist |
| `/arbitrage` | 3–10 | Cross-book arbitrage opportunities | Not aligned with pregame model approach; low priority |
| `/historical/sports/{key}/matches` | 2 | Flat per-source game results with scores, ML odds, `has_odds` flag | Could enrich game results pipeline — separate from odds backfill |
| `/historical/sports/{key}/closing-odds` | 5 | Final pregame prices (real closing lines, not snapshot) | CLV denominator — use instead of last snapshot for true CLV |
| `/live` | 1 | In-progress game odds (sub-10s freshness) | Not relevant — pregame model only |
| `/live/sse` | 7/event | Point-by-point live SSE stream | Not relevant — pregame model only |
| `wss://parlay-api.com/ws/odds/{sport_key}` | Flat (Business tier) | Real-time push on every price change; sub-5s latency; `initial_state` frame on connect (last 500 props); filter to single game via `subscribe` message; heartbeat every 30s | **Future — full-stack application / real-time alerting**. No per-frame credit cost on Business tier. Requires always-on persistent process — incompatible with current GitHub Actions batch architecture. Revisit when real-time alerting or live betting product is scoped. |

**Highest priority new capabilities:**
1. **`/line-movement`** — tested, working, directly enables CLV meta-model. Opening + closing + full snapshot history in a single call per game. Adds ~75 credits/day.
2. **`/historical/closing-odds`** — true closing lines (not snapshot-at-close). Critical for accurate CLV denominator; needs a test call.
3. **`/consensus`** — could replace multi-book aggregation in `mart_bookmaker_disagreement`. Evaluate after migration is stable.

---

## 5. Capability Gaps (Odds API features without confirmed Parlay equivalent)

> Updated after live testing on 2026-05-09.

| Feature | Odds API | Parlay API | Risk | Status |
|---|---|---|---|---|
| Starter-key tier for live endpoints | Yes — separate key for live-only access at lower cost | Not documented | Low — remove the fallback logic | Confirmed not needed |
| Historical events endpoint | `/v4/historical/sports/baseball_mlb/events` (confirmed working) | `/v1/historical/sports/baseball_mlb/events` → **404** | **High** — path does not exist; must use `/matches` instead with different schema | ✅ Tested — use `/matches` |
| `commenceTimeFrom`/`commenceTimeTo` on historical | Supported for date-range scoping | Parlay historical uses `date=YYYY-MM-DD` (single date, not range) | **Medium** — backfill loops must iterate day-by-day; cannot pass a date range in one call | Action: update backfill loop logic |
| Credit counter headers | `x-requests-used`, `x-requests-remaining` in every response | Not present — only `x-request-id` and `x-response-time` returned | Low — track credits via call counter in script | ✅ Confirmed — remove header parsing |
| Multiple regions in one call | Separate call per region (same behavior) | Assumed same | Low | Unverified but low risk |
| American odds format on historical | `oddsFormat=american` query param | ✅ Same — `oddsFormat=american` confirmed working | None | ✅ Tested |

---

## 6. Migration Scope Summary

### Minimal viable migration (daily automated pipeline only)

Changes required in `parlay_api_ingestion.py` relative to `odds_api_ingestion.py`:

1. `BASE_URL = "https://parlay-api.com/v1"` (was `"https://api.the-odds-api.com/v4"`)
2. `os.environ.get("PARLAY_API_KEY")` (was `ODDS_API_KEY`)
3. Remove dual-key (starter/main) fallback logic — single key only
4. Auth: switch to `headers={"X-API-Key": key}` instead of `params={"apiKey": key}` (optional but recommended)
5. `source_system = 'parlay_api'` (was `'the_odds_api'`) in all insert functions
6. `process_name = 'parlay_api_ingestion.py'` in insert functions
7. Target tables: `baseball_data.parlayapi.*` (new schema — existing `oddsapi` tables untouched)
8. Capture `x-requests-last` header (new; add alongside existing `x-requests-used/remaining`)

**Historical subcommands:** Port `historical-events` and `historical-odds` after verifying the `/historical/` path works. Not required for the initial daily cutover.

### What does NOT need to change

- Snowflake write logic (insert functions, MERGE pattern, VARIANT handling)
- Response parsing (`raw_json`, extracted relational fields, `bookmakers_count`)
- All CLI subcommand structure and argument names
- dbt staging model output schema — `stg_parlayapi_odds` must match `stg_oddsapi_odds` columns exactly (see Epic 0.4)
- Rate-limit retry logic
- Logging

---

## 7. Recommended Next Steps

> Updated after live endpoint testing on 2026-05-09.

**Already resolved (no longer blockers):**
- ✅ Live endpoints compatible — confirmed
- ✅ Historical odds compatible — confirmed with `oddsFormat=american`
- ✅ Credit headers — confirmed absent; ingestion script must use call counter instead
- ✅ Line-movement endpoint — confirmed at `/v1/sports/baseball_mlb/line-movement?eventId={id}`

**Still needed before historical backfill:**
1. **Test `/historical/closing-odds`** — call `/v1/historical/sports/baseball_mlb/closing-odds?date=2026-05-08`; confirm schema and whether it provides true closing lines vs. last snapshot.
2. **Test `date` param scoping** — confirm `/historical/odds` uses `date=YYYY-MM-DD` (single date), not `commenceTimeFrom`/`commenceTimeTo`. Backfill loops must iterate day-by-day.

**Migration work (unblocked, ready to implement):**
3. **Implement Epic 0.2** — DDL for `baseball_data.parlayapi` schema and raw tables. Add `mlb_matches_raw` table (for `/matches` endpoint) alongside `mlb_events_raw` and `mlb_odds_raw` equivalents.
4. **Implement Epic 0.3** — `parlay_api_ingestion.py` with the 8 targeted changes; remove credit header parsing; add call counter logging.
5. **Choose tier** — Free tier (1,000/month) covers daily automated (events + odds = ~150/month). Add line-movement daily fetch: ~75 credits/day × 30 = 2,250/month total. **Starter ($5/mo, 20,000 credits) required if enabling line-movement.**

**Longer-term (post-migration, Epic 12):**
6. **Line-movement daily ingestion** — fetch for all daily game `eventId`s after odds ingestion. Store snapshots as VARIANT in new `mlb_line_movement_raw` table. Enables CLV denominator and sharp-money features.
7. **`/ev` and `/consensus` evaluation** — test after migration is stable with ≥50 has_odds games available.
