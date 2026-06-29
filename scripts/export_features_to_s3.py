#!/usr/bin/env python3
"""
export_features_to_s3.py   (E11.1-W7b — feature export-mirror)
-------------------------------------------------------------
Mirror the dbt-built `feature_pregame_*` OUTPUT tables (native Snowflake, in
`baseball_data.betting_features`) to S3 lakehouse parquet so the prediction/serving
READERS — `predict_today.py` / `betting_ml/utils/data_loader.py` (the feature matrix)
and `write_serving_store.py` (4 of them) — can read them DIRECTLY via DuckDB in `--s3`
mode (E11.1-W7b), with zero Snowflake at READ time.

WHY a mirror (not a DuckDB build): W7b is PHASED. Converting the whole `feature_pregame_*`
dbt tree (~7k lines, SCD-2 + matchup joins + league baselines) to DuckDB dual-branch is the
W7b-2 effort. For W7b-1 the feature BUILD stays on Snowflake (reading the S3-backed
`lakehouse_ext` views via dbt), and THIS script copies the build's OUTPUT to S3 — a 1:1,
row-exact copy → parity is trivially clean — so the READERS go fully Snowflake-free now and
the build conversion can land later without touching the readers again.

⚠️ FRESHNESS / ORDER (the daily op wires this): run AFTER the dbt feature build and BEFORE
`predict_today.py --s3` + `write_serving_store.py --s3`, else the served matrix/blobs go stale.
This is the same freshness contract as the W6 `daily_model_predictions` mirror. INTRADAY
feature freshness is a known W7b-1 limitation (the mirror is daily-cadence) — eliminated by
the W7b-2 DuckDB build (which would write S3 directly). The 4 tables write_serving_store reads
(game/weather/public_betting/umpire) are stable intraday, so the daily mirror is sufficient
for the serving blobs; `predict_today` runs right after the morning build+mirror.

⚠️ >1 min (full-history `feature_pregame_game_features`) → operator runs it (HALT tier on the
daily path once W7B_LAKEHOUSE_S3=1).

Tables mirrored = the UNION of what predict_today/data_loader + write_serving_store read
(grep-derived from those files; keep in sync if a new feature_pregame_* read is added):

Usage:
  uv run python scripts/export_features_to_s3.py                                  # all
  uv run python scripts/export_features_to_s3.py --table feature_pregame_game_features
  uv run python scripts/export_features_to_s3.py --dry-run
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

# lakehouse_name → Snowflake fully-qualified feature table. The readers address each by its
# BARE name ({LAKEHOUSE}/<name>/data.parquet) via scripts/utils/lakehouse_read.register_views.
# This set = predict_today/data_loader reads (game/lineup/starter/sub_model_signals/
# public_betting/odds) ∪ write_serving_store reads (game/weather/public_betting/umpire).
FEATURE_TABLES = {
    "feature_pregame_game_features":          "baseball_data.betting_features.feature_pregame_game_features",
    "feature_pregame_lineup_features":        "baseball_data.betting_features.feature_pregame_lineup_features",
    "feature_pregame_starter_features":       "baseball_data.betting_features.feature_pregame_starter_features",
    "feature_pregame_weather_features":       "baseball_data.betting_features.feature_pregame_weather_features",
    "feature_pregame_public_betting_features":"baseball_data.betting_features.feature_pregame_public_betting_features",
    "feature_pregame_umpire_features":        "baseball_data.betting_features.feature_pregame_umpire_features",
    "feature_pregame_sub_model_signals":      "baseball_data.betting_features.feature_pregame_sub_model_signals",
    "feature_pregame_odds_features":          "baseball_data.betting_features.feature_pregame_odds_features",
}

# Non-dbt SERVING marts the prediction/serving READERS need from S3 but that are NOT in any
# dbt lakehouse wave (Python-written, not dbt models → no DuckDB build branch): team_elo_history
# (compute_elo output, read by write_serving_store --teams). Mirrored here so the serving --s3
# path is complete; its generator (compute_elo) is the W8+ tail.
#
# NOT mirrored: mart_bankroll_state. Bankroll now serves from DynamoDB; the Snowflake object no
# longer exists (`does not exist or not authorized`). BOTH readers already try/except it and fall
# back to mart_clv_labeled_games when it's unavailable — write_serving_store.py (~L2690) and
# performance.py /summary (~L97-118) — so the bankroll read 404s → CLV fallback IDENTICALLY in
# Snowflake and --s3 mode. Mirroring a non-existent object would only fail the export, so it's
# excluded; the readers keep their existing CLV fallback (no behavior change).
SERVING_MARTS = {
    "team_elo_history":   "baseball_data.betting.team_elo_history",
}

MIRROR_TABLES = {**FEATURE_TABLES, **SERVING_MARTS}
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
        schema="betting_features",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


def _coerce_variant_cells(df: pd.DataFrame) -> pd.DataFrame:
    """json.dumps any dict/list VARIANT cell to clean VARCHAR so pyarrow can write it
    (mirrors export_w6_raw_to_s3._coerce_variant_cells)."""
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
    # AWS_ACCESS_KEY_ID is UNSET in the env. Passing aws_access_key_id=None to boto3 DISABLES
    # its default credential chain → "AuthorizationHeaderMalformed: a non-empty Access Key
    # (AKID) must be provided" (the 2026-06-29 W7b-parallel mirror failure). So pass explicit
    # keys ONLY when both are present (local/static-cred dev); otherwise let boto3 resolve the
    # instance role — the same chain DuckDB COPY already uses for the W-series S3 writes.
    kwargs = {"region_name": os.environ.get("AWS_DEFAULT_REGION", "us-east-1")}
    akid, secret = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY")
    if akid and secret:
        kwargs["aws_access_key_id"] = akid
        kwargs["aws_secret_access_key"] = secret
    return boto3.client("s3", **kwargs)


def _export(conn, lakehouse_name: str, fqn: str, dry_run: bool) -> int:
    # data.parquet (single-file mart layout) — register_views globs <name>/**/*.parquet so
    # data.parquet is matched (the `**` matches zero subdirs).
    s3_key = f"baseball/lakehouse/{lakehouse_name}/data.parquet"
    print(f"\n[{lakehouse_name}] {fqn} → s3://{_S3_BUCKET}/{s3_key}")
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {fqn}")
        rows = cur.fetchall()
        # Preserve the SELECT * identifier case the dbt model produced. The Snowflake
        # DictCursor / data_loader path reads these with the SAME case (the model's
        # column names), so keep description case AS-IS (do NOT force lower) to guarantee
        # the served feature column names match the Snowflake-path matrix exactly.
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
    print(f"  uploading {tmp.stat().st_size/1e6:.1f} MB → s3://{_S3_BUCKET}/{s3_key} ...", flush=True)
    _s3().upload_file(str(tmp), _S3_BUCKET, s3_key)
    tmp.unlink(missing_ok=True)
    print(f"  done — {len(df):,} rows.")
    return len(df)


def main():
    ap = argparse.ArgumentParser(description="E11.1-W7b feature + serving-mart export-mirror → S3")
    ap.add_argument("--table", choices=ALL_NAMES, help="Export one (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="Row counts only, no S3 write")
    args = ap.parse_args()

    selected = [args.table] if args.table else ALL_NAMES
    print(f"E11.1-W7b feature mirror: {selected}" + ("  | DRY-RUN" if args.dry_run else ""))

    failures: list[tuple[str, str]] = []
    conn = get_snowflake_conn()
    try:
        for name in selected:
            try:
                _export(conn, name, MIRROR_TABLES[name], args.dry_run)
            except Exception as exc:  # noqa: BLE001 — continue to the others
                print(f"  ERROR exporting {name}: {exc}")
                failures.append((name, str(exc)))
    finally:
        conn.close()

    if failures:
        print(f"\nFeature mirror finished with {len(failures)} failure(s):")
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)

    print(f"\nFeature mirror complete. {len(selected)} table(s) written.")
    if not args.dry_run:
        print("\nReaders can now run with --s3 (predict_today.py / write_serving_store.py).")


if __name__ == "__main__":
    main()
