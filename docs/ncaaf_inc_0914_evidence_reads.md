# NCAAF-INC-0914 — the sports NCAAF dbt build was killed by a deploy, and took 4 hours to say so

**Incident:** `sports_ncaaf_dbt_build_job` run `06d7352c-5744-4902-b42d-a0c8aa4a43ba`, forcibly
marked failed by Dagster's run monitor with no traceback.
**Status: CAUSE MEASURED.** Phase 1 (diagnose) is closed; §7 is the fix, §8 the restore/verify.

---

## 0. Verdict

**The 2026-09-14 18:00:15Z Orchestration-CD deploy (PR #1121, merged 18:00:11Z) recreated the
`dagster-codeloc` container — which is both the code server and the run worker — while this run's
execution subprocess was one second into its first dbt command. The drain that authorised the
recreate had probed 25 seconds earlier, while the run was in `STARTING`, and its GraphQL filter
lists `STARTED` only.**

### 0a. Timeline (UTC, every line measured)

| Time | What | Source |
|---|---|---|
| 18:00:00.70 | run created; `PIPELINE_ENQUEUED` 18:00:00.77 | R1 |
| 18:00:09.44 | `PIPELINE_STARTING` | R1 |
| 18:00:11 | PR #1121 merged to `main` | GitHub API |
| 18:00:16.06 | launch `ENGINE_EVENT` | R1 |
| **18:00:23** | **`deploy.sh`: "no in-flight runs — safe to recreate"** — the run is in `STARTING`, which the probe cannot see | CD job log |
| 18:00:23–18:00:53 | `dagster-codeloc` / `-daemon` / `-webserver` **Recreated** | CD job log |
| 18:00:47.67 | `PIPELINE_START` — "Executing steps in process (pid: 693)" | R1 |
| 18:00:48.10 | `STEP_START sports_ncaaf_dbt_run_op` | R1 |
| **18:00:48.12** | the dbt staging command is logged — **and the run never speaks again** | R1 |
| 22:01:20.14 | `PIPELINE_CANCELING` — the 4 h `max_runtime` cap | R1 |
| 22:01:20.46 | `PIPELINE_FAILURE` — *"forcibly marked as failed"* | R1 |

`start + 14400 s = 22:00:47.67`; killed at 22:01:20.14 (**wall 14432.8 s**) — the +32 s is the
monitoring daemon's tick. The predicted value and the observed value agree.

The teardown instant is not itself timestamped (docker-compose output carries no clock), so it is
bracketed: **[18:00:23, 18:00:53]**, with the run's last breath at 18:00:48.12 and the deploy's
next timestamped line at 18:00:53.

### 0b. ⭐ Five runs died in that one event, at three different detection latencies

| Run | Job | State when killed | Detected by | Latency |
|---|---|---|---|---|
| `06d7352c` | **sports_ncaaf_dbt_build_job** | STARTED | instance-wide 14400 s cap | **4 h** |
| `2e8e1232` | intraday_schedule_job | STARTED | its own `dagster/max_runtime` 1500 s (E11.26) | **26 min** |
| `945d7932` | **sports_nfl_dbt_build_job** | never started | Dagster's 180 s start-timeout | **~3 min** |
| `e010208c` | artifact_freshness_job | never started | 180 s start-timeout | ~3 min |
| `2027d275` | intraday_public_betting_job | never started | 180 s start-timeout | ~3 min |

**The difference was entirely whether the job carried a ceiling of its own.** `DefaultRunLauncher`
does not implement `supports_check_run_worker_health`, so once a run reaches STARTED this instance
never checks whether its worker is alive. The NCAAF run crossed into STARTED ~1 second before the
teardown — the one second that cost it 4 hours instead of 3 minutes.

`intraday_schedule_job` failing at 1581.9 s against its 1500 s tag is the **measured proof that the
E11.26 ceiling works**, from the same event, on the same box, in the same minute.

### 0c. OOM is ruled out, not assumed

R4 returned **nothing** from `dmesg` and nothing from the journal across 17:30–22:30;
`OOMKilled=false`; memory now 3.1 / 15.7 GB. Independently, §2b's mechanism argument holds: the
code server's own `_check_for_orphaned_runs` fails any run whose process died, within one cleanup
tick, **with an exit code** — a subprocess OOM could not have produced four hours of silence.

### 0d. Serving impact: none measurable — but that is a property of Monday, not a safety margin

Two earlier jobs ran the **identical** `ncaaf.staging` + `ncaaf.marts` selectors through the same
`_run_sports_dbt` helper, both after the 09-13 game day and both SUCCESS: `sports_ncaaf_roll_forward_job`
(13:00:45, 301.7 s) and `sports_ncaaf_strength_refit_job` (14:30:27, 587.5 s). R5 confirms
`dim_ncaaf_game` holds completed games through **2026-09-13**, the most recent CFB game day, and
`sports_ncaaf_serving_write_job` has run SUCCESS hourly at `:20` throughout. The 18:00 build was
the day's **third** full NCAAF rebuild.

⚠️ Both of those jobs are **Monday-only**. On any other gate-open day the 18:00 build is the only
NCAAF mart rebuild, and losing it would have aged every NCAAF surface.

**Self-heal: confirmed, no manual re-run needed.** The 09-15 18:00 tick fired and the game-day gate
correctly skipped (no CFB games Sun–Tue); `sports_nfl_dbt_build_job` ran green in the same minute
(192.6 s). The next gate-open day rebuilds.

---

## 1. What the alert TEXT alone proves (Dagster source, version-dependent — see R0)

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
   global value. This is the single most decisive number to read (R1).

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
in the 22:00–22:45 UTC window. Arithmetic consistent — but R1 is what settles it.

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

This is a **window**, not a proof that it fired here. R1 decides.

### 3c. Other Monday tenants (code-derived; presence to be confirmed by R2)

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

## 4. Operator reads — ONE paste, ON THE BOX, ~1 minute total

SSM in first:

```bash
aws ssm start-session --target i-07594af1679f81c38
```

If any `docker` command below says *permission denied*, become the box's owner first and re-paste:
`sudo -u ec2-user -H bash -l`

Everything below appends to **`/tmp/ncaaf-inc-0914-evidence.txt`**. Paste the blocks in order,
then send that one file back.

---

### R0 — preamble + box context

```bash
set -u
DC="docker compose -f /home/ec2-user/app/services/dagster/aws/docker-compose.yml"
RID=06d7352c-5744-4902-b42d-a0c8aa4a43ba
OUT=/tmp/ncaaf-inc-0914-evidence.txt
: > "$OUT"
{
  echo "### captured $(date -u '+%Y-%m-%dT%H:%M:%SZ') UTC on $(hostname)"
  echo "### box uptime / load / memory"
  uptime
  free -m
  echo "### containers"
  $DC ps
  echo "### dagster version actually running (the image pins dagster>=1.11.5 UNPINNED)"
  $DC exec -T dagster-codeloc python -c "import dagster,sys; print('dagster', dagster.__version__, '| python', sys.version.split()[0])"
} 2>&1 | tee -a "$OUT"
```

**Why:** the §1–§2 inferences are read from Dagster **1.13.5** source. If the box reports a
materially different version, re-check `_daemon/monitoring/run_monitoring.py` at that tag before
trusting any of it (finding F6).

---

### R1 — ⭐ THE RUN: record + full Postgres event log  *(the single most decisive read)*

```bash
$DC exec -T dagster-codeloc python - <<'PY' 2>&1 | tee -a "$OUT"
from dagster import DagsterInstance
import datetime as dt
RID = "06d7352c-5744-4902-b42d-a0c8aa4a43ba"
def u(ts):
    if not ts:
        return None
    if isinstance(ts, dt.datetime):
        return ts.astimezone(dt.timezone.utc).isoformat()
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()
print("### R1 — run record + event log")
with DagsterInstance.get() as inst:
    rec = inst.get_run_record_by_id(RID)
    if rec is None:
        print("!! NO RUN RECORD FOR", RID, "— check the run id")
        raise SystemExit(0)
    r = rec.dagster_run
    print("job           :", r.job_name)
    print("status        :", r.status)
    print("tags          :", dict(r.tags))
    print("created (UTC) :", u(rec.create_timestamp))
    print("start   (UTC) :", u(rec.start_time))
    print("end     (UTC) :", u(rec.end_time))
    if rec.start_time and rec.end_time:
        print("wall_secs     :", round(rec.end_time - rec.start_time, 1),
              " (14400 == the run-monitor max_runtime cap)")
    print("-" * 78)
    n = 0
    for e in inst.all_logs(RID):
        n += 1
        et = e.dagster_event.event_type_value if e.dagster_event else "LOG"
        raw = (e.user_message or "").replace("\n", " \\n ")
        msg = raw[:400] + (f"   [...{len(raw)} chars total]" if len(raw) > 400 else "")
        print(u(e.timestamp), "|", et, "|", e.step_key or "-", "|", msg)
    print("-" * 78)
    print("total events  :", n)
PY
```

**Why:** the Postgres event log is the **only** durable record — raw stdout goes to
`LocalComputeLogManager` on ephemeral disk, and the container that held it was destroyed at
22:32. This prints four things that between them decide the incident:

- `wall_secs` — is it ≈ **14400**? (confirms/refutes the whole §1 reading)
- `created` vs `start` — was the run already launched, or still **QUEUED**, at **18:00:23** when
  the deploy's drain probe declared "no in-flight runs"? (the F4 blind spot)
- the **status-transition events** (`RUN_ENQUEUED` → `RUN_STARTING` → `RUN_START` → `STEP_START`…)
  and **where the log goes silent**
- whether `"Exception while attempting to terminate run…"` or a
  `"Run execution process for … "` crash-explanation event is present (§5 decides on these)

---

### R2 — ⭐ every Dagster run since 2026-09-14, against the deploy windows

```bash
$DC exec -T dagster-codeloc python - <<'PY' 2>&1 | tee -a "$OUT"
from dagster import DagsterInstance, RunsFilter
import datetime as dt
LO = dt.datetime(2026, 9, 14, 0, 0, tzinfo=dt.timezone.utc)
def f(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%m-%d %H:%M:%S") if t else "     --     "
print("### R2 — all runs since 2026-09-14 00:00 UTC")
with DagsterInstance.get() as inst:
    recs = inst.get_run_records(filters=RunsFilter(created_after=LO), limit=500, ascending=True)
    print(f"{'start(UTC)':>14} {'end(UTC)':>14} {'wall_s':>9}  {'status':<10} {'run':<9} job")
    for rec in recs:
        r = rec.dagster_run
        w = round(rec.end_time - rec.start_time, 1) if (rec.start_time and rec.end_time) else None
        flag = "  <== ~14400s CAP" if (w and 14200 <= w <= 14600) else ""
        print(f"{f(rec.start_time):>14} {f(rec.end_time):>14} {str(w):>9}  "
              f"{r.status.value:<10} {r.run_id[:8]:<9} {r.job_name}{flag}")
    print("-" * 78)
    print("total runs:", len(recs))
PY
```

**Why:** answers four questions at once — did `sports_nfl_dbt_build_job` also fire at 18:00 (same
cron minute, same DuckDB file, finding F3)? Was **any other** run orphaned by the same six
deploys (look for the `<== ~14400s CAP` flag, or a run still sitting `STARTED`)? Did the P1.2W
refit run at 14:30? And did the **next** NCAAF fire (2026-09-15 18:00 UTC) self-heal?

> If several unrelated jobs show `wall_s ≈ 14400`, the cause is **systemic to deploys**, not
> specific to NCAAF — and the fix moves from a job tag to the drain/serialisation boundary.

---

### R3 — which schedules are actually ON

```bash
$DC exec -T dagster-codeloc python - <<'PY' 2>&1 | tee -a "$OUT"
from dagster import DagsterInstance
print("### R3 — persisted instigator states")
print("A schedule at its CODE DEFAULT has NO row here — absence means 'never toggled',")
print("NOT 'stopped' (the NF-CAP1 reading). sports_ncaaf_dbt_schedule's code default is STOPPED.")
with DagsterInstance.get() as inst:
    states = list(inst.all_instigator_state())
    print("-" * 78)
    for s in sorted(states, key=lambda x: x.instigator_name):
        print(f"{str(s.instigator_type):<26} {s.status.value:<9} {s.instigator_name}")
    print("-" * 78)
    print("rows:", len(states))
PY
```

**Why:** corroborates R1's `tags`. `sports_ncaaf_dbt_schedule` ships `default_status=STOPPED`, so
if it has no RUNNING row **and** R1 shows no `gate=game_day` tag, the run was launched by hand and
the 18:00 arithmetic does not apply — the window must be re-derived from R1's actual `start`.

---

### R4 — the OOM branch, opened or closed

```bash
{
  echo "### R4 — kernel OOM / container kills"
  sudo dmesg -T | grep -iE 'out of memory|killed process|oom-kill|oom_reaper' | tail -40
  echo "--- journal 2026-09-14 17:30 → 22:30 UTC ---"
  sudo journalctl --since '2026-09-14 17:30:00' --until '2026-09-14 22:30:00' --utc --no-pager \
    | grep -iE 'oom|killed process|out of memory' | tail -60
  echo "--- docker inspect dagster-codeloc (⚠️ CONTAMINATED — see note) ---"
  docker inspect credence-dagster-dagster-codeloc-1 \
    --format 'StartedAt={{.State.StartedAt}} RestartCount={{.RestartCount}} OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}'
} 2>&1 | tee -a "$OUT"
```

⚠️ **`docker inspect` can no longer date the 18:00 restart.** The 22:32 and 22:45 deploys recreated
the container again, so `.State.StartedAt` now reports the *latest* deploy. (`.RestartCount` never
could — it does not increment on API/compose restarts; FU-1.) It is captured for the record only.
The kernel log is the part that still carries information.

---

### R5 — impact: how stale are the NCAAF marts *right now* (CONTENT, never an mtime)

```bash
$DC exec -T dagster-codeloc python - <<'PY' 2>&1 | tee -a "$OUT"
import duckdb, os
print("### R5 — NCAAF mart content vintage")
p = os.environ.get("SPORTS_DUCKDB_PATH", "/var/lib/credence/sports/sports.duckdb")
print("SPORTS_DUCKDB_PATH =", p, "| exists:", os.path.exists(p))
try:
    con = duckdb.connect(p, read_only=True)
except Exception as exc:
    print("!! could not open read-only:", type(exc).__name__, exc)
    print("   (a LOCK error here means a build is CURRENTLY RUNNING against this file)")
    raise SystemExit(0)
for label, sql in [
    ("dim_ncaaf_game / 2026", """
        select season,
               max(game_date) filter (where is_completed)        as last_completed_game,
               count(*)       filter (where is_completed)        as completed_games,
               max(season_order_week) filter (where is_completed) as last_completed_week,
               max(game_date)                                     as last_scheduled_game
        from main_ncaaf_marts.dim_ncaaf_game where season = 2026 group by season"""),
    ("rollup_ncaaf_team_week_asof / 2026", """
        select season, max(season_order_week) as max_asof_week, count(*) as n_rows
        from main_ncaaf_marts.rollup_ncaaf_team_week_asof where season = 2026 group by season"""),
]:
    try:
        print(f"-- {label}: {con.execute(sql).fetchall()}")
    except Exception as exc:
        print(f"-- {label}: !! {type(exc).__name__}: {exc}")
PY
```

**Why:** INC-41 — a content read, never an object mtime and never `aws s3 ls`. If the
**2026-09-12** Saturday slate is missing from `last_completed_game`, the marts never absorbed it,
and `sports_ncaaf_serving_write_schedule` has been republishing that stale state hourly at **:20**
ever since. This is also the **before** half of the restore verification.

---

### R6 — does the deploy drain probe actually answer? (tests finding F4)

```bash
{
  echo "### R6 — the exact GraphQL the deploy drain runs"
  curl -fsS http://localhost:3000/graphql -H 'Content-Type: application/json' \
    --data '{"query":"{ runsOrError(filter:{statuses:[STARTED]}, limit:5){ __typename ... on Runs { results { runId status } } ... on PythonError { message } } }"}'
  echo
} 2>&1 | tee -a "$OUT"
```

**Why:** `deploy.sh:167-175` treats a *transport* failure as `unknown` (the INC-36 fix) but a
**GraphQL-level** error still degrades to a silent `0` — `runsOrError` resolving to `PythonError`
yields JSON with no `results` key, `.get('results',[])` gives 0, and the drain logs
*"no in-flight runs — safe to recreate."* This read shows the raw shape. A clean
`"__typename":"Runs"` means the probe is healthy today and F4 stays a latent defect rather than a
contributing cause.

---

### R7 — host-cron activity in the window (the non-Dagster half of the census)

```bash
{
  echo "### R7 — capture-cron.log, 2026-09-14 17:00→22:30"
  awk '/2026-09-14 1[7-9]:|2026-09-14 2[0-2]:/' /home/ec2-user/capture-cron.log 2>/dev/null | tail -80
  echo "--- errors/timeouts anywhere in that log today ---"
  grep -iE 'error|timeout|killed|Traceback|MemoryError' /home/ec2-user/capture-cron.log 2>/dev/null | tail -40
  echo "--- daemon log (⚠️ only since the 22:32/22:45 recreate — the 22:00 event is GONE) ---"
  $DC logs --no-color --timestamps --tail 200 dagster-daemon 2>/dev/null | grep -iE 'monitor|exceeded|terminat|forcib' | tail -40
} 2>&1 | tee -a "$OUT"
```

⚠️ The daemon's own *"has exceeded maximum runtime … terminating run"* log line for 22:00 was
written by a container destroyed at 22:32 — container logs die with the container. Only Postgres
(R1) still has it. This read is for *current* state and for the host crons.

---

### R8 — free, and you already have it: the alert email's own timestamp

Please paste the **received time of the SNS failure email** (UTC if possible). It independently
pins the kill instant, and `kill − 14400 s` gives the run's start without trusting any clock on the
box.

---

### Send back

```bash
wc -l /tmp/ncaaf-inc-0914-evidence.txt && cat /tmp/ncaaf-inc-0914-evidence.txt
```

R1 and R2 are the two that decide it; R0 and R3–R8 close the branches R1 cannot.

---
## 5. Falsifiable predictions — what each outcome of R1 means

> **OUTCOME (2026-09-16):** rows 1, 3 and 4 fired. `wall_secs` 14432.8 ≈ 14400; `start`
> 18:00:47 with the log stopping at 18:00:48.12 inside the recreate window; tags carry
> `gate=game_day` + `dagster/schedule_name`. Neither the terminate-exception event nor a
> crash-explanation event is present — consistent with a code server that was **up and
> answering but had forgotten the run**, i.e. recreated. R2 fired the systemic row: four
> other runs died in the same event.


| R1 shows | Reading |
|---|---|
| `wall_secs ≈ 14400` (±one monitoring tick) | §1 confirmed: killed by the 4 h cap, not by a dbt error. |
| `wall_secs` materially ≠ 14400 | §1 is **wrong** for this box — a `dagster/max_runtime` tag or a different Dagster version is in play. Stop and re-derive from R0. |
| `start ≈ 18:00:1x–18:01` **and** last step log stops at/near that minute | The run was launched into the 18:00:23–18:00:53 recreate window. Cause: **deploy-during-run orphaning**, drain blind to QUEUED/STARTING (§3b). |
| `tags` contain `sport=ncaaf, gate=game_day` | Launched by `sports_ncaaf_dbt_schedule` (those tags are set only there). Absent ⇒ a manual/ad-hoc launch, and the 18:00 arithmetic does not apply — re-derive the window from the actual `start`. |
| An engine event `"Exception while attempting to terminate run…"` | codeloc was **unreachable** at 22:00, not merely forgetful. A different sub-cause (container down/saturated at that moment) — note both later deploys were *after* 22:00. |
| An engine event `"Run execution process for … "` with an exit code | The subprocess died and codeloc *did* notice — which contradicts §2b's 4-hour silence and would be an anomaly worth its own line. |
| Step logs showing dbt output progressing well past 18:01 | The worker was alive and working; §2c says it still could not reach 4 h, so re-open with the last logged timestamp as the new anchor. |
| R2 shows other runs with `wall_s ≈ 14400` or stuck STARTED | The cause is **systemic to deploys**, not specific to NCAAF — which changes the fix from a job tag to the drain/serialisation boundary. |

**If R1 shows a `start` that does not sit inside any deploy window and no terminate-exception
event, then the evidence does not distinguish "worker died silently" from "worker hung outside its
own bounded legs", and the honest verdict is that it cannot.** The instrumentation that *would*
distinguish them is named in follow-up F1: a run-worker liveness check (or an equivalent
heartbeat), which this instance does not have at all today (§2a).

---

## 6. What was NOT established at phase 1 — now closed

| Open at phase 1 | Settled by |
|---|---|
| The cause | R1 + R2 + the CD job log (§0a) |
| QUEUED vs STARTING vs STARTED at 18:00:23 | R1 — **STARTING** (18:00:09.44 → 18:00:47.67) |
| Whether `sports_nfl_dbt_build_job` also fired at 18:00 | R2 — yes, and it died in the same event |
| Whether OOM played any part | R4 — no (§0c) |
| The Dagster version on the box | R0 — **1.13.22** (the source reading in §1 holds) |

One read is still outstanding and is **not load-bearing**: R6 (does the drain probe return a
well-formed `Runs` body today?). The `PythonError`-reads-as-drained hole is fixed in §7 regardless,
because requiring `__typename == "Runs"` is the correct reading of the response whether or not the
probe is currently degraded.

---

## 7. The fix

Two changes. The first is the cause; the second bounds how long a future orphaning can stay
invisible and is explicitly **not** a cure. ⛔ Nothing here raises a timeout, a budget or a tier cap
to make the symptom go away, and the run monitor's kill behaviour is untouched — it did its job.

### 7a. CAUSE — `services/dagster/aws/deploy.sh`, `in_flight()`

The drain now counts every **non-terminal** run (`QUEUED, NOT_STARTED, STARTING, STARTED,
CANCELING`), not just the ones already executing. Under `QueuedRunCoordinator` every scheduled run
spends its first seconds in states the old filter could not see — measured here as a **47-second**
blind window, with the probe landing squarely inside it.

It also now **branches on `__typename`**. INC-36 hardened the *transport* failure (a failed curl
returns the `unknown` sentinel); a **GraphQL-level** error still degraded to `0`, because
`runsOrError` resolving to `PythonError` returns HTTP 200 with a body carrying no `results` key and
`.get('results', [])` read that as "drained". Verified two-sided against real response shapes:

| probe body | before | after |
|---|---|---|
| `Runs` with 1 result (a run in STARTING) | 1 | 1 |
| `Runs`, empty — genuinely drained | 0 | 0 |
| **`PythonError`** | **0 — "drained"** | **`unknown`** |
| top-level `errors` / `data: null` | `unknown` | `unknown` |
| non-JSON body | `unknown` | `unknown` |

With this in place the 18:00 deploy would have waited ~3 minutes and all five runs would have
completed. The `unknown` path is unchanged: still ALERT-loud and still bounded by `DRAIN_UNKNOWN_MAX`.

### 7b. DETECTION LATENCY — `pipeline/jobs/sports_dbt_job.py`, both build jobs

`sports_ncaaf_dbt_build_job` and `sports_nfl_dbt_build_job` now carry the two run tags that every
comparable job on this box already had, and that their own sibling `sports_ncaaf_strength_refit_job`
has carried since NCAAF-P1.2W:

- **`dagster/max_runtime` = 10800 s**, *derived* as `_DBT_LEGS_PER_JOB (4) × DBT_TIMEOUT_SECONDS
  (2400) + 1200`, so E11.26's `leg_cap < job_ceiling < cadence` (2400 < 10800 < 86400) holds by
  construction and cannot drift if the leg cap moves. The ceiling deliberately sits **above** the
  legs' worst case: a ceiling below them would preempt a slow-but-healthy build and replace its
  diagnosable leg timeout with the cause-free forcible-failure message.
  ⚠️ This takes worst-case detection 4 h → 3 h. That is all it does. The four-hour blindness is
  finding F1 — no worker-liveness check exists on this launcher at all — and no timeout fixes that.

- **`concurrency_group = "sports_dbt_build"`, shared by both.** This is a *second, distinct* defect
  the census surfaced: the two schedules carry the identical cron (`0 11` America/Los_Angeles) and
  materialize into **one DuckDB file** (`profiles.yml` resolves a single `SPORTS_DUCKDB_PATH` for
  both sports, separate schemas). DuckDB's write lock is exclusive, so on any day both game-day
  gates open, whichever opens second dies on the lock. R3 confirmed **both schedules RUNNING**.
  `tag_concurrency_limits` in `services/dagster/dagster.yaml` already caps a group at 1 run per
  unique value, so one build simply queues behind the other. If the PM would rather card this
  separately, it is the one-line `SPORTS_DBT_CONCURRENCY_GROUP` constant and its two guard clauses.

### 7c. Guards — RED-proven, 7/7

- `betting_ml/tests/test_deploy_concurrency_guard.py` — **extended, not forked** (INC-36 owns
  `deploy.sh`'s invariants): two clauses in the existing `TestTheDrainDoesNotFailOpen`.
- `betting_ml/tests/test_ncaaf_inc_0914_run_ceiling.py` — AST-based, so a comment mentioning a tag
  cannot satisfy a clause that a missing tag should fail (INC-38). Imports nothing from `pipeline`,
  so it stays in the fast gate (E11.23).
- `betting_ml/tests/ncaaf_inc_0914_red_proof.py` — **7/7 breaks turn their named clause RED** on a
  7/7 green baseline, with all four house controls. The **NOT-SELECTED** control actually fired on
  the first run (unqualified node ids), which is the control working: a false RED is the dangerous
  direction. One case deliberately re-introduces the INC-36 `|| echo 0` fail-open, proving that
  widening the filter did not weaken the guard already there.

Local: football shard 2207 passed · core shard 6691 passed · fast-gate hygiene 505 passed.

---

## 8. Restore + verify

**No restore run is required, and no manual re-run is recommended.** The marts were rebuilt twice
on 09-14 *after* the game day (§0d), R5 shows completed games through 2026-09-13 — the most recent
CFB game day — no CFB games have been played since, and the 09-15 tick correctly skipped on the
game-day gate. Firing a rebuild now would materialize the same rows from the same lake.

Nothing downstream consumed a stale mart: `sports_ncaaf_strength_refit_job` ran at **14:30**, three
and a half hours *before* the failed build, on the 13:00 roll-forward's marts;
`sports_ncaaf_serving_write_job` has been SUCCESS hourly at `:20` throughout; and
`sports_ncaaf_prediction_snapshot_job` ran green on 09-15.

**The verification that matters is of the fix, not of the data**, and it is a RUNTIME-GATE item —
CI mocks all IO and cannot see a shell probe running against a live Dagit:

1. **After merge, the next CD deploy exercises 7a automatically.** In the deploy's own log, the
   drain line should now read `N in-flight run(s) active — waiting…` whenever a run is live —
   including one still in `STARTING`. Five consecutive deploys on 09-14 logged
   `no in-flight runs` while runs were in flight; that is the before-state to compare against.
2. **Confirm the tags landed** (they ship with the image, so this is post-deploy):
   ```bash
   docker compose -f /home/ec2-user/app/services/dagster/aws/docker-compose.yml \
     exec -T dagster-codeloc python - <<'PY'
   from dagster import DagsterInstance, RunsFilter
   import datetime as dt
   LO = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
   with DagsterInstance.get() as inst:
       for rec in inst.get_run_records(filters=RunsFilter(created_after=LO), limit=200):
           r = rec.dagster_run
           if r.job_name.endswith("_dbt_build_job"):
               print(r.job_name, r.run_id[:8], r.status.value,
                     "| max_runtime:", r.tags.get("dagster/max_runtime"),
                     "| group:", r.tags.get("concurrency_group"))
   PY
   ```
   A run launched from the new image must show `max_runtime: 10800` and
   `group: sports_dbt_build`. ⚠️ An older run predates the change and will show neither — check a
   run whose start time is after the deploy.
3. **R6 is still worth one paste** when convenient — it says whether the drain probe is returning a
   well-formed `Runs` body today, i.e. whether the `PythonError` hole was ever live or purely latent.
