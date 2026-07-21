# Design — flip the `monthly_schedule` raw writer to S3 (E11.20 phase-2a, step 3 prerequisite)

**Status:** WRITER BUILT default-OFF (2026-07-20); operator soak + bridge retirement PENDING. This
is the story that actually makes the 30-min capture tick Snowflake-free — the prerequisite for
deleting the tick's `refresh_w1_external_tables` + dbt legs (E11.20 phase-2a step 3), which by itself
banks ~0 wake-minutes (see `e11_20_cost_flips.md` §5a).

**BUILT (this PR — a runtime no-op until `W11_RAW_WRITE_MODE` is set):**
- `run_schedule` (`scripts/ingest_statsapi.py`) gates a Snowflake→S3 dual-write on `W11_RAW_WRITE_MODE`
  (default `snowflake` = SF INSERT only, unchanged). Writes the exact 2-col contract + the same-month
  retention prune. `main()` now opens the SF connection ONLY when the SF leg is live (`s3` mode opens
  no session — the connect IS the wake).
- `prune_same_month_partitions` (`scripts/utils/lakehouse_raw_writer.py`) — the live INC-20 retention.
- The lean `schedule-capture` image is S3-capable (`+boto3 +pyarrow`, COPYs `utils/lakehouse_raw_writer`,
  region → `us-east-2`) so a leaked `W11_RAW_WRITE_MODE` can't `ImportError` it (odds-capture cure).
- Tests: `betting_ml/tests/test_monthly_schedule_s3_writer.py` (9 — real writer→parquet contract +
  retention + main() conditional-connect; fast gate green). Writer parquet schema confirmed identical
  to prod `lakehouse_raw/monthly_schedule/` (`ingestion_ts`/`json_field` VARCHAR).

**REMAINING (operator, box):** the runtime gate + soak (below), then the ORDERED bridge retirement
(step 3), then E11.20 phase-2a step 3 (delete the tick's SF legs).

**Serving-criticality: MAXIMUM.** `monthly_schedule` is the source of the entire game universe —
`stg_statsapi_games`, `stg_statsapi_lineups`, `stg_statsapi_lineups_wide`,
`stg_statsapi_probable_pitchers` all flatten it. A regression serves ZERO predictions (the 7/20 P0
class). This story's merge bar is a **real box run** (CLAUDE.md RUNTIME GATE — CI mocks all IO and
cannot see the failure modes here). Do NOT ship on CI-green alone.

---

## Why this, and why the refresh-leg delete is blocked on it

Minute-level `query_history` (`e11_20_cost_flips.md` §5a) proved the capture tick's
`ext_table_refresh` is NOT the tick's first Snowflake touch. Every tick already:
1. `ingest_statsapi.py schedule …` — a **native Snowflake INSERT** into `statsapi.monthly_schedule`.
2. `export_odds_raw_to_s3.py --source monthly_schedule --since <today>` — a **Snowflake READ** that
   mirrors that fresh row to S3 (`_schedule_lakehouse_intraday`, `pipeline/ops/intraday_ops.py`).
3. `run_w1_lakehouse.py --w3pre-only / --w7b-only` — DuckDB/S3 (already SF-free).
4. `refresh_w1_external_tables.py` — the `ALTER EXTERNAL TABLE … REFRESH` (SF), so the SF views the
   remaining consumers read see the fresh parquet.

Deleting step 4 removes ~150 queries and **zero wake-minutes** — steps 1–2 already woke the
warehouse in the same minute. The wake dies only when the WRITER (step 1) becomes S3-native, which
retires both the native INSERT *and* the export bridge (step 2). Then step 3 already reads S3, and
step 4's SF ext-table refresh is only needed by the *remaining* SF consumers — see the consumer
audit below for what those are.

---

## The exact S3 contract (verified against prod, 2026-07-20)

The export bridge writes `lakehouse_raw/monthly_schedule/dt=<ingestion_date>/part-*.parquet` with
**two columns** (`scripts/export_odds_raw_to_s3.py` SOURCES):

| column | type | value |
|---|---|---|
| `ingestion_ts` | ISO **VARCHAR** | the snapshot wall-clock (SF `CURRENT_TIMESTAMP` at insert) |
| `json_field` | JSON **string** | `to_json(json_field)` — the full month's schedule payload |

- Partition key `dt=` = `ingestion_ts::date` (via `_partition_date`, `lakehouse_raw_writer.py`).
- `monthly_schedule` is already in `RAW_SOURCES` and `_JSON_COLS`, so `rows_to_arrow_table` serializes
  a `json_field` dict → JSON string automatically. A live writer supplies `json_field` as the raw
  `dict` (NOT pre-serialized) and `ingestion_ts` as an ISO string.
- One `monthly_schedule` INSERT = **one month** (`run_schedule` iterates `iter_months`; each month is
  one row whose `json_field` is that month's full payload). The daily op passes `--start-date
  yesterday`, so a normal day = 1 month, the 1st of a month = 2 months (prev + current). Intraday =
  `--start-date/--end-date today` = 1 month (the current one). So a fire writes 1–2 rows, all under
  `dt=<today>`.

### Retention (INC-20 — the OOM landmine; MUST be replicated)

The export bridge collapses partitions to **latest ingestion-DATE per calendar month** on a FULL run
(`latest_dt_per_month` + `prune_partitions`, skipped when `--since` is set). Without it, ~50 daily
full-month snapshots (~470 MiB) pile up and the DuckDB flatten SIGKILLs on ~750k pre-dedup fat-JSON
game-rows.

**Live-writer equivalent (correct + simple):** each fire →
1. `write_raw_rows_s3("monthly_schedule", rows, mode="overwrite_partition")` — idempotent within the
   day (28 intraday fires collapse to the last).
2. Prune every `dt=` partition in the **same `(year, month)` as today** except `dt=<today>`.

This exactly reproduces "latest-per-month": prior months' single retained partition is never touched
(the writer only fetches current month, except the 1st when a prev-month row also lands *inside*
`dt=<today>` — the flatten's latest-ingestion-per-game_pk dedup handles the transient overlap, no
dup, no OOM). The `__nullts__` historical partition is BACKFILL-ONLY — the live writer never touches
it. Leave the one-time historical backfill to `export_odds_raw_to_s3` (or a scripted equivalent);
this story is the LIVE writer only.

---

## Implementation plan

### 1. `scripts/ingest_statsapi.py::run_schedule` — add the gated S3 leg (template: `run_venues`)

- Lazy import inside `run_schedule`, guarded by `if do_s3:` — mirrors `run_venues` exactly:
  `from utils.lakehouse_raw_writer import lakehouse_write_legs, w11_write_mode, write_raw_rows_s3`
  (+ `prune_partitions` for the retention step).
- `do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())` — the shared **`W11_RAW_WRITE_MODE`** env
  (default `'snowflake'` → `do_s3=False` → merge is a NO-OP; `s3`/`both` opt in).
- Collect one mirror row per month: `{"ingestion_ts": <one ISO-UTC stamp shared by the whole fire>,
  "json_field": payload}`. A single stamp per fire = one snapshot the flatten dedup treats atomically
  (the `public_betting_mirror_rows` pattern).
- After the loop, if `do_s3`: `write_raw_rows_s3(..., mode="overwrite_partition")` then the same-month
  prune (compute `keep = {today}`; delete same-`(year,month)` partitions via `prune_partitions` scoped
  to the current month, or a small explicit `_delete_partition` loop — `prune_partitions` deletes
  everything not in `keep_dts` and always keeps `__nullts__`, so pass it the full keep-set of
  *current-month* partitions = just `today`, but ONLY prune within the current month to avoid nuking
  prior months — add a `month_scope` guard or filter partition list to the current month first).
  ⚠️ Verify `prune_partitions`' delete scope before reuse — the export calls it with the full
  latest-per-month keep-set; the live writer must NOT delete prior-month partitions it didn't rewrite.
- Keep `do_sf` writing the SF INSERT during the **parallel/soak** window (`W11_RAW_WRITE_MODE=both`),
  then drop to `s3` once parity passes.

### 2. Lean `schedule-capture` image — make it S3-capable (odds-capture precedent, 2026-07-05)

`run_schedule` IS the lean image's whole job (unlike `run_venues`, which the lean image never runs).
The image (`services/schedule_capture/Dockerfile`) installs only `requests snowflake-connector-python
cryptography python-dotenv tzdata` and COPYs only `ingest_statsapi.py` — **no boto3/pyarrow/`scripts/
utils`**. So a lazy `from utils…` that actually executes there = `ModuleNotFoundError` every fire
(the exact lean-capture-image landmine). Two facts soften this:
  - The host-cron `schedule-capture` line is **currently commented out** (`capture.crontab` L47 —
    Dagster's `intraday_schedule_capture_*` schedules own the tick, INC-30 single-owner). So the lean
    image is a DORMANT fallback today.
  - With `W11_RAW_WRITE_MODE` unset in the lean image's env, `do_s3=False` → the import never runs.

**Correct resolution (S3-forward, per the odds-capture landmine):** add `boto3 pyarrow` to the image
`pip install`, `COPY scripts/utils/lakehouse_raw_writer.py ./utils/` (+ any `scripts/utils` module it
imports — audit its imports; it is designed lean but confirm), and set `AWS_DEFAULT_REGION=us-east-2`
on the service. Then the fallback image can honor the flag if it's ever re-activated. The guard
`betting_ml/tests/test_lean_capture_images_selfcontained.py` only bans `betting_ml` imports (a
`utils.` import is fine) — but re-run it to confirm. Do NOT rely on "the flag won't reach the lean
image" — that's the odds-capture mistake (`env_file` leaked `LAKEHOUSE_RAW_WRITE_MODE`).

### 3. Retire the export bridge + the native INSERT (AFTER parity) — ORDER IS LOAD-BEARING

⚠️ During `both` mode the NEW writer and the OLD bridge (`export_odds_raw_to_s3 --source
monthly_schedule`, still called by `_schedule_lakehouse_intraday` + the daily
`lakehouse_schedule_export_op`, `daily_ingestion_ops.py` L591) BOTH write
`lakehouse_raw/monthly_schedule/dt=<today>/` (last-writer-wins; the rows are identical so it is
benign, `overwrite_partition` is idempotent). **But flipping to `s3` while the bridge still runs is
an INC-31 stale-mirror CLOBBER: `s3` stops the SF INSERT, so the bridge then reads a FROZEN SF table
and re-mirrors OLD data over the writer's fresh S3 key.** Safe order:

1. `both` (writer + bridge both write; SF INSERT live). Soak + parity (below).
2. **Remove the bridge's `monthly_schedule` leg** from `_schedule_lakehouse_intraday` and
   `lakehouse_schedule_export_op` — still in `both`, so the writer is now the SOLE S3 author while
   the SF INSERT still backstops. Verify a daily + a few intraday fires.
3. **Then** flip `W11_RAW_WRITE_MODE=s3` (drops the SF INSERT). Never before step 2.
4. Drop the SF `monthly_schedule` table only after the consumer audit confirms zero SF-table readers;
   remove it from `check_data_freshness` at the same time (else it false-warns on the frozen table).

### 4. THEN E11.20 phase-2a step 3 (the actual tick delete) becomes correct

Once the writer is S3-native and the bridge is gone, `_schedule_lakehouse_intraday` no longer opens a
SF session for capture. The `refresh_w1_external_tables` leg then serves only the *remaining* SF
consumers — retire it per that audit.

---

## Consumer audit (INC-27 rule: the dbt DAG is NOT the consumer list — grep the raw path)

Before dropping the SF `monthly_schedule` table or the ext-table refresh, `grep -rIn
"statsapi.monthly_schedule"` AND grep readers of the S3 PATH/layout (`lakehouse_raw/monthly_schedule`,
`lakehouse_ext.stg_statsapi_*`). Known consumers of the four flattened staging models (from the
2026-07-20 grep) — every one must be confirmed reading S3, not the SF view, before step 4:
`write_serving_store.py` (still `--s3`-gated on `W7B_LAKEHOUSE_S3`), `picks.py`, `predict_today.py`,
`generate_matchup_signals.py`, plus the app/backend routers. The dbt staging rebuild in the tick
(`intraday_lineup_rebuild` — `stg_statsapi_lineups_wide` is `materialized='table'`, an 84.8s CTAS)
stays until those SF-view readers are cut to DuckDB; it is load-bearing, not waste (§5a).

## Runtime gate (box; the merge bar)

1. Deploy with `W11_RAW_WRITE_MODE=both`. Run `ingest_statsapi.py schedule --start-date <yesterday>`
   in `dagster-codeloc`; confirm the S3 `dt=<today>` partition is written AND the same-month prune
   left prior months intact (`aws s3 ls .../monthly_schedule/`).
2. Parity: flatten `stg_statsapi_games` over the S3-native partition vs the export-bridge output —
   the game_pk set + `abstract_game_state` per game must be identical (per-ROW through
   `lakehouse_ext.stg_statsapi_games`, not just parquet — the parity-is-necessary-not-sufficient rule;
   watch the postponed-DH dedup + the INC-23 VARCHAR `game_date`).
3. `predict_today` green on the box; a full slate's lineups still confirm (lineup_monitor fires).
4. Only then flip to `s3` and retire the bridge.
