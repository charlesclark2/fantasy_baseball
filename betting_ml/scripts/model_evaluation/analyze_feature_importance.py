"""Card 7.MB Task 3 — SHAP + XGBoost gain feature importance on fold_2025.

Fits XGBClassifier (baseline hyperparams) on the fold_2025 training split,
computes SHAP values via TreeExplainer, and cross-checks with XGBoost gain
importance. Flags prune candidates and noise-risk features.

Outputs:
    betting_ml/evaluation/model_evaluation/shap_importance_fold2025.png
    betting_ml/evaluation/model_evaluation/feature_importance_v1.parquet

Usage:
    uv run python betting_ml/scripts/model_evaluation/analyze_feature_importance.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS
from betting_ml.utils.feature_hygiene import flag_identifier_features

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_FOLD = "fold_2025"

_NON_FEAT = _NON_FEATURE_COLS | {"split"}

# Phase 7 feature group prefixes — these are the newest, most likely to be noisy
_PHASE7_GROUPS = {
    "starter_velo", "starter_pitch_mix", "starter_spin",
    "elo", "oaa", "pythagorean",
    "injury", "injured",
    "lineup_archetype",
    "sharp", "market", "odds",
}


def _infer_feature_group(col: str) -> str:
    """Map a column name to a semantic feature group."""
    # Strip home_/away_ prefix for sub-group detection
    stripped = col
    for prefix in ("home_", "away_"):
        if col.startswith(prefix):
            stripped = col[len(prefix):]
            break

    if stripped.startswith("starter_"):
        sub = "_".join(stripped.split("_")[1:3])
        return f"starter_{sub}"
    if stripped.startswith("bullpen") or stripped.startswith("bp_"):
        return "bullpen"
    if stripped.startswith("off_"):
        return "team_offense"
    if stripped.startswith("pit_"):
        return "team_pitching"
    if stripped.startswith("vs_lhp") or stripped.startswith("vs_rhp"):
        return "platoon_splits"
    if stripped.startswith("avg_"):
        return "rolling_batting"
    if stripped.startswith("win_rate") or stripped.startswith("win_pct") or stripped.startswith("streak"):
        return "season_record"
    if stripped.startswith("games_played") or stripped.startswith("wins") or stripped.startswith("losses"):
        return "season_record"
    if stripped.startswith("pythagorean"):
        return "pythagorean"
    if stripped.startswith("elo"):
        return "elo"
    if stripped.startswith("oaa"):
        return "oaa"
    if stripped.startswith("injury") or stripped.startswith("injured"):
        return "injury"
    if stripped.startswith("lineup_archetype"):
        return "lineup_archetype"
    if stripped.startswith("closer") or stripped.startswith("reliever"):
        return "bullpen"
    if stripped.startswith("days_rest") or stripped.startswith("consecutive"):
        return "schedule"
    if stripped.startswith("moneyline") or stripped.startswith("implied_prob"):
        return "market"

    # Context / park / weather
    for kw in ("ump_", "park_", "elevation", "temp_", "humidity", "wind_",
               "center_ft", "left_ft", "right_ft"):
        if col.startswith(kw) or stripped.startswith(kw):
            return "park_weather_ump"

    for kw in ("market_", "odds_", "sharp_", "over_", "under_", "totals_"):
        if col.startswith(kw):
            return "market"

    if col.startswith("total_") or col.startswith("runs_"):
        return "totals"
    if col.startswith("ml_") or col.startswith("is_"):
        return "market"

    return "other"


def _is_phase7(group: str) -> bool:
    return any(group.startswith(p) or group == p for p in _PHASE7_GROUPS)


def _apply_identifier_flag(df: pd.DataFrame, values: pd.DataFrame) -> pd.DataFrame:
    """Add Story 30.1 identifier columns and fold them into prune_candidate.

    `df` must contain a `feature` column and an `importance_prune` column.
    `values` is the raw (pre-imputation) feature frame for cardinality stats.
    Returns `df` with `identifier_risk`, `identifier_reason`, and a
    `prune_candidate = importance_prune OR identifier_risk` column.
    """
    flags = flag_identifier_features(df["feature"].tolist(), values=values)
    df = df.merge(
        flags[["identifier_risk", "cardinality", "card_ratio", "reason"]].rename(
            columns={"reason": "identifier_reason"}
        ),
        left_on="feature",
        right_index=True,
        how="left",
    )
    df["identifier_risk"] = df["identifier_risk"].fillna(False).astype(bool)
    df["prune_candidate"] = df["importance_prune"] | df["identifier_risk"]
    return df


def reflag_only() -> None:
    """Fast path: re-apply the identifier flagger to the existing parquet.

    Reads the persisted feature_importance_v1.parquet and the fold feature
    frame, recomputes the identifier flags + prune_candidate, and rewrites the
    parquet — WITHOUT refitting XGBoost/SHAP. Used to demonstrate that the
    updated flagger now catches the identifier columns (Story 30.1 AC).
    """
    out = _OUTPUT_DIR / "feature_importance_v1.parquet"
    df = pd.read_parquet(out)
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{_FOLD}.parquet")
    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)

    # Backwards-compat: older parquet has `prune_candidate` as the importance-only
    # flag. Preserve it under `importance_prune` before re-deriving.
    if "importance_prune" not in df.columns:
        df = df.rename(columns={"prune_candidate": "importance_prune"})

    avail = [c for c in df["feature"] if c in tr_f.columns]
    df = _apply_identifier_flag(df, tr_f[avail])

    flagged = df[df["identifier_risk"]].sort_values("mean_abs_shap", ascending=False)
    print(f"=== Re-flag only — {out.name} ===")
    print(f"Identifier-risk features now flagged: {len(flagged)}")
    cols = ["feature", "mean_abs_shap", "cardinality", "card_ratio",
            "importance_prune", "identifier_risk", "prune_candidate"]
    print(flagged[cols].to_string(index=False))
    df.to_parquet(out, index=False)
    print(f"\nRewrote {out}")


def main() -> None:
    print(f"=== Feature Importance Analysis — {_FOLD} ===\n")

    # ── Load fold ────────────────────────────────────────────────────────────
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{_FOLD}.parquet")
    tgt  = pd.read_parquet(_OUTPUT_DIR / f"targets_{_FOLD}.parquet")

    feat_cols = [c for c in feat.columns if c not in _NON_FEAT]

    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)
    tr_t = tgt[tgt["split"] == "train"].reset_index(drop=True)

    if "game_date" in tr_f.columns:
        sort_idx = tr_f["game_date"].argsort()
        tr_f = tr_f.iloc[sort_idx].reset_index(drop=True)
        tr_t = tr_t.iloc[sort_idx].reset_index(drop=True)

    X_tr = tr_f[feat_cols].values.astype(np.float32)
    y_tr = tr_t["home_win"].values.astype(np.float32)
    valid = ~np.isnan(y_tr)
    X_tr, y_tr = X_tr[valid], y_tr[valid]

    print(f"Training rows: {len(X_tr)}, features: {X_tr.shape[1]}")

    # ── Fit XGBoost (baseline hyperparams) ──────────────────────────────────
    print("Fitting XGBClassifier…", flush=True)
    clf = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, n_jobs=-1,
    )
    clf.fit(X_tr, y_tr)

    # ── XGBoost native gain importance ───────────────────────────────────────
    print("Computing XGBoost gain importance…", flush=True)
    gain_scores = clf.get_booster().get_score(importance_type="gain")
    # get_score uses f0, f1, … indices when trained on arrays
    gain_arr = np.array([
        gain_scores.get(f"f{i}", 0.0) for i in range(len(feat_cols))
    ])
    # Normalise to sum = 1
    gain_sum = gain_arr.sum()
    if gain_sum > 0:
        gain_arr = gain_arr / gain_sum

    # ── SHAP values ──────────────────────────────────────────────────────────
    print("Computing SHAP values (TreeExplainer)…", flush=True)
    explainer = shap.TreeExplainer(clf)
    shap_values = explainer.shap_values(X_tr)  # shape (n_samples, n_features)
    mean_abs_shap = np.abs(shap_values).mean(axis=0)

    # ── SHAP summary bar plot ────────────────────────────────────────────────
    print("Saving SHAP summary bar plot…", flush=True)
    fig, ax = plt.subplots(figsize=(10, 16))
    shap.summary_plot(
        shap_values, X_tr,
        feature_names=feat_cols,
        plot_type="bar",
        max_display=40,
        show=False,
    )
    plt.tight_layout()
    png_path = _OUTPUT_DIR / "shap_importance_fold2025.png"
    plt.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved → {png_path}")

    # ── Build importance DataFrame ────────────────────────────────────────────
    print("Building feature importance table…", flush=True)
    groups = [_infer_feature_group(c) for c in feat_cols]
    median_shap = float(np.median(mean_abs_shap))

    df = pd.DataFrame({
        "feature":           feat_cols,
        "mean_abs_shap":     mean_abs_shap,
        "xgb_gain_importance": gain_arr,
        "feature_group":     groups,
    })

    df["importance_prune"] = (
        (df["mean_abs_shap"] < 0.001) &
        (df["xgb_gain_importance"] < 0.0005)
    )

    df["noise_risk"] = (
        df["feature_group"].apply(_is_phase7) &
        (df["mean_abs_shap"] < median_shap)
    )

    # Story 30.1 — identifier/temporal flagger. Importance-only pruning CANNOT
    # catch a memorized identifier (home_starter_pitcher_id is rank #12 by SHAP),
    # so flag by name/cardinality and OR it into prune_candidate.
    df = _apply_identifier_flag(df, tr_f[feat_cols])

    df = df.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    # ── Summary stats ─────────────────────────────────────────────────────────
    n_prune = df["prune_candidate"].sum()
    n_noise = df["noise_risk"].sum()
    n_ident = df["identifier_risk"].sum()
    print(f"\nTotal features:     {len(df)}")
    print(f"Prune candidates:   {n_prune}  (importance-prune OR identifier-risk)")
    print(f"Identifier-risk:    {n_ident}  (name *_id/*_pk/game_year/season/*_cluster_id or high-card int)")
    print(f"Noise-risk:         {n_noise}  (Phase-7 group AND below median SHAP)")
    ident_feats = df.loc[df["identifier_risk"], "feature"].tolist()
    if ident_feats:
        print(f"  identifier features: {ident_feats}")
    print(f"Median SHAP:        {median_shap:.5f}")
    print(f"\nTop 20 features by mean |SHAP|:")
    print(df[["feature","mean_abs_shap","xgb_gain_importance","feature_group"]].head(20).to_string(index=False))

    print(f"\nGroup summary (mean |SHAP|):")
    grp = (
        df.groupby("feature_group")["mean_abs_shap"]
        .agg(["mean","count"])
        .sort_values("mean", ascending=False)
    )
    print(grp.to_string())

    # ── Write parquet ─────────────────────────────────────────────────────────
    out = _OUTPUT_DIR / "feature_importance_v1.parquet"
    df.to_parquet(out, index=False)
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Card 7.MB / Story 30.1 feature-importance flagger")
    parser.add_argument(
        "--reflag-only", action="store_true",
        help="Re-apply the Story 30.1 identifier flagger to the existing parquet "
             "(no XGBoost/SHAP refit). Demonstrates the identifier columns now flag.",
    )
    args = parser.parse_args()
    if args.reflag_only:
        reflag_only()
    else:
        main()
