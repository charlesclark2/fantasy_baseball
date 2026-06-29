#!/usr/bin/env python3
"""
scripts/ddl/generate_w9_external_tables.py   (E11.1-W9 — sub-model signal stores)

Emit Snowflake EXTERNAL TABLE DDL for the W9 S3 parquet (the 5 sub-model SIGNAL OUTPUT
stores mirrored by scripts/export_w9_signals_to_s3.py) so a Snowflake-side reader — and the
W8 feature-layer conversion of `feature_pregame_sub_model_signals` — can read the signal path
from S3 (`lakehouse_ext`) instead of the native Snowflake tables.

The 5 stores = exactly what feature_pregame_sub_model_signals reads:
    mart_sub_model_signals       (betting; SCD-2 — run_env/bullpen/env_state/defense/matchup)
    offense_v1_signals           (betting_features; retired generator, historical rows)
    offense_v2_signals           (betting_features; MERGE)
    starter_suppression_signals  (betting_features; MERGE)
    starter_ip_signals           (betting_features; MERGE)

Identical mechanism to generate_w7b_external_tables.py — DuckDB DESCRIBE the actual S3 parquet
→ Snowflake type map → UPPERCASE unquoted columns via `<COL_UPPER> <TYPE> AS
(VALUE:<col_lower>::<TYPE>)` so downstream unquoted refs resolve (no INFER_SCHEMA
quoted-lowercase case-trap). All five are single-file data.parquet outputs from
export_w9_signals_to_s3.py (full-table SELECT * → row-exact parity).

PREREQUISITES:
  1. scripts/export_w9_signals_to_s3.py has written lakehouse/<name>/data.parquet for each.
  2. AWS creds reachable via the DuckDB credential chain; the lakehouse_ext schema + stage +
     parquet_snappy file format already exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w9_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w9_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w9_external_tables.generated.sql — REVIEW, then run in Snowflake BEFORE the
parity check + before any W8 source repoint. Refresh: refresh_w1_external_tables.py (--w9 /
W9_TABLES). AUTO_REFRESH=FALSE. Rollback: the native Snowflake stores are NOT dropped (the
generators keep writing them during the W9 window); drop the external tables to roll back.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w9_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# The W9 signal stores (single-file data.parquet layout). Order is documentation only; the DDL
# itself is order-independent.
W9_MODELS = [
    "mart_sub_model_signals",
    "offense_v1_signals",
    "offense_v2_signals",
    "starter_suppression_signals",
    "starter_ip_signals",
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
        f"COMMENT = 'E11.1-W9: {model} signal store from S3 lakehouse parquet';\n"
        f"-- Preserve the feature/reader grant on (re)create (INC-18 band-aid class):\n"
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{model} TO ROLE CREDENCE_API_RO;\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w9_external_tables.generated.sql — GENERATED by generate_w9_external_tables.py\n"
        "-- E11.1-W9: external tables over the S3 parquet for the 5 sub-model signal STORES\n"
        "-- (mart_sub_model_signals + offense_v1/offense_v2/starter_suppression/starter_ip\n"
        "-- _signals). Reuses the lakehouse_ext schema + s3_lakehouse stage + parquet_snappy\n"
        "-- file format (W1d). Run AFTER export_w9_signals_to_s3.py has written\n"
        "-- lakehouse/<name>/data.parquet, and BEFORE the parity check / any W8 source repoint.\n"
        "-- Refresh: scripts/refresh_w1_external_tables.py --w9 (W9_TABLES). AUTO_REFRESH=FALSE.\n"
        "-- DO NOT hand-edit — regenerate from the parquet if a store's schema changes.\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W9_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (has export_w9_signals_to_s3.py written it?)",
                  file=sys.stderr)
    conn.close()
    verify = "\n-- Verification (run after CREATE):\n" + "".join(
        f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W9_MODELS
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
