"""
export_w4_raw_to_s3.py
----------------------
E11.1-W4 lakehouse precursor export: Snowflake raw tables → S3 parquet.
Mirrors export_ref_players_to_s3.py. Run before run_w1_lakehouse.py --w4.

Exports the W4 raw substrate tables (catcher framing, park factors, statsapi
player profiles, FanGraphs Stuff+, ZiPS hitting/pitching projections, and the
FanGraphs hitting leaderboard) from Snowflake to S3 Parquet so the dbt-duckdb
lakehouse build can resolve them without a request-path Snowflake hit.

Each table is written as a single Parquet file (the tables are
small-to-moderate leaderboards/projections) to:
  s3://baseball-betting-ml-artifacts/baseball/lakehouse/<table>/part-0.parquet

These tables carry a VARIANT column (`raw_json`, and possibly others). The
Snowflake connector returns VARIANT values as Python str (JSON text), but if a
cell comes back as a dict/list it is re-serialized with json.dumps so the
column lands in Parquet as clean VARCHAR (DuckDB parses it with json functions
downstream). Column names are lowercased to match the duckdb read-through and
the marts' lowercase column refs.

Usage:
  uv run python scripts/export_w4_raw_to_s3.py                 # all tables
  uv run python scripts/export_w4_raw_to_s3.py --table fg_stuff_plus_raw
  uv run python scripts/export_w4_raw_to_s3.py --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import snowflake.connector
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified table name.
TABLES = {
    "catcher_framing_raw": "baseball_data.savant.catcher_framing_raw",
    "savant_park_factors_raw": "baseball_data.fangraphs.savant_park_factors_raw",
    "player_profiles_raw": "baseball_data.statsapi.player_profiles_raw",
    "fg_stuff_plus_raw": "baseball_data.fangraphs.fg_stuff_plus_raw",
    "fg_zips_hitting_raw": "baseball_data.fangraphs.fg_zips_hitting_raw",
    "fg_hitting_leaderboard_raw": "baseball_data.fangraphs.fg_hitting_leaderboard_raw",
    "fg_zips_pitching_raw": "baseball_data.fangraphs.fg_zips_pitching_raw",
}


# ── Snowflake connection ─────────────────────────────────────────────────────
# E11.1-W11-FG (2026-07-05): delegate to the shared inline-key-safe resolver.
# This script previously carried its OWN reader (SNOWFLAKE_PRIVATE_KEY_PATH else
# os.environ["SNOWFLAKE_PASSWORD"]) — BOTH are UNSET on the EC2 box, which authenticates via the
# INLINE SNOWFLAKE_PRIVATE_KEY → KeyError('SNOWFLAKE_PASSWORD'). Same straggler class CLAUDE.md
# calls out (fixed the same way in refresh_w1_external_tables.py): route through the INC-22 shared
# resolver (PATH-if-exists → inline key → password). Queries are fully-qualified, so the schema is
# immaterial (kept 'savant' to preserve the prior default).

def get_snowflake_conn():
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="savant")


# ── VARIANT serialization ────────────────────────────────────────────────────

def _coerce_variant_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Re-serialize any dict/list cells in object-dtype columns to JSON strings.

    VARIANT columns (e.g. raw_json) usually come back as str (JSON text), but if
    the connector hands back a dict/list, json.dumps it so the column is a clean
    VARCHAR in Parquet. Scalars (str/int/float/None) are left untouched.
    """
    def _fix(cell):
        if isinstance(cell, (dict, list)):
            return json.dumps(cell)
        return cell

    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_fix)
    return df


# ── Export ────────────────────────────────────────────────────────────────────

def _export_one(conn, lakehouse_name: str, snowflake_fqn: str, dry_run: bool) -> int:
    s3_key = f"baseball/lakehouse/{lakehouse_name}/part-0.parquet"
    print(f"\n[{lakehouse_name}] {snowflake_fqn} → s3://{_S3_BUCKET}/{s3_key}")

    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {snowflake_fqn}")
        rows = cur.fetchall()
        # Lowercase column names so the duckdb read-through and the marts'
        # lowercase column refs resolve cleanly.
        col_names = [desc[0].lower() for desc in cur.description]
    finally:
        cur.close()

    df = pd.DataFrame(rows, columns=col_names)
    df = _coerce_variant_cells(df)
    print(f"  fetched {len(df):,} rows | columns: {list(df.columns)}")

    if dry_run:
        print("  dry-run — no S3 write")
        return len(df)

    tmp_path = Path(f"/tmp/{lakehouse_name}.parquet")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp_path))

    # INC-16 (AWS re-host): pass explicit keys ONLY when present (local/static-cred dev); else
    # let boto3 resolve the EC2 instance IAM role. Passing aws_access_key_id=None disables the
    # default chain → AuthorizationHeaderMalformed "a non-empty Access Key (AKID) must be provided".
    _s3_kwargs = {"region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")}
    _akid, _secret = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if _akid and _secret:
        _s3_kwargs["aws_access_key_id"] = _akid
        _s3_kwargs["aws_secret_access_key"] = _secret
    s3 = boto3.client("s3", **_s3_kwargs)
    print(f"  uploading to s3://{_S3_BUCKET}/{s3_key} ...", flush=True)
    s3.upload_file(str(tmp_path), _S3_BUCKET, s3_key)
    tmp_path.unlink(missing_ok=True)
    print(f"  done — {len(df):,} rows.")
    return len(df)


def main():
    ap = argparse.ArgumentParser(
        description="Export W4 raw tables → S3 Parquet (E11.1-W4 lakehouse precursor)"
    )
    ap.add_argument(
        "--table",
        choices=sorted(TABLES.keys()),
        help="Export a single table (default: all).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Count rows only, no S3 write")
    args = ap.parse_args()

    selected = {args.table: TABLES[args.table]} if args.table else dict(TABLES)

    print(f"E11.1-W4 export: {len(selected)} table(s) → s3://{_S3_BUCKET}/baseball/lakehouse/")
    if args.dry_run:
        print("DRY RUN — no S3 write")

    failures: list[tuple[str, str]] = []
    conn = get_snowflake_conn()
    try:
        for lakehouse_name, snowflake_fqn in selected.items():
            try:
                _export_one(conn, lakehouse_name, snowflake_fqn, args.dry_run)
            except Exception as exc:  # noqa: BLE001 — continue to the other tables
                print(f"  ERROR exporting {lakehouse_name} ({snowflake_fqn}): {exc}")
                failures.append((lakehouse_name, str(exc)))
    finally:
        conn.close()

    if failures:
        print(f"\nExport finished with {len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        print("\nNext step (after fixing failures):")
        print("  uv run python scripts/run_w1_lakehouse.py --w4")
        sys.exit(1)

    print(f"\nExport complete. {len(selected)} table(s) written.")
    print("\nNext step:")
    print("  uv run python scripts/run_w1_lakehouse.py --w4")


if __name__ == "__main__":
    main()
