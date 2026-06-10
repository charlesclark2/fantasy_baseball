"""
run_scoring_nuts.py — Epic 17, Story 17.1 Phase 1, v3

Full NUTS inference for the PyMC hierarchical NegBin run-scoring model.
Reuses all data-prep and model-building code from run_scoring_advi.py.

v3 changes (final architectural attempt within log-link NegBin):

  Fix 1 — Jensen correction:
    Each signal term is corrected by -beta_s² × sigma_s² / 2, where sigma_s² is
    the training-data z-score variance (≈1.0 after StandardScaler). This is treated
    as a fixed constant per signal; beta_s is still a learned PyMC variable. The
    correction makes E[exp(beta*z)] ≈ exp(beta*E[z]) across the training distribution,
    zeroing the structural Jensen floor that caused the irreducible +0.170 PPM
    overestimate at beta_bullpen=0.172, sigma_z=1.14.

    Approximate Jensen offsets (training z-score variance ≈ 1.0 by construction):
      run_env:  -beta_run_env² × σ²_run_env / 2   ≈ -0.0012  (β≈0.05)
      offense:  -beta_offense² × σ²_offense / 2   ≈ -0.0005  (β≈0.03)
      bullpen:  -beta_bullpen² × σ²_bullpen / 2   ≈ -0.0149  (β≈0.17)  ← dominant
      starter:  -beta_starter² × σ²_starter / 2   ≈ -0.0011  (β≈0.05)
    Exact training variances logged at runtime.

  Fix 2 — Within-season actual runs regressor:
    rolling_league_runs_14d: 14-calendar-day rolling mean of league-wide total
    runs/game, using only games strictly before each game's date. Sourced from
    mart_game_results (home_final_score + away_final_score). Leakage-safe: each
    row's window uses games with game_date < row's game_date. Prior: Normal(0.1, 0.3).
    Also Jensen-corrected.

2026 calibration window (v2, unchanged):
  - pre-May 2026 (March + April) → training observations for delta_2026
  - May-2026 → kill criterion (pure OOS)
  - Signal scalers fitted on 2022-2025 only; applied to all rows

PRE-COMMITTED KILL CRITERION: PPM ≤ 8.81 on May-2026 OOS games.
  PASS → proceed to three-layer eval + Layer 4.
  FAIL → formally close Epic 17 totals; record in implementation_guide.md and
         totals_2026_failure_analysis.md as the seventh independent confirmation.

Usage (HAND-OFF — expect ~10-15 minutes on M-series CPU):
  uv run python betting_ml/models/bayesian/run_scoring_nuts.py

Outputs:
  betting_ml/models/bayesian/nuts_trace.nc
  betting_ml/models/bayesian/nuts_summary.json
"""

from __future__ import annotations

import json
import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_BAYESIAN_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "bayesian"
_TRACE_PATH   = _BAYESIAN_DIR / "nuts_trace.nc"
_SUMMARY_PATH = _BAYESIAN_DIR / "nuts_summary.json"

# NUTS settings
_N_DRAWS   = 4000
_N_TUNE    = 2000
_N_CHAINS  = 4
_TARGET_ACCEPT = 0.9

# Kill criterion
_KILL_THRESHOLD_NUTS = 8.81
_OOS_SEASON = 2026
_CALIB_MONTHS = [3, 4]   # March + April 2026 → training observations for delta_2026
_OOS_MONTH    = 5        # May 2026 → kill criterion (pure OOS)
_MIN_CALIB_OBS = 200     # warn if fewer observations in the 2026 calibration window


# ---------------------------------------------------------------------------
# Import data-prep and model from ADVI module
# ---------------------------------------------------------------------------

from betting_ml.models.bayesian.run_scoring_advi import (
    _load_oos_signals,
    _load_game_results,
    _expand_to_sides,
    _build_training_frame,
    _fit_and_apply_scalers,
    _TRAIN_SEASONS,
)


# ---------------------------------------------------------------------------
# Fix 2: rolling 14-day league run environment feature
# ---------------------------------------------------------------------------

def _add_rolling_league_runs(game_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add rolling_league_runs_14d to a game-level DataFrame.

    For each game on date D, computes the mean total runs/game across all
    completed games in the 14 calendar days strictly before D (window: [D-14, D)).
    Leakage-safe: a game's own result is never in its own window.

    Games with no prior-14d data (e.g. first week of each season) receive NaN —
    callers should impute with the training mean before z-scoring.
    """
    game_df = game_df.copy()
    game_df["total_runs"] = game_df["home_final_score"] + game_df["away_final_score"]

    # Aggregate to daily totals
    daily = (
        game_df.groupby("game_date")
        .agg(runs_sum=("total_runs", "sum"), n_games=("total_runs", "count"))
        .reset_index()
        .sort_values("game_date")
        .reset_index(drop=True)
    )

    dates     = daily["game_date"].values
    runs_sum  = daily["runs_sum"].values
    n_games   = daily["n_games"].values

    rolling_vals: dict = {}
    for i, d in enumerate(dates):
        window_start = d - np.timedelta64(14, "D")
        mask = (dates >= window_start) & (dates < d)
        total_n = int(n_games[mask].sum())
        rolling_vals[d] = (
            float(runs_sum[mask].sum()) / float(total_n) if total_n > 0 else np.nan
        )

    daily["rolling_league_runs_14d"] = daily["game_date"].map(rolling_vals)

    game_df = game_df.merge(
        daily[["game_date", "rolling_league_runs_14d"]],
        on="game_date",
        how="left",
    )
    return game_df


# ---------------------------------------------------------------------------
# Index builder — extended to give 2026 its own season index
# ---------------------------------------------------------------------------

def _build_indices_with_2026(
    base_train: pd.DataFrame,
    full: pd.DataFrame,
) -> tuple[pd.DataFrame, dict, dict, dict]:
    """
    Build integer indices for batting_team, pitching_team, season.

    base_train: 2022-2025 rows only (used to derive the canonical team list and
                the first 4 season indices 0..3).
    full:       all rows — 2022-2025 + pre-May 2026 calibration + May-2026 OOS.
                Gets indices applied in place.

    2026 is assigned season_idx = 4 (its own column in delta_season), allowing
    the model to estimate a distinct intercept from the March-April calibration
    observations rather than borrowing the 2025 intercept.
    """
    teams = sorted(set(
        base_train["batting_team"].dropna().tolist()
        + base_train["pitching_team"].dropna().tolist()
    ))
    team_to_idx = {t: i for i, t in enumerate(teams)}

    base_seasons = sorted(base_train["season"].unique().tolist())    # [2022, 2023, 2024, 2025]
    all_seasons  = base_seasons + [_OOS_SEASON]                      # [2022, 2023, 2024, 2025, 2026]
    season_to_idx = {s: i for i, s in enumerate(all_seasons)}

    full = full.copy()
    full["batting_team_idx"]  = full["batting_team"].map(team_to_idx)
    full["pitching_team_idx"] = full["pitching_team"].map(team_to_idx)
    full["season_idx"]        = full["season"].map(season_to_idx)

    before = len(full)
    full = full.dropna(subset=["batting_team_idx", "pitching_team_idx", "season_idx"])
    dropped = before - len(full)
    if dropped > 0:
        log.warning("Dropped %d rows with unmapped team/season indices", dropped)

    full["batting_team_idx"]  = full["batting_team_idx"].astype(int)
    full["pitching_team_idx"] = full["pitching_team_idx"].astype(int)
    full["season_idx"]        = full["season_idx"].astype(int)

    coords = {
        "team":   teams,
        "season": [str(s) for s in all_seasons],   # 5 seasons including "2026"
        "obs":    [],                               # set after train_df is finalised
    }
    return full, team_to_idx, season_to_idx, coords


# ---------------------------------------------------------------------------
# Fix 1 + Fix 2: Jensen-corrected model with rolling regressor (v3)
# ---------------------------------------------------------------------------

def build_model_v3(
    df_train: pd.DataFrame,
    coords: dict,
    sigma_sq_dict: dict,
) -> object:
    """
    Jensen-corrected NegBin model with within-season rolling runs regressor.

    Each signal s contributes: beta_s * z_s - beta_s² * sigma_sq_s / 2
    where sigma_sq_s is the training z-score variance (fixed constant ≈ 1.0).
    This makes E_z[exp(beta*z - beta²*sigma²/2)] = exp(beta*E[z]) = 1 on the
    training distribution, zeroing the Jensen structural floor.

    rolling_league_z (Fix 2) is included with the same Jensen correction and
    prior Normal(0.1, 0.3).
    """
    import pymc as pm

    sigma_sq_run_env = float(sigma_sq_dict["run_env_z"])
    sigma_sq_offense = float(sigma_sq_dict["offense_mu_z"])
    sigma_sq_bullpen = float(sigma_sq_dict["opp_bullpen_mu_z"])
    sigma_sq_starter = float(sigma_sq_dict["opp_starter_mu_z"])
    sigma_sq_rolling = float(sigma_sq_dict["rolling_league_z"])

    n_teams   = len(coords["team"])
    n_seasons = len(coords["season"])

    bat_idx = df_train["batting_team_idx"].values
    pit_idx = df_train["pitching_team_idx"].values
    sea_idx = df_train["season_idx"].values

    z_run_env  = df_train["run_env_z"].values
    z_offense  = df_train["offense_mu_z"].values
    z_bullpen  = df_train["opp_bullpen_mu_z"].values
    z_starter  = df_train["opp_starter_mu_z"].values
    z_rolling  = df_train["rolling_league_z"].values

    with pm.Model(coords=coords) as model:

        # ── Hyperpriors ──────────────────────────────────────────────────────
        mu_log_league = pm.Normal("mu_log_league", mu=np.log(4.5), sigma=0.2)
        sigma_offense = pm.HalfNormal("sigma_offense", sigma=0.25)
        sigma_defense = pm.HalfNormal("sigma_defense", sigma=0.25)
        sigma_season  = pm.HalfNormal("sigma_season",  sigma=0.15)

        # ── Group-level effects ───────────────────────────────────────────────
        alpha_offense = pm.Normal("alpha_offense", mu=0, sigma=sigma_offense, dims="team")
        alpha_defense = pm.Normal("alpha_defense", mu=0, sigma=sigma_defense, dims="team")
        delta_season  = pm.Normal("delta_season",  mu=0, sigma=sigma_season,  dims="season")

        # ── Signal coefficients ───────────────────────────────────────────────
        beta_run_env = pm.Normal("beta_run_env", mu=0.0, sigma=0.3)
        beta_offense = pm.Normal("beta_offense", mu=0.2, sigma=0.3)
        beta_bullpen = pm.Normal("beta_bullpen", mu=0.1, sigma=0.3)
        beta_starter = pm.Normal("beta_starter", mu=0.1, sigma=0.3)
        beta_rolling = pm.Normal("beta_rolling", mu=0.1, sigma=0.3)

        # ── Jensen-corrected log-linear predictor ─────────────────────────────
        # Each term: beta * z - beta² * sigma² / 2
        # Correction zeroes E[exp(beta*z)] floor on the training distribution.
        log_mu_side = (
            mu_log_league
            + alpha_offense[bat_idx]
            + alpha_defense[pit_idx]
            + delta_season[sea_idx]
            + beta_run_env * z_run_env - beta_run_env**2 * sigma_sq_run_env / 2
            + beta_offense * z_offense - beta_offense**2 * sigma_sq_offense / 2
            + beta_bullpen * z_bullpen - beta_bullpen**2 * sigma_sq_bullpen / 2
            + beta_starter * z_starter - beta_starter**2 * sigma_sq_starter / 2
            + beta_rolling * z_rolling - beta_rolling**2 * sigma_sq_rolling / 2
        )
        mu_side = pm.Deterministic("mu_side", pm.math.exp(log_mu_side))

        # ── NegBin overdispersion ─────────────────────────────────────────────
        alpha_nb = pm.HalfNormal("alpha_nb", sigma=5.0)

        # ── Likelihood ────────────────────────────────────────────────────────
        _ = pm.NegativeBinomial(
            "runs",
            mu=mu_side,
            alpha=alpha_nb,
            observed=df_train["runs_scored"].values,
            dims="obs",
        )

    return model


# ---------------------------------------------------------------------------
# NUTS inference
# ---------------------------------------------------------------------------

def run_nuts(model, train_df: pd.DataFrame) -> object:
    """Run NUTS sampler with 4 chains × 4000 draws (2000 tune)."""
    import pymc as pm

    log.info("Starting NUTS sampler: %d chains × %d draws + %d tune steps",
             _N_CHAINS, _N_DRAWS, _N_TUNE)
    log.info("Expected runtime: ~10-15 minutes on M-series CPU.")
    log.info("Progress bars are per-chain. Watch for divergences (should be < 1%%).")

    with model:
        trace = pm.sample(
            draws=_N_DRAWS,
            tune=_N_TUNE,
            chains=_N_CHAINS,
            target_accept=_TARGET_ACCEPT,
            random_seed=42,
            progressbar=True,
            return_inferencedata=True,
        )

    return trace


def check_nuts_diagnostics(trace) -> dict:
    """Report R-hat, ESS, divergences."""
    import arviz as az

    log.info("\n=== NUTS Diagnostics ===")

    divergences = int(trace.sample_stats["diverging"].values.sum())
    log.info("Divergences: %d (threshold: < %d)", divergences,
             int(_N_DRAWS * _N_CHAINS * 0.01))

    summary = az.summary(trace, var_names=[
        "mu_log_league", "sigma_offense", "sigma_defense", "sigma_season",
        "beta_run_env", "beta_offense", "beta_bullpen", "beta_starter",
        "beta_rolling", "alpha_nb",
    ])
    log.info("\nParameter summary (key scalars):\n%s", summary.to_string())

    rhat_cols = [c for c in summary.columns if "r_hat" in c.lower()]
    if rhat_cols:
        rhat_vals = summary[rhat_cols[0]].values
        max_rhat = float(np.nanmax(rhat_vals))
        log.info("\nMax R-hat: %.4f (threshold: < 1.01)", max_rhat)
        if max_rhat > 1.01:
            log.warning("R-hat > 1.01 — chains not converged. Do NOT use this trace.")
        else:
            log.info("R-hat OK: all scalar params converged.")
    else:
        max_rhat = float("nan")

    ess_cols = [c for c in summary.columns if "ess_bulk" in c.lower()]
    if ess_cols:
        ess_vals = summary[ess_cols[0]].values
        min_ess = float(np.nanmin(ess_vals))
        log.info("Min ESS (bulk): %.0f (threshold: > 400)", min_ess)
        if min_ess < 400:
            log.warning("Low ESS — increase draws or check parameterization.")
    else:
        min_ess = float("nan")

    return {
        "divergences": divergences,
        "max_rhat": max_rhat,
        "min_ess_bulk": min_ess,
        "rhat_ok": max_rhat < 1.01 if not np.isnan(max_rhat) else False,
    }


# ---------------------------------------------------------------------------
# Kill criterion check (v3 — Jensen-corrected + rolling)
# ---------------------------------------------------------------------------

def run_kill_criterion(
    trace,
    full_df: pd.DataFrame,
    coords: dict,
    sigma_sq_dict: dict,
) -> dict:
    """
    Posterior predictive mean on May-2026 OOS. Must be ≤ 8.81.

    Log-linear predictor includes Jensen corrections and rolling_league_z regressor,
    matching build_model_v3. sigma_sq_dict provides the fixed training variance
    constants for each signal.
    """
    may_mask = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month == _OOS_MONTH)
    )
    may_df = full_df[may_mask].copy().reset_index(drop=True)

    if len(may_df) == 0:
        log.error("No May-2026 OOS games found")
        return {"error": "no May-2026 games"}

    log.info("\nMay-2026 OOS: %d rows, %d unique games", len(may_df), may_df["game_pk"].nunique())

    post = trace.posterior
    n_chains  = post.dims["chain"]
    n_draws   = post.dims["draw"]
    n_samples = n_chains * n_draws

    mu_log_league = post["mu_log_league"].values.reshape(n_samples)
    alpha_offense = post["alpha_offense"].values.reshape(n_samples, len(coords["team"]))
    alpha_defense = post["alpha_defense"].values.reshape(n_samples, len(coords["team"]))
    delta_season  = post["delta_season"].values.reshape(n_samples, len(coords["season"]))
    beta_run_env  = post["beta_run_env"].values.reshape(n_samples)
    beta_offense  = post["beta_offense"].values.reshape(n_samples)
    beta_bullpen  = post["beta_bullpen"].values.reshape(n_samples)
    beta_starter  = post["beta_starter"].values.reshape(n_samples)
    beta_rolling  = post["beta_rolling"].values.reshape(n_samples)
    alpha_nb      = post["alpha_nb"].values.reshape(n_samples)

    bat_idx    = may_df["batting_team_idx"].values
    pit_idx    = may_df["pitching_team_idx"].values
    sea_idx    = may_df["season_idx"].values
    run_env_z  = may_df["run_env_z"].values
    offense_z  = may_df["offense_mu_z"].values
    bullpen_z  = may_df["opp_bullpen_mu_z"].values
    starter_z  = may_df["opp_starter_mu_z"].values
    rolling_z  = may_df["rolling_league_z"].values

    # Jensen correction constants (fixed training variances)
    sq_run_env  = float(sigma_sq_dict["run_env_z"])
    sq_offense  = float(sigma_sq_dict["offense_mu_z"])
    sq_bullpen  = float(sigma_sq_dict["opp_bullpen_mu_z"])
    sq_starter  = float(sigma_sq_dict["opp_starter_mu_z"])
    sq_rolling  = float(sigma_sq_dict["rolling_league_z"])

    log.info("Computing posterior predictive for %d OOS rows × %d draws...", len(may_df), n_samples)

    log_mu = (
        mu_log_league[:, None]
        + alpha_offense[:, bat_idx]
        + alpha_defense[:, pit_idx]
        + delta_season[:, sea_idx]
        + beta_run_env[:, None] * run_env_z[None, :]
        - (beta_run_env**2)[:, None] * sq_run_env / 2
        + beta_offense[:, None] * offense_z[None, :]
        - (beta_offense**2)[:, None] * sq_offense / 2
        + beta_bullpen[:, None] * bullpen_z[None, :]
        - (beta_bullpen**2)[:, None] * sq_bullpen / 2
        + beta_starter[:, None] * starter_z[None, :]
        - (beta_starter**2)[:, None] * sq_starter / 2
        + beta_rolling[:, None] * rolling_z[None, :]
        - (beta_rolling**2)[:, None] * sq_rolling / 2
    )
    mu_oos = np.exp(log_mu)  # (n_samples, n_oos)

    rng = np.random.default_rng(42)
    ppc_runs = np.zeros_like(mu_oos, dtype=float)
    for d in range(n_samples):
        a = float(alpha_nb[d])
        p_nb = a / (a + mu_oos[d])
        ppc_runs[d] = rng.negative_binomial(a, p_nb).astype(float)

    game_pks = may_df["game_pk"].unique()
    home_sel, away_sel = [], []
    actual_totals = []
    for gk in game_pks:
        rows = may_df[may_df["game_pk"] == gk]
        if len(rows) != 2:
            continue
        h_row = rows[rows["side"] == "home"]
        a_row = rows[rows["side"] == "away"]
        if len(h_row) == 0 or len(a_row) == 0:
            continue
        home_sel.append(h_row.index[0])
        away_sel.append(a_row.index[0])
        actual_totals.append(
            float(h_row["runs_scored"].values[0]) + float(a_row["runs_scored"].values[0])
        )

    home_sel = np.array(home_sel)
    away_sel = np.array(away_sel)
    actual_totals = np.array(actual_totals)

    total_ppc = ppc_runs[:, home_sel] + ppc_runs[:, away_sel]  # (n_samples, n_games)
    ppm = float(total_ppc.mean())
    actual_mean = float(actual_totals.mean())
    bias = ppm - actual_mean
    passed = ppm <= _KILL_THRESHOLD_NUTS

    log.info("\n========= NUTS KILL CRITERION CHECK =========")
    log.info("  May-2026 games evaluated:           %d", len(actual_totals))
    log.info("  NUTS posterior predictive mean:     %.4f", ppm)
    log.info("  Actual May-2026 mean total_runs:    %.4f", actual_mean)
    log.info("  Bias (PPM - actual):                %+.4f", bias)
    log.info("  Kill criterion threshold:           %.2f", _KILL_THRESHOLD_NUTS)
    log.info("  Result: %s", "PASS → proceed to three-layer eval" if passed else
             "FAIL → Epic 17 totals formally closed")
    log.info("=============================================")

    # delta_2026 posterior
    season_2026_idx = len(coords["season"]) - 1
    delta_2026_vals = delta_season[:, season_2026_idx]
    delta_2026_mean = float(delta_2026_vals.mean())
    delta_2026_std  = float(delta_2026_vals.std())
    delta_2026_p3   = float(np.percentile(delta_2026_vals, 3))
    delta_2026_p97  = float(np.percentile(delta_2026_vals, 97))
    hdi_excludes_zero = (delta_2026_p3 > 0) or (delta_2026_p97 < 0)

    implied_per_side   = np.exp(mu_log_league.mean() + delta_2026_mean)
    baseline_per_side  = np.exp(mu_log_league.mean())
    run_shift_per_side = implied_per_side - baseline_per_side

    log.info("\n  delta_2026 (estimated from March-April calibration):")
    log.info("    mean=%.4f  std=%.4f  94%% HDI=[%.4f, %.4f]",
             delta_2026_mean, delta_2026_std, delta_2026_p3, delta_2026_p97)
    log.info("    HDI excludes zero: %s",
             "YES — model detected 2026 run environment shift" if hdi_excludes_zero
             else "NO — 2026 intercept consistent with zero")
    log.info("    Implied run shift: %+.3f per side (%+.3f total)",
             run_shift_per_side, run_shift_per_side * 2)

    # Rolling feature: mean z-score for May-2026 (diagnostic)
    rolling_z_may_mean = float(rolling_z.mean())
    log.info("\n  rolling_league_z (May-2026): mean=%.4f  std=%.4f",
             rolling_z_may_mean, float(rolling_z.std()))
    log.info("  beta_rolling posterior: mean=%.4f", float(beta_rolling.mean()))

    return {
        "n_games": len(actual_totals),
        "ppm": ppm,
        "actual_mean": actual_mean,
        "bias": bias,
        "threshold": _KILL_THRESHOLD_NUTS,
        "passed": passed,
        "delta_2026_mean": delta_2026_mean,
        "delta_2026_hdi_low": delta_2026_p3,
        "delta_2026_hdi_high": delta_2026_p97,
        "delta_2026_hdi_excludes_zero": hdi_excludes_zero,
        "season_run_shift_total": float(run_shift_per_side * 2),
        "beta_rolling_mean": float(beta_rolling.mean()),
        "rolling_z_may_mean": rolling_z_may_mean,
    }


# ---------------------------------------------------------------------------
# Coefficient direction check (NUTS posterior)
# ---------------------------------------------------------------------------

def check_coefficient_directions_nuts(trace) -> dict:
    post = trace.posterior
    checks = {
        "beta_run_env": ("positive", lambda x: x > 0),
        "beta_offense":  ("positive", lambda x: x > 0),
        "beta_bullpen":  ("positive", lambda x: x > 0),
        "beta_starter":  ("positive", lambda x: x > 0),
        "beta_rolling":  ("positive", lambda x: x > 0),
    }
    results = {}
    log.info("\nNUTS coefficient posterior means (HDI 94%%):")
    for param, (expected, check_fn) in checks.items():
        vals = post[param].values.ravel()
        mean_ = float(vals.mean())
        p3  = float(np.percentile(vals, 3))
        p97 = float(np.percentile(vals, 97))
        pct_correct = float(check_fn(vals).mean())
        sign_ok = pct_correct > 0.80
        log.info("  %-18s  mean=%+.3f  [%+.3f, %+.3f]  P(correct)=%.2f  %s",
                 param, mean_, p3, p97, pct_correct, "OK" if sign_ok else "WARN")
        results[param] = {"mean": mean_, "p3": p3, "p97": p97, "sign_ok": sign_ok}
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("Epic 17 Story 17.1 — NUTS Full Inference (Phase 1, v3)")
    log.info("Fixes: Jensen correction + rolling league runs regressor")
    log.info("=" * 60)

    # ── Load all data ────────────────────────────────────────────────────────
    log.info("\n[1/5] Loading OOS signals and game results...")
    all_seasons = _TRAIN_SEASONS + [_OOS_SEASON]
    signals  = _load_oos_signals()
    games    = _load_game_results(all_seasons)

    # Fix 2: add rolling 14d league runs feature to game-level df
    log.info("  Computing rolling_league_runs_14d (14-day window, leakage-safe)...")
    games = _add_rolling_league_runs(games)

    sides    = _expand_to_sides(games)
    full_df  = _build_training_frame(signals, sides)

    # Merge rolling feature from game level into (game_pk, side) frame
    rolling_map = games[["game_pk", "rolling_league_runs_14d"]].drop_duplicates("game_pk")
    full_df = full_df.merge(rolling_map, on="game_pk", how="left")

    # Spot-check: first May-2026 game's rolling window must exclude May games
    may_2026_games = full_df[
        (full_df["season"] == 2026) & (full_df["game_date"].dt.month == 5)
    ].drop_duplicates("game_pk").sort_values("game_date")
    if len(may_2026_games) > 0:
        sample = may_2026_games.iloc[0]
        sample_date = sample["game_date"]
        log.info("  Rolling 14d spot-check: first May-2026 game on %s → rolling_14d=%.3f",
                 sample_date.date(),
                 float(sample["rolling_league_runs_14d"])
                 if pd.notna(sample["rolling_league_runs_14d"]) else float("nan"))
        log.info("    Window: [%s, %s)  — strictly before game date ✓",
                 (sample_date - pd.Timedelta(days=14)).date(),
                 sample_date.date())

    # ── Split 2026 into calibration (Mar+Apr) and OOS (May) ─────────────────
    log.info("\n[2/5] Splitting 2026 into calibration + OOS windows...")
    calib_mask = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month.isin(_CALIB_MONTHS))
    )
    may_mask = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month == _OOS_MONTH)
    )
    base_train_mask = full_df["season"].isin(_TRAIN_SEASONS)

    n_calib_obs   = int(calib_mask.sum())
    n_calib_games = int(full_df.loc[calib_mask, "game_pk"].nunique())
    n_may_obs     = int(may_mask.sum())
    n_may_games   = int(full_df.loc[may_mask, "game_pk"].nunique())

    log.info("  2026 calibration (Mar+Apr): %d rows, %d games", n_calib_obs, n_calib_games)
    log.info("  2026 OOS (May):             %d rows, %d games", n_may_obs, n_may_games)

    if n_calib_obs < _MIN_CALIB_OBS:
        log.warning(
            "  WARN: Only %d calibration observations (< %d threshold).",
            n_calib_obs, _MIN_CALIB_OBS,
        )
    else:
        log.info("  Calibration obs count OK (%d >= %d).", n_calib_obs, _MIN_CALIB_OBS)

    if n_may_obs == 0:
        log.error("No May-2026 OOS games found — cannot run kill criterion.")
        sys.exit(1)

    # ── Build indices — 2026 gets its own season index (4) ───────────────────
    log.info("\n[3/5] Building indices and z-scoring signals...")
    base_train_df = full_df[base_train_mask].copy()
    full_df, team_to_idx, season_to_idx, coords = _build_indices_with_2026(base_train_df, full_df)

    # Re-derive masks after potential dropna in _build_indices_with_2026
    base_train_mask = full_df["season"].isin(_TRAIN_SEASONS)
    calib_mask_v2   = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month.isin(_CALIB_MONTHS))
    )
    train_mask_extended = base_train_mask | calib_mask_v2

    # Scalers fitted on 2022-2025 only; applied to all rows
    train_for_scalers = full_df[base_train_mask].copy().reset_index(drop=True)
    train_for_scalers, full_df, _ = _fit_and_apply_scalers(train_for_scalers, full_df)

    # Fix 2: z-score rolling_league_runs_14d on 2022-2025 training data
    from sklearn.preprocessing import StandardScaler

    # Impute NaN (first week of each season) with training mean → z-scores to 0
    train_rolling_mean = float(
        full_df.loc[base_train_mask, "rolling_league_runs_14d"].dropna().mean()
    )
    full_df["rolling_league_runs_14d"] = (
        full_df["rolling_league_runs_14d"].fillna(train_rolling_mean)
    )
    rolling_scaler = StandardScaler()
    rolling_scaler.fit(
        full_df.loc[base_train_mask, "rolling_league_runs_14d"].values.reshape(-1, 1)
    )
    full_df["rolling_league_z"] = rolling_scaler.transform(
        full_df["rolling_league_runs_14d"].values.reshape(-1, 1)
    ).ravel()
    log.info(
        "  rolling_league_runs_14d → rolling_league_z   mean=%.4f  std=%.4f",
        float(full_df.loc[base_train_mask, "rolling_league_z"].mean()),
        float(full_df.loc[base_train_mask, "rolling_league_z"].std()),
    )
    log.info("  rolling_league_runs_14d training: mean=%.4f  std=%.4f",
             train_rolling_mean,
             float(full_df.loc[base_train_mask, "rolling_league_runs_14d"].std()))
    log.info("  rolling_league_z May-2026: mean=%.4f",
             float(full_df.loc[
                 (full_df["season"] == 2026) & (full_df["game_date"].dt.month == 5),
                 "rolling_league_z"
             ].mean()))

    # Fix 1: compute Jensen correction constants (training z-score variances ≈ 1.0)
    sigma_sq_dict = {
        "run_env_z":        float(full_df.loc[base_train_mask, "run_env_z"].var()),
        "offense_mu_z":     float(full_df.loc[base_train_mask, "offense_mu_z"].var()),
        "opp_bullpen_mu_z": float(full_df.loc[base_train_mask, "opp_bullpen_mu_z"].var()),
        "opp_starter_mu_z": float(full_df.loc[base_train_mask, "opp_starter_mu_z"].var()),
        "rolling_league_z": float(full_df.loc[base_train_mask, "rolling_league_z"].var()),
    }
    log.info("  Jensen correction σ² (training z-score variances, should be ≈1.0):")
    for k, v in sigma_sq_dict.items():
        log.info("    %-25s  σ²=%.6f", k, v)

    # Combined training frame (2022-2025 + 2026 Mar+Apr)
    train_df = full_df[train_mask_extended].copy().reset_index(drop=True)
    coords["obs"] = list(range(len(train_df)))

    log.info("\n  Training (2022-2025):        %d rows, %d games",
             int(base_train_mask.sum()), full_df.loc[base_train_mask, "game_pk"].nunique())
    log.info("  Training (2026 calibration): %d rows, %d games",
             n_calib_obs, n_calib_games)
    log.info("  Combined training total:     %d rows", len(train_df))
    log.info("  Teams: %d  |  Seasons: %d (2022-2025 + 2026)",
             len(team_to_idx), len(coords["season"]))
    log.info("  Runs scored — mean=%.3f  std=%.3f",
             train_df["runs_scored"].mean(), train_df["runs_scored"].std())

    # ── Build model (v3: Jensen-corrected + rolling) and run NUTS ────────────
    log.info("\n[4/5] Building PyMC model (v3) and running NUTS...")
    import pymc as pm
    import arviz as az

    model = build_model_v3(train_df, coords, sigma_sq_dict)

    trace = run_nuts(model, train_df)

    log.info("\nSaving trace → %s", _TRACE_PATH)
    trace.to_netcdf(str(_TRACE_PATH), engine="h5netcdf")
    log.info("Trace saved.")

    # ── Diagnostics ──────────────────────────────────────────────────────────
    diag = check_nuts_diagnostics(trace)
    coef = check_coefficient_directions_nuts(trace)

    mll_mean    = float(trace.posterior["mu_log_league"].values.mean())
    mll_implied = float(np.exp(mll_mean))
    log.info("\nmu_log_league: mean=%.4f → implied per-side runs=%.3f", mll_mean, mll_implied)

    # ── Kill criterion ────────────────────────────────────────────────────────
    log.info("\n[5/5] Running NUTS kill criterion check on May-2026 OOS...")
    kill = run_kill_criterion(trace, full_df, coords, sigma_sq_dict)

    # ── Save summary ─────────────────────────────────────────────────────────
    summary = {
        "model_version": "v3_jensen_rolling",
        "nuts_settings": {
            "draws": _N_DRAWS,
            "tune": _N_TUNE,
            "chains": _N_CHAINS,
            "target_accept": _TARGET_ACCEPT,
        },
        "jensen_sigma_sq": sigma_sq_dict,
        "calibration_window": {
            "n_calib_obs": n_calib_obs,
            "n_calib_games": n_calib_games,
            "months": _CALIB_MONTHS,
        },
        "diagnostics": diag,
        "mu_log_league_implied_per_side": mll_implied,
        "coefficients": {k: {"mean": v["mean"], "sign_ok": v["sign_ok"]} for k, v in coef.items()},
        "kill_criterion": kill,
    }
    with open(_SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    log.info("\nSummary saved → %s", _SUMMARY_PATH)

    log.info("\n" + "=" * 60)
    log.info("NUTS PHASE 1 SUMMARY (v3 — Jensen + rolling)")
    log.info("=" * 60)
    log.info("Calibration obs (Mar+Apr 2026): %d  %s",
             n_calib_obs, "OK" if n_calib_obs >= _MIN_CALIB_OBS else "WARN: sparse")
    log.info("Divergences:      %d  %s",
             diag["divergences"], "OK" if diag["divergences"] < 20 else "WARN")
    log.info("Max R-hat:        %.4f  %s",
             diag["max_rhat"], "OK" if diag.get("rhat_ok") else "WARN")
    log.info("Min ESS (bulk):   %.0f  %s",
             diag["min_ess_bulk"], "OK" if diag["min_ess_bulk"] > 400 else "WARN")
    log.info("delta_2026:       mean=%.4f  94%% HDI=[%.4f, %.4f]  excl.zero=%s",
             kill.get("delta_2026_mean", float("nan")),
             kill.get("delta_2026_hdi_low", float("nan")),
             kill.get("delta_2026_hdi_high", float("nan")),
             kill.get("delta_2026_hdi_excludes_zero", "?"))
    log.info("beta_rolling:     mean=%.4f  rolling_z_may=%.4f",
             kill.get("beta_rolling_mean", float("nan")),
             kill.get("rolling_z_may_mean", float("nan")))
    log.info("Kill criterion:   PPM=%.4f  threshold=%.2f  %s",
             kill.get("ppm", float("nan")), _KILL_THRESHOLD_NUTS,
             "PASS" if kill.get("passed") else "FAIL")
    log.info("Trace saved at:   %s", _TRACE_PATH)
    log.info("=" * 60)

    if kill.get("passed"):
        log.info("\nPASS. Proceed to three-layer + Layer 4 evaluation (Phase 2).")
        log.info("  Load trace with: az.from_netcdf('%s')", _TRACE_PATH)
    else:
        log.warning("\nKill criterion FAILED.")
        log.warning("Pre-committed decision: Epic 17 totals formally closed.")
        log.warning("Record in implementation_guide.md and totals_2026_failure_analysis.md.")
        log.warning("Re-open criteria: (a) full 2026 season data for honest delta_2026,")
        log.warning("or (b) sub-model signals that capture within-season scoring regime shifts.")


if __name__ == "__main__":
    main()
