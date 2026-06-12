"""Epic 1 (Story 1.2) — Market-blind production retrain for total_runs.

Removes market-derived features from the training matrix and applies the 8.N
exponential decay sample weights.  This is the direct fix for the market
circularity problem: total_line_consensus was the #1 permutation-importance
feature (imp=0.064) in the 8.W batch retrain analysis.

Artifact written to:
    betting_ml/models/total_runs/ngboost_market_blind_2026.pkl

CV results written to Snowflake (dev by default):
    baseball_data.betting_ml_dev.cv_results_totals   (TARGET_ENV != "prod")
    baseball_data.betting_ml.cv_results_totals        (TARGET_ENV == "prod")

Gate: CV MAE must be <= 3.5107 (v2 production baseline).

Usage:
    uv run python betting_ml/scripts/train_total_runs_prod.py
    uv run python betting_ml/scripts/train_total_runs_prod.py --weighted
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
from betting_ml.utils.sample_weights import compute_sample_weights
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_ARTIFACT_PATH = (
    PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "ngboost_market_blind_2026.pkl"
)
_FEATURE_COLS_PATH = (
    PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "feature_columns_market_blind.json"
)
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/total_runs/ngboost_market_blind_2026.pkl"

# Market-blind baseline gate. v2 production was 3.5107 but included market features
# (total_line_consensus #1, ml_consensus_std #2) which gave "free" MAE improvement.
# 3.5521 is the true market-blind baseline established in Epic 1.
_CV_MAE_GATE = 3.5521

_DIST_NAME = "Normal"
_MAX_DEPTH = 3
_N_ESTIMATORS = 500

TARGET_ENV = os.getenv("TARGET_ENV", "dev")
_ML_SCHEMA = "betting_ml" if TARGET_ENV == "prod" else "betting_ml_dev"

_NON_FEAT = _NON_FEATURE_COLS | {"split"}

# Market-derived columns excluded from training (same as home_win elasticnet).
# total_line_consensus is the #1 importance feature for total_runs (imp=0.064);
# ml_consensus_std is #2 (imp=0.027).  Both are pure market signals.
_MARKET_COLS_TO_EXCLUDE: set[str] = {
    # Raw decimal / American odds
    "home_moneyline_decimal", "away_moneyline_decimal",
    "home_moneyline", "away_moneyline",
    # Opening / closing implied probabilities
    "home_win_prob_sharp", "away_win_prob_sharp",
    "home_open_win_prob", "away_open_win_prob",
    "home_close_win_prob", "away_close_win_prob",
    # Consensus win probability
    "home_win_prob_consensus", "away_win_prob_consensus",
    # Line movement
    "home_h2h_line_movement", "away_h2h_line_movement",
    "home_open_line", "away_open_line",
    # Totals market — primary circularity source for this target
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
    # consensus/movement; market_bookmaker_count is book availability. (Totals is the
    # primary circularity target — these are exactly the cols that invalidate a
    # model-vs-Bovada totals edge claim.)
    "over_prob_consensus", "under_implied_prob", "total_line_movement",
    "home_ml_money_pct", "over_ticket_pct", "market_bookmaker_count",
    "over_american", "under_american",
    # `total_line_std` (consensus stddev of the betting total, from mart_odds_consensus)
    # is a 9th leak: the near-identically-named `totals_line_std` (plural, from
    # mart_bookmaker_disagreement) IS excluded above, but the consensus singular slipped
    # through the name collision. Both are market-dispersion features → exclude both.
    "total_line_std",
}

# Phase 8 features identified as noise for total_runs (mean_imp ≈ 0 in 8.W analysis).
# ELO captures win probability, not scoring volume.  OAA is a defensive metric with
# limited total-runs signal.  Both pct_diff columns near-zero importance.
_NOISE_COLS_TO_EXCLUDE: set[str] = {
    "away_elo",
    "home_away_off_xwoba_30d_pct_diff",
    "home_team_oaa_blended",
    "home_away_starter_k_pct_std_pct_diff",
}

_ALL_EXCLUDED = _NON_FEAT | _MARKET_COLS_TO_EXCLUDE | _NOISE_COLS_TO_EXCLUDE


def _run_cv(df, feature_cols: list[str], weighted: bool) -> tuple[list[float], list[dict]]:
    fold_maes: list[float] = []
    fold_rows: list[dict] = []

    folds = list(all_season_splits(df, min_train_seasons=3))
    print(f"\nRunning {len(folds)} season-forward CV folds...")

    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values
        yev = df.loc[eval_idx, "total_runs"].values

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        sample_weights = None
        if weighted and "game_date" in df.columns:
            sample_weights = compute_sample_weights(
                df.loc[train_idx], date_col="game_date"
            )

        from ngboost import NGBRegressor
        from ngboost.distns import Normal
        from sklearn.tree import DecisionTreeRegressor

        base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_MAX_DEPTH)
        ngb = NGBRegressor(Dist=Normal, n_estimators=_N_ESTIMATORS, Base=base, verbose=False)

        t0 = time.time()
        ngb.fit(Xtr.values, ytr, sample_weight=sample_weights)
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
            CREATE TABLE IF NOT EXISTS baseball_data.{_ML_SCHEMA}.cv_results_totals (
                fold         VARCHAR,
                n_eval       INTEGER,
                mae          FLOAT,
                elapsed_s    FLOAT,
                retrain_tag  VARCHAR,
                n_features   INTEGER,
                loaded_at    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for row in fold_rows:
            cur.execute(
                f"""
                INSERT INTO baseball_data.{_ML_SCHEMA}.cv_results_totals
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
        "--weighted", action="store_true",
        help="Apply exponential decay sample_weights (Card 8.N — recommended)",
    )
    parser.add_argument(
        "--no-snowflake", action="store_true",
        help="Skip Snowflake CV write (useful for local dry-runs)",
    )
    args = parser.parse_args()

    print("=== TOTAL RUNS — MARKET-BLIND PRODUCTION RETRAIN (Epic 1, Story 1.2) ===\n")
    print(f"  Schema:  baseball_data.{_ML_SCHEMA}")
    print(f"  Weighted decay: {args.weighted}")

    print("\nLoading historical features from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= 2021].reset_index(drop=True)
    print(f"  {len(df):,} rows, seasons {sorted(df['game_year'].unique())}")

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols = [c for c in numeric_cols if c not in _ALL_EXCLUDED]
    print(f"  Feature columns after exclusions: {len(feature_cols)}")
    print(f"    Market cols excluded:  {len(_MARKET_COLS_TO_EXCLUDE)}")
    print(f"    Noise cols excluded:   {len(_NOISE_COLS_TO_EXCLUDE)}")

    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    fold_maes, fold_rows = _run_cv(df, feature_cols, weighted=args.weighted)
    mean_mae = float(np.mean(fold_maes))

    print(f"\n{'='*50}")
    print(f"  Mean CV MAE:  {mean_mae:.4f}")
    print(f"  Gate:         <= {_CV_MAE_GATE}")
    gate_pass = mean_mae <= _CV_MAE_GATE
    print(f"  Gate result:  {'PASS' if gate_pass else 'FAIL'}")
    print(f"{'='*50}")

    print("\nFitting final model on all 2021+ data...")
    pipe_full = build_imputation_pipeline()

    valid_mask = df["total_runs"].notna()
    Xall_raw = df.loc[valid_mask, feature_cols]
    yall = df.loc[valid_mask, "total_runs"].values

    Xall = pipe_full.fit_transform(Xall_raw).select_dtypes(include=[np.number])
    final_feature_cols = list(Xall.columns)

    sample_weights = None
    if args.weighted and "game_date" in df.columns:
        sample_weights = compute_sample_weights(
            df.loc[valid_mask], date_col="game_date"
        )

    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_MAX_DEPTH)
    ngb_final = NGBRegressor(
        Dist=Normal, n_estimators=_N_ESTIMATORS, Base=base, verbose=False
    )
    t0 = time.time()
    ngb_final.fit(Xall.values, yall, sample_weight=sample_weights)
    print(f"  Final fit: {time.time() - t0:.0f}s, {len(yall):,} rows, {len(final_feature_cols)} features")

    # Smoke test
    sample_pred = ngb_final.predict(Xall.values[:5])
    assert all(0.0 < p < 30.0 for p in sample_pred), f"Smoke test failed: {sample_pred}"
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

1. Compare predictions vs. v2 artifact on today's games:
     uv run python scripts/compare_model_versions.py --target total_runs

2. Update model_registry.yaml:
   - Set artifact_path: {_ARTIFACT_PATH.relative_to(PROJECT_ROOT)}
   - Set feature_columns_path: {_FEATURE_COLS_PATH.relative_to(PROJECT_ROOT)}
   - Bump model_version: v3
   - Record cv_mae: {mean_mae:.4f}

3. Commit artifact and registry:
   git add betting_ml/models/total_runs/ngboost_market_blind_2026.pkl \\
           betting_ml/models/total_runs/feature_columns_market_blind.json \\
           betting_ml/models/model_registry.yaml
   git commit -m "Epic 1: total_runs market-blind retrain (v3, MAE={mean_mae:.4f})"
""")


if __name__ == "__main__":
    main()
