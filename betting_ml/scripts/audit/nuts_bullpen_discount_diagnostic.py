"""
nuts_bullpen_discount_diagnostic.py — Epic 17 Story 17.1b

Diagnostic NUTS run adding a 2026-specific bullpen beta interaction term.

Model change vs production:
    Effective bullpen coefficient for 2026 rows:
        beta_bullpen × (1 + beta_bullpen_2026_discount)
    Prior: beta_bullpen_2026_discount ~ Normal(0, 0.5)  [no discount by default]
    is_2026 = 1 for March-April 2026 calibration rows; 0 for 2022-2025 rows.

This is NOT a production model. Outputs go to nuts_trace_diag.nc / nuts_summary_diag.json.
Do NOT update the model registry or commit this as the Epic 17 champion.

Questions answered:
  1. Is beta_bullpen_2026_discount < 0 with 94% HDI excluding zero?
     → Confirms bullpen beta drift as the specific mechanism driving PPM overshoot.
  2. What is PPM on May-2026 with the discount applied?
     → Theoretical ceiling: if bullpen signal were correctly calibrated, would the
        kill criterion (≤ 8.81) pass?

Usage (HAND-OFF — expect ~10 min on M-series CPU):
    uv run python betting_ml/scripts/audit/nuts_bullpen_discount_diagnostic.py

Outputs:
    betting_ml/models/bayesian/nuts_trace_diag.nc
    betting_ml/models/bayesian/nuts_summary_diag.json
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
_TRACE_PATH   = _BAYESIAN_DIR / "nuts_trace_diag.nc"
_SUMMARY_PATH = _BAYESIAN_DIR / "nuts_summary_diag.json"

_N_DRAWS       = 4000
_N_TUNE        = 2000
_N_CHAINS      = 4
_TARGET_ACCEPT = 0.9
_KILL_THRESHOLD = 8.81
_OOS_SEASON    = 2026
_CALIB_MONTHS  = [3, 4]
_OOS_MONTH     = 5
_MIN_CALIB_OBS = 200

from betting_ml.models.bayesian.run_scoring_nuts import _build_indices_with_2026
from betting_ml.models.bayesian.run_scoring_advi import (
    _load_oos_signals,
    _load_game_results,
    _expand_to_sides,
    _build_training_frame,
    _fit_and_apply_scalers,
    _TRAIN_SEASONS,
)


# ---------------------------------------------------------------------------
# Diagnostic model — production model + bullpen 2026 interaction term
# ---------------------------------------------------------------------------

def build_model_with_discount(df_train: pd.DataFrame, coords: dict):
    """
    PyMC model identical to production build_model, plus:
        beta_bullpen_2026_discount ~ Normal(0, 0.5)
    Effective bullpen coeff for row i:
        beta_bullpen * opp_bullpen_mu_z[i] * (1 + beta_bullpen_2026_discount * is_2026[i])
    is_2026[i] = 1 for March-April 2026 calibration rows; 0 for 2022-2025.
    """
    import pymc as pm

    n_teams   = len(coords["team"])
    n_seasons = len(coords["season"])

    is_2026 = df_train["season"].eq(_OOS_SEASON).astype(float).values
    bullpen_z_vals = df_train["opp_bullpen_mu_z"].values

    n_2026_train = int(is_2026.sum())
    log.info("  is_2026 indicator: %d of %d training rows are 2026 calibration",
             n_2026_train, len(df_train))

    with pm.Model(coords=coords) as model:

        # ── Hyperpriors ──────────────────────────────────────────────────────
        mu_log_league = pm.Normal("mu_log_league", mu=np.log(4.5), sigma=0.2)
        sigma_offense = pm.HalfNormal("sigma_offense", sigma=0.25)
        sigma_defense = pm.HalfNormal("sigma_defense", sigma=0.25)
        sigma_season  = pm.HalfNormal("sigma_season",  sigma=0.15)

        # ── Group-level effects ──────────────────────────────────────────────
        alpha_offense = pm.Normal("alpha_offense", mu=0, sigma=sigma_offense, dims="team")
        alpha_defense = pm.Normal("alpha_defense", mu=0, sigma=sigma_defense, dims="team")
        delta_season  = pm.Normal("delta_season",  mu=0, sigma=sigma_season,  dims="season")

        # ── Signal coefficients ──────────────────────────────────────────────
        beta_run_env = pm.Normal("beta_run_env", mu=0.0, sigma=0.3)
        beta_offense = pm.Normal("beta_offense", mu=0.2, sigma=0.3)
        beta_bullpen = pm.Normal("beta_bullpen", mu=0.1, sigma=0.3)
        beta_starter = pm.Normal("beta_starter", mu=0.1, sigma=0.3)

        # ── 2026 bullpen discount — diagnostic term ───────────────────────────
        # A negative posterior mean means the model prefers a weaker bullpen
        # signal for 2026 rows than for 2022-2025 rows.
        # sigma=0.5 allows discounts up to ±1.0 at 2σ (complete on/off of signal).
        beta_bullpen_2026_discount = pm.Normal(
            "beta_bullpen_2026_discount", mu=0.0, sigma=0.5
        )

        bat_idx = df_train["batting_team_idx"].values
        pit_idx = df_train["pitching_team_idx"].values
        sea_idx = df_train["season_idx"].values

        # Effective bullpen contribution — scalar for 2022-2025, discounted for 2026
        bullpen_contrib = (
            beta_bullpen * bullpen_z_vals * (1.0 + beta_bullpen_2026_discount * is_2026)
        )

        log_mu_side = (
            mu_log_league
            + alpha_offense[bat_idx]
            + alpha_defense[pit_idx]
            + delta_season[sea_idx]
            + beta_run_env * df_train["run_env_z"].values
            + beta_offense * df_train["offense_mu_z"].values
            + bullpen_contrib
            + beta_starter * df_train["opp_starter_mu_z"].values
        )
        mu_side = pm.Deterministic("mu_side", pm.math.exp(log_mu_side))

        alpha_nb = pm.HalfNormal("alpha_nb", sigma=5.0)

        _runs = pm.NegativeBinomial(
            "runs",
            mu=mu_side,
            alpha=alpha_nb,
            observed=df_train["runs_scored"].values,
            dims="obs",
        )

    return model


# ---------------------------------------------------------------------------
# Discount kill criterion — May 2026 PPM with is_2026=1 for all rows
# ---------------------------------------------------------------------------

def run_discount_kill_criterion(trace, full_df: pd.DataFrame, coords: dict) -> dict:
    """
    Posterior predictive mean on May-2026 OOS with the bullpen discount applied.
    All May-2026 rows have is_2026=1 → effective beta = beta_bullpen * (1 + discount).
    """
    may_mask = (
        (full_df["season"] == _OOS_SEASON) &
        (full_df["game_date"].dt.month == _OOS_MONTH)
    )
    may_df = full_df[may_mask].copy().reset_index(drop=True)

    if len(may_df) == 0:
        log.error("No May-2026 OOS games found.")
        return {"error": "no May-2026 games"}

    log.info("\nMay-2026 OOS: %d rows, %d unique games", len(may_df), may_df["game_pk"].nunique())

    post      = trace.posterior
    n_samples = post.dims["chain"] * post.dims["draw"]

    mu_log_league    = post["mu_log_league"].values.reshape(n_samples)
    alpha_offense    = post["alpha_offense"].values.reshape(n_samples, len(coords["team"]))
    alpha_defense    = post["alpha_defense"].values.reshape(n_samples, len(coords["team"]))
    delta_season     = post["delta_season"].values.reshape(n_samples, len(coords["season"]))
    beta_run_env     = post["beta_run_env"].values.reshape(n_samples)
    beta_offense_v   = post["beta_offense"].values.reshape(n_samples)
    beta_bullpen     = post["beta_bullpen"].values.reshape(n_samples)
    beta_starter     = post["beta_starter"].values.reshape(n_samples)
    beta_discount    = post["beta_bullpen_2026_discount"].values.reshape(n_samples)
    alpha_nb         = post["alpha_nb"].values.reshape(n_samples)

    bat_idx   = may_df["batting_team_idx"].values
    pit_idx   = may_df["pitching_team_idx"].values
    sea_idx   = may_df["season_idx"].values
    run_env_z = may_df["run_env_z"].values
    offense_z = may_df["offense_mu_z"].values
    bullpen_z = may_df["opp_bullpen_mu_z"].values
    starter_z = may_df["opp_starter_mu_z"].values

    log.info("Computing posterior predictive for %d OOS rows × %d draws...", len(may_df), n_samples)

    # All May-2026 rows have is_2026=1 → effective bullpen = beta_bullpen * (1 + discount)
    effective_bullpen = beta_bullpen[:, None] * bullpen_z[None, :] * (1.0 + beta_discount[:, None])

    log_mu = (
        mu_log_league[:, None]
        + alpha_offense[:, bat_idx]
        + alpha_defense[:, pit_idx]
        + delta_season[:, sea_idx]
        + beta_run_env[:, None] * run_env_z[None, :]
        + beta_offense_v[:, None] * offense_z[None, :]
        + effective_bullpen
        + beta_starter[:, None] * starter_z[None, :]
    )
    mu_oos = np.exp(log_mu)

    rng = np.random.default_rng(42)
    ppc_runs = np.zeros_like(mu_oos, dtype=float)
    for d in range(n_samples):
        a    = float(alpha_nb[d])
        p_nb = a / (a + mu_oos[d])
        ppc_runs[d] = rng.negative_binomial(a, p_nb).astype(float)

    game_pks = may_df["game_pk"].unique()
    home_sel, away_sel, actual_totals = [], [], []
    for gk in game_pks:
        rows  = may_df[may_df["game_pk"] == gk]
        h_row = rows[rows["side"] == "home"]
        a_row = rows[rows["side"] == "away"]
        if len(h_row) == 0 or len(a_row) == 0:
            continue
        home_sel.append(h_row.index[0])
        away_sel.append(a_row.index[0])
        actual_totals.append(
            float(h_row["runs_scored"].values[0]) + float(a_row["runs_scored"].values[0])
        )

    home_sel     = np.array(home_sel)
    away_sel     = np.array(away_sel)
    actual_totals = np.array(actual_totals)

    total_ppc   = ppc_runs[:, home_sel] + ppc_runs[:, away_sel]
    ppm         = float(total_ppc.mean())
    actual_mean = float(actual_totals.mean())
    bias        = ppm - actual_mean
    passed      = ppm <= _KILL_THRESHOLD

    log.info("\n========= DISCOUNT DIAGNOSTIC KILL CRITERION CHECK =========")
    log.info("  May-2026 games evaluated:           %d", len(actual_totals))
    log.info("  PPM (with bullpen discount):        %.4f", ppm)
    log.info("  Actual May-2026 mean total_runs:    %.4f", actual_mean)
    log.info("  Bias (PPM - actual):                %+.4f", bias)
    log.info("  Kill criterion threshold:           %.2f", _KILL_THRESHOLD)
    log.info("  Result: %s",
             "PASS → bullpen recalibration is sufficient fix" if passed else
             "FAIL → bullpen drift is not the only problem")
    log.info("============================================================")

    # ── Discount posterior ──────────────────────────────────────────────────
    disc_mean = float(beta_discount.mean())
    disc_std  = float(beta_discount.std())
    disc_p3   = float(np.percentile(beta_discount, 3))
    disc_p97  = float(np.percentile(beta_discount, 97))
    hdi_neg   = disc_p97 < 0   # entire HDI on negative side → confirmed mechanism

    log.info("\n  beta_bullpen_2026_discount posterior:")
    log.info("    mean=%.4f  std=%.4f  94%% HDI=[%.4f, %.4f]",
             disc_mean, disc_std, disc_p3, disc_p97)
    log.info("    HDI entirely negative: %s", "YES — bullpen drift confirmed" if hdi_neg else
             "NO — discount not reliably negative from March-April calibration data")

    # Effective beta for 2026
    base_bullpen = float(post["beta_bullpen"].values.mean())
    eff_beta_2026 = base_bullpen * (1 + disc_mean)
    log.info("    Effective beta_bullpen for 2026: %.4f  (base=%.4f × (1%+.4f))",
             eff_beta_2026, base_bullpen, disc_mean)

    # delta_2026 in this run
    n_seasons_coords = len(coords["season"])
    delta_2026_vals = delta_season[:, n_seasons_coords - 1]
    d26_mean = float(delta_2026_vals.mean())
    d26_p3   = float(np.percentile(delta_2026_vals, 3))
    d26_p97  = float(np.percentile(delta_2026_vals, 97))
    log.info("    delta_2026 (joint posterior): mean=%.4f  94%% HDI=[%.4f, %.4f]",
             d26_mean, d26_p3, d26_p97)

    return {
        "n_games": len(actual_totals),
        "ppm": ppm,
        "actual_mean": actual_mean,
        "bias": bias,
        "threshold": _KILL_THRESHOLD,
        "passed": passed,
        "beta_bullpen_2026_discount_mean": disc_mean,
        "beta_bullpen_2026_discount_p3": disc_p3,
        "beta_bullpen_2026_discount_p97": disc_p97,
        "hdi_entirely_negative": hdi_neg,
        "effective_beta_bullpen_2026": eff_beta_2026,
        "delta_2026_mean": d26_mean,
    }


# ---------------------------------------------------------------------------
# Convergence check (scalar params + discount)
# ---------------------------------------------------------------------------

def check_diagnostics(trace) -> dict:
    import arviz as az

    divergences = int(trace.sample_stats["diverging"].values.sum())
    log.info("Divergences: %d (threshold: < %d)", divergences,
             int(_N_DRAWS * _N_CHAINS * 0.01))

    summary = az.summary(trace, var_names=[
        "mu_log_league", "sigma_offense", "sigma_defense", "sigma_season",
        "beta_run_env", "beta_offense", "beta_bullpen", "beta_starter",
        "beta_bullpen_2026_discount", "alpha_nb",
    ])
    log.info("\nParameter summary:\n%s", summary.to_string())

    rhat_cols = [c for c in summary.columns if "r_hat" in c.lower()]
    max_rhat  = float(np.nanmax(summary[rhat_cols[0]].values)) if rhat_cols else float("nan")
    ess_cols  = [c for c in summary.columns if "ess_bulk" in c.lower()]
    min_ess   = float(np.nanmin(summary[ess_cols[0]].values)) if ess_cols else float("nan")

    log.info("Max R-hat: %.4f (threshold: < 1.01)", max_rhat)
    log.info("Min ESS:   %.0f (threshold: > 400)", min_ess)

    return {
        "divergences": divergences,
        "max_rhat": max_rhat,
        "min_ess_bulk": min_ess,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("Epic 17 Story 17.1b — NUTS Bullpen Discount Diagnostic")
    log.info("beta_bullpen_2026_discount ~ Normal(0, 0.5)")
    log.info("NOT a production model. Diagnostic only.")
    log.info("=" * 60)

    # ── Data pipeline (identical to run_scoring_nuts.py v2) ─────────────────
    log.info("\n[1/5] Loading OOS signals and game results...")
    all_seasons = _TRAIN_SEASONS + [_OOS_SEASON]
    signals = _load_oos_signals()
    games   = _load_game_results(all_seasons)
    sides   = _expand_to_sides(games)
    full_df = _build_training_frame(signals, sides)

    log.info("\n[2/5] Splitting 2026 into calibration (Mar+Apr) and OOS (May)...")
    calib_mask      = (full_df["season"] == _OOS_SEASON) & (full_df["game_date"].dt.month.isin(_CALIB_MONTHS))
    may_mask        = (full_df["season"] == _OOS_SEASON) & (full_df["game_date"].dt.month == _OOS_MONTH)
    base_train_mask = full_df["season"].isin(_TRAIN_SEASONS)

    n_calib_obs = int(calib_mask.sum())
    n_may_obs   = int(may_mask.sum())
    log.info("  2026 calibration (Mar+Apr): %d rows, %d games",
             n_calib_obs, int(full_df.loc[calib_mask, "game_pk"].nunique()))
    log.info("  2026 OOS (May):             %d rows, %d games",
             n_may_obs, int(full_df.loc[may_mask, "game_pk"].nunique()))

    if n_calib_obs < _MIN_CALIB_OBS:
        log.warning("Only %d calibration obs — discount estimate may be sparse.", n_calib_obs)
    if n_may_obs == 0:
        log.error("No May-2026 OOS games — cannot compute kill criterion.")
        sys.exit(1)

    log.info("\n[3/5] Building indices and z-scoring signals...")
    base_train_df = full_df[base_train_mask].copy()
    full_df, team_to_idx, season_to_idx, coords = _build_indices_with_2026(base_train_df, full_df)

    base_train_mask = full_df["season"].isin(_TRAIN_SEASONS)
    calib_mask_v2   = (full_df["season"] == _OOS_SEASON) & (full_df["game_date"].dt.month.isin(_CALIB_MONTHS))
    train_mask_ext  = base_train_mask | calib_mask_v2

    train_for_scalers = full_df[base_train_mask].copy().reset_index(drop=True)
    train_for_scalers, full_df, _ = _fit_and_apply_scalers(train_for_scalers, full_df)

    train_df = full_df[train_mask_ext].copy().reset_index(drop=True)
    coords["obs"] = list(range(len(train_df)))

    n_2026_calib_train = int((train_df["season"] == _OOS_SEASON).sum())
    log.info("  Training rows: %d (2022-2025) + %d (2026 calib) = %d total",
             int(base_train_mask.sum()), n_2026_calib_train,
             len(train_df))
    log.info("  Teams: %d  |  Seasons: %d (2022-2025 + 2026)",
             len(team_to_idx), len(coords["season"]))

    # ── Build diagnostic model + run NUTS ────────────────────────────────────
    log.info("\n[4/5] Building diagnostic model and running NUTS...")
    import pymc as pm
    import arviz as az

    model = build_model_with_discount(train_df, coords)

    log.info("Starting NUTS: %d chains × %d draws + %d tune, target_accept=%.2f",
             _N_CHAINS, _N_DRAWS, _N_TUNE, _TARGET_ACCEPT)
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

    log.info("\nSaving trace → %s", _TRACE_PATH)
    trace.to_netcdf(str(_TRACE_PATH), engine="h5netcdf")
    log.info("Trace saved.")

    # ── Diagnostics ──────────────────────────────────────────────────────────
    diag = check_diagnostics(trace)

    # Coefficient check
    log.info("\nCoefficient posteriors (94%% HDI):")
    for param in ["beta_run_env", "beta_offense", "beta_bullpen", "beta_starter",
                  "beta_bullpen_2026_discount"]:
        vals = trace.posterior[param].values.ravel()
        log.info("  %-30s  mean=%+.4f  HDI=[%+.4f, %+.4f]",
                 param, float(vals.mean()),
                 float(np.percentile(vals, 3)), float(np.percentile(vals, 97)))

    # ── Kill criterion with discount ─────────────────────────────────────────
    log.info("\n[5/5] Running kill criterion on May-2026 OOS (with discount)...")
    kill = run_discount_kill_criterion(trace, full_df, coords)

    # ── Save summary ─────────────────────────────────────────────────────────
    summary = {
        "model": "diagnostic — beta_bullpen_2026_discount added",
        "diagnostics": diag,
        "kill_criterion": kill,
    }
    with open(_SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    log.info("Summary saved → %s", _SUMMARY_PATH)

    log.info("\n" + "=" * 60)
    log.info("DISCOUNT DIAGNOSTIC SUMMARY")
    log.info("=" * 60)
    log.info("Divergences:                  %d", diag["divergences"])
    log.info("Max R-hat:                    %.4f", diag["max_rhat"])
    log.info("Min ESS:                      %.0f", diag["min_ess_bulk"])
    disc_mean = kill.get("beta_bullpen_2026_discount_mean", float("nan"))
    disc_p3   = kill.get("beta_bullpen_2026_discount_p3", float("nan"))
    disc_p97  = kill.get("beta_bullpen_2026_discount_p97", float("nan"))
    log.info("beta_bullpen_2026_discount:   mean=%+.4f  HDI=[%+.4f, %+.4f]",
             disc_mean, disc_p3, disc_p97)
    log.info("  HDI entirely negative:      %s", kill.get("hdi_entirely_negative", "?"))
    log.info("  Effective beta_bullpen 2026: %.4f", kill.get("effective_beta_bullpen_2026", float("nan")))
    log.info("Kill criterion (with discount): PPM=%.4f  threshold=%.2f  %s",
             kill.get("ppm", float("nan")), _KILL_THRESHOLD,
             "PASS" if kill.get("passed") else "FAIL")
    log.info("=" * 60)

    if kill.get("passed"):
        log.info("\nKill criterion PASSES with discount.")
        log.info("Interpretation: bullpen recalibration is sufficient.")
        log.info("Next step: implement OOD gate on bullpen_z > 1.5σ (Epic 19).")
        log.info("Document as Story 17.1b in implementation_guide.md.")
    else:
        log.warning("\nKill criterion FAILS even with discount.")
        log.warning("Bullpen drift is not the only problem.")
        log.warning("Sub-model retrain is needed before Epic 17 can proceed.")
        log.warning("Gate Epic 17 on bullpen retrain.")


if __name__ == "__main__":
    main()
