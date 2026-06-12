#!/usr/bin/env bash
# Grant DynamoDB access on the user-bets/users tables to the three principals that
# touch them (Performance redesign, stories B1/B2). Idempotent: re-running just
# overwrites the inline policies. Run with AWS creds that can manage IAM
# (e.g. AWS_PROFILE=default).
#
# Principals & least-privilege:
#   #1 Lambda role (B2 endpoints)            -> read/write
#   #3 baseball-access-user (Streamlit+local)-> read/write
#   #2 Dagster principal (settle op)         -> Scan + UpdateItem only
#
# The Dagster principal name isn't known to the repo (it's a Dagster Cloud secret),
# so pass it explicitly:  DAGSTER_PRINCIPAL=<name> [DAGSTER_PRINCIPAL_TYPE=user|role]
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
LAMBDA_FN="${LAMBDA_FN:-credence-prod-lambda-api}"
DEV_USER="${DEV_USER:-baseball-access-user}"
DAGSTER_PRINCIPAL="${DAGSTER_PRINCIPAL:-}"
DAGSTER_PRINCIPAL_TYPE="${DAGSTER_PRINCIPAL_TYPE:-user}"

BETS="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/credence-prod-dynamo-user-bets"
GSI="${BETS}/index/gsi-pending-by-game"
USERS="arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/credence-prod-dynamo-users"

echo "Account: ${ACCOUNT}  Region: ${REGION}"

RW_DOC=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "UserBetsReadWrite",
    "Effect": "Allow",
    "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query"],
    "Resource": ["${BETS}", "${GSI}", "${USERS}"]
  }]
}
JSON
)

SETTLE_DOC=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "UserBetsSettle",
    "Effect": "Allow",
    "Action": ["dynamodb:Scan", "dynamodb:UpdateItem"],
    "Resource": ["${BETS}", "${GSI}"]
  }]
}
JSON
)

# ── #3 baseball-access-user (Streamlit + local uvicorn dev) ──────────────────
echo "Attaching read/write to IAM user ${DEV_USER} ..."
aws iam put-user-policy --user-name "${DEV_USER}" \
  --policy-name credence-dynamo-user-bets-rw --policy-document "${RW_DOC}"

# ── #1 Lambda execution role (discovered from the function) ──────────────────
ROLE_ARN="$(aws lambda get-function --function-name "${LAMBDA_FN}" --query 'Configuration.Role' --output text)"
ROLE_NAME="${ROLE_ARN##*/}"
echo "Attaching read/write to Lambda role ${ROLE_NAME} ..."
aws iam put-role-policy --role-name "${ROLE_NAME}" \
  --policy-name credence-dynamo-user-bets-rw --policy-document "${RW_DOC}"

# ── #2 Dagster principal (settle op) ─────────────────────────────────────────
if [[ -n "${DAGSTER_PRINCIPAL}" ]]; then
  echo "Attaching settle (Scan+UpdateItem) to ${DAGSTER_PRINCIPAL_TYPE} ${DAGSTER_PRINCIPAL} ..."
  if [[ "${DAGSTER_PRINCIPAL_TYPE}" == "role" ]]; then
    aws iam put-role-policy --role-name "${DAGSTER_PRINCIPAL}" \
      --policy-name credence-dynamo-user-bets-settle --policy-document "${SETTLE_DOC}"
  else
    aws iam put-user-policy --user-name "${DAGSTER_PRINCIPAL}" \
      --policy-name credence-dynamo-user-bets-settle --policy-document "${SETTLE_DOC}"
  fi
else
  echo "⚠️  DAGSTER_PRINCIPAL not set — skipped settle grant (#2). The daily"
  echo "    settle_user_bets_op will keep failing until you run, e.g.:"
  echo "      DAGSTER_PRINCIPAL=<dagster-iam-user> $0"
fi

echo "Done."
