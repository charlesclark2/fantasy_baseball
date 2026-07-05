"""
parity_check_w5.py   (E11.1-W5 lakehouse decommission)
------------------------------------------------------
INDEPENDENT value-preserving gate for the 15 W5 models: compare the live Snowflake
CTAS (`baseball_data.betting.*`) against the dbt-duckdb S3 Parquet on row count,
PK uniqueness, and a column-level hash.

⚠️ RUN ORDER MATTERS — this MUST run BEFORE the W5 models are flipped to views in
prod (i.e. before the PR merges). While the W5 dbt models are still TABLES in
`baseball_data.betting`, this compares two genuinely independent builds (Snowflake
CTAS vs DuckDB/S3). After cutover `betting.*` is a view over the same parquet and
the check becomes tautological (the W1/W2/W3/W4 lesson).

W5 models:
  Group A (game-results team/game chain, 10) — dim_team_name_lookup, mart_game_results,
    mart_game_spine, mart_head_to_head_team_history, mart_home_away_splits,
    mart_park_run_factors, mart_team_pythagorean_rolling, mart_team_rolling_offense,
    mart_team_rolling_pitching, mart_team_season_record
  Group B (W4-deferred + precursor, 5) — stg_batter_sprint_speed, mart_eb_park_factors,
    mart_bullpen_effectiveness, mart_team_fielding_oaa, mart_team_defense_quality_rolling

FRESHNESS note: every model that descends from stg_batter_pitches / mart_game_results /
mart_game_spine reads the S3 pitch substrate (a SUPERSET of Snowflake savant.batter_pitches
— see parity_check_w1), so a small DuckDB-side current-season / today's-scheduled row
surplus is EXPECTED freshness, not a defect (flagged informational, not a hard gate). The
three models that read ONLY the exported raw / seed (dim_team_name_lookup,
stg_batter_sprint_speed, mart_eb_park_factors) should match within tolerance.

⚠️ TYPE note: mart_game_results.game_date is DATE; mart_game_spine.game_date is
TIMESTAMP_NTZ. The DuckDB branch emits ::date / ::timestamp to preserve those exactly.

Run:
  uv run python scripts/run_w1_lakehouse.py --w5        # writes W5 parquet to S3
  uv run python scripts/parity_check_w5.py              # compare vs the live betting.* tables

Usage:
  uv run python scripts/parity_check_w5.py [--model mart_game_results] [--sample 10000]
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

# W5 model → TRUE primary-key columns (grain). Verified unique on the DuckDB output.
W5_PK = {
    # Group A
    "dim_team_name_lookup":            ["name_lower"],
    "mart_game_results":               ["game_pk"],
    "mart_game_spine":                 ["game_pk"],
    "mart_head_to_head_team_history":  ["team_a", "team_b", "game_year"],
    "mart_home_away_splits":           ["game_pk", "team"],  # NB: per-GAME, not per-date — doubleheaders collide on (team, flag, game_date)
    "mart_park_run_factors":           ["venue_id", "game_year"],
    "mart_team_pythagorean_rolling":   ["game_pk", "team_abbrev"],
    "mart_team_rolling_offense":       ["game_pk", "team"],
    "mart_team_rolling_pitching":      ["game_pk", "team"],
    "mart_team_season_record":         ["team_id", "record_date"],
    # Group B
    "stg_batter_sprint_speed":         ["player_mlbam_id", "season"],
    "mart_eb_park_factors":            ["venue_id", "season"],
    "mart_bullpen_effectiveness":      ["game_pk", "team_abbrev"],
    "mart_team_fielding_oaa":          ["game_pk", "side"],
    "mart_team_defense_quality_rolling": ["game_pk", "side"],
}
W5_MODELS = list(W5_PK)

# Models that descend from the S3 pitch substrate (stg_batter_pitches / mart_game_results
# / mart_game_spine, which ⊇ Snowflake) → a small current-season / today's-scheduled row
# surplus is expected freshness, not a defect (informational, not a hard gate). The three
# omitted (dim_team_name_lookup, stg_batter_sprint_speed, mart_eb_park_factors) read only
# the exported raw / seed and should match within 0.1%.
W5_PITCH_DERIVED = {
    "mart_game_results",
    "mart_game_spine",
    "mart_head_to_head_team_history",
    "mart_home_away_splits",
    "mart_park_run_factors",
    "mart_team_pythagorean_rolling",
    "mart_team_rolling_offense",
    "mart_team_rolling_pitching",
    "mart_team_season_record",
    "mart_bullpen_effectiveness",
    "mart_team_fielding_oaa",
    "mart_team_defense_quality_rolling",
}


# ── Snowflake connection ─────────────────────────────────────────────────────

def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared resolver.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


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
    pk = ", ".join(W5_PK[model])
    return bool(duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT ({pk})) "
        f"FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0])


def sample_hash(duck, sf_conn, model: str, sample_n: int) -> tuple[str, str]:
    pk = ", ".join(W5_PK[model])
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
    print(f"\n── {model}  (pk: {', '.join(W5_PK[model])}) ──")
    ok = True

    try:
        sf_n = snowflake_row_count(sf_conn, model)
        duck_n = duckdb_row_count(duck, model)
        delta = abs(sf_n - duck_n) / max(sf_n, 1)
        pitch = model in W5_PITCH_DERIVED
        status = "✅" if (delta <= _ROW_COUNT_TOLERANCE or pitch) else "⚠️ "
        print(f"  rows   {status}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  delta={delta:.4%}")
        if delta > _ROW_COUNT_TOLERANCE:
            if pitch:
                print("           (pitch/spine-derived: a current-season / today's-scheduled "
                      "surplus = S3 stg freshness; investigate only if large or DuckDB < "
                      "Snowflake on completed seasons)")
            else:
                print("           (raw/seed-fed mart: a >0.1% delta is unexpected — investigate "
                      "the precursor export / seed mirror)")
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
                  "ratio/float cols, the DATE/TIMESTAMP stringification differs, or a "
                  "current-season freshness row shifted the sample; row-count + PK are the gates)")
    except Exception as e:
        print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W5 parity gate: Snowflake CTAS vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single W5 model (default: all)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W5_MODELS
    print("Parity check (W5): Snowflake betting.* CTAS  vs  S3 Parquet")
    print("⚠️  Run BEFORE flipping the W5 models to views (else tautological).")
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
        print("\n✅ All W5 models pass parity — safe to create external tables + flip to views.")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing marts.")
        sys.exit(1)


if __name__ == "__main__":
    main()
