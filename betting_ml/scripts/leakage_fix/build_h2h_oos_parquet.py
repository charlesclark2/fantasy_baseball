"""
build_h2h_oos_parquet.py — persist the leakage-free H2H OOS surface as a parquet.

The H2H analogue of `walk_forward_oos.py`'s totals surface. It reuses the exact
leakage-free walk-forward machinery from `evaluate_h2h_oos.py` (build_oos_matrix +
train_h2h folds/fit/proba) but, instead of only printing per-season aggregates,
**persists one row per market-covered game** so Layer 4 (selective strategy) can run
on it the same way it runs on `oos_predictions_totals_v1.parquet`.

Output: betting_ml/models/layer3/oos_predictions_h2h_v2.parquet  with columns
  game_pk, season, game_year, home_win (outcome),
  model_p_home_raw      — the model's out-of-fold P(home win) (leakage-free)
  market_devig_home     — de-vigged Bovada P(home win)
  model_p_home_blended  — compute_posterior(raw, market, h2h_alpha); see NOTE
  model_p_home_win      — the signal Layer 4 consumes (= model_p_home_raw)

NOTE on "blended posterior at the production alpha": the production h2h alpha is
**0.0** (best_alpha.json), and compute_posterior(·, ·, 0.0) returns the market
exactly. So a blended posterior is degenerate — it would equal market on every
game, producing ZERO Layer-4 bets (no direction flips, no magnitude triggers) and
a constant 0.0 edge. That degeneracy is itself the finding: at production alpha the
*deployed* H2H signal is pure market. To actually test whether the MODEL has
selective edge we set `model_p_home_win = model_p_home_raw` (the model's own view)
and keep the alpha-0 blend in `model_p_home_blended` for transparency.

Coverage: build_oos_matrix yields eval folds 2024–2026 (run_env 2021 floor + ≥1
prior train season at min_train_seasons=2). 2023 is not producible leakage-free
here (unlike the totals surface, whose matrix starts a season earlier).

Snowflake + walk-forward refits => HAND-OFF run (>1 min). Then run Layer 4 via:
  uv run python betting_ml/scripts/evaluation/bayesian_model_eval.py \
      --h2h-parquet betting_ml/models/layer3/oos_predictions_h2h_v2.parquet
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.leakage_fix.evaluate_h2h_oos import _build_dataset, _cv_vs_market  # noqa: E402
from betting_ml.scripts.train_h2h import (  # noqa: E402
    _fit, _proba, _tune, _folds, select_winner, _N_TRIALS,
)
from betting_ml.utils.probability_layer import compute_posterior  # noqa: E402
from betting_ml.utils.mlflow_utils import log_search_run  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_OUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_h2h_v2.parquet"
_BEST_ALPHA = _PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"


def _collect_oos_preds(kind: str, X, y, meta, params, calibrate: bool) -> pd.DataFrame:
    """Walk-forward out-of-fold predictions, one row per eval game (leakage-free:
    each game scored by a model trained only on prior seasons)."""
    rows = []
    for tr_idx, ev_idx in _folds(meta):
        model = _fit(kind, X.loc[tr_idx], y.loc[tr_idx].to_numpy(), params, calibrate)
        p_ev = _proba(model, X.loc[ev_idx])
        m = meta.loc[ev_idx]
        for pk, se, yr, pp, yy in zip(
            m["game_pk"].to_numpy(), m["season"].to_numpy(), m["game_year"].to_numpy(),
            np.asarray(p_ev, dtype=float), y.loc[ev_idx].to_numpy(),
        ):
            rows.append({"game_pk": int(pk), "season": int(se), "game_year": int(yr),
                         "model_p_home_raw": float(pp), "home_win": float(yy)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Persist leakage-free H2H OOS surface (parquet)")
    ap.add_argument("--env", default="prod")
    ap.add_argument("--trials", type=int, default=_N_TRIALS)
    ap.add_argument("--seasons", type=int, nargs="+", default=[2022, 2023, 2024, 2025, 2026])
    ap.add_argument("--both-approaches", action="store_true",
                    help="Tune elasticnet AND lightgbm and persist the winner (default: "
                         "lightgbm only — the established Approach-B winner).")
    ap.add_argument("--out", default=str(_OUT_PATH))
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()
    seasons = tuple(args.seasons)

    log.info("Building leakage-free matrix (seasons=%s)...", seasons)
    X, y, meta, prob_by_pk = _build_dataset(args.env, seasons)
    log.info("  X=%s base_rate=%.4f market_coverage=%d/%d",
             X.shape, y.mean(), len(prob_by_pk), len(y))

    if args.both_approaches:
        log.info("Tuning elasticnet + lightgbm...")
        p1 = _tune("elasticnet", X, y, meta, args.trials)
        a1 = _cv_vs_market("elasticnet", X, y, meta, p1, prob_by_pk, calibrate=False)
        p2 = _tune("lightgbm", X, y, meta, args.trials)
        a2 = _cv_vs_market("lightgbm", X, y, meta, p2, prob_by_pk, calibrate=True)
        winner, _ = select_winner(a1, a2)
        params, calibrate = (p1, False) if winner == "elasticnet" else (p2, True)
        log.info("Winner: %s (A1 ll=%.4f / A2 ll=%.4f)", winner, a1["log_loss"], a2["log_loss"])
    else:
        winner, calibrate = "lightgbm", True
        log.info("Tuning lightgbm (established Approach-B winner)...")
        params = _tune("lightgbm", X, y, meta, args.trials)

    log.info("Collecting walk-forward OOS predictions (%s)...", winner)
    oos = _collect_oos_preds(winner, X, y, meta, params, calibrate)

    # Attach market + the (degenerate-at-alpha-0) blended posterior.
    oos["market_devig_home"] = oos["game_pk"].map(prob_by_pk)
    h2h_alpha = float(json.loads(_BEST_ALPHA.read_text()).get("best_alpha", 0.0))
    oos["model_p_home_blended"] = [
        compute_posterior(r, m, h2h_alpha) if pd.notna(m) else np.nan
        for r, m in zip(oos["model_p_home_raw"], oos["market_devig_home"])
    ]
    # Layer 4 signal = the model's own view (raw); blended is pure market at alpha=0.
    oos["model_p_home_win"] = oos["model_p_home_raw"]

    # Market-covered games only (Layer 4 needs market_devig_home).
    before = len(oos)
    oos = oos.dropna(subset=["market_devig_home"]).reset_index(drop=True)
    log.info("OOS rows: %d (market-covered, dropped %d uncovered)", len(oos), before - len(oos))
    log.info("Seasons: %s", oos["season"].value_counts().sort_index().to_dict())

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(args.out, index=False)
    log.info("Wrote %s", args.out)

    # Per-season model vs market Brier (documents the contamination/degraded-line story).
    per_season = {}
    for s, g in oos.groupby("season"):
        yy = g["home_win"].to_numpy(float)
        per_season[f"model_brier_{int(s)}"] = float(np.mean((g["model_p_home_raw"].to_numpy(float) - yy) ** 2))
        per_season[f"market_brier_{int(s)}"] = float(np.mean((g["market_devig_home"].to_numpy(float) - yy) ** 2))
        per_season[f"n_{int(s)}"] = int(len(g))

    run_id = log_search_run(
        experiment="h2h_oos_surface",
        run_name=f"oos_predictions_h2h_v2_{winner}",
        params={"winner": winner, "calibrate": calibrate, "h2h_alpha": h2h_alpha,
                "n_rows": len(oos), "trials": args.trials, "seasons": str(seasons)},
        metrics=per_season,
        tags={"surface": "h2h_oos", "blended_degenerate_at_alpha0": str(h2h_alpha == 0.0)},
        artifacts=[args.out],
        enabled=not args.no_mlflow,
    )
    if run_id:
        log.info("MLflow run_id: %s", run_id)
    log.info("DONE. Run Layer 4 with:\n  uv run python betting_ml/scripts/evaluation/"
             "bayesian_model_eval.py --h2h-parquet %s", args.out)


if __name__ == "__main__":
    main()
