# E11.26 — the hung `intraday_schedule_job`

**Status:** fixed in code + guarded; **the runtime gate (a real box run) is an operator step — see
§4.** Infra/orchestration, `best_alpha=0`, not user-facing (no changelog entry).

## 1. What happened, and what the cause was NOT

On **2026-07-29** `intraday_schedule_job` ran **>1 hour**. That parked `deploy.sh`'s drain loop for
its full `DRAIN_TIMEOUT` (600 s), which pushed the deploy past the CD poll budget and released the
`orchestration-cd` concurrency group while the SSM command was still live on the box — so a second
`deploy.sh` launched into a running one, `docker compose` hit `removal of container … is already in
progress`, and the auto-rollback left `dagster-daemon` down for ~10 minutes (**INC-36**). INC-36
hardened the *deploy* against a long-running job. **The long-running job itself was never fixed.**

The reflex diagnosis is **INC-32** — "an un-timed-out subprocess on a daemon/serialized path". An
AST sweep of `pipeline/`, `services/` and `scripts/` for `subprocess.run`/`check_output`/`call`
without `timeout=` returns **nothing on this job's chain**: `intraday_ops._run_script` has passed a
finite `timeout=` since the A2.16/INC-32 port on 2026-06-15, and `_dbt_exec._run_dbt_remote` bounds
both its HTTP calls and its poll loop. There was no missing timeout to add.

## 2. The actual root cause: a per-leg budget sized like a daily batch job, on a 30-minute tick

Every leg carried the module default of **1800 s** — which **is** this job's own cron cadence
(`*/30 14-23` + `0,30 0-3` UTC). A timeout equal to the cadence bounds the leg and bounds nothing
that matters: the *run* can still outlive its own successor.

| | seconds | vs. cadence |
|---|---:|---:|
| tick cadence | 1800 | 1.0x |
| per-leg timeout (module default), **each** leg | 1800 | 1.0x |
| live budget, `TICK_SF_FREE=1` — ingest + `--w3pre-only` + `--w7b-only` | **5400** | **3.0x** |
| rollback budget, `TICK_SF_FREE=0` — + ext refresh + dbt, incl. the dbt-runner 409 `RetryRequested` (40x30 s) | **10200** | **5.7x** |
| the only ceiling in the system: global `run_monitoring.max_runtime_seconds` | 14400 | 8.0x |

**A run of ">1 hour" therefore needs no hang at all — it is inside the budget the job was granted.**
Nothing terminated it because the only ceiling is a 4-hour global cap sized for the Sunday
full-refresh build.

Two aggravating factors, both structural:

* **`intraday_schedule_job` carried no `concurrency_group` tag.** Every other recurring job in
  `pipeline/jobs/intraday_jobs.py` has one, so the `tag_concurrency_limits` rule in
  `services/dagster/dagster.yaml` (limit 1 per unique value) never applied to it. A tick permitted
  to run 90 minutes on a 30-minute cron can **stack** — and concurrent ticks write the same S3
  partitions and each run DuckDB with `threads=2` on a **2-vCPU** box. That is how a slow tick
  compounds into the CPU saturation that starves the Dagster daemon (the INC-32 outcome, reached by
  a different route).
* **`subprocess.run` kills only the DIRECT child.** A "killed" leg could leave a grandchild holding
  a vCPU — half the box.

Measured context (INC-42 diagnostics, 2026-08-12, the only place these runs are visible): a healthy
tick completes **under 10 minutes** for all three live legs together; a pathological `--w3pre` leg
errored on its own at **1044 s** inside its 1800 s allowance.

## 3. The fix — three layers, each doing one job

| layer | where | what it bounds |
|---|---|---|
| **per-leg cap, 480 s** | `betting_ml/monitoring/intraday_tick_budget.LEG_TIMEOUT_SECONDS`, wired into every `_run_script`/`_run_dbt` call on the chain | a single wedged leg — fails **in-op**, so it keeps INC-41's per-leg independence (the other leg still runs) and pages with its own name attached |
| **job ceiling, 1500 s** | `dagster/max_runtime` tag on `intraday_schedule_job` | *everything else* — a `requests` poll, the dbt-runner 409 backoff (20 min), pure in-process work. It does not require anyone to have enumerated every wait, which is exactly why per-leg timeouts alone were insufficient |
| **`concurrency_group`** | job tag, against the existing instance rule | stacking, so a slow tick cannot compound |

Plus two smaller closures on the same path:

* **`betting_ml/utils/bounded_subprocess.run_bounded`** replaces `subprocess.run` in `_run_script`:
  the child starts in its **own process group** and the **whole group** is killed on expiry *and* on
  any `BaseException` (a Dagster run-monitoring termination — which the new ceiling makes a routine
  path, so it has to be clean).
* **`send_alert`'s SNS publish is bounded** (5 s connect / 10 s read / 3 attempts). botocore's
  defaults allow a ~5-minute stall, and this function is called from inside ops *precisely when they
  are already failing and slow* — an unbounded page compounds the overrun it is reporting.

### The invariants (pinned by `betting_ml/tests/test_e11_26_intraday_tick_budget.py`)

```
I1  leg cap (480)            <  job ceiling (1500)     single wedged leg always caught in-op
I2  job ceiling (1500)       <  cadence (1800)         a run is dead before its successor fires
I3  live budget (3x480=1440) <= job ceiling (1500)     all-legs-timeout still caught in-op
I4  no leg runs on the 1800s module default
```

⚠️ **I1 is currently implied by I3** (with three live legs, `3xLEG <= MAX` entails `LEG < MAX`), so
no mutation isolates it and the RED proof does not claim a fixture for it. It is retained because it
states the design intent and becomes independently binding if `LIVE_LEGS` shrinks. Recorded rather
than hidden — an isolating fixture per clause is necessary but not sufficient when one clause
re-tests another (NF-D17 / NF-W7j).

### What the RED proof found that review did not

`uv run python betting_ml/tests/e11_26_red_proof.py` — **22/22 breaks caught**. Three of those cases
exist only because the proof failed first:

1. ⭐ **Deleting `start_new_session=True` made the proof run kill itself** (exit 144, no output, and
   it left the deliberate break on disk because a signal skips `finally`). Without
   `start_new_session` the child shares the *caller's* process group, so `killpg` reaches the caller
   — in production that is **the Dagster run worker SIGKILLing itself**, turning a bounded leg
   timeout into a lost run with no diagnosis. `_terminate_group` now refuses to signal a group it is
   a member of, and the proof restores stale backups on start-up.
2. **The SIGKILL escalation was untestable against a `time.sleep` child** (it dies on SIGTERM), and
   an elapsed-time assertion could not see the difference either — a SIGTERM-only runner still
   returns in ~11 s because the post-kill drain bounds it. The test now uses a **SIGTERM-ignoring**
   child (the realistic wedge) and asserts **the child is dead**, not that the call returned quickly.
3. **The cron guard was satisfied by a different schedule.** `artifact_freshness_daytime` carries the
   identical cron string, so `'"*/30 14-23 * * *"' in src` stayed green with the intraday cadence
   changed underneath it. It now reads the cron off the named `ScheduleDefinition`.

Two pre-existing guards (`test_cost_wake_gates.py::test_ext_refresh_is_gated_not_removed`,
`test_lineup_intraday_wide_rebuild.py::test_intraday_schedule_rebuilds_lineups_wide_...`) anchored on
`'refresh_w1_external_tables.py")'` — the closing paren moved when the call gained `timeout=`. Both
were **re-anchored onto the new implementation, not weakened**, and both are re-proved falsifiable in
the RED proof.

## 4. ⏭️ Runtime gate — OPERATOR, run on the BOX after the PR merges to `dev` and deploys

CI mocks all IO, so **CI-green is necessary-not-sufficient** for this change class. Two things must
be observed on a real box.

**(a) A normal tick still completes, and now carries both tags.** Run on the **EC2 BOX**:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python -c "
from dagster import DagsterInstance
import datetime as dt
i = DagsterInstance.get()
for rec in i.get_run_records(limit=200):
    r = rec.dagster_run
    if r.job_name != 'intraday_schedule_job':
        continue
    ts = rec.start_time or rec.create_timestamp.timestamp()
    end = rec.end_time
    dur = (end - ts) if end else None
    print(dt.datetime.fromtimestamp(ts, dt.UTC).isoformat(), r.run_id[:8], r.status.value,
          f'{dur:.0f}s' if dur else 'RUNNING',
          'max_runtime=' + str(r.tags.get('dagster/max_runtime')),
          'cgroup=' + str(r.tags.get('concurrency_group')))
" 2>&1 | head -20
```

PASS = the newest runs show `SUCCESS`, a duration **well under 1500 s**, `max_runtime=1500` and
`cgroup=intraday_schedule`. ⚠️ Runs from **before** the deploy carry `max_runtime=None` — that is the
pre-fix baseline, not a failure; compare by timestamp against the deploy time. Per FU-1, the tags
only take effect for runs launched **after the executing `dagster-codeloc` container was recreated**
(`up -d --build`), not merely restarted.

**(b) A deliberately-slow leg is KILLED at the timeout, not hung.** Run on the **EC2 BOX** — this
drives the real `run_bounded` at a 5-second budget against a SIGTERM-ignoring child that has spawned
a grandchild, so it proves the kill path in the container the job actually executes in.

⚠️ **THE CHECK MUST DISTINGUISH A ZOMBIE FROM A LIVE PROCESS.** `os.kill(pid, 0)` SUCCEEDS on a
zombie, and `dagster-codeloc` runs `dagster api grpc` as PID 1 with no `init: true`, so a
successfully-killed orphan is reparented to a process that never calls `wait()` and its PID-table
entry persists indefinitely. The first cut of this command used a bare `os.kill` and reported
`FAIL: grandchild SURVIVED` for a process that had in fact been killed (measured on the box
2026-08-20: `State: Z (zombie)`, `cmdline: []`, 1 jiffy of CPU). A false FAIL on a verification
command is worse than no command — it tells a future operator the fix is broken.

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python -c "
import subprocess, sys, time, os, pathlib
from betting_ml.utils.bounded_subprocess import run_bounded

def state(pid):
    # 'gone' or 'zombie' both mean KILLED; only 'alive' is a failure.
    try:
        os.kill(pid, 0)
    except OSError:
        return 'gone'
    st = pathlib.Path('/proc/%d/status' % pid)
    if st.exists():
        for line in st.read_text().splitlines():
            if line.startswith('State:'):
                return 'zombie' if line.split()[1].upper().startswith('Z') else 'alive'
    return 'alive'

# a child that spawns a grandchild AND ignores SIGTERM — the realistic wedge
script = ('import os,signal,subprocess,sys,time\n'
          'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
          'g = subprocess.Popen([sys.executable, \"-c\", \"import time; time.sleep(300)\"])\n'
          'open(\"/tmp/e1126_gpid\",\"w\").write(str(g.pid))\n'
          'time.sleep(300)\n')
t0 = time.monotonic()
try:
    run_bounded([sys.executable, '-c', script], timeout=5)
    print('FAIL: it returned instead of timing out')
except subprocess.TimeoutExpired:
    print('PASS: timed out after %.1fs (expected ~10s, NOT 300s)' % (time.monotonic()-t0))
time.sleep(2)
gpid = int(open('/tmp/e1126_gpid').read())
st = state(gpid)
note = '  (killed; defunct only because PID 1 does not reap)' if st == 'zombie' else ''
print(('PASS' if st in ('gone','zombie') else 'FAIL') + ': grandchild %d is %s%s' % (gpid, st, note))
" 2>&1 | tail -5
```

PASS = **both** lines start `PASS` — timed out at ~10 s (the 5 s budget plus the 5 s SIGTERM grace
before SIGKILL, which is the escalation working, not a delay) and the grandchild reads `gone` or
`zombie`. `alive` would be a genuine defect in `run_bounded`.

ℹ️ A zombie holds **no CPU and no memory**, only a PID-table entry, so it is not what E11.26 exists
to prevent (an orphan burning one of the box's two vCPUs). Zombies arise here only on a leg timeout,
which should be rare. Adding `init: true` to the compose service would reap them, but that changes
PID 1 for every service and therefore the container's shutdown/signal path — on a box whose last
deploy incident (INC-36) involved container removal, that is a change to argue on its own merits,
not a tidy-up to fold into this story.

**(c) Optional, only if you want the ceiling itself observed end-to-end:** launch
`intraday_schedule_job` from Dagit with the run tag `dagster/max_runtime` overridden to `60` against
a slate where a leg takes longer, and confirm run-monitoring terminates it at ~60 s rather than the
run sitting for hours. Not required for merge — (a) and (b) cover the code this story changed.

## 5. What this does NOT cover

* `intraday_weather_job` and `intraday_public_betting_job` also carry no `concurrency_group` and no
  ceiling. They are hourly (not 30-minute) and were not implicated on 7/29, so they are left alone
  deliberately rather than swept up — but the same reasoning applies if either ever runs long.
* `_dbt_exec._run_dbt_remote`'s 409 `RetryRequested(max_retries=40, seconds_to_wait=30)` is a 20-minute
  backoff shared with the HALT-tier daily build. It is **not** narrowed here (that would change the
  daily build's behaviour); the job ceiling bounds it for this job, which is the point of having a
  ceiling that does not depend on enumerating every wait.
* `_dbt_exec._local_state_upload` runs a `dbtf source freshness` subprocess with **no timeout**. It is
  reachable only on the local/dev path (`DBT_RUNNER_URL` unset, `use_state=True`) — never on the box,
  and never from this job — so it is recorded here rather than changed under this story.
* `services/dbt_runner/server.py::_run_cmd`'s comment claims it kills "the child **and its process
  group**"; it uses `subprocess.run`, which does not. The runner's timeout + reaper still free the
  single-tenant lock correctly, so the behaviour is sound and only the prose overclaims — recorded,
  not fixed here.
