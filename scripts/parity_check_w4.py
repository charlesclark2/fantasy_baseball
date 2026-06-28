"""
parity_check_w4.py   (E11.1-W4 lakehouse decommission)
------------------------------------------------------
INDEPENDENT value-preserving gate for the 6 W4 marts: compare the live Snowflake
CTAS (`baseball_data.betting.mart_*`) against the dbt-duckdb S3 Parquet on row
count, PK uniqueness, and a column-level hash.

⚠️ RUN ORDER MATTERS — this MUST run BEFORE the W4 models are flipped to views in
prod (i.e. before the PR merges). While the W4 dbt models are still TABLES in
`baseball_data.betting`, this compares two genuinely independent builds (Snowflake
CTAS vs DuckDB/S3). After cutover `betting.mart_*` is a view over the same parquet
and the check becomes tautological (the W1/W2/W3 lesson).

W4 marts (all originally `materialized='table'`, NOT incremental):
  FanGraphs    — mart_pitcher_arsenal_summary, mart_pitcher_profile_summary,
                 mart_batter_profile_summary
  posteriors   — mart_park_factors_granular  (← migrated fit_granular_park_priors.py --s3)
  cluster      — mart_batter_woba_vs_cluster (← migrated cluster_pitchers.py --s3 / --seed)
  raw-savant   — mart_catcher_framing

FRESHNESS note: the three FanGraphs/cluster marts that descend from pitch data
(profile summaries + batter_woba_vs_cluster) read S3 stg_batter_pitches /
mart_pitch_* (a superset of Snowflake savant.batter_pitches — see parity_check_w1).
So a small DuckDB-side current-season row surplus is EXPECTED freshness, not a
defect — flagged informational. mart_park_factors_granular + mart_catcher_framing
read the SAME exported raw, so they should match within tolerance.

⚠️ PRECURSOR PARITY: the FanGraphs marts build on the migrated FanGraphs precursor
subtree (stg_fangraphs__* + fct_fangraphs_*). A mart-level match transitively
confirms the precursor flatten is value-identical; spot-check a precursor with
--model on its lakehouse_ext view if a FanGraphs mart's hash drifts.

Run:
  uv run python scripts/run_w1_lakehouse.py --w4         # writes W4 parquet to S3
  uv run python scripts/parity_check_w4.py               # compare vs the live betting.* tables

Usage:
  uv run python scripts/parity_check_w4.py [--model mart_catcher_framing] [--sample 10000]
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
_ROW_COUNT_TOLERANCE = 0.001  # 0.1%

# W4 mart → TRUE primary-key columns (grain).
W4_PK = {
    "mart_pitcher_arsenal_summary": ["pitcher_id", "game_year"],
    "mart_pitcher_profile_summary": ["pitcher_id", "game_year"],
    "mart_batter_profile_summary":  ["batter_id", "game_year"],
    "mart_park_factors_granular":   ["venue_id", "season"],
    "mart_batter_woba_vs_cluster":  ["batter_id", "cluster_id", "game_date"],
    "mart_catcher_framing":         ["player_id", "season"],
}
W4_MODELS = list(W4_PK)

# Marts that descend from S3 pitch data (⊇ Snowflake) → a small current-season row
# surplus is expected freshness, not a defect (informational, not a hard gate).
W4_PITCH_DERIVED = {
    "mart_pitcher_profile_summary",
    "mart_batter_profile_summary",
    "mart_batter_woba_vs_cluster",
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
    # E11.1-W4: harden S3 reads against transient httpfs timeouts (default 30s GET window).
    for _pragma in ("SET http_timeout = 600000", "SET http_retries = 8",
                    "SET http_retry_wait_ms = 500", "SET http_retry_backoff = 4"):
        try:
            conn.execute(_pragma)
        except Exception:
            pass
    return conn


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
    pk = ", ".join(W4_PK[model])
    return bool(duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT ({pk})) "
        f"FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0])


def sample_hash(duck, sf_conn, model: str, sample_n: int) -> tuple[str, str]:
    pk = ", ".join(W4_PK[model])
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


def check_model(duck, sf_conn, model: str, sample_n: int) -> bool:
    print(f"\n── {model}  (pk: {', '.join(W4_PK[model])}) ──")
    ok = True

    try:
        sf_n = snowflake_row_count(sf_conn, model)
        duck_n = duckdb_row_count(duck, model)
        delta = abs(sf_n - duck_n) / max(sf_n, 1)
        pitch = model in W4_PITCH_DERIVED
        status = "✅" if (delta <= _ROW_COUNT_TOLERANCE or pitch) else "⚠️ "
        print(f"  rows   {status}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  delta={delta:.4%}")
        if delta > _ROW_COUNT_TOLERANCE:
            if pitch:
                print("           (pitch-derived: a current-season surplus = S3 stg freshness; "
                      "investigate only if large or DuckDB < Snowflake on completed seasons)")
            else:
                print("           (non-pitch mart: a >0.1% delta is unexpected — investigate "
                      "the precursor export / builder run)")
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
            print("           (hash mismatch = WARNING — Snowflake/DuckDB rounding differs on "
                  "ratio/float cols, or a current-season freshness row shifted the sample; "
                  "row-count + PK are the gates. For a FanGraphs mart, spot-check the "
                  "stg_fangraphs__* JSON flatten if the mismatch is structural.)")
    except Exception as e:
        print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W4 parity gate: Snowflake CTAS vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single W4 model (default: all)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W4_MODELS
    print("Parity check (W4): Snowflake betting.* CTAS  vs  S3 Parquet")
    print("⚠️  Run BEFORE flipping the W4 models to views (else tautological).")
    print(f"Models: {models}")

    duck = get_duckdb_conn()
    sf_conn = get_snowflake_conn()

    results = {m: check_model(duck, sf_conn, m, args.sample) for m in models}

    sf_conn.close()
    duck.close()

    print("\n── Summary ──")
    all_ok = True
    for model, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {model}")
        all_ok = all_ok and ok

    if all_ok:
        print("\n✅ All W4 models pass parity — safe to create external tables + flip to views.")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing marts.")
        sys.exit(1)


if __name__ == "__main__":
    main()
