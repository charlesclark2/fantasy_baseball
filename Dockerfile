FROM python:3.12-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Required: the dbt-fusion install script references $SHELL when updating shell configs.
# In Docker there is no $SHELL by default; setting it here prevents a non-zero exit.
ENV SHELL=/bin/bash

# Install dbt-fusion binary
RUN curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh | sh -s -- --to /usr/local/bin

ENV DAGSTER_HOME=/app/dagster_home

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock* ./

# Install project Python deps + Dagster stack
RUN pip install --no-cache-dir \
    "dagster>=1.11.5" \
    dagster-cloud \
    dagster-webserver \
    dagster-pipes \
    dagster-dbt \
    dagster-snowflake \
    pandas \
    numpy \
    scikit-learn \
    joblib \
    "snowflake-connector-python>=3.6" \
    cryptography \
    statsmodels \
    scipy \
    xgboost \
    ngboost \
    shap \
    optuna \
    pyarrow \
    "mlb-statsapi>=0.0.44" \
    python-dotenv \
    plotly \
    curl-cffi \
    lightgbm \
    catboost \
    requests \
    pyyaml

# Copy the full project
COPY . .

# Generate dbt manifest so @dbt_assets can load it at import time.
# parse reads profile metadata but does not connect to Snowflake.
RUN touch /tmp/snowflake_rsa_key.pem && \
    SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem \
    dbt parse --project-dir dbt --profiles-dir dbt

# Dagster hybrid agent entry point
CMD ["dagster-cloud", "agent", "run"]
