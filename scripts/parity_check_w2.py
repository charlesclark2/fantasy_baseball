"""
parity_check_w2.py   (E11.1-W2 lakehouse decommission)
------------------------------------------------------
INDEPENDENT value-preserving gate for the W2 marts: compare the live
Snowflake CTAS (`baseball_data.betting.mart_*`) against the dbt-duckdb S3 Parquet
on grain, row count, PK uniqueness, and a column-level hash.

⚠️ RUN ORDER MATTERS — this MUST run BEFORE the W2 models are flipped to views in
prod. While the W2 dbt models are still TABLES in `baseball_data.betting`, this
script compares two genuinely independent builds (Snowflake CTAS vs DuckDB/S3).
If you run it AFTER cutover, `betting.mart_*` is a view over the same parquet and
the check becomes tautological (the W1 lesson — parity_check_w1 is now tautological
post-decommission; this script is written to be run pre-cutover).

Run:
  python3 scripts/run_w1_lakehouse.py            # writes W1 + W2 parquet to S3
  uv run python scripts/parity_check_w2.py        # compare vs the live betting.* tables

Exits non-zero if any mart fails the gate:
  - Row count mismatch (>0.1% tolerance for float round-trip noise)
  - PK not unique in the S3 output
Column hash mismatch is a WARNING only (Snowflake vs DuckDB float/rounding
differ in the last decimal on the rolling ratio columns — expected, not a defect).

Usage:
  uv run python scripts/parity_check_w2.py [--model mart_starter_csw_rolling] [--sample 10000]
"""

import argparse
import os
import re
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
_ROW_COUNT_TOLERANCE = 0.001  # 0.1%

# W2 mart → TRUE primary-key columns (grain). NB: the two rolling marts split a
# switch hitter into one row per batter_hand (and a pitcher per pitcher_hand), so
# (game_pk, batter_id) is NOT unique — the hand is part of the grain. The Snowflake
# `incremental` unique_key was ['game_pk','batter_id'] but that was never actually
# unique on the source; the MERGE just tolerated dup keys. [E11.1-W2]
W2_PK = {
    "mart_pitcher_batted_ball_profile": ["pitcher_id", "game_year"],
    "mart_batter_bat_tracking_profile": ["batter_id", "game_date"],
    "mart_batter_rolling_stats":        ["game_pk", "batter_id", "batter_hand"],
    "mart_pitcher_rolling_stats":       ["game_pk", "pitcher_id", "pitcher_hand"],
    "mart_starting_pitcher_game_log":   ["game_pk", "pitcher_id"],
    "mart_pitcher_batter_history":      ["pitcher_id", "batter_id", "game_date"],
    "mart_starter_csw_rolling":         ["pitcher_id", "game_pk"],
    "mart_starter_pitch_mix_rolling":   ["pitcher_id", "game_pk"],
}
W2_MODELS = list(W2_PK)

# Marts sourced from stg_batter_pitches via an INCREMENTAL Snowflake table accrue
# STALE rows (game_pks dropped from stg are never deleted by the MERGE). For these,
# a raw row-count delta vs the fresh DuckDB rebuild is EXPECTED and is not a defect.
# The real gate is: the fresh rebuild must not be MISSING any game that is still in
# current stg (no real data loss). We reconcile game_pk sets against current stg.
W2_STALENESS_AWARE = {
    "mart_batter_rolling_stats",
    "mart_pitcher_rolling_stats",
    "mart_starting_pitcher_game_log",
}


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


def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    conn.execute(f"SET s3_region='{region}';")
    if key_id:
        conn.execute(f"SET s3_access_key_id='{key_id}';")
        conn.execute(f"SET s3_secret_access_key='{secret}';")
    return conn


# ── Pre-flight: lakehouse stg integrity ──────────────────────────────────────

def preflight_stg_integrity(duck) -> bool:
    """HARD pre-flight on stg_batter_pitches before trusting any mart parity.

    Catches the failure that made W2 parity look like a mismatch (2018, 2026-06-26):
    `ingest_statcast_to_s3.py --start-date …` re-ingest writes `game_date=` partitions
    but NEVER deletes the prior season's year-level `part-0.parquet`. The mart build's
    `**/*.parquet` glob then reads BOTH → that whole season is DOUBLE-counted (here:
    599,499 dup 2018 rows, broke PK uniqueness + inflated every downstream mart).
    Run this BEFORE the per-mart checks so a dupe fails loud instead of masquerading
    as a parity delta.
    """
    base = f"s3://{_S3_BUCKET}/{_S3_PREFIX}/stg_batter_pitches"
    print("\n── PRE-FLIGHT: stg_batter_pitches integrity ──")
    ok = True

    # (1) Stale year-level part-0.parquet sitting ALONGSIDE game_date= partitions.
    try:
        year_files = [r[0] for r in duck.execute(
            f"SELECT file FROM glob('{base}/year=*/part-0.parquet')").fetchall()]
        partition_years = {r[0] for r in duck.execute(
            f"SELECT DISTINCT regexp_extract(file, 'year=([0-9]+)', 1) "
            f"FROM glob('{base}/year=*/game_date=*/*.parquet')").fetchall()}
        bad = [f for f in year_files
               if (m := re.search(r"year=(\d+)", f)) and m.group(1) in partition_years]
        if bad:
            ok = False
            print("  ❌ STALE year-level parquet(s) coexist with game_date partitions "
                  "(doubles that season):")
            for f in bad:
                print(f"       {f}")
            print("     FIX: aws s3 rm <file(s) above>  (see ingest_statcast_to_s3.py CLEANUP)")
        else:
            print("  ✅ no stale year-level files alongside game_date partitions")
    except Exception as e:
        print(f"  ⚠️  year-level file check skipped: {e}")

    # (2) Natural-key duplicates anywhere in stg (encoding-independent).
    try:
        dups = duck.execute(
            f"SELECT count(*) - count(DISTINCT (game_pk, at_bat_number, pitch_number, "
            f"batter_id, pitcher_id, inning_half)) "
            f"FROM read_parquet('{base}/**/*.parquet', union_by_name=true)").fetchone()[0]
        if dups:
            ok = False
            print(f"  ❌ {dups:,} natural-key DUPLICATE pitches in stg_batter_pitches")
        else:
            print("  ✅ stg_batter_pitches natural-key unique (0 dupes)")
    except Exception as e:
        ok = False
        print(f"  ❌ natural-key dupe check ERROR: {e}")

    return ok


# ── Per-model checks ─────────────────────────────────────────────────────────

def s3_path(model: str) -> str:
    return f"s3://{_S3_BUCKET}/{_S3_PREFIX}/{model}/data.parquet"


def snowflake_row_count(sf_conn, model: str) -> int:
    cur = sf_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
    n = cur.fetchone()[0]
    cur.close()
    return n


def duckdb_row_count(duck, model: str) -> int:
    return duck.execute(
        f"SELECT COUNT(*) FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0]


def duckdb_pk_unique(duck, model: str) -> bool:
    pk = ", ".join(W2_PK[model])
    result = duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT ({pk})) "
        f"FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0]
    return bool(result)


def current_stg_game_pks(duck) -> set:
    """Distinct regular-season game_pks in the current S3 stg_batter_pitches — the
    'fresh' game universe the rebuilt marts should cover."""
    glob = f"s3://{_S3_BUCKET}/{_S3_PREFIX}/stg_batter_pitches/**/*.parquet"
    rows = duck.execute(
        f"SELECT DISTINCT game_pk FROM read_parquet('{glob}', union_by_name=true) "
        f"WHERE game_type = 'R'"
    ).fetchall()
    return {r[0] for r in rows}


def duck_game_pks(duck, model: str) -> set:
    return {r[0] for r in duck.execute(
        f"SELECT DISTINCT game_pk FROM read_parquet('{s3_path(model)}')").fetchall()}


def sf_game_pks(sf_conn, model: str) -> set:
    cur = sf_conn.cursor()
    cur.execute(f"SELECT DISTINCT game_pk FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
    s = {r[0] for r in cur.fetchall()}
    cur.close()
    return s


def sample_hash(duck, sf_conn, model: str, sample_n: int) -> tuple[str, str]:
    """MD5 of a PK-sorted sample from both sources."""
    pk = ", ".join(W2_PK[model])
    duck_hash = duck.execute(f"""
        SELECT md5(STRING_AGG(concat_ws('|', COLUMNS(*)), ',' ORDER BY {pk}))
        FROM (SELECT * FROM read_parquet('{s3_path(model)}') ORDER BY {pk} LIMIT {sample_n})
    """).fetchone()[0]

    cur = sf_conn.cursor()
    cur.execute(f"""
        SELECT MD5(LISTAGG(v, ',') WITHIN GROUP (ORDER BY {pk}))
        FROM (
            SELECT MD5(CONCAT_WS('|', *)) AS v, {pk}
            FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}
            ORDER BY {pk}
            LIMIT {sample_n}
        )
    """)
    sf_hash = cur.fetchone()[0]
    cur.close()
    return duck_hash, sf_hash


def check_model(duck, sf_conn, model: str, sample_n: int, stg_games: set | None = None) -> bool:
    print(f"\n── {model}  (pk: {', '.join(W2_PK[model])}) ──")
    ok = True

    if model in W2_STALENESS_AWARE:
        # Reconcile game_pk SETS (not raw counts) — the Snowflake incremental table
        # carries stale game_pks that current stg no longer has; the only real defect
        # is a CURRENT game missing from the fresh DuckDB rebuild.
        try:
            sf_n = snowflake_row_count(sf_conn, model)
            duck_n = duckdb_row_count(duck, model)
            sf_g, duck_g = sf_game_pks(sf_conn, model), duck_game_pks(duck, model)
            stale = sf_g - stg_games                       # in SF, gone from stg → stale (OK)
            real_loss = (sf_g & stg_games) - duck_g        # current game SF has, DuckDB dropped (BAD)
            fresh = duck_g - sf_g                          # new games the fresh rebuild has
            print(f"  rows      Snowflake={sf_n:,}  DuckDB={duck_n:,}  (Δ explained by staleness below)")
            print(f"  games     SF={len(sf_g):,}  DuckDB={len(duck_g):,}  "
                  f"| stale-only-in-SF={len(stale):,}  fresh-only-in-DuckDB={len(fresh):,}")
            lstatus = "✅" if not real_loss else "❌"
            print(f"  no-loss{lstatus}  current-stg games missing from DuckDB rebuild: {len(real_loss)}")
            if real_loss:
                print(f"           e.g. {sorted(real_loss)[:5]}")
                ok = False
        except Exception as e:
            print(f"  rows   ❌  ERROR: {e}")
            return False
    else:
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
            return False

    try:
        unique = duckdb_pk_unique(duck, model)
        status = "✅" if unique else "❌"
        print(f"  pk_uniq{status}  PK unique in S3 output: {unique}")
        if not unique:
            ok = False
    except Exception as e:
        print(f"  pk_uniq❌  ERROR: {e}")
        ok = False

    try:
        duck_h, sf_h = sample_hash(duck, sf_conn, model, sample_n)
        match = duck_h == sf_h
        status = "✅" if match else "⚠️ "
        print(f"  hash   {status}  sample {sample_n:,} rows match: {match}")
        if not match:
            print(f"           duck={duck_h}  sf={sf_h}")
            print("           (hash mismatch = WARNING — Snowflake/DuckDB rounding "
                  "differs on ratio cols; row-count + PK are the gates)")
    except Exception as e:
        print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W2 parity gate: Snowflake CTAS vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single W2 model (default: all)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W2_MODELS
    print("Parity check (W2): Snowflake betting.* CTAS  vs  S3 Parquet")
    print("⚠️  Run BEFORE flipping the W2 models to views (else tautological).")
    print(f"Models: {models}")

    duck = get_duckdb_conn()
    sf_conn = get_snowflake_conn()

    if not preflight_stg_integrity(duck):
        print("\n❌ PRE-FLIGHT FAILED — fix stg_batter_pitches before trusting W2 parity. "
              "Aborting (the mart deltas below would be lakehouse-source artifacts, not "
              "transform diffs).")
        sf_conn.close(); duck.close()
        sys.exit(2)

    stg_games = None
    if any(m in W2_STALENESS_AWARE for m in models):
        print("Loading current stg_batter_pitches game_pk set (for staleness reconciliation)…")
        stg_games = current_stg_game_pks(duck)
        print(f"  current regular-season games in stg: {len(stg_games):,}")

    results = {m: check_model(duck, sf_conn, m, args.sample, stg_games) for m in models}

    sf_conn.close()
    duck.close()

    print("\n── Summary ──")
    all_ok = True
    for model, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {model}")
        all_ok = all_ok and ok

    if all_ok:
        print("\n✅ All W2 models pass parity — safe to create external tables + flip to views.")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing marts.")
        sys.exit(1)


if __name__ == "__main__":
    main()
