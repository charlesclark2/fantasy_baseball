"""
diagnose_season_deltas.py — Read delta_season posteriors from NUTS trace.

Reports:
  1. Posterior mean/std/HDI for each training season's delta
  2. Estimated PPM change if 2026 uses mean(all training deltas) instead of delta_2025
  3. Team effect contribution breakdown for May-2026 games

Local only (no Snowflake). Runtime < 10 seconds (trace load).

Usage:
    uv run python betting_ml/scripts/audit/diagnose_season_deltas.py
"""

from pathlib import Path
import numpy as np
import pandas as pd
import arviz as az

_REPO = Path(__file__).parents[3]
_TRACE_PATH = _REPO / "betting_ml" / "models" / "bayesian" / "nuts_trace.nc"
_OOS_DIR    = _REPO / "betting_ml" / "models" / "layer3" / "oos_signals"

_MU_LOG_LEAGUE  = 1.4701
_DELTA_2025     = -0.0773   # current mapping for 2026
_BASELINE_SIDE  = np.exp(_MU_LOG_LEAGUE)
_TRAIN_SEASONS  = [2022, 2023, 2024, 2025]

# NUTS posterior means for covariates
_BETAS = {
    "run_env_z":       0.0511,
    "offense_mu_z":    0.0321,
    "opp_bullpen_mu_z": 0.1912,
    "opp_starter_mu_z": 0.0427,
}


def load_trace():
    print(f"Loading trace from {_TRACE_PATH} ...")
    return az.from_netcdf(str(_TRACE_PATH))


def report_season_deltas(trace):
    post = trace.posterior
    delta_season = post["delta_season"].values  # (chains, draws, n_seasons)
    n_chains, n_draws, n_seasons = delta_season.shape
    flat = delta_season.reshape(n_chains * n_draws, n_seasons)  # (16000, 4)

    # Seasons are indexed 0..3 → 2022..2025 in order
    print("\n========= delta_season POSTERIOR SUMMARY =========")
    print(f"  {'Season':<8}  {'Mean':>8}  {'Std':>8}  {'p5':>8}  {'p95':>8}  "
          f"{'HDI-3%':>8}  {'HDI-97%':>8}")
    delta_means = []
    for i, season in enumerate(["2022", "2023", "2024", "2025"]):
        vals = flat[:, i]
        mean_ = float(vals.mean())
        std_  = float(vals.std())
        p5    = float(np.percentile(vals, 5))
        p95   = float(np.percentile(vals, 95))
        p3    = float(np.percentile(vals, 3))
        p97   = float(np.percentile(vals, 97))
        delta_means.append(mean_)
        print(f"  {season:<8}  {mean_:>8.4f}  {std_:>8.4f}  {p5:>8.4f}  {p95:>8.4f}  "
              f"{p3:>8.4f}  {p97:>8.4f}")

    mean_all_seasons = float(np.mean(delta_means))
    print(f"\n  Mean of all training season deltas:  {mean_all_seasons:.4f}")
    print(f"  Currently using (2025 delta):         {_DELTA_2025:.4f}")
    print(f"  Difference (mean - current):          {mean_all_seasons - _DELTA_2025:+.4f}")

    # Estimate PPM change if 2026 maps to mean(all) instead of 2025
    baseline_current = np.exp(_MU_LOG_LEAGUE + _DELTA_2025)
    baseline_mean    = np.exp(_MU_LOG_LEAGUE + mean_all_seasons)
    ppm_change = (baseline_mean - baseline_current) * 2
    print(f"\n  Switching 2026 mapping: delta_2025 → mean(all seasons)")
    print(f"    Baseline current:   {baseline_current * 2:.4f} total runs")
    print(f"    Baseline mean:      {baseline_mean * 2:.4f} total runs")
    print(f"    Estimated PPM Δ:    {ppm_change:+.4f} total runs")
    print(f"    Projected NUTS PPM: {8.8607 + ppm_change:.4f}  (threshold: 8.81)")

    return flat, delta_means, mean_all_seasons


def report_team_effects(trace):
    post = trace.posterior
    alpha_offense = post["alpha_offense"].values  # (chains, draws, n_teams)
    alpha_defense = post["alpha_defense"].values

    n_chains, n_draws, n_teams = alpha_offense.shape
    flat_off = alpha_offense.reshape(n_chains * n_draws, n_teams)
    flat_def = alpha_defense.reshape(n_chains * n_draws, n_teams)

    # Posterior means per team
    off_means = flat_off.mean(axis=0)  # (n_teams,)
    def_means = flat_def.mean(axis=0)

    # Coords: get team names
    if "team" in trace.posterior.coords:
        teams = list(trace.posterior.coords["team"].values)
    else:
        teams = [f"team_{i}" for i in range(n_teams)]

    team_df = pd.DataFrame({
        "team": teams,
        "alpha_offense_mean": off_means,
        "alpha_defense_mean": def_means,
    }).sort_values("alpha_offense_mean", ascending=False)

    print("\n========= TEAM EFFECTS — TOP 5 OFFENSE, BOTTOM 5 DEFENSE =========")
    print("  Top 5 offense (highest alpha_offense = most runs scored):")
    for _, row in team_df.head(5).iterrows():
        print(f"    {row['team']:<25}  alpha_offense={row['alpha_offense_mean']:+.4f}  "
              f"alpha_defense={row['alpha_defense_mean']:+.4f}")
    print("  Top 5 weak defense (highest alpha_defense = most runs allowed vs them):")
    worst_def = team_df.sort_values("alpha_defense_mean", ascending=False)
    for _, row in worst_def.head(5).iterrows():
        print(f"    {row['team']:<25}  alpha_offense={row['alpha_offense_mean']:+.4f}  "
              f"alpha_defense={row['alpha_defense_mean']:+.4f}")

    print(f"\n  sigma_offense posterior mean: (from logged NUTS output: 0.053)")
    print(f"  sigma_defense posterior mean: (from logged NUTS output: 0.021)")

    # Overall magnitude
    exp_off_effect = np.exp(off_means).mean() - 1
    exp_def_effect = np.exp(def_means).mean() - 1
    print(f"\n  Average exp(alpha_offense) - 1: {exp_off_effect:+.4f}  "
          f"(net offense lift vs league baseline)")
    print(f"  Average exp(alpha_defense) - 1: {exp_def_effect:+.4f}  "
          f"(net defense drag vs league baseline)")

    return team_df


def check_mean_season_sensitivity(trace):
    """Monte-Carlo estimate: if all 2026 rows used mean(training deltas) instead of delta_2025,
    what would PPM be? Uses the actual posterior samples."""
    post = trace.posterior
    delta_season = post["delta_season"].values  # (chains, draws, n_seasons)
    n_chains, n_draws, n_seasons = delta_season.shape
    flat_delta = delta_season.reshape(n_chains * n_draws, n_seasons)  # (16000, 4)

    # For each posterior draw, mean of training seasons = mean across last dim
    mean_delta_per_draw = flat_delta.mean(axis=1)  # (16000,)
    delta_2025_per_draw = flat_delta[:, -1]        # (16000,)

    # Difference in log-space per draw
    log_diff = mean_delta_per_draw - delta_2025_per_draw  # (16000,)

    # Approximate PPM change: PPM_new ≈ PPM_old * mean(exp(log_diff))
    # (since the season delta enters as exp(delta) in the NegBin mean)
    mean_exp_diff = float(np.exp(log_diff).mean())
    ppm_new_estimate = 8.8607 * mean_exp_diff
    ppm_change_mc = ppm_new_estimate - 8.8607

    print("\n========= MONTE-CARLO PPM ESTIMATE: mean(training deltas) for 2026 =========")
    print(f"  mean(exp(delta_mean - delta_2025)): {mean_exp_diff:.6f}")
    print(f"  Estimated PPM change:               {ppm_change_mc:+.4f} total runs")
    print(f"  Projected PPM:                      {ppm_new_estimate:.4f}  (threshold: 8.81)")


def main():
    trace = load_trace()

    flat_delta, delta_means, mean_all = report_season_deltas(trace)
    report_team_effects(trace)
    check_mean_season_sensitivity(trace)

    print("\n========= SUMMARY OF FIX OPTIONS =========")
    print(f"  Current PPM:      8.8607  (threshold 8.81, over by +0.0507)")
    print(f"  Primary covariate driver: opp_bullpen_mu_z (+0.2882 z-shift, +0.456 total runs)")
    print(f"  Season mapping fix (mean vs 2025): see Projected PPM above")
    print()


if __name__ == "__main__":
    main()
