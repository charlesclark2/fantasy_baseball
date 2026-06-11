"""Snowflake connection service for the Credence Sports API backend.

Connection pattern mirrors betting_ml/utils/data_loader.py::_connect() but adapted for
Lambda: private key arrives via SNOWFLAKE_PRIVATE_KEY env var (raw PEM or base64-encoded
PEM) instead of a filesystem path. Falls back to file-based key for local development.

No connection pooling — Lambda creates a new connection per invocation.
Role in use must be read-only for all SELECT endpoints. Only POST /bets is permitted
INSERT access, and only to baseball_data.betting_ml.user_bets.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

_FALLBACK_KEY_PATH = os.environ.get(
    "SNOWFLAKE_PRIVATE_KEY_PATH",
    os.path.expanduser(
        "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
    ),
)


def _load_private_key_bytes() -> bytes:
    key_val = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "").strip()
    if key_val:
        if not key_val.startswith("-----"):
            # base64-encoded PEM — decode first
            key_val = base64.b64decode(key_val).decode("utf-8")
        pem_bytes = key_val.encode("utf-8")
    else:
        with open(_FALLBACK_KEY_PATH, "rb") as fh:
            pem_bytes = fh.read()

    p_key = serialization.load_pem_private_key(
        pem_bytes, password=None, backend=default_backend()
    )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def get_snowflake_connection(
    schema: str | None = None,
) -> snowflake.connector.SnowflakeConnection:
    """Open a Snowflake connection. Caller is responsible for closing it.

    The role must be read-only for all backend queries except POST /bets
    (INSERT on baseball_data.betting_ml.user_bets only).
    """
    pkb = _load_private_key_bytes()
    kwargs: dict[str, Any] = dict(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "IHUPICS-DP59975"),
        user=os.environ.get("SNOWFLAKE_USER", "dbt_rw"),
        private_key=pkb,
        role=os.environ.get("SNOWFLAKE_ROLE", "CREDENCE_API_RO"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="baseball_data",
    )
    if schema:
        kwargs["schema"] = schema
    return snowflake.connector.connect(**kwargs)


def execute_query(query: str, params: dict | None = None) -> list[dict]:
    """Run a query, return all rows as dicts, and close the connection."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(query, params or {})
        return cur.fetchall()
    finally:
        conn.close()
