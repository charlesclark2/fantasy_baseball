"""rebaseline_purged_cv.py — Epic E1.5: re-baseline the champions honestly.

Re-scores each production champion (`home_win` v5, `run_differential` v5, `total_runs`)
through THREE cross-validation regimes on the SAME folds and the SAME recipe:

  1. **standard** — the legacy season-forward split (`all_season_splits`), the optimistic
     baseline that current champion metrics were measured under.
  2. **purged**   — the purged + embargoed walk-forward CV (E1.1). Drops the prior-season
     boundary band that carries forward into the eval season's rolling features.
  3. **purged+weighted** — purged CV with AFML sample-uniqueness weights (E1.2).

The champion recipe is held FIXED across all three; only the CV changes. So the metric
change `standard → purged` is the **leakage estimate**: how much of the champion's apparent
accuracy was near-boundary fold leakage rather than real skill. That purged number is the
honest baseline the Edge models (E2–E4) must beat under `evaluate_promotion`.

Output: `ablation_results/purged_cv_recalibration.md` + a JSON sidecar. Any champion whose
edge-vs-market story depended on the near-boundary folds is flagged (purge delta > the
metric noise floor).

Runtime: retrains each champion recipe × folds × 3 regimes — minutes (NGBoost dominates).
HAND OFF to run with Snowflake creds. One `--target` per invocation is parallelizable;
`--target all` runs the three serially. Writes nothing to prod.

Usage:
    uv run python betting_ml/scripts/rebaseline_purged_cv.py --target all
    uv run python betting_ml/scripts/rebaseline_purged_cv.py --target total_runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.promotion_gate_eval import (
    _TARGETS, _build_specs, _contract_cols, _reconstruct_champion_cols, make_gate_splitter,
)
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.promotion_gate import NOISE_FLOOR
from betting_ml.utils.sample_uniqueness import compute_sample_uniqueness
from betting_ml.utils.training_cache import get_cached_df

_REPORT = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "purged_cv_recalibration.md"
_JSON = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "purged_cv_recalibration.json"


def _champion_cols(name: str, cfg: dict, df: pd.DataFrame) -> list[str]:
    if cfg["champion_kind"] == "reconstruct":
        return _reconstruct_champion_cols(df)
    return _contract_cols(cfg["champion_contract"], df)


def _eval_champion(df, name, cfg, *, splitter, uniqueness_weight: bool, champ_cols) -> dict:
    """Score the champion recipe per game across a splitter's folds; return per-season +
    pooled mean of the target metric (lower = better)."""
    champion, _ = _build_specs(name, cfg)
    metric = cfg["metric"]
    target_col = cfg["target_col"]
    seasons, scores = [], []
    per_season = []
    for train_idx, eval_idx in splitter(df):
        yr = int(df.loc[eval_idx, "game_year"].mode().iloc[0])
        ytr = df.loc[train_idx, target_col].values
        yev = df.loc[eval_idx, target_col].values
        sw = compute_sample_uniqueness(df.loc[train_idx, "game_date"]) if uniqueness_weight else None
        Xtr, Xev = _impute(df.loc[train_idx, champ_cols], df.loc[eval_idx, champ_cols])
        out = champion.fit_predict(Xtr, ytr, Xev, yev, sample_weight=sw)
        s = out.score_to_truth(yev, metric)
        seasons.append(np.full(len(s), yr)); scores.append(s)
        per_season.append({"season": yr, "n": int(len(s)), "score": float(s.mean()),
                           "n_train": int(len(Xtr))})
    season = np.concatenate(seasons); score = np.concatenate(scores)
    return {"recipe": champion.name, "metric": metric, "pooled": float(score.mean()),
            "per_season": per_season, "_season": season, "_score": score}


def run(target: str, df: pd.DataFrame, *, embargo_days: int) -> dict:
    cfg = _TARGETS[target]
    champ_cols = _champion_cols(target, cfg, df)
    feat_set = set(champ_cols)
    metric = cfg["metric"]
    floor = NOISE_FLOOR.get(metric, 0.0)
    print(f"\n=== {target} re-baseline ({metric}, champion={len(champ_cols)} feats) ===")

    std_split, _ = make_gate_splitter(False)
    pur_split, pur_obj = make_gate_splitter(True, feature_cols=feat_set, embargo_days=embargo_days)
    # purged+weighted reuses a fresh purged splitter (the object tracks last_stats per run)
    purw_split, _ = make_gate_splitter(True, feature_cols=feat_set, embargo_days=embargo_days)

    print("  [1/3] standard season-forward CV ...")
    std = _eval_champion(df, target, cfg, splitter=std_split, uniqueness_weight=False, champ_cols=champ_cols)
    print("  [2/3] purged + embargoed CV (E1.1) ...")
    pur = _eval_champion(df, target, cfg, splitter=pur_split, uniqueness_weight=False, champ_cols=champ_cols)
    print("  [3/3] purged + uniqueness-weighted CV (E1.1+E1.2) ...")
    purw = _eval_champion(df, target, cfg, splitter=purw_split, uniqueness_weight=True, champ_cols=champ_cols)

    leakage = pur["pooled"] - std["pooled"]          # >0 ⇒ purged is WORSE ⇒ optimism removed
    weight_delta = purw["pooled"] - pur["pooled"]
    flagged = leakage > floor
    purge_drops = [{"eval_year": s.eval_year, "n_dropped": s.n_dropped,
                    "frac_dropped": round(s.frac_dropped, 4), "purge_days": s.purge_days,
                    "n_train_raw": s.n_train_raw} for s in (pur_obj.last_stats or [])]
    print(f"  pooled {metric}: standard={std['pooled']:.4f}  purged={pur['pooled']:.4f}  "
          f"purged+wt={purw['pooled']:.4f}")
    print(f"  → leakage estimate (purged−standard) = {leakage:+.4f}  "
          f"(noise floor {floor}; {'FLAGGED' if flagged else 'within noise'})")
    return {
        "target": target, "metric": metric, "noise_floor": floor,
        "n_champion_features": len(champ_cols), "champion_recipe": std["recipe"],
        "standard_pooled": std["pooled"], "purged_pooled": pur["pooled"],
        "purged_weighted_pooled": purw["pooled"],
        "leakage_estimate": leakage, "weight_delta": weight_delta,
        "leakage_flagged": bool(flagged),
        "per_season": {"standard": std["per_season"], "purged": pur["per_season"],
                       "purged_weighted": purw["per_season"]},
        "purge_drops": purge_drops,
    }


def _write_report(results: dict) -> None:
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _JSON.parent.mkdir(parents=True, exist_ok=True)
    _JSON.write_text(json.dumps(results, indent=2, default=float))
    lines = [
        "# Purged-CV Re-baseline of the Champions (Epic E1.5)",
        "",
        "Each champion recipe re-scored on identical folds under three CV regimes — only the "
        "CV changes, the recipe is fixed. **Leakage estimate = purged − standard** (positive ⇒ "
        "the standard split was optimistic). The **purged** column is the honest baseline the "
        "Edge models (E2–E4) must beat via `evaluate_promotion`.",
        "",
        "| target | metric | standard | purged | purged+wt | leakage (purged−std) | flagged? |",
        "|---|---|---|---|---|---|---|",
    ]
    for t, r in results.items():
        flag = "⚠️ yes" if r["leakage_flagged"] else "no"
        lines.append(f"| {t} | {r['metric']} | {r['standard_pooled']:.4f} | {r['purged_pooled']:.4f} | "
                     f"{r['purged_weighted_pooled']:.4f} | {r['leakage_estimate']:+.4f} "
                     f"(floor {r['noise_floor']}) | {flag} |")
    lines += ["",
              "_`purged+wt` adds AFML sample-uniqueness weights (E1.2) on top of the purged CV. "
              "`flagged` = leakage exceeds the metric noise floor → that champion's edge story "
              "leaned on near-boundary folds; re-examine before trusting it as the Edge baseline._",
              ""]
    for t, r in results.items():
        lines += [f"## {t}", "",
                  f"- champion recipe: `{r['champion_recipe']}` · {r['n_champion_features']} features",
                  f"- weight effect (purged+wt − purged): {r['weight_delta']:+.4f}", ""]
        drops = r["purge_drops"]
        if drops:
            lines.append("Purge band per fold (E1.1):")
            lines.append("")
            lines.append("| eval year | purge days | train raw | dropped | frac |")
            lines.append("|---|---|---|---|---|")
            for d in drops:
                lines.append(f"| {d['eval_year']} | {d['purge_days']} | {d['n_train_raw']} | "
                             f"{d['n_dropped']} | {d['frac_dropped']:.1%} |")
            lines.append("")
        lines.append("Per-season pooled metric (lower = better):")
        lines.append("")
        lines.append("| season | standard | purged | purged+wt |")
        lines.append("|---|---|---|---|")
        std_by = {s["season"]: s for s in r["per_season"]["standard"]}
        pur_by = {s["season"]: s for s in r["per_season"]["purged"]}
        purw_by = {s["season"]: s for s in r["per_season"]["purged_weighted"]}
        for yr in sorted(std_by):
            lines.append(f"| {yr} | {std_by[yr]['score']:.4f} | "
                         f"{pur_by.get(yr, {}).get('score', float('nan')):.4f} | "
                         f"{purw_by.get(yr, {}).get('score', float('nan')):.4f} |")
        lines.append("")
    _REPORT.write_text("\n".join(lines))
    print(f"\nWrote {_REPORT}")
    print(f"Wrote {_JSON}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs", "all"], default="all")
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--refresh-cache", action="store_true")
    args = ap.parse_args()

    df = get_cached_df("edge_e1_training", load_features, refresh=args.refresh_cache).reset_index(drop=True)
    print(f"Loaded {len(df)} rows; seasons {sorted(df['game_year'].dropna().unique().tolist())}")
    targets = ["home_win", "run_diff", "total_runs"] if args.target == "all" else [args.target]
    results = {t: run(t, df, embargo_days=args.embargo_days) for t in targets}
    _write_report(results)
    print("\n=== LEAKAGE ESTIMATES ===")
    for t, r in results.items():
        print(f"  {t:12s} {r['metric']}: standard={r['standard_pooled']:.4f} → "
              f"purged={r['purged_pooled']:.4f}  leakage={r['leakage_estimate']:+.4f}"
              f"  {'⚠️ FLAGGED' if r['leakage_flagged'] else ''}")


if __name__ == "__main__":
    main()
