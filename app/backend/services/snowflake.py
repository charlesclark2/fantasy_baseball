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


# E11.24 — the warehouse for ACCOUNT_USAGE cost/metering reads (the admin + finances cost
# panels). Measured 2026-07-29: today those queries wake NOTHING (0 of 636 resumes over 8 days
# had one as the first-query-after-resume) — they are PASSENGERS that only ever run while the
# warehouse is already awake for pipeline work. ⚠️ That is precisely why they must move BEFORE
# the literal-zero cutovers land: once targets 1/2/6 quiet the warehouse down and it actually
# sleeps, "open the admin cost page" becomes the first query after a resume — i.e. the page
# that displays the Snowflake bill starts BILLING for the privilege. Routing them to a separate
# X-Small warehouse makes that structurally impossible.
# Needs: GRANT USAGE ON WAREHOUSE MONITOR_WH TO ROLE CREDENCE_API_RO. Both call sites already
# swallow their exceptions and degrade to an empty panel, so a missing grant is cosmetic.
MONITORING_WAREHOUSE = os.environ.get("SNOWFLAKE_MONITOR_WAREHOUSE", "MONITOR_WH")


def get_snowflake_connection(
    schema: str | None = None,
    warehouse: str | None = None,
) -> snowflake.connector.SnowflakeConnection:
    """Open a Snowflake connection. Caller is responsible for closing it.

    The role must be read-only for all backend queries except POST /bets
    (INSERT on baseball_data.betting_ml.user_bets only).

    Pass `warehouse` for ACCOUNT_USAGE cost/metering reads (see MONITORING_WAREHOUSE) so a
    cost query can never resume the warehouse it is reporting on.
    """
    pkb = _load_private_key_bytes()
    kwargs: dict[str, Any] = dict(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "IHUPICS-DP59975"),
        user=os.environ.get("SNOWFLAKE_USER", "dbt_rw"),
        private_key=pkb,
        role=os.environ.get("SNOWFLAKE_ROLE", "CREDENCE_API_RO"),
        warehouse=warehouse or os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="baseball_data",
    )
    if schema:
        kwargs["schema"] = schema
    return snowflake.connector.connect(**kwargs)


def execute_query(query: str, params: dict | None = None,
                  warehouse: str | None = None) -> list[dict]:
    """Run a query, return all rows as dicts, and close the connection."""
    conn = get_snowflake_connection(warehouse=warehouse)
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(query, params or {})
        return cur.fetchall()
    finally:
        conn.close()
