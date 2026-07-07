#!/usr/bin/env bash
# E9.9 / A0.6 — provision the notification-preferences / push-subscriptions table.
# One item per user, keyed by the Cognito `sub` (attribute `user_id`). Managed by
# app/backend/routers/alerts.py. Run once with AWS creds that can create DynamoDB
# tables. Idempotent: if it already exists the create fails harmlessly and we just
# wait for ACTIVE.
#
#   AWS_PROFILE=default ./infrastructure/dynamo/create_push_subscriptions_table.sh
#
# After creating, grant the API Lambda role access:
#   ./infrastructure/dynamo/grant_alerts_iam.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
TABLE="${DYNAMO_PUSH_SUBSCRIPTIONS_TABLE:-credence-prod-dynamo-push-subscriptions}"

echo "Creating ${TABLE} in ${REGION} ..."
aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${TABLE}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions AttributeName=user_id,AttributeType=S \
  --key-schema AttributeName=user_id,KeyType=HASH \
  --tags Key=app,Value=credence Key=component,Value=push-subscriptions Key=story,Value=E9.9 \
  || echo "create-table failed (likely already exists) — continuing to wait-for-ACTIVE"

echo "Waiting for ${TABLE} to become ACTIVE ..."
aws dynamodb wait table-exists --region "${REGION}" --table-name "${TABLE}"
echo "Done. Table ${TABLE} is ACTIVE."
echo
echo "Next: ./infrastructure/dynamo/grant_alerts_iam.sh   (IAM for the API Lambda role)"
