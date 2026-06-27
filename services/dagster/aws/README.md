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

## INC-16-P4 — cutover, HTTPS dagit, SSM, decommission Railway

P4 promotes the box from `dev`→`main`, flips orchestration ownership Dagster+ Cloud →
this box, fronts dagit with HTTPS+auth, and retires SSH. Spread across a clean
multi-day window; keep Dagster+ as idle rollback until AWS proves stable.

### 1. Promote to main + rebuild (incl. capture profile)
```bash
cd ~/app && git fetch origin && git checkout main && git pull origin main
docker compose -f services/dagster/aws/docker-compose.yml up -d --build
docker compose -f services/dagster/aws/docker-compose.yml --profile capture build   # captures are a SEPARATE profile
```

### 2. Pre-cutover checklist (verify ALL green before enabling schedules)
```bash
C="docker compose -f services/dagster/aws/docker-compose.yml"
# Snowflake key normalizes (the _normalize_pem fix) — must show -----BEGIN:
$C exec dbt-runner head -1 /tmp/snowflake_rsa_key.pem
$C exec dagster-codeloc head -1 /tmp/snowflake_rsa_key.pem
# IMDSv2 hop-limit persists at 2 (containers reach the instance role):
aws ec2 describe-instance-metadata-options --instance-id i-07594af1679f81c38 \
  --query 'InstanceMetadataOptions.HttpPutResponseHopLimit'   # → 2
$C exec dagster-codeloc printenv AWS_DEFAULT_REGION            # → us-east-1
# No serving PG anywhere (P2): both should be EMPTY:
$C exec dagster-codeloc printenv DATABASE_URL || echo "unset OK"
grep -rn "DATABASE_URL" ~/app/app/backend ~/app/scripts/write_serving_store.py || echo "no PG refs OK"
# Lambda still carries the P2 grants (run from operator laptop with admin profile):
#   aws iam list-role-policies --role-name credence-prod-lambda-execution-role
#   → expect DynamoServingCacheRead + S3ArtifactsZoneOverlayRead
```

### 3. Full daily cycle (dry validation before flipping schedules)
Manually launch the daily chain in dagit (or via the box) end-to-end —
`compute_elo → dbt_daily_build → predict_today → write_serving_store` — and confirm
picks + the 4 backend surfaces + the E9.31 heatmap serve from DynamoDB/S3.

### 4. Flip schedules in ONE window (never both on — no double-serve)
Enable the AWS-box dagit schedules + sensors **while disabling the Dagster+ Cloud
schedules in the same window.** This restores `lineup_monitor` re-scoring (fixes the
"pre-lineup-only" symptom).

- ✅ **No capture double-serve risk** (verified in code): the 4 host-cron captures
  (odds/schedule/derivative/weather) have **no registered Dagster schedule**. The
  capture-equivalent `ScheduleDefinition`s (`intraday_schedule_capture_*`,
  `intraday_weather_*`) are deliberately **omitted from `all_intraday_schedules`**
  (E11.4) — they're not in `Definitions`, so they don't even appear as schedules in
  dagit. Registered schedules are the 7 weekly/daily + `odds_clv_rebuild_daily`
  (post-game CLV marts, NOT a capture). Enable all of them freely.
- 🔁 **In the SAME window**: enable the `odds_current_rebuild_sensor` AND
  **re-comment `capture.crontab` line 42** (the interim served-price refresh) +
  re-install — the sensor takes over the odds-mart rebuild; running both is
  redundant. Re-commenting re-syncs the box working tree with the committed file:
  ```bash
  sed -i "/dagster-codeloc bash -lc/ s|^|# |" ~/app/services/dagster/aws/capture.crontab
  crontab ~/app/services/dagster/aws/capture.crontab && crontab -l | grep -c '^#.*write_serving_store'
  ```
- `crond` survives reboot (already `systemctl enable`d) — confirm after any restart:
  `systemctl is-enabled crond && systemctl is-active crond`.

### 5. HTTPS dagit (Caddy) + SSM shell — kill the IP-memorize + SSH friction
**DNS (operator, at the credencesports.com DNS host — Route 53 or Vercel DNS):**
add an **A record** `dagster.credencesports.com → 100.57.225.242` (the EIP). Use a
SUBdomain; the apex stays on Vercel for the frontend.

**Security group** — open 80+443 (and during *first* cert issuance, from anywhere so
Let's Encrypt's HTTP-01 can reach the box; tighten to the operator IP afterwards),
then **drop the old :3000 rule** (dagit is no longer published — Caddy reaches it
over the compose net; the `127.0.0.1:3000` binding keeps the SSH-tunnel fallback):
```bash
SG=$(aws ec2 describe-instances --instance-ids i-07594af1679f81c38 \
  --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 80  --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 443 --cidr 0.0.0.0/0
# after cert issues + you've confirmed https works, tighten 80/443 to your IP and remove 3000:
#   aws ec2 revoke-security-group-ingress --group-id $SG --protocol tcp --port 3000 --cidr <oldIP>/32
```

**Caddy basic-auth secret** (operator decision: basic-auth + SG allowlist):
```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'CHOOSE_A_STRONG_PASSWORD'
# put the user + the printed hash in services/dagster/aws/.env:
#   DAGIT_HOSTNAME=dagster.credencesports.com
#   DAGIT_BASIC_AUTH_USER=charlie
#   DAGIT_BASIC_AUTH_HASH=$$2a$$14$$....   # ⚠️ DOUBLE every $ → $$
# ⚠️ GOTCHA (verified 2026-06-26): docker-compose interpolates env_file values, so a
# bcrypt hash with single `$` arrives MANGLED in the container (Caddy then 401s every
# login). DOUBLE every `$` in the .env hash ($2a$14$… → $$2a$$14$$…); compose collapses
# $$→$ so Caddy sees the real 60-char hash. Verify: `docker compose exec caddy printenv
# DAGIT_BASIC_AUTH_HASH | wc -c` must be 61 (60 + newline), single-$, starts $2a$14$.
docker compose -f services/dagster/aws/docker-compose.yml up -d caddy
docker compose -f services/dagster/aws/docker-compose.yml logs caddy | grep -i "certificate obtained\|serving"
```
Then browse `https://dagster.credencesports.com` → basic-auth prompt → dagit.

**SSM Session Manager (retire SSH):** the SSM agent ships on AL2023; the instance
role just needs the managed policy (operator, admin profile):
```bash
aws iam attach-role-policy --role-name credence-dagster-ec2-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=i-07594af1679f81c38"     # PingStatus → Online
aws ssm start-session --target i-07594af1679f81c38           # shell, no SSH key, no port 22
```
Once SSM works, **remove the :22 SG rule**. The box is in a public subnet with an
IGW, so the agent reaches the public SSM endpoints over the internet — no interface
VPC endpoints needed. Record the DNS A record, cert, auth choice, and SSM enablement
in `infrastructure/aws_resources.md`.

> ⛔ Claude does not enter DNS-registrar / AWS-console credentials — the operator
> makes the DNS + any registrar changes; this runbook specifies *what*.

### 6. Decommission (only after a clean multi-day AWS window)
Cancel the **Railway** plan (serving PG fully replaced by DynamoDB → safe; an
optional `pg_dump` is insurance only) and **decommission Dagster+ Cloud** (~$275/mo
saved). Target steady-state AWS infra ~$15–35/mo.

## INC-16-P5 — Orchestration CI/CD (gate + auto-deploy)

Kills the manual "codeloc redeploy off main" step + the **baked-image drift** (a
`git pull` does NOT update a running container — code is `COPY`'d into the image, so
it must be rebuilt). Two GitHub Actions workflows, scoped to orchestration paths
(`pipeline/**`, `services/dagster/aws/**`, `services/dbt_runner/**`, `services/*_capture/**`,
`infrastructure/**`):

- **`orchestration_ci.yml`** (on PRs) — `dagster definitions validate` (defs load),
  `docker compose config` + lean-image builds, and the two guards:
  `scripts/ci/check_env_parity.py` (every `env.required` key documented in `.env.example`)
  + `scripts/ci/check_deploy_wiring.py` (PEM normalization at every consumer, region
  wired, no PG on serving/capture). These catch the deploy-only traps P2/P4 hit.
- **`orchestration_cd.yml`** (on merge to `main`) — OIDC → SSM Run Command runs
  **`deploy.sh`** on the box as `ec2-user`, waits, surfaces stdout/stderr, fails the
  job if the box deploy didn't succeed.

**`deploy.sh`** (the payload — also runnable by hand on the box):
0. env-parity: every `env.required` key present **and non-empty** in `.env` (empty
   shadows code defaults — the P4 trap) → abort before touching anything.
1. snapshot images → `:rollback`.
2. `git pull --ff-only origin main`.
3. **graceful drain** — wait (≤10 min) for in-flight Dagster runs to finish.
4. `up -d --build` (core) **and** `--profile capture build` (captures are a separate profile).
5. reinstall the host crontab **iff** `capture.crontab` changed in the pull.
6. **verify** (defs import, daemon up, dbt-runner `/health`, PEM materialized, instance
   role reachable from a container = IMDS hop-limit ok) → on any failure, **roll back to
   `:rollback` and exit 1** (never leave a half-deploy).

### Operator-provisioned (Claude does NOT handle credentials)
- **GitHub OIDC → AWS deploy role** (`secrets.AWS_DEPLOY_ROLE_ARN`): trust the GitHub
  OIDC provider (`token.actions.githubusercontent.com`, scoped to this repo/`main`);
  perms = `ssm:SendCommand` (on the instance + the `AWS-RunShellScript` document) +
  `ssm:GetCommandInvocation`. No long-lived keys in CI.
- **GitHub repo vars**: `AWS_REGION=us-east-1`, `DEPLOY_INSTANCE_ID=i-07594af1679f81c38`.
- **Branch protection** on `main`: require `Orchestration CI` (all 3 jobs) + the existing
  fast/slow gates + dbt-Build jobs for orchestration-path PRs.
- **Image pinning** (P7 task 1, folded in): `flaresolverr` pinned off `:latest` so the
  auto-`--build` CD can't pull a breaking upstream image silently.

### EVENTUAL (deferred — post-beta SLA, NOT in this story)
True blue/green (Caddy/ALB-fronted dual stateless stacks + a daemon-ownership handoff,
or a standby box to flip to). The Dagster daemon is a **singleton** — never two at once
— so any blue/green is a brief single-owner handoff, not seamless N+1. Cost ≈ doubled
compute during deploys. The NOW path (health-gated + auto-rollback + drain) is in `deploy.sh`.
