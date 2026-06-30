#!/usr/bin/env python3
"""
parity_check_w8b.py   (E11.1-W8b — serving aggregator + complex upstream parity gate)
-------------------------------------------------------------------------------------
The SAFETY GATE for the W8b dual-branch migration. For each of the 9 W8b models it compares the
LIVE NATIVE Snowflake table (computed by the pre-cutover model from native upstream) against the
DuckDB-over-S3 parquet (run_w1_lakehouse.py --w8b). A value-preserving migration matches every
column's fingerprint at equal row counts.

⚠️ PARITY IS NECESSARY-NOT-SUFFICIENT (the W8a 24h-outage lesson). It reads the parquet via DuckDB,
so it is BLIND to the entire Snowflake-ext-table read-bug class (binary-ts→garbage, VALUE:case→NULL,
glob-dup). The CUTOVER gate is a per-ROW fetch THROUGH the actual lakehouse_ext.feature_* table +
`predict_today` features NON-NULL on the box (the INC-17-P2 matchup class is invisible to row-count
parity — verify served matchup features non-null on a real post_lineup prediction).

WHAT IT CHECKS (per model, Snowflake-native vs DuckDB-over-S3, computed IN-ENGINE so the wide feature
tables never land in pandas):
  • row count + distinct game_pk            (exact)
  • per-column fingerprint: non-null count (exact) + rounded SUM for numerics / boolean true-count
    (float rtol 1e-6; _std cols 1e-4 for cross-engine STDDEV noise; POSTERIOR-derived cols — eb_/
    sequential/archetype/cluster/matchup/h2h — get a looser 2% rel OR 5e-3 per-row-abs tolerance and
    are reported as benign drift, never a FAIL: see the E11.1-W9-tail PARITY RIDER below). Metadata
    cols (computed_at/record_hash) are ts/text → only their non-null count is compared (build differs).
  • SCD-2 SPAN check for feature_pregame_lineup_features (is_current sentinel): the is_current split
    must match both engines.

A count delta is a FRESHNESS snapshot (native vs S3 built at slightly different times), reported NOT
failed — re-run --w8b + re-check. A *value* fingerprint drift at a SHARED row count IS a failure.

⚠️ feature_pregame_game_features_raw + feature_pregame_game_features are INCREMENTAL on Snowflake.
Before cutover the native table is the OLD (NUMBER home_win_rate_trailing_3yr) build; compare it to
the DuckDB FLOAT build — values match (rounded sums), the home_win_rate_trailing_3yr type differs
(expected; the DROP+rebuild adopts FLOAT). The fingerprint casts to double so NUMBER-vs-FLOAT is
value-invariant.

RUN (operator — after export_w8b_precursors_to_s3.py + export_features_to_s3.py + the W8a/prior-wave
parquet exist, and run_w1_lakehouse.py --w8b (or --w8b-only) has written the parquet):
  uv run python scripts/parity_check_w8b.py                                  # all 9
  uv run python scripts/parity_check_w8b.py --table feature_pregame_game_features_raw
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_S3_BUCKET = "baseball-betting-ml-artifacts"
_LAKEHOUSE = f"s3://{_S3_BUCKET}/baseball/lakehouse"

# lakehouse_name → live native Snowflake FQN. All 9 W8b models live in betting_features (the feature
# schema). injury_status is NOT here (finalized in W8b but its parity was W7b-class).
W8B_TABLES = {
    "feature_pregame_starter_features":       "baseball_data.betting_features.feature_pregame_starter_features",
    "feature_pregame_lineup_features":        "baseball_data.betting_features.feature_pregame_lineup_features",
    "feature_pregame_bullpen_state_features": "baseball_data.betting_features.feature_pregame_bullpen_state_features",
    "feature_batter_archetype_matchups":      "baseball_data.betting_features.feature_batter_archetype_matchups",
    "feature_pitcher_batter_h2h_matchups":    "baseball_data.betting_features.feature_pitcher_batter_h2h_matchups",
    "feature_pitcher_cluster_matchups":       "baseball_data.betting_features.feature_pitcher_cluster_matchups",
    "feature_pregame_game_features_raw":      "baseball_data.betting_features.feature_pregame_game_features_raw",
    "feature_league_contact_baseline":        "baseball_data.betting_features.feature_league_contact_baseline",
    "feature_pregame_game_features":          "baseball_data.betting_features.feature_pregame_game_features",
}
ALL_NAMES = list(W8B_TABLES)

# metadata cols whose VALUES legitimately differ between the native build and the DuckDB build
# (build run-time) — fingerprint their non-null count only, never a value sum.
_META_COLS = {"computed_at", "fit_date", "run_id", "record_hash", "valid_from", "valid_to"}

_SUM_RTOL = 1e-6
# STDDEV uses DIFFERENT numerical algorithms in Snowflake vs DuckDB, so a _std column's SUM carries
# benign cross-engine float noise (~1e-6, up to ~6e-6). Looser rtol for `_std` cols ONLY; genuine
# drift (>=~1e-4) is still caught.
_STD_RTOL = 1e-4

# ── E11.1-W9-tail PARITY RIDER — posterior-input drift is a benign FALSE-RED class ──────────────
# The native feature build (≈04:17 morning dbt) and the DuckDB-over-S3 build (≈14:52 --w8b) read
# DIFFERENT generations of the EB / sequential / archetype / cluster posteriors. Population
# shrinkage nudges every historical posterior ~0.001–0.004 on each daytime recompute, so every
# posterior-DERIVED aggregator column's SUM differs by ~1% at an otherwise value-preserving,
# EQUAL-row-count build. That is NOT a migration defect — pre-rider it fired RED on aligned dailies
# and misled sessions into chasing a non-bug (the W8b-memory PARITY-FAIL NON-BUG). Posterior columns
# therefore get a looser per-column tolerance — relative 2% OR mean per-row abs ≤ 5e-3, whichever
# passes — and are reported as an informational drift class, NEVER a hard FAIL. Deterministic columns
# keep the tight 1e-6, and EVERY column's non-null COUNT stays EXACT — so a real migration bug (wrong
# column/join → count or null change; wrong scale → ≫2% diff) is still caught. (Parity remains
# necessary-not-sufficient; the binding cutover gate is the per-ROW ext fetch + predict_today.)
_POSTERIOR_RTOL = 2e-2
_POSTERIOR_ABS  = 5e-3   # mean per-row absolute drift floor (|Δsum| / n_rows)
# Substring tokens identifying posterior/cluster/archetype-derived columns. Verified against the
# 751-col aggregator: catches the 83 EB/sequential/archetype/cluster/matchup/h2h columns and ZERO
# deterministic columns (rolling _Nd / park / weather / win_rate / odds all excluded).
_POSTERIOR_TOKENS = ("eb_", "sequential", "archetype", "cluster", "matchup", "h2h")


def _is_posterior_col(col: str) -> bool:
    """True if `col` is derived from an EB/sequential/archetype/cluster posterior (which recomputes
    between the native and S3 build snapshots → benign value drift at equal row counts)."""
    return any(tok in col for tok in _POSTERIOR_TOKENS)
_NUMERIC = {"DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "BIGINT", "INTEGER", "HUGEINT",
            "SMALLINT", "TINYINT", "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT", "INT"}
_BOOLEAN = {"BOOLEAN", "BOOL"}


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
    loc = f"{_LAKEHOUSE}/{name}/data.parquet"
    rows = duck.execute(f"DESCRIBE SELECT * FROM read_parquet('{loc}')").fetchall()
    return [(r[0].lower(), r[1].upper().split("(")[0].strip()) for r in rows]


def _fingerprint_exprs(cols: list[tuple[str, str]]) -> list[tuple[str, str]]:
    exprs: list[tuple[str, str]] = [("n_rows", "count(*)")]
    col_names = {c for c, _ in cols}
    if "game_pk" in col_names:
        exprs.append(("n_games", "count(distinct game_pk)"))
    for col, dt in cols:
        exprs.append((f"c__{col}", f"count({col})"))
        if col in _META_COLS:
            continue  # non-null count only; values differ by build run-time
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


def _scd2_fp(run, source: str) -> dict[str, int]:
    row = run(
        f"SELECT sum(case when is_current then 1 else 0 end), "
        f"       sum(case when is_current then 0 else 1 end) FROM {source}"
    )
    return {"n_current": row[0], "n_closed": row[1]}


def _num(x) -> float:
    return float(x) if x is not None else 0.0


def _compare(name: str, sf: dict, s3: dict, scd2: tuple[dict, dict] | None) -> bool:
    print(f"\n=== {name} ===")
    n_sf, n_s3 = _num(sf["n_rows"]), _num(s3["n_rows"])
    print(f"  rows: snowflake={n_sf:,.0f}  s3={n_s3:,.0f}")
    if "n_games" in sf:
        print(f"  games: snowflake={_num(sf['n_games']):,.0f}  s3={_num(s3['n_games']):,.0f}")

    if n_sf != n_s3:
        print(f"  ⚠️ ROW-COUNT DELTA ({n_sf - n_s3:+,.0f}) — native build vs S3 build are time-"
              f"offset snapshots; re-run --w8b if behind, then re-check. Column fingerprints "
              f"below are only authoritative at equal counts.")

    if scd2 is not None:
        acc_sf, acc_s3 = scd2
        print("  SCD-2 spans (is_current split):")
        print(f"    is_current=TRUE : snowflake={_num(acc_sf['n_current']):,.0f}  s3={_num(acc_s3['n_current']):,.0f}")
        print(f"    is_current=FALSE: snowflake={_num(acc_sf['n_closed']):,.0f}  s3={_num(acc_s3['n_closed']):,.0f}")
        if n_sf == n_s3 and (acc_sf["n_current"] != acc_s3["n_current"]
                             or acc_sf["n_closed"] != acc_s3["n_closed"]):
            print("    ❌ SCD-2 span split mismatch at equal row count.")
            return False

    ok = True
    mism = []
    post_drift = []   # posterior-derived cols whose drift is within the benign tolerance (informational)
    n_rows = max(n_sf, 1.0)
    for key in sorted(set(sf) & set(s3)):
        if key in ("n_rows", "n_games"):
            continue
        a, b = sf[key], s3[key]
        if key.startswith("c__"):
            # Non-null COUNT stays EXACT for ALL columns (posterior tolerance never loosens counts).
            if _num(a) != _num(b):
                mism.append(f"{key}: sf={_num(a):,.0f} s3={_num(b):,.0f}")
        else:
            col = key[3:]   # strip the s__ prefix
            fa, fb = _num(a), _num(b)
            denom = max(abs(fa), abs(fb), 1.0)
            rel = abs(fa - fb) / denom
            if _is_posterior_col(col):
                # Benign build-snapshot posterior drift: pass on either a loose relative OR a small
                # mean per-row absolute drift. Report (non-zero drift) but never FAIL.
                per_row = abs(fa - fb) / n_rows
                if rel > _POSTERIOR_RTOL and per_row > _POSTERIOR_ABS:
                    mism.append(f"{key}: sf={fa:.6g} s3={fb:.6g} (posterior col, "
                                f"rel={rel:.3g} per_row={per_row:.3g} — EXCEEDS posterior tolerance)")
                elif abs(fa - fb) > 0:
                    post_drift.append(f"{col}: rel={rel:.2g} per_row={per_row:.2g}")
            else:
                rtol = _STD_RTOL if col.endswith("_std") else _SUM_RTOL
                if rel > rtol:
                    mism.append(f"{key}: sf={fa:.6g} s3={fb:.6g}")
    if n_sf == n_s3:
        if post_drift:
            print(f"  ℹ️ {len(post_drift)} posterior-derived column(s) drift within the benign "
                  f"tolerance (≤{_POSTERIOR_RTOL:.0%} rel or ≤{_POSTERIOR_ABS:g} per-row abs) — "
                  f"expected build-snapshot noise, NOT a migration defect:")
            for m in post_drift[:8]:
                print(f"     · {m}")
            if len(post_drift) > 8:
                print(f"     · … (+{len(post_drift) - 8} more posterior cols)")
        if mism:
            ok = False
            print(f"  ❌ {len(mism)} column fingerprint mismatch(es):")
            for m in mism[:40]:
                print(f"     - {m}")
        else:
            print(f"  ✅ all {len([k for k in sf if k.startswith(('c__', 's__'))])} column "
                  f"fingerprints match (value-preserving; posterior drift within tolerance).")
    else:
        print("  (column fingerprints skipped at unequal counts — re-build then re-run)")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="E11.1-W8b serving-aggregator + complex-upstream parity gate")
    ap.add_argument("--table", choices=ALL_NAMES, help="Check one (default: all 9)")
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

    all_ok = True
    try:
        for name in selected:
            fqn = W8B_TABLES[name]
            try:
                cols = _duck_columns(duck, name)
            except Exception as e:
                print(f"\n=== {name} ===\n  ❌ cannot read S3 parquet "
                      f"({_LAKEHOUSE}/{name}/data.parquet): {e}\n  Has run_w1_lakehouse.py --w8b run?")
                all_ok = False
                continue

            def d_run(sql: str, _name=name):
                loc = f"{_LAKEHOUSE}/{_name}/data.parquet"
                return list(duck.execute(sql.replace(f"FROM {_name}", f"FROM read_parquet('{loc}')")).fetchone())

            sf_fp = _fingerprint(lambda s, _f=fqn, _n=name: sf_run(s.replace(f"FROM {_n}", f"FROM {_f}")), name, cols)
            s3_fp = _fingerprint(d_run, name, cols)
            scd2 = None
            if any(c == "is_current" for c, _ in cols):
                scd2 = (
                    _scd2_fp(lambda s, _f=fqn, _n=name: sf_run(s.replace(f"FROM {_n}", f"FROM {_f}")), name),
                    _scd2_fp(d_run, name),
                )
            all_ok &= _compare(name, sf_fp, s3_fp, scd2)
    finally:
        sf.close()
        duck.close()

    print("\n" + ("✅ W8b parity PASS — serving aggregator + complex upstream are value-preserving.\n"
                  "   ⚠️ STILL REQUIRED before cutover: a per-ROW fetch through lakehouse_ext.feature_* "
                  "(catches the SF-ext read-bug class parity is blind to) + predict_today matchup "
                  "features NON-NULL on a real post_lineup run (the INC-17-P2 class)."
                  if all_ok else "❌ W8b parity FAIL — see mismatches above."))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
