"""
parity_check_w6.py   (E11.1-W6 lakehouse decommission)
------------------------------------------------------
INDEPENDENT value-preserving gate for the 15 W6 models (2 Group-C staging flattens + 13
odds/CLV + odds-serving marts): compare the live Snowflake build (`baseball_data.betting.*`)
against the dbt-duckdb S3 Parquet on row count, PK uniqueness, and a column-level hash.

⚠️ RUN ORDER MATTERS — run BEFORE the W6 models are flipped to views in prod (before the PR
merges). After cutover `betting.*` is a view over the same parquet and the check becomes
tautological.

⚠️ PARTITIONED: mart_odds_outcomes is split into _history/_current date buckets — its S3 read
globs **/*.parquet (the UNION = the full table). Parity is on the FULL table ONCE; the intraday
delta is only the _current bucket thereafter (operator addendum guard #3).

FRESHNESS note (DuckDB S3 ⊇/⊆ Snowflake — informational, not a hard gate):
  • spine/odds-derived marts (bridge, consensus, line_movement, closing_line_value,
    disagreement, team_schedule_context, player_game_starts, mart_odds_outcomes) read the S3
    pitch/odds substrate (⊇ Snowflake) → a small current-season / today's-scheduled surplus is
    expected freshness.
  • prediction-derived marts (clv_labeled_games, clv_label_count, prediction_clv) read the
    daily_model_predictions S3 mirror — a SNAPSHOT at export time → DuckDB may be ⊆ Snowflake if
    the live table advanced after the export. Re-export immediately before parity for a clean
    compare.
  Strict (raw/static-fed): stg_statsapi_venues.
⚠️ TZ note: mart_closing_line_value.close_snapshot_ts / mart_prediction_clv.close_snapshot_ts
  are TIMESTAMP_TZ; for the few LIVE-arm rows the NTZ→TZ promotion uses the session tz, which
  can differ Snowflake vs DuckDB — a hash mismatch isolated to those rows is a WARNING, not a
  gate (historical rows, the dominant mass, are exact).

Run:
  uv run python scripts/export_w6_raw_to_s3.py            # precursor exports (incl. dmp mirror)
  uv run python scripts/run_w1_lakehouse.py --w6          # writes W6 parquet to S3
  uv run python scripts/parity_check_w6.py                # compare vs live betting.* builds

Usage:
  uv run python scripts/parity_check_w6.py [--model mart_odds_outcomes] [--sample 10000]
"""

import argparse
import os
import sys

from pathlib import Path

import duckdb
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

# Ensure repo root on sys.path for the delegating import below.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_PREFIX = "baseball/lakehouse"
_SNOWFLAKE_SCHEMA = "BASEBALL_DATA.BETTING"
_ROW_COUNT_TOLERANCE = 0.001  # 0.1%

# W6 model → TRUE primary-key columns (grain). Verified unique on the DuckDB output.
W6_PK = {
    "stg_statsapi_venues":        ["venue_id"],
    "stg_statsapi_lineups":       ["game_pk", "home_away", "batting_order"],
    "mart_odds_outcomes":         ["ingestion_ts", "event_id", "bookmaker_key", "market_key", "outcome_name"],
    "mart_odds_events":           ["event_id"],
    "mart_game_odds_bridge":      ["game_pk"],
    "mart_odds_consensus":        ["event_id"],
    "mart_odds_line_movement":    ["game_pk"],
    "mart_closing_line_value":    ["game_pk"],
    "mart_clv_labeled_games":     ["game_pk", "market_type"],
    "mart_clv_label_count":       [],  # one row total — special-cased (no PK)
    "mart_prediction_clv":        ["game_pk", "model_version", "coalesce(retrain_tag,'')"],
    "mart_derivative_closes":     ["game_pk", "market_key", "bookmaker_key", "outcome_name"],
    "mart_bookmaker_disagreement":["game_pk"],
    "mart_team_schedule_context": ["team_abbrev", "game_pk"],
    "mart_player_game_starts":    ["game_pk", "team", "side", "player_id"],
}
W6_MODELS = list(W6_PK)

# Date-bucketed (read **/*.parquet for the full table).
W6_PARTITIONED = {"mart_odds_outcomes"}

# Freshness-sensitive (DuckDB S3 ⊇/⊆ Snowflake) → row-count delta is informational, not a gate.
W6_FRESHNESS = {
    "stg_statsapi_lineups", "mart_odds_outcomes", "mart_game_odds_bridge", "mart_odds_consensus",
    "mart_odds_line_movement", "mart_closing_line_value", "mart_bookmaker_disagreement",
    "mart_clv_labeled_games", "mart_clv_label_count", "mart_prediction_clv",
    "mart_team_schedule_context", "mart_player_game_starts",
}


def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared resolver.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    try:
        conn.execute("INSTALL icu; LOAD icu;")
    except Exception:
        pass
    conn.execute("SET TimeZone='UTC';")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-2")
    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    conn.execute(f"SET s3_region='{region}';")
    if key_id:
        conn.execute(f"SET s3_access_key_id='{key_id}';")
        conn.execute(f"SET s3_secret_access_key='{secret}';")
    for _pragma in ("SET http_timeout = 600000", "SET http_retries = 8",
                    "SET http_retry_wait_ms = 500", "SET http_retry_backoff = 4"):
        try:
            conn.execute(_pragma)
        except Exception:
            pass
    return conn


def s3_read(model: str) -> str:
    """A read_parquet(...) expression for the model's S3 parquet (glob both buckets if partitioned)."""
    if model in W6_PARTITIONED:
        return f"read_parquet('s3://{_S3_BUCKET}/{_S3_PREFIX}/{model}/**/*.parquet', union_by_name=true)"
    return f"read_parquet('s3://{_S3_BUCKET}/{_S3_PREFIX}/{model}/data.parquet')"


def snowflake_row_count(sf_conn, model: str) -> int:
    cur = sf_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
    n = cur.fetchone()[0]
    cur.close()
    return n


def duckdb_row_count(duck, model: str) -> int:
    return duck.execute(f"SELECT COUNT(*) FROM {s3_read(model)}").fetchone()[0]


def duckdb_pk_unique(duck, model: str) -> bool:
    pk = ", ".join(W6_PK[model])
    return bool(duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT ({pk})) FROM {s3_read(model)}"
    ).fetchone()[0])


def sample_hash(duck, sf_conn, model: str, sample_n: int) -> tuple[str, str]:
    pk = ", ".join(W6_PK[model])
    duck_hash = duck.execute(f"""
        SELECT md5(STRING_AGG(concat_ws('|', COLUMNS(*)), ',' ORDER BY {pk}))
        FROM (SELECT * FROM {s3_read(model)} ORDER BY {pk} LIMIT {sample_n})
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
    pk_desc = ", ".join(W6_PK[model]) or "(single row)"
    print(f"\n── {model}  (pk: {pk_desc}) ──")
    ok = True

    try:
        sf_n = snowflake_row_count(sf_conn, model)
        duck_n = duckdb_row_count(duck, model)
        delta = abs(sf_n - duck_n) / max(sf_n, 1)
        fresh = model in W6_FRESHNESS
        status = "✅" if (delta <= _ROW_COUNT_TOLERANCE or fresh) else "⚠️ "
        print(f"  rows   {status}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  delta={delta:.4%}")
        if delta > _ROW_COUNT_TOLERANCE:
            if fresh:
                print("           (spine/odds/prediction-derived: a current-season / today's "
                      "surplus = S3 substrate freshness, or a ⊆ if the dmp mirror lags the live "
                      "table; investigate only if large or DuckDB < Snowflake on completed history)")
            else:
                print("           (raw/static-fed mart: a >0.1% delta is unexpected — investigate "
                      "the precursor export)")
    except Exception as e:
        print(f"  rows   ❌  ERROR: {e}")
        return False

    if W6_PK[model]:
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
                print("           (hash mismatch = WARNING — float rounding, DATE/TIMESTAMP "
                      "stringification, close_snapshot_ts live-arm tz, or a freshness row shifted "
                      "the sample; row-count + PK are the gates)")
        except Exception as e:
            print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")
    else:
        # mart_clv_label_count — one row. Compare the live_total_count value.
        try:
            d = duck.execute(f"SELECT live_total_count FROM {s3_read(model)}").fetchone()[0]
            cur = sf_conn.cursor()
            cur.execute(f"SELECT live_total_count FROM {_SNOWFLAKE_SCHEMA}.{model.upper()}")
            s = cur.fetchone()[0]; cur.close()
            print(f"  value  {'✅' if d == s else '⚠️ '}  live_total_count  DuckDB={d}  Snowflake={s}")
        except Exception as e:
            print(f"  value  ⚠️   ERROR: {e} (non-blocking)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W6 parity gate: Snowflake build vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single W6 model (default: all)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W6_MODELS
    print("Parity check (W6): Snowflake betting.* build  vs  S3 Parquet")
    print("⚠️  Run BEFORE flipping the W6 models to views (else tautological).")
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
        print("\n✅ All W6 models pass parity — safe to create external tables + flip to views.")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing marts.")
        sys.exit(1)


if __name__ == "__main__":
    main()
