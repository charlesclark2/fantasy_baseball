"""
retrain_bullpen_17_0_retune.py — Epic 17.0 (Optuna retune on extended window)

Story 17.0: Re-tune bullpen_v2 hyperparameters on the extended 2021-2026
training window after the initial retrain attempt failed the NLL gate by a
narrow margin (5-fold mean 1.8912 vs gate 1.8852, delta +0.006).

Root cause of gate failure: champion params were tuned on 2021-2025 data;
adding 2026 shifts the optimum. A fresh Optuna search on the extended window
is expected to close the gap.

Spec:
  - 50 Optuna trials (10 probe + 40 full), minimize mean NegBin NLL across
    5-fold walk-forward CV (test seasons 2022, 2023, 2024, 2025, 2026)
  - Candidate B architecture: LightGBM mean + starter-IP exposure scaling + NegBin r
  - Same hyperparameter search space as original bullpen_v2 Optuna tuning
  - Same 24 FEATURE_COLS as current champion (no sequential features)
  - Promotion gate: 4-fold apples-to-apples mean NLL (folds 2022-2025 only) < 1.8852
  - Both metrics reported: 5-fold mean (2022-2026) AND 4-fold mean (2022-2025)
  - OOD gate: mean |z_2026| ≤ 1.0σ on existing oos_signals_bullpen.parquet
  - Both gates must pass before artifact is saved
  - MLflow experiment: bullpen_v2_retrain_17_0

Usage:
    uv run python betting_ml/scripts/retrain_bullpen_17_0_retune.py
    uv run python betting_ml/scripts/retrain_bullpen_17_0_retune.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable", category=UserWarning)

import joblib
import mlflow
import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.train_bullpen_distributional import (
    FEATURE_COLS,
    _TARGET_COL,
    _YEAR_COL,
    _MIN_R,
    _OPTUNA_SEED,
    _CALIB_80_GATE,
    _fetch_bullpen_runs,
    _fetch_starter_ip_p20,
    _negbin_nll,
    _negbin_calib_80,
    _fit_negbin_r,
)
from betting_ml.utils.mlflow_utils import get_or_create_experiment

_PARQUET_PATH   = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_ARTIFACT_PATH  = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v2.pkl"
_OOS_SIGNALS    = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals" / "oos_signals_bullpen.parquet"
_SCALERS_PATH   = _PROJECT_ROOT / "betting_ml" / "models" / "bayesian" / "signal_scalers.joblib"

_STORY               = "17.0-retune"
_MIN_YEAR            = 2021
_N_RECENT_FOLDS      = 5
_CHAMPION_NLL        = 1.8852       # 4-fold gate (2022-2025 apples-to-apples comparison)
_CHAMPION_R          = 1.4853
_OOD_Z_GATE          = 1.0         # |mean z_2026| must be ≤ this
_MLFLOW_EXPERIMENT   = "bullpen_v2_retrain_17_0"

# Optuna search space bounds — identical to _make_optuna_objective in original script
_OPTUNA_N_EST_MIN    = 100
_OPTUNA_N_EST_MAX    = 800
_OPTUNA_N_EST_STEP   = 50
_OPTUNA_LR_MIN       = 0.005
_OPTUNA_LR_MAX       = 0.2
_OPTUNA_LEAVES_MIN   = 15
_OPTUNA_LEAVES_MAX   = 127
_OPTUNA_MCS_MIN      = 10
_OPTUNA_MCS_MAX      = 100
_OPTUNA_SUB_MIN      = 0.5
_OPTUNA_SUB_MAX      = 1.0
_OPTUNA_COL_MIN      = 0.5
_OPTUNA_COL_MAX      = 1.0
_OPTUNA_PROBE        = 10
_OPTUNA_FULL         = 40          # 50 total


def _load_data() -> pd.DataFrame:
    parquet_df = pd.read_parquet(_PARQUET_PATH)
    parquet_df = parquet_df[parquet_df[_YEAR_COL] >= _MIN_YEAR].copy()
    for col in FEATURE_COLS:
        if col in parquet_df.columns:
            parquet_df[col] = pd.to_numeric(parquet_df[col], errors="coerce")

    runs_df = _fetch_bullpen_runs(_MIN_YEAR)
    ip_df   = _fetch_starter_ip_p20(_MIN_YEAR)

    df = parquet_df.merge(
        runs_df[["game_pk", "pitching_team", "bullpen_runs_allowed", "score_delta"]],
        on=["game_pk", "pitching_team"],
        how="inner",
    )
    df = df.merge(
        ip_df[["game_pk", "pitching_team", "starter_ip_p20_outs"]],
        on=["game_pk", "pitching_team"],
        how="left",
    )
    df = df.dropna(subset=[_TARGET_COL]).reset_index(drop=True)
    df[_TARGET_COL] = df[_TARGET_COL].astype(float)
    df["score_delta"] = pd.to_numeric(df["score_delta"], errors="coerce").fillna(0)

    seasons = sorted(df[_YEAR_COL].unique())
    null_p20 = df["starter_ip_p20_outs"].isna().mean()
    print(f"  Dataset: {len(df):,} rows | seasons {seasons} | p20 null rate: {null_p20:.1%}")
    return df


def _cv_candidate_b_with_params(
    df: pd.DataFrame,
    tuned_params: dict,
    folds: list[tuple],
) -> tuple[float, float, float, list[dict]]:
    """Run Candidate B CV with given params and pre-specified folds.
    Returns (mean_nll, mean_calib, mean_r, fold_records).
    """
    from lightgbm import LGBMRegressor

    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        tr = df[df[_YEAR_COL].isin(train_seasons)].copy()
        te = df[df[_YEAR_COL] == test_season].copy()

        impute_vals = {col: float(tr[col].median()) for col in FEATURE_COLS}
        for col in FEATURE_COLS:
            tr[col] = tr[col].fillna(impute_vals[col])
            te[col] = te[col].fillna(impute_vals[col])

        X_tr = tr[FEATURE_COLS].to_numpy(dtype=float)
        y_tr = tr[_TARGET_COL].to_numpy(dtype=float)
        X_te = te[FEATURE_COLS].to_numpy(dtype=float)
        y_te = te[_TARGET_COL].to_numpy(dtype=float)

        p20_tr = tr["starter_ip_p20_outs"].to_numpy(dtype=float)
        p20_te = te["starter_ip_p20_outs"].to_numpy(dtype=float)

        valid_tr = ~np.isnan(p20_tr)
        fold_avg_bp_outs = float(np.mean(27.0 - p20_tr[valid_tr])) if valid_tr.any() else 12.0

        lgb = LGBMRegressor(random_state=_OPTUNA_SEED, verbose=-1, **tuned_params)
        lgb.fit(X_tr, y_tr)

        mu_base_tr = np.clip(lgb.predict(X_tr), 1e-6, None)
        mu_base_te = np.clip(lgb.predict(X_te), 1e-6, None)

        denom    = max(fold_avg_bp_outs, 1e-3)
        scale_tr = np.where(np.isnan(p20_tr), 1.0, (27.0 - p20_tr) / denom)
        scale_te = np.where(np.isnan(p20_te), 1.0, (27.0 - p20_te) / denom)

        mu_adj_tr = np.clip(mu_base_tr * scale_tr, 1e-6, None)
        mu_adj_te = np.clip(mu_base_te * scale_te, 1e-6, None)

        r     = _fit_negbin_r(y_tr, mu_adj_tr)
        nll   = _negbin_nll(y_te, mu_adj_te, r)
        calib = _negbin_calib_80(y_te, mu_adj_te, r)
        p20_cov = float(valid_tr.mean())

        fold_records.append({
            "fold":              len(fold_records) + 1,
            "train_seasons":     list(map(int, train_seasons)),
            "test_season":       int(test_season),
            "n_train":           int(len(y_tr)),
            "n_test":            int(len(y_te)),
            "nll":               round(nll, 4),
            "calib_80":          round(calib, 4),
            "r":                 round(r, 4),
            "p20_coverage":      round(p20_cov, 4),
            "fold_avg_bp_outs":  round(fold_avg_bp_outs, 3),
        })

    mean_nll   = float(np.mean([f["nll"]      for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    mean_r     = float(np.mean([f["r"]        for f in fold_records]))
    return mean_nll, mean_calib, mean_r, fold_records


def _make_candidate_b_objective(df: pd.DataFrame, folds: list[tuple]):
    """Optuna objective: Candidate B (with IP scaling) 5-fold mean NLL."""
    def objective(trial) -> float:
        from lightgbm import LGBMRegressor

        params = {
            "n_estimators":      trial.suggest_int("n_estimators",      _OPTUNA_N_EST_MIN, _OPTUNA_N_EST_MAX, step=_OPTUNA_N_EST_STEP),
            "learning_rate":     trial.suggest_float("learning_rate",   _OPTUNA_LR_MIN, _OPTUNA_LR_MAX, log=True),
            "num_leaves":        trial.suggest_int("num_leaves",        _OPTUNA_LEAVES_MIN, _OPTUNA_LEAVES_MAX),
            "min_child_samples": trial.suggest_int("min_child_samples", _OPTUNA_MCS_MIN, _OPTUNA_MCS_MAX),
            "subsample":         trial.suggest_float("subsample",       _OPTUNA_SUB_MIN, _OPTUNA_SUB_MAX),
            "colsample_bytree":  trial.suggest_float("colsample_bytree",_OPTUNA_COL_MIN, _OPTUNA_COL_MAX),
        }

        fold_nlls = []
        for train_seasons, test_season in folds:
            tr = df[df[_YEAR_COL].isin(train_seasons)].copy()
            te = df[df[_YEAR_COL] == test_season].copy()

            impute_vals = {col: float(tr[col].median()) for col in FEATURE_COLS}
            for col in FEATURE_COLS:
                tr[col] = tr[col].fillna(impute_vals[col])
                te[col] = te[col].fillna(impute_vals[col])

            X_tr = tr[FEATURE_COLS].to_numpy(dtype=float)
            y_tr = tr[_TARGET_COL].to_numpy(dtype=float)
            X_te = te[FEATURE_COLS].to_numpy(dtype=float)
            y_te = te[_TARGET_COL].to_numpy(dtype=float)

            p20_tr = tr["starter_ip_p20_outs"].to_numpy(dtype=float)
            p20_te = te["starter_ip_p20_outs"].to_numpy(dtype=float)

            valid_tr = ~np.isnan(p20_tr)
            fold_avg_bp_outs = float(np.mean(27.0 - p20_tr[valid_tr])) if valid_tr.any() else 12.0

            lgb = LGBMRegressor(random_state=_OPTUNA_SEED, verbose=-1, **params)
            lgb.fit(X_tr, y_tr)

            mu_base_tr = np.clip(lgb.predict(X_tr), 1e-6, None)
            mu_base_te = np.clip(lgb.predict(X_te), 1e-6, None)

            denom    = max(fold_avg_bp_outs, 1e-3)
            scale_tr = np.where(np.isnan(p20_tr), 1.0, (27.0 - p20_tr) / denom)
            scale_te = np.where(np.isnan(p20_te), 1.0, (27.0 - p20_te) / denom)

            mu_adj_tr = np.clip(mu_base_tr * scale_tr, 1e-6, None)
            mu_adj_te = np.clip(mu_base_te * scale_te, 1e-6, None)

            r   = _fit_negbin_r(y_tr, mu_adj_tr)
            nll = _negbin_nll(y_te, mu_adj_te, r)
            fold_nlls.append(nll)

        return float(np.mean(fold_nlls))

    return objective


def _run_ood_check() -> tuple[float, bool]:
    """Run OOD gate: load existing OOS signals, compute 2026 z-scores vs existing scaler.
    Returns (mean_z_2026, gate_pass).
    """
    print("\nRunning OOD gate check...")

    if not _OOS_SIGNALS.exists():
        print(f"  ERROR: OOS signals not found at {_OOS_SIGNALS}")
        return float("nan"), False

    if not _SCALERS_PATH.exists():
        print(f"  ERROR: Signal scalers not found at {_SCALERS_PATH}")
        return float("nan"), False

    df = pd.read_parquet(_OOS_SIGNALS)
    scalers = joblib.load(_SCALERS_PATH)

    if "opp_bullpen_mu" not in scalers:
        print(f"  ERROR: 'opp_bullpen_mu' key not found in signal_scalers.joblib")
        print(f"  Available keys: {list(scalers.keys())}")
        return float("nan"), False

    scaler = scalers["opp_bullpen_mu"]
    season_col = "season" if "season" in df.columns else _YEAR_COL

    if season_col not in df.columns:
        print(f"  ERROR: season column not found in OOS signals. Columns: {list(df.columns)}")
        return float("nan"), False

    if "bullpen_mu" not in df.columns:
        print(f"  ERROR: 'bullpen_mu' column not found in OOS signals. Columns: {list(df.columns)}")
        return float("nan"), False

    df_2026 = df[df[season_col] == 2026].copy()
    if len(df_2026) == 0:
        print("  ERROR: No 2026 rows found in OOS signals.")
        return float("nan"), False

    z_2026 = scaler.transform(df_2026["bullpen_mu"].values.reshape(-1, 1)).ravel()
    mean_z  = float(z_2026.mean())
    abs_z   = float(abs(mean_z))
    gate_pass = abs_z <= _OOD_Z_GATE

    print(f"  2026 rows in OOS signals: {len(df_2026):,}")
    print(f"  2026 mean z-score:        {mean_z:+.4f}  (|z| = {abs_z:.4f})")
    print(f"  OOD gate (|z| ≤ {_OOD_Z_GATE:.1f}): {'PASS ✓' if gate_pass else 'FAIL ✗'}  "
          f"({abs_z:.4f} {'≤' if gate_pass else '>'} {_OOD_Z_GATE:.1f})")

    # Context: breakdown by season
    print("\n  z-score by season (for reference):")
    for yr, grp in df.groupby(season_col):
        if grp["bullpen_mu"].notna().sum() < 10:
            continue
        z_yr = scaler.transform(grp["bullpen_mu"].dropna().values.reshape(-1, 1)).ravel()
        print(f"    {int(yr)}: mean z = {z_yr.mean():+.4f}  std z = {z_yr.std():.4f}  n = {len(z_yr):,}")

    return mean_z, gate_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 17.0 retune — Optuna on 2021-2026 extended window")
    parser.add_argument("--dry-run", action="store_true", help="Do not save artifact even if gates pass.")
    args = parser.parse_args()

    print("=" * 72)
    print(f"Story {_STORY} — bullpen_v2 Optuna retune on 2021-2026 extended window")
    print(f"  Optuna: {_OPTUNA_PROBE + _OPTUNA_FULL} trials (Candidate B objective with IP scaling)")
    print(f"  NLL gate:  4-fold mean (2022-2025) < {_CHAMPION_NLL}  [apples-to-apples]")
    print(f"  OOD gate:  |mean z_2026| ≤ {_OOD_Z_GATE}")
    print(f"  MLflow:    {_MLFLOW_EXPERIMENT}")
    print("=" * 72)

    if not _ARTIFACT_PATH.exists():
        print(f"ERROR: {_ARTIFACT_PATH} not found.")
        sys.exit(1)

    champion = joblib.load(_ARTIFACT_PATH)
    prev_params = champion["tuned_params"]
    print(f"\nLoaded champion: candidate={champion.get('candidate')}, "
          f"cv_nll={champion.get('cv_nll')}, r={champion.get('r'):.4f}")
    print(f"Previous tuned params: {prev_params}")

    print("\nLoading data (2021-2026)...")
    df = _load_data()

    seasons = sorted(df[_YEAR_COL].unique())
    n_folds = min(_N_RECENT_FOLDS, len(seasons) - 1)
    all_folds  = [(seasons[:i], seasons[i]) for i in range(len(seasons) - n_folds, len(seasons))]
    folds_4    = [(tr, te) for tr, te in all_folds if te != 2026]   # 2022-2025 only

    test_seasons = [f[1] for f in all_folds]
    print(f"\nCV folds: {n_folds} folds, test seasons = {test_seasons}")
    print(f"  5-fold mean: seasons {test_seasons}")
    print(f"  4-fold mean (gate): seasons {[f[1] for f in folds_4]}")

    # ── Optuna ────────────────────────────────────────────────────────────────
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    objective = _make_candidate_b_objective(df, all_folds)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )

    print(f"\n[Optuna] Phase 1 — probe ({_OPTUNA_PROBE} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_PROBE, show_progress_bar=True)
    probe_best = study.best_value
    print(f"[Optuna] Probe best NLL: {probe_best:.4f}")

    print(f"[Optuna] Phase 2 — full search ({_OPTUNA_FULL} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_FULL, show_progress_bar=True)

    best_params = study.best_params
    best_optuna_nll = study.best_value
    print(f"[Optuna] Best params:    {best_params}")
    print(f"[Optuna] Best 5-fold NLL: {best_optuna_nll:.4f}  "
          f"(Δ vs prev: {champion.get('cv_nll', float('nan')) - best_optuna_nll:+.4f})")

    # ── Full CV with best params ───────────────────────────────────────────────
    print(f"\nRunning full 5-fold CV with best params...")
    mean_nll_5, mean_calib_5, mean_r_5, fold_records = _cv_candidate_b_with_params(
        df, best_params, all_folds
    )

    # Per-fold table
    print(f"\n  {'Fold':>4}  {'Test':>6}  {'NLL':>8}  {'calib80':>8}  {'r':>6}  {'n_test':>7}")
    for fr in fold_records:
        marker = " ← 2026 OOS" if fr["test_season"] == 2026 else ""
        print(f"  {fr['fold']:>4}  {fr['test_season']:>6}  {fr['nll']:>8.4f}  "
              f"{fr['calib_80']:>8.4f}  {fr['r']:>6.4f}  {fr['n_test']:>7,}{marker}")

    # 4-fold apples-to-apples (2022-2025)
    folds_4_records = [fr for fr in fold_records if fr["test_season"] != 2026]
    mean_nll_4   = float(np.mean([fr["nll"]      for fr in folds_4_records]))
    mean_calib_4 = float(np.mean([fr["calib_80"] for fr in folds_4_records]))
    fold_2026    = next((fr for fr in fold_records if fr["test_season"] == 2026), None)

    print(f"\n  {'─' * 68}")
    print(f"  5-fold mean NLL (2022-2026): {mean_nll_5:.4f}")
    print(f"  4-fold mean NLL (2022-2025): {mean_nll_4:.4f}  ← gate comparison")
    print(f"  4-fold mean calib_80:        {mean_calib_4:.4f}")
    print(f"  2026 fold NLL:               {fold_2026['nll']:.4f}  calib_80={fold_2026['calib_80']:.4f}")

    nll_pass   = mean_nll_4 < _CHAMPION_NLL
    calib_pass = mean_calib_4 >= _CALIB_80_GATE

    print(f"\n  NLL gate (4-fold):   {'PASS ✓' if nll_pass else 'FAIL ✗'}  "
          f"({mean_nll_4:.4f} {'<' if nll_pass else '>='} {_CHAMPION_NLL})")
    print(f"  calib_80 gate:       {'PASS ✓' if calib_pass else 'FAIL ✗'}  "
          f"({mean_calib_4:.4f} {'>=' if calib_pass else '<'} {_CALIB_80_GATE})")

    # ── OOD gate ──────────────────────────────────────────────────────────────
    mean_z_2026, ood_pass = _run_ood_check()

    # ── Combined gate summary ─────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("STORY 17.0 PROMOTION GATES")
    print(f"{'─' * 72}")
    print(f"  1. NLL gate (4-fold 2022-2025 mean < {_CHAMPION_NLL}):")
    print(f"       {mean_nll_4:.4f}  →  {'PASS ✓' if nll_pass else 'FAIL ✗'}  "
          f"(margin: {_CHAMPION_NLL - mean_nll_4:+.4f})")
    print(f"  2. OOD gate (|mean z_2026| ≤ {_OOD_Z_GATE}):")
    print(f"       |{mean_z_2026:.4f}| = {abs(mean_z_2026):.4f}  →  {'PASS ✓' if ood_pass else 'FAIL ✗'}  "
          f"(margin: {_OOD_Z_GATE - abs(mean_z_2026):+.4f})")
    print(f"{'─' * 72}")

    both_pass = nll_pass and calib_pass and ood_pass
    print(f"  Overall: {'BOTH GATES PASS — proceed to promotion' if both_pass else 'GATE FAILURE — do not promote'}")
    print("=" * 72)

    # ── MLflow logging ────────────────────────────────────────────────────────
    mlflow.set_experiment(_MLFLOW_EXPERIMENT)
    get_or_create_experiment(_MLFLOW_EXPERIMENT)

    with mlflow.start_run(run_name=f"17_0_retune") as run:
        mlflow.log_params({
            "story":            _STORY,
            "min_year":         _MIN_YEAR,
            "n_optuna_trials":  _OPTUNA_PROBE + _OPTUNA_FULL,
            "n_folds_total":    n_folds,
            "nll_gate_threshold": _CHAMPION_NLL,
            "ood_z_gate":       _OOD_Z_GATE,
            **{f"best_{k}": v for k, v in best_params.items()},
            **{f"prev_{k}": v for k, v in prev_params.items()},
        })
        mlflow.log_metrics({
            "optuna_best_5fold_nll":  best_optuna_nll,
            "cv_mean_nll_5fold":      mean_nll_5,
            "cv_mean_nll_4fold":      mean_nll_4,
            "cv_mean_calib_4fold":    mean_calib_4,
            "cv_fold_2026_nll":       fold_2026["nll"] if fold_2026 else float("nan"),
            "cv_fold_2026_calib80":   fold_2026["calib_80"] if fold_2026 else float("nan"),
            "ood_mean_z_2026":        mean_z_2026,
            "nll_gate_pass":          float(nll_pass),
            "ood_gate_pass":          float(ood_pass),
            "both_gates_pass":        float(both_pass),
        })
        for fr in fold_records:
            mlflow.log_metrics({
                f"fold_{fr['test_season']}_nll":      fr["nll"],
                f"fold_{fr['test_season']}_calib80":  fr["calib_80"],
                f"fold_{fr['test_season']}_r":        fr["r"],
            })
        mlflow.set_tag("verdict", "PASS" if both_pass else "FAIL")
        mlflow.set_tag("sub_model_registry_key", "bullpen_v2")
        print(f"\n  MLflow run_id: {run.info.run_id}")

    if not both_pass:
        fails = []
        if not nll_pass:
            fails.append(f"NLL {mean_nll_4:.4f} >= {_CHAMPION_NLL} (by {mean_nll_4 - _CHAMPION_NLL:+.4f})")
        if not calib_pass:
            fails.append(f"calib_80 {mean_calib_4:.4f} < {_CALIB_80_GATE}")
        if not ood_pass:
            fails.append(f"|z_2026| {abs(mean_z_2026):.4f} > {_OOD_Z_GATE}")
        print(f"\nFailed gates: {'; '.join(fails)}")
        print("Do not promote. Investigate before next step.")
        sys.exit(1)

    if args.dry_run:
        print("\n--dry-run: skipping artifact save.")
        return

    # ── Build final model on all 2021-2026 data ───────────────────────────────
    print("\nBuilding final model on all 2021-2026 data...")
    from lightgbm import LGBMRegressor

    impute_vals = {col: float(df[col].median()) for col in FEATURE_COLS}
    df_final = df.copy()
    for col in FEATURE_COLS:
        df_final[col] = df_final[col].fillna(impute_vals[col])

    p20_all = df_final["starter_ip_p20_outs"].to_numpy(dtype=float)
    valid   = ~np.isnan(p20_all)
    new_league_avg_bp_outs = float(np.mean(27.0 - p20_all[valid])) if valid.any() else 12.0

    X_all = df_final[FEATURE_COLS].to_numpy(dtype=float)
    y_all = df_final[_TARGET_COL].to_numpy(dtype=float)

    final_model = LGBMRegressor(random_state=_OPTUNA_SEED, verbose=-1, **best_params)
    final_model.fit(X_all, y_all)

    mu_base = np.clip(final_model.predict(X_all), 1e-6, None)
    scale   = np.where(np.isnan(p20_all), 1.0,
                       (27.0 - p20_all) / max(new_league_avg_bp_outs, 1e-3))
    mu_adj  = np.clip(mu_base * scale, 1e-6, None)
    new_r   = _fit_negbin_r(y_all, mu_adj)

    in_sample_nll = _negbin_nll(y_all, mu_adj, new_r)
    in_sample_cal = _negbin_calib_80(y_all, mu_adj, new_r)

    print(f"  New r:                  {new_r:.4f}  (was {_CHAMPION_R})")
    print(f"  New league_avg_bp_outs: {new_league_avg_bp_outs:.3f}  "
          f"(was {champion.get('league_avg_bullpen_outs', float('nan')):.3f})")
    print(f"  In-sample NLL:          {in_sample_nll:.4f}")
    print(f"  In-sample calib_80:     {in_sample_cal:.4f}")

    new_artifact = {
        **champion,
        "model":                   final_model,
        "impute_vals":             impute_vals,
        "r":                       new_r,
        "league_avg_bullpen_outs": new_league_avg_bp_outs,
        "tuned_params":            best_params,
        "cv_nll":                  mean_nll_4,       # 4-fold apples-to-apples is the canonical metric
        "cv_nll_5fold":            mean_nll_5,
        "cv_calib_80":             mean_calib_4,
        "cv_mean_r":               mean_r_5,
        "tuned_cv_nll":            mean_nll_4,
        "cv_fold_records":         fold_records,
        "story":                   _STORY,
        "training_seasons":        sorted(map(int, df[_YEAR_COL].unique().tolist())),
        "prev_cv_nll":             champion.get("cv_nll"),
        "prev_r":                  champion.get("r"),
        "prev_tuned_params":       prev_params,
        "ood_mean_z_2026":         mean_z_2026,
    }

    joblib.dump(new_artifact, _ARTIFACT_PATH)
    print(f"\nArtifact saved → {_ARTIFACT_PATH.relative_to(_PROJECT_ROOT)}")
    print("\nNext steps:")
    print("  Step 3a: uv run python betting_ml/scripts/generate_bullpen_signals.py --backfill 2021")
    print("  Step 3b: Update signal scalers (re-fit opp_bullpen_mu scaler on new signals)")
    print("  Step 4:  Update probability_layer.py OOD constants if scaler changes")
    print("  Step 5:  Update sub_model_registry.yaml with story=17.0, training_seasons=2021-2026")


if __name__ == "__main__":
    main()
