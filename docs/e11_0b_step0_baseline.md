# E11.0b — Step-0 baseline (MEASURE FIRST) + decision

**Date:** 2026-06-22 (measured) · **Decision (PM):** Option (b) — measure-only, defer the build.
**Re-measure:** ~2026-06-25/26 (2–3 days of post-T2 incremental cycles; aligns with the W1 parity check).

E11.0b's own rule is **MEASURE FIRST — don't migrate blind.** This note records the clean
*before* number so the post-T2 re-measure has a baseline, and documents why no Railway cron was
built this session.

## Why no build this session

1. **T2 is <1 day old.** E11.9-T2 (`feature_pregame_game_features(_raw)` full-CTAS → `incremental`,
   delete+insert) was committed **2026-06-22** — confirmed in-tree at
   `dbt/models/feature/feature_pregame_game_features.sql:29` and `_raw.sql:31`. The story requires
   re-pulling the bill "after a few days of post-T2 cycles." That data does not exist yet, and the
   06-22 signal shows no clear per-tick wall-clock drop yet (lineup_monitor avg 349s vs 06-21 404s /
   06-20 377s — within noise; the few post-deploy runs are swamped by morning pre-deploy runs).

2. **🔑 The two biggest meter consumers are OUT of E11.0b scope by architecture.**
   `lineup_monitor_job` and `statcast_catchup_job` (see `pipeline/jobs/sensor_jobs.py`) are **chained
   serving graphs**, not standalone dbt jobs — the dbt rebuilds are interleaved with and **gate**
   `lineup_predict` / `predict_today_morning` / `write_serving_store_op`:

   ```
   lineup_monitor: ingest_umpires → dbt_staging → dbt_feature → lineup_predict
                   → narratives → dbt_clv → write_serving_store
   ```

   You can't fire-and-forget the dbt (predict waits on it), so the only way to take their wall-clock
   off the Dagster meter is to move the **entire predict+serve chain** to Railway — which **is
   E11.1-Wsv** (the serving migration, flagged POST-JULY-1, parallel-run, parity-gated, do-NOT-rush —
   beta-user outage risk). Out of scope for E11.0b by design.

3. **The genuinely cron-direct-eligible slice is negligible** (see numbers below) — building
   multi-service Railway crons for ~6 min/day of meter, for an unsized post-T2 bill, is migrating
   blind for likely-tiny savings.

## Baseline numbers (the *before*)

### Dagster metered run-minutes/day (API-measured, the meter proxy)

Source: `penumbra-partners.dagster.plus` GraphQL, run `endTime − startTime` summed per job.
(Dollar figure — **$36.20 since 6/18 ≈ ~$240/mo** — is operator-sourced from the Dagster+ usage CSV;
the billing $ is not exposed via the run API. Use run-minutes as the API-measurable proxy.)

| Job | 06-19 | 06-20 | 06-21 | 06-22* | In E11.0b scope? |
|---|---|---|---|---|---|
| `lineup_monitor_job` | 113m | 151m | 54m | 52m | ❌ serving chain → E11.1-Wsv |
| `statcast_catchup_job` | 114m | 32m | 31m | 24m | ❌ serving chain → E11.1-Wsv |
| `daily_ingestion_job` | 21m | 27m | 72m | 19m | ❌ ends in predict+serve → E11.1-Wsv |
| `odds_current_rebuild_job` | 5m | 5m | 4m | 5m | ✅ cron-direct-eligible |
| `odds_clv_rebuild_job` | 1m | 1m | 1m | 1m | ✅ cron-direct-eligible |
| **TOTAL dbt-triggering** | **253m** | **215m** | **161m** | **101m*** | |

\* 06-22 is a partial day (measured mid-evening) and post-T2-deploy mid-day — not a clean post-T2 day.
Run COUNT also varies with game volume, so day-to-day totals are not directly comparable; the
re-measure needs full post-T2 days.

**⇒ The cron-direct-eligible scope (`odds_current_rebuild` + `odds_clv_rebuild`) is ~6 min/day —
< 5% of the metered minutes.** ~95% is serving-chain wall-clock that E11.0b cannot touch.

### Snowflake `WAREHOUSE_METERING_HISTORY` — COMPUTE_WH credits/day (context)

06-18: 11.19 · 06-19: 7.32 · 06-20: 7.65 · 06-21: 6.74 · 06-22: 5.79 (partial).
Trending down, but conflates all of E11.9 (A) redundant-rebuild removal + (B) ADD-COLUMN fix +
(C) tagging — not T2 in isolation.

### `feature_pregame` rebuild statements/day (QUERY_HISTORY)

Count is ~unchanged post-T2 (06-22: 161 `create or replace` stmts) and **this is expected** — the
incremental `delete+insert` still issues a `create or replace` for the temp table each tick. T2 cut
the **cost per rebuild** (7-day window vs all-history), **not the count**. So rebuild-count is the
wrong proxy; the per-tick **wall-clock** (lineup_monitor run duration) is the signal — re-measure that.

## Decision tree (post re-measure ~6/25)

- **If the Dagster bill has fallen to ~the old $50–100/mo** (likely — T2 trimmed the dominant
  lineup_monitor rebuild) → **CLOSE E11.0b**, or scope it to the single worst remaining cron-direct
  job only. Don't run a multi-service migration for a bill T2 already cut.
- **If still high** → migrate ONLY the genuinely cron-direct, NON-serving jobs
  (`odds_clv_rebuild` / `odds_current_rebuild`) to Railway crons (E11.4 pattern). **NOT** the serving
  chains — those move under E11.1-Wsv, carefully, post-July-1.

## Scope clarification

Moving W1's DuckDB ops (`ingest_statcast_to_s3_op` / `run_w1_lakehouse_op`) and the one-shot
`w1_parity_job` off Dagster does **NOT** belong to E11.0b — that's lakehouse BUILD overhead (the
parallel-validation window). Fold it into the **W1 decommission / W2 cron-build** work.

## How to re-measure (~6/25–26)

```bash
# Dagster metered run-minutes/day (full post-T2 days), per job:
uv run python scripts/ops/dagster_runs.py lineup_monitor_job 60     # + statcast_catchup_job, odds_*_rebuild_job
# Snowflake warehouse credits:
#   SELECT TO_DATE(start_time) d, ROUND(SUM(credits_used),2) cr
#   FROM snowflake.account_usage.warehouse_metering_history
#   WHERE warehouse_name='COMPUTE_WH' AND start_time >= '2026-06-18' GROUP BY 1 ORDER BY 1;
# Plus the operator's Dagster+ usage CSV for the $ before/after vs $36.20-since-6/18.
```
