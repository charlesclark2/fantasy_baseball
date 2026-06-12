"""Story 30.3 — production serving-skew parity harness.

Answers the question 30.1 raised: the SAME home_win contract+model scores
corr 0.42 OFFLINE (feature-store surface) but ~0.001 LIVE. 30.1 proved the model
has skill, so the live zero-skill is a SERVING problem. This harness localizes it
by building, for one date, the EXACT matrix `predict_today.py` feeds each model and
comparing it — column-for-column — against the trained contract AND the training
distribution.

It reproduces predict_today's matrix construction faithfully:
    df_hist  = load_features(min_games_played=15)          # training/offline surface
    df_today = load_todays_features(date)                  # the LIVE serve path
    pipeline = build_imputation_pipeline().fit(X_hist)     # imputer fit on TRAIN
    X_today  = pipeline.transform(reindex(df_today))       # served, imputed matrix
and then, per target contract, reports:
  - COUNT + ORDER parity of the served matrix vs the registry feature_columns_*.json
  - per-feature live state: structurally-absent | served-but-ALL-NULL (→ constant
    impute) | served-real, with the training-surface null rate alongside
  - the STRONG-TIER subset (the diffuse top drivers) called out separately, since
    a handful of those served null collapses the thin edge
  - a headline "% of the model matrix imputed-to-constant live" — the single number
    that explains the offline-vs-live skill gap

⭐ The offline-vs-live paradox, made concrete: the feature store is NOT
point-in-time-snapshotted. Re-reading it for a *settled* date returns the
POST-game-backfilled (dense) row; the live serve only ever saw the PRE-game
(sparse) row. So run this for TODAY (date defaults to today) to capture the real
live-sparse profile — running it for a past date reads the dense backfill and will
*understate* the skew (that re-read is exactly why the 0.42 benchmark is optimistic).

Runtime: loads ~30k historical rows from Snowflake + fits the imputation pipeline —
minutes. Hand off to run with real credentials:

    uv run python betting_ml/scripts/serving_parity_report.py --date 2026-06-12
    uv run python betting_ml/scripts/serving_parity_report.py            # today
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, load_todays_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "serving_parity"

# Strong-tier home_win drivers (INFLUENCE_REPORT.md families: starter Stuff+,
# lineup xwoba-vs-cluster, EB posteriors, bullpen, platoon). These are the diffuse
# signal carriers — if they arrive null/constant live, the thin edge evaporates.
_STRONG_TIER = [
    "away_starter_stuff_plus", "home_starter_stuff_plus",
    "away_starter_changeup_stuff_plus", "home_starter_fastball_stuff_plus",
    "away_lineup_avg_xwoba_vs_cluster", "home_lineup_avg_xwoba_vs_cluster",
    "away_lineup_archetype_avg_xwoba", "home_lineup_archetype_avg_xwoba",
    "home_avg_eb_woba", "away_avg_eb_woba",
    "home_avg_eb_woba_sequential", "away_avg_eb_woba_sequential",
    "home_starter_eb_xwoba_against", "away_starter_eb_xwoba_against",
    "home_starter_eb_xwoba_against_sequential", "away_starter_eb_xwoba_against_sequential",
    "home_avg_xwoba_vs_lhp", "home_avg_xwoba_vs_rhp",
    "home_bp_eb_xwoba", "away_bp_eb_xwoba",
    "home_elo", "away_elo", "elo_diff",
    "away_win_pct", "home_win_pct",
]


def _registry_contracts() -> dict[str, list[str]]:
    reg = yaml.safe_load((PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml").read_text())
    out = {}
    for tgt in ("total_runs", "run_differential", "home_win"):
        raw = json.loads((PROJECT_ROOT / reg[tgt]["feature_columns_path"]).read_text())
        out[tgt] = raw["feature_cols"] if isinstance(raw, dict) else raw
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=_date.today().isoformat(),
                    help="slate to inspect (default: today — the only date with a true live-sparse profile)")
    args = ap.parse_args()
    target_date = args.date
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    contracts = _registry_contracts()
    print(f"[parity] contracts: " + ", ".join(f"{t}={len(c)}" for t, c in contracts.items()))

    print(f"[parity] loading LIVE serve path for {target_date} ...")
    df_today = load_todays_features(target_date)
    if df_today.empty:
        print(f"No games for {target_date}; nothing to compare.")
        sys.exit(0)
    data_source = df_today["data_source"].iloc[0] if "data_source" in df_today.columns else "unknown"
    n_today = len(df_today)
    print(f"[parity] {n_today} game(s); live data_source={data_source}")

    print("[parity] loading training/offline surface (load_features) ...")
    df_hist = load_features(min_games_played=15)
    print(f"[parity] {len(df_hist):,} historical rows")

    # --- Reproduce predict_today's matrix construction EXACTLY -----------------
    retained = load_retained_features()
    all_feat = list(dict.fromkeys(retained + contracts["total_runs"] + contracts["run_differential"]))
    cols_hist = [c for c in all_feat if c in df_hist.columns]
    cols_today = [c for c in all_feat if c in df_today.columns]
    X_hist = df_hist[cols_hist]
    X_today_raw = df_today[cols_today].reindex(columns=X_hist.columns, fill_value=np.nan)

    pipeline = build_imputation_pipeline()
    X_hist_imp = pipeline.fit_transform(X_hist).select_dtypes(include=[np.number])
    X_today_imp = pipeline.transform(X_today_raw).reindex(columns=X_hist_imp.columns, fill_value=0.0)
    served_cols = set(X_today_imp.columns)

    # Training-surface null rate per feature (what the model learned to expect).
    train_null = {c: float(df_hist[c].isna().mean()) for c in df_hist.columns}

    report: dict = {"date": target_date, "data_source": data_source, "n_games": n_today, "targets": {}}
    md = [f"# Story 30.3 — Serving-Parity Report ({target_date})", "",
          f"- Live `data_source`: **{data_source}**, {n_today} game(s)",
          f"- Contracts: " + ", ".join(f"`{t}`={len(c)}" for t, c in contracts.items()),
          "",
          "Per target: how the LIVE served matrix compares to the trained contract and the",
          "training distribution. `served-but-ALL-NULL` columns are imputed to a single",
          "training-median constant for every game → zero discrimination (the live-skill killer).",
          ""]

    for tgt, cols in contracts.items():
        absent = [c for c in cols if c not in served_cols]
        present_raw = [c for c in cols if c in df_today.columns]
        all_null = [c for c in present_raw if df_today[c].isna().all()]
        # ORDER parity: the served slice is reindex(columns=cols), so order is correct
        # iff every col is present. Report the structural fact.
        order_ok = len(absent) == 0
        imputed_frac = round(len(all_null) / len(cols), 3)

        # strong-tier breakdown
        strong_in = [c for c in _STRONG_TIER if c in cols]
        strong_null = [c for c in strong_in if c in df_today.columns and df_today[c].isna().all()]
        strong_absent = [c for c in strong_in if c not in served_cols]

        report["targets"][tgt] = {
            "contract_len": len(cols), "served": len(cols) - len(absent),
            "absent": absent, "served_but_all_null": all_null,
            "imputed_to_constant_frac": imputed_frac, "order_ok": order_ok,
            "strong_tier_null_or_absent": sorted(set(strong_null) | set(strong_absent)),
        }

        md += [f"## {tgt}  (contract {len(cols)})", "",
               f"- structurally served: **{len(cols) - len(absent)}/{len(cols)}**  "
               f"(absent→0.0-fill: {len(absent)})",
               f"- served-but-ALL-NULL→constant-impute: **{len(all_null)}**  "
               f"(**{imputed_frac:.0%}** of the matrix flattened to a constant live)",
               f"- column ORDER parity: {'OK (all present, reindex preserves contract order)' if order_ok else 'BROKEN — absent cols above'}",
               f"- STRONG-TIER served null/absent: **{len(strong_null) + len(strong_absent)}/{len(strong_in)}**"
               f"{' → ' + ', '.join(sorted(set(strong_null) | set(strong_absent))) if (strong_null or strong_absent) else ''}",
               ""]
        if all_null:
            md += ["<details><summary>served-but-all-null columns (live null / train null)</summary>", ""]
            for c in sorted(all_null):
                md.append(f"  - `{c}` — train null {train_null.get(c, float('nan')):.2%}")
            md += ["", "</details>", ""]
        if absent:
            md += ["**ABSENT (silently 0.0-filled — structural gap):** " + ", ".join(f"`{c}`" for c in absent), ""]

    out_json = _OUT_DIR / f"parity_{target_date}.json"
    out_md = _OUT_DIR / f"parity_{target_date}.md"
    out_json.write_text(json.dumps(report, indent=2, default=float))
    out_md.write_text("\n".join(md))
    print(f"[parity] wrote {out_md}")
    print(f"[parity] wrote {out_json}")

    # Headline to stdout
    for tgt, r in report["targets"].items():
        print(f"  {tgt}: {r['served']}/{r['contract_len']} served | "
              f"{len(r['served_but_all_null'])} all-null→const ({r['imputed_to_constant_frac']:.0%}) | "
              f"strong-tier degraded {len(r['strong_tier_null_or_absent'])}")


if __name__ == "__main__":
    main()
