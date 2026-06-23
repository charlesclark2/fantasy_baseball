-- E11.1-W1 lakehouse helper macros.
-- These macros centralize S3 path logic for dbt-duckdb model migrations.
-- All Wave 1 mart models call lakehouse_loc() so the bucket is in one place.

-- S3 bucket + prefix used by all lakehouse models.
{% macro lakehouse_bucket() %}baseball-betting-ml-artifacts{% endmacro %}
{% macro lakehouse_prefix() %}baseball/lakehouse{% endmacro %}

-- Full S3 path for a named model (directory style, trailing slash for glob).
{% macro lakehouse_loc(model_name) %}s3://{{ lakehouse_bucket() }}/{{ lakehouse_prefix() }}/{{ model_name }}/{% endmacro %}

-- Called from on-run-start when --target duckdb. Creates a persistent S3 secret
-- using the AWS credential chain (reads ~/.aws/credentials the same way the CLI does)
-- so httpfs can reach the lakehouse bucket without requiring explicit env-var exports.
-- dbt-fusion does not apply env_var() from profiles.yml settings to DuckDB connections
-- (it ignores the settings dict), so this hook is the credential injection point.
{% macro setup_duckdb_s3_secret() %}
  {% if target.name == 'duckdb' %}
    CREATE OR REPLACE PERSISTENT SECRET baseball_s3 (
      TYPE S3,
      PROVIDER credential_chain,
      REGION 'us-east-2'
    )
  {% endif %}
{% endmacro %}
