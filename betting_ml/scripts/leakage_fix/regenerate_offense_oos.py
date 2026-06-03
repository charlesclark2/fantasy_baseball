"""
regenerate_offense_oos.py — Leakage fix (Layer 3 in-sample signal leakage)

Walk-forward, leakage-free regeneration of the offense_v2 per-side run signals.

Root problem (see project memory `project_layer3_signal_leakage`): production
signal generators score ALL backfilled games with the FINAL sub-model trained on
2021-2025, so 2021-2025 Layer 3 features are in-sample. This regenerates the
offense signals so each season's signal comes from a model trained ONLY on prior
seasons — genuinely out-of-sample — and (per user) trains from 2016 where the
data supports it.

Scheme (per eval season S in [eval_from .. last]):
  - train LightGBM+NegBin on seasons [train_from .. S-1]
  - RE-TUNE hyperparameters per fold via Optuna on INNER walk-forward folds of the
    training seasons (eliminates hyperparameter-selection leakage too)
  - fit final model + NegBin r on training residuals; predict season S
  - emit OOS per-(game_pk, side) signals: pred_runs_mu, pred_runs_dispersion (r),
    pred_runs_uncertainty (80% NegBin PI width)

Reuses offense_v2 / offense_v1 trainer functions verbatim (same features, fold
prep, NegBin machinery) so the regenerated signals are apples-to-apples with
production, only leakage-free.

Output: betting_ml/models/layer3/oos_signals/oos_signals_offense.parquet
        columns: game_pk, side, season, pred_runs_mu, pred_runs_dispersion,
                 pred_runs_uncertainty  (consumed by the Phase 2 OOS Layer 3 matrix builder)

Usage:
    # full regeneration (HAND OFF — per-fold Optuna across seasons, minutes):
    uv run python betting_ml/scripts/leakage_fix/regenerate_offense_oos.py --trials 30
    # fewer trials / narrower window for a faster pass:
    uv run python betting_ml/scripts/leakage_fix/regenerate_offense_oos.py --trials 10 --eval-from 2024
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.scripts.offense_v1.train_offense_v1 import load_data, prepare_fold
from betting_ml.scripts.offense_v2.train_offense_v2 import (
    _make_optuna_objective, _fit_negbin_r, _negbin_nll, _calib_80,
    _MIN_MU, _LGBM_INIT_PARAMS, _OPTUNA_SEED,
)

_OUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals" / "oos_signals_offense.parquet"
_TRAIN_FROM_DEFAULT = 2016
_EVAL_FROM_DEFAULT = 2021     # Layer 3 matrix floor (run_env caps the matrix at 2021)
_INNER_MIN_TRAIN = 1          # inner walk-forward needs ≥1 train season per fold


def _tune(df_train: pd.DataFrame, inner_folds: list[tuple], trials: int) -> dict:
    """Per-fold Optuna on inner walk-forward folds; returns LightGBM params."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    objective = _make_optuna_objective("lgbm", df_train, inner_folds)
    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED))
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    return {**study.best_params, "objective": "mae", "random_state": _OPTUNA_SEED, "verbose": -1}


def regenerate(df: pd.DataFrame, train_from: int, eval_from: int, trials: int,
               inner_min_train: int = _INNER_MIN_TRAIN) -> pd.DataFrame:
    """Walk-forward OOS offense signal regeneration. df = offense load_data() frame."""
    import lightgbm as lgb

    df = df[df["game_year"] >= train_from].reset_index(drop=True)
    seasons = sorted(int(s) for s in df["game_year"].unique())
    eval_seasons = [s for s in seasons if s >= eval_from]
    print(f"train_from={train_from}  eval_from={eval_from}  trials={trials}  "
          f"seasons={seasons}  eval_seasons={eval_seasons}")

    out_frames: list[pd.DataFrame] = []
    for S in eval_seasons:
        train_idx = df.index[df["game_year"] < S]
        eval_idx = df.index[df["game_year"] == S]
        if len(train_idx) == 0 or len(eval_idx) == 0:
            continue
        df_train = df.loc[train_idx]
        inner_folds = list(all_season_splits(df_train, min_train_seasons=inner_min_train))
        params = _tune(df_train, inner_folds, trials) if inner_folds else {**_LGBM_INIT_PARAMS}

        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        model = lgb.LGBMRegressor(**params)
        model.fit(X_tr, y_tr)
        mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
        mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
        r = _fit_negbin_r(y_tr, mu_tr)
        p = r / (r + mu_ev)
        unc = nbinom.ppf(0.90, n=r, p=p) - nbinom.ppf(0.10, n=r, p=p)

        nll = _negbin_nll(y_ev, mu_ev, r)
        mae = float(np.mean(np.abs(mu_ev - y_ev)))
        c80 = _calib_80(y_ev, mu_ev, r)
        n_train_seasons = int(df_train["game_year"].nunique())
        print(f"  eval {S}: train {train_from}-{S-1} ({n_train_seasons} seasons, "
              f"{len(train_idx):,} rows, {len(inner_folds)} inner folds) → "
              f"n_eval={len(eval_idx):,}  NLL={nll:.4f}  MAE={mae:.3f}  calib80={c80:.3f}  r={r:.3f}")

        sub = df.loc[eval_idx, ["game_pk", "side", "game_year"]].reset_index(drop=True)
        sub = sub.rename(columns={"game_year": "season"})
        sub["pred_runs_mu"] = mu_ev
        sub["pred_runs_dispersion"] = float(r)
        sub["pred_runs_uncertainty"] = unc
        out_frames.append(sub)

    if not out_frames:
        raise RuntimeError("No eval seasons produced — check train_from/eval_from vs data.")
    return pd.concat(out_frames, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Leakage-free walk-forward offense_v2 OOS signals")
    ap.add_argument("--train-from", type=int, default=_TRAIN_FROM_DEFAULT,
                    help=f"Earliest training season (default {_TRAIN_FROM_DEFAULT}; clamped to data floor)")
    ap.add_argument("--eval-from", type=int, default=_EVAL_FROM_DEFAULT,
                    help=f"First OOS season to emit (default {_EVAL_FROM_DEFAULT} = Layer 3 matrix floor)")
    ap.add_argument("--trials", type=int, default=30, help="Optuna trials per fold (default 30)")
    ap.add_argument("--out", default=str(_OUT_PATH))
    args = ap.parse_args()

    print("Loading offense data (load_data)...")
    df = load_data()
    print(f"  {len(df):,} game-side rows, seasons {sorted(int(s) for s in df['game_year'].unique())}")

    oos = regenerate(df, args.train_from, args.eval_from, args.trials)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(out_path, index=False)
    print(f"\nWrote {len(oos):,} OOS offense signal rows → {out_path}")
    print(oos.groupby("season").agg(n=("game_pk", "size"),
                                    mean_mu=("pred_runs_mu", "mean"),
                                    mean_unc=("pred_runs_uncertainty", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
