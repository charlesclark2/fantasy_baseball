#!/usr/bin/env bash
# Deploy the Credence Sports FastAPI backend to AWS Lambda.
#
# Usage:
#   ./infrastructure/lambda/deploy.sh             # full deploy
#   ./infrastructure/lambda/deploy.sh --dry-run   # package only, skip AWS CLI calls
#
# Prerequisites:
#   - AWS CLI configured with credentials that can update Lambda functions
#   - Python 3.12 available (must match Lambda runtime)
#   - Run from the repository root

set -euo pipefail

FUNCTION_NAME="credence-prod-lambda-api"
REGION="us-east-1"
PACKAGE_DIR="$(pwd)/.lambda_build/package"
ZIP_PATH="$(pwd)/.lambda_build/deployment.zip"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

echo "=== Credence Sports Lambda Deploy ==="
echo "Function : $FUNCTION_NAME"
echo "Region   : $REGION"
[[ "$DRY_RUN" == "true" ]] && echo "Mode     : DRY RUN (skipping AWS CLI)"
echo ""

# ── 1. Clean previous build ──────────────────────────────────────────────────
rm -rf .lambda_build
mkdir -p "$PACKAGE_DIR"

# ── 2. Install dependencies into the package directory ───────────────────────
# Use --platform / --only-binary so pip fetches Linux x86_64 wheels even when
# running on macOS. Without this, compiled extensions (.so files) are built for
# the local OS and fail on Lambda's Amazon Linux 2 runtime.
echo "Installing Python dependencies..."
pip install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --upgrade \
  "fastapi>=0.115.0" \
  "mangum>=0.19.0" \
  "snowflake-connector-python>=3.12.0" \
  "python-jose[cryptography]>=3.3.0" \
  "boto3>=1.35.0" \
  "pydantic>=2.0.0" \
  "cryptography>=41.0" \
  "python-dotenv>=1.0" \
  "sentry-sdk[fastapi]>=2.0.0" \
  -t "$PACKAGE_DIR" \
  --quiet

# ── 3. Copy backend source ────────────────────────────────────────────────────
echo "Copying app/backend/ source..."
mkdir -p "$PACKAGE_DIR/app"
cp -r app/backend "$PACKAGE_DIR/app/"
# Copy app/__init__.py if it exists (needed for `app` to be a Python package)
[ -f app/__init__.py ] && cp app/__init__.py "$PACKAGE_DIR/app/"

# ── 4. Zip the package ────────────────────────────────────────────────────────
echo "Creating deployment.zip..."
cd .lambda_build/package
zip -r ../deployment.zip . --quiet
cd ../..

SIZE_KB=$(du -k "$ZIP_PATH" | cut -f1)
echo "Package size: ${SIZE_KB} KB"

if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  echo "Dry run complete. Deployment package at: $ZIP_PATH"
  echo "Skipped: aws lambda update-function-code"
  exit 0
fi

# ── 5. Deploy to Lambda ────────────────────────────────────────────────────────
echo "Uploading to Lambda..."
OUTPUT=$(aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  --region "$REGION" \
  --output json)

echo "Waiting for Lambda update to complete..."
aws lambda wait function-updated \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION"

FUNCTION_ARN=$(echo "$OUTPUT" | python3 -c "import sys, json; print(json.load(sys.stdin)['FunctionArn'])")
echo ""
echo "Deploy complete."
echo "Function ARN: $FUNCTION_ARN"
