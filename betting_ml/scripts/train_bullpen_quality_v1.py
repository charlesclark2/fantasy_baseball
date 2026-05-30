"""
train_bullpen_quality_v1.py — Epic 6.3

Trains the bullpen quality model v1: distributional Normal model predicting
next-game bullpen xwOBA (actual_bullpen_xwoba) for the pitching team.

Distribution family: Normal — bullpen xwOBA is a continuous rate metric.

Two candidates (Case 1 — no prior champion; lower CV NLL wins outright):
  Candidate A — NGBoost Normal  (joint mu + sigma via gradient boosting)
  Candidate B — LightGBM mean + Normal sigma fitted from training residuals

Walk-forward temporal CV: season-level folds from 2016 onward.
Selection gates: lower mean CV NLL wins; calib_80 ≥ 0.80; MAE is tiebreaker.
Optuna tunes winner hyperparameters (objective = mean CV NLL).

Inputs:  betting_ml/data/bullpen_state_train.parquet  (built by 6.1 + 6.2)
Outputs:
  betting_ml/models/sub_models/bullpen_quality_v1.pkl
  s3://baseball-betting-ml-artifacts/sub_models/bullpen_quality_v1.pkl
  sub_model_registry.yaml  (bullpen_v1 → bullpen_quality_v1 block)

MLflow experiment: bullpen_state_v1
Emits signals: bullpen_quality_mu, bullpen_quality_sigma

Usage:
    uv run python betting_ml/scripts/train_bullpen_quality_v1.py
    uv run python betting_ml/scripts/train_bullpen_quality_v1.py --no-promote
    uv run python betting_ml/scripts/train_bullpen_quality_v1.py --force-winner {ngboost,lgbm}
"""
from __future__ import annotations

import argparse
import json
import joblib
import re
import sys
from datetime import date
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from scipy.stats import norm, wilcoxon

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold
from betting_ml.utils.artifact_store import upload_artifact

_PARQUET_PATH    = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_ARTIFACT_PATH   = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_quality_v1.pkl"
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/bullpen_quality_v1.pkl"
_REGISTRY_PATH   = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"

_TARGET_COL   = "actual_bullpen_xwoba"
_YEAR_COL     = "game_year"
_CALIB_80_Z   = float(norm.ppf(0.90))   # 1.2816 — half-width for symmetric 80% PI
_CALIB_80_GATE = 0.80
_MIN_SIGMA    = 1e-4                     # floor to avoid log(0) in NLL

_OPTUNA_PROBE_TRIALS = 10
_OPTUNA_FULL_TRIALS  = 50
_OPTUNA_SEED         = 42

# NGBoost comparison-phase defaults
_NGBOOST_N_EST = 500
_NGBOOST_LR    = 0.05

# LightGBM comparison-phase defaults
_LGBM_N_EST  = 500
_LGBM_LR     = 0.05
_LGBM_LEAVES = 31

# ── Feature set ───────────────────────────────────────────────────────────────
FEATURE_COLS = [
    # EB quality prior (Epic 6A.3)
    "eb_bullpen_xwoba",
    "eb_bullpen_uncertainty",
    "eb_bullpen_coverage_pct",
    # Rolling quality — 14-day window
    "xwoba_against_14d",
    "k_pct_14d",
    "bb_pct_14d",
    "hard_hit_pct_14d",
    "whiff_rate_14d",
    "innings_pitched_14d",
    # Rolling quality — 30-day window
    "xwoba_against_30d",
    "k_pct_30d",
    "bb_pct_30d",
    "hard_hit_pct_30d",
    "whiff_rate_30d",
    "innings_pitched_30d",
    # Availability (Epic 6.2) — normalized; excludes fatigue_score (collinear)
    "availability_index",
    # Workload features
    "bullpen_ip_prev_1d",
    "bullpen_ip_prev_2d",
    "bullpen_ip_prev_3d",
    "pitchers_used_prev_3d",
    "pitchers_used_prev_7d",
    "reliever_appearances_prev_3d",
    "high_leverage_used_prev_2d",
    "closer_used_prev_1d",
]


# ── Normal distribution utilities ─────────────────────────────────────────────

def _normal_nll(y: np.ndarray, mu: np.ndarray, sigma: float | np.ndarray) -> float:
    """Mean NLL under N(mu, sigma). sigma may be scalar or array."""
    sigma = np.clip(sigma, _MIN_SIGMA, None)
    return float(-norm.logpdf(y, loc=mu, scale=sigma).mean())


def _normal_calib_80(y: np.ndarray, mu: np.ndarray, sigma: float | np.ndarray) -> float:
    """Fraction of y within the symmetric 80% Normal PI."""
    sigma = np.clip(sigma, _MIN_SIGMA, None)
    lo = mu - _CALIB_80_Z * sigma
    hi = mu + _CALIB_80_Z * sigma
    return float(((y >= lo) & (y <= hi)).mean())


# ── Data preparation ──────────────────────────────────────────────────────────

def _load_data() -> pd.DataFrame:
    df = pd.read_parquet(_PARQUET_PATH)
    for col in FEATURE_COLS + [_TARGET_COL]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    df = df.dropna(subset=[_TARGET_COL]).reset_index(drop=True)
    return df


def _prepare_fold(
    df: pd.DataFrame,
    train_seasons: list[int],
    test_season: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Split data into train/test arrays with median imputation from training fold."""
    tr = df[df[_YEAR_COL].isin(train_seasons)].copy()
    te = df[df[_YEAR_COL] == test_season].copy()

    # Compute imputation values from training fold
    impute_vals = {col: float(tr[col].median()) for col in FEATURE_COLS}

    for col in FEATURE_COLS:
        tr[col] = tr[col].fillna(impute_vals[col])
        te[col] = te[col].fillna(impute_vals[col])

    X_tr = tr[FEATURE_COLS].to_numpy(dtype=float)
    y_tr = tr[_TARGET_COL].to_numpy(dtype=float)
    X_te = te[FEATURE_COLS].to_numpy(dtype=float)
    y_te = te[_TARGET_COL].to_numpy(dtype=float)

    return X_tr, y_tr, X_te, y_te, impute_vals


def _fold_record(
    fold_idx: int,
    train_seasons: list[int],
    test_season: int,
    y_tr: np.ndarray,
    y_te: np.ndarray,
    mu_te: np.ndarray,
    sigma_te: float | np.ndarray,
) -> dict:
    nll   = _normal_nll(y_te, mu_te, sigma_te)
    mae   = float(np.mean(np.abs(mu_te - y_te)))
    calib = _normal_calib_80(y_te, mu_te, sigma_te)
    mean_sigma = float(np.mean(np.clip(sigma_te, _MIN_SIGMA, None)))
    return {
        "fold":          fold_idx,
        "train_seasons": list(map(int, train_seasons)),
        "test_season":   int(test_season),
        "n_train":       int(len(y_tr)),
        "n_test":        int(len(y_te)),
        "nll":           round(nll, 4),
        "mae":           round(mae, 4),
        "calib_80":      round(calib, 4),
        "mean_sigma":    round(mean_sigma, 4),
    }


# ── Candidate A: NGBoost Normal ───────────────────────────────────────────────

def _walk_forward_cv_ngboost(
    df: pd.DataFrame,
    n_estimators: int = _NGBOOST_N_EST,
    learning_rate: float = _NGBOOST_LR,
    minibatch_frac: float = 1.0,
) -> tuple[float, float, float, list[dict]]:
    """Returns (mean_nll, mean_mae, mean_calib_80, fold_records)."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    seasons = sorted(df[_YEAR_COL].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [A] NGBoost Normal: n_est={n_estimators}, lr={learning_rate}, "
          f"mbfrac={minibatch_frac}, {len(folds)} folds")

    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)

        ngb = NGBRegressor(
            Dist=Normal,
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            minibatch_frac=minibatch_frac,
            random_state=42,
            verbose=False,
        )
        ngb.fit(X_tr, y_tr)

        mu_te    = ngb.predict(X_te)
        dist_te  = ngb.pred_dist(X_te)
        sigma_te = np.clip(dist_te.params["scale"], _MIN_SIGMA, None)

        rec = _fold_record(
            len(fold_records) + 1, list(train_seasons), test_season,
            y_tr, y_te, mu_te, sigma_te,
        )
        fold_records.append(rec)
        print(
            f"    fold {rec['fold']:>2} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  σ={rec['mean_sigma']:.4f}"
        )

    mean_nll   = float(np.mean([f["nll"]   for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"]   for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    return mean_nll, mean_mae, mean_calib, fold_records


# ── Candidate B: LightGBM mean + residual sigma ───────────────────────────────

def _walk_forward_cv_lgbm(
    df: pd.DataFrame,
    n_estimators: int = _LGBM_N_EST,
    learning_rate: float = _LGBM_LR,
    num_leaves: int = _LGBM_LEAVES,
    min_child_samples: int = 20,
    subsample: float = 1.0,
    colsample_bytree: float = 1.0,
) -> tuple[float, float, float, list[dict]]:
    """Returns (mean_nll, mean_mae, mean_calib_80, fold_records)."""
    from lightgbm import LGBMRegressor

    seasons = sorted(df[_YEAR_COL].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [B] LightGBM+σ: n_est={n_estimators}, lr={learning_rate}, "
          f"leaves={num_leaves}, {len(folds)} folds")

    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)

        lgb = LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            num_leaves=num_leaves,
            min_child_samples=min_child_samples,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=42,
            verbose=-1,
        )
        lgb.fit(X_tr, y_tr)

        mu_tr   = lgb.predict(X_tr)
        sigma   = float(np.std(y_tr - mu_tr))
        sigma   = max(sigma, _MIN_SIGMA)
        mu_te   = lgb.predict(X_te)

        rec = _fold_record(
            len(fold_records) + 1, list(train_seasons), test_season,
            y_tr, y_te, mu_te, sigma,
        )
        fold_records.append(rec)
        print(
            f"    fold {rec['fold']:>2} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  σ={sigma:.4f}"
        )

    mean_nll   = float(np.mean([f["nll"]   for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"]   for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    return mean_nll, mean_mae, mean_calib, fold_records


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_fold_table(label: str, fold_records: list[dict]) -> None:
    print(f"\n── {label} walk-forward CV ─────────────────────────────────────────")
    print(f"  {'Fold':>4}  {'Train':>12}  {'Test':>6}  {'NLL':>7}  "
          f"{'MAE':>6}  {'Calib80':>8}  {'σ (mean)':>9}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>12}  {r['test_season']:>6}  "
            f"{r['nll']:>7.4f}  {r['mae']:>6.4f}  {r['calib_80']:>8.4f}  "
            f"{r['mean_sigma']:>9.4f}"
        )
    print(
        f"  {'Mean':>4}  {'':>12}  {'':>6}  "
        f"{np.mean([f['nll'] for f in fold_records]):>7.4f}  "
        f"{np.mean([f['mae'] for f in fold_records]):>6.4f}  "
        f"{np.mean([f['calib_80'] for f in fold_records]):>8.4f}  "
        f"{np.mean([f['mean_sigma'] for f in fold_records]):>9.4f}"
    )


def _print_gate_summary(
    a_nll: float, a_mae: float, a_calib: float, a_folds: list[dict],
    b_nll: float, b_mae: float, b_calib: float, b_folds: list[dict],
) -> tuple[str, float]:
    """Print gate table. Case 1: lower NLL wins outright. Returns (winner_type, winner_nll)."""
    print("\n" + "=" * 78)
    print("bullpen_quality_v1 head-to-head: Cand A (NGBoost Normal) | Cand B (LightGBM+σ)")
    print("  Case 1 (new model — no prior champion): lower mean CV NLL wins outright")
    print("=" * 78)

    def gate(val: float, threshold: float, lower_is_better: bool = True) -> str:
        ok = (val < threshold) if lower_is_better else (val >= threshold)
        return "PASS" if ok else "FAIL"

    w = 28
    print(f"  {'Gate':<{w}}  {'Cand A (NGBoost)':>20}  {'Cand B (LightGBM+σ)':>20}")
    print(f"  {'-'*w}  {'-'*20}  {'-'*20}")

    # Primary: NLL (lower wins)
    nll_winner = "A" if a_nll <= b_nll else "B"
    print(
        f"  {'NLL (lower wins — primary)':<{w}}  "
        f"{a_nll:>16.4f} {'←' if nll_winner == 'A' else ' ':>3}  "
        f"{b_nll:>16.4f} {'←' if nll_winner == 'B' else ' ':>3}"
    )
    print(
        f"  {'calib_80 (≥ 0.80)':<{w}}  "
        f"{a_calib:>16.4f} {gate(a_calib, _CALIB_80_GATE, False):>4}  "
        f"{b_calib:>16.4f} {gate(b_calib, _CALIB_80_GATE, False):>4}"
    )
    print(
        f"  {'MAE (tiebreaker)':<{w}}  "
        f"{a_mae:>20.4f}  {b_mae:>20.4f}"
    )

    # Wilcoxon signed-rank test on fold NLLs
    a_fold_nlls = [f["nll"] for f in a_folds]
    b_fold_nlls = [f["nll"] for f in b_folds]
    if len(a_fold_nlls) >= 5:
        try:
            stat, p_wil = wilcoxon(a_fold_nlls, b_fold_nlls)
            print(f"\n  Wilcoxon signed-rank test (fold NLLs, A vs B): p={p_wil:.4f}")
        except Exception:
            p_wil = float("nan")
    else:
        p_wil = float("nan")

    # Fold win count
    a_wins = sum(1 for a, b in zip(a_fold_nlls, b_fold_nlls) if a < b)
    b_wins = len(a_fold_nlls) - a_wins
    print(f"  Fold NLL win count: A={a_wins}  B={b_wins} (total={len(a_fold_nlls)} folds)")

    # Selection: Case 1 — lower mean NLL wins
    print("=" * 78)
    a_calib_ok = a_calib >= _CALIB_80_GATE
    b_calib_ok = b_calib >= _CALIB_80_GATE

    if a_nll <= b_nll:
        winner_type = "ngboost"
        winner_nll  = a_nll
        calib_ok    = a_calib_ok
        print(f"\n  Winner: Candidate A — NGBoost Normal (NLL {a_nll:.4f} ≤ LightGBM {b_nll:.4f})")
    else:
        winner_type = "lgbm"
        winner_nll  = b_nll
        calib_ok    = b_calib_ok
        print(f"\n  Winner: Candidate B — LightGBM+σ (NLL {b_nll:.4f} < NGBoost {a_nll:.4f})")

    if not calib_ok:
        print(f"  WARNING: winner calib_80 = {(a_calib if winner_type == 'ngboost' else b_calib):.4f} "
              f"< {_CALIB_80_GATE} — calibration gate not met")

    return winner_type, winner_nll


# ── Optuna tuning ─────────────────────────────────────────────────────────────

def _make_optuna_objective(winner_type: str, df: pd.DataFrame):
    seasons = sorted(df[_YEAR_COL].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    def objective(trial) -> float:
        if winner_type == "ngboost":
            from ngboost import NGBRegressor
            from ngboost.distns import Normal
            n_est    = trial.suggest_int("n_estimators", 200, 1000, step=100)
            lr       = trial.suggest_float("learning_rate", 0.005, 0.1, log=True)
            mbfrac   = trial.suggest_float("minibatch_frac", 0.5, 1.0)
            fold_nlls = []
            for train_seasons, test_season in folds:
                X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
                ngb = NGBRegressor(
                    Dist=Normal, n_estimators=n_est, learning_rate=lr,
                    minibatch_frac=mbfrac, random_state=_OPTUNA_SEED, verbose=False,
                )
                ngb.fit(X_tr, y_tr)
                mu_te   = ngb.predict(X_te)
                sigma_te = np.clip(ngb.pred_dist(X_te).params["scale"], _MIN_SIGMA, None)
                fold_nlls.append(_normal_nll(y_te, mu_te, sigma_te))
            return float(np.mean(fold_nlls))

        else:  # lgbm
            from lightgbm import LGBMRegressor
            n_est   = trial.suggest_int("n_estimators", 100, 1000, step=50)
            lr      = trial.suggest_float("learning_rate", 0.005, 0.2, log=True)
            leaves  = trial.suggest_int("num_leaves", 15, 127)
            min_cs  = trial.suggest_int("min_child_samples", 10, 100)
            sub     = trial.suggest_float("subsample", 0.5, 1.0)
            colsub  = trial.suggest_float("colsample_bytree", 0.5, 1.0)
            fold_nlls = []
            for train_seasons, test_season in folds:
                X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
                lgb = LGBMRegressor(
                    n_estimators=n_est, learning_rate=lr, num_leaves=leaves,
                    min_child_samples=min_cs, subsample=sub, colsample_bytree=colsub,
                    random_state=_OPTUNA_SEED, verbose=-1,
                )
                lgb.fit(X_tr, y_tr)
                mu_tr = lgb.predict(X_tr)
                sigma = max(float(np.std(y_tr - mu_tr)), _MIN_SIGMA)
                mu_te = lgb.predict(X_te)
                fold_nlls.append(_normal_nll(y_te, mu_te, sigma))
            return float(np.mean(fold_nlls))

    return objective


def _tune_winner(winner_type: str, df: pd.DataFrame, initial_nll: float) -> tuple[dict, float]:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    objective = _make_optuna_objective(winner_type, df)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )

    print(
        f"\n[Optuna] Phase 1 — probe ({_OPTUNA_PROBE_TRIALS} trials), "
        f"objective=mean CV NLL, initial NLL={initial_nll:.4f}"
    )
    study.optimize(objective, n_trials=_OPTUNA_PROBE_TRIALS, show_progress_bar=True)
    probe_best = study.best_value
    print(
        f"[Optuna] Probe best NLL: {probe_best:.4f}  "
        f"(Δ vs initial: {initial_nll - probe_best:+.4f})"
    )

    print(f"[Optuna] Phase 2 — full pass ({_OPTUNA_FULL_TRIALS} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_FULL_TRIALS, show_progress_bar=True)

    best_params = study.best_params
    best_nll    = study.best_value
    print(f"[Optuna] Best params: {best_params}")
    print(f"[Optuna] Best NLL:    {best_nll:.4f}  (Δ vs initial: {initial_nll - best_nll:+.4f})")
    return best_params, best_nll


# ── Registry update ───────────────────────────────────────────────────────────

def _update_registry(
    cv_nll: float,
    cv_mae: float,
    mean_sigma: float,
    winner_type: str,
    calib_80: float,
    n_features: int,
    mlflow_run_id: str | None = None,
    tuned_params: dict | None = None,
) -> None:
    text   = _REGISTRY_PATH.read_text()
    today  = date.today().isoformat()
    arch   = "NGBoost Normal" if winner_type == "ngboost" else "LightGBM + residual σ"
    params_str = json.dumps(tuned_params or {})

    quality_block = f"""  bullpen_quality_v1:
    artifact_path: {_ARTIFACT_S3_URI}
    feature_columns: {json.dumps(FEATURE_COLS)}
    n_features: {n_features}
    architecture: {arch}
    mlflow_run_id: {mlflow_run_id or "null"}
    tuned_params: {params_str}
    cv_strategy: walk_forward_season
    cv_metric: normal_nll
    cv_score: {round(cv_nll, 4)}
    cv_mae: {round(cv_mae, 4)}
    cv_calib_80: {round(calib_80, 4)}
    mean_sigma: {round(mean_sigma, 4)}
    promotion_gate:
      metric: normal_nll
      direction: lower_is_better
      case: 1  # new model — no prior champion; lower NLL wins outright
    output_signals:
      - bullpen_quality_mu
      - bullpen_quality_sigma
    trained_at: "{today}"
    promotion_status: champion
    notes: |
      Story 6.3. Distributional Normal model predicting next-game bullpen xwOBA.
      Winner: {arch} (Case 1 — no prior champion).
      CV NLL {round(cv_nll, 4)} | CV MAE {round(cv_mae, 4)} | calib_80 {round(calib_80, 4)}.
      {n_features} features: EB priors, rolling quality (14d/30d), availability index, workload.
      Trained {today}.
"""

    # Insert/replace the bullpen_quality_v1 sub-block inside bullpen_v1
    pattern = r"(  bullpen_quality_v1:.*?)(?=  \S|\Z)"
    replacement = quality_block
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)
    if new_text == text:
        # Block doesn't exist yet — insert before the notes: line of bullpen_v1
        new_text = re.sub(
            r"(bullpen_v1:.*?)(  notes:)",
            r"\1" + quality_block + r"  notes:",
            text,
            count=1,
            flags=re.DOTALL,
        )

    _REGISTRY_PATH.write_text(new_text)
    print(f"\nRegistry updated: bullpen_v1 → bullpen_quality_v1 ({arch}, "
          f"NLL={round(cv_nll, 4)}, trained {today})")


# ── Training orchestration ────────────────────────────────────────────────────

def train(
    promote: bool = True,
    force_winner: str | None = None,
) -> str:
    if not _PARQUET_PATH.exists():
        print(f"ERROR: {_PARQUET_PATH} not found. Run build_bullpen_state_dataset.py first.")
        sys.exit(1)

    print(f"\nLoading training data from {_PARQUET_PATH.name}...")
    df = _load_data()
    seasons = sorted(df[_YEAR_COL].unique())
    print(f"Loaded {len(df):,} rows | {len(seasons)} seasons [{int(seasons[0])}–{int(seasons[-1])}]")
    print(f"Target: mean={df[_TARGET_COL].mean():.4f}  std={df[_TARGET_COL].std():.4f}")
    print(f"Features: {len(FEATURE_COLS)}")

    null_pct = df[FEATURE_COLS].isna().mean() * 100
    high_null = null_pct[null_pct > 2]
    if not high_null.empty:
        print(f"  Null rates > 2% (will be median-imputed per fold):")
        for col, pct in high_null.items():
            print(f"    {col}: {pct:.1f}%")

    print("\n" + "=" * 72)
    print("TRAINING bullpen_quality_v1 — Distributional Normal (Epic 6.3)")
    print(f"Distribution: Normal | CV: walk-forward season | {len(seasons)-1} folds")
    print(f"Case 1 (new model): lower mean CV NLL wins outright; calib_80 ≥ {_CALIB_80_GATE}")
    print("=" * 72)

    mlflow.set_experiment("bullpen_state_v1")
    get_or_create_experiment("bullpen_state_v1")

    with mlflow.start_run(run_name=f"6.3_comparison_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id

        mlflow.log_params({
            "n_rows":               len(df),
            "n_seasons":            len(seasons),
            "n_features":           len(FEATURE_COLS),
            "train_start":          int(seasons[0]),
            "ngboost_n_est_default": _NGBOOST_N_EST,
            "ngboost_lr_default":   _NGBOOST_LR,
            "lgbm_n_est_default":   _LGBM_N_EST,
            "lgbm_lr_default":      _LGBM_LR,
            "calib_80_gate":        _CALIB_80_GATE,
            "optuna_probe_trials":  _OPTUNA_PROBE_TRIALS,
            "optuna_full_trials":   _OPTUNA_FULL_TRIALS,
            "force_winner":         str(force_winner),
            "promote":              promote,
        })

        # ── Candidate A: NGBoost Normal ────────────────────────────────────
        print("\n[1/2] Candidate A — NGBoost Normal")
        a_nll, a_mae, a_calib, a_folds = _walk_forward_cv_ngboost(df)
        _print_fold_table("Candidate A (NGBoost Normal)", a_folds)
        mlflow.log_metrics({"cand_a_cv_nll": a_nll, "cand_a_cv_mae": a_mae, "cand_a_calib_80": a_calib})
        for rec in a_folds:
            log_cv_fold(rec["fold"], rec["test_season"], {
                "a_nll": rec["nll"], "a_mae": rec["mae"],
                "a_calib_80": rec["calib_80"], "a_sigma": rec["mean_sigma"],
            })

        # ── Candidate B: LightGBM + residual sigma ─────────────────────────
        print("\n[2/2] Candidate B — LightGBM + residual σ")
        b_nll, b_mae, b_calib, b_folds = _walk_forward_cv_lgbm(df)
        _print_fold_table("Candidate B (LightGBM+σ)", b_folds)
        mlflow.log_metrics({"cand_b_cv_nll": b_nll, "cand_b_cv_mae": b_mae, "cand_b_calib_80": b_calib})
        for rec in b_folds:
            log_cv_fold(rec["fold"], rec["test_season"], {
                "b_nll": rec["nll"], "b_mae": rec["mae"],
                "b_calib_80": rec["calib_80"], "b_sigma": rec["mean_sigma"],
            })

        # ── Selection ──────────────────────────────────────────────────────
        winner_type, winner_nll = _print_gate_summary(
            a_nll, a_mae, a_calib, a_folds,
            b_nll, b_mae, b_calib, b_folds,
        )

        if force_winner is not None:
            winner_type = force_winner
            winner_nll  = a_nll if force_winner == "ngboost" else b_nll
            print(f"\n[--force-winner {force_winner}] Overriding gate-based selection.")

        winner_mae   = a_mae   if winner_type == "ngboost" else b_mae
        winner_calib = a_calib if winner_type == "ngboost" else b_calib
        winner_folds = a_folds if winner_type == "ngboost" else b_folds

        mlflow.log_params({"winner_type": winner_type})
        mlflow.log_metrics({"winner_cv_nll": winner_nll, "winner_cv_mae": winner_mae,
                            "winner_calib_80": winner_calib})

        # ── Optuna tuning of winner ────────────────────────────────────────
        print(f"\n{'='*72}")
        print(f"Optuna hyperparameter tuning — winner: {winner_type.upper()}")
        print(f"{'='*72}")
        tuned_params, tuned_nll = _tune_winner(winner_type, df, winner_nll)
        mlflow.log_params({f"tuned_{k}": v for k, v in tuned_params.items()})
        mlflow.log_metrics({"tuned_cv_nll": tuned_nll})

        # ── Final model: train on all data with tuned params ───────────────
        print(f"\nTraining final {winner_type.upper()} on all {len(df):,} rows...")

        # Compute final imputation values from all data (used at inference)
        impute_vals = {col: float(df[col].median()) for col in FEATURE_COLS}
        for col in FEATURE_COLS:
            df[col] = df[col].fillna(impute_vals[col])

        X_all = df[FEATURE_COLS].to_numpy(dtype=float)
        y_all = df[_TARGET_COL].to_numpy(dtype=float)

        if winner_type == "ngboost":
            from ngboost import NGBRegressor
            from ngboost.distns import Normal
            final_n_est   = tuned_params.get("n_estimators", _NGBOOST_N_EST)
            final_lr      = tuned_params.get("learning_rate", _NGBOOST_LR)
            final_mbfrac  = tuned_params.get("minibatch_frac", 1.0)
            print(f"  Tuned params: n_estimators={final_n_est}, lr={final_lr:.5f}, "
                  f"minibatch_frac={final_mbfrac:.3f}")
            final_model = NGBRegressor(
                Dist=Normal, n_estimators=final_n_est, learning_rate=final_lr,
                minibatch_frac=final_mbfrac, random_state=_OPTUNA_SEED, verbose=False,
            )
            final_model.fit(X_all, y_all)
            mu_all    = final_model.predict(X_all)
            sigma_all = np.clip(final_model.pred_dist(X_all).params["scale"], _MIN_SIGMA, None)
            final_sigma = float(np.mean(sigma_all))   # informational; inference uses pred_dist

        else:  # lgbm
            from lightgbm import LGBMRegressor
            final_n_est    = tuned_params.get("n_estimators", _LGBM_N_EST)
            final_lr       = tuned_params.get("learning_rate", _LGBM_LR)
            final_leaves   = tuned_params.get("num_leaves", _LGBM_LEAVES)
            final_min_cs   = tuned_params.get("min_child_samples", 20)
            final_sub      = tuned_params.get("subsample", 1.0)
            final_colsub   = tuned_params.get("colsample_bytree", 1.0)
            print(f"  Tuned params: n_estimators={final_n_est}, lr={final_lr:.5f}, "
                  f"num_leaves={final_leaves}, min_child_samples={final_min_cs}")
            final_model = LGBMRegressor(
                n_estimators=final_n_est, learning_rate=final_lr, num_leaves=final_leaves,
                min_child_samples=final_min_cs, subsample=final_sub,
                colsample_bytree=final_colsub, random_state=_OPTUNA_SEED, verbose=-1,
            )
            final_model.fit(X_all, y_all)
            mu_all      = final_model.predict(X_all)
            final_sigma = max(float(np.std(y_all - mu_all)), _MIN_SIGMA)
            sigma_all   = np.full(len(y_all), final_sigma)

        in_sample_nll = _normal_nll(y_all, mu_all, sigma_all)
        in_sample_mae = float(np.mean(np.abs(mu_all - y_all)))
        in_sample_cal = _normal_calib_80(y_all, mu_all, sigma_all)

        print(f"  In-sample NLL:           {in_sample_nll:.4f}")
        print(f"  In-sample MAE:           {in_sample_mae:.4f}")
        print(f"  In-sample calib_80:      {in_sample_cal:.4f}")
        print(f"  Walk-forward CV NLL:     {tuned_nll:.4f}  (tuned)")
        print(f"  Walk-forward CV MAE:     {winner_mae:.4f}")
        print(f"  Mean σ (final model):    {final_sigma:.4f}")

        mlflow.log_metrics({
            "final_insample_nll": in_sample_nll,
            "final_insample_mae": in_sample_mae,
            "final_insample_cal": in_sample_cal,
            "final_mean_sigma":   final_sigma,
        })

        # ── Save artifact ──────────────────────────────────────────────────
        artifact = {
            "model":          final_model,
            "model_type":     winner_type,
            "feature_cols":   FEATURE_COLS,
            "impute_vals":    impute_vals,
            "min_sigma":      _MIN_SIGMA,
            # Stored for LightGBM inference (constant sigma); NGBoost uses pred_dist
            "residual_sigma": final_sigma,
            "target_mean":    float(y_all.mean()),
            "target_std":     float(y_all.std()),
            # CV metrics
            "cv_nll":         winner_nll,
            "cv_mae":         winner_mae,
            "cv_calib_80":    winner_calib,
            "tuned_cv_nll":   tuned_nll,
            "tuned_params":   tuned_params,
            # Comparison phase metrics
            "cand_a_cv_nll":  a_nll,
            "cand_a_cv_mae":  a_mae,
            "cand_a_calib_80": a_calib,
            "cand_b_cv_nll":  b_nll,
            "cand_b_cv_mae":  b_mae,
            "cand_b_calib_80": b_calib,
            "cv_fold_records": winner_folds,
        }

        _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, _ARTIFACT_PATH)
        print(f"\nArtifact saved → {_ARTIFACT_PATH}")

        if promote:
            upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)

        mlflow.log_artifact(str(_ARTIFACT_PATH))
        mlflow.set_tag("sub_model_registry_key", "bullpen_quality_v1")
        print(f"  MLflow run_id: {mlflow_run_id}")

        # ── Registry ───────────────────────────────────────────────────────
        if promote:
            _update_registry(
                cv_nll=tuned_nll,
                cv_mae=winner_mae,
                mean_sigma=final_sigma,
                winner_type=winner_type,
                calib_80=winner_calib,
                n_features=len(FEATURE_COLS),
                mlflow_run_id=mlflow_run_id,
                tuned_params=tuned_params,
            )

    # ── Final summary ──────────────────────────────────────────────────────────
    arch_label = "NGBoost Normal" if winner_type == "ngboost" else "LightGBM+σ"
    print("\n" + "=" * 72)
    print(
        f"bullpen_quality_v1 result: CHAMPION ({arch_label}, "
        f"CV NLL {winner_nll:.4f} → tuned {tuned_nll:.4f}, "
        f"CV MAE {winner_mae:.4f}, calib_80 {winner_calib:.4f})"
    )
    print("\nNext steps (Story 6.4):")
    print("  1. Write generate_bullpen_signals.py loading bullpen_quality_v1.pkl")
    print("     Emit: bullpen_quality_mu, bullpen_quality_sigma, bullpen_availability_index")
    print("  2. Store signals in sub-model output mart, backfill 2021–2026")
    print("  3. dbtf build --select feature_pregame_bullpen_state_features")
    print(f"\n=== DONE — MLflow run: {mlflow_run_id} (run `mlflow ui` to browse) ===")
    print("=" * 72)
    return mlflow_run_id


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train bullpen_quality_v1 — distributional Normal (Epic 6.3)"
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Run CV and save artifact locally but skip S3 upload and registry update.",
    )
    parser.add_argument(
        "--force-winner",
        choices=["ngboost", "lgbm"],
        default=None,
        metavar="{ngboost,lgbm}",
        help="Override gate-based selection and train the specified architecture.",
    )
    args = parser.parse_args()
    train(
        promote=not args.no_promote,
        force_winner=args.force_winner,
    )


if __name__ == "__main__":
    main()
