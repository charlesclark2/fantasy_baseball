# INC-16-P1 — AWS re-host of the Dagster orchestration stack

Re-homes the Railway orchestration (down after the Railway workspace was
restricted — see `../../../quant_sports_intel_models/baseball/edge_program/INC16_AWS_REHOST_RECOVERY.md`)
onto **one EC2 box** running Docker Compose. This is a **re-deploy** of the
existing OSS Dagster config (`../dagster.yaml`, ported start commands), not a
rebuild. The Railway `../railway.*.toml` units and Dagster+ Cloud stay intact as
rollback until Phase 4.

## What runs on the box (one `t4g.medium`, 4 GB, arm64)

| Container | Role | Reached at |
|-----------|------|-----------|
| `dagster-postgres` | Dagster's **own** run/event/schedule storage (metadata only — NOT the serving cache, which → DynamoDB in P2) | `dagster-postgres:5432` (internal) |
| `dagster-codeloc` | gRPC code server **+ run worker** (DefaultRunLauncher subprocesses) | `dagster-codeloc:4000` (internal) |
| `dagster-daemon` | scheduler + sensors + run queue + run-monitoring (heartbeat) | — |
| `dagster-webserver` | dagit UI / GraphQL | `:3000` (operator IP only) |
| `dbt-runner` | out-of-process dbt (`pipeline/ops/_dbt_exec` POSTs `/run`) | `dbt-runner:8080` (internal) |
| `flaresolverr` | FanGraphs Cloudflare solver (~1 GB Chromium) | `flaresolverr:8191` (internal) |

**🔑 Why flaresolverr lives here:** FanGraphs' `cf_clearance` cookie is IP-bound.
All containers NAT out through the instance's **Elastic IP**, so flaresolverr's
headless-Chrome requests share the agent's egress IP — exactly what Railway's
co-location gave us. The EIP keeps that IP stable across reboots.

**🔒 Schedules are OFF on standup.** `dagster-postgres` starts empty and nothing
in `pipeline/` sets `default_status=RUNNING`, so every schedule + sensor boots
STOPPED. Bringing the stack up fires nothing. Turning them on is INC-16-P4.

**Cost traps avoided:** public subnet + **S3 gateway VPC endpoint** (no NAT
Gateway, ~$32/mo saved); single small EC2 (no Aurora / MWAA). Target ~$15–35/mo.

## Provision (operator — spends money, creates real infra)

```bash
# awscli v2 configured; an existing EC2 key pair named $KEY_NAME
REGION=us-east-1 KEY_NAME=my-key ./provision-ec2.sh
```

Creates the SG (SSH 22 + dagit 3000 from your IP only), the S3 gateway endpoint,
an IAM instance profile (S3 access — no static keys on the box), the t4g.medium
running `cloud-init.sh` (Docker + compose + git + a 4 GB swapfile so the heavy
image build doesn't OOM), and an Elastic IP. Prints the SSH command + next steps.

## Bring up the stack (on the box, after cloud-init ~2 min)

```bash
git clone <repo> ~/app && cd ~/app
cp services/dagster/aws/.env.example services/dagster/aws/.env   # fill from the
chmod 600 services/dagster/aws/.env                              # Dagster Cloud secrets export
docker compose -f services/dagster/aws/docker-compose.yml up -d --build
```

The first build is heavy (PyMC/CatBoost/etc.); the swapfile from cloud-init
covers it. If it still OOMs, build the images on a larger box and push to ECR,
then `up -d` (pull only).

## Health checks (the AC)

```bash
C="docker compose -f services/dagster/aws/docker-compose.yml"
$C ps                                              # all 6 Up / healthy
$C logs dagster-codeloc | grep -i "Started Dagster code server\|Serving on"   # gRPC up
$C logs dagster-daemon  | grep -i "daemon"          # heartbeat
$C logs dbt-runner | grep -i "starting on"          # dbt-runner up
$C exec dagster-codeloc curl -fsS http://dbt-runner:8080/health   # {"ok":true}
# flaresolverr healthy + IP-sharing (the FanGraphs proof):
$C exec dagster-codeloc python services/dagster/aws/validate_flaresolverr.py
#   → "OK: Cloudflare clearance obtained — pulled N hitting-leaderboard rows."
```

Then open dagit: SG allows `:3000` from your IP → `http://<elastic-ip>:3000`.
Confirm the `baseball_betting` location loads green with **15 jobs / 9 schedules
/ 10 sensors**, and **every schedule + sensor shows STOPPED**. Do not toggle any.

> **Hardening option:** instead of exposing `:3000`, drop the SG rule for 3000,
> change the compose port to `127.0.0.1:3000:3000`, and tunnel:
> `ssh -L 3000:localhost:3000 ec2-user@<elastic-ip>` → browse `localhost:3000`.

## CI/CD — shipping `pipeline/` changes to this box

Railway's auto-deploy-on-push is gone. Until a GitHub Actions deploy job is added,
a pipeline change goes live by SSHing in and:

```bash
cd ~/app && git pull
docker compose -f services/dagster/aws/docker-compose.yml up -d --build dagster-codeloc
```

(rebuilds only the code server; the daemon/webserver load it over gRPC). A codeloc
restart interrupts an in-flight run — do it at a low-risk time, not mid-slate.

## FanGraphs robustness (E11.7 gap closed in this story)

`ingest_fangraphs_stuff_plus` + `ingest_fangraphs_hitting_leaderboard` are now
**WARN-tier** (`pipeline/ops/daily_ingestion_ops.py`): a flaresolverr/FanGraphs
outage logs a warning and the op succeeds, so the daily job degrades to the
Statcast fallback instead of failing. Recorded in the CLAUDE.md op→tier map.

## Rollback / decommission

Dagster+ Cloud + the Railway `railway.*.toml` configs are untouched — they remain
the rollback target. Decommission only after AWS serves a clean multi-day window
(INC-16-P4).

## Capture crons (INC-16-P3 — EC2 host-cron)

The 4 Railway capture crons are re-homed onto **this box** as run-once images under
the `capture` profile in `docker-compose.yml`, fired by the host crontab
`capture.crontab`. (Operator decision 2026-06-26: EC2-host-cron now; rearchitect to
Lambda + EventBridge when data sources / ingest frequency grow — the images are
already standalone, so that lift is mechanical.)

| Service | Script | Cadence (UTC) | Tier |
|---------|--------|---------------|------|
| `odds-capture` | `odds_api_ingestion.py odds` → `mlb_odds_raw` | `*/30` | live-price feed |
| `schedule-capture` | `ingest_statsapi.py schedule` + `trigger_dbt.py` | `*/30` (self-guards 14-03 UTC) | dbt trigger = ALERT-on-skip |
| `derivative-capture` | `derivative_odds_backfill.py capture` | `*/30` | EVAL/CLV-only |
| `weather-capture` | `ingest_weather.py` (T-24/6/3/1h + observed) | hourly (self-guards 10-02 UTC) | WARN |

**Key-handling fix (same root cause as the P2 Snowflake-key bug):** all 4 capture
entrypoints materialized the PEM with `printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY"` —
which breaks on a single-line `\n`-escaped/base64 env value. Fixed to normalize
(`\n`-escaped checked first, then base64, raw PEM passthrough). Verify after build:
`docker compose ... run --rm odds-capture` should land rows in `mlb_odds_raw`.

### Deploy (on the box)
```bash
cd ~/app && git pull origin dev
# build the 4 capture images once:
docker compose -f services/dagster/aws/docker-compose.yml --profile capture build
# smoke-test one (should connect to Snowflake + write):
docker compose -f services/dagster/aws/docker-compose.yml run --rm odds-capture
# AL2023 minimal ships NO cron — install + start the daemon first:
sudo dnf install -y cronie && sudo systemctl enable --now crond
# install the schedule:
crontab services/dagster/aws/capture.crontab && crontab -l
tail -f ~/capture-cron.log   # watch a couple of fires
```

> **`crontab: command not found` on a fresh box** → AL2023 has no cron by default.
> Run the `dnf install -y cronie && systemctl enable --now crond` line above, then
> re-run the `crontab …` install. cron inherits `ec2-user`'s `docker` group, so the
> `docker compose run` lines work; the crontab's `PATH` covers `docker`'s location.

### Odds backfill (P3 task 2 — run at deploy with the live gap)
Compute the gap (last capture → now): `MAX(captured_at)` in
`baseball_data.oddsapi.mlb_odds_raw`. The Odds API's **historical** endpoint (paid
tier, `?date=<ISO>`) can retrieve missed snapshots — check
`odds_api_ingestion.py --help` for a historical mode; if available, pull the gap
window for today's games. If intraday history isn't retrievable, **log the gap
explicitly** (today's CLV / line-movement features are holed) and resume forward
capture — pick *side* is unaffected (model's), only *prices* were stale.

### Served-price freshness (P3 task 3)
Restoring capture makes **raw** odds (`mlb_odds_raw`) current. **Displayed** prices
read `mart_odds_outcomes`, which refreshes only when the odds marts rebuild
(`dbt run --select stg_oddsapi_odds mart_odds_outcomes`) — driven by the
`odds_current_rebuild_sensor`, **enabled at P4**. To refresh served prices *before*
P4, uncomment the optional chain at the bottom of `capture.crontab` (capture → odds-
mart rebuild via dbt-runner → `write_serving_store`); remove it at P4 when the sensor
takes over.

## Next phases

- **P4** — dev→main cutover: enable AWS dagit schedules + sensors (incl.
  `odds_current_rebuild_sensor`) while turning Dagster+ OFF in the same window,
  run a full daily cycle, cancel Railway, decommission Dagster+ (~$275/mo saved).
