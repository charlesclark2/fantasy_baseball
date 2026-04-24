"""Card 3.10 — Era-Split Correlation Stability.

Tests whether feature-outcome correlations are stable across the pre-2022
(game_year in [2016,2017,2018,2019,2021]) and post-2022 (game_year in
[2022,2023,2024,2025]) eras. Fisher z-tests determine statistical significance
of correlation shifts. Writes results JSON and prints a summary table.
"""

import json
import os
import sys
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from betting_ml.utils.data_loader import load_features

TARGETS = ["total_runs", "run_differential", "home_win"]

EXCLUDE_COLS = {
    # targets
    "total_runs", "run_differential", "home_win",
    # metadata / identifiers
    "game_pk", "game_date", "home_team", "away_team",
    "home_team_id", "away_team_id", "venue_id", "game_year",
    # binary era / data-availability flags
    "post_2022_rules", "has_starter_platoon_data", "has_odds",
}

PRE_YEARS = [2016, 2017, 2018, 2019, 2021]
POST_YEARS = [2022, 2023, 2024, 2025]
MIN_ERA_ROWS = 1_000
R_DELTA_THRESHOLD = 0.015
MEAN_ABS_R_STABLE_THRESHOLD = 0.010


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        return super().default(obj)


def _candidate_features(df: pd.DataFrame) -> list[str]:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    candidates = [c for c in numeric_cols if c not in EXCLUDE_COLS]

    df_pre = df[df["game_year"].isin(PRE_YEARS)]
    df_post = df[df["game_year"].isin(POST_YEARS)]

    qualified = [
        c for c in candidates
        if df_pre[c].notna().sum() >= MIN_ERA_ROWS
        and df_post[c].notna().sum() >= MIN_ERA_ROWS
    ]
    return qualified


def step1_full_dataset_correlations(
    df: pd.DataFrame, candidates: list[str]
) -> tuple[list[dict], list[str]]:
    print("\nSTEP 1 — Full-Dataset Correlations (Top 20 Features)")
    records: list[dict] = []

    for feat in candidates:
        mask = df[feat].notna()
        x = df.loc[mask, feat].values
        row: dict[str, Any] = {"feature": feat}
        abs_rs: list[float] = []
        for target in TARGETS:
            y = df.loc[mask, target].values
            r, p = stats.pearsonr(x, y)
            r = float(r)
            p = float(p)
            n = int(mask.sum())
            records.append({
                "feature": feat,
                "target": target,
                "pearson_r": r,
                "p_value": p,
                "n": n,
            })
            abs_rs.append(abs(r))
            row[f"r_{target}"] = r
        row["mean_abs_r"] = float(np.mean(abs_rs))

    # rank features by mean_abs_r
    feat_summary: dict[str, dict] = {}
    for feat in candidates:
        feat_recs = [r for r in records if r["feature"] == feat]
        mean_abs = float(np.mean([abs(r["pearson_r"]) for r in feat_recs]))
        rs = {r["target"]: r["pearson_r"] for r in feat_recs}
        feat_summary[feat] = {"mean_abs_r": mean_abs, **rs}

    sorted_feats = sorted(feat_summary, key=lambda f: feat_summary[f]["mean_abs_r"], reverse=True)
    top_features = sorted_feats[:20]

    if len(top_features) < 10:
        raise ValueError(
            f"Only {len(top_features)} qualified features; minimum 10 required."
        )

    header = f"  {'Feature':<45} {'mean|r|':>8} {'r_total':>9} {'r_run_diff':>11} {'r_home_win':>11}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for feat in top_features:
        s = feat_summary[feat]
        print(
            f"  {feat:<45} {s['mean_abs_r']:>8.4f}"
            f" {s.get('total_runs', 0.0):>9.4f}"
            f" {s.get('run_differential', 0.0):>11.4f}"
            f" {s.get('home_win', 0.0):>11.4f}"
        )

    # filter records to top_features only
    top_set = set(top_features)
    top_records = [r for r in records if r["feature"] in top_set]

    return top_records, top_features


def step2_era_split_correlations(
    df: pd.DataFrame, top_features: list[str]
) -> list[dict]:
    print("\nSTEP 2 — Era-Split Correlations (Flagged features: |r_delta| > 0.015)")
    df_pre = df[df["game_year"].isin(PRE_YEARS)]
    df_post = df[df["game_year"].isin(POST_YEARS)]

    records: list[dict] = []
    flagged_rows: list[dict] = []

    for feat in top_features:
        for target in TARGETS:
            mask_pre = df_pre[feat].notna()
            mask_post = df_post[feat].notna()
            x_pre = df_pre.loc[mask_pre, feat].values
            y_pre = df_pre.loc[mask_pre, target].values
            x_post = df_post.loc[mask_post, feat].values
            y_post = df_post.loc[mask_post, target].values

            pre_r, pre_p = stats.pearsonr(x_pre, y_pre)
            post_r, post_p = stats.pearsonr(x_post, y_post)
            pre_n = int(mask_pre.sum())
            post_n = int(mask_post.sum())
            r_delta = float(post_r) - float(pre_r)
            abs_r_delta = abs(r_delta)
            flagged = bool(abs_r_delta > R_DELTA_THRESHOLD)

            rec = {
                "feature": feat,
                "target": target,
                "pre_2022_r": float(pre_r),
                "pre_2022_n": pre_n,
                "pre_2022_p": float(pre_p),
                "post_2022_r": float(post_r),
                "post_2022_n": post_n,
                "post_2022_p": float(post_p),
                "r_delta": r_delta,
                "abs_r_delta": abs_r_delta,
                "flagged": flagged,
            }
            records.append(rec)
            if flagged:
                flagged_rows.append(rec)

    if flagged_rows:
        print(f"  {'Feature':<45} {'Target':<16} {'Pre-r':>7} {'Post-r':>7} {'r_delta':>8} {'Flagged':>8}")
        print("  " + "-" * 100)
        flagged_sorted = sorted(flagged_rows, key=lambda r: abs(r["r_delta"]), reverse=True)
        for r in flagged_sorted:
            print(
                f"  {r['feature']:<45} {r['target']:<16}"
                f" {r['pre_2022_r']:>7.4f} {r['post_2022_r']:>7.4f}"
                f" {r['r_delta']:>8.4f} {'YES':>8}"
            )
    else:
        print("  No features flagged at |r_delta| > 0.015 threshold")

    return records


def step3_fisher_z_tests(
    df: pd.DataFrame,
    top_features: list[str],
    era_split_records: list[dict],
    full_dataset_records: list[dict],
) -> list[dict]:
    print("\nSTEP 3 — Fisher Z-Test (Top 10 per target)")
    df_pre = df[df["game_year"].isin(PRE_YEARS)]
    df_post = df[df["game_year"].isin(POST_YEARS)]

    # build lookup: (feat, target) → era_split rec
    era_lookup: dict[tuple[str, str], dict] = {
        (r["feature"], r["target"]): r for r in era_split_records
    }

    # build full-dataset |r| per (feat, target)
    full_lookup: dict[tuple[str, str], float] = {
        (r["feature"], r["target"]): abs(r["pearson_r"])
        for r in full_dataset_records
    }

    fisher_records: list[dict] = []

    for target in TARGETS:
        # top 10 features for this target by full-dataset |r|
        target_feats = sorted(
            top_features,
            key=lambda f: full_lookup.get((f, target), 0.0),
            reverse=True,
        )[:10]

        for feat in target_feats:
            er = era_lookup[(feat, target)]
            pre_r = er["pre_2022_r"]
            post_r = er["post_2022_r"]
            r_delta = er["r_delta"]
            pre_n = er["pre_2022_n"]
            post_n = er["post_2022_n"]

            z1 = np.arctanh(np.clip(pre_r, -0.9999, 0.9999))
            z2 = np.arctanh(np.clip(post_r, -0.9999, 0.9999))
            se = np.sqrt(1.0 / (pre_n - 3) + 1.0 / (post_n - 3))
            z_stat = float((z2 - z1) / se)
            p_value = float(2.0 * (1.0 - stats.norm.cdf(abs(z_stat))))
            significant = bool(abs(r_delta) > R_DELTA_THRESHOLD and p_value < 0.05)

            fisher_records.append({
                "feature": feat,
                "target": target,
                "pre_2022_r": float(pre_r),
                "post_2022_r": float(post_r),
                "r_delta": float(r_delta),
                "z_stat": z_stat,
                "p_value": p_value,
                "significant": significant,
            })

    # print sorted by |r_delta| descending
    print(f"  {'Feature':<45} {'Target':<16} {'Pre r':>7} {'Post r':>7} {'r_delta':>8} {'z_stat':>8} {'p_value':>9} {'Sig':>5}")
    print("  " + "-" * 118)
    for rec in sorted(fisher_records, key=lambda r: abs(r["r_delta"]), reverse=True):
        sig_label = "YES" if rec["significant"] else "no"
        print(
            f"  {rec['feature']:<45} {rec['target']:<16}"
            f" {rec['pre_2022_r']:>7.4f} {rec['post_2022_r']:>7.4f}"
            f" {rec['r_delta']:>8.4f} {rec['z_stat']:>8.3f} {rec['p_value']:>9.4f} {sig_label:>5}"
        )

    return fisher_records


def step4_era_stability_summary(
    top_features: list[str],
    era_split_records: list[dict],
    fisher_records: list[dict],
) -> tuple[dict, dict]:
    n_features_tested = len(top_features)
    n_flagged_delta_015 = sum(1 for r in fisher_records if abs(r["r_delta"]) > R_DELTA_THRESHOLD)
    n_significantly_shifted = sum(1 for r in fisher_records if r["significant"])
    shifted_features = sorted({r["feature"] for r in fisher_records if r["significant"]})
    mean_abs_r_delta = float(np.mean([r["abs_r_delta"] for r in era_split_records]))
    correlation_structure_is_stable = bool(mean_abs_r_delta < MEAN_ABS_R_STABLE_THRESHOLD)

    summary = {
        "n_features_tested": n_features_tested,
        "n_flagged_delta_015": n_flagged_delta_015,
        "n_significantly_shifted": n_significantly_shifted,
        "mean_abs_r_delta": mean_abs_r_delta,
        "correlation_structure_is_stable": correlation_structure_is_stable,
        "shifted_features": shifted_features,
    }

    # design recommendation
    if len(shifted_features) > 5:
        separate_era_models_required = True
        post_2022_rules_flag_sufficient = False
        verdict = "separate_era_models_required"
        phase4 = "Train separate pre-2022 and post-2022 models; do not pool eras without interaction terms."
    else:
        separate_era_models_required = False
        post_2022_rules_flag_sufficient = True
        verdict = "post_2022_rules_flag_sufficient"
        phase4 = "Train unified model with post_2022_rules flag."

    rationale = (
        f"{len(shifted_features)} features showed significant correlation shifts "
        f"(|r_delta| > {R_DELTA_THRESHOLD}, p < 0.05); "
        f"mean |r_delta| = {mean_abs_r_delta:.4f} across top {n_features_tested} features × 3 targets. "
        f"Verdict: {verdict}. "
        f"Phase 4 implication: {phase4}"
    )

    recommendation = {
        "separate_era_models_required": separate_era_models_required,
        "post_2022_rules_flag_sufficient": post_2022_rules_flag_sufficient,
        "correlation_structure_is_stable": correlation_structure_is_stable,
        "rationale": rationale,
    }

    print("\nSTEP 4 — Era Stability Summary")
    print(f"  n_features_tested:             {n_features_tested}")
    print(f"  n_flagged_delta_015:           {n_flagged_delta_015}")
    print(f"  n_significantly_shifted:       {n_significantly_shifted}")
    print(f"  mean_abs_r_delta:              {mean_abs_r_delta:.4f}")
    print(f"  correlation_structure_is_stable: {correlation_structure_is_stable}")
    print(f"  shifted_features:              {shifted_features}")
    print(f"  Verdict: {verdict}")

    return summary, recommendation


def main() -> None:
    print("Loading features from mart...")
    df = load_features(min_games_played=15)
    print(f"  Total rows loaded: {len(df):,}")

    # Gate check
    pre_n = int(df[df["game_year"].isin(PRE_YEARS)].shape[0])
    post_n = int(df[df["game_year"].isin(POST_YEARS)].shape[0])
    print(f"  Gate check — pre-2022 era rows: {pre_n:,}")
    print(f"  Gate check — post-2022 era rows: {post_n:,}")
    assert pre_n >= 5_000, f"Gate requires >=5,000 pre-2022 rows, got {pre_n}"
    assert post_n >= 2_500, f"Gate requires >=2,500 post-2022 rows, got {post_n}"

    candidates = _candidate_features(df)
    print(f"  Candidate features (≥{MIN_ERA_ROWS} non-null in each era): {len(candidates)}")

    full_records, top_features = step1_full_dataset_correlations(df, candidates)
    print(f"\n  Top {len(top_features)} features selected: {top_features}")

    era_split_records = step2_era_split_correlations(df, top_features)
    fisher_records = step3_fisher_z_tests(df, top_features, era_split_records, full_records)
    era_summary, design_rec = step4_era_stability_summary(top_features, era_split_records, fisher_records)

    results = {
        "full_dataset_correlations": full_records,
        "top_features_selected": top_features,
        "era_split_correlations": era_split_records,
        "fisher_z_tests": fisher_records,
        "era_stability_summary": era_summary,
        "design_recommendation": design_rec,
    }

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evaluation")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "era_split_corr_stability_results.json")

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, cls=_NumpyEncoder)
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
