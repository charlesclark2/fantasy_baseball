"""pbo_line_movement_head1.py — Epic E1.4 applied to the E3.1 Head-1 search.

Formalizes the E3.1 "no edge" read into the program's go-live numbers: a Probability of
Backtest Overfitting (PBO via CSCV) and a Deflated Sharpe (DSR) on record, written to the
standing `ablation_results/overfitting_dashboard.md`.

WHY a GRID (not the single model): PBO measures whether the IN-SAMPLE-best CONFIG keeps its
edge OUT-OF-SAMPLE. That needs ≥2 candidate configs scored across time sub-periods. We score
the natural Head-1 search grid — feature-set variants (microstructure-only → +anchor → +sharp
→ full) × two NGBoost settings — over the E1.1 purged folds, bucket the OOS predictions by
time, and run `pbo_cscv` on the (bucket × config) −MAE matrix. PBO→0.5 ⇒ picking the "best"
line-movement config is selection noise.

DSR: the directional bet that a CLV strategy would actually place — bet the predicted move
direction, capture the realized favorable line move — has per-game PnL `return = sign(pred)·move`.
`deflated_sharpe` deflates that series' Sharpe by the number of configs tried (a floor on the
true multiple-testing count) and its non-normality. DSR < 0.95 ⇒ not live-eligible.

GATES (E1.4): ship→shadow PBO<0.5; shadow→live PBO<0.2 AND DSR≥0.95 AND live-CLV. We expect
Head-1 to FAIL — this puts a defensible number on that. Writes nothing to prod.

Runtime: grid(≈5) × folds(3) × markets(2) NGBoost fits — a few minutes. HAND OFF with creds.

Usage:
    uv run python betting_ml/scripts/pbo_line_movement_head1.py
    uv run python betting_ml/scripts/pbo_line_movement_head1.py --market h2h --n-buckets 12
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

from betting_ml.models.total_runs_trainer import train_ngboost
from betting_ml.scripts.train_line_movement_head1 import (
    MARKETS, _impute, load_line_movement_dataset,
)
from betting_ml.utils.cv import make_purged_splitter
from betting_ml.utils.overfitting import (
    deflated_sharpe, pbo_cscv, render_overfitting_dashboard,
)
from betting_ml.utils.training_cache import get_cached_df

_DASHBOARD = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "overfitting_dashboard.md"
_JSON = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "pbo_line_movement_head1.json"


def _config_grid(market: str) -> list[dict]:
    """The natural Head-1 search space for this market (the configs PBO selects among)."""
    spec = MARKETS[market]
    ms = spec["multi_season"]
    enr = spec["enrichment"]
    anchor = [c for c in enr if "anchor" in c or c in ("consensus_win_prob", "pred_total_runs")]
    sharp = [c for c in enr if "sharp" in c or "pinnacle" in c]
    full = ms + enr
    return [
        {"name": "microstructure", "feats": ms, "n_est": 300, "lr": 0.1},
        {"name": "micro+anchor", "feats": ms + anchor, "n_est": 300, "lr": 0.1},
        {"name": "micro+sharp", "feats": ms + sharp, "n_est": 300, "lr": 0.1},
        {"name": "full", "feats": full, "n_est": 300, "lr": 0.1},
        {"name": "full_lowLR", "feats": full, "n_est": 150, "lr": 0.03},
    ]


def _oos_predictions(d: pd.DataFrame, target: str, cfg: dict) -> pd.DataFrame:
    """Per-game OOS predictions for one config across the purged folds."""
    _, splitter = make_purged_splitter(feature_cols=cfg["feats"])
    rows = []
    for train_idx, eval_idx in splitter(d):
        ytr = d.loc[train_idx, target].to_numpy()
        Xtr, Xev = _impute(d.loc[train_idx, cfg["feats"]], d.loc[eval_idx, cfg["feats"]])
        out = train_ngboost(Xtr, pd.Series(ytr), Xev, dist="Normal", n_estimators=cfg["n_est"])
        pred = np.asarray(out["y_pred"])
        rows.append(pd.DataFrame({
            "game_date": d.loc[eval_idx, "game_date"].values,
            "y": d.loc[eval_idx, target].values, "pred": pred,
        }))
    return pd.concat(rows, ignore_index=True).sort_values("game_date").reset_index(drop=True)


def run_market(market: str, d: pd.DataFrame, *, n_buckets: int) -> dict:
    spec = MARKETS[market]
    target = spec["target"]
    d = d[d[target].notna() & d[spec["open_col"]].notna()].reset_index(drop=True)
    grid = _config_grid(market)
    print(f"\n=== {market}: PBO/DSR over {len(grid)} configs ({len(d)} games) ===")

    preds = {c["name"]: _oos_predictions(d, target, c) for c in grid}
    # Align all configs on a common time order (they share eval folds → same game rows/order).
    base = preds[grid[0]["name"]]
    n = len(base)
    bucket = np.minimum((np.arange(n) * n_buckets) // n, n_buckets - 1)

    # perf[t, config] = −MAE of that config in time-bucket t (higher is better).
    perf = np.zeros((n_buckets, len(grid)))
    pooled_mae = {}
    for j, c in enumerate(grid):
        p = preds[c["name"]]
        ae = np.abs(p["y"].to_numpy() - p["pred"].to_numpy())
        pooled_mae[c["name"]] = float(ae.mean())
        for t in range(n_buckets):
            m = bucket == t
            perf[t, j] = -float(ae[m].mean()) if m.any() else 0.0

    pbo = pbo_cscv(perf, higher_is_better=True, n_splits=min(n_buckets, 16))

    # DSR on the best config's directional CLV-PnL: bet the predicted move, capture the move.
    best = min(grid, key=lambda c: pooled_mae[c["name"]])["name"]
    bp = preds[best]
    moved = bp["y"].to_numpy() != 0
    ret = np.sign(bp["pred"].to_numpy()[moved]) * bp["y"].to_numpy()[moved]
    dsr = deflated_sharpe(ret, n_trials=len(grid))   # n_trials = grid size (a floor)

    print(f"  PBO={pbo.pbo:.3f} (ship→shadow<0.5: {pbo.ships_to_shadow})  "
          f"best config={best} (MAE {pooled_mae[best]:.4f})")
    print(f"  DSR={dsr.dsr:.3f}  SR={dsr.observed_sr:.3f} vs deflated SR0={dsr.sr0:.3f}  "
          f"live(≥0.95)={dsr.passes_live}")
    return {
        "market": market, "n_games": int(len(d)), "n_configs": len(grid),
        "pooled_mae": pooled_mae, "best_config": best,
        "pbo": pbo.pbo, "pbo_ships_to_shadow": pbo.ships_to_shadow,
        "pbo_clears_live": pbo.clears_live_pbo, "n_combos": pbo.n_combos,
        "dsr": dsr.dsr, "observed_sr": dsr.observed_sr, "deflated_sr0": dsr.sr0,
        "dsr_passes_live": dsr.passes_live, "n_moved": int(moved.sum()),
        "_pbo_obj": pbo, "_dsr_obj": dsr,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["h2h", "totals", "all"], default="all")
    ap.add_argument("--n-buckets", type=int, default=12)
    ap.add_argument("--refresh-cache", action="store_true")
    args = ap.parse_args()

    d = get_cached_df("edge_e31_line_movement", load_line_movement_dataset,
                      refresh=args.refresh_cache)
    markets = ["h2h", "totals"] if args.market == "all" else [args.market]
    results = {m: run_market(m, d, n_buckets=args.n_buckets) for m in markets}

    entries = [{
        "strategy": f"E3.1 Head-1 line-movement ({m})", "stage": "proposed",
        "pbo": r["_pbo_obj"], "dsr": r["_dsr_obj"], "live_clv": None,
        "notes": f"best={r['best_config']}; MAE {r['pooled_mae'][r['best_config']]:.4f}; "
                 f"loses to no-move (E3.1) — directional skill ≈ drift base rate",
    } for m, r in results.items()]
    _DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    _DASHBOARD.write_text(render_overfitting_dashboard(entries))
    _JSON.parent.mkdir(parents=True, exist_ok=True)
    _JSON.write_text(json.dumps({m: {k: v for k, v in r.items() if not k.startswith("_")}
                                 for m, r in results.items()}, indent=2, default=float))
    print(f"\nWrote {_DASHBOARD}\nWrote {_JSON}")
    print("\n=== E1.4 VERDICT (Head-1) ===")
    for m, r in results.items():
        verdict = "HOLD" if r["pbo"] >= 0.5 else ("LIVE-elig" if (r["pbo_clears_live"] and r["dsr_passes_live"]) else "SHADOW-elig")
        print(f"  {m:7s}: PBO={r['pbo']:.3f}  DSR={r['dsr']:.3f}  → {verdict}")


if __name__ == "__main__":
    main()
