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
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified feature table. The readers address each by its
# BARE name ({LAKEHOUSE}/<name>/data.parquet) via scripts/utils/lakehouse_read.register_views.
#
# E11.1-W8b — W7b-1 MIRROR RETIREMENT (TRIMMED to the un-migrated tail). The W8a/W8b dual-branch
# waves now BUILD the migrated feature tables to S3 directly (run_w1_lakehouse --w8a/--w8b → the SAME
# data.parquet key), so this export-mirror is redundant for them and was removed:
#   game_features, lineup_features, starter_features  (W8b dbt-built),
#   sub_model_signals, odds_features                  (W8a dbt-built).
#
# ⛔ FULL RETIREMENT (INC-31, 2026-07-09) — umpire / weather / public_betting REMOVED.
# WHY: those three were the last-kept W11-deferred tail here, mirrored via `SELECT * FROM <sf model>`
# which PRESERVES Snowflake's UPPERCASE column case (see _export's "do NOT force lower" comment). But
# the W11b/W11c/W11d native builds (run_w1_lakehouse --w11b/c/d-only, gated ON on the box) now write
# the SAME `feature_pregame_{umpire,weather,public_betting}_features/data.parquet` key with LOWERCASE
# columns (DuckDB COPY), and the lakehouse_ext DDLs read LOWERCASE keys (GET(VALUE,'game_pk')). This
# mirror ran LATER in the daily cycle and CLOBBERED the native lowercase parquet with an UPPERCASE one
# → GET(VALUE,'game_pk') returned NULL for EVERY column (incl. game_pk) → all three served feature
# BLOCKS materialized 100% NULL on the current slate (the F2 umpire-null recurrence + weather/public-
# betting siblings). This is the exact "🔠 VALUE:<key> is CASE-SENSITIVE / SELECT*→UPPERCASE reads
# ALL-NULL" landmine. Since the native builds are the sole authoritative writer post-cutover, retiring
# them here removes the double-writer race entirely — the "Full retirement is the W11 step once those
# models migrate" this file always anticipated. (After merge+deploy, one native --w11b/c/d rebuild +
# ext refresh + a per-ROW ext-table verify repopulates them; see the INC-31 handoff.)
FEATURE_TABLES: dict[str, str] = {}

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


def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — this
    # script's own file-path→password resolver KeyError'd on the box. Delegate to the
    # shared PATH-if-exists→inline→password resolver. Queries are fully-qualified, so
    # the default schema is immaterial. See CLAUDE.md "SNOWFLAKE MISREADS"/INC-22 landmine.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting_features")


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
