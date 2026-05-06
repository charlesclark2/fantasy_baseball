"""Card 7.V Task 2 — small-scale total_runs retrain experiments.

Trains four NGBoost configurations on 2021–2024 game data and evaluates on the
2025 holdout. Reports the four metrics that diagnose the v1 failure mode:
    - cv_mae           (lower is better)
    - std_pred         (target ≥ 2.0)
    - mean_residual    (target |x| ≤ 0.5)
    - pct_pred_over    (target ≥ 25%, computed against 2025 consensus lines
                        when available; falls back to 8.0 sentinel line)

Run from project root:
    uv run python betting_ml/scripts/prototype_total_runs_experiments.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline


_HOLDOUT_YEAR = 2025

_RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "prototype_total_runs_results.json"

_LINE_QUERY = """
SELECT game_pk, AVG(total_line_consensus) AS line
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_year = {year} AND total_line_consensus IS NOT NULL
GROUP BY game_pk
"""


def _load_holdout_lines(year: int) -> dict[int, float]:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_LINE_QUERY.format(year=year))
        return {int(r[0]): float(r[1]) for r in cur.fetchall() if r[1] is not None}
    finally:
        conn.close()


def _fit_one(X_train, y_train, X_eval, dist_name: str, max_depth: int, n_estimators: int):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal, LogNormal
    from sklearn.tree import DecisionTreeRegressor

    dist_cls = {"Normal": Normal, "LogNormal": LogNormal}[dist_name]
    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=max_depth)
    ngb = NGBRegressor(
        Dist=dist_cls,
        n_estimators=n_estimators,
        Base=base,
        verbose=False,
    )
    t0 = time.time()
    ngb.fit(X_train, y_train)
    dur = time.time() - t0
    pred = ngb.predict(X_eval)
    return ngb, pred, dur


def main() -> None:
    print("Loading historical features (2021+)...")
    df = load_features(min_games_played=15)
    print(f"  Loaded {len(df):,} rows; seasons {sorted(df['game_year'].unique())}")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    print(f"  Using {len(feature_cols)} retained features")

    train_idx = df.index[(df["game_year"] >= 2021) & (df["game_year"] <= 2024)]
    eval_idx  = df.index[df["game_year"] == _HOLDOUT_YEAR]
    print(f"  Train rows (2021–2024): {len(train_idx):,}")
    print(f"  Eval rows (2025): {len(eval_idx):,}")

    X_train_raw = df.loc[train_idx, feature_cols]
    X_eval_raw  = df.loc[eval_idx, feature_cols]
    y_train = df.loc[train_idx, "total_runs"].values
    y_eval  = df.loc[eval_idx, "total_runs"].values

    pipeline = build_imputation_pipeline()
    X_train_imp = pipeline.fit_transform(X_train_raw)
    X_train_imp = X_train_imp.select_dtypes(include=[np.number])
    X_eval_imp  = pipeline.transform(X_eval_raw)
    X_eval_imp  = X_eval_imp.reindex(columns=X_train_imp.columns, fill_value=0.0)

    print("Loading 2025 consensus lines for pct_pred_over computation...")
    lines = _load_holdout_lines(_HOLDOUT_YEAR)
    eval_pks = df.loc[eval_idx, "game_pk"].astype(int).values
    line_arr = np.array([lines.get(pk, np.nan) for pk in eval_pks])
    fallback_line = 8.0
    line_eval = np.where(np.isnan(line_arr), fallback_line, line_arr)
    n_with_line = int(np.sum(~np.isnan(line_arr)))
    print(f"  {n_with_line}/{len(eval_pks)} eval rows have a consensus line; "
          f"using 8.0 sentinel for the rest")

    experiments = [
        {"id": "A", "dist": "LogNormal", "max_depth": 3, "n_estimators": 500,
         "desc": "Reproduce v1 baseline behavior"},
        {"id": "B", "dist": "Normal",    "max_depth": 3, "n_estimators": 500,
         "desc": "Isolate LogNormal vs Normal effect"},
        {"id": "C", "dist": "Normal",    "max_depth": 8, "n_estimators": 200,
         "desc": "Chosen approach: Normal + deeper trees"},
        {"id": "D", "dist": "LogNormal", "max_depth": 8, "n_estimators": 200,
         "desc": "Deeper trees alone (keep LogNormal)"},
    ]

    results = []
    Xtr_v = X_train_imp.values
    Xev_v = X_eval_imp.values

    for exp in experiments:
        print(f"\n=== Experiment {exp['id']}: dist={exp['dist']}, "
              f"max_depth={exp['max_depth']}, n_estimators={exp['n_estimators']} ===")
        try:
            _, pred, dur = _fit_one(
                Xtr_v, y_train, Xev_v,
                dist_name=exp["dist"],
                max_depth=exp["max_depth"],
                n_estimators=exp["n_estimators"],
            )
            mae = float(np.mean(np.abs(pred - y_eval)))
            std_pred = float(np.std(pred))
            mean_resid = float(np.mean(pred - y_eval))
            pct_over = float(np.mean(pred > line_eval))
            print(f"  fit time: {dur:.1f}s")
            print(f"  cv_mae:        {mae:.4f}")
            print(f"  std_pred:      {std_pred:.4f}")
            print(f"  mean_residual: {mean_resid:+.4f}")
            print(f"  pct_pred_over: {pct_over*100:.1f}%")

            results.append({
                **exp,
                "fit_time_sec": dur,
                "mae_2025": mae,
                "std_pred": std_pred,
                "mean_residual": mean_resid,
                "pct_pred_over": pct_over,
                "viable": True,
            })
        except Exception as exc:
            print(f"  FAILED: {exc}")
            results.append({**exp, "viable": False, "error": str(exc)})

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {_RESULTS_PATH}")

    print("\n=== Summary ===")
    print(f"{'Exp':>3}  {'Dist':>10}  {'depth':>5}  {'n_est':>5}  "
          f"{'MAE':>7}  {'Std':>6}  {'MeanRes':>8}  {'%Over':>6}")
    for r in results:
        if not r.get("viable"):
            print(f"{r['id']:>3}  {r['dist']:>10}  {r['max_depth']:>5}  "
                  f"{r['n_estimators']:>5}  FAILED")
            continue
        print(f"{r['id']:>3}  {r['dist']:>10}  {r['max_depth']:>5}  "
              f"{r['n_estimators']:>5}  {r['mae_2025']:>7.4f}  "
              f"{r['std_pred']:>6.3f}  {r['mean_residual']:>+8.3f}  "
              f"{r['pct_pred_over']*100:>5.1f}%")


if __name__ == "__main__":
    main()
