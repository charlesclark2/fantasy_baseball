#!/usr/bin/env bash
# =============================================================================
# E9.9 / A0.6 — provision the qualified-plays notification pipeline.
#
#   OPERATOR-RUN from a laptop with AWS admin creds (Claude does NOT run this).
#   Idempotent where AWS allows. Region us-east-1 (SES/SNS live there).
#
# Creates / wires:
#   1. SNS topic  credence-prod-qualified-bets-today  (predict_today publishes here)
#   2. Lambda role credence-push-sender-lambda-role   (Dynamo r/w + SES send + SNS publish[SMS] + logs)
#   3. Lambda     push-notification-sender            (SNS-triggered fan-out; bundles pywebpush)
#   4. SNS → Lambda subscription + invoke permission
#   5. box instance-role grant                        (sns:Publish on the topic + DynamoDB PutItem on serving cache)
#
# PREREQS (do these first):
#   • uv run python services/notifications/push_sender/gen_vapid.py   → VAPID keys
#   • SES: alerts@credencesports.com verified (SES already in PRODUCTION, 50k/day)
#
# Usage:
#   VAPID_PRIVATE_KEY="$(cat vapid_private.pem)" \
#   VAPID_SUBJECT="mailto:support@credencesports.com" \
#   SES_FROM_ADDRESS="alerts@credencesports.com" \
#     ./services/notifications/provision-notifications.sh
# =============================================================================
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC_NAME="${TOPIC_NAME:-credence-prod-qualified-bets-today}"
LAMBDA_NAME="${LAMBDA_NAME:-push-notification-sender}"
LAMBDA_ROLE="${LAMBDA_ROLE:-credence-push-sender-lambda-role}"
SUBS_TABLE="${DYNAMO_PUSH_SUBSCRIPTIONS_TABLE:-credence-prod-dynamo-push-subscriptions}"
SERVING_CACHE_TABLE="${SERVING_CACHE_TABLE:-credence-prod-serving-cache}"
BOX_ROLE_NAME="${BOX_ROLE_NAME:-credence-dagster-ec2-role}"
# Dagster box facts (aws_resources.md §EC2 / BOX_OPERATIONS.md). predict_today runs here.
BOX_INSTANCE_ID="${BOX_INSTANCE_ID:-i-07594af1679f81c38}"
BOX_REGION="${BOX_REGION:-us-east-1}"
BOX_ENV_PATH="${BOX_ENV_PATH:-/home/ec2-user/app/services/dagster/aws/.env}"
BOX_DEPLOY_SH="${BOX_DEPLOY_SH:-/home/ec2-user/app/services/dagster/aws/deploy.sh}"
APP_URL="${APP_URL:-https://www.credencesports.com}"
SES_FROM_ADDRESS="${SES_FROM_ADDRESS:-alerts@credencesports.com}"
VAPID_SUBJECT="${VAPID_SUBJECT:-mailto:support@credencesports.com}"
VAPID_PRIVATE_KEY="${VAPID_PRIVATE_KEY:?set VAPID_PRIVATE_KEY (PEM from gen_vapid.py)}"

ACCT="$(aws sts get-caller-identity --query Account --output text)"
HERE="$(cd "$(dirname "$0")" && pwd)"
say() { echo "[provision-notif] $*"; }

# --- 1. SNS topic -----------------------------------------------------------
TOPIC_ARN="$(aws sns create-topic --region "$REGION" --name "$TOPIC_NAME" --query TopicArn --output text)"
say "topic: $TOPIC_ARN"

# --- 2. Lambda role ---------------------------------------------------------
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --role-name "$LAMBDA_ROLE" --assume-role-policy-document "$TRUST" 2>/dev/null \
  && say "created lambda role $LAMBDA_ROLE" || say "lambda role $LAMBDA_ROLE exists"
aws iam attach-role-policy --role-name "$LAMBDA_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
aws iam put-role-policy --role-name "$LAMBDA_ROLE" --policy-name credence-push-sender-access \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:Scan\",\"dynamodb:GetItem\",\"dynamodb:UpdateItem\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCT}:table/${SUBS_TABLE}\"},
    {\"Effect\":\"Allow\",\"Action\":[\"ses:SendEmail\",\"ses:SendRawEmail\"],\"Resource\":\"*\"},
    {\"Effect\":\"Allow\",\"Action\":\"sns:Publish\",\"Resource\":\"*\"}]}"
say "lambda role policies attached (SNS Publish=* is required for SMS — SNS SMS has no topic ARN)"
sleep 8  # role propagation

# --- 3. build + deploy the Lambda (bundle pywebpush for arm64) --------------
BUILD="$(mktemp -d)"
cp "$HERE/push_sender/handler.py" "$BUILD/"
# Two-pass cross-build (the Lambda is linux/arm64; this laptop is not):
#   1. install the full tree normally — this is the ONLY pass that can pull the
#      sdist-only `http-ece` (it has no wheel, so `--only-binary=:all:` rejects it).
#   2. force-reinstall ONLY `cryptography` (the one mandatory native package, Rust —
#      no pure fallback) with its linux/aarch64 wheel. `--no-deps` keeps this pass
#      scoped to cryptography so `--only-binary=:all:` doesn't touch http-ece.
# Everything else (pywebpush/py-vapid/http-ece/requests/urllib3/idna/certifi) is
# pure-python/noarch and runs as-is on the Lambda. charset-normalizer's native
# speedup, if present as a mac build, degrades to its bundled pure-python fallback.
say "installing deps (pass 1: full tree, native for THIS host)…"
pip install --quiet --upgrade -r "$HERE/push_sender/requirements.txt" --target "$BUILD" >/dev/null
say "installing deps (pass 2: swap cryptography for linux/aarch64)…"
# --upgrade is REQUIRED alongside --force-reinstall: without it, pip refuses to
# overwrite the existing (mac) cryptography dir under --target and silently leaves
# the wrong-arch binary in place.
pip install --quiet --upgrade --force-reinstall --no-deps \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 \
  --only-binary=:all: \
  cryptography==43.0.3 --target "$BUILD" >/dev/null
# Fail loudly if the swap didn't land a Linux/aarch64 binary (belt-and-suspenders).
RUST_SO="$(find "$BUILD/cryptography" -name '_rust*.so' | head -1)"
if [ -z "$RUST_SO" ] || ! file "$RUST_SO" | grep -qiE 'ELF.*(aarch64|arm)'; then
  echo "[provision-notif] FATAL: cryptography native lib is not Linux/aarch64 — Lambda would crash." >&2
  file "$RUST_SO" >&2 || true
  exit 1
fi
say "cryptography native lib OK: $(file "$RUST_SO" | cut -d: -f2- | sed 's/^ //')"
ZIP="$BUILD.zip"
( cd "$BUILD" && zip -qr "$ZIP" . )
say "package: $ZIP ($(du -h "$ZIP" | cut -f1))"

ENVVARS="Variables={DYNAMO_PUSH_SUBSCRIPTIONS_TABLE=$SUBS_TABLE,SES_FROM_ADDRESS=$SES_FROM_ADDRESS,VAPID_SUBJECT=$VAPID_SUBJECT,APP_URL=$APP_URL,VAPID_PRIVATE_KEY=$VAPID_PRIVATE_KEY}"
if aws lambda get-function --region "$REGION" --function-name "$LAMBDA_NAME" >/dev/null 2>&1; then
  aws lambda update-function-code --region "$REGION" --function-name "$LAMBDA_NAME" --zip-file "fileb://$ZIP" >/dev/null
  aws lambda wait function-updated --region "$REGION" --function-name "$LAMBDA_NAME"
  aws lambda update-function-configuration --region "$REGION" --function-name "$LAMBDA_NAME" \
    --timeout 60 --memory-size 256 --environment "$ENVVARS" >/dev/null
  say "lambda $LAMBDA_NAME updated"
else
  aws lambda create-function --region "$REGION" --function-name "$LAMBDA_NAME" \
    --runtime python3.12 --architectures arm64 --handler handler.lambda_handler \
    --role "arn:aws:iam::${ACCT}:role/${LAMBDA_ROLE}" \
    --timeout 60 --memory-size 256 --zip-file "fileb://$ZIP" --environment "$ENVVARS" >/dev/null
  say "lambda $LAMBDA_NAME created"
fi

# --- 4. SNS → Lambda subscription + invoke permission -----------------------
aws lambda add-permission --region "$REGION" --function-name "$LAMBDA_NAME" \
  --statement-id "${TOPIC_NAME}-invoke" --action lambda:InvokeFunction --principal sns.amazonaws.com \
  --source-arn "$TOPIC_ARN" 2>/dev/null || true
aws sns subscribe --region "$REGION" --topic-arn "$TOPIC_ARN" \
  --protocol lambda --notification-endpoint "arn:aws:lambda:${REGION}:${ACCT}:function:${LAMBDA_NAME}" >/dev/null
say "SNS $TOPIC_NAME → Lambda $LAMBDA_NAME wired"

# --- 5. box instance-role grants (predict_today publishes + claims idempotency) ---
aws iam put-role-policy --role-name "$BOX_ROLE_NAME" --policy-name credence-qualified-bets-publish \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":\"sns:Publish\",\"Resource\":\"$TOPIC_ARN\"},
    {\"Effect\":\"Allow\",\"Action\":\"dynamodb:PutItem\",\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCT}:table/${SERVING_CACHE_TABLE}\"}]}"
say "box role $BOX_ROLE_NAME: sns:Publish + serving-cache PutItem (per-day alert idempotency claim)"

# Auto-set the box env var + kick a redeploy unless SKIP_BOX_WIRING=1.
if [ "${SKIP_BOX_WIRING:-0}" != "1" ]; then
  say "wiring the box (instance $BOX_INSTANCE_ID, region $BOX_REGION)…"
  # c) set QUALIFIED_BETS_SNS_TOPIC_ARN in the box .env (idempotent: strip any prior line first)
  CID_ENV="$(aws ssm send-command --region "$BOX_REGION" --instance-ids "$BOX_INSTANCE_ID" \
    --document-name AWS-RunShellScript --comment "E9.9 set qualified-bets topic" \
    --parameters "commands=[\"sudo -u ec2-user -H bash -lc 'sed -i /^QUALIFIED_BETS_SNS_TOPIC_ARN=/d $BOX_ENV_PATH && echo QUALIFIED_BETS_SNS_TOPIC_ARN=$TOPIC_ARN >> $BOX_ENV_PATH'\"]" \
    --query 'Command.CommandId' --output text)"
  say "  SSM set-env CommandId=$CID_ENV"
  # d) redeploy so the box runs the --notify code + recreates containers with the new env
  CID_DEP="$(aws ssm send-command --region "$BOX_REGION" --instance-ids "$BOX_INSTANCE_ID" \
    --document-name AWS-RunShellScript --comment "E9.9 redeploy for --notify hook" \
    --parameters "commands=[\"sudo -u ec2-user -H bash $BOX_DEPLOY_SH\"],executionTimeout=[\"1800\"]" \
    --query 'Command.CommandId' --output text)"
  say "  SSM deploy CommandId=$CID_DEP  (deploy.sh pulls main + up -d --build; ~10-15 min)"
  say "  ⚠️ deploy.sh pulls MAIN — merge this branch to main FIRST, or the --notify code won't be on the box."
fi

cat <<EOF

============================================================================
✅ notifications provisioned.
   SNS topic:  $TOPIC_ARN
   Lambda:     $LAMBDA_NAME  (region $REGION)
   Box:        $BOX_INSTANCE_ID / $BOX_REGION  ($BOX_ENV_PATH)

REMAINING manual steps:

1. Merge this branch to main so the box's deploy.sh pulls the --notify code.
   (If you ran with SKIP_BOX_WIRING=1, also run steps c/d below by hand.)

2. Frontend: set NEXT_PUBLIC_VAPID_PUBLIC_KEY (printed by gen_vapid.py) in Vercel → redeploy.

3. TEST end-to-end (opt in on a real account first, then force a message):
   aws sns publish --region $REGION --topic-arn $TOPIC_ARN --message \\
     '{"date":"$(date +%F)","n_qualified":2,"plays":[{"matchup":"NYY @ BOS","pick":"Over 8.5"},{"matchup":"LAD @ SF","pick":"LAD ML"}]}'
   → confirm push <5 min / email <10 min.

--- the box commands the script auto-ran (for reference / SKIP_BOX_WIRING=1) --------
  c) set the topic env var:
     aws ssm send-command --region $BOX_REGION --instance-ids $BOX_INSTANCE_ID \\
       --document-name AWS-RunShellScript --parameters \\
       "commands=[\"sudo -u ec2-user -H bash -lc 'sed -i /^QUALIFIED_BETS_SNS_TOPIC_ARN=/d $BOX_ENV_PATH && echo QUALIFIED_BETS_SNS_TOPIC_ARN=$TOPIC_ARN >> $BOX_ENV_PATH'\"]"
  d) redeploy (pulls main + up -d --build):
     aws ssm send-command --region $BOX_REGION --instance-ids $BOX_INSTANCE_ID \\
       --document-name AWS-RunShellScript --parameters \\
       "commands=[\"sudo -u ec2-user -H bash $BOX_DEPLOY_SH\"],executionTimeout=[\"1800\"]"

NOTE: SMS via SNS may require moving SNS SMS out of the sandbox (production access)
+ a monthly spend limit; US A2P 10DLC registration applies for reliable delivery.
============================================================================
EOF
