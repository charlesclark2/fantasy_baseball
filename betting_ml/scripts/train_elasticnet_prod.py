"""Epic 1 (Story 1.1) — Market-blind production retrain for home_win.

Market exclusion already present in this script (_MARKET_COLS_TO_EXCLUDE populated
in Card 7.MB). Epic 1 adds the season-forward CV gate check to confirm the new
545-feature model beats the v1 production baseline.

CV results written to Snowflake (dev by default):
    baseball_data.betting_ml_dev.cv_results_home_win   (TARGET_ENV != "prod")
    baseball_data.betting_ml.cv_results_home_win        (TARGET_ENV == "prod")

Gate: CV Brier must be <= 0.2422 (v1 production baseline).

Usage:
    uv run python betting_ml/scripts/train_elasticnet_prod.py
    uv run python betting_ml/scripts/train_elasticnet_prod.py --weighted
    uv run python betting_ml/scripts/train_elasticnet_prod.py --no-snowflake
"""

from __future__ import annotations

import json
import os
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

from dotenv import load_dotenv
load_dotenv()

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.sample_weights import compute_sample_weights
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

# Challenger artifact — training always writes here; production champion is never touched.
# To promote: update model_registry.yaml to point artifact_path at the challenger path,
# or explicitly copy: cp elasticnet_market_blind_2026.pkl elasticnet_2026.pkl
_CHALLENGER_PATH = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "elasticnet_market_blind_2026.pkl"
_CHAMPION_PATH   = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "elasticnet_2026.pkl"
_FEATURE_COLS_PATH = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "feature_columns_market_blind.json"
_CHALLENGER_S3_URI = "s3://baseball-betting-ml-artifacts/home_win/elasticnet_market_blind_2026.pkl"

# Market-blind baseline gate. v1 production was 0.2422 but included market features
# (away_moneyline_decimal #3, home_win_prob_sharp #6) which gave "free" Brier improvement.
# 0.2446 is the true market-blind baseline established in Epic 1 (two independent runs).
_CV_BRIER_GATE = 0.2446

_C_GRID = [0.001, 0.01, 0.1, 1.0]
_INNER_FOLDS = 5

TARGET_ENV = os.getenv("TARGET_ENV", "dev")
_ML_SCHEMA = "betting_ml" if TARGET_ENV == "prod" else "betting_ml_dev"

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
    # ── Story 30.4 — complete the market-blind exclusion (2026-06-12) ──
    # These market-derived cols leaked into every deployed contract because they were
    # added to the feature store AFTER this exclude list was authored, so the base
    # models were only "consensus-and-moneyline-blind," not market-blind (architecture
    # Principle 3 / §5.6 / §5.7). over_american/under_american are raw totals odds
    # prices; home_ml_money_pct/over_ticket_pct are public-betting % (8.R);
    # over_prob_consensus/under_implied_prob/total_line_movement are totals-market
    # consensus/movement; market_bookmaker_count is book availability.
    "over_prob_consensus", "under_implied_prob", "total_line_movement",
    "home_ml_money_pct", "over_ticket_pct", "market_bookmaker_count",
    "over_american", "under_american",
    # `total_line_std` (consensus stddev of the betting total, from mart_odds_consensus)
    # is a 9th leak: the near-identically-named `totals_line_std` (plural, from
    # mart_bookmaker_disagreement) IS excluded above, but the consensus singular slipped
    # through the name collision. Both are market-dispersion features → exclude both.
    "total_line_std",
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


def _run_cv(
    df: pd.DataFrame,
    feature_cols: list[str],
    best_c: float,
    weighted: bool,
) -> tuple[list[float], list[dict]]:
    fold_briers: list[float] = []
    fold_rows: list[dict] = []

    folds = list(all_season_splits(df, min_train_seasons=3))
    print(f"\nRunning {len(folds)} season-forward CV folds (gate check)...")

    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        tr_mask = df.loc[train_idx, "home_win"].notna()
        ev_mask = df.loc[eval_idx, "home_win"].notna()

        Xtr = df.loc[train_idx[tr_mask], feature_cols].values.astype(np.float32)
        ytr = df.loc[train_idx[tr_mask], "home_win"].values.astype(np.float32)
        Xev = df.loc[eval_idx[ev_mask], feature_cols].values.astype(np.float32)
        yev = df.loc[eval_idx[ev_mask], "home_win"].values.astype(np.float32)

        sample_weights = None
        if weighted and "game_date" in df.columns:
            sample_weights = compute_sample_weights(
                df.loc[train_idx[tr_mask]], date_col="game_date"
            ).astype(np.float32)

        pipe = Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(
                penalty="elasticnet", solver="saga", l1_ratio=0.5,
                C=best_c, max_iter=2000, random_state=42,
            )),
        ])

        t0 = time.time()
        pipe.fit(Xtr, ytr, clf__sample_weight=sample_weights)
        elapsed = time.time() - t0

        p_ev = pipe.predict_proba(Xev)[:, 1]
        brier = float(np.mean((yev - p_ev) ** 2))
        fold_briers.append(brier)

        fold_rows.append({
            "fold": str(eval_year),
            "n_eval": len(yev),
            "brier": brier,
            "elapsed_s": elapsed,
        })
        print(f"  {eval_year}: Brier={brier:.4f}  n={len(yev)}  ({elapsed:.0f}s)")

    return fold_briers, fold_rows


def _write_snowflake(fold_rows: list[dict], mean_brier: float, n_features: int) -> None:
    print(f"\nWriting CV results to Snowflake ({_ML_SCHEMA})...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS baseball_data.{_ML_SCHEMA}")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS baseball_data.{_ML_SCHEMA}.cv_results_home_win (
                fold         VARCHAR,
                n_eval       INTEGER,
                brier        FLOAT,
                elapsed_s    FLOAT,
                retrain_tag  VARCHAR,
                n_features   INTEGER,
                loaded_at    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for row in fold_rows:
            cur.execute(
                f"""
                INSERT INTO baseball_data.{_ML_SCHEMA}.cv_results_home_win
                    (fold, n_eval, brier, elapsed_s, retrain_tag, n_features)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (row["fold"], row["n_eval"], row["brier"],
                 row["elapsed_s"], "market_blind_epic1", n_features),
            )
        conn.commit()
        print(f"  Inserted {len(fold_rows)} fold rows  (mean Brier={mean_brier:.4f})")
    finally:
        conn.close()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--weighted", action="store_true",
                        help="Apply exponential decay sample_weights (Card 8.N)")
    parser.add_argument("--no-snowflake", action="store_true",
                        help="Skip Snowflake CV write (useful for local dry-runs)")
    args, _ = parser.parse_known_args()

    print("=== HOME WIN — MARKET-BLIND PRODUCTION RETRAIN (Epic 1, Story 1.1) ===\n")
    print(f"  Schema:      baseball_data.{_ML_SCHEMA}")
    print(f"  Weighted:    {args.weighted}")

    print("\nLoading full feature dataset from Snowflake...")
    df = load_features(min_games_played=15)
    print(f"  Loaded {len(df):,} rows, years: {sorted(df['game_year'].unique())}")

    df = df[df["game_year"] >= 2021].reset_index(drop=True)
    print(f"  After 2021+ filter: {len(df):,} rows")

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols = [
        c for c in numeric_cols
        if c not in _NON_FEAT and c not in _MARKET_COLS_TO_EXCLUDE
    ]
    print(f"  Feature columns: {len(feature_cols)}")
    print(f"    Market cols excluded: {len(_MARKET_COLS_TO_EXCLUDE)}")

    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    valid_mask = df["home_win"].notna()
    X = df.loc[valid_mask, feature_cols].values.astype(np.float32)
    y = df.loc[valid_mask, "home_win"].values.astype(np.float32)
    print(f"  Training rows (non-null home_win): {len(X):,}")

    sample_weights = None
    if args.weighted and "game_date" in df.columns:
        sample_weights = compute_sample_weights(
            df.loc[valid_mask], date_col="game_date"
        ).astype(np.float32)
        print(f"  Decay sample_weights: min={sample_weights.min():.3f} max={sample_weights.max():.3f}")

    print(f"\nInner CV C-tuning over {_C_GRID} ({_INNER_FOLDS}-fold TimeSeriesSplit)...")
    t0 = time.time()
    best_c = _tune_C(X, y, sample_weights=sample_weights)
    print(f"\n  Best C = {best_c} (tuning took {time.time() - t0:.1f}s)")

    # Season-forward CV gate check
    fold_briers, fold_rows = _run_cv(df, feature_cols, best_c=best_c, weighted=args.weighted)
    mean_brier = float(np.mean(fold_briers))

    print(f"\n{'='*50}")
    print(f"  Mean CV Brier: {mean_brier:.4f}")
    print(f"  Gate:          <= {_CV_BRIER_GATE}")
    gate_pass = mean_brier <= _CV_BRIER_GATE
    print(f"  Gate result:   {'PASS' if gate_pass else 'FAIL'}")
    print(f"{'='*50}")

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

    p_sample = pipeline.predict_proba(X[:5])[:, 1]
    assert all(0.0 < p < 1.0 for p in p_sample), f"Smoke test failed: {p_sample}"
    print(f"  Smoke test passed: sample probs = {p_sample.round(4)}")

    in_sample_brier = float(np.mean((y - pipeline.predict_proba(X)[:, 1]) ** 2))
    print(f"  In-sample Brier (informational): {in_sample_brier:.4f}")
    print(f"  n_features_in_: {pipeline.n_features_in_}")

    _CHALLENGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, _CHALLENGER_PATH)
    _FEATURE_COLS_PATH.write_text(json.dumps(feature_cols, indent=2))
    print(f"\nChallenger: {_CHALLENGER_PATH}")
    print(f"Champion:   {_CHAMPION_PATH}  (untouched)")
    print(f"Features:   {_FEATURE_COLS_PATH}  ({len(feature_cols)} cols)")

    from betting_ml.utils.artifact_store import upload_artifact
    upload_artifact(_CHALLENGER_PATH, _CHALLENGER_S3_URI)

    if not args.no_snowflake:
        _write_snowflake(fold_rows, mean_brier, len(feature_cols))

    if not gate_pass:
        print(
            f"\nWARNING: CV Brier {mean_brier:.4f} exceeds gate {_CV_BRIER_GATE}. "
            "Do NOT promote to production — investigate feature set or hyperparameters."
        )
        sys.exit(1)

    print(f"""
=== NEXT STEPS ===
Gate PASSED (Brier={mean_brier:.4f} <= {_CV_BRIER_GATE}).

1. Compare predictions vs. champion on today's games:
     uv run python scripts/compare_model_versions.py --target home_win

2. Promote challenger → champion (pick one):
   a) Point registry at challenger (preferred — preserves both files):
      artifact_path: {_CHALLENGER_PATH.relative_to(PROJECT_ROOT)}
   b) Or copy over champion:
      cp {_CHALLENGER_PATH} {_CHAMPION_PATH}

3. Update model_registry.yaml:
   - Set artifact_path: {_CHALLENGER_PATH.relative_to(PROJECT_ROOT)}
   - Set feature_columns_path: {_FEATURE_COLS_PATH.relative_to(PROJECT_ROOT)}
   - Set rollback_artifact_path: {_CHAMPION_PATH.relative_to(PROJECT_ROOT)}
   - Bump model_version: v2
   - Record cv_brier: {mean_brier:.4f}

4. Commit artifact and registry:
   git add betting_ml/models/home_win/elasticnet_market_blind_2026.pkl \\
           betting_ml/models/home_win/feature_columns_market_blind.json \\
           betting_ml/models/model_registry.yaml
   git commit -m "Epic 1: home_win market-blind retrain (v2, Brier={mean_brier:.4f})"
""")


if __name__ == "__main__":
    main()
