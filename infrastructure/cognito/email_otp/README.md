# Cognito email-OTP sign-in (G100-C0)

Passwordless sign-in with a 6-digit code emailed via SES. This is the **second door** into
the product — before it, Google was the only self-serve way in, which excluded every
email-first visitor. See `handler.py` for the mechanism and the three hazards it closes.

Native email/**password** signup stays permanently closed (the pool has no email
auto-verification — `infrastructure/aws_resources.md`). An emailed code needs no separate
verification step, which is exactly why it works where a password form cannot.

All commands below run on the **LAPTOP** (AWS CLI). Pool `us-east-1_gG9zMbwQt`.

> ⚠️ **Set the region first.** The pool is in `us-east-1`, but a shell configured for the
> lakehouse defaults to `us-east-2` (the artifacts bucket), which makes every command here
> fail with `ResourceNotFoundException: … does not exist`. Use a fresh shell (and flip back
> before any S3/DuckDB `us-east-2` work):
> ```bash
> export AWS_DEFAULT_REGION=us-east-1
> ```

---

## One-time setup (operator)

### 1. Execution role

The function needs **SES send only**. It deliberately has no `cognito-idp` permissions: the
triggers are invoked *by* Cognito and mutate nothing.

```bash
cat > /tmp/emailotp-trust.json <<'JSON'
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole" } ] }
JSON

aws iam create-role \
  --role-name credence-prod-cognito-email-otp-role \
  --assume-role-policy-document file:///tmp/emailotp-trust.json

aws iam attach-role-policy \
  --role-name credence-prod-cognito-email-otp-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

cat > /tmp/emailotp-policy.json <<'JSON'
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow",
    "Action": ["ses:SendEmail"],
    "Resource": [
      "arn:aws:ses:us-east-1:769392325318:identity/credencesports.com",
      "arn:aws:ses:us-east-1:769392325318:configuration-set/credence-prod-ses-config"
    ] } ] }
JSON

aws iam put-role-policy \
  --role-name credence-prod-cognito-email-otp-role \
  --policy-name email-otp-ses \
  --policy-document file:///tmp/emailotp-policy.json
```

### 2. Create the function

```bash
./infrastructure/cognito/email_otp/deploy.sh --dry-run   # build the zip + import smoke test

ROLE_ARN=$(aws iam get-role --role-name credence-prod-cognito-email-otp-role \
  --query 'Role.Arn' --output text)

aws lambda create-function \
  --function-name credence-prod-cognito-email-otp \
  --runtime python3.12 \
  --handler handler.handler \
  --role "$ROLE_ARN" \
  --zip-file fileb://infrastructure/cognito/email_otp/.build/deployment.zip \
  --timeout 10 --region us-east-1 \
  --environment 'Variables={OTP_FROM_ADDRESS=noreply@credencesports.com,SES_CONFIGURATION_SET=credence-prod-ses-config,OTP_TTL_MINUTES=15}'
```

### 3. Let Cognito invoke it

```bash
POOL_ARN=$(aws cognito-idp describe-user-pool --user-pool-id us-east-1_gG9zMbwQt \
  --region us-east-1 --query 'UserPool.Arn' --output text)

aws lambda add-permission \
  --function-name credence-prod-cognito-email-otp \
  --statement-id cognito-customauth-invoke \
  --action lambda:InvokeFunction \
  --principal cognito-idp.amazonaws.com \
  --source-arn "$POOL_ARN" \
  --region us-east-1
```

### 4. Wire all THREE triggers on the pool

Console → Cognito → user pool `us-east-1_gG9zMbwQt` → **User pool properties → Lambda
triggers**, set all three to `credence-prod-cognito-email-otp`:

- **Define auth challenge**
- **Create auth challenge**
- **Verify auth challenge response**

⚠️ **All three, or the flow silently half-works.** Missing *Create* means no code is ever
sent; missing *Verify* means every code is rejected. Both present as "the code doesn't
work", with nothing in the API logs — the Lambda is invoked by Cognito, not by us.

> ⚠️ Prefer the Console: `update-user-pool` **replaces** the whole config, so a CLI call
> that omits the existing **Pre sign-up** trigger would silently unwire E9.7/G100-C0's
> account linking and start splitting every new Google user into two accounts.

### 5. Allow the CUSTOM_AUTH flow on the app client

```bash
aws cognito-idp describe-user-pool-client \
  --user-pool-id us-east-1_gG9zMbwQt \
  --client-id 1qh95e78bd7g6ipqcvdcpf7ou6 \
  --region us-east-1 --query 'UserPoolClient.ExplicitAuthFlows'
```

`ALLOW_CUSTOM_AUTH` must be present. ⚠️ `update-user-pool-client` is also a **full
replace** — pass back every flow the describe returned, plus `ALLOW_CUSTOM_AUTH`, or the
Google/password flows break. Doing it in the Console avoids that entirely.

Also set **Authentication flow session duration** to **15 minutes** (`AuthSessionValidity`).
That is the real expiry of an emailed code; the email says "15 minutes", so if this is left
at the 3-minute default the email tells the user something the system will not honour.

### 6. Extend the PreSignUp role for pre-provisioning

G100-C0's PreSignUp change creates a native user for a brand-new federated sign-in, so that
role needs two more actions:

```bash
POOL_ARN=$(aws cognito-idp describe-user-pool --user-pool-id us-east-1_gG9zMbwQt \
  --region us-east-1 --query 'UserPool.Arn' --output text)
cat > /tmp/presignup-policy.json <<JSON
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow",
    "Action": ["cognito-idp:ListUsers", "cognito-idp:AdminLinkProviderForUser",
               "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword"],
    "Resource": "${POOL_ARN}" } ] }
JSON

aws iam put-role-policy \
  --role-name credence-prod-cognito-presignup-link-role \
  --policy-name presignup-link-cognito \
  --policy-document file:///tmp/presignup-policy.json

./infrastructure/cognito/presignup_link/deploy.sh
```

Without the grant the trigger **fails open** — Google sign-in keeps working exactly as it
does today, it just keeps producing federated-only accounts (which cannot use OTP). So a
missed grant is a silent no-op, not an outage: check CloudWatch for
`presignup-link: pre-provision failed`.

### 7. Grant the API Lambda the admin auth actions

`app/backend/routers/email_otp.py` drives the challenge server-side.

```bash
cat > /tmp/api-otp-policy.json <<'JSON'
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow",
    "Action": ["cognito-idp:ListUsers", "cognito-idp:AdminCreateUser",
               "cognito-idp:AdminSetUserPassword", "cognito-idp:AdminInitiateAuth",
               "cognito-idp:AdminRespondToAuthChallenge"],
    "Resource": "arn:aws:cognito-idp:us-east-1:769392325318:userpool/us-east-1_gG9zMbwQt" } ] }
JSON

aws iam put-role-policy \
  --role-name credence-prod-lambda-execution-role \
  --policy-name email-otp-cognito \
  --policy-document file:///tmp/api-otp-policy.json
```

### 8. Open the two API-Gateway routes (NF3.2 — the step that is always forgotten)

A router with no `Depends()` is **not** a public route: the JWT authorizer sits in front of
the Lambda and answers 401 before FastAPI is reached.

```bash
for RK in "POST /auth/email-otp/start" "POST /auth/email-otp/verify"; do
  aws apigatewayv2 create-route \
    --api-id 8dhmehjak7 --region us-east-1 \
    --route-key "$RK" \
    --target "integrations/p093jnh" \
    --authorization-type NONE
done
```

Then prove it from outside — the only real verification, since CI mocks all IO:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://api.credencesports.com/auth/email-otp/start \
  -H 'Content-Type: application/json' -d '{"email":"not-an-email"}'
# 400 = the route is reachable and FastAPI validated it.   401 = the authorizer is still on.
```

⚠️ **`400` is the pass here, not `200`.** A deliberately-invalid address is used so the
check cannot create an account or send mail as a side effect of testing reachability.

### 9. Deploy the API

```bash
./infrastructure/lambda/deploy.sh
```

⚠️ The API Lambda has **no CD**. `git push` deploys the frontend only.

---

## Acceptance test — the only one that counts

CI cannot see Cognito, SES, or the gateway. Run this live, in a **private window**, with an
address that has never touched the product:

1. `https://www.credencesports.com/signup` → "Email me a sign-in code" → enter the address.
2. The code arrives from `noreply@credencesports.com` within ~30s (check spam once).
3. Enter it → you land on `/dashboard`, signed in.
4. **The invariant:** sign out, then sign in with **Google** using that same address. You
   must land on the **same** account — one user in Cognito, not two:

```bash
aws cognito-idp list-users --user-pool-id us-east-1_gG9zMbwQt \
  --filter "email = \"<the address>\"" \
  --query 'Users[].{Username:Username,Status:UserStatus,Created:UserCreateDate}' --output table
```

Expect **exactly one row**, with a UUID username (not `google_…`). Two rows means the
linking did not happen — check CloudWatch for `presignup-link:`.

5. And the reverse order, with a second fresh address: Google first, then request an email
   code for the same address. It must send a **code** (not "use Google"), and again leave
   exactly one user.

---

## Known limitation — accounts created before this shipped

A person who signed in with Google **before** the pre-provisioning change has a federated
profile and no native user. Their `sub` owns their data and cannot be moved, so requesting
an email code for that address returns **"you already have an account with Google"** rather
than splitting them in two. They keep working exactly as they do today.

This set is closed and shrinking — every Google sign-in from the deploy onward gets a
native user. To count it:

```bash
aws cognito-idp list-users --user-pool-id us-east-1_gG9zMbwQt \
  --query 'Users[?starts_with(Username, `google_`)].{Username:Username,Created:UserCreateDate}' \
  --output table
```

⛔ **Do not "fix" one of these by deleting the federated profile** (the E9.7 README's
cleanup recipe). That recipe was written when the data lived on the *native* side; here it
is the reverse, and deleting takes the person's bets and leagues with it.

---

## Rollback

- **The email door:** revert the frontend; the routes become unreachable from the UI. To
  kill it server-side, delete the two gateway routes (they then 401).
- **Pre-provisioning:** `PRESIGNUP_PREPROVISION=0` — no redeploy.
  ```bash
  aws lambda update-function-configuration \
    --function-name credence-prod-cognito-presignup-link \
    --environment 'Variables={PRESIGNUP_PREPROVISION=0}' --region us-east-1
  ```
  Google sign-in immediately returns to producing plain federated accounts.

## Redeploying code changes

```bash
./infrastructure/cognito/email_otp/deploy.sh
```
