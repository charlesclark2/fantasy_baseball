#!/usr/bin/env python3
"""
scripts/ddl/generate_w7b_external_tables.py   (E11.1-W7b — the FINISH wave, part b)

Emit Snowflake EXTERNAL TABLE DDL for the W7b S3 parquet so the request-path
last-resort + the feature build can read these models from S3 (lakehouse_ext) instead
of the native Snowflake builds. Two cohesive pieces this wave covers:

  (A) the mart_player_profile_identity from-scratch injury chain:
      stg_statsapi_transactions, stg_statsapi_player_injury_status,
      feature_pregame_injury_status, mart_player_profile_identity
  (B) the W7a serving-mart backlog:
      stg_statsapi_probable_pitchers, stg_statsapi_lineups_wide

Identical mechanism to generate_w7_external_tables.py — DuckDB DESCRIBE the actual S3
parquet → Snowflake type map → UPPERCASE unquoted columns via
`<COL_UPPER> <TYPE> AS (VALUE:<col_lower>::<TYPE>)` so downstream unquoted refs resolve
(no INFER_SCHEMA quoted-lowercase case-trap). All six models are single-file data.parquet
outputs from run_w1_lakehouse.py _build_w7b (deterministic SQL → row-exact parity).

PREREQUISITES:
  1. The player_transactions typed precursor parquet exists in S3
     (scripts/export_w7b_precursors_to_s3.py); monthly_schedule raw + stg_statsapi_lineups
     parquet already exist (W3pre/W6). The W2/W4/W6 upstream parquet exist.
  2. run_w1_lakehouse.py --w7b (or --w7b-only) has written lakehouse/<model>/data.parquet
     for each W7B_MODELS entry.
  3. AWS creds reachable via the DuckDB credential chain; the lakehouse_ext schema + stage
     + parquet_snappy file format already exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w7b_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w7b_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w7b_external_tables.generated.sql — REVIEW, then run in Snowflake
BEFORE the parity check + before the request-path last-resort / feature source repoint
(W7b-2). Refresh: refresh_w1_external_tables.py (W7B_TABLES). AUTO_REFRESH=FALSE.
Rollback: the original Snowflake builds are not dropped (the models' else arm stays the
native build); revert the model to roll back.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w7b_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# The new S3 tables that need a Snowflake-visible external table. Single-file
# data.parquet layout (run_w1_lakehouse.py _build_marts → data.parquet). Order is the
# build dependency order for documentation; the DDL itself is order-independent.
#   (A) profile_identity injury chain                       (B) serving-mart backlog
W7B_MODELS = [
    "stg_statsapi_transactions",
    "stg_statsapi_player_injury_status",
    "feature_pregame_injury_status",
    "mart_player_profile_identity",
    "stg_statsapi_probable_pitchers",
    "stg_statsapi_lineups_wide",
]


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
    if t.startswith("TIMESTAMP"):  # TIMESTAMP / TIMESTAMP WITH TIME ZONE → NTZ instant
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
    col_lines = [
        f"    {name.upper():<32} {duckdb_to_snowflake_type(dt):<14} AS (VALUE:{name.lower()}::{duckdb_to_snowflake_type(dt)})"
        for name, dt in cols
    ]
    cols_block = ",\n".join(col_lines)
    return (
        f"-- ── {model}  ({len(cols)} columns) ──\n"
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{model} (\n"
        f"{cols_block}\n)\n"
        f"WITH LOCATION = @{STAGE}/{model}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'E11.1-W7b: {model} from S3 lakehouse parquet';\n"
        f"-- Preserve the request/feature reader grant on (re)create (INC-18 band-aid class):\n"
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{model} TO ROLE CREDENCE_API_RO;\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w7b_external_tables.generated.sql — GENERATED by generate_w7b_external_tables.py\n"
        "-- E11.1-W7b: external tables over the S3 parquet for the mart_player_profile_identity\n"
        "-- injury chain (stg_statsapi_transactions / _player_injury_status /\n"
        "-- feature_pregame_injury_status / mart_player_profile_identity) + the serving-mart\n"
        "-- backlog (stg_statsapi_probable_pitchers / stg_statsapi_lineups_wide). Reuses the\n"
        "-- lakehouse_ext schema + s3_lakehouse stage + parquet_snappy file format (W1d).\n"
        "-- Run AFTER run_w1_lakehouse.py --w7b has written lakehouse/<model>/data.parquet, and\n"
        "-- BEFORE the parity check + the request-path last-resort / feature source repoint.\n"
        "-- Refresh: scripts/refresh_w1_external_tables.py (W7B_TABLES). AUTO_REFRESH=FALSE.\n"
        "-- DO NOT hand-edit — regenerate from the parquet if a model's schema changes.\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W7B_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (has run_w1_lakehouse.py --w7b written it?)",
                  file=sys.stderr)
    conn.close()
    verify = "\n-- Verification (run after CREATE):\n" + "".join(
        f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W7B_MODELS
    )
    ddl = "\n".join(blocks) + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, then run it in Snowflake before the parity check / source repoint.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
