# Performance Page Redesign — Design Doc

**Status:** DRAFT — design-first, build deferred until sign-off
**Date:** 2026-06-11
**Author:** A0.4.6 follow-on (web Performance page)

---

## 1. Problem & goals

The web Performance page ([frontend/app/performance/page.tsx](../frontend/app/performance/page.tsx))
currently renders nothing useful: its P&L curve and Recent Results derive from
`/picks/history`, which returns **zero rows**. Goals:

1. **Show how the production model has been performing** (model quality).
2. **Show our actual placed bets and how they've done** — parity with the
   Streamlit "Actual Bet Performance" section (app/pages/4_Model_Performance.py).
3. **Season filter** — the page must be filterable by season or it gets unusable
   (model-quality data spans 2021–2026).
4. **Per-user bet association** — beta testers each see their own bets.

---

## 2. Root-cause findings (investigation 2026-06-11)

### 2.1 Why the page is empty
`/picks/history` filters `WHERE qualified_bet = TRUE`, but `qualified_bet` is
**NULL on all 45,355 rows** of `baseball_data.betting_ml.daily_model_predictions`.

### 2.2 Two conflicting definitions of "qualified" — and the gate is non-functional
- **Def A — Story 19.2 gate** (`compute_bet_permission`,
  betting_ml/utils/probability_layer.py:376): `qualified_bet = gate_signals_met
  >= min_criteria_met`. **But `min_criteria_met = 3` and only 1 of 5 criteria is
  wired** (`offensive_signal`; the other four return 0). It can never reach 3 →
  always False. VAE/OOD veto is also disabled. **Effectively non-functional.**
- **Def B — Layer 4 selective strategy**: `layer4_h2h_decision != 'abstain'` /
  `layer4_totals_decision != 'abstain'`. This is what production actually uses
  (scripts/write_api_cache.py, `/picks/ev`). **The real working selector today.**

### 2.3 Prod write path drops the gate columns
Production scripts/predict_today.py computes the gate but never INSERTs
`qualified_bet` / `gate_signals_met` / `game_conviction_score`. The legacy
betting_ml/scripts/predict_today.py *does* write them. Backfilling Def A from
stored columns is cheap (needs only `pred_total_runs` + `total_line_consensus`);
Def B is already derivable from stored `layer4_*_decision`.

### 2.4 Real bets ≠ model qualified picks
Of 122 `placed_bets`, only ~16 (13%) are on the side the model's Layer 4
decision picked. The real bets were largely **not** strict model picks — so
"model performance" and "our real-bet performance" will diverge substantially
and must be presented as distinct things.

### 2.5 Data inventory
| Source | Rows | Span | Notes |
|---|---|---|---|
| `placed_bets` | 122 | 2026-05-03→ | Real bets, $5 stakes. `outcome` & `profit_loss` NULL on all rows. **No user_id.** |
| `mart_prediction_clv` | 43,801 | 2021–2026 | Global model-quality (model_prob, market_prob, CLV, outcome). |
| `mart_game_results` | 25,795 | 2015–2026 | Final scores for settlement. |
| `mart_clv_labeled_games` | 9,503 | 2021–2026 | Fully settled, clv + actual_outcome. |

### 2.6 Auth / identity
- API Gateway validates the Cognito JWT before invoking the Lambda; FastAPI
  handlers are otherwise unauthenticated **except** the alerts router, which
  extracts the Cognito `sub` from
  `requestContext.authorizer.jwt.claims.sub` with an `X-User-Id` local-dev
  fallback (app/backend/routers/alerts.py:43). **Reusable pattern.**
- Frontend has `email` + `accessToken` post-login (frontend/lib/auth-context.tsx).
- `placed_bets` is written only by Streamlit (app/pages/3_EV_Kelly.py:659); the
  frontend bet-log page is mock-only. Predictions are global (all users, same picks).

---

## 3. Workstream A — "qualified" definition + backfill

**DECIDED 2026-06-11:** Option **B — standardize on Layer 4** (`decision != 'abstain'`)
as the canonical `qualified_bet`. The Story 19.2 gate is split off as a separate
research track (`gate_*` columns) to be finished later. Rationale: the 19.2 gate is
non-functional as configured (always False), so backfilling it now would ship a
meaningless flag; Layer 4 is the live selector and is cheaply derivable.

Original options considered:

| Option | What it means | Cost | Risk |
|---|---|---|---|
| **B: standardize on Layer 4** (recommended) | `decision != abstain` is "qualified"; rename/retire the Story 19.2 gate flag or keep it as `gate_*` columns | Low — derivable from stored cols; forward write path already has it | Layer 4's own edge is unproven, but it's the live selector |
| A: finish + backfill the 19.2 gate | Wire ≥3 criteria or lower `min_criteria_met`, then replay over history | High — must finish the gate first; needs feature columns not all stored | Backfilling now yields all-False until gate is finished |
| A+B hybrid | Persist both: `qualified_bet` (Layer 4) for product + `gate_*` (19.2) for research | Medium | Two flags to keep straight |

**Recommended:** **B** for the product surface now, exposing Layer 4 as the
canonical `qualified_bet`; treat the 19.2 gate as a separate research track
(`gate_qualified` / `gate_signals_met`) to finish later. This unblocks the page
without shipping an all-False flag.

**Backfill plan (Def B):**
1. Forward fix: add `qualified_bet`, `gate_signals_met`, `game_conviction_score`
   to the prod scripts/predict_today.py INSERT (it's already computed in-memory).
2. Historical: SQL `UPDATE ... SET qualified_bet = (layer4_h2h_decision != 'abstain')`
   per market, scoped by the most-recent prediction row per game_pk.
3. Relax `/picks/history` to not hard-require `qualified_bet = TRUE` (or make it a
   query param) so the page is resilient if the flag lags.

---

## 4. Workstream B — per-user bets architecture

**Principle:** picks/predictions stay **global**; **bets are per-user**.

### 4.1 Storage — DECIDED 2026-06-11: **DynamoDB** (OLTP), NOT Snowflake
Bets/users are OLTP (single-row writes on log, per-user reads on page load, point
updates on settle). Snowflake is OLAP (warehouse latency + credits per query, poor
at single-row DML), so bets move to DynamoDB; model/prediction data stays in
Snowflake. The settle job bridges the two (read finals from Snowflake → write
outcomes to DynamoDB).

Tables (provisioned manually per infra convention; see infrastructure/aws_resources.md
and infrastructure/dynamo/create_user_bets_tables.sh):
- `credence-prod-dynamo-user-bets` — PK `user_id` (Cognito sub), SK `bet_id`.
  Attributes mirror the old placed_bets columns. **Sparse GSI** `gsi-pending-by-game`
  (PK `pending_game_pk`, SK `bet_id`): only pending bets carry `pending_game_pk`,
  so the index = unsettled bets; settling REMOVEs it.
- `credence-prod-dynamo-users` — PK `user_id`; `email`, `first_seen_at`,
  `last_seen_at` (upserted on login-sync, story B2).
- One-time migration: `scripts/migrate_placed_bets_to_dynamo.py` (122 Snowflake
  `placed_bets` → DynamoDB under owner sub `14187448-…`). `placed_bets` retained
  read-only/legacy, then deprecated.
- Streamlit writer (app/pages/3_EV_Kelly.py:659) is retired in favor of the
  frontend bet-log → `POST /bets` → DynamoDB (story B2).
- Backend stays Snowflake **read-only**; bet writes go to DynamoDB via the Lambda
  IAM role (no Snowflake write grant).

### 4.2 Backend
- New auth dependency reusing the alerts-router pattern: `get_user_id(request)`
  → Cognito `sub`, `X-User-Id` fallback for local.
- `POST /bets` — write a bet into `user_bets` scoped to the caller's `user_id`.
- All bet-reading endpoints filter `WHERE user_id = :caller` (row-level scoping
  in SQL — no shared cache key across users; cache per user_id or skip cache).
- Model-quality endpoints stay global/unscoped (shared cache OK).

### 4.3 Frontend
- Wire the bet-log page (currently mock) to `POST /bets` + a `GET /bets` list.
- Performance page reads the caller's bets only.

### 4.4 Caching caveat
Current S3 cache keys (e.g. `picks/history.json`) are global. Per-user bet
endpoints must **not** share a global cache key — key by `user_id` or bypass
cache for bet reads.

---

## 5. Workstream C — Performance page rebuild

### 5.1 New endpoints (all accept `?season=YYYY` | `all`)
1. `GET /performance/bets` — caller's `user_bets`, **settled**, with summary
   (W-L-P, win rate, ROI on stake, net P&L $, cumulative-P&L series, recent rows).
2. `GET /performance/model` — global model-quality from `mart_prediction_clv`:
   prediction count, actionable win rate, mean CLV, Brier. **Skill metrics only —
   no simulated $ P&L** (DECIDED 2026-06-11; avoid conflating with real-bet $).

### 5.2 Settlement — DECIDED 2026-06-11: settle op in `daily_ingestion_job` (DONE in B1)
- `scripts/settle_user_bets.py` scans the sparse `gsi-pending-by-game` index →
  reads final scores from Snowflake `stg_statsapi_games` (status 'F') → writes
  `outcome`/`profit_loss` and REMOVEs `pending_game_pk` (drops the bet out of the
  pending index). Idempotent. (Op pattern = loose script via `_run_script`, like
  `write_api_cache.py`; the "packaged code only" rule is about Dagster *imports*,
  not subprocess'd scripts.)
- `settle_user_bets_op` wired into `daily_ingestion_job`, fanning out from
  `dbt_daily_build` (scores fresh) and **never depended on** — a settle failure
  can't block predictions or the API cache. Reuses the existing daily schedule.
- API reads stored outcomes; unfinished games stay pending → shown "Pending" and
  excluded from the cumulative curve.

### 5.3 Page layout ("both, combined")
- **Summary tiles** — real-bet stats (Total Bets, Record W-L-P, Win Rate, Net
  P&L $, ROI) from `/performance/bets`.
- **Model-quality strip** — Mean CLV + Brier + actionable win-rate from
  `/performance/model`, labeled "Model skill (all picks)". **Skill metrics only.**
- **P&L curve** — real cumulative $ from settled bets (Flat; Kelly later).
- **By Market tab** — keep, fed by per-market bet aggregation.
- **By Conviction / By Signal** — placeholder until the gate is finished.
- **Recent Results** — caller's recent settled bets.
- **Season selector** — header control; drives `?season=` on all three queries.
- Remove all remaining MOCK_DATA.

---

## 6. Proposed sequencing (epic/stories — build after sign-off)

1. **B1** ✅ **DONE / verified end-to-end 2026-06-11.** DynamoDB `user-bets` + `users`
   tables provisioned; 122 `placed_bets` migrated; `settle_user_bets.py` +
   `settle_user_bets_op` wired into `daily_ingestion_job` after `dbt_daily_build`.
   Live run: 122 migrated → 116 settled (67W/47L/2P, +$159.16) → 6 today's games
   correctly pending in the sparse GSI. Scripts are AWS_PROFILE-aware (one-time
   admin runs use the ~/.aws power-user; .env keys = limited baseball-access-user).
2. **A1** Forward-persist + historical backfill of `qualified_bet` (Def B = Layer 4);
   relax `/picks/history` filter.
3. **B2** ✅ **DONE / tested 2026-06-11.** `get_user_id` shared dep
   (`app/backend/dependencies.py`; `alerts.py` refactored onto it); `dynamo.py`
   service (`put_bet`/`list_bets`/`upsert_user`); `models/bets.py`; `routers/bets.py`
   `POST/GET /bets` + `POST /users/login` (login-sync), registered in `main.py`.
   Streamlit retargeted to DynamoDB via `app/utils/user_bets.py` (both pages).
   Verified against live tables: put/list/upsert round-trip + self-cleanup;
   `load_owner_bets_df` → 122 rows, +$159.16 stored P&L. Runtime prereq: IAM
   grants (Lambda role #1, baseball-access-user #3).
4. **C1** `/performance/bets` (per-user, settled) + `/performance/model` (global,
   skill metrics only) with `?season=`.
5. **C2** Frontend rebuild: tiles, model strip, P&L curve, season selector, wire bet-log.
6. **A2** (research, later) finish the Story 19.2 gate (wire ≥3 criteria).
7. **C3** By Conviction tab — P&L breakdown by EV tier (gated on A2 or can be done on raw `ev` field alone).
8. **C4** By Signal tab — P&L attribution by sub-model signal group (gated on enriching `/performance/bets` with signal data).

---

## 7. Decisions — ALL RESOLVED 2026-06-11
- [x] **Q1:** "qualified" = **Layer 4** (`decision != 'abstain'`); 19.2 gate split to research track.
- [x] **Q2:** **New `user_bets` table** (canonical bet store); `placed_bets` kept read-only/legacy then deprecated.
- [x] **Q3:** Settle as an **`@op` in `daily_ingestion_job`** (after `dbt_daily_build`); logic in packaged code.
- [x] **Q4:** Model-quality strip shows **skill metrics only** (CLV / Brier / actionable win-rate) — no simulated $ P&L.

**→ Design is fully specified and signed off. B1 DONE; next = B2.**

---

## 8. B2 — backend bets API + login-sync (detailed spec)

Goal: serve and write per-user bets from DynamoDB, and auto-capture each user
into the `users` table on login. Backend is FastAPI on Lambda; auth is enforced
by the API Gateway JWT authorizer (the handler trusts the validated `sub`).

### 8.1 Shared auth dependency  — `app/backend/dependencies.py` (new)
- `get_user_id(request: Request) -> str`: promote the existing
  `alerts.py::_extract_user_id` (Cognito `sub` from
  `request.scope["aws.event"]["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]`,
  `X-User-Id` header fallback for local dev, else 401).
- Refactor `alerts.py` to import this dependency (kill the duplicate).
- Email is NOT reliably in the access-token claims, so login-sync takes it from
  the request body (the frontend has it from the decoded id_token) — see 8.4.

### 8.2 DynamoDB service — `app/backend/services/dynamo.py` (new)
Mirror the `s3_cache.py` service style. `boto3.resource("dynamodb", region)`,
table names from env (`USER_BETS_TABLE`, `USERS_TABLE`).
- `put_bet(user_id: str, bet: dict) -> dict` — stamp `bet_id` (uuid4), `placed_at`
  (utc iso), `user_id`, `pending_game_pk = game_pk` (so settlement finds it via
  the GSI); floats → `Decimal`; `put_item`; return the stored item (floats back).
- `list_bets(user_id: str) -> list[dict]` — `query(KeyConditionExpression=Key("user_id").eq(user_id))`,
  paginated; Decimals → float on the way out. **Not S3-cached** (per-user OLTP read).
- `upsert_user(user_id: str, email: str | None) -> None` — `update_item`
  `SET last_seen_at = :now, email = :e, first_seen_at = if_not_exists(first_seen_at, :now)`.

### 8.3 Models — `app/backend/models/bets.py` (new)
- `BetCreate`: game_pk, score_date, matchup, market (`h2h home|h2h away|over|under`),
  bookmaker, american_odds, stake, total_line?, model_prob?, market_prob?, ev?,
  kelly_capped?, notes?. Validate market enum + stake > 0.
- `Bet`: BetCreate + bet_id, user_id, placed_at, outcome?, profit_loss?.
- `BetsResponse`: { bets: list[Bet], total: int }.

### 8.4 Router — `app/backend/routers/bets.py` (new); register in `main.py`
- `POST /bets` (`user_id = Depends(get_user_id)`) → `put_bet`, return `Bet` (201).
- `GET /bets` (`Depends(get_user_id)`) → `list_bets`, return `BetsResponse`
  (newest first; outcome/profit_loss null while pending).
- `POST /users/login` (`Depends(get_user_id)`, body `{ email }`) → `upsert_user`;
  the frontend calls this once post-login (auth-context `onLoginSuccess`). This is
  the "capture the sub on first login" mechanism — sub from JWT, email from body.

### 8.5 Retarget the Streamlit bet tracker (write + reads) — DONE
Streamlit is a full bet tracker (writes AND reads), so a write-only retarget would
desync its own history. Both pages now go through `app/utils/user_bets.py`
(`load_owner_bets_df` / `write_owner_bet`, owner sub from `OWNER_USER_ID`), which
wraps the same `dynamo.py` service:
- `3_EV_Kelly.py` — "Log a Bet" → `write_owner_bet`; "Bet History" → `load_owner_bets_df`.
- `4_Model_Performance.py` — "Actual Bet Performance" → `load_owner_bets_df`, using
  the **stored** `outcome`/`profit_loss` (settled by the daily op; no score join).
- Dead Snowflake bet SQL/helpers removed. `placed_bets` is now fully legacy/read-only.
- Requires the Streamlit/local-dev principal (`baseball-access-user`) to get the
  DynamoDB grant (IAM principal #3 in aws_resources.md).

### 8.6 IAM (prerequisite, see aws_resources.md)
- **Lambda role** needs DynamoDB read/write (policy #1) before deploy — exercised
  by POST/GET /bets + login-sync.
- **Dagster principal** DynamoDB grant (policy #2) is the B1 settle dependency,
  tracked separately (⚠️ open infra task).

### 8.7 Testing (before deploy — repo rule)
- Local uvicorn + `X-User-Id` header: `POST /bets` → `GET /bets` round-trips;
  `POST /users/login` upserts. Verify items land via the AWS CLI / boto3 under
  the owner sub. Confirm a freshly-posted bet carries `pending_game_pk` and is
  picked up by `settle_user_bets.py` once its game is final.

---

## 9. C3 — By Conviction breakdown tab

**Status:** ⬜ NOT STARTED — deferred until enough live bets accumulate per tier  
**Gate:** C2 complete (Performance page live); ≥30 settled bets (approx); `ev` field
populated on DynamoDB bets (already stored by `POST /bets` from the frontend bet-log).

**Goal:** Replace the "By Conviction — coming soon" placeholder in the Performance page's
`BreakdownTabs` with a real breakdown of win rate and P&L by EV tier. Subscribers can see
whether high-confidence picks are outperforming lower-confidence ones — a core transparency
feature for a betting analytics product.

**Design:**
- EV tiers (computed client-side from the `ev` field on settled bets):
  - **High Edge** — `ev ≥ 0.10` (≥10% expected value)
  - **Medium Edge** — `ev ∈ [0.05, 0.10)`
  - **Low Edge** — `ev ∈ [0.00, 0.05)`
  - **Negative EV** — `ev < 0.00` (for transparency; we place these rarely)
- Table columns: Tier | Bets | Record | Win Rate | Net P&L
- No new backend endpoint — computed purely client-side from `bets` already in state.
- Show tier counts so subscribers see the sample size per bucket.
- Add an `InfoTooltip` on the section header explaining that EV is the model's
  expected edge over the offered odds at bet time.

**Tasks:**
- [ ] Implement `computeByConviction(bets: PerformanceBet[]): ConvictionAgg[]` — same
  shape as `computeByMarket`, partitioned by `ev` tier instead of market.
- [ ] Replace the "Per-conviction breakdowns coming in a future release." placeholder
  in the `conviction` `TabsContent` with a `ConvictionTable` component (styled the same
  as `ByMarketTable`).
- [ ] Add `InfoTooltip` on the "By Conviction" tab label explaining EV tiers.
- [ ] Show "Not enough data" placeholder if total settled bets < 10.

**Acceptance criteria:**
- [ ] Conviction table shows four tiers, each with correct Bets / Win Rate / Net P&L.
- [ ] Tier boundaries are labeled clearly (e.g. "High Edge ≥10% EV").
- [ ] No new backend endpoints required (pure client-side aggregation).
- [ ] Works correctly when some tiers have zero bets (shows "—" not NaN/error).

---

## 10. C4 — By Signal attribution tab

**Status:** ⬜ NOT STARTED — requires backend enrichment  
**Gate:** C2 complete AND `/performance/bets` enriched with signal attribution (see below).

**Goal:** Replace the "By Signal — coming soon" placeholder with a breakdown of bets and
P&L by the primary sub-model signal that drove each pick. This shows subscribers *which
parts of the model* are generating returns — e.g. "our bullpen model picks are winning at
62%, our offensive model picks are at 54%."

**Design:**
The signal attribution requires knowing which sub-model dominated each pick. Two
implementation paths:

**Path A (preferred — lighter):** Enrich the DynamoDB bet record at bet-log time.
When the frontend logs a bet (`POST /bets`), pass the `market` and `game_pk`. The backend
can do a point query on `baseball_data.betting_ml.feature_pregame_sub_model_signals` to
look up the dominant signal group for that game/market (whichever sub-model signal had
the highest absolute contribution at prediction time) and store it as `signal_group` on
the DynamoDB item.
- Pros: no retroactive joins; signal attribution is frozen at bet time.
- Cons: requires `feature_pregame_sub_model_signals` to be queryable at `/bets` write time.

**Path B (retroactive — broader coverage):** Add a `GET /performance/bets/signals`
endpoint that joins settled DynamoDB bets to `feature_pregame_sub_model_signals` in
Snowflake on `(game_pk, market_type)`, returns an enriched list with `signal_group` per bet.
- Pros: covers historical bets including the 122 migrated ones.
- Cons: Snowflake join on each page load (needs caching per user_id).

**Recommended:** Path B for historical coverage, with S3 cache keyed by
`performance/bets_signals_{user_id}_{season or all}.json` (date-scoped → auto-expiry).

**Signal groups** (from `feature_pregame_sub_model_signals`):
- `bullpen` — bullpen quality / freshness signals
- `starter` — starting pitcher EB posterior
- `offense` — team offensive EB posterior
- `run_env` — park + weather run environment
- `matchup` — pitcher–batter matchup matrix

**Table columns:** Signal Group | Bets | Record | Win Rate | Net P&L

**Tasks:**
- [ ] Decide Path A vs Path B (recommend B for historical coverage).
- [ ] **Path B:** Add `GET /performance/bets/signals` endpoint (or enrich
  `/performance/bets` with a `signal_group` field). Join DynamoDB settled bets to
  `feature_pregame_sub_model_signals` on `(game_pk, market_type)`; determine dominant
  signal group per bet (e.g. highest absolute z-score or signal contribution column).
  S3-cache the result per `user_id × season`, date-scoped.
- [ ] Frontend: implement `computeBySignal(enrichedBets)` aggregation; replace the
  signal tab placeholder with a `BySignalTable` component.
- [ ] `InfoTooltip` on the tab explaining what signal groups represent.

**Acceptance criteria:**
- [ ] Signal table shows per-group Bets / Win Rate / Net P&L for settled bets.
- [ ] Attribution is reproducible — same bet always maps to the same signal group.
- [ ] Cache is user-scoped (no cross-user data leakage via a shared cache key).
- [ ] Graceful fallback if Snowflake join returns no rows for a bet (show "unknown").
