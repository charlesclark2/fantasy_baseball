# EC2 Box Operations — session reference

**Read this before any session that touches the box (pipeline / serving / ingestion / dbt / deploy).** It consolidates the operational mechanics that sessions kept re-discovering. Authoritative as of 2026-06-30; if a file contradicts this doc, the file wins — and fix the doc.

The "box" = a self-hosted **Dagster OSS** orchestrator on a single **AWS EC2** instance, run via **Docker Compose** under `services/dagster/aws/`. It replaced Railway (INC-16). It is the SOLE live orchestrator.

> 🚨 Pair this with the **"RECURRING LANDMINES"** block in `CLAUDE.md` (inline Snowflake key, boto3 instance-role, DuckDB region, binary-parquet-timestamp, VALUE:-case, box-aware memory, the runtime gate). This doc is the "how it works"; CLAUDE.md is the "what bites you."

---

## 1. Box facts (`infrastructure/aws_resources.md`)
| | |
|---|---|
| Instance ID | `i-07594af1679f81c38` |
| Type | `r6g.large` (arm64, 2 vCPU, **16 GB RAM**) — resized from `t4g.medium` (4 GB) on INC-22 after DuckDB OOM-killed the host |
| Elastic IP | `100.57.225.242` (stable — FanGraphs `cf_clearance` is bound to this IP) |
| Region | **us-east-1** (the instance). ⚠️ but DuckDB S3 reads of `baseball-betting-ml-artifacts` need **`us-east-2`** explicitly |
| OS | Amazon Linux 2023 arm64 |
| IAM | role `credence-dagster-ec2-role` — **no static AWS keys on the box**; S3/DynamoDB via the instance role (`credential_chain`); `AWS_ACCESS_KEY_ID` is UNSET |
| Public dagit | `https://dagster.credencesports.com` (Caddy HTTPS + basic-auth) |
| Cost | ~$73/mo |

**Access:** prefer **SSM** `aws ssm start-session --target i-07594af1679f81c38` (no SSH needed). SSH fallback: `ssh -i ~/.ssh/credence-dagster-key.pem ec2-user@100.57.225.242`. Repo on the box is at `~/app`.

---

## 2. Docker Compose layout (`services/dagster/aws/docker-compose.yml`)
Six core services on the `credence-dagster` bridge network:

| Service | Role |
|---|---|
| `dagster-postgres` | Dagster run/event/schedule metadata ONLY (not serving cache; regenerable) |
| `dagster-codeloc` | gRPC code server + run worker; needs the full op env (`env_file: .env`) incl. `DBT_RUNNER_URL` + `FLARESOLVERR_URL` |
| `dagster-daemon` | scheduler + sensors + run queue + heartbeat |
| `dagster-webserver` | dagit UI, bound `127.0.0.1:3000` (public via Caddy only) |
| `dbt-runner` | out-of-process dbt execution at `http://dbt-runner:8080` (see §4) |
| `flaresolverr` | FanGraphs Cloudflare solver at `http://flaresolverr:8191/v1` (see §5) |
| `caddy` | HTTPS reverse-proxy + basic-auth for dagit (Let's Encrypt) |

**Run a script in a container (the common one):**
```bash
docker compose -f services/dagster/aws/docker-compose.yml exec dagster-codeloc \
  python scripts/<script>.py <args>
```
`-T` (no TTY) for non-interactive/cron contexts; add `-e AWS_DEFAULT_REGION=us-east-2` when the script does a DuckDB S3 read.

**Bring up / rebuild:**
```bash
docker compose -f services/dagster/aws/docker-compose.yml up -d --build
docker compose -f services/dagster/aws/docker-compose.yml --profile capture build
```

**Capture profile** = run-once cron images (NOT started by `up`): `odds-capture`, `schedule-capture`, `derivative-capture`, `weather-capture`. Fired by host cron (see §3), invoked `... run --rm <svc>`.

---

## 3. Host crontab / captures (`services/dagster/aws/capture.crontab`)
The intraday data captures run as **host cron**, not Dagster schedules (they were re-homed off Dagster+ to avoid the metered run-minutes).

| Schedule | Job | Tier |
|---|---|---|
| `*/30` | `odds-capture` → `mlb_odds_raw` (h2h/totals, all books) | **HALT** (serving-critical odds) |
| `*/30` | `schedule-capture` → intraday schedule + lineup-staging dbt rebuild (self-guards 14:00–03:00 UTC) | WARN |
| `*/30` | `derivative-capture` → derivative odds (team_totals/F5/…) | WARN |
| `0 * * * *` | `weather-capture` (self-guards 10:00–02:00 UTC) | WARN |
| `0 13` | MLB player-prop forward catch-up (`backfill_multisport_props_to_s3.py … --player-props-only`) | WARN |
| `30 12,17` | `check_data_freshness.py` (pages via SNS) | WARN |
| `*/5` | `healthcheck.sh` (core containers up; 1h cooldown) | ALERT |

Logs: `/home/ec2-user/capture-cron.log`. Install: `crontab ~/app/services/dagster/aws/capture.crontab` (deploy.sh reinstalls it — see §6). ⚠️ **INC-23 (2026-06-30)** hardens this to reconcile on EVERY deploy + ALERT if the odds-capture line is missing (a box resize/reprovision had silently dropped it → 5.6h stale odds). ⚠️ Note: an **intraday schedule-capture also exists inside Dagster** now (Option 2, INC-22, gated `SCHEDULE_LAKEHOUSE_INTRADAY=1`) because the lean host-cron only refreshed Snowflake views, never the parquet prod serves — don't double-run the two.

---

## 4. dbt on the box (out-of-process — MANDATORY)
**Never run `dbtf` in-process inside a Dagster op.** All dbt goes through `pipeline/ops/_dbt_exec._run_dbt`, which POSTs to the `dbt-runner` service (`DBT_RUNNER_URL=http://dbt-runner:8080`), polls `/status`, 30-min hard timeout, single-tenant (409 = busy → retry). If `DBT_RUNNER_URL` is unset it falls back to a local `dbtf` subprocess (dev/CI only) and that skip must be LOUD (INC-5/ALERT-tier).

**Local validation a session must run before handoff:**
```bash
uv run pytest -m "not slow" -n auto      # fast gate (~15s)
uv run pytest -m slow -n auto            # slow gate (~95s) if you touched @slow tests
scripts/dbt_state.sh build --select state:modified+ --target dev   # ⬅ use the wrapper
dbtf compile                              # full compile check
```
⚠️ **Always use `scripts/dbt_state.sh` for `state:modified+`** — plain `dbtf … state:modified+` without `--state` makes fusion 404 against dbt Platform (we're self-managed) and the selection breaks (E11.16). The wrapper injects `--state dbt/state --defer`, mirroring CI.

---

## 5. Flaresolverr (FanGraphs Cloudflare)
FanGraphs sits behind a Cloudflare JS challenge → direct requests 403. `flaresolverr` runs headless Chrome to solve it. Its `cf_clearance` is **bound to the box's egress IP + TLS fingerprint**, so it MUST be co-located on the box (this is why the EIP is stable). Scripts reach it via `FLARESOLVERR_URL=http://flaresolverr:8191/v1`; client = `scripts/utils/fangraphs_client.py` (`fetch_leaderboard`/`fetch_projections`, sends the full URL with `cmd: request.get`). FanGraphs ingests are **WARN-tier** (`pipeline/ops/daily_ingestion_ops.py`) — a Cloudflare/flaresolverr outage degrades quietly (Stuff+ is a nullable LEFT JOIN with a Statcast fallback). Validate: `... exec dagster-codeloc python services/dagster/aws/validate_flaresolverr.py`.

---

## 6. Deploy / CD (`services/dagster/aws/deploy.sh` + `.github/workflows/orchestration_cd.yml`)
CD = GitHub Actions OIDC → SSM RunCommand → `deploy.sh` on the box (auto on merge to main for `dagster/**`/`scripts/**`; or run manually via SSM). Flow, atomic with auto-rollback:
1. `git pull origin main` (FIRST — so env-parity validates the new env)
2. env-parity check vs `env.required` (every key present + non-empty)
3. snapshot images → `:rollback`
4. graceful drain (≤600s for in-flight runs)
5. **`docker compose up -d --build` + `--profile capture build`**
6. reconcile host crontab (capture.crontab)
7. verify (daemon up / defs import / dbt-runner health / PEM materialized / IMDS hop-2) → **rollback on any failure**

🚨 **BAKED-IMAGE DRIFT (the recurring gotcha):** a `git pull` updates the working tree but the running containers keep the OLD image — code is COPY'd in at build. **Only `up -d --build` ships new code.** A "successful" deploy without `--build` silently runs stale code.

🟥 **The merge bar for box code is NOT CI-green** (CI mocks all IO). For pipeline / serving / writers / sensors / date-tz / boto3 / DuckDB-on-box changes: **CI green AND the relevant op actually RAN once on the box** (a scoped run is fine — skip the stable W1 pitch rebuild, run the targeted chain). See CLAUDE.md "RUNTIME GATE".

---

## 7. Snowflake private key on the box (INLINE, not a file)
Compose `env_file:` can't carry real PEM newlines, so the key arrives as **`SNOWFLAKE_PRIVATE_KEY`** (raw / base64 / `\n`-escaped), NOT a file. The shared resolver (in `pipeline/resources/__init__.py`, `scripts/utils/snowflake_loader.py`, `betting_ml/utils/data_loader.py`, `scripts/ingest_statsapi.py`) resolves in order: **`SNOWFLAKE_PRIVATE_KEY_PATH` if the file exists → inline `SNOWFLAKE_PRIVATE_KEY` (normalized + written to `/tmp/snowflake_rsa_key.pem` 0600) → `SNOWFLAKE_PASSWORD`**. ⚠️ Older code that reads `SNOWFLAKE_PRIVATE_KEY_PATH` raw FAILS on the box — use the resolver pattern, or stay pure DuckDB/S3.

---

## 8. DuckDB memory on the box (box-aware)
`scripts/run_w1_lakehouse.py::_safe_memory_limit_gb()` = `clamp(0.6 × physical_RAM, 2, 11)` (≈9.6 GB on the 16 GB box). **Never hardcode `memory_limit` above physical RAM** — a hardcoded 11 GB on the old 4 GB box never spilled → kernel OOM-killed the HOST incl. Dagster (INC-22). Heavy flatten tiers also set `threads=2` to keep the working set spillable.

---

## 9. Quick "how do I…" index
- **Run a one-off script on the box:** `docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc python scripts/X.py …` (add `-e AWS_DEFAULT_REGION=us-east-2` for DuckDB S3).
- **Re-serve a specific date:** `… exec dagster-codeloc python scripts/write_serving_store.py --date YYYY-MM-DD --picks …`.
- **Debug a downstream (feature/serving) change fast:** SKIP `run_w1_lakehouse`'s full W1 pitch rebuild (~10 min); run only the targeted chain (`--w8a-only` etc.) — safe per the INC-21 recovery.
- **Run/validate dbt:** `scripts/dbt_state.sh build --select state:modified+ --target dev` locally; on the box it goes through `dbt-runner`.
- **Check the box / containers:** SSM in → `docker compose -f ~/app/services/dagster/aws/docker-compose.yml ps`; logs at `~/capture-cron.log`.
- **Ship a code change to the box:** merge to main (CD) OR SSM in + `deploy.sh` — and remember it needs `--build`.

---

## 10. Flag / schedule / sensor INTENDED-STATE table (E11.23 — the cutover-runtime-landmine cure)
The E11.1 cutover left a class of RUNTIME failures CI can't see (it mocks all IO): **intraday refresh jobs shipped GATED-OFF** and **serving-critical sensors/schedules that boot STOPPED** → they silently NEVER RUN (odds froze 3 days with NO alert; the lineup monitor was dead 2 days; K-page empty). This section is the source of truth for what MUST be on. Two structural cures back it up:
- **Self-start in code:** every serving-critical sensor + the primary schedules now declare `default_status=RUNNING`, so they auto-start on the box and after any Dagster-DB reset / re-host (the INC-16 class) instead of booting STOPPED.
- **A heartbeat detector:** `check_monitors_healthy_op` runs inside every `daily_ingestion_job` and ALARMS (email CRITICAL, ALERT-tier — never HALT) if a critical sensor/schedule is manually STOPPED or a permanently-on intraday flag is unset. Its critical sets + required flags mirror the tables below — **extend both together.**

> 🟥 **RUNTIME GATE:** the "Intended" column is the target; the box's ACTUAL state is only verifiable ON the box. After any change here, confirm on the box (`docker compose … exec -T dagster-codeloc env | grep <FLAG>`, and Dagit → Sensors/Schedules) — CI cannot see it.

### 10a. Serving-critical env flags — must be permanently `1` on the box
These are enforced by `check_monitors_healthy_op` (an unset one = a silently-gated-off refresh):

| Flag | Intended | Why (incident) |
|---|---|---|
| `SCHEDULE_LAKEHOUSE_INTRADAY` | **`1`** | INC-22: the in-Dagster intraday schedule/game-state capture that refreshes the S3 parquet prod serves. Off → game-state stuck in "Preview", stale lineups. Also START `intraday_schedule_capture_daytime/_overnight` AND disable the lean host-cron `schedule-capture` (don't double-ingest). |
| `LINEUP_INTRADAY_S3_REBUILD` | **`1`** | The intraday lineup-confirm re-score reaches the S3 W8b feature parquet (the 824819 loop). Off → a confirmed lineup never re-scores. |
| `W8A_LAKEHOUSE_S3` | **`1`** | Feature layer + EB posteriors served from S3 (cut over 2026-06-30). |
| `W8B_LAKEHOUSE_S3` | **`1`** | Serving pregame aggregator served from S3 (cut over 2026-06-30). |
| `LINEUP_MONITOR_S3` | **`1`** | E11.20 phase-2a: lineup-monitor detection tick reads S3+DynamoDB, not Snowflake (kills the ~10-min COMPUTE_WH wake). Flipped + converged 2026-07-20. Off → detection wakes the warehouse every tick. ⚠️ Rollback (a soak regression) = set `0` AND remove from the enforced set, else this heartbeat false-pages. |

### 10b. Other cutover / gating flags — intended state (NOT auto-enforced; confirm per cutover)
| Flag | Intended | Note |
|---|---|---|
| `W6_LAKEHOUSE_INTRADAY` | `1` **post-cutover** | Gates the intraday MART rebuild (served-price freshness). The RAW odds S3 mirror export is UNGATED (always runs), so odds don't freeze even with this off; flip to `1` once the W6 external tables exist + parity is validated. NOT in the enforced set (avoids false pages pre-cutover). |
| `W7A_LAKEHOUSE_S3`, `W7B_LAKEHOUSE_S3` | `1` | Matchup consumers + prediction path off SF (cut over). `*_PARALLEL` variants are validation-only. |
| `W9_LAKEHOUSE_S3` | `0` | W9 signal-store SF writes STAY; only the output-mirror ships. `W9_LAKEHOUSE_S3_READS` follows the W-plan. |
| `ODDS_COVERAGE_STRICT` | `0` → `1` | ALERT today; flip to `1` (HALT on a current-slate odds freeze) once confirmed it doesn't false-fire. |
| `FEATURE_COVERAGE_STRICT` | `0` → `1` | ALERT today; flip to `1` after the W11b umpire cutover restores the block. |
| `PROPS_DAILY_INGEST` | `0` | Redundant with the host-cron `0 13` props line — enable EXACTLY ONE (else double-pay Odds API credits). |
| `W11_RAW_WRITE_MODE` / `LAKEHOUSE_RAW_WRITE_MODE` | per-cutover (`snowflake`→`both`→`s3`) | Tier-A raw writers' dual-write mode; advance per the W11 cutover, not blindly. |
| `W11_W4W5_NIGHTLY`, `W11B_UMPIRE_NIGHTLY`, `W11C_WEATHER_NIGHTLY`, `W11D_PUBLIC_BETTING_NIGHTLY`, `W11_W3PRE_DAILY`, `W11_BATTER_PITCHES_SF_RETIRED` | per-cutover | Nightly-rebuild / SF-retire gates; each flips with its wave's box cutover. |
| `W11TX_TRANSACTIONS_NIGHTLY` | `1` **once cut over** | INC-32 hygiene: gates the nightly `--w11tx-only` rebuild + `--w11tx` ext refresh that keeps `lakehouse_ext.stg_statsapi_transactions` (the injury-status chain) fresh from the live raw mirror. MUST be `1` before the SF raw `player_transactions` is dropped, else the ext table FREEZES on drop (`decommission_w11_abcd_drop.py`). Flip on only after `W11_RAW_WRITE_MODE=both\|s3` + the ext table exists + a box-validated `--w11tx-only` run (per-ROW ext fetch = the runtime gate). |

### 10c. Sensors — ALL self-start (`default_status=RUNNING`); the critical set is heartbeat-checked
All 11 sensors carry `default_status=RUNNING`. `check_monitors_healthy_op` alarms if any of these is manually STOPPED: `run_failure_alert_sensor`, `odds_current_rebuild_sensor`, `odds_freshness_alert_sensor`, `schedule_freshness_alert_sensor`, `statcast_freshness_sensor`, `lineup_monitor_sensor`, `pregame_alert_sensor`, `conviction_pick_alert_sensor`, `morning_watchdog_sensor`, `clv_alert_sensor`, `model_health_alert_sensor`.

**INC-32 (2026-07-18) — tick-STALENESS heartbeat:** the STOPPED check above is blind to a sensor that is still nominally RUNNING but whose evaluations have *stalled* (the sensor-daemon wedged mid-slate — 7/17, all evals stopped ~21:30Z after `lineup_monitor.py` hung the daemon thread). `check_monitors_healthy_op` now ALSO pages if any critical sensor's most-recent tick is older than `SENSOR_TICK_STALE_SECONDS` (default 60 min) — the daemon ticks every RUNNING sensor continuously (even a SkipReason is a tick), so a stale tick = a wedged daemon. Structural cure: every sensor subprocess (op AND the `_evaluate_lineup_monitor` sensor-eval path) now has a hard subprocess timeout so a wedge can't block the daemon in the first place.

### 10d. Schedules — intended boot state
| Schedule | Intended | Note |
|---|---|---|
| `daily_ingestion_job_schedule` | **RUNNING** (self-start) | the primary serving pipeline; heartbeat-checked. |
| `odds_clv_rebuild_daily` | **RUNNING** (self-start) | daily CLV / line-movement rebuild; heartbeat-checked. |
| `lineup_monitor_schedule_daytime` / `_overnight` | **STOPPED** (manual fallback) | INC-32: DEMOTED 2026-07-18. The `lineup_monitor_sensor` (10-min, un-wedgeable, staleness-heartbeat-checked) is now the SOLE driver of `lineup_monitor_job`; running these too double-fired the job (check-then-act race → 2 runs per confirmed lineup → doubled dbt-runner 409 contention). NOT critical / not heartbeat-checked — a STOPPED one is expected. Re-enabling one reintroduces the double-fire. |
| `intraday_schedule_capture_daytime` / `_overnight` | operator-gated STOPPED | START only WITH `SCHEDULE_LAKEHOUSE_INTRADAY=1` AND after disabling the lean host-cron `schedule-capture` (double-ingest). NOT self-start / not heartbeat-checked. |
| `intraday_public_betting_daytime` / `_overnight` | operator-gated STOPPED | START only with `W11_RAW_WRITE_MODE=s3\|both` (paid ActionNetwork capture opt-in). |
| `weekly_ml_job_schedule`, `weekly_meta_model_job_schedule`, `weekly_player_profiles_job_schedule`, `clv_monitoring_job_schedule`, `magnitude_monitor_job_schedule` | STOPPED (optional) | heavy/optional; operator toggles as needed. |
| `w1_parity_schedule` | STOPPED (one-shot legacy) | fires only on its pinned parity date; leave off. |
| `sports_ncaaf_dbt_schedule` / `sports_nfl_dbt_schedule` | **STOPPED until the 2026 season opens** — then **RUNNING** | NCAAF-P1.1. Game-day-GATED rebuilds of the `sports_dbt` NCAAF/NFL marts (dbt-duckdb; no warehouse, no API credits). Cron fires daily inside the season months (NCAAF Aug–Jan, NFL Sep–Feb) at 11:00 PT and `betting_ml/monitoring/sports_game_day_gate.py` SKIPs when no game was played the prior day — so ~2–3 runs/week, not 7. ⛔ Shipped STOPPED on purpose: there are no live football games until **Aug 2026 (NCAAF) / Sep 2026 (NFL)**. ⏰ **ACTION: turn BOTH ON in Dagit before the openers** — while STOPPED, the NCAAF/NFL marts (incl. P0.4 roster-continuity + P0.5 coaching-change) only rebuild when an operator launches the job by hand, which is the "silently rot" state P1.1 exists to end. NOT heartbeat-checked (nothing serving-critical depends on them yet); revisit if a live NCAAF/NFL serving surface ships. The gate FAILS OPEN — an unreadable/stale mart rebuilds rather than skipping. |
