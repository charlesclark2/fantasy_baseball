# Lean Railway cron image for E2.0b derivative-odds live capture.
# Runs ONCE per Railway-cron fire and exits (NOT always-on, NOT in Dagster).
# Build context = REPO ROOT so the script can be copied from scripts/.
#
#   docker build -f services/derivative_capture/Dockerfile -t derivative-capture .
#
# Railway: point the service at this Dockerfile with the repo root as build context,
# set the env vars listed in the Railway service (same set as odds_capture + Snowflake),
# and configure the Cron Schedule after running the probe.
FROM python:3.12-slim

# derivative_odds_backfill.py needs these — no ML / dbt / Dagster stack.
RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv \
    pandas \
    pyarrow

WORKDIR /app

COPY scripts/derivative_odds_backfill.py ./
COPY services/derivative_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One capture run, then exit (Railway cron re-invokes on schedule).
CMD ["./entrypoint.sh"]
