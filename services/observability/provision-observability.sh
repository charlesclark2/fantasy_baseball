#!/usr/bin/env bash
# =============================================================================
# INC-16-P6 — provision observability for the AWS orchestration box.
#
#   OPERATOR-RUN from a laptop with AWS creds (Claude does NOT run this — it
#   creates IAM/SNS/alarms and subscribes an email). Idempotent where AWS allows.
#
# Creates, all wired to ONE SNS topic → one operator email subscription:
#   1. SNS topic + email subscription (you confirm the email link)
#   2. box instance-role grants: sns:Publish + CloudWatchAgentServerPolicy
#   3. CloudWatch alarms (EC2 status, mem, swap, disk, CPU-sustained, CPU credits)
#   4. the daily-output dead-man Lambda + its role + an EventBridge morning schedule
#
# After it runs: set ALERT_SNS_TOPIC_ARN (printed at the end) in the box .env, and
# apply the CloudWatch agent to the CURRENT box (it predates cloud-init's agent step)
# — both one-liners are printed at the end.
#
# Usage:
#   ALERT_EMAIL=you@example.com ./services/observability/provision-observability.sh
# =============================================================================
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
INSTANCE_ID="${DEPLOY_INSTANCE_ID:-i-07594af1679f81c38}"
ROLE_NAME="${BOX_ROLE_NAME:-credence-dagster-ec2-role}"
TOPIC_NAME="${TOPIC_NAME:-credence-prod-alerts}"
TABLE="${SERVING_CACHE_TABLE:-credence-prod-serving-cache}"
LAMBDA_NAME="${LAMBDA_NAME:-credence-deadman-daily}"
LAMBDA_ROLE="${LAMBDA_ROLE:-credence-deadman-lambda-role}"
# EventBridge schedule = the morning cutoff. 12:30 UTC = 08:30 ET (DST) — the cycle
# should be done by then. cron(min hour ? * * *) in UTC.
CUTOFF_CRON="${CUTOFF_CRON:-cron(30 12 * * ? *)}"
ALERT_EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL=you@example.com}"

ACCT="$(aws sts get-caller-identity --query Account --output text)"
HERE="$(cd "$(dirname "$0")" && pwd)"
say() { echo "[provision-obs] $*"; }

# --- 1. SNS topic + email subscription --------------------------------------
TOPIC_ARN="$(aws sns create-topic --region "$REGION" --name "$TOPIC_NAME" --query TopicArn --output text)"
say "topic: $TOPIC_ARN"
aws sns subscribe --region "$REGION" --topic-arn "$TOPIC_ARN" \
  --protocol email --notification-endpoint "$ALERT_EMAIL" >/dev/null
say "subscribed $ALERT_EMAIL — CONFIRM the email link before alarms can deliver."

# --- 2. box instance-role grants --------------------------------------------
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name credence-alerts-publish \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"sns:Publish\",\"Resource\":\"$TOPIC_ARN\"}]}"
aws iam attach-role-policy --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy 2>/dev/null || true
say "box role $ROLE_NAME: sns:Publish + CloudWatchAgentServerPolicy"

alarm() {  # alarm() NAME DESC METRIC NAMESPACE STAT THRESHOLD COMPARISON PERIODS PERIOD [extra-dims]
  local name="$1" desc="$2" metric="$3" ns="$4" stat="$5" thr="$6" cmp="$7" periods="$8" period="$9"; shift 9
  aws cloudwatch put-metric-alarm --region "$REGION" \
    --alarm-name "$name" --alarm-description "$desc" \
    --namespace "$ns" --metric-name "$metric" --statistic "$stat" \
    --threshold "$thr" --comparison-operator "$cmp" \
    --evaluation-periods "$periods" --period "$period" \
    --dimensions Name=InstanceId,Value="$INSTANCE_ID" \
    --treat-missing-data "$1" \
    --alarm-actions "$TOPIC_ARN" --ok-actions "$TOPIC_ARN"
  say "alarm: $name"
}

# --- 3. CloudWatch alarms (all → the topic) ---------------------------------
# EC2-native (no agent): instance + system reachability. Missing-data = breaching
# (a dead instance stops publishing).
alarm credence-box-status-instance "EC2 instance status check failed" \
  StatusCheckFailed_Instance AWS/EC2 Maximum 1 GreaterThanOrEqualToThreshold 2 60 breaching
alarm credence-box-status-system "EC2 system status check failed" \
  StatusCheckFailed_System AWS/EC2 Maximum 1 GreaterThanOrEqualToThreshold 2 60 breaching
# CPU sustained (NOT spikes): >90% for 30 min (3×10min). Builds/predict bursts are
# expected minutes-long — only hours-long saturation pages.
alarm credence-box-cpu-sustained "CPU >90% sustained 30m (runaway / mis-run retrain)" \
  CPUUtilization AWS/EC2 Average 90 GreaterThanThreshold 3 600 notBreaching
# CWAgent (mem/swap/disk). OOM is the likeliest failure on the 4 GB box.
alarm credence-box-mem "memory >85% for 10m (OOM precursor)" \
  mem_used_percent CWAgent Average 85 GreaterThanThreshold 1 600 notBreaching
alarm credence-box-swap "swap >50% (memory pressure / thrashing)" \
  swap_used_percent CWAgent Average 50 GreaterThanThreshold 1 600 notBreaching
alarm credence-box-disk "root disk >85% (docker images/logs/parquet)" \
  disk_used_percent CWAgent Average 85 GreaterThanThreshold 1 300 notBreaching

# CPU credits — depends on the instance's billing mode.
MODE="$(aws ec2 describe-instance-credit-specifications --region "$REGION" \
  --instance-ids "$INSTANCE_ID" --query 'InstanceCreditSpecifications[0].CpuCredits' --output text)"
say "CPU credit mode: $MODE"
if [ "$MODE" = "standard" ]; then
  alarm credence-box-cpu-credits "CPUCreditBalance <50 (throttle precursor)" \
    CPUCreditBalance AWS/EC2 Average 50 LessThanThreshold 1 300 notBreaching
else
  # unlimited (t4g default): no throttle; surplus credits = COST. Alarm if charged.
  alarm credence-box-cpu-surplus "CPUSurplusCreditsCharged >0 (sustained burst = cost)" \
    CPUSurplusCreditsCharged AWS/EC2 Maximum 0 GreaterThanThreshold 1 3600 notBreaching
fi

# --- 4. daily-output dead-man Lambda + EventBridge schedule -----------------
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam create-role --role-name "$LAMBDA_ROLE" --assume-role-policy-document "$TRUST" 2>/dev/null \
  && say "created lambda role $LAMBDA_ROLE" || say "lambda role $LAMBDA_ROLE exists"
aws iam attach-role-policy --role-name "$LAMBDA_ROLE" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || true
aws iam put-role-policy --role-name "$LAMBDA_ROLE" --policy-name credence-deadman-access \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[
    {\"Effect\":\"Allow\",\"Action\":\"dynamodb:GetItem\",\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCT}:table/${TABLE}\"},
    {\"Effect\":\"Allow\",\"Action\":\"sns:Publish\",\"Resource\":\"$TOPIC_ARN\"}]}"
say "lambda role policies attached"
sleep 8  # let the new role propagate before create-function

ZIP="$(mktemp -d)/deadman.zip"
( cd "$HERE/deadman_lambda" && zip -q "$ZIP" handler.py )
ENVVARS="Variables={SERVING_CACHE_TABLE=$TABLE,ALERT_SNS_TOPIC_ARN=$TOPIC_ARN,HEARTBEAT_TZ=America/New_York}"
if aws lambda get-function --region "$REGION" --function-name "$LAMBDA_NAME" >/dev/null 2>&1; then
  aws lambda update-function-code --region "$REGION" --function-name "$LAMBDA_NAME" --zip-file "fileb://$ZIP" >/dev/null
  aws lambda update-function-configuration --region "$REGION" --function-name "$LAMBDA_NAME" --environment "$ENVVARS" >/dev/null
  say "lambda $LAMBDA_NAME updated"
else
  aws lambda create-function --region "$REGION" --function-name "$LAMBDA_NAME" \
    --runtime python3.12 --architectures arm64 --handler handler.lambda_handler \
    --role "arn:aws:iam::${ACCT}:role/${LAMBDA_ROLE}" \
    --timeout 30 --memory-size 128 --zip-file "fileb://$ZIP" --environment "$ENVVARS" >/dev/null
  say "lambda $LAMBDA_NAME created"
fi

RULE="credence-deadman-daily-schedule"
aws events put-rule --region "$REGION" --name "$RULE" \
  --schedule-expression "$CUTOFF_CRON" --description "INC-16-P6 daily-output dead-man cutoff" >/dev/null
aws lambda add-permission --region "$REGION" --function-name "$LAMBDA_NAME" \
  --statement-id "${RULE}-invoke" --action lambda:InvokeFunction --principal events.amazonaws.com \
  --source-arn "arn:aws:events:${REGION}:${ACCT}:rule/${RULE}" 2>/dev/null || true
aws events put-targets --region "$REGION" --rule "$RULE" \
  --targets "Id=deadman,Arn=arn:aws:lambda:${REGION}:${ACCT}:function:${LAMBDA_NAME}" >/dev/null
say "EventBridge rule $RULE → $LAMBDA_NAME ($CUTOFF_CRON UTC)"

cat <<EOF

============================================================================
✅ observability provisioned. TWO remaining manual steps:

1. CONFIRM the SNS subscription email just sent to $ALERT_EMAIL.

2. Set ALERT_SNS_TOPIC_ARN on the box .env + apply the CloudWatch agent to the
   CURRENT box (it predates cloud-init's agent step). Run these via SSM:

   aws ssm send-command --instance-ids $INSTANCE_ID --document-name AWS-RunShellScript \\
     --comment "P6: set alert topic + start CW agent" --parameters 'commands=[
       "sudo -u ec2-user -H bash -lc \\"cd /home/ec2-user/app/services/dagster/aws && sed -i /^ALERT_SNS_TOPIC_ARN=/d .env && echo ALERT_SNS_TOPIC_ARN=$TOPIC_ARN >> .env\\"",
       "sudo dnf install -y amazon-cloudwatch-agent",
       "sudo cp /home/ec2-user/app/services/dagster/aws/cloudwatch-agent-config.json /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json",
       "sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"
     ]'

   Then reinstall the crontab (healthcheck line) + enable run_failure_alert_sensor in Dagit.

   TEST: aws lambda invoke --function-name $LAMBDA_NAME /dev/stdout   # (before today's run → expect ALERT email)
============================================================================
EOF
