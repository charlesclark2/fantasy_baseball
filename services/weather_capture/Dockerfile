# Lean Railway cron image for E11.4 intraday weather capture.
# Replaces the Dagster `intraday_weather_job` (~7% of Dagster+ run-minutes).
# Runs ONCE per Railway-cron fire and exits — NOT always-on, NOT in Dagster.
# Build context = REPO ROOT so the script can be copied from scripts/.
#
#   docker build -f services/weather_capture/Dockerfile -t weather-capture .
#
# Railway: point the service at this Dockerfile with the repo root as build context,
# set the env vars below, and configure Cron Schedule.
#
# Required env vars (set in Railway service settings):
#   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
#   SNOWFLAKE_PRIVATE_KEY   — PEM key content (Railway stores as env string)
#   SNOWFLAKE_ROLE          (optional)
#   OPENWEATHERMAP_API_KEY  (optional; enables fallback source)

FROM python:3.12-slim

# E11.1-W11 Tier-C: pyarrow + boto3 added so this cron image can write the S3 lakehouse mirror
# (weather_raw dual-write under W11_RAW_WRITE_MODE) AND the hourly all-slate-park weather
# time-series (weather_intraday_series, always S3). ⚠️ W12/W9 landmine: a monitor/consumer
# repointed to an S3 mirror needs the mirror WRITTEN on the same cadence — this image writes S3
# whenever the hourly capture fires (the S3-native-writer flip), so the intraday series stays fresh.
RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv \
    boto3 \
    pyarrow

WORKDIR /app

# ingest_weather.py imports scripts/utils/lakehouse_raw_writer (the shared S3 raw writer), so the
# utils package is copied alongside it. Still no betting_ml/pipeline imports.
COPY scripts/ingest_weather.py ./
COPY scripts/utils/ ./utils/
COPY services/weather_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One weather capture per Railway-cron fire, then exit.
CMD ["./entrypoint.sh"]
