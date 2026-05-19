FROM python:3.12-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install dbt-fusion binary
# SHELL must be set — the install script references $SHELL to update shell config files
# and will abort with "SHELL: parameter not set" if it's unset (as in Docker containers)
RUN SHELL=/bin/bash curl -fsSL https://public.cdn.getdbt.com/fs/install/install.sh | sh -s -- --to /usr/local/bin

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

# Dagster hybrid agent entry point
CMD ["dagster-cloud", "agent", "run"]
