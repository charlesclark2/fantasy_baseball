#!/usr/bin/env python3
"""
export_w8b_precursors_to_s3.py   (E11.1-W8b — serving-aggregator precursor mirror)
----------------------------------------------------------------------------------
Mirror the 4 precursor tables that the W8b DuckDB branches read but which are NOT in the
W8b/W8a/prior-wave dbt build → S3 lakehouse parquet. With these in S3, the W8b serving-aggregator
wave (complex upstream + matchup models + the aggregator) builds entirely on DuckDB:

  • feature_pregame_lineup_state    (betting_features; scripts/backfill_lineup_state_scd2.py — SCD-2)
      → read by feature_pregame_lineup_features AND the 3 matchup models (the INC-17-P2 dual-source
      CTE: SCD-2 lineup_state UNION historical stg_statsapi_lineups_wide). ⚠️ The CLASS that, if it
      goes empty, NULLs 2026 slot_*_player_id → matchup/lineup features impute to constants (silent
      discrimination collapse). A full-table SELECT * mirror carries every SCD-2 version intact.
  • team_sequential_posteriors      (betting; sequential_bayes/update_team_posteriors.py — SCD-2 MERGE)
      → read by feature_pregame_game_features_raw (the Epic-16.3 pre-game team-sequential beliefs;
      a source() read). Same low-risk full-table mirror pattern as W8a player_sequential_posteriors.
  • stg_actionnetwork_public_betting (betting; dbt staging over a VARIANT raw) → read by the
      aggregator's public_betting CTE. Mirrored (not DuckDB-built) to avoid a VARIANT-flatten blind
      translation on the serving-critical path; its raw (actionnetwork.public_betting_raw) stays SF.

  ✅ E11.1-W11-FG (2026-07-04): fct_fangraphs_pitching_analytics was DROPPED from this mirror — the
     "bounded follow-up" the old note flagged is done. stg_fangraphs__zips_pitching + fct are now
     dual-branched and W4-BUILT natively in DuckDB (run_w1_lakehouse W4_PRECURSOR_MODELS), writing the
     SAME lakehouse/fct_fangraphs_pitching_analytics/data.parquet the W8b build registers. Keeping the
     mirror here would OVERWRITE that parquet daily with SF's UPPERCASE SELECT * columns ("Do NOT force
     lower" below), which would make the new lowercase-VALUE: W4 ext table read all-NULL. W8b still reads
     the same S3 location (DuckDB is case-insensitive); the parquet is now W4-sourced.

WHY a mirror (NOT a per-table DuckDB build) — same design as W8a/W9/W7b-1:
  lineup_state + team_sequential_posteriors are STATEFUL SCD-2 Python writes; re-implementing their
  accumulate semantics in DuckDB-over-S3 is the exact class that wiped W7a's rolling history. A SINGLE
  full-table SELECT * copy is accumulate-safe BY CONSTRUCTION (carries every SCD-2 version). The two
  dbt-built tables (stg_actionnetwork_public_betting, fct_fangraphs_pitching_analytics) keep their
  Snowflake build as the source of truth; this is the additive read-mirror to S3.

S3 LAYOUT: baseball/lakehouse/<name>/data.parquet (single-file mart layout). The universal
  `<name>/**/*.parquet` glob matches data.parquet; run_w1_lakehouse._register_w8a_views registers them.

S3 AUTH: the shared instance-role-safe `lakehouse_raw_writer.make_s3_client()` (the W7b-1 AKID footgun
  cure — NEVER pass aws_access_key_id=os.environ.get(...) to boto3). Lint-enforced.

Usage:
  uv run python scripts/export_w8b_precursors_to_s3.py                                 # all 4
  uv run python scripts/export_w8b_precursors_to_s3.py --table feature_pregame_lineup_state
  uv run python scripts/export_w8b_precursors_to_s3.py --dry-run                       # counts only
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
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
# Shared instance-role-safe S3 client (NO hand-rolled boto3 — the W7b-1 AKID footgun the cure lints).
try:
    from scripts.utils.lakehouse_raw_writer import make_s3_client as _s3_client
except ImportError:  # pragma: no cover — pytest pythonpath=scripts
    from utils.lakehouse_raw_writer import make_s3_client as _s3_client

load_dotenv()

_S3_BUCKET = "baseball-betting-ml-artifacts"

# lakehouse_name → Snowflake fully-qualified precursor table. (Schemas: feature_pregame_lineup_state
# is in betting_features; the other 3 default to betting — staging/marts have no +schema override.)
MIRROR_TABLES = {
    "feature_pregame_lineup_state":    "baseball_data.betting_features.feature_pregame_lineup_state",
    "team_sequential_posteriors":      "baseball_data.betting.team_sequential_posteriors",
    "stg_actionnetwork_public_betting": "baseball_data.betting.stg_actionnetwork_public_betting",
    # fct_fangraphs_pitching_analytics DROPPED (E11.1-W11-FG) — now W4-built natively in DuckDB; see docstring.
}
ALL_NAMES = sorted(MIRROR_TABLES)


def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — this
    # script's own file-path→password resolver KeyError'd on the box. Delegate to the
    # shared PATH-if-exists→inline→password resolver. Queries are fully-qualified, so
    # the default schema is immaterial. See CLAUDE.md "SNOWFLAKE MISREADS"/INC-22 landmine.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


def _coerce_variant_cells(df: pd.DataFrame) -> pd.DataFrame:
    """json.dumps any dict/list VARIANT cell to clean VARCHAR so pyarrow can write it
    (stg_actionnetwork_public_betting may carry normalized VARIANT-derived columns)."""
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
        # SELECT * = the WHOLE table (every SCD-2 version) → accumulate-safe; the W8b consumer applies
        # its own is_current / dual-source filter (lineup_state) or reads the full table (the others).
        cur.execute(f"SELECT * FROM {fqn}")
        rows = cur.fetchall()
        # Preserve the SELECT * identifier case (the DuckDB reader addresses columns by that case; the
        # matchup/lineup CTEs read lineup_state's lowercase slot_*_player_id / valid_from). Do NOT force lower.
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
    ap = argparse.ArgumentParser(description="E11.1-W8b serving-aggregator precursor export-mirror → S3")
    ap.add_argument("--table", choices=ALL_NAMES, help="Export one (default: all 4)")
    ap.add_argument("--dry-run", action="store_true", help="Row counts only, no S3 write")
    args = ap.parse_args()

    selected = [args.table] if args.table else ALL_NAMES
    print(f"E11.1-W8b precursor mirror: {selected}" + ("  | DRY-RUN" if args.dry_run else ""))

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
        print("\nNext: generate_w8b_external_tables.py, refresh_w1_external_tables.py --w8b, "
              "then run_w1_lakehouse.py --w8b-only + parity_check_w8b.py.")


if __name__ == "__main__":
    main()
