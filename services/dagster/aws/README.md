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

## Next phases (not in P1)

- **P2** — serving cache → DynamoDB (drop the serving `DATABASE_URL`; add a
  DynamoDB statement to the IAM policy in `provision-ec2.sh`).
- **P3** — capture crons (odds/schedule/derivative) → Lambda + EventBridge.
- **P4** — enable schedules, run a full daily cycle, cancel Railway.
