# NFL lakehouse ingest image (NFL-N0.2).
#
# Runs the registry-driven ingest (weekly incremental) and the off-Lambda backfill. Per the
# CURRENT cross-sport decision (sport_data_platform.md §16.3) prod orchestration is a Dagster
# op on the existing EC2 box, NOT Lambda+EventBridge — but the image keeps the AWS Lambda base
# so the platform-doc's original Lambda sketch still works if ever wanted.
#
# 🪪 S3 auth = the INSTANCE ROLE on the box (AWS_ACCESS_KEY_ID is UNSET there). s3io.py resolves
# the botocore chain and passes explicit creds to delta-rs — NEVER bake keys here.
FROM public.ecr.aws/lambda/python:3.12

# Delta pins MATCH pyproject.toml (E11.20) — an unpinned float would risk format drift.
COPY quant_sports_intel_models/football/nfl/ingest/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The ingest package (import path: ...football.nfl.ingest).
COPY quant_sports_intel_models/football/nfl/ingest/ \
     ${LAMBDA_TASK_ROOT}/quant_sports_intel_models/football/nfl/ingest/
# Namespace-package __init__ shims so the dotted import resolves under the Lambda root.
RUN mkdir -p ${LAMBDA_TASK_ROOT}/quant_sports_intel_models/football/nfl && \
    touch ${LAMBDA_TASK_ROOT}/quant_sports_intel_models/__init__.py \
          ${LAMBDA_TASK_ROOT}/quant_sports_intel_models/football/__init__.py \
          ${LAMBDA_TASK_ROOT}/quant_sports_intel_models/football/nfl/__init__.py

# Lambda shape (platform-doc sketch). Box/Dagster/CLI runs call run_ingest / -m ...backfill.
CMD ["quant_sports_intel_models.football.nfl.ingest.handler.lambda_handler"]
