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
