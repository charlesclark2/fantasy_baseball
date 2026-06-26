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
#   DERIVATIVE_CAPTURE_MARKETS     (optional; overrides code default — correct value confirmed 2026-06-24:
#                                   team_totals,alternate_totals,h2h_1st_5_innings,totals_1st_5_innings,totals_1st_1_innings
#                                   NOTE: h2h_h1/totals_h1 are WRONG keys; baseball books don't use the generic 1st-Half family)
#
# EVAL/CLV-ONLY: derivative odds are never model training features.
set -euo pipefail

# Railway stores the private key as an env string; the connector wants a FILE.
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

echo "[derivative_capture] $(date -u +%FT%TZ) start"
python derivative_odds_backfill.py capture
echo "[derivative_capture] $(date -u +%FT%TZ) done"
