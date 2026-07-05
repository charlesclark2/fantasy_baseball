"""
export_statcast_to_s3.py
------------------------
E11.1-W1 prerequisite: export BASEBALL_DATA.BETTING.STG_BATTER_PITCHES from
Snowflake to S3 Parquet so the dbt-duckdb lakehouse build can read it.

Writes one Parquet file per game_year to:
  s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_batter_pitches/
  year=YYYY/part-0.parquet

Run ONCE before the first `dbtf run --target duckdb --select mart_pitch_*`.
Re-run periodically (weekly) to absorb new Statcast revisions.

This script takes several minutes for the full 2015→present history (~7.6M rows).
Hand off to operator per §0.1 — do not run inline in a Claude session.

Usage:
  # Export all seasons (default: 2015 → current)
  uv run python scripts/export_statcast_to_s3.py

  # Export a single season (fast, for incremental refresh)
  uv run python scripts/export_statcast_to_s3.py --year 2026

  # Dry-run: show row counts per year without writing
  uv run python scripts/export_statcast_to_s3.py --dry-run
"""

import argparse
import os
import sys
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import snowflake.connector
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_PREFIX = "baseball/lakehouse/stg_batter_pitches"
_SNOWFLAKE_TABLE = "BASEBALL_DATA.BETTING.STG_BATTER_PITCHES"
_DEFAULT_YEARS = list(range(2015, 2027))
_BATCH_ROWS = 500_000  # rows per fetchmany batch (~100 MB in memory)


# ── Snowflake connection ─────────────────────────────────────────────────────

def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — this
    # script's own file-path→password resolver KeyError'd on the box. Delegate to the
    # shared PATH-if-exists→inline→password resolver. Queries are fully-qualified, so
    # the default schema is immaterial. See CLAUDE.md "SNOWFLAKE MISREADS"/INC-22 landmine.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


# ── Export ──────────────────────────────────────────────────────────────────

def export_year(conn, s3, year: int, dry_run: bool = False) -> int:
    """Fetch one game_year from Snowflake and write to S3 Parquet. Returns row count."""
    sql = f"SELECT * FROM {_SNOWFLAKE_TABLE} WHERE game_year = {year}"
    print(f"  [{year}] querying Snowflake ...", flush=True)
    cur = conn.cursor()
    cur.execute(sql)

    # Stream in batches to keep peak memory bounded.
    schema = None
    writer = None
    row_count = 0
    tmp_path = Path(f"/tmp/stg_batter_pitches_{year}.parquet")

    while True:
        batch = cur.fetchmany(_BATCH_ROWS)
        if not batch:
            break
        col_names = [desc[0].lower() for desc in cur.description]
        import pandas as pd
        df = pd.DataFrame(batch, columns=col_names)
        table = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            schema = table.schema
            if not dry_run:
                writer = pq.ParquetWriter(str(tmp_path), schema)
        if not dry_run:
            writer.write_table(table)
        row_count += len(batch)
        print(f"  [{year}] {row_count:,} rows fetched ...", flush=True)

    cur.close()

    if writer:
        writer.close()

    print(f"  [{year}] {row_count:,} rows total", flush=True)

    if dry_run:
        print(f"  [{year}] dry-run — no S3 write")
        return row_count

    if row_count == 0:
        print(f"  [{year}] no rows — skipping S3 upload")
        return 0

    # Upload to S3.
    s3_key = f"{_S3_PREFIX}/year={year}/part-0.parquet"
    print(f"  [{year}] uploading to s3://{_S3_BUCKET}/{s3_key} ...", flush=True)
    s3.upload_file(str(tmp_path), _S3_BUCKET, s3_key)
    tmp_path.unlink(missing_ok=True)
    print(f"  [{year}] done", flush=True)
    return row_count


def main():
    ap = argparse.ArgumentParser(description="Export stg_batter_pitches → S3 Parquet (E11.1-W1)")
    ap.add_argument("--year", type=int, help="Export a single season (default: all 2015→present)")
    ap.add_argument("--dry-run", action="store_true", help="Count rows only, no S3 write")
    args = ap.parse_args()

    years = [args.year] if args.year else _DEFAULT_YEARS

    print(f"E11.1-W1 export: {_SNOWFLAKE_TABLE} → s3://{_S3_BUCKET}/{_S3_PREFIX}/")
    print(f"Seasons: {years}")
    if args.dry_run:
        print("DRY RUN — no S3 writes")

    conn = get_snowflake_conn()
    # INC-16 (AWS re-host): pass explicit keys ONLY when present (local/static-cred dev); else
    # let boto3 resolve the EC2 instance IAM role. Passing aws_access_key_id=None disables the
    # default chain → AuthorizationHeaderMalformed "a non-empty Access Key (AKID) must be provided".
    _s3_kwargs = {"region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")}
    _akid, _secret = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if _akid and _secret:
        _s3_kwargs["aws_access_key_id"] = _akid
        _s3_kwargs["aws_secret_access_key"] = _secret
    s3 = boto3.client("s3", **_s3_kwargs)

    total = 0
    for year in years:
        try:
            n = export_year(conn, s3, year, dry_run=args.dry_run)
            total += n
        except Exception as e:
            print(f"  [{year}] ERROR: {e}", file=sys.stderr)
            conn.close()
            sys.exit(1)

    conn.close()
    print(f"\nExport complete. Total rows: {total:,}")
    print(f"S3 path: s3://{_S3_BUCKET}/{_S3_PREFIX}/year=YYYY/part-0.parquet")
    print("\nNext step:")
    print("  dbtf run --target duckdb --select stg_batter_pitches mart_pitch_*")


if __name__ == "__main__":
    main()
