#!/usr/bin/env python3
"""
scripts/refresh_w1_external_tables.py
E11.1-W1d: Refresh Snowflake external table metadata after S3 writes.

External tables with AUTO_REFRESH=FALSE cache their file listing at creation
time.  This script runs ALTER EXTERNAL TABLE ... REFRESH for all 7 mart_pitch_*
external tables so Snowflake sees the files just written by run_w1_lakehouse.py.

Tier: HALT (serving-critical — the daily feature build reads from these tables).
Run: uv run python scripts/refresh_w1_external_tables.py
"""

import os
import sys

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv()

_SCHEMA = "baseball_data.lakehouse_ext"

W1_TABLES = [
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
]


def _load_private_key():
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw, password=passphrase.encode() if passphrase else None, backend=default_backend()
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    import snowflake.connector
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="lakehouse_ext",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


def main():
    conn = get_snowflake_conn()
    cur = conn.cursor()
    failed = []
    for table in W1_TABLES:
        fqn = f"{_SCHEMA}.{table}"
        try:
            cur.execute(f"ALTER EXTERNAL TABLE {fqn} REFRESH")
            print(f"  refreshed {fqn}")
        except Exception as e:
            print(f"  FAILED {fqn}: {e}", file=sys.stderr)
            failed.append(table)
    cur.close()
    conn.close()
    if failed:
        raise RuntimeError(
            f"External table refresh FAILED for: {failed}  "
            "Downstream feature build will see stale S3 data."
        )
    print("W1 external table refresh complete.")


if __name__ == "__main__":
    main()
