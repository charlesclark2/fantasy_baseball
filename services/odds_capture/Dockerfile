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

# odds_api_ingestion.py needs these — no ML / dbt / Dagster stack (kept lean on purpose).
# 2026-07-05: +pyarrow +boto3 so this image writes the S3 lakehouse_raw mirror ITSELF
# (LAKEHOUSE_RAW_WRITE_MODE=s3). The Snowflake decommission wants odds capture S3-NATIVE, not SF-only —
# SF-only would keep the oddsapi.mlb_odds_raw table alive purely to be re-mirrored by a separate export
# cron (more footprint, not less). boto3 resolves S3 via the instance-role chain (make_s3_client passes
# NO keys). snowflake-connector stays for now (the entrypoint still materializes the key).
RUN pip install --no-cache-dir \
    requests \
    snowflake-connector-python \
    cryptography \
    python-dotenv \
    pyarrow \
    boto3

WORKDIR /app

# odds_api_ingestion.py + date_utils.py are self-contained (no betting_ml/pipeline imports — enforced by
# test_lean_capture_images_selfcontained.py). PLUS the shared lakehouse raw-writer so the writer lands
# parquet in S3 directly: only lakehouse_raw_writer.py is imported for write_raw_rows_s3 — its
# snowflake_loader dep is lazy (inside append_raw_rows_lakehouse, which the S3 path never calls).
COPY scripts/odds_api_ingestion.py scripts/date_utils.py ./
COPY scripts/utils/__init__.py ./utils/__init__.py
COPY scripts/utils/lakehouse_raw_writer.py ./utils/lakehouse_raw_writer.py
COPY services/odds_capture/entrypoint.sh ./
RUN chmod +x entrypoint.sh

# One capture, then exit (Railway cron re-invokes on schedule).
CMD ["./entrypoint.sh"]
