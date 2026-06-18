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


def run_market(market: str, d: pd.DataFrame, *, n_buckets: int, n_trials: int) -> dict:
    spec = MARKETS[market]
    target = spec["target"]
    d = d[d[target].notna() & d[spec["open_col"]].notna()].reset_index(drop=True)
    grid = _config_grid(market)
    print(f"\n=== {market}: PBO/DSR over {len(grid)} configs ({len(d)} games) ===")

    preds = {c["name"]: _oos_predictions(d, target, c) for c in grid}
    # Align all configs on a common time order (they share eval folds → same game rows/order).
    base = preds[grid[0]["name"]]
    y = base["y"].to_numpy()
    n = len(base)
    bucket = np.minimum((np.arange(n) * n_buckets) // n, n_buckets - 1)

    # The BASELINES are configs too — adding them makes PBO adversarial (otherwise it just
    # ranks ~identical nested feature sets and reports a degenerate ≈0). drift = predict the
    # pooled mean move (the unconditional drift); no_move = predict 0.
    drift_const = float(np.mean(y))
    pred_by_col: dict[str, np.ndarray] = {c["name"]: preds[c["name"]]["pred"].to_numpy() for c in grid}
    pred_by_col["no_move"] = np.zeros(n)
    pred_by_col["drift"] = np.full(n, drift_const)
    model_cols = [c["name"] for c in grid]
    cols = model_cols + ["no_move", "drift"]

    # perf[t, config] = −MAE of that config in time-bucket t (higher is better).
    perf = np.zeros((n_buckets, len(cols)))
    pooled_mae = {}
    for j, name in enumerate(cols):
        ae = np.abs(y - pred_by_col[name])
        pooled_mae[name] = float(ae.mean())
        for t in range(n_buckets):
            m = bucket == t
            perf[t, j] = -float(ae[m].mean()) if m.any() else 0.0

    pbo = pbo_cscv(perf, higher_is_better=True, n_splits=min(n_buckets, 16))
    # The decisive read: across configs INCLUDING the baselines, who wins OOS? If a baseline
    # has the best (lowest) pooled MAE, the model adds nothing — PBO being low just means the
    # NULL is consistently best.
    best_overall = min(cols, key=lambda nm: pooled_mae[nm])
    best_model = min(model_cols, key=lambda nm: pooled_mae[nm])
    model_wins_mae = best_overall in model_cols

    # ── Directional skill vs the drift base rate (best model config) ──────────────
    pm = pred_by_col[best_model]
    moved = y != 0
    ym, pmm = y[moved], pm[moved]
    drift_dir = 1.0 if ym.mean() >= 0 else -1.0
    base_rate = float((np.sign(ym) == drift_dir).mean())          # majority-direction share
    dir_acc = float((np.sign(pmm) == np.sign(ym)).mean())
    dir_lift = dir_acc - base_rate                                # conditional skill over drift

    # ── DSR on the EXCESS return over the drift baseline (the binding edge number) ──
    # raw directional PnL = sign(pred)·move rewards merely predicting the drift direction (a
    # constant predictor scores positive). The honest series nets the always-drift bet:
    #   excess = (sign(pred) − drift_dir)·move  → 0 whenever the model agrees with the drift.
    # Its Sharpe is positive ONLY if the model's disagreements-with-drift are profitable.
    excess = (np.sign(pmm) - drift_dir) * ym
    dsr = deflated_sharpe(excess, n_trials=n_trials)
    # Reported for transparency only — drift-contaminated, do NOT gate on it.
    dsr_raw = deflated_sharpe(np.sign(pmm) * ym, n_trials=n_trials)

    edge = bool(model_wins_mae and dsr.passes_live)
    print(f"  PBO={pbo.pbo:.3f} over {len(cols)} configs (incl. baselines); "
          f"OOS-best by MAE = {best_overall}  → model_wins_MAE={model_wins_mae}")
    print(f"  dir-acc(best model)={dir_acc:.3f} vs drift base rate {base_rate:.3f}  "
          f"→ lift {dir_lift:+.3f}")
    print(f"  DSR(excess-over-drift)={dsr.dsr:.3f}  SR={dsr.observed_sr:.3f} vs SR0={dsr.sr0:.3f}"
          f"  (n_trials={n_trials})   [raw drift-contaminated DSR={dsr_raw.dsr:.3f}]")
    print(f"  → EDGE: {'YES' if edge else 'NO'} "
          f"(needs model to beat baselines on MAE AND DSR-excess≥0.95)")
    return {
        "market": market, "n_games": int(len(d)), "n_configs": len(cols),
        "pooled_mae": pooled_mae, "best_overall_config": best_overall,
        "best_model_config": best_model, "model_wins_mae": model_wins_mae,
        "dir_acc": dir_acc, "drift_base_rate": base_rate, "dir_lift": dir_lift,
        "pbo": pbo.pbo, "n_combos": pbo.n_combos,
        "dsr_excess": dsr.dsr, "dsr_excess_sr": dsr.observed_sr, "dsr_excess_sr0": dsr.sr0,
        "dsr_raw_contaminated": dsr_raw.dsr, "n_trials": n_trials,
        "edge": edge, "n_moved": int(moved.sum()),
        "_pbo_obj": pbo, "_dsr_obj": dsr,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["h2h", "totals", "all"], default="all")
    ap.add_argument("--n-buckets", type=int, default=12)
    # The program has run 13+ no-edge searches with many configs each. n_trials deflates the
    # benchmark for that multiple testing; 5 (the grid size) grossly under-deflates. 50 is a
    # defensible floor for the program-wide trial count.
    ap.add_argument("--n-trials", type=int, default=50)
    ap.add_argument("--refresh-cache", action="store_true")
    args = ap.parse_args()

    d = get_cached_df("edge_e31_line_movement", load_line_movement_dataset,
                      refresh=args.refresh_cache)
    markets = ["h2h", "totals"] if args.market == "all" else [args.market]
    results = {m: run_market(m, d, n_buckets=args.n_buckets, n_trials=args.n_trials)
               for m in markets}

    # Dashboard verdict gates on the EXCESS-over-drift DSR (the _dsr_obj is that one), so the
    # standing report reflects the honest edge test, not the drift-contaminated raw Sharpe.
    entries = [{
        "strategy": f"E3.1 Head-1 line-movement ({m})", "stage": "proposed",
        "pbo": r["_pbo_obj"], "dsr": r["_dsr_obj"],
        "live_clv": None if r["edge"] else False,
        "notes": f"OOS-best by MAE={r['best_overall_config']} (model_wins_MAE={r['model_wins_mae']}); "
                 f"dir-lift over drift {r['dir_lift']:+.3f}; DSR-excess {r['dsr_excess']:.3f} "
                 f"(raw drift-contaminated {r['dsr_raw_contaminated']:.3f}) — no robust edge",
    } for m, r in results.items()]
    _DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    _DASHBOARD.write_text(render_overfitting_dashboard(entries))
    _JSON.parent.mkdir(parents=True, exist_ok=True)
    _JSON.write_text(json.dumps({m: {k: v for k, v in r.items() if not k.startswith("_")}
                                 for m, r in results.items()}, indent=2, default=float))
    print(f"\nWrote {_DASHBOARD}\nWrote {_JSON}")
    print("\n=== E1.4 VERDICT (Head-1, drift-adjusted) ===")
    for m, r in results.items():
        print(f"  {m:7s}: PBO={r['pbo']:.3f}  dir-lift={r['dir_lift']:+.3f}  "
              f"DSR-excess={r['dsr_excess']:.3f}  → EDGE: {'YES' if r['edge'] else 'NO'}")


if __name__ == "__main__":
    main()
