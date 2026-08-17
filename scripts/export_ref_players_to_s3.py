"""
export_ref_players_to_s3.py
---------------------------
Seed the FROZEN HISTORICAL ARCHIVE layer of the player-name dimension.

⛔ THIS IS NOT A LIVE WRITER, AND ITS SOURCE IS DEAD.
   `baseball_data.savant.ref_players` has NO writer anywhere in this repo — no ingest, no dbt
   model, no op (verified by a whole-repo grep, this story). Snowflake reports it
   `last_altered = 2025-10-13` with `max(mlb_played_last) = 2025`. It is a one-time historical
   load that will never advance again. Re-running this script CANNOT make the dimension fresher;
   it only re-copies the same 25,900 rows.

WHAT CHANGED (E5.10 follow-up)
------------------------------
This script used to write `baseball/lakehouse/stg_ref_players/` — the prefix ~11 consumers read
directly. Because nothing scheduled it, that prefix sat 53 days stale holding ZERO 2026 players,
and a serving writer silently skipped 34 batters. The fix does NOT schedule this script (that
would refresh an mtime over dead content and make an INC-41 freshness SLA read GREEN forever —
the exact false-green INC-41 exists to prevent). Instead:

  * this script now writes `baseball/lakehouse/stg_ref_players_archive/`, a prefix whose NAME
    declares that it is frozen, so it can never again be mistaken for a live table;
  * `scripts/build_ref_players_dimension.py` MERGES this archive under the LIVE
    `player_profiles_raw` feed and writes the `stg_ref_players/` prefix every consumer reads.

The archive still earns its place: measured over the whole Statcast history, it misses ZERO
pre-2020 debutants while the live profiles feed misses 471 of them (profiles was backfilled from
`mart_pitch_play_event WHERE game_year >= 2020`). Live fixes the present; the archive holds the
past. Dropping either one regresses coverage.

⇒ RUN THIS ONLY to (re-)seed the archive prefix — a fresh bucket, a restored environment, or a
   one-off correction to the historical table. Routine freshness is `build_ref_players_dimension.py`.

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
# ⛔ The ARCHIVE prefix, deliberately NOT the live `stg_ref_players/` prefix consumers read.
# Writing the live prefix from this dead source is the defect this story fixed.
_S3_KEY = "baseball/lakehouse/stg_ref_players_archive/part-0.parquet"
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

    tmp_path = Path("/tmp/stg_ref_players_archive.parquet")
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
    print("  uv run python scripts/build_ref_players_dimension.py   "
          "# merge this archive under the LIVE feed and publish stg_ref_players/")


if __name__ == "__main__":
    main()
