#!/usr/bin/env python3
"""
scripts/ddl/generate_w5_external_tables.py   (E11.1-W5 lakehouse decommission)

Emit Snowflake EXTERNAL TABLE DDL for the W5 models by reading the ACTUAL schema
of each S3 parquet (written by run_w1_lakehouse.py --w5) via DuckDB.

W5 = the seeds + mart_game_results/mart_game_spine team/game chain (Group A, 10 marts)
+ the 4 W4-deferred marts and the stg_batter_sprint_speed precursor (Group B, 5 models).
Each becomes a thin Snowflake VIEW over its lakehouse_ext external table. Same machinery
+ rationale as generate_w4_external_tables.py — see that file for the case-preservation /
type-inference notes (UPPERCASE unquoted identifiers via VALUE:<col_lower>).

NOTE: the SEEDS (ref_teams, ref_team_aliases) are NOT here — they stay dbt seeds in
Snowflake (the source of truth, ~negligible cost). export_w5_raw_to_s3.py only mirrors
them to S3 so the DuckDB build can register them as views; they need no external table.

PREREQUISITES:
  1. run_w1_lakehouse.py --w5 has been run at least once (W5 parquet exists in S3),
     which itself needs the precursor exports first:
       uv run python scripts/export_w5_raw_to_s3.py
  2. AWS credentials reachable via the DuckDB credential chain (same as the runner).
  3. The lakehouse_ext schema + stage + parquet_snappy file format already exist
     (created by scripts/ddl/w1_external_tables.sql during W1d — REUSED here).

USAGE:
  uv run python scripts/ddl/generate_w5_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w5_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w5_external_tables.generated.sql
  The operator REVIEWS this, then runs it in Snowflake BEFORE flipping the W5 models
  to views (i.e. before the PR merges — CI's `dbtf build --select state:modified+`
  builds the view-over-external-table on the Snowflake target and FAILS if the table
  is absent). AUTO_REFRESH=FALSE — refreshed each run by
  scripts/refresh_w1_external_tables.py (W5_TABLES). Rollback: the original
  Snowflake-built tables are not dropped; re-enable their dbt build to roll back.

⚠️ TYPE-PRESERVATION (W5-specific — read before reviewing the DDL):
  • mart_game_results.GAME_DATE is DATE; mart_game_spine.GAME_DATE is TIMESTAMP_NTZ —
    the DuckDB branch emits ::date / ::timestamp respectively, so the inferred external
    column types match the retired Snowflake tables. Spot-check those two in the DDL.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w5_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# Mirror the 15 W5 dual-branch models (run_w1_lakehouse.W5_MART_MODELS +
# W5B_PRECURSOR_MODELS + W5B_MART_MODELS). Kept explicit so this script has no
# import-time dependency on the runner. ORDER does not matter here.
W5_MODELS = [
    # Group A — game-results team/game chain (10)
    "dim_team_name_lookup",
    "mart_game_results",
    "mart_game_spine",
    "mart_head_to_head_team_history",
    "mart_home_away_splits",
    "mart_park_run_factors",
    "mart_team_pythagorean_rolling",
    "mart_team_rolling_offense",
    "mart_team_rolling_pitching",
    "mart_team_season_record",
    # Group B — W4-deferred marts + the sprint-speed precursor (5)
    "stg_batter_sprint_speed",
    "mart_eb_park_factors",
    "mart_bullpen_effectiveness",
    "mart_team_fielding_oaa",
    "mart_team_defense_quality_rolling",
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
        f"COMMENT = 'E11.1-W5: {model} from S3 lakehouse parquet';\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()

    header = (
        "-- =============================================================================\n"
        "-- w5_external_tables.generated.sql  —  GENERATED by generate_w5_external_tables.py\n"
        "-- E11.1-W5: Snowflake external tables over S3 parquet for the mart_game_results /\n"
        "-- mart_game_spine team/game chain + the 4 W4-deferred marts + stg_batter_sprint_speed.\n"
        "-- Reuses the lakehouse_ext schema + s3_lakehouse stage + parquet_snappy file format\n"
        "-- created by w1_external_tables.sql (W1d). Run AFTER run_w1_lakehouse.py --w5 has\n"
        "-- written the W5 parquet, and BEFORE merging the W5 models (which become views over\n"
        "-- these tables). Refresh: scripts/refresh_w1_external_tables.py (W5_TABLES). DO NOT\n"
        "-- hand-edit — regenerate from the parquet if a model's schema changes.\n"
        "-- NOTE: seeds (ref_teams/ref_team_aliases) stay dbt seeds — no external table here.\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W5_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  "
                  f"(has run_w1_lakehouse.py --w5 written this parquet yet?)",
                  file=sys.stderr)
    conn.close()

    verify = "\n-- Verification (run after CREATE):\n" + "".join(
        f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W5_MODELS
    )
    ddl = "\n".join(blocks) + verify

    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, then run it in Snowflake before flipping the W5 models to views.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
