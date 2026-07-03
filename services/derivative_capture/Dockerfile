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
# E11.1-W11-E: + boto3 for the gated S3 dual-write (write_raw_rows_s3 → lakehouse_raw/).
RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv \
    pandas \
    pyarrow \
    boto3

WORKDIR /app

COPY scripts/derivative_odds_backfill.py ./
# E11.1-W11-E: the shared lakehouse raw-writer (write_raw_rows_s3 + the W11 write-mode gate) so the
# live capture can dual-write S3. Only lakehouse_raw_writer.py is imported (its snowflake_loader dep
# is lazy — inside append_raw_rows_lakehouse, which this writer never calls); boto3 resolves S3 via
# the instance-role credential chain (make_s3_client passes NO keys). Needs AWS_DEFAULT_REGION set.
COPY scripts/utils/__init__.py ./utils/__init__.py
COPY scripts/utils/lakehouse_raw_writer.py ./utils/lakehouse_raw_writer.py
COPY services/derivative_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One capture run, then exit (Railway cron re-invokes on schedule).
CMD ["./entrypoint.sh"]
