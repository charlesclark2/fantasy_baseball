# E11.15 — Self-hosted Dagster (OSS) on Railway

Replace Dagster+ Serverless (billed per run-minute, ~$325/mo true-monthly and growing)
with self-hosted **OSS Dagster** on Railway (flat compute). This directory holds the
self-host config; the live `pipeline/` code (15 jobs / 9 schedules / 10 sensors) ports
**unchanged** — only the instance/orchestration layer changes.

> **🔒 This orchestrates the LIVE serving pipeline.** Stand up in parallel → validate →
> cut over → keep Dagster+ as instant rollback → decommission only after a clean
> multi-day window. **NEVER run schedules on both at once (double-serve).**

---

## Phase 0 — Design decision: **full OSS self-host** (zero Dagster+ cost)

Chosen over Dagster+ Hybrid (which keeps the hosted UI / Insights / alerting but
**retains** Dagster+ cost). Full OSS maximizes the saving. Trade-off accepted: we lose
Dagster+ Insights / branch-deploys / built-in alerting. Our failure contract already
covers basic alerting — the WARN/HALT/ALERT tiers (CLAUDE.md) + the alert **sensors**
(`pregame_alert_sensor`, `clv_alert_sensor`, `model_health_alert_sensor`,
`odds_freshness_alert_sensor`, `schedule_freshness_alert_sensor`, …) raise/emit on their
own and keep working under OSS. Re-add light external alerting only if a gap shows up.

### Architecture (4 new Railway services, one project, private networking)

```
                         ┌──────────────────────────────────────────┐
                         │  Railway project: credence-sports-baseball │
                         │                production                  │
   operator ──public──►  │  ┌────────────────┐                        │
                         │  │ dagster-       │   gRPC :4000 (private)  │
                         │  │  webserver     │──┐                      │
                         │  │ (dagit UI)     │  │                      │
                         │  └────────────────┘  ▼                      │
                         │  ┌────────────────┐ ┌──────────────────┐    │
                         │  │ dagster-daemon │─►│ dagster-codeloc  │    │
                         │  │ schedules /    │  │ gRPC code server │    │
                         │  │ sensors / queue│  │ + RUN subprocess │    │
                         │  │ / run-monitor  │  │   (the worker)   │    │
                         │  └───────┬────────┘  └────────┬─────────┘    │
                         │          │ run/event/sched     │ ops         │
                         │          ▼ storage (private)    │            │
                         │  ┌────────────────┐             │            │
                         │  │ dagster-postgres│            │            │
                         │  └────────────────┘             │            │
                         │                                 │            │
                         │   EXISTING (unchanged):         ▼            │
                         │   • dbt-runner  ◄── HTTP /run  (dbt stays OUT-of-process)
                         │   • Postgres (serving store: daily_picks/api_cache)  ◄── write_serving_store
                         │   • odds/weather/schedule capture crons, flaresolverr │
                         └──────────────────────────────────────────────────────┘
```

| Service | Role | Start command | Public? | Notes |
|---------|------|---------------|---------|-------|
| `dagster-codeloc` | gRPC code location **and the run worker** (DefaultRunLauncher executes runs as subprocesses here) | `dagster api grpc --host '[::]' --port 4000 --python-file pipeline/__init__.py --attribute defs --working-directory /app` | No (private only) | Heaviest service — holds loaded Definitions + runs ops. Binds `[::]` for dual-stack DNS. |
| `dagster-daemon` | scheduler + sensor daemon + run queue + run-monitoring | `dagster-daemon run --workspace /app/services/dagster/workspace.yaml` | No | **Serving-critical heartbeat.** If down, nothing fires. |
| `dagster-webserver` | dagit UI / GraphQL | `dagster-webserver --host 0.0.0.0 --port $PORT --workspace /app/services/dagster/workspace.yaml` | Yes (generated domain) | Operator console. Can sleep-to-zero when idle. |
| `dagster-postgres` | run/event/schedule storage | (Railway Postgres image) | No | **Separate** from the serving `Postgres`. Empty DB ⇒ all schedules/sensors STOPPED. |

**Image:** all three app services reuse the **repo-root `Dockerfile`** (full ML + Dagster
stack, `DAGSTER_HOME`, `PYTHONPATH=/app`, dbt manifest parsed at build) → **zero image
drift** vs the current Dagster+ build. They differ only by start command + `DAGSTER_HOME`
override + env. The Dockerfile `CMD` (`dagster-cloud agent run`) is always overridden.

**Run launcher = DefaultRunLauncher (subprocess on the code-server).** Execution cost ≈ $0
(no per-run container); cost is held RAM. **dbt never runs in-process** —
`pipeline/ops/_dbt_exec` posts to the existing `dbt-runner` (`DBT_RUNNER_URL`). This is the
load-hygiene rule that keeps the projection honest.

**Concurrency / safety (ported from A2.16 `deployment_settings.yaml`):** the
`QueuedRunCoordinator` in `dagster.yaml` caps each `concurrency_group`-tagged sensor job at
1 concurrent run and bounds total runs (`max_concurrent_runs: 5`); `run_monitoring` enforces
the 4h hard timeout.

### Why parallel standup is safe (no double-serve)

`grep -rn default_status pipeline/schedules pipeline/sensors` → **nothing**. With no
`default_status=RUNNING` in code, every schedule and sensor defaults to **STOPPED** on a
fresh instance. The new `dagster-postgres` starts empty ⇒ the OSS daemon boots with
everything **OFF**. Standing the stack up while Dagster+ keeps running fires **nothing**.
Cutover is an explicit, reversible toggle (Phase 3).

### Excluded jobs

`odds_snapshot_job` / `pregame_snapshot_job` (E11.6b) **do not exist** in `pipeline/`
(grep-confirmed; decommissioned 2026-06-16). Nothing to port or turn off. All 15 live jobs
load from `pipeline/__init__.py:defs` automatically — no per-job porting needed.

---

## Files in this directory

| File | Purpose |
|------|---------|
| `dagster.yaml` | OSS instance config (Postgres storage, QueuedRunCoordinator, DefaultRunLauncher, run-monitoring). `DAGSTER_HOME=/app/services/dagster` selects it. |
| `workspace.yaml` | Code location for daemon + webserver → `dagster-codeloc.railway.internal:4000`. |
| `railway.codeloc.toml` / `railway.daemon.toml` / `railway.webserver.toml` | Per-service Railway config (Dockerfile path + start command + restart policy). Set each service's **Config-as-code path** to the matching file. |

`dagster_home/dagster.yaml` (the Dagster+ agent config) and `dagster-cloud.yaml` are left
**untouched** — they are the rollback target until Phase 4.

---

## Env var matrix (wire via Railway **reference variables** — nothing copied/echoed)

All three app services get `DAGSTER_HOME` + `DAGSTER_PG_URL`. Only **`dagster-codeloc`**
strictly needs the full op env (it is the worker), but setting the same env on all three is
harmless and simplest. Use reference-variable syntax `${{ Service.VAR }}` so secrets stay
write-only inside Railway and never leave it.

| Var | All / codeloc | Value / source |
|-----|---------------|----------------|
| `DAGSTER_HOME` | all 3 | `/app/services/dagster` (literal; overrides the Dockerfile's `/app/dagster_home`) |
| `DAGSTER_PG_URL` | all 3 | `${{ dagster-postgres.DATABASE_URL }}` (the NEW Dagster PG — private) |
| `SNOWFLAKE_ACCOUNT/USER/ROLE/WAREHOUSE` | codeloc | `${{ dbt-runner.SNOWFLAKE_* }}` |
| `SNOWFLAKE_PRIVATE_KEY` | codeloc | `${{ dbt-runner.SNOWFLAKE_PRIVATE_KEY }}` (resources write it to `/tmp/...pem` on import) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | codeloc | `${{ dbt-runner.AWS_* }}` |
| `AWS_DEFAULT_REGION` | codeloc | `us-east-1` |
| `DBT_RUNNER_URL` | codeloc | `https://dbt-runner-production-8899.up.railway.app` (existing; keeps current behavior. Optional: switch to `http://dbt-runner.railway.internal:$PORT` once a fixed private port is set on dbt-runner) |
| `DBT_RUNNER_AUTH_TOKEN` | codeloc | `${{ dbt-runner.DBT_RUNNER_AUTH_TOKEN }}` |
| `DBT_STATE_BUCKET` / `DBT_STATE_PREFIX` / `TARGET_ENV` | codeloc | `${{ dbt-runner.* }}` (`baseball-betting-ml-artifacts` / `dbt_state` / `prod`) |
| `DATABASE_URL` | codeloc | `${{ Postgres.DATABASE_URL }}` — the **SERVING** PG (write_serving_store / write_api_cache). ⚠️ NOT the Dagster PG. |
| `ODDS_API_KEY` / `ODDS_API_STARTER_KEY` | codeloc | `${{ odds-api-data-feed.* }}` |
| `OPENWEATHERMAP_API_KEY` | codeloc | `${{ weather-capture.OPENWEATHERMAP_API_KEY }}` |
| `PARLAY_API_KEY` | codeloc | `${{ odds-api-data-feed.PARLAY_API_KEY }}` (if present there) |
| DynamoDB tables: `USER_BETS_TABLE`, `USERS_TABLE` | codeloc | from current Dagster+ secrets (settle_user_bets_op) |
| Email/alerts: `OWNER_EMAIL`, `OWNER_USER_ID`, `ADMIN_EMAILS`, `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `SENTRY_DSN` | codeloc | from current Dagster+ secrets (alert sensors / narratives) |
| Target db/schema overrides: `ODDS_TARGET_DATABASE/SCHEMA`, `SAVANT_TARGET_*`, `PARLAY_TARGET_*` | codeloc | only if currently overridden in Dagster+ (else code defaults apply) |

> **Operator action:** the canonical complete set is the current **Dagster Cloud →
> Deployment → Environment variables / Secrets** list. Export it and reconcile against this
> matrix. Reference-wire everything already present on a Railway sibling service; set the
> remainder (DynamoDB / Cognito / SES / Sentry) **write-only** on `dagster-codeloc`. A
> missing var only bites the specific op that reads it — validate per-job in Phase 2.

---

## CI/CD — how `pipeline/` changes ship to the self-host (replaces Dagster+ auto-build)

Under Dagster+ Serverless, pushing the repo rebuilt+shipped the code location automatically.
The self-host keeps that property via **Railway's native GitHub integration** — no separate
CI job to write:

- All three Dagster services are connected to `charlesclark2/fantasy_baseball` on branch
  **`main`** with Railway-managed deploy triggers (the GitHub App is already authorized — the
  `dbt-runner` deploys from this same repo). **A push/merge to `main` auto-rebuilds + redeploys.**
- **Watch patterns scope the rebuilds** so unrelated changes (e.g. `frontend/`) don't trigger a
  heavy image build:
  - `dagster-codeloc` (holds + runs the Definitions): `pipeline/**`, `betting_ml/**`,
    `scripts/**`, `dbt/**`, `services/dagster/**`, `Dockerfile`, `pyproject.toml`, `uv.lock`.
  - `dagster-daemon` / `dagster-webserver` (load the code **over gRPC** from codeloc — they
    don't execute pipeline logic): only `services/dagster/**`, `Dockerfile`, `pyproject.toml`,
    `uv.lock`. So a normal `pipeline/` change rebuilds **one** service (codeloc), not three.
- **Net flow for a Dagster change:** edit `pipeline/` → PR → merge to `main` → Railway rebuilds
  `dagster-codeloc` → new gRPC code server comes up with the new Definitions → daemon/webserver
  pick it up. No manual deploy step.
- **Caveat (matches Dagster+):** a codeloc redeploy restarts the code server, so a run in flight
  at deploy time is interrupted (Dagster will surface/retry it). Merge pipeline changes at a
  low-risk time, not mid-slate — same discipline as a Dagster+ code push.
- **dbt model changes** are picked up because the image runs `dbtf parse` at build, regenerating
  the manifest the `@dbt_assets` load from. (dbt **execution** still goes to the `dbt-runner`.)
- If you prefer a gated pipeline (tests before deploy), add a GitHub Actions job on `main` that
  runs the fast gate, then let Railway deploy on the same push — Railway's trigger and an Actions
  check are independent and compose.

---

## Provisioned state (Phase 1 standup — 2026-06-25, via Railway MCP)

Created in project `credence-sports-baseball` (`faa64ea4-…`), env `production` (`471a53d3-…`):

| Service | ID | State |
|---------|----|-------|
| `dagster-postgres` (image `postgres-ssl:16`, 10 GB vol at `/var/lib/postgresql/data`) | `8d0d8f86-…` | **Deployed + healthy** (listening dual-stack `:5432`; role/db `dagster`) |
| `dagster-codeloc` (repo `main`, config `railway.codeloc.toml`) | `8863cebe-…` | Created; **builds on first push of this config to `main`** |
| `dagster-daemon` (repo `main`, config `railway.daemon.toml`) | `35c12725-…` | Created; builds on push |
| `dagster-webserver` (repo `main`, config `railway.webserver.toml`, domain `dagster-webserver-production-ebf0.up.railway.app`) | `fe6cfc63-…` | Created; builds on push |

**Env already wired (reference variables — values never copied out of Railway):**
- all 3: `DAGSTER_HOME=/app/services/dagster`, `DAGSTER_PG_URL → dagster-postgres.DATABASE_URL`.
- `dagster-codeloc` also: `SNOWFLAKE_* / AWS_* / DBT_RUNNER_AUTH_TOKEN / DBT_STATE_* / TARGET_ENV →
  dbt-runner`, `DATABASE_URL → Postgres` (serving PG), `ODDS_API_KEY / ODDS_API_STARTER_KEY →
  odds-api-data-feed`, literal `AWS_DEFAULT_REGION=us-east-1`, `DBT_RUNNER_URL=<dbt-runner public>`.

**Operator must still set on `dagster-codeloc` (from Dagster Cloud → Secrets — not on any Railway
sibling; all WARN/ALERT-tier, so the morning serving path runs without them, but set before
enabling those sensors):** `OPENWEATHERMAP_API_KEY`, `PARLAY_API_KEY`, `USER_BETS_TABLE`,
`USERS_TABLE`, `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `OWNER_EMAIL`, `OWNER_USER_ID`,
`ADMIN_EMAILS`, `SENTRY_DSN`, and any `*_TARGET_DATABASE/SCHEMA` overrides currently set in
Dagster+. Reconcile the FULL list against the Dagster Cloud env/secrets export.

> **Benign log note:** `dagster-postgres` logs `role "postgres" does not exist` once at boot — the
> image's `collation-refresh` helper assumes the default `postgres` superuser; we use a
> least-privilege `dagster` role instead. PG is healthy and accepting connections. Ignore it.

> **gRPC bind:** `dagster-codeloc` binds `[::]:4000` so Railway's dual-stack private DNS (AAAA for
> `dagster-codeloc.railway.internal`) resolves. The PG already listens on `::` too. If a future
> Dagster version rejects `[::]`, fall back to `0.0.0.0` (Railway private net is dual-stack).

---

## Phase 1 — stand up in parallel (schedules OFF, no cutover)

Prereq: **Railway Pro active** (flat compute; $20/mo incl. $20 usage credit). ✅ confirmed
2026-06-25. The 4 services above are already created; the remaining steps are the **first build**
(needs this config on `main`) + the env top-up + health check.

1. **Provision `dagster-postgres`** (Railway Postgres) in the production environment.
2. **Create the 3 app services** from the GitHub repo (`charlesclark2/fantasy_baseball`,
   branch that contains this dir), each with its Config-as-code path set:
   - `dagster-codeloc` → `services/dagster/railway.codeloc.toml`
   - `dagster-daemon` → `services/dagster/railway.daemon.toml`
   - `dagster-webserver` → `services/dagster/railway.webserver.toml`
3. **Wire env** per the matrix (reference variables). Set `DAGSTER_HOME=/app/services/dagster`
   on all three; `DAGSTER_PG_URL` → the new PG; full op env on `dagster-codeloc`.
4. **Deploy order:** `dagster-postgres` → `dagster-codeloc` (wait healthy: log shows
   `Started Dagster code server` / `Serving on ... :4000`) → `dagster-daemon` (log shows the
   daemon heartbeat) → `dagster-webserver` (open the generated domain).
5. **Confirm in dagit:** the `baseball_betting` location loads green; **15 jobs / 9 schedules
   / 10 sensors** present; **every schedule + sensor shows STOPPED.** Do not toggle anything.

---

## Phase 2 — validate (still no cutover)

On the self-hosted dagit, **manually launch** (Launchpad) and confirm parity vs Dagster+:

- [ ] `snowflake_check_job` → green (env/connectivity sanity first).
- [ ] `daily_ingestion_job` → completes; predictions land; `write_serving_store` /
      `write_api_cache` write to the **serving** PG (spot-check `daily_picks` row count + a
      pick vs what Dagster+ produced the same morning).
- [ ] `lineup_monitor_job` → re-scores on confirmed lineups.
- [ ] `statcast_catchup_job` → ingests + rebuilds + re-scores.
- [ ] dbt steps route to the **dbt-runner** (check dbt-runner logs show the POST `/run`), not
      an in-process dbt.
- [ ] Failure tiers behave: force a peripheral failure (e.g. a WARN-tier ingest) → op
      succeeds with a logged warning; confirm a HALT-tier failure fails the run.
- [ ] **Sensor/schedule dry-run:** toggle ONE harmless sensor (e.g. `statcast_freshness_sensor`)
      ON briefly, confirm it ticks/evaluates, then toggle OFF. Do **not** enable serving
      schedules yet (Dagster+ still owns them).
- [ ] Compare a self-hosted run's structured logs/asset materializations to the Dagster+ run.

Let it sit idle 1–2 days (daemon + code-server healthy, schedules OFF) to confirm stability
and **measure real RAM** (Railway metrics) before cutover.

---

## Phase 3 — cutover (low-risk time — NOT mid-slate; ideally overnight after the last game settles)

**Atomic toggle, one direction at a time. Never both ON.**

1. In **Dagster+**: turn **OFF** every schedule and sensor (Deployment → Automation → stop
   all). Confirm none are running.
2. In **self-hosted dagit**: turn **ON** the same set — the 9 live schedules + the 10 sensors:
   `daily_ingestion_schedule`, `odds_clv_rebuild_schedule`, `historical_matches_weekly_schedule`,
   `weekly_player_profiles_schedule`, `weekly_clv_monitoring_schedule`, `weekly_ml_schedule`,
   `weekly_meta_model_schedule`, `magnitude_monitor_schedule` (+ the intraday weather/schedule
   schedules are **deprecated** — they run on Railway crons; leave OFF, matching today); and
   all sensors (`odds_current_rebuild_sensor`, `statcast_freshness_sensor`,
   `lineup_monitor_sensor`, `morning_watchdog_sensor`, `pregame_alert_sensor`,
   `clv_alert_sensor`, `model_health_alert_sensor`, `conviction_pick_alert_sensor`,
   `odds_freshness_alert_sensor`, `schedule_freshness_alert_sensor`).
   → Match exactly what was ON in Dagster+ before step 1.
3. **Monitor one full daily cycle** end-to-end on self-hosted: morning `daily_ingestion` →
   intraday `lineup_monitor` → `statcast_catchup` → `write_serving_store`. Verify the picks
   users see are fresh and correct.

### 🔁 Rollback (instant)

If anything misbehaves: in **self-hosted dagit** stop ALL schedules/sensors, then in
**Dagster+** re-enable them (reverse of steps 1–2). Dagster+ image/secrets are still intact,
so it resumes immediately. Investigate offline. (Keep Dagster+ paid + intact through Phase 4.)

---

## Phase 4 — decommission (after a clean multi-day window)

Only once self-hosted has served several full daily cycles cleanly:

1. Dagster+ → confirm all schedules/sensors OFF (already, from cutover).
2. Delete the Dagster+ **deployment** (Serverless) / stop the agent → **stops the bill.**
3. Confirm $0 Dagster+ going forward (next invoice).
4. Repo cleanup follow-on (separate small PR): drop `dagster-cloud` from the image, remove
   `dagster_home/` + `dagster-cloud.yaml`, and the `DAGSTER_CLOUD_*` env. Keep until the
   invoice confirms $0 so rollback stays possible.

---

## Cost — before / after (validate by measuring; AC)

| | Before (Dagster+ Serverless) | After (self-hosted on Railway) |
|---|---|---|
| Orchestration | ~$325/mo true-monthly ($139 was the Jun 18–30 partial cycle; $139÷13×30 ≈ $325, growing with the season) | ≈ **$0** Dagster+ |
| Railway (existing: dbt-runner + crons + serving PG) | ~$23/mo (~1.9 GB RAM avg) | ~$23/mo (unchanged) |
| Railway (new: codeloc + daemon + webserver + dagster-PG, ~1.5 GB RAM 24/7) | — | ≈ **+$27/mo** |
| **Total infra** | **~$345/mo** | **≈ $50/mo** |
| **Saving** | | **≈ $275/mo (~85%)** |

Cost is dominated by **held RAM** (RAM $10.14/GB-mo, CPU $20.29/vCPU-mo; runs are short ⇒
execution ≈ $0; private networking free). Keep the services lean; optionally sleep the
webserver when idle. **AC — operator, after a few days live:** read Railway metrics for the 4
new services (`MEMORY_USAGE_GB` avg) and report the **actual** added $/mo vs the ~$27
projection and the ~$50 new total, against the $139 baseline.
