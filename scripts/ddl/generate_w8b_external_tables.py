#!/usr/bin/env python3
"""
scripts/ddl/generate_w8b_external_tables.py   (E11.1-W8b — serving aggregator + complex upstream)

Emit Snowflake EXTERNAL TABLE DDL over the S3 parquet that the W8b DuckDB build writes, so the
dbt models' Snowflake (else) branch `select * from baseball_data.lakehouse_ext.<model>` resolves
(and the at-cutover DROP+rebuild of the 2 INCREMENTAL aggregators adopts a deterministic FLOAT schema).

The W8b parquet is written by:
  scripts/run_w1_lakehouse.py --w8b            (each model → lakehouse/<model>/data.parquet)
which itself depends on:
  scripts/export_w8b_precursors_to_s3.py       (lineup_state, team_sequential_posteriors,
                                                stg_actionnetwork_public_betting, fct_fangraphs_pitching_analytics)
  scripts/export_features_to_s3.py             (the W11-deferred umpire/weather tail the aggregator reads)
  the W8a feature layer + prior-wave (W1-W7b) parquet already in S3.

⚠️ feature_pregame_injury_status is NOT emitted here — it already has a lakehouse_ext external table
  (W7b / refresh_w1_external_tables.W7B_TABLES); W8b only FINALIZES its dbt else-branch to read it.

PREREQUISITES:
  1. run_w1_lakehouse.py --w8b (or --w8b-only) has written all 9 parquet files.
  2. AWS creds reachable via the DuckDB credential chain; the lakehouse_ext schema + stage +
     parquet_snappy file format already exist (W1d).

USAGE:
  uv run python scripts/ddl/generate_w8b_external_tables.py            # → stdout + .sql file
  uv run python scripts/ddl/generate_w8b_external_tables.py --print    # stdout only

OUTPUT: scripts/ddl/w8b_external_tables.generated.sql — REVIEW, then run in Snowflake BEFORE the
PR merges (the else branches read these). Refresh: refresh_w1_external_tables.py (W8B_TABLES).
AUTO_REFRESH=FALSE.  ⚠️ feature_pregame_game_features_raw + feature_pregame_game_features are
INCREMENTAL on Snowflake — after creating their external tables, DROP the native incrementals
(baseball_data.betting_features.<model>) so the next dbt build rebuilds them from the external table
with FLOAT columns (INC-19: home_win_rate_trailing_3yr flips NUMBER(21,4)→FLOAT); a plain
`--full-refresh` MERGEs (does NOT DROP) and would leave NUMBER → 002108 HALT.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "w8b_external_tables.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"

# The 9 W8b models (single-file data.parquet). Order matches the build dependency order in
# run_w1_lakehouse.W8B_FEATURE_MODELS + the 2 Python-built macro models. injury_status is NOT here
# (reuses its existing W7b external table). The 2 aggregators are the INCREMENTALs that also need a
# native DROP+rebuild at cutover.
W8B_MODELS = [
    "feature_pregame_starter_features",
    "feature_pregame_lineup_features",
    "feature_pregame_bullpen_state_features",
    "feature_batter_archetype_matchups",
    "feature_pitcher_batter_h2h_matchups",
    "feature_pitcher_cluster_matchups",
    "feature_pregame_game_features_raw",
    "feature_league_contact_baseline",
    "feature_pregame_game_features",
]

# The 2 INCREMENTALs + their native Snowflake FQN (the DROP+rebuild targets). Both live in
# betting_features (the feature schema). home_win_rate_trailing_3yr flips NUMBER(21,4)→FLOAT, so a
# DROP is mandatory (dbt --full-refresh MERGEs, does NOT DROP NUMBER→FLOAT — 002108 HALT).
W8B_INCREMENTALS = {
    "feature_pregame_game_features_raw": "baseball_data.betting_features.feature_pregame_game_features_raw",
    "feature_pregame_game_features":     "baseball_data.betting_features.feature_pregame_game_features",
}

# ⚠️ TIMESTAMP columns stored as ISO **VARCHAR** in the parquet (run_w1_lakehouse._string_timestamp_wrap).
# Snowflake misreads BINARY parquet timestamps per-row (micros read as seconds → year ~56M → connector
# EOVERFLOW on fetch — the W8a 24h serving outage). So these columns land in the parquet as strings; the
# external table declares them TIMESTAMP_NTZ AS (VALUE:col::TIMESTAMP_NTZ) — a reliable STRING parse.
# Keep in sync with _string_timestamp_wrap (it stringifies EVERY TIMESTAMP* col). DATE cols read fine →
# NOT listed.  lineup_features carries SCD-2 sentinel timestamps; the aggregator + wrapper carry
# odds_ingestion_ts (the wrapper via raw.*).
TS_STRING_COLS = {
    "feature_pregame_lineup_features":  {"valid_from", "valid_to", "computed_at"},
    "feature_pregame_game_features_raw": {"odds_ingestion_ts"},
    "feature_pregame_game_features":    {"odds_ingestion_ts"},
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
    # ⚠️ VALUE: is CASE-SENSITIVE and must match the parquet's STORED field name EXACTLY (W8a bug 3:
    # a hard .lower() reads an uppercase field as ALL-NULL, silently, parity-blind). The 9 W8b models
    # alias every output column lowercase, so the described case IS lowercase — but emit the EXACT
    # described case regardless (robust if a future column inherits a mirror's case). The external-table
    # COLUMN name stays UPPERCASE (unquoted-ref friendly for the dbt else branch); only VALUE: must match.
    # TIMESTAMP cols are stored as ISO VARCHAR but exposed as TIMESTAMP_NTZ via a STRING parse
    # (VALUE:col::TIMESTAMP_NTZ) — see TS_STRING_COLS — sidestepping Snowflake's broken binary
    # parquet-timestamp per-row read.
    ts_string = {c.lower() for c in TS_STRING_COLS.get(model, ())}

    def _line(name: str, dt: str) -> str:
        sf = "TIMESTAMP_NTZ" if name.lower() in ts_string else duckdb_to_snowflake_type(dt)
        return f"    {name.upper():<40} {sf:<14} AS (VALUE:{name}::{sf})"

    col_lines = [_line(name, dt) for name, dt in cols]
    cols_block = ",\n".join(col_lines)
    return (
        f"-- ── {model}  ({len(cols)} columns) ──\n"
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{model} (\n"
        f"{cols_block}\n)\n"
        f"WITH LOCATION = @{STAGE}/{model}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'E11.1-W8b: {model} from S3 lakehouse parquet (serving aggregator + complex upstream)';\n"
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{model} TO ROLE CREDENCE_API_RO;\n"
    )


def main() -> None:
    print_only = "--print" in sys.argv
    conn = get_duckdb_conn()
    header = (
        "-- =============================================================================\n"
        "-- w8b_external_tables.generated.sql — GENERATED by generate_w8b_external_tables.py\n"
        "-- E11.1-W8b: external tables over the S3 parquet for the serving aggregator + the complex\n"
        "-- upstream / matchup feature models. Run AFTER run_w1_lakehouse.py --w8b (parquet must exist)\n"
        "-- and BEFORE the PR merges (the models' Snowflake else branch reads these). Refresh:\n"
        "-- refresh_w1_external_tables.py (W8B_TABLES).\n"
        "-- =============================================================================\n"
    )
    blocks = [header]
    for model in W8B_MODELS:
        try:
            cols = describe_parquet(conn, model)
            blocks.append(emit_external_table(model, cols))
            print(f"  {model}: {len(cols)} columns", file=sys.stderr)
        except Exception as e:
            print(f"  SKIP {model}: {e}  (have you run run_w1_lakehouse.py --w8b yet?)",
                  file=sys.stderr)
    conn.close()

    drop = (
        "\n-- =============================================================================\n"
        "-- ⚠️ INC-19 DROP+rebuild — run ONCE at cutover for the 2 INCREMENTAL aggregators so the\n"
        "-- native Snowflake tables adopt the FLOAT column types from the external table\n"
        "-- (home_win_rate_trailing_3yr flips NUMBER(21,4)→FLOAT; dbt --full-refresh MERGEs, it does\n"
        "-- NOT DROP — so DROP explicitly here, then let the next `dbtf build --select <model>` recreate\n"
        "-- from lakehouse_ext.<model>). Rebuild feature_pregame_game_features_raw BEFORE its wrapper.\n"
        "-- =============================================================================\n"
        + "".join(f"DROP TABLE IF EXISTS {fqn};\n" for fqn in W8B_INCREMENTALS.values())
    )
    verify = "\n-- Verification:\n" + "".join(f"-- SELECT count(*) FROM {SCHEMA}.{m};\n" for m in W8B_MODELS)
    ddl = "\n".join(blocks) + drop + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)
        print("Review it, run the CREATE EXTERNAL TABLEs + the 2 aggregator DROPs in Snowflake, then "
              "rebuild the 2 incrementals (raw before wrapper) before merging the model repoint.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
