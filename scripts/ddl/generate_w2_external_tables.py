#!/usr/bin/env python3
"""
scripts/ddl/generate_w2_external_tables.py   (E11.1-W2 lakehouse decommission)

Emit Snowflake EXTERNAL TABLE DDL for the W2 marts by reading the ACTUAL schema
of each S3 parquet (written by run_w1_lakehouse.py) via DuckDB.

WHY GENERATE INSTEAD OF HAND-WRITING (cf. W1's scripts/ddl/w1_external_tables.sql):
  • The W2 rolling marts have ~80 columns each — hand-listing is error-prone.
  • Snowflake INFER_SCHEMA / USING TEMPLATE would create QUOTED-LOWERCASE columns
    from DuckDB's lowercase parquet, which breaks downstream UNQUOTED refs
    (`mart_x.batter_id` → BATTER_ID ≠ "batter_id"). This generator forces UPPERCASE
    unquoted identifiers via `<COL_UPPER> <TYPE> AS (VALUE:<col_lower>::<TYPE>)`,
    exactly matching the proven W1 pattern — no case trap.
  • Types come from the real parquet (no guessing).

PREREQUISITES:
  1. run_w1_lakehouse.py has been run at least once (W2 parquet exists in S3).
  2. AWS credentials reachable via the DuckDB credential chain (same as the runner).
  3. The lakehouse_ext schema + stage + parquet_snappy file format already exist
     (created by scripts/ddl/w1_external_tables.sql during W1d — REUSED here).

USAGE:
  uv run python scripts/ddl/generate_w2_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w2_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w2_external_tables.generated.sql
  The operator REVIEWS this, then runs it in Snowflake (MCP or connector) BEFORE
  flipping the W2 models to views. AUTO_REFRESH=FALSE — refreshed each run by
  scripts/refresh_w1_external_tables.py (W2_TABLES). Rollback: the original
  Snowflake-built tables are not dropped; re-enable their dbt build to roll back.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w2_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# Mirror run_w1_lakehouse.W2_MART_MODELS (kept explicit so this script has no
# import-time dependency on the runner / argv parsing).
W2_MART_MODELS = [
    "mart_pitcher_batted_ball_profile",
    "mart_batter_bat_tracking_profile",
    "mart_batter_rolling_stats",
    "mart_pitcher_rolling_stats",
    "mart_starting_pitcher_game_log",
    "mart_pitcher_batter_history",
    "mart_starter_csw_rolling",
    "mart_starter_pitch_mix_rolling",
]


def duckdb_to_snowflake_type(duck_type: str) -> str:
    """Map a DuckDB column type to the Snowflake external-table column type."""
    t = duck_type.upper().strip()
    if t.startswith("DECIMAL") or t.startswith("NUMERIC"):
        # W2 ratio/decimal finals are read back as floats downstream.
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
    # Conservative default — surfaces anything unmapped for the operator to check.
    return "VARCHAR"


def get_duckdb_conn():
    import duckdb
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("""
        CREATE OR REPLACE SECRET baseball_s3 (
          TYPE S3, PROVIDER credential_chain, REGION 'us-east-2'
        )
    """)
    return conn


def describe_parquet(conn, model: str) -> list[tuple[str, str]]:
    loc = f"{LAKEHOUSE}/{model}/data.parquet"
    rows = conn.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{loc}')"
    ).fetchall()
    # DESCRIBE → (column_name, column_type, null, key, default, extra)
    return [(r[0], r[1]) for r in rows]


def emit_external_table(model: str, cols: list[tuple[str, str]]) -> str:
    col_lines = []
    for name, duck_type in cols:
        sf_type = duckdb_to_snowflake_type(duck_type)
        # UPPERCASE unquoted external-table column; VALUE: accessor uses the
        # lowercase parquet name (DuckDB writes lowercase).
        col_lines.append(
            f"    {name.upper():<30} {sf_type:<14} AS (VALUE:{name.lower()}::{sf_type})"
        )
    cols_block = ",\n".join(col_lines)
    return (
        f"-- ── {model}  ({len(cols)} columns) ──\n"
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{model} (\n"
        f"{cols_block}\n"
        f")\n"
        f"WITH LOCATION = @{STAGE}/{model}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'E11.1-W2: {model} from S3 lakehouse parquet';\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()

    header = (
        "-- =============================================================================\n"
        "-- w2_external_tables.generated.sql  —  GENERATED by generate_w2_external_tables.py\n"
        "-- E11.1-W2: Snowflake external tables over S3 parquet for the W2 marts.\n"
        "-- Reuses the lakehouse_ext schema + s3_lakehouse stage + parquet_snappy file\n"
        "-- format created by w1_external_tables.sql (W1d). Run AFTER run_w1_lakehouse.py\n"
        "-- has written the W2 parquet, and BEFORE merging the W2 models (which become\n"
        "-- views over these tables). Refresh: scripts/refresh_w1_external_tables.py.\n"
        "-- DO NOT hand-edit — regenerate from the parquet if a mart's schema changes.\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W2_MART_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  "
                  f"(has run_w1_lakehouse.py written this parquet yet?)",
                  file=sys.stderr)
    conn.close()

    verify = "\n-- Verification (run after CREATE):\n" + "".join(
        f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W2_MART_MODELS
    )
    ddl = "\n".join(blocks) + verify

    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, then run it in Snowflake before flipping the W2 models to views.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
