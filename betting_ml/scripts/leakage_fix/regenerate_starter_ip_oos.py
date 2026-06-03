"""
regenerate_starter_ip_oos.py — Leakage fix (starter_ip_v1 walk-forward OOS signals)

Per game-side starter innings-pitched signal (LightGBM mean + NegBin r-by-decile),
leakage-free. Idx-based prepare_fold (mirrors offense). Data floor 2020.
See `project_layer3_signal_leakage`.

Per eval season S: per-fold Optuna (inner walk-forward of train seasons), fit
LightGBM on [train_from..S-1], fit NegBin r-by-decile on train residuals, predict
S. Emit per (game_pk, side): starter_ip_mu, starter_ip_dispersion (per-row r),
starter_ip_uncertainty (per-row 80% NegBin PI width).

Output: betting_ml/models/layer3/oos_signals/oos_signals_starter_ip.parquet
        columns: game_pk, side, season, starter_ip_mu, starter_ip_dispersion, starter_ip_uncertainty

Usage:
    uv run python betting_ml/scripts/leakage_fix/regenerate_starter_ip_oos.py --trials 30
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.scripts.starter_v1.train_starter_ip_v1 import (
    load_data, prepare_fold, fit_negbin_r_by_decile, assign_r, negbin_nll, negbin_calib_80,
)

_OUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals" / "oos_signals_starter_ip.parquet"
_TRAIN_FROM_DEFAULT = 2020
_EVAL_FROM_DEFAULT = 2021
_SEED = 42
_MIN_MU = 1e-6


def _lgbm_params(trial) -> dict:
    return {
        "num_leaves":        trial.suggest_int("num_leaves", 15, 127),
        "learning_rate":     trial.suggest_float("learning_rate", 0.005, 0.15, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 80),
        "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.4, 1.0),
        "n_estimators":      trial.suggest_int("n_estimators", 100, 800, step=50),
        "objective": "mae", "random_state": _SEED, "verbose": -1,
    }


def _r_for(y_tr, mu_tr, mu_ev) -> np.ndarray:
    r_by_decile, interior = fit_negbin_r_by_decile(y_tr, mu_tr)
    return assign_r(mu_ev, interior, r_by_decile)


def _tune(df_train: pd.DataFrame, inner_folds: list[tuple], trials: int) -> dict:
    import optuna
    import lightgbm as lgb
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial) -> float:
        params = _lgbm_params(trial)
        nlls = []
        for tr_idx, ev_idx in inner_folds:
            X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df_train, tr_idx, ev_idx)
            m = lgb.LGBMRegressor(**params).fit(X_tr, y_tr)
            mu_tr = np.clip(m.predict(X_tr), _MIN_MU, None)
            mu_ev = np.clip(m.predict(X_ev), _MIN_MU, None)
            nlls.append(negbin_nll(y_ev, mu_ev, _r_for(y_tr, mu_tr, mu_ev)))
        return float(np.mean(nlls))

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=_SEED))
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    return {**study.best_params, "objective": "mae", "random_state": _SEED, "verbose": -1}


def regenerate(df: pd.DataFrame, train_from: int, eval_from: int, trials: int) -> pd.DataFrame:
    import lightgbm as lgb
    df = df[df["game_year"] >= train_from].reset_index(drop=True)
    seasons = sorted(int(s) for s in df["game_year"].unique())
    eval_seasons = [s for s in seasons if s >= eval_from]
    print(f"train_from={train_from} eval_from={eval_from} trials={trials} seasons={seasons} eval={eval_seasons}")

    out: list[pd.DataFrame] = []
    for S in eval_seasons:
        train_idx = df.index[df["game_year"] < S]
        eval_idx = df.index[df["game_year"] == S]
        if len(train_idx) == 0 or len(eval_idx) == 0:
            continue
        df_train = df.loc[train_idx]
        inner = list(all_season_splits(df_train, min_train_seasons=1))
        params = _tune(df_train, inner, trials) if inner else \
            {"num_leaves": 63, "learning_rate": 0.05, "n_estimators": 500,
             "objective": "mae", "random_state": _SEED, "verbose": -1}

        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        model = lgb.LGBMRegressor(**params).fit(X_tr, y_tr)
        mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
        mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
        r_ev = _r_for(y_tr, mu_tr, mu_ev)
        p = r_ev / (r_ev + mu_ev)
        unc = nbinom.ppf(0.90, n=r_ev, p=p) - nbinom.ppf(0.10, n=r_ev, p=p)

        nll, c80 = negbin_nll(y_ev, mu_ev, r_ev), negbin_calib_80(y_ev, mu_ev, r_ev)
        mae = float(np.mean(np.abs(mu_ev - y_ev)))
        print(f"  eval {S}: train {train_from}-{S-1} ({df_train['game_year'].nunique()} seasons, "
              f"{len(train_idx):,} rows) → n_eval={len(eval_idx):,}  NLL={nll:.4f}  MAE={mae:.4f}  "
              f"calib80={c80:.3f}  mean_r={float(np.mean(r_ev)):.3f}")

        sub = df.loc[eval_idx, ["game_pk", "side", "game_year"]].reset_index(drop=True)
        sub = sub.rename(columns={"game_year": "season"})
        sub["starter_ip_mu"] = mu_ev
        sub["starter_ip_dispersion"] = r_ev
        sub["starter_ip_uncertainty"] = unc
        out.append(sub)

    if not out:
        raise RuntimeError("No eval seasons produced.")
    return pd.concat(out, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Leakage-free walk-forward starter_ip_v1 OOS signals")
    ap.add_argument("--train-from", type=int, default=_TRAIN_FROM_DEFAULT)
    ap.add_argument("--eval-from", type=int, default=_EVAL_FROM_DEFAULT)
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--out", default=str(_OUT_PATH))
    args = ap.parse_args()

    print("Loading starter IP data (load_data)...")
    df = load_data()
    print(f"  {len(df):,} game-side rows, seasons {sorted(int(s) for s in df['game_year'].unique())}")
    oos = regenerate(df, args.train_from, args.eval_from, args.trials)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(args.out, index=False)
    print(f"\nWrote {len(oos):,} OOS starter-IP rows → {args.out}")
    print(oos.groupby("season").agg(n=("game_pk", "size"),
                                    mean_mu=("starter_ip_mu", "mean")).round(4).to_string())


if __name__ == "__main__":
    main()
