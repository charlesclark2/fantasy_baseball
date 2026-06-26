#!/usr/bin/env bash
# Provision the DynamoDB serving-cache table (INC-16-P2 — replaces the Railway PG
# api_cache after the Railway workspace was restricted). Run once with AWS
# credentials that can create DynamoDB tables. Idempotent: if the table already
# exists the create-table call fails harmlessly and we just wait for ACTIVE.
#
# Naming follows infrastructure/aws_resources.md: credence-{env}-{service}-{descriptor}
#
#   AWS_PROFILE=default ./infrastructure/dynamo/create_serving_cache_table.sh
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ENV="${CREDENCE_ENV:-prod}"

TABLE="credence-${ENV}-serving-cache"

# Single-table, structured PK/SK (INC-16-P2 design):
#   pk (S) = namespace      = cache_key up to the first '/'  ("picks","team",…)
#   sk (S) = "{rest}#{date}" for date-scoped rows | "{rest}#PERMANENT" for permanent
# Point reads = GetItem(pk,sk); team-list = Query(pk="team"); picks/game purge =
# Query(pk="picks", begins_with "game/"); admin invalidate_today = a small Scan.
# value / is_permanent / updated_at / cache_date are non-key attributes (DynamoDB
# is schemaless beyond the key) → only pk + sk are declared here. No GSI needed.
echo "Creating ${TABLE} in ${REGION} ..."
aws dynamodb create-table \
  --region "${REGION}" \
  --table-name "${TABLE}" \
  --billing-mode PAY_PER_REQUEST \
  --attribute-definitions \
      AttributeName=pk,AttributeType=S \
      AttributeName=sk,AttributeType=S \
  --key-schema \
      AttributeName=pk,KeyType=HASH \
      AttributeName=sk,KeyType=RANGE \
  --tags Key=app,Value=credence Key=component,Value=serving-cache Key=incident,Value=INC-16 \
  || echo "create-table failed (likely already exists) — continuing to wait-for-ACTIVE"

echo "Waiting for ${TABLE} to become ACTIVE ..."
aws dynamodb wait table-exists --region "${REGION}" --table-name "${TABLE}"
echo "Done. Table ${TABLE} is ACTIVE."
echo
echo "Set SERVING_CACHE_TABLE=${TABLE} on the EC2 writer (.env) and the Lambda"
echo "backend if you override the default. IAM grants: see infrastructure/aws_resources.md."
