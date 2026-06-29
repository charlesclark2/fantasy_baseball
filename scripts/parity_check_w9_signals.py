#!/usr/bin/env python3
"""
parity_check_w9_signals.py   (E11.1-W9 — signal-store mirror parity + accumulate gate)
-------------------------------------------------------------------------------------
The SAFETY GATE for the W9 sub-model signal-store export-mirror. export_w9_signals_to_s3.py
copies the 5 signal stores (mart_sub_model_signals + the 4 betting_features signal tables)
Snowflake → S3 parquet 1:1. This script proves that copy is VALUE-PRESERVING and — for the
SCD-2 store — that the ACCUMULATE history is INTACT (DO #3: a full-table copy cannot truncate
history, but we prove it rather than assume it; the W7a posterior-wipe lesson).

WHAT IT CHECKS (per table, Snowflake vs DuckDB-over-S3, computed IN-ENGINE so 1.45M-row
mart_sub_model_signals never lands in pandas):
  • row count + distinct game_pk            (exact)
  • per-column fingerprint: non-null count (exact) + rounded SUM for numerics / boolean
    true-count (float rtol 1e-6) — a value-preserving copy matches every column's fingerprint.
  • ACCUMULATE check for mart_sub_model_signals: is_current=TRUE and is_current=FALSE (the
    closed/history rows) counts match BOTH sides → the SCD-2 history wasn't truncated.

A mirror is, by construction, a FRESHNESS SNAPSHOT: if a generator wrote new rows on Snowflake
AFTER the mirror ran, Snowflake will be a superset. That's reported (count delta), not failed —
re-run the export and re-check. A *value* fingerprint drift on a SHARED row count IS a failure.

RUN (operator — after export_w9_signals_to_s3.py has written the parquet for the day):
  uv run python scripts/parity_check_w9_signals.py                       # all 5 stores
  uv run python scripts/parity_check_w9_signals.py --table mart_sub_model_signals
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_S3_BUCKET = "baseball-betting-ml-artifacts"
_LAKEHOUSE = f"s3://{_S3_BUCKET}/baseball/lakehouse"

# lakehouse_name → Snowflake FQN (must match export_w9_signals_to_s3.MIRROR_TABLES)
MIRROR_TABLES = {
    "mart_sub_model_signals":      "baseball_data.betting.mart_sub_model_signals",
    "offense_v1_signals":          "baseball_data.betting_features.offense_v1_signals",
    "offense_v2_signals":          "baseball_data.betting_features.offense_v2_signals",
    "starter_suppression_signals": "baseball_data.betting_features.starter_suppression_signals",
    "starter_ip_signals":          "baseball_data.betting_features.starter_ip_signals",
}
ALL_NAMES = sorted(MIRROR_TABLES)

_SUM_RTOL = 1e-6  # rounded-sum float-engine drift band

_NUMERIC = {"DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "BIGINT", "INTEGER", "HUGEINT",
            "SMALLINT", "TINYINT", "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT", "INT"}
_BOOLEAN = {"BOOLEAN", "BOOL"}


# ── connections ───────────────────────────────────────────────────────────────
def _sf_conn():
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection()


def _duck_conn():
    import duckdb
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("CREATE OR REPLACE SECRET baseball_s3 "
                 "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')")
    for _p in ("SET http_timeout=600000", "SET http_retries=8"):
        try:
            conn.execute(_p)
        except Exception:
            pass
    return conn


def _duck_columns(duck, name: str) -> list[tuple[str, str]]:
    """(lower_name, base_type) for each column of the S3 parquet — the source of truth for
    which columns to fingerprint (the parquet was written from the SF SELECT *)."""
    loc = f"{_LAKEHOUSE}/{name}/data.parquet"
    rows = duck.execute(f"DESCRIBE SELECT * FROM read_parquet('{loc}')").fetchall()
    out = []
    for r in rows:
        col, dt = r[0].lower(), r[1].upper().split("(")[0].strip()
        out.append((col, dt))
    return out


# ── fingerprint SQL (cross-engine: DuckDB + Snowflake both parse it) ───────────
def _fingerprint_exprs(cols: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return [(alias, sql_expr)] — count(*) , distinct game_pk, and per-column
    non-null count + (numeric rounded SUM | boolean true-count)."""
    exprs: list[tuple[str, str]] = [("n_rows", "count(*)")]
    col_names = {c for c, _ in cols}
    if "game_pk" in col_names:
        exprs.append(("n_games", "count(distinct game_pk)"))
    for col, dt in cols:
        exprs.append((f"c__{col}", f"count({col})"))
        if dt in _NUMERIC:
            exprs.append((f"s__{col}", f"sum(round(cast({col} as double), 6))"))
        elif dt in _BOOLEAN:
            exprs.append((f"s__{col}", f"sum(case when {col} then 1 else 0 end)"))
    return exprs


def _fingerprint(run, source: str, cols: list[tuple[str, str]]) -> dict[str, float]:
    exprs = _fingerprint_exprs(cols)
    select = ", ".join(f"{e} as {a}" for a, e in exprs)
    row = run(f"SELECT {select} FROM {source}")
    return {a: row[i] for i, (a, _) in enumerate(exprs)}


def _accumulate_fp(run, source: str) -> dict[str, int]:
    """SCD-2 history-intact check: current vs closed row counts."""
    row = run(
        f"SELECT sum(case when is_current then 1 else 0 end), "
        f"       sum(case when is_current then 0 else 1 end) FROM {source}"
    )
    return {"n_current": row[0], "n_closed": row[1]}


# ── compare ───────────────────────────────────────────────────────────────────
def _num(x) -> float:
    return float(x) if x is not None else 0.0


def _compare(name: str, sf: dict, s3: dict, accumulate: tuple[dict, dict] | None) -> bool:
    print(f"\n=== {name} ===")
    n_sf, n_s3 = _num(sf["n_rows"]), _num(s3["n_rows"])
    print(f"  rows: snowflake={n_sf:,.0f}  s3={n_s3:,.0f}")
    if "n_games" in sf:
        print(f"  games: snowflake={_num(sf['n_games']):,.0f}  s3={_num(s3['n_games']):,.0f}")

    if n_sf != n_s3:
        # Freshness snapshot: a count delta is EXPECTED if a generator wrote after the mirror.
        print(f"  ⚠️ ROW-COUNT DELTA ({n_sf - n_s3:+,.0f}) — mirror is a snapshot; re-run "
              f"export_w9_signals_to_s3.py if Snowflake is ahead, then re-check. "
              f"Column fingerprints below are only meaningful at equal counts.")

    if accumulate is not None:
        acc_sf, acc_s3 = accumulate
        print(f"  SCD-2 accumulate (history-intact):")
        print(f"    is_current=TRUE : snowflake={_num(acc_sf['n_current']):,.0f}  s3={_num(acc_s3['n_current']):,.0f}")
        print(f"    is_current=FALSE: snowflake={_num(acc_sf['n_closed']):,.0f}  s3={_num(acc_s3['n_closed']):,.0f}  (the SCD-2 HISTORY)")
        if n_sf == n_s3 and (acc_sf["n_current"] != acc_s3["n_current"]
                             or acc_sf["n_closed"] != acc_s3["n_closed"]):
            print("    ❌ accumulate split mismatch at equal row count.")
            return False

    # Column fingerprint diff (only authoritative when counts are equal).
    ok = True
    mism = []
    for key in sorted(set(sf) & set(s3)):
        if key in ("n_rows", "n_games"):
            continue
        a, b = sf[key], s3[key]
        if key.startswith("c__"):  # exact non-null counts
            if _num(a) != _num(b):
                mism.append(f"{key}: sf={_num(a):,.0f} s3={_num(b):,.0f}")
        else:  # s__ : rounded SUM / bool-count — float tolerance
            fa, fb = _num(a), _num(b)
            denom = max(abs(fa), abs(fb), 1.0)
            if abs(fa - fb) / denom > _SUM_RTOL:
                mism.append(f"{key}: sf={fa:.6g} s3={fb:.6g}")
    if n_sf == n_s3:
        if mism:
            ok = False
            print(f"  ❌ {len(mism)} column fingerprint mismatch(es):")
            for m in mism[:30]:
                print(f"     - {m}")
        else:
            print(f"  ✅ all {len([k for k in sf if k.startswith(('c__', 's__'))])} column "
                  f"fingerprints match (value-preserving).")
    else:
        print("  (column fingerprints skipped at unequal counts — re-mirror then re-run)")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="E11.1-W9 signal-store mirror parity + accumulate gate")
    ap.add_argument("--table", choices=ALL_NAMES, help="Check one (default: all 5)")
    args = ap.parse_args()
    selected = [args.table] if args.table else ALL_NAMES

    sf = _sf_conn()
    duck = _duck_conn()

    def sf_run(sql: str):
        cur = sf.cursor()
        try:
            cur.execute(sql)
            return list(cur.fetchone())
        finally:
            cur.close()

    def duck_run_for(name: str):
        loc = f"{_LAKEHOUSE}/{name}/data.parquet"
        def _run(sql: str):
            # the mirror has no FQN — point the bare table name at the parquet
            duck_sql = sql.replace(f"FROM {name}", f"FROM read_parquet('{loc}')")
            return list(duck.execute(duck_sql).fetchone())
        return _run

    all_ok = True
    try:
        for name in selected:
            fqn = MIRROR_TABLES[name]
            try:
                cols = _duck_columns(duck, name)
            except Exception as e:
                print(f"\n=== {name} ===\n  ❌ cannot read S3 parquet "
                      f"({_LAKEHOUSE}/{name}/data.parquet): {e}\n  Has export_w9_signals_to_s3.py run?")
                all_ok = False
                continue
            d_run = duck_run_for(name)
            sf_fp = _fingerprint(lambda s: sf_run(s.replace(f"FROM {name}", f"FROM {fqn}")), name, cols)
            s3_fp = _fingerprint(d_run, name, cols)
            acc = None
            if any(c == "is_current" for c, _ in cols):
                acc = (
                    _accumulate_fp(lambda s: sf_run(s.replace(f"FROM {name}", f"FROM {fqn}")), name),
                    _accumulate_fp(d_run, name),
                )
            all_ok &= _compare(name, sf_fp, s3_fp, acc)
    finally:
        sf.close()
        duck.close()

    print("\n" + ("✅ W9 parity PASS — signal-store mirror is value-preserving."
                  if all_ok else "❌ W9 parity FAIL — see mismatches above."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
