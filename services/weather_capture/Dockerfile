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

RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv

WORKDIR /app

# ingest_weather.py is self-contained (no betting_ml/pipeline imports).
COPY scripts/ingest_weather.py ./
COPY services/weather_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One weather capture per Railway-cron fire, then exit.
CMD ["./entrypoint.sh"]
