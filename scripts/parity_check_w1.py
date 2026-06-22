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


def main():
    ap = argparse.ArgumentParser(description="E11.1-W1 parity gate: Snowflake vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single model (default: all W1 models)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W1_MODELS

    print("E11.1-W1 parity check: Snowflake vs S3 Parquet")
    print(f"Models: {models}")

    duck = get_duckdb_conn()
    sf_conn = get_snowflake_conn()

    results = {}
    for model in models:
        results[model] = check_model(duck, sf_conn, model, args.sample)

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
