#!/usr/bin/env python3
"""
export_w9_signals_to_s3.py   (E11.1-W9 — sub-model SIGNAL-STORE export-mirror)
-----------------------------------------------------------------------------
Mirror the 5 sub-model SIGNAL OUTPUT tables (the stores the 7 generators write)
from native Snowflake → S3 lakehouse parquet, so the W8 feature-layer consumer
(`feature_pregame_sub_model_signals`) — and any future Snowflake-side reader via the
`lakehouse_ext` external tables — can read the signal path from S3 with zero Snowflake.

WHY a mirror (NOT a per-generator DuckDB write) — the #1 W9 risk, avoided by design:
  The 7 generators write to two store shapes:
    • SCD-2 store `mart_sub_model_signals` (ACCUMULATE — valid_from/valid_to/is_current
      history; 4 generators: run_env, bullpen, env_state, defense_quality, + matchup)
    • MERGE-by-grain `betting_features` tables (offense_v2_signals, starter_suppression_
      signals, starter_ip_signals; one row per (game_pk, side) overwritten in place, but
      ACCUMULATING game-sides across daily runs).
  Re-implementing those write/accumulate semantics in DuckDB-over-S3 per generator is the
  exact class that wiped the rolling posterior history in W7a (a `--mode today` snapshot
  full-replaced the season → leakage guard found nothing). A SINGLE full-table copy of each
  store is accumulate-safe BY CONSTRUCTION: it carries every historical SCD-2 version and
  every accumulated game-side, so "history intact" is guaranteed, not re-derived. The
  Snowflake SCD-2 / MERGE write stays the live (correct) accumulate path during the W9
  window — this script is the ADDITIVE dual-write to S3 (same staging as W7b-1's feature
  mirror: keep the stateful Snowflake write, copy its OUTPUT to S3, retire the read later).

ACCUMULATE / PARITY (DO #3): the real-run check is row-count + is_current/closed-row parity
  per table (scripts/parity_check_w9_signals.py). A full-table mirror cannot truncate the
  SCD-2 history because it SELECTs every row (current AND closed); the parity check proves it.

S3 LAYOUT: baseball/lakehouse/<name>/data.parquet (single-file mart layout). The universal
  `<name>/**/*.parquet` glob (scripts/utils/lakehouse_read.register_views) matches data.parquet,
  and generate_w9_external_tables.py DESCRIBEs the same parquet to emit the lakehouse_ext DDL.

S3 AUTH: the shared instance-role-safe `lakehouse_raw_writer.make_s3_client()` (the W7b-1 AKID
  footgun cure — NEVER pass aws_access_key_id=os.environ.get(...) to boto3; the credential chain
  resolves the EC2 instance role / env static creds). The boto3 credential lint enforces this.

Usage:
  uv run python scripts/export_w9_signals_to_s3.py                                # all 5
  uv run python scripts/export_w9_signals_to_s3.py --table mart_sub_model_signals
  uv run python scripts/export_w9_signals_to_s3.py --dry-run                      # row counts only
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
# cure session lint-gates). `make_s3_client` is the current public name; tolerate a rename
# to `s3_client` if the cure session lands one (coordination rebase note in the handoff).
try:
    from scripts.utils.lakehouse_raw_writer import make_s3_client as _s3_client
except ImportError:  # pragma: no cover — pytest pythonpath=scripts
    try:
        from utils.lakehouse_raw_writer import make_s3_client as _s3_client
    except ImportError:
        from utils.lakehouse_raw_writer import s3_client as _s3_client  # type: ignore

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified signal-store table. These are EXACTLY the 5
# tables feature_pregame_sub_model_signals reads (source('betting','mart_sub_model_signals')
# + 4× source('betting_features', '<tbl>')). offense_v1_signals is mirrored for parity even
# though its generator is retired (the wide pivot still LEFT JOINs the historical rows).
#
#   mart_sub_model_signals      ← run_env, bullpen, env_state, defense_quality, matchup (SCD-2)
#   offense_v1_signals          ← (retired generator; historical rows only)
#   offense_v2_signals          ← offense_v2/generate_offense_signals.py (MERGE)
#   starter_suppression_signals ← starter_v1/generate_starter_signals.py (MERGE)
#   starter_ip_signals          ← starter_v1/generate_starter_ip_signals.py (MERGE)
MIRROR_TABLES = {
    "mart_sub_model_signals":      "baseball_data.betting.mart_sub_model_signals",
    "offense_v1_signals":          "baseball_data.betting_features.offense_v1_signals",
    "offense_v2_signals":          "baseball_data.betting_features.offense_v2_signals",
    "starter_suppression_signals": "baseball_data.betting_features.starter_suppression_signals",
    "starter_ip_signals":          "baseball_data.betting_features.starter_ip_signals",
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
    """json.dumps any dict/list VARIANT cell to clean VARCHAR so pyarrow can write it
    (mirrors export_features_to_s3._coerce_variant_cells)."""
    def _fix(cell):
        if isinstance(cell, (dict, list)):
            return json.dumps(cell)
        return cell
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_fix)
    return df


def _export(conn, lakehouse_name: str, fqn: str, dry_run: bool) -> int:
    # Single-file data.parquet layout — register_views globs <name>/**/*.parquet (the `**`
    # matches zero subdirs) and generate_w9_external_tables.py DESCRIBEs <name>/data.parquet.
    s3_key = f"baseball/lakehouse/{lakehouse_name}/data.parquet"
    print(f"\n[{lakehouse_name}] {fqn} → s3://{_S3_BUCKET}/{s3_key}")
    cur = conn.cursor()
    try:
        # SELECT * = the WHOLE store (current AND closed SCD-2 rows) → accumulate-safe; the
        # consumer (feature_pregame_sub_model_signals) applies its own is_current filter.
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
    ap = argparse.ArgumentParser(description="E11.1-W9 sub-model signal-store export-mirror → S3")
    ap.add_argument("--table", choices=ALL_NAMES, help="Export one (default: all 5)")
    ap.add_argument("--dry-run", action="store_true", help="Row counts only, no S3 write")
    args = ap.parse_args()

    selected = [args.table] if args.table else ALL_NAMES
    print(f"E11.1-W9 signal-store mirror: {selected}" + ("  | DRY-RUN" if args.dry_run else ""))

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
        print(f"\nSignal-store mirror finished with {len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)

    print(f"\nSignal-store mirror complete. {len(selected)} table(s) written.")
    if not args.dry_run:
        print("\nNext: refresh_w1_external_tables.py --w9, then parity_check_w9_signals.py.")


if __name__ == "__main__":
    main()
