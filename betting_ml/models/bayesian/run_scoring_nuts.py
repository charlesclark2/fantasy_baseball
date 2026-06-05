"""
run_scoring_nuts.py — Epic 17, Story 17.1 Phase 1

Full NUTS inference for the PyMC hierarchical NegBin run-scoring model.
Reuses all data-prep and model-building code from run_scoring_advi.py.

2026 calibration window (v2):
  - pre-May 2026 (March + April) games are included as training observations
    for a 5th pooled season intercept (delta_2026).
  - May-2026 games are held out entirely for the kill criterion (pure OOS).
  - Signal scalers are still fitted on 2022-2025 only; applied to all rows.

Signal direction (confirmed in ADVI Phase 0):
  - beta_run_env > 0: higher run environment → more runs per side
  - beta_offense > 0: better batting signal → more runs
  - beta_bullpen > 0: opp_bullpen_mu = bullpen_runs_allowed (higher = worse bullpen = more runs)
  - beta_starter > 0: opp_starter_mu = xwoba_against (higher = worse starter = more runs)

NUTS kill criterion: posterior predictive mean ≤ 8.81 on May-2026 OOS games.
If > 8.81, DO NOT proceed to evaluation. Update memory and revise model.

Usage (HAND-OFF — expect ~10 minutes on M-series CPU):
  uv run python betting_ml/models/bayesian/run_scoring_nuts.py

Outputs:
  betting_ml/models/bayesian/nuts_trace.nc        — ArviZ InferenceData (NetCDF)
  betting_ml/models/bayesian/nuts_summary.json    — scalar diagnostics + kill criterion
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
# Import data-prep and model from ADVI module (excluding _build_indices —
# we override it below to support the 2026 season extension)
# ---------------------------------------------------------------------------

from betting_ml.models.bayesian.run_scoring_advi import (
    _load_oos_signals,
    _load_game_results,
    _expand_to_sides,
    _build_training_frame,
    _fit_and_apply_scalers,
    build_model,
    _TRAIN_SEASONS,
)


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
# NUTS inference
# ---------------------------------------------------------------------------

def run_nuts(model, train_df: pd.DataFrame) -> object:
    """Run NUTS sampler with 4 chains × 4000 draws (2000 tune)."""
    import pymc as pm

    log.info("Starting NUTS sampler: %d chains × %d draws + %d tune steps",
             _N_CHAINS, _N_DRAWS, _N_TUNE)
    log.info("Expected runtime: ~10 minutes on M-series CPU.")
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
        "beta_run_env", "beta_offense", "beta_bullpen", "beta_starter", "alpha_nb",
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
# Kill criterion check
# ---------------------------------------------------------------------------

def run_kill_criterion(trace, full_df: pd.DataFrame, coords: dict) -> dict:
    """
    Posterior predictive mean on May-2026 OOS. Must be ≤ 8.81.

    May-2026 rows use season_idx = 4 (the dedicated 2026 intercept estimated
    from March-April calibration data). They were NOT in the model likelihood.
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
    alpha_nb      = post["alpha_nb"].values.reshape(n_samples)

    bat_idx   = may_df["batting_team_idx"].values
    pit_idx   = may_df["pitching_team_idx"].values
    sea_idx   = may_df["season_idx"].values
    run_env_z = may_df["run_env_z"].values
    offense_z = may_df["offense_mu_z"].values
    bullpen_z = may_df["opp_bullpen_mu_z"].values
    starter_z = may_df["opp_starter_mu_z"].values

    log.info("Computing posterior predictive for %d OOS rows × %d draws...", len(may_df), n_samples)

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
             "FAIL → stop; do not evaluate; revise model structure")
    log.info("=============================================")

    # delta_2026 posterior: index 4 = the dedicated 2026 season intercept
    season_2026_idx = len(coords["season"]) - 1   # index of "2026" (last entry)
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
    log.info("    HDI excludes zero: %s", "YES — model detected 2026 run environment shift" if hdi_excludes_zero else "NO — 2026 intercept consistent with zero")
    log.info("    Implied run shift: %+.3f per side (%+.3f total)",
             run_shift_per_side, run_shift_per_side * 2)

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
    log.info("Epic 17 Story 17.1 — NUTS Full Inference (Phase 1, v2)")
    log.info("2026 calibration window: March+April → delta_2026 estimated")
    log.info("=" * 60)

    # ── Load all data ────────────────────────────────────────────────────────
    log.info("\n[1/5] Loading OOS signals and game results...")
    all_seasons = _TRAIN_SEASONS + [_OOS_SEASON]
    signals  = _load_oos_signals()
    games    = _load_game_results(all_seasons)
    sides    = _expand_to_sides(games)
    full_df  = _build_training_frame(signals, sides)

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
            "  WARN: Only %d calibration observations (< %d threshold). "
            "delta_2026 estimate may be unstable — partial pooling with sigma_season "
            "will shrink it toward the mean of 2022-2025 deltas.",
            n_calib_obs, _MIN_CALIB_OBS
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

    # Combined training set: 2022-2025 + pre-May 2026
    # May-2026 rows have correct season_idx=4 but are excluded from likelihood
    train_mask_extended = base_train_mask | calib_mask
    # Re-derive masks from full_df after dropna in _build_indices_with_2026
    base_train_mask = full_df["season"].isin(_TRAIN_SEASONS)
    calib_mask_v2   = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month.isin(_CALIB_MONTHS))
    )
    train_mask_extended = base_train_mask | calib_mask_v2

    # Scalers fitted on 2022-2025 only; applied to all rows including 2026
    train_for_scalers = full_df[base_train_mask].copy().reset_index(drop=True)
    train_for_scalers, full_df, _ = _fit_and_apply_scalers(train_for_scalers, full_df)

    # Combined training frame for model fitting
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

    # ── Build model and run NUTS ─────────────────────────────────────────────
    log.info("\n[4/5] Building PyMC model and running NUTS...")
    import pymc as pm
    import arviz as az

    model = build_model(train_df, coords)

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
    kill = run_kill_criterion(trace, full_df, coords)

    # ── Save summary ─────────────────────────────────────────────────────────
    summary = {
        "nuts_settings": {
            "draws": _N_DRAWS,
            "tune": _N_TUNE,
            "chains": _N_CHAINS,
            "target_accept": _TARGET_ACCEPT,
        },
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
    log.info("NUTS PHASE 1 SUMMARY (v2 — with delta_2026)")
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
    log.info("Kill criterion:   PPM=%.4f  threshold=%.2f  %s",
             kill.get("ppm", float("nan")), _KILL_THRESHOLD_NUTS,
             "PASS" if kill.get("passed") else "FAIL")
    log.info("Trace saved at:   %s", _TRACE_PATH)
    log.info("=" * 60)

    if kill.get("passed"):
        log.info("\nNext: run three-layer + Layer 4 evaluation (Phase 2).")
        log.info("  Load trace with: az.from_netcdf('%s')", _TRACE_PATH)
    else:
        log.warning("\nKill criterion FAILED. Do NOT proceed to evaluation.")
        log.warning("Review delta_2026_mean and bias source before next iteration.")


if __name__ == "__main__":
    main()
