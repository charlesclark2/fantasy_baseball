# Lean Railway "cron service" image for live Odds API capture (Story 12.3.7 / A2.18).
# Runs ONCE per Railway-cron fire and exits — NOT always-on, NOT in Dagster (the I/O-bound
# capture stays off the Dagster+ run-minute bill). Build context = REPO ROOT so the two
# self-contained scripts can be copied from scripts/.
#
#   docker build -f services/odds_capture/Dockerfile -t odds-capture .
#
# Railway: point the service at this Dockerfile with the repo root as build context,
# set the env vars in services/odds_capture/README.md, and set a Cron Schedule.
FROM python:3.12-slim

# odds_api_ingestion.py needs exactly these — no ML / dbt / Dagster stack (kept lean on purpose).
RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv

WORKDIR /app

# Both scripts are self-contained (no betting_ml/pipeline imports).
COPY scripts/odds_api_ingestion.py scripts/date_utils.py ./
COPY services/odds_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One capture, then exit (Railway cron re-invokes on schedule).
CMD ["./entrypoint.sh"]
