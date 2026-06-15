"""
audit_feature_completeness_30_12.py — Story 30.12 Task 1: feature-store completeness map.

Reads baseball_data.betting_features.feature_pregame_game_features and, for every feature in the
UNION of the 3 deployed model contracts (home_win / run_diff / total_runs), computes the null-rate by
(season × month-of-season) across 2021–2026. Classifies each feature as:

  - absent_from_store      : in a model contract but NOT a column in the feature table (→ 100% imputed
                             to a constant at serve time; the most serving-skew-relevant case).
  - clean                  : ~no nulls anywhere.
  - early_season_by_construction : null-rate high in Mar/Apr, decays to ~0 by mid-season (benign; the
                             A2.5 is_degraded flag already catches these — season-to-date features).
  - persistent_gap         : a non-zero null FLOOR that survives into mid-season (month ≥ 5) in ≥1 season
                             (a genuine data gap, e.g. pythagorean_win_exp_diff's 2024 ~6.5% floor).

Per-SEASON breakdown is kept (the 30.12 grounding floor turned out to be 2024-ONLY — 2025/2026 are clean
mid-season — so a feature can be a persistent_gap in one season and clean in another; that distinction
matters for root-cause).

HAND-OFF: pulls the full feature table (10.8k rows × ~320 cols) — under a minute, but it's a Snowflake
pull so run it yourself:

    uv run python betting_ml/scripts/audit_feature_completeness_30_12.py

Outputs:
    quant_sports_intel_models/baseball/ablation_results/feature_completeness_30_12.csv   (feature×season×month null rates)
    quant_sports_intel_models/baseball/ablation_results/feature_completeness_30_12.md    (classified report)
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
_OUT_CSV = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/feature_completeness_30_12.csv"
_OUT_MD = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/feature_completeness_30_12.md"

# classification thresholds
_MIDSEASON_MONTH = 5        # May+ = "mid-season" (early-season ramp excluded)
_FLOOR_TOL = 0.02           # mid-season null-rate above this in the CLEAN era = a real floor (0.5% over-flagged)
_EARLY_TOL = 0.05           # early-season (Mar/Apr) null-rate above this = "early-season null"
_ERA_FLOOR = 0.50           # older-season null above this (with recent clean) = data-availability era boundary
_LAG_TOL = 0.03             # current-season LATEST-month null above this (over a clean steady-state) = recent-lag

# Explicit TIERS (Story 30.12 Task-2 refinement). The PRIMARY tier is read from COMPLETED-season
# structure; `recent_lag` and `likely_semantic` are CROSS-CUTTING annotations (the current-season tail
# bump hits ~all features regardless of their primary story, and semantic-vs-structural is a name signal):
#   serve_time_indicator   — absent from the store BY DESIGN (the imputation indicators)
#   clean                  — no material nulls in any completed season
#   early_season           — high Mar/Apr, decays to ~0 by mid-season (A2.5 is_degraded territory)
#   single_season_gap      — exactly ONE completed season gapped mid-season (a season-specific source break)
#   era_boundary           — null in older seasons (≥50%), clean from 2024+ (feature didn't exist; data-availability)
#   resolved_source_gap    — older seasons gapped at a LOW floor, clean by 2025 (a fixed upstream gap; e.g. pythagorean)
#   persistent_coverage    — a floor that survives into the clean era (2025) → see likely_semantic to sub-classify
# Annotations: recent_lag (bool), likely_semantic (bool — coverage that's null-by-category, handled by design).
_SEMANTIC_PAT = ("_vs_cluster", "_cluster_", "archetype", "_vs_lhb", "_vs_rhb", "vs_starter_archetype",
                 "stuff_plus", "_h2h_", "platoon", "_vs_lhp", "_vs_rhp",
                 "lineup_vs_", "_used_prev", "_vs_starter_")   # matchup / bullpen-usage coverage = by-design


def _contract_union() -> set[str]:
    import yaml
    reg = yaml.safe_load(_REGISTRY.read_text())
    union: set[str] = set()
    for tgt in ("home_win", "run_differential", "total_runs"):
        p = reg[tgt].get("feature_columns_path")
        raw = json.loads((_PROJECT_ROOT / p).read_text())
        cols = raw["feature_cols"] if isinstance(raw, dict) else raw
        union |= set(cols)
    return union


def _table_columns(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT column_name FROM baseball_data.information_schema.columns "
        "WHERE table_schema='BETTING_FEATURES' AND table_name='FEATURE_PREGAME_GAME_FEATURES'")
    return [r[0].lower() for r in cur.fetchall()]


def _load(conn, cols: list[str]) -> pd.DataFrame:
    sel = ", ".join(['game_pk', 'game_year', 'game_date'] + cols)
    sql = f"SELECT {sel} FROM {_TABLE} WHERE game_year >= 2021"
    cur = conn.cursor()
    cur.execute(sql)
    df = cur.fetch_pandas_all()          # Snowflake-native (pyarrow); cols come back UPPERCASE
    df.columns = [c.lower() for c in df.columns]
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["mo"] = df["game_date"].dt.month
    return df


def classify_tier(df: pd.DataFrame, feat: str, absent: set[str], current_season: int) -> dict:
    """Assign a PRIMARY tier from completed-season structure + cross-cutting annotations.
    See the _SEMANTIC_PAT / tier docstring above for the tier semantics."""
    likely_semantic = any(p in feat for p in _SEMANTIC_PAT)
    if feat in absent:
        return {"feature": feat, "tier": "serve_time_indicator", "floor_2025": None,
                "early_null": None, "gap_seasons": "n/a", "recent_lag": False,
                "likely_semantic": likely_semantic}

    early_null = float(df.loc[df.mo.isin([3, 4]), feat].isna().mean()) if (df.mo.isin([3, 4])).any() else 0.0
    season_mid = (df[df.mo >= _MIDSEASON_MONTH].groupby("game_year")[feat]
                  .apply(lambda x: float(x.isna().mean())))
    mid = {int(y): r for y, r in season_mid.items()}
    completed = [s for s in mid if s != current_season]
    older = [s for s in completed if s <= current_season - 2]              # 2021..(current-2)
    f2025 = mid.get(current_season - 1, 0.0)                               # latest COMPLETED season (steady-state)
    gaps = sorted(s for s in completed if mid.get(s, 0) > _FLOOR_TOL)

    # cross-cutting: current-season tail bump over a clean steady-state
    cur = df[df.game_year == current_season]
    cur_mo = cur.groupby("mo")[feat].apply(lambda x: float(x.isna().mean())) if len(cur) else pd.Series(dtype=float)
    latest_null = float(cur_mo.iloc[-1]) if len(cur_mo) else 0.0
    earlier_null = float(cur_mo.iloc[:-1].max()) if len(cur_mo) > 1 else 0.0
    recent_lag = bool(latest_null > _LAG_TOL and latest_null > max(2 * earlier_null, f2025 + _LAG_TOL))

    # PRIMARY tier from completed-season structure (priority order)
    older_max = max((mid.get(s, 0) for s in older), default=0.0)
    comp_max = max((mid.get(s, 0) for s in completed), default=0.0)
    if comp_max <= _FLOOR_TOL and early_null <= _EARLY_TOL:
        tier = "clean"
    elif comp_max <= _FLOOR_TOL and early_null > _EARLY_TOL:
        tier = "early_season"
    elif len(gaps) == 1 and all(mid.get(s, 0) < 0.01 for s in completed if s not in gaps):
        tier = "single_season_gap"
    elif f2025 < _FLOOR_TOL and older_max > _FLOOR_TOL:
        tier = "era_boundary" if older_max >= _ERA_FLOOR else "resolved_source_gap"
    else:
        tier = "persistent_coverage"
    return {"feature": feat, "tier": tier, "floor_2025": round(f2025, 4),
            "early_null": round(early_null, 4), "gap_seasons": ",".join(map(str, gaps)) or "-",
            "recent_lag": recent_lag, "likely_semantic": likely_semantic}


def main() -> None:
    union = _contract_union()
    print(f"Contract union: {len(union)} features")
    conn = get_snowflake_connection(schema="betting_features")
    try:
        tbl_cols = set(_table_columns(conn))
        present = sorted(union & tbl_cols)
        absent = sorted(union - tbl_cols)
        print(f"  present in store: {len(present)}  |  ABSENT from store: {len(absent)}")
        if absent:
            print("  ⚠ absent (100% imputed at serve):", absent)
        df = _load(conn, present)
        print(f"  loaded {len(df)} rows, seasons {sorted(df.game_year.unique())}")
    finally:
        conn.close()

    # per feature × season × month null-rate CSV (long format)
    rows = []
    for feat in present:
        g = df.groupby(["game_year", "mo"])[feat].apply(lambda x: float(x.isna().mean()))
        for (yr, mo), r in g.items():
            rows.append({"feature": feat, "season": int(yr), "month": int(mo),
                         "null_rate": round(r, 4)})
    long = pd.DataFrame(rows)
    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    long.to_csv(_OUT_CSV, index=False)

    # classification — explicit tiers
    current = int(df.game_year.max())
    cls = pd.DataFrame([classify_tier(df, f, set(absent), current) for f in sorted(union)])
    _TIER_ORDER = ["persistent_coverage", "single_season_gap", "era_boundary", "resolved_source_gap",
                   "early_season", "serve_time_indicator", "clean"]
    cls["o"] = cls["tier"].apply(lambda t: _TIER_ORDER.index(t) if t in _TIER_ORDER else 99)
    cls = cls.sort_values(["o", "floor_2025"], ascending=[True, False],
                          na_position="last").drop(columns="o")
    counts = cls["tier"].value_counts().to_dict()
    cls.to_csv(_OUT_CSV.with_name("feature_completeness_30_12_tiers.csv"), index=False)

    def _tbl(sub: pd.DataFrame) -> str:
        if sub.empty:
            return "_(none)_\n"
        h = "| feature | 2025 floor | early | gap_seasons | recent_lag | likely_semantic |\n|---|---|---|---|---|---|\n"
        return h + "".join(
            f"| `{r.feature}` | {r.floor_2025} | {r.early_null} | {r.gap_seasons} | "
            f"{'⚠' if r.recent_lag else ''} | {'sem' if r.likely_semantic else ''} |\n"
            for r in sub.itertuples())

    persistent = cls[cls["tier"] == "persistent_coverage"]
    structural = persistent[~persistent["likely_semantic"]]   # the genuine-bug candidates
    semantic = persistent[persistent["likely_semantic"]]       # by-design coverage
    n_lag = int(cls["recent_lag"].sum())

    md = (f"# Story 30.12 — Feature-store completeness map (tiered)\n\n"
          f"Contract union: **{len(union)}** features. Tiers: "
          + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) +
          f".\n\n`recent_lag` flag set on **{n_lag}** features (current-season tail bump = the 30.6 serving-skew "
          f"signature; cross-cuts all tiers). Mid-season = month ≥ {_MIDSEASON_MONTH}; clean-era floor tol "
          f"{_FLOOR_TOL}; era floor {_ERA_FLOOR}.\n\n"
          f"## 🔧 persistent_coverage — STRUCTURAL (not name-semantic → genuine-gap candidates, root-cause these)\n\n"
          + _tbl(structural) +
          f"\n## persistent_coverage — SEMANTIC by design ({len(semantic)} — null-by-category, handled by coverage cols + imputation)\n\n"
          + _tbl(semantic.head(30)) +
          (f"\n_…+{len(semantic)-30} more in the tiers CSV._\n" if len(semantic) > 30 else "") +
          f"\n## single_season_gap (a season-specific source break — e.g. pythagorean)\n\n"
          + _tbl(cls[cls["tier"] == "single_season_gap"]) +
          f"\n## era_boundary (feature didn't exist pre-2024 — train-consistency, benign live)\n\n"
          + _tbl(cls[cls["tier"] == "era_boundary"]) +
          f"\n## resolved_source_gap (older-season gap, clean by 2025)\n\n"
          + _tbl(cls[cls["tier"] == "resolved_source_gap"]) +
          f"\n## early_season ({counts.get('early_season',0)} — Mar/Apr decay, benign) · "
          f"serve_time_indicator ({counts.get('serve_time_indicator',0)} by-design) · "
          f"clean ({counts.get('clean',0)}).\n")
    _OUT_MD.write_text(md)

    print("\n=== TIERS ===")
    for k in _TIER_ORDER:
        print(f"  {k:22s} {counts.get(k,0)}")
    print(f"  recent_lag flagged:    {n_lag}")
    print("\n🔧 STRUCTURAL persistent_coverage (genuine-gap candidates):")
    for r in structural.itertuples():
        print(f"  {r.feature:46s} 2025_floor={r.floor_2025}  gaps={r.gap_seasons}  lag={'Y' if r.recent_lag else 'n'}")
    print(f"\nWrote {_OUT_CSV}\n      {_OUT_CSV.with_name('feature_completeness_30_12_tiers.csv')}\n      {_OUT_MD}")


if __name__ == "__main__":
    main()
