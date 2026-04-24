"""Card 3.9 — Home/Away Pitching Quality Asymmetry.

Investigates the 9× asymmetry between home and away pitching xwOBA as
predictors of total runs (home r≈0.075, away r≈0.008 in NB04). Tests four
hypotheses via partial correlation (H1), park quartile stratification (H1b),
era-split (H2), and starter vs. team-level comparison (H3). Writes results JSON.
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
    "h_pit_30":  "home_pit_xwoba_against_30d",
    "a_pit_30":  "away_pit_xwoba_against_30d",
    "h_pit_std": "home_pit_xwoba_against_std",
    "a_pit_std": "away_pit_xwoba_against_std",
    "h_start":   "home_starter_xwoba_against_std",
    "a_start":   "away_starter_xwoba_against_std",
    "park_rf":   "park_run_factor_3yr",
}

TARGETS = ["total_runs", "run_differential", "home_win"]

H1_PARTIAL_R_THRESHOLD = 0.030
H2_ASYMMETRY_RATIO_THRESHOLD = 3.0
H3_DELTA_THRESHOLD = 0.010


def _partial_corr_multi(x: np.ndarray, y: np.ndarray, controls: np.ndarray) -> tuple[float, float]:
    """Partial correlation of x with y, controlling for one or more variables (columns of controls)."""
    Z = sm.add_constant(controls)

    def residuals(a: np.ndarray) -> np.ndarray:
        return sm.OLS(a, Z).fit().resid

    r, p = stats.pearsonr(residuals(x), residuals(y))
    return float(r), float(p)


def step1_raw_and_partial_correlations(df: pd.DataFrame) -> tuple[list[dict], list[dict], dict]:
    print("\nSTEP 1 — Raw and Partial Correlations (H1 test)")
    raw_records: list[dict] = []
    partial_records: list[dict] = []
    n = len(df)

    pit_features = ["h_pit_30", "a_pit_30"]
    header = f"  {'feature':<25} {'target':<18} {'raw_r':>8} {'partial_r':>10}  controlling_for"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for feat in pit_features:
        for target in TARGETS:
            r, p = stats.pearsonr(df[feat].values, df[target].values)
            raw_records.append({
                "feature": ALIASES[feat],
                "target": target,
                "pearson_r": float(r),
                "p_value": float(p),
                "n": int(n),
            })

    # Partial r: each pitching feature controlling for park_rf + the opposing pitching feature
    partial_pairs = [
        ("a_pit_30", ["park_rf", "h_pit_30"]),
        ("h_pit_30", ["park_rf", "a_pit_30"]),
    ]
    for feat, ctrl_aliases in partial_pairs:
        controls = df[[c for c in ctrl_aliases]].values
        ctrl_label = " + ".join(ALIASES[c] for c in ctrl_aliases)
        for target in TARGETS:
            raw_r, _ = stats.pearsonr(df[feat].values, df[target].values)
            partial_r, _ = _partial_corr_multi(df[feat].values, df[target].values, controls)
            partial_records.append({
                "feature": ALIASES[feat],
                "target": target,
                "raw_pearson_r": float(raw_r),
                "partial_r": float(partial_r),
                "controlling_for": ctrl_label,
                "n": int(n),
            })
            print(f"  {ALIASES[feat]:<25} {target:<18} {raw_r:>8.4f} {partial_r:>10.4f}  {ctrl_label}")

    max_away_partial = max(abs(r["partial_r"]) for r in partial_records if r["feature"] == ALIASES["a_pit_30"])
    h1_park_absorbs_away = bool(max_away_partial < H1_PARTIAL_R_THRESHOLD)
    print(f"\n  max |partial_r| for a_pit_30: {max_away_partial:.4f}")
    print(f"  h1_park_absorbs_away: {h1_park_absorbs_away} (threshold < {H1_PARTIAL_R_THRESHOLD})")

    return raw_records, partial_records, {"h1_park_absorbs_away": h1_park_absorbs_away, "max_away_partial_r": float(max_away_partial)}


def step2_park_quartile_stratification(df: pd.DataFrame) -> list[dict]:
    print("\nSTEP 2 — Park Factor Quartile Stratification (H1 quartile evidence)")
    df = df.copy()
    df["quartile"] = pd.qcut(df["park_rf"], q=4, labels=[1, 2, 3, 4]).astype(int)

    records: list[dict] = []
    for target in TARGETS:
        print(f"\n  Target: {target}")
        print(f"  {'Q':<4} {'n':>6} {'park_rf_range':<22} {'h_pit_30_r':>12} {'a_pit_30_r':>12} {'asymmetry_ratio':>16}")
        print("  " + "-" * 76)
        for q in [1, 2, 3, 4]:
            sub = df[df["quartile"] == q]
            n_q = len(sub)
            rf_min = float(sub["park_rf"].min())
            rf_max = float(sub["park_rf"].max())
            h_r, _ = stats.pearsonr(sub["h_pit_30"].values, sub[target].values)
            a_r, _ = stats.pearsonr(sub["a_pit_30"].values, sub[target].values)
            asymmetry = float(abs(h_r) / max(abs(a_r), 1e-6))
            records.append({
                "quartile": int(q),
                "n": int(n_q),
                "park_rf_min": rf_min,
                "park_rf_max": rf_max,
                "target": target,
                "home_pit_r": float(h_r),
                "away_pit_r": float(a_r),
                "asymmetry_ratio": asymmetry,
            })
            print(f"  Q{q}   {n_q:>6} [{rf_min:.3f}, {rf_max:.3f}]        {h_r:>12.4f} {a_r:>12.4f} {asymmetry:>16.2f}")

    return records


def step3_era_split_correlations(df: pd.DataFrame) -> tuple[list[dict], dict]:
    print("\nSTEP 3 — Era-Split Correlations (H2 test)")
    era_defs = {
        "pre_juiced": [2016, 2017, 2018, 2019],
        "modern":     [2021, 2022, 2023, 2024, 2025],
    }
    pit_feats = ["h_pit_30", "a_pit_30", "h_pit_std", "a_pit_std"]

    records: list[dict] = []
    asymmetry_ratios_by_era: dict[str, list[float]] = {}

    header = f"  {'era':<12} {'target':<18} {'h_pit_30_r':>12} {'a_pit_30_r':>12} {'asymmetry':>10} {'n':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for era_name, years in era_defs.items():
        sub = df[df["game_year"].isin(years)]
        n_era = len(sub)
        era_ratios: list[float] = []
        for target in TARGETS:
            feat_rs: dict[str, float] = {}
            for feat in pit_feats:
                r, _ = stats.pearsonr(sub[feat].values, sub[target].values)
                feat_rs[feat] = float(r)
            h_r = feat_rs["h_pit_30"]
            a_r = feat_rs["a_pit_30"]
            asymmetry = float(abs(h_r) / max(abs(a_r), 1e-6))
            era_ratios.append(asymmetry)
            records.append({
                "era": era_name,
                "n": int(n_era),
                "target": target,
                "h_pit_30_r": h_r,
                "a_pit_30_r": a_r,
                "h_pit_std_r": feat_rs["h_pit_std"],
                "a_pit_std_r": feat_rs["a_pit_std"],
                "asymmetry_ratio": asymmetry,
            })
            print(f"  {era_name:<12} {target:<18} {h_r:>12.4f} {a_r:>12.4f} {asymmetry:>10.2f} {n_era:>6}")
        asymmetry_ratios_by_era[era_name] = era_ratios

    high_both = all(
        min(ratios) > H2_ASYMMETRY_RATIO_THRESHOLD
        for ratios in asymmetry_ratios_by_era.values()
    )
    h2_era_confound = bool(not high_both)
    print(f"\n  h2_era_confound: {h2_era_confound}")
    print(f"    (asymmetry > {H2_ASYMMETRY_RATIO_THRESHOLD} in BOTH eras means H2 refuted → h2_era_confound=False)")

    return records, {"h2_era_confound": h2_era_confound}


def step4_starter_vs_team_level(df: pd.DataFrame) -> tuple[list[dict], dict]:
    print("\nSTEP 4 — Starter vs. Team-Level Comparison (H3 test)")
    comparisons = [
        ("home", "h_start", "h_pit_30"),
        ("away", "a_start", "a_pit_30"),
    ]
    records: list[dict] = []
    away_deltas: list[float] = []

    header = f"  {'side':<6} {'type':<12} {'total_runs_r':>13} {'run_diff_r':>11} {'home_win_r':>11} {'mean_abs_r':>11}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for side, start_alias, team_alias in comparisons:
        for feat_alias, feat_type in [(start_alias, "starter"), (team_alias, "team_level")]:
            rs = {}
            for target in TARGETS:
                r, _ = stats.pearsonr(df[feat_alias].values, df[target].values)
                rs[target] = float(r)
            mean_abs = float(np.mean([abs(v) for v in rs.values()]))
            records.append({
                "side": side,
                "feature_type": feat_type,
                "feature": ALIASES[feat_alias],
                "total_runs_r": rs["total_runs"],
                "run_differential_r": rs["run_differential"],
                "home_win_r": rs["home_win"],
                "mean_abs_r": mean_abs,
            })
            print(f"  {side:<6} {feat_type:<12} {rs['total_runs']:>13.4f} {rs['run_differential']:>11.4f} {rs['home_win']:>11.4f} {mean_abs:>11.4f}")

        # delta for this side: starter mean_abs_r - team_level mean_abs_r
        starter_rec = records[-2]
        team_rec = records[-1]
        delta = starter_rec["mean_abs_r"] - team_rec["mean_abs_r"]
        if side == "away":
            away_deltas.append(delta)

    mean_away_delta = float(np.mean(away_deltas)) if away_deltas else 0.0
    h3_park_contamination = bool(mean_away_delta > H3_DELTA_THRESHOLD)
    print(f"\n  mean away starter-vs-team delta: {mean_away_delta:.4f}")
    print(f"  h3_park_contamination: {h3_park_contamination} (threshold > {H3_DELTA_THRESHOLD})")

    return records, {"h3_park_contamination": h3_park_contamination, "away_starter_minus_team_delta": mean_away_delta}


def build_hypothesis_verdicts(
    h1_info: dict, h2_info: dict, h3_info: dict,
    partial_records: list[dict],
) -> dict:
    h1 = h1_info["h1_park_absorbs_away"]
    h2 = h2_info["h2_era_confound"]
    h3 = h3_info["h3_park_contamination"]
    delta = h3_info["away_starter_minus_team_delta"]
    max_partial = h1_info["max_away_partial_r"]

    a_partial_total = next(
        (r["partial_r"] for r in partial_records
         if r["feature"] == ALIASES["a_pit_30"] and r["target"] == "total_runs"),
        None,
    )

    h1_verdict = "supported" if h1 else "not supported"
    h1_evidence = (
        f"Max |partial_r| for away_pit_xwoba_against_30d (controlling for park_run_factor_3yr + "
        f"home_pit_xwoba_against_30d) = {max_partial:.4f}. "
        f"Threshold < {H1_PARTIAL_R_THRESHOLD} → H1 {'supported' if h1 else 'refuted'}. "
        f"Park factor {'does' if h1 else 'does not'} fully absorb away pitching variance."
    )

    h2_verdict = "supported" if h2 else "not supported"
    h2_evidence = (
        f"Asymmetry ratio (|h_pit_30_r| / |a_pit_30_r|) examined in pre_juiced (2016–2019) and "
        f"modern (2021–2025) eras. H2 era confound = {h2}. "
        f"{'Asymmetry confined to one era — rotation alignment sample may drive asymmetry.' if h2 else 'Asymmetry present in both eras — not era-specific; H2 refuted.'}"
    )

    h3_verdict = "supported" if h3 else "not supported"
    h3_evidence = (
        f"Mean away starter vs. team-level |r| delta = {delta:.4f}. "
        f"Threshold > {H3_DELTA_THRESHOLD} → H3 {'supported' if h3 else 'refuted'}. "
        f"Away starter feature {'outperforms' if h3 else 'does not clearly outperform'} away team-level xwOBA, "
        f"{'suggesting park contamination in team-level measurement.' if h3 else 'suggesting both capture similar near-zero signal.'}"
    )

    h4_verdict = "inconclusive"
    h4_evidence = (
        "H4 (signal direction ambiguity) posits that away xwOBA_against measured in home parks "
        "introduces directional noise. If H1 is refuted and H3 shows near-zero delta, the residual "
        "asymmetry is likely structural — away pitching quality is genuinely less predictive of "
        "runs in home parks due to selection and lineup optimization effects. "
        f"With a_pit_30 partial r (vs total_runs, controlling park + h_pit_30) = {f'{a_partial_total:.4f}' if a_partial_total is not None else 'N/A'}, "
        "this ambiguity remains plausible but cannot be separated from structural explanations without "
        "pitch-level park-adjusted data."
    )

    return {
        "H1_park_absorbs_away_variance": {
            "verdict": h1_verdict,
            "evidence": h1_evidence,
            "h1_park_absorbs_away": bool(h1),
        },
        "H2_rotation_era_confound": {
            "verdict": h2_verdict,
            "evidence": h2_evidence,
            "h2_era_confound": bool(h2),
        },
        "H3_park_contamination_team_level": {
            "verdict": h3_verdict,
            "evidence": h3_evidence,
            "h3_park_contamination": bool(h3),
            "away_starter_minus_team_delta": float(delta),
        },
        "H4_signal_direction_ambiguity": {
            "verdict": h4_verdict,
            "evidence": h4_evidence,
        },
    }


def build_design_recommendation(h1_info: dict, h2_info: dict, h3_info: dict, partial_records: list[dict]) -> dict:
    park_absorbs = bool(h1_info["h1_park_absorbs_away"])
    prefer_starter = bool(h3_info["h3_park_contamination"])
    h2 = bool(h2_info["h2_era_confound"])

    asymmetry_is_structural = bool(not h2 and not park_absorbs)

    a_partial_total = next(
        (r["partial_r"] for r in partial_records
         if r["feature"] == ALIASES["a_pit_30"] and r["target"] == "total_runs"),
        float("nan"),
    )
    delta = h3_info["away_starter_minus_team_delta"]

    if park_absorbs:
        phase4_implication = (
            "Away team-level pitching xwOBA is redundant once park factor is controlled; "
            "include park_run_factor_3yr and rely on home pitching features."
        )
    elif prefer_starter:
        phase4_implication = (
            "Prefer away_starter_xwoba_against_std over away_pit_xwoba_against_30d in Phase 4; "
            "team-level away xwOBA is contaminated by park effects."
        )
    elif asymmetry_is_structural:
        phase4_implication = (
            "Asymmetry is structural — include both home and away pitching features and allow "
            "the model to learn the differential weighting; do not drop either."
        )
    else:
        phase4_implication = (
            "Evidence is mixed; include both pitching feature sets and apply regularization "
            "to prevent away team-level xwOBA from dominating."
        )

    rationale = (
        f"Partial r of away_pit_xwoba_against_30d vs. total_runs (controlling for "
        f"park_run_factor_3yr + home_pit_xwoba_against_30d) = {a_partial_total:.4f}. "
        f"H1 (park absorbs away variance): {'supported' if park_absorbs else 'not supported'}. "
        f"H2 (era confound): {'supported' if h2 else 'not supported (asymmetry in both eras)'}. "
        f"H3 (park contamination): {'supported' if prefer_starter else 'not supported'} "
        f"(away starter vs. team-level delta = {delta:.4f}). "
        f"asymmetry_is_structural = {asymmetry_is_structural}. "
        f"Phase 4 implication: {phase4_implication}"
    )

    return {
        "park_absorbs_away_variance": park_absorbs,
        "prefer_starter_over_team_level_away": prefer_starter,
        "asymmetry_is_structural": asymmetry_is_structural,
        "rationale": rationale,
    }


def main() -> None:
    print("Loading features from mart...")
    raw = load_features(min_games_played=15)

    rename_map = {full: alias for alias, full in ALIASES.items()}
    df_full = raw.rename(columns=rename_map)

    required_alias_cols = list(ALIASES.keys()) + TARGETS + ["game_year"]
    df = df_full[required_alias_cols].dropna(subset=[c for c in ALIASES.keys()])
    print(f"  Non-null rows for asymmetry analysis: {len(df):,} (dropped {len(df_full) - len(df):,})")

    gate_rows = df[df["game_year"] != 2020]
    print(f"  Gate check — rows with park_rf and a_pit_30 non-null (excl. 2020): {len(gate_rows):,}")
    assert len(gate_rows) >= 5000, f"Gate requires >=5000 rows, got {len(gate_rows)}"

    raw_records, partial_records, h1_info = step1_raw_and_partial_correlations(df)
    quartile_records = step2_park_quartile_stratification(df)
    era_records, h2_info = step3_era_split_correlations(df)
    starter_records, h3_info = step4_starter_vs_team_level(df)

    hypothesis_verdicts = build_hypothesis_verdicts(h1_info, h2_info, h3_info, partial_records)
    design_recommendation = build_design_recommendation(h1_info, h2_info, h3_info, partial_records)

    print("\n" + "=" * 60)
    print("HYPOTHESIS VERDICTS")
    print("=" * 60)
    for h_name, h_data in hypothesis_verdicts.items():
        print(f"  {h_name}: {h_data['verdict'].upper()}")

    print("\n" + "=" * 60)
    print("DESIGN RECOMMENDATION")
    print("=" * 60)
    print(f"  park_absorbs_away_variance:           {design_recommendation['park_absorbs_away_variance']}")
    print(f"  prefer_starter_over_team_level_away:  {design_recommendation['prefer_starter_over_team_level_away']}")
    print(f"  asymmetry_is_structural:              {design_recommendation['asymmetry_is_structural']}")
    print(f"  rationale: {design_recommendation['rationale']}")

    results = {
        "raw_correlations":          raw_records,
        "partial_correlations":      partial_records,
        "park_quartile_correlations": quartile_records,
        "era_split_correlations":    era_records,
        "starter_vs_team_correlations": starter_records,
        "hypothesis_verdicts":       hypothesis_verdicts,
        "design_recommendation":     design_recommendation,
    }

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluation")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "home_away_pitch_asymmetry_results.json")

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
