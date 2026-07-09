"""
export_w5_raw_to_s3.py
----------------------
E11.1-W5 lakehouse precursor export: Snowflake seeds + raw/builder tables → S3 parquet.
Mirrors export_w4_raw_to_s3.py. Run before run_w1_lakehouse.py --w5.

Two groups:
  • SEEDS (tiny static team dimension) — needed so the DuckDB build of the
    mart_game_results / mart_game_spine team chain can resolve `ref_teams` /
    `ref_team_aliases` as registered views. The seeds STAY dbt seeds in Snowflake
    (the source of truth, ~negligible cost); this only mirrors them to S3 so the
    DuckDB branch can read them. Exported from the PROD `betting.*` seed tables so
    the parity check (Snowflake CTAS vs DuckDB/S3) compares like-for-like.
  • W4-DEFERRED RAW/BUILDER tables — the precursors the four W4-inherited marts
    read (eb_park_factors_raw, oaa_team_season_raw, sprint_speed_raw). Like the
    W4 raw exports these are read directly by the marts' DuckDB branch via
    read_parquet(lakehouse_loc(...)). The builders that write these tables
    (fit_park_priors.py, the FanGraphs OAA + Savant sprint ingests) KEEP writing
    Snowflake — this export is the one-time/opt-in S3 mirror for the lakehouse
    build, same pattern + recurring-freshness caveat as W4 (wire into the daily op
    at cutover).

  ⚠️ E11.1-W8a OWNERSHIP TRANSFER (2026-06-29): eb_bullpen_team_posteriors was
  REMOVED from this mirror. W8a's dual-branch dbt model now BUILDS it directly to
  lakehouse/eb_bullpen_team_posteriors/data.parquet (run_w1_lakehouse.py --w8a).
  This mirror wrote it as `part-0.parquet`; leaving BOTH in the same prefix made
  the lakehouse_ext external table (and the `**/*.parquet` glob readers, e.g. W5b
  mart_bullpen_effectiveness) UNION both files → ~2x rows → a (game_pk, team)
  uniqueness-test failure. The stale part-0.parquet was deleted as a one-time
  cleanup. Keep --w8a ordered BEFORE --w5 so W5b reads the fresh data.parquet.

Each table is written as a single Parquet file to:
  s3://baseball-betting-ml-artifacts/baseball/lakehouse/<table>/part-0.parquet

Column names are lowercased to match the duckdb read-through and the marts'
lowercase column refs. Any dict/list VARIANT cell is json.dumps'd to clean VARCHAR
(harmless for these mostly-scalar tables; kept for symmetry with the W4 exporter).

Usage:
  uv run python scripts/export_w5_raw_to_s3.py                 # all tables
  uv run python scripts/export_w5_raw_to_s3.py --table ref_teams
  uv run python scripts/export_w5_raw_to_s3.py --dry-run
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
    # ── Seeds (tiny static team dimension) ────────────────────────────────────
    "ref_teams":                  "baseball_data.betting.ref_teams",
    "ref_team_aliases":           "baseball_data.betting.ref_team_aliases",
    # ── W4-deferred raw / builder-output precursors ───────────────────────────
    "eb_park_factors_raw":        "baseball_data.betting.eb_park_factors_raw",
    # NOTE: eb_bullpen_team_posteriors REMOVED 2026-06-29 — W8a's dbt model now BUILDS it to
    # lakehouse/eb_bullpen_team_posteriors/data.parquet (run_w1_lakehouse --w8a). Mirroring it
    # here too (as part-0.parquet) made the ext table / glob readers UNION both → ~2x rows. See
    # the docstring "W8a OWNERSHIP TRANSFER" note. Keep --w8a ordered before --w5.
    # E11.22 DROPPED (2026-07-09): oaa_team_season_raw + sprint_speed_raw were dropped from Snowflake
    # post both→s3 cutover — their consumers (mart_team_fielding_oaa / stg_batter_sprint_speed) read
    # the live lakehouse_raw/ mirror now, so this SF-mirror bridge no longer applies to them.
}


# ── Snowflake connection (mirrors export_w4_raw_to_s3.py) ─────────────────────

def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — this
    # script's own file-path→password resolver KeyError'd on the box. Delegate to the
    # shared PATH-if-exists→inline→password resolver. Queries are fully-qualified, so
    # the default schema is immaterial. See CLAUDE.md "SNOWFLAKE MISREADS"/INC-22 landmine.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


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
        description="Export W5 seeds + raw tables → S3 Parquet (E11.1-W5 lakehouse precursor)"
    )
    ap.add_argument(
        "--table",
        choices=sorted(TABLES.keys()),
        help="Export a single table (default: all).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Count rows only, no S3 write")
    args = ap.parse_args()

    selected = {args.table: TABLES[args.table]} if args.table else dict(TABLES)

    print(f"E11.1-W5 export: {len(selected)} table(s) → s3://{_S3_BUCKET}/baseball/lakehouse/")
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
    print("  uv run python scripts/run_w1_lakehouse.py --w5")


if __name__ == "__main__":
    main()
