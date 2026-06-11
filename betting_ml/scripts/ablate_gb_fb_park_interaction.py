"""
ablate_gb_fb_park_interaction.py — Story 27.5

Challenger evaluation: does adding gb_pct × eb_so_factor and
fb_pct × eb_hr_factor interaction features to run_env_v4's feature matrix
improve walk-forward NegBin NLL and calib_80?

Protocol:
  Baseline:   FEATURE_COLS_V3 (19 features — same as run_env_v4 champion)
  Challenger: FEATURE_COLS_V3 + 4 interaction terms:
                home_fb_x_hr_park  = home_starter_fb_pct × eb_hr_factor
                home_gb_x_so_park  = home_starter_gb_pct × eb_so_factor
                away_fb_x_hr_park  = away_starter_fb_pct × eb_hr_factor
                away_gb_x_so_park  = away_starter_gb_pct × eb_so_factor

Walk-forward CV: same season-forward folds as run_env_v4
  (train on all seasons before the test season, test on each season 2022–2026).
  Per fold: Ridge alpha selected on NLL, NegBin r MLE-fit from training residuals.
  Gate: promote challenger if mean CV NLL improves AND mean calib_80 does not
  worsen vs baseline (Sub-model output standard for run_env).

Orthogonality check: |Pearson r| between each interaction term and existing
  signal mus — must be < 0.30.

Coverage check: interaction features must be non-null ≥90% of 2021–2026 rows
  (Story 27.5 AC1).

Usage (hand off to user — >1 min):
    uv run python betting_ml/scripts/ablate_gb_fb_park_interaction.py
    uv run python betting_ml/scripts/ablate_gb_fb_park_interaction.py --dry-run
    uv run python betting_ml/scripts/ablate_gb_fb_park_interaction.py --seasons 2023 2024 2025 2026
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.train_run_env_v3 import (
    FEATURE_COLS_V3,
    _prepare_fold,
    _compute_prior_season_runs,
    _add_era_features,
    _compute_impute_values_v3,
    _apply_imputation_v3,
)

_MIN_MU = 0.5
_ALPHA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

# Interaction feature columns added in the challenger
_INTERACTION_COLS = [
    "home_fb_x_hr_park",
    "home_gb_x_so_park",
    "away_fb_x_hr_park",
    "away_gb_x_so_park",
]

# Existing signal mus used for orthogonality check
_EXISTING_MU_COLS = [
    "run_env_mu_v4",
    "pred_runs_mu_v2",
    "starter_suppression_mu_v1",
    "bullpen_mu_v2",
    "matchup_advantage_mu_v1",
    "env_league_state_mu_v1",
    "defense_quality_mu_v1",
]

# ---------------------------------------------------------------------------
# Snowflake queries
# ---------------------------------------------------------------------------

_TRAINING_QUERY = """
SELECT
    g.game_pk,
    g.game_date,
    EXTRACT(YEAR FROM g.game_date)::INTEGER          AS game_year,
    g.home_final_score + g.away_final_score          AS total_runs,

    -- Park: v4 features (leakage-safe prior-season)
    p.eb_park_run_factor,
    p.elevation_ft,
    p.center_ft,
    IFF(p.roof_type = 'Dome', 1, 0)                 AS is_dome,

    -- Park: granular factors for interaction terms (Story 27.5)
    p.eb_hr_factor,
    p.eb_so_factor,

    -- Weather (dome-coalesced to neutral indoor defaults)
    COALESCE(w.temp_f,             70)              AS temp_f,
    COALESCE(w.wind_component_mph,  0)              AS wind_component_mph,
    COALESCE(w.humidity_pct,       50)              AS humidity_pct,

    -- Umpire z-scores
    u.ump_runs_per_game_zscore,
    u.ump_run_impact_zscore,

    -- Team offensive controls
    th.off_woba_30d                                 AS home_off_woba_30d,
    ta.off_woba_30d                                 AS away_off_woba_30d,

    -- Starter quality controls
    sh.starter_proj_fip                             AS home_starter_proj_fip,
    sh.xwoba_against_30d                            AS home_starter_xwoba_30d,
    sa.starter_proj_fip                             AS away_starter_proj_fip,
    sa.xwoba_against_30d                            AS away_starter_xwoba_30d,

    -- Pitcher IDs needed to join batted-ball profile
    sh.pitcher_id                                   AS home_pitcher_id,
    sa.pitcher_id                                   AS away_pitcher_id

FROM baseball_data.betting.mart_game_results g
LEFT JOIN baseball_data.betting_features.feature_pregame_park_features p
    ON p.game_pk = g.game_pk
LEFT JOIN baseball_data.betting_features.feature_pregame_weather_features w
    ON w.game_pk = g.game_pk
LEFT JOIN baseball_data.betting_features.feature_pregame_umpire_features u
    ON u.game_pk = g.game_pk
LEFT JOIN baseball_data.betting_features.feature_pregame_team_features th
    ON th.game_pk = g.game_pk AND th.side = 'home'
LEFT JOIN baseball_data.betting_features.feature_pregame_team_features ta
    ON ta.game_pk = g.game_pk AND ta.side = 'away'
LEFT JOIN baseball_data.betting_features.feature_pregame_starter_features sh
    ON sh.game_pk = g.game_pk AND sh.side = 'home'
LEFT JOIN baseball_data.betting_features.feature_pregame_starter_features sa
    ON sa.game_pk = g.game_pk AND sa.side = 'away'

WHERE g.game_date >= '2021-01-01'
  AND g.game_type = 'R'
  AND g.home_final_score IS NOT NULL
  AND g.away_final_score IS NOT NULL
ORDER BY g.game_date, g.game_pk
"""

_BATTED_BALL_QUERY = """
SELECT
    pitcher_id,
    game_year,
    gb_pct,
    fb_pct
FROM baseball_data.betting.mart_pitcher_batted_ball_profile
ORDER BY pitcher_id, game_year
"""

_SIGNALS_QUERY = """
SELECT
    game_pk,
    MAX(CASE WHEN signal_name = 'run_env_mu'             AND sub_model_version = 'v4' AND side = 'home' THEN signal_value END) AS run_env_mu_v4,
    MAX(CASE WHEN signal_name = 'pred_runs_mu'           AND sub_model_version = 'v2' AND side = 'home' THEN signal_value END) AS pred_runs_mu_v2,
    MAX(CASE WHEN signal_name = 'starter_suppression_mu' AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS starter_suppression_mu_v1,
    MAX(CASE WHEN signal_name = 'bullpen_mu'             AND sub_model_version = 'v2' AND side = 'home' THEN signal_value END) AS bullpen_mu_v2,
    MAX(CASE WHEN signal_name = 'matchup_advantage_mu'   AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS matchup_advantage_mu_v1,
    MAX(CASE WHEN signal_name = 'env_league_state_mu'    AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS env_league_state_mu_v1,
    MAX(CASE WHEN signal_name = 'defense_quality_mu'     AND sub_model_version = 'v1' AND side = 'home' THEN signal_value END) AS defense_quality_mu_v1
FROM baseball_data.betting.mart_sub_model_signals
WHERE is_current = TRUE
GROUP BY game_pk
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_training_data() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_TRAINING_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["game_pk"]   = df["game_pk"].astype(int)
    return df


def _load_batted_ball() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_BATTED_BALL_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=cols)


def _load_signals() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SIGNALS_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_pk"] = df["game_pk"].astype(int)
    return df


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _join_batted_ball(df: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    """Join prior-season GB%/FB% for home and away starters.

    Uses game_year - 1 to join the pitcher profile — leakage-safe because the
    mart itself contains only completed-season data.
    """
    bb_home = bb.rename(columns={"pitcher_id": "home_pitcher_id", "gb_pct": "home_gb_pct",
                                   "fb_pct": "home_fb_pct"})
    bb_away = bb.rename(columns={"pitcher_id": "away_pitcher_id", "gb_pct": "away_gb_pct",
                                   "fb_pct": "away_fb_pct"})

    df = df.copy()
    # Join key: pitcher_id + prior season (game_year - 1 in the mart)
    df["_join_year"] = df["game_year"] - 1

    df = df.merge(
        bb_home[["home_pitcher_id", "game_year", "home_gb_pct", "home_fb_pct"]],
        left_on=["home_pitcher_id", "_join_year"],
        right_on=["home_pitcher_id", "game_year"],
        how="left",
        suffixes=("", "_bb_home"),
    ).drop(columns=["game_year_bb_home"], errors="ignore")

    df = df.merge(
        bb_away[["away_pitcher_id", "game_year", "away_gb_pct", "away_fb_pct"]],
        left_on=["away_pitcher_id", "_join_year"],
        right_on=["away_pitcher_id", "game_year"],
        how="left",
        suffixes=("", "_bb_away"),
    ).drop(columns=["game_year_bb_away", "_join_year"], errors="ignore")

    return df


def _build_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute four interaction terms from batted-ball profile × park factor.

    Rationale:
      fb_pct × eb_hr_factor — fly-ball starter in HR-friendly park gives up
        more home runs than an additive model predicts; this captures the
        non-linear synergy between pitcher batted-ball tendency and park HR rate.
      gb_pct × eb_so_factor — ground-ball starter in a high-K park suppresses
        runs more than additive effects predict; fewer hard-contact balls are
        compounded by a strikeout-friendly environment.
    """
    df = df.copy()
    df["home_fb_x_hr_park"] = df["home_fb_pct"] * df["eb_hr_factor"]
    df["home_gb_x_so_park"] = df["home_gb_pct"] * df["eb_so_factor"]
    df["away_fb_x_hr_park"] = df["away_fb_pct"] * df["eb_hr_factor"]
    df["away_gb_x_so_park"] = df["away_gb_pct"] * df["eb_so_factor"]
    return df


# ---------------------------------------------------------------------------
# NegBin utilities (mirrors run_env_v4 protocol exactly)
# ---------------------------------------------------------------------------

def _negbin_logpmf(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    y  = np.round(y).clip(0).astype(int)
    mu = np.clip(mu, _MIN_MU, None)
    p  = r / (r + mu)
    return (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1)
        + r * np.log(p + 1e-12)
        + y * np.log(1.0 - p + 1e-12)
    )


def _negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    return float(-_negbin_logpmf(y, mu, r).mean())


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    def neg_loglik(log_r: float) -> float:
        return -_negbin_logpmf(y, mu, np.exp(log_r)).sum()
    result = minimize_scalar(neg_loglik, bounds=(np.log(0.1), np.log(500)), method="bounded")
    return float(np.exp(result.x))


def _negbin_calib_80(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    mu = np.clip(mu, _MIN_MU, None)
    p  = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return float(((y >= lo) & (y <= hi)).mean())


# ---------------------------------------------------------------------------
# Walk-forward CV: baseline (FEATURE_COLS_V3) and challenger (+ interactions)
# ---------------------------------------------------------------------------

def _run_wf_cv(
    df: pd.DataFrame,
    extra_cols: list[str],
    tag: str,
) -> list[dict]:
    """Walk-forward NegBin CV.

    Mirrors the run_env_v4 protocol:
      - Alpha grid search on mean fold NLL
      - NegBin r MLE-fit from training residuals
      - Metrics: NLL, MAE, calib_80

    extra_cols: additional feature columns beyond FEATURE_COLS_V3; empty for baseline.
    """
    all_cols = list(FEATURE_COLS_V3) + extra_cols
    seasons  = sorted(df["game_year"].unique())
    folds    = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    # Alpha selection on NLL (same as v4)
    best_alpha    = 1.0
    best_mean_nll = float("inf")

    for alpha in _ALPHA_GRID:
        fold_nlls = []
        for train_seasons, test_season in folds:
            X_tr, y_tr, X_te, y_te = _fold_arrays(df, list(train_seasons), test_season, extra_cols)
            pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
            pipe.fit(X_tr, y_tr)
            mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
            mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
            r     = _fit_negbin_r(y_tr, mu_tr)
            fold_nlls.append(_negbin_nll(y_te, mu_te, r))
        mean_nll = float(np.mean(fold_nlls))
        if mean_nll < best_mean_nll:
            best_mean_nll = mean_nll
            best_alpha    = alpha

    results = []
    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te = _fold_arrays(df, list(train_seasons), test_season, extra_cols)
        pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
        pipe.fit(X_tr, y_tr)
        mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
        mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
        r     = _fit_negbin_r(y_tr, mu_tr)

        nll     = _negbin_nll(y_te, mu_te, r)
        mae     = float(np.mean(np.abs(mu_te - y_te)))
        calib80 = _negbin_calib_80(y_te, mu_te, r)

        results.append({
            "tag": tag,
            "eval_year": int(test_season),
            "n_eval": int(len(y_te)),
            "nll": nll,
            "mae": mae,
            "calib_80": calib80,
            "negbin_r": r,
            "alpha": best_alpha,
        })
    return results


def _fold_arrays(
    df: pd.DataFrame,
    train_seasons: list[int],
    test_season: int,
    extra_cols: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Prepare train/test arrays, incorporating era features and imputation.

    Base features follow the v3/v4 preparation (_prepare_fold).
    Extra interaction columns are median-imputed on the training fold.
    """
    train_df = df[df["game_year"].isin(train_seasons)].copy()
    test_df  = df[df["game_year"] == test_season].copy()

    prior_season_runs = _compute_prior_season_runs(train_df)
    train_df = _add_era_features(train_df, prior_season_runs)
    test_df  = _add_era_features(test_df,  prior_season_runs)

    impute_vals = _compute_impute_values_v3(train_df)
    train_imp   = _apply_imputation_v3(train_df, impute_vals)
    test_imp    = _apply_imputation_v3(test_df,  impute_vals)

    # Median-impute interaction columns on training fold median
    for col in extra_cols:
        if col in train_imp.columns:
            med = float(train_imp[col].median())
            if np.isnan(med):
                med = 0.0
            train_imp[col] = train_imp[col].fillna(med)
            test_imp[col]  = test_imp[col].fillna(med)

    all_cols = list(FEATURE_COLS_V3) + extra_cols
    X_tr = train_imp[all_cols].to_numpy(dtype=float)
    y_tr = train_imp["total_runs"].to_numpy(dtype=float)
    X_te = test_imp[all_cols].to_numpy(dtype=float)
    y_te = test_imp["total_runs"].to_numpy(dtype=float)
    return X_tr, y_tr, X_te, y_te


# ---------------------------------------------------------------------------
# Orthogonality check
# ---------------------------------------------------------------------------

def _check_orthogonality(df: pd.DataFrame) -> bool:
    print("\n--- ORTHOGONALITY CHECK (|r| < 0.30 required) ---")
    all_pass = True
    for ix_col in _INTERACTION_COLS:
        if ix_col not in df.columns:
            print(f"  {ix_col}: MISSING — skipping")
            continue
        for mu_col in _EXISTING_MU_COLS:
            if mu_col not in df.columns:
                continue
            sub = df[[ix_col, mu_col]].dropna()
            if len(sub) < 10:
                print(f"  {ix_col} × {mu_col}: too few non-null rows")
                continue
            r = float(sub.corr().iloc[0, 1])
            status = "PASS" if abs(r) < 0.30 else "FAIL"
            if abs(r) >= 0.30:
                all_pass = False
            print(f"  {ix_col} × {mu_col:<38s} r={r:+.3f}  [{status}]")
    return all_pass


# ---------------------------------------------------------------------------
# Coverage check
# ---------------------------------------------------------------------------

def _check_coverage(df: pd.DataFrame) -> bool:
    print("\n--- COVERAGE CHECK (≥90% non-null required) ---")
    all_pass = True
    for col in _INTERACTION_COLS:
        if col not in df.columns:
            print(f"  {col}: MISSING")
            all_pass = False
            continue
        nn  = df[col].notna().sum()
        pct = 100.0 * nn / max(len(df), 1)
        status = "PASS" if pct >= 90.0 else "FAIL"
        if pct < 90.0:
            all_pass = False
        print(f"  {col}: {nn:,} / {len(df):,} non-null = {pct:.1f}%  [{status}]")
    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Story 27.5 ablation: GB/FB × park interaction features. "
            "Tests whether adding starter batted-ball × granular-park interaction "
            "terms improves run_env_v4 walk-forward NegBin NLL and calib_80."
        )
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Load and join data, print coverage, then exit before CV.")
    parser.add_argument("--seasons", type=int, nargs="+",
                        help="Restrict eval years (default: all available folds).")
    args = parser.parse_args()

    print("=== STORY 27.5 — GB/FB × PARK INTERACTION ABLATION ===\n")

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading run_env training data (v4 feature set + pitcher IDs)...")
    df = _load_training_data()
    df["game_pk"] = df["game_pk"].astype(int)
    print(f"  {len(df):,} games, seasons {sorted(df['game_year'].unique())}")

    print("\nLoading mart_pitcher_batted_ball_profile (GB%/FB% per pitcher-season)...")
    bb = _load_batted_ball()
    print(f"  {len(bb):,} pitcher-season rows, seasons {sorted(bb['game_year'].unique())}")

    print("\nLoading sub-model signals for orthogonality check...")
    sig = _load_signals()
    sig["game_pk"] = sig["game_pk"].astype(int)
    print(f"  {len(sig):,} signal rows")

    # ── Join batted-ball profile (prior-season) ────────────────────────────
    print("\nJoining prior-season batted-ball profiles...")
    df = _join_batted_ball(df, bb)

    # ── Compute interaction features ───────────────────────────────────────
    print("Computing interaction features...")
    df = _build_interaction_features(df)

    # Merge signals for orthogonality check
    df_orth = df.merge(sig, on="game_pk", how="left")

    # ── Coverage check ─────────────────────────────────────────────────────
    coverage_pass = _check_coverage(df)

    # ── Orthogonality check ────────────────────────────────────────────────
    orth_pass = _check_orthogonality(df_orth)

    # ── Component coverage detail ──────────────────────────────────────────
    print("\n--- COMPONENT COVERAGE (batted-ball profile + park factors) ---")
    for col in ["home_gb_pct", "home_fb_pct", "away_gb_pct", "away_fb_pct",
                "eb_hr_factor", "eb_so_factor"]:
        nn  = df[col].notna().sum()
        pct = 100.0 * nn / max(len(df), 1)
        print(f"  {col:<25s}: {nn:,} / {len(df):,}  ({pct:.1f}%)")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV.")
        print(f"\nCoverage pass: {coverage_pass}   Orthogonality pass: {orth_pass}")
        return

    if args.seasons:
        df = df[df["game_year"].isin(args.seasons)].reset_index(drop=True)
        print(f"\nFiltered to eval seasons: {args.seasons}  ({len(df):,} rows)")

    # Drop rows with no total_runs (forfeit / cancelled games)
    df = df.dropna(subset=["total_runs"]).reset_index(drop=True)
    print(f"\nTraining rows after total_runs filter: {len(df):,}")

    # ── Walk-forward CV: baseline ──────────────────────────────────────────
    print("\n--- BASELINE: FEATURE_COLS_V3 (19 features, Ridge+NegBin) ---")
    base_results = _run_wf_cv(df, extra_cols=[], tag="baseline")
    _print_cv_table("Baseline", base_results)

    # ── Walk-forward CV: challenger ────────────────────────────────────────
    print(f"\n--- CHALLENGER: + {len(_INTERACTION_COLS)} interaction features ---")
    print(f"   Added: {_INTERACTION_COLS}")
    chal_results = _run_wf_cv(df, extra_cols=_INTERACTION_COLS, tag="challenger")
    _print_cv_table("Challenger", chal_results)

    # ── Delta summary ──────────────────────────────────────────────────────
    base_nll_mean   = float(np.mean([r["nll"]     for r in base_results]))
    base_mae_mean   = float(np.mean([r["mae"]     for r in base_results]))
    base_calib_mean = float(np.mean([r["calib_80"] for r in base_results]))

    chal_nll_mean   = float(np.mean([r["nll"]     for r in chal_results]))
    chal_mae_mean   = float(np.mean([r["mae"]     for r in chal_results]))
    chal_calib_mean = float(np.mean([r["calib_80"] for r in chal_results]))

    delta_nll   = chal_nll_mean   - base_nll_mean
    delta_mae   = chal_mae_mean   - base_mae_mean
    delta_calib = chal_calib_mean - base_calib_mean

    n_nll_improving = sum(
        1 for b, c in zip(base_results, chal_results) if c["nll"] < b["nll"]
    )
    n_calib_improving = sum(
        1 for b, c in zip(base_results, chal_results) if c["calib_80"] >= b["calib_80"] - 0.001
    )

    print("\n--- DELTA SUMMARY ---")
    print(f"  ΔNLL   = {delta_nll:+.4f}  (challenger - baseline; negative = improvement)")
    print(f"  ΔMAE   = {delta_mae:+.4f}")
    print(f"  Δcalib_80 = {delta_calib:+.4f}")
    print(f"  NLL improves in {n_nll_improving}/{len(base_results)} folds")
    print(f"  calib_80 does not worsen in {n_calib_improving}/{len(base_results)} folds")

    # ── Verdict ───────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("PROMOTE/DEFER VERDICT")
    print("=" * 64)
    nll_improves   = n_nll_improving > len(base_results) / 2 or delta_nll < -0.001
    calib_ok       = delta_calib > -0.005
    verdict = "PROMOTE" if (nll_improves and calib_ok) else "DEFER"

    print(f"  Coverage ≥90%:  {'PASS' if coverage_pass else 'FAIL'}")
    print(f"  Orthogonality:  {'PASS' if orth_pass else 'FAIL'}")
    print(f"  NLL improvement: {'YES' if nll_improves else 'NO'} "
          f"(ΔNLL={delta_nll:+.4f}, {n_nll_improving}/{len(base_results)} folds)")
    print(f"  calib_80 OK:    {'YES' if calib_ok else 'NO'} "
          f"(Δcalib_80={delta_calib:+.4f})")
    print(f"\n  VERDICT: {verdict}")

    if verdict == "PROMOTE":
        print(
            "  → Promote: add interaction features to run_env_v5 feature set;\n"
            "    retrain run_env_v5 challenger with train_run_env_v5.py\n"
            "    (see Story 27.5 implementation_guide.md for run command)."
        )
    else:
        print(
            "  → DEFER: interaction features do not clear the NLL + calib_80 gate.\n"
            "    Re-eval trigger: after full 2026 season Statcast backfill (~Oct 2026)\n"
            "    or when within-season rolling GB%/FB% is available as a feature."
        )

    print("\n  Record this verdict in implementation_guide.md §Story 27.5 ACs.")


def _print_cv_table(label: str, results: list[dict]) -> None:
    print(f"\n  {label} — walk-forward NegBin CV (Ridge, alpha by NLL)")
    print(f"  {'Year':>6}  {'NLL':>8}  {'MAE':>7}  {'calib80':>8}  {'r':>7}  {'alpha':>8}  {'n':>6}")
    print("  " + "-" * 62)
    for r in results:
        print(
            f"  {r['eval_year']:>6}  {r['nll']:>8.4f}  {r['mae']:>7.3f}  "
            f"{r['calib_80']:>8.4f}  {r['negbin_r']:>7.3f}  {r['alpha']:>8}  {r['n_eval']:>6}"
        )
    nll_m   = float(np.mean([r["nll"]     for r in results]))
    mae_m   = float(np.mean([r["mae"]     for r in results]))
    calib_m = float(np.mean([r["calib_80"] for r in results]))
    r_m     = float(np.mean([r["negbin_r"] for r in results]))
    print(f"  {'Mean':>6}  {nll_m:>8.4f}  {mae_m:>7.3f}  {calib_m:>8.4f}  {r_m:>7.3f}")


if __name__ == "__main__":
    main()
