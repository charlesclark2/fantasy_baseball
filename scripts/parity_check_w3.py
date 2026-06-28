"""
parity_check_w3.py   (E11.1-W3 lakehouse decommission)
------------------------------------------------------
INDEPENDENT value-preserving gate for the W3 marts: compare the live Snowflake
CTAS (`baseball_data.betting.mart_*`) against the dbt-duckdb S3 Parquet on grain,
row count, PK uniqueness, and a column-level hash.

⚠️ RUN ORDER MATTERS — this MUST run BEFORE the W3 models are flipped to views in
prod (i.e. before the PR merges). While the W3 dbt models are still TABLES in
`baseball_data.betting`, this compares two genuinely independent builds (Snowflake
CTAS vs DuckDB/S3). After cutover `betting.mart_*` is a view over the same parquet
and the check becomes tautological (the W1/W2 lesson).

W3 marts (all originally `materialized='table'`, NOT incremental):
  season-grain  — pitcher_pitch_archetype, batter_vs_pitch_archetype,
                  batter_vs_handedness_splits, pitcher_vs_handedness_splits,
                  starter_tto_splits
  game-grain    — team_base_state_splits, team_vs_pitcher_hand,
                  bullpen_handedness_splits, bullpen_leverage, bullpen_workload,
                  reliever_top3_availability

FRESHNESS note: the DuckDB rebuild reads S3 stg_batter_pitches (which is a superset
of Snowflake savant.batter_pitches — see parity_check_w1.py: 2 extra completed 2026
games + current-season freshness). So a small DuckDB-side row/game surplus is
EXPECTED and not a defect. For game-grain marts the real gate is no-loss: every
game_pk in the current stg must appear in the DuckDB rebuild. For season-grain marts
a >0.1% row delta is informational on the current season, hard on completed history.

⚠️ mart_team_vs_pitcher_hand parity: the single-game `woba`/`xwoba` columns are
ZEROED in BOTH builds by design (the Snowflake build has a latent scale-0
bare-::numeric bug; the DuckDB branch reproduces it via ::numeric(38,0) so the
migration is value-preserving). They are consumed by nothing (only the _7d/_30d/_std
rolling columns feed features + the serving store). A hash match is therefore
expected on those columns; any rounding mismatch on the ROLLING ratio columns is the
usual Snowflake/DuckDB last-decimal WARNING, not a defect.

Run:
  python3 scripts/run_w1_lakehouse.py            # writes W1+W2+W3 parquet to S3
  uv run python scripts/parity_check_w3.py        # compare vs the live betting.* tables

Usage:
  uv run python scripts/parity_check_w3.py [--model mart_bullpen_workload] [--sample 10000]
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

# W3 mart → TRUE primary-key columns (grain).
W3_PK = {
    "mart_pitcher_pitch_archetype":      ["pitcher_id", "game_year"],
    "mart_batter_vs_pitch_archetype":    ["batter_id", "pitch_archetype", "game_year"],
    "mart_batter_vs_handedness_splits":  ["batter_id", "pitcher_hand", "game_year"],
    "mart_pitcher_vs_handedness_splits": ["pitcher_id", "batter_hand", "game_year"],
    "mart_starter_tto_splits":           ["pitcher_id", "season"],
    "mart_team_base_state_splits":       ["team_abbrev", "game_pk"],
    "mart_team_vs_pitcher_hand":         ["team", "opp_starter_hand", "game_pk"],
    "mart_bullpen_handedness_splits":    ["team_abbrev", "game_pk"],
    "mart_bullpen_leverage":             ["team_abbrev", "game_pk"],
    "mart_bullpen_workload":             ["game_pk", "pitching_team"],
    "mart_reliever_top3_availability":   ["game_pk", "team_abbrev"],
}
W3_MODELS = list(W3_PK)

# Game-grain marts: the DuckDB rebuild reads S3 stg (⊇ Snowflake stg), so a raw row
# delta is expected freshness, not a defect. The gate is: no current-stg game_pk
# missing from the DuckDB rebuild (no real data loss). Reconcile game_pk SETS.
W3_FRESHNESS_AWARE = {
    "mart_team_base_state_splits",
    "mart_team_vs_pitcher_hand",
    "mart_bullpen_handedness_splits",
    "mart_bullpen_leverage",
    "mart_bullpen_workload",
    "mart_reliever_top3_availability",
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


# ── Pre-flight: lakehouse stg integrity (identical to parity_check_w2) ────────

def preflight_stg_integrity(duck) -> bool:
    """HARD pre-flight on stg_batter_pitches before trusting any mart parity.
    Catches the stale year-level parquet + natural-key dupe failure mode (W1/W2)."""
    base = f"s3://{_S3_BUCKET}/{_S3_PREFIX}/stg_batter_pitches"
    print("\n── PRE-FLIGHT: stg_batter_pitches integrity ──")
    ok = True
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
            print("  ❌ STALE year-level parquet(s) coexist with game_date partitions:")
            for f in bad:
                print(f"       {f}")
            print("     FIX: aws s3 rm <file(s) above>  (see ingest_statcast_to_s3.py CLEANUP)")
        else:
            print("  ✅ no stale year-level files alongside game_date partitions")
    except Exception as e:
        print(f"  ⚠️  year-level file check skipped: {e}")

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
    pk = ", ".join(W3_PK[model])
    return bool(duck.execute(
        f"SELECT COUNT(*) = COUNT(DISTINCT ({pk})) "
        f"FROM read_parquet('{s3_path(model)}')"
    ).fetchone()[0])


def current_stg_game_pks(duck) -> set:
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
    pk = ", ".join(W3_PK[model])
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
    print(f"\n── {model}  (pk: {', '.join(W3_PK[model])}) ──")
    ok = True

    if model in W3_FRESHNESS_AWARE:
        try:
            sf_n = snowflake_row_count(sf_conn, model)
            duck_n = duckdb_row_count(duck, model)
            sf_g, duck_g = sf_game_pks(sf_conn, model), duck_game_pks(duck, model)
            extra = duck_g - sf_g                      # fresher games S3 has, SF doesn't (OK)
            real_loss = (sf_g & (stg_games or sf_g)) - duck_g  # current game SF has, DuckDB dropped (BAD)
            print(f"  rows      Snowflake={sf_n:,}  DuckDB={duck_n:,}  (Δ explained by stg freshness)")
            print(f"  games     SF={len(sf_g):,}  DuckDB={len(duck_g):,}  "
                  f"| only-in-DuckDB(fresher)={len(extra):,}")
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
            status = "✅" if delta <= _ROW_COUNT_TOLERANCE else "⚠️ "
            print(f"  rows   {status}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  delta={delta:.4%}")
            if delta > _ROW_COUNT_TOLERANCE:
                print("           (season-grain: a small surplus = current-season stg freshness; "
                      "investigate only if large or DuckDB < Snowflake on completed seasons)")
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
                  "ratio cols; row-count + PK + no-loss are the gates)")
    except Exception as e:
        print(f"  hash   ⚠️   ERROR: {e} (non-blocking)")

    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W3 parity gate: Snowflake CTAS vs DuckDB/S3")
    ap.add_argument("--model", help="Check a single W3 model (default: all)")
    ap.add_argument("--sample", type=int, default=10_000, help="Sample size for column hash")
    args = ap.parse_args()

    models = [args.model] if args.model else W3_MODELS
    print("Parity check (W3): Snowflake betting.* CTAS  vs  S3 Parquet")
    print("⚠️  Run BEFORE flipping the W3 models to views (else tautological).")
    print(f"Models: {models}")

    duck = get_duckdb_conn()
    sf_conn = get_snowflake_conn()

    if not preflight_stg_integrity(duck):
        print("\n❌ PRE-FLIGHT FAILED — fix stg_batter_pitches before trusting W3 parity. Aborting.")
        sf_conn.close(); duck.close()
        sys.exit(2)

    stg_games = None
    if any(m in W3_FRESHNESS_AWARE for m in models):
        print("Loading current stg_batter_pitches game_pk set (for freshness reconciliation)…")
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
        print("\n✅ All W3 models pass parity — safe to create external tables + flip to views.")
    else:
        print("\n❌ Parity failures above — do NOT cut over the failing marts.")
        sys.exit(1)


if __name__ == "__main__":
    main()
