FROM python:3.12-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Required: the dbt-fusion install script references $SHELL when updating shell configs.
# In Docker there is no $SHELL by default; setting it here prevents a non-zero exit.
ENV SHELL=/bin/bash

ENV DAGSTER_HOME=/app/dagster_home

# Make the repo-root packages (pipeline, betting_ml) importable in-process for
# every process the agent spawns — code server, sensor/schedule daemons, etc.
# The project is not pip-installed, and sensors evaluate in-process (unlike the
# subprocess ops, which insert sys.path themselves). Without this, in-process
# `import betting_ml` raises ModuleNotFoundError during sensor evaluation
# (e.g. clv_alert_sensor).
ENV PYTHONPATH=/app

WORKDIR /app

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock* ./

# Install project Python deps + Dagster stack
# (dbt-core's `dbt` CLI is installed here as a side-effect of dagster-dbt)
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

# Install dbt-fusion AFTER pip so it overwrites dbt-core's `dbt` CLI entry point.
# The pip install of dagster-dbt pulls in dbt-core which places its own `dbt`
# binary at /usr/local/bin/dbt; installing fusion last ensures fusion wins.
RUN curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh | sh -s -- --to /usr/local/bin --update && \
    ln -sf /usr/local/bin/dbt /usr/local/bin/dbtf

# Copy the full project
COPY . .

# Generate dbt manifest so @dbt_assets can load it at import time.
# parse reads profile metadata but does not connect to Snowflake.
RUN touch /tmp/snowflake_rsa_key.pem && \
    SNOWFLAKE_PRIVATE_KEY_PATH=/tmp/snowflake_rsa_key.pem \
    dbtf parse --project-dir dbt --profiles-dir dbt

# Dagster hybrid agent entry point
CMD ["dagster-cloud", "agent", "run"]
