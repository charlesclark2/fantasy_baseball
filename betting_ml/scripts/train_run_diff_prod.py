"""Epic 1 (Story 1.3) — Market-blind production retrain for run_differential.

Two critical changes vs. the 7.MA artifact (current production v1):
  1. Full Phase 8 feature store — switches from feature_columns.json (294 pre-Phase 8
     features) to load_features() full numeric set, giving run_diff its first exposure
     to ELO, FIP projections, CSW%, catcher framing, H2H matchup wOBA, etc.
  2. Market exclusion — home_win_prob_consensus was the #1 permutation-importance
     feature (imp=0.040, 3× the signal of #2) in the 8.W analysis; the model was
     effectively a market-following machine.

Artifact written to:
    betting_ml/models/run_differential/ngboost_market_blind_2026.pkl

CV results written to Snowflake (dev by default):
    baseball_data.betting_ml_dev.cv_results_run_diff   (TARGET_ENV != "prod")
    baseball_data.betting_ml.cv_results_run_diff        (TARGET_ENV == "prod")

Gate: CV MAE must be <= 3.4724 (v1 production baseline).

Notes:
  - LogNormal excluded: run_differential can be negative (home team loses),
    which violates LogNormal's strictly-positive support.
  - Standard sample weights (no decay): decay-weighting was introduced for
    total_runs in 8.N; run_diff uses the standard non-weighted setup.

Usage:
    uv run python betting_ml/scripts/train_run_diff_prod.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_ARTIFACT_PATH = (
    PROJECT_ROOT / "betting_ml" / "models" / "run_differential" / "ngboost_market_blind_2026.pkl"
)
_FEATURE_COLS_PATH = (
    PROJECT_ROOT / "betting_ml" / "models" / "run_differential" / "feature_columns_market_blind.json"
)
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/run_differential/ngboost_market_blind_2026.pkl"

# Market-blind baseline gate. v1 production was 3.4724 but included market features
# (home_win_prob_consensus #1, imp=0.040) which gave "free" MAE improvement.
# 3.4981 is the true market-blind baseline established in Epic 1.
_CV_MAE_GATE = 3.4981

_DIST_NAME = "Normal"
_MAX_DEPTH = 3
_N_ESTIMATORS = 200  # 7.MA found 200 optimal for run_diff (vs 500 for total_runs)

TARGET_ENV = os.getenv("TARGET_ENV", "dev")
_ML_SCHEMA = "betting_ml" if TARGET_ENV == "prod" else "betting_ml_dev"

_NON_FEAT = _NON_FEATURE_COLS | {"split"}

# Market-derived columns excluded from training (same canonical set as home_win).
# home_win_prob_consensus was the #1 permutation-importance feature for run_diff
# (imp=0.040 — 3× the importance of #2 pythagorean_win_exp_diff).
_MARKET_COLS_TO_EXCLUDE: set[str] = {
    # Raw decimal / American odds
    "home_moneyline_decimal", "away_moneyline_decimal",
    "home_moneyline", "away_moneyline",
    # Opening / closing implied probabilities
    "home_win_prob_sharp", "away_win_prob_sharp",
    "home_open_win_prob", "away_open_win_prob",
    "home_close_win_prob", "away_close_win_prob",
    # Consensus win probability — #1 feature in current production model
    "home_win_prob_consensus", "away_win_prob_consensus",
    # Line movement
    "home_h2h_line_movement", "away_h2h_line_movement",
    "home_open_line", "away_open_line",
    # Totals market
    "open_total", "close_total", "total_line", "total_line_consensus",
    # Public betting signals (8.R)
    "pct_home_ml", "pct_away_ml",
    "ml_sharp_signal", "total_sharp_signal",
    "has_public_betting",
    # Market consensus spread / book availability (8.T)
    "ml_implied_prob_std", "ml_implied_prob_range",
    "sharp_soft_ml_spread", "n_books_available",
    "stale_book_flag", "totals_line_std", "totals_line_range",
    "ml_consensus_std",
}

_ALL_EXCLUDED = _NON_FEAT | _MARKET_COLS_TO_EXCLUDE


def _run_cv(df, feature_cols: list[str]) -> tuple[list[float], list[dict]]:
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    fold_maes: list[float] = []
    fold_rows: list[dict] = []

    folds = list(all_season_splits(df, min_train_seasons=3))
    print(f"\nRunning {len(folds)} season-forward CV folds...")

    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "run_differential"].values
        yev = df.loc[eval_idx, "run_differential"].values

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_MAX_DEPTH)
        ngb = NGBRegressor(Dist=Normal, n_estimators=_N_ESTIMATORS, Base=base, verbose=False)

        t0 = time.time()
        ngb.fit(Xtr.values, ytr)
        elapsed = time.time() - t0

        y_pred = ngb.predict(Xev.values)
        mae = float(np.mean(np.abs(yev - y_pred)))
        fold_maes.append(mae)

        fold_rows.append({
            "fold": str(eval_year),
            "n_eval": len(yev),
            "mae": mae,
            "elapsed_s": elapsed,
        })
        print(f"  {eval_year}: MAE={mae:.4f}  n={len(yev)}  ({elapsed:.0f}s)")

    return fold_maes, fold_rows


def _write_snowflake(fold_rows: list[dict], mean_mae: float, n_features: int) -> None:
    print(f"\nWriting CV results to Snowflake ({_ML_SCHEMA})...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS baseball_data.{_ML_SCHEMA}")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS baseball_data.{_ML_SCHEMA}.cv_results_run_diff (
                fold         VARCHAR,
                n_eval       INTEGER,
                mae          FLOAT,
                elapsed_s    FLOAT,
                retrain_tag  VARCHAR,
                n_features   INTEGER,
                loaded_at    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute(
            f"ALTER TABLE baseball_data.{_ML_SCHEMA}.cv_results_run_diff "
            "ADD COLUMN IF NOT EXISTS retrain_tag VARCHAR"
        )
        cur.execute(
            f"ALTER TABLE baseball_data.{_ML_SCHEMA}.cv_results_run_diff "
            "ADD COLUMN IF NOT EXISTS n_features INTEGER"
        )
        for row in fold_rows:
            cur.execute(
                f"""
                INSERT INTO baseball_data.{_ML_SCHEMA}.cv_results_run_diff
                    (fold, n_eval, mae, elapsed_s, retrain_tag, n_features)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (row["fold"], row["n_eval"], row["mae"],
                 row["elapsed_s"], "market_blind_epic1", n_features),
            )
        conn.commit()
        print(f"  Inserted {len(fold_rows)} fold rows  (mean MAE={mean_mae:.4f})")
    finally:
        conn.close()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-snowflake", action="store_true",
        help="Skip Snowflake CV write (useful for local dry-runs)",
    )
    args = parser.parse_args()

    print("=== RUN DIFFERENTIAL — MARKET-BLIND PRODUCTION RETRAIN (Epic 1, Story 1.3) ===\n")
    print(f"  Schema:      baseball_data.{_ML_SCHEMA}")
    print(f"  Features:    load_features() full Phase 8 store (market cols excluded)")
    print(f"  Dist:        NGBoost Normal  (LogNormal excluded — run_diff can be negative)")
    print(f"  n_estimators:{_N_ESTIMATORS}   max_depth:{_MAX_DEPTH}")

    print("\nLoading historical features from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= 2021].reset_index(drop=True)
    print(f"  {len(df):,} rows, seasons {sorted(df['game_year'].unique())}")

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols = [c for c in numeric_cols if c not in _ALL_EXCLUDED]
    print(f"  Feature columns after exclusions: {len(feature_cols)}")
    print(f"    Market cols excluded: {len(_MARKET_COLS_TO_EXCLUDE)}")

    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    # Drop rows without a run_differential label
    df = df[df["run_differential"].notna()].reset_index(drop=True)
    print(f"  Rows with run_differential label: {len(df):,}")

    fold_maes, fold_rows = _run_cv(df, feature_cols)
    mean_mae = float(np.mean(fold_maes))

    print(f"\n{'='*50}")
    print(f"  Mean CV MAE:  {mean_mae:.4f}")
    print(f"  Gate:         <= {_CV_MAE_GATE}")
    gate_pass = mean_mae <= _CV_MAE_GATE
    print(f"  Gate result:  {'PASS' if gate_pass else 'FAIL'}")
    print(f"{'='*50}")

    print("\nFitting final model on all 2021+ data...")
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    pipe_full = build_imputation_pipeline()
    Xall_raw = df[feature_cols]
    yall = df["run_differential"].values

    Xall = pipe_full.fit_transform(Xall_raw).select_dtypes(include=[np.number])
    final_feature_cols = list(Xall.columns)

    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_MAX_DEPTH)
    ngb_final = NGBRegressor(
        Dist=Normal, n_estimators=_N_ESTIMATORS, Base=base, verbose=False
    )
    t0 = time.time()
    ngb_final.fit(Xall.values, yall)
    print(f"  Final fit: {time.time() - t0:.0f}s, {len(yall):,} rows, {len(final_feature_cols)} features")

    # Smoke test — run_diff can be negative so check reasonable range
    sample_pred = ngb_final.predict(Xall.values[:5])
    assert all(-20.0 < p < 20.0 for p in sample_pred), f"Smoke test failed: {sample_pred}"
    print(f"  Smoke test passed: {sample_pred.round(2)}")

    # Save artifact and feature columns
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(ngb_final, _ARTIFACT_PATH)
    _FEATURE_COLS_PATH.write_text(json.dumps(final_feature_cols, indent=2))
    print(f"\nArtifact: {_ARTIFACT_PATH}")
    print(f"Features: {_FEATURE_COLS_PATH}  ({len(final_feature_cols)} cols)")

    from betting_ml.utils.artifact_store import upload_artifact
    upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)

    if not args.no_snowflake:
        _write_snowflake(fold_rows, mean_mae, len(final_feature_cols))

    if not gate_pass:
        print(
            f"\nWARNING: CV MAE {mean_mae:.4f} exceeds gate {_CV_MAE_GATE}. "
            "Do NOT promote to production — investigate feature set or hyperparameters."
        )
        sys.exit(1)

    print(f"""
=== NEXT STEPS ===
Gate PASSED (MAE={mean_mae:.4f} <= {_CV_MAE_GATE}).

1. Compare predictions vs. v1 artifact on today's games:
     uv run python scripts/compare_model_versions.py --target run_differential

2. Update model_registry.yaml:
   - Set artifact_path: {_ARTIFACT_PATH.relative_to(PROJECT_ROOT)}
   - Set feature_columns_path: {_FEATURE_COLS_PATH.relative_to(PROJECT_ROOT)}
   - Bump model_version: v2
   - Record cv_mae: {mean_mae:.4f}

3. Commit artifact and registry:
   git add betting_ml/models/run_differential/ngboost_market_blind_2026.pkl \\
           betting_ml/models/run_differential/feature_columns_market_blind.json \\
           betting_ml/models/model_registry.yaml
   git commit -m "Epic 1: run_diff market-blind retrain (v2, MAE={mean_mae:.4f})"
""")


if __name__ == "__main__":
    main()
