"""
ablate_defense_quality.py — Story 27.4 AC2

Layer-3 ablation: does adding defense_quality_v1 signals improve NLL / Brier
on both total_runs and home_win?

Compares walk-forward temporal CV (2021+ data, season-forward folds):
  - Baseline:  current sub-model signal matrix (feature_pregame_sub_model_signals)
  - With DQ:   + home_defense_quality_mu + away_defense_quality_mu
               + home_oaa_z + away_oaa_z
               + home_sprint_z + away_sprint_z

Uses Ridge (total_runs) and Logistic (home_win) regression for speed.
NLL is estimated as Normal NLL for total_runs (residual std from training fold)
and binary log-loss for home_win.

Gate (Story 27.4 AC2):
  Promote if at least one target shows NLL improvement across ≥ majority of folds.
  Defer otherwise; record verdict and re-eval trigger in this report.

Orthogonality check (AC1):
  Reports |Pearson r| between defense_quality_mu and each existing signal mu.
  Must be < 0.3 for all.

Usage (hand off to user — >1 min):
    uv run python betting_ml/scripts/ablate_defense_quality.py
    uv run python betting_ml/scripts/ablate_defense_quality.py --dry-run
    uv run python betting_ml/scripts/ablate_defense_quality.py --seasons 2023 2024 2025 2026
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_RIDGE_ALPHA = 1000
_LOG_REG_C   = 0.01

# Existing sub-model signal mu columns — used for orthogonality check
_EXISTING_MU_COLS = [
    "run_env_mu_v4",
    "pred_runs_mu_v2",
    "starter_suppression_mu_v1",
    "bullpen_mu_v2",
    "matchup_advantage_mu_v1",
    "env_league_state_mu_v1",
]

_DQ_COLS = [
    "home_defense_quality_mu",
    "away_defense_quality_mu",
    "home_oaa_z",
    "away_oaa_z",
    "home_sprint_z",
    "away_sprint_z",
]

# ---------------------------------------------------------------------------
# Snowflake queries
# ---------------------------------------------------------------------------

_SIGNALS_QUERY = """
SELECT
    game_pk,
    MAX(CASE WHEN signal_name = 'run_env_mu'              AND sub_model_version = 'v4' AND side = 'home' THEN signal_value END) AS run_env_mu_v4,
    MAX(CASE WHEN signal_name = 'pred_runs_mu'            AND sub_model_version = 'v2' AND side = 'home' THEN signal_value END) AS pred_runs_mu_v2,
    MAX(CASE WHEN signal_name = 'starter_suppression_mu'  AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS starter_suppression_mu_v1,
    MAX(CASE WHEN signal_name = 'bullpen_mu'              AND sub_model_version = 'v2' AND side = 'home' THEN signal_value END) AS bullpen_mu_v2,
    MAX(CASE WHEN signal_name = 'matchup_advantage_mu'    AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS matchup_advantage_mu_v1,
    MAX(CASE WHEN signal_name = 'env_league_state_mu'     AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS env_league_state_mu_v1
FROM baseball_data.betting.mart_sub_model_signals
WHERE is_current = TRUE
GROUP BY game_pk
"""

_DQ_MART_QUERY = """
SELECT
    game_pk,
    side,
    defense_quality_mu,
    oaa_z,
    sprint_z
FROM baseball_data.betting.mart_team_defense_quality_rolling
WHERE game_date >= '2021-01-01'
ORDER BY game_pk, side
"""

_OUTCOMES_QUERY = """
SELECT
    game_pk,
    TO_DATE(game_date)                       AS game_date,
    EXTRACT(YEAR FROM game_date)::INTEGER    AS game_year,
    home_final_score + away_final_score      AS total_runs,
    CASE WHEN home_final_score > away_final_score THEN 1 ELSE 0 END AS home_win
FROM baseball_data.betting.mart_game_results
WHERE game_type = 'R'
  AND game_date >= '2021-01-01'
ORDER BY game_date, game_pk
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_signals() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SIGNALS_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=cols)


def _load_dq_mart() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_DQ_MART_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=cols)


def _load_outcomes() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_OUTCOMES_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def _pivot_dq(dq_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot defense quality from long (game_pk, side) to wide (game_pk)."""
    home = dq_df[dq_df["side"] == "home"].copy()
    away = dq_df[dq_df["side"] == "away"].copy()
    home = home[["game_pk", "defense_quality_mu", "oaa_z", "sprint_z"]].rename(columns={
        "defense_quality_mu": "home_defense_quality_mu",
        "oaa_z": "home_oaa_z",
        "sprint_z": "home_sprint_z",
    })
    away = away[["game_pk", "defense_quality_mu", "oaa_z", "sprint_z"]].rename(columns={
        "defense_quality_mu": "away_defense_quality_mu",
        "oaa_z": "away_oaa_z",
        "sprint_z": "away_sprint_z",
    })
    return home.merge(away, on="game_pk", how="outer")


# ---------------------------------------------------------------------------
# CV helpers
# ---------------------------------------------------------------------------

def _normal_nll(y_true: np.ndarray, y_pred: np.ndarray, sigma: float) -> float:
    """Mean Normal NLL: 0.5*log(2π*σ²) + 0.5*(y-μ)²/σ²"""
    return float(np.mean(
        0.5 * np.log(2 * np.pi * sigma ** 2) + 0.5 * ((y_true - y_pred) / sigma) ** 2
    ))


def _binary_logloss(y_true: np.ndarray, p_pred: np.ndarray, eps: float = 1e-7) -> float:
    p = np.clip(p_pred, eps, 1 - eps)
    return float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))


def _brier(y_true: np.ndarray, p_pred: np.ndarray) -> float:
    return float(np.mean((p_pred - y_true) ** 2))


def _fold_cv_totals(df: pd.DataFrame, feature_cols: list[str], tag: str) -> list[dict]:
    results = []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values.astype(float)
        yev = df.loc[eval_idx, "total_runs"].values.astype(float)

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        # Zero-fill remaining NaNs in new DQ columns
        for col in _DQ_COLS:
            if col in Xtr.columns:
                Xtr[col] = Xtr[col].fillna(0.0)
                Xev[col] = Xev[col].fillna(0.0)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)

        # Estimate sigma from training residuals
        train_resid = ytr - model.predict(Xtr.values)
        sigma = max(float(np.std(train_resid)), 0.5)

        mae  = float(np.mean(np.abs(yev - y_pred)))
        nll  = _normal_nll(yev, y_pred, sigma)
        bias = float(np.mean(y_pred - yev))

        results.append({
            "tag": tag, "eval_year": eval_year,
            "n_eval": len(yev), "mae": mae, "nll": nll,
            "bias": bias, "sigma": sigma,
        })
    return results


def _fold_cv_h2h(df: pd.DataFrame, feature_cols: list[str], tag: str) -> list[dict]:
    results = []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "home_win"].values.astype(int)
        yev = df.loc[eval_idx, "home_win"].values.astype(int)

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        for col in _DQ_COLS:
            if col in Xtr.columns:
                Xtr[col] = Xtr[col].fillna(0.0)
                Xev[col] = Xev[col].fillna(0.0)

        # Skip folds with only one class (shouldn't happen, but guard)
        if len(np.unique(ytr)) < 2:
            continue

        model = LogisticRegression(C=_LOG_REG_C, max_iter=500, solver="lbfgs")
        model.fit(Xtr.values, ytr)
        p_pred = model.predict_proba(Xev.values)[:, 1]

        logloss = _binary_logloss(yev, p_pred)
        brier   = _brier(yev, p_pred)

        results.append({
            "tag": tag, "eval_year": eval_year,
            "n_eval": len(yev), "logloss": logloss, "brier": brier,
        })
    return results


# ---------------------------------------------------------------------------
# Orthogonality check
# ---------------------------------------------------------------------------

def _check_orthogonality(df: pd.DataFrame) -> None:
    print("\n--- ORTHOGONALITY CHECK (|r| < 0.30 required) ---")
    dq_col = "home_defense_quality_mu"
    if dq_col not in df.columns:
        print("  home_defense_quality_mu not found — skipping")
        return
    print(f"  Correlations between {dq_col} and existing signal mus:")
    for col in _EXISTING_MU_COLS:
        if col in df.columns:
            r = float(df[[dq_col, col]].dropna().corr().iloc[0, 1])
            status = "PASS" if abs(r) < 0.30 else "FAIL"
            print(f"    {dq_col} × {col:40s} r={r:+.3f}  [{status}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Story 27.4 ablation: defense_quality_v1 signals (Layer-3 NLL/Brier delta)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print data loading stats then exit before CV.",
    )
    parser.add_argument(
        "--seasons", type=int, nargs="+",
        help="Restrict to specific eval years (default: all available folds).",
    )
    args = parser.parse_args()

    print("=== STORY 27.4 — DEFENSE QUALITY ABLATION TEST ===\n")
    print("Loading outcomes from mart_game_results...")
    df_out = _load_outcomes()
    df_out["game_pk"] = df_out["game_pk"].astype(int)
    print(f"  {len(df_out):,} games, seasons {sorted(df_out['game_year'].unique())}")

    print("\nLoading existing sub-model signals from mart_sub_model_signals...")
    df_sig = _load_signals()
    df_sig["game_pk"] = df_sig["game_pk"].astype(int)
    print(f"  {len(df_sig):,} signal rows")

    print("\nLoading defense quality from mart_team_defense_quality_rolling...")
    dq_raw = _load_dq_mart()
    dq_raw["game_pk"] = dq_raw["game_pk"].astype(int)
    print(f"  {len(dq_raw):,} mart rows (both sides)")

    dq_wide = _pivot_dq(dq_raw)
    print(f"  {len(dq_wide):,} games after pivot to wide")
    for col in _DQ_COLS:
        n_pop = dq_wide[col].notna().sum() if col in dq_wide.columns else 0
        print(f"  {col}: {n_pop:,} / {len(dq_wide):,} non-null ({100*n_pop/max(len(dq_wide),1):.1f}%)")

    # Assemble merged dataset
    df = df_out.merge(df_sig, on="game_pk", how="left") \
               .merge(dq_wide, on="game_pk", how="left")
    df = df.sort_values("game_date").reset_index(drop=True)
    if args.seasons:
        df = df[df["game_year"].isin(args.seasons)].reset_index(drop=True)
    print(f"\n  Merged: {len(df):,} rows, seasons {sorted(df['game_year'].unique())}")

    # Report DQ coverage post-merge
    dq_coverage = df["home_defense_quality_mu"].notna().mean() * 100
    print(f"  defense_quality coverage: {dq_coverage:.1f}% of rows")

    # Orthogonality check
    _check_orthogonality(df)

    # Fill signal defaults (league-average neutral values)
    for col in _EXISTING_MU_COLS + _DQ_COLS:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)

    _NON_FEAT = (
        _NON_FEATURE_COLS
        | {"split", "game_type", "game_date", "home_win", "total_runs"}
        | set(_EXISTING_MU_COLS + _DQ_COLS)
    )

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    base_signal_cols  = [c for c in _EXISTING_MU_COLS if c in df.columns]
    extra_dq_cols     = [c for c in _DQ_COLS if c in df.columns]
    base_feature_cols = [c for c in numeric_cols if c not in _NON_FEAT] + base_signal_cols
    dq_feature_cols   = base_feature_cols + extra_dq_cols

    print(f"\n  Baseline feature cols:  {len(base_feature_cols)}")
    print(f"  With-DQ feature cols:   {len(dq_feature_cols)}")
    print(f"  DQ columns added:       {extra_dq_cols}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV. Data shape looks correct.")
        return

    # ---- TOTAL RUNS ablation ----
    print("\n--- TOTAL RUNS (NLL / MAE, Ridge α=1000) ---")
    df_tr = df.dropna(subset=["total_runs"]).reset_index(drop=True)

    print("  Baseline:")
    base_tr = _fold_cv_totals(df_tr, base_feature_cols, "baseline")
    for r in base_tr:
        print(f"    {r['eval_year']}: NLL={r['nll']:.4f}  MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    base_nll_mean = float(np.mean([r["nll"] for r in base_tr]))
    base_mae_mean = float(np.mean([r["mae"] for r in base_tr]))
    print(f"    Mean: NLL={base_nll_mean:.4f}  MAE={base_mae_mean:.4f}")

    print("  With defense_quality:")
    dq_tr = _fold_cv_totals(df_tr, dq_feature_cols, "with_dq")
    for r in dq_tr:
        print(f"    {r['eval_year']}: NLL={r['nll']:.4f}  MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    dq_nll_mean = float(np.mean([r["nll"] for r in dq_tr]))
    dq_mae_mean = float(np.mean([r["mae"] for r in dq_tr]))
    print(f"    Mean: NLL={dq_nll_mean:.4f}  MAE={dq_mae_mean:.4f}")

    nll_delta_tr = dq_nll_mean - base_nll_mean
    mae_delta_tr = dq_mae_mean - base_mae_mean
    n_improving_nll_tr = sum(
        1 for b, d in zip(base_tr, dq_tr) if d["nll"] < b["nll"]
    )
    print(f"\n  TOTAL RUNS DELTA: ΔNLL={nll_delta_tr:+.4f}  ΔMAE={mae_delta_tr:+.4f}")
    print(f"  NLL improvement in {n_improving_nll_tr}/{len(base_tr)} folds")

    # ---- HOME WIN ablation ----
    print("\n--- HOME WIN (log-loss / Brier, Logistic C=0.01) ---")
    df_hw = df.dropna(subset=["home_win"]).reset_index(drop=True)

    print("  Baseline:")
    base_hw = _fold_cv_h2h(df_hw, base_feature_cols, "baseline")
    for r in base_hw:
        print(f"    {r['eval_year']}: LogLoss={r['logloss']:.4f}  Brier={r['brier']:.4f}  n={r['n_eval']}")
    base_ll_mean = float(np.mean([r["logloss"] for r in base_hw]))
    base_br_mean = float(np.mean([r["brier"]   for r in base_hw]))
    print(f"    Mean: LogLoss={base_ll_mean:.4f}  Brier={base_br_mean:.4f}")

    print("  With defense_quality:")
    dq_hw = _fold_cv_h2h(df_hw, dq_feature_cols, "with_dq")
    for r in dq_hw:
        print(f"    {r['eval_year']}: LogLoss={r['logloss']:.4f}  Brier={r['brier']:.4f}  n={r['n_eval']}")
    dq_ll_mean = float(np.mean([r["logloss"] for r in dq_hw]))
    dq_br_mean = float(np.mean([r["brier"]   for r in dq_hw]))
    print(f"    Mean: LogLoss={dq_ll_mean:.4f}  Brier={dq_br_mean:.4f}")

    ll_delta_hw  = dq_ll_mean - base_ll_mean
    br_delta_hw  = dq_br_mean - base_br_mean
    n_improving_hw = sum(
        1 for b, d in zip(base_hw, dq_hw) if d["logloss"] < b["logloss"]
    )
    print(f"\n  HOME WIN DELTA: ΔLogLoss={ll_delta_hw:+.4f}  ΔBrier={br_delta_hw:+.4f}")
    print(f"  LogLoss improvement in {n_improving_hw}/{len(base_hw)} folds")

    # ---- Verdict ----
    print("\n" + "=" * 60)
    print("PROMOTE/DEFER VERDICT")
    print("=" * 60)
    promotes_totals = n_improving_nll_tr > len(base_tr) / 2 or nll_delta_tr < -0.001
    promotes_h2h    = n_improving_hw   > len(base_hw)  / 2 or ll_delta_hw  < -0.001
    verdict = "PROMOTE" if (promotes_totals or promotes_h2h) else "DEFER"
    print(f"  Total runs: {'IMPROVES' if promotes_totals else 'NO GAIN'} "
          f"(ΔNLL={nll_delta_tr:+.4f}, improving in {n_improving_nll_tr}/{len(base_tr)} folds)")
    print(f"  Home win:   {'IMPROVES' if promotes_h2h else 'NO GAIN'} "
          f"(ΔLogLoss={ll_delta_hw:+.4f}, improving in {n_improving_hw}/{len(base_hw)} folds)")
    print(f"\n  VERDICT: {verdict}")
    if verdict == "PROMOTE":
        print("  → defense_quality_v1 signal is promoted; wire into feature_pregame_sub_model_signals")
        print("    and regenerate both totals and H2H eval gates before Epic 27.3 / 28.x runs.")
    else:
        print("  → DEFER: defense_quality adds no measurable Layer-3 improvement at this stage.")
        print("    Re-eval trigger: when 2026 full season data is available (~Oct 2026) or when")
        print("    within-season OAA running totals become available (daily Savant team feed).")
    print("\n  Record this verdict in implementation_guide.md §Story 27.4 ACs.")


if __name__ == "__main__":
    main()
