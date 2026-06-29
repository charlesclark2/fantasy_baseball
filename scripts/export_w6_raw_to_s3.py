#!/usr/bin/env python3
"""
export_w6_raw_to_s3.py
----------------------
E11.1-W6 lakehouse precursor export → S3 parquet, so the W6 odds/CLV + Group-C marts'
DuckDB branches can read them. Two output tiers:

  • FLAT tables → s3://.../baseball/lakehouse/<name>/part-0.parquet  (read by the marts
    via {{ source(...) }} → a TYPED view registered in run_w1_lakehouse._build_w6):
      - odds_snapshots_historical  (oddsapi; 2021–2025 backfill, ~2.6M rows, STATIC —
        read directly by mart_closing_line_value + mart_odds_line_movement)
      - daily_model_predictions    (betting_ml; ~54k rows, RECURRING — read by
        mart_prediction_clv + mart_clv_labeled_games. The Snowflake table STAYS the
        serving write/read target; this is only an S3 mirror for the lakehouse CLV
        build. ⚠ FRESHNESS: re-export before each W6 daily build, AFTER predict_today,
        else the /performance CLV marts go stale — the daily op wires this.)

  • RAW JSON → s3://.../baseball/lakehouse_raw/venues_raw/  (W3pre-style raw tier, read by
    stg_statsapi_venues' DuckDB flatten via {{ lakehouse_raw_loc("venues_raw") }}):
      - venues_raw (statsapi; ~96 rows; json_field VARIANT → JSON-string VARCHAR)
    NOTE: stg_statsapi_lineups reads lakehouse_raw/monthly_schedule, ALREADY exported by
    scripts/export_odds_raw_to_s3.py (W3pre) — not re-exported here.

⚠️ >1 min on odds_snapshots_historical (2.6M rows) → operator runs it.

Usage:
  uv run python scripts/export_w6_raw_to_s3.py                              # all
  uv run python scripts/export_w6_raw_to_s3.py --table daily_model_predictions
  uv run python scripts/export_w6_raw_to_s3.py --table odds_snapshots_historical
  uv run python scripts/export_w6_raw_to_s3.py --dry-run
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

# scripts/ is on sys.path under the runtime; the raw-tier writer lives there.
from utils.lakehouse_raw_writer import write_raw_rows_s3

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified table (FLAT tier, part-0.parquet).
FLAT_TABLES = {
    "odds_snapshots_historical": "baseball_data.oddsapi.odds_snapshots_historical",
    "daily_model_predictions":   "baseball_data.betting_ml.daily_model_predictions",
}

# RAW-JSON tier (lakehouse_raw/, json_field VARIANT → JSON-string VARCHAR), exported via
# the shared keystone so the bytes match the live-writer / W3pre export layout exactly.
RAW_SOURCES = {
    # ingest_date is ALSO aliased to ingestion_ts so write_raw_rows_s3 keys the dt= partition
    # off the venue's (stable) ingest_date — NOT today (the default for an absent ingestion_ts).
    # That makes the re-export idempotent under mode='overwrite_partition' (same data → same
    # partition cleared+rewritten); without it a cross-day re-run would orphan the prior dt=
    # partition and double the 96 venue rows (the W2 re-ingest dupe class). The flatten ignores
    # the extra ingestion_ts column (reads venue_id / ingest_date / json_field).
    "venues_raw": (
        "baseball_data.statsapi.venues_raw",
        "venue_id, ingest_date::varchar as ingest_date, "
        "ingest_date::varchar as ingestion_ts, to_json(json_field) as json_field",
    ),
}

ALL_NAMES = list(FLAT_TABLES) + list(RAW_SOURCES)


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
        schema="betting",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


def _coerce_variant_cells(df: pd.DataFrame) -> pd.DataFrame:
    """json.dumps any dict/list VARIANT cell to clean VARCHAR (e.g.
    daily_model_predictions.sub_model_versions_used)."""
    def _fix(cell):
        if isinstance(cell, (dict, list)):
            return json.dumps(cell)
        return cell
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_fix)
    return df


def _s3():
    # INC-16 (AWS re-host): on the EC2 host S3 access comes from the instance IAM ROLE, so
    # AWS_ACCESS_KEY_ID is UNSET. Passing aws_access_key_id=None to boto3 DISABLES its default
    # credential chain → "AuthorizationHeaderMalformed: a non-empty Access Key (AKID) must be
    # provided". Pass explicit keys ONLY when both are present (local/static-cred dev); else let
    # boto3 resolve the instance role — the same chain DuckDB COPY uses for the W-series writes.
    kwargs = {"region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")}
    akid, secret = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if akid and secret:
        kwargs["aws_access_key_id"] = akid
        kwargs["aws_secret_access_key"] = secret
    return boto3.client("s3", **kwargs)


def _export_flat(conn, lakehouse_name: str, fqn: str, dry_run: bool) -> int:
    s3_key = f"baseball/lakehouse/{lakehouse_name}/part-0.parquet"
    print(f"\n[{lakehouse_name}] {fqn} → s3://{_S3_BUCKET}/{s3_key}")
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {fqn}")
        rows = cur.fetchall()
        col_names = [desc[0].lower() for desc in cur.description]
    finally:
        cur.close()
    df = _coerce_variant_cells(pd.DataFrame(rows, columns=col_names))
    print(f"  fetched {len(df):,} rows | {len(df.columns)} columns")
    if dry_run:
        print("  dry-run — no S3 write")
        return len(df)
    tmp = Path(f"/tmp/{lakehouse_name}.parquet")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp))
    print(f"  uploading {tmp.stat().st_size/1e6:.1f} MB → s3://{_S3_BUCKET}/{s3_key} ...", flush=True)
    _s3().upload_file(str(tmp), _S3_BUCKET, s3_key)
    tmp.unlink(missing_ok=True)
    print(f"  done — {len(df):,} rows.")
    return len(df)


def _export_raw(conn, source: str, fqn: str, cols: str, dry_run: bool) -> int:
    print(f"\n[{source}] {fqn} → lakehouse_raw/{source}/ (raw JSON tier)")
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT {cols} FROM {fqn}")
        names = [d[0].lower() for d in cur.description]
        rows = [dict(zip(names, r)) for r in cur.fetchall()]
    finally:
        cur.close()
    print(f"  fetched {len(rows):,} rows")
    if dry_run:
        print("  dry-run — no S3 write")
        return len(rows)
    # mode='overwrite_partition' keeps the dt= partition idempotent across re-runs.
    n = write_raw_rows_s3(source, rows, mode="overwrite_partition")
    print(f"  done — {n:,} rows → lakehouse_raw/{source}/")
    return n


def main():
    ap = argparse.ArgumentParser(description="E11.1-W6 precursor export → S3")
    ap.add_argument("--table", choices=sorted(ALL_NAMES), help="Export one (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="Row counts only, no S3 write")
    args = ap.parse_args()

    selected = [args.table] if args.table else ALL_NAMES
    print(f"E11.1-W6 export: {selected}" + ("  | DRY-RUN" if args.dry_run else ""))

    failures: list[tuple[str, str]] = []
    conn = get_snowflake_conn()
    try:
        for name in selected:
            try:
                if name in FLAT_TABLES:
                    _export_flat(conn, name, FLAT_TABLES[name], args.dry_run)
                else:
                    fqn, cols = RAW_SOURCES[name]
                    _export_raw(conn, name, fqn, cols, args.dry_run)
            except Exception as exc:  # noqa: BLE001 — continue to the others
                print(f"  ERROR exporting {name}: {exc}")
                failures.append((name, str(exc)))
    finally:
        conn.close()

    if failures:
        print(f"\nExport finished with {len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)

    print(f"\nExport complete. {len(selected)} table(s) written.")
    if not args.dry_run:
        print("\nNext: uv run python scripts/run_w1_lakehouse.py --w6")
        print("Then: uv run python scripts/parity_check_w6.py")


if __name__ == "__main__":
    main()
