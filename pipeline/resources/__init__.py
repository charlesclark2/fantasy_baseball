import os
from pathlib import Path

from dagster_snowflake import SnowflakeResource
from dagster_dbt import DbtCliResource

# Snowflake private key is injected as a PEM string via env var.
# Write it to a temp file on import so downstream connectors can reference the path.
_pem = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "")
_key_path = Path("/tmp/snowflake_rsa_key.pem")
if _pem and not _key_path.exists():
    _key_path.write_text(_pem)
    _key_path.chmod(0o600)
# Expose the key path to dbt via env var (profiles.yml reads SNOWFLAKE_PRIVATE_KEY_PATH)
os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"] = str(_key_path)

snowflake_resource = SnowflakeResource(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    role=os.environ["SNOWFLAKE_ROLE"],
    private_key_path=str(_key_path),
)

_dbt_dir = str(Path(__file__).parents[2] / "dbt")
dbt_resource = DbtCliResource(
    project_dir=_dbt_dir,
    profiles_dir=_dbt_dir,
)
