#!/usr/bin/env python3
"""
parity_check_w7b.py   (E11.1-W7b — prediction/serving-path read parity)
----------------------------------------------------------------------
The SAFETY GATE for the W7b multi-day parallel run. W7b adds an `--s3` read mode to the
prediction/serving path (predict_today/data_loader feature matrix, write_serving_store
served picks, the request-path last-resort) so it reads the S3 lakehouse via DuckDB instead
of Snowflake. Before the operator flips `W7B_LAKEHOUSE_S3=1` and decommissions the Snowflake
views, this script runs the KEY prediction/serving reads BOTH ways (Snowflake vs DuckDB-S3)
for a given date and confirms they are IDENTICAL within tolerance.

⚠️ The serving feature matrix is highest-stakes: a single drifted column or renamed
identifier = a wrong served pick. So `--check features` does a column-by-column, key-aligned
diff of `load_todays_features` (numeric tolerance for float engine differences; exact for
ints/strings/keys), not just a row count.

Like every prior lakehouse wave, the S3 substrate can be a FRESHNESS SUPERSET of Snowflake on
the in-flight day (or vice-versa during the transition, since the feature mirror runs after the
dbt build) — so row-count gates are `present-in-both`-scoped and value diffs run only on the
shared keys. Investigate any *value* drift on a shared key; a count delta is expected during
the mirror window and is reported, not failed.

RUN (operator — after the daily build + feature mirror have populated S3 for the date):
  uv run python scripts/parity_check_w7b.py --date 2026-06-29                 # all checks
  uv run python scripts/parity_check_w7b.py --date 2026-06-29 --check features
  uv run python scripts/parity_check_w7b.py --date 2026-06-29 --check picks
  uv run python scripts/parity_check_w7b.py --date 2026-06-29 --check predictions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from scripts.utils import lakehouse_read as lr  # noqa: E402

_FLOAT_RTOL = 1e-4   # DuckDB vs Snowflake float-engine drift band (W-series precedent)


# ── connections ───────────────────────────────────────────────────────────────
def _sf_conn():
    """Snowflake connection (reuses the data_loader keypair factory)."""
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _sf_df(conn, sql: str, params: dict | None = None) -> pd.DataFrame:
    cur = conn.cursor()
    try:
        cur.execute(sql, params) if params else cur.execute(sql)
        cols = [d[0].upper() for d in cur.description]
        rows = cur.fetchall()
    finally:
        cur.close()
    return pd.DataFrame(rows, columns=cols)


def _duck_df(conn, sql: str, params: dict | None = None) -> pd.DataFrame:
    duck_sql = lr.to_duckdb_param_sql(lr.strip_fqn(sql))
    cur = conn.execute(duck_sql, params) if params else conn.execute(duck_sql)
    df = cur.fetch_df()
    df.columns = [c.upper() for c in df.columns]
    return df


# ── generic key-aligned column diff ───────────────────────────────────────────
def _compare(sf: pd.DataFrame, s3: pd.DataFrame, keys: list[str], label: str) -> bool:
    keys = [k.upper() for k in keys]
    print(f"\n=== {label} ===")
    print(f"  rows: snowflake={len(sf):,}  s3={len(s3):,}")
    miss_cols = set(sf.columns) ^ set(s3.columns)
    if miss_cols:
        print(f"  ⚠️ COLUMN-SET MISMATCH ({len(miss_cols)}): {sorted(miss_cols)}")
    common_cols = [c for c in sf.columns if c in s3.columns]
    for k in keys:
        if k not in common_cols:
            print(f"  ❌ key {k} missing from a side — cannot align.")
            return False
    sf2 = sf[common_cols].drop_duplicates(subset=keys).set_index(keys).sort_index()
    s3b = s3[common_cols].drop_duplicates(subset=keys).set_index(keys).sort_index()
    shared = sf2.index.intersection(s3b.index)
    only_sf = len(sf2.index.difference(s3b.index))
    only_s3 = len(s3b.index.difference(sf2.index))
    print(f"  keys: shared={len(shared):,}  only_snowflake={only_sf:,}  only_s3={only_s3:,}")
    if len(shared) == 0:
        print("  ⚠️ no shared keys — nothing to value-compare (likely a freshness/mirror gap).")
        return only_sf == 0  # tolerate S3 superset; fail if Snowflake has keys S3 lacks
    a, b = sf2.loc[shared], s3b.loc[shared]
    ok = True
    val_cols = [c for c in common_cols if c not in keys]
    for c in val_cols:
        sa, sb = a[c], b[c]
        if pd.api.types.is_numeric_dtype(sa) and pd.api.types.is_numeric_dtype(sb):
            na, nb = pd.to_numeric(sa, errors="coerce"), pd.to_numeric(sb, errors="coerce")
            both_na = na.isna() & nb.isna()
            close = ((na - nb).abs() <= (_FLOAT_RTOL * nb.abs().clip(lower=1.0))) | both_na
            nbad = int((~close).sum())
        else:
            both_na = sa.isna() & sb.isna()
            eq = (sa.astype("string") == sb.astype("string")) | both_na
            nbad = int((~eq).sum())
        if nbad:
            ok = False
            print(f"  ❌ {c}: {nbad}/{len(shared)} value mismatches")
    if ok:
        print(f"  ✅ all {len(val_cols)} value columns match on {len(shared):,} shared keys "
              f"(float rtol {_FLOAT_RTOL}).")
    if only_sf:
        ok = False
        print(f"  ❌ {only_sf} key(s) present in Snowflake but MISSING from S3 — "
              "the S3 read would drop these (investigate before cutover).")
    return ok


# ── checks ────────────────────────────────────────────────────────────────────
def check_features(date: str) -> bool:
    """The serving feature matrix — load_todays_features() both ways, column-by-column."""
    import betting_ml.utils.data_loader as dl
    print(f"\n########## FEATURE MATRIX  ({date}) ##########")
    dl.set_s3_mode(False)
    sf = dl.load_todays_features(date)
    dl.set_s3_mode(True)
    s3 = dl.load_todays_features(date)
    dl.set_s3_mode(False)
    sf.columns = [str(c).upper() for c in sf.columns]
    s3.columns = [str(c).upper() for c in s3.columns]
    key = "GAME_PK" if "GAME_PK" in sf.columns else sf.columns[0]
    return _compare(sf, s3, [key], "load_todays_features (served matrix)")


def check_picks(date: str, conn_sf, conn_s3) -> bool:
    """Served picks — write_serving_store's picks/today + EV source queries both ways."""
    from scripts.write_serving_store import _PICKS_TODAY_SQL, _EV_TODAY_SQL
    lr.register_views(conn_s3, lr.referenced_tables(_PICKS_TODAY_SQL, _EV_TODAY_SQL))
    ok = True
    for sql, label, keys in (
        (_PICKS_TODAY_SQL, "picks/today (served)", ["GAME_PK", "MARKET"]),
        (_EV_TODAY_SQL, "picks/ev (served)", ["GAME_PK", "MARKET"]),
    ):
        params = {"today": date}
        sf = _sf_df(conn_sf, sql, params)
        s3 = _duck_df(conn_s3, sql, params)
        usable = [k for k in keys if k in sf.columns]
        ok &= _compare(sf, s3, usable or [sf.columns[0]], label)
    return ok


def check_predictions(date: str, conn_sf, conn_s3) -> bool:
    """daily_model_predictions (the picks source) for the date — SF vs S3 mirror."""
    sql = ("SELECT * FROM baseball_data.betting_ml.daily_model_predictions "
           "WHERE game_date = %(today)s")
    lr.register_views(conn_s3, ["daily_model_predictions"])
    sf = _sf_df(conn_sf, sql, {"today": date})
    s3 = _duck_df(conn_s3, sql, {"today": date})
    key = [k for k in ("GAME_PK", "MODEL_NAME", "TARGET") if k in sf.columns] or [sf.columns[0]]
    return _compare(sf, s3, key, "daily_model_predictions")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="Slate date YYYY-MM-DD to compare.")
    ap.add_argument("--check", choices=["all", "features", "picks", "predictions"],
                    default="all")
    args = ap.parse_args()

    results: dict[str, bool] = {}
    if args.check in ("all", "features"):
        try:
            results["features"] = check_features(args.date)
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ features check errored: {e}")
            results["features"] = False

    if args.check in ("all", "picks", "predictions"):
        conn_sf = _sf_conn()
        conn_s3 = lr.duck_connect()
        try:
            if args.check in ("all", "predictions"):
                try:
                    results["predictions"] = check_predictions(args.date, conn_sf, conn_s3)
                except Exception as e:  # noqa: BLE001
                    print(f"  ❌ predictions check errored: {e}")
                    results["predictions"] = False
            if args.check in ("all", "picks"):
                try:
                    results["picks"] = check_picks(args.date, conn_sf, conn_s3)
                except Exception as e:  # noqa: BLE001
                    print(f"  ❌ picks check errored: {e}")
                    results["picks"] = False
        finally:
            conn_sf.close()
            conn_s3.close()

    print("\n========== SUMMARY ==========")
    for name, ok in results.items():
        print(f"  {name:14s} {'✅ PARITY' if ok else '❌ MISMATCH'}")
    all_ok = all(results.values())
    print(f"\n{'✅ ALL CHECKS PASS — safe to advance the parallel run.' if all_ok else '❌ MISMATCH — do NOT cut over; investigate above.'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
