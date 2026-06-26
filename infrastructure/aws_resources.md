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
