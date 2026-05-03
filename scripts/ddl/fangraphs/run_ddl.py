"""
run_ddl.py
----------
One-time script to create the baseball_data.fangraphs schema and all four
FanGraphs raw tables in Snowflake.

Usage:
    uv run python scripts/ddl/fangraphs/run_ddl.py
"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "utils"))
from snowflake_loader import get_snowflake_connection  # noqa: E402

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

DDL_STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS baseball_data.fangraphs",

    """CREATE TABLE IF NOT EXISTS baseball_data.fangraphs.fg_stuff_plus_raw (
        season              INTEGER         NOT NULL,
        pitcher_name        VARCHAR(256),
        fg_pitcher_id       VARCHAR(64),
        load_id             VARCHAR(64)     NOT NULL,
        ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        source_endpoint     VARCHAR(1024),
        request_params      VARIANT,
        http_status_code    INTEGER,
        raw_json            VARIANT         NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS baseball_data.fangraphs.fg_zips_pitching_raw (
        season              INTEGER         NOT NULL,
        pitcher_name        VARCHAR(256),
        fg_pitcher_id       VARCHAR(64),
        projection_type     VARCHAR(64),
        load_id             VARCHAR(64)     NOT NULL,
        ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        source_endpoint     VARCHAR(1024),
        request_params      VARIANT,
        http_status_code    INTEGER,
        raw_json            VARIANT         NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS baseball_data.fangraphs.fg_zips_hitting_raw (
        season              INTEGER         NOT NULL,
        batter_name         VARCHAR(256),
        fg_batter_id        VARCHAR(64),
        projection_type     VARCHAR(64),
        load_id             VARCHAR(64)     NOT NULL,
        ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        source_endpoint     VARCHAR(1024),
        request_params      VARIANT,
        http_status_code    INTEGER,
        raw_json            VARIANT         NOT NULL
    )""",

    """CREATE TABLE IF NOT EXISTS baseball_data.fangraphs.fg_hitting_leaderboard_raw (
        season              INTEGER         NOT NULL,
        window_type         VARCHAR(16)     NOT NULL,
        window_start        DATE            NOT NULL,
        window_end          DATE            NOT NULL,
        load_id             VARCHAR(64)     NOT NULL,
        ingestion_ts        TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        source_endpoint     VARCHAR(1024),
        request_params      VARIANT,
        http_status_code    INTEGER,
        raw_json            VARIANT         NOT NULL
    )""",
]


def main() -> None:
    conn = get_snowflake_connection(database="baseball_data", schema="public")
    try:
        with conn.cursor() as cur:
            for stmt in DDL_STATEMENTS:
                label = stmt.strip().splitlines()[0][:80]
                log.info("Executing: %s ...", label)
                cur.execute(stmt)
                log.info("  OK")
        log.info("All FanGraphs DDL applied successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("DDL run failed")
        sys.exit(1)
