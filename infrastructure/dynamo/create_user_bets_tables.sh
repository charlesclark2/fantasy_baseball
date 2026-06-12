#!/usr/bin/env bash
# Provision the per-user bets/users DynamoDB tables (Performance page redesign, story B1).
# Run once with AWS credentials that can create DynamoDB tables. Idempotent-ish:
# create-table fails if the table already exists — that's fine, it means it's provisioned.
#
# Naming follows infrastructure/aws_resources.md: credence-{env}-{service}-{descriptor}
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ENV="${CREDENCE_ENV:-prod}"

USER_BETS_TABLE="credence-${ENV}-dynamo-user-bets"
USERS_TABLE="credence-${ENV}-dynamo-users"

echo "Creating ${USER_BETS_TABLE} in ${REGION} ..."
# Base table key: user_id (PK) + bet_id (SK) -> "get all of a user's bets" is a Query.
# Sparse GSI gsi-pending-by-game on pending_game_pk: only PENDING bets carry the
# pending_game_pk attribute, so the index contains only unsettled bets. The settle
# job queries it by game_pk; settling REMOVEs the attribute, dropping the row out.
aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${USER_BETS_TABLE}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
      AttributeName=user_id,AttributeType=S \
      AttributeName=bet_id,AttributeType=S \
      AttributeName=pending_game_pk,AttributeType=N \
  --key-schema \
      AttributeName=user_id,KeyType=HASH \
      AttributeName=bet_id,KeyType=RANGE \
  --global-secondary-indexes '[
    {
      "IndexName": "gsi-pending-by-game",
      "KeySchema": [
        {"AttributeName": "pending_game_pk", "KeyType": "HASH"},
        {"AttributeName": "bet_id", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"}
    }
  ]'

echo "Creating ${USERS_TABLE} in ${REGION} ..."
# Registry of app users; upserted on first authenticated request (login-sync, story B2).
aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${USERS_TABLE}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions AttributeName=user_id,AttributeType=S \
  --key-schema AttributeName=user_id,KeyType=HASH

echo "Waiting for tables to become ACTIVE ..."
aws dynamodb wait table-exists --region "${REGION}" --table-name "${USER_BETS_TABLE}"
aws dynamodb wait table-exists --region "${REGION}" --table-name "${USERS_TABLE}"
echo "Done. Tables ${USER_BETS_TABLE} and ${USERS_TABLE} are ACTIVE."
