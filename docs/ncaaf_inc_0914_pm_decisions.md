# NCAAF-INC-0914 — four decisions for the PM

**Context in one paragraph.** On 2026-09-14 a routine CD deploy recreated `dagster-codeloc` (the
Dagster code server *and* run worker) while five runs were in flight, and killed all five. The
proximate defect is fixed in PR #1129: the deploy's drain probe filtered `statuses:[STARTED]` only,
so it could not see a run in `QUEUED`/`STARTING` — a measured **47-second** blind window per run —
and it reported "no in-flight runs" 25 seconds before tearing the worker down. What the incident
also measured, and what these decisions are about, is that **this box deploys ~11 times a day, each
deploy recreates the run worker, and nothing on the box can tell that a run worker has died.** The
NCAAF build took **4 hours** to be declared failed, and the alert named no cause. Full evidence:
`docs/ncaaf_inc_0914_evidence_reads.md` (§0 verdict, §7 fix). Spec:
`plan_specs/ncaaf/ncaaf-inc-0914.yaml`.

**The one number that frames all four decisions.** The same event produced three detection
latencies, and the only difference was what instrumentation each job happened to have:

| Latency | Runs | Caught by |
|---|---|---|
| ~3 min | `sports_nfl_dbt_build_job`, `artifact_freshness_job`, `intraday_public_betting_job` | Dagster's 180 s **start**-timeout (they never reached STARTED) |
| 26 min | `intraday_schedule_job` | its own E11.26 `dagster/max_runtime` (1500 s) |
| **4 h** | **`sports_ncaaf_dbt_build_job`** | the instance-wide 14400 s cap — it had crossed into STARTED ~1 s before the teardown |

`DefaultRunLauncher` does not implement `supports_check_run_worker_health`, and the base
`RunLauncher` returns `False`. **Once a run reaches STARTED, this instance never checks whether its
worker is alive.** That is why a dead worker and a hung worker are indistinguishable here, and why
the alert that eventually fires names no cause — it will read identically for OOM, crash and hang.

---

## Decision 1 — When the drain gives up, what should happen to the runs the deploy is about to kill?

**Why this is still live after the fix.** The drain waits up to `DRAIN_TIMEOUT` (600 s) and then
**proceeds anyway with a WARN** — correct by INC-36's design, because a deploy that blocks forever
is its own incident. But `daily_ingestion_job` runs **~86 minutes** (5178 s on 09-14, 5302 s on
09-15). Any deploy landing inside it waits 600 s and recreates into a live run. PR #1129 narrows
the window; it does not close it.

**Load-bearing fact:** every in-flight run is a *subprocess of `dagster-codeloc`*
(`DefaultRunLauncher`), so a recreate kills all of them **by construction**. After a recreate,
any run that was non-terminal before it is dead — there is no "it might have survived" case.

| Option | What it costs | What it buys |
|---|---|---|
| **A. Status quo** | 0 | Dead runs surface up to 3 h later with a message naming no cause. |
| **B. Fail-and-attribute** — after the recreate, `deploy.sh` marks any run that was non-terminal before it as FAILED, naming the deploy + commit SHA | ~15 lines in `deploy.sh`; needs a runtime-gate verification (CI mocks all IO) | Converts a 3-hour cause-free mystery into an **instant, correctly-attributed** failure. Self-limiting: after PR #1129 it usually finds nothing. |
| **C. Refuse the deploy** rather than proceed | Deploys can be blocked for ~86 min by one job | Runs never die — but INC-36 is the counter-evidence: a long-blocked deploy is what pushed one past the CD poll budget and let two deploys race. |
| **D. Raise `DRAIN_TIMEOUT`** above the longest job | 0 code | ⛔ **Not recommended, and the repo has already paid for it.** This is precisely INC-36's root cause. Also E2.1-r: raising a timeout to make a symptom vanish. |

**Recommendation: B.** It is the cheapest option that makes the residual case *diagnosable* rather
than *prevented-and-otherwise-silent*, and it is correct by construction rather than by heuristic.
⛔ Explicitly not D.

---

## Decision 2 — Do we want a general "orphaned run" detector, or is a 3-hour bound acceptable?

PR #1129 gives the two sports dbt builds a job-sized `dagster/max_runtime` (10800 s), which takes
worst-case detection from 4 h to 3 h **and nothing more**. A timeout cannot do better, because the
gap is the absent liveness check, not the ceiling's value. Causes the drain fix does **not** cover:
a host OOM, a container crash, a manual `docker restart`, an autoheal action, or Decision 1's
drain-timeout case.

| Option | Cost | Latency | Names the cause? |
|---|---|---|---|
| **A. Accept the 3 h bound** | 0 | ≤3 h | No |
| **B. Orphaned-run detector** — a run in `STARTED` whose Dagster event log has been silent for > N minutes. Reads **Postgres only**; no launcher change, no new dependency. Hosted as an unbound leaf on an existing hourly job | ~1 day, incl. RED proof | ~1 h | Yes — it can correlate against the container's start time and say *"the code server was recreated at T"* |
| **C. Change the run launcher** (Docker/K8s) so `check_run_worker_health` exists | Large | ~1 min | Yes | 

**On C:** `DefaultRunLauncher` was chosen deliberately — runs execute as subprocesses inside the
code server, so per-run execution cost is ≈ $0 and there is no container spin-up. Switching that on
a 2-vCPU / 16 GB box to gain a health check is a big change for one property. **Not recommended.**

**Recommendation: B, carded as its own small story rather than folded into this incident.** It is
the instrumentation the incident report promised would distinguish "worker died" from "worker
hung", and it generalises past deploys. If the answer is A, that is a legitimate call — but it
should be a recorded decision, not a default, because the next occurrence will look exactly like
this one did.

---

## Decision 3 — Scope check: should the shared `concurrency_group` stay in this PR?

I included a second, **distinct** defect the census surfaced, and I am flagging it rather than
letting it pass silently. `sports_ncaaf_dbt_schedule` and `sports_nfl_dbt_schedule` carry the
**identical cron** (`0 11` America/Los_Angeles) and materialize into **one DuckDB file**
(`profiles.yml` resolves a single `SPORTS_DUCKDB_PATH` for both sports, separate schemas). DuckDB's
write lock is exclusive, so on any day both game-day gates open, whichever opens second dies on the
lock. Both schedules were **verified RUNNING on the box (2026-09-15)**. It has not fired yet only
because the two gates have not both opened since.

The fix is one shared constant plus two guard clauses; `tag_concurrency_limits` in
`services/dagster/dagster.yaml` already caps a group at 1 run per unique value, so one build simply
queues behind the other.

**Recommendation: keep it in this PR.** It is small, it is already RED-proven, and it will fire on
the next day both gates open. If you would rather track it separately, it is
`SPORTS_DBT_CONCURRENCY_GROUP` in `pipeline/jobs/sports_dbt_job.py` and
`TestTheTwoBuildsCannotRaceOnTheSharedDuckDB` — clean to lift out.

---

## Decision 4 — Deploy cadence (process, no code)

**Eleven** `orchestration_cd` deploys on 2026-09-14, six of them between 16:56 and 22:46, each
recreating the run worker, each logging "no in-flight runs". Before PR #1129 that meant eleven
chances a day to silently kill in-flight work.

After PR #1129 each deploy **waits for the box to be idle**, which trades deploy latency for run
safety — up to 600 s per merge on a busy day, and predictably so while `daily_ingestion_job` runs
(12:00–13:28 UTC).

**Recommendation: accept and watch.** No code change. Revisit only if deploy latency becomes a real
complaint, in which case the lever is batching merges to `main`, not shortening the drain. Worth one
line in whatever owns the box's operating picture — the census thread (leaf-run detector,
`ZPmBj8PF`) or `BOX_OPERATIONS.md`. **Extend that, do not fork a second schedule ledger.**

---

## Minor item, no decision needed unless you want one

`Dockerfile:43` installs `dagster>=1.11.5` **unpinned**. The box measured **1.13.22** while the
source analysis behind this diagnosis was read against **1.13.5** — the three code paths it turns on
(`_force_mark_as_failed`, `check_run_timeout`, `CancelExecution`) are identical in both, so nothing
turned on it. But a run-monitoring semantics change can arrive on any `--build`. Same
unpinned-dependency class `CLAUDE.md` already records for the ML libs.

---

## What I need back

For each of Decisions 1–4: the option, and any reasoning you want recorded in the spec's
`closeout.followUps`. Decisions 1 and 2 are the ones that change what gets built next; 3 is a
scope check on a PR that is ready to merge; 4 is a recorded acceptance.
