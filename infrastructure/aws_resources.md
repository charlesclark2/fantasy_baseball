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
| Function name | `credence-prod-lambda-api` |
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

### IAM additions for /admin/finances

The `GET /admin/finances` endpoint calls AWS Cost Explorer. Add this inline policy to
the Lambda execution role (`credence-prod-lambda-api`) in the IAM console:

```json
{
  "Effect": "Allow",
  "Action": ["ce:GetCostAndUsage"],
  "Resource": "*"
}
```

Without this, AWS costs show as `—` and the endpoint logs a warning.

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
| Lambda function | `credence-prod-lambda-api` |
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

**1. Lambda execution role** (`credence-prod-lambda-api`) — used by the B2 API
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

Add `dynamodb:PutItem` on this table to the Lambda execution role (`credence-prod-lambda-api`):

```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:PutItem"],
  "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/credence-prod-dynamo-data-quality-reports"
}
```

### Lambda environment variable

| Variable | Value |
|---|---|
| `DATA_QUALITY_TABLE` | `credence-prod-dynamo-data-quality-reports` |

Set via Lambda console → credence-prod-lambda-api → Configuration → Environment variables.

---

## Railway PostgreSQL Serving Store (A2.12)

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
(Lambda console → credence-prod-lambda-api → Configuration → Environment variables).
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

## SES — Email (A0.5)

> Not yet provisioned. Domain `credencesports.com` must be verified in us-east-1.
