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
    python-dotenv \
    tzdata \
    boto3 \
    pyarrow
    # tzdata (INC-22): the slim image ships no system zoneinfo DB, so entrypoint.sh's
    # zoneinfo('America/Los_Angeles') baseball-day resolution needs the tzdata wheel.
    # boto3 + pyarrow (E11.20 phase-2a): ingest_statsapi.py now imports utils.lakehouse_raw_writer
    # (pyarrow at module load; boto3 at S3-write time) to gate the monthly_schedule S3 dual-write on
    # W11_RAW_WRITE_MODE. Made S3-CAPABLE (not overridden to SF-only) so the flag can never reach
    # this env_file image and break it — the odds-capture landmine cure (2026-07-05). This is a
    # dormant fallback (the Dagster intraday_schedule_capture schedules own the tick), but it stays
    # correct if reactivated. See docs/monthly_schedule_s3_flip_design.md.

WORKDIR /app

# ingest_statsapi.py + utils.lakehouse_raw_writer are self-contained (stdlib + the pip deps above;
# NO betting_ml/pipeline/pandas imports — enforced by test_lean_capture_images_selfcontained.py).
COPY scripts/ingest_statsapi.py ./
COPY scripts/utils/__init__.py ./utils/__init__.py
COPY scripts/utils/lakehouse_raw_writer.py ./utils/lakehouse_raw_writer.py
COPY services/schedule_capture/trigger_dbt.py ./
COPY services/schedule_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One capture + dbt trigger per Railway-cron fire, then exit.
CMD ["./entrypoint.sh"]
