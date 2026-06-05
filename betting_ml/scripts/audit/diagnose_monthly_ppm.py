"""
diagnose_monthly_ppm.py — Epic 17 monthly PPM breakdown diagnostic

Computes posterior predictive mean (PPM) for each month of 2026 using the
v2 NUTS trace (nuts_trace.nc), simulating v1 model behavior:
    "2026 borrows delta_2025" → uses delta_season[:, 3] for all 2026 rows.

The v2 trace is used for the posterior samples; only the season-index lookup
is changed (index 4 → index 3) to reproduce the v1 mapping.

Questions answered:
  - Is the kill criterion failure (PPM > 8.81) specific to May-2026, or is it
    present across all 2026 months?
  - If April and June pass but May fails, the OOD gate approach (Epic 19) is
    more defensible — the model works in normal regimes and the gate prevents
    betting in the specific environment where bullpen signal drifts.

Usage (HAND-OFF — expect ~5 min on M-series CPU):
    uv run python betting_ml/scripts/audit/diagnose_monthly_ppm.py

Outputs: console only (no files written)
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_BAYESIAN_DIR  = _PROJECT_ROOT / "betting_ml" / "models" / "bayesian"
_TRACE_PATH    = _BAYESIAN_DIR / "nuts_trace.nc"
_SCALER_PATH   = _BAYESIAN_DIR / "signal_scalers.joblib"
_OOS_SEASON    = 2026
_KILL_THRESHOLD = 8.81
_TRAIN_SEASONS  = [2022, 2023, 2024, 2025]
_DELTA_2025_IDX = 3   # index of 2025 in v2 season coords [2022, 2023, 2024, 2025, 2026]
_MIN_GAMES_FOR_PPM = 10

from betting_ml.models.bayesian.run_scoring_nuts import _build_indices_with_2026
from betting_ml.models.bayesian.run_scoring_advi import (
    _load_oos_signals,
    _load_game_results,
    _expand_to_sides,
    _build_training_frame,
)

MONTH_NAMES = {3: "March", 4: "April", 5: "May", 6: "June", 7: "July"}


# ---------------------------------------------------------------------------
# PPM for a subset of rows — v1-like (use delta_2025 for all 2026 rows)
# ---------------------------------------------------------------------------

def compute_monthly_ppm(
    month_df: pd.DataFrame,
    post: object,
    coords: dict,
    n_samples: int,
    month_name: str,
) -> dict:
    """
    Posterior predictive mean using v1 mapping: delta_2025 (index 3) for
    all 2026 rows, regardless of the season_idx in the data.
    """
    if len(month_df) == 0:
        return {"month": month_name, "n_games": 0, "status": "no data"}

    # Extract posterior arrays
    mu_log_league = post["mu_log_league"].values.reshape(n_samples)
    alpha_offense = post["alpha_offense"].values.reshape(n_samples, len(coords["team"]))
    alpha_defense = post["alpha_defense"].values.reshape(n_samples, len(coords["team"]))
    delta_season  = post["delta_season"].values.reshape(n_samples, len(coords["season"]))
    beta_run_env  = post["beta_run_env"].values.reshape(n_samples)
    beta_offense  = post["beta_offense"].values.reshape(n_samples)
    beta_bullpen  = post["beta_bullpen"].values.reshape(n_samples)
    beta_starter  = post["beta_starter"].values.reshape(n_samples)
    alpha_nb      = post["alpha_nb"].values.reshape(n_samples)

    bat_idx   = month_df["batting_team_idx"].values
    pit_idx   = month_df["pitching_team_idx"].values
    run_env_z = month_df["run_env_z"].values
    offense_z = month_df["offense_mu_z"].values
    bullpen_z = month_df["opp_bullpen_mu_z"].values
    starter_z = month_df["opp_starter_mu_z"].values

    # V1 behavior: all 2026 rows use delta_2025 (index 3)
    delta_2026_v1 = delta_season[:, _DELTA_2025_IDX]   # (n_samples,)

    log_mu = (
        mu_log_league[:, None]
        + alpha_offense[:, bat_idx]
        + alpha_defense[:, pit_idx]
        + delta_2026_v1[:, None]                    # same for all rows in this month
        + beta_run_env[:, None] * run_env_z[None, :]
        + beta_offense[:, None] * offense_z[None, :]
        + beta_bullpen[:, None] * bullpen_z[None, :]
        + beta_starter[:, None] * starter_z[None, :]
    )
    mu_mat = np.exp(log_mu)   # (n_samples, n_rows)

    rng = np.random.default_rng(42)
    ppc_runs = np.zeros_like(mu_mat, dtype=float)
    for d in range(n_samples):
        a    = float(alpha_nb[d])
        p_nb = a / (a + mu_mat[d])
        ppc_runs[d] = rng.negative_binomial(a, p_nb).astype(float)

    # Pair home/away by game_pk
    game_pks = month_df["game_pk"].unique()
    home_sel, away_sel, actual_totals = [], [], []
    for gk in game_pks:
        rows  = month_df[month_df["game_pk"] == gk]
        h_row = rows[rows["side"] == "home"]
        a_row = rows[rows["side"] == "away"]
        if len(h_row) == 0 or len(a_row) == 0:
            continue
        home_sel.append(h_row.index[0])
        away_sel.append(a_row.index[0])
        actual_totals.append(
            float(h_row["runs_scored"].values[0]) + float(a_row["runs_scored"].values[0])
        )

    n_games = len(actual_totals)
    if n_games < _MIN_GAMES_FOR_PPM:
        return {"month": month_name, "n_games": n_games, "status": "too few games"}

    home_sel     = np.array(home_sel)
    away_sel     = np.array(away_sel)
    actual_totals = np.array(actual_totals)

    total_ppc   = ppc_runs[:, home_sel] + ppc_runs[:, away_sel]
    ppm         = float(total_ppc.mean())
    actual_mean = float(actual_totals.mean())
    bias        = ppm - actual_mean
    passed      = ppm <= _KILL_THRESHOLD

    return {
        "month": month_name,
        "n_games": n_games,
        "ppm": ppm,
        "actual_mean": actual_mean,
        "bias": bias,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=" * 60)
    log.info("Epic 17 — Monthly PPM breakdown (v1-like: 2026 → delta_2025)")
    log.info("=" * 60)

    # ── Data pipeline ────────────────────────────────────────────────────────
    log.info("\n[1/4] Loading OOS signals and 2026 game results...")
    all_seasons = _TRAIN_SEASONS + [_OOS_SEASON]
    signals = _load_oos_signals()
    games   = _load_game_results(all_seasons)
    sides   = _expand_to_sides(games)
    full_df = _build_training_frame(signals, sides)

    # Filter to 2026 only for PPM analysis
    df_2026 = full_df[full_df["season"] == _OOS_SEASON].copy()
    log.info("  2026 rows: %d  |  games: %d  |  months present: %s",
             len(df_2026), df_2026["game_pk"].nunique(),
             sorted(df_2026["game_date"].dt.month.unique().tolist()))

    # ── Build indices (must match v2 trace) ──────────────────────────────────
    log.info("\n[2/4] Building team/season indices matching v2 trace...")
    # Derive base team list from 2022-2025 (same logic as run_scoring_nuts.py)
    base_train_df = full_df[full_df["season"].isin(_TRAIN_SEASONS)].copy()
    full_df, team_to_idx, season_to_idx, coords = _build_indices_with_2026(base_train_df, full_df)
    df_2026 = full_df[full_df["season"] == _OOS_SEASON].copy()

    # ── Apply v2 scalers ─────────────────────────────────────────────────────
    log.info("[3/4] Applying v2 signal scalers (fitted on 2022-2025)...")
    if not _SCALER_PATH.exists():
        log.error("signal_scalers.joblib not found at %s", _SCALER_PATH)
        log.error("Run run_scoring_nuts.py first to generate scalers.")
        sys.exit(1)

    scalers: dict = joblib.load(_SCALER_PATH)
    signal_map = {
        "run_env_mu":   "run_env_z",
        "pred_runs_mu": "offense_mu_z",
        "opp_bullpen_mu": "opp_bullpen_mu_z",
        "opp_starter_mu": "opp_starter_mu_z",
    }
    for raw, z in signal_map.items():
        if raw in scalers and raw in df_2026.columns:
            df_2026[z] = scalers[raw].transform(df_2026[raw].values.reshape(-1, 1)).ravel()
        else:
            log.error("Missing signal column or scaler: %s / %s", raw, z)
            sys.exit(1)

    log.info("  Z-scores applied. Signal means for 2026:")
    for raw, z in signal_map.items():
        log.info("    %-22s  mean=%+.4f", z, float(df_2026[z].mean()))

    # ── Load v2 trace ─────────────────────────────────────────────────────────
    log.info("\n[4/4] Loading v2 NUTS trace and computing monthly PPM...")
    if not _TRACE_PATH.exists():
        log.error("NUTS trace not found at %s", _TRACE_PATH)
        sys.exit(1)

    import arviz as az
    log.info("  Loading trace from %s...", _TRACE_PATH)
    trace = az.from_netcdf(str(_TRACE_PATH))
    post  = trace.posterior

    n_chains  = post.dims["chain"]
    n_draws   = post.dims["draw"]
    n_samples = n_chains * n_draws
    log.info("  Trace loaded: %d chains × %d draws = %d samples", n_chains, n_draws, n_samples)

    # Confirm coord structure matches expectations (5 seasons)
    trace_seasons = list(post.coords["season"].values) if "season" in post.coords else []
    log.info("  Trace season coords: %s", trace_seasons)
    if len(trace_seasons) != 5:
        log.warning("Expected 5 seasons in trace; got %d. Delta index may be wrong.", len(trace_seasons))

    # ── Compute PPM per 2026 month ────────────────────────────────────────────
    months_of_interest = [3, 4, 5, 6, 7]
    results = []

    for month_num in months_of_interest:
        mname = MONTH_NAMES.get(month_num, f"Month {month_num}")
        month_df = df_2026[df_2026["game_date"].dt.month == month_num].copy().reset_index(drop=True)

        if len(month_df) == 0:
            log.info("  %s: no data — skipping", mname)
            results.append({"month": mname, "n_games": 0, "status": "no data"})
            continue

        n_games = month_df["game_pk"].nunique()
        log.info("  %s: %d rows, %d games — computing PPM...", mname, len(month_df), n_games)
        r = compute_monthly_ppm(month_df, post, coords, n_samples, mname)
        results.append(r)

    # ── Summary table ─────────────────────────────────────────────────────────
    log.info("\n" + "=" * 65)
    log.info("MONTHLY PPM BREAKDOWN — 2026 (v1-like: 2026 → delta_2025)")
    log.info("=" * 65)
    log.info("  %-8s  %-8s  %-8s  %-8s  %-8s  %s",
             "Month", "Games", "PPM", "Actual", "Bias", "vs 8.81")
    log.info("  " + "-" * 63)

    for r in results:
        if r.get("status") in ("no data", "too few games"):
            log.info("  %-8s  %-8s  — (n=%d: %s)",
                     r["month"], "", r.get("n_games", 0), r["status"])
            continue
        gate = "PASS" if r["passed"] else "FAIL"
        log.info("  %-8s  %-8d  %-8.4f  %-8.4f  %-+8.4f  %s",
                 r["month"], r["n_games"], r["ppm"], r["actual_mean"], r["bias"], gate)

    log.info("=" * 65)

    # Interpretation
    fail_months  = [r["month"] for r in results if r.get("status") == "FAIL"]
    pass_months  = [r["month"] for r in results if r.get("status") == "PASS"]
    skip_months  = [r["month"] for r in results if r.get("status") in ("no data", "too few games")]

    log.info("\nInterpretation:")
    if fail_months and pass_months:
        log.info("  PASS months:  %s", pass_months)
        log.info("  FAIL months:  %s", fail_months)
        log.info("  → Failure is MONTH-SPECIFIC, not a uniform 2026 problem.")
        log.info("  → OOD gate approach (Epic 19) is more defensible:")
        log.info("    the model works in %s; gate prevents betting in %s.", pass_months, fail_months)
    elif not fail_months:
        log.info("  ALL months PASS → v1 mapping works across 2026.")
        log.info("  The May kill criterion failure in v2 was caused by delta_2026 shrinking to 0")
        log.info("  (Mar-Apr calibration teaching model 2026 is normal).")
    else:
        log.info("  ALL populated months FAIL → bias is uniform across 2026.")
        log.info("  OOD gate is not sufficient. Full sub-model retrain needed.")

    if skip_months:
        log.info("  Skipped (insufficient data): %s", skip_months)

    log.info("\nNote: Uses v2 trace posteriors with v1 season mapping for 2026.")
    log.info("Delta index %d (2025) applied to all 2026 rows.", _DELTA_2025_IDX)


if __name__ == "__main__":
    main()
