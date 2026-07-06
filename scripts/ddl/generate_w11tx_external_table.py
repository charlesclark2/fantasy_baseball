#!/usr/bin/env python3
"""
scripts/ddl/generate_w11tx_external_table.py   (E11.22 — player_transactions read-cutover)

Emit Snowflake EXTERNAL TABLE DDL over the S3 parquet that run_w1_lakehouse.py --w11tx writes, so
the stg_statsapi_transactions model's Snowflake (else) branch can read
`baseball_data.lakehouse_ext.stg_statsapi_transactions` instead of {{ source('statsapi',
'player_transactions') }} — the last un-repointed reader that blocked dropping the SF raw. The model
is TABLE-materialized on the Snowflake side (no incremental) → no DROP+rebuild at cutover.

The parquet is written by:
  scripts/run_w1_lakehouse.py --w11tx  (→ lakehouse/stg_statsapi_transactions/data.parquet)
which reads the player_transactions raw mirror written by ingest_transactions.py dual-writing under
W11_RAW_WRITE_MODE=both/s3 (+ the one-time export_w11_raw_to_s3.py --source player_transactions bridge).

This is the exact generate_w11b_external_tables.py pattern for a single stg model. The only TIMESTAMP
output is ingestion_ts (string-wrapped by run_w1_lakehouse._string_timestamp_wrap → stored as ISO
VARCHAR in the parquet, exposed here as TIMESTAMP_NTZ via a VALUE:col::TIMESTAMP_NTZ string parse — the
W8a binary-timestamp cure). transaction_date/effective_date/resolution_date are DATE → read directly.

PREREQUISITES:
  1. run_w1_lakehouse.py --w11tx (or --w11tx-only) has written the parquet.
  2. The lakehouse_ext schema + stage + parquet_snappy file format already exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w11tx_external_table.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w11tx_external_table.py --print    # stdout only

OUTPUT: scripts/ddl/w11tx_external_tables.generated.sql — REVIEW, run in Snowflake BEFORE the model
repoint merges. Refresh: refresh_w1_external_tables.py (--w11tx / W11TX_TABLES). AUTO_REFRESH=FALSE.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w11tx_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

W11TX_MODELS = ["stg_statsapi_transactions"]

# ISO-VARCHAR-stored TIMESTAMP columns (run_w1_lakehouse._string_timestamp_wrap) → exposed as
# TIMESTAMP_NTZ via a string parse. Keep in sync with the model's TIMESTAMP outputs.
TS_STRING_COLS = {
    "stg_statsapi_transactions": {"ingestion_ts"},
}


def duckdb_to_snowflake_type(duck_type: str) -> str:
    t = duck_type.upper().strip()
    if t.startswith("DECIMAL") or t.startswith("NUMERIC"):
        return "FLOAT"
    if t in ("DOUBLE", "FLOAT", "REAL"):
        return "FLOAT"
    if t in ("BIGINT", "INTEGER", "HUGEINT", "UBIGINT", "UINTEGER",
             "SMALLINT", "USMALLINT", "TINYINT", "UTINYINT", "INT", "INT64"):
        return "NUMBER(38,0)"
    if t in ("BOOLEAN", "BOOL"):
        return "BOOLEAN"
    if t == "DATE":
        return "DATE"
    if t.startswith("TIMESTAMP"):
        return "TIMESTAMP_NTZ"
    if t in ("VARCHAR", "TEXT", "STRING", "CHAR", "BLOB", "UUID"):
        return "VARCHAR"
    return "VARCHAR"


def get_duckdb_conn():
    import duckdb
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("CREATE OR REPLACE SECRET baseball_s3 "
                 "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')")
    for _p in ("SET http_timeout = 600000", "SET http_retries = 8"):
        try:
            conn.execute(_p)
        except Exception:
            pass
    return conn


def describe_parquet(conn, model: str):
    loc = f"{LAKEHOUSE}/{model}/data.parquet"
    rows = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{loc}')").fetchall()
    return [(r[0], r[1]) for r in rows]


def emit_external_table(model: str, cols) -> str:
    # The VALUE: accessor is CASE-SENSITIVE and must match the parquet's stored field name EXACTLY.
    # The stg duckdb branch aliases every column lowercase, so emit the described case.
    ts_string = {c.lower() for c in TS_STRING_COLS.get(model, ())}

    def _line(name: str, dt: str) -> str:
        sf = "TIMESTAMP_NTZ" if name.lower() in ts_string else duckdb_to_snowflake_type(dt)
        return f"    {name.upper():<24} {sf:<14} AS (VALUE:{name}::{sf})"

    col_lines = [_line(name, dt) for name, dt in cols]
    cols_block = ",\n".join(col_lines)
    return (
        f"-- ── {model}  ({len(cols)} columns) ──\n"
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{model} (\n"
        f"{cols_block}\n)\n"
        f"WITH LOCATION = @{STAGE}/{model}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'E11.22: {model} from S3 lakehouse parquet (player_transactions read-cutover)';\n"
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{model} TO ROLE CREDENCE_API_RO;\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w11tx_external_tables.generated.sql — GENERATED by generate_w11tx_external_table.py\n"
        "-- E11.22: external table over the S3 parquet for stg_statsapi_transactions. Run AFTER\n"
        "-- run_w1_lakehouse.py --w11tx (parquet must exist) and BEFORE the model repoint merges\n"
        "-- (the else branch reads this). Refresh: refresh_w1_external_tables.py --w11tx (W11TX_TABLES).\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W11TX_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (have you run run_w1_lakehouse.py --w11tx yet?)",
                  file=sys.stderr)
    conn.close()

    verify = "\n-- Verification:\n" + "".join(f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W11TX_MODELS)
    ddl = "\n".join(blocks) + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, run the CREATE EXTERNAL TABLE in Snowflake, then merge the model repoint.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
