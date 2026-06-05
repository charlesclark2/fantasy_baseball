"""
diagnose_17_1_bias.py — Story 17.1 kill-criterion failure diagnostic

Computes per-month (March/April/May 2026) signal z-scores and expected PPM
using the NUTS posterior means. Identifies which signal and which month
drives the +0.70 bias observed in the kill criterion check.

Usage:
    uv run python betting_ml/scripts/audit/diagnose_17_1_bias.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

_OOS_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals"
_SCALERS_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "bayesian" / "signal_scalers.joblib"

# NUTS posterior means (from nuts_summary.json, Candidate A signals, 17.1 run 2026-06-05)
_BETAS = {
    "run_env":  0.04970,
    "offense":  0.03080,
    "bullpen":  0.17233,
    "starter":  0.04714,
}
_MU_LOG_LEAGUE  = 1.4726
_DELTA_2026     = -0.0024


def _load_signals() -> pd.DataFrame:
    offense = pd.read_parquet(_OOS_DIR / "oos_signals_offense.parquet")[
        ["game_pk", "side", "season", "pred_runs_mu"]
    ]
    bullpen = pd.read_parquet(_OOS_DIR / "oos_signals_bullpen.parquet")[
        ["game_pk", "side", "bullpen_mu"]
    ]
    starter = pd.read_parquet(_OOS_DIR / "oos_signals_starter.parquet")[
        ["game_pk", "side", "starter_suppression_mu"]
    ]
    run_env = pd.read_parquet(_OOS_DIR / "oos_signals_run_env.parquet")[
        ["game_pk", "run_env_mu"]
    ]
    df = (
        offense
        .merge(bullpen, on=["game_pk", "side"], how="inner")
        .merge(starter, on=["game_pk", "side"], how="inner")
        .merge(run_env, on="game_pk", how="inner")
    )
    # Build opp_bullpen_mu and opp_starter_mu cross-terms
    opp = bullpen.copy()
    opp_side = opp["side"].map({"home": "away", "away": "home"})
    opp = opp.assign(side=opp_side).rename(columns={
        "bullpen_mu": "opp_bullpen_mu",
    })
    opp2 = starter.copy()
    opp2_side = opp2["side"].map({"home": "away", "away": "home"})
    opp2 = opp2.assign(side=opp2_side).rename(columns={
        "starter_suppression_mu": "opp_starter_mu",
    })
    df = df.merge(opp[["game_pk", "side", "opp_bullpen_mu"]], on=["game_pk", "side"], how="inner")
    df = df.merge(opp2[["game_pk", "side", "opp_starter_mu"]], on=["game_pk", "side"], how="inner")
    return df


def _load_game_dates(game_pks: list[int]) -> pd.DataFrame:
    from betting_ml.utils.data_loader import get_snowflake_connection
    pk_list = ", ".join(str(p) for p in sorted(set(game_pks)))
    sql = f"""
        SELECT game_pk, game_date
        FROM baseball_data.betting.mart_game_results
        WHERE game_pk IN ({pk_list})
          AND game_year = 2026
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["month"] = df["game_date"].dt.month
    return df


def main() -> None:
    scalers = joblib.load(_SCALERS_PATH)

    print("=== Loaded NUTS signal scalers ===")
    for k, sc in scalers.items():
        print(f"  {k:25s}  mean={sc.mean_[0]:.4f}  scale={sc.scale_[0]:.4f}")

    print("\nLoading OOS signal parquets...")
    sig = _load_signals()
    print(f"  Total rows: {len(sig):,}")

    sig_2026 = sig[sig["season"] == 2026].copy()
    print(f"  2026 rows: {len(sig_2026):,}")

    print("\nQuerying 2026 game dates from Snowflake...")
    dates = _load_game_dates(sig_2026["game_pk"].unique().tolist())
    sig_2026 = sig_2026.merge(dates, on="game_pk", how="left")
    print(f"  Matched {sig_2026['month'].notna().sum():,} / {len(sig_2026):,} rows with dates")

    # Z-score using NUTS scalers
    sig_2026["z_run_env"]  = (sig_2026["run_env_mu"]    - scalers["run_env_mu"].mean_[0])   / scalers["run_env_mu"].scale_[0]
    sig_2026["z_offense"]  = (sig_2026["pred_runs_mu"]  - scalers["pred_runs_mu"].mean_[0]) / scalers["pred_runs_mu"].scale_[0]
    sig_2026["z_bullpen"]  = (sig_2026["opp_bullpen_mu"]- scalers["opp_bullpen_mu"].mean_[0]) / scalers["opp_bullpen_mu"].scale_[0]
    sig_2026["z_starter"]  = (sig_2026["opp_starter_mu"]- scalers["opp_starter_mu"].mean_[0]) / scalers["opp_starter_mu"].scale_[0]

    # Expected per-side log-mu contribution from each signal
    sig_2026["contrib_run_env"] = _BETAS["run_env"] * sig_2026["z_run_env"]
    sig_2026["contrib_offense"] = _BETAS["offense"] * sig_2026["z_offense"]
    sig_2026["contrib_bullpen"] = _BETAS["bullpen"] * sig_2026["z_bullpen"]
    sig_2026["contrib_starter"] = _BETAS["starter"] * sig_2026["z_starter"]
    sig_2026["total_contrib"]   = (
        sig_2026["contrib_run_env"] + sig_2026["contrib_offense"]
        + sig_2026["contrib_bullpen"] + sig_2026["contrib_starter"]
    )
    # Expected per-side mu
    sig_2026["pred_per_side"] = np.exp(
        _MU_LOG_LEAGUE + _DELTA_2026 + sig_2026["total_contrib"]
    )

    month_labels = {3: "March", 4: "April", 5: "May  "}
    print("\n=== 2026 Monthly Signal Z-scores and Expected PPM ===")
    print(f"{'Month':<8}  {'n_sides':>7}  {'z_run_env':>10}  {'z_offense':>10}  "
          f"{'z_bullpen':>10}  {'z_starter':>10}  {'pred_total':>11}  {'contrib_bull':>13}")
    print("-" * 100)
    for month in [3, 4, 5]:
        m = sig_2026[sig_2026["month"] == month]
        if len(m) == 0:
            continue
        label = month_labels.get(month, str(month))
        n = len(m)
        zr = m["z_run_env"].mean()
        zo = m["z_offense"].mean()
        zb = m["z_bullpen"].mean()
        zs = m["z_starter"].mean()
        pred_ppm = m["pred_per_side"].mean() * 2
        bull_contrib_total = m["contrib_bullpen"].mean() * 2
        print(f"{label:<8}  {n:>7,}  {zr:>10.4f}  {zo:>10.4f}  "
              f"{zb:>10.4f}  {zs:>10.4f}  {pred_ppm:>11.4f}  {bull_contrib_total:>13.4f}")

    # Overall 2026 stats
    print("-" * 100)
    all_2026 = sig_2026.dropna(subset=["month"])
    n = len(all_2026)
    print(f"{'2026 all':<8}  {n:>7,}  "
          f"{all_2026['z_run_env'].mean():>10.4f}  {all_2026['z_offense'].mean():>10.4f}  "
          f"{all_2026['z_bullpen'].mean():>10.4f}  {all_2026['z_starter'].mean():>10.4f}  "
          f"{all_2026['pred_per_side'].mean()*2:>11.4f}  "
          f"{all_2026['contrib_bullpen'].mean()*2:>13.4f}")

    # Training baseline (2022-2025)
    train = sig[sig["season"].isin([2022, 2023, 2024, 2025])].copy()
    train["z_run_env"]  = (train["run_env_mu"]    - scalers["run_env_mu"].mean_[0])   / scalers["run_env_mu"].scale_[0]
    train["z_offense"]  = (train["pred_runs_mu"]  - scalers["pred_runs_mu"].mean_[0]) / scalers["pred_runs_mu"].scale_[0]
    train["z_bullpen"]  = (train["opp_bullpen_mu"]- scalers["opp_bullpen_mu"].mean_[0]) / scalers["opp_bullpen_mu"].scale_[0]
    train["z_starter"]  = (train["opp_starter_mu"]- scalers["opp_starter_mu"].mean_[0]) / scalers["opp_starter_mu"].scale_[0]
    train["total_contrib"] = (
        _BETAS["run_env"] * train["z_run_env"]
        + _BETAS["offense"] * train["z_offense"]
        + _BETAS["bullpen"] * train["z_bullpen"]
        + _BETAS["starter"] * train["z_starter"]
    )
    train["pred_per_side"] = np.exp(_MU_LOG_LEAGUE + train["total_contrib"])
    print(f"\n{'Training':<8}  {len(train):>7,}  "
          f"{train['z_run_env'].mean():>10.4f}  {train['z_offense'].mean():>10.4f}  "
          f"{train['z_bullpen'].mean():>10.4f}  {train['z_starter'].mean():>10.4f}  "
          f"{train['pred_per_side'].mean()*2:>11.4f}  "
          f"{(_BETAS['bullpen']*train['z_bullpen'].mean()*2):>13.4f}")

    print("\n=== Signal Distribution: opp_bullpen_mu by month (2026) ===")
    for month in [3, 4, 5]:
        m = sig_2026[sig_2026["month"] == month]["opp_bullpen_mu"]
        if len(m) == 0:
            continue
        print(f"  {month_labels.get(month, str(month))}: n={len(m):5,}  "
              f"mean={m.mean():.4f}  std={m.std():.4f}  p25={m.quantile(0.25):.4f}  "
              f"p75={m.quantile(0.75):.4f}  max={m.max():.4f}")

    print("\n=== Bias decomposition for May-2026 ===")
    may = sig_2026[sig_2026["month"] == 5]
    if len(may) > 0:
        base_ppm = np.exp(_MU_LOG_LEAGUE) * 2
        delta_contribution = np.exp(_MU_LOG_LEAGUE + _DELTA_2026) * 2 - base_ppm
        signal_contribution = may["pred_per_side"].mean() * 2 - np.exp(_MU_LOG_LEAGUE + _DELTA_2026) * 2
        print(f"  Base PPM (no signals, no 2026 adj):   {base_ppm:.4f}")
        print(f"  + delta_2026 contribution:             {delta_contribution:+.4f}  → {np.exp(_MU_LOG_LEAGUE+_DELTA_2026)*2:.4f}")
        print(f"  + signal contribution:                 {signal_contribution:+.4f}  → {may['pred_per_side'].mean()*2:.4f}")
        print(f"     of which bullpen: {may['contrib_bullpen'].mean()*2:+.4f}")
        print(f"     of which run_env: {may['contrib_run_env'].mean()*2:+.4f}")
        print(f"     of which offense: {may['contrib_offense'].mean()*2:+.4f}")
        print(f"     of which starter: {may['contrib_starter'].mean()*2:+.4f}")
        print(f"  NUTS actual PPM (full posterior):      9.3023")
        print(f"  Actual May-2026 mean total_runs:       8.6842")

    print("\n=== Jensen's Inequality Decomposition (May-2026, bullpen) ===")
    if len(may) > 0:
        b = _BETAS["bullpen"]
        z_bull = may["z_bullpen"]
        mu_z = z_bull.mean()
        sigma_z = z_bull.std()
        # Log-space: log E[exp(b*z)] = b*mu_z + b^2*sigma_z^2/2
        log_mean_elev = b * mu_z
        log_jensen    = 0.5 * b**2 * sigma_z**2
        baseline_per_side = np.exp(_MU_LOG_LEAGUE + _DELTA_2026)
        # Mean elevation contribution: baseline*(exp(b*mu_z)-1)
        mean_elev_ppm = baseline_per_side * (np.exp(log_mean_elev) - 1) * 2
        # Jensen correction ON TOP of mean elevation: baseline*exp(b*mu_z)*(exp(b^2*sigma^2/2)-1)
        jensen_ppm    = baseline_per_side * np.exp(log_mean_elev) * (np.exp(log_jensen) - 1) * 2
        print(f"  z_bullpen May-2026: mean={mu_z:+.4f}  std={sigma_z:.4f}")
        print(f"  beta_bullpen = {b:.5f}")
        print(f"  Log-space mean elevation (b*mu_z):   {log_mean_elev:+.5f}")
        print(f"  Log-space Jensen correction (b²σ²/2):{log_jensen:+.5f}")
        print(f"  PPM mean-elevation contribution:     {mean_elev_ppm:+.4f}")
        print(f"  PPM Jensen contribution:             {jensen_ppm:+.4f}")
        print(f"  PPM total bullpen:                   {mean_elev_ppm+jensen_ppm:+.4f}")
        # Jensen floor at mu_z=0 (structural, irreducible)
        jensen_floor_ppm = baseline_per_side * (np.exp(log_jensen) - 1) * 2
        print(f"  Structural Jensen floor (mu_z=0):    {jensen_floor_ppm:+.4f}  ← irreducible at β={b:.3f}, σ_z={sigma_z:.3f}")
        print(f"  Kill threshold:  8.8100")
        print(f"  Baseline PPM:    {baseline_per_side*2:.4f}  (mu_log_league + delta_2026, z=0)")
        print(f"  Floor = baseline + Jensen: {baseline_per_side*2 + jensen_floor_ppm:.4f}")
        fixable = (baseline_per_side * 2 + jensen_floor_ppm) <= 8.81
        print(f"  Architecture fixable within log-link at this beta: {'YES' if fixable else 'NO — floor exceeds threshold'}")


if __name__ == "__main__":
    main()
