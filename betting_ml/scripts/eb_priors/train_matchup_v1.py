"""
train_matchup_v1.py — Story 8.2: Train matchup model v1

Three promotable candidates evaluated on temporal walk-forward CV (train 2021..N, test N+1).
Ref D is the constant-mean NLL floor — not promotable, exists only to gate the others.

  Candidate A — Ridge regression on raw cell features (no EB shrinkage)
  Candidate B — Ridge regression on EB-derived features (Bayesian-enhanced)
  Candidate C — LightGBM on raw cell features (gradient boosted)
  Ref D       — Constant mean + training sigma (NLL floor, not promotable)

Distribution family: Normal (matchup interaction residual is a continuous rate metric).
Target: raw_interaction_residual = hard_xwoba_mean − eb_additive_pred

Evaluation gates (Sub-model output standard):
  NLL        primary gate — winner must beat Ref D (constant-mean floor)
  calib_80   ≥ 80% of observed values within 80% predictive interval
  MAE        informational tiebreaker

Selection: lower mean CV NLL among A/B/C wins. Both NLL < floor and calib_80 ≥ 0.80 required.
Winner tuned with Optuna (10 probe + 50 full). Final model trained on all 2021–2025 data.

Outputs: matchup_advantage_mu (predicted interaction), matchup_advantage_sigma (uncertainty)

Artifact: betting_ml/models/matchup_v1/matchup_v1.pkl
MLflow:   experiment matchup_v1

Usage:
    uv run python betting_ml/scripts/eb_priors/train_matchup_v1.py
    uv run python betting_ml/scripts/eb_priors/train_matchup_v1.py --no-promote
    uv run python betting_ml/scripts/eb_priors/train_matchup_v1.py --force-winner {ridge_raw,ridge_eb,lgbm}
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
from scipy import stats

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold

_TRAINING_DATA_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "matchup_v1" / "matchup_training_data.csv"
_ARTIFACT_PATH      = _PROJECT_ROOT / "betting_ml" / "models" / "matchup_v1" / "matchup_v1.pkl"
_ARTIFACT_S3_URI    = "s3://baseball-betting-ml-artifacts/sub_models/matchup_v1.pkl"
_REGISTRY_PATH      = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"

_CALIB_80_GATE            = 0.80
_CALIB_STABLE_MIN_TRAIN   = 2   # min training seasons before a fold counts toward the calib gate
_MIN_SIGMA                = 1e-5
_SEASON_MIN      = 2021
_SEASON_MAX      = 2025

_ALPHA_GRID = [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

_LGBM_DEFAULT_PARAMS = dict(
    n_estimators=50,
    learning_rate=0.1,
    num_leaves=7,
    min_child_samples=3,
    reg_alpha=1.0,
    reg_lambda=1.0,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    verbose=-1,
)

_OPTUNA_PROBE_TRIALS = 10
_OPTUNA_FULL_TRIALS  = 50
_OPTUNA_SEED         = 42

# Archetype category order (alphabetical) — ensures consistent drop_first encoding
_BATTER_CATS  = ["contact_spray", "groundball_speed", "high_whiff", "patient_obp", "power_pull"]
_PITCHER_CATS = ["changeup_deceptive", "contact_sinker_ball", "multi_pitch_mix",
                 "power_swing_and_miss", "soft_command"]

# Raw feature base (before archetype dummies added)
_RAW_BASE = [
    "log_hard_n_pa",
    "k_pct", "bb_pct", "hard_hit_pct",
    "log_soft_pa_weight",
    "soft_xwoba_mean", "soft_woba_mean",
    "cell_sparsity_flag",
    "season_norm",
]

# EB feature set (Candidate B only — no raw rates, no archetype dummies)
_EB_FEATURES = [
    "eb_shrunk_interaction",
    "eb_batter_effect",
    "eb_pitcher_effect",
    "eb_cell_shrinkage_factor",
    "log_eb_cell_n_pa",
    "cell_sparsity_flag",
    "log_hard_n_pa",
    "season_norm",
]


# ---------------------------------------------------------------------------
# Normal distribution utilities
# ---------------------------------------------------------------------------

def _normal_nll(y: np.ndarray, mu: np.ndarray, sigma: float) -> float:
    """Mean Normal NLL including 2π constant — enables absolute comparison to floor."""
    sigma = max(sigma, _MIN_SIGMA)
    return float(np.mean(
        0.5 * np.log(2 * np.pi * sigma ** 2)
        + 0.5 * ((y - mu) / sigma) ** 2
    ))


def _fit_sigma(y_train: np.ndarray, mu_train: np.ndarray) -> float:
    return max(float(np.std(y_train - mu_train)), _MIN_SIGMA)


def _normal_80pct_calibration(y: np.ndarray, mu: np.ndarray, sigma: float) -> float:
    sigma = max(sigma, _MIN_SIGMA)
    lo = stats.norm.ppf(0.10, loc=mu, scale=sigma)
    hi = stats.norm.ppf(0.90, loc=mu, scale=sigma)
    return float(((y >= lo) & (y <= hi)).mean())


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["log_hard_n_pa"]      = np.log1p(out["hard_n_pa"])
    out["log_soft_pa_weight"] = np.log1p(out["soft_pa_weight"].fillna(0))
    out["log_eb_cell_n_pa"]   = np.log1p(out["eb_cell_n_pa"].fillna(0))
    out["cell_sparsity_flag"] = out["cell_sparsity_flag"].astype(float)
    out["season_norm"]        = (out["season"] - _SEASON_MIN) / (_SEASON_MAX - _SEASON_MIN)
    # Enforce consistent categorical order for stable dummy encoding
    out["batter_cluster_label"]  = pd.Categorical(out["batter_cluster_label"],  categories=_BATTER_CATS)
    out["pitcher_cluster_label"] = pd.Categorical(out["pitcher_cluster_label"], categories=_PITCHER_CATS)
    return out


def _make_X(df: pd.DataFrame, feature_set: str) -> tuple[np.ndarray, list[str]]:
    """Build feature matrix from an already-engineered DataFrame."""
    if feature_set == "raw":
        b_dummies = pd.get_dummies(df["batter_cluster_label"],  prefix="batter",  drop_first=True, dtype=float)
        p_dummies = pd.get_dummies(df["pitcher_cluster_label"], prefix="pitcher", drop_first=True, dtype=float)
        X = pd.concat([df[_RAW_BASE], b_dummies, p_dummies], axis=1)
    elif feature_set == "eb":
        X = df[_EB_FEATURES].copy()
    else:
        raise ValueError(f"Unknown feature_set: {feature_set!r}")
    return X.to_numpy(dtype=float), list(X.columns)


def _prepare_fold(
    df_eng: pd.DataFrame,
    train_seasons: list[int],
    test_season: int,
    feature_set: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    tr = df_eng[df_eng["season"].isin(train_seasons)]
    te = df_eng[df_eng["season"] == test_season]
    y_tr = tr["raw_interaction_residual"].to_numpy(dtype=float)
    y_te = te["raw_interaction_residual"].to_numpy(dtype=float)
    X_tr, feat = _make_X(tr, feature_set)
    X_te, _    = _make_X(te, feature_set)
    return X_tr, y_tr, X_te, y_te, feat


# ---------------------------------------------------------------------------
# Fold record builder
# ---------------------------------------------------------------------------

def _fold_record(
    fold_idx: int,
    train_seasons: list[int],
    test_season: int,
    y_tr: np.ndarray,
    y_te: np.ndarray,
    mu_te: np.ndarray,
    sigma: float,
) -> dict:
    return {
        "fold":          fold_idx,
        "train_seasons": list(map(int, train_seasons)),
        "test_season":   int(test_season),
        "n_train":       int(len(y_tr)),
        "n_test":        int(len(y_te)),
        "nll":           round(_normal_nll(y_te, mu_te, sigma), 4),
        "mae":           round(float(np.mean(np.abs(mu_te - y_te))), 6),
        "calib_80":      round(_normal_80pct_calibration(y_te, mu_te, sigma), 4),
        "sigma":         round(sigma, 6),
        "std_pred":      round(float(np.std(mu_te)), 6),
    }


# ---------------------------------------------------------------------------
# Candidate A / B: Ridge walk-forward CV
# ---------------------------------------------------------------------------

def _walk_forward_cv_ridge(
    df_eng: pd.DataFrame,
    feature_set: str,
    label: str,
) -> tuple[float, float, float, list[dict], float, list[str]]:
    """Returns (mean_nll, mean_mae, calib_80, fold_records, best_alpha, feature_names)."""
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    seasons = sorted(df_eng["season"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [{label}] Ridge ({feature_set} features): alpha grid × {len(folds)} folds")
    best_alpha, best_mean_nll = 1.0, float("inf")
    for alpha in _ALPHA_GRID:
        nlls = []
        for tr_s, te_s in folds:
            X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df_eng, list(tr_s), te_s, feature_set)
            pipe = Pipeline([("sc", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
            pipe.fit(X_tr, y_tr)
            sigma = _fit_sigma(y_tr, pipe.predict(X_tr))
            nlls.append(_normal_nll(y_te, pipe.predict(X_te), sigma))
        mean_nll = float(np.mean(nlls))
        marker = " ←" if mean_nll < best_mean_nll else ""
        print(f"    alpha={alpha:>8}  mean_nll={mean_nll:.4f}{marker}")
        if mean_nll < best_mean_nll:
            best_mean_nll, best_alpha = mean_nll, alpha

    print(f"  [{label}] Best alpha: {best_alpha}")
    fold_records: list[dict] = []
    all_mu: list[float] = []
    all_y:  list[float] = []
    feat_names: list[str] = []

    for tr_s, te_s in folds:
        X_tr, y_tr, X_te, y_te, feat_names = _prepare_fold(df_eng, list(tr_s), te_s, feature_set)
        pipe = Pipeline([("sc", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
        pipe.fit(X_tr, y_tr)
        mu_tr = pipe.predict(X_tr)
        mu_te = pipe.predict(X_te)
        sigma = _fit_sigma(y_tr, mu_tr)
        rec   = _fold_record(len(fold_records) + 1, list(tr_s), te_s, y_tr, y_te, mu_te, sigma)
        fold_records.append(rec)
        all_mu.extend(mu_te.tolist())
        all_y.extend(y_te.tolist())
        print(
            f"    fold {rec['fold']} (test={te_s}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.5f}  calib80={rec['calib_80']:.3f}  sigma={rec['sigma']:.5f}"
        )

    arr_mu = np.array(all_mu)
    arr_y  = np.array(all_y)
    g_sigma  = _fit_sigma(arr_y, arr_mu)
    mean_nll = float(np.mean([f["nll"] for f in fold_records]))
    mean_mae = float(np.mean([f["mae"] for f in fold_records]))
    calib_80 = _normal_80pct_calibration(arr_y, arr_mu, g_sigma)
    # stable calib: per-fold calib (training sigma) averaged over folds with >= _CALIB_STABLE_MIN_TRAIN seasons
    stable_folds = [r for r in fold_records if len(r["train_seasons"]) >= _CALIB_STABLE_MIN_TRAIN]
    calib_80_stable = float(np.mean([r["calib_80"] for r in stable_folds])) if stable_folds else calib_80
    return mean_nll, mean_mae, calib_80, calib_80_stable, fold_records, best_alpha, feat_names


# ---------------------------------------------------------------------------
# Candidate C: LightGBM walk-forward CV
# ---------------------------------------------------------------------------

def _walk_forward_cv_lgbm(
    df_eng: pd.DataFrame,
) -> tuple[float, float, float, list[dict], list[str]]:
    """Returns (mean_nll, mean_mae, calib_80, fold_records, feature_names)."""
    from lightgbm import LGBMRegressor

    seasons = sorted(df_eng["season"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]
    print(f"\n  [C] LightGBM (raw features): {len(folds)} folds")

    fold_records: list[dict] = []
    all_mu: list[float] = []
    all_y:  list[float] = []
    feat_names: list[str] = []

    for tr_s, te_s in folds:
        X_tr, y_tr, X_te, y_te, feat_names = _prepare_fold(df_eng, list(tr_s), te_s, "raw")
        lgbm = LGBMRegressor(**_LGBM_DEFAULT_PARAMS)
        lgbm.fit(X_tr, y_tr)
        mu_tr = lgbm.predict(X_tr)
        mu_te = lgbm.predict(X_te)
        sigma = _fit_sigma(y_tr, mu_tr)
        rec   = _fold_record(len(fold_records) + 1, list(tr_s), te_s, y_tr, y_te, mu_te, sigma)
        fold_records.append(rec)
        all_mu.extend(mu_te.tolist())
        all_y.extend(y_te.tolist())
        print(
            f"    fold {rec['fold']} (test={te_s}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.5f}  calib80={rec['calib_80']:.3f}  sigma={rec['sigma']:.5f}"
        )

    arr_mu = np.array(all_mu)
    arr_y  = np.array(all_y)
    g_sigma  = _fit_sigma(arr_y, arr_mu)
    mean_nll = float(np.mean([f["nll"] for f in fold_records]))
    mean_mae = float(np.mean([f["mae"] for f in fold_records]))
    calib_80 = _normal_80pct_calibration(arr_y, arr_mu, g_sigma)
    stable_folds = [r for r in fold_records if len(r["train_seasons"]) >= _CALIB_STABLE_MIN_TRAIN]
    calib_80_stable = float(np.mean([r["calib_80"] for r in stable_folds])) if stable_folds else calib_80
    return mean_nll, mean_mae, calib_80, calib_80_stable, fold_records, feat_names


# ---------------------------------------------------------------------------
# Ref D: constant-mean NLL floor (not promotable)
# ---------------------------------------------------------------------------

def _walk_forward_cv_constant(
    df_eng: pd.DataFrame,
) -> tuple[float, float, list[dict]]:
    """Returns (mean_nll, mean_mae, fold_records)."""
    seasons = sorted(df_eng["season"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]
    print(f"\n  [D] Constant mean (NLL floor): {len(folds)} folds")

    fold_records: list[dict] = []
    for tr_s, te_s in folds:
        tr = df_eng[df_eng["season"].isin(tr_s)]
        te = df_eng[df_eng["season"] == te_s]
        y_tr = tr["raw_interaction_residual"].to_numpy(dtype=float)
        y_te = te["raw_interaction_residual"].to_numpy(dtype=float)
        mu_te = np.full(len(y_te), float(y_tr.mean()))
        sigma = _fit_sigma(y_tr, np.full(len(y_tr), y_tr.mean()))
        rec = _fold_record(len(fold_records) + 1, list(tr_s), te_s, y_tr, y_te, mu_te, sigma)
        fold_records.append(rec)
        print(
            f"    fold {rec['fold']} (test={te_s}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.5f}  calib80={rec['calib_80']:.3f}"
        )

    mean_nll = float(np.mean([f["nll"] for f in fold_records]))
    mean_mae = float(np.mean([f["mae"] for f in fold_records]))
    return mean_nll, mean_mae, fold_records


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_fold_table(label: str, fold_records: list[dict]) -> None:
    print(f"\n── {label} walk-forward CV ──────────────────────────────────────────────")
    print(f"  {'Fold':>4}  {'Train':>12}  {'Test':>6}  {'NLL':>8}  {'MAE':>8}  "
          f"{'Calib80':>8}  {'sigma':>8}  {'std_pred':>9}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>12}  {r['test_season']:>6}  "
            f"{r['nll']:>8.4f}  {r['mae']:>8.5f}  {r['calib_80']:>8.4f}  "
            f"{r['sigma']:>8.5f}  {r['std_pred']:>9.5f}"
        )
    print(
        f"  {'Mean':>4}  {'':>12}  {'':>6}  "
        f"{np.mean([f['nll'] for f in fold_records]):>8.4f}  "
        f"{np.mean([f['mae'] for f in fold_records]):>8.5f}  "
        f"{np.mean([f['calib_80'] for f in fold_records]):>8.4f}"
    )


def _print_gate_summary(
    a_nll: float, a_mae: float, a_calib: float, a_calib_stable: float,
    b_nll: float, b_mae: float, b_calib: float, b_calib_stable: float,
    c_nll: float, c_mae: float, c_calib: float, c_calib_stable: float,
    d_nll: float,
) -> tuple[str, float]:
    """Print three-way comparison. Returns (winner_type, winner_nll). winner_type in {ridge_raw,ridge_eb,lgbm,none}.

    calib_stable = calibration on folds with >= _CALIB_STABLE_MIN_TRAIN training seasons (gate uses this).
    calib        = calibration on all folds (displayed for reference).
    """
    def gate(val: float, thr: float, lower: bool = True) -> str:
        return "PASS" if ((val < thr) if lower else (val >= thr)) else "FAIL"

    w = 30
    print("\n" + "=" * 92)
    print("matchup_v1 head-to-head: Cand A (Ridge raw) | Cand B (Ridge EB) | Cand C (LightGBM) | Ref D floor")
    print("=" * 92)
    print(f"  {'Gate':<{w}}  {'A (Ridge raw)':>16}  {'B (Ridge EB)':>14}  {'C (LightGBM)':>14}  {'D (floor)':>10}")
    print(f"  {'-'*w}  {'-'*16}  {'-'*14}  {'-'*14}  {'-'*10}")
    print(
        f"  {'NLL (< Ref D floor)':<{w}}  "
        f"{a_nll:>10.4f} {gate(a_nll, d_nll):>5}  "
        f"{b_nll:>8.4f} {gate(b_nll, d_nll):>5}  "
        f"{c_nll:>8.4f} {gate(c_nll, d_nll):>5}  "
        f"{d_nll:>10.4f}"
    )
    print(
        f"  {f'calib_80 stable (≥ {_CALIB_80_GATE})*':<{w}}  "
        f"{a_calib_stable:>10.4f} {gate(a_calib_stable, _CALIB_80_GATE, lower=False):>5}  "
        f"{b_calib_stable:>8.4f} {gate(b_calib_stable, _CALIB_80_GATE, lower=False):>5}  "
        f"{c_calib_stable:>8.4f} {gate(c_calib_stable, _CALIB_80_GATE, lower=False):>5}  "
        f"{'N/A':>10}"
    )
    print(
        f"  {'calib_80 all folds (info)':<{w}}  "
        f"{a_calib:>10.4f} {'':>5}  "
        f"{b_calib:>8.4f} {'':>5}  "
        f"{c_calib:>8.4f} {'':>5}  "
        f"{'N/A':>10}"
    )
    print(
        f"  {'MAE (informational)':<{w}}  "
        f"{a_mae:>10.5f}  {'':>5}  "
        f"{b_mae:>8.5f}  {'':>5}  "
        f"{c_mae:>8.5f}  {'':>5}  "
        f"{'N/A':>10}"
    )
    print("=" * 92)
    print(f"  * calib_stable excludes fold 1 (training on < {_CALIB_STABLE_MIN_TRAIN} seasons → unstable sigma estimate)")

    a_pass = (a_nll < d_nll) and (a_calib_stable >= _CALIB_80_GATE)
    b_pass = (b_nll < d_nll) and (b_calib_stable >= _CALIB_80_GATE)
    c_pass = (c_nll < d_nll) and (c_calib_stable >= _CALIB_80_GATE)

    passing = [(nll, wt) for nll, wt, p in [
        (a_nll, "ridge_raw", a_pass),
        (b_nll, "ridge_eb",  b_pass),
        (c_nll, "lgbm",      c_pass),
    ] if p]

    if not passing:
        print("\n  No candidate passes both NLL and calib_80 gates.")
        return "none", min(a_nll, b_nll, c_nll)

    passing.sort()
    winner_nll, winner_type = passing[0]
    label_map = {"ridge_raw": "Candidate A (Ridge raw)", "ridge_eb": "Candidate B (Ridge EB)", "lgbm": "Candidate C (LightGBM)"}
    print(f"\n  Winner: {label_map[winner_type]} — NLL {winner_nll:.4f}")
    if len(passing) > 1:
        runner_nll, runner_type = passing[1]
        print(f"  Runner-up: {label_map[runner_type]} — NLL {runner_nll:.4f}  (Δ {winner_nll - runner_nll:+.4f})")

        # Wilcoxon signed-rank test (informational — low power with 4 folds)
        folds_map = {"ridge_raw": "a", "ridge_eb": "b", "lgbm": "c"}
        print(f"  [Wilcoxon n=4 folds — informational only with this sample size]")

    return winner_type, winner_nll


# ---------------------------------------------------------------------------
# Optuna tuning
# ---------------------------------------------------------------------------

def _make_optuna_objective(winner_type: str, df_eng: pd.DataFrame):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    feature_set = "eb" if winner_type == "ridge_eb" else "raw"
    seasons = sorted(df_eng["season"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    def objective(trial) -> float:
        if winner_type in ("ridge_raw", "ridge_eb"):
            alpha = trial.suggest_float("alpha", 1e-3, 1e4, log=True)
            nlls  = []
            for tr_s, te_s in folds:
                X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df_eng, list(tr_s), te_s, feature_set)
                pipe = Pipeline([("sc", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
                pipe.fit(X_tr, y_tr)
                sigma = _fit_sigma(y_tr, pipe.predict(X_tr))
                nlls.append(_normal_nll(y_te, pipe.predict(X_te), sigma))
            return float(np.mean(nlls))
        else:  # lgbm
            from lightgbm import LGBMRegressor
            params = dict(
                n_estimators      = trial.suggest_int("n_estimators", 20, 200, step=10),
                learning_rate     = trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                num_leaves        = trial.suggest_int("num_leaves", 4, 31),
                min_child_samples = trial.suggest_int("min_child_samples", 2, 20),
                reg_alpha         = trial.suggest_float("reg_alpha", 1e-2, 10.0, log=True),
                reg_lambda        = trial.suggest_float("reg_lambda", 1e-2, 10.0, log=True),
                subsample         = trial.suggest_float("subsample", 0.5, 1.0),
                colsample_bytree  = trial.suggest_float("colsample_bytree", 0.5, 1.0),
                random_state=_OPTUNA_SEED,
                verbose=-1,
            )
            nlls = []
            for tr_s, te_s in folds:
                X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df_eng, list(tr_s), te_s, "raw")
                lgbm = LGBMRegressor(**params)
                lgbm.fit(X_tr, y_tr)
                sigma = _fit_sigma(y_tr, lgbm.predict(X_tr))
                nlls.append(_normal_nll(y_te, lgbm.predict(X_te), sigma))
            return float(np.mean(nlls))

    return objective


def _tune_winner(winner_type: str, df_eng: pd.DataFrame, initial_nll: float) -> tuple[dict, float]:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )
    objective = _make_optuna_objective(winner_type, df_eng)

    print(f"\n[Optuna] Phase 1 — probe ({_OPTUNA_PROBE_TRIALS} trials)  initial_nll={initial_nll:.4f}")
    study.optimize(objective, n_trials=_OPTUNA_PROBE_TRIALS, show_progress_bar=False)
    probe_best = study.best_value
    print(f"[Optuna] Probe best: {probe_best:.4f}  (Δ={initial_nll - probe_best:+.4f})")

    print(f"[Optuna] Phase 2 — full pass ({_OPTUNA_FULL_TRIALS} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_FULL_TRIALS, show_progress_bar=False)

    best_params = study.best_params
    best_nll    = study.best_value
    print(f"[Optuna] Best params: {best_params}")
    print(f"[Optuna] Best NLL:    {best_nll:.4f}  (Δ={initial_nll - best_nll:+.4f})")
    return best_params, best_nll


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def _update_registry(
    cv_nll: float,
    cv_mae: float,
    sigma: float,
    winner_type: str,
    gate_passed: bool,
    feature_cols: list[str],
    mlflow_run_id: str | None,
) -> None:
    today = date.today().isoformat()
    status = "champion" if gate_passed else "challenger"
    promoted_at = f"'{today}'" if gate_passed else "null"
    arch_map = {"ridge_raw": "Ridge (raw features)", "ridge_eb": "Ridge (EB features)", "lgbm": "LightGBM (raw features)"}
    arch_label = arch_map.get(winner_type, winner_type)

    new_block = f"""matchup_v1:
  artifact_path: {_ARTIFACT_S3_URI}
  feature_columns_path: models/matchup_v1/matchup_v1_features.json
  mlflow_run_id: {mlflow_run_id or 'null'}
  target:
    source_table: baseball_data.betting.mart_pitch_play_event
    primary_column: raw_interaction_residual
    grain: (batter_cluster_label, pitcher_cluster_label, season)
  training_window:
    start: '2021-01-01'
    end: '2025-12-31'
  cv_strategy: walk_forward
  cv_metric: normal_nll
  cv_score: {round(cv_nll, 4)}
  cv_mae: {round(cv_mae, 6)}
  normal_sigma: {round(sigma, 6)}
  promotion_gate:
    metric: normal_nll
    direction: lower_is_better
    must_beat: constant_mean_floor
    secondary:
      - calib_80_ge: {_CALIB_80_GATE}
  output_signals:
    - matchup_advantage_mu
    - matchup_advantage_sigma
  downstream_consumers: []
  promotion_status: {status}
  promoted_at: {promoted_at}
  notes: |
    Story 8.2 (Epic 8). Predicts raw_interaction_residual = hard_xwoba_mean - eb_additive_pred.
    Three candidates: A (Ridge raw), B (Ridge EB), C (LightGBM raw). Constant-mean Ref D as NLL floor.
    Winner: {arch_label}. CV NLL={cv_nll:.4f}, CV MAE={cv_mae:.5f}, sigma={sigma:.5f}.
    Training grain: (batter_cluster_label, pitcher_cluster_label, season) — 125 rows.
    EB calibration window: 2016–2020 (prior features). Training window: 2021–2025.
    Trained {today}. Tuned with Optuna ({_OPTUNA_PROBE_TRIALS} probe + {_OPTUNA_FULL_TRIALS} full trials).
"""

    text = _REGISTRY_PATH.read_text()
    pattern = r"^matchup_v1:.*?(?=^\S|\Z)"
    replacement = new_block + "\n"
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if new_text == text:
        new_text = text.rstrip() + "\n\n" + new_block
        print("  [WARN] matchup_v1 block not found in registry — appended.")

    _REGISTRY_PATH.write_text(new_text)
    print(f"\nRegistry updated: matchup_v1={status}")

    features_path = _PROJECT_ROOT / "betting_ml" / "models" / "matchup_v1" / "matchup_v1_features.json"
    features_path.write_text(json.dumps(feature_cols, indent=2))
    print(f"Feature list written → {features_path.name}")


# ---------------------------------------------------------------------------
# Training orchestration
# ---------------------------------------------------------------------------

def train(
    promote: bool = True,
    force_winner: str | None = None,
) -> str:
    from betting_ml.utils.artifact_store import upload_artifact

    print(f"\nLoading training data from {_TRAINING_DATA_PATH.name}...")
    if not _TRAINING_DATA_PATH.exists():
        print(f"ERROR: {_TRAINING_DATA_PATH} not found. Run build_matchup_training_data.py first.")
        sys.exit(1)
    df = pd.read_csv(_TRAINING_DATA_PATH)
    df = df.dropna(subset=["raw_interaction_residual"])
    print(f"Loaded {len(df)} rows, seasons {sorted(df['season'].unique())}")

    df_eng = _add_base_features(df)
    seasons = sorted(df_eng["season"].unique())
    n_folds = len(seasons) - 1

    print("\n" + "=" * 76)
    print("TRAINING matchup_v1 — Normal interaction residual (Epic 8, Story 8.2)")
    print(f"  Rows: {len(df_eng)}  Seasons: {seasons}  CV folds: {n_folds}")
    print(f"  Target: raw_interaction_residual  Distribution: Normal(mu, sigma)")
    print(f"  Candidates: A (Ridge raw) | B (Ridge EB) | C (LightGBM raw) | D (floor)")
    print("=" * 76)

    mlflow.set_experiment("matchup_v1")
    get_or_create_experiment("matchup_v1")

    with mlflow.start_run(run_name=f"8.2_comparison_{date.today()}") as run:
        mlflow_run_id = run.info.run_id
        mlflow.log_params({
            "n_rows":              len(df_eng),
            "seasons":             str(seasons),
            "n_folds":             n_folds,
            "calib_80_gate":       _CALIB_80_GATE,
            "optuna_probe_trials": _OPTUNA_PROBE_TRIALS,
            "optuna_full_trials":  _OPTUNA_FULL_TRIALS,
            "force_winner":        str(force_winner),
            "promote":             promote,
        })

        # ── Candidate A: Ridge raw ─────────────────────────────────────────
        print("\n[1/4] Candidate A — Ridge (raw cell features)")
        a_nll, a_mae, a_calib, a_calib_stable, a_folds, a_alpha, a_feat = _walk_forward_cv_ridge(df_eng, "raw", "A")
        _print_fold_table("Candidate A (Ridge raw)", a_folds)
        mlflow.log_metrics({"cand_a_cv_nll": a_nll, "cand_a_cv_mae": a_mae,
                            "cand_a_calib_80": a_calib, "cand_a_calib_80_stable": a_calib_stable,
                            "cand_a_alpha": a_alpha})
        for rec in a_folds:
            log_cv_fold(rec["fold"], rec["test_season"],
                        {"a_nll": rec["nll"], "a_mae": rec["mae"], "a_calib_80": rec["calib_80"]})

        # ── Candidate B: Ridge EB ──────────────────────────────────────────
        print("\n[2/4] Candidate B — Ridge (EB features)")
        b_nll, b_mae, b_calib, b_calib_stable, b_folds, b_alpha, b_feat = _walk_forward_cv_ridge(df_eng, "eb", "B")
        _print_fold_table("Candidate B (Ridge EB)", b_folds)
        mlflow.log_metrics({"cand_b_cv_nll": b_nll, "cand_b_cv_mae": b_mae,
                            "cand_b_calib_80": b_calib, "cand_b_calib_80_stable": b_calib_stable,
                            "cand_b_alpha": b_alpha})
        for rec in b_folds:
            log_cv_fold(rec["fold"], rec["test_season"],
                        {"b_nll": rec["nll"], "b_mae": rec["mae"], "b_calib_80": rec["calib_80"]})

        # ── Candidate C: LightGBM ──────────────────────────────────────────
        print("\n[3/4] Candidate C — LightGBM (raw features)")
        c_nll, c_mae, c_calib, c_calib_stable, c_folds, c_feat = _walk_forward_cv_lgbm(df_eng)
        _print_fold_table("Candidate C (LightGBM raw)", c_folds)
        mlflow.log_metrics({"cand_c_cv_nll": c_nll, "cand_c_cv_mae": c_mae,
                            "cand_c_calib_80": c_calib, "cand_c_calib_80_stable": c_calib_stable})
        for rec in c_folds:
            log_cv_fold(rec["fold"], rec["test_season"],
                        {"c_nll": rec["nll"], "c_mae": rec["mae"], "c_calib_80": rec["calib_80"]})

        # ── Ref D: constant mean floor ─────────────────────────────────────
        print("\n[4/4] Ref D — Constant mean (NLL floor, not promotable)")
        d_nll, d_mae, d_folds = _walk_forward_cv_constant(df_eng)
        _print_fold_table("Ref D (Constant mean floor)", d_folds)
        mlflow.log_metrics({"ref_d_cv_nll": d_nll, "ref_d_cv_mae": d_mae})

        # ── Selection ──────────────────────────────────────────────────────
        winner_type, winner_nll = _print_gate_summary(
            a_nll, a_mae, a_calib, a_calib_stable,
            b_nll, b_mae, b_calib, b_calib_stable,
            c_nll, c_mae, c_calib, c_calib_stable,
            d_nll,
        )
        gate_passed = winner_type != "none"

        if force_winner is not None:
            winner_type = force_winner
            winner_nll  = {"ridge_raw": a_nll, "ridge_eb": b_nll, "lgbm": c_nll}[force_winner]
            gate_passed = True
            print(f"\n[--force-winner {force_winner}] Overriding gate-based selection.")

        if winner_type == "none":
            # No gate-passing candidate — pick best NLL, suppress promotion
            winner_type = min(
                [("ridge_raw", a_nll), ("ridge_eb", b_nll), ("lgbm", c_nll)],
                key=lambda x: x[1]
            )[0]
            winner_nll = {"ridge_raw": a_nll, "ridge_eb": b_nll, "lgbm": c_nll}[winner_type]
            gate_passed = False
            print(f"\n  Gate failed — tuning best-NLL candidate ({winner_type}) without promoting.")

        if not promote:
            gate_passed = False
            print("\n[--no-promote] Registry update and S3 upload suppressed.")

        winner_mae = {"ridge_raw": a_mae, "ridge_eb": b_mae, "lgbm": c_mae}[winner_type]
        mlflow.log_params({"winner_type": winner_type, "gate_passed": gate_passed})
        mlflow.log_metrics({"winner_cv_nll": winner_nll, "winner_cv_mae": winner_mae})

        # ── Optuna tuning ──────────────────────────────────────────────────
        print(f"\n{'='*72}")
        print(f"Optuna tuning — winner: {winner_type.upper()}")
        print(f"{'='*72}")
        tuned_params, tuned_nll = _tune_winner(winner_type, df_eng, winner_nll)
        mlflow.log_params({f"tuned_{k}": v for k, v in tuned_params.items()})
        mlflow.log_metrics({"tuned_cv_nll": tuned_nll})

        # ── Final model: all data with tuned params ────────────────────────
        print(f"\nTraining final {winner_type.upper()} on all {len(df_eng)} rows (2021–2025)...")
        feature_set = "eb" if winner_type == "ridge_eb" else "raw"
        X_all, feat_all = _make_X(df_eng, feature_set)
        y_all = df_eng["raw_interaction_residual"].to_numpy(dtype=float)

        if winner_type in ("ridge_raw", "ridge_eb"):
            from sklearn.linear_model import Ridge
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
            final_alpha = tuned_params.get("alpha", a_alpha if winner_type == "ridge_raw" else b_alpha)
            print(f"  alpha={final_alpha:.4f}")
            final_model = Pipeline([("sc", StandardScaler()), ("ridge", Ridge(alpha=final_alpha))])
            final_model.fit(X_all, y_all)
            mu_all = final_model.predict(X_all)
        else:  # lgbm
            from lightgbm import LGBMRegressor
            final_params = {**_LGBM_DEFAULT_PARAMS, **tuned_params}
            print(f"  params={final_params}")
            final_model = LGBMRegressor(**final_params)
            final_model.fit(X_all, y_all)
            mu_all = final_model.predict(X_all)

        global_sigma   = _fit_sigma(y_all, mu_all)
        insample_nll   = _normal_nll(y_all, mu_all, global_sigma)
        insample_mae   = float(np.mean(np.abs(mu_all - y_all)))
        print(f"  In-sample NLL:       {insample_nll:.4f}")
        print(f"  In-sample MAE:       {insample_mae:.5f}")
        print(f"  Walk-forward NLL:    {winner_nll:.4f}")
        print(f"  Global sigma:        {global_sigma:.5f}")
        mlflow.log_metrics({"final_insample_nll": insample_nll, "final_insample_mae": insample_mae,
                            "final_sigma": global_sigma})

        # Sparse cell NLL (informational — all cells are dense in 2021–2025)
        sparse_mask = df_eng["cell_sparsity_flag"].astype(bool).values
        if sparse_mask.sum() > 0:
            sparse_nll = _normal_nll(y_all[sparse_mask], mu_all[sparse_mask], global_sigma)
            print(f"  Sparse-cell NLL:     {sparse_nll:.4f}  ({sparse_mask.sum()} cells)")
            mlflow.log_metric("final_sparse_cell_nll", sparse_nll)
        else:
            print("  Sparse-cell NLL:     N/A (all cells dense — cell_sparsity_flag=False for all rows)")

        # ── Artifact ───────────────────────────────────────────────────────
        artifact = {
            "model":          final_model,
            "model_type":     winner_type,
            "feature_set":    feature_set,
            "feature_cols":   feat_all,
            "sigma":          global_sigma,
            "season_min":     _SEASON_MIN,
            "season_max":     _SEASON_MAX,
            "batter_cats":    _BATTER_CATS,
            "pitcher_cats":   _PITCHER_CATS,
            "target":         "raw_interaction_residual",
            "distribution":   "Normal",
            "output_mu":      "matchup_advantage_mu",
            "output_sigma":   "matchup_advantage_sigma",
            "tuned_params":   tuned_params,
            "tuned_cv_nll":   tuned_nll,
            "cv_nll":         winner_nll,
            "cv_mae":         winner_mae,
            "cand_a_cv_nll":  a_nll,  "cand_a_cv_mae": a_mae,  "cand_a_calib_80": a_calib,
            "cand_b_cv_nll":  b_nll,  "cand_b_cv_mae": b_mae,  "cand_b_calib_80": b_calib,
            "cand_c_cv_nll":  c_nll,  "cand_c_cv_mae": c_mae,  "cand_c_calib_80": c_calib,
            "ref_d_cv_nll":   d_nll,
            "gate_passed":    gate_passed,
        }
        winner_folds = {"ridge_raw": a_folds, "ridge_eb": b_folds, "lgbm": c_folds}[winner_type]
        artifact["cv_fold_records"] = winner_folds

        _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, _ARTIFACT_PATH)
        print(f"\nArtifact saved → {_ARTIFACT_PATH}")

        if promote:
            upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)

        mlflow.log_artifact(str(_ARTIFACT_PATH))
        mlflow.set_tag("sub_model_registry_key", "matchup_v1")
        print(f"  MLflow run_id: {mlflow_run_id}")

        if promote:
            _update_registry(
                cv_nll=winner_nll,
                cv_mae=winner_mae,
                sigma=global_sigma,
                winner_type=winner_type,
                gate_passed=gate_passed,
                feature_cols=feat_all,
                mlflow_run_id=mlflow_run_id,
            )

    # ── Summary ────────────────────────────────────────────────────────────
    arch_label = {"ridge_raw": "Ridge (raw)", "ridge_eb": "Ridge (EB)", "lgbm": "LightGBM (raw)"}[winner_type]
    print("\n" + "=" * 76)
    if gate_passed:
        print(
            f"matchup_v1 result: PROMOTED ({arch_label}, "
            f"CV NLL {winner_nll:.4f} < floor {d_nll:.4f})"
        )
        print("\nNext steps (Story 8.3):")
        print("  1. Implement generate_matchup_signals.py using compute_matchup_signal_soft()")
        print("  2. Load matchup_v1.pkl, emit matchup_advantage_mu / matchup_advantage_sigma")
        print("  3. Store signals in mart_sub_model_signals, backfill 2021–2026")
    else:
        print(f"matchup_v1 result: NOT PROMOTED")
        print(f"  Best candidate: {arch_label}, NLL {winner_nll:.4f}, floor {d_nll:.4f}")
    print(f"\n=== DONE — MLflow run: {mlflow_run_id} ===")
    print("=" * 76)
    return mlflow_run_id


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Train matchup_v1 (Story 8.2)")
    parser.add_argument("--no-promote", action="store_true",
                        help="Run CV and save artifact locally; skip S3 upload and registry update.")
    parser.add_argument("--force-winner", choices=["ridge_raw", "ridge_eb", "lgbm"],
                        default=None, metavar="{ridge_raw,ridge_eb,lgbm}",
                        help="Override gate-based selection and promote the specified architecture.")
    args = parser.parse_args()
    train(promote=not args.no_promote, force_winner=args.force_winner)


if __name__ == "__main__":
    main()
