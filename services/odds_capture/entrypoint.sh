#!/usr/bin/env bash
# Live Odds API capture — one snapshot of MLB odds across us, us2, eu (all books incl.
# Bovada + Pinnacle), appended to baseball_data.oddsapi.mlb_odds_raw. Runs once and exits;
# Railway's cron re-invokes it on schedule. Cost = markets(2) × regions(3) = 6 credits/call.
set -euo pipefail

# Railway stores secrets as env strings; the Snowflake connector wants a key FILE.
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem
  chmod 600 /tmp/snowflake_rsa_key.pem
  export SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem
fi

echo "[odds_capture] $(date -u +%FT%TZ) start — regions=us,us2,eu markets=h2h,totals"
python odds_api_ingestion.py odds --markets h2h totals --regions us us2 eu
echo "[odds_capture] $(date -u +%FT%TZ) done"
