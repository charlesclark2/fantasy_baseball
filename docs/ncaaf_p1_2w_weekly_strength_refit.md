# NCAAF-P1.2W — the weekly P1.2 strength re-fit, scheduled

**What changed:** the P1.2 team-strength posterior is now re-fit **weekly, in season, by a box
Dagster job**, instead of once per season by an operator on a laptop. The fit itself is untouched —
same CLI, same model, same artifacts, no calibration verdict re-read.

---

## 1. Why

Every NCAAF surface's strength rating, uncertainty band and both ranks move **only** when
`ncaaf/derived/team_strength_week` is rewritten. NCAAF-P3.3b proved nothing scheduled did that, three
ways that agree, and the state was still live when this story ran:

| read | value | taken |
|---|---|---|
| `ncaaf/derived/team_strength_week` newest Delta commit | **2026-08-18T06:16:36Z** (v67) | 2026-09-13 |
| distinct `as_of_week` for season 2026 | **{1}** — the pre-season prior, on all 138 teams | 2026-09-13 |
| `ncaaf/raw/games` newest Delta commit | 2026-09-07T13:00:52Z (v32) — the roll-forward firing | 2026-09-13 |

Three played weeks in which a team could win by 26 and see its rating sit unchanged beside that win
in its own schedule.

## 2. What the job does

`sports_ncaaf_strength_refit_job`, fired by `sports_ncaaf_strength_refit_schedule`
(`30 7 * 8,9,10,11,12,1 1` — **Monday 07:30 America/Los_Angeles, Aug → Jan**):

```
precondition → NCAAF mart rebuild → run_team_strength --s3 → VERIFY → serving publish
```

### 2.1 The discriminator is the story

P1.2 reads its covariates from the **sports dbt marts**, not from the lake. So `run_team_strength`
against stale marts reproduces the pre-season cold start, writes a full set of Delta commits, exits
0 and looks exactly like success — **it did that on 2026-08-17**. Two consequences:

* **the marts rebuild runs INSIDE the job, before the fit.** Never assumed done by
  `sports_ncaaf_dbt_schedule`, which does genuinely rebuild them most in-season mornings — relying
  on that is the INC-25 shape.
* **the run must prove it WORKED, not that it RAN.** `ncaaf_strength_verify_op` reads the landed
  artifact and **fails the run and pages** on any of:

  | verdict | what it means |
  |---|---|
  | `VINTAGE_DID_NOT_ADVANCE` | the Delta version captured before the fit is still the newest one — the fit wrote nothing |
  | `COLD_START` | `covariate_component_roster_flux` / `_coaching` are zero — the stale-marts signature |
  | `WEEK_DID_NOT_ADVANCE` | the marts hold completed games and the fit emitted no as-of week past 1 |
  | `UNREADABLE` | the artifact could not be read after the fit — unverified, never scored healthy |

  ⭐ **All three readings are needed, and this is measured rather than argued.** The NCAAF-PS
  report's operator SQL (`0/0/138` is a cold start, `136/136/138` is a real fit) is the obvious
  check to schedule, and **on its own it certifies the frozen artifact**: on 2026-09-13 the frozen
  table read `roster_flux 136 / coaching 136 / 138 teams`. The covariate check passes on an artifact
  that has not moved since August.

### 2.2 Sequencing

07:30 is 90 minutes after the roll-forward's 06:00 raw ingest — **but the offset is a courtesy, not
the ordering guarantee.** The guarantee is `ncaaf_strength_precondition_op`, which reads
`ncaaf/raw/games`' own Delta commit and **refuses to fit** when it is older than 48h, paging and
naming the roll-forward. A re-fit over stale raw would *succeed* and stamp today's date on the
served "ratings as of" line, which is worse than failing.

### 2.3 Monitoring, and what each half can and cannot see

| detector | catches | blind to |
|---|---|---|
| the job's own verify step | a fit that ran and did nothing | the job not running at all |
| `CRITICAL_SCHEDULES` heartbeat | the schedule **toggled off** — and, because it self-starts, a Dagster-volume reset too | `NCAAF_STRENGTH_REFIT_ENABLED` never set or lapsed (the schedule is RUNNING and every tick skips) |
| `ncaaf_team_strength_week` freshness contract | **all** of the above, from the artifact side — 192 **active** hours over Aug–Jan | nothing, while its host job runs |

The flag's own drift is the reason the artifact contract is load-bearing rather than belt-and-braces:
an armed-but-not-firing schedule looks healthy from every producer-side angle, and only the landed
data disagrees (INC-41).

The freshness contract is evaluated by an unbound ALERT leaf on
`sports_ncaaf_prediction_snapshot_job` (Tuesday), **not** inside the re-fit job: a monitor hosted
inside its own subject cannot see its subject stop (NF-INFRA2). The snapshot is also the artifact
stale ratings damage irreversibly — its rows are immutable.

### 2.4 The season boundary

Lag accrues **only inside Aug–Jan, and the clock restarts each August**. A final January fit is
legitimately fresh through July and starts ageing again on August 1 — idle by *declaration*, not by
a suppressed check (a suppressed check would false-page on its first read back, because by then the
raw gap spans the whole winter; measured: a Jan-25 fit carries 152h into August and would breach a
192h SLA barely an hour after the season's first scheduled fire).

⚠️ **When the season ends, stop this schedule and `sports_ncaaf_prediction_snapshot_schedule`
together.** Stopping the re-fit alone leaves the SLA's host running, and it will correctly report
that the weekly re-fit has died.

---

## 3. ⏭️ OPERATOR — the runtime gate (deploy-held; CI mocks all IO)

> Run these **after the PR merges to `dev` and `dev` is promoted to `main`** (the box image ships on
> merge to `main` via `orchestration_cd.yml`). **Merged never means running** — the schedule ships
> `default_status=STOPPED`.

### Step 0 — expect ranks to move, a lot

The first real in-season fit replaces a pre-season prior (`strength_margin_sd ≈ 7.3`) with a
posterior that has absorbed **three** played weeks. **Teams will move a long way on the board the
morning it lands.** That is the product working; it is not a defect, and it is the single thing most
likely to be misread on the day.

### Step 1 — arm the schedule (BOX, one flag + a redeploy)

The schedule ships `default_status=RUNNING` and is already ticking — and **every tick is skipping**,
loudly, until one flag is set. (Why a flag rather than a STOPPED default: a STOPPED-default schedule
in `CRITICAL_SCHEDULES` cannot see the revert that matters, because a wiped toggle leaves no
persisted row to flag — the NF-CAP1 reading — and E11.23's `test_critical_instigators_self_start`
pins every member to `RUNNING`. See the schedule's module docstring.)

**On the box**, add the key to `${APP_DIR}/services/dagster/aws/.env` — the file `deploy.sh`
validates, **not** `~/app/.env` — and redeploy so the code-location container is RECREATED (a
container restart is not enough; FU-1: an env flip only takes effect in the container Dagster runs
job subprocesses in):

```
NCAAF_STRENGTH_REFIT_ENABLED=1
```

⚠️ `git pull` never touches the box's `.env`. This key is deliberately **not** in `env.required` —
that would fail the next deploy to enforce a default whose correct value at deploy time is OFF.

Then confirm the flag is live **in the job-executing container**:

```bash
docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
  printenv NCAAF_STRENGTH_REFIT_ENABLED
```

Confirm `sports_ncaaf_roll_forward_schedule` is **ON** in Dagit and its last run is green — the
re-fit refuses to fit on raw games older than 48h.

### Step 2 — launch the first run by hand and watch it (Dagit, browser)

Dagit → **Jobs** → `sports_ncaaf_strength_refit_job` → **Launch Run**.

⚠️ **Launch it on a Monday after 06:00 PT**, or the roll-forward's weekly ingest will be more than
48h old and the precondition will refuse (by design). For a deliberate off-cycle run, set
`NCAAF_STRENGTH_REFIT_RAW_MAX_LAG_HOURS` on the box first and say so in the run log.

**Time each step and record it** — the fit and the marts rebuild are both >2-minute steps, and the
job's ceiling (`dagster/max_runtime` 10800s) was sized from the leg caps rather than from a measured
run.

Read the step log for these `[METRIC]` lines:

```
[METRIC] ncaaf_refit_raw_games_verdict=OK lag_hours=<~1.5> version=<n>
[METRIC] ncaaf_refit_before_version=67 before_commit=2026-08-18T06:16:36Z before_max_as_of_week=1
[METRIC] ncaaf_refit_completed_games=<>0>
[METRIC] ncaaf_refit_after_version=<>67>
[METRIC] ncaaf_refit_max_as_of_week=<>1>
[METRIC] ncaaf_refit_covariate_nonzero_roster_flux=<~136>
[METRIC] ncaaf_refit_covariate_nonzero_coaching=<~136>
[METRIC] ncaaf_refit_verdict=REFIT_LANDED
```

### Step 3 — verify from ARTIFACT CONTENT, not from the run's colour (LAPTOP)

```bash
cd /Users/charlesclark/Documents/machine_learning/baseball_betting/baseball_betting_and_fantasy
SPORTS_LAKE_REGION=us-east-2 uv run python -c "
from deltalake import DeltaTable
from quant_sports_intel_models.football.ncaaf.ingest import s3io
dt = DeltaTable(s3io.table_uri('ncaaf','team_strength_week',tier='derived'),
                storage_options=s3io.storage_options())
h = dt.history(1)[0]
print('newest commit:', h.get('timestamp'), 'version:', h.get('version'))
df = dt.to_pyarrow_table().to_pandas()
d = df[df.season == 2026]
print('teams:', d.team_id.nunique(), 'as_of_week:', sorted(d.as_of_week.unique()))
for c in ('covariate_component_roster_flux','covariate_component_coaching'):
    print(c, int((d[c] != 0).sum()))
print(d.sort_values('as_of_week').groupby('team').tail(1)
        .query(\"team.str.contains('North Dakota|Dakota', na=False)\")
        [['team','as_of_week','games_in_window','strength_margin','strength_margin_sd']])
"
```

Acceptance:

* **newest commit is past 2026-08-18** and the version is past 67;
* **`as_of_week` reaches the played weeks**, not `{1}`;
* **covariate counts > 0** (expect ~136 of 138 for both);
* a team that has played — e.g. NDSU — shows a **rating that has absorbed its games**
  (`games_in_window > 0`), not the pre-season prior.

### Step 4 — verify the live page's stamp, CACHE-BUSTED (LAPTOP)

⚠️ **A cached read and a failed deploy are byte-identical.** Bust the cache or you are reading the
old blob and calling it a pass.

```bash
curl -s "https://credence-sports.vercel.app/api/..." >/dev/null  # (browser is fine; see below)
```

In the browser, open a team page with a **hard reload** (`Cmd-Shift-R`) or append a cache-buster
(`?cb=$(date +%s)`), and check the ratings stamp shows:

* **"ratings as of"** = the new fit's date (today), not 18 Aug; and
* **"next update"** = **a real date** (the next Monday), where it previously stated an absence.

The "next update" half is what this story's one-line registry change activates; if it still states
an absence, the **frontend** did not redeploy (`frontend/` auto-deploys on push to `main`, and a
Redeploy without a `frontend/` change is skipped by `ignoreCommand` — untick *"Use project's Ignore
Build Step"*). If "ratings as of" is stale but the artifact check in step 3 passed, the **serving
write** has not re-published — re-fire `sports_ncaaf_serving_write_job`.

### Step 5 — record the outcome

If steps 2–4 pass, add the changelog entry (it is deliberately **not** in this PR — a declaration
must not outrun production) and note the measured step timings.

---

## 4. Rollback

Set `NCAAF_STRENGTH_REFIT_ENABLED=0` on the box and redeploy (preferred — it leaves the schedule
RUNNING, so the heartbeat still watches it), or toggle the schedule **OFF** in Dagit. The ratings stop advancing and the
freshness SLA starts reporting it within ~8 active days — which is the correct behaviour, not a
defect. Nothing else needs reverting: the job writes only the ratings table (rewritable) and
re-publishes the serving store from it.
