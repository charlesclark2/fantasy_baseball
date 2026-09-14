# NCAAF-INC-0914 — evidence reads (phase 1: diagnose, no fix yet)

**Incident:** `sports_ncaaf_dbt_build_job` run `06d7352c-5744-4902-b42d-a0c8aa4a43ba` was
**forcibly marked as failed** by Dagster's run monitor. The alert carries no traceback.

**Status:** cause NOT yet named. This document is the evidence plan and the part of it that
could be answered without box access. Sections 1–3 are **measured**; section 4 is what the
operator must read; section 5 states the falsifiable predictions so the reads *decide* rather
than merely inform.

---

## 1. What the alert TEXT alone proves (Dagster source, version-dependent — see read D)

The string `"This job is being forcibly marked as failed. The computational resources created by
the run may not have been fully cleaned up."` is emitted by exactly one function,
`_force_mark_as_failed`, in `dagster/_daemon/monitoring/run_monitoring.py`, and in Dagster 1.13.5
that function has **exactly one caller**: the tail of `check_run_timeout`.

Three consequences, each a narrowing:

1. **The kill path is the `max_runtime` cap, not a worker-health check.** The run-worker-health
   branch of `monitor_started_run` emits a *different* message (`"Detected run worker status …"`)
   and `return`s before `check_run_timeout` is ever reached.

2. **`end_time − start_time` should be ≈ `max_runtime_seconds` = 14400 s (4 h).**
   `services/dagster/dagster.yaml` sets `run_monitoring.max_runtime_seconds: 14400`, and
   `sports_ncaaf_dbt_build_job` carries **no `dagster/max_runtime` run tag**, so it inherits the
   global value. This is the single most decisive number to read (read A).

3. **`terminate()` did NOT succeed.** `check_run_timeout` calls `report_run_failed(… "Exceeded
   maximum runtime of 14400 seconds.")` *only* when `run_launcher.terminate()` returns truthy;
   `_force_mark_as_failed` then finds the run already finished and emits **nothing**. Getting the
   forcible-failure text therefore means the cancel failed or raised.

   `DefaultRunLauncher.terminate` → gRPC `CancelExecution` on the code server, and that returns
   `success=True` **iff `run_id in self._executions`** — the codeloc gRPC server's *in-memory*
   registry of subprocesses it launched. ⇒ **at ~22:00 UTC the codeloc server had no in-memory
   record of this run.**

---

## 2. What that rules IN and OUT

### ⭐ 2a. This instance performs NO run-worker health check at all

`DefaultRunLauncher` does not override `supports_check_run_worker_health`, and the base
`RunLauncher` returns `False`. So on this box the run monitor **never** asks whether a run worker
is alive; the 4-hour cap is the only backstop.

⇒ **A dead run worker and a hung run worker are indistinguishable here, and both surface ~4 hours
late with a message that names no cause.** The alert's silence is a property of the instrument,
not of this incident — it will read identically for OOM, for a crash, and for a hang. (This is the
E11.30 "detected but nobody can tell what" class, at the run-monitor layer.)

### 2b. A subprocess OOM with codeloc surviving is *unlikely*, on mechanism

The codeloc gRPC server runs its own `_cleanup_thread` → `_check_for_orphaned_runs`, which, for
any run whose execution process is no longer alive, writes a crash-explanation engine event
(`"Run execution process for {run_id} …"` with the exit code) and calls `report_run_failed`
**within one cleanup tick**. So had the run *subprocess* been OOM-killed while codeloc itself kept
running, the run would have failed within minutes carrying an exit code — not sat for four hours.

⇒ Combined with §1.3, the surviving explanations all route through **"codeloc did not live
continuously, with this run in its `_executions`, from launch until 22:00."**

### 2c. The run cannot have reached 14400 s while its own Python was executing

`_run_sports_dbt` (`pipeline/jobs/sports_dbt_job.py:170`) passes `timeout=DBT_TIMEOUT_SECONDS`
(2400 s). The job has four such legs (staging → marts → leakage gates → tests) ⇒ **≤ 9600 s =
2.67 h < 4 h.**

I checked the one way that bound could be a lie and it is **not**: on POSIX, `subprocess.run`'s
timeout path calls `process.kill()` then `process.wait()` — *not* the unbounded `communicate()`
used on Windows — so a surviving grandchild holding the pipe cannot block the caller. (The
grandchild *leak* is still real — see follow-up F2 — but it does not wedge this op.)

⇒ **Whatever consumed those four hours was not this job's Python.**

---

## 3. Concurrency census for 2026-09-14 (measured, no box access needed)

2026-09-14 is a **Monday**. `sports_ncaaf_dbt_schedule` = `0 11 * 8-12,1 *` in
`America/Los_Angeles` = **18:00:00 UTC**; 18:00:00 + 14400 s = **22:00:00 UTC**. The alert landed
in the 22:00–22:45 UTC window. Arithmetic consistent — but see read A, which is what settles it.

### 3a. ⭐ Eleven box deploys today, six in the afternoon; every one recreated the run worker

From the GitHub Actions API for `orchestration_cd.yml` (`gh run list --workflow=orchestration_cd.yml`),
with the box-side `deploy.sh` output surfaced in each job log:

| CD run created (UTC) | PR | drain verdict logged on the box | `dagster-codeloc` |
|---|---|---|---|
| 16:56:53 | #1114 | `no in-flight runs — safe to recreate` | **Recreated** |
| 17:36:22 | #1115 | `no in-flight runs — safe to recreate` | **Recreated** |
| 17:53:34 | #1120 | `no in-flight runs — safe to recreate` | **Recreated** |
| **18:00:15** | **#1121** (merged 18:00:11) | **`[deploy 18:00:23] no in-flight runs — safe to recreate`** | **Recreated 18:00:23–18:00:53** |
| 22:32:07 | #1123 | `no in-flight runs — safe to recreate` | **Recreated** |
| 22:45:55 | #1125 | (in progress at time of writing) | — |

Earlier: 04:08, 04:19, 05:27, 05:56, 06:04.

The 18:00 deploy tore down and rebuilt `dagster-codeloc`, `dagster-daemon` and
`dagster-webserver` **starting 23 seconds after the NCAAF schedule's own cron minute**.

### 3b. ⭐ The drain that authorised that recreate is structurally blind to a run that is not yet STARTED

`services/dagster/aws/deploy.sh:167-175` probes:

```graphql
{ runsOrError(filter:{statuses:[STARTED]}, limit:1){ … } }
```

`statuses:[STARTED]` **only**. The instance uses `QueuedRunCoordinator`
(`services/dagster/dagster.yaml`), so every scheduled run passes **QUEUED → STARTING → STARTED**.
A run created by a cron tick seconds before a merge can therefore be *invisible* to the drain and
still be launched into — or torn down by — the recreate that the drain just authorised.

This is a **window**, not a proof that it fired here. Read A decides.

### 3c. Other Monday tenants (code-derived; presence to be confirmed by read B)

| Schedule | cron | UTC Monday |
|---|---|---|
| `sports_ncaaf_roll_forward_schedule` | `0 6 * 2-12,1 1` LA | 13:00 |
| `sports_nfl_roll_forward_schedule` | `15 6 * 3-12,1-2 1` LA | 13:15 |
| `sports_ncaaf_strength_refit_schedule` (P1.2W) | `30 7 * 8-12,1 1` LA | 14:30 — **also runs `_run_sports_dbt` against the same DuckDB** |
| **`sports_nfl_dbt_schedule`** | `0 11 * 9-12,1-2 *` LA | **18:00 — the same minute as NCAAF** |
| `sports_ncaaf_serving_write_schedule` | `20 * * 8-12,1 *` LA | hourly :20 |
| `sports_ncaaf_odds_live_schedule` | `0 * * 8-12,1 *` LA | hourly :00 |

Host crons active in 18:00–22:00 UTC (`services/dagster/aws/capture.crontab`): `odds-capture` and
`derivative-capture` (`*/30`), `weather-capture` (`0 * * * *`), live props (`0 13-23`),
k-projections (`:15`), batter-TB (`:20`), healthcheck (`*/5`). Box is **2 vCPU / 16 GB**
(`r6g.large`); `dagster-codeloc` has **no `mem_limit`**.

⚠️ `sports_ncaaf_dbt_schedule` and `sports_nfl_dbt_schedule` share the identical cron minute
**and the same DuckDB file** (`SPORTS_DUCKDB_PATH`; `profiles.yml` targets one path for both
sports, materialising into separate schemas). That is a latent collision independent of this
incident — DuckDB's write lock is exclusive — and it is recorded as follow-up F3 rather than
asserted as this cause, because a lock conflict fails *fast and loud with a traceback*, which is
not the symptom seen here.

---

## 4. Operator reads — paste-ready, in decision order

### READ A — the run record and its event log  ⭐ *this one read settles the most*
**WHERE: the EC2 BOX** (SSM in: `aws ssm start-session --target i-07594af1679f81c38`)

```bash
docker compose -f /home/ec2-user/app/services/dagster/aws/docker-compose.yml \
  exec -T dagster-codeloc python - <<'PY'
from dagster import DagsterInstance
import datetime as dt
RID = "06d7352c-5744-4902-b42d-a0c8aa4a43ba"
def u(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat() if ts else None
with DagsterInstance.get() as inst:
    rec = inst.get_run_record_by_id(RID)
    r = rec.dagster_run
    print("job        :", r.job_name)
    print("status     :", r.status)
    print("tags       :", dict(r.tags))
    print("start (UTC):", u(rec.start_time))
    print("end   (UTC):", u(rec.end_time))
    if rec.start_time and rec.end_time:
        print("wall_secs  :", round(rec.end_time - rec.start_time, 1))
    print("-" * 72)
    for e in inst.all_logs(RID):
        et = e.dagster_event.event_type_value if e.dagster_event else "-"
        msg = (e.user_message or "").replace("\n", " ")[:300]
        print(u(e.timestamp), "|", et, "|", e.step_key or "-", "|", msg)
PY
```

Runtime: seconds. Reads Dagster's **Postgres** event log, which survives every container
recreation (raw stdout does not — `LocalComputeLogManager` is on ephemeral disk).

### READ B — every Dagster run today, against the deploy windows
**WHERE: the EC2 BOX**

```bash
docker compose -f /home/ec2-user/app/services/dagster/aws/docker-compose.yml \
  exec -T dagster-codeloc python - <<'PY'
from dagster import DagsterInstance, RunsFilter
import datetime as dt
LO = dt.datetime(2026, 9, 14, 0, 0, tzinfo=dt.timezone.utc)
def f(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%H:%M:%S") if t else "--:--:--"
with DagsterInstance.get() as inst:
    recs = inst.get_run_records(filters=RunsFilter(created_after=LO), limit=300, ascending=True)
    print(f"{'start':>8} {'end':>9}  {'wall_s':>8}  {'status':<9} {'run':<9} job")
    for rec in recs:
        r = rec.dagster_run
        w = round(rec.end_time - rec.start_time, 1) if (rec.start_time and rec.end_time) else None
        print(f"{f(rec.start_time):>8} {f(rec.end_time):>9}  {str(w):>8}  {r.status.value:<9} "
              f"{r.run_id[:8]:<9} {r.job_name}")
PY
```

Runtime: seconds. Answers three things at once: whether `sports_nfl_dbt_build_job` also fired at
18:00; whether **any other** run was orphaned by the same deploys (any `wall_s ≈ 14400`, or a run
still STARTED); and whether the P1.2W refit ran at 14:30.

### READ C — the OOM branch, closed or opened
**WHERE: the EC2 BOX**

```bash
sudo dmesg -T | grep -iE 'out of memory|killed process|oom-kill' | tail -40
sudo journalctl --since '2026-09-14 17:30' --until '2026-09-14 22:30' --no-pager | grep -iE 'oom|killed process|docker' | tail -60
```

### READ D — the Dagster version actually on the box (§1 is version-dependent)
**WHERE: the EC2 BOX**

```bash
docker compose -f /home/ec2-user/app/services/dagster/aws/docker-compose.yml \
  exec -T dagster-codeloc python -c "import dagster; print('dagster', dagster.__version__)"
```

Why it matters: the image installs `dagster>=1.11.5` **unpinned** (`Dockerfile:43`), so the running
version is whatever was latest at the last `--build`. My §1 reading is from 1.13.5 source. If the
box reports something materially different, re-check `run_monitoring.py` for that tag.

### READ E — impact: how stale are the NCAAF marts right now
**WHERE: the EC2 BOX**

```bash
docker compose -f /home/ec2-user/app/services/dagster/aws/docker-compose.yml \
  exec -T dagster-codeloc python - <<'PY'
import duckdb, os
p = os.environ["SPORTS_DUCKDB_PATH"]
con = duckdb.connect(p, read_only=True)
print(con.execute("""
  select season,
         max(game_date) filter (where is_completed)      as last_completed_game,
         count(*) filter (where is_completed)            as completed_games,
         max(season_order_week) filter (where is_completed) as last_completed_week
  from main_ncaaf_marts.dim_ncaaf_game
  where season = 2026 group by season
""").fetchall())
PY
```

This is a **content** read (INC-41: never an mtime, never `aws s3 ls`). If the 2026-09-12 Saturday
slate is absent from `last_completed_game`, the marts have not absorbed it — and
`sports_ncaaf_serving_write_schedule` has been publishing that state hourly at :20.

⚠️ **`docker inspect dagster-codeloc` is no longer usable as evidence here.** The 22:32 and 22:45
deploys recreated the container again, so `.State.StartedAt` now reports the *latest* deploy and
can no longer distinguish an 18:00 restart from a 22:45 one. (`.RestartCount` never could — it does
not increment on API/compose restarts; FU-1.) The durable record is the Postgres event log, i.e.
reads A and B.

---

## 5. Falsifiable predictions — what each outcome of READ A means

| Read A shows | Reading |
|---|---|
| `wall_secs ≈ 14400` (±one monitoring tick) | §1 confirmed: killed by the 4 h cap, not by a dbt error. |
| `wall_secs` materially ≠ 14400 | §1 is **wrong** for this box — a `dagster/max_runtime` tag or a different Dagster version is in play. Stop and re-derive from READ D. |
| `start ≈ 18:00:1x–18:01` **and** last step log stops at/near that minute | The run was launched into the 18:00:23–18:00:53 recreate window. Cause: **deploy-during-run orphaning**, drain blind to QUEUED/STARTING (§3b). |
| `tags` contain `sport=ncaaf, gate=game_day` | Launched by `sports_ncaaf_dbt_schedule` (those tags are set only there). Absent ⇒ a manual/ad-hoc launch, and the 18:00 arithmetic does not apply — re-derive the window from the actual `start`. |
| An engine event `"Exception while attempting to terminate run…"` | codeloc was **unreachable** at 22:00, not merely forgetful. A different sub-cause (container down/saturated at that moment) — note both later deploys were *after* 22:00. |
| An engine event `"Run execution process for … "` with an exit code | The subprocess died and codeloc *did* notice — which contradicts §2b's 4-hour silence and would be an anomaly worth its own line. |
| Step logs showing dbt output progressing well past 18:01 | The worker was alive and working; §2c says it still could not reach 4 h, so re-open with the last logged timestamp as the new anchor. |
| READ B shows other runs with `wall_s ≈ 14400` or stuck STARTED | The cause is **systemic to deploys**, not specific to NCAAF — which changes the fix from a job tag to the drain/serialisation boundary. |

**If READ A shows a `start` that does not sit inside any deploy window and no terminate-exception
event, then the evidence does not distinguish "worker died silently" from "worker hung outside its
own bounded legs", and the honest verdict is that it cannot.** The instrumentation that *would*
distinguish them is named in follow-up F1: a run-worker liveness check (or an equivalent
heartbeat), which this instance does not have at all today (§2a).

---

## 6. What is NOT established

- **The cause.** Nothing above names one. §3a is a measured coincidence of timing plus a measured
  structural window (§3b); it is a hypothesis with a decisive test, not a verdict.
- Whether the run was QUEUED, STARTING or STARTED at 18:00:23.
- Whether `sports_nfl_dbt_build_job` also fired at 18:00 and what it did to the shared DuckDB.
- Whether OOM played any part (READ C), though §2b makes a subprocess-OOM an awkward fit.
- The Dagster version on the box (READ D).
