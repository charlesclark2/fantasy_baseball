#!/usr/bin/env python3
"""
scripts/ddl/generate_w8a_external_tables.py   (E11.1-W8a — upstream feature layer + EB posteriors)

Emit Snowflake EXTERNAL TABLE DDL over the S3 parquet that the W8a DuckDB build writes, so the
dbt models' Snowflake (else) branch `select * from baseball_data.lakehouse_ext.<model>` resolves
(and the at-cutover DROP+rebuild of the 5 EB incrementals adopts a deterministic FLOAT schema).

The W8a parquet is written by:
  scripts/run_w1_lakehouse.py --w8a            (each model → lakehouse/<model>/data.parquet)
which itself depends on:
  scripts/export_w8a_precursors_to_s3.py       (the 3 Python tables + 3 EB-prior seeds)
  scripts/export_w9_signals_to_s3.py           (the 5 sub-model signal stores)
  the prior-wave (W1-W7b) parquet already in S3.

PREREQUISITES:
  1. run_w1_lakehouse.py --w8a (or --w8a-only) has written all 13 parquet files.
  2. AWS creds reachable via the DuckDB credential chain; the lakehouse_ext schema + stage +
     parquet_snappy file format already exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w8a_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w8a_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w8a_external_tables.generated.sql — REVIEW, then run in Snowflake BEFORE the
PR merges (the else branches read these). Refresh: refresh_w1_external_tables.py (W8A_TABLES).
AUTO_REFRESH=FALSE.  ⚠️ The 5 EB models are INCREMENTAL on Snowflake — after creating their
external tables, DROP the native incrementals (baseball_data.{betting,betting_features}.<model>)
so the next dbt build rebuilds them from the external table with FLOAT columns (INC-19); a plain
`--full-refresh` MERGEs (does NOT DROP) and would leave the NUMBER columns → 002108 HALT.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w8a_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# The 13 W8a models (single-file data.parquet). Order matches run_w1_lakehouse.W8A_MODELS.
# The 5 EB models are the INCREMENTAL ones that also need a native DROP+rebuild at cutover.
W8A_MODELS = [
    "stg_statsapi_starter_snapshots",
    "feature_pregame_starter_status",
    "feature_pregame_park_status",
    "feature_pregame_park_features",
    "feature_pregame_team_features",
    "feature_pregame_expected_lineup",
    "feature_pregame_odds_features",
    "feature_pregame_sub_model_signals",
    "int_bullpen_ali_by_season",
    "eb_bullpen_posteriors",
    "eb_bullpen_team_posteriors",
    "eb_starter_posteriors",
    "eb_batter_posteriors_raw",
]

# The 5 EB incrementals + their native Snowflake FQN (the DROP+rebuild targets).
EB_INCREMENTALS = {
    "int_bullpen_ali_by_season":  "baseball_data.betting.int_bullpen_ali_by_season",
    "eb_bullpen_posteriors":      "baseball_data.betting.eb_bullpen_posteriors",
    "eb_bullpen_team_posteriors": "baseball_data.betting.eb_bullpen_team_posteriors",
    "eb_starter_posteriors":      "baseball_data.betting.eb_starter_posteriors",
    "eb_batter_posteriors_raw":   "baseball_data.betting.eb_batter_posteriors_raw",
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
    # ⚠️ The VALUE: accessor is CASE-SENSITIVE and must match the parquet's STORED field name
    # EXACTLY (verified: VALUE:GAME_PK returns values, VALUE:game_pk returns NULL for an uppercase
    # field). Some W8a parquet inherit UPPERCASE columns from Snowflake-mirrored upstreams — the W9
    # signal stores (GAME_PK/SIDE), mart_player_start_probability (GAME_PK), and
    # feature_pregame_market_features (the 13 moneyline/totals cols) — because a Snowflake `SELECT *`
    # → parquet yields uppercase, and DuckDB preserves the source case for un-aliased columns. The
    # prior-wave generators hard-`.lower()`ed this path, which SILENTLY reads those columns as NULL
    # through the external table (the same latent bug is live in W9 lakehouse_ext.mart_sub_model_signals,
    # whose game_pk is all-NULL). Parity can't catch it (it reads the parquet via DuckDB, which is
    # case-insensitive). So emit the EXACT described case. The external-table COLUMN name stays
    # UPPERCASE (unquoted-ref friendly for the dbt else branch); only the VALUE: key must match.
    col_lines = [
        f"    {name.upper():<32} {duckdb_to_snowflake_type(dt):<14} AS (VALUE:{name}::{duckdb_to_snowflake_type(dt)})"
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
        f"COMMENT = 'E11.1-W8a: {model} from S3 lakehouse parquet (upstream feature layer + EB posteriors)';\n"
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{model} TO ROLE CREDENCE_API_RO;\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w8a_external_tables.generated.sql — GENERATED by generate_w8a_external_tables.py\n"
        "-- E11.1-W8a: external tables over the S3 parquet for the upstream feature layer +\n"
        "-- EB posteriors. Run AFTER run_w1_lakehouse.py --w8a (parquet must exist) and BEFORE\n"
        "-- the PR merges (the models' Snowflake else branch reads these). Refresh:\n"
        "-- refresh_w1_external_tables.py (W8A_TABLES).\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W8A_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (have you run run_w1_lakehouse.py --w8a yet?)",
                  file=sys.stderr)
    conn.close()

    drop = (
        "\n-- =============================================================================\n"
        "-- ⚠️ INC-19 DROP+rebuild — run ONCE at cutover for the 5 EB INCREMENTALS so the\n"
        "-- native Snowflake tables adopt the FLOAT column types from the external table.\n"
        "-- (dbt --full-refresh MERGEs, it does NOT DROP — so DROP explicitly here, then let\n"
        "-- the next `dbtf build --select <model>` recreate from lakehouse_ext.<model>.)\n"
        "-- =============================================================================\n"
        + "".join(f"DROP TABLE IF EXISTS {fqn};\n" for fqn in EB_INCREMENTALS.values())
    )
    verify = "\n-- Verification:\n" + "".join(f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W8A_MODELS)
    ddl = "\n".join(blocks) + drop + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, run the CREATE EXTERNAL TABLEs + the EB DROPs in Snowflake, then "
              "rebuild the 5 EB incrementals before merging the model repoint.", file=sys.stderr)


if __name__ == "__main__":
    main()
