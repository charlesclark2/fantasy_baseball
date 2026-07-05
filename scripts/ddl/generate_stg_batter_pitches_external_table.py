#!/usr/bin/env python3
"""
scripts/ddl/generate_stg_batter_pitches_external_table.py   (INC-27 — un-orphan the dropped table)

Emit Snowflake DDL that recreates ``baseball_data.betting.stg_batter_pitches`` as a thin VIEW over a
new external table ``baseball_data.lakehouse_ext.stg_batter_pitches`` built over the S3 parquet that
the daily ingest already writes:

    s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_batter_pitches/**/*.parquet
        (year=YYYY/*.parquet historical  +  year=YYYY/game_date=.../part-0.parquet daily)

WHY (INC-27, 2026-07-04): W11-E DISABLED the SF-native stg_batter_pitches incremental and DROPPED
``betting.stg_batter_pitches`` on a dbt-DAG conclusion ("only consumer = mart_pa_outcome_substrate,
duckdb-only"). But ~6+ Python scripts embed ``baseball_data.betting.stg_batter_pitches`` as a RAW SQL
STRING the DAG can't see — write_serving_store.py (box-score, HALT-tier), app/backend/routers/picks.py
(box-score endpoint), and the team/bullpen posterior state-writers — which then 500'd / HALTed at
runtime. Recreating the object as an external-table-backed view un-breaks EVERY consumer at once with
NO consumer code change and NO deploy (fully reversible: DROP the view + external table to revert).

This is NOT a hack — it is the exact same pattern as the ~100 other decommissioned tables in
lakehouse_ext (mart_pitch_*, the odds/CLV marts, the feature layer …). The daily REFRESH is wired
into refresh_w1_external_tables.py (W1_TABLES-adjacent, HALT/required) so the view never goes stale;
the exporter (ingest_statcast_to_s3_op) writes the parquet every day before the feature build.

PARTITION LAYOUT: like mart_pitch_* (year-partitioned), the external table uses a bare
``WITH LOCATION = @stage/stg_batter_pitches/`` — Snowflake recursively lists every file under the
prefix (both the historical year=YYYY/*.parquet and the daily game_date=.../part-0.parquet), so no
explicit PATTERN is needed. DuckDB writes lowercase parquet column names, so the VALUE: accessors are
lowercase (matches w1_external_tables.sql). stg_batter_pitches has NO TIMESTAMP columns (game_date is
a DATE, INT32 — reads correctly), so the W8a varchar-timestamp override does NOT apply here.

PREREQUISITES:
  1. The S3 stg_batter_pitches parquet exists (it does — ingest/export_statcast_to_s3 write it daily).
  2. The lakehouse_ext schema + s3_lakehouse stage + parquet_snappy file format already exist (W1d).
  3. AWS creds reachable via the DuckDB credential chain (instance role on the box).

USAGE (on the EC2 BOX — DuckDB must reach S3 in us-east-2):
  docker compose -f services/dagster/aws/docker-compose.yml exec -T \
    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
    python scripts/ddl/generate_stg_batter_pitches_external_table.py            # → stdout + .sql file
  # ... then apply the emitted DDL in Snowflake via data_loader.get_snowflake_connection()
  # (the Snowflake MCP role CANNOT run CREATE EXTERNAL TABLE / CREATE VIEW DDL).

OUTPUT: scripts/ddl/stg_batter_pitches_external_table.generated.sql
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "scripts" / "ddl" / "stg_batter_pitches_external_table.generated.sql"

BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
SCHEMA = "baseball_data.lakehouse_ext"
STAGE = f"{SCHEMA}.s3_lakehouse"
FILE_FORMAT = f"{SCHEMA}.parquet_snappy"
MODEL = "stg_batter_pitches"
PUBLIC_VIEW = "baseball_data.betting.stg_batter_pitches"


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
        # stg_batter_pitches has no TIMESTAMP columns, but keep the mapping honest.
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


def describe_parquet(conn):
    # union_by_name=true reconciles the two writer layouts (historical per-year vs daily partitioned).
    loc = f"{LAKEHOUSE}/{MODEL}/**/*.parquet"
    rows = conn.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{loc}', union_by_name=true)"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _ext_table_stmt(cols) -> str:
    # VALUE: accessor is CASE-SENSITIVE and must match the parquet's stored (lowercase) field name.
    def _line(name: str, dt: str) -> str:
        sf = duckdb_to_snowflake_type(dt)
        return f"    {name.upper():<40} {sf:<14} AS (VALUE:{name}::{sf})"

    cols_block = ",\n".join(_line(name, dt) for name, dt in cols)
    return (
        f"CREATE OR REPLACE EXTERNAL TABLE {SCHEMA}.{MODEL} (\n"
        f"{cols_block}\n)\n"
        f"WITH LOCATION = @{STAGE}/{MODEL}/\n"
        f"FILE_FORMAT = {FILE_FORMAT}\n"
        f"AUTO_REFRESH = FALSE\n"
        f"COMMENT = 'INC-27: stg_batter_pitches from S3 lakehouse parquet (un-orphan the dropped table)'"
    )


def build_statements(cols) -> list[str]:
    """The executable DDL statements, in order (no trailing semicolons — the connector executes one
    at a time). CREATE EXTERNAL TABLE → GRANT → CREATE VIEW → GRANT."""
    return [
        _ext_table_stmt(cols),
        f"GRANT SELECT ON EXTERNAL TABLE {SCHEMA}.{MODEL} TO ROLE CREDENCE_API_RO",
        f"CREATE OR REPLACE VIEW {PUBLIC_VIEW} AS SELECT * FROM {SCHEMA}.{MODEL}",
        f"GRANT SELECT ON VIEW {PUBLIC_VIEW} TO ROLE CREDENCE_API_RO",
    ]


def render_sql_file(cols) -> str:
    stmts = build_statements(cols)
    return (
        f"-- ── {MODEL}  ({len(cols)} columns) ──\n"
        f"{stmts[0]};\n{stmts[1]};\n\n"
        f"-- ── betting.stg_batter_pitches view (what the raw-SQL Python consumers read) ──\n"
        f"-- A thin passthrough so write_serving_store.py / picks.py / the posterior writers resolve\n"
        f"-- baseball_data.betting.stg_batter_pitches unchanged. Reversible: DROP VIEW to revert.\n"
        f"{stmts[2]};\n{stmts[3]};\n"
    )


def apply_statements(stmts) -> None:
    """Execute the DDL on Snowflake via the shared inline-key resolver (works on the EC2 box; the
    Snowflake MCP role CANNOT run CREATE EXTERNAL TABLE / CREATE VIEW). DDL is fully qualified, so
    the connection's default schema is immaterial."""
    _root = str(REPO_ROOT)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection(schema="lakehouse_ext")
    cur = conn.cursor()
    try:
        for stmt in stmts:
            print(f"  executing: {stmt.splitlines()[0][:80]} …", file=sys.stderr)
            is_grant = stmt.lstrip().upper().startswith("GRANT")
            try:
                cur.execute(stmt)
            except Exception as e:  # noqa: BLE001
                if is_grant:
                    # A GRANT hiccup (role already has access / missing grant priv) must NOT block
                    # the critical un-break — the ext table + view are already created above.
                    print(f"  WARNING skip GRANT (non-fatal): {e}", file=sys.stderr)
                    continue
                raise
        # Smoke: the view must return rows.
        cur.execute(f"SELECT count(*) FROM {PUBLIC_VIEW}")
        n = cur.fetchone()[0]
        print(f"  ✅ {PUBLIC_VIEW} created — {n:,} rows visible through the view.", file=sys.stderr)
        if not n:
            raise RuntimeError(f"{PUBLIC_VIEW} returned 0 rows — check the S3 parquet / stage listing.")
    finally:
        cur.close()
        conn.close()


def main() -> None:
    print_only = "--print" in sys.argv
    do_apply = "--apply" in sys.argv
    conn = get_duckdb_conn()
    cols = describe_parquet(conn)
    conn.close()
    print(f"  {MODEL}: {len(cols)} columns", file=sys.stderr)

    header = (
        "-- =============================================================================\n"
        "-- stg_batter_pitches_external_table.generated.sql — GENERATED by\n"
        "-- generate_stg_batter_pitches_external_table.py  (INC-27, 2026-07-04)\n"
        "-- Recreates betting.stg_batter_pitches as a view over lakehouse_ext.stg_batter_pitches\n"
        "-- (external table over the S3 parquet). Un-breaks the raw-SQL Python consumers the dbt\n"
        "-- DAG couldn't see. Run on the EC2 box via data_loader.get_snowflake_connection().\n"
        "-- Refresh wired into refresh_w1_external_tables.py (W1 required tier).\n"
        "-- =============================================================================\n"
    )
    verify = (
        f"\n-- Verification (expect a row count in the millions + a fresh max game_date):\n"
        f"-- SELECT count(*) FROM {SCHEMA}.{MODEL};\n"
        f"-- SELECT max(game_date) FROM {PUBLIC_VIEW};\n"
        f"-- A box-score smoke test (must return batter rows for a completed game):\n"
        f"-- SELECT batter_id, count(*) pa FROM {PUBLIC_VIEW}\n"
        f"--   WHERE game_pk = (SELECT max(game_pk) FROM {PUBLIC_VIEW} WHERE woba_denom = 1)\n"
        f"--     AND woba_denom = 1 GROUP BY batter_id LIMIT 5;\n"
    )
    ddl = header + "\n" + render_sql_file(cols) + verify
    if print_only:
        print(ddl)
    else:
        OUT_PATH.write_text(ddl)
        print(f"\nWrote {OUT_PATH}", file=sys.stderr)

    if do_apply:
        print("\n--apply: executing the DDL on Snowflake (inline-key resolver) …", file=sys.stderr)
        apply_statements(build_statements(cols))
    elif not print_only:
        print("Review it, then re-run with --apply to execute on the box (or run the CREATE "
              "EXTERNAL TABLE + CREATE VIEW in Snowflake via data_loader.get_snowflake_connection "
              "— the MCP role can't run DDL).", file=sys.stderr)


if __name__ == "__main__":
    main()
