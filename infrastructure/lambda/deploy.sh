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

# Force AWS CLI to use the named profile rather than any injected env-var credentials
# (e.g. baseball-access-user keys that may be exported from .env in the current shell).
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

FUNCTION_NAME="credence-prod-lambda-api"
REGION="us-east-1"
PACKAGE_DIR="$(pwd)/.lambda_build/package"
ZIP_PATH="$(pwd)/.lambda_build/deployment.zip"
# Deploy via S3 — a direct --zip-file upload base64-inflates the package and hits the
# ~70 MB request cap (the duckdb dep added in W7b pushed the zip past it). Uploading the
# zip to S3 and pointing update-function-code at it lifts the ceiling to the 250 MB
# unzipped quota. The bucket MUST be in the same region as the function (us-east-1) —
# baseball-betting-ml-artifacts is us-east-2, so use the us-east-1 api-cache bucket.
# Override with LAMBDA_DEPLOY_BUCKET if needed (must be a us-east-1 bucket).
S3_DEPLOY_BUCKET="${LAMBDA_DEPLOY_BUCKET:-credence-prod-s3-api-cache}"
S3_DEPLOY_KEY="lambda-deploy/${FUNCTION_NAME}.zip"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

echo "=== Credence Sports Lambda Deploy ==="
echo "Function : $FUNCTION_NAME"
echo "Region   : $REGION"
[[ "$DRY_RUN" == "true" ]] && echo "Mode     : DRY RUN (skipping AWS CLI)"
echo ""

# ── 0. Import smoke test (fail-fast pre-flight) ───────────────────────────────
# Guards against shipping code that crashes the Lambda at INIT. On 2026-06-15 a
# missing `from fastapi import Depends` made app.backend.main fail at import time,
# so every route 500'd (init crash) — yet packaging/zipping succeeded blindly and
# the broken tree reached prod. We catch it here by actually IMPORTING the app:
#   - `python -m py_compile` is NOT enough — a missing-name (NameError) at module
#     load is not a syntax error, so it compiles fine and still crashes on import.
#   - We import the SOURCE tree with the local interpreter (cwd = repo root, so
#     `app.backend.main` resolves to ./app/backend/main.py — exactly what step 3
#     copies into the package). The PACKAGED deps are Linux-only manylinux wheels
#     that cannot import on macOS, so we deliberately test source-against-host-env.
#   - Importing is side-effect-safe: routers/services (incl. pg) define lazily and
#     do not open connections at import, so this needs no DB/network access.
# `set -e` aborts the deploy on any non-zero exit, printing the offending traceback.
echo "Running import smoke test (app.backend.main)..."
SMOKE_PY='import app.backend.main; print("  smoke test OK: app.backend.main imports clean")'
if command -v uv >/dev/null 2>&1; then
  uv run python -c "$SMOKE_PY"
else
  python3 -c "$SMOKE_PY"
fi
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
  "psycopg2-binary>=2.9.0" \
  "duckdb>=1.1.0" \
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

# ── 5. Deploy to Lambda (via S3 to avoid the ~70 MB direct-upload request cap) ──
echo "Uploading package to s3://${S3_DEPLOY_BUCKET}/${S3_DEPLOY_KEY}..."
aws s3 cp "$ZIP_PATH" "s3://${S3_DEPLOY_BUCKET}/${S3_DEPLOY_KEY}" --region "$REGION"

echo "Pointing Lambda at the S3 object..."
OUTPUT=$(aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --s3-bucket "$S3_DEPLOY_BUCKET" \
  --s3-key "$S3_DEPLOY_KEY" \
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
