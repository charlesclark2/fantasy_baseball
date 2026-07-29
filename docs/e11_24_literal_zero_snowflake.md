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
- ⚠️ **HALF A FLIP SAVES NOTHING.** The INSERT leg still opens a Snowflake session until the write
  leg is S3-only. 🚨 **The var is `W11_RAW_WRITE_MODE`, NOT `LAKEHOUSE_RAW_WRITE_MODE`** —
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

## Stage 2 — the remaining off-serving-path stragglers (next session)

**4. The three sequential-posterior state writers** (`update_{player,team,matchup_cell}_posteriors.py`).
Not a drop-in like Elo. `update_player_posteriors` and `update_matchup_cell_posteriors` already have
`--s3` for their *source* reads; what remains is the **stateful** sequential-posterior store
(read-modify-write) plus DDL, and `update_team_posteriors` has no `--s3` branch at all (it reads
`stg_batter_pitches`, `eb_bullpen_posteriors`, `mart_game_results` from Snowflake). Migrating a
read-modify-write store needs a store decision (parquet overwrite, as Elo did, vs DynamoDB) and its
own parity gate, because these posteriors feed served features.
📉 **Note the sequencing dividend:** these run inside `statcast_catchup_job`, so stage 1's gate (1b)
already removes ~5 of their ~6 daily executions. Their *marginal* wake share after 1b is small — do
them for literal-zero, not for a big credit delta.

**4b. `check_data_freshness.py`** — host cron at `30 12,17 * * *`, 24/7, connects to Snowflake and
reads `baseball_data.lakehouse_ext.stg_statsapi_games`, i.e. an external table **over S3**. That is a
pure DuckDB repoint (2 guaranteed resumes/day removed) and the cheapest remaining item.

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
