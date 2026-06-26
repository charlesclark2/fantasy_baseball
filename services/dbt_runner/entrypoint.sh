#!/usr/bin/env bash
# E11.0 dbt-runner entrypoint — starts the FastAPI HTTP server.
# profiles.yml is gitignored (contains creds); generate it at startup from env vars
# so the container never needs the file in the build context.
set -euo pipefail

# Write the RSA private key to a file; dbt needs a path not a string.
# INC-16-P2: a Docker Compose env_file can't carry real newlines, so the key
# arrives base64-encoded (recommended) or with literal \n escapes. Normalize to a
# real PEM (a raw multi-line PEM is passed through unchanged) — otherwise dbt fails
# with "Unable to load PEM file".
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  # Check \n-escaped FIRST: such a value still starts with "-----BEGIN", so a
  # leading "-----"* case would wrongly skip the \n→newline expansion.
  case "$SNOWFLAKE_PRIVATE_KEY" in
    *'\n'*)
      printf '%b\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem ;;   # \n-escaped (%b expands)
    "-----"*)
      printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem ;;   # raw PEM
    *)
      printf '%s' "$SNOWFLAKE_PRIVATE_KEY" | base64 -d > /tmp/snowflake_rsa_key.pem ;;  # base64
  esac
  chmod 600 /tmp/snowflake_rsa_key.pem
  export SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem
fi

# Generate /dbt/profiles.yml from env vars — mirrors the local profiles.yml
# structure but replaces credentials with values from Railway env vars.
cat > /dbt/profiles.yml <<EOF
baseball_betting_and_fantasy:
  target: baseball_betting_and_fantasy
  outputs:
    baseball_betting_and_fantasy:
      type: snowflake
      account: ${SNOWFLAKE_ACCOUNT}
      user: ${SNOWFLAKE_USER}
      role: ${SNOWFLAKE_ROLE}
      database: baseball_data
      warehouse: ${SNOWFLAKE_WAREHOUSE}
      schema: betting
      private_key_path: /tmp/snowflake_rsa_key.pem
EOF
chmod 600 /dbt/profiles.yml

echo "[dbt-runner] $(date -u +%FT%TZ) starting on :${PORT:-8080}"
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1
