# Cognito PreSignUp auto-link trigger (E9.7)

Makes a **Google sign-in resolve to the existing native account with the same verified
email**, so one person = one Cognito `sub`. Without it, Google sign-in creates a separate
`Google_<sub>` user and the app (which keys bets/portfolio/alerts by `sub`) shows an empty
account. See `handler.py` for the mechanism.

All commands below run on the **LAPTOP** (AWS CLI, `us-east-1`). Pool `us-east-1_gG9zMbwQt`.

---

## One-time setup (operator)

### 1. Execution role
```bash
# Trust policy: Lambda may assume the role
cat > /tmp/presignup-trust.json <<'JSON'
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow", "Principal": { "Service": "lambda.amazonaws.com" },
    "Action": "sts:AssumeRole" } ] }
JSON

aws iam create-role \
  --role-name credence-prod-cognito-presignup-link-role \
  --assume-role-policy-document file:///tmp/presignup-trust.json

aws iam attach-role-policy \
  --role-name credence-prod-cognito-presignup-link-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Least-privilege: only ListUsers + AdminLinkProviderForUser on THIS pool
POOL_ARN=$(aws cognito-idp describe-user-pool --user-pool-id us-east-1_gG9zMbwQt \
  --query 'UserPool.Arn' --output text)
cat > /tmp/presignup-policy.json <<JSON
{ "Version": "2012-10-17", "Statement": [
  { "Effect": "Allow",
    "Action": ["cognito-idp:ListUsers", "cognito-idp:AdminLinkProviderForUser"],
    "Resource": "${POOL_ARN}" } ] }
JSON

aws iam put-role-policy \
  --role-name credence-prod-cognito-presignup-link-role \
  --policy-name presignup-link-cognito \
  --policy-document file:///tmp/presignup-policy.json
```

### 2. Create the function
```bash
# Build the zip first (handler-only; boto3 is in the runtime)
./infrastructure/cognito/presignup_link/deploy.sh --dry-run

ROLE_ARN=$(aws iam get-role --role-name credence-prod-cognito-presignup-link-role \
  --query 'Role.Arn' --output text)

aws lambda create-function \
  --function-name credence-prod-cognito-presignup-link \
  --runtime python3.12 \
  --handler handler.handler \
  --role "$ROLE_ARN" \
  --zip-file fileb://infrastructure/cognito/presignup_link/.build/deployment.zip \
  --timeout 10 --region us-east-1
```

### 3. Let Cognito invoke it
```bash
POOL_ARN=$(aws cognito-idp describe-user-pool --user-pool-id us-east-1_gG9zMbwQt \
  --query 'UserPool.Arn' --output text)

aws lambda add-permission \
  --function-name credence-prod-cognito-presignup-link \
  --statement-id cognito-presignup-invoke \
  --action lambda:InvokeFunction \
  --principal cognito-idp.amazonaws.com \
  --source-arn "$POOL_ARN" \
  --region us-east-1
```

### 4. Wire the trigger on the pool
Console → Cognito → user pool `us-east-1_gG9zMbwQt` → **User pool properties → Lambda
triggers → Pre sign-up** → select `credence-prod-cognito-presignup-link` → Save.

CLI equivalent (⚠️ `update-user-pool` **replaces** the whole config — include any triggers/
settings already set, or use the Console which merges):
```bash
FN_ARN=$(aws lambda get-function --function-name credence-prod-cognito-presignup-link \
  --query 'Configuration.FunctionArn' --output text)
# Prefer the Console unless you are certain of the full current pool config.
aws cognito-idp update-user-pool --user-pool-id us-east-1_gG9zMbwQt \
  --lambda-config "PreSignUp=${FN_ARN}"
```

---

## One-time cleanup for accounts that ALREADY have a duplicate Google user

Anyone who already clicked "Continue with Google" before this trigger existed now has a
separate `Google_<sub>` user. The trigger only links on the **first** federated sign-in,
so delete that duplicate — the next Google sign-in re-fires PreSignUp and links to the
native account. (Do this for `ctcb57@gmail.com` and any other tester.)

```bash
EMAIL="ctcb57@gmail.com"
# List users for the email — find the one whose Username starts with "Google_"
aws cognito-idp list-users --user-pool-id us-east-1_gG9zMbwQt \
  --filter "email = \"${EMAIL}\"" \
  --query 'Users[].Username' --output table

# Delete ONLY the Google_<...> duplicate (NOT the native username/password user)
aws cognito-idp admin-delete-user --user-pool-id us-east-1_gG9zMbwQt \
  --username "Google_XXXXXXXXXXXX"
```
Then sign in with Google again → it should land on the native account with your bets.

> Note: any bets logged **while** signed in as the duplicate are keyed to the duplicate's
> `sub` and are discarded with it. Confirm nothing important was logged under the duplicate
> before deleting (for `ctcb57@gmail.com` the bets are on the native account, so it's safe).

---

## Redeploying code changes
```bash
./infrastructure/cognito/presignup_link/deploy.sh
```

## Verify
After setup, sign in with Google using an email that has a native account → you land on the
existing account (bets visible), and Cognito shows **no** new `Google_<sub>` user (the
identity is linked to the native user instead). A brand-new email with no native account
still creates a normal federated user.
