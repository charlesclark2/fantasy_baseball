import base64
import os
from pathlib import Path

from dagster_snowflake import SnowflakeResource
from dagster_dbt import DbtCliResource
from pipeline.resources.dbt_runner_resource import DbtRunnerResource  # E11.0


def _normalize_pem(raw: str) -> str:
    """Return a real multi-line PEM from however the key arrives in the env.

    INC-16-P2: on AWS the key is injected via a Docker Compose `env_file`, which
    CANNOT carry real newlines — so a pasted PEM arrives either base64-encoded
    (recommended, single line) or with literal ``\\n`` escapes. A raw multi-line
    PEM (Railway/Dagster+) is passed through unchanged. Without this, the verbatim
    write below produces an unparseable key file and every Snowflake consumer in
    the container fails with "Unable to load PEM file".
    """
    raw = raw.strip()
    if not raw:
        return raw
    # Check \n-escaped FIRST: such a value still starts with "-----BEGIN", so a
    # startswith("-----") passthrough would wrongly skip the conversion.
    if "\\n" in raw:
        return raw.replace("\\n", "\n").strip()  # \n-escaped single line
    if raw.startswith("-----"):
        return raw  # already a real (multi-line) PEM
    return base64.b64decode(raw).decode("utf-8")  # base64-encoded PEM


# Snowflake private key is injected as a PEM string via env var.
# Write it to a temp file on import so downstream connectors can reference the path.
_pem = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "")
_key_path = Path("/tmp/snowflake_rsa_key.pem")
if _pem:
    _key_path.write_text(_normalize_pem(_pem))
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
