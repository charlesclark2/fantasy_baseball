"""
snowflake_loader.py
-------------------
Shared Snowflake connection factory and raw-table append utility.

Public API:
  get_snowflake_connection(database, schema) -> SnowflakeConnection
  append_raw_rows(table_fqn, rows, conn) -> int

Columns named 'raw_json' or 'request_params' are automatically wrapped in
PARSE_JSON() on insert; all others are bound as plain scalars.
The 'ingestion_ts' column is omitted from INSERT so the DEFAULT CURRENT_TIMESTAMP
defined in DDL fires on every row.

Authentication env vars (same convention as all other ingest scripts):
  SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE  (required)
  SNOWFLAKE_PRIVATE_KEY_PATH                              (preferred auth)
  SNOWFLAKE_PRIVATE_KEY_PASSPHRASE                        (optional)
  SNOWFLAKE_PASSWORD                                      (fallback)
  SNOWFLAKE_ROLE                                          (optional)
"""

import json
import logging
import os
import time

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)

log = logging.getLogger(__name__)

_JSON_COLS = frozenset({"raw_json", "request_params"})
_SKIP_COLS = frozenset({"ingestion_ts"})


class SnowflakeLoadError(Exception):
    pass


def _load_private_key(path: str, passphrase: str | None) -> bytes:
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def get_snowflake_connection(
    database: str = "baseball_data",
    schema: str = "fangraphs",
) -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  database,
        "schema":    schema,
    }

    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if private_key_path:
        log.info("Authenticating with private key: %s", private_key_path)
        kwargs["private_key"] = _load_private_key(
            private_key_path,
            os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
        )
    else:
        password = os.environ.get("SNOWFLAKE_PASSWORD")
        if not password:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        log.info("Authenticating with password")
        kwargs["password"] = password

    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role

    # E11.3 — tag every session with the Dagster job name so ACCOUNT_USAGE.QUERY_HISTORY
    # gives cost-by-job attribution. Set DAGSTER_JOB_NAME in the subprocess env from each
    # Dagster op (_run_script injects it); falls back to 'manual' for local runs.
    job_tag = os.environ.get("DAGSTER_JOB_NAME", "manual")
    env_tag = os.environ.get("TARGET_ENV", "dev")
    kwargs["session_parameters"] = {"QUERY_TAG": f"{job_tag}|{env_tag}"}

    return snowflake.connector.connect(**kwargs)


_BATCH_SIZE = 200


def append_raw_rows(
    table_fqn: str,
    rows: list[dict],
    conn: snowflake.connector.SnowflakeConnection,
) -> int:
    """INSERT rows into table_fqn; returns number of rows inserted.

    Columns in _JSON_COLS are serialised to JSON string and wrapped in
    PARSE_JSON(). Columns in _SKIP_COLS are omitted (rely on DDL defaults).

    Rows are batched into _BATCH_SIZE-row UNION ALL statements so that each
    network round-trip to Snowflake inserts multiple rows at once.
    """
    if not rows:
        return 0

    start_ms = time.monotonic() * 1000
    load_id = rows[0].get("load_id", "unknown")

    columns = [c for c in rows[0].keys() if c not in _SKIP_COLS]
    row_select = "SELECT " + ", ".join(
        "PARSE_JSON(%s)" if c in _JSON_COLS else "%s"
        for c in columns
    )
    col_list = ", ".join(columns)

    def _to_values(row: dict) -> list:
        vals = []
        for col in columns:
            v = row.get(col)
            vals.append(json.dumps(v) if col in _JSON_COLS and v is not None else v)
        return vals

    try:
        with conn.cursor() as cur:
            for i in range(0, len(rows), _BATCH_SIZE):
                batch = rows[i : i + _BATCH_SIZE]
                sql = (
                    f"INSERT INTO {table_fqn} ({col_list}) "
                    + " UNION ALL ".join(row_select for _ in batch)
                )
                params = [v for row in batch for v in _to_values(row)]
                cur.execute(sql, params)
    except Exception as exc:
        raise SnowflakeLoadError(
            f"Failed inserting into {table_fqn} (load_id={load_id})"
        ) from exc

    elapsed_ms = time.monotonic() * 1000 - start_ms
    log.info(
        "Appended %d rows to %s (load_id=%s, elapsed=%.0fms)",
        len(rows), table_fqn, load_id, elapsed_ms,
    )
    return len(rows)
