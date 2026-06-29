#!/usr/bin/env python3
"""
scripts/ddl/generate_w6_external_tables.py   (E11.1-W6 lakehouse decommission)

Emit Snowflake EXTERNAL TABLE DDL for the W6 models by reading the ACTUAL schema of each
S3 parquet (written by run_w1_lakehouse.py --w6) via DuckDB. Same machinery + rationale as
generate_w5_external_tables.py.

W6 = the 2 Group-C staging flattens (stg_statsapi_venues, stg_statsapi_lineups) + the 13
odds/CLV + odds-serving marts. Each becomes a thin Snowflake VIEW over its lakehouse_ext
external table.

⚠️ PARTITIONED mart (mart_odds_outcomes): its parquet is split into _history/ + _current/
date buckets (E11.1-W6 option b). The external table's WITH LOCATION = @stage/<model>/
recurses into BOTH subdirs (Snowflake lists all files under the prefix), so the view UNIONs
them. Column inference reads `<model>/**/*.parquet` (both buckets share the schema; the
commence_date split column is RETAINED in the files — not Hive-stripped).

PREREQUISITES:
  1. run_w1_lakehouse.py --w6 has been run (W6 parquet in S3), which needs the precursor
     exports first: uv run python scripts/export_w6_raw_to_s3.py
  2. AWS credentials reachable via the DuckDB credential chain.
  3. The lakehouse_ext schema + stage + parquet_snappy file format exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w6_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w6_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w6_external_tables.generated.sql  — operator REVIEWS, then runs in
  Snowflake BEFORE flipping the W6 models to views (before the PR merges). AUTO_REFRESH=FALSE
  — refreshed by scripts/refresh_w1_external_tables.py (W6_TABLES, daily) AND the intraday
  odds path (--w6-odds: stg_oddsapi_odds + mart_odds_outcomes + mart_game_odds_bridge).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w6_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# Mirror the 15 W6 dual-branch models (run_w1_lakehouse.W6_STG_MODELS + W6_MART_MODELS).
W6_MODELS = [
    # Group-C staging flattens
    "stg_statsapi_venues",
    "stg_statsapi_lineups",
    # odds/CLV + odds-serving marts
    "mart_odds_outcomes",          # PARTITIONED (_history/_current)
    "mart_odds_events",
    "mart_game_odds_bridge",
    "mart_odds_consensus",
    "mart_odds_line_movement",
    "mart_closing_line_value",
    "mart_clv_labeled_games",
    "mart_clv_label_count",
    "mart_prediction_clv",
    "mart_derivative_closes",
    "mart_bookmaker_disagreement",
    "mart_team_schedule_context",
    "mart_player_game_starts",
]

# Date-bucketed marts: column inference globs **/*.parquet; the external table LOCATION is
# the model dir (Snowflake recurses both buckets).
PARTITIONED = {"mart_odds_outcomes"}


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
    if t.startswith("TIMESTAMP") and "TZ" in t.replace("_", ""):
        # DuckDB TIMESTAMP WITH TIME ZONE → Snowflake TIMESTAMP_TZ (odds_snapshots_historical
        # snapshot_ts / close_snapshot_ts surface as TIMESTAMP_TZ in the live marts).
        return "TIMESTAMP_TZ"
    if t.startswith("TIMESTAMP"):
        return "TIMESTAMP_NTZ"
    if t in ("VARCHAR", "TEXT", "STRING", "CHAR", "BLOB", "UUID"):
        return "VARCHAR"
    return "VARCHAR"


def get_duckdb_conn():
    import duckdb
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    try:
        conn.execute("INSTALL icu; LOAD icu")
    except Exception:
        pass
    conn.execute("""
        CREATE OR REPLACE SECRET baseball_s3 (
          TYPE S3, PROVIDER credential_chain, REGION 'us-east-2'
        )
    """)
    for _pragma in ("SET http_timeout = 600000", "SET http_retries = 8",
                    "SET http_retry_wait_ms = 500", "SET http_retry_backoff = 4"):
        try:
            conn.execute(_pragma)
        except Exception:
            pass
    return conn


def describe_parquet(conn, model: str) -> list[tuple[str, str]]:
    if model in PARTITIONED:
        loc = f"{LAKEHOUSE}/{model}/**/*.parquet"
        rows = conn.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{loc}', union_by_name=true)"
        ).fetchall()
    else:
        loc = f"{LAKEHOUSE}/{model}/data.parquet"
        rows = conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{loc}')").fetchall()
    return [(r[0], r[1]) for r in rows]


def emit_external_table(model: str, cols: list[tuple[str, str]]) -> str:
    col_lines = []
    for name, duck_type in cols:
        sf_type = duckdb_to_snowflake_type(duck_type)
        col_lines.append(
            f"    {name.upper():<34} {sf_type:<14} AS (VALUE:{name.lower()}::{sf_type})"
        )
    cols_block = ",\n".join(col_lines)
    note = "  (PARTITIONED _history/_current — LOCATION recurses both)" if model in PARTITIONED else ""
    return (
        f"-- ── {model}  ({len(cols)} columns){note} ──\n"
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{model} (\n"
        f"{cols_block}\n"
        f")\n"
        f"WITH LOCATION = @{STAGE}/{model}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'E11.1-W6: {model} from S3 lakehouse parquet';\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w6_external_tables.generated.sql — GENERATED by generate_w6_external_tables.py\n"
        "-- E11.1-W6: Snowflake external tables over S3 parquet for the odds/CLV + odds-serving\n"
        "-- marts + the 2 Group-C staging flattens. Reuses the lakehouse_ext schema + stage +\n"
        "-- parquet_snappy file format (W1d). Run AFTER run_w1_lakehouse.py --w6, BEFORE merging\n"
        "-- the W6 models. Refresh: refresh_w1_external_tables.py (W6_TABLES daily) + the\n"
        "-- intraday odds path (--w6-odds). mart_odds_outcomes is date-bucketed (_history/_current).\n"
        "-- DO NOT hand-edit — regenerate from the parquet if a model's schema changes.\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W6_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (has run_w1_lakehouse.py --w6 written this parquet yet?)",
                  file=sys.stderr)
    conn.close()
    verify = "\n-- Verification (run after CREATE):\n" + "".join(
        f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W6_MODELS
    )
    ddl = "\n".join(blocks) + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, then run it in Snowflake before flipping the W6 models to views.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
