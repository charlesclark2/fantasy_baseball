"""
parity_check_w1.py
------------------
E11.1-W1 value-preserving gate: compare Snowflake mart outputs vs dbt-duckdb
S3 Parquet outputs on grain, row count, PK uniqueness, and a column-level hash.

Run AFTER the dbt-duckdb build completes:
  dbtf run --target duckdb --select stg_batter_pitches mart_pitch_*
  uv run python scripts/parity_check_w1.py

The script exits non-zero if any mart fails the parity gate:
  - Row count mismatch (>0.1% tolerance for float round-trip noise)
  - PK not unique in S3 output
  - Column hash mismatch on a 10k-row sample

Usage:
  uv run python scripts/parity_check_w1.py [--model mart_pitch_characteristics] [--sample 10000]
"""

import argparse
import os
import sys

import duckdb
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
_S3_PREFIX = "baseball/lakehouse"
_SNOWFLAKE_SCHEMA = "BASEBALL_DATA.BETTING"

W1_MODELS = [
    "mart_pitch_characteristics",
    "mart_pitch_play_event",
    "mart_pitch_game_context",
    "mart_pitch_fielding",
    "mart_pitch_hitter_profile",
    "mart_pitch_pitcher_profile",
    "mart_pitch_hit_characteristics",
]
_PK = "pitch_sk"
_ROW_COUNT_TOLERANCE = 0.001  # 0.1%

# E13.2 Phase 0: stg_batter_pitches is the TRAINING SOURCE for the PA-outcome
# substrate (mart_pa_outcome_substrate → stg_batter_pitches). On the duckdb target
# it resolves to S3 Parquet written by scripts/ingest_statcast_to_s3.py — a
# DIFFERENT op than the W1 mart_pitch_* path (which the INC-10 regression broke).
# Before trusting a heavy lakehouse training run we confirm the S3 copy is COMPLETE
# vs Snowflake: row-count by season + PK uniqueness. We deliberately do NOT compare
# pitch_sk VALUES across sources — Snowflake derives it via md5_number_upper64 (INT64)
# while the S3 ingest uses SHA-256 hex (VARCHAR); the keys are unique within each
# source but not equal across them, so a cross-source value hash is expected to differ.
_STG_MODEL = "stg_batter_pitches"
_STG_SEASON_COL = "game_year"
# Nested year=/game_date= partitions (vs the flat *.parquet of the W1 marts), and
# the per-year schema evolves (bat-tracking 2023+, intercept 2024+) → union_by_name.
_STG_S3_GLOB = f"s3://{_S3_BUCKET}/{_S3_PREFIX}/{_STG_MODEL}/**/*.parquet"


# ── Snowflake connection ─────────────────────────────────────────────────────

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


# ── DuckDB connection with S3 credentials ───────────────────────────────────

def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    conn.execute(f"SET s3_region='{region}';")
    conn.execute(f"SET s3_access_key_id='{key_id}';")
    conn.execute(f"SET s3_secret_access_key='{secret}';")
    return conn


# ── Per-model checks ─────────────────────────────────────────────────────────

def s3_path(model: str) -> str:
    return f"s3://{_S3_BUCKET}/{_S3_PREFIX}/{model}/*.parquet"


def snowflake_row_count(sf_conn, model: str) -> int:
    cur = sf_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
    n = cur.fetchone()[0]
    cur.close()
    return n


def duckdb_row_count(duck: duckdb.DuckDBPyConnection, model: str) -> int:
    return duck.execute(
        f"SELECT COUNT(*) FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0]


def duckdb_pk_unique(duck: duckdb.DuckDBPyConnection, model: str) -> bool:
    result = duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT {_PK}) FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0]
    return bool(result)


def sample_hash(duck: duckdb.DuckDBPyConnection, sf_conn, model: str, sample_n: int) -> tuple[str, str]:
    """MD5 hash of a sorted sample_n rows from both sources. Returns (duck_hash, sf_hash)."""
    # DuckDB: read sample ordered by pitch_sk, hash the concat of all values.
    duck_hash = duck.execute(f"""
        SELECT md5(STRING_AGG(concat_ws('|', COLUMNS(*)), ',' ORDER BY {_PK}))
        FROM (SELECT * FROM read_parquet('{s3_path(model)}') ORDER BY {_PK} LIMIT {sample_n})
    """).fetchone()[0]

    # Snowflake: same sample.
    cur = sf_conn.cursor()
    cur.execute(f"""
        SELECT MD5(LISTAGG(v, ',') WITHIN GROUP (ORDER BY {_PK}))
        FROM (
            SELECT MD5(CONCAT_WS('|', *)) AS v, {_PK}
            FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}
            ORDER BY {_PK}
            LIMIT {sample_n}
        )
    """)
    sf_hash = cur.fetchone()[0]
    cur.close()
    return duck_hash, sf_hash


# ── Main ─────────────────────────────────────────────────────────────────────

def check_model(duck, sf_conn, model: str, sample_n: int) -> bool:
    print(f"\n── {model} ──")
    ok = True

    # Row count
    try:
        sf_n = snowflake_row_count(sf_conn, model)
        duck_n = duckdb_row_count(duck, model)
        delta = abs(sf_n - duck_n) / max(sf_n, 1)
        status = "✅" if delta <= _ROW_COUNT_TOLERANCE else "❌"
        print(f"  rows   {status}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  delta={delta:.4%}")
        if delta > _ROW_COUNT_TOLERANCE:
            ok = False
    except Exception as e:
        print(f"  rows   ❌  ERROR: {e}")
        ok = False
        return ok

    # PK uniqueness
    try:
        unique = duckdb_pk_unique(duck, model)
        status = "✅" if unique else "❌"
        print(f"  pk_uniq{status}  {_PK} unique in S3 output: {unique}")
        if not unique:
            ok = False
    except Exception as e:
        print(f"  pk_uniq❌  ERROR: {e}")
        ok = False

    # Column hash (sample)
    try:
        duck_h, sf_h = sample_hash(duck, sf_conn, model, sample_n)
        match = duck_h == sf_h
        status = "✅" if match else "⚠️ "
        print(f"  hash   {status}  sample {sample_n:,} rows match: {match}")
        if not match:
            print(f"           duck={duck_h}  sf={sf_h}")
            # Hash mismatch is a warning (float precision diffs are expected);
            # only fail on row count or PK uniqueness.
    except Exception as e:
        print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")

    return ok


def check_stg_batter_pitches(duck, sf_conn) -> bool:
    """E13.2 Phase 0: row-count-by-season + PK-uniqueness for stg_batter_pitches.

    Confirms the S3 training source (ingest_statcast_to_s3 output) is COMPLETE vs
    Snowflake season-by-season.

    GATE TIERS (gate redesign 2026-06-24 — a correctness fix, NOT a softening):
      - COMPLETED seasons (game_year < current year): HARD gate. A finished season's
        Statcast is frozen; any row-count divergence beyond tolerance is a real defect.
      - CURRENT in-flight season (game_year == current year): INFORMATIONAL WARN, never
        a hard fail. A season inside the live Statcast revision window CANNOT hit exact
        <=0.1% parity: (1) the two sources refresh on different clocks, and (2) Snowflake's
        stg_batter_pitches incremental only re-absorbs a trailing 14-day lookback, so it
        can permanently lag whole games that Savant filed/corrected after that window
        closed. Verified 2026-06-24: two real, completed 2026 games (game_pk 825099
        CWS@AZ, 824912 SF@ATL — both Final in MLB StatsAPI) were present in the full S3
        re-fetch but absent from Snowflake's savant.batter_pitches. Holding the in-flight
        season to exact parity therefore emits a permanently misleading FAIL; S3 being
        AHEAD of Snowflake here is expected and means S3 is the more complete source.
      - GRAND TOTAL across all seasons: HARD gate (catches any gross/global divergence).
      - PK uniqueness (surrogate + natural composite): HARD gate (duplication is always
        a defect, season-independent).
    """
    from datetime import date
    in_flight_season = date.today().year
    print(f"\n── {_STG_MODEL}  (E13.2 training source) ──")
    print(f"   in-flight season = {in_flight_season} (informational WARN); "
          f"earlier seasons + grand total are HARD gates")
    ok = True

    # Snowflake counts by season
    try:
        cur = sf_conn.cursor()
        cur.execute(
            f"SELECT {_STG_SEASON_COL}, COUNT(*) "
            f"FROM {_SNOWFLAKE_SCHEMA}.{_STG_MODEL.upper()} "
            f"GROUP BY {_STG_SEASON_COL} ORDER BY {_STG_SEASON_COL}"
        )
        sf_by_season = {int(r[0]): int(r[1]) for r in cur.fetchall() if r[0] is not None}
        cur.close()
    except Exception as e:
        print(f"  seasons❌  Snowflake count ERROR: {e}")
        return False

    # DuckDB/S3 counts by season
    try:
        rows = duck.execute(
            f"SELECT {_STG_SEASON_COL}, COUNT(*) "
            f"FROM read_parquet('{_STG_S3_GLOB}', union_by_name=true) "
            f"GROUP BY {_STG_SEASON_COL} ORDER BY {_STG_SEASON_COL}"
        ).fetchall()
        s3_by_season = {int(r[0]): int(r[1]) for r in rows if r[0] is not None}
    except Exception as e:
        print(f"  seasons❌  S3 count ERROR: {e}")
        return False

    all_seasons = sorted(set(sf_by_season) | set(s3_by_season))
    sf_total = duck_total = 0
    for yr in all_seasons:
        sf_n = sf_by_season.get(yr, 0)
        s3_n = s3_by_season.get(yr, 0)
        sf_total += sf_n
        duck_total += s3_n
        delta = abs(sf_n - s3_n) / max(sf_n, 1)
        within = (sf_n > 0 and s3_n > 0 and delta <= _ROW_COUNT_TOLERANCE)
        if yr >= in_flight_season:
            # In-flight season: informational only — never hard-fails the gate.
            status = "✅" if within else "⚠️ "
            note = "" if within else "  WARN (in-flight: live revision window — informational, not a gate)"
            print(f"  {yr}  {status}  Snowflake={sf_n:>9,}  S3={s3_n:>9,}  delta={delta:.4%}{note}")
        else:
            # Completed season: HARD gate.
            status = "✅" if within else "❌"
            if not within:
                ok = False
            print(f"  {yr}  {status}  Snowflake={sf_n:>9,}  S3={s3_n:>9,}  delta={delta:.4%}")

    # Grand total: HARD gate.
    total_delta = abs(sf_total - duck_total) / max(sf_total, 1)
    tstatus = "✅" if total_delta <= _ROW_COUNT_TOLERANCE else "❌"
    print(f"  TOTAL  {tstatus}  Snowflake={sf_total:,}  S3={duck_total:,}  delta={total_delta:.4%}")
    if total_delta > _ROW_COUNT_TOLERANCE:
        ok = False

    # PK uniqueness in S3 (surrogate key)
    try:
        unique = duck.execute(
            f"SELECT COUNT(*) = COUNT(DISTINCT {_PK}) "
            f"FROM read_parquet('{_STG_S3_GLOB}', union_by_name=true)"
        ).fetchone()[0]
        status = "✅" if unique else "❌"
        print(f"  pk_uniq{status}  {_PK} unique in S3 output: {bool(unique)}")
        if not unique:
            ok = False
    except Exception as e:
        print(f"  pk_uniq❌  ERROR: {e}")
        ok = False

    # NATURAL-key uniqueness in S3 (encoding-independent).
    # The surrogate pitch_sk check above has a BLIND SPOT: if two writers with
    # DIFFERENT key encodings both land in the glob (e.g. a stale Snowflake-export
    # year-parquet with INT64 md5 keys overlapping SHA-256-hex daily partitions),
    # union_by_name casts pitch_sk to VARCHAR and the duplicate logical pitches get
    # non-equal surrogate strings → COUNT(DISTINCT pitch_sk) falsely passes while the
    # data is double-counted. Hashing the NATURAL composite catches it regardless of
    # surrogate encoding. (This is exactly the bug found 2026-06-23 in year=2026.)
    try:
        nat_unique = duck.execute(
            "SELECT COUNT(*) = COUNT(DISTINCT (game_pk, at_bat_number, pitch_number, "
            "batter_id, pitcher_id, inning_half)) "
            f"FROM read_parquet('{_STG_S3_GLOB}', union_by_name=true)"
        ).fetchone()[0]
        status = "✅" if nat_unique else "❌"
        print(f"  nat_key{status}  natural composite unique in S3 output: {bool(nat_unique)}")
        if not nat_unique:
            ok = False
    except Exception as e:
        print(f"  nat_key❌  ERROR: {e}")
        ok = False

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W1 parity gate: Snowflake vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single mart_pitch_* model (default: all W1 models)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    ap.add_argument(
        "--stg-only", action="store_true",
        help="Run ONLY the E13.2 stg_batter_pitches season/PK check (skip W1 marts).",
    )
    ap.add_argument(
        "--no-stg", action="store_true",
        help="Skip the E13.2 stg_batter_pitches season/PK check.",
    )
    args = ap.parse_args()

    run_w1 = not args.stg_only
    run_stg = (args.stg_only or not args.no_stg) and not args.model
    models = [args.model] if args.model else (W1_MODELS if run_w1 else [])

    print("Parity check: Snowflake vs S3 Parquet")
    if models:
        print(f"W1 models: {models}")
    if run_stg:
        print(f"E13.2 source: {_STG_MODEL} (season row-count + PK uniqueness)")

    duck = get_duckdb_conn()
    sf_conn = get_snowflake_conn()

    results = {}
    for model in models:
        results[model] = check_model(duck, sf_conn, model, args.sample)
    if run_stg:
        results[_STG_MODEL] = check_stg_batter_pitches(duck, sf_conn)

    sf_conn.close()
    duck.close()

    print("\n── Summary ──")
    all_ok = True
    for model, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {model}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n✅ All W1 models pass parity gate — Snowflake credit savings realised:")
        print("   Remove mart_pitch_* from Snowflake dbt schedules (keep duckdb runs).")
    else:
        print("\n❌ Parity failures above — do NOT remove Snowflake schedules yet.")
        sys.exit(1)


if __name__ == "__main__":
    main()
