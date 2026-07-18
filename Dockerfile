FROM python:3.12-slim

# libgomp1 = GNU OpenMP runtime (libgomp.so.1). LightGBM / XGBoost / CatBoost
# dlopen it at import time; the python:3.12-slim base does not ship it, so
# unpickling any tree-model artifact (e.g. offense_v2, starter_ip_v1) fails with
# "OSError: libgomp.so.1: cannot open shared object file".
RUN apt-get update && apt-get install -y curl libgomp1 && rm -rf /var/lib/apt/lists/*

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
#
# 🔒 PICKLE-FRAGILE ML LIBS ARE PINNED EXACT — and MUST stay in lockstep with the
# `==` pins in pyproject.toml / uv.lock. Every served model artifact is a
# joblib/pickle of a scikit-learn / ngboost / lightgbm / xgboost / catboost
# estimator; those pickles embed version-specific (often Cython) internals, so a
# train/serve version skew fails to UNPICKLE at serve time. This image is the
# SERVING runtime — it must match the training env that created the S3 artifacts.
# Historically this block used bare, UNPINNED names, so every rebuild floated all
# ML libs to latest PyPI (e.g. scikit-learn drifted to 1.9.0 while the lock said
# 1.8.0 → sklearn._loss moved → "No module named '_loss'" broke strikeout_glm_v1
# on the box). Bump a version here only alongside a re-fit + re-promote of every
# affected artifact AND the matching pyproject/uv.lock bump, in the same PR.
RUN pip install --no-cache-dir \
    "dagster>=1.11.5" \
    dagster-cloud \
    dagster-webserver \
    dagster-pipes \
    dagster-dbt \
    dagster-snowflake \
    dagster-postgres \
    pandas==2.3.3 \
    numpy==2.4.4 \
    scikit-learn==1.8.0 \
    joblib==1.5.3 \
    "snowflake-connector-python>=3.6" \
    cryptography \
    statsmodels==0.14.6 \
    scipy==1.17.1 \
    xgboost==3.2.0 \
    ngboost==0.5.10 \
    shap==0.49.1 \
    optuna \
    pyarrow \
    "mlb-statsapi>=0.0.44" \
    python-dotenv \
    plotly \
    curl-cffi \
    lightgbm==4.6.0 \
    catboost==1.2.10 \
    requests \
    pyyaml \
    mlflow \
    boto3 \
    psycopg2-binary \
    arviz \
    h5netcdf \
    h5py \
    pymc \
    "duckdb>=1.1.0" \
    deltalake==1.6.1 \
    polars==1.42.1 \
    "dbt-duckdb>=1.9,<2.0"

# Guard: fail the image build NOW if any pickle-fragile serving lib resolved to a
# version other than the pinned/locked one (belt-and-suspenders over the == pins —
# catches a stale cached layer or a transitive override). A serving pickle failing
# to load is a silent WARN-tier degrade in prod; catching skew here makes it loud.
RUN python -c "\
import importlib.metadata as m; \
want={'scikit-learn':'1.8.0','ngboost':'0.5.10','lightgbm':'4.6.0','xgboost':'3.2.0','catboost':'1.2.10','joblib':'1.5.3','numpy':'2.4.4','scipy':'1.17.1','pandas':'2.3.3'}; \
bad={p:(m.version(p),v) for p,v in want.items() if m.version(p)!=v}; \
assert not bad, f'PICKLE-FRAGILE LIB VERSION SKEW (got,want): {bad} — serving artifacts will fail to unpickle; align Dockerfile+pyproject+uv.lock'; \
print('pickle-fragile serving libs pinned OK:', want)"

# Smoke-check: fail the image build now if any heavy Bayesian dep is missing,
# rather than silently dying in the weekly Dagster op a day later.
# h5py is h5netcdf's HDF5 backend — importing h5netcdf alone succeeds but file
# writes fail at runtime without h5py, so we must check both explicitly.
RUN python -c "import pymc; import pytensor; import arviz; import h5netcdf; import h5py; print('Bayesian deps OK')"
RUN python -c "import duckdb; print('duckdb OK')"
# E11.20 — Delta lakehouse deps: fail the build NOW on a deltalake/polars version skew
# (delta-rs 1.x had breaking API churn; scripts/utils/delta_lake.py is written against
# 1.6), and PRE-BAKE the DuckDB `delta` + `httpfs` extensions into the image so the
# HALT-tier daily ops never depend on a runtime `INSTALL delta` network fetch.
RUN python -c "\
import importlib.metadata as m; \
want={'deltalake':'1.6.1','polars':'1.42.1'}; \
bad={p:(m.version(p),v) for p,v in want.items() if m.version(p)!=v}; \
assert not bad, f'DELTA DEP VERSION SKEW (got,want): {bad} — align Dockerfile+pyproject+uv.lock'; \
import deltalake, polars; print('delta deps OK:', want)"
RUN python -c "\
import duckdb; c=duckdb.connect(); \
c.execute('INSTALL httpfs'); c.execute('INSTALL delta'); c.execute('LOAD delta'); \
print('duckdb delta extension baked OK')"
# NFL-N0.3 — the sports_dbt build (pipeline/jobs/sports_dbt_job.py runs `python -m dbt.cli.main`)
# needs the dbt-duckdb ADAPTER, which `dagster-dbt`→dbt-core does NOT pull in. Fail the build NOW
# if it's missing (the box otherwise dies with "Could not find adapter type duckdb!" at run time).
# Coexists with dbt-fusion: fusion's /usr/local/bin/dbt stays the MLB Snowflake path; the sports
# job invokes the dbt-core python module + duckdb adapter, a separate DuckDB-native DAG.
RUN python -c "import dbt.adapters.duckdb; print('dbt-duckdb adapter OK')"
# E11.15 — OSS self-host stores run/event/schedule state in Postgres; the storage class
# dagster_postgres.DagsterPostgresStorage must import or the instance won't load.
RUN python -c "from dagster_postgres import DagsterPostgresStorage; print('dagster_postgres OK')"

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
