#!/usr/bin/env bash
# =============================================================================
# INC-16-P1 — provision the AWS compute box for the Dagster re-host.
#
# Creates (in the DEFAULT VPC, public subnet — NO NAT gateway):
#   * a security group locked to the operator IP (SSH 22 + dagit 3000)
#   * an S3 GATEWAY VPC endpoint (free; keeps S3 traffic off any NAT)
#   * an IAM role + instance profile granting S3 access (DynamoDB added in P2)
#   * a t4g.medium (4 GB, arm64/Graviton) running cloud-init.sh, gp3 30 GB
#   * an Elastic IP associated to it — STABLE egress IP so FanGraphs' IP-bound
#     cf_clearance survives reboots
#
# ⚠️ This SPENDS money and creates real infrastructure. The operator runs it —
#    review every value below first. Re-running is largely idempotent (it looks
#    up existing resources by name/tag before creating).
#
# Prereqs: awscli v2 configured (`aws configure`), an existing EC2 key pair.
#
#   REGION=us-east-1 KEY_NAME=my-key ./services/dagster/aws/provision-ec2.sh
# =============================================================================
set -euo pipefail

# ---- tunables ---------------------------------------------------------------
REGION="${REGION:-us-east-1}"
KEY_NAME="${KEY_NAME:?set KEY_NAME to an existing EC2 key pair name}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.medium}"          # 4 GB arm64; do NOT undersize (flaresolverr Chromium ~1 GB)
VOLUME_GB="${VOLUME_GB:-30}"
NAME_TAG="${NAME_TAG:-credence-dagster}"
SG_NAME="${SG_NAME:-credence-dagster-sg}"
ROLE_NAME="${ROLE_NAME:-credence-dagster-ec2-role}"
PROFILE_NAME="${PROFILE_NAME:-credence-dagster-ec2-profile}"
ARTIFACTS_BUCKET="${ARTIFACTS_BUCKET:-baseball-betting-ml-artifacts}"
# Operator IP for the SG; auto-detect if not provided.
OPERATOR_IP="${OPERATOR_IP:-$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')}"
CIDR="${OPERATOR_IP}/32"

export AWS_DEFAULT_REGION="$REGION"
echo "[provision] region=$REGION operator=$CIDR type=$INSTANCE_TYPE key=$KEY_NAME"

# ---- default VPC + a public subnet -----------------------------------------
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)
SUBNET_ID=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" \
  Name=map-public-ip-on-launch,Values=true \
  --query 'Subnets[0].SubnetId' --output text)
echo "[provision] vpc=$VPC_ID subnet=$SUBNET_ID"

# ---- security group ---------------------------------------------------------
SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$SG_NAME" \
    --description "INC-16 Dagster re-host: SSH+dagit from operator IP" \
    --vpc-id "$VPC_ID" --query 'GroupId' --output text)
  echo "[provision] created SG $SG_ID"
fi
# Ingress: SSH (initial bring-up; drop once SSM works) + Caddy 80/443 from the
# operator IP. dagit :3000 is NOT exposed (P4: Caddy fronts it on 443; webserver is
# bound to 127.0.0.1). 80/443 may need 0.0.0.0/0 briefly for first Let's Encrypt
# issuance, then tighten. (Egress defaults to allow-all — the agent NEEDS it:
# FanGraphs/Snowflake/odds APIs/GitHub/ghcr/SSM/Let's Encrypt.)
for PORT in 22 80 443; do
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
    --protocol tcp --port "$PORT" --cidr "$CIDR" 2>/dev/null \
    && echo "[provision] ingress $PORT <- $CIDR" \
    || echo "[provision] ingress $PORT already present"
done

# ---- S3 gateway VPC endpoint (free; avoids NAT for S3 traffic) --------------
RT_IDS=$(aws ec2 describe-route-tables --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'RouteTables[].RouteTableId' --output text)
EXISTING_EP=$(aws ec2 describe-vpc-endpoints \
  --filters Name=vpc-id,Values="$VPC_ID" Name=service-name,Values="com.amazonaws.${REGION}.s3" \
  --query 'VpcEndpoints[0].VpcEndpointId' --output text 2>/dev/null || echo "None")
if [ "$EXISTING_EP" = "None" ] || [ -z "$EXISTING_EP" ]; then
  aws ec2 create-vpc-endpoint --vpc-id "$VPC_ID" \
    --service-name "com.amazonaws.${REGION}.s3" --vpc-endpoint-type Gateway \
    --route-table-ids $RT_IDS >/dev/null
  echo "[provision] created S3 gateway endpoint"
else
  echo "[provision] S3 gateway endpoint already present ($EXISTING_EP)"
fi

# ---- IAM role + instance profile (S3 access; no static keys on the box) ------
if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version":"2012-10-17",
      "Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]
    }' >/dev/null
  echo "[provision] created role $ROLE_NAME"
fi
# Scoped S3 access to the artifacts bucket (lakehouse + dbt state + serving fallback).
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name s3-artifacts \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[{
      \"Effect\":\"Allow\",
      \"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\",\"s3:DeleteObject\"],
      \"Resource\":[\"arn:aws:s3:::${ARTIFACTS_BUCKET}\",\"arn:aws:s3:::${ARTIFACTS_BUCKET}/*\"]
    }]
  }" >/dev/null
# DynamoDB serving-cache access (INC-16-P2): write_serving_store runs on this box
# and writes the serving cache → needs read+write+query+delete on the table.
SERVING_CACHE_TABLE="${SERVING_CACHE_TABLE:-credence-prod-serving-cache}"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name dynamo-serving-cache \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[{
      \"Effect\":\"Allow\",
      \"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\",\"dynamodb:BatchWriteItem\",
                  \"dynamodb:Query\",\"dynamodb:Scan\",\"dynamodb:DeleteItem\"],
      \"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${SERVING_CACHE_TABLE}\"
    }]
  }" >/dev/null
echo "[provision] dynamo-serving-cache policy attached for ${SERVING_CACHE_TABLE}"
# Serving S3-fallback cache RW (INC-16-P4): write_serving_store/write_api_cache write
# the picks/perf JSON the backend reads as its S3 fallback.
API_CACHE_BUCKET="${API_CACHE_BUCKET:-credence-prod-s3-api-cache}"
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name credence-s3-api-cache-rw \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::${API_CACHE_BUCKET}/*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"s3:ListBucket\"],\"Resource\":\"arn:aws:s3:::${API_CACHE_BUCKET}\"}
    ]
  }" >/dev/null
echo "[provision] credence-s3-api-cache-rw attached for ${API_CACHE_BUCKET}"
# User-bet settlement (INC-16-P4): settle_user_bets scans/updates the bets table.
USER_BETS_TABLE="${USER_BETS_TABLE:-credence-prod-dynamo-user-bets}"
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name credence-dynamo-user-bets-settle \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[{
      \"Effect\":\"Allow\",
      \"Action\":[\"dynamodb:Scan\",\"dynamodb:Query\",\"dynamodb:GetItem\",\"dynamodb:UpdateItem\"],
      \"Resource\":[
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${USER_BETS_TABLE}\",
        \"arn:aws:dynamodb:${REGION}:${ACCOUNT_ID}:table/${USER_BETS_TABLE}/index/*\"
      ]
    }]
  }" >/dev/null
echo "[provision] credence-dynamo-user-bets-settle attached for ${USER_BETS_TABLE}"
# SSM Session Manager (INC-16-P4 retires SSH) — managed policy on the instance role.
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore >/dev/null 2>&1 || true
echo "[provision] AmazonSSMManagedInstanceCore attached (SSM shell)"
if ! aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
  echo "[provision] created instance profile $PROFILE_NAME (propagation ~10s)"
  sleep 12
fi

# ---- latest Amazon Linux 2023 arm64 AMI via SSM -----------------------------
AMI_ID=$(aws ssm get-parameters \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --query 'Parameters[0].Value' --output text)
echo "[provision] ami=$AMI_ID"

# ---- launch -----------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" --security-group-ids "$SG_ID" --subnet-id "$SUBNET_ID" \
  --iam-instance-profile "Name=$PROFILE_NAME" \
  --metadata-options "HttpEndpoint=enabled,HttpTokens=required,HttpPutResponseHopLimit=2" \
  --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp3}" \
  --user-data "file://${SCRIPT_DIR}/cloud-init.sh" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME_TAG}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "[provision] launched $INSTANCE_ID — waiting for running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# ---- Elastic IP (stable egress for FanGraphs cf_clearance) ------------------
ALLOC_ID=$(aws ec2 allocate-address --domain vpc --query 'AllocationId' --output text)
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null
EIP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)

cat <<EOF

[provision] ✅ done
  instance : $INSTANCE_ID
  elastic IP: $EIP   (stable egress — FanGraphs cf_clearance binds to this)
  SSH      : ssh ec2-user@$EIP

Next (on the box, after cloud-init finishes — ~2 min):
  git clone <repo> ~/app && cd ~/app
  cp services/dagster/aws/.env.example services/dagster/aws/.env   # fill it
  chmod 600 services/dagster/aws/.env
  docker compose -f services/dagster/aws/docker-compose.yml up -d --build
EOF
