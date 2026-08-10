#!/usr/bin/env bash
# Deploy the Cognito email-OTP CUSTOM_AUTH trigger Lambda (G100-C0).
#
# Packages ONLY handler.py — boto3 ships in the Lambda Python runtime, so there are no
# dependencies to bundle. The function CODE is created/updated here; the IAM role, the
# three Cognito trigger wirings, the app-client auth-flow change and the SES grant are
# one-time operator steps documented in README.md (run those FIRST for a fresh deploy).
#
# Usage:
#   ./infrastructure/cognito/email_otp/deploy.sh              # update code (function must exist)
#   ./infrastructure/cognito/email_otp/deploy.sh --dry-run    # zip only
#
# Prereqs: AWS CLI with Lambda perms; run from the repo root.

set -euo pipefail

# Prefer the named AWS profile over any injected env-var keys (mirrors the API deploy).
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

FUNCTION_NAME="${EMAIL_OTP_FUNCTION_NAME:-credence-prod-cognito-email-otp}"
REGION="${AWS_REGION:-us-east-1}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZIP_PATH="${SRC_DIR}/.build/deployment.zip"
DRY_RUN=false
for arg in "$@"; do [[ "$arg" == "--dry-run" ]] && DRY_RUN=true; done

echo "=== Cognito email-OTP Lambda deploy ==="
echo "Function : $FUNCTION_NAME"
echo "Region   : $REGION"
[[ "$DRY_RUN" == "true" ]] && echo "Mode     : DRY RUN"
echo ""

# Fail-fast: the handler must import + expose handler() with the local interpreter.
echo "Import smoke test..."
SMOKE_PY="import importlib.util,sys; s=importlib.util.spec_from_file_location('h','${SRC_DIR}/handler.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert callable(m.handler); print('  OK: handler imports + is callable')"
if command -v uv >/dev/null 2>&1; then uv run python -c "$SMOKE_PY"; else python3 -c "$SMOKE_PY"; fi
echo ""

rm -rf "${SRC_DIR}/.build"; mkdir -p "${SRC_DIR}/.build"
( cd "$SRC_DIR" && zip -j "$ZIP_PATH" handler.py --quiet )
echo "Package: $(du -k "$ZIP_PATH" | cut -f1) KB"

if [[ "$DRY_RUN" == "true" ]]; then echo "Dry run complete → $ZIP_PATH"; exit 0; fi

echo "Updating function code..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://${ZIP_PATH}" \
  --region "$REGION" \
  --output json >/dev/null

aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"
echo "Deploy complete: $FUNCTION_NAME"
