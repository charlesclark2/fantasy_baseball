"""
export_w7b_precursors_to_s3.py
------------------------------
E11.1-W7b lakehouse precursor export: the player_transactions TYPED Snowflake table
→ S3 parquet, so the stg_statsapi_transactions duckdb branch can read it (the head of
the mart_player_profile_identity injury chain). Mirrors export_w4_raw_to_s3.py /
export_w5_raw_to_s3.py exactly. Run before run_w1_lakehouse.py --w7b.

WHY a TYPED parquet (not a raw-JSON flatten):
  baseball_data.statsapi.player_transactions is already a RELATIONAL table
  (transaction_id, player_id, …, description, ingestion_ts) — NOT a VARIANT JSON blob
  like monthly_schedule. So the lowest-risk migration is the W4/W5 typed-table pattern:
  export it as a flat parquet to lakehouse/player_transactions/part-0.parquet, and have
  stg_statsapi_transactions's duckdb branch read it via read_parquet(lakehouse_loc(...))
  with the SAME dedup (row_number()/where rn=1) it already runs on Snowflake — no JSON
  parsing, value-identical output. (The raw-flatten path would only be needed if the
  source were un-flattened JSON, as monthly_schedule is for stg_statsapi_games/lineups.)

  The ingest writer (ingest_transactions.py) KEEPS its Snowflake append — this is the
  one-time/opt-in S3 mirror with the same recurring-freshness caveat as W4/W5 (wire the
  re-export into the daily op at cutover, or flip the writer to dual-write S3).

Each table is written as a single Parquet file to:
  s3://baseball-betting-ml-artifacts/baseball/lakehouse/<table>/part-0.parquet

Column names are lowercased to match the duckdb read-through and the marts' lowercase
column refs. Any dict/list VARIANT cell is json.dumps'd to clean VARCHAR (harmless for
this scalar table; kept for symmetry with the W4/W5 exporters).

Usage:
  uv run python scripts/export_w7b_precursors_to_s3.py                 # all tables
  uv run python scripts/export_w7b_precursors_to_s3.py --table player_transactions
  uv run python scripts/export_w7b_precursors_to_s3.py --dry-run
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
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified table name.
TABLES = {
    # ── Head of the mart_player_profile_identity injury chain ─────────────────
    # player_transactions → stg_statsapi_transactions (duckdb branch reads this) →
    # stg_statsapi_player_injury_status → feature_pregame_injury_status (SCD-2) →
    # mart_player_profile_identity.
    "player_transactions": "baseball_data.statsapi.player_transactions",
}


# ── Snowflake connection (mirrors export_w5_raw_to_s3.py) ─────────────────────

def _load_private_key() -> bytes | None:
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw, password=passphrase.encode() if passphrase else None, backend=default_backend()
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="statsapi",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


# ── VARIANT serialization ────────────────────────────────────────────────────

def _coerce_variant_cells(df: pd.DataFrame) -> pd.DataFrame:
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

    s3 = boto3.client(
        "s3",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    print(f"  uploading to s3://{_S3_BUCKET}/{s3_key} ...", flush=True)
    s3.upload_file(str(tmp_path), _S3_BUCKET, s3_key)
    tmp_path.unlink(missing_ok=True)
    print(f"  done — {len(df):,} rows.")
    return len(df)


def main():
    ap = argparse.ArgumentParser(
        description="Export W7b precursor tables → S3 Parquet (E11.1-W7b lakehouse precursor)"
    )
    ap.add_argument(
        "--table",
        choices=sorted(TABLES.keys()),
        help="Export a single table (default: all).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Count rows only, no S3 write")
    args = ap.parse_args()

    selected = {args.table: TABLES[args.table]} if args.table else dict(TABLES)

    print(f"E11.1-W7b export: {len(selected)} table(s) → s3://{_S3_BUCKET}/baseball/lakehouse/")
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
        sys.exit(1)

    print(f"\nExport complete. {len(selected)} table(s) written.")
    print("\nNext step:")
    print("  uv run python scripts/run_w1_lakehouse.py --w7b")


if __name__ == "__main__":
    main()
