"""
regenerate_run_env_oos.py — Leakage fix (run_env_v4 walk-forward OOS signals)

Per-game run-environment signal, leakage-free. run_env_v4 is Ridge+NegBin with
alpha chosen on NLL, so per-fold "re-tuning" is an alpha grid search on inner
walk-forward folds of the training seasons. Data floor is 2021 (weather/umpire
coverage — cannot reach 2016; documented), so eval starts 2022.

See `project_layer3_signal_leakage`. Reuses run_env trainer functions verbatim.

Scheme (per eval season S): train Ridge on seasons [train_from..S-1] (alpha
grid-searched on inner walk-forward folds of those seasons), fit NegBin r on
train residuals, predict S. Emit per-game: run_env_mu, run_env_dispersion (r),
run_env_uncertainty (80% NegBin PI width).

Output: betting_ml/models/layer3/oos_signals/oos_signals_run_env.parquet
        columns: game_pk, season, run_env_mu, run_env_dispersion, run_env_uncertainty

Usage:
    uv run python betting_ml/scripts/leakage_fix/regenerate_run_env_oos.py
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

from betting_ml.scripts.train_run_env import load_training_data
from betting_ml.scripts.train_run_env_v3 import _prepare_fold
from betting_ml.scripts.train_run_env_v4 import (
    _fit_negbin_r, _negbin_nll, _negbin_80pct_calibration, _MIN_MU, _ALPHA_GRID,
)

_OUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals" / "oos_signals_run_env.parquet"
_TRAIN_FROM_DEFAULT = 2021   # run_env data floor (weather/umpire)
_EVAL_FROM_DEFAULT = 2022    # first season with ≥1 prior training season


def _ridge_pipe(alpha: float):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])


def _best_alpha(df_prior: pd.DataFrame) -> float:
    """Alpha grid search on inner walk-forward folds of the prior seasons (NLL)."""
    seasons = sorted(int(s) for s in df_prior["game_year"].unique())
    inner = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]
    if not inner:
        return 1.0
    best_alpha, best_nll = 1.0, float("inf")
    for alpha in _ALPHA_GRID:
        nlls = []
        for tr, te in inner:
            X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df_prior, list(tr), te)
            pipe = _ridge_pipe(alpha).fit(X_tr, y_tr)
            mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
            mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
            nlls.append(_negbin_nll(y_te, mu_te, _fit_negbin_r(y_tr, mu_tr)))
        mean_nll = float(np.mean(nlls))
        if mean_nll < best_nll:
            best_nll, best_alpha = mean_nll, alpha
    return best_alpha


def regenerate(df: pd.DataFrame, train_from: int, eval_from: int) -> pd.DataFrame:
    df = df[df["game_year"] >= train_from].reset_index(drop=True)
    seasons = sorted(int(s) for s in df["game_year"].unique())
    eval_seasons = [s for s in seasons if s >= eval_from]
    print(f"train_from={train_from}  eval_from={eval_from}  seasons={seasons}  eval_seasons={eval_seasons}")

    out_frames: list[pd.DataFrame] = []
    for S in eval_seasons:
        train_seasons = [s for s in seasons if s < S]
        if not train_seasons:
            continue
        df_prior = df[df["game_year"] < S]
        alpha = _best_alpha(df_prior)
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, train_seasons, S)
        pipe = _ridge_pipe(alpha).fit(X_tr, y_tr)
        mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
        mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
        r = _fit_negbin_r(y_tr, mu_tr)
        p = r / (r + mu_te)
        unc = nbinom.ppf(0.90, n=r, p=p) - nbinom.ppf(0.10, n=r, p=p)

        nll = _negbin_nll(y_te, mu_te, r)
        mae = float(np.mean(np.abs(mu_te - y_te)))
        c80 = _negbin_80pct_calibration(y_te, mu_te, r)
        print(f"  eval {S}: train {train_from}-{S-1} ({len(train_seasons)} seasons, {len(X_tr):,} rows) "
              f"alpha={alpha} → n_eval={len(y_te):,}  NLL={nll:.4f}  MAE={mae:.3f}  calib80={c80:.3f}  r={r:.3f}")

        # _prepare_fold preserves test-season row order (df is ORDER BY game_date,game_pk),
        # so the same-filter slice aligns with mu_te.
        ev = df[df["game_year"] == S].reset_index(drop=True)
        assert len(ev) == len(mu_te), f"row-order misalignment for {S}: {len(ev)} vs {len(mu_te)}"
        sub = ev[["game_pk", "game_year"]].rename(columns={"game_year": "season"})
        sub["run_env_mu"] = mu_te
        sub["run_env_dispersion"] = float(r)
        sub["run_env_uncertainty"] = unc
        out_frames.append(sub)

    if not out_frames:
        raise RuntimeError("No eval seasons produced — check train_from/eval_from vs data.")
    return pd.concat(out_frames, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Leakage-free walk-forward run_env_v4 OOS signals")
    ap.add_argument("--train-from", type=int, default=_TRAIN_FROM_DEFAULT)
    ap.add_argument("--eval-from", type=int, default=_EVAL_FROM_DEFAULT)
    ap.add_argument("--out", default=str(_OUT_PATH))
    args = ap.parse_args()

    print("Loading run_env data (load_training_data)...")
    df = load_training_data()
    print(f"  {len(df):,} game rows, seasons {sorted(int(s) for s in df['game_year'].unique())}")

    oos = regenerate(df, args.train_from, args.eval_from)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(out_path, index=False)
    print(f"\nWrote {len(oos):,} OOS run_env signal rows → {out_path}")
    print(oos.groupby("season").agg(n=("game_pk", "size"),
                                    mean_mu=("run_env_mu", "mean"),
                                    mean_unc=("run_env_uncertainty", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
