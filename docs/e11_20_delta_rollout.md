# E11.20 — Delta Lake + Polars rollout (PHASE 1) + the `run_w1_lakehouse_op` decomposition

**Status:** PHASE-1 CODE-COMPLETE 2026-07-10 · box backfill/measurement PENDING (operator run-order §6)
**Prereq:** E11.22 signed off 2026-07-07 ✅ · **Spike input:** `docs/e11_20a_delta_polars_spike.md` (🟢 GO)

E11.20 is a MAJOR workstream; per the spike's own rollout guidance ("hot/high-churn tables
first, NOT a big-bang") it ships in phases. This doc is the phase-1 record + the template
the later phases (and the fall's ×3 multi-sport replication) follow.

---

## 1. What phase 1 delivers

### 1a. ⭐ The `run_w1_lakehouse_op` DECOMPOSITION (live for everyone, no flag)

The single HALT-tier monolith (8+ sequential subprocess stages, one 45-min cap, one retry
unit, one opaque duration) is now **11 per-wave Dagster ops** wired in the daily job in the
monolith's exact order — each independently runnable, retryable, and separately timed
(the E11.21 attribution requirement falls out of the per-op Dagster durations):

| # | Op | Invokes | Tier |
|---|----|---------|------|
| 1 | `lakehouse_schedule_export_op` | `export_odds_raw_to_s3 --source monthly_schedule` | HALT |
| 2 | `lakehouse_w1_pitch_marts_op` | `run_w1_lakehouse.py --w1-only` (Delta-aware) | HALT |
| 3 | `lakehouse_w2_marts_op` | `--w2-only` (NEW flag) | HALT |
| 4 | `lakehouse_w3_marts_op` | `--w3-only` | HALT |
| 5 | `lakehouse_w3pre_flatten_op` | derivative bridge + `--w3pre-only` | HALT when `W11_W3PRE_DAILY=1`, ALERT-skip off |
| 6 | `lakehouse_w6_odds_marts_op` | `--w6-only` | HALT |
| 7 | `lakehouse_w7b_serving_op` | W7b export + `--w7b-only` | W7b mirror tier |
| 8 | `lakehouse_spine_odds_bridge_op` | `--w5-only --w5-group-a-only` + `--w6-odds-current` + refresh | W8a mirror tier |
| 9 | `lakehouse_w8a_feature_layer_op` | W8a export + `--w8a-only` + refresh | W8a mirror tier |
| 10 | `lakehouse_w8b_aggregator_op` | `--w5b-only` + W8b export + `--w8b-only` + refresh | W8b mirror tier |
| 11 | `lakehouse_w11_nightly_op` | the 5 gated W11/E11.22 nightly tiers | ALERT-continue |
| — | `lakehouse_delta_maintenance_op` | `delta_maintenance.py` (off critical path) | WARN |

Every gated-off stage logs a WARNING (loud skip — ALERT contract), and every stage keeps
its own generous wall cap so a stalled httpfs read fails inside its own wave.

### 1b. Delta-on-path, migration set = the W1 pitch-mart family (7 tables)

`mart_pitch_characteristics, mart_pitch_play_event, mart_pitch_game_context,
mart_pitch_fielding, mart_pitch_hitter_profile, mart_pitch_pitcher_profile,
mart_pitch_hit_characteristics` — the highest-volume tables in the daily rebuild, pure
row-local pitch-level projections (zero window functions, verified 2026-07-10), no
request-time reader outside the shared read helpers, no export-mirror writing their keys
(INC-31 writer-uniqueness audit §5).

- **Layout:** `s3://baseball-betting-ml-artifacts/baseball/lakehouse_delta/<table>/`
  (own prefix — NEVER inside `lakehouse/<table>/`, where the ext-table `**/*.parquet`
  glob would double-count the Delta part-files).
- **Write path:** delta-rs (`deltalake==1.6.1`, pinned; DuckDB's delta extension is
  READ-only), via `scripts/utils/delta_lake.py` — instance-role-safe `storage_options()`
  (the AKID landmine cure, behaviorally tested), `partition_by=["game_year"]`,
  `schema_mode="merge"` (additive INC-19 cure).
- **Daily incremental = O(current season):** a partition-pinned replaceWhere
  (`game_year = <LA-year>`) rebuilt from the season-filtered mart SQL — chosen over
  row-level MERGE because the pitch marts have no single-column PK and a deterministic
  partition swap is idempotent with zero PK assumptions. An **empty season slice SKIPs**
  (an empty replaceWhere would delete the partition). Full history is the **explicit
  opt-in** `--w1-only --delta-full` (per-season loop, memory-bounded to one season).
- **Read path:** every choke point routes Delta-backed tables through
  `delta_scan(...)` under cutover — `scripts/utils/lakehouse_read.py` (serving/predict),
  `betting_ml/utils/lakehouse_monitor.py` (sensors), and the three view-registration
  helpers inside `run_w1_lakehouse.py` (W2/W3/W4/W8 precursor views). The registry
  (`betting_ml/utils/delta_lakehouse.py`, pure stdlib) is the single source of truth;
  a guard test enforces `DELTA_W1_TABLES == MART_MODELS` exactly.
- **Rollout flag:** `LAKEHOUSE_DELTA_W1 = off | mirror | cutover` (default **off** — the
  merge is a no-op; a typo'd value raises loudly). `mirror` = parquet stays authoritative
  + Delta written for parity; `cutover` = Delta is the DuckDB-reader source of truth
  **plus the ⭐ SF-COMPAT SEASON MIRROR** (next bullet).
- **⭐ SF-compat season mirror (cutover):** real SF stragglers still read
  `baseball_data.betting.mart_pitch_play_event` as **raw SQL on a Snowflake connection**
  (the INC-27 class — found by the mandatory grep): `update_player_posteriors.py` (a
  DAILY op, no `--s3` branch), `ingest_player_profiles.py`, and the eb_priors/matchup
  offline scripts (`compute_bullpen_posteriors/v3`, `fit_bullpen_priors`,
  `build_matchup_training_data`, `train_matchup_v1`, `cluster_stability_analysis`).
  Freezing the legacy parquet would have silently staled them all. So under cutover the
  daily build ALSO writes `lakehouse/<table>/season_YYYY/data.parquet` — historical
  seasons back-filled once (self-healing on the first cutover run), only the **current**
  season rewritten daily, from the SAME arrow slice as the Delta write (cannot diverge) —
  and the legacy single `data.parquet` is deleted (both layouts under the ext glob at
  once would double-count: the glob-dup landmine; deletion failure raises). The ext
  tables keep their REQUIRED daily refresh and stay fully fresh, so every SF straggler
  keeps working unchanged. This is the W6 `_history`/`_current` pattern generalized
  per-season. The dir is `season_YYYY` (no `=`) so DuckDB hive-partition inference never
  fabricates a phantom column. The stragglers repoint (and the SF objects drop) in
  **phase 1.5** — §6 step 6.
- **Maintenance:** daily `delta_maintenance.py` (compact + vacuum clamped ≥168h — below
  that time-travel is physically destroyed; guarded by test).
- **Parity:** `scripts/parity_check_delta_w1.py` (per-season counts/games/key-hash both
  stores). Parity is necessary-NOT-sufficient: the cutover gate also requires the real
  consumer reads on the box (§6 step 4).

### 1c. Polars

`polars==1.42.1` pinned into the box image alongside delta-rs. Phase 1 deliberately does
NOT rewrite hot paths in Polars — the spike showed DuckDB `delta_scan` reads at parity
with `read_parquet`, so there is no read-latency deficit to fix; Polars adoption starts
where it pays (phase-2 heavy aggregations), always keeping the **Polars→pandas boundary
at `model.predict()`** (spike §5 — `X = feat_pl.to_pandas()` then
`X[model.feature_names_in_]`; the pickled sklearn contract is pandas-only).

---

## 2. Incident classes structurally retired (for the migrated tables)

| Class | Old defense | Delta defense |
|---|---|---|
| INC-19 additive type/schema drift | TYPE-PIN blocks + contract guard + operator DROP+rebuild | `schema_mode="merge"`: an additive column is a metadata commit, no rewrite. (A genuine stored-type FLIP is still a deliberate migration — the spike is explicit; don't oversell.) |
| INC-20 unbounded retention/OOM | hand-rolled retention per writer | `optimize.compact()` + `vacuum(≥168h)` in the daily maintenance op |
| Binary-ts misread / silent partial writes | ISO-VARCHAR stringify + parity | ACID commits (no torn multi-file states) + **no SF read of Delta at all** (gotcha #5 resolution). The VARCHAR-ts wrap is KEPT on the Delta write so consumer-visible types are identical in both modes; dropping it is phase-2 cleanup once zero SF readers is verified. |
| INC-31 two-writers-one-key clobber | grep discipline + guard tests | Structurally impossible on Delta: one table = one `_delta_log`, ACID single-writer commits; a stray parquet writer cannot silently replace table contents. (The SF-compat season mirror is written by the SAME build from the SAME arrow slice — one writer, one source.) |

## 3. What phase 1 does NOT claim

- **W2/W3 are still full rebuilds.** They are windowed/cumulative aggregates — a safe
  incremental conversion needs a per-model lookback audit (phase 2). The per-op timings
  from the decomposition are exactly the data that phase needs.
- **The measured numbers (AC B/C) come from the box**, not this doc — §6 produces them.
- **AC-C (the W1-family SF-credit drop) lands in phase 1.5, not phase 1.** The SF
  ext-table surface must stay alive (and refreshed, off the compat mirror) until the
  raw-SQL stragglers listed in §1b are repointed to the lakehouse — only then can the
  SF objects drop and the credit reduction be measured. Phase 1's measured number is
  AC-B (runtime).
- **`stg_ref_players` name-join staleness:** under cutover, a late player-name correction
  reaches only the current-season partition daily; historical partitions pick it up on
  the next `--delta-full`. Run the backfill monthly or after any ref_players backfill.

## 4. SF-credit measurement plan (AC C)

The migrated tables' Snowflake surface = the 7 `lakehouse_ext.mart_pitch_*` ext tables +
their `betting.mart_pitch_*` views + the daily `ALTER EXTERNAL TABLE … REFRESH` calls.
Post-cutover these are dropped (§6 step 6) → zero warehouse spin for this family.

BEFORE (run now, and again 7 days post-cutover; Snowflake MCP):
```sql
select date_trunc('day', start_time) d,
       count(*) q,
       sum(total_elapsed_time)/1000 sec,
       sum(credits_used_cloud_services) cs_credits
from snowflake.account_usage.query_history
where start_time >= dateadd('day', -7, current_timestamp)
  and (query_text ilike '%lakehouse_ext.mart_pitch%'
       or query_text ilike '%betting.mart_pitch%')
group by 1 order by 1;
```
Plus the whole-account daily anchor (the $55/day number) from
`snowflake.account_usage.warehouse_metering_history` grouped by day, so the delta is
attributable. Residual spend after phase 1 = Cortex + the not-yet-migrated families —
name the next-biggest ext-table read families from `query_history` in the AFTER report
to seed phase 2's migration order.

## 5. INC-31 systemic audit result (DO #6)

- **Writer-uniqueness:** no export mirror writes any `lakehouse/mart_pitch_*` key —
  `run_w1_lakehouse.py` is the sole writer pre-cutover, delta-rs sole writer post. ✅
- **🩹 Fixed a live latent clobber:** `export_w8b_precursors_to_s3.py` still
  `SELECT *`-mirrored (UPPERCASE) `stg_actionnetwork_public_betting` onto the key the
  W11d native build (lowercase, gated ON on the box) owns — the exact INC-31 pattern,
  masked only by the daily ordering (mirror at stage 8, native rebuild at stage 11).
  RETIRED from the mirror dict (requires `W11D_PUBLIC_BETTING_NIGHTLY=1` live, else the
  key freezes — verify at deploy).
- **Known benign duplicate:** `team_elo_history` is mirrored by BOTH
  `export_features_to_s3.py` and `export_w8a_precursors_to_s3.py` — same SF source, same
  method, same case → identical content, no clobber risk. Consolidate in phase 2.
- **Cadence:** the Delta W1 tables are daily-written/daily-read; no intraday consumer
  reads them (the intraday paths touch W3pre/W6/W7b/W8b only). ✅

## 6. ⏭️ Box run-order (the RUNTIME GATE — produces the AC B/C numbers)

Conventions: **BOX shell** = `aws ssm start-session --target i-07594af1679f81c38` (repo at
`~/app`); the code-location container reads its env from
`~/app/services/dagster/aws/.env` (`env_file`), so persistent flags are set THERE + a
`docker compose up -d` to recreate. **Deploy note:** steps 1+ need the rebuilt image
(`deltalake==1.6.1`/`polars==1.42.1`/duckdb `delta` extension baked) — the baked-image
drift landmine applies until `up -d --build` runs.

**Step 0 — BEFORE baseline (LAPTOP, do FIRST, pre-deploy).**
(a) In Dagit (https://the-box-caddy-host/ or `ssh -L 3000:localhost:3000` tunnel), open the
latest green `daily_ingestion_job` run and record: the `run_w1_lakehouse_op` duration + the
total job duration. (b) Snowflake MCP — run BOTH queries and save the outputs:
```sql
-- (i) W1-family SF surface (the reads/refreshes the cutover deletes)
select date_trunc('day', start_time) d, count(*) q,
       sum(total_elapsed_time)/1000 sec, sum(credits_used_cloud_services) cs_credits
from snowflake.account_usage.query_history
where start_time >= dateadd('day', -7, current_timestamp)
  and (query_text ilike '%lakehouse_ext.mart_pitch%' or query_text ilike '%betting.mart_pitch%')
group by 1 order by 1;
-- (ii) whole-account daily anchor (the $55/day number)
select date_trunc('day', start_time) d, warehouse_name, sum(credits_used) credits
from snowflake.account_usage.warehouse_metering_history
where start_time >= dateadd('day', -7, current_timestamp)
group by 1, 2 order by 1, 2;
```

**Step 1 — deploy the decomposition, Delta still OFF (BOX).** After the PR merges to main:
```bash
aws ssm start-session --target i-07594af1679f81c38          # LAPTOP → BOX shell
cd ~/app/services/dagster/aws && ./deploy.sh                 # BOX (>1 min: git pull + up -d --build; single-owner crontab per INC-30)
grep -E "W11D_PUBLIC_BETTING_NIGHTLY|W7B_LAKEHOUSE_S3" .env  # BOX: W11D_PUBLIC_BETTING_NIGHTLY=1 REQUIRED (the retired w8b public-betting mirror's precondition)
```
Leave `LAKEHOUSE_DELTA_W1` unset. Let ONE scheduled daily cycle run green → in Dagit,
record every `lakehouse_*_op` duration (the per-wave BEFORE row of the AC-B table).

**Step 2 — mirror mode + the one-time Delta backfill (BOX; backfill ≈ a full W1 rebuild, >1 min).**
```bash
echo 'LAKEHOUSE_DELTA_W1=mirror' >> ~/app/services/dagster/aws/.env
cd ~/app/services/dagster/aws && docker compose up -d        # recreate so dagster-codeloc picks up the flag
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 -e LAKEHOUSE_DELTA_W1=mirror \
  dagster-codeloc python -u scripts/run_w1_lakehouse.py --w1-only --delta-full
```

**Step 3 — parity (BOX), then 2–3 mirror daily cycles.**
```bash
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 \
  dagster-codeloc python -u scripts/parity_check_delta_w1.py
```
Must print `Delta W1 parity PASSED`. Re-run after each mirror daily cycle (the daily now
writes the current-season partition each morning).

**Step 4 — consumer runtime gate (BOX; per-row reads through the REAL consumers — parity
is necessary-NOT-sufficient).** All three must succeed:
```bash
# (a) W2 reading W1 via delta_scan (dry-run: counts only, no S3 write)
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 -e LAKEHOUSE_DELTA_W1=cutover \
  dagster-codeloc python -u scripts/run_w1_lakehouse.py --w2-only --dry-run
# (b) the serving writer end-to-end on --s3 (the daily already runs --s3; this exercises
#     the delta_scan branch in lakehouse_read under cutover)  (>1 min)
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 -e LAKEHOUSE_DELTA_W1=cutover \
  dagster-codeloc python -u scripts/write_serving_store.py --s3
# (c) maintenance (compact+vacuum) runs clean on the backfilled tables
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 -e LAKEHOUSE_DELTA_W1=mirror \
  dagster-codeloc python -u scripts/delta_maintenance.py
```

**Step 5 — flip cutover (BOX) → the AC-B AFTER numbers.**
```bash
sed -i 's/^LAKEHOUSE_DELTA_W1=.*/LAKEHOUSE_DELTA_W1=cutover/' ~/app/services/dagster/aws/.env
cd ~/app/services/dagster/aws && docker compose up -d
# One-time compat migration (>1 min — builds every historical season's SF-compat
# season_YYYY/data.parquet, then DELETES the legacy data.parquet; self-healing, so the
# next daily would also do it — running it manually keeps the first daily cycle fast
# and lets you verify the layout swap immediately):
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 -e LAKEHOUSE_DELTA_W1=cutover \
  dagster-codeloc python -u scripts/run_w1_lakehouse.py --w1-only
# Verify the layout swap (exactly one season_* file per season, NO data.parquet at root):
aws s3 ls s3://baseball-betting-ml-artifacts/baseball/lakehouse/mart_pitch_play_event/ --recursive | head -20
# Refresh the ext tables onto the new layout NOW (don't wait for the daily):
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  dagster-codeloc python -u scripts/refresh_w1_external_tables.py
```
Next daily cycle: `lakehouse_w1_pitch_marts_op` drops from full-history rebuild to
O(current-season) — Delta partition swap + the current-season compat file only. Record
every `lakehouse_*_op` duration + the total job duration → the AC-B BEFORE→AFTER table.
`predict_today_morning` + `check_served_prediction_integrity_op` green = the serving
gate; also spot-check one SF straggler read is fresh (LAPTOP, Snowflake MCP):
`select max(game_date) from baseball_data.betting.mart_pitch_play_event;` → today-ish.
**Rollback from cutover:** re-materialize the legacy layout first, then flip the flag —
```bash
docker compose -f ~/app/services/dagster/aws/docker-compose.yml exec -T \
  -e AWS_DEFAULT_REGION=us-east-2 -e LAKEHOUSE_DELTA_W1=off \
  dagster-codeloc python -u scripts/run_w1_lakehouse.py --w1-only        # rewrites data.parquet (>1 min)
for t in mart_pitch_characteristics mart_pitch_play_event mart_pitch_game_context \
         mart_pitch_fielding mart_pitch_hitter_profile mart_pitch_pitcher_profile \
         mart_pitch_hit_characteristics; do                               # remove season files (glob-dup!)
  aws s3 rm --recursive "s3://baseball-betting-ml-artifacts/baseball/lakehouse/$t/" \
    --exclude "*" --include "season_*/data.parquet"
done
sed -i 's/^LAKEHOUSE_DELTA_W1=.*/LAKEHOUSE_DELTA_W1=off/' ~/app/services/dagster/aws/.env
cd ~/app/services/dagster/aws && docker compose up -d
```
(from mirror, rollback is just the `sed` + `up -d` — data.parquet never left.)

**Step 6 — PHASE 1.5: straggler repoint + SF decommission of the W1 family → the AC-C numbers.**
⚠️ **ORDER MATTERS twice over:** (1) the raw-SQL SF stragglers (§1b list) must be
REPOINTED to the lakehouse before anything drops — they are why the compat mirror
exists; (2) the daily `dbt_daily_build` rebuilds the SF `mart_pitch_*` views every run,
so dropping their ext tables before retiring those dbt models would fail the HALT-tier
dbt run. The sequence is:
(a0) **Straggler repoint (a follow-up story/PR):** route `update_player_posteriors.py`'s
PA-substrate read through the W7a dual-connection pattern its sibling
`update_matchup_cell_posteriors.py --s3` already uses; repoint `ingest_player_profiles.py`
+ the eb_priors offline scripts via `scripts/utils/lakehouse_read` (delta-aware). Gate:
one green daily cycle with `W7A`-style flags on + the INC-27 grep returning zero
`betting.mart_pitch_` raw-SQL hits outside DDL/parity tooling.
(a) **Zero-reader verification (LAPTOP, Snowflake MCP):**
```sql
select query_start_time, user_name, direct_objects_accessed
from snowflake.account_usage.access_history,
     lateral flatten(input => direct_objects_accessed) o
where query_start_time >= dateadd('day', -7, current_timestamp)
  and o.value:objectName::string ilike '%mart_pitch%'
order by query_start_time desc limit 50;
```
Expect ONLY the dbt view re-creates + the (now-skipped) REFRESH calls — no real readers.
(b) **Follow-up code change (a small PR — the 7 SF-side dbt models must retire BEFORE the
objects drop):** delete `dbt/models/mart/mart_pitch_*.sql` (all 7) + their schema.yml
entries, or flip each to `enabled=false`; `dbtf compile` green; merge + `./deploy.sh`.
(c) **DROP the SF objects (LAPTOP, Snowflake MCP; DDL — the MCP role can't run
`ALTER EXTERNAL TABLE`, but DROP goes through the normal role; if blocked, run via
`data_loader.get_snowflake_connection()` inline on the box):**
```sql
drop view if exists baseball_data.betting.mart_pitch_characteristics;
drop view if exists baseball_data.betting.mart_pitch_play_event;
drop view if exists baseball_data.betting.mart_pitch_game_context;
drop view if exists baseball_data.betting.mart_pitch_fielding;
drop view if exists baseball_data.betting.mart_pitch_hitter_profile;
drop view if exists baseball_data.betting.mart_pitch_pitcher_profile;
drop view if exists baseball_data.betting.mart_pitch_hit_characteristics;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_characteristics;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_play_event;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_game_context;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_fielding;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_hitter_profile;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_pitcher_profile;
drop external table if exists baseball_data.lakehouse_ext.mart_pitch_hit_characteristics;
```
(INC-27 discipline: `grep -rIn "betting\.mart_pitch_\|lakehouse_ext\.mart_pitch_"` the
whole repo first and require ZERO hits outside DDL/parity tooling — as of 2026-07-10 the
grep DOES find the §1b straggler list, which is exactly why (a0) precedes this step. The
same phase-1.5 PR must also remove `W1_TABLES` from the default REQUIRED refresh set in
`scripts/refresh_w1_external_tables.py` — refreshing a dropped ext table would HALT —
and update `betting_ml/tests/test_delta_lakehouse_guard.py::`
`test_refresh_script_keeps_w1_required_for_the_compat_mirror`, which pins the
phase-1 state.)
(d) **Delete the frozen legacy parquet (BOX or LAPTOP with AWS creds):**
```bash
for t in mart_pitch_characteristics mart_pitch_play_event mart_pitch_game_context \
         mart_pitch_fielding mart_pitch_hitter_profile mart_pitch_pitcher_profile \
         mart_pitch_hit_characteristics; do
  aws s3 rm --recursive "s3://baseball-betting-ml-artifacts/baseball/lakehouse/$t/"
done
```
(e) **AFTER credit measurement (LAPTOP, 7 days later):** re-run BOTH Step-0 queries →
the AC-C BEFORE→AFTER table; the (i) query should be ~zero, and the residual (ii) spend
is attributable to Cortex + the not-yet-migrated families (name the next-biggest from
`query_history` to seed phase 2's migration order).

## 7. Multi-sport template note

The pattern to replicate ×3 in the fall: pure-stdlib registry (`delta_lakehouse.py`) +
delta-rs write helpers (`delta_lake.py`) + per-wave decomposed ops + three-state
per-family flag (off/mirror/cutover) + parity script + maintenance op + the §6 gate
sequence. Phase order per sport: pitch/play-level row-local marts first (partition
overwrite), windowed aggregates second (MERGE after a lookback audit), state tables last
(the stretch goal — Delta MERGE can hold Elo/posterior/SCD-2 state and retire the last
non-Cortex SF warehouse writes).
