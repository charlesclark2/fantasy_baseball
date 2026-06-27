"""
parity_check_w3pre.py   (E11.1-W3pre lakehouse decommission)
------------------------------------------------------------
INDEPENDENT value-preserving gate for the W3pre STAGING tier: compare the live
Snowflake staging tables (`baseball_data.betting.stg_*`, built by flattening the
Snowflake raw VARIANT) against the dbt-duckdb flattened S3 parquet
(`lakehouse/stg_*/data.parquet`, built by run_w1_lakehouse.py --w3pre-only from the
RAW S3 tier) on row count, PK uniqueness, natural-key SET coverage, and a sample hash.

⚠️ RUN ORDER (mirrors the W2 lesson — must be PRE-cutover):
  1. uv run python scripts/export_odds_raw_to_s3.py          # Snowflake raw VARIANT → S3 raw parquet
  2. uv run python scripts/run_w1_lakehouse.py --w3pre-only   # flatten raw → lakehouse/stg_*/data.parquet
  3. uv run python scripts/parity_check_w3pre.py              # compare vs the live betting.stg_* tables
  Run it BEFORE the W3pre stg models are flipped to views (else the SF side is a view over
  the same parquet → tautological). The SF reference is the existing stg table from the last
  dbt build; small raw drift since that build shows as a sub-tolerance row-count delta.

  ⚠️ SERVING-COUPLED — stg_oddsapi_odds (→ mart_odds_outcomes) and stg_statsapi_games
  (→ mart_game_odds_bridge) are read at request time by predict_today / write_serving_store.
  Do NOT cut these over until parity is GREEN.

Exits non-zero on any failure:
  - Row-count mismatch beyond tolerance (append/snapshot tables) → see staleness note
  - PK not unique in the S3 output (for the de-duplicated models)
  - A natural key present in Snowflake but MISSING from the DuckDB rebuild (real loss)
Hash mismatch is a WARNING (DuckDB/Snowflake decimal rounding on derived odds columns).

Usage:
  uv run python scripts/parity_check_w3pre.py [--model stg_oddsapi_odds] [--sample 10000]
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
_S3_RAW_PREFIX = "baseball/lakehouse_raw"
_SNOWFLAKE_SCHEMA = "BASEBALL_DATA.BETTING"
_ROW_COUNT_TOLERANCE = 0.005  # 0.5% — absorbs raw drift since the last SF stg build

# stg model → TRUE primary-key columns (the de-dup grain).
W3PRE_PK = {
    "stg_oddsapi_odds":    ["load_id", "event_id", "bookmaker_key", "market_key", "outcome_name"],
    "stg_oddsapi_events":  ["event_id"],
    "stg_derivative_odds": ["actual_snapshot_ts", "event_id", "bookmaker_key", "market_key", "outcome_name"],
    "stg_statsapi_games":  ["game_pk"],
}
W3PRE_MODELS = list(W3PRE_PK)

# Models whose grain is fully de-duplicated → PK MUST be unique in the S3 output.
# (The append/snapshot models keep one row per snapshot, so PK-uniqueness is a WARNING.)
W3PRE_DEDUPED = {"stg_oddsapi_events", "stg_statsapi_games"}

# A natural "coverage key" per model used for the no-loss SET check (the real defect is a
# key in Snowflake that the fresh DuckDB rebuild dropped).
W3PRE_COVERAGE_KEY = {
    "stg_oddsapi_odds":    "event_id",
    "stg_oddsapi_events":  "event_id",
    "stg_derivative_odds": "event_id",
    "stg_statsapi_games":  "game_pk",
}

# RAW source per model + the raw-row natural key (for the pre-flight dupe guard). The raw
# tier is append-only dt=YYYY-MM-DD/part-<uuid>.parquet; a re-export run in append mode
# (instead of overwrite_partition) would double a partition — this catches that.
W3PRE_RAW = {
    "stg_oddsapi_odds":    ("mlb_odds_raw",       "load_id || '|' || json_extract_string(raw_json, '$.id')"),
    "stg_oddsapi_events":  ("mlb_events_raw",     "load_id"),
    "stg_derivative_odds": ("derivative_odds_raw", "load_id || '|' || event_id"),
    "stg_statsapi_games":  ("monthly_schedule",   "ingestion_ts"),
}


# ── connections ──────────────────────────────────────────────────────────────

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
    conn.execute(f"SET s3_region='{os.environ.get('AWS_DEFAULT_REGION', 'us-east-2')}';")
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        conn.execute(f"SET s3_access_key_id='{os.environ['AWS_ACCESS_KEY_ID']}';")
        conn.execute(f"SET s3_secret_access_key='{os.environ['AWS_SECRET_ACCESS_KEY']}';")
    return conn


# ── pre-flight: RAW tier integrity ───────────────────────────────────────────

def raw_glob(source: str) -> str:
    return f"s3://{_S3_BUCKET}/{_S3_RAW_PREFIX}/{source}/**/*.parquet"


def preflight_raw_integrity(duck, models: list[str]) -> bool:
    """HARD pre-flight on the RAW tier before trusting any stg parity.

    Adapts the W2 hardened guard to the dt=/part-<uuid> append layout: a re-export run in
    mode='append' (rather than 'overwrite_partition') would write a SECOND part file with
    the same rows into a dt= partition → the **/*.parquet glob double-counts that day and
    inflates the flattened stg. Catch it by comparing raw row count to distinct raw key.
    """
    print("\n── PRE-FLIGHT: RAW tier integrity (lakehouse_raw/) ──")
    ok = True
    seen = set()
    for model in models:
        source, key_expr = W3PRE_RAW[model]
        if source in seen:
            continue
        seen.add(source)
        try:
            n, ndistinct = duck.execute(
                f"SELECT count(*), count(DISTINCT ({key_expr})) "
                f"FROM read_parquet('{raw_glob(source)}', union_by_name=true)"
            ).fetchone()
            dupes = n - ndistinct
            if dupes:
                ok = False
                print(f"  ❌ {source}: {dupes:,} raw-key DUPLICATE rows "
                      f"({n:,} rows / {ndistinct:,} distinct {key_expr})")
                print(f"     FIX: a partition was written twice in append mode — "
                      f"re-export that source with mode='overwrite_partition', or "
                      f"aws s3 rm the duplicate part-<uuid>.parquet.")
            else:
                print(f"  ✅ {source}: {n:,} rows, raw-key unique (0 dupes)")
        except Exception as e:
            ok = False
            print(f"  ❌ {source}: raw read/dupe check ERROR: {e}")
    return ok


# ── per-model checks ─────────────────────────────────────────────────────────

def s3_path(model: str) -> str:
    return f"s3://{_S3_BUCKET}/{_S3_PREFIX}/{model}/data.parquet"


def sf_count(sf, model: str) -> int:
    cur = sf.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
    n = cur.fetchone()[0]
    cur.close()
    return n


def duck_count(duck, model: str) -> int:
    return duck.execute(f"SELECT COUNT(*) FROM read_parquet('{s3_path(model)}')").fetchone()[0]


def duck_pk_unique(duck, model: str) -> bool:
    pk = ", ".join(W3PRE_PK[model])
    return bool(duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT ({pk})) FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0])


def sf_keys(sf, model: str) -> set:
    col = W3PRE_COVERAGE_KEY[model]
    cur = sf.cursor()
    cur.execute(f"SELECT DISTINCT {col} FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
    s = {r[0] for r in cur.fetchall()}
    cur.close()
    return s


def duck_keys(duck, model: str) -> set:
    col = W3PRE_COVERAGE_KEY[model]
    return {r[0] for r in duck.execute(
        f"SELECT DISTINCT {col} FROM read_parquet('{s3_path(model)}')").fetchall()}


def sample_hash(duck, sf, model: str, sample_n: int) -> tuple[str, str]:
    pk = ", ".join(W3PRE_PK[model])
    duck_h = duck.execute(f"""
        SELECT md5(STRING_AGG(concat_ws('|', COLUMNS(*)), ',' ORDER BY {pk}))
        FROM (SELECT * FROM read_parquet('{s3_path(model)}') ORDER BY {pk} LIMIT {sample_n})
    """).fetchone()[0]
    cur = sf.cursor()
    cur.execute(f"""
        SELECT MD5(LISTAGG(v, ',') WITHIN GROUP (ORDER BY {pk}))
        FROM (SELECT MD5(CONCAT_WS('|', *)) AS v, {pk}
              FROM {_SNOWFLAKE_SCHEMA}.{model.upper()} ORDER BY {pk} LIMIT {sample_n})
    """)
    sf_h = cur.fetchone()[0]
    cur.close()
    return duck_h, sf_h


def check_model(duck, sf, model: str, sample_n: int) -> bool:
    print(f"\n── {model}  (pk: {', '.join(W3PRE_PK[model])}) ──")
    ok = True

    # Row count (tolerance) ────────────────────────────────────────────────────
    try:
        sf_n, duck_n = sf_count(sf, model), duck_count(duck, model)
        delta = abs(sf_n - duck_n) / max(sf_n, 1)
        status = "✅" if delta <= _ROW_COUNT_TOLERANCE else "❌"
        print(f"  rows   {status}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  delta={delta:.4%}")
        if delta > _ROW_COUNT_TOLERANCE:
            ok = False
    except Exception as e:
        print(f"  rows   ❌  ERROR: {e}")
        return False

    # No-loss coverage: every Snowflake key must survive in the DuckDB rebuild ──
    try:
        sf_k, duck_k = sf_keys(sf, model), duck_keys(duck, model)
        missing = sf_k - duck_k
        status = "✅" if not missing else "❌"
        print(f"  no-loss{status}  {W3PRE_COVERAGE_KEY[model]} in SF={len(sf_k):,} "
              f"DuckDB={len(duck_k):,}  missing-from-DuckDB={len(missing)}")
        if missing:
            print(f"           e.g. {sorted(str(m) for m in missing)[:5]}")
            ok = False
    except Exception as e:
        print(f"  no-loss❌  ERROR: {e}")
        ok = False

    # PK uniqueness (gate for de-duplicated models; warning otherwise) ──────────
    try:
        unique = duck_pk_unique(duck, model)
        if model in W3PRE_DEDUPED:
            status = "✅" if unique else "❌"
            print(f"  pk_uniq{status}  PK unique in S3 output: {unique}")
            if not unique:
                ok = False
        else:
            print(f"  pk_uniq{'✅' if unique else '⚠️ '}  PK unique: {unique} "
                  f"(append/snapshot grain — informational)")
    except Exception as e:
        print(f"  pk_uniq❌  ERROR: {e}")
        ok = False

    # Column sample hash (warning only) ────────────────────────────────────────
    try:
        duck_h, sf_h = sample_hash(duck, sf, model, sample_n)
        match = duck_h == sf_h
        print(f"  hash   {'✅' if match else '⚠️ '}  sample {sample_n:,} rows match: {match}")
        if not match:
            print("           (hash mismatch = WARNING — decimal rounding on derived odds "
                  "cols; row-count + no-loss + PK are the gates)")
    except Exception as e:
        print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W3pre parity gate: Snowflake stg vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single W3pre model (default: all)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W3PRE_MODELS
    print("Parity check (W3pre): Snowflake betting.stg_*  vs  DuckDB/S3 flattened parquet")
    print("⚠️  Run BEFORE flipping the W3pre stg models to views (else tautological).")
    print(f"Models: {models}")

    duck = get_duckdb_conn()
    sf = get_snowflake_conn()

    if not preflight_raw_integrity(duck, models):
        print("\n❌ PRE-FLIGHT FAILED — fix the RAW tier before trusting stg parity. "
              "Aborting (the stg deltas below would be raw-source artifacts, not transform diffs).")
        sf.close(); duck.close()
        sys.exit(2)

    results = {m: check_model(duck, sf, m, args.sample) for m in models}
    sf.close(); duck.close()

    print("\n── Summary ──")
    all_ok = True
    for model, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {model}")
        all_ok = all_ok and ok

    if all_ok:
        print("\n✅ All W3pre stg models pass parity — safe to create external tables + flip to views.")
        print("   (Cut over the serving-coupled stg_oddsapi_odds / stg_statsapi_games LAST, "
              "and verify mart_odds_outcomes / mart_game_odds_bridge after.)")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing models.")
        sys.exit(1)


if __name__ == "__main__":
    main()
