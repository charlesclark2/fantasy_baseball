#!/usr/bin/env bash
# E9.9 / A0.6 — grant the API Lambda role (and the local-dev IAM user) DynamoDB
# access on the notification-preferences table `credence-prod-dynamo-push-subscriptions`.
# The /alerts/* endpoints (app/backend/routers/alerts.py) do GetItem + PutItem; the
# API Lambda role was never granted the table, so opting in 500s with AccessDenied.
#
# Idempotent: re-running overwrites the inline policy. IAM changes are LIVE — no
# Lambda redeploy needed. Run with IAM-admin creds (e.g. AWS_PROFILE=default).
#
#   ./infrastructure/dynamo/grant_alerts_iam.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
LAMBDA_FN="${LAMBDA_FN:-credence-prod-lambda-api}"
DEV_USER="${DEV_USER:-baseball-access-user}"
TABLE="${DYNAMO_PUSH_SUBSCRIPTIONS_TABLE:-credence-prod-dynamo-push-subscriptions}"

ARN="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}"
echo "Account: ${ACCOUNT}  Region: ${REGION}  Table: ${TABLE}"

RW_DOC=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "PushSubscriptionsReadWrite",
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
    "Resource": ["${ARN}"]
  }]
}
JSON
)

# ── API Lambda execution role (discovered from the function) ─────────────────
ROLE_ARN="$(aws lambda get-function --function-name "${LAMBDA_FN}" --query 'Configuration.Role' --output text)"
ROLE_NAME="${ROLE_ARN##*/}"
echo "Attaching read/write to Lambda role ${ROLE_NAME} ..."
aws iam put-role-policy --role-name "${ROLE_NAME}" \
  --policy-name credence-dynamo-push-subscriptions-rw --policy-document "${RW_DOC}"

# ── local-dev IAM user (uvicorn against real Dynamo) ─────────────────────────
if aws iam get-user --user-name "${DEV_USER}" >/dev/null 2>&1; then
  echo "Attaching read/write to IAM user ${DEV_USER} ..."
  aws iam put-user-policy --user-name "${DEV_USER}" \
    --policy-name credence-dynamo-push-subscriptions-rw --policy-document "${RW_DOC}"
else
  echo "ℹ️  IAM user ${DEV_USER} not found — skipped (only needed for local dev)."
fi

echo "Done. IAM is live immediately — no Lambda redeploy needed."
