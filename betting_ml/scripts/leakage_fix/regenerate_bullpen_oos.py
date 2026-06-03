"""
regenerate_bullpen_oos.py — Leakage fix (bullpen_v2 walk-forward OOS signals)

Per game-side bullpen runs-allowed signal (LightGBM mean + global NegBin r),
leakage-free. Season-based prepare_fold; grain is (game_pk, pitching_team) →
mapped to side (home/away) via mart_game_results.home_team. Data floor follows
the bullpen_state parquet (rebuild with build_bullpen_state_dataset.py
--min-year 2016 to reach 2016). See `project_layer3_signal_leakage`.

Per eval season S: per-fold Optuna (inner walk-forward of train seasons), fit
LightGBM on [train_from..S-1], fit NegBin r on train residuals, predict S.
Emit per (game_pk, side): bullpen_mu, bullpen_dispersion (r), bullpen_uncertainty
(80% NegBin PI width).

Output: betting_ml/models/layer3/oos_signals/oos_signals_bullpen.parquet
        columns: game_pk, side, season, bullpen_mu, bullpen_dispersion, bullpen_uncertainty

Usage:
    uv run python betting_ml/scripts/leakage_fix/regenerate_bullpen_oos.py --trials 30
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.scripts.train_bullpen_distributional import (
    _load_data, _prepare_fold, _fit_negbin_r, _negbin_nll, _negbin_calib_80,
    _negbin_pi_width, _YEAR_COL,
)

_OUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals" / "oos_signals_bullpen.parquet"
_TRAIN_FROM_DEFAULT = 2016    # clamped to the parquet's actual floor
_EVAL_FROM_DEFAULT = 2021
_SEED = 42
_MIN_MU = 1e-6


def _home_team_map() -> dict[int, str]:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT game_pk, home_team FROM baseball_data.betting.mart_game_results WHERE game_type='R'")
        return {int(r[0]): r[1] for r in cur.fetchall()}
    finally:
        conn.close()


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


def _tune(df_prior: pd.DataFrame, trials: int) -> dict:
    import optuna
    import lightgbm as lgb
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    seasons = sorted(int(s) for s in df_prior[_YEAR_COL].unique())
    inner = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]
    if not inner:
        return {"num_leaves": 31, "learning_rate": 0.05, "n_estimators": 500,
                "objective": "mae", "random_state": _SEED, "verbose": -1}

    def objective(trial) -> float:
        params = _lgbm_params(trial)
        nlls = []
        for tr, te in inner:
            X_tr, y_tr, X_ev, y_ev, _ = _prepare_fold(df_prior, list(tr), te)
            m = lgb.LGBMRegressor(**params).fit(X_tr, y_tr)
            mu_tr = np.clip(m.predict(X_tr), _MIN_MU, None)
            mu_ev = np.clip(m.predict(X_ev), _MIN_MU, None)
            nlls.append(_negbin_nll(y_ev, mu_ev, _fit_negbin_r(y_tr, mu_tr)))
        return float(np.mean(nlls))

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=_SEED))
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    return {**study.best_params, "objective": "mae", "random_state": _SEED, "verbose": -1}


def regenerate(df: pd.DataFrame, home_team: dict[int, str], train_from: int,
               eval_from: int, trials: int) -> pd.DataFrame:
    import lightgbm as lgb
    df = df[df[_YEAR_COL] >= train_from].reset_index(drop=True)
    seasons = sorted(int(s) for s in df[_YEAR_COL].unique())
    eval_seasons = [s for s in seasons if s >= eval_from]
    print(f"train_from={train_from} eval_from={eval_from} trials={trials} seasons={seasons} eval={eval_seasons}")

    out: list[pd.DataFrame] = []
    for S in eval_seasons:
        train_seasons = [s for s in seasons if s < S]
        if not train_seasons:
            continue
        df_prior = df[df[_YEAR_COL] < S]
        params = _tune(df_prior, trials)
        X_tr, y_tr, X_ev, y_ev, _ = _prepare_fold(df, train_seasons, S)
        model = lgb.LGBMRegressor(**params).fit(X_tr, y_tr)
        mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
        mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
        r = _fit_negbin_r(y_tr, mu_tr)
        unc = _negbin_pi_width(mu_ev, r)

        nll, c80 = _negbin_nll(y_ev, mu_ev, r), _negbin_calib_80(y_ev, mu_ev, r)
        mae = float(np.mean(np.abs(mu_ev - y_ev)))
        print(f"  eval {S}: train {train_from}-{S-1} ({len(train_seasons)} seasons, {len(X_tr):,} rows) "
              f"→ n_eval={len(y_ev):,}  NLL={nll:.4f}  MAE={mae:.4f}  calib80={c80:.3f}  r={r:.3f}")

        # Same-filter slice aligns with mu_ev (prepare_fold builds te = df[year==S]).
        ev = df[df[_YEAR_COL] == S].reset_index(drop=True)
        assert len(ev) == len(mu_ev), f"row-order misalignment for {S}: {len(ev)} vs {len(mu_ev)}"
        side = [("home" if home_team.get(int(pk)) == pt else "away")
                for pk, pt in zip(ev["game_pk"], ev["pitching_team"])]
        sub = pd.DataFrame({
            "game_pk": ev["game_pk"].astype(int).to_numpy(),
            "side": side,
            "season": S,
            "bullpen_mu": mu_ev,
            "bullpen_dispersion": float(r),
            "bullpen_uncertainty": unc,
        })
        out.append(sub)

    if not out:
        raise RuntimeError("No eval seasons produced.")
    return pd.concat(out, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Leakage-free walk-forward bullpen_v2 OOS signals")
    ap.add_argument("--train-from", type=int, default=_TRAIN_FROM_DEFAULT)
    ap.add_argument("--eval-from", type=int, default=_EVAL_FROM_DEFAULT)
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--out", default=str(_OUT_PATH))
    args = ap.parse_args()

    print("Loading bullpen data (_load_data)...")
    df = _load_data(args.train_from)
    print(f"  {len(df):,} (game,team) rows, seasons {sorted(int(s) for s in df[_YEAR_COL].unique())}")
    print("Loading home_team map (mart_game_results)...")
    home_team = _home_team_map()

    oos = regenerate(df, home_team, args.train_from, args.eval_from, args.trials)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(args.out, index=False)
    print(f"\nWrote {len(oos):,} OOS bullpen rows → {args.out}")
    print(oos.groupby(["season", "side"]).agg(n=("game_pk", "size"),
                                               mean_mu=("bullpen_mu", "mean")).round(4).to_string())


if __name__ == "__main__":
    main()
