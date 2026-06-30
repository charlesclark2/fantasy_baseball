#!/usr/bin/env bash
# E11.4 intraday schedule capture — re-ingest today's MLB schedule, then trigger
# the lineup-staging dbt rebuild on E11.0. Runs once and exits; Railway cron re-invokes.
#
# This replaces the Dagster `intraday_schedule_job` (was ~20% of Dagster+ run-minutes).
# Python/polling runs here (off Dagster's bill); dbt runs on the E11.0 container.
#
# Active window: 10:00 AM – 11:59 PM ET = 14:00–03:30 UTC.
# Railway cron fires every 30 min all day; we exit early outside the window.
set -euo pipefail

# Time-window guard (UTC hours 04–13 = before 10AM or after midnight ET — skip).
HOUR=$(date -u +%H)
HOUR_INT=$((10#$HOUR))
if [ "$HOUR_INT" -ge 4 ] && [ "$HOUR_INT" -le 13 ]; then
  echo "[schedule_capture] UTC hour $HOUR_INT outside active window (14-3 UTC), exiting"
  exit 0
fi

# Railway stores the private key as an env string; the Snowflake connector wants a FILE.
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

# INC-22: the US baseball-day (America/Los_Angeles), NOT the UTC date. A bare `date -u`
# rolls to TOMORROW at 00:00 UTC — but this cron's active window runs to 03:59 UTC
# (= 8 PM–11:59 PM PT), exactly when the late West-coast slate's lineups post. With the
# UTC date, those captures targeted *tomorrow*, so the current day's late lineups never
# landed (e.g. the 6/29 MIL/SEA/COL/ATH/AZ lineups). zoneinfo (+ the tzdata wheel in the
# image) resolves LA with correct DST, matching betting_ml.utils.game_day everywhere else.
TODAY=$(python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat())")
echo "[schedule_capture] $(date -u +%FT%TZ) start — baseball-day(LA)=$TODAY"

# Step 1: re-ingest today's schedule (picks up retroactive lineup confirmations).
python ingest_statsapi.py schedule --start-date "$TODAY" --end-date "$TODAY" --capture-reason intraday_gameday

echo "[schedule_capture] schedule ingest done — triggering dbt staging rebuild"

# Step 2: rebuild lineup staging models on E11.0 so lineup_monitor_sensor sees fresh data.
# Non-fatal: if E11.0 is unreachable we still landed the raw data; the next 30-min tick retries.
export DBT_JOB_NAME="schedule_capture_cron"
python trigger_dbt.py \
  run \
  --select stg_statsapi_lineups stg_statsapi_lineups_wide stg_statsapi_probable_pitchers \
  --target baseball_betting_and_fantasy \
|| echo "[schedule_capture] WARNING: dbt trigger failed (non-fatal) — raw data landed"

echo "[schedule_capture] $(date -u +%FT%TZ) done"
