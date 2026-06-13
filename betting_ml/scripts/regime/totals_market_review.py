"""totals_market_review.py — Story 27.7 / 30.10 promotion diligence.

Before promoting the season-normalized totals challenger as the PROJECTION source, the operator
asked for three things the calibration gate doesn't fully surface:
  1. per-season residuals (MAE + bias + over/under split), champion vs challenger
  2. 2026-so-far behavior specifically
  3. how the model stacks up against the MARKET line (is the projection more accurate than just
     taking the consensus total? does it pick the right side of the line?)

This walk-forward-scores BOTH the deployed champion (eb_enriched v4, 369 feats) and the
season-normalized challenger (ngboost_tuned_seasonnorm, 111 feats) on the same folds the gate
uses (all_season_splits, min_train_seasons=3 → eval 2024/2025/2026), captures per-GAME predicted
means + the market line, and reports per season:

  n, model MAE vs actual, MARKET-line MAE vs actual (|line−actual|),
  model bias (mean pred−actual), market bias (mean line−actual),
  directional accuracy = P(sign(pred−line) == sign(actual−line)) over games where actual≠line
    (i.e. does the projection pick the correct side of the market total?),
  pct_over: model vs actual.

MARKET LINE: uses `total_line_consensus` (full-coverage consensus). NOT Bovada-specific — the
operator's edge/CLV work targets Bovada, but no Bovada totals loader exists in betting_ml and
consensus is the available, complete market benchmark for a projection-accuracy comparison. A
Bovada-specific pass would be a follow-up.

⚠ Directional accuracy here is a PROJECTION sanity check, NOT a betting edge claim — totals stays
bet_paused; beating the line on point-accuracy ≠ beating the closing line after vig.

Runs >1 min (Snowflake load + 2× NGBoost fits per fold). Hand off:
    uv run python betting_ml/scripts/regime/totals_market_review.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.promotion_gate_eval import _challenger_ngb, _contract_cols
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features

_TARGET = "total_runs"
_LINE = "total_line_consensus"
_CHALLENGER = "betting_ml/models/total_runs/feature_columns_ngboost_tuned_seasonnorm_2026.json"
_CHAMPION = "betting_ml/models/total_runs/feature_columns_eb_2026.json"
_CHAL_TUNING = "betting_ml/evaluation/tuning_results_ngboost_total_runs.json"


def _fit_predict(Xtr, ytr, Xev, n_estimators):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    m = NGBRegressor(n_estimators=n_estimators, Dist=Normal, verbose=False)
    m.fit(Xtr.values, ytr)
    return np.asarray(m.predict(Xev.values), float)


def _season_metrics(label, season, pred, actual, line):
    err = pred - actual
    mae = float(np.mean(np.abs(err)))
    bias = float(np.mean(err))
    has_line = ~np.isnan(line)
    n_line = int(has_line.sum())
    market_mae = float(np.mean(np.abs(line[has_line] - actual[has_line]))) if n_line else float("nan")
    market_bias = float(np.mean(line[has_line] - actual[has_line])) if n_line else float("nan")
    # directional: does the projection land on the same side of the line as the result?
    diff_pred = pred[has_line] - line[has_line]
    diff_act = actual[has_line] - line[has_line]
    push = diff_act == 0
    nz = ~push
    dir_acc = float(np.mean(np.sign(diff_pred[nz]) == np.sign(diff_act[nz]))) if nz.sum() else float("nan")
    pct_over_model = float(np.mean(pred[has_line] > line[has_line])) if n_line else float("nan")
    pct_over_actual = float(np.mean(actual[has_line] > line[has_line])) if n_line else float("nan")
    return {"model": label, "season": int(season), "n": len(actual), "n_lined": n_line,
            "mae": mae, "market_mae": market_mae, "mae_edge_vs_market": market_mae - mae,
            "bias": bias, "market_bias": market_bias,
            "dir_acc": dir_acc, "pct_over_model": pct_over_model, "pct_over_actual": pct_over_actual}


def run() -> None:
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    chal_cols = _contract_cols(_CHALLENGER, df)
    champ_cols = _contract_cols(_CHAMPION, df)
    chal_ne = _challenger_ngb(_CHAL_TUNING)["n_estimators"]
    print(f"Challenger (seasonnorm): {len(chal_cols)} feats, n_est={chal_ne}  |  "
          f"Champion (eb v4): {len(champ_cols)} feats, n_est=500")
    if _LINE not in df.columns:
        raise SystemExit(f"market line {_LINE} not in features")

    rows = []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        ev = df.loc[eval_idx]
        season = int(ev["game_year"].iloc[0])
        y_tr = df.loc[train_idx, _TARGET].values
        y_ev = ev[_TARGET].values
        line = pd.to_numeric(ev[_LINE], errors="coerce").to_numpy(dtype=float)

        Xtr_c, Xev_c = _impute(df.loc[train_idx, chal_cols], ev[chal_cols])
        Xtr_p, Xev_p = _impute(df.loc[train_idx, champ_cols], ev[champ_cols])
        print(f"  fold eval {season}: train n={len(train_idx)}  eval n={len(eval_idx)} — fitting champion + challenger...")
        pred_chal = _fit_predict(Xtr_c, y_tr, Xev_c, chal_ne)
        pred_champ = _fit_predict(Xtr_p, y_tr, Xev_p, 500)
        rows.append(_season_metrics("champion_v4", season, pred_champ, y_ev, line))
        rows.append(_season_metrics("challenger_seasonnorm", season, pred_chal, y_ev, line))

    res = pd.DataFrame(rows).sort_values(["season", "model"]).reset_index(drop=True)

    print("\n=== PER-SEASON RESIDUALS + MARKET COMPARISON ===")
    print("  (mae_edge_vs_market > 0 ⇒ model point-projection beats the consensus line; "
          "dir_acc = P(correct side of line); pct_over_model should track pct_over_actual)")
    hdr = ("season", "model", "n", "n_lined", "mae", "market_mae", "edge", "bias", "mkt_bias",
           "dir_acc", "over_m", "over_a")
    print("  {:>6} {:<22} {:>5} {:>7} {:>6} {:>10} {:>7} {:>7} {:>8} {:>7} {:>7} {:>7}".format(*hdr))
    for _, r in res.iterrows():
        print("  {:>6d} {:<22} {:>5d} {:>7d} {:>6.3f} {:>10.3f} {:>+7.3f} {:>+7.3f} {:>+8.3f} "
              "{:>7.3f} {:>7.3f} {:>7.3f}".format(
                  r["season"], r["model"], r["n"], r["n_lined"], r["mae"], r["market_mae"],
                  r["mae_edge_vs_market"], r["bias"], r["market_bias"], r["dir_acc"],
                  r["pct_over_model"], r["pct_over_actual"]))

    print("\n=== POOLED (n-weighted over folds) ===")
    for label in ("champion_v4", "challenger_seasonnorm"):
        sub = res[res["model"] == label]
        w = sub["n"].to_numpy(); wl = sub["n_lined"].to_numpy()
        pooled_mae = float(np.average(sub["mae"], weights=w))
        pooled_mkt_mae = float(np.average(sub["market_mae"], weights=wl))
        pooled_bias = float(np.average(sub["bias"], weights=w))
        pooled_dir = float(np.average(sub["dir_acc"], weights=wl))
        print(f"  {label:<22} MAE={pooled_mae:.3f}  market_MAE={pooled_mkt_mae:.3f}  "
              f"edge={pooled_mkt_mae - pooled_mae:+.3f}  bias={pooled_bias:+.3f}  dir_acc={pooled_dir:.3f}")

    out = PROJECT_ROOT / "betting_ml" / "evaluation" / "regime" / "totals_market_review.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(out, index=False)
    print(f"\nWrote {out}")
    print("\nRead: a projection source should (a) have small per-season bias incl. 2026, (b) MAE at "
          "least competitive with the market line (edge≥~0), (c) dir_acc>0.5. It need NOT beat the "
          "market after vig — totals stays bet_paused; this is point-accuracy diligence only.")


if __name__ == "__main__":
    run()
