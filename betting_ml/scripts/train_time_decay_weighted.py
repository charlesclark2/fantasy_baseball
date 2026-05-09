"""Card 8.N — Time-decay weighted retrain for all three production models.

Applies exponential decay sample_weights (half-life = 162 games) to all three
production model training runs (home_win, total_runs, run_differential).
For each target:
  1. Runs temporal CV with decay sample_weights → records CV metric.
  2. Compares to unweighted baseline from model_registry.yaml.
  3. Trains final weighted artifact on the full 2021+ window.
  4. Promotes (updates model_registry.yaml) if weighted metric is better.
Writes betting_ml/evaluation/time_decay_weighting_impact.md.

Run from project root (~45–90 min for NGBoost):
    uv run python betting_ml/scripts/train_time_decay_weighted.py
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.sample_weights import compute_sample_weights
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_REGISTRY_PATH = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
_EVAL_DIR = PROJECT_ROOT / "betting_ml" / "evaluation"
_REPORT_PATH = _EVAL_DIR / "time_decay_weighting_impact.md"

# home_win elasticnet hyperparameters (from Card 7.MB / model_registry)
_ENET_C = 0.01
_ENET_NON_FEAT = _NON_FEATURE_COLS | {"split"}

# total_runs NGBoost hyperparameters (v2)
_TR_N_ESTIMATORS = 500
_TR_MAX_DEPTH = 3

# run_differential NGBoost hyperparameters (v1)
_RD_N_ESTIMATORS = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _impute_align(
    X_train_raw: pd.DataFrame,
    X_eval_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pipe = build_imputation_pipeline()
    Xtr = pipe.fit_transform(X_train_raw).select_dtypes(include=[np.number])
    Xev = pipe.transform(X_eval_raw)
    Xev = Xev[[c for c in Xtr.columns if c in Xev.columns]]
    Xev = Xev.reindex(columns=Xtr.columns, fill_value=0.0)
    return Xtr, Xev


def _get_eval_year(df: pd.DataFrame, idx: pd.Index) -> int:
    return int(df.loc[idx, "game_year"].iloc[0])


def _load_registry() -> dict:
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f)


def _save_registry(reg: dict) -> None:
    with open(_REGISTRY_PATH, "w") as f:
        yaml.dump(reg, f, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# home_win: ElasticNet CV with decay weights
# ---------------------------------------------------------------------------

def run_home_win_cv(df: pd.DataFrame, feature_cols: list[str]) -> float:
    """Run temporal CV for home_win ElasticNet with decay sample_weights.
    Returns mean Brier score across folds.
    """
    from sklearn.model_selection import TimeSeriesSplit
    print("\n--- home_win: ElasticNet weighted CV ---")

    briers = []
    folds = list(all_season_splits(df, min_train_seasons=3))

    for train_idx, eval_idx in folds:
        eval_year = _get_eval_year(df, eval_idx)

        valid_train = df.loc[train_idx].dropna(subset=["home_win"])
        valid_eval = df.loc[eval_idx].dropna(subset=["home_win"])

        X_train_raw = valid_train[feature_cols]
        X_eval_raw = valid_eval[feature_cols]
        y_train = valid_train["home_win"].astype(int).values
        y_eval = valid_eval["home_win"].astype(int).values

        # Decay sample_weights for training fold
        sample_weights = None
        if "game_date" in df.columns:
            sample_weights = compute_sample_weights(valid_train, date_col="game_date").astype(np.float32)

        # Impute + scale inline (Pipeline's inner transforms don't need weights)
        imp = SimpleImputer(strategy="median")
        scl = StandardScaler()
        X_tr = scl.fit_transform(imp.fit_transform(X_train_raw.values.astype(np.float32)))
        X_ev = scl.transform(imp.transform(X_eval_raw.values.astype(np.float32)))

        clf = LogisticRegression(
            penalty="elasticnet", solver="saga", l1_ratio=0.5,
            C=_ENET_C, max_iter=2000, random_state=42,
        )
        clf.fit(X_tr, y_train, sample_weight=sample_weights)

        p = np.clip(clf.predict_proba(X_ev)[:, 1], 1e-7, 1 - 1e-7)
        brier = float(brier_score_loss(y_eval, p))
        briers.append(brier)
        print(f"  Fold {eval_year}: n={len(y_eval)} Brier={brier:.4f}")

    cv_brier = float(np.mean(briers))
    print(f"  Mean CV Brier (weighted): {cv_brier:.4f}")
    return cv_brier


def train_home_win_final(df: pd.DataFrame, feature_cols: list[str]) -> Path:
    """Train final weighted home_win artifact on full 2021+ window."""
    from sklearn.model_selection import TimeSeriesSplit

    print("\n  Training final home_win weighted artifact...")
    valid = df.dropna(subset=["home_win"])
    X_raw = valid[feature_cols].values.astype(np.float32)
    y = valid["home_win"].astype(int).values

    sample_weights = None
    if "game_date" in df.columns:
        sample_weights = compute_sample_weights(valid, date_col="game_date").astype(np.float32)

    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(
            penalty="elasticnet", solver="saga", l1_ratio=0.5,
            C=_ENET_C, max_iter=2000, random_state=42,
        )),
    ])
    t0 = time.time()
    pipeline.fit(X_raw, y, clf__sample_weight=sample_weights)
    print(f"  Fit complete in {time.time() - t0:.1f}s")

    out_path = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "elasticnet_decay_weighted.pkl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, out_path)
    print(f"  Saved: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# total_runs: NGBoost CV with decay weights
# ---------------------------------------------------------------------------

def run_total_runs_cv(df: pd.DataFrame, feature_cols: list[str]) -> float:
    """Run temporal CV for total_runs NGBRegressor with decay sample_weights.
    Returns mean MAE across folds.
    """
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    print("\n--- total_runs: NGBoost Normal weighted CV ---")

    maes = []
    folds = list(all_season_splits(df, min_train_seasons=3))

    for train_idx, eval_idx in folds:
        eval_year = _get_eval_year(df, eval_idx)

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values
        yev = df.loc[eval_idx, "total_runs"].values

        Xtr, Xev = _impute_align(Xtr_raw, Xev_raw)

        sample_weights = None
        if "game_date" in df.columns:
            sample_weights = compute_sample_weights(df.loc[train_idx], date_col="game_date")

        base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_TR_MAX_DEPTH)
        ngb = NGBRegressor(Dist=Normal, n_estimators=_TR_N_ESTIMATORS, Base=base, verbose=False)
        t0 = time.time()
        ngb.fit(Xtr.values, ytr, sample_weight=sample_weights)
        pred = ngb.predict(Xev.values)
        mae = float(np.mean(np.abs(pred - yev)))
        print(f"  Fold {eval_year}: n={len(yev)} MAE={mae:.4f} ({time.time()-t0:.0f}s)")
        maes.append(mae)

    cv_mae = float(np.mean(maes))
    print(f"  Mean CV MAE (weighted): {cv_mae:.4f}")
    return cv_mae


def train_total_runs_final(df: pd.DataFrame, feature_cols: list[str], version: str | None = None) -> Path:
    """Train final weighted total_runs artifact on full 2021+ window."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    print("\n  Training final total_runs weighted artifact...")
    pipe = build_imputation_pipeline()
    X_full = pipe.fit_transform(df[feature_cols]).select_dtypes(include=[np.number])
    y_full = df["total_runs"].values

    sample_weights = compute_sample_weights(df, date_col="game_date") if "game_date" in df.columns else None

    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_TR_MAX_DEPTH)
    ngb = NGBRegressor(Dist=Normal, n_estimators=_TR_N_ESTIMATORS, Base=base, verbose=False)
    t0 = time.time()
    ngb.fit(X_full.values, y_full, sample_weight=sample_weights)
    print(f"  Fit complete in {time.time()-t0:.0f}s")

    filename = f"ngboost_decay_weighted_{version}.pkl" if version else "ngboost_decay_weighted.pkl"
    out_path = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(ngb, out_path)
    print(f"  Saved: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# run_differential: NGBoost CV with decay weights
# ---------------------------------------------------------------------------

def run_run_diff_cv(df: pd.DataFrame, feature_cols: list[str]) -> float:
    """Run temporal CV for run_differential NGBRegressor with decay sample_weights.
    Returns mean MAE across folds.
    """
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    print("\n--- run_differential: NGBoost Normal weighted CV ---")

    maes = []
    folds = list(all_season_splits(df, min_train_seasons=3))

    for train_idx, eval_idx in folds:
        eval_year = _get_eval_year(df, eval_idx)

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "run_differential"].values
        yev = df.loc[eval_idx, "run_differential"].values

        Xtr, Xev = _impute_align(Xtr_raw, Xev_raw)

        sample_weights = None
        if "game_date" in df.columns:
            sample_weights = compute_sample_weights(df.loc[train_idx], date_col="game_date")

        base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=3)
        ngb = NGBRegressor(Dist=Normal, n_estimators=_RD_N_ESTIMATORS, Base=base, verbose=False)
        t0 = time.time()
        ngb.fit(Xtr.values, ytr, sample_weight=sample_weights)
        pred = ngb.predict(Xev.values)
        mae = float(np.mean(np.abs(pred - yev)))
        print(f"  Fold {eval_year}: n={len(yev)} MAE={mae:.4f} ({time.time()-t0:.0f}s)")
        maes.append(mae)

    cv_mae = float(np.mean(maes))
    print(f"  Mean CV MAE (weighted): {cv_mae:.4f}")
    return cv_mae


def train_run_diff_final(df: pd.DataFrame, feature_cols: list[str], version: str | None = None) -> Path:
    """Train final weighted run_differential artifact on full 2021+ window."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    print("\n  Training final run_differential weighted artifact...")
    pipe = build_imputation_pipeline()
    X_full = pipe.fit_transform(df[feature_cols]).select_dtypes(include=[np.number])
    y_full = df["run_differential"].values

    sample_weights = compute_sample_weights(df, date_col="game_date") if "game_date" in df.columns else None

    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=3)
    ngb = NGBRegressor(Dist=Normal, n_estimators=_RD_N_ESTIMATORS, Base=base, verbose=False)
    t0 = time.time()
    ngb.fit(X_full.values, y_full, sample_weight=sample_weights)
    print(f"  Fit complete in {time.time()-t0:.0f}s")

    filename = f"ngboost_decay_weighted_{version}.pkl" if version else "ngboost_decay_weighted.pkl"
    out_path = PROJECT_ROOT / "betting_ml" / "models" / "run_differential" / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(ngb, out_path)
    print(f"  Saved: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(results: dict) -> None:
    """Write time_decay_weighting_impact.md from results dict."""
    lines = [
        "# Time-Decay Training Weighting — Impact Report",
        "",
        "## Method",
        "",
        "Exponential decay: `weight_i = exp(-lambda * days_since_game_i)`, `lambda = ln(2)/162`.",
        "Half-life = 162 games (≈ one MLB regular season, ~182 days).",
        "Weights normalized to sum to n (preserves effective sample size for regularization scaling).",
        "Unweighted baselines sourced from `model_registry.yaml`.",
        "",
        "## CV Metric Comparison",
        "",
        "| Target           | Metric | Unweighted | Weighted | Delta   | Improved? |",
        "|------------------|--------|------------|----------|---------|-----------|",
    ]

    for target, info in results.items():
        metric = info["metric"]
        unweighted = info["unweighted"]
        weighted = info["weighted"]
        delta = weighted - unweighted
        improved = delta < 0  # lower is better for both Brier and MAE
        delta_str = f"{delta:+.4f}"
        improved_str = "Yes ✓" if improved else "No"
        lines.append(
            f"| {target:<16} | {metric:<6} | {unweighted:.4f}     | {weighted:.4f}   | {delta_str} | {improved_str}      |"
        )

    lines += [
        "",
        "## Artifacts",
        "",
    ]
    for target, info in results.items():
        artifact = info.get("artifact_path", "N/A")
        promoted = info.get("promoted", False)
        status = "promoted to production registry" if promoted else "saved (not promoted — weighted metric did not improve)"
        lines.append(f"- **{target}**: `{artifact}` — {status}")

    lines += [
        "",
        "## Conclusion",
        "",
    ]
    improved_targets = [t for t, info in results.items() if info["weighted"] < info["unweighted"]]
    if improved_targets:
        lines.append(
            f"Time-decay weighting improved CV metrics for: **{', '.join(improved_targets)}**. "
            "Weighted artifacts promoted to model_registry.yaml."
        )
    else:
        lines.append(
            "Time-decay weighting did not improve CV metrics on any target in this run. "
            "Weighted artifacts saved to `*_decay_weighted.pkl` paths but not promoted. "
            "The feature set may already capture temporal structure adequately, or the "
            "half-life parameter may need tuning."
        )
    lines += [
        "",
        "All weighted artifacts remain available for manual champion-challenger comparison.",
    ]

    _EVAL_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {_REPORT_PATH}")


# ---------------------------------------------------------------------------
# Registry promotion
# ---------------------------------------------------------------------------

def maybe_promote(registry: dict, target: str, info: dict) -> bool:
    """Promote weighted artifact into registry if metric improved."""
    if info["weighted"] >= info["unweighted"]:
        return False

    entry = registry.get(target, {})
    metric_key = "cv_brier" if info["metric"] == "Brier" else "cv_mae"
    artifact_rel = Path(info["artifact_path"]).relative_to(PROJECT_ROOT)

    # Keep rollback pointing to previous production artifact
    entry["rollback_artifact_path"] = entry.get("artifact_path", "")
    entry["artifact_path"] = str(artifact_rel)
    entry[metric_key] = round(info["weighted"], 4)

    import datetime
    entry["deployed_date"] = datetime.date.today().isoformat()
    existing_notes = entry.get("notes", "")
    entry["notes"] = (
        f"Card 8.N decay-weighted retrain (half_life=162). "
        f"Weighted {info['metric']}={info['weighted']:.4f} vs unweighted {info['unweighted']:.4f}. "
        + existing_notes
    )
    registry[target] = entry
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=None,
                        help="Version tag appended to artifact filenames (e.g. v3). "
                             "Omitting uses the default production paths. "
                             "With --version v3, total_runs saves to "
                             "ngboost_decay_weighted_v3.pkl (production artifact unchanged).")
    args, _ = parser.parse_known_args()
    _version = args.version

    print("=" * 65)
    print("Card 8.N — Time-Decay Weighted Retrain (half_life=162 games)")
    print("=" * 65)
    if _version:
        print(f"  Version tag: {_version} (artifacts will not overwrite production)")

    print("\nLoading features from Snowflake (2021+)...")
    df = load_features(min_games_played=15)
    print(f"  Loaded {len(df):,} rows; seasons {sorted(df['game_year'].unique())}")

    if "game_date" not in df.columns:
        print("WARNING: 'game_date' column not found in features — weights will be uniform.")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    print(f"  Retained feature columns available: {len(feature_cols)}")

    # ElasticNet feature set (all numeric non-target cols)
    import datetime as _dt
    _current_year = _dt.date.today().year
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    enet_feature_cols = [c for c in numeric_cols if c not in _ENET_NON_FEAT]

    # Drop in-progress current season for run_differential (can't validate targets)
    df_hist = df[df["game_year"] < _current_year].copy()
    print(f"  Historical rows (< {_current_year}): {len(df_hist):,}")

    registry = _load_registry()

    results: dict[str, dict] = {}

    # ---- home_win ----
    baseline_brier = float(registry.get("home_win", {}).get("cv_brier", float("nan")))
    print(f"\nhome_win baseline Brier (registry): {baseline_brier:.4f}")
    cv_brier_w = run_home_win_cv(df, enet_feature_cols)
    hw_artifact = train_home_win_final(df, enet_feature_cols)
    results["home_win"] = {
        "metric": "Brier",
        "unweighted": baseline_brier,
        "weighted": cv_brier_w,
        "artifact_path": str(hw_artifact),
        "promoted": False,
    }

    # ---- total_runs ----
    baseline_tr_mae = float(registry.get("total_runs", {}).get("cv_mae", float("nan")))
    print(f"\ntotal_runs baseline MAE (registry): {baseline_tr_mae:.4f}")
    cv_mae_tr = run_total_runs_cv(df, feature_cols)
    tr_artifact = train_total_runs_final(df, feature_cols, version=_version)
    results["total_runs"] = {
        "metric": "MAE",
        "unweighted": baseline_tr_mae,
        "weighted": cv_mae_tr,
        "artifact_path": str(tr_artifact),
        "promoted": False,
    }

    # ---- run_differential ----
    baseline_rd_mae = float(registry.get("run_differential", {}).get("cv_mae", float("nan")))
    print(f"\nrun_differential baseline MAE (registry): {baseline_rd_mae:.4f}")
    cv_mae_rd = run_run_diff_cv(df_hist, feature_cols)
    rd_artifact = train_run_diff_final(df_hist, feature_cols, version=_version)
    results["run_differential"] = {
        "metric": "MAE",
        "unweighted": baseline_rd_mae,
        "weighted": cv_mae_rd,
        "artifact_path": str(rd_artifact),
        "promoted": False,
    }

    # ---- Promotion ----
    print("\n--- Promotion decisions ---")
    promoted_any = False
    for target, info in results.items():
        promoted = maybe_promote(registry, target, info)
        info["promoted"] = promoted
        direction = "IMPROVED" if promoted else "no improvement"
        print(f"  {target}: weighted={info['weighted']:.4f} vs baseline={info['unweighted']:.4f} → {direction}")
        if promoted:
            promoted_any = True

    if promoted_any:
        _save_registry(registry)
        print(f"  Updated {_REGISTRY_PATH}")
    else:
        print("  No models promoted (weighted metrics did not beat baselines).")

    write_report(results)

    print("\n=== Summary ===")
    for target, info in results.items():
        delta = info["weighted"] - info["unweighted"]
        print(
            f"  {target:<20} {info['metric']} "
            f"unweighted={info['unweighted']:.4f} "
            f"weighted={info['weighted']:.4f} "
            f"delta={delta:+.4f}"
            + (" [PROMOTED]" if info["promoted"] else "")
        )
    print("\nCard 8.N complete.")


if __name__ == "__main__":
    main()
