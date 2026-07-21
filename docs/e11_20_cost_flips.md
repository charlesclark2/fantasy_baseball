# E11.20-COST — Snowflake spend attribution + the wake-kill flip package

**Status:** measured + flip code shipped 2026-07-16 · operator flips + box runtime gate PENDING (§4)
**Context:** SF at $124 MTD on 7/16 (~$300/mo pace). Account = ONE warehouse (`COMPUTE_WH`,
X-Small, auto_suspend already 60s — config was NOT the problem).

## 1. The measurement (7 trailing days, account_usage — laptop ACCOUNTADMIN)

| Class | Credits/wk | Share | Detail |
|---|---|---|---|
| **Wake/idle burn** (resume minimums + suspend tails) | **~26** | **~80%** | warehouse metered credits in ALL 24 h of every day — including All-Star-break days (2.4–2.7 credits/day with ZERO games) |
| Attributed query compute (total) | ~5.5 | ~17% | `query_attribution_history` |
| — capture-dbt tick (`stg_statsapi_probable_pitchers` / `lineups_wide` SF rebuilds) | 1.60 | | **#1 waker: 288/336 30-min buckets/wk** — double-fired (host cron + Dagster, §2.1) |
| — everything else (daily job, serving writes, monitors) | 3.67 | | mostly inside the already-awake daily window |
| — state writers (Elo MERGE 0.35 + prediction_log CLV 0.50) | 0.85 | | 24–34 buckets only → NOT wake drivers |
| — Cortex narratives (mistral-7b, ~20/day) | 0.22 | | negligible |
| Cloud services | ~2.8 | | ~half = 17,005 `ALTER EXTERNAL TABLE … REFRESH`/wk (zero warehouse compute, metadata-only) |
| AI_FUNCTIONS (separate SKU) | ~0.03 | | negligible |

**Revised thesis (overturns the §4 AC-C seeding in `e11_20_delta_rollout.md`):** the pregame
feature family's dbt-on-SF materializations bill only **~0.03 credits/day** — elapsed-seconds
made them look big, but on an X-Small inside the already-awake daily window they are nearly
free. **The dollars are wake events**: 24/7 tick chains that resume the warehouse ~every
15 min around the clock. Delta-migrating read families is a runtime play, not a credit play;
the credit play is killing ticks.

The 24/7 wakers, by 30-min buckets touched (of 336/wk):
1. **capture-dbt tick 288** — the schedule capture fired from BOTH the host cron
   (`capture.crontab` line 38, never disabled) AND the Dagster
   `intraday_schedule_capture_*` schedules (operator-started per INC-22 Option-2 — its
   step 3 "disable the lean cron" never happened). Each fire: SF `monthly_schedule`
   INSERT + `trigger_dbt` 3-model staging rebuild + GRANTs.
2. **lineup-monitor tick 273** — the sensor's idle path ran the SF-querying
   `lineup_monitor.py` hourly 24/7 (even `mins is None` = no games at all), and the
   2026-07-07 cron backstop ran it 28×/day unconditionally. ~50 SF sessions/day, each a
   warehouse resume for a SELECT+INSERT+COMMIT.
3. **write_book_odds_op 72–85** — `write_serving_store.py --book-odds --game-detail`
   WITHOUT `--s3` on every intraday odds cycle → SF reads through game hours.
4. ext-table refreshes 222 — cloud-services only (no warehouse resume); left as-is for
   now, but the 10% free-allowance interplay means they get MORE billable as compute
   drops — revisit after the wake-kill lands.

## 2. The flip package (shipped 2026-07-16; guard: `betting_ml/tests/test_cost_wake_gates.py`)

1. **`services/dagster/aws/capture.crontab`** — host schedule-capture line DISABLED
   (commented, with the mutual-exclusion rule). Dagster `intraday_schedule_capture_*` is
   the sole owner (it is the functional superset: same capture + dbt rebuild PLUS the S3
   propagation chain). Kills the double-fire AND the INC-30-class dbt-runner 409 contention.
2. **`pipeline/sensors/lineup_monitor_sensor.py`** — `_MONITOR_HORIZON` (8 h) gate in BOTH
   the sensor and the cron-backstop body: the SF subprocess is skipped entirely (no SF
   session) when no Preview game is within 8 h (lineups post 1–4 h out; active lead is 5 h).
   Gate reads the S3 lakehouse via DuckDB (no SF wake, the proven W12 read); fail-open on
   lookup errors; `lineup_monitor_state` dedup makes re-entry catch everything. Kills the
   overnight/break-day monitor burn with zero SLA risk.
3. **`pipeline/ops/intraday_ops.py::write_book_odds_op`** — appends `--s3` when BOTH
   `W7B_LAKEHOUSE_S3=1` AND `W6_LAKEHOUSE_INTRADAY=1` (the intraday S3 mart rebuild runs
   just upstream in the same job — both required, else the line-movement chart would
   re-freeze at the morning serve, the 2026-07-03 regression). Kills ~15 SF sessions/day.
4. **Operator env flip: `W9_LAKEHOUSE_S3_READS=1`** — repoints all 7 sub-model signal
   generators' reads to DuckDB-over-S3 (S3 inputs live since W8a/W8b; writes stay SF per
   W9 design). Gate: `scripts/parity_check_w9_signals.py` green on the box first.

**Projected savings:** break-day burn 2.4–2.7 → ~1.0 credits/day (daily job + odds window
only); game-day 4.2–5.1 → ~2.5–3.0. **≈1.5–2.0 credits/day ≈ $90–120/mo (~40%)** at the
~$2–3/credit account rate. Verify with §5 after 3 post-flip days.

## 3. Deliberately NOT flipped this week (Friday live-gate discipline)

- `W11_RAW_WRITE_MODE both→s3` (weather/derivative captures): a W11 cutover decision with
  its own consumer-verification gate — not a quick flip.
- `write_api_cache_op` (daily SF read): inside the awake daily window → ~zero marginal
  credits. Phase-2 nicety, not a dollar.
- Ext-table refresh scoping: cloud-services only today; revisit post-wake-kill.
- Retiring the SF 3-model staging rebuild from the Dagster capture tick entirely:
  requires first repointing its remaining SF readers (`lineup_monitor.py` state+joins,
  `write_pitcher_k_projections` cron, zone overlays) to DuckDB — phase-2 item below.

## 4. ⏭️ Operator run-order (BOX unless noted)

```bash
# (a) Confirm the box flag state (decides what write_book_odds_op does after deploy):
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  env | grep -E 'W7A_LAKEHOUSE_S3|W7B_LAKEHOUSE_S3|W6_LAKEHOUSE_INTRADAY|W9_LAKEHOUSE|W11_RAW_WRITE_MODE|LAKEHOUSE_RAW_WRITE_MODE|SCHEDULE_LAKEHOUSE_INTRADAY'

# (b) Confirm the Dagster capture schedules are RUNNING (they own the tick now):
#     Dagit → Automation: intraday_schedule_capture_daytime + _overnight = RUNNING.

# (c) Deploy the flip code (crontab + sensor + intraday op) — deploy.sh reinstalls the
#     crontab (single-owner, root) so the host schedule-capture line drops out with it:
cd ~/app && ./services/dagster/aws/deploy.sh

# (d) Verify the cron actually dropped:
sudo crontab -l | grep schedule-capture   # expect: only the commented line / nothing active

# (e) W9 read-flip gate + flip:
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc python -u scripts/parity_check_w9_signals.py
# if PASSED:
echo 'W9_LAKEHOUSE_S3_READS=1' >> ~/app/services/dagster/aws/.env
cd ~/app/services/dagster/aws && docker compose up -d
```

**Runtime gate (Friday 7/17, games resume):** daily job green end-to-end; post_lineup
coverage ≥0.85; a confirmed lineup triggers the monitor + re-score normally (the horizon
gate must be INSIDE the window by then — first pitch ≤8 h); the served book-odds/game-detail
blobs refresh through the evening (line-movement chart advances past the morning serve).

## 5. AFTER measurement (run ~3 days post-flip; LAPTOP)

`uv run python scripts/../<session scratchpad>/sf_spend_attribution.py` equivalents — or simply:
```sql
select to_date(start_time) d, round(sum(credits_used),2) creds
from snowflake.account_usage.warehouse_metering_history
where start_time >= dateadd('day',-10,current_timestamp) group by 1 order by 1 desc;
```
plus the buckets-touched query on the three waker families (expect capture-dbt ≈ half,
lineup-monitor ≈ game-window-only, book-odds SF ≈ 0).

### 5a. Phase-2a-2 (2026-07-20) — consumers repointed; ⛔ the tick leg NOT deleted, and why

**Shipped (code, pending deploy):** `write_pitcher_k_projections.py` and
`generate_zone_overlays_today.py` now read the S3 lakehouse via DuckDB (`register_lakehouse_views`)
— zero Snowflake sessions in the steady state. The K writer's history frame moved too
(`load_frame_cached(..., use_s3=True)`): `betting_ml/data/cache` is gitignored, so a CD-built image
starts with an EMPTY cache and the FIRST hourly run of every deploy was pulling the whole
2021-present windowed frame from the warehouse. Frame parity vs Snowflake: **exact on all 25
columns × 26,918 rows** — the only delta was 12 rows Snowflake fans out ×4 on pks 823356/823357
(the known SCD-2 zombie-current defect, already healed in the parquet), i.e. S3 is strictly cleaner.
Zone overlays also got the INC-22 clock fix + a real intraday trigger and now find **189 pairs** for
a live slate where the organic path had produced 0 since 2026-06-30.

**⛔ Step 3 (delete the capture tick's `refresh_w1_external_tables` + dbt legs) was NOT executed.
Minute-level `query_history` shows it would bank ≈ nothing and would break serving.** Evidence from
a 9h window on 2026-07-20 (quiet hours 08:00–10:00 PT, no daily job, no games):

| tick component | queries/hr | distinct wake-MINUTES/hr |
|---|---|---|
| `ext_table_refresh` | ~150 | 4 |
| `monthly_schedule` read + write | ~10 | 4–6 |
| everything else (`other`) | ~31–45 | 5–7 |

Two findings that overturn the planned change:

1. **The refresh is not the first SF touch of the tick.** Each tick fires
   `ingest_statsapi.py schedule` (a native Snowflake WRITE to `statsapi.monthly_schedule`) and
   `export_odds_raw_to_s3.py --source monthly_schedule` (a Snowflake READ) *before* the refresh, in
   the SAME minutes. Deleting the refresh removes ~150 queries and **zero wake-minutes** — the exact
   buckets-vs-queries trap §2/F1 already paid for once. The real prerequisite is flipping the
   `monthly_schedule` RAW WRITER to S3 (the W11 Tier-A pattern), which retires both the native write
   and the export bridge. That is the next story, and it must land *before* the refresh leg is cut.
   **Design worked out in `docs/monthly_schedule_s3_flip_design.md`** (exact 2-col S3 contract, the
   INC-20 latest-per-month retention replicated as a same-month prune, the lean `schedule-capture`
   image S3-capability decision, the consumer audit, and the box runtime gate).
2. **The tick's dbt leg is load-bearing, not waste.** `intraday_lineup_rebuild`'s Snowflake branch
   for `stg_statsapi_lineups_wide` is `materialized='table'` — the observed
   `create or replace transient table ... as (...)` at **84.8s over 20 runs**, not a view no-op. Its
   consumers (`write_serving_store_intraday_op`, which still runs WITHOUT `--s3` per W7b-1, plus
   `picks.py` and `predict_today.py`) read those Snowflake objects on the live slate. Dropping the
   rebuild would stale the intraday serving path for no credit gain.

**What DOES bank now, in measured order:** `lineup_monitor` is the largest single remaining waker
(~21–22 distinct wake-minutes per 9h across four query shapes: the candidates join, the
`lineup_monitor_state` read, the `pipeline_run_log` INSERT, and the `daily_model_predictions`
DISTINCT). The `LINEUP_MONITOR_S3=1` path that kills all four is already built — it is blocked only
on deploying the `lineup_predict` S3 mirror (see §5b), not on new code. The K-writer repoint
removes a further ~9 wake-minutes/9h (four query shapes, all confirmed present in `query_history`
before the change).

**Box verification (post-deploy, 2026-07-20):** both writers ran clean in `dagster-codeloc` —
K projections scored 30 starters, zone overlays found **234 pairs** (up from 189 as more lineups
posted). ⚠️ **The K run prints `[cache] MISS … — pulling from Snowflake...` and this is a LIE** —
that string was hardcoded in `betting_ml/utils/training_cache.get_cached_df` regardless of the
loader passed in. The tell that S3 really was used is the ROW COUNT: **26,918** (Snowflake returns
26,930 — the ×4 zombie fan-out). Fixed: `get_cached_df` now takes a `source_label` defaulting to
the neutral `"source"`, and `load_frame_cached` passes `"the S3 lakehouse"` / `"Snowflake"`. A
hardcoded source name in a shared cache helper is a future misdiagnosis waiting to happen.

### 5b. lineup_monitor flip gate — RUN, and its result

`scripts/parity_check_lineup_monitor.py`, 2026-07-20 21:21 UTC (mid-interval, 10 games posted):

```
candidates      : SF=10  S3=10     ✅  (incl. min_slots_filled + starters — the INC-32 readiness signal)
post_lineup set : SF=10  S3=0      ❌
```

**✅ RE-RUN POST-DEPLOY (same day) — PARITY PASSED: candidates 13=13, post_lineup 13=13.** The
deploy was the entire fix, exactly as diagnosed below.

**✅ FLIPPED + CONVERGED 2026-07-20 22:11–22:35 UTC.** `LINEUP_MONITOR_S3=1` set in the box `.env`,
`up -d`, live container env verified `1`.

⚠️ **Expect a ONE-TIME re-trigger wave on any mid-day state-backend switch.** `lineup_monitor.py`
branches `if pk not in already_triggered: trigger` FIRST — the `games_with_post_lineup` guard only
covers the `elif`. DynamoDB starts empty while the day's triggers live in Snowflake
`lineup_monitor_state`, so every still-`Preview` complete-lineup game re-triggers once. Observed
exactly: the 22:17 run fired all **13** games = the precise union of everything triggered
19:15→21:37. Benign and self-limiting (the trigger writes the state item). Convergence confirmed —
no run after 22:17 despite eligible `Preview` candidates, DynamoDB Count stable at 13.

**Discriminator vs the INC-32 loop**, both visible in one `dagster_runs.py` output: INC-32 = the
SAME pk every tick forever (7/19 `823523` × 10+); healthy = each pk once as its lineup completes,
plus one wave at the switch. 🔧 On the BOX that script needs
`DAGSTER_GRAPHQL_URL=http://localhost:3000/graphql` — the default public Caddy URL returns 401.

**The original mismatch was expected and NOT a defect** — it was the un-deployed image, not the code. The
`lineup_predict` → `export_w6_raw_to_s3.py --table daily_model_predictions` mirror is committed but
the box still runs the pre-mirror baked image, so today's post_lineup rows cannot be in S3 yet.
Confirmed in the parquet: 7/17–7/19 all carry post_lineup rows (mirrored by the next morning's
daily export); 7/20 carries only `morning`. **Do not flip on this result.** Correct order:
deploy → re-run the parity check on a live slate → both halves must match → then set
`LINEUP_MONITOR_S3=1`. Flipping before the deploy would re-arm the INC-32 infinite re-trigger loop
(Step-2b would see zero post_lineup rows and re-fire every game every tick).

## 6. Phase-2 build plan (REVISED priorities — code not built this week, by measurement)

The story's DO-3 assumed pregame = the SF-credit target; measurement demoted it (~0.03
credits/day). Revised phase-2 order:
1. **Tick-chain SF retirement (the remaining credit play):** repoint `lineup_monitor.py`
   (state table → DynamoDB or S3-Delta; probables/lineups joins → the lakehouse parquet the
   intraday chain already rebuilds) + the K-projection cron's SF reads → then drop the
   3-model SF staging rebuild from the capture tick (`trigger_dbt` leg) entirely. Kills the
   last 24/7 SF sessions → warehouse awake only for the daily job + game-window odds ticks.
2. **W6 odds marts → Delta (the runtime target, 9–14 min/day):** the phase-1 machinery
   repeat — `_current`-bucket partition maps to a Delta replaceWhere cleanly; the CLV
   post-hoc marts stay daily-full. Mirror + `parity_check_delta_w6` + green soak, flip
   AFTER phase-1 fully closes (never two serving cutovers at once).
3. **Pregame feature family → Delta:** runtime/architecture play only now; sequence last.

## 7. DO-4 state-table stretch — SCOPED, verdict: DEFER

Elo MERGE (0.35 cr/wk, 24 buckets) + prediction_log CLV updates (0.50 cr/wk, 34 buckets) +
posterior INSERTs (smaller) ≈ **≤1.5 credits/wk ≈ $15–20/mo**, all inside already-awake
windows (not wake drivers). A Delta ACID/MERGE migration of serving-adjacent state is
higher-risk than its return while the wake-kill banks 5–8× more. Re-measure after §5; the
stretch only becomes worth it as the LAST step to a truly Cortex-only Snowflake.
