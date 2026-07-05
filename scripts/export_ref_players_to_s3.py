"""
export_ref_players_to_s3.py
---------------------------
E11.1-W1 lakehouse gap-closer: export BASEBALL_DATA.SAVANT.REF_PLAYERS from
Snowflake to S3 Parquet so the dbt-duckdb lakehouse build can resolve the
player-name dimension.

Closes the 2026-06-23 duckdb build failure: mart_pitch_hitter_profile and
mart_pitch_pitcher_profile join the savant.ref_players source directly, but
savant sources have no duckdb resolution (only stg_batter_pitches has a
target.name=='duckdb' S3-read branch). Those two marts compiled to the
Snowflake FQN `baseball_data.savant.ref_players` and failed with
"Catalog baseball_data does not exist". stg_ref_players.sql now reads the
Parquet this script writes when target.name == 'duckdb'.

Writes a single Parquet file (the table is small, ~25.9k rows) to:
  s3://baseball-betting-ml-artifacts/baseball/lakehouse/stg_ref_players/part-0.parquet

Run ONCE before the next `dbtf run --target duckdb --select ... mart_pitch_*`.
Re-run when ref_players changes (new players added — infrequent).

Usage:
  uv run python scripts/export_ref_players_to_s3.py
  uv run python scripts/export_ref_players_to_s3.py --dry-run
"""

import argparse
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
_S3_KEY = "baseball/lakehouse/stg_ref_players/part-0.parquet"
_SNOWFLAKE_TABLE = "BASEBALL_DATA.SAVANT.REF_PLAYERS"


# ── Snowflake connection (mirrors export_statcast_to_s3.py) ──────────────────

def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — this
    # script's own file-path→password resolver KeyError'd on the box. Delegate to the
    # shared PATH-if-exists→inline→password resolver. Queries are fully-qualified, so
    # the default schema is immaterial. See CLAUDE.md "SNOWFLAKE MISREADS"/INC-22 landmine.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="savant")


# ── Export ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Export savant.ref_players → S3 Parquet (E11.1-W1 lakehouse gap-closer)"
    )
    ap.add_argument("--dry-run", action="store_true", help="Count rows only, no S3 write")
    args = ap.parse_args()

    print(f"E11.1-W1 export: {_SNOWFLAKE_TABLE} → s3://{_S3_BUCKET}/{_S3_KEY}")
    if args.dry_run:
        print("DRY RUN — no S3 write")

    conn = get_snowflake_conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_SNOWFLAKE_TABLE}")
        rows = cur.fetchall()
        # Lowercase column names so the duckdb read-through (stg_ref_players) and
        # the marts' lowercase column refs resolve cleanly.
        col_names = [desc[0].lower() for desc in cur.description]
        cur.close()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=col_names)
    print(f"  fetched {len(df):,} rows | columns: {list(df.columns)}")

    if args.dry_run:
        print("  dry-run — no S3 write")
        return

    tmp_path = Path("/tmp/stg_ref_players.parquet")
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
    print(f"  uploading to s3://{_S3_BUCKET}/{_S3_KEY} ...", flush=True)
    s3.upload_file(str(tmp_path), _S3_BUCKET, _S3_KEY)
    tmp_path.unlink(missing_ok=True)

    print(f"\nExport complete. {len(df):,} rows.")
    print("\nNext step:")
    print("  dbtf run --target duckdb --select stg_ref_players mart_pitch_hitter_profile mart_pitch_pitcher_profile")


if __name__ == "__main__":
    main()
