# Design — E11.20 phase-2a **step 3**: retire the capture tick's Snowflake legs (`TICK_SF_FREE`)

**Status:** BUILT default-OFF (2026-07-21); operator flip PENDING (gated on the monthly_schedule
writer flip + bridge retirement AND the W7b-2 flip — see below). This is the FINAL phase-2a step:
after it, the 30-min `intraday_schedule_job` capture tick makes no Snowflake read/write, killing the
#1 warehouse waker (E11.20-COST).

**Serving-criticality: HIGH** — the tick keeps today's game-state + confirmed lineups fresh for the
lineup monitor and the `--s3` serving reads. Merge = runtime no-op (`TICK_SF_FREE` unset); the flip is
a real box run (RUNTIME GATE).

---

## What the tick does today, and what step 3 removes

`intraday_schedule_job` = `intraday_schedule_capture` → `intraday_lineup_rebuild`:

| Leg | SF touch | Step 3 |
|---|---|---|
| `ingest_statsapi.py schedule` (in `intraday_schedule_capture`) | SF **INSERT** into `statsapi.monthly_schedule` | retired by the **monthly_schedule writer flip** (`W11_RAW_WRITE_MODE=s3`), NOT this flag |
| `export_odds_raw_to_s3 --source monthly_schedule` (in `_schedule_lakehouse_intraday`) | SF **READ** (bridge) | retired by the writer flip's **bridge retirement** (ordered before the `s3` flip), NOT this flag |
| `run_w1_lakehouse --w3pre-only` / `--w7b-only` (in `_schedule_lakehouse_intraday`) | none (DuckDB/S3) | **STAYS** — these build the S3 parquet the monitor + serving read |
| `refresh_w1_external_tables.py` (no-arg, in `_schedule_lakehouse_intraday`) | SF **ALTER EXTERNAL TABLE REFRESH** ×~30 | **`TICK_SF_FREE` skips it** |
| `intraday_lineup_rebuild` (dbt run of `stg_statsapi_lineups[_wide]` + `stg_statsapi_probable_pitchers`) | SF **dbt staging rebuild** | **`TICK_SF_FREE` skips it** |

So `TICK_SF_FREE` owns exactly the two legs the phase-2a plan names: the **ext-table refresh** and the
**dbt staging rebuild**. The capture INSERT + the export bridge are owned by the *writer-flip* story
(`monthly_schedule_s3_flip_design.md` §3) because their retirement is order-coupled to
`W11_RAW_WRITE_MODE` (flipping to `s3` while the bridge still runs is the INC-31 clobber). The tick is
fully Snowflake-free only when BOTH stories' flips are done.

## Why skipping each leg is safe

- **`intraday_lineup_rebuild` (dbt SF staging):** the `else`-branch dbt models it rebuilds are, per the
  2026-07-21 consumer audit, native `materialized='table'` for `stg_statsapi_lineups_wide` +
  `stg_statsapi_probable_pitchers` (a re-pivot/flatten — NOT a thin `lakehouse_ext` view, despite the
  header comments) and a view for `stg_statsapi_lineups`. So this op genuinely MATERIALIZES those SF
  tables intraday. It is redundant exactly when every intraday reader goes to the S3 parquet instead:
  - the **lineup monitor** reads the S3 `stg_statsapi_lineups_wide`/`_probable_pitchers` parquet directly
    (`_candidates_s3`) ONLY when **`LINEUP_MONITOR_S3=1`** — its default (`_candidates_sf`) still reads
    the SF views. So **`LINEUP_MONITOR_S3=1` is a HARD PREREQ** (already flipped + enforced on the box,
    2026-07-20).
  - the intraday **serving/predict** (`write_serving_store_intraday_op`, `lineup_predict`) read the SF
    views until **W7b-2** flips them to `--s3`.
  That S3 parquet is kept fresh intraday by `_schedule_lakehouse_intraday`'s `--w7b-only` build + the
  `W7B_SERVING_TABLES` refresh. **HARD PREREQ: `SCHEDULE_LAKEHOUSE_INTRADAY=1`** — the `--w7b` S3 rebuild
  that replaces this leg. If OFF, dropping the dbt rebuild would leave lineups_wide stale on BOTH paths →
  the monitor goes blind (post_lineup never fires). So `TICK_SF_FREE` is INERT unless
  `SCHEDULE_LAKEHOUSE_INTRADAY=1`, and it logs LOUD if set without it (keeps the dbt rebuild as a safe
  fallback). All other SF readers of these three models (eb_priors posterior fits, the `audit_serving_
  freshness` script, the deprecated `app/pages/*` Streamlit) are daily/offline or NOT-SHIPPED — served
  by the daily ext-refresh, never the 30-min tick.
- **`refresh_w1_external_tables.py` (no-arg):** it refreshes a broad set (games/lineups + W2/W3/W4/W5/
  W6/W7/W11tx), but the tick only *rebuilds* games/lineups (`--w3pre`/`--w7b`). Refreshing the other
  groups re-lists **unchanged** parquet (a data no-op — they're rebuilt by the DAILY run, not the tick).
  So skipping the whole refresh only stops the games/lineups ext tables from updating intraday — exactly
  the W7b-2-covered consumers. The daily refresh still runs. `backfill_lineup_state_scd2` reads the RAW
  `statsapi.monthly_schedule` directly (not these ext tables), so it is unaffected.

## The gate

```python
# pipeline/ops/intraday_ops.py
def _tick_sf_free() -> bool:
    # E11.20 phase-2a step 3. Requires SCHEDULE_LAKEHOUSE_INTRADAY=1 (the S3 --w7b rebuild that
    # replaces the dbt staging leg) — INERT without it so a lone TICK_SF_FREE can't blind the monitor.
    return (os.environ.get("TICK_SF_FREE") == "1"
            and os.environ.get("SCHEDULE_LAKEHOUSE_INTRADAY") == "1")
```
- `intraday_lineup_rebuild`: loud ALERT-skip when `_tick_sf_free()`; else run the dbt rebuild. If
  `TICK_SF_FREE=1` but `SCHEDULE_LAKEHOUSE_INTRADAY!=1`, log a loud misconfig warning and DON'T skip.
- `_schedule_lakehouse_intraday`: skip the trailing `refresh_w1_external_tables.py` when `_tick_sf_free()`.

## Ordering — the flip sequence (all operator, post-07-24, after AC-C)

1. monthly_schedule writer flip: `W11_RAW_WRITE_MODE=both` → soak/parity → **retire the export bridge**
   (`_schedule_lakehouse_intraday` + `lakehouse_schedule_export_op`) → `W11_RAW_WRITE_MODE=s3`.
2. W7b-2 flip: `W7B_INTRADAY_S3=1` (+ `W6_LAKEHOUSE_INTRADAY=1`), soak per its runtime gate.
3. Confirm on the LIVE box env (not docs): `SCHEDULE_LAKEHOUSE_INTRADAY=1` AND `LINEUP_MONITOR_S3=1`.
4. **Then** `TICK_SF_FREE=1`. Verify a full slate: lineups still confirm (monitor fires post_lineup),
   pick-detail lineup card populates, and `query_history` shows NO Snowflake session from the tick
   (`intraday_schedule_capture` / `intraday_lineup_rebuild`) during game hours.
5. Rollback = unset `TICK_SF_FREE` (instant; the SF legs resume).

Enforce (`env.required` + heartbeat) only after soak — same rollback-reverts-enforcement caveat as
`LINEUP_MONITOR_S3` / `W7B_INTRADAY_S3`.
