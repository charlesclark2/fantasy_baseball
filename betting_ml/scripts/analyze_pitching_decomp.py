"""Card 3.8 — Bullpen vs. Starter Signal Decomposition.

Determines whether home_starter_xwoba_against_std and home_bp_xwoba_against_30d
contribute independent variance to game outcomes or are redundant (both r≈0.06
in NB04). Runs four analysis steps, prints a summary table, writes results JSON.
"""

import json
import os
import sys
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from betting_ml.utils.data_loader import load_features

ALIASES = {
    "h_start": "home_starter_xwoba_against_std",
    "h_bp":    "home_bp_xwoba_against_30d",
    "a_start": "away_starter_xwoba_against_std",
    "a_bp":    "away_bp_xwoba_against_30d",
    "h_bp_pit": "home_bullpen_pitches_prev_3d",
    "h_bp_use": "home_pitchers_used_prev_7d",
    "a_bp_pit": "away_bullpen_pitches_prev_3d",
    "a_bp_use": "away_pitchers_used_prev_7d",
}

TARGETS = ["total_runs", "run_differential", "home_win"]
COLLINEARITY_THRESHOLD = 0.70
INCREMENTAL_R2_THRESHOLD = 0.002
WORKLOAD_THRESHOLD = 0.005


def _partial_corr_residual(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> tuple[float, float]:
    """Partial correlation of x with y, controlling for z, via residual-on-residual OLS."""
    def residuals(a, b):
        b_with_const = sm.add_constant(b)
        model = sm.OLS(a, b_with_const).fit()
        return model.resid

    e_x = residuals(x, z)
    e_y = residuals(y, z)
    r, p = stats.pearsonr(e_x, e_y)
    return float(r), float(p)


def step1_cross_correlation(df: pd.DataFrame) -> dict:
    print("\nSTEP 1 — Cross-correlation")
    h_r, h_p = stats.pearsonr(df["h_start"], df["h_bp"])
    a_r, a_p = stats.pearsonr(df["a_start"], df["a_bp"])
    high_collinearity = bool(abs(h_r) > COLLINEARITY_THRESHOLD or abs(a_r) > COLLINEARITY_THRESHOLD)
    print(f"  h_start vs h_bp:  r={h_r:.4f}  p={h_p:.4f}")
    print(f"  a_start vs a_bp:  r={a_r:.4f}  p={a_p:.4f}")
    print(f"  high_collinearity: {high_collinearity}")
    return {
        "home_starter_vs_bp_r":    float(h_r),
        "home_starter_vs_bp_pval": float(h_p),
        "away_starter_vs_bp_r":    float(a_r),
        "away_starter_vs_bp_pval": float(a_p),
        "high_collinearity":       high_collinearity,
    }


def step2_partial_correlations(df: pd.DataFrame) -> list[dict]:
    print("\nSTEP 2 — Partial correlations")
    pairs = [
        ("h_start", "h_bp"),
        ("h_bp",    "h_start"),
        ("a_start", "a_bp"),
        ("a_bp",    "a_start"),
    ]
    records = []
    header = f"  {'feature':<32} {'target':<18} {'pearson_r':>10} {'partial_r':>10} {'controlling_for'}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for feat_alias, ctrl_alias in pairs:
        feat_col = feat_alias
        ctrl_col = ctrl_alias
        for target in TARGETS:
            x = df[feat_col].values
            y = df[target].values
            z = df[ctrl_col].values
            pearson_r, _ = stats.pearsonr(x, y)
            partial_r, _ = _partial_corr_residual(x, y, z)
            records.append({
                "feature":         ALIASES[feat_alias],
                "target":          target,
                "pearson_r":       float(pearson_r),
                "partial_r":       float(partial_r),
                "controlling_for": ALIASES[ctrl_alias],
            })
            print(f"  {ALIASES[feat_alias]:<32} {target:<18} {pearson_r:>10.4f} {partial_r:>10.4f}  {ALIASES[ctrl_alias]}")
    return records


def step3_ols_decomposition(df: pd.DataFrame) -> dict:
    print("\nSTEP 3 — OLS R² decomposition")
    print(f"  {'target':<18} {'starter_r2':>12} {'bullpen_r2':>12} {'combined_r2':>12} {'incremental_r2':>15}")
    print("  " + "-" * 73)

    result = {}
    for target in TARGETS:
        y = df[target].values
        X_start   = sm.add_constant(df[["h_start", "a_start"]].values)
        X_bp      = sm.add_constant(df[["h_bp",    "a_bp"]].values)
        X_combined = sm.add_constant(df[["h_start", "a_start", "h_bp", "a_bp"]].values)

        r2_start   = sm.OLS(y, X_start).fit().rsquared
        r2_bp      = sm.OLS(y, X_bp).fit().rsquared
        r2_combined = sm.OLS(y, X_combined).fit().rsquared
        incremental = r2_combined - max(r2_start, r2_bp)

        result[target] = {
            "starter_only_r2":  float(r2_start),
            "bullpen_only_r2":  float(r2_bp),
            "combined_r2":      float(r2_combined),
            "incremental_r2":   float(incremental),
        }
        print(f"  {target:<18} {r2_start:>12.6f} {r2_bp:>12.6f} {r2_combined:>12.6f} {incremental:>15.6f}")
    return result


def step4_workload_signal(df: pd.DataFrame, ols_decomp: dict) -> tuple[list[dict], dict]:
    print("\nSTEP 4 — Workload correlations")
    workload_features = ["h_bp_pit", "h_bp_use", "a_bp_pit", "a_bp_use"]
    records = []
    print(f"  {'feature':<40} {'target':<18} {'pearson_r':>10}")
    print("  " + "-" * 72)
    for feat_alias in workload_features:
        for target in TARGETS:
            r, _ = stats.pearsonr(df[feat_alias].values, df[target].values)
            records.append({
                "feature":   ALIASES[feat_alias],
                "target":    target,
                "pearson_r": float(r),
            })
            print(f"  {ALIASES[feat_alias]:<40} {target:<18} {r:>10.4f}")

    # Workload incremental R²: OLS(t ~ h_bp + h_bp_pit + h_bp_use) vs bullpen_only
    print()
    workload_incremental = {}
    for target in TARGETS:
        y = df[target].values
        X_bp_workload = sm.add_constant(
            df[["h_bp", "h_bp_pit", "h_bp_use"]].values
        )
        r2_with_workload = sm.OLS(y, X_bp_workload).fit().rsquared
        bullpen_only_r2 = ols_decomp[target]["bullpen_only_r2"]
        incr = r2_with_workload - bullpen_only_r2
        workload_incremental[f"home_{target}"] = float(incr)
        print(f"  Workload incremental R² (h side, {target}): {incr:.6f}")

    return records, workload_incremental


def build_recommendation(cross_corr: dict, ols_decomp: dict, workload_incremental: dict) -> dict:
    high_collinearity = cross_corr["high_collinearity"]
    mean_incremental = float(np.mean([ols_decomp[t]["incremental_r2"] for t in TARGETS]))
    max_workload_incr = max(workload_incremental.values())

    keep_both = False
    drop_bullpen = False

    if high_collinearity:
        drop_bullpen = True
        keep_both = False
        rationale_base = (
            f"High collinearity detected: home r={cross_corr['home_starter_vs_bp_r']:.4f}, "
            f"away r={cross_corr['away_starter_vs_bp_r']:.4f} (threshold |r|>0.70). "
            "Drop bullpen xwOBA; retain the stronger predictor."
        )
    elif mean_incremental < INCREMENTAL_R2_THRESHOLD:
        drop_bullpen = True
        keep_both = False
        rationale_base = (
            f"No high collinearity (home r={cross_corr['home_starter_vs_bp_r']:.4f}, "
            f"away r={cross_corr['away_starter_vs_bp_r']:.4f}), but mean incremental R²="
            f"{mean_incremental:.6f} < {INCREMENTAL_R2_THRESHOLD} threshold. "
            "Marginal gain not worth added collinearity; drop bullpen xwOBA."
        )
    else:
        keep_both = True
        drop_bullpen = False
        rationale_base = (
            f"No high collinearity (home r={cross_corr['home_starter_vs_bp_r']:.4f}, "
            f"away r={cross_corr['away_starter_vs_bp_r']:.4f}) and mean incremental R²="
            f"{mean_incremental:.6f} >= {INCREMENTAL_R2_THRESHOLD} threshold. "
            "Keep both starter and bullpen xwOBA in Phase 4."
        )

    add_workload_flag = bool(max_workload_incr > WORKLOAD_THRESHOLD)
    workload_note = (
        f" Workload max incremental R²={max_workload_incr:.6f} "
        f"{'>' if add_workload_flag else '<='} {WORKLOAD_THRESHOLD} threshold — "
        f"{'add workload features.' if add_workload_flag else 'workload adds no meaningful signal beyond trailing xwOBA.'}"
    )

    return {
        "keep_both":         bool(keep_both),
        "drop_bullpen":      bool(drop_bullpen),
        "add_workload_flag": bool(add_workload_flag),
        "rationale":         rationale_base + workload_note,
    }


def main() -> None:
    print("Loading features from mart...")
    raw = load_features(min_games_played=15)

    # Rename to aliases for cleaner downstream references
    rename_map = {full: alias for alias, full in ALIASES.items()}
    df_full = raw.rename(columns=rename_map)

    required_alias_cols = list(ALIASES.keys()) + TARGETS
    df = df_full[required_alias_cols].dropna()
    print(f"  Non-null rows for pitching analysis: {len(df):,} (dropped {len(df_full) - len(df):,})")

    cross_corr     = step1_cross_correlation(df)
    partial_corrs  = step2_partial_correlations(df)
    ols_decomp     = step3_ols_decomposition(df)
    workload_corrs, workload_incremental = step4_workload_signal(df, ols_decomp)
    recommendation = build_recommendation(cross_corr, ols_decomp, workload_incremental)

    print("\n" + "=" * 60)
    print("DESIGN RECOMMENDATION")
    print("=" * 60)
    print(f"  keep_both:         {recommendation['keep_both']}")
    print(f"  drop_bullpen:      {recommendation['drop_bullpen']}")
    print(f"  add_workload_flag: {recommendation['add_workload_flag']}")
    print(f"  rationale: {recommendation['rationale']}")

    results = {
        "cross_correlation":      cross_corr,
        "partial_correlations":   partial_corrs,
        "ols_decomposition":      ols_decomp,
        "workload_correlations":  workload_corrs,
        "workload_incremental_r2": workload_incremental,
        "design_recommendation":  recommendation,
    }

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluation")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "pitching_decomp_results.json")
    class _NumpyEncoder(json.JSONEncoder):
        def default(self, obj: Any) -> Any:
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            return super().default(obj)

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
