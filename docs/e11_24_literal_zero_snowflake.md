# E11.24 — LITERAL-ZERO SNOWFLAKE (the August-bill lever)

Status: **stage 1 CODE-COMPLETE, all levers default-OFF** (2026-07-29). Stages 2–4 scoped below.

## Why this story exists

E11.20 cut COMPUTE_WH resumes **177 → 44/day (−75%)** and the credit line barely moved (<15%).
That is not a failed measurement — it is what the E11.20-COST thesis predicts: ~80% of the bill is
**wake/idle burn**, and 44 resumes still spread across enough of the day that an X-Small warehouse
never sleeps in long stretches. **Reducing wakes ≠ killing wakes.** The warehouse only stops
metering when the resume count on a quiet window reaches ~zero, so every remaining waker has to go.

## The measured target list (7/29 census, 44 resumes on 7/28)

Resumes attributed by joining each `RESUME_WAREHOUSE` event to the first query at/after it.

| # | Waker | Share | Stage | State |
|---|-------|-------|-------|-------|
| 1 | Hourly `CREATE TABLE IF NOT EXISTS … team_elo_history` (a no-op DDL) | 14% | 1 | ✅ shipped, `E11_24_ELO_SF_FREE` |
| 1b | **Root cause of #1** — `statcast_catchup_job` re-fires hourly and runs the whole chain on ~5 fires that land nothing | (multiplies 1, 4 and part of "daily one-offs") | 1 | ✅ shipped, `E11_24_STATCAST_CATCHUP_GATE` |
| 2 | 24/7 hourly weather slate/venue `SELECT` | 14% | 1 | ✅ shipped, `E11_24_WEATHER_SF_FREE` (+ matched write flip) |
| 3 | `CREDENCE_API` metering query "waking the warehouse it measures" | **0% — REFUTED, see below** | 1 | ✅ shipped anyway, `SNOWFLAKE_MONITOR_WAREHOUSE` (backend + audit readers) |
| 4 | Raw-SQL stragglers: the 3 sequential-posterior state writers | part of daily one-offs | 2 | scoped below |
| 4b | `check_data_freshness.py` (host cron, 2×/day, 24/7) | ~2 resumes/day | 2 | scoped below |
| 5 | The dead `predict_today` Snowflake freshness branch | 0 (it is a read, not a waker) | 3 | **soak-blocked** |
| 6 | Intraday EB/lineup dbt rebuild chain | **41%** | 4 | **soak-blocked** |
| 7 | Drop the ext tables / `lakehouse_ext` mirrors → suspend/drop the warehouse | — | 5 | after 1–6 |

### The finding that reframes #1

The census flagged the hourly `team_elo_history` DDL as "NOT the daily `compute_elo` op — identify
the caller". The caller is **`statcast_catchup_job`, re-fired by `statcast_freshness_sensor` on an
hourly `run_key` from 04:00 ET until Savant publishes** (`statcast_freshness_sensor.py:160`). On a
normal morning that is ~6 fires, and ~5 of them land **no pitches** — yet each still runs two
`refresh_w1_external_tables.py` passes (an `ALTER EXTERNAL TABLE … REFRESH` storm), the bullpen
posterior dbt build, the three sequential-posterior writers, `compute_elo`, the umpire feature
rebuild, `predict_today_morning` and a serving write.

So the DDL was the *visible symptom*; the redundant re-fire is the cause, and it multiplies **every
Snowflake touch in the morning chain by ~6**. That is why the gate (1b) is shipped alongside the
Elo repoint (1) — repointing Elo alone would have moved the attribution, not the resume count.

## Stage 1 — what shipped (all default-OFF)

### 1. `compute_elo` → Snowflake-free (`E11_24_ELO_SF_FREE=1`)

Reads `mart_game_results` from the S3 lakehouse via DuckDB (through `register_lakehouse_views`, not
a hardcoded glob — the 2026-07-20 phase-1.5 P0 lesson) and writes `team_elo_history` straight to
`baseball/lakehouse/team_elo_history/data.parquet`. No Snowflake session at all.

**Parity verified 2026-07-29 (laptop, real S3):** 26,796 games → 53,592 rows.
Every row matches the current Snowflake-produced parquet to **5e-5** (the SF MERGE stored
`%.4f`-rounded values), **0** date mismatches, **0** rows only-in-new.

⭐ The overwrite additionally **deletes 135 stale 2018 `OAK` rows** the Snowflake MERGE could never
remove: `mart_game_results` now emits `ATH` for those games after the Athletics rebrand, so game
531832 carries three rows (`ATH`, `LAA`, and a dead `OAK`). A MERGE-only writer cannot delete, so an
upstream identity remap orphans rows forever; the full-overwrite native writer is self-correcting.
The orphans are inert today (nothing joins on `OAK`), so this is a cleanup, not a behaviour change.

🚨 **Same-flip consequence (INC-31 writer-uniqueness).** Two `SELECT *` mirrors wrote that same S3
key — `export_w8a_precursors_to_s3.py` and `export_features_to_s3.py`. Both now **skip**
`team_elo_history` under the lever. Leaving either live would publish a *frozen* Snowflake snapshot
over fresh Elo on every daily run (worse than INC-31's case, which only flipped column case). The
parquet columns stay **UPPERCASE** for the same reason — the Snowflake external table addresses
`VALUE:<KEY>` case-sensitively, so a lowercase write reads ALL-NULL through Snowflake while DuckDB
stays green. `team_elo_history` is `export_features_to_s3.py`'s only remaining table, so under the
lever that whole mirror becomes a loud no-op (its full retirement).

**No Snowflake consumer is stranded.** `feature_pregame_team_features`'s DuckDB branch reads the S3
view; its Snowflake branch is `select * from lakehouse_ext.feature_pregame_team_features` (i.e. also
over S3). `team_elo_history` is not in `W8A_TABLES`, so no ext table over it goes stale. The only
Snowflake reader left is `write_serving_store.py`'s non-`--s3` fallback, and `W7B_LAKEHOUSE_S3=1` is
live on the box.

### 1b. The statcast catch-up no-op gate (`E11_24_STATCAST_CATCHUP_GATE=1`)

`catchup_ingest_statcast` becomes a conditional output (`Out(Nothing, is_required=False)`): it always
runs the ingest, then yields no output when yesterday's pitches are *still* absent, so Dagster
**SKIPS** the rest of the chain. Verified against a real Dagster job (1.13.5): the run **succeeds**
in both branches and only the downstream step is skipped — a skip is not a failure, and the sensor
retries on the next hourly `run_key`.

- **Fail-OPEN by construction.** Any lakehouse read problem resolves to "run the chain". A transient
  S3 blip must never suppress the self-heal (the "silently never runs" outage class).
- **Same predicate as the sensor** (`lh_year('stg_batter_pitches', …)` + `game_date = ?`), so the
  gate cannot skip work the sensor would immediately re-request — that would be an infinite no-op loop.
- ⚠️ The chain contains `predict_today_morning`, so this flips **after** the E11.20 W8b soak closes.

### 2. Weather capture → Snowflake-free (`E11_24_WEATHER_SF_FREE=1`)

The hourly `weather-capture` cron invokes `ingest_weather.py` **five times per fire** (T-24/6/3/1h +
observed + the intraday series), and every one opened a Snowflake session just to ask "which outdoor
parks are on the slate?". All four slate reads now route through one `_slate_games()` helper, and the
dedup read (`_already_fetched`) resolves from the S3 `weather_raw` mirror.

- `ref_venues` is a **dbt seed** with no parquet, so the image now COPYs `dbt/seeds/ref_venues.csv`
  and reads it with DuckDB. The seed is the source of truth for the Snowflake table too.
- **INC-23:** `stg_statsapi_games.game_date` is an ISO VARCHAR in the lakehouse. It is cast at the
  use site (`::timestamptz AT TIME ZONE 'UTC'`) so callers get the same *naive UTC datetime*
  Snowflake's `TIMESTAMP_NTZ` returned — rather than leaking a string to four call sites.
- **Lean-image rule:** the reader comes from `utils.lakehouse_read` (guard-tested betting_ml-free),
  never `betting_ml.utils.lakehouse_monitor`. `duckdb` added to the image.
- ✅ **RESOLVED ON THE LIVE BOX 2026-07-29 — the write leg was ALREADY `W11_RAW_WRITE_MODE=s3`.**
  So every one of the 73 measured weather wakes came from the slate/venue READ alone:
  `ingest_weather.py` called `get_snowflake_conn()` UNCONDITIONALLY, regardless of write mode.
  `E11_24_WEATHER_SF_FREE=1` is the whole fix; no compose/write-leg change is required.
- ⚠️ The half-flip hazard still stands for anyone on a box where the write leg is `snowflake`
  or `both`: the INSERT would keep opening a session until the write leg is S3-only. 🚨 **The var is `W11_RAW_WRITE_MODE`, NOT `LAKEHOUSE_RAW_WRITE_MODE`** —
  `ingest_weather.py` calls `w11_write_mode()` (`W11_WRITE_MODE_ENV = "W11_RAW_WRITE_MODE"`; the W11
  Tier-A wave has its own switch, independent of the odds one). Setting the odds var here is a
  SILENT NO-OP — the W6_ODDS_SF_FREE class of bite, caught 2026-07-29 before it shipped. `needs_snowflake =
  do_sf or not weather_sf_free()` — so a half-flip degrades to "same as today", never to a lost write.
  Safe to flip the write: `stg_weather_raw_snapshots`' DuckDB branch already reads the S3 mirror and
  its Snowflake branch is a view over `lakehouse_ext`, so freezing native `statsapi.weather_raw`
  strands no consumer.

**Verified 2026-07-29 (laptop, real S3):** 15 outdoor games for 7/29, 14 completed outdoor for 7/28,
dedup sets non-empty (9 observed, 10 at T-6), `game_datetime_utc` returned as `datetime`, not `str`.

### 3. Metering queries stop waking the warehouse they measure

`get_monitoring_connection()` (and a `warehouse=` param on both loaders) routes every
`snowflake.account_usage` read onto `SNOWFLAKE_MONITOR_WAREHOUSE` (default `MONITOR_WH`).
This is also what makes the E11.24 proof itself trustworthy: the 7/29 census had to **discard its own
UTC day** because the audit queries landed on it.

Operator DDL (once, ACCOUNTADMIN):

```sql
CREATE WAREHOUSE IF NOT EXISTS MONITOR_WH WITH WAREHOUSE_SIZE='XSMALL'
  AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE;
GRANT USAGE ON WAREHOUSE MONITOR_WH TO ROLE ACCOUNTADMIN;
```

### ✅ The `CREDENCE_API` caller — FOUND, and the story's framing of it is WRONG (2026-07-29)

It is **your own admin cost dashboard**: `app/backend/routers/admin.py::snowflake_credits` and
`app/backend/routers/finances.py::_snowflake_costs_by_month`, both reading
`SNOWFLAKE.ACCOUNT_USAGE.**METERING_DAILY_HISTORY**`. The first search missed them because it
grepped `warehouse_metering_history` — a different view. 88 executions since 7/17, still firing.

🚨 **But measured against RESUMES it is not a waker at all: 0 of 636 resumes over 8 days had a
`METERING_DAILY_HISTORY` query first-after-resume, and on 7/28 — the census day — `CREDENCE_API`
caused 0 resumes.** The dashboard is a **passenger**: it only ever runs while the warehouse is
already awake for pipeline work. The story's "self-inflicted wake" and the roadmap's "26 → 6 wakes"
came from the hour-bucket proxy the census itself flagged as upper-bounded, not from resume events.

⇒ **Target 3 is not a cost lever today. Do not book a saving for it.** Two things are still true
and are why it shipped anyway:

1. **It becomes a waker the moment the story succeeds.** Once targets 1/2/6 quiet the warehouse
   enough that it genuinely sleeps, "open the admin cost page" *is* the first query after a resume
   — the page that displays the Snowflake bill starts billing for the privilege. Fixing it now is
   cheap; fixing it after the fact means re-opening a solved question.
2. **The real observer effect is ours, not the app's** — 15 resumes in 8 days came from
   `DBT_RW`/`ACCOUNTADMIN` audit sessions (the cost scripts + interactive MCP sessions) reading
   `ACCOUNT_USAGE`. That is what `get_monitoring_connection()` removes, and it is why the 7/29
   census had to discard its own UTC day.

Re-run this after any change to confirm the class stays dead:

```sql
select user_name, role_name, warehouse_name, count(*) n,
       min(start_time) first_seen, max(start_time) last_seen
from snowflake.account_usage.query_history
where start_time >= dateadd(day, -7, current_timestamp())
  and query_text ilike '%ACCOUNT_USAGE%'
group by 1,2,3 order by n desc;
```

### 4. The dead derivative-odds export bridge — RETIRED (2026-07-29)

Not on the original target list; found by sweeping the monitoring/DQ family. `export_odds_raw_to_s3.py`
was still listing two tables as **live** sources while the daily `lakehouse_w3pre_flatten_op` invoked
the derivative one on every run. Both writers were long retired:

| Table | SF `max(ingestion_ts)` | Days stale | Rows in the 7-day export window |
|---|---|---|---|
| `oddsapi.derivative_odds_raw` | 2026-07-07 00:00:07 | 22 | **0** |
| `oddsapi.mlb_events_raw` | 2026-06-04 23:25:12 | 55 | **0** |

Derivative capture reads `W11_RAW_WRITE_MODE`, which the box has at `s3`, so its Snowflake writer
stopped and the `--since <7d>` export had been selecting zero rows and writing nothing. Its only
remaining effect was resuming `COMPUTE_WH` (~5 provisioning waits / 8 days). **This is the 4th instance
of the retired-writer-bridge class** (after `mlb_odds_raw` 7/05, `monthly_schedule` 7/23, and
`derivative_odds_raw`'s own stale entry in `check_data_freshness.py`).

Safety checks before removal — the class has caused one P0, so none were assumed:
- **No clobber.** Zero rows selected ⇒ no frozen-over-fresh overwrite.
- **No prune.** `prune_partitions()` is `monthly_schedule`-only and only when `--since` is absent ⇒ *not*
  the partition-deleting variant that starved probable pitchers in July.
- **No stranded consumer.** No dbt `source()` reader; a repo-wide `grep -rIn` (the INC-27 rule — the dbt
  DAG cannot see raw-SQL string consumers) found only comments, the parity script, and the writer's own
  DDL. `stg_derivative_odds`' Snowflake branch already reads `lakehouse_ext`.
- The writer's `CREATE TABLE IF NOT EXISTS` is correctly gated inside `if do_sf:` ⇒ unlike
  `team_elo_history` it was *not* additionally a no-op-DDL waker.

Shipped: `SOURCES` is now **empty** (both tables moved to `RETIRED_SOURCES` with the evidence); the
bridge call removed from `lakehouse_w3pre_flatten_op` (the `--w3pre-only` flatten stays — that is the
real work and it reads S3); both registered in `RETIRED_NATIVE_SOURCES` so a 5th instance cannot merge;
`mlb_events_raw` added to `parity_check_w3pre.py`'s `FROZEN_SOURCES` — that one matters, because with S3
correctly *ahead* of a frozen Snowflake the pre-flight reads the gap as a doubled partition and advises
`aws s3 rm` on live capture data. Host cron line 35 was already commented out (verified, not assumed),
so nothing was left calling a now-erroring `--source`.

## Stage 2 — ⛔ THERE IS NO INDEPENDENT STAGE 2. Everything left is gated on target 6 (2026-07-29)

A full sweep of every **automatically-invoked** Snowflake toucher (the ~200 files that import a SF
connector are mostly hand-run research scripts and cost nothing — the population that matters is the
`_run_script` set in `pipeline/ops/`, the host `capture.crontab` lines, the sensors, and the API)
overturns this section's original premise. **The remaining writers cannot leave Snowflake
independently, because their OUTPUT tables are read by Snowflake-executing dbt models.**

**The coupling, concretely:**

| Residual writer | Read leg | Write leg | What pins the write to Snowflake |
|---|---|---|---|
| `update_{player,team,matchup_cell}_posteriors.py` (3) | partly `--s3` already | SF stateful read-modify-write | `feature_pregame_game_features_raw.sql` reads `{{ source('betting','team_sequential_posteriors') }}`; the `eb_posteriors/*.sql` family (5 models) reads `player_sequential_posteriors` |
| The 8 signal generators | ✅ **already DuckDB/S3** | SF SCD-2 via `scd2_writer.scd2_upsert` | `feature_pregame_sub_model_signals.sql` selects `from mart_sub_model_signals` on Snowflake |

So the wake is unavoidable while the reader is a SF-native dbt model: you cannot move the write
without moving the read, and the read *is* target 6.

**🔧 CORRECTION to 4b (my own earlier claim, wrong).** I described `check_data_freshness.py` as "a pure
DuckDB repoint, the cheapest remaining item." It is not. Only `_is_game_day` reads `lakehouse_ext`;
**7 of its 8 monitored tables are `baseball_data.betting.*` Snowflake-resident tables** — and they are
precisely the outputs of the writers in the table above (`player_/team_/matchup_cell_sequential_posteriors`,
`eb_bullpen_team_posteriors`, `mart_player_archetype_posteriors`, `eb_park_factors_raw`,
`player_profiles_raw`). A monitor cannot be repointed off a store its subjects still live in. 4b is a
**dividend of target 6, not a precursor to it.**

**✅ The store decision is already made — and the code comments saying otherwise are STALE.** All 8
generators carry a variant of *"re-implementing SCD-2 accumulate in DuckDB is the W7a-wipe class the W9
design forbids."* True but obsolete: `deltalake==1.6.1` is pinned and **`scripts/utils/delta_lake.py`
already ships `merge_upsert()`** — a partition-pinned `when_matched_update_all / when_not_matched_insert_all`
MERGE (delta-rs writes Delta; DuckDB still cannot, per the E11.20a spike). History-preserving accumulate
outside Snowflake is therefore a solved problem as of the E11.20 rollout. **The blocker was never the
store — it is the dbt readers.**

⭐ **The leverage when target 6 unblocks:** `betting_ml/scripts/scd2_writer.py::scd2_upsert` is a *single
shared function* behind all 8 generators. One Delta port there migrates 8 daily writers at once — do not
migrate them one-by-one.

📉 **And the marginal prize is small anyway:** these writers run inside `statcast_catchup_job`, so stage
1's gate (1b) already removes ~5 of their ~6 daily executions. Post-1b they are a literal-zero
housekeeping item, not a credit lever.

**Conclusion: target 6 is not one target among several — it is the gate on 4, 4b and 7.** That is the
same conclusion the provisioning-wait census reached from the other direction (target 6 = 67.7% of
waits, not the 41% the first census estimated). Two independent instruments, one answer. Correct order
is therefore **6 → 4 → 4b → 7**, and nothing in 4/4b should be attempted before 6 lands.

### 🔧 CORRECTION to the heading above — "everything" was too strong. One family IS independent.

The coupling argument is sound for the **writers** (posteriors + generators). I over-generalized it to the
whole residual. A by-user attribution shows a family that has nothing to do with the dbt chain:

| User | Provisioning waits (8d) | Distinct query shapes |
|---|---|---|
| `DBT_RW` | 713 | 114 ← target 6 + the pipeline |
| **`CREDENCE_API`** | **56 (7.1%)** | **4** |
| `CCL1196` (operator Snowsight) | 24 | 8 |

**56 wakes from 4 queries, and the live API is the caller — which is also a CLAUDE.md violation
("Snowflake … never on a request path").** 42 of the 56 are one shape: the
`ACCOUNT_USAGE.METERING_DAILY_HISTORY` roll-up behind `/admin/snowflake-credits` and `/admin/finances`.

⭐ **The mechanism, nailed:** it fires **2× per hour around the clock** (7/27: hours 01–09 unbroken).
That is not a human opening a page — both endpoints carried `staleTime: 3_600_000` in
`frontend/app/admin/page.tsx`, so **an admin tab left OPEN refetched both hourly, forever.** The page
that displays the bill was 5.3% of the wakes that produce it. Fixed on both sides:
- **server:** both queries routed to `MONITOR_WH` (already shipped) ⇒ they can never wake the warehouse
  they measure;
- **client:** `staleTime` → **12h**, because the payloads are MONTH-grained *and* `account_usage`
  metering latency is ~12h+ (E11.20-COST lesson-1) ⇒ an hourly refetch was mathematically guaranteed to
  return identical numbers.

⚠️ **Both fixes are committed but NOT deployed** — the metering shape's `last_seen` is **7/29, today**, on
`COMPUTE_WH`. This family only stops on the next **Lambda + Vercel** deploy. It is the third time target 3
flipped verdict (refuted → un-refuted → mechanism identified); the story's framing was right each time.

The remaining ~24 waits are the operator's own Snowsight browsing (`POLICY_REFERENCES` 9,
`COST_INSIGHTS`/`ACCOUNT_ROOT_BUDGET`/metering 8). **Behavioural, not code** — worth knowing that opening
Snowsight cost pages wakes `COMPUTE_WH`, so audit from `MONITOR_WH` (`use warehouse MONITOR_WH` first).

### ✅ VERIFIED LIVE 2026-07-29 15:17 — the metering repoint works

`information_schema.query_history()` (near-real-time; **not** `account_usage`, which lags 45–90 min and
made the first check ambiguous) after loading the admin page post-deploy:

| Time | Warehouse | Shape |
|---|---|---|
| 15:17:33 | **MONITOR_WH** | `SUM(CREDITS_USED_COMPUTE)…` ✅ (prov 219ms — woke MONITOR_WH, exactly the intent) |
| 15:17:34 | **MONITOR_WH** | `SUM(CREDITS_USED_COMPUTE)…` ✅ |
| 15:17:29/31/34 | COMPUTE_WH | the 3 non-metering shapes (see below) — by design, not a miss |

⚠️ **Instrument note:** the first post-deploy check looked like a failure because a `dateadd(hour,-6)`
window still contained a PRE-deploy row — identified by its identical millisecond (`.827`). **For "did the
thing I just did work", use `information_schema.query_history()`; reserve `account_usage` for trends.**

### 🚩 The 3 remaining `CREDENCE_API` shapes — a TARGET-7 BLOCKER and a LATENCY defect, not a cost lever

Measured over 8 days. **Executions, not provisioning waits** — waits undercount a request-time read badly,
since only the call that happens to wake the warehouse is counted:

| Endpoint | Executions | Waits | avg ms | **max ms** |
|---|---|---|---|---|
| admin cost panel (fixed above) | 86 | 43 | 2,652 | **24,344** |
| **`/pipeline/status`** — the PUBLIC dashboard status dot | 75 | 3 | 423 | **19,015** |
| admin model freshness (`model_registry`) | 46 | 5 | 658 | **19,894** |
| admin live served version (`daily_model_predictions`) | 46 | 7 | 364 | 999 |

⇒ the residual cost is only ~14 waits, **but a request-time Snowflake read that occasionally takes 19–24
SECONDS is a serving-latency defect.** When the warehouse is asleep the dashboard dot blocks for ~19s. This
is exactly what CLAUDE.md's "Snowflake … never on a request path" rule exists to prevent.

**Why this is NOT a safe drive-by fix** (do it as a scoped story, with a parity check):
- 🧨 **E9.26b landmine:** the obvious repoint — read `daily_model_predictions` from the lakehouse — is the
  read that **reliably FAILS inside the API Lambda** while working everywhere else, and `lakehouse_query`
  **catches-and-returns `[]`**, so it would fail *silently*. The narrowest-mart rule applies: a
  single-column `DISTINCT model_version` may be fine where the 94-col join was not, but that must be
  proven **in the Lambda**, not locally.
- `/pipeline/status` is **user-facing** (the dot's green/amber/red semantics), and the serving store is
  **not** a drop-in mirror: `write_api_cache.py` / `write_serving_store.py` derive their own
  `pipeline_status` from prediction AGE, they do not copy the 9-column `betting_ml.pipeline_status` row.
  A repoint changes the derivation ⇒ needs a semantics parity assertion before it ships.

⇒ **Ordering: this belongs with target 7 (every `COMPUTE_WH` caller must be gone before the warehouse can
be dropped), not with the cost stages.** Do not attempt it during the W8b soak.

### ✅ The retired-writer-bridge family is now fully closed — verified in the wake data

Each removal is visible as a hard stop, which is the cleanest possible confirmation the bridges are dead:

| Frozen-table `DISTINCT ingestion_ts` scan | Waits (14d) | Last seen | Status |
|---|---|---|---|
| `statsapi.monthly_schedule` | 15 | 2026-07-25 | already dead |
| `oddsapi.mlb_odds_raw` | 14 | 2026-07-27 | already dead (removed 7/27) |
| `oddsapi.derivative_odds_raw` | 11 | **2026-07-29** | the one retired today — stops at next deploy |

`export_w11_raw_to_s3.py` still lists 4 sources but has **no live caller** (no non-comment reference in
`pipeline/` or the crontab), so it contributes nothing.

📉 **Total waits are already trending down hard** — 215 (7/19) → 130 → 95 → 132 → 113 → 100 → 111 → 88 →
78 → 69 (7/28), i.e. roughly **−68% since 7/19** off the E11.20 phase-2a/2b flips. ⚠️ Do not read 7/29 as
a data point; the day is partial and `account_usage` lags.

### ✅ PRE-VERIFIED FOR 8/1 — the umpire idempotency-gate premise is CONFIRMED, and more strongly than claimed

I had asserted the umpire chain is "an idempotent no-op on nearly every tick" from code reading. Measured
2026-07-29 (on `MONITOR_WH`, so the audit did not contaminate):

| Evidence | Value |
|---|---|
| Umpire-chain query executions | **~100–165 / day** (the 117 figure was only the subset that had to *wake* the warehouse) |
| Rows ever produced by the live assignment feed (`data_source='statsapi'`) | **30**, across **6 dates**, since 2026-05-18 |
| `min(loaded_at)` vs `max(loaded_at)` per game_date | **IDENTICAL on all 6 dates** ⇒ the assignment is written in **exactly ONE load stamp** and never re-written |

⇒ **essentially every umpire-chain fire after the slate's single write is a pure no-op.** A per-slate
idempotency gate is justified, and it is structurally the same gate as the shipped 1b. **Gate key:** "is
there an assignment row for this slate whose `loaded_at` is newer than the last rebuild?" — because the
feed writes once, that fires exactly once per slate instead of ~100×.

⚠️ **Design caution for whoever builds it:** the gate must key on *assignment newer than last rebuild*,
not on "already rebuilt today" — and it must not entrench the lateness documented below.

### 🚩 SEPARATE FINDING (not E11.24 — flagging, not chasing): the HP-umpire assignment lands AFTER first pitch for ~half the slate

Found while verifying the above; it is a **serving-quality** issue, not a cost one, and it deserves its
own story rather than a drive-by fix.

- The assignment feed **only started working on 2026-07-27** (before that: 1 row on 4 scattered dates;
  7/27 and 7/28 have 11 and 15 rows = exactly their game counts).
- It lands at **23:16 UTC (7/27)** and **23:09 UTC (7/28)** — and **6 of 11 (55%) and 6 of 15 (40%) games
  had ALREADY STARTED** by then.

That is precisely the window story 30.5 exists to beat ("ingest the HP umpire on the afternoon lineup path
so it is available BEFORE the re-score, the actionable bet"). ⚠️ **Do not read the 1.000 historical
coverage as health:** 30 assignment rows cannot cover ~150 games — past-date coverage comes from the
`umpscorecards` **post-game tendency** feed backfilling (26,657 rows), not from the pregame assignment. The
two feeds share a table and only `data_source` distinguishes them, so a naive coverage check on this block
looks perfect while the pregame path is missing ~half the slate.
📉 Note this makes the cost case *stronger*, not weaker: the chain re-runs ~100×/day to serve a feed that
writes once, late.

## Stages 3–4 — SOAK-BLOCKED until the E11.20 W8b soak exits (2026-07-31)

The E11.20 guardrail is **one serving-flip per soak**, and the 7/30 no-false-abstain attribution must
stay clean. Nothing in stage 1 touches the predict/serving path.

**5. Remove the dead `predict_today` Snowflake freshness branch.** `W8B_FRESHNESS_S3` flipped
2026-07-29, so the Snowflake leg is dead weight — and it is the leg that carried the 7-hour
`TIMESTAMP_LTZ`→`::timestamp_ntz` bug that false-abstained every slate 7/24→7/29. Removal must land
**with a branch-parity assertion**: score the SAME slate through both branches and assert they agree,
because a single-branch unit test structurally cannot catch a SQL timezone bug. This moves **zero**
wakes (the gate is a read inside `predict_today`, not a waker) — it is a correctness/decommission
item, so do not expect it in the credit series.

**6. The intraday EB/lineup dbt rebuild chain — 41%, the single biggest remaining waker.** On the
serving/predict path, highest regression risk, and the place a false-abstain would recur. Do it last,
alone, with the full runtime gate: repoint → real box run → measure resumes before/after.

**7. Drop the ext tables / `lakehouse_ext` mirrors, then suspend/drop the warehouse.** Before deleting
**any** S3 layout or Snowflake object: `grep -rIn` the repo for the **PATH string** (the prefix/glob),
not just the table name. A Snowflake `access_history` zero-reader check **cannot see DuckDB/S3 path
readers** — that is exactly how phase-1.5 served a zero-prediction slate.

## Measuring each cutover (do not assume)

Before/after, on the **laptop**, per the E11.20-COST methodology — resumes, not elapsed-seconds:

⚠️ The column is **`TIMESTAMP`** (not `timestamp_start`), and you must filter
`event_state = 'STARTED'` — `RESUME_WAREHOUSE` and `RESUME_CLUSTER` are separate event rows, so an
unfiltered count roughly doubles. Verified against the live view 2026-07-29.

```sql
select to_char(convert_timezone('UTC', timestamp)::timestamp_ntz, 'YYYY-MM-DD') as utc_day,
       count(*) as resumes
from snowflake.account_usage.warehouse_events_history
where event_name = 'RESUME_WAREHOUSE' and event_state = 'STARTED'
  and warehouse_name = 'COMPUTE_WH'
  and timestamp >= dateadd(day, -14, current_timestamp())
group by 1 order by 1;
```

Attribution (which family owns each resume) joins each resume to the first query at/after it:
`qualify row_number() over (partition by resume_ts order by start_time) = 1`.
**Run it on `MONITOR_WH`** (`use warehouse MONITOR_WH;`) or the audit becomes a line in its own
results — measured below at 15 resumes in 8 days.

### 🔧🔧 METHODOLOGY CORRECTION — use `queued_provisioning_time`, NOT first-query-after-resume

**"First query at/after the resume event" systematically misattributes**, and it is the method both
the E11.20 census and this doc's first draft used. The query that *causes* a resume starts
**before** the resume event is recorded, so `start_time >= resume_ts` filters the true cause out and
credits whatever ran next. Applied here it ranked
`GRANT SELECT … TO ROLE CREDENCE_API_RO` as the **#1 residual waker at 111 resumes** — a
metadata-only statement that does not need a warehouse at all, and which does not appear anywhere in
the provisioning data. It also left a 53% unclassifiable "other" bucket.

⭐ **The right instrument is `query_history.queued_provisioning_time > 0`** — a query only queues on
provisioning if it *waited for the warehouse to start*, so it names the waker directly. It leaves
**3.7%** unclassified instead of 53%.

```sql
select left(regexp_replace(query_text,'\s+',' '),95) as waker_query,
       count(*) as provisioning_waits,
       round(avg(queued_provisioning_time)/1000,1) as avg_wait_s
from snowflake.account_usage.query_history
where warehouse_name = 'COMPUTE_WH'
  and start_time >= dateadd(day, -8, current_timestamp())
  and queued_provisioning_time > 0
group by 1 order by provisioning_waits desc;
```

### Measured baseline — 8 days to 2026-07-29, 802 provisioning waits

| Waker | Waits | Share | Status |
|---|---|---|---|
| **6. intraday EB/lineup + feature dbt chain** | 543 | **67.7%** | soak-blocked |
| 2. weather slate/venue | 74 | 9.2% | ✅ shipped |
| `pipeline_run_log` INSERT (lineup monitor audit) | 62 | 7.7% | see caveat |
| 3. admin/finances cost dashboard | 43 | 5.4% | ✅ shipped |
| 1. `compute_elo` games read | 34 | 4.2% | ✅ shipped |
| still unclassified | 30 | 3.7% | — |
| audit/metering (our own sessions) | 16 | 2.0% | ✅ shipped |

**🚨 This REVERSES the "target 3 is refuted" finding above.** The cost dashboard *does* wake the
warehouse — **43 provisioning waits in 8 days (~5/day)**. The "0 of 636 resumes" reading was an
artifact of the broken heuristic, not evidence. Target 3 as the story specified it was correct, and
shipping it was the right call for the stated reason and not only the forward-looking one.

**Target 6 is 68%, not the census's 41% — it is not one target among several, it is the story.**
Everything else combined is under a third of it.

⚠️ **`pipeline_run_log` (62) is NOT the free win it looks like.** `lineup_monitor.py` already skips
that INSERT on a *quiet* tick (the phase-2a guard); the 62 are *triggering* ticks, and the
`lineup_monitor_job` they fire does Snowflake work moments later — so removing the INSERT most
likely **shifts** the resume to the dbt step rather than removing it. Do not book it as a saving
without measuring after target 6 lands.

### Sub-family decomposition (what to fix, in order)

| Sub-family | Waits | UTC hours | Owner |
|---|---|---|---|
| **umpire chain** (`stg_statsapi_umpire_game_log` 52 + `feature_pregame_umpire_features` 60) | **116** | **13–23** | lineup_monitor tick |
| `stg_statsapi_lineups_wide` CTAS | 78 | slate hours | lineup_monitor tick |
| `stg_statsapi_probable_pitchers` CTAS | 65 | slate hours | lineup_monitor tick |
| `int_bullpen_ali_by_season` | 39 | **08–13** | statcast catch-up |
| `compute_elo` | 34 | **08–13** | statcast catch-up |
| `feature_pregame_lineup_features` / `_starter_features` | 55 | slate hours | lineup_monitor tick |

Two things fall straight out of the hour distribution:

1. **The shipped catch-up gate (1b) is worth ~2× what target 1 alone was.** `compute_elo` (34) and
   `int_bullpen_ali` (39) are **both** confined to 08:00–13:00 UTC — exactly the catch-up re-fire
   window — confirming from data what the code review predicted. The gate takes **~73 waits (9%)**,
   not 34.
2. ⭐ **The umpire chain is the largest single sub-family in target 6 (116, ~14.5/day, hours 13–23)
   and it is the SAME no-op-re-fire pattern.** `lineup_ingest_umpires` is the *first* op of
   `lineup_monitor_job`, which ticks every ~10 min through the slate — but the HP-umpire assignment
   is posted once per afternoon and does not change. So the ingest + `stg_statsapi_umpire_game_log`
   + `feature_pregame_umpire_features` rebuild are idempotent no-ops on nearly every tick. **A
   per-slate idempotency gate there is the highest-value item in target 6, and it is structurally
   the same fix as 1b** — do it first when the soak lifts.

⛔ **Do not assume wake↓ ⇒ credit↓** (the E11.20 lesson). The win is legible in RESUMES; the credit
line only moves once the warehouse actually stays suspended for long stretches.
🚨 **Clean-baseline caveat:** use **≤7/28** as the pre-flip reference. 7/29 is contaminated by the
census's own audit queries — which is what stage 1's `MONITOR_WH` change permanently fixes.

## Exit criterion

`warehouse_events_history` shows near-zero `RESUME_WAREHOUSE` on a **zero-game window**, the warehouse
stays suspended, and August metering trends to ~$0. The Bedrock narrative path is unaffected (SF
Cortex is already retired).
