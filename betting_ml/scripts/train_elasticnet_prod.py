"""Card 7.MB — Retrain elasticnet on full 2021–2026 dataset for production deploy.

Trains LogisticRegression (elasticnet, inner-CV C tuning) on all available data.
Serializes the fitted Pipeline to betting_ml/models/home_win/elasticnet_2026.pkl.

After running this script, follow the deploy protocol in docs/model_deploy_runbook.md:
  1. Verify the artifact smoke test passes
  2. Update model_registry.yaml: bump artifact_path, set rollback_artifact_path
  3. Update predict_today.py: set MODEL_VERSION = "v1"
  4. Git tag: git tag model/home_win/v2

Usage:
    uv run python betting_ml/scripts/train_elasticnet_prod.py
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

from sklearn.exceptions import ConvergenceWarning
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features
from betting_ml.utils.sample_weights import compute_sample_weights
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_OUTPUT_PATH_V1 = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "elasticnet_2026.pkl"
_C_GRID = [0.001, 0.01, 0.1, 1.0]
_INNER_FOLDS = 5

# Columns excluded from features (targets + identifiers + market signals)
_NON_FEAT = _NON_FEATURE_COLS | {"split"}

# Market-derived columns excluded from model training so the model generates
# independent signal. These stay in the feature store for use in the betting
# signal comparison layer (model prob vs. market price) but must not flow into
# model training — including them creates circularity that compresses CLV.
# Populated 2026-05-08 based on 8.W per-target feature importance analysis
# (away_moneyline_decimal #3, home_win_prob_sharp #6, home_open_win_prob #11).
_MARKET_COLS_TO_EXCLUDE: set[str] = {
    # Raw decimal / American odds
    "home_moneyline_decimal", "away_moneyline_decimal",
    "home_moneyline", "away_moneyline",
    # Opening / closing implied probabilities (sharp-book derived)
    "home_win_prob_sharp", "away_win_prob_sharp",
    "home_open_win_prob", "away_open_win_prob",
    "home_close_win_prob", "away_close_win_prob",
    # Consensus win probability (market composite)
    "home_win_prob_consensus", "away_win_prob_consensus",
    # Line movement
    "home_h2h_line_movement", "away_h2h_line_movement",
    "home_open_line", "away_open_line",
    # Totals market
    "open_total", "close_total", "total_line",
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


def _tune_C(X: np.ndarray, y: np.ndarray, sample_weights: np.ndarray | None = None) -> float:
    tss = TimeSeriesSplit(n_splits=_INNER_FOLDS)
    best_c, best_ll = _C_GRID[0], float("inf")
    for c in _C_GRID:
        lls = []
        for inner_tr, inner_te in tss.split(X):
            Xi_tr, Xi_te = X[inner_tr], X[inner_te]
            yi_tr, yi_te = y[inner_tr], y[inner_te]
            sw_tr = sample_weights[inner_tr] if sample_weights is not None else None
            pre = Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ])
            Xi_tr_p = pre.fit_transform(Xi_tr)
            Xi_te_p = pre.transform(Xi_te)
            clf = LogisticRegression(
                penalty="elasticnet", solver="saga", l1_ratio=0.5,
                C=c, max_iter=1000, random_state=42,
            )
            clf.fit(Xi_tr_p, yi_tr, sample_weight=sw_tr)
            p = np.clip(clf.predict_proba(Xi_te_p)[:, 1], 1e-7, 1 - 1e-7)
            ll = float(-np.mean(yi_te * np.log(p) + (1 - yi_te) * np.log(1 - p)))
            lls.append(ll)
        mean_ll = float(np.mean(lls))
        if mean_ll < best_ll:
            best_ll, best_c = mean_ll, c
        print(f"  C={c:.3f}: mean_log_loss={mean_ll:.4f}")
    return best_c


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--weighted", action="store_true",
                        help="Apply exponential decay sample_weights (Card 8.N)")
    parser.add_argument("--version", default=None,
                        help="Version tag for the output artifact (e.g. v2). "
                             "Omitting uses the default v1 production path. "
                             "With --version v2, saves to elasticnet_v2_2026.pkl.")
    args, _ = parser.parse_known_args()

    global _OUTPUT_PATH
    if args.version:
        _OUTPUT_PATH = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / f"elasticnet_{args.version}_2026.pkl"
    else:
        _OUTPUT_PATH = _OUTPUT_PATH_V1

    print("=== ELASTICNET PRODUCTION RETRAIN (Card 7.MB) ===\n")
    if args.weighted:
        print("  Weighted mode: exponential decay sample_weights enabled (Card 8.N)\n")

    print("Loading full feature dataset from Snowflake...")
    df = load_features(min_games_played=15)
    print(f"  Loaded {len(df):,} rows, years: {sorted(df['game_year'].unique())}")

    # Filter to 2021+ to match 7.MA training window
    df = df[df["game_year"] >= 2021].reset_index(drop=True)
    print(f"  After 2021+ filter: {len(df):,} rows")

    # Feature selection (numeric only, exclude identifiers/targets/market-blind exclusions)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols = [c for c in numeric_cols if c not in _NON_FEAT and c not in _MARKET_COLS_TO_EXCLUDE]
    print(f"  Feature columns: {len(feature_cols)}")

    # Sort chronologically for inner CV
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    valid_mask = df["home_win"].notna()
    X = df.loc[valid_mask, feature_cols].values.astype(np.float32)
    y = df.loc[valid_mask, "home_win"].values.astype(np.float32)
    print(f"  Training rows (non-null home_win): {len(X):,}")

    # Compute decay sample_weights aligned to valid rows (Card 8.N)
    sample_weights = None
    if args.weighted and "game_date" in df.columns:
        sample_weights = compute_sample_weights(df.loc[valid_mask], date_col="game_date").astype(np.float32)
        print(f"  Decay sample_weights: min={sample_weights.min():.3f} max={sample_weights.max():.3f} sum={sample_weights.sum():.1f}")

    print(f"\nInner CV C-tuning over {_C_GRID} ({_INNER_FOLDS}-fold TimeSeriesSplit)...")
    t0 = time.time()
    best_c = _tune_C(X, y, sample_weights=sample_weights)
    print(f"\n  Best C = {best_c} (tuning took {time.time() - t0:.1f}s)")

    print("\nFitting final pipeline on all training data...")
    t1 = time.time()
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(
            penalty="elasticnet", solver="saga", l1_ratio=0.5,
            C=best_c, max_iter=2000, random_state=42,
        )),
    ])
    pipeline.fit(X, y, clf__sample_weight=sample_weights)
    fit_time = time.time() - t1
    print(f"  Fit complete in {fit_time:.1f}s")

    # Smoke test
    p_sample = pipeline.predict_proba(X[:5])[:, 1]
    assert all(0.0 < p < 1.0 for p in p_sample), f"Smoke test failed: {p_sample}"
    print(f"  Smoke test passed: sample probs = {p_sample.round(4)}")

    in_sample_brier = float(np.mean((y - pipeline.predict_proba(X)[:, 1]) ** 2))
    print(f"  In-sample Brier (informational, not CV): {in_sample_brier:.4f}")
    print(f"  n_features_in_: {pipeline.n_features_in_}")

    # Serialize
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, _OUTPUT_PATH)
    print(f"\nArtifact saved: {_OUTPUT_PATH}")
    print(f"  Best C: {best_c}")
    print(f"  Features: {len(feature_cols)}")
    print(f"  Training rows: {len(X):,}")

    print("""
=== NEXT STEPS (deploy protocol) ===
1. Verify artifact:
     uv run python -c "
     import joblib, numpy as np
     m = joblib.load('betting_ml/models/home_win/elasticnet_2026.pkl')
     p = m.predict_proba(np.zeros((1, m.n_features_in_)))[0, 1]
     assert 0.0 < p < 1.0, f'Bad prob: {p}'
     print(f'OK — p={p:.4f}, n_features={m.n_features_in_}')
     "

2. Update model_registry.yaml:
   - Set artifact_path: betting_ml/models/home_win/elasticnet_2026.pkl
   - Set rollback_artifact_path: betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl
   - Set model_name: elasticnet
   - Set cv_brier: 0.2425, ece_raw: 0.0202
   - Remove calibrator_* fields

3. Update predict_today.py: set MODEL_VERSION = "v1"

4. Commit and tag:
   git add betting_ml/models/home_win/elasticnet_2026.pkl betting_ml/models/model_registry.yaml
   git commit -m "Deploy elasticnet as home_win v1 (Card 7.MB)"
   git tag model/home_win/v2
""")


if __name__ == "__main__":
    main()
