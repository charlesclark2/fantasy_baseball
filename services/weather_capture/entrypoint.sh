#!/usr/bin/env bash
# E11.4 intraday weather capture — fetch forecast snapshots at all T-24/6/3/1h
# checkpoints + observed_at_first_pitch. Runs once and exits; Railway cron re-invokes.
#
# This replaces the Dagster `intraday_weather_job` (~7% of Dagster+ run-minutes).
# Each checkpoint is soft-fail: a single API hiccup doesn't kill the whole run.
#
# Active window: 06:00 AM – 10:00 PM ET = 10:00–02:00 UTC.
# Starts at 10:00 UTC (6 AM ET) to cover T-3/T-1 for the earliest morning games
# (10:00 AM ET first pitch). Railway cron fires hourly all day; exit early outside window.
set -euo pipefail

# Time-window guard (UTC hours 03–09 = outside 10:00 UTC - 02:00 UTC active window).
HOUR=$(date -u +%H)
HOUR_INT=$((10#$HOUR))
if [ "$HOUR_INT" -ge 3 ] && [ "$HOUR_INT" -le 9 ]; then
  echo "[weather_capture] UTC hour $HOUR_INT outside active window (10-2 UTC), exiting"
  exit 0
fi

# Railway stores the private key as an env string; the Snowflake connector wants a FILE.
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "$SNOWFLAKE_PRIVATE_KEY" > /tmp/snowflake_rsa_key.pem
  chmod 600 /tmp/snowflake_rsa_key.pem
  export SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem
fi

TODAY=$(date -u +%Y-%m-%d)
echo "[weather_capture] $(date -u +%FT%TZ) start — date=$TODAY"

# Forecast checkpoints — each is non-fatal (mirrors the Dagster soft-fail loop).
for HOURS in 24 6 3 1; do
  echo "[weather_capture] T-${HOURS}h forecast checkpoint"
  python ingest_weather.py \
    --date "$TODAY" \
    --observation-type forecast_intraday \
    --hours-to-first-pitch "$HOURS" \
  || echo "[weather_capture] WARNING: T-${HOURS}h checkpoint failed (non-fatal)"
done

# Observed-at-first-pitch (no-op before games start; script skips if no pitched games).
echo "[weather_capture] observed_at_first_pitch checkpoint"
python ingest_weather.py --observation-type observed_at_first_pitch \
  || echo "[weather_capture] WARNING: observed_at_first_pitch failed (non-fatal)"

echo "[weather_capture] $(date -u +%FT%TZ) done"
