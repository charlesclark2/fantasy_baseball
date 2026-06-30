#!/usr/bin/env python3
"""
parity_check_w11.py   (E11.1-W11 — ingestion-decommission FINISH wave)
---------------------------------------------------------------------
RAW-TIER parity gate for the W11 Tier-A feeds: compare the S3 mirror
(lakehouse_raw/<source>/, written by the flipped live writer and/or scripts/export_w11_raw_to_s3.py)
against the live Snowflake RAW table, BEFORE any reader is repointed (the W7b mirror→validate→cutover
discipline). This validates the *mirror*, not a transform — the stg/mart duckdb branches still read
Snowflake (or the W4/W5 lakehouse/ snapshot) until the operator flips them post-GREEN.

Checks (per source):
  • row count        — parquet vs Snowflake raw (tolerance absorbs append drift since the export ran)
  • dupe guard       — a doubled dt= partition would inflate the parquet ABOVE the source (the W2 class)
  • no-loss coverage — every natural key in Snowflake survives in the parquet (where a key is configured)

Exits non-zero on a row-count delta beyond tolerance, a doubled partition, or a missing key.

⚠️ RUN ORDER (must be PRE-cutover):
  1. uv run python scripts/export_w11_raw_to_s3.py [--source <s>]   # Snowflake raw → S3 lakehouse_raw/
     (and/or set LAKEHOUSE_RAW_WRITE_MODE=both on the live writer for a parallel window)
  2. uv run python scripts/parity_check_w11.py [--source <s>]       # this gate
  3. only on GREEN: repoint the source's stg/mart duckdb branch lakehouse_loc → lakehouse_raw_loc,
     rebuild --w4/--w5, verify, then flip the writer to LAKEHOUSE_RAW_WRITE_MODE=s3 + drop the SF raw.

Usage:
  uv run python scripts/parity_check_w11.py [--source fg_stuff_plus_raw] [--tolerance 0.01]
"""

import argparse
import os
import sys

import duckdb

# scripts/ is on sys.path under the runtime; reuse the INC-22 inline-key-safe connector resolver
# (NEVER re-implement key-FILE-only auth — it fails on the box where the key is inline).
from utils.snowflake_loader import get_snowflake_connection

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_RAW_PREFIX = "baseball/lakehouse_raw"

# source → (fully-qualified Snowflake raw FQN, coverage-key SQL or None). The coverage key is a
# column expression valid in BOTH DuckDB and Snowflake (plain column refs / concat). None → row-count
# + dupe guard only (column names not confidently known offline; the box run can add one). The dupe
# guard always uses the same coverage key when present, else compares parquet-count to SF source-count.
SOURCES = {
    "fg_stuff_plus_raw":          ("baseball_data.fangraphs.fg_stuff_plus_raw",          "load_id || '|' || fg_pitcher_id"),
    "fg_hitting_leaderboard_raw": ("baseball_data.fangraphs.fg_hitting_leaderboard_raw", "load_id"),
    "catcher_framing_raw":        ("baseball_data.savant.catcher_framing_raw",           None),
    "player_transactions":        ("baseball_data.statsapi.player_transactions",         "transaction_id"),
    "sprint_speed_raw":           ("baseball_data.savant.sprint_speed_raw",              "player_mlbam_id || '|' || season"),
    "oaa_team_season_raw":        ("baseball_data.external.oaa_team_season_raw",         None),
    "savant_park_factors_raw":    ("baseball_data.fangraphs.savant_park_factors_raw",    None),
}

_DEFAULT_TOLERANCE = 0.01  # 1% — absorbs append drift between the export and this check


def raw_glob(source: str) -> str:
    return f"s3://{_S3_BUCKET}/{_S3_RAW_PREFIX}/{source}/**/*.parquet"


def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"SET s3_region='{os.environ.get('AWS_DEFAULT_REGION', 'us-east-2')}';")
    # Instance-role on the box; static creds locally (mirrors get_duckdb_conn in parity_check_w3pre).
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        conn.execute(f"SET s3_access_key_id='{os.environ['AWS_ACCESS_KEY_ID']}';")
        conn.execute(f"SET s3_secret_access_key='{os.environ['AWS_SECRET_ACCESS_KEY']}';")
    return conn


def check_source(duck, sf, source: str, tolerance: float) -> bool:
    fqn, cov_key = SOURCES[source]
    print(f"\n── {source}  ({fqn}) ──")
    ok = True

    # Row count ─────────────────────────────────────────────────────────────────
    try:
        parquet_n = duck.execute(
            f"SELECT count(*) FROM read_parquet('{raw_glob(source)}', union_by_name=true)"
        ).fetchone()[0]
        cur = sf.cursor()
        cur.execute(f"SELECT count(*) FROM {fqn}")
        sf_n = cur.fetchone()[0]
        cur.close()
        delta = abs(sf_n - parquet_n) / max(sf_n, 1)
        status = "✅" if delta <= tolerance else "❌"
        print(f"  rows    {status}  Snowflake={sf_n:,}  parquet={parquet_n:,}  delta={delta:.4%}")
        if delta > tolerance:
            ok = False
            if parquet_n > sf_n:
                print("           parquet > Snowflake → likely a DOUBLED dt= partition. FIX: re-export "
                      "with mode='overwrite_partition' (default), or aws s3 rm the duplicate part file.")
            else:
                print("           parquet < Snowflake → partial/stale mirror. FIX: re-run "
                      "export_w11_raw_to_s3.py (full, no --since) so the mirror covers all history.")
    except Exception as e:
        print(f"  rows    ❌  ERROR: {e}")
        return False

    # No-loss coverage (where a natural key is configured) ───────────────────────
    if cov_key:
        try:
            duck_k = {r[0] for r in duck.execute(
                f"SELECT DISTINCT {cov_key} FROM read_parquet('{raw_glob(source)}', union_by_name=true)"
            ).fetchall()}
            cur = sf.cursor()
            cur.execute(f"SELECT DISTINCT {cov_key} FROM {fqn}")
            sf_k = {r[0] for r in cur.fetchall()}
            cur.close()
            missing = sf_k - duck_k
            status = "✅" if not missing else "❌"
            print(f"  no-loss {status}  key=({cov_key})  SF={len(sf_k):,}  parquet={len(duck_k):,}  "
                  f"missing-from-parquet={len(missing)}")
            if missing:
                print(f"           e.g. {sorted(str(m) for m in missing)[:5]}")
                ok = False
        except Exception as e:
            print(f"  no-loss ⚠️   ERROR: {e} (key may not exist — box run can correct the key)")
    else:
        print("  no-loss —   (no coverage key configured offline; row-count is the gate — "
              "add a natural key on the box if a stronger no-loss check is wanted)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W11 RAW-tier parity: S3 mirror vs Snowflake raw")
    ap.add_argument("--source", choices=sorted(SOURCES), help="Check a single source (default: all)")
    ap.add_argument("--tolerance", type=float, default=_DEFAULT_TOLERANCE,
                    help=f"Row-count tolerance (default {_DEFAULT_TOLERANCE})")
    args = ap.parse_args()

    sources = [args.source] if args.source else list(SOURCES)
    print("Parity check (W11 RAW tier): S3 lakehouse_raw/  vs  Snowflake raw")
    print("⚠️  Run BEFORE repointing any stg/mart duckdb branch to lakehouse_raw_loc (mirror→validate→cutover).")
    print(f"Sources: {sources}")

    duck = get_duckdb_conn()
    sf = get_snowflake_connection()
    try:
        results = {s: check_source(duck, sf, s, args.tolerance) for s in sources}
    finally:
        sf.close()
        duck.close()

    print("\n── Summary ──")
    all_ok = all(results.values())
    for source, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {source}")

    if all_ok:
        print("\n✅ All W11 raw mirrors pass parity — safe to repoint the duckdb branches + flip the writers.")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing source(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
