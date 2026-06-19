# Lean Railway cron image for E11.4 intraday schedule capture + dbt staging rebuild.
# Replaces the Dagster `intraday_schedule_job` (intraday_schedule_capture + intraday_lineup_rebuild).
# Runs ONCE per Railway-cron fire and exits — NOT always-on, NOT in Dagster.
# Build context = REPO ROOT so scripts can be copied from scripts/.
#
#   docker build -f services/schedule_capture/Dockerfile -t schedule-capture .
#
# Railway: point the service at this Dockerfile with the repo root as build context,
# set the env vars in the comment block below, and configure Cron Schedule.
#
# Required env vars (set in Railway service settings):
#   SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
#   SNOWFLAKE_PRIVATE_KEY   — PEM key content (Railway stores as env string)
#   SNOWFLAKE_ROLE          (optional)
#   DBT_RUNNER_URL          — E11.0 dbt-runner service URL
#   DBT_RUNNER_AUTH_TOKEN   — E11.0 bearer token

FROM python:3.12-slim

RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv

WORKDIR /app

# ingest_statsapi.py is self-contained (stdlib + pip deps above; no betting_ml/pipeline imports).
COPY scripts/ingest_statsapi.py ./
COPY services/schedule_capture/trigger_dbt.py ./
COPY services/schedule_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One capture + dbt trigger per Railway-cron fire, then exit.
CMD ["./entrypoint.sh"]
