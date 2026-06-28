#!/usr/bin/env bash
# =============================================================================
# INC-16-P6 — shell-side ops notifier (sourced by healthcheck.sh + deploy.sh).
#
#   source notify.sh
#   notify CRITICAL "subject line" "full message body"
#
# Publishes to the same shared SNS topic the Python notifier + CloudWatch alarms
# use → one inbox. Self-resolves ALERT_SNS_TOPIC_ARN from the environment, else
# from the box .env (cron/SSM shells have a minimal env). Never exits non-zero —
# a failed alert must not fail the caller.
# =============================================================================
_NOTIFY_ENV_FILE="${NOTIFY_ENV_FILE:-/home/ec2-user/app/services/dagster/aws/.env}"

notify() {
  local severity="${1:-ERROR}" subject="${2:-alert}" message="${3:-}"
  local arn="${ALERT_SNS_TOPIC_ARN:-}"
  if [ -z "$arn" ] && [ -f "$_NOTIFY_ENV_FILE" ]; then
    arn="$(grep -E '^ALERT_SNS_TOPIC_ARN=' "$_NOTIFY_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
  fi
  local region="${AWS_DEFAULT_REGION:-${AWS_REGION:-us-east-1}}"
  if [ -z "$arn" ]; then
    echo "[notify] WARNING: ALERT_SNS_TOPIC_ARN unset — alert NOT sent: ${severity}: ${subject}" >&2
    return 0
  fi
  aws sns publish --region "$region" --topic-arn "$arn" \
    --subject "[Credence PROD] ${severity}: ${subject}" \
    --message "severity: ${severity}"$'\n\n'"${message}" >/dev/null 2>&1 \
    || echo "[notify] WARNING: sns publish failed for: ${severity}: ${subject}" >&2
  return 0
}
