"""Snowflake connection service for the Credence Sports API backend.

Connection pattern mirrors betting_ml/utils/data_loader.py::_connect() but adapted for
Lambda: private key arrives via SNOWFLAKE_PRIVATE_KEY env var (raw PEM or base64-encoded
PEM) instead of a filesystem path. Falls back to file-based key for local development.

No connection pooling — Lambda creates a new connection per invocation.
Role in use must be read-only for all SELECT endpoints. Only POST /bets is permitted
INSERT access, and only to baseball_data.betting_ml.user_bets.

⏱️ EVERY HEAVY IMPORT IN HERE IS LAZY, AND THAT IS A COLD-START PROPERTY OF THE WHOLE API, NOT A
STYLE CHOICE (PERF, 2026-08-11). `snowflake.connector` imports `snowflake.connector.options`, which
imports **pandas** (and through it **pyarrow**) unconditionally — its optional-dependency probe. This
module is imported at MODULE SCOPE by `routers/{admin,finances,pipeline}.py`, and `main.py` imports
every router to register it, so `import app.backend.main` pulled pandas + pyarrow into the init of
EVERY Lambda cold start. Measured on the deployed function: init averaged 3,976 ms (p50 4,023 ms,
max 5,130 ms) against a warm p50 of 88 ms, and `routers.admin` alone was 595 ms of a 1,383 ms local
import — 466 ms of it this module. Nothing on a user request path has ever needed Snowflake (the
repo rule is that Snowflake is never on a request path); the three routers that use it are
admin/ops surfaces, so they are the right place to pay for it, on first use.

⛔ DO NOT MOVE THESE BACK TO MODULE SCOPE, and do not add a new module-scope import of
`snowflake.connector` (or pandas/pyarrow) anywhere `main.py` can reach at import time — it silently
adds seconds to every cold start for every caller, with no error and no failing test to notice it.
Guarded by `betting_ml/tests/test_api_cold_start_imports.py`, which imports `app.backend.main` in a
subprocess and fails if pandas/pyarrow/snowflake.connector landed in `sys.modules`.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # import-free at runtime; keeps the annotation resolvable for type checkers
    import snowflake.connector

logger = logging.getLogger(__name__)

_FALLBACK_KEY_PATH = os.environ.get(
    "SNOWFLAKE_PRIVATE_KEY_PATH",
    os.path.expanduser(
        "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
    ),
)


def _load_private_key_bytes() -> bytes:
    # Lazy — see the module docstring. `cryptography` is cheap next to pandas, but it is only ever
    # needed on the connection path, so it rides along rather than being loaded for every caller.
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

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
    import snowflake.connector  # lazy — see the module docstring

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
    import snowflake.connector  # lazy — see the module docstring

    conn = get_snowflake_connection(warehouse=warehouse)
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute(query, params or {})
        return cur.fetchall()
    finally:
        conn.close()
