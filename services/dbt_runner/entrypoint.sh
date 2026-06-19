#!/usr/bin/env bash
# E11.0 dbt-runner entrypoint — starts the FastAPI HTTP server.
# Railway stores the Snowflake private key as an env string; dbt profiles.yml
# needs a file path. Write the PEM to /tmp on startup (same pattern as
# services/odds_capture/entrypoint.sh).
set -euo pipefail

if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem
  chmod 600 /tmp/snowflake_rsa_key.pem
  export SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem
fi

echo "[dbt-runner] $(date -u +%FT%TZ) starting on :${PORT:-8080}"
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1
