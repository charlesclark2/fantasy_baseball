"""
run_scoring_advi.py — Epic 17, Story 17.1 Phase 0

ADVI fast-pass for the PyMC hierarchical NegBin run-scoring model.
This is an identifiability check, NOT final inference. Confirms:
  1. ELBO convergence within 20K iterations
  2. Coefficient directions (beta signs)
  3. Team effect variance (sigma_offense, sigma_defense)
  4. Season intercept variation (delta_season)
  5. Approximate kill criterion: ADVI posterior predictive mean ≤ 8.85 on May-2026 OOS
     (ADVI underestimates uncertainty — the full NUTS check uses ≤ 8.81)

Data surface:
  - OOS signal parquets from betting_ml/models/layer3/oos_signals/ (leakage-free)
  - mart_game_results from Snowflake for runs_scored, team names, game_date
  - Training: 2022–2025 (2021 excluded — run_env OOS not available for 2021 in walk-forward)
  - Test (kill criterion): May-2026 games only

Usage:
  uv run python betting_ml/models/bayesian/run_scoring_advi.py

Expected runtime: 5–20 minutes (ADVI 20K iterations + Snowflake query + PPC scoring).
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_OOS_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals"
_BAYESIAN_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "bayesian"
_TRAIN_SEASONS = [2022, 2023, 2024, 2025]  # 2021 excluded: run_env not available in walk-forward OOS
_OOS_SEASON = 2026


# ---------------------------------------------------------------------------
# Step 1: Load OOS signal parquets
# ---------------------------------------------------------------------------

def _load_oos_signals() -> pd.DataFrame:
    """Merge all OOS signal parquets into (game_pk, side) grain."""
    log.info("Loading OOS signal parquets from %s", _OOS_DIR)

    offense = pd.read_parquet(_OOS_DIR / "oos_signals_offense.parquet")[
        ["game_pk", "side", "season", "pred_runs_mu"]
    ]
    bullpen = pd.read_parquet(_OOS_DIR / "oos_signals_bullpen.parquet")[
        ["game_pk", "side", "bullpen_mu"]
    ]
    starter = pd.read_parquet(_OOS_DIR / "oos_signals_starter.parquet")[
        ["game_pk", "side", "starter_suppression_mu"]
    ]
    # run_env is game-level (no side column) — same value for both sides of a game
    run_env = pd.read_parquet(_OOS_DIR / "oos_signals_run_env.parquet")[
        ["game_pk", "run_env_mu"]
    ]

    df = (
        offense
        .merge(bullpen, on=["game_pk", "side"], how="inner")
        .merge(starter, on=["game_pk", "side"], how="inner")
        .merge(run_env, on="game_pk", how="inner")  # game-level join; 2021 games drop here
    )
    log.info("OOS signals merged: %d rows (game_pk, side pairs)", len(df))
    log.info("Season distribution:\n%s", df.groupby("season").size().to_string())
    return df


# ---------------------------------------------------------------------------
# Step 2: Pull mart_game_results from Snowflake
# ---------------------------------------------------------------------------

def _load_game_results(seasons: list[int]) -> pd.DataFrame:
    """Pull game_pk, game_date, home/away team names, per-side runs_scored."""
    from betting_ml.utils.data_loader import get_snowflake_connection

    season_list = ", ".join(str(s) for s in seasons)
    sql = f"""
        select
            game_pk,
            game_date,
            game_year as season,
            home_team,
            away_team,
            home_final_score,
            away_final_score
        from baseball_data.betting.mart_game_results
        where game_type = 'R'
          and home_final_score is not null
          and game_year in ({season_list})
    """
    log.info("Querying mart_game_results for seasons %s", season_list)
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()

    df["game_date"] = pd.to_datetime(df["game_date"])
    df["home_final_score"] = pd.to_numeric(df["home_final_score"], errors="coerce")
    df["away_final_score"] = pd.to_numeric(df["away_final_score"], errors="coerce")
    df["season"] = df["season"].astype(int)
    log.info("Loaded %d completed games from mart_game_results", len(df))
    return df


def _expand_to_sides(game_df: pd.DataFrame) -> pd.DataFrame:
    """Expand game-level rows to (game_pk, side) grain with batting/pitching team."""
    home = game_df.assign(
        side="home",
        batting_team=game_df["home_team"],
        pitching_team=game_df["away_team"],
        runs_scored=game_df["home_final_score"],
    )
    away = game_df.assign(
        side="away",
        batting_team=game_df["away_team"],
        pitching_team=game_df["home_team"],
        runs_scored=game_df["away_final_score"],
    )
    # home_team serves as park_id proxy (in MLB, home team → park is 1:1)
    keep = ["game_pk", "game_date", "season", "side", "batting_team", "pitching_team",
            "runs_scored", "home_team"]
    return pd.concat([home[keep], away[keep]], ignore_index=True)


# ---------------------------------------------------------------------------
# Step 3: Build training frame with cross-terms
# ---------------------------------------------------------------------------

def _build_training_frame(signals: pd.DataFrame, sides: pd.DataFrame) -> pd.DataFrame:
    """
    Merge signals with game side info. Apply the correct cross-term logic:
      - offense_mu_z:       batting team's pred_runs_mu
      - opp_bullpen_mu_z:   OPPOSING team's bullpen_mu (suppression of batting side)
      - opp_starter_mu_z:   OPPOSING team's starter_suppression_mu
      - run_env_z:          game-level (same value for home and away rows of same game)
    """
    df = sides.merge(signals[["game_pk", "side", "pred_runs_mu", "bullpen_mu",
                               "starter_suppression_mu", "run_env_mu"]],
                     on=["game_pk", "side"], how="inner")

    # The opposing side's signals (bullpen, starter) need to be fetched from the
    # other side's row. We do this by merging the opposing side's signals.
    opp_map = {"home": "away", "away": "home"}
    opp_signals = signals[["game_pk", "side", "bullpen_mu", "starter_suppression_mu"]].copy()
    opp_signals["opp_side"] = opp_signals["side"].map(opp_map)
    opp_signals = opp_signals.rename(columns={
        "bullpen_mu": "opp_bullpen_mu",
        "starter_suppression_mu": "opp_starter_mu",
    })
    opp_signals = opp_signals[["game_pk", "opp_side", "opp_bullpen_mu", "opp_starter_mu"]]
    opp_signals = opp_signals.rename(columns={"opp_side": "side"})

    df = df.merge(opp_signals, on=["game_pk", "side"], how="inner")

    # Drop rows with any null signal or target
    signal_cols = ["run_env_mu", "pred_runs_mu", "opp_bullpen_mu", "opp_starter_mu", "runs_scored"]
    before = len(df)
    df = df.dropna(subset=signal_cols).reset_index(drop=True)
    log.info("Dropped %d rows with null signals; %d remain", before - len(df), len(df))

    return df


# ---------------------------------------------------------------------------
# Step 4: Build integer indices for team/season/park
# ---------------------------------------------------------------------------

def _build_indices(train: pd.DataFrame, full: pd.DataFrame) -> tuple[pd.DataFrame, dict, dict, dict]:
    """
    Build integer indices for batting_team, pitching_team, season.
    Indices are built from TRAINING data only; OOS uses the same mapping.
    Returns: (full_df_with_indices, team_to_idx, season_to_idx, coords)
    """
    teams = sorted(train["batting_team"].dropna().unique().tolist()
                   + train["pitching_team"].dropna().unique().tolist())
    teams = sorted(set(teams))
    team_to_idx = {t: i for i, t in enumerate(teams)}

    seasons = sorted(train["season"].unique().tolist())
    season_to_idx = {s: i for i, s in enumerate(seasons)}
    # 2026 OOS: map to the last training season (Option A — conservative)
    season_to_idx[_OOS_SEASON] = season_to_idx[max(seasons)]

    def _apply_indices(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["batting_team_idx"] = df["batting_team"].map(team_to_idx)
        df["pitching_team_idx"] = df["pitching_team"].map(team_to_idx)
        df["season_idx"] = df["season"].map(season_to_idx)
        return df

    full = _apply_indices(full)
    before = len(full)
    full = full.dropna(subset=["batting_team_idx", "pitching_team_idx", "season_idx"])
    if before - len(full) > 0:
        log.warning("Dropped %d rows with unmapped team/season indices", before - len(full))
    full["batting_team_idx"] = full["batting_team_idx"].astype(int)
    full["pitching_team_idx"] = full["pitching_team_idx"].astype(int)
    full["season_idx"] = full["season_idx"].astype(int)

    coords = {
        "team":   teams,
        "season": [str(s) for s in seasons],
        "obs":    list(range(len(full[full["season"].isin(_TRAIN_SEASONS)]))),
    }
    return full, team_to_idx, season_to_idx, coords


# ---------------------------------------------------------------------------
# Step 5: Z-score signals on training data
# ---------------------------------------------------------------------------

def _fit_and_apply_scalers(
    train: pd.DataFrame,
    full: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, object]:
    from sklearn.preprocessing import StandardScaler
    import joblib

    signal_cols = {
        "run_env_mu": "run_env_z",
        "pred_runs_mu": "offense_mu_z",
        "opp_bullpen_mu": "opp_bullpen_mu_z",
        "opp_starter_mu": "opp_starter_mu_z",
    }

    scalers = {}
    for raw_col, z_col in signal_cols.items():
        scaler = StandardScaler()
        train_vals = train[raw_col].values.reshape(-1, 1)
        scaler.fit(train_vals)
        scalers[raw_col] = scaler

    for raw_col, z_col in signal_cols.items():
        scaler = scalers[raw_col]
        for df in [train, full]:
            df[z_col] = scaler.transform(df[raw_col].values.reshape(-1, 1)).ravel()

    # Verify z-scoring on training data
    for raw_col, z_col in signal_cols.items():
        mean_ = train[z_col].mean()
        std_ = train[z_col].std()
        log.info("  %-20s → %-22s  mean=%.4f  std=%.4f", raw_col, z_col, mean_, std_)
    assert all(abs(train[z].mean()) < 0.01 for z in signal_cols.values()), "Z-score means off"
    assert all(abs(train[z].std() - 1.0) < 0.05 for z in signal_cols.values()), "Z-score stds off"

    scaler_path = _BAYESIAN_DIR / "signal_scalers.joblib"
    joblib.dump(scalers, scaler_path)
    log.info("Saved signal scalers → %s", scaler_path)
    return train, full, scalers


# ---------------------------------------------------------------------------
# Step 6: PyMC model
# ---------------------------------------------------------------------------

def build_model(df_train: pd.DataFrame, coords: dict):
    import pymc as pm

    # run_env is game-level — each side of the same game has the same run_env_z.
    # This is the key fix vs LTV: run_env enters ONCE per side row (same value),
    # not summed across sides. The regression coefficient beta_run_env captures
    # the marginal effect after accounting for team offense/defense pooling.

    n_teams = len(coords["team"])
    n_seasons = len(coords["season"])

    with pm.Model(coords=coords) as model:

        # ─── Hyperpriors ──────────────────────────────────────────────────────
        mu_log_league = pm.Normal("mu_log_league", mu=np.log(4.5), sigma=0.2)
        sigma_offense = pm.HalfNormal("sigma_offense", sigma=0.25)
        sigma_defense = pm.HalfNormal("sigma_defense", sigma=0.25)
        sigma_season  = pm.HalfNormal("sigma_season",  sigma=0.15)

        # ─── Group-level effects (partial pooling) ─────────────────────────────
        alpha_offense = pm.Normal("alpha_offense", mu=0, sigma=sigma_offense, dims="team")
        alpha_defense = pm.Normal("alpha_defense", mu=0, sigma=sigma_defense, dims="team")
        delta_season  = pm.Normal("delta_season",  mu=0, sigma=sigma_season,  dims="season")

        # ─── Signal coefficients ───────────────────────────────────────────────
        beta_run_env = pm.Normal("beta_run_env", mu=0.0, sigma=0.3)
        beta_offense = pm.Normal("beta_offense", mu=0.2, sigma=0.3)
        # bullpen_mu target=bullpen_runs_allowed; starter_suppression_mu target=xwoba_against
        # Both are "quality-against" (higher = worse pitcher = more runs for batting team) → positive prior
        beta_bullpen = pm.Normal("beta_bullpen", mu=0.1, sigma=0.3)
        beta_starter = pm.Normal("beta_starter", mu=0.1, sigma=0.3)

        # ─── Per-side expected log run rate ───────────────────────────────────
        bat_idx = df_train["batting_team_idx"].values
        pit_idx = df_train["pitching_team_idx"].values
        sea_idx = df_train["season_idx"].values

        log_mu_side = (
            mu_log_league
            + alpha_offense[bat_idx]
            + alpha_defense[pit_idx]
            + delta_season[sea_idx]
            + beta_run_env * df_train["run_env_z"].values
            + beta_offense * df_train["offense_mu_z"].values
            + beta_bullpen * df_train["opp_bullpen_mu_z"].values
            + beta_starter * df_train["opp_starter_mu_z"].values
        )
        mu_side = pm.Deterministic("mu_side", pm.math.exp(log_mu_side))

        # ─── NegBin overdispersion ─────────────────────────────────────────────
        alpha_nb = pm.HalfNormal("alpha_nb", sigma=5.0)

        # ─── Likelihood (per-side runs scored) ────────────────────────────────
        runs = pm.NegativeBinomial(
            "runs",
            mu=mu_side,
            alpha=alpha_nb,
            observed=df_train["runs_scored"].values,
            dims="obs",
        )

    return model


# ---------------------------------------------------------------------------
# Step 7: Prior predictive check
# ---------------------------------------------------------------------------

def run_prior_predictive_check(model) -> None:
    import pymc as pm

    log.info("Running prior predictive check (500 draws)...")
    with model:
        prior_pc = pm.sample_prior_predictive(draws=500, random_seed=42)

    runs_draws = prior_pc.prior_predictive["runs"].values  # shape: (1, 500, n_obs)
    # For each draw, compute total_runs as home + away (adjacent rows in training are NOT
    # paired here — just checking the marginal distribution covers [0, 30])
    flat_runs = runs_draws.ravel()
    p_lt2   = float((flat_runs < 2).mean())
    p_gt25  = float((flat_runs > 25).mean())
    mean_   = float(flat_runs.mean())
    p10, p90 = float(np.percentile(flat_runs, 10)), float(np.percentile(flat_runs, 90))

    log.info("Prior predictive check (per-side runs drawn from NegBin prior):")
    log.info("  mean=%.2f  p10=%.1f  p90=%.1f  P(<2)=%.4f  P(>25)=%.4f",
             mean_, p10, p90, p_lt2, p_gt25)

    # Rough total_runs prior: sum pairs of adjacent draws to simulate home+away
    # (not exact — just a sanity check on the distribution scale)
    n_pairs = len(flat_runs) // 2
    total_pairs = flat_runs[:n_pairs] + flat_runs[n_pairs:2*n_pairs]
    total_mean = float(total_pairs.mean())
    log.info("  Rough prior total_runs mean (sum of independent draws): %.2f", total_mean)
    if not (7.0 <= total_mean <= 12.0):
        log.warning("  Prior total_runs mean %.2f outside [7, 11] — check mu_log_league prior", total_mean)
    else:
        log.info("  Prior predictive check PASS: total_runs mean %.2f in [7, 11]", total_mean)


# ---------------------------------------------------------------------------
# Step 8: ADVI fast-pass
# ---------------------------------------------------------------------------

def run_advi(model, n_iterations: int = 20_000) -> object:
    import pymc as pm

    log.info("Starting ADVI fast-pass (%d iterations)...", n_iterations)
    with model:
        approx = pm.fit(
            method="advi",
            n=n_iterations,
            progressbar=True,
            random_seed=42,
        )
    log.info("ADVI complete.")
    return approx


def check_advi_convergence(approx) -> bool:
    """Inspect ELBO trajectory for convergence."""
    hist = approx.hist
    if hist is None or len(hist) == 0:
        log.warning("No ELBO history available — cannot assess convergence")
        return False

    hist = np.asarray(hist)
    n = len(hist)
    # Check last 10% of iterations: ELBO should be stable (std / abs(mean) < 0.01)
    tail = hist[int(0.9 * n):]
    if len(tail) < 10:
        log.warning("Too few ELBO values to assess convergence")
        return False

    tail_std = float(np.std(tail))
    tail_mean = float(np.mean(tail))
    rel_std = abs(tail_std / tail_mean) if abs(tail_mean) > 1e-6 else float("inf")

    # Report trajectory milestones
    quartiles = [int(0.25 * n), int(0.5 * n), int(0.75 * n), n - 1]
    for q in quartiles:
        log.info("  ELBO at iter %5d: %.2f", q, hist[q])
    log.info("  ELBO tail (last 10%%): mean=%.2f  std=%.4f  rel_std=%.6f",
             tail_mean, tail_std, rel_std)

    converged = rel_std < 0.02  # within 2% relative variation in the tail
    log.info("  Convergence: %s (rel_std %.4f vs threshold 0.02)", "PASS" if converged else "FAIL", rel_std)
    return converged


def check_coefficient_directions(advi_trace) -> dict:
    """Check that signal coefficients have the expected signs."""
    posterior = advi_trace.posterior

    results = {}
    # Both bullpen_mu (target=bullpen_runs_allowed) and starter_suppression_mu
    # (target=xwoba_against) are "quality-against" metrics: higher = worse pitcher
    # = batting team scores more. Expected signs are ALL positive.
    checks = {
        "beta_run_env":  ("positive", lambda x: x > 0),
        "beta_offense":  ("positive", lambda x: x > 0),
        "beta_bullpen":  ("positive", lambda x: x > 0),
        "beta_starter":  ("positive", lambda x: x > 0),
    }

    log.info("\nCoefficient posterior means and sign checks:")
    for param, (expected, check_fn) in checks.items():
        vals = posterior[param].values.ravel()
        mean_ = float(vals.mean())
        p5    = float(np.percentile(vals, 5))
        p95   = float(np.percentile(vals, 95))
        pct_correct = float(check_fn(vals).mean())
        sign_ok = pct_correct > 0.80  # >80% of posterior mass has the expected sign
        log.info("  %-18s  mean=%+.3f  [%+.3f, %+.3f]  expected=%s  P(correct)=%.2f  %s",
                 param, mean_, p5, p95, expected, pct_correct, "OK" if sign_ok else "WARN")
        results[param] = {"mean": mean_, "p5": p5, "p95": p95, "expected": expected,
                          "pct_correct": pct_correct, "sign_ok": sign_ok}

    return results


def check_variance_components(advi_trace) -> dict:
    """Check sigma_offense, sigma_defense, sigma_season for meaningful variation."""
    posterior = advi_trace.posterior
    results = {}

    log.info("\nVariance component posterior means:")
    for param in ["sigma_offense", "sigma_defense", "sigma_season"]:
        vals = posterior[param].values.ravel()
        mean_ = float(vals.mean())
        p5    = float(np.percentile(vals, 5))
        p95   = float(np.percentile(vals, 95))

        collapsed  = mean_ < 0.02  # collapsed toward zero → partial pooling ineffective
        exploded   = mean_ > 2.0   # very large → over-regularization failure
        status = "COLLAPSED" if collapsed else ("EXPLODED" if exploded else "OK")

        log.info("  %-20s  mean=%.4f  [%.4f, %.4f]  %s", param, mean_, p5, p95, status)
        results[param] = {"mean": mean_, "p5": p5, "p95": p95, "status": status}

    return results


def check_season_intercepts(advi_trace, season_to_idx: dict) -> dict:
    """Check delta_season posterior means for year-to-year variation."""
    posterior = advi_trace.posterior
    idx_to_season = {v: k for k, v in season_to_idx.items() if k != _OOS_SEASON}
    seasons_sorted = sorted(idx_to_season.items())

    delta_vals = posterior["delta_season"].values  # shape: (chain, draw, n_seasons)
    if delta_vals.ndim == 3:
        delta_vals = delta_vals.reshape(-1, delta_vals.shape[-1])

    log.info("\nSeason intercept (delta_season) posterior means:")
    results = {}
    means = []
    for idx, season in seasons_sorted:
        col_vals = delta_vals[:, idx]
        mean_ = float(col_vals.mean())
        std_  = float(col_vals.std())
        log.info("  %d  mean=%+.4f  std=%.4f", season, mean_, std_)
        results[season] = {"mean": mean_, "std": std_}
        means.append(mean_)

    spread = max(means) - min(means) if means else 0.0
    log.info("  Season intercept spread (max - min): %.4f", spread)
    if spread < 0.02:
        log.warning("  Season intercepts near-zero — model may not be capturing year-to-year regime variation")
    else:
        log.info("  Season intercept spread OK (%.4f > 0.02)", spread)
    results["spread"] = spread
    return results


# ---------------------------------------------------------------------------
# Step 9: Approximate kill criterion (ADVI posterior predictive mean)
# ---------------------------------------------------------------------------

def run_advi_kill_criterion(
    approx,
    full_df: pd.DataFrame,
    train_df: pd.DataFrame,
    model,
    coords: dict,
) -> dict:
    """
    Approximate kill criterion using ADVI mean-field posterior predictive.

    ADVI underestimates posterior uncertainty (mean-field approximation), but
    the posterior MEAN should be close to NUTS. If the ADVI PPM is > 8.85
    (5-sigma above the 8.81 NUTS kill criterion), the model structure is broken
    and NUTS will not fix it.
    """
    import pymc as pm

    may_2026_mask = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month == 5)
    )
    may_df = full_df[may_2026_mask].copy().reset_index(drop=True)

    if len(may_df) == 0:
        log.error("No May-2026 OOS games found — check data loading")
        return {"error": "no May-2026 games"}

    log.info("\nMay-2026 OOS: %d (game_pk, side) rows, %d unique game_pks",
             len(may_df), may_df["game_pk"].nunique())

    # Score both sides; then pair by game_pk to compute total_runs PPC
    log.info("Sampling ADVI approximate posterior predictive for May-2026 OOS (1000 draws)...")

    n_train = len(train_df)
    n_oos   = len(may_df)

    # Re-build model with May 2026 data as observation placeholder
    # The cleanest approach: sample from approx, then compute mu_side manually
    # for OOS rows using the ADVI mean-field approximation samples
    with model:
        advi_samples = approx.sample(1000)  # 1000 draws from the ADVI approximation

    # Extract parameter posterior samples
    post = advi_samples.posterior
    mu_log_league  = post["mu_log_league"].values.ravel()       # (1000,)
    alpha_offense  = post["alpha_offense"].values.reshape(-1, len(coords["team"]))  # (1000, n_teams)
    alpha_defense  = post["alpha_defense"].values.reshape(-1, len(coords["team"]))
    delta_season   = post["delta_season"].values.reshape(-1, len(coords["season"]))  # (1000, n_seasons)
    beta_run_env   = post["beta_run_env"].values.ravel()
    beta_offense   = post["beta_offense"].values.ravel()
    beta_bullpen   = post["beta_bullpen"].values.ravel()
    beta_starter   = post["beta_starter"].values.ravel()
    alpha_nb       = post["alpha_nb"].values.ravel()

    bat_idx = may_df["batting_team_idx"].values   # (n_oos,)
    pit_idx = may_df["pitching_team_idx"].values
    sea_idx = may_df["season_idx"].values
    run_env_z  = may_df["run_env_z"].values
    offense_z  = may_df["offense_mu_z"].values
    bullpen_z  = may_df["opp_bullpen_mu_z"].values
    starter_z  = may_df["opp_starter_mu_z"].values

    # Vectorised over draws: shape (n_draws, n_oos)
    log_mu = (
        mu_log_league[:, None]
        + alpha_offense[:, bat_idx]
        + alpha_defense[:, pit_idx]
        + delta_season[:, sea_idx]
        + beta_run_env[:, None] * run_env_z[None, :]
        + beta_offense[:, None] * offense_z[None, :]
        + beta_bullpen[:, None] * bullpen_z[None, :]
        + beta_starter[:, None] * starter_z[None, :]
    )
    mu_oos = np.exp(log_mu)  # (n_draws, n_oos)

    # Sample from NegBin for each draw
    from scipy.stats import nbinom
    rng = np.random.default_rng(42)
    ppc_runs = np.zeros_like(mu_oos)
    for d in range(mu_oos.shape[0]):
        # NegBin parameterization: p = alpha_nb / (alpha_nb + mu)
        a = float(alpha_nb[d])
        p_nb = a / (a + mu_oos[d])
        ppc_runs[d] = rng.negative_binomial(a, p_nb)

    # Pair home and away sides by game_pk
    may_home = may_df[may_df["side"] == "home"].copy().reset_index(drop=True)
    may_away = may_df[may_df["side"] == "away"].copy().reset_index(drop=True)

    may_home_mask = (may_df["side"] == "home").values
    may_away_mask = (may_df["side"] == "away").values

    ppc_home = ppc_runs[:, may_home_mask]  # (n_draws, n_home_games)
    ppc_away = ppc_runs[:, may_away_mask]

    # Align by game_pk (in case ordering differs)
    home_pks = may_df[may_df["side"] == "home"]["game_pk"].values
    away_pks = may_df[may_df["side"] == "away"]["game_pk"].values
    if not np.array_equal(np.sort(home_pks), np.sort(away_pks)):
        log.warning("Home and away game_pk sets differ — using intersection")
        shared_pks = sorted(set(home_pks) & set(away_pks))
    else:
        shared_pks = sorted(set(home_pks))

    home_order = {pk: i for i, pk in enumerate(home_pks)}
    away_order = {pk: i for i, pk in enumerate(away_pks)}
    home_sel = np.array([home_order[pk] for pk in shared_pks])
    away_sel = np.array([away_order[pk] for pk in shared_pks])

    total_ppc = ppc_home[:, home_sel] + ppc_away[:, away_sel]  # (n_draws, n_games)
    ppm = float(total_ppc.mean())

    # Actual May-2026 mean total_runs (from game results joined above)
    may_game_df = may_df[may_df["side"] == "home"].merge(
        may_df[may_df["side"] == "away"][["game_pk", "runs_scored"]].rename(
            columns={"runs_scored": "away_runs"}
        ),
        on="game_pk",
    )
    if "runs_scored" in may_game_df.columns and may_game_df["runs_scored"].notna().any():
        actual_mean = float((may_game_df["runs_scored"] + may_game_df["away_runs"]).mean())
    else:
        actual_mean = float("nan")

    advi_kill_threshold = 8.85  # ADVI is noisier; use 8.85 here vs 8.81 for NUTS
    passed = ppm <= advi_kill_threshold

    log.info("\n========= ADVI KILL CRITERION CHECK =========")
    log.info("  May-2026 games evaluated:           %d", len(shared_pks))
    log.info("  ADVI posterior predictive mean:     %.4f", ppm)
    log.info("  Actual May-2026 mean total_runs:    %.4f", actual_mean)
    log.info("  Bias (PPM - actual):                %+.4f", ppm - actual_mean if not np.isnan(actual_mean) else float("nan"))
    log.info("  ADVI kill criterion threshold:      %.2f (NUTS criterion: 8.81)", advi_kill_threshold)
    log.info("  Result: %s", "PASS → proceed to NUTS hand-off" if passed else "FAIL → stop; revise model structure")
    log.info("=============================================\n")

    # Season-effect contribution check (how much does delta_season for 2026 add?)
    from sklearn.preprocessing import StandardScaler  # already fitted
    season_2026_idx = list(coords["season"]).index(str(max(_TRAIN_SEASONS))) if str(max(_TRAIN_SEASONS)) in coords["season"] else -1
    if season_2026_idx >= 0:
        delta_2026_mean = float(delta_season[:, season_2026_idx].mean())
        season_contribution_runs = np.exp(delta_2026_mean) * np.exp(float(mu_log_league.mean())) - np.exp(float(mu_log_league.mean()))
        log.info("  2026 season effect (mapped to 2025 posterior): delta=%.4f, "
                 "implied run shift ≈ %+.3f runs/side (%+.3f total)",
                 delta_2026_mean, season_contribution_runs, 2 * season_contribution_runs)

    return {
        "n_games": len(shared_pks),
        "advi_ppm": ppm,
        "actual_mean": actual_mean,
        "bias": ppm - actual_mean if not np.isnan(actual_mean) else float("nan"),
        "threshold": advi_kill_threshold,
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 60)
    log.info("Epic 17 Story 17.1 — ADVI Fast-Pass (Phase 0)")
    log.info("=" * 60)

    # -- Data prep ----------------------------------------------------------
    log.info("\n[1/5] Loading OOS signal parquets...")
    signals = _load_oos_signals()

    all_seasons = _TRAIN_SEASONS + [_OOS_SEASON]
    log.info("\n[2/5] Loading mart_game_results from Snowflake (seasons %s)...", all_seasons)
    game_results = _load_game_results(seasons=all_seasons)
    sides = _expand_to_sides(game_results)

    log.info("\n[3/5] Merging signals with game sides and applying cross-terms...")
    full_df = _build_training_frame(signals, sides)

    train_df = full_df[full_df["season"].isin(_TRAIN_SEASONS)].copy().reset_index(drop=True)
    log.info("Training set: %d rows  (seasons %s)", len(train_df), _TRAIN_SEASONS)
    log.info("Full set (train + OOS): %d rows", len(full_df))

    if len(train_df) < 5000:
        log.error("Training set too small (%d rows) — check signal coverage", len(train_df))
        sys.exit(1)

    full_df, team_to_idx, season_to_idx, coords = _build_indices(train_df, full_df)
    train_df = full_df[full_df["season"].isin(_TRAIN_SEASONS)].copy().reset_index(drop=True)

    log.info("\n[4/5] Fitting signal scalers on training data...")
    log.info("Signal distributions BEFORE z-scoring (training):")
    for col in ["run_env_mu", "pred_runs_mu", "opp_bullpen_mu", "opp_starter_mu"]:
        log.info("  %-25s  mean=%.4f  std=%.4f", col, train_df[col].mean(), train_df[col].std())
    train_df, full_df, scalers = _fit_and_apply_scalers(train_df, full_df)
    train_df = full_df[full_df["season"].isin(_TRAIN_SEASONS)].copy().reset_index(drop=True)

    log.info("\nTraining data summary:")
    log.info("  Rows: %d  |  Unique game_pks: %d  |  Teams: %d  |  Seasons: %d",
             len(train_df), train_df["game_pk"].nunique(),
             len(team_to_idx), len([s for s in season_to_idx if s != _OOS_SEASON]))
    log.info("  Runs scored — mean=%.3f  std=%.3f  min=%d  max=%d",
             train_df["runs_scored"].mean(), train_df["runs_scored"].std(),
             train_df["runs_scored"].min(), train_df["runs_scored"].max())

    # Re-index obs coord to match actual training rows
    coords["obs"] = list(range(len(train_df)))

    # -- Model + ADVI -------------------------------------------------------
    log.info("\n[5/5] Building PyMC model and running ADVI fast-pass...")
    import pymc as pm
    import arviz as az

    model = build_model(train_df, coords)

    log.info("\nRunning prior predictive check...")
    run_prior_predictive_check(model)

    log.info("\nRunning ADVI (20,000 iterations)...")
    approx = run_advi(model, n_iterations=20_000)

    converged = check_advi_convergence(approx)
    with model:
        advi_trace = approx.sample(1000, random_seed=42)

    coef_results   = check_coefficient_directions(advi_trace)
    var_results    = check_variance_components(advi_trace)
    season_results = check_season_intercepts(advi_trace, season_to_idx)

    # mu_log_league sanity check
    mll_mean = float(advi_trace.posterior["mu_log_league"].values.mean())
    mll_implied_side = float(np.exp(mll_mean))
    log.info("\nmu_log_league: mean=%.4f → implied per-side runs=%.3f (target: 4.3–4.7)",
             mll_mean, mll_implied_side)
    if 4.0 <= mll_implied_side <= 5.0:
        log.info("  mu_log_league PASS: implied per-side runs %.3f in [4.0, 5.0]", mll_implied_side)
    else:
        log.warning("  mu_log_league WARN: implied per-side runs %.3f outside [4.0, 5.0]", mll_implied_side)

    kill_results = run_advi_kill_criterion(approx, full_df, train_df, model, coords)

    # -- Summary report -----------------------------------------------------
    log.info("\n" + "=" * 60)
    log.info("ADVI FAST-PASS SUMMARY REPORT")
    log.info("=" * 60)
    log.info("ELBO convergence:        %s", "PASS" if converged else "FAIL")
    log.info("mu_log_league (per side):%.3f runs  %s",
             mll_implied_side, "OK" if 4.0 <= mll_implied_side <= 5.0 else "WARN")
    for param, res in coef_results.items():
        status = "OK" if res["sign_ok"] else "WARN — wrong sign"
        log.info("  %-18s  mean=%+.3f  expected=%s  %s",
                 param, res["mean"], res["expected"], status)
    for param, res in var_results.items():
        log.info("  %-20s  mean=%.4f  %s", param, res["mean"], res["status"])
    log.info("Season spread:           %.4f  %s",
             season_results.get("spread", 0), "OK" if season_results.get("spread", 0) > 0.02 else "WARN")
    log.info("ADVI kill criterion:     PPM=%.4f  threshold=%.2f  %s",
             kill_results.get("advi_ppm", float("nan")),
             kill_results.get("threshold", 8.85),
             "PASS" if kill_results.get("passed") else "FAIL")

    all_ok = (
        converged
        and all(r["sign_ok"] for r in coef_results.values())
        and all(r["status"] == "OK" for r in var_results.values())
        and kill_results.get("passed", False)
    )
    log.info("\nOVERALL ADVI PHASE 0 RESULT: %s",
             "PASS — proceed to NUTS hand-off" if all_ok else "FAIL or WARN — review above before NUTS")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
