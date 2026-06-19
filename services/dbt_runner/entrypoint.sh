#!/usr/bin/env bash
# E11.0 dbt-runner entrypoint — starts the FastAPI HTTP server.
# profiles.yml is gitignored (contains creds); generate it at startup from env vars
# so the container never needs the file in the build context.
set -euo pipefail

# Write the RSA private key to a file; dbt needs a path not a string.
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem
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
