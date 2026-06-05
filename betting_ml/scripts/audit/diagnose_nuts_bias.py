"""
diagnose_nuts_bias.py — Epic 17.1 NUTS kill-criterion bias breakdown.

Quantifies which covariate signal is driving the PPM overshoot on May-2026 OOS.
All data is local (no Snowflake needed). Runtime < 5 seconds.

Usage:
    uv run python betting_ml/scripts/audit/diagnose_nuts_bias.py
"""

from pathlib import Path
import numpy as np
import pandas as pd
import joblib

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parents[3]
_OOS_DIR = _REPO / "betting_ml" / "models" / "layer3" / "oos_signals"
_BAYESIAN_DIR = _REPO / "betting_ml" / "models" / "bayesian"
_SCALER_PATH = _BAYESIAN_DIR / "signal_scalers.joblib"

# NUTS posterior means (from Phase 1 run output)
_MU_LOG_LEAGUE   = 1.4701
_DELTA_2025      = -0.0773   # 2026 mapped to 2025
_BETA_RUN_ENV    = 0.0511
_BETA_OFFENSE    = 0.0321
_BETA_BULLPEN    = 0.1912
_BETA_STARTER    = 0.0427
_BASELINE_SIDE   = np.exp(_MU_LOG_LEAGUE)               # no season, no covariates
_BASELINE_2026   = np.exp(_MU_LOG_LEAGUE + _DELTA_2025)  # with 2025 season delta

# ---------------------------------------------------------------------------
# Load OOS parquets and replicate cross-term logic from run_scoring_advi.py
# ---------------------------------------------------------------------------
def load_oos_signals() -> pd.DataFrame:
    offense = pd.read_parquet(_OOS_DIR / "oos_signals_offense.parquet")[
        ["game_pk", "side", "pred_runs_mu", "season"]
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

    # Cross-term: opposing side's bullpen and starter signals
    opp_map = {"home": "away", "away": "home"}
    opp = (
        df[["game_pk", "side", "bullpen_mu", "starter_suppression_mu"]]
        .assign(side=df["side"].map(opp_map))
        .rename(columns={"bullpen_mu": "opp_bullpen_mu",
                         "starter_suppression_mu": "opp_starter_mu"})
    )
    df = df.merge(opp, on=["game_pk", "side"], how="inner")
    return df


def main():
    # ── Load ────────────────────────────────────────────────────────────────
    df = load_oos_signals()
    scalers: dict = joblib.load(_SCALER_PATH)

    signal_map = {
        "run_env_mu":          "run_env_z",
        "pred_runs_mu":        "offense_mu_z",
        "opp_bullpen_mu":      "opp_bullpen_mu_z",
        "opp_starter_mu":      "opp_starter_mu_z",
    }
    for raw, z in signal_map.items():
        df[z] = scalers[raw].transform(df[raw].values.reshape(-1, 1)).ravel()

    # ── Season summary ───────────────────────────────────────────────────────
    print("\n========= RAW SIGNAL MEANS BY SEASON =========")
    raw_cols = list(signal_map.keys())
    summary = df.groupby("season")[raw_cols].mean().round(4)
    print(summary.to_string())

    print("\n========= Z-SCORED SIGNAL MEANS BY SEASON =========")
    z_cols = list(signal_map.values())
    z_summary = df.groupby("season")[z_cols].mean().round(4)
    print(z_summary.to_string())

    # ── May-2026 specifically ────────────────────────────────────────────────
    # Need game_date — try to load from a parquet that has it
    if "game_date" not in df.columns:
        # Try to infer from run_env parquet
        try:
            re_full = pd.read_parquet(_OOS_DIR / "oos_signals_run_env.parquet")
            if "game_date" in re_full.columns:
                df = df.merge(re_full[["game_pk", "game_date"]], on="game_pk", how="left")
                df["game_date"] = pd.to_datetime(df["game_date"])
        except Exception:
            pass

    if "game_date" in df.columns:
        may26 = df[(df["season"] == 2026) & (df["game_date"].dt.month == 5)]
    else:
        # Fall back to all 2026
        may26 = df[df["season"] == 2026]
        print("\nWARN: game_date not found in parquets; using all 2026 rows (not just May)")

    print(f"\n========= MAY-2026 OOS SIGNAL MEANS ({len(may26)} rows, "
          f"{may26['game_pk'].nunique()} games) =========")
    for raw, z in signal_map.items():
        raw_mean = float(may26[raw].mean())
        z_mean   = float(may26[z].mean())
        print(f"  {raw:<25}  raw={raw_mean:+.4f}  z={z_mean:+.4f}")

    # ── Linear contribution estimate ────────────────────────────────────────
    # For small deviations in log space:
    #   delta_E[runs/side] ≈ baseline_2026 * beta * mean_z_score
    betas = {
        "run_env_z":       _BETA_RUN_ENV,
        "offense_mu_z":    _BETA_OFFENSE,
        "opp_bullpen_mu_z": _BETA_BULLPEN,
        "opp_starter_mu_z": _BETA_STARTER,
    }
    print(f"\n========= PER-SIGNAL CONTRIBUTION TO PPM BIAS =========")
    print(f"  Baseline per side (mu_log_league only):          {_BASELINE_SIDE:.4f}")
    print(f"  Baseline per side (mu_log_league + delta_2025):  {_BASELINE_2026:.4f}")
    print(f"  Baseline total (x2):                             {_BASELINE_2026*2:.4f}")
    print()

    total_covariate_contribution_per_side = 0.0
    for z_col, beta in betas.items():
        mean_z = float(may26[z_col].mean())
        # First-order approximation: exp(beta * z) ≈ baseline * beta * z for small beta*z
        # More accurate: contribution = baseline_2026 * (exp(beta*z_mean) - 1)
        log_contribution = beta * mean_z
        run_contribution_per_side = _BASELINE_2026 * (np.exp(log_contribution) - 1)
        total_covariate_contribution_per_side += log_contribution
        print(f"  {z_col:<25}  beta={beta:.4f}  mean_z={mean_z:+.4f}  "
              f"log-contrib={log_contribution:+.4f}  "
              f"≈ {run_contribution_per_side*2:+.3f} total runs")

    total_log_contrib = total_covariate_contribution_per_side
    predicted_per_side = _BASELINE_2026 * np.exp(total_log_contrib)
    predicted_total = predicted_per_side * 2
    print(f"\n  Predicted total (baseline_2026 + all covariates, avg team effects=0):")
    print(f"    {predicted_total:.4f} runs")
    print(f"  Actual NUTS PPM:      8.8607")
    print(f"  Kill criterion:       8.81")
    print(f"  Bias from threshold:  +{8.8607-8.81:.4f}")
    print(f"  Explained bias:       +{predicted_total - _BASELINE_2026*2:.4f} from covariates + "
          f"{8.8607 - predicted_total:.4f} from team effects")

    # ── Training vs 2026 signal distribution comparison ─────────────────────
    print("\n========= TRAINING (2022-2025) vs 2026 RAW SIGNAL DISTRIBUTIONS =========")
    train_df = df[df["season"].isin([2022, 2023, 2024, 2025])]
    oos_df   = df[df["season"] == 2026]
    for raw, z in signal_map.items():
        t_mean = float(train_df[raw].mean())
        t_std  = float(train_df[raw].std())
        o_mean = float(oos_df[raw].mean())
        o_std  = float(oos_df[raw].std())
        z_shift = (o_mean - t_mean) / t_std if t_std > 0 else float("nan")
        print(f"  {raw:<25}  train_mean={t_mean:.4f}  2026_mean={o_mean:.4f}  "
              f"shift={o_mean-t_mean:+.4f}  z_shift={z_shift:+.2f}σ")

    print()


if __name__ == "__main__":
    main()
