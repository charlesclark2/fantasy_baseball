"""
retrain_bullpen_17_0.py — Epic 17.0

Story 17.0: Retrain bullpen_v2 on extended window (2021-2026).
Root cause: Hypothesis B confirmed — feature distribution drift in bullpen_mu.
2026 bullpen_mu mean=1.590 vs training mean=1.423 (+0.2882σ), but actual runs flat.
Fix: extend training window to include 2026 so model calibrates to current feature dist.

Spec:
  - Same 24 features as current champion (FEATURE_COLS)
  - Same tuned_params as current champion (loaded from bullpen_v2.pkl)
  - Candidate B architecture (two-stage starter-IP → bullpen NegBin)
  - Walk-forward CV, recent 5 folds (2022, 2023, 2024, 2025, 2026)
  - Promotion gate: NegBin NLL < 1.8852 AND calib_80 ≥ 0.80
  - On pass: overwrite betting_ml/models/sub_models/bullpen_v2.pkl locally
  - Skip S3 upload (promote after OOD gate check passes in Step 3)

Usage:
    uv run python betting_ml/scripts/retrain_bullpen_17_0.py
    uv run python betting_ml/scripts/retrain_bullpen_17_0.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy connectable", category=UserWarning)

import joblib
import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

# Import shared utilities from the main training script
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

_PARQUET_PATH  = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v2.pkl"

_STORY          = "17.0"
_MIN_YEAR       = 2021          # parquet coverage starts 2021
_N_RECENT_FOLDS = 5
_CHAMPION_NLL   = 1.8852        # Story 17.0 gate: must beat this
_CHAMPION_R     = 1.4853        # informational: previous r


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


def _cv_candidate_b(df: pd.DataFrame, tuned_params: dict) -> tuple[float, float, float, list[dict]]:
    """Recent-5-fold walk-forward CV for Candidate B. Returns (mean_nll, mean_calib, mean_r, fold_records)."""
    from lightgbm import LGBMRegressor

    seasons = sorted(df[_YEAR_COL].unique())
    n_folds = min(_N_RECENT_FOLDS, len(seasons) - 1)
    folds   = [(seasons[:i], seasons[i]) for i in range(len(seasons) - n_folds, len(seasons))]

    print(f"\n  Walk-forward CV: {n_folds} folds, test seasons = {[f[1] for f in folds]}")
    print(f"  {'Fold':>4}  {'Test':>6}  {'NLL':>8}  {'calib80':>8}  {'r':>6}  {'n_test':>7}  {'p20_cov':>8}")

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

        denom = max(fold_avg_bp_outs, 1e-3)
        scale_tr = np.where(np.isnan(p20_tr), 1.0, (27.0 - p20_tr) / denom)
        scale_te = np.where(np.isnan(p20_te), 1.0, (27.0 - p20_te) / denom)

        mu_adj_tr = np.clip(mu_base_tr * scale_tr, 1e-6, None)
        mu_adj_te = np.clip(mu_base_te * scale_te, 1e-6, None)

        r     = _fit_negbin_r(y_tr, mu_adj_tr)
        nll   = _negbin_nll(y_te, mu_adj_te, r)
        calib = _negbin_calib_80(y_te, mu_adj_te, r)
        p20_cov = float(valid_tr.mean())

        marker = " ← 2026 OOS" if test_season == 2026 else ""
        print(f"  {len(fold_records)+1:>4}  {test_season:>6}  {nll:>8.4f}  {calib:>8.4f}  "
              f"{r:>6.4f}  {len(y_te):>7,}  {p20_cov:>8.3f}{marker}")

        fold_records.append({
            "fold": len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season": int(test_season),
            "n_train": int(len(y_tr)),
            "n_test": int(len(y_te)),
            "nll": round(nll, 4),
            "calib_80": round(calib, 4),
            "r": round(r, 4),
            "p20_coverage": round(p20_cov, 4),
            "fold_avg_bp_outs": round(fold_avg_bp_outs, 3),
        })

    mean_nll   = float(np.mean([f["nll"]     for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    mean_r     = float(np.mean([f["r"]        for f in fold_records]))
    return mean_nll, mean_calib, mean_r, fold_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 17.0 — bullpen_v2 retrain on 2021-2026")
    parser.add_argument("--dry-run", action="store_true", help="CV only; do not save artifact.")
    args = parser.parse_args()

    print("=" * 70)
    print(f"Story {_STORY} — bullpen_v2 retrain (2021-2026 extended window)")
    print(f"  Gate:  NLL < {_CHAMPION_NLL} AND calib_80 >= {_CALIB_80_GATE}")
    print(f"  Root cause: Hypothesis B (feature drift, not real-world scoring change)")
    print("=" * 70)

    if not _ARTIFACT_PATH.exists():
        print(f"ERROR: {_ARTIFACT_PATH} not found.")
        sys.exit(1)

    champion = joblib.load(_ARTIFACT_PATH)
    tuned_params = champion["tuned_params"]
    print(f"\nLoaded champion: candidate={champion.get('candidate')}, "
          f"cv_nll={champion.get('cv_nll')}, r={champion.get('r'):.4f}")
    print(f"Tuned params: {tuned_params}")

    print("\nLoading data (2021-2026)...")
    df = _load_data()

    print("\nRunning Candidate B walk-forward CV...")
    mean_nll, mean_calib, mean_r, fold_records = _cv_candidate_b(df, tuned_params)

    print(f"\n{'─' * 70}")
    print(f"  Mean NLL:      {mean_nll:.4f}  (gate: < {_CHAMPION_NLL})")
    print(f"  Mean calib_80: {mean_calib:.4f}  (gate: >= {_CALIB_80_GATE})")
    print(f"  Mean r:        {mean_r:.4f}  (champion r: {_CHAMPION_R})")

    nll_pass   = mean_nll < _CHAMPION_NLL
    calib_pass = mean_calib >= _CALIB_80_GATE
    story_pass = nll_pass and calib_pass

    print(f"\n  NLL gate:      {'PASS ✓' if nll_pass else 'FAIL ✗'}  "
          f"({mean_nll:.4f} {'<' if nll_pass else '>='} {_CHAMPION_NLL})")
    print(f"  calib_80 gate: {'PASS ✓' if calib_pass else 'FAIL ✗'}  "
          f"({mean_calib:.4f} {'>=' if calib_pass else '<'} {_CALIB_80_GATE})")
    print(f"\n  Story 17.0 gate: {'PASS — proceed to Step 3 (OOD gate check)' if story_pass else 'FAIL — investigate before proceeding'}")
    print("=" * 70)

    if not story_pass:
        print("\nGate FAILED. Do not proceed to Step 3.")
        fold_2026 = next((f for f in fold_records if f["test_season"] == 2026), None)
        if fold_2026:
            print(f"  2026 fold: NLL={fold_2026['nll']:.4f}  calib_80={fold_2026['calib_80']:.4f}")
        sys.exit(1)

    if args.dry_run:
        print("\n--dry-run: skipping artifact save.")
        return

    # Gate passed — build final model on all 2021-2026 data
    print("\nBuilding final model on all 2021-2026 data...")
    from lightgbm import LGBMRegressor

    impute_vals = {col: float(df[col].median()) for col in FEATURE_COLS}
    df_final = df.copy()
    for col in FEATURE_COLS:
        df_final[col] = df_final[col].fillna(impute_vals[col])

    p20_all = df_final["starter_ip_p20_outs"].to_numpy(dtype=float)
    valid = ~np.isnan(p20_all)
    new_league_avg_bp_outs = float(np.mean(27.0 - p20_all[valid])) if valid.any() else 12.0

    X_all = df_final[FEATURE_COLS].to_numpy(dtype=float)
    y_all = df_final[_TARGET_COL].to_numpy(dtype=float)

    final_model = LGBMRegressor(random_state=_OPTUNA_SEED, verbose=-1, **tuned_params)
    final_model.fit(X_all, y_all)

    mu_base = np.clip(final_model.predict(X_all), 1e-6, None)
    scale   = np.where(np.isnan(p20_all), 1.0,
                       (27.0 - p20_all) / max(new_league_avg_bp_outs, 1e-3))
    mu_adj  = np.clip(mu_base * scale, 1e-6, None)
    new_r   = _fit_negbin_r(y_all, mu_adj)

    in_sample_nll = _negbin_nll(y_all, mu_adj, new_r)
    in_sample_cal = _negbin_calib_80(y_all, mu_adj, new_r)

    print(f"  New r:                  {new_r:.4f}  (was {_CHAMPION_R})")
    print(f"  New league_avg_bp_outs: {new_league_avg_bp_outs:.3f}  (was {champion.get('league_avg_bullpen_outs', 'n/a'):.3f})")
    print(f"  In-sample NLL:          {in_sample_nll:.4f}")
    print(f"  In-sample calib_80:     {in_sample_cal:.4f}")

    new_artifact = {
        **champion,
        "model":                  final_model,
        "impute_vals":            impute_vals,
        "r":                      new_r,
        "league_avg_bullpen_outs": new_league_avg_bp_outs,
        "cv_nll":                 mean_nll,
        "cv_calib_80":            mean_calib,
        "cv_mean_r":              mean_r,
        "tuned_cv_nll":           mean_nll,
        "cv_fold_records":        fold_records,
        "story":                  _STORY,
        "training_seasons":       sorted(df[_YEAR_COL].unique().tolist()),
        "prev_cv_nll":            champion.get("cv_nll"),
        "prev_r":                 champion.get("r"),
    }

    joblib.dump(new_artifact, _ARTIFACT_PATH)
    print(f"\nArtifact saved → {_ARTIFACT_PATH.relative_to(_PROJECT_ROOT)}")
    print("\nNext steps:")
    print("  Step 3: Run OOD gate check (generate new OOS signals, verify 2026 z ≤ ±1.0σ)")
    print("  Step 4: Update probability_layer.py + sub_model_registry.yaml OOD constants")
    print("  Then:   Re-run generate_bullpen_signals.py --backfill 2021 to update signals table")


if __name__ == "__main__":
    main()
