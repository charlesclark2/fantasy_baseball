"""
audit_lineup_dependence_30_8.py — Story 30.8 Task 1: pre/post-lineup feature classification.

Classifies every column in the 3 live model contracts (home_win 211 / run_diff 169 /
total_runs 113) as:
  - Class-A (PRE-LINEUP available)  : team/starter/park/weather/ELO/umpire/EB/overnight —
                                      present at morning serve before lineups post.
  - Class-B (requires CONFIRMED lineup): batting-order / slot / archetype-matchup /
                                      batter-cluster / lineup-statcast / batter-sequential —
                                      null until both lineups post (~game day).
This gates the rest of 30.8 (the pre-lineup contract = the Class-A subset per target).

METHOD — empirical, confound-aware. A column is Class-B if it's present when lineups are
CONFIRMED but absent when they're not. Naive "completed-window dense vs future sparse" is
CONFOUNDED by ROLLING-WINDOW incremental features (e.g. eb_starter_posteriors only covers
current_date-7, so older completed games are null for a NON-lineup reason). To isolate the
lineup-confirmation variable we use a TIGHT recent window on both sides — last 3 COMPLETED
days (recent + lineup-confirmed) vs next 3 FUTURE days (recent + unconfirmed) — both inside
the rolling windows. A name-pattern cross-check flags agreement/disagreement for review.

    null_dense  = null-rate over completed games in [current_date-3, current_date-1]
    null_sparse = null-rate over future games in   [current_date+1, current_date+3]
    Class-B  if  null_sparse - null_dense > 0.5      (present-confirmed, absent-unconfirmed)
    Class-A  if  null_sparse <= 0.5                  (present even pre-lineup)
    ambiguous otherwise (null in BOTH windows — structural/rolling, NOT lineup-gated → A)

HAND-OFF: two Snowflake pulls of the contract columns over ~2 weeks of games — under a minute
but a Snowflake script, so run it yourself:

    uv run python betting_ml/scripts/audit_lineup_dependence_30_8.py

Outputs:
    quant_sports_intel_models/baseball/ablation_results/lineup_dependence_30_8.csv
    quant_sports_intel_models/baseball/ablation_results/lineup_dependence_30_8.md
    betting_ml/models/home_win/feature_columns_pre_lineup_home_win.json   (Class-A subset)
    betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json
    betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

_TABLE = "baseball_data.betting_features.feature_pregame_game_features"
_REGISTRY = _PROJECT_ROOT / "betting_ml/models/model_registry.yaml"
_OUT_CSV = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/lineup_dependence_30_8.csv"
_OUT_MD = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/lineup_dependence_30_8.md"

_DELTA_TOL = 0.5   # null_sparse - null_dense above this = lineup-gated (Class-B)
_PRESENT_TOL = 0.5  # null_sparse at/below this = present pre-lineup (Class-A)

# Lineup-dependence NAME signal (cross-check only; the empirical delta is authoritative).
_LINEUP_PAT = ("lineup_", "batting_order", "batter_cluster", "_vs_cluster", "archetype",
               "_vs_starter_archetype", "_vs_lhp", "_vs_rhp", "platoon", "avg_eb_woba_sequential",
               "slot_", "_h2h_woba", "bat_speed", "attack_angle", "swing_length")

# Per-target live contract (model_registry.yaml is authoritative) + the pre-lineup output path.
_TARGETS = {
    "home_win":   {"reg": "home_win",         "out": "betting_ml/models/home_win/feature_columns_pre_lineup_home_win.json"},
    "run_diff":   {"reg": "run_differential", "out": "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json"},
    "total_runs": {"reg": "total_runs",       "out": "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json"},
}


def _contracts() -> dict[str, list[str]]:
    import yaml
    reg = yaml.safe_load(_REGISTRY.read_text())
    out = {}
    for tgt, meta in _TARGETS.items():
        p = reg[meta["reg"]]["feature_columns_path"]
        raw = json.loads((_PROJECT_ROOT / p).read_text())
        out[tgt] = raw["feature_cols"] if isinstance(raw, dict) else raw
    return out


def _table_columns(conn) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM baseball_data.information_schema.columns "
                "WHERE table_schema='BETTING_FEATURES' AND table_name='FEATURE_PREGAME_GAME_FEATURES'")
    return {r[0].lower() for r in cur.fetchall()}


def _window_stats(conn, cols: list[str], lo_off: int, hi_off: int) -> tuple[pd.Series, pd.Series]:
    """(null-rate, distinct-non-null-count) per col over games in [current_date+lo, +hi].
    nunique catches SEASON-FILL placeholders: a feature that's non-null but CONSTANT
    pre-lineup (e.g. a `_seasonnorm` lineup twin filled with the season average) is dead
    weight, not real signal — must be excluded from the pre-lineup contract."""
    sel = ", ".join(cols)
    sql = (f"SELECT {sel} FROM {_TABLE} "
           f"WHERE game_date >= dateadd('day',{lo_off},current_date()) "
           f"AND game_date <= dateadd('day',{hi_off},current_date())")
    cur = conn.cursor()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    if df.empty:
        nan = pd.Series({c: float("nan") for c in cols})
        return nan, nan
    return df.isna().mean(), df.nunique(dropna=True)


def main() -> None:
    contracts = _contracts()
    union = sorted({c for cols in contracts.values() for c in cols})
    print(f"Contract union: {len(union)} features "
          f"(home_win {len(contracts['home_win'])}, run_diff {len(contracts['run_diff'])}, "
          f"total_runs {len(contracts['total_runs'])})")

    conn = get_snowflake_connection()
    try:
        present = sorted(set(union) & _table_columns(conn))
        absent = sorted(set(union) - set(present))
        if absent:
            print(f"  {len(absent)} contract cols ABSENT from the store (→ Class-A imputation indicators): {absent}")
        dense_null, dense_nu = _window_stats(conn, present, -3, -1)   # completed, lineup-confirmed, recent
        sparse_null, sparse_nu = _window_stats(conn, present, 1, 3)   # future, unconfirmed, recent
    finally:
        conn.close()

    rows = []
    for c in union:
        if c not in present:
            rows.append({"feature": c, "class": "A", "reason": "absent-from-store (imputation indicator)",
                         "null_dense": None, "null_sparse": None, "name_lineup": False, "name_agrees": True})
            continue
        nd, ns = float(dense_null.get(c, float("nan"))), float(sparse_null.get(c, float("nan")))
        d_nu, s_nu = int(dense_nu.get(c, 0) or 0), int(sparse_nu.get(c, 0) or 0)
        name_lineup = any(p in c for p in _LINEUP_PAT)
        if pd.notna(ns) and pd.notna(nd) and (ns - nd) > _DELTA_TOL:
            cls, reason = "B", f"present-confirmed/absent-unconfirmed (Δnull {ns-nd:+.2f})"
        elif pd.notna(ns) and ns <= _PRESENT_TOL and s_nu <= 1 and d_nu > 1:
            # non-null but CONSTANT pre-lineup while VARIED when confirmed = season-fill
            # placeholder (e.g. a `_seasonnorm` lineup twin) → dead weight pre-lineup.
            cls, reason = "B", f"season-fill placeholder (constant pre-lineup: nunique {s_nu} vs dense {d_nu})"
        elif pd.notna(ns) and ns <= _PRESENT_TOL:
            cls, reason = "A", f"present pre-lineup (null_sparse {ns:.2f}, nunique {s_nu})"
        else:
            cls, reason = "A", f"null in BOTH windows — structural/rolling, not lineup-gated (sparse {ns:.2f}/dense {nd:.2f})"
        rows.append({"feature": c, "class": cls, "reason": reason,
                     "null_dense": round(nd, 3) if pd.notna(nd) else None,
                     "null_sparse": round(ns, 3) if pd.notna(ns) else None,
                     "name_lineup": name_lineup, "name_agrees": (cls == "B") == name_lineup})
    cls_df = pd.DataFrame(rows)
    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cls_df.to_csv(_OUT_CSV, index=False)

    class_b = set(cls_df[cls_df["class"] == "B"]["feature"])
    disagree = cls_df[~cls_df["name_agrees"]]

    # Write the per-target pre-lineup contracts (Class-A subset, order preserved).
    sizes = {}
    for tgt, meta in _TARGETS.items():
        pre = [c for c in contracts[tgt] if c not in class_b]
        sizes[tgt] = (len(contracts[tgt]), len(pre), len(contracts[tgt]) - len(pre))
        out_path = _PROJECT_ROOT / meta["out"]
        out_path.write_text(json.dumps(
            {"target": meta["reg"], "model_name": f"pre_lineup_{tgt}", "story": "30.8",
             "n_features": len(pre),
             "derived_from": f"{meta['reg']} live contract minus {len(contracts[tgt]) - len(pre)} Class-B lineup cols",
             "feature_cols": pre}, indent=2))

    def _tbl(sub):
        if sub.empty:
            return "_(none)_\n"
        h = "| feature | class | null dense/sparse | name? | reason |\n|---|---|---|---|---|\n"
        return h + "".join(
            f"| `{r.feature}` | {r['class']} | {r.null_dense}/{r.null_sparse} | "
            f"{'L' if r.name_lineup else ''} | {r.reason} |\n" for _, r in sub.iterrows())

    md = (
        f"# Story 30.8 — Pre/post-lineup feature classification (Task 1)\n\n"
        f"Contract union **{len(union)}**. Class-B (lineup-gated) = **{len(class_b)}** features. Method: "
        f"null-rate over last-3-completed (confirmed) vs next-3-future (unconfirmed) games — tight recent windows "
        f"to isolate lineup-confirmation from the rolling-window incremental confound. Name cross-check = `L`.\n\n"
        f"## Pre-lineup contract sizes (Class-A subset = the morning model's inputs)\n\n"
        f"| target | post-lineup (live) | pre-lineup (Class-A) | Class-B dropped |\n|---|---|---|---|\n"
        + "".join(f"| {t} | {a} | {b} | {d} |\n" for t, (a, b, d) in sizes.items()) +
        f"\n## 🔵 Class-B — requires confirmed lineup ({len(class_b)})\n\n" + _tbl(cls_df[cls_df['class'] == 'B']) +
        f"\n## ⚠️ name/empirical DISAGREEMENTS — review these ({len(disagree)})\n\n" + _tbl(disagree) +
        f"\n_Full per-feature table in the CSV. Class-A = everything not listed Class-B._\n"
    )
    _OUT_MD.write_text(md)

    print("\n=== pre-lineup contract sizes ===")
    for t, (a, b, d) in sizes.items():
        print(f"  {t:12s} post-lineup {a:4d}  ->  pre-lineup {b:4d}  (dropped {d} Class-B)")
    print(f"\nClass-B (lineup-gated): {len(class_b)}")
    print(f"name/empirical disagreements (review): {len(disagree)}")
    print(f"\nWrote {_OUT_MD}\n      {_OUT_CSV}\n      + 3 pre-lineup contract JSONs")


if __name__ == "__main__":
    main()
