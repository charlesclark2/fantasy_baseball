# MLB-INC-0917 — a transient W3 failure skipped the whole daily job, including the only odds-staging writer

Spec: `plan_specs/mlb/mlb-inc-0917.yaml`. Fix: `betting_ml/monitoring/lakehouse_retry.py`, wired in
`pipeline/ops/daily_ingestion_ops.py`, guarded by `betting_ml/tests/test_mlb_inc_0917_lakehouse_retry.py`.

## 1. The page

INC-41 paged `stg_oddsapi_odds` STALE: 1801 active-minutes against its 1800 SLA, with the content
timestamp stuck at the 2026-09-15 ~12:00Z build. The monitor was right. MLB-LAKE2 had made
`lakehouse_w3pre_flatten_op` (in the 12:00Z `daily_ingestion_job`) the table's only writer and added
this SLA so that a stopped writer would page. The SLA is **not** widened: it fired one minute past its
bound on a writer that had genuinely stopped.

## 2. Diagnosis — none of the spec's three forks

| Fork | Result | Evidence |
|---|---|---|
| (1) `W11_W3PRE_DAILY` regressed | **Refuted** | `=1` in the box `.env` (mtime 09-14 04:10Z, unchanged) and in both `dagster-codeloc` and `dagster-daemon`. All seven neighbouring gate flags are also `1`. |
| (2) the op did not run | **Confirmed, for an upstream reason** | Run `2b460fb5` (09-16 12:00:23Z) went to **FAILURE**. `lakehouse_w3_marts_op` failed at 12:26:21Z, and W3pre logged "Dependencies … failed. Not executing." |
| (3) the op ran green but did not advance the table | Not applicable | — |

**The W3 error.** S3 returned 403 `RequestTimeTooSkewed` while `run_w1_lakehouse.py:2741` bound
`CREATE OR REPLACE VIEW stg_batter_pitches`. The INC-43 salvage (#770) preserved the full diagnostic;
before that fix, this error would have surfaced as a destroyed Unicode error.

**Timings.** W3 took **998s** on 09-16, against 250s, 251s and 249s on 09-13/14/15. W2 bound the same
view minutes earlier on 09-16 in its usual 272s. The same W3 build also succeeded at 08:00Z that day,
inside `odds_clv_rebuild_job` (whose `run_w1_lakehouse --w6` path rebuilds W1, W3 and W6). **The
failure was transient.**

**Mechanism: not measured.** This is the INC-42 class. INC-42's failures landed at 1044.7s and
1056.1s, and this one at about 998s — all three past S3's 900s SigV4 tolerance. That is consistent with
INC-42's open hypothesis H ("DuckDB signs once per query") and is a third consistent observation, not a
confirmation. INC-42's "the glob grew too large" lead does **not** explain this failure: the glob is 366
files / 1.09 GB, and it bound normally in W2 minutes earlier.

**What was ruled out:**
- **A concurrent rewrite of the pitch glob.** The ingest's 14-day lookback rewrote the 09-01..09-15
  files between 12:00:38 and 12:02:48Z, before W3 started at 12:09:42Z. The key named in the error
  (`game_date=2026-05-26`) was last written on 06-26.
- **A deploy killing the run.** No CD deploy ran between 07:11Z on 09-16 and 03:39Z on 09-17.
- **The 08:00Z lakehouse writes as flag evidence.** `odds_clv_rebuild_job` runs `--w6`, which never
  builds W3pre, so those writes say nothing about the flag.

## 3. Impact — larger than the page

Every HALT-tier op after W3 was skipped:
- W3pre, W6, W7b, spine/odds-bridge, W8a, W8b and the W11 tail
- `dbt_daily_build` and the signal generators
- **`predict_today_morning`** and the serving writes

**The 09-16 morning tier never served.** The prediction mirror has no ~13:xx `feature_store` batch for
09-16, compared with 13:16 on 09-14 and 13:18 on 09-15. The slate ran on 22 `intraday_assembly` rows
until the lineup rebuild landed at 20:41Z, which then added 8 `feature_store` rows. `best_alpha=0`, so no
bet rode on it. **Nobody re-executed the failed run.**

## 4. Fix — one bounded, loud retry

All nine ops below are full, idempotent rebuilds, so a second attempt is safe.

- **Retried** (`RetryPolicy(max_retries=1, delay=60)`):
  - W1, W2, W3, W3pre, W6
  - the mirror-tier W7b, spine, W8a and W8b ops (these raise only when their cutover flags are on,
    which they are)
- **Not retried**, each with its reason stated in the registry:
  - `lakehouse_schedule_export_op` does no work, so it cannot fail.
  - `lakehouse_w11_nightly_op` swallows its own failures, so a retry could never trigger.
  - `lakehouse_delta_maintenance_op` is WARN tier.
- **Keyed on the op failing.** The retry never matches error text (the NCAAF-LAKE1 lesson).
- **Loud.** Each retried attempt logs `[METRIC] lakehouse_op_retry=<op> attempt=N` and pages WARN
  (`dedup_key` is per op), so a recovered transient is counted rather than hidden inside a green run.
  Those counts are the evidence INC-42's hypothesis H still needs.
- **Bounded, per op.** For every capped op, `cap × 2 + 60` stays below the 14,400s `run_monitoring` cap.
  In the pathological case where every capped op times out twice, the job is still ended by run
  monitoring; that case is stated here, not hidden.
- **A persistent failure behaves as before.** It fails after the retry and pages CRITICAL through
  `run_failure_alert_sensor`.

**Verification.** Proven under the daily job's own `in_process_executor`: a failed attempt emits
`STEP_UP_FOR_RETRY` (no `STEP_FAILURE`, no failure hook), and the downstream op runs. Every one of 11
deliberate source breaks turned the guard RED.

## 5. Restore

Operator ran `run_w1_lakehouse.py --w3pre-only` on the box at ~04:20Z on 09-17. It reported
`w3pre_tier_verdict=OK`, with budget fraction 0.197 against LAKE2's 0.172 comparator.

Content check from the parquet itself: `stg_oddsapi_odds` `max(ingestion_ts)` = **2026-09-17 04:00:04Z**
(9,829,486 rows); `stg_derivative_odds` = 2026-09-17 01:30:04Z. Still owed:
- the next daily fire advancing these tables unattended
- the INC-41 monitor clearing
