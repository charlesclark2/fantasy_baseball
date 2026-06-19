# E11.0 — dbt-runner Railway service.
# Runs the baseball dbt project (dbt-fusion → Snowflake) as a standalone
# HTTP-triggered container so dbt execution moves off Dagster+ run-minutes.
# Dagster ops POST /run; the server spawns dbtf and exposes /status/{run_id}
# for polling. Build context = REPO ROOT (same pattern as services/odds_capture).
#
#   docker build -f services/dbt_runner/Dockerfile -t dbt-runner .
#
# Railway: point the service at this Dockerfile with the repo root as the build
# context; set env vars (SNOWFLAKE_*, DBT_RUNNER_AUTH_TOKEN, TARGET_ENV);
# configure as a web service (not a cron — it's always-on, Dagster triggers it).

FROM python:3.12-slim

# curl is needed for the dbt-fusion install script.
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# dbt-fusion install script checks $SHELL when patching shell profiles.
# In Docker there is no $SHELL by default; set it to suppress a non-zero exit.
ENV SHELL=/bin/bash

WORKDIR /dbt_runner

# Install the HTTP server deps (lean — no ML / Dagster stack).
COPY services/dbt_runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install dbt-fusion and symlink as dbtf (mirrors the main Dockerfile).
RUN curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh \
      | sh -s -- --to /usr/local/bin --update && \
    ln -sf /usr/local/bin/dbt /usr/local/bin/dbtf

# Copy the baseball dbt project.
COPY dbt/ /dbt/

# HTTP server entrypoint.
COPY services/dbt_runner/server.py .
COPY services/dbt_runner/entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
