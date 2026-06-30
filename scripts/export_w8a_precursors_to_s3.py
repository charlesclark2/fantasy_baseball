#!/usr/bin/env python3
"""
export_w8a_precursors_to_s3.py   (E11.1-W8a — upstream feature-layer precursor mirror)
--------------------------------------------------------------------------------------
Mirror the 3 PYTHON-WRITTEN precursor tables that the W8a feature/EB DuckDB branches read
but which are NOT dbt models (so they have no DuckDB branch of their own) → S3 lakehouse
parquet. With these in S3, the W8a consumers can build entirely on DuckDB:

  • mart_player_start_probability   (betting_ml/scripts/score_playing_time.py; write_pandas
      CREATE OR REPLACE) → read by feature_pregame_expected_lineup (Σ P(start)·stat).
  • feature_pregame_market_features (scripts/backfill_market_features_scd2.py; SCD-2 MERGE)
      → read by feature_pregame_odds_features (the is_current lowvig h2h / totals snapshot).
  • player_sequential_posteriors    (betting_ml/scripts/sequential_bayes/update_player_
      posteriors.py; SCD-2 MERGE) → read by eb_starter_posteriors + eb_batter_posteriors_raw
      (the Epic-16.2 as-of `seq` column; a HARDCODED FQN read, not a ref/source — the W7a
      "hidden dependency" class). The operator chose to bring this 3rd mirror along so both
      EB models stay in W8a scope (it is the identical low-risk full-table mirror pattern).
  • team_elo_history                 (betting_ml/scripts/compute_elo.py; write_pandas REPLACE)
      → read by feature_pregame_team_features via a source() on baseball_data.betting (the
      elo_before_game pre-game feature). Already mirrored by W7b export_features_to_s3.py for
      the serving readers; re-mirrored here so a standalone `--w8a-only` build is self-contained
      (it does not have to assume the W7b export ran first). Same low-risk full-table mirror;
      both writers hit the SAME S3 key with the SAME SELECT *, so the daily double-write is
      idempotent.

WHY a mirror (NOT a per-table DuckDB write) — same design as W9/W7b-1:
  All 3 are STATEFUL Python writes (write_pandas REPLACE or SCD-2 MERGE). Re-implementing
  their write/accumulate semantics in DuckDB-over-S3 is the exact class that wiped W7a's
  rolling history. A SINGLE full-table `SELECT *` copy is accumulate-safe BY CONSTRUCTION:
  it carries every row (every SCD-2 version, every walk-forward snapshot). The native
  Snowflake write stays the live (correct) path; this is the additive dual-write to S3.

S3 LAYOUT: baseball/lakehouse/<name>/data.parquet (single-file mart layout). The universal
  `<name>/**/*.parquet` glob matches data.parquet; generate_w8a_external_tables.py DESCRIBEs
  the same parquet to emit the lakehouse_ext DDL.

S3 AUTH: the shared instance-role-safe `lakehouse_raw_writer.make_s3_client()` (the W7b-1
  AKID footgun cure — NEVER pass aws_access_key_id=os.environ.get(...) to boto3; the
  credential chain resolves the EC2 instance role / env static creds). Lint-enforced.

Usage:
  uv run python scripts/export_w8a_precursors_to_s3.py                                 # all 3
  uv run python scripts/export_w8a_precursors_to_s3.py --table mart_player_start_probability
  uv run python scripts/export_w8a_precursors_to_s3.py --dry-run                       # counts only
"""

import argparse
import json
import os
import sys
from pathlib import Path

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

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
# Shared instance-role-safe S3 client (NO hand-rolled boto3 — the W7b-1 AKID footgun the
# cure session lint-gates).
try:
    from scripts.utils.lakehouse_raw_writer import make_s3_client as _s3_client
except ImportError:  # pragma: no cover — pytest pythonpath=scripts
    from utils.lakehouse_raw_writer import make_s3_client as _s3_client

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified precursor table. The 3 Python-written tables read
# by the W8a DuckDB branches that are not already in S3, PLUS the 3 EB-prior dbt SEEDS the EB
# DuckDB branches read via ref() (dbt seeds live in Snowflake only; the W5 game chain already
# mirrors ref_teams/ref_team_aliases the same way — export_w5_raw_to_s3.py). The seeds are tiny
# (93/432/528 rows) and static; re-mirror only when the seed CSV changes.
MIRROR_TABLES = {
    "mart_player_start_probability":   "baseball_data.betting.mart_player_start_probability",
    "feature_pregame_market_features": "baseball_data.betting_features.feature_pregame_market_features",
    "player_sequential_posteriors":    "baseball_data.betting.player_sequential_posteriors",
    "team_elo_history":                "baseball_data.betting.team_elo_history",
    "ref_eb_starter_priors":           "baseball_data.betting.ref_eb_starter_priors",
    "ref_eb_lineup_priors":            "baseball_data.betting.ref_eb_lineup_priors",
    "ref_eb_bullpen_priors":           "baseball_data.betting.ref_eb_bullpen_priors",
}
ALL_NAMES = sorted(MIRROR_TABLES)


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
    """json.dumps any dict/list VARIANT cell to clean VARCHAR so pyarrow can write it."""
    def _fix(cell):
        if isinstance(cell, (dict, list)):
            return json.dumps(cell)
        return cell
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_fix)
    return df


def _export(conn, lakehouse_name: str, fqn: str, dry_run: bool) -> int:
    s3_key = f"baseball/lakehouse/{lakehouse_name}/data.parquet"
    print(f"\n[{lakehouse_name}] {fqn} → s3://{_S3_BUCKET}/{s3_key}")
    cur = conn.cursor()
    try:
        # SELECT * = the WHOLE table (every SCD-2 version / walk-forward snapshot) →
        # accumulate-safe; the W8a consumer applies its own is_current / as-of filter.
        cur.execute(f"SELECT * FROM {fqn}")
        rows = cur.fetchall()
        # Preserve the SELECT * identifier case the table produced (the DuckDB / Snowflake
        # readers address columns by that case) — do NOT force lower.
        col_names = [desc[0] for desc in cur.description]
    finally:
        cur.close()
    df = _coerce_variant_cells(pd.DataFrame(rows, columns=col_names))
    print(f"  fetched {len(df):,} rows | {len(df.columns)} columns")
    if dry_run:
        print("  dry-run — no S3 write")
        return len(df)
    tmp = Path(f"/tmp/{lakehouse_name}.parquet")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp))
    print(f"  uploading {tmp.stat().st_size / 1e6:.1f} MB → s3://{_S3_BUCKET}/{s3_key} ...", flush=True)
    _s3_client().upload_file(str(tmp), _S3_BUCKET, s3_key)
    tmp.unlink(missing_ok=True)
    print(f"  done — {len(df):,} rows.")
    return len(df)


def main():
    ap = argparse.ArgumentParser(description="E11.1-W8a Python-precursor export-mirror → S3")
    ap.add_argument("--table", choices=ALL_NAMES, help="Export one (default: all 3)")
    ap.add_argument("--dry-run", action="store_true", help="Row counts only, no S3 write")
    args = ap.parse_args()

    selected = [args.table] if args.table else ALL_NAMES
    print(f"E11.1-W8a precursor mirror: {selected}" + ("  | DRY-RUN" if args.dry_run else ""))

    failures: list[tuple[str, str]] = []
    conn = get_snowflake_conn()
    try:
        for name in selected:
            try:
                _export(conn, name, MIRROR_TABLES[name], args.dry_run)
            except Exception as exc:  # noqa: BLE001 — per-table isolation; continue to the rest
                print(f"  ERROR exporting {name}: {exc}")
                failures.append((name, str(exc)))
    finally:
        conn.close()

    if failures:
        print(f"\nPrecursor mirror finished with {len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)

    print(f"\nPrecursor mirror complete. {len(selected)} table(s) written.")
    if not args.dry_run:
        print("\nNext: generate_w8a_external_tables.py, refresh_w1_external_tables.py --w8a, "
              "then run_w1_lakehouse.py --w8a-only + parity_check_w8a.py.")


if __name__ == "__main__":
    main()
