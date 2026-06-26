#!/usr/bin/env bash
# Live Odds API capture — one snapshot of MLB odds across us, us2, eu (all books incl.
# Bovada + Pinnacle), appended to baseball_data.oddsapi.mlb_odds_raw. Runs once and exits;
# Railway's cron re-invokes it on schedule. Cost = markets(2) × regions(3) = 6 credits/call.
set -euo pipefail

# Railway stores secrets as env strings; the Snowflake connector wants a key FILE.
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  # INC-16-P3: a single-line env value (cron/Compose env_file/Lambda) can't carry
  # real PEM newlines, so the key arrives \n-escaped (check FIRST — it still starts
  # with -----BEGIN) or base64. A raw multi-line PEM passes through unchanged.
  case "$SNOWFLAKE_PRIVATE_KEY" in
    *'\n'*)   printf '%b\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem ;;
    "-----"*) printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem ;;
    *)        printf '%s' "$SNOWFLAKE_PRIVATE_KEY" | base64 -d > /tmp/snowflake_rsa_key.pem ;;
  esac
  chmod 600 /tmp/snowflake_rsa_key.pem
  export SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem
fi

echo "[odds_capture] $(date -u +%FT%TZ) start — regions=us,us2,eu markets=h2h,totals"
python odds_api_ingestion.py odds --markets h2h totals --regions us us2 eu
echo "[odds_capture] $(date -u +%FT%TZ) done"
