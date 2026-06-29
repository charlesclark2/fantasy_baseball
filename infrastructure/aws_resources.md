# AWS Resources — Credence Sports

Canonical record of all provisioned AWS resources for the Credence Sports platform.
Update this file whenever a resource is created or modified.

Naming convention: `credence-{environment}-{service}-{descriptor}`

---

## Domain & DNS (A0.1 — COMPLETE)

| Resource | Value |
|---|---|
| Domain | `credencesports.com` |
| Hosted Zone | Route 53 — `credencesports.com` |
| Wildcard ACM Certificate (us-east-1) | `arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID` |

> **Note:** Replace `ACCOUNT_ID` and `CERT_ID` with actual values after confirming in ACM console.
> Certificate must be in `us-east-1` for use with CloudFront and API Gateway.

---

## Cognito (A0.2 — COMPLETE)

| Resource | Value |
|---|---|
| User Pool ID | `us-east-1_gG9zMbwQt` |
| App Client ID | `1qh95e78bd7g6ipqcvdcpf7ou6` |
| App Client Secret | None (browser-based flow) |
| Region | `us-east-1` |
| Self-signup | Disabled (beta: admin-created accounts only) |
| User Groups | `beta_tester`, `subscriber`, `admin` |
| Hosted UI domain | `credencesports.auth.us-east-1.amazoncognito.com` |

JWT issuer URL: `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_gG9zMbwQt`

---

## Lambda — FastAPI Backend (A0.3)

| Resource | Value |
|---|---|
| Function name | `credence-prod-lambda-execution-role` |
| Runtime | `python3.12` |
| Handler | `app.backend.main.handler` |
| Architecture | `x86_64` |
| Memory | `512 MB` |
| Timeout | `30 seconds` |
| Region | `us-east-1` |

### Environment Variables (set in Lambda console or via CLI)

```
TARGET_ENV=prod

SNOWFLAKE_ACCOUNT=IHUPICS-DP59975
SNOWFLAKE_USER=credence_api
SNOWFLAKE_PRIVATE_KEY=<base64-encoded PEM or raw PEM>
SNOWFLAKE_ROLE=CREDENCE_API_RO
SNOWFLAKE_WAREHOUSE=COMPUTE_WH

COGNITO_APP_CLIENT_ID=1qh95e78bd7g6ipqcvdcpf7ou6
COGNITO_USER_POOL_ID=us-east-1_gG9zMbwQt

# Comma-separated Cognito usernames (= emails) for admin-only endpoints (/admin/*)
ADMIN_EMAILS=ctcb57@gmail.com

DYNAMO_PUSH_SUBSCRIPTIONS_TABLE=credence-prod-dynamo-push-subscriptions
USER_BETS_TABLE=credence-prod-dynamo-user-bets
USERS_TABLE=credence-prod-dynamo-users
AWS_REGION=us-east-1

CACHE_BUCKET=credence-prod-s3-api-cache
DAGSTER_CLOUD_API_TOKEN=<token from .env>

# Admin finances endpoint (GET /admin/finances)
# RAILWAY_MONTHLY_ESTIMATE and DAGSTER_MONTHLY_ESTIMATE are now set via the admin dashboard UI
# (stored in S3 admin-settings/finances-config.json) — no longer needed as env vars.
# OWNER_USER_ID: the owner's Cognito sub (find in Cognito console → User Pool → ctcb57@gmail.com → sub attribute)
# Without this, the finances endpoint falls back to dynamodb:Scan (add that permission or just set this var)
OWNER_USER_ID=<Cognito sub for ctcb57@gmail.com>
```

### Snowflake Role Grants Required

```sql
-- Create dedicated read-only role for the backend
CREATE ROLE IF NOT EXISTS CREDENCE_API_RO;

-- Read access on betting_ml and betting schemas
GRANT USAGE ON DATABASE baseball_data TO ROLE CREDENCE_API_RO;
GRANT USAGE ON SCHEMA baseball_data.betting_ml TO ROLE CREDENCE_API_RO;
GRANT USAGE ON SCHEMA baseball_data.betting TO ROLE CREDENCE_API_RO;
GRANT SELECT ON ALL TABLES IN SCHEMA baseball_data.betting_ml TO ROLE CREDENCE_API_RO;
GRANT SELECT ON ALL TABLES IN SCHEMA baseball_data.betting TO ROLE CREDENCE_API_RO;
GRANT SELECT ON FUTURE TABLES IN SCHEMA baseball_data.betting_ml TO ROLE CREDENCE_API_RO;
GRANT SELECT ON FUTURE TABLES IN SCHEMA baseball_data.betting TO ROLE CREDENCE_API_RO;

-- NOTE: user bets are OLTP and live in DynamoDB (see "DynamoDB — User Bets &
-- Users" below), NOT Snowflake. The backend needs no Snowflake write grant; it
-- stays read-only. Bet writes go to DynamoDB via the Lambda IAM role.

-- Warehouse access
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE CREDENCE_API_RO;

-- Snowflake ACCOUNT_USAGE (for /admin/snowflake-credits and /admin/finances Snowflake cost line)
-- Run as ACCOUNTADMIN:
-- GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE CREDENCE_API_RO;

-- Assign to service account
GRANT ROLE CREDENCE_API_RO TO USER credence_api;
```

### IAM additions for POST /auth/verify-email (A0.4.22 — password reset)

The `POST /auth/verify-email` endpoint marks the caller's Cognito `email_verified`
attribute to `true`, which is required before `forgotPassword()` can send a code to
admin-created accounts.

Add an inline policy named **`CognitoEmailVerify`** to the Lambda execution role
(`credence-prod-lambda-execution-role`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["cognito-idp:AdminUpdateUserAttributes"],
      "Resource": "arn:aws:cognito-idp:us-east-1:*:userpool/us-east-1_gG9zMbwQt"
    }
  ]
}
```

Verify it is present before deploying:
```bash
aws iam get-role-policy \
  --role-name credence-prod-lambda-execution-role \
  --policy-name CognitoEmailVerify
```

---

### IAM additions for /admin/finances

The `GET /admin/finances` endpoint calls AWS Cost Explorer. Add this inline policy to
the Lambda execution role (`credence-prod-lambda-execution-role`) in the IAM console:

```json
{
  "Effect": "Allow",
  "Action": ["ce:GetCostAndUsage"],
  "Resource": "*"
}
```

Without this, AWS costs show as `—` and the endpoint logs a warning. As of E9.39 the
endpoint groups Cost Explorer by SERVICE into line items (EC2 / S3 / Lambda / API
Gateway / DynamoDB / SES / Other AWS); Snowflake applies the daily 10%-cloud-services
billing rule; the dead Railway/Dagster cost lines are removed (Railway is cancelled,
Dagster self-hosts on the EC2 box — that spend lands in the EC2 line item).

### Lambda env for the Admin Dagster panel (E9.39 — post-INC-16)

The Admin "Recent Pipeline Runs" panel (`GET /admin/pipeline-runs`) now reads the
self-hosted EC2 dagit instead of Dagster+ Cloud. Set on `credence-prod-lambda-execution`:

| Env var | Value |
|---|---|
| `DAGSTER_GRAPHQL_URL` | `https://dagster.credencesports.com/graphql` (default if unset) |
| `DAGIT_BASIC_AUTH_USER` | Caddy basic-auth user (same as the box `.env`) |
| `DAGIT_BASIC_AUTH_PASSWORD` | Caddy basic-auth **plaintext** password (Caddy stores the *hash*; the Lambda client needs the plaintext to build the `Authorization: Basic` header) |

`DAGSTER_CLOUD_API_TOKEN` is no longer required and is ignored unless the URL is a
`*.dagster.plus` host. Creds are operator-supplied via Lambda env — never committed.

### Deploying

```bash
# Dry run (package only, no AWS call)
./infrastructure/lambda/deploy.sh --dry-run

# Full deploy
./infrastructure/lambda/deploy.sh
```

---

## API Gateway (A0.3 — MANUAL SETUP REQUIRED)

# MANUAL STEP REQUIRED
# Create the HTTP API in the AWS Console (not via CLI in this session).
# Configuration documented below for reproducibility.

| Setting | Value |
|---|---|
| API type | HTTP API (not REST API — cheaper and sufficient) |
| API name | `credence-prod-apigw-api` |
| Stage | `$default` (auto-deploy enabled) |
| Region | `us-east-1` |

### JWT Authorizer

| Setting | Value |
|---|---|
| Authorizer type | JWT |
| Name | `credence-prod-apigw-authorizer-cognito` |
| Identity source | `$request.header.Authorization` |
| Issuer URL | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_gG9zMbwQt` |
| Audience | `1qh95e78bd7g6ipqcvdcpf7ou6` |

Apply this authorizer to all routes except `GET /health`.

### Lambda Integration

| Setting | Value |
|---|---|
| Integration type | AWS Lambda |
| Lambda function | `credence-prod-lambda-execution-role` |
| Payload format version | `2.0` (required for Mangum HTTP API v2) |
| Timeout | 29 seconds |

### Custom Domain

| Setting | Value |
|---|---|
| Domain name | `api.credencesports.com` |
| ACM certificate | Wildcard cert from A0.1 (us-east-1) |
| API mapping | `credence-prod-apigw-api` → `$default` |

# MANUAL STEP REQUIRED
# After creating the custom domain in API Gateway, copy the "API Gateway domain name"
# (format: abc123.execute-api.us-east-1.amazonaws.com) and create an A record in
# Route 53 for api.credencesports.com pointing to it as an alias.

---

## DynamoDB — Push Subscriptions (A0.6 prereq)

| Resource | Value |
|---|---|
| Table name | `credence-prod-dynamo-push-subscriptions` |
| Partition key | `user_id` (String) |
| Billing mode | Pay-per-request (on-demand) |
| Region | `us-east-1` |

---

## DynamoDB — User Bets & Users (Performance redesign, story B1)

OLTP store for per-user bets and the app-users registry. Bets are transactional
(single-row writes on log, per-user reads on page load, point updates on settle),
so they live in DynamoDB rather than Snowflake. Model/prediction data stays OLAP
in Snowflake.

| Resource | Value |
|---|---|
| Bets table | `credence-prod-dynamo-user-bets` |
| — Partition key | `user_id` (String, Cognito sub) |
| — Sort key | `bet_id` (String, UUID) |
| — GSI | `gsi-pending-by-game`: PK `pending_game_pk` (Number), SK `bet_id`; **sparse** — only pending bets carry `pending_game_pk`, so the index = unsettled bets. Settling REMOVEs the attribute. Projection ALL. |
| Users table | `credence-prod-dynamo-users` |
| — Partition key | `user_id` (String, Cognito sub) |
| — Attributes | `email`, `first_seen_at`, `last_seen_at` (upserted on login-sync, story B2) |
| Billing mode | Pay-per-request (on-demand) |
| Region | `us-east-1` |

```bash
# Provision both tables (run once with create-table AWS creds)
./infrastructure/dynamo/create_user_bets_tables.sh

# One-time migration of the 122 legacy Snowflake placed_bets → DynamoDB (owner)
uv run python scripts/migrate_placed_bets_to_dynamo.py
```

Settlement: `scripts/settle_user_bets.py` (run by `settle_user_bets_op` in the
Dagster `daily_ingestion_job`, after `dbt_daily_build`) scans the pending GSI,
reads final scores from Snowflake, and writes `outcome`/`profit_loss`.

> **Apply all grants below with one script** (idempotent; run with IAM-admin creds):
> ```bash
> AWS_PROFILE=default DAGSTER_PRINCIPAL=<dagster-iam-name> \
>   ./infrastructure/dynamo/grant_dynamo_iam.sh
> ```
> It attaches read/write to the Lambda role + `baseball-access-user`, and the
> settle-only policy to the Dagster principal (omit `DAGSTER_PRINCIPAL` to skip #2).

### IAM — three distinct principals need access

Three separate identities touch these tables; each needs its own grant.

**1. Lambda execution role** (`credence-prod-lambda-execution-role`) — used by the B2 API
endpoints (`POST /bets`, `GET /bets`, login-sync). Read/write the bets + users
tables and Query the bets GSI:
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Query"],
  "Resource": [
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-user-bets",
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-user-bets/index/gsi-pending-by-game",
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-users"
  ]
}
```

**2. Dagster / pipeline IAM principal** — the identity the Dagster deployment
uses (the same creds that write the S3 API cache). Its creds are **tightly scoped
today (S3 only)**, so the daily `settle_user_bets_op` will fail until this grant
is added. The settle job scans the pending GSI and updates the bets table:
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:Scan", "dynamodb:UpdateItem"],
  "Resource": [
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-user-bets",
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-user-bets/index/gsi-pending-by-game"
  ]
}
```

**3. `baseball-access-user`** (the IAM user in the repo `.env`; used by the
Streamlit app's bet tracker and by local backend dev against uvicorn). Needs the
same read/write as the Lambda role (policy #1 actions) on the bets + users tables
+ bets GSI. Until granted, Streamlit bet logging/history and local `GET/POST /bets`
testing fail with AccessDenied (the one-time migration sidestepped this by using
the `~/.aws` power-user profile). Same actions/resources as policy #1.

> ⚠️ **Open infra task (blocks daily auto-settlement):** grant policy #2 to the
> Dagster principal. Until then, `settle_user_bets_op` errors each run (it's off
> the critical path, so it won't block predictions, but bets won't auto-settle —
> they can be settled manually with `AWS_PROFILE=default uv run python
> scripts/settle_user_bets.py`). The one-time migration used the local power-user
> profile, which already has write access, so it was unaffected.

---

## DynamoDB — Data Quality Reports (A0.4.15)

User-submitted data issue reports from the picks detail page. Writes via `POST /feedback/data-quality`.
Email notification to `support@credencesports.com` via SES is deferred (see A0.5 below).

| Resource | Value |
|---|---|
| Table name | `credence-prod-dynamo-data-quality-reports` |
| Partition key | `report_id` (String, UUID) |
| Billing mode | Pay-per-request (on-demand) |
| Region | `us-east-1` |

```bash
# Provision (run once with create-table IAM creds)
aws dynamodb create-table \
  --table-name credence-prod-dynamo-data-quality-reports \
  --attribute-definitions AttributeName=report_id,AttributeType=S \
  --key-schema AttributeName=report_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### Lambda IAM — inline policy addition

Add `dynamodb:PutItem` on this table to the Lambda execution role (`credence-prod-lambda-execution-role`):

```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:PutItem", "dynamodb:Scan", "dynamodb:UpdateItem"],
  "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-data-quality-reports"
}
```

### Lambda environment variable

| Variable | Value |
|---|---|
| `DATA_QUALITY_TABLE` | `credence-prod-dynamo-data-quality-reports` |

Set via Lambda console → credence-prod-lambda-execution-role → Configuration → Environment variables.

---

## EC2 — Dagster Orchestration (INC-16 re-host)

Re-homes the Railway orchestration onto AWS after the Railway workspace was
restricted (see `quant_sports_intel_models/baseball/edge_program/INC16_AWS_REHOST_RECOVERY.md`).
One box runs the full stack as Docker Compose — config + runbook in
`services/dagster/aws/`. **Phase 1 (compute) provisioned 2026-06-26.**

| Resource | Value |
|---|---|
| Instance ID | `i-07594af1679f81c38` |
| Elastic IP (stable egress — FanGraphs `cf_clearance` is IP-bound) | `100.57.225.242` |
| Instance type | `t4g.medium` (arm64 / Graviton, 4 GB) |
| Region / subnet | `us-east-1`, default VPC public subnet |
| AMI | Amazon Linux 2023 arm64 (latest via SSM) |
| Root volume | 30 GB gp3 |
| Key pair | `credence-dagster-key` (private key at `~/.ssh/credence-dagster-key.pem`) |
| Security group | `credence-dagster-sg` — ingress SSH 22 + dagit 3000 from operator IP only; egress all |
| IAM role / instance profile | `credence-dagster-ec2-role` / `credence-dagster-ec2-profile` (no static keys on the box). Policies: S3 RW on `baseball-betting-ml-artifacts` (model artifacts + dbt state); **`credence-s3-api-cache-rw`** — S3 Get/Put on `credence-prod-s3-api-cache/*` + ListBucket (the serving S3 fallback that `write_serving_store`/`write_api_cache` populate — INC-16-P4); DynamoDB RW on `credence-prod-serving-cache` (P2); **`credence-dynamo-user-bets-settle`** — DynamoDB Scan/Query/GetItem/UpdateItem on `credence-prod-dynamo-user-bets` + `/index/*` (the `settle_user_bets` op — INC-16-P4) |
| S3 access | **S3 gateway VPC endpoint** (no NAT — cost trap avoided) |
| SSH | `ssh -i ~/.ssh/credence-dagster-key.pem ec2-user@100.57.225.242` |

### Containers (Docker Compose — `services/dagster/aws/docker-compose.yml`)

| Container | Role | Port |
|---|---|---|
| `dagster-postgres` | Dagster run/event/schedule storage (metadata only — NOT the serving cache) | 5432 (internal) |
| `dagster-codeloc` | gRPC code server + run worker | 4000 (internal) |
| `dagster-daemon` | scheduler + sensors + run queue + run-monitoring | — |
| `dagster-webserver` | dagit UI / GraphQL | 3000 (operator IP) |
| `dbt-runner` | out-of-process dbt | 8080 (internal) |
| `flaresolverr` | FanGraphs Cloudflare solver (shares EIP egress) | 8191 (internal) |
| `caddy` (INC-16-P4) | HTTPS reverse proxy + basic-auth → dagit | 80 + 443 (public, auth-gated) |
| `odds/schedule/derivative/weather-capture` (P3) | run-once capture images (`profile: capture`, host-cron) | — |

dagit (P4): **`https://dagster.credencesports.com`** — Caddy terminates TLS
(Let's Encrypt) + HTTP basic-auth in front of the OSS webserver (which has no auth
of its own). `dagster-webserver` is bound to `127.0.0.1:3000` (SSH-tunnel fallback
only); the public `:3000` SG rule is dropped at cutover.
**Schedules boot STOPPED** — turning them on is INC-16 Phase 4.

### INC-16-P4 — HTTPS dagit + SSM (operator actions; see `services/dagster/aws/README.md` §P4)
- **DNS:** Route 53 (zone `credencesports.com`) A record `dagster.credencesports.com` → `100.57.225.242` (the EIP). _[fill ✅ when created]_
- **TLS:** Caddy auto-issues/renews Let's Encrypt for the subdomain (`caddy_data` volume persists certs). _[fill cert serial/expiry when issued]_
- **Auth choice (operator-confirmed 2026-06-26):** **Caddy basic-auth + SG IP-allowlist** (defense-in-depth, $0). Hash via `docker run --rm caddy:2 caddy hash-password`; user+hash in box `.env` (`DAGIT_BASIC_AUTH_USER`/`_HASH`).
- **Security group:** add 80+443; drop the old `:3000` rule; remove `:22` once SSM works.
- **Shell:** SSM Session Manager — attach `AmazonSSMManagedInstanceCore` to `credence-dagster-ec2-role`; `aws ssm start-session --target i-07594af1679f81c38`. SSH retired (public-subnet+IGW → agent reaches public SSM endpoints, no interface VPC endpoints).

### Provisioned via

```bash
AWS_PROFILE=default REGION=us-east-1 KEY_NAME=credence-dagster-key \
  ./services/dagster/aws/provision-ec2.sh
```

### Cost notes

~$15–35/mo target (t4g.medium + EIP + gp3 + S3 endpoint). NAT Gateway, Aurora,
and MWAA deliberately avoided. Dagster+ Cloud stays as the idle rollback until a
clean multi-day window (Phase 4), then is decommissioned.

---

## DynamoDB — Serving Cache (INC-16-P2)

Replaces the Railway PostgreSQL `api_cache` (down after the Railway restriction —
INC-16). Key→JSON serving cache the FastAPI backend reads at request time; read
order is now **DynamoDB → S3** (Snowflake last resort). Writer:
`scripts/write_serving_store.py` (on the EC2 box). Reader:
`app/backend/services/serving_cache.py`.

| Resource | Value |
|---|---|
| Table | `credence-prod-serving-cache` |
| PK | `pk` (String) — namespace = cache_key up to the first `/` ("picks", "team", "player", "players", "performance", "zone_matchup") |
| SK | `sk` (String) — `"{rest}#{cache_date}"` for date-scoped rows, `"{rest}#PERMANENT"` for permanent (Final-game / profile) rows |
| Attributes | `value` (JSON string), `is_permanent` (Bool), `updated_at` (ISO), `cache_date` (date or `PERMANENT`) |
| Billing | Pay-per-request (on-demand) |
| Region | `us-east-1` |
| GSI | none — point reads = GetItem; `team/` list = Query(pk=`team`); `picks/game/*` purge = Query(pk=`picks`, begins_with `game/`); admin full-refresh = a small Scan |

```bash
# Provision (run once with create-table IAM creds)
AWS_PROFILE=default ./infrastructure/dynamo/create_serving_cache_table.sh
```

### IAM — three grants

**1. EC2 instance-profile role** (`credence-dagster-ec2-role`) — the writer runs on
the box. Attached automatically by `services/dagster/aws/provision-ec2.sh`
(policy `dynamo-serving-cache`): `GetItem`/`PutItem`/`BatchWriteItem`/`Query`/`Scan`/`DeleteItem`
on `arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-serving-cache`.

**2. Lambda execution role** (`credence-prod-lambda-execution-role`) — the backend
reads the cache. Add `GetItem`/`Query`/`Scan` on the table:
```bash
aws iam put-role-policy \
  --role-name credence-prod-lambda-execution-role \
  --policy-name DynamoServingCacheRead \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
      "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-serving-cache"
    }]
  }' --region us-east-1
```

**3. Lambda execution role — E9.31 zone-overlay S3 read (unparked with INC-16-P2).**
The `GET /players/{id}/zone-overlay` endpoint falls back to reading overlay JSON
from `baseball-betting-ml-artifacts/baseball/serving/zone_matchup/*`. Grant the
Lambda role the S3 read so the heatmap resolves (no 404):
```bash
aws iam put-role-policy \
  --role-name credence-prod-lambda-execution-role \
  --policy-name S3ArtifactsZoneOverlayRead \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::baseball-betting-ml-artifacts/baseball/serving/zone_matchup/*"
    }]
  }' --region us-east-1
```

> **Portfolios (no new grant):** `user_portfolios` moved off PG to a `portfolio`
> map on the **users** table (`credence-prod-dynamo-users`), read/written via
> `app/backend/services/dynamo.py`. The Lambda role already has GetItem/UpdateItem
> on that table (bets/users grant), so portfolio reads/writes are already covered.

---

## Railway PostgreSQL Serving Store (A2.12) — ⛔ DECOMMISSIONED (INC-16-P2)

> **Superseded by the DynamoDB Serving Cache above.** The Railway PG (api_cache +
> daily_picks + user_portfolios) went down with the Railway restriction (INC-16)
> and is **not** being restored: api_cache → DynamoDB serving-cache, user_portfolios
> → users-table `portfolio` map, daily_picks → retired (never read). Once the live
> backend + writer are validated on DynamoDB, drop `DATABASE_URL` from the EC2 box
> `.env` and the Lambda config. Original spec retained below for history.

Primary OLTP read path for all FastAPI endpoints. Dagster reverse-ETLs prediction
outputs to PG after each pipeline run; FastAPI reads PG first (sub-1ms), falls
through to S3 then Snowflake on miss.

| Resource | Value |
|---|---|
| Provider | Railway (same project as FlareSolverr) |
| Plugin | PostgreSQL (Railway-managed) |
| Connection string | `DATABASE_URL` env var — set in Lambda console and Dagster Cloud secrets |
| Tables | `api_cache`, `daily_picks`, `user_portfolios` |
| DDL | `infrastructure/pg/create_serving_tables.sql` |

### Provision (run once)

```bash
# After Railway provisions the database, copy DATABASE_URL from the Railway dashboard
psql $DATABASE_URL -f infrastructure/pg/create_serving_tables.sql
```

### Lambda environment variable to add

Add `DATABASE_URL=<Railway connection string>` to the Lambda environment variables
(Lambda console → credence-prod-lambda-execution-role → Configuration → Environment variables).
Set the same value in Dagster Cloud secrets for the write path (`write_serving_store_op`).

### Table inventory

| Table | Primary key | Purpose |
|---|---|---|
| `api_cache` | `(cache_key, cache_date)` | Blob store keyed by endpoint path + date; replaces S3 as primary read path |
| `daily_picks` | `(game_pk, market, prediction_date)` | Individual pick rows for portfolio-side SQL filtering |
| `user_portfolios` | `user_id` (Cognito sub) | Per-user min EV threshold, markets, bankroll, max Kelly |

`api_cache.is_permanent = TRUE` on Final-game detail blobs so they survive date rollover
without needing S3's permanent prefix. S3 remains as secondary fallback during transition.

---

## S3 — ML Artifacts + dbt State (Story I.2 / E11.2)

| Resource | Value |
|---|---|
| **Bucket** | `baseball-betting-ml-artifacts` |
| **Region** | `us-east-1` |
| **Status** | ✅ Live — pre-existing; ML model artifacts in use |

### Key prefixes

| Prefix | Contents |
|---|---|
| `batter_clustering/` | Batter cluster model artifacts |
| `home_win/` | Home-win model artifacts |
| `layer3/` | Layer-3 signal model artifacts |
| `meta_model/` | Meta-model artifacts |
| `pitcher_clustering/` | Pitcher cluster model artifacts |
| `run_differential/` | Run-differential model artifacts |
| `sub_models/` | Sub-model artifacts |
| `total_runs/` | Total-runs model artifacts |
| `dbt_state/{env}/` | **E11.2** — dbt `manifest.json` + `sources.json` for `--state` incremental builds; keyed by `TARGET_ENV` (`prod`/`dev`) |

### IAM — Lambda execution role (zone overlay reads)

The `/players/{id}/zone-overlay` endpoint (E9.31) reads zone overlay JSONs from the
`baseball/serving/zone_matchup/overlay/` prefix. Add this inline policy to
`credence-prod-lambda-execution-role`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::baseball-betting-ml-artifacts/baseball/serving/zone_matchup/*"
    }
  ]
}
```

Add via CLI (run with default IAM-admin profile, not baseball-access-user):
```bash
aws iam put-role-policy \
  --role-name credence-prod-lambda-execution-role \
  --policy-name S3ArtifactsZoneOverlayRead \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::baseball-betting-ml-artifacts/baseball/serving/zone_matchup/*"
    }]
  }' \
  --region us-east-1
```

Verify after adding:
```bash
aws iam get-role-policy \
  --role-name credence-prod-lambda-execution-role \
  --policy-name S3ArtifactsZoneOverlayRead
```

---

### IAM — dbt-runner Railway service

The Railway dbt-runner writes `dbt_state/{env}/manifest.json` and `sources.json` after
each successful daily build (E11.2 Task 2). The IAM principal used by the dbt-runner
needs read+write on the `dbt_state/` prefix:

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject"],
  "Resource": "arn:aws:aws:s3:::baseball-betting-ml-artifacts/dbt_state/*"
}
```

The `baseball-access-user` IAM user (in `.env`) already has broader write access to this
bucket for model artifact uploads; the same credential set works for dbt state. Set
`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` in the Railway dbt-runner service env vars
if not already present.

---

## API Cache — S3 (A0.3)

| Resource | Value |
|---|---|
| **Cache bucket** | `credence-prod-s3-api-cache` |
| **Cache key pattern** | `api-cache/{YYYY-MM-DD}/{endpoint}.json` |
| **Date-scoped keys** | Yesterday's cache never serves today — keys auto-expire by date prefix |
| **Endpoints cached** | `picks/today.json`, `picks/ev.json`, `picks/history.json`, `performance/summary.json` |
| **Endpoints NOT cached** | `/performance/by-model`, `/alerts/*`, `/admin/*`, `/health` |
| **Cache population** | `write_api_cache.py` called as final step of `predict` job in `daily_ingestion.yml` |
| **Cache invalidation** | `POST /admin/cache/invalidate` — used by admin Force Refresh button |
| **Fallback** | On cache miss, FastAPI falls back to Snowflake and warms the cache |
| **Status** | ✅ Live — bucket provisioned, pipeline writes cache daily after predictions complete |

```bash
# Provision the cache bucket (run once)
aws s3api create-bucket \
  --bucket credence-prod-s3-api-cache \
  --region us-east-1

# Grant the Lambda execution role read/write access
# (attach an inline policy or managed policy to the Lambda's IAM role)
```

Lambda IAM policy to add:
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::credence-prod-s3-api-cache",
    "arn:aws:s3:::credence-prod-s3-api-cache/*"
  ]
}
```

---

## S3 — Frontend Hosting (A0.4)

> Not yet provisioned. Document here when A0.4 begins.

---

## CloudFront (A0.4)

> Not yet provisioned. Document here when A0.4 begins.

---

## Brand Identity Assets (A0.4.10)

Static logo assets in `frontend/public/brand/`. Served via Next.js static file handling (no CDN needed until A0.4 CloudFront is provisioned).

| File | Description | Status |
|---|---|---|
| `logo-full.svg` | Full lockup (icon + wordmark), dark background | ⏳ Pending SVG conversion (Vectorizer.ai) |
| `logo-icon.svg` | Icon only, for favicon and small contexts | ⏳ Pending SVG conversion (Vectorizer.ai) |
| `logo-wordmark.svg` | Wordmark only (white), dark background | ⏳ Pending SVG conversion (Vectorizer.ai) |
| `logo-full-light.svg` | Full lockup, light background (inverted) | ⏳ Pending generation |
| `white-logo-wordmark.svg` | Source file — white wordmark PNG-traced | ✅ Ready (source) |
| `black-logo-wordmark.svg` | Source file — black wordmark PNG-traced | ✅ Ready (source) |

**Manual steps remaining:**
1. Generate `logo-full-light.svg` — light-background inverted variant (only needed if the logo ever appears on a white/light background, e.g. email templates). The placeholder at `frontend/public/brand/logo-full-light.svg` is not referenced in the app.

---

## SES — Email (A0.5 / A0.4.18)

> **Status as of 2026-06-18: SES PRODUCTION — 50,000 msg/day, 14 msg/s, us-east-1.**

| Resource | Value |
|---|---|
| Region | `us-east-1` |
| Verified identity | `credencesports.com` (domain-level; DKIM RSA-2048 + custom MAIL FROM) |
| MAIL FROM domain | `mail.credencesports.com` |
| Sending address | `noreply@credencesports.com` |
| Production access | ✅ Granted 2026-06-18 (50k msg/day, 14 msg/s) |
| Configuration set | `credence-prod-ses-config` |
| Suppression list | Account-level, BOUNCE + COMPLAINT (see below) |

### Cognito SES wiring

Cognito user pool `us-east-1_gG9zMbwQt` sends all auth emails (invites, password reset,
verification) via SES `noreply@credencesports.com`. Configured via:

```bash
aws cognito-idp update-user-pool \
  --user-pool-id us-east-1_gG9zMbwQt \
  --email-configuration \
    "SourceArn=arn:aws:ses:us-east-1:ACCOUNT_ID:identity/credencesports.com,\
EmailSendingAccount=DEVELOPER,\
From=noreply@credencesports.com,\
ConfigurationSet=credence-prod-ses-config" \
  --region us-east-1
```

Replace `ACCOUNT_ID` with the actual AWS account ID (visible in AWS console top-right).

### Bounce / complaint handling (required before bulk sends)

AWS best-practice: enable account-level suppression list + SNS alerting for bounces/complaints.

**Step 1 — Enable account-level suppression (automatic address suppression on hard bounce/complaint):**
```bash
aws sesv2 put-account-suppression-attributes \
  --suppressed-reasons BOUNCE COMPLAINT \
  --region us-east-1
```

**Step 2 — Create SNS topic for bounce/complaint notifications:**
```bash
aws sns create-topic \
  --name credence-prod-ses-bounce-complaint \
  --region us-east-1
# ↳ Note the TopicArn returned (format: arn:aws:sns:us-east-1:ACCOUNT_ID:credence-prod-ses-bounce-complaint)
```

**Step 3 — Subscribe support@credencesports.com to the topic (confirm the subscription email):**
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT_ID:credence-prod-ses-bounce-complaint \
  --protocol email \
  --notification-endpoint support@credencesports.com \
  --region us-east-1
# ↳ Check support@credencesports.com inbox and confirm the subscription link
```

**Step 4 — Create SES configuration set:**
```bash
aws sesv2 create-configuration-set \
  --configuration-set-name credence-prod-ses-config \
  --region us-east-1
```

**Step 5 — Wire SNS bounce/complaint event destination to the configuration set:**
```bash
aws sesv2 create-configuration-set-event-destination \
  --configuration-set-name credence-prod-ses-config \
  --event-destination-name bounce-complaint-sns \
  --event-destination '{
    "Enabled": true,
    "MatchingEventTypes": ["BOUNCE", "COMPLAINT"],
    "SnsDestination": {
      "TopicArn": "arn:aws:sns:us-east-1:ACCOUNT_ID:credence-prod-ses-bounce-complaint"
    }
  }' \
  --region us-east-1
```

**Step 6 — Test with SES mailbox simulator (sends a raw SES email; confirms bounce handling fires):**
```bash
# Hard-bounce test — confirm support@credencesports.com receives an SNS notification
aws sesv2 send-email \
  --from-email-address "noreply@credencesports.com" \
  --destination '{"ToAddresses": ["bounce@simulator.amazonses.com"]}' \
  --content '{"Simple": {"Subject": {"Data": "Bounce test"}, "Body": {"Text": {"Data": "test"}}}}' \
  --configuration-set-name credence-prod-ses-config \
  --region us-east-1

# Complaint test — confirm support@credencesports.com receives an SNS notification
aws sesv2 send-email \
  --from-email-address "noreply@credencesports.com" \
  --destination '{"ToAddresses": ["complaint@simulator.amazonses.com"]}' \
  --content '{"Simple": {"Subject": {"Data": "Complaint test"}, "Body": {"Text": {"Data": "test"}}}}' \
  --configuration-set-name credence-prod-ses-config \
  --region us-east-1
```

**Important:** Steps 1–6 must complete before provisioning beta users at any scale.

### Cognito invite template

Branded HTML template: `infrastructure/email/cognito-invite-template.html`
- Dark header, brand green `#10b981` accents, credentials box, "Get Started" CTA → `https://www.credencesports.com/login`
- Contains required `{username}` and `{####}` Cognito placeholders
- Sends from `noreply@credencesports.com` (not the default `no-reply@verificationemail.com`)

**Push template to Cognito (run from repo root; requires AWS CLI with admin rights):**
```bash
python infrastructure/email/update_cognito_invite_template.py --dry-run   # preview
python infrastructure/email/update_cognito_invite_template.py             # live push
```

### Provisioning a beta user (one-time per user, Cognito console)

1. AWS Console → Cognito → User pools → `us-east-1_gG9zMbwQt`
2. **Users** tab → **Create user**
3. Set **Username** = user's email address
4. Select **"Send an invitation"** (triggers the branded invite email)
5. Select **"Generate a password"** (temp password included in invite)
6. Leave email pre-verified: ✅ (admin-created users with `email_verified = true` skip the OTP flow and go straight to the set-permanent-password screen)
7. Assign to the `beta_tester` group after creation: Users → select user → Group memberships → Add to group → `beta_tester`

### Test invite (run before bulk provisioning)

Send a test invite to yourself via Cognito console (same steps as above, username = `ctcb57@gmail.com`).
Verify:
- Email arrives from `noreply@credencesports.com` (not AWS default domain)
- Subject and branding look correct
- Temp-password login works at `https://www.credencesports.com/login`
- After setting permanent password, dashboard loads
- No spam folder

---

## Observability — INC-16-P6 (orchestration box alerting)

> **Status: code-complete 2026-06-27; provisioned by `services/observability/provision-observability.sh` (operator-run).** One SNS topic is the unified channel — the Python notifier (`pipeline/utils/alerting.py`), the box shell notifier (`services/dagster/aws/notify.sh`), and all CloudWatch alarms publish to it; one email subscription delivers everything.

| Resource | Name / value | Purpose |
|----------|--------------|---------|
| SNS topic | `credence-prod-alerts` | single alert channel (email subscription confirmed by operator) |
| Box role grant | `credence-alerts-publish` (inline on `credence-dagster-ec2-role`) | `sns:Publish` to the topic |
| Box role grant | `CloudWatchAgentServerPolicy` (managed) | CloudWatch agent → mem/swap/disk metrics |
| CloudWatch agent | config `services/dagster/aws/cloudwatch-agent-config.json` (mirrored in `cloud-init.sh`) | publishes `mem_used_percent` / `swap_used_percent` / `disk_used_percent` (namespace `CWAgent`, dim `InstanceId`) |
| Lambda | `credence-deadman-daily` (py3.12 arm64) | off-box daily-output dead-man switch; reads the DynamoDB heartbeat (`pk=ops, sk=heartbeat#daily`), alerts if not today's date |
| Lambda role | `credence-deadman-lambda-role` | `dynamodb:GetItem` on serving cache + `sns:Publish` |
| EventBridge rule | `credence-deadman-daily-schedule` (`cron(30 12 * * ? *)` UTC = 08:30 ET) | invokes the dead-man Lambda at the morning cutoff |

### CloudWatch alarms (all → `credence-prod-alerts`, dim `InstanceId`)
| Alarm | Condition | Notes |
|-------|-----------|-------|
| `credence-box-status-instance` | `StatusCheckFailed_Instance` ≥1, 2×60s | instance reachability; missing-data = breaching |
| `credence-box-status-system` | `StatusCheckFailed_System` ≥1, 2×60s | AWS-side reachability |
| `credence-box-cpu-sustained` | `CPUUtilization` >90% avg, 3×600s (30 min) | sustained only — build/predict bursts don't page |
| `credence-box-mem` | `mem_used_percent` >85% avg, 1×600s | OOM precursor (likeliest failure on the 4 GB box) |
| `credence-box-swap` | `swap_used_percent` >50% avg, 1×600s | thrashing / memory pressure |
| `credence-box-disk` | `disk_used_percent` >85% avg, 1×300s | docker images/logs/parquet on small root vol |
| `credence-box-cpu-credits` *(standard mode)* | `CPUCreditBalance` <50 | throttle precursor — only if instance is `standard` |
| `credence-box-cpu-surplus` *(unlimited mode)* | `CPUSurplusCreditsCharged` >0, 1×3600s | t4g default; sustained burst = cost, not throttle |

### Alert layers (one per failure mode)
- **Daily-output dead-man** (Lambda, off-box) — heartbeat from `write_serving_store`; fires whatever the root cause. Highest value.
- **Box/instance liveness + resource** — CloudWatch alarms above.
- **Service liveness** — `services/dagster/aws/healthcheck.sh` host-cron (every 5 min): core containers up + dagit/dbt-runner/flaresolverr reachable; 1h cooldown.
- **Dagster run failures** — `run_failure_alert_sensor` (OSS) → SES/SNS; LOUD for HALT-tier jobs. Replaces Dagster+ Cloud's run-failure alerting (gone post-cutover).
- **Freshness / capture staleness** — the existing raise-to-alert sensors (`odds_freshness`, `schedule_freshness`, `statcast_freshness`, `clv`, `model_health`) now call `send_alert` directly (their old "raise → Dagster+ email" path died with the cutover); plus `check_data_freshness.py` routed via the crontab.
- **Deploy rollback** — `deploy.sh` `rollback()` pages on auto-rollback.

**Subject convention:** `[Credence PROD] <SEVERITY>: <subject>`. De-dup: Python notifier rate-limits per key (1h); healthcheck has a 1h file cooldown; freshness sensors carry per-condition `dedup_key`s.
