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
| Self-signup — native (email/password) | **Disabled, permanently.** No email auto-verification, so `SignUp` creates an account that can never confirm itself or reset its password (E9.57, verified live). Do not open it without first configuring verification. |
| Self-signup — federated (Google) | **LIVE and public since E9.58** (2026-08-05). |
| Self-signup — email OTP (passwordless) | **G100-C0 — LIVE, verified end-to-end 2026-08-10.** A 6-digit code emailed via SES, driven by `CUSTOM_AUTH` triggers (`infrastructure/cognito/email_otp/`). Sidesteps the row above entirely: the code IS the proof of email ownership, so there is no verification step left to be missing. Second self-serve door beside Google. |
| Lambda triggers | **Pre sign-up** → `credence-prod-cognito-presignup-link` · **Define / Create / Verify auth challenge** → `credence-prod-cognito-email-otp` |
| App-client auth flows | must include `ALLOW_CUSTOM_AUTH` (G100-C0) |
| Auth session validity | **15 min** — this is the real expiry of an emailed OTP, and the code email says "15 minutes". Leaving it at the 3-minute default makes the email promise something the pool will not honour. |
| User Groups | `beta_tester`, `subscriber`, `admin`, `passwordless` (G100-C0-MFA — see below; membership means "no user-chosen password" and NOTHING else, because it exempts the account from subscriber TOTP) |
| Hosted UI domain | `us-east-1gg9zmbwqt.auth.us-east-1.amazoncognito.com` |
| Hosted UI custom domain | None (`CustomDomain: null`) |
| Allowed callback URLs | `https://www.credencesports.com/callback` **and** `https://credencesports.com/callback` (both verified allowlisted 2026-08-06 — a bogus `redirect_uri` correctly returns `redirect_mismatch`) |

### ⭐ Canonical identity — one human, one `sub`

Every store keys on the **native** Cognito user's `sub` (bets, leagues, portfolio, alerts,
and the groups that carry entitlement). Federated identities are LINKED INTO that native
user by the Pre sign-up trigger, so Google and email OTP resolve to the same account.

G100-C0 closed the half that was missing: E9.7 linked Google into a native user only **when
one already existed**, so a Google-FIRST person had no native counterpart — invisible while
Google was the only door, and a duplicate-account bug the moment a second door could also
create accounts. The trigger now **pre-provisions** a native user for a brand-new federated
sign-in and links into that, so the invariant holds in both arrival orders.

⚠️ **It is not retroactive.** Accounts created before that deploy are federated-only; their
`sub` owns their data and cannot be moved to a native user. `POST /auth/email-otp/start`
answers `next: "google"` for those addresses rather than minting a second account. ⛔ Do
**not** apply the E9.7 README's "delete the duplicate `Google_<sub>`" cleanup to one — that
recipe assumed the data lived on the native side; here it is the reverse and deleting takes
the person's bets and leagues with it.

⚠️ **PRECONDITION ON FLIPPING `ENFORCE_SUBSCRIBER_MFA=1`** (the E9.8 go-live step). The
server-side guard `auth.require_subscriber_mfa` exempts a session only when
`_session_is_federated` recognises it, which keys off `amr` and the **federated username
shape** — and a pre-provisioned/linked user's username is a plain UUID, not `google_…`. It
fails CLOSED, so with enforcement on, a `subscriber` who signs in by Google-linked or email
OTP could be 403'd and told to enable TOTP they cannot enroll (they have no password to
re-authenticate with). This is inert today (`ENFORCE_SUBSCRIBER_MFA` defaults to `0`) and
the frontend side is already handled (`sessionUsesPasswordlessAuth`).

🔧 **G100-C0-MFA — the code fix has LANDED, the live gate has NOT been run.** A `passwordless`
group is applied at both creation points and exempted in the guard. **The flip stays blocked
until the two-sided live gate passes**, because CI mocks all IO and a wrong exemption here is
an MFA bypass on a paying account that passes CI exactly as happily as the correct version.
Full runbook — group creation, the PreSignUp IAM addition, the backfill, and the acceptance
test — is `docs/g100_c0_mfa_passwordless_exemption.md`. The instrument is
`GET /auth/session-diagnostics` (authenticated, self-only): it reports the claims as the
Lambda receives them post-authorizer plus the verdict the guard would reach, so both legs can
be answered *before* the flag is flipped and without a real subscriber. ⚠️ It also carries a
`guard_version` marker — the API Lambda has no CD, so a merged PR is not a deployed build.

⭐ Found while fixing it: `require_subscriber_mfa` split `cognito:groups` on `,` only, while
this gateway delivers `[subscriber]` — so with enforcement on it would have gated **nobody**.
Both readings now share `dependencies.parse_groups_claim`.

#### ✅ Verified live 2026-08-10 — all four legs, against the real pool

Recorded because this is the class of claim that rots into "documented but never actually
true" (cf. `W7B_LAKEHOUSE_S3`). Each line is a measurement, not an intention:

- **OTP signup end-to-end** — `/start` for a never-seen address created ONE user
  (`CONFIRMED`, UUID username), SES delivered the code, `/verify` minted the token trio.
- **OTP first → Google second** — signing in with Google on that same address returned the
  **same UUID**, with `identities` carrying `providerName: "Google"`. One user, two methods.
- **Google first → OTP second** *(the case that was broken before G100-C0)* — after deleting
  the user and signing in with Google FIRST, the resulting username was a **UUID, not
  `google_…`** ⇒ pre-provisioning fired; the subsequent `/start` then returned
  `next: "otp"` with a delivered code.
- **Legacy refusal** — both pre-existing federated-only accounts returned `next: "google"`,
  `session: null`, and sent no mail.

⭐ **The one-line signature to re-check if this is ever suspected of regressing:** sign in
with Google using a brand-new address and read the username. A **UUID** is healthy; a
**`google_…`** means pre-provisioning is off or failing, and every account created in that
window is a federated-only one that can never use email OTP. `PRESIGNUP_PREPROVISION=0` and
a missing `AdminCreateUser` grant both produce exactly that, and both fail OPEN — i.e.
silently, with a perfectly successful sign-in. CloudWatch:
`presignup-link: pre-provision failed`.

⚠️ Population of federated-only (pre-G100-C0) accounts at cutover: **2**, both operator-owned
(2026-08-06, 2026-08-09). Closed set — it cannot grow while pre-provisioning is on.

JWT issuer URL: `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_gG9zMbwQt`

---

## Lambda — FastAPI Backend (A0.3)

| Resource | Value |
|---|---|
| Function name | `credence-prod-lambda-api` |
| Execution role | `credence-prod-lambda-execution-role` |
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

# E9.62 — Vercel metered spend on the finances page (GET /v1/billing/charges, FOCUS v1.3 JSONL).
# OPTIONAL: without it the page still shows the $20/mo Pro seat floor from 2026-08 and adds a
# note saying metered spend is unavailable — it never errors. Provision it to get real usage.
VERCEL_API_TOKEN=<Vercel account token — see "Vercel billing token" below>
VERCEL_TEAM_ID=<team_xxx; OMIT the var entirely for a personal (non-team) account>
```

### Vercel billing token (E9.62, admin finances)

`GET https://api.vercel.com/v1/billing/charges` needs a bearer token whose account holds one of
Owner / Member / Developer / Security / Billing on the team being queried. Create it at
**vercel.com → Account Settings → Tokens** (scope it to the team; give it an expiry and note the
renewal date — an expired token degrades to the seat floor silently apart from the page's note).

⚠️ `update-function-configuration` **REPLACES the whole Variables map** — read the current
environment first and re-send it, or every other setting on the function is wiped:

```bash
aws lambda get-function-configuration --function-name credence-prod-lambda-api \
  --region us-east-1 --query 'Environment.Variables' > /tmp/lambda-env.json

python3 - <<'PY'
import json
env = json.load(open('/tmp/lambda-env.json'))
env['VERCEL_API_TOKEN'] = '<paste token>'
env['VERCEL_TEAM_ID']   = '<team_xxx>'   # omit this line for a personal account
json.dump({'Variables': env}, open('/tmp/lambda-env-new.json','w'))
PY

aws lambda update-function-configuration --function-name credence-prod-lambda-api \
  --region us-east-1 --environment file:///tmp/lambda-env-new.json

# The call returns with LastUpdateStatus=InProgress — poll before testing, or you read the OLD env.
aws lambda get-function-configuration --function-name credence-prod-lambda-api --region us-east-1 \
  --query '{vercel:Environment.Variables.VERCEL_TEAM_ID,status:LastUpdateStatus}'
```

⭐ Read the flag, don't infer it (G100-D1): to check whether the token is live, query
`Environment.Variables.VERCEL_API_TOKEN` — the finances page looks identical with the token
absent (seat floor + note) and with the token present but reporting no overage.

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

Apply this authorizer to all routes except:
- `GET /health`
- `GET /fantasy/nfl/track-record/manifest` (NF3.2 public receipts manifest — added 2026-08-02)
- `GET /fantasy/nfl/track-record/{season}` (NF3.2 public receipts per-season data — added 2026-08-02)

✅ **ROUTE INVENTORY — RE-CONFIRMED 2026-08-08** (`aws apigatewayv2 get-routes`, run with the
`AdministratorAccess-769392325318` SSO profile; the everyday `baseball-access-user` profile is denied
`apigateway:*`, which is why this went unverified for so long). **THIRTEEN** routes now exist — the
2026 board flip and E9.59's pricing route have landed since the 2026-08-05 reading of nine:

```
ANY  /{proxy+}                            ← the catch-all: everything not listed below
OPTIONS /{proxy+}                         ← CORS preflight (must stay unauthenticated —
                                             a browser preflight cannot carry a bearer token)
ANY  /health
GET  /picks/featured
GET  /blog/posts
GET  /blog/posts/{id}
POST /stripe/webhook
GET  /fantasy/nfl/track-record/manifest
GET  /fantasy/nfl/track-record/{season}
GET  /fantasy/nfl/manifest                ← the E9.56 launch flip (2026 board, LOCKED payload)
GET  /fantasy/nfl/projections             ← ditto
GET  /fantasy/nfl/board                   ← ditto
GET  /subscription/public-pricing         ← E9.59 public pricing read
```

⛔ **`GET /fantasy/nfl/featured-player` (E9.46) is NOT in this list because it does not exist yet** —
measured 401 on 2026-08-08 while every other public surface returned 200. The command to create it
is below. Do not add it here until `get-routes` shows it.

⚠️ **THIS LIST GOES STALE SILENTLY AND IS MAINTAINED BY HAND** — it drifted by four routes in three
days. It is only ever true as of its stamp; re-run `get-routes` before relying on it, and never
build a `--route-settings` map from this block without listing first (a settings entry for a route
that does not exist governs nothing while reading exactly like a limit that is in place).

⭐ **AND YOU CAN CHECK IT WITHOUT `apigateway:*`, WHICH MATTERS BECAUSE THE EVERYDAY PROFILE IS
DENIED IT** (`baseball-access-user`, the reason this went unverified for so long): curl each path
and read the status — **401 means the authorizer rejected it before the Lambda ever ran**; any other
status, including a 422 from FastAPI validation, means the route is exempt. That is a two-second
check anyone can run, so a suspected-missing route never has to wait for an admin session.

⇒ **the model is: the catch-all carries the authorizer, and an explicit route EXEMPTS a path from
it.** Every explicit route above is a deliberate public surface. This CORRECTS the paragraph that
previously stood here, which claimed `GET /health` had no explicit route and called the mechanism
"never fully confirmed" — `ANY /health` does exist, and the inference was backwards.

⚠️ Re-read the AuthorizationType per route before relying on this
(`--query 'Items[].{Route:RouteKey,Auth:AuthorizationType}'`); the route LIST is confirmed, and a
route's auth type is the thing that actually gates it.

What was already confirmed, and still holds: HTTP API route matching is most-specific-wins, so adding an **explicit route for a
specific path with `--authorization-type NONE`** reliably exempts that exact path regardless of
whatever the catch-all does. That's the mechanism used for the two track-record routes above —
mirror it (`aws apigatewayv2 create-route --route-key "GET /your/new/public/path" --target
"integrations/p093jnh" --authorization-type NONE --api-id 8dhmehjak7 --region us-east-1`) for any
future public route. A router with no `Depends()` in FastAPI is NOT sufficient by itself — this
authorizer sits in front of the Lambda entirely and rejects an unauthenticated request before
Mangum/FastAPI ever sees it (see NF3.2: `fantasy_public.router` shipped correct at the app layer
but still 401'd until this API Gateway route was added).

#### G100-C0 — the two email-OTP routes — ✅ APPLIED + VERIFIED LIVE 2026-08-10

Passwordless sign-in. Public by necessity, not by preference: a caller signing in has no
token yet, so an authorizer on these routes makes the feature unreachable for exactly the
people it exists for.

```bash
for RK in "POST /auth/email-otp/start" "POST /auth/email-otp/verify"; do
  aws apigatewayv2 create-route \
    --api-id 8dhmehjak7 --region us-east-1 \
    --route-key "$RK" \
    --target "integrations/p093jnh" \
    --authorization-type NONE
done
```

Prove it from outside — deliberately with an INVALID address, so the reachability check
cannot create an account or send mail as a side effect:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://api.credencesports.com/auth/email-otp/start \
  -H 'Content-Type: application/json' -d '{"email":"not-an-email"}'
# 400 = reachable (FastAPI validated it).  401 = the authorizer is still in front.
```

⭐ **These carry no entitlement decision**, so the `jwt_verify` argument that makes the
other `NONE` routes safe does not apply: they read no Bearer token at all. What guards them
instead is the throttle in `routers/email_otp.py` (3 sends per address, 10 per IP), which
exists precisely because a `NONE` route that sends email is otherwise a mail-bomb primitive.

#### E9.46 — `GET /fantasy/nfl/featured-player` (the home page's fantasy card) — ⛔ NOT YET APPLIED

The landing page's fantasy proof card. Public by design and public in the FastAPI layer
(`fantasy_public.featured_router`, no `Depends`), which — as always — is **not sufficient**:

```bash
aws apigatewayv2 create-route \
  --api-id 8dhmehjak7 --region us-east-1 \
  --route-key "GET /fantasy/nfl/featured-player" \
  --target "integrations/p093jnh" \
  --authorization-type NONE
```

⭐ **The symptom is not an error page.** The card's read failing makes the component hide itself, so
the home page renders with the whole fantasy section simply absent — which reads as "the feature did
not ship" rather than "one route is missing". Confirmed live 2026-08-08: the Lambda was deployed and
serving, and `curl https://api.credencesports.com/fantasy/nfl/featured-player` returned
`401 {"message":"Unauthorized"}` while every other public surface returned 200.

### 🔒 The generic-board public routes — ✅ APPLIED (re-confirmed anonymously 2026-08-08)

⭐ **RE-VERIFIED FROM OUTSIDE, not read off this doc.** An anonymous `curl` of all three returns
**200** (`manifest`, `projections`, `board`), which is discriminating here: the authorizer sits in
front of the Lambda, so a route still carrying it answers 401 before FastAPI is reached. ⇒ the
routes below already exist and **the freemium build needs NO gateway change** — `deploy.sh` alone
takes the free board live.

⚠️ **THE FREEMIUM BUILD CHANGED WHAT THESE ROUTES SERVE, not whether they are reachable.** The
paragraph below describes the E9.56 state (2026 locked behind a per-point marker), which is
**retired** — the generic board is now free for every caller and the redaction is off the live path
(`docs/freemium_tier.md`). What still holds verbatim is the *reason the flip is dangerous without
the enforcement deployed*, and the `jwt_verify` argument underneath it: on a `NONE` route the Bearer
token is attacker-controlled, which is what makes the PAID capabilities safe to decide there.

⚠️⚠️ **`GET /fantasy/nfl/board` IS NOW APPLICATION-GATED PER PRESET, AND IT STAYS `NONE` AT THE
GATEWAY.** One preset is free (`full_ppr`/12) and the other 13 answer **403** to an unentitled
caller — decided inside the Lambda, by `entitlement.allows_board`, because the gateway authorizer is
all-or-nothing and cannot see a query parameter. So the route must remain anonymously reachable:
⛔ **do not "tighten" it by putting the authorizer back on**, which would 401 the free board and take
the whole wedge offline. This is also precisely why `jwt_verify` is load-bearing on this route rather
than merely tidy — the Bearer token that decides a paid preset arrives unvalidated by anything
upstream, so only a locally signature-verified one may grant it.

⇒ **the two answers a paid board URL can give are each individually safe to cache, for two separate
reasons**: an entitled caller carries `Authorization` ⇒ `private`, and an anonymous one gets a 403 ⇒
non-200 ⇒ `no-store`. Losing either is a breach, not a caching regression. The Vercel CDN route
(`frontend/app/api/public/[...path]/route.ts`) additionally pins its `config`/`size` patterns to the
free selection, so the edge cannot fetch a paid board at all.

🕐 **A ROLLBACK HAS A CACHE TAIL.** These responses are CDN-cached `s-maxage=900,
stale-while-revalidate=3600`, so the open board propagates within ~15 min of `deploy.sh` and — if
the Lambda is rolled back — the edge may keep serving the open payload for up to ~75 min afterwards.
Plan a withdrawal around that window rather than expecting it to be instant.

<details>
<summary>The original E9.56 flip instructions (retired — kept for the jwt_verify rationale)</summary>


The freemium split (past seasons free, 2026 locked behind a per-point marker) is enforced
**server-side** in `app/backend/services/entitlement.py`. Until these routes exist, the three 2026
surfaces stay behind the authorizer and a logged-out visitor gets 401 — which is the correct
PRE-launch state. Apply these **only** when the public launch is wanted, and **only after**
`./infrastructure/lambda/deploy.sh` has shipped the enforcement:

```bash
# ⛔ RUN deploy.sh FIRST. On a public route WITHOUT the deployed enforcement, these serve the FULL
#    2026 payload to anonymous callers — the exact leak E9.56 exists to prevent.
for RK in "GET /fantasy/nfl/manifest" "GET /fantasy/nfl/projections" "GET /fantasy/nfl/board"; do
  aws apigatewayv2 create-route \
    --api-id 8dhmehjak7 --region us-east-1 \
    --route-key "$RK" \
    --target "integrations/p093jnh" \
    --authorization-type NONE
done

# Then PROVE it from outside — this is the only real verification (CI mocks all IO):
uv run python scripts/check_api_entitlement.py --strict
```

⭐ **Why the flip is safe only with the enforcement deployed:** an `--authorization-type NONE` route
gets **no upstream token validation**, so the Bearer token becomes attacker-controlled. Measured
2026-08-04 — a forged unsigned JWT claiming `{"cognito:groups":["subscriber","admin"]}` returns
**200** on the existing NONE route (`/fantasy/nfl/track-record/manifest`) while every JWT-authorized
route returns 401. `app/backend/services/jwt_verify.py` is what makes entitlement on such a route
trustworthy (real RS256 JWKS verification, fails closed); the unverified
`dependencies._decode_jwt_payload` path is valid ONLY behind the authorizer.

⚠️ **THE FLIP ALSO MOVES WHERE A *LEGITIMATE* SUBSCRIBER IS AUTHENTICATED**, which is easy to miss
because nothing about it is visible in the FastAPI source. Today the gateway validates a subscriber's
token and Mangum hands the Lambda a populated `requestContext.authorizer`. On a NONE route that
context is ABSENT, so `resolve_entitlement` falls through to verifying the token itself — i.e. after
the flip, **every paying subscriber's access to these three endpoints depends on the Lambda reaching
the Cognito JWKS endpoint**. Two preconditions to confirm before flipping:

```bash
# 1. The Lambda must have public egress (NOT VPC-attached) to reach cognito-idp.
#    Expect empty SubnetIds/SecurityGroupIds.
aws lambda get-function-configuration --function-name credence-prod-lambda-api \
  --region us-east-1 --query 'VpcConfig'

# 2. OPTIONS preflight must stay reachable. `OPTIONS /{proxy+}` already covers the new paths and
#    must remain --authorization-type NONE — a browser preflight cannot carry a bearer token, so a
#    JWT-gated OPTIONS breaks every cross-origin call with an opaque CORS error, not a 401.
```

It fails CLOSED: if JWKS is unreachable, a real subscriber degrades to the LOCKED view rather than
erroring. That is the safe direction and it is visible (they get the CTA, not a blank page), but it
means a JWKS outage presents as "my subscription stopped working." JWKS is cached per warm container
(1h TTL, plus a refetch on an unknown `kid` so a key rotation self-heals), so the cost is one HTTPS
fetch per cold start with a 3s timeout.

</details>

### 🚦 E9.56 — API Gateway throttling (rate limiting / anti-bulk-scrape) — ✅ APPLIED 2026-08-08

⚠️ **AWS WAF does not support API Gateway HTTP APIs** (it covers REST APIs, CloudFront, ALB, AppSync
and others). This API is an HTTP API, so WAF is not an option here — **stage/route throttling is the
lever**. If real bot protection is needed later, the path is to front the API with CloudFront and
attach WAF there.

Throttling cannot stop one user reading one payload (nothing can — the browser must receive what it
renders). It stops bulk extraction: a competitor pulling the entire board in one pass, or polling
`/picks/featured` daily to accumulate our featured-pick history.

⚠️⚠️ **`--route-settings` KEYS MUST BE ROUTES THAT ALREADY EXIST.** This API authorizes per explicit
route on top of a catch-all, so **most paths have no explicit route object** — `GET /health` famously
does not (see the authorizer note above). A `--route-settings` entry for a non-existent route key is
not an error you can rely on seeing; it simply governs nothing, which reads exactly like a limit that
is in place. ⇒ **list the routes first and only set per-route caps on keys that come back.** The 2026
routes in particular do not exist until the launch flip above creates them, so their per-route caps
are a POST-flip step, not part of this one.

⚠️ **`update-stage --route-settings` REPLACES the whole map** (it is not a merge). Read the current
settings first and re-send everything you want to keep, in one call.

```bash
# ── 0. Permissions. `baseball-access-user` is DENIED apigateway:* — use an admin profile.
export AWS_PROFILE=<your-admin-profile>          # or run these in the API Gateway console
API=8dhmehjak7; REGION=us-east-1

# ── 1. What exists today (and what throttling is already set — do not clobber it).
aws apigatewayv2 get-routes --api-id $API --region $REGION \
  --query 'Items[].RouteKey' --output table
aws apigatewayv2 get-stage --api-id $API --region $REGION --stage-name '$default' \
  --query '{default:DefaultRouteSettings,perRoute:RouteSettings}'

# ── 2. Stage-wide default. Conservative; this is the one that actually bounds a bulk pull.
aws apigatewayv2 update-stage \
  --api-id $API --region $REGION --stage-name '$default' \
  --default-route-settings 'ThrottlingBurstLimit=100,ThrottlingRateLimit=50'

# ── 3. Tighter caps on the public, un-authenticated, bulk-attractive routes.
#      ONLY include keys that step 1 actually listed.
aws apigatewayv2 update-stage \
  --api-id $API --region $REGION --stage-name '$default' \
  --route-settings '{
    "GET /picks/featured":                    {"ThrottlingBurstLimit":20,"ThrottlingRateLimit":5},
    "GET /fantasy/nfl/track-record/{season}": {"ThrottlingBurstLimit":20,"ThrottlingRateLimit":5},
    "GET /fantasy/nfl/track-record/manifest": {"ThrottlingBurstLimit":20,"ThrottlingRateLimit":5}
  }'

# ── 4. Confirm it took, and that the app still works.
aws apigatewayv2 get-stage --api-id $API --region $REGION --stage-name '$default' \
  --query '{default:DefaultRouteSettings,perRoute:RouteSettings}'
uv run python scripts/check_api_entitlement.py     # expect **0 FAILED** (the pass COUNT grows
                                                   # with every public route — 54 on 2026-08-08;
                                                   # asserting a literal count just goes stale)
```

✅ **MEASURED STATE, 2026-08-08** — applied and verified:

```
default : ThrottlingBurstLimit 100, ThrottlingRateLimit 50     DetailedMetricsEnabled: false
perRoute: 20 burst / 5 rate on all SIX of —
          GET /picks/featured · /fantasy/nfl/manifest · /fantasy/nfl/projections
          /fantasy/nfl/board · /fantasy/nfl/track-record/manifest · /fantasy/nfl/track-record/{season}
```

Entitlement re-verified after the change: **54 passed, 0 FAILED.**

🕳️ **THREE PUBLIC ROUTES DELIBERATELY HAVE NO PER-ROUTE CAP** and inherit the 100/50 default:
`GET /subscription/public-pricing`, `GET /blog/posts`, `GET /blog/posts/{id}`. That is a judgement,
not an oversight — each returns a small payload with no bulk-extraction value (one price; blog
prose), so a tighter cap would buy nothing and add a way to break the marketing pages. Recorded here
so the gap is a decision rather than something a future reader has to guess about.

📊 **`DetailedMetricsEnabled: false`, SO `ThrottleCount` IS API-WIDE, NOT PER-ROUTE.** You will know
*that* something throttled, never *which route* — which matters because the six capped routes sit at
5/s while the default is 50/s, so the cause is almost never the default. Leaving it off is the right
call on cost grounds (per-route metrics are billed CloudWatch custom metrics — roughly $10–20/month
across thirteen routes, which is absurd against a ~$120 baseline and would make the cost guard a
cost). ⇒ **if `ThrottleCount` fires, enable detailed metrics TEMPORARILY to localise it, then turn
them back off.**

⚖️ **A per-route cap is shared across ALL callers, including our own CDN.** Post-`main` the anonymous
board reads arrive from Vercel's egress rather than from visitors, so the CDN and any direct
subscriber traffic draw on the same 20/5. The numbers are comfortable — CDN origin load is ~0.02–0.07
req/s (bounded by TTL windows × cache keys × POPs, and independent of visitor count) against 5/s —
but it is the same shared-bucket shape as the per-IP note in §5 of the spend-guardrails section, one
layer up.

📉 **Watch for over-throttling for ~24h.** A throttled request returns **429**, and the landing page
fetches `/picks/featured` server-side per render — so a limit set too low degrades the marketing page
first and silently (the fetch is wrapped in `.catch(() => ({game_pk:null}))`, i.e. it fails to an
empty state rather than an error). CloudWatch → `AWS/ApiGateway` → `ThrottleCount` and `4xx` for
`ApiId=8dhmehjak7`. Raise the caps if legitimate traffic is tripping them; the burst limit is the one
that bites a page doing several calls at once.

⚠️ **Throttling is per-API, not per-caller** — API Gateway HTTP API throttling has no per-client
dimension without usage plans (REST-API-only). So a limit low enough to stop a scraper can also
degrade a burst of genuine traffic; start at the values above and watch, rather than tightening
blind. Per-caller limiting would need CloudFront+WAF (rate-based rules) in front.

⚠️ Neither block above has been applied or verified from a session — the `baseball-access-user` CLI
profile has **no `apigateway:*` permission** (`aws apigatewayv2 get-routes` is denied), which is also
why this file's route inventory has always been maintained by hand.

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

## DynamoDB — Push Subscriptions / Notification Preferences (E9.9 / A0.6)

One item per user; the master `enabled` flag plus per-channel toggles govern delivery.

| Resource | Value |
|---|---|
| Table name | `credence-prod-dynamo-push-subscriptions` |
| Partition key | `user_id` (String, Cognito `sub`) |
| Billing mode | Pay-per-request (on-demand) |
| Region | `us-east-1` |

```bash
# Provision the table (run once; idempotent), then grant the API Lambda role:
./infrastructure/dynamo/create_push_subscriptions_table.sh
./infrastructure/dynamo/grant_alerts_iam.sh
```

> **Naming note:** the E9.9 story sketched a table `credence-prod-user-push-subscriptions`;
> this already-provisioned table serves the identical purpose (PK is the Cognito `sub`), so
> we reuse it rather than orphan it. Wired via `DYNAMO_PUSH_SUBSCRIPTIONS_TABLE`.

**Item schema** (all attributes optional except `user_id`):

| Attribute | Type | Meaning |
|---|---|---|
| `user_id` | S | Cognito `sub` (PK) |
| `enabled` | BOOL | master opt-in — nothing delivers unless true |
| `email_enabled` | BOOL | email channel toggle (default true) |
| `push_enabled` | BOOL | Web Push toggle (set on subscribe, cleared on unsubscribe/410-prune) |
| `sms_enabled` | BOOL | SMS toggle |
| `email` | S | SES destination |
| `phone_number` | S | E.164 (SMS; **not** from Cognito — entered in Settings) |
| `push_subscription` | M | `{endpoint, keys:{p256dh, auth}}` from the browser |
| `created_at` / `updated_at` | S | ISO-8601 |

Managed by `app/backend/routers/alerts.py`
(`GET/PUT /alerts/preferences`, `POST/DELETE /alerts/subscribe`).

> **IAM (required):** the API Lambda role `credence-prod-lambda-execution-role` needs
> `GetItem`/`PutItem`/`UpdateItem`/`DeleteItem` on this table — otherwise opting in
> 500s with `AccessDeniedException`. Grant it (idempotent; IAM is live, no redeploy):
> ```bash
> ./infrastructure/dynamo/grant_alerts_iam.sh
> ```

---

## Notifications — Qualified-plays alerts (E9.9 / A0.6)

`predict_today --notify` publishes ONE SNS message when the model posts
`qualified_bet > 0` for today's slate (idempotent per day via a serving-cache
conditional put). The `push-notification-sender` Lambda fans it out to opted-in
users over Web Push (VAPID/pywebpush) + SES email + SNS SMS. Honest framing: the
copy says the model posted N **qualified** plays — never a "+EV / you'll win" claim.

| Resource | Value |
|---|---|
| SNS topic | `credence-prod-qualified-bets-today` (us-east-1) |
| Lambda | `push-notification-sender` (py3.12 arm64; bundles pywebpush/py-vapid) |
| Lambda role | `credence-push-sender-lambda-role` — Dynamo Scan/Get/Update + SES send + SNS Publish (SMS) + logs |
| Box role grant | `credence-qualified-bets-publish` (inline on `credence-dagster-ec2-role`) — `sns:Publish` to the topic + `dynamodb:PutItem` on the serving cache (per-day idempotency claim) |
| VAPID public key | frontend env `NEXT_PUBLIC_VAPID_PUBLIC_KEY` (safe to ship) |
| VAPID private key | Lambda env `VAPID_PRIVATE_KEY` ONLY (never the bundle) |
| Box env | `QUALIFIED_BETS_SNS_TOPIC_ARN` (predict_today reads it; unset ⇒ loud skip) |
| Box (predict_today runs here) | instance `i-07594af1679f81c38`, region `us-east-1`; `.env` at `/home/ec2-user/app/services/dagster/aws/.env`; redeploy via `.../deploy.sh` (pulls main + `up -d --build`) |

`provision-notifications.sh` auto-wires the box (sets the env var + kicks `deploy.sh`
via SSM) unless `SKIP_BOX_WIRING=1`. It prints the exact `aws ssm send-command`
lines it ran (real instance-id/region/paths baked in) so they can be re-run by hand.
⚠️ `deploy.sh` pulls **main** — merge before (re)deploying or the `--notify` code
won't be on the box.

```bash
# One-time keys, then provision (operator, laptop with AWS admin + SES prod):
uv run python services/notifications/push_sender/gen_vapid.py
VAPID_PRIVATE_KEY="$(cat vapid_private.pem)" VAPID_SUBJECT=mailto:support@credencesports.com \
  ./services/notifications/provision-notifications.sh
```

> **SMS status (as of 2026-07-07): code-complete, NOT yet deliverable — gated "Coming
> soon" in the UI.** The account is in the SNS SMS **sandbox** with **no origination
> number**, so even sandbox verification fails (`No origination entities available to
> send`). Email + push work without any of this. To enable SMS:
> 1. **Request an origination number** (toll-free is cheapest to start, ~$2/mo + ~$0.008/msg):
>    ```bash
>    aws pinpoint-sms-voice-v2 request-phone-number --region us-east-1 \
>      --iso-country-code US --message-type TRANSACTIONAL --number-type TOLL_FREE --number-capabilities SMS
>    ```
> 2. **Toll-free verification** — submit the registration form (company / use-case / sample
>    messages / opt-in) in the **AWS End User Messaging SMS** console. Review ~1–3 weeks;
>    unverified TFNs are rate-limited/filtered. (10DLC is the alternative — needs brand+campaign.)
> 3. **Exit the SMS sandbox** (support request) to text arbitrary numbers, OR stay in
>    sandbox and `create-sms-sandbox-phone-number` + `verify-sms-sandbox-phone-number` per recipient.
> 4. **Flip the UI gate on:** set `SMS_AVAILABLE = true` in
>    `frontend/components/notifications-settings.tsx` and redeploy the frontend.
> The Lambda already has `sns:Publish` + reads `phone_number` — no backend change needed.

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
| Instance type | `r6g.large` (arm64 / Graviton, 2 vCPU / **16 GB**) — resized from `t4g.medium` (4 GB) on **INC-22 (2026-06-29)**. The 4 GB box OOM-killed itself running a `run_w1_lakehouse` monthly_schedule flatten (DuckDB `memory_limit` exceeded physical RAM); memory-optimized r6g gives the headroom for a flatten + the resident Dagster/dbt-runner/flaresolverr stack, and the `memory_limit` is now box-aware (`run_w1_lakehouse._safe_memory_limit_gb`). Resize = Stop → Change instance type → Start (EBS + EIP persist). |
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

~$15–35/mo was the original `t4g.medium` target. **INC-22 (2026-06-29):** resized to
`r6g.large` (16 GB) ⇒ compute ~$73/mo on-demand (+EIP + gp3 + S3 endpoint) — the 4 GB
box could not run the DuckDB lakehouse flattens without OOM-killing the host. Consider a
1-yr Compute Savings Plan / RI to claw back ~40% if the size holds. NAT Gateway, Aurora,
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

## 💸 Spend guardrails + billing alarms (G100-D1) — ✅ MOSTLY APPLIED 2026-08-08

> **Applied:** AWS Budget `credence-prod-monthly-250` · Cost Anomaly Detection (re-pointed to
> `ctcb57@gmail.com`, threshold `ABSOLUTE ≥ $25 AND PERCENTAGE ≥ 40%`) · Vercel spend notification ·
> API Gateway stage + per-route throttling (§ above).
> **CloudWatch billing alarm — ✅ NOW FULLY WIRED (2026-08-08), after three stacked defects.**
> (1) billing alerts had never been enabled, so `EstimatedCharges` did not exist; (2) the creation
> command here passed `--treat-missing-data notBreaching`, which made the alarm report **`OK`**
> while watching that missing metric; (3) re-putting it with the corrected flag left a **stale**
> `OK` behind, because CloudWatch leaves an updated alarm's state unchanged. Each one hid the next,
> and all three presented as a healthy alarm. Now: `TreatMissingData: missing`, metric present, and
> `get-metric-statistics` on the alarm's exact dimension returns real data. **Baseline measured at
> ~$107/month, so the $250 threshold stands at 2.3x** — validated rather than assumed.

> Cost model and the reasoning behind the $250 threshold: **`docs/g100_d1_cost_model.md`**.
> Regenerate its numbers with `uv run python scripts/estimate_launch_cost.py`.
>
> **Why this exists:** organic traffic is cheap (~$21/month all-in at 100k monthly visitors), but a
> single un-throttled scraper on the newly-public board costs **~$3,210/month, $2,772 of it egress**.
>
> **Measured pre-existing state (2026-08-08)** — corrects an earlier draft of this section that said
> there was no monitoring at all. **No AWS Budget and no CloudWatch billing alarm**: that part
> stands. But AWS had auto-enabled **Cost Anomaly Detection**, and its default subscription was live
> the whole time — **paging a university address rather than the `ctcb57@gmail.com` inbox every
> other alarm in this stack uses**, at a threshold needing roughly a full day of a $107/day scrape
> to accumulate. So the honest description is not "no monitoring" but **"one detector, pointed at a
> different inbox, firing about a day late"** — the harder failure to notice, because the console
> renders it as configured and healthy. Details and the fix in §3.

### Two gotchas that make a billing alarm silently useless

- 🔴 **`AWS/Billing` `EstimatedCharges` is published ONLY in `us-east-1`.** An alarm created in any
  other region watches a metric that does not exist, stays in `INSUFFICIENT_DATA` forever, and never
  fires. This is the classic guard-that-cannot-fail; every command below pins `--region us-east-1`.
- 🔴 **Billing metrics must be switched on first**, and they can take up to ~24 h to appear.
  Billing console → **Billing preferences** → tick **"Receive CloudWatch billing alerts"**. Until
  that is done the alarm below has nothing to watch.
- ⚠️ **SNS here is `us-east-1`.** Do **not** export `AWS_DEFAULT_REGION=us-east-2` for these — that
  is the S3 *lakehouse bucket* only, and passing it yields a misleading `InvalidParameter: TopicArn`.

### 1. AWS Budget — $250/month, three notifications  ▸ LAPTOP

```bash
# `baseball-access-user` is unlikely to have budgets:* — use the admin SSO profile.
export AWS_PROFILE=<your-admin-profile>
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
EMAIL=ctcb57@gmail.com

cat > /tmp/g100-budget.json <<JSON
{
  "BudgetName": "credence-prod-monthly-250",
  "BudgetLimit": { "Amount": "250", "Unit": "USD" },
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
JSON

# 80% actual = early warning · 100% actual = it happened · 100% FORECAST = it is going to happen.
# The forecast notification is the one that catches a scrape on day 2 instead of day 20.
cat > /tmp/g100-budget-notifications.json <<JSON
[
  { "Notification": { "NotificationType": "ACTUAL",     "ComparisonOperator": "GREATER_THAN",
                      "Threshold": 80,  "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "$EMAIL" } ] },
  { "Notification": { "NotificationType": "ACTUAL",     "ComparisonOperator": "GREATER_THAN",
                      "Threshold": 100, "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "$EMAIL" } ] },
  { "Notification": { "NotificationType": "FORECASTED", "ComparisonOperator": "GREATER_THAN",
                      "Threshold": 100, "ThresholdType": "PERCENTAGE" },
    "Subscribers": [ { "SubscriptionType": "EMAIL", "Address": "$EMAIL" } ] }
]
JSON

aws budgets create-budget \
  --account-id "$ACCOUNT_ID" \
  --budget file:///tmp/g100-budget.json \
  --notifications-with-subscribers file:///tmp/g100-budget-notifications.json \
  --region us-east-1

# Verify
aws budgets describe-budgets --account-id "$ACCOUNT_ID" --region us-east-1 \
  --query 'Budgets[].{Name:BudgetName,Limit:BudgetLimit.Amount}' --output table
```

### 2. CloudWatch billing alarm → the existing `credence-prod-alerts` topic  ▸ LAPTOP

Reuses the same SNS topic as every other page (`pipeline/utils/alerting.py::send_alert`), so this
lands in the inbox the operator already watches.

```bash
export AWS_PROFILE=<your-admin-profile>
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
TOPIC_ARN="arn:aws:sns:us-east-1:${ACCOUNT_ID}:credence-prod-alerts"

aws cloudwatch put-metric-alarm \
  --region us-east-1 \
  --alarm-name "credence-prod-billing-over-250" \
  --alarm-description "G100-D1: estimated monthly AWS charges exceeded \$250 — see docs/g100_d1_cost_model.md" \
  --namespace "AWS/Billing" \
  --metric-name "EstimatedCharges" \
  --dimensions Name=Currency,Value=USD \
  --statistic Maximum \
  --period 21600 \
  --evaluation-periods 1 \
  --threshold 250 \
  --comparison-operator GreaterThanThreshold \
  --treat-missing-data missing \
  --alarm-actions "$TOPIC_ARN"

# 🔴🔴 `--treat-missing-data missing` IS LOAD-BEARING AND WAS WRONG IN THE FIRST CUT OF THIS DOC.
#
# It originally said `notBreaching`, and the result (measured 2026-08-08) was an alarm sitting at
# **StateValue: OK** while `AWS/Billing EstimatedCharges` DID NOT EXIST — because billing alerts had
# never been enabled. `notBreaching` converts "I can see nothing" into "everything is fine", so the
# alarm reported green while watching a metric that was not there. A guard that cannot fail,
# displaying success: strictly worse than no alarm, because it reads as covered.
#
# Its own StateReason gave it away and is worth recognising verbatim:
#   "no datapoints were received for 1 period and 1 missing datapoint was treated as [NonBreaching]"
#
# With `missing`, an absent metric shows as INSUFFICIENT_DATA — visibly not-OK, which is the honest
# state and the repo's standing rule that an UNEVALUABLE check is never scored healthy (NF1.7 (a)).
# ⛔ Do not use `breaching` either: that pages immediately and forever until the metric appears.

# ⭐ VERIFY THE METRIC EXISTS — DO NOT VERIFY BY READING THE ALARM STATE. `INSUFFICIENT_DATA` means
#    both "not populated yet" and "will never exist", and (as above) a mis-set treat-missing-data
#    can render the second case as OK. `list-metrics` answers it definitively and immediately:
aws cloudwatch list-metrics --region us-east-1 \
  --namespace AWS/Billing --metric-name EstimatedCharges --output table
#   EMPTY  ⇒ billing alerts are NOT enabled. The alarm can never fire. Go tick the preference.
#   A row ⇒ enabled; the alarm reaches OK on its own (metric can take ~24h to first appear).
#
# ⚠️ BUT A NON-EMPTY LIST IS STILL NOT PROOF — CLOUDWATCH DIMENSION MATCHING IS EXACT, NOT SUBSET.
#    Once enabled, `AWS/Billing` publishes MANY variants: `{ServiceName, Currency}` per service,
#    `{Currency, LinkedAccount}`, `{ServiceName, Currency, LinkedAccount}`, and the bare
#    `{Currency}` total. They are DIFFERENT metrics. An alarm on `{Currency=USD}` sees ONLY the
#    bare-total variant, so a list full of per-service rows can look like success while the alarm
#    still watches nothing. ⇒ verify END-TO-END by asking exactly what the alarm asks:
aws cloudwatch get-metric-statistics --region us-east-1 \
  --namespace AWS/Billing --metric-name EstimatedCharges \
  --dimensions Name=Currency,Value=USD \
  --start-time $(date -u -v-2d +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 21600 --statistics Maximum --output table
#   ✅ MEASURED 2026-08-08: returns Maximum 24.72 @ 03:29Z ⇒ the alarm is fully wired.
#   If it returns EMPTY, this account publishes only the LinkedAccount-qualified variant; re-put the
#   alarm with `--dimensions Name=Currency,Value=USD Name=LinkedAccount,Value=<account-id>`.
#
# 💰 BONUS, AND USE IT: those datapoints are the real month-to-date bill, which is how the $250
#    threshold got validated instead of assumed. $24.72 at 7.15 days into August ⇒ $3.46/day ⇒
#    ~$107/month, i.e. the threshold sits at 2.3x baseline. Re-read this occasionally; if the
#    baseline moves materially, rescale the budget + alarm to ~2x it.

aws cloudwatch describe-alarms --region us-east-1 \
  --alarm-names credence-prod-billing-over-250 \
  --query 'MetricAlarms[].{Name:AlarmName,State:StateValue,Missing:TreatMissingData,Threshold:Threshold}' \
  --output table

# ⚠️ A STATE READ IMMEDIATELY AFTER AN UPDATE IS STALE — DO NOT TREAT IT AS THE NEW CONFIG'S VERDICT.
# Per AWS: "When you update an existing alarm, its state is left unchanged, but the update
# completely overwrites the previous configuration." So re-putting the alarm with the corrected
# `--treat-missing-data missing` leaves the old `OK` sitting there, and with `--period 21600` the
# next evaluation is up to SIX HOURS away. Measured 2026-08-08: `Missing: missing` alongside
# `State: OK` — correct config, stale verdict, and indistinguishable at a glance from the very bug
# that was just fixed. (Same shape as the mis-set flag above, one layer over: the state field is
# again the thing you must not verify by.)
#
# Clear it rather than waiting. Safe: INSUFFICIENT_DATA fires `insufficient-data-actions`, and none
# are configured. ⛔ NEVER do this with `--state-value ALARM` — that DOES fire the SNS action and
# pages a real incident that is not happening.
aws cloudwatch set-alarm-state --region us-east-1 \
  --alarm-name credence-prod-billing-over-250 \
  --state-value INSUFFICIENT_DATA \
  --state-reason "clearing the stale OK carried over from the previous config"
```

### 3. Cost Anomaly Detection — free, and the FAST signal  ▸ LAPTOP

A monthly-total alarm at $250 over a ~$120 baseline trips ~1.2 days into a $107/day scrape. Anomaly
detection compares against a learned daily baseline and is materially quicker; it costs nothing.

🔴 **AWS ALLOWS EXACTLY ONE DIMENSIONAL (`SERVICE`) SPEND MONITOR PER ACCOUNT, AND THIS ACCOUNT
ALREADY HAS ONE.** Measured 2026-08-08: `create-anomaly-monitor` returns
`ValidationException: Limit exceeded on dimensional spend monitor creation`. That is not a
misconfiguration and nothing needs deleting — **the monitor is the detector, the SUBSCRIPTION is the
notification**, and it is only the subscription we are missing. ⇒ LIST FIRST, REUSE THE ARN.

```bash
export AWS_PROFILE=<your-admin-profile>          # `baseball-access-user` is denied ce:*
EMAIL=ctcb57@gmail.com

# 1. Find the existing dimensional monitor and take its ARN.
aws ce get-anomaly-monitors --region us-east-1 \
  --query 'AnomalyMonitors[].{Name:MonitorName,Type:MonitorType,Dim:MonitorDimension,Arn:MonitorArn}' \
  --output table

MONITOR_ARN=$(aws ce get-anomaly-monitors --region us-east-1 \
  --query 'AnomalyMonitors[?MonitorType==`DIMENSIONAL`]|[0].MonitorArn' --output text)
echo "MonitorArn: $MONITOR_ARN"
# ⚠️ If this prints `None`, there genuinely is no dimensional monitor — only then create one:
#   aws ce create-anomaly-monitor --region us-east-1 \
#     --anomaly-monitor '{"MonitorName":"credence-prod-services","MonitorType":"DIMENSIONAL","MonitorDimension":"SERVICE"}'

# 2. Check the existing SUBSCRIPTION before creating one.
#
# 🔴 MEASURED 2026-08-08: this account already has `Default-Services-Subscription` (DAILY) —
#    AWS auto-creates it when it auto-enables Cost Anomaly Detection. ⇒ the action here is almost
#    certainly UPDATE, not CREATE. Two subscriptions on one monitor means two emails per anomaly,
#    which is how a monitor gets muted.
#
# ⚠️ AND THE SUMMARY VIEW HIDES THE ONLY TWO FIELDS THAT MATTER. `{Name, Frequency}` looks healthy
#    for a subscription that notifies NOBODY: an auto-created default often has an EMPTY
#    `Subscribers` list and surfaces only in the console. That is a detector that runs and pages
#    no one — the E11.30 shape exactly (the detection existed for days; the page never fired).
#    A percentage-based default `ThresholdExpression` is the second trap: on a small bill a
#    routine $2 → $6 Lambda blip is +200%, so it fires constantly and gets ignored.
#    ⇒ ALWAYS inspect Subscribers + ThresholdExpression, never just Name/Frequency.
aws ce get-anomaly-subscriptions --region us-east-1 \
  --query 'AnomalySubscriptions[].{Name:SubscriptionName,Freq:Frequency,Arn:SubscriptionArn,Subs:Subscribers,Threshold:ThresholdExpression,Monitors:MonitorArnList}' \
  --output json

# 2b. UPDATE it. ── THE MEASURED STATE, 2026-08-08 ──────────────────────────────────────────────
#
#   Subscribers : ccl1196@wgu.edu  (EMAIL, CONFIRMED)
#   Threshold   : AND[ ANOMALY_TOTAL_IMPACT_ABSOLUTE >= 100.0,
#                      ANOMALY_TOTAL_IMPACT_PERCENTAGE >= 40.0 ]
#   Monitor     : …anomalymonitor/eaf80e43-28c0-4251-bee5-6ce3dc8192b8   ✅ correctly attached
#
# 🔴 FINDING 1 — IT PAGED A DIFFERENT INBOX FROM EVERY OTHER ALARM IN THIS STACK. The budget and
#    the `credence-prod-alerts` SNS topic both go to ctcb57@gmail.com; this one went to a
#    university address. Not merely inconsistent: a `.edu` address is the kind that gets
#    deactivated, and when it does, delivery stops SILENTLY — the subscription still reads
#    CONFIRMED. Split alert destinations are how one channel goes unwatched without anyone
#    deciding that it should.
#
# ⚠️ FINDING 2 — THE THRESHOLD IS AN `And`, SO THE STRICTER LEG BINDS, AND HERE THAT IS THE
#    ABSOLUTE ONE. Against this account's actual risk the percentage leg is free: the egress
#    baseline is ~zero, so a scrape is thousands of percent and clears 40% instantly. The $100
#    absolute leg is what sets the delay — at the ~$107/day scrape rate, roughly a FULL DAY must
#    accumulate before it fires. Lowering it to $25 fires ~4x sooner.
#
# ⚖️ THE TRADEOFF, STATED: the percentage leg CANNOT separate a scrape from a legitimate spike
#    (both are enormous against a ~zero egress baseline), so the absolute leg is the only real
#    discriminator. At $25 a laptop-run lakehouse backfill — which writes to PROD S3 — may
#    occasionally trip it. Those are deliberate, recognisable events and missing a scrape costs
#    far more than recognising a backfill. If it proves noisy, raise to $50; do not remove the
#    percentage leg, which is what keeps ordinary drift out.

SUB_ARN=$(aws ce get-anomaly-subscriptions --region us-east-1 \
  --query 'AnomalySubscriptions[?SubscriptionName==`Default-Services-Subscription`]|[0].SubscriptionArn' \
  --output text)

aws ce update-anomaly-subscription --region us-east-1 \
  --subscription-arn "$SUB_ARN" \
  --subscribers "[{\"Type\":\"EMAIL\",\"Address\":\"$EMAIL\",\"Status\":\"CONFIRMED\"}]" \
  --threshold-expression '{
    "And": [
      {"Dimensions":{"Key":"ANOMALY_TOTAL_IMPACT_ABSOLUTE","MatchOptions":["GREATER_THAN_OR_EQUAL"],"Values":["25.0"]}},
      {"Dimensions":{"Key":"ANOMALY_TOTAL_IMPACT_PERCENTAGE","MatchOptions":["GREATER_THAN_OR_EQUAL"],"Values":["40.0"]}}
    ]
  }'

# `--subscribers` REPLACES the list — to keep the old address as well, pass both entries.
# Verify (the only proof the update took):
aws ce get-anomaly-subscriptions --region us-east-1 \
  --query 'AnomalySubscriptions[].{Subs:Subscribers,Threshold:ThresholdExpression}' --output json

# 2c. ONLY if step 2 returned no subscription at all, create one: ─────────────────────────────

aws ce create-anomaly-subscription --region us-east-1 \
  --anomaly-subscription "{
    \"SubscriptionName\": \"credence-prod-anomaly-daily\",
    \"MonitorArnList\": [\"$MONITOR_ARN\"],
    \"Subscribers\": [{\"Type\":\"EMAIL\",\"Address\":\"$EMAIL\",\"Status\":\"CONFIRMED\"}],
    \"Frequency\": \"DAILY\",
    \"ThresholdExpression\": {
      \"Dimensions\": {
        \"Key\": \"ANOMALY_TOTAL_IMPACT_ABSOLUTE\",
        \"MatchOptions\": [\"GREATER_THAN_OR_EQUAL\"],
        \"Values\": [\"25\"]
      }
    }
  }"
```

### 4. Vercel spend notification  ▸ VERCEL DASHBOARD (no CLI)

Vercel has no API for this — it is dashboard-only.

1. **vercel.com** → your team → **Settings** → **Billing** → **Spend Management**.
2. Set **Spend Amount** to **`$60`**. Rationale: the model puts us at $20 (the seat) up to ~250k
   monthly visitors and ~$41 at 500k, so $60 is comfortably above any organic outcome and still
   catches a genuine surprise early.
3. Enable the **email notification** at that amount.
4. ⛔ **Do NOT enable "Pause Production Deployment" as the spend-management action.** It takes the
   *site* down to save money — an outage triggered by a billing threshold, which is strictly worse
   than the overage it prevents and precisely the failure this project's degrade switch exists to
   avoid. Notification only; the operator decides what to do.
5. Also worth setting: **Settings → Billing → Usage Alerts** for **Edge Requests**, the quota that
   binds first (§4 of the cost model).

### 5. The degrade kill switch (what to do when an alarm fires)  ▸ LAPTOP

```bash
# ON — serve only the cached/static floor; the expensive personalized endpoints answer 503.
# ⚠️ update-function-configuration REPLACES the whole Variables map — read the current env first
#    and re-send everything, or you will wipe every other setting on the function.
aws lambda get-function-configuration --function-name credence-prod-lambda-api \
  --region us-east-1 --query 'Environment.Variables' > /tmp/lambda-env.json

python3 - <<'PY'
import json
env = json.load(open('/tmp/lambda-env.json'))
env['COST_DEGRADE_MODE'] = '1'          # '0' or remove the key to turn it back OFF
json.dump({'Variables': env}, open('/tmp/lambda-env-new.json','w'))
PY

aws lambda update-function-configuration --function-name credence-prod-lambda-api \
  --region us-east-1 --environment file:///tmp/lambda-env-new.json

# ⚠️ WAIT FOR PROPAGATION BEFORE CURLING. `update-function-configuration` RETURNS IMMEDIATELY with
#    `"LastUpdateStatus": "InProgress"`; a curl fired before it flips to `Successful` hits the OLD
#    env and reports the pre-flip behaviour. Poll until Successful:
aws lambda get-function-configuration --function-name credence-prod-lambda-api --region us-east-1 \
  --query '{degrade:Environment.Variables.COST_DEGRADE_MODE,status:LastUpdateStatus}'

# (a) THE FLOOR STAYS UP — anonymous, no token required:
curl -si https://api.credencesports.com/fantasy/nfl/track-record/manifest | head -1  # expect 200
curl -si https://api.credencesports.com/subscription/public-pricing | head -1        # expect 200

# (b) THE DENIAL — ⛔ REQUIRES A REAL BEARER TOKEN. Sign in at www.credencesports.com, open
#     devtools → Network, click any API call, copy the `authorization` request header value.
TOKEN='eyJ...'
curl -si -H "Authorization: Bearer $TOKEN" \
  https://api.credencesports.com/performance/summary | head -1                       # expect 503

# OFF — remove the key (absent == off; `degrade_mode_enabled` reads it per request).
python3 - <<'PY'
import json
env = json.load(open('/tmp/lambda-env.json'))
env.pop('COST_DEGRADE_MODE', None)
json.dump({'Variables': env}, open('/tmp/lambda-env-off.json','w'))
PY
aws lambda update-function-configuration --function-name credence-prod-lambda-api \
  --region us-east-1 --environment file:///tmp/lambda-env-off.json
```

⛔⛔ **AN UNAUTHENTICATED CURL CANNOT DEMONSTRATE THE 503, AND ITS `401` READS EXACTLY LIKE SUCCESS —
this block prescribed precisely that broken check until 2026-08-08.** The original line was a bare
`curl .../performance/summary` expecting 503. That path has **no explicit API Gateway route**, so it
falls to `ANY /{proxy+}`, which carries the Cognito JWT authorizer (NF3.2) — **the gateway rejects it
with 401 before the Lambda is ever invoked, degrade mode on or off.** A `401` is a blocked-looking
status on an endpoint you expected to be blocked, so the check passes the eye test while measuring
nothing about the flag. It is the repo's vacuous-guard class (NF1.7 (a) / INC-38) in an operator
runbook rather than in a test.

⭐ **AND IT IS NOT INCIDENTAL — IT IS STRUCTURAL, BECAUSE THE TWO ALLOWLISTS COINCIDE BY DESIGN.**
Cross-check the 13 `--authorization-type NONE` routes above against `_DEGRADE_ALLOWED_PREFIXES` in
`app/backend/services/cost_guardrails.py`: **every single public route is degrade-allowlisted.** That
is the correct product outcome — degrade mode is *defined* as "keep exactly the anonymous free floor
up" — but it has a verification consequence that is easy to miss: **there is no anonymous request
that degrade mode refuses**, so the switch's denial half is unobservable without a valid token, and
any token-free smoke of it can only ever produce a false pass. Anonymous curls verify the *floor*
(a); only an authenticated one verifies the *denial* (b). Both halves are needed — (a) alone cannot
distinguish "degrade is working" from "degrade never turned on."

🪤 **AND IT HAS ALREADY BEEN RELIED ON, THE SAME MORNING, BY A DIFFERENT SESSION.** The E9.46
carry-over fix (`4b74506f`, 09:25Z 2026-08-08) ruled the kill switch out of a live prod diagnosis
with: *"degrade mode is OFF (a non-floor public path returns 200)."* There is **no such thing as a
non-floor public path** — the two allowlists coincide — so that observation is equally consistent
with degrade being ON. The conclusion happened to be correct (the flag was not flipped until 09:32Z)
but the inference was not, and it was one of four bullets eliminating causes on a P1. ⇒ **to
establish the flag's state, READ THE FLAG** — `aws lambda get-function-configuration … --query
'Environment.Variables.COST_DEGRADE_MODE'` — never infer it from a 200 on any anonymous route.

Rate-limit tuning knobs on the same function (all optional; defaults in
`app/backend/services/cost_guardrails.py`): `COST_RL_PUBLIC_BURST` (30),
`COST_RL_PUBLIC_PER_SECOND` (0.5), `COST_RL_AUTH_BURST` (60), `COST_RL_AUTH_PER_SECOND` (2.0).

⚠️⚠️ **THE CDN COLLAPSES EVERY ANONYMOUS VISITOR ONTO A HANDFUL OF VERCEL EGRESS IPs, AND THE
PER-IP LIMITER SEES THOSE, NOT THE VISITORS.** Once the front-end half deploys (`dev` → `main`), an
anonymous cache MISS reaches us as browser → Vercel CDN → Vercel function → API Lambda, so the
Lambda's `sourceIp` is Vercel's, and **all CDN-origin traffic shares ONE bucket**. This is a direct
consequence of the CDN design and it is the one interaction that could make the two guardrails fight
each other: throttle the CDN and the board goes stale or blank for *everyone*, which is exactly the
outage the degrade switch exists to avoid.

The arithmetic says it is comfortable, and — the part that matters — **it does not get worse as
traffic grows**: cache misses are bounded by `(TTL windows × cache keys × POPs)`, ≈0.1 req/s
sustained against the 0.5/s allowance, and that ceiling is independent of visitor count. The
residual risk is a burst, not a trend: a simultaneous multi-POP expiry can spend the burst-30.

**Watch for it right after the front-end deploys:** errors from `/api/public/*` (the route surfaces
an upstream 429 as a 502) or `ThrottleCount` rising with no matching visitor spike. **The fix is one
env var and no code deploy** — set `COST_RL_PUBLIC_PER_SECOND=2.0` via the §5 procedure. Do NOT
"fix" it by having the CDN route forward the visitor's IP: that value is caller-controlled and
trusting it re-opens the spoofing bypass the limiter's IP-precedence order exists to close.

⚠️ These are **not** in `env.required` on purpose — every one has a safe in-code default, and adding
a required key means the next deploy FAILS until the box `.env` is hand-edited (the recurring
one-logical-thing-many-owners trap). `COST_DEGRADE_MODE` unset simply means "off".

### 6. Live smoke — the part CI cannot prove  ▸ LAPTOP, AFTER `deploy.sh`

CI mocks all IO, so neither the throttle nor the degrade flag is provable in the merge gate.

✅ **RUN AGAINST PROD 2026-08-08, backend half PASSED** — results inline below.

🔴 **THE FRONT-END HOST IS `www.credencesports.com`. THE APEX `credencesports.com` DOES NOT RESOLVE**
(measured: curl exit 6, `000`). An earlier draft of this section used the apex and the CDN check
appeared to fail for a reason that had nothing to do with the route. The API host
(`api.credencesports.com`) is unaffected.

⚠️ **THE TWO HALVES DEPLOY SEPARATELY AND THE CDN CHECK NEEDS THE FRONT-END HALF.** `deploy.sh`
ships the API from whatever is checked out; the Next front end deploys to PRODUCTION only from
`main`. A commit merged to `dev` therefore has a live backend and no `/api/public/*` route — that
path 404s until `dev` → `main` lands. This is the safe direction (the deployed front end still calls
the API directly, and the backend change is purely additive), but do not read the 404 as a defect.

⚠️ **THE `dev` PREVIEW URL CANNOT BE CURLED.** Vercel Deployment Protection 302s every path to
`vercel.com/sso-api`, so a shell check sees the SSO redirect's headers (`no-store`), never the
route's. Either open the URL in a logged-in browser and read DevTools → Network, or mint a
**Protection Bypass for Automation** secret (Project → Settings → Deployment Protection) and pass
`-H "x-vercel-protection-bypass: <secret>"`.

```bash
# (a) The per-IP limit engages and returns an honest 429 with Retry-After.
for i in $(seq 1 60); do
  curl -s -o /dev/null -w "%{http_code} " https://api.credencesports.com/fantasy/nfl/track-record/manifest
done; echo
# Expect: 200s, then 429s. Confirm the headers on a throttled one:
curl -si https://api.credencesports.com/fantasy/nfl/track-record/manifest \
  -H 'Origin: https://credencesports.com' | grep -iE 'HTTP/|retry-after|access-control-allow-origin|cache-control'
# ⭐ access-control-allow-origin MUST be present on the 429 — without it the browser sees an
#    opaque network error instead of a throttle, and the frontend cannot tell them apart.
#
#   MEASURED 2026-08-08 (prod): 33 × 200, then 429s with occasional 200s interleaved.
#     HTTP/2 429 · retry-after: 2 · cache-control: no-store
#     access-control-allow-origin: https://www.credencesports.com     ← the ordering property, live
#   ⭐ The interleaved 200s are the REFILL, not a leak: 0.5 tokens/s = one request per 2 s, which is
#     exactly what `retry-after: 2` advertises. A run of unbroken 429s would mean the bucket was not
#     refilling and legitimate callers would be locked out until the container cycled.

# (b) Cache headers are entitlement-keyed.
curl -si https://api.credencesports.com/fantasy/nfl/track-record/manifest | grep -i 'cache-control\|vary'
#   expect: public, s-maxage=3600, stale-while-revalidate=86400   +   Vary: ... Authorization
curl -si https://api.credencesports.com/fantasy/nfl/track-record/manifest \
  -H 'Authorization: Bearer anything' | grep -i 'cache-control'
#   expect: private, no-store    ← a token must NEVER produce a shared-cacheable response
#
#   MEASURED 2026-08-08 (prod), both PASS:
#     anonymous → cache-control: public, s-maxage=3600, stale-while-revalidate=86400 · vary: Authorization
#     +Bearer  → cache-control: private, no-store                                    · vary: Authorization

# (c) The CDN read path really is cached. ⚠️ `www.`, not the apex — and only after dev → main.
curl -si https://www.credencesports.com/api/public/featured | grep -iE 'HTTP/|cache-control|x-vercel-cache'
curl -si https://www.credencesports.com/api/public/featured | grep -i 'x-vercel-cache'   # expect HIT
#   a 404 here means the front-end half has not deployed yet (see the warning above), not a bug
#
# ✅ VERIFIED 2026-08-08, and 🔴 THE RESULT LOOKS LIKE A FAILURE UNTIL YOU READ IT PROPERLY:
#
#     hit 1:  200  age: 322  cache-control: public   x-vercel-cache: STALE
#     hit 2:  200  age: 0    cache-control: public   x-vercel-cache: HIT
#     hit 3:  200  age: 2    cache-control: public   x-vercel-cache: HIT
#
# ⚠️ `cache-control: public` — WITHOUT the s-maxage / stale-while-revalidate we set. Do NOT read
#    that as "the header was ignored." Vercel CONSUMES both directives for its own edge cache and
#    STRIPS them from the client-facing response, which is exactly the behaviour we want: the CDN
#    holds the copy, the browser does not hold a stale one.
#
# ⭐ THE PROOF THE TTL IS REALLY HONOURED IS `age` CROSSING `s-maxage`, NOT THE HEADER. Hit 1 was
#    age 322 against s-maxage 300 ⇒ past freshness ⇒ served STALE while revalidating in the
#    background (inside the 900s SWR window); hit 2 then returned age 0, the revalidated object.
#    A cache that ignored the directives would have no notion of "stale" at 322 seconds, so this
#    transition — and not a bare HIT — is what actually verifies the configuration.
#
# ⏳ AND THE CONSEQUENCE FOR ANYONE DEBUGGING AN UPSTREAM FIX: a change to the underlying payload
#    can take up to s-maxage + SWR to appear (≈20 min for `/picks/featured`). Bypass with a unique
#    query string — `?nocache=$RANDOM` — before concluding a fix did not land.
#
# Payload fidelity was checked the same way and is byte-identical to the direct API read, which is
# the property that matters here: the route is a pass-through, not a transform.

# (d) Then exercise §5 above: flip the degrade flag on, WAIT for LastUpdateStatus=Successful, then
#     confirm BOTH halves — the anonymous floor still 200s AND an authenticated (real bearer token)
#     call to /performance/summary 503s — then flip it back OFF and re-confirm the 200s.
#     ⛔ A token-free curl of /performance/summary is NOT the denial half: it 401s at the gateway
#        either way. See the warning under §5 — that false pass has already been shipped once.
```

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
