#!/usr/bin/env python3
"""
scripts/ddl/generate_w11d_external_tables.py   (E11.1-W11 Tier-D — public-betting ingestion → S3)

Emit Snowflake EXTERNAL TABLE DDL over the S3 parquet that the W11d DuckDB build writes, so the
public-betting dbt models' Snowflake (else) branch `select * from baseball_data.lakehouse_ext.<model>`
resolves. The 4 public-betting models are TABLE-materialized on the Snowflake side (no incrementals) →
no DROP+rebuild is needed at cutover (unlike the W8a EB posteriors).

The W11d parquet is written by:
  scripts/run_w1_lakehouse.py --w11d   (each model → lakehouse/<model>/data.parquet)
which reads the public_betting_raw raw mirror written by:
  ingest_actionnetwork_betting dual-writing under W11_RAW_WRITE_MODE=both/s3, and
  scripts/export_w11_raw_to_s3.py --source public_betting_raw  (the one-time history bridge),
plus the pregame-spine feature_pregame_game_features parquet (built by --w8b).

PREREQUISITES:
  1. run_w1_lakehouse.py --w11d (or --w11d-only after a --w8b build) has written all 4 parquet files.
  2. AWS creds reachable via the DuckDB credential chain; the lakehouse_ext schema + stage +
     parquet_snappy file format already exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w11d_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w11d_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w11d_external_tables.generated.sql — REVIEW, then run in Snowflake BEFORE the
PR merges (the else branches read these). Refresh: refresh_w1_external_tables.py (--w11d / W11D_TABLES).
AUTO_REFRESH=FALSE.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w11d_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# The 4 W11d public-betting models (single-file data.parquet). Order = run_w1_lakehouse.W11D_MODELS.
W11D_MODELS = [
    "stg_actionnetwork_public_betting",
    "stg_actionnetwork_public_betting_snapshots",
    "feature_pregame_public_betting_status",
    "feature_pregame_public_betting_features",
]

# ⚠️ TIMESTAMP columns stored as ISO **VARCHAR** in the parquet (run_w1_lakehouse._string_timestamp_wrap).
# Snowflake misreads BINARY parquet timestamps per-row (micros read as seconds → year ~56M → connector
# EOVERFLOW on fetch — the W8a 24h serving outage). So these columns land in the parquet as strings; the
# external table declares them TIMESTAMP_NTZ AS (VALUE:col::TIMESTAMP_NTZ) — a reliable STRING parse.
# Keep this in sync with _string_timestamp_wrap (it stringifies EVERY TIMESTAMP* output col). DATE
# columns (game_date on the plain stg) read correctly from parquet → NOT listed.
TS_STRING_COLS = {
    "stg_actionnetwork_public_betting":            {"ingestion_timestamp"},
    "stg_actionnetwork_public_betting_snapshots":  {"loaded_at"},
    "feature_pregame_public_betting_status":       {"valid_from", "valid_to", "computed_at"},
    "feature_pregame_public_betting_features":     {"public_betting_snapshot_ts"},
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
    # ⚠️ The VALUE: accessor is CASE-SENSITIVE and must match the parquet's STORED field name EXACTLY.
    # The public-betting parquet columns are lowercase (the stg/feature duckdb branches alias every
    # column lowercase), so emit the EXACT described case. Columns stored as ISO VARCHAR in the parquet
    # but exposed as TIMESTAMP_NTZ via a STRING parse (VALUE:col::TIMESTAMP_NTZ) — see TS_STRING_COLS.
    ts_string = {c.lower() for c in TS_STRING_COLS.get(model, ())}

    def _line(name: str, dt: str) -> str:
        sf = "TIMESTAMP_NTZ" if name.lower() in ts_string else duckdb_to_snowflake_type(dt)
        return f"    {name.upper():<32} {sf:<14} AS (VALUE:{name}::{sf})"

    col_lines = [_line(name, dt) for name, dt in cols]
    cols_block = ",\n".join(col_lines)
    return (
        f"-- ── {model}  ({len(cols)} columns) ──\n"
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{model} (\n"
        f"{cols_block}\n)\n"
        f"WITH LOCATION = @{STAGE}/{model}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'E11.1-W11 Tier-D: {model} from S3 lakehouse parquet (public-betting feed)';\n"
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{model} TO ROLE CREDENCE_API_RO;\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w11d_external_tables.generated.sql — GENERATED by generate_w11d_external_tables.py\n"
        "-- E11.1-W11 Tier-D: external tables over the S3 parquet for the public-betting stg + feature\n"
        "-- layer. Run AFTER run_w1_lakehouse.py --w11d (parquet must exist) and BEFORE the PR\n"
        "-- merges (the models' Snowflake else branch reads these). Refresh:\n"
        "-- refresh_w1_external_tables.py --w11d (W11D_TABLES).\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W11D_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (have you run run_w1_lakehouse.py --w11d yet?)",
                  file=sys.stderr)
    conn.close()

    verify = "\n-- Verification:\n" + "".join(f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W11D_MODELS)
    ddl = "\n".join(blocks) + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, run the CREATE EXTERNAL TABLEs in Snowflake, then merge the model repoint.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
