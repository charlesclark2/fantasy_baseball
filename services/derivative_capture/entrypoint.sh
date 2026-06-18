#!/usr/bin/env bash
# E2.0b derivative-odds live capture — snapshot upcoming MLB games' derivative markets.
# Runs once and exits; Railway cron re-invokes on schedule.
#
# Required env vars (set in Railway service settings):
#   ODDS_API_KEY                   — MAIN-tier key (starter key excludes additional markets)
#   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
#   SNOWFLAKE_PRIVATE_KEY          — PEM key content (Railway stores as env string)
#   SNOWFLAKE_ROLE                 (optional)
#   ODDS_TARGET_DATABASE           (default: baseball_data)
#   ODDS_TARGET_SCHEMA             (default: oddsapi)
#   DERIVATIVE_CAPTURE_MARKETS     (optional; set after probe — e.g. team_totals,alternate_totals)
#
# EVAL/CLV-ONLY: derivative odds are never model training features.
set -euo pipefail

# Railway stores the private key as an env string; the connector wants a FILE.
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem
  chmod 600 /tmp/snowflake_rsa_key.pem
  export SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem
fi

echo "[derivative_capture] $(date -u +%FT%TZ) start"
python derivative_odds_backfill.py capture
echo "[derivative_capture] $(date -u +%FT%TZ) done"
