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
