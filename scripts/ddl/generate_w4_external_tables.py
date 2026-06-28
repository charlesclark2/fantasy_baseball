#!/usr/bin/env python3
"""
scripts/ddl/generate_w4_external_tables.py   (E11.1-W4 lakehouse decommission)

Emit Snowflake EXTERNAL TABLE DDL for the W4 models by reading the ACTUAL schema
of each S3 parquet (written by run_w1_lakehouse.py --w4) via DuckDB.

W4 = the FanGraphs / posteriors-cluster / raw-savant non-serving marts (6) PLUS the
FanGraphs precursor subtree they build on (4 staging + 2 fct + 1 statsapi staging).
Each becomes a thin Snowflake VIEW over its lakehouse_ext external table. Same
machinery + rationale as generate_w3_external_tables.py — see that file for the
case-preservation / type-inference notes (UPPERCASE unquoted identifiers via
VALUE:<col_lower>).

PREREQUISITES:
  1. run_w1_lakehouse.py --w4 has been run at least once (W4 parquet exists in S3),
     which itself needs the precursor exports + migrated builders first:
       uv run python scripts/export_w4_raw_to_s3.py
       uv run python betting_ml/scripts/eb_priors/fit_granular_park_priors.py --s3 --start-season 2015
       uv run python betting_ml/scripts/pitcher_clustering/cluster_pitchers.py --seed   # one-time history
  2. AWS credentials reachable via the DuckDB credential chain (same as the runner).
  3. The lakehouse_ext schema + stage + parquet_snappy file format already exist
     (created by scripts/ddl/w1_external_tables.sql during W1d — REUSED here).

USAGE:
  uv run python scripts/ddl/generate_w4_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w4_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w4_external_tables.generated.sql
  The operator REVIEWS this, then runs it in Snowflake BEFORE flipping the W4 models
  to views (i.e. before the PR merges — CI's `dbtf build --select state:modified+`
  builds the view-over-external-table on the Snowflake target and FAILS if the table
  is absent). AUTO_REFRESH=FALSE — refreshed each run by
  scripts/refresh_w1_external_tables.py (W4_TABLES). Rollback: the original
  Snowflake-built tables are not dropped; re-enable their dbt build to roll back.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w4_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# Mirror run_w1_lakehouse.W4_PRECURSOR_MODELS + W4_MART_MODELS (kept explicit so this
# script has no import-time dependency on the runner). ORDER does not matter here.
W4_MODELS = [
    # FanGraphs precursor subtree (built on DuckDB so the 3 FG marts can read it)
    "stg_fangraphs__stuff_plus",
    "stg_fangraphs__pitcher_arsenal",
    "stg_fangraphs__zips_hitting",
    "stg_fangraphs__hitting_leaderboard",
    "fct_fangraphs_pitcher_arsenal_wide",
    "fct_fangraphs_hitting_analytics",
    "stg_statsapi_player_profiles",
    # The 6 W4 marts
    "mart_pitcher_arsenal_summary",
    "mart_pitcher_profile_summary",
    "mart_batter_profile_summary",
    "mart_park_factors_granular",
    "mart_batter_woba_vs_cluster",
    "mart_catcher_framing",
]


def duckdb_to_snowflake_type(duck_type: str) -> str:
    """Map a DuckDB column type to the Snowflake external-table column type."""
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
    conn.execute("""
        CREATE OR REPLACE SECRET baseball_s3 (
          TYPE S3, PROVIDER credential_chain, REGION 'us-east-2'
        )
    """)
    # E11.1-W4: harden S3 reads against transient httpfs timeouts (default 30s GET window).
    for _pragma in ("SET http_timeout = 600000", "SET http_retries = 8",
                    "SET http_retry_wait_ms = 500", "SET http_retry_backoff = 4"):
        try:
            conn.execute(_pragma)
        except Exception:
            pass
    return conn


def describe_parquet(conn, model: str) -> list[tuple[str, str]]:
    loc = f"{LAKEHOUSE}/{model}/data.parquet"
    rows = conn.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{loc}')"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def emit_external_table(model: str, cols: list[tuple[str, str]]) -> str:
    col_lines = []
    for name, duck_type in cols:
        sf_type = duckdb_to_snowflake_type(duck_type)
        col_lines.append(
            f"    {name.upper():<34} {sf_type:<14} AS (VALUE:{name.lower()}::{sf_type})"
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
        f"COMMENT = 'E11.1-W4: {model} from S3 lakehouse parquet';\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()

    header = (
        "-- =============================================================================\n"
        "-- w4_external_tables.generated.sql  —  GENERATED by generate_w4_external_tables.py\n"
        "-- E11.1-W4: Snowflake external tables over S3 parquet for the W4 marts + their\n"
        "-- FanGraphs precursor subtree. Reuses the lakehouse_ext schema + s3_lakehouse\n"
        "-- stage + parquet_snappy file format created by w1_external_tables.sql (W1d).\n"
        "-- Run AFTER run_w1_lakehouse.py --w4 has written the W4 parquet, and BEFORE\n"
        "-- merging the W4 models (which become views over these tables). Refresh:\n"
        "-- scripts/refresh_w1_external_tables.py (W4_TABLES). DO NOT hand-edit —\n"
        "-- regenerate from the parquet if a model's schema changes.\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W4_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  "
                  f"(has run_w1_lakehouse.py --w4 written this parquet yet?)",
                  file=sys.stderr)
    conn.close()

    verify = "\n-- Verification (run after CREATE):\n" + "".join(
        f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W4_MODELS
    )
    ddl = "\n".join(blocks) + verify

    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, then run it in Snowflake before flipping the W4 models to views.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
