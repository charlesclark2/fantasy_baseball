"""
evaluate_sub_model.py — Sub-model evaluation harness (Story 2.3)

Evaluates a trained sub-model against its registered target using walk-forward
season CV, calibration analysis, season-stability breakdown, and optional
version comparison. Produces a JSON metrics file and a human-readable report.

Usage:
    uv run python betting_ml/scripts/evaluate_sub_model.py \\
        --name run_env_v1 \\
        [--compare run_env_v2] \\
        [--coverage-mode drop|impute_with_indicator] \\
        [--target-window 2022-2026] \\
        [--output-dir models/sub_models/run_env_v1/]

IMPORTANT: This script does NOT import train_elasticnet_prod,
train_total_runs_prod, or train_run_diff_prod. Those scripts are for the
monolithic production models. Sub-model evaluation is standalone.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy import stats
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
_DEFAULT_OUTPUT_ROOT = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models"

# Monolithic train scripts must not be imported — enforced by CI AST check.
_FORBIDDEN_IMPORTS = {
    "train_elasticnet_prod",
    "train_total_runs_prod",
    "train_run_diff_prod",
}


# ---------------------------------------------------------------------------
# Registry access
# ---------------------------------------------------------------------------

def _load_registry() -> dict[str, Any]:
    with open(_REGISTRY_PATH) as fh:
        return yaml.safe_load(fh) or {}


def _get_entry(name: str) -> dict[str, Any]:
    registry = _load_registry()
    if name not in registry:
        raise KeyError(f"'{name}' not in sub_model_registry.yaml. Available: {sorted(registry)}")
    return registry[name]


# ---------------------------------------------------------------------------
# Artifact + feature loading
# ---------------------------------------------------------------------------

def _load_artifact(entry: dict[str, Any]):
    import joblib
    path = _PROJECT_ROOT / entry["artifact_path"]
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    return joblib.load(path)


def _load_feature_columns(entry: dict[str, Any]) -> list[str]:
    path = _PROJECT_ROOT / entry["feature_columns_path"]
    if not path.exists():
        raise FileNotFoundError(f"Feature columns file not found: {path}")
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Dataset loading from Snowflake
# ---------------------------------------------------------------------------

def _load_signals_from_snowflake(name: str, target_window: tuple[int, int]) -> pd.DataFrame:
    """Load stored signals from mart_sub_model_signals for evaluation."""
    from betting_ml.utils.data_loader import get_snowflake_connection

    start_year, end_year = target_window
    query = f"""
        select
            s.game_pk,
            s.side,
            s.signal_name,
            s.signal_value,
            s.signal_available,
            s.sub_model_version,
            g.game_year,
            g.game_date
        from baseball_data.betting.mart_sub_model_signals s
        join baseball_data.betting.mart_game_results g
          on s.game_pk = g.game_pk
        where s.sub_model_name = '{name}'
          and s.is_current = true
          and g.game_year between {start_year} and {end_year}
        order by g.game_date
    """
    conn = get_snowflake_connection()
    return pd.read_sql(query, conn)


def _load_target_from_snowflake(entry: dict[str, Any], target_window: tuple[int, int]) -> pd.DataFrame:
    """Load ground-truth target values from the registered source table."""
    from betting_ml.utils.data_loader import get_snowflake_connection

    target = entry["target"]
    table = target["source_table"]
    col = target["primary_column"]
    start_year, end_year = target_window

    # Derive game_year column if not directly available
    query = f"""
        select
            game_pk,
            {col} as target_value,
            game_date,
            extract(year from game_date) as game_year
        from {table}
        where extract(year from game_date) between {start_year} and {end_year}
          and {col} is not null
        order by game_date
    """
    conn = get_snowflake_connection()
    return pd.read_sql(query, conn)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    pearson_r, _ = stats.pearsonr(y_true, y_pred)
    spearman_r, _ = stats.spearmanr(y_true, y_pred)
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "pearson_r": round(float(pearson_r), 4),
        "spearman_r": round(float(spearman_r), 4),
        "n": int(len(y_true)),
    }


def _classification_metrics(y_true: np.ndarray, y_pred_prob: np.ndarray) -> dict[str, float]:
    brier = brier_score_loss(y_true, y_pred_prob)
    ll = log_loss(y_true, y_pred_prob)
    auc = roc_auc_score(y_true, y_pred_prob)
    return {
        "brier": round(float(brier), 4),
        "log_loss": round(float(ll), 4),
        "auc": round(float(auc), 4),
        "n": int(len(y_true)),
    }


def _detect_target_type(cv_metric: str | None) -> str:
    if cv_metric in {"brier", "log_loss", "auc"}:
        return "binary"
    return "regression"


# ---------------------------------------------------------------------------
# Calibration (reliability diagram values)
# ---------------------------------------------------------------------------

def _calibration_table(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_buckets: int = 10,
) -> list[dict[str, float]]:
    """
    Reliability diagram by predicted-value decile.
    Returns a list of dicts: {bucket, pred_mean, actual_mean, n}.
    """
    df = pd.DataFrame({"y_true": y_true, "y_pred": y_pred})
    df["bucket"] = pd.qcut(df["y_pred"], q=n_buckets, labels=False, duplicates="drop")
    result = []
    for bucket, grp in df.groupby("bucket"):
        result.append({
            "bucket": int(bucket),
            "pred_mean": round(float(grp["y_pred"].mean()), 4),
            "actual_mean": round(float(grp["y_true"].mean()), 4),
            "n": int(len(grp)),
        })
    return result


def _ece(calibration: list[dict[str, float]]) -> float:
    """Expected calibration error (weighted average absolute deviation)."""
    total_n = sum(r["n"] for r in calibration)
    if total_n == 0:
        return float("nan")
    ece = sum(abs(r["pred_mean"] - r["actual_mean"]) * r["n"] / total_n for r in calibration)
    return round(float(ece), 4)


# ---------------------------------------------------------------------------
# Walk-forward CV
# ---------------------------------------------------------------------------

def _walk_forward_cv(
    df: pd.DataFrame,
    model,
    feature_cols: list[str],
    target_col: str,
    cv_metric: str,
    min_train_seasons: int = 3,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """
    Run walk-forward season CV. Returns (aggregate_metrics, per_fold_rows).
    df must have 'game_year' column.
    """
    from betting_ml.utils.cv_splits import all_season_splits

    all_y_true, all_y_pred = [], []
    fold_rows = []

    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=min_train_seasons):
        train = df.loc[train_idx]
        eval_ = df.loc[eval_idx]
        if eval_.empty:
            continue

        X_train = train[feature_cols].values
        y_train = train[target_col].values
        X_eval = eval_[feature_cols].values
        y_eval = eval_[target_col].values

        model.fit(X_train, y_train)

        target_type = _detect_target_type(cv_metric)
        if target_type == "binary":
            y_pred = model.predict_proba(X_eval)[:, 1]
        else:
            y_pred = model.predict(X_eval)

        all_y_true.extend(y_eval)
        all_y_pred.extend(y_pred)

        eval_year = int(eval_["game_year"].iloc[0])
        if target_type == "binary":
            fold_metrics = _classification_metrics(np.array(y_eval), np.array(y_pred))
        else:
            fold_metrics = _regression_metrics(np.array(y_eval), np.array(y_pred))

        fold_rows.append({"eval_year": eval_year, **fold_metrics})

    y_true_arr = np.array(all_y_true)
    y_pred_arr = np.array(all_y_pred)
    target_type = _detect_target_type(cv_metric)
    if target_type == "binary":
        agg = _classification_metrics(y_true_arr, y_pred_arr)
    else:
        agg = _regression_metrics(y_true_arr, y_pred_arr)

    return agg, fold_rows


# ---------------------------------------------------------------------------
# Season-stability table
# ---------------------------------------------------------------------------

def _season_stability(
    df: pd.DataFrame,
    y_pred: np.ndarray,
    target_col: str,
    cv_metric: str,
) -> list[dict[str, Any]]:
    """Compute per-season metrics for the full eval set."""
    target_type = _detect_target_type(cv_metric)
    rows = []
    for year, grp in df.groupby("game_year"):
        idx = grp.index
        y_t = grp[target_col].values
        y_p = y_pred[df.index.get_indexer(idx)]
        if target_type == "binary":
            m = _classification_metrics(y_t, y_p)
        else:
            m = _regression_metrics(y_t, y_p)
        rows.append({"season": int(year), **m})
    return rows


# ---------------------------------------------------------------------------
# Coverage-mode handling
# ---------------------------------------------------------------------------

def _apply_coverage_mode(
    df: pd.DataFrame,
    feature_cols: list[str],
    coverage_mode: str,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Handle partially-available signals (e.g., bat tracking 2023-07+).

    coverage_mode='drop':
        Rows with ANY NULL in feature_cols are dropped.
    coverage_mode='impute_with_indicator':
        For each feature with nulls, impute to column mean and add a boolean
        <feature>_available indicator column.
    """
    if coverage_mode == "drop":
        before = len(df)
        df = df.dropna(subset=feature_cols).reset_index(drop=True)
        after = len(df)
        print(f"[coverage-mode=drop] Dropped {before - after} rows with NULL features "
              f"({after} remaining)")
        return df, feature_cols

    # impute_with_indicator
    new_cols = list(feature_cols)
    for col in feature_cols:
        if df[col].isna().any():
            indicator_col = f"{col}_available"
            df[indicator_col] = df[col].notna().astype(float)
            df[col] = df[col].fillna(df[col].mean())
            new_cols.append(indicator_col)
    return df, new_cols


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------

def _compare_versions(
    name_a: str,
    name_b: str,
    df: pd.DataFrame,
    target_col: str,
    cv_metric: str,
    coverage_mode: str,
) -> dict[str, Any]:
    """
    Run both versions against the same eval window and report deltas.
    Both models are evaluated on the portion of data where BOTH have signals.
    """
    entry_a = _get_entry(name_a)
    entry_b = _get_entry(name_b)
    model_a = _load_artifact(entry_a)
    model_b = _load_artifact(entry_b)
    feat_a = _load_feature_columns(entry_a)
    feat_b = _load_feature_columns(entry_b)

    shared_feat = sorted(set(feat_a) & set(feat_b))
    if not shared_feat:
        print(f"[WARNING] No overlapping features between {name_a} and {name_b}; "
              "using each model's own features independently.")

    target_type = _detect_target_type(cv_metric)

    def _eval_model(model, feat_cols, df_in):
        df_clean, cols_used = _apply_coverage_mode(df_in.copy(), feat_cols, coverage_mode)
        X = df_clean[cols_used].values
        y = df_clean[target_col].values
        if target_type == "binary":
            y_pred = model.predict_proba(X)[:, 1]
            return _classification_metrics(np.array(y), np.array(y_pred)), df_clean
        else:
            y_pred = model.predict(X)
            return _regression_metrics(np.array(y), np.array(y_pred)), df_clean

    metrics_a, _ = _eval_model(model_a, feat_a, df)
    metrics_b, _ = _eval_model(model_b, feat_b, df)

    delta = {}
    for k in metrics_a:
        if isinstance(metrics_a[k], (int, float)) and k != "n":
            delta[k] = round(metrics_b[k] - metrics_a[k], 4)

    return {
        name_a: metrics_a,
        name_b: metrics_b,
        "delta (b - a)": delta,
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _render_markdown_report(
    name: str,
    entry: dict[str, Any],
    cv_agg: dict[str, float],
    cv_folds: list[dict[str, Any]],
    calibration: list[dict[str, float]],
    ece: float,
    stability: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
    coverage_mode: str,
    target_window: tuple[int, int],
) -> str:
    lines = [
        f"# Sub-Model Evaluation Report: {name}",
        f"",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"",
        f"## Target",
        f"- Source table: `{entry['target']['source_table']}`",
        f"- Target column: `{entry['target']['primary_column']}`",
        f"- Grain: `{entry['target']['grain']}`",
        f"- Evaluation window: {target_window[0]}–{target_window[1]}",
        f"- Coverage mode: `{coverage_mode}`",
        f"",
        f"## Walk-Forward CV — Aggregate",
        "",
    ]
    for k, v in cv_agg.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Walk-Forward CV — Per Fold", ""]

    if cv_folds:
        headers = list(cv_folds[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in cv_folds:
            lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    else:
        lines.append("_No folds produced — check training window and min_train_seasons._")

    lines += ["", f"## Calibration (ECE = {ece})", ""]
    if calibration:
        lines.append("| bucket | pred_mean | actual_mean | n |")
        lines.append("|--------|-----------|-------------|---|")
        for r in calibration:
            lines.append(f"| {r['bucket']} | {r['pred_mean']} | {r['actual_mean']} | {r['n']} |")

    lines += ["", "## Season Stability", ""]
    if stability:
        headers = list(stability[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in stability:
            lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")

    if comparison:
        lines += ["", "## Version Comparison", ""]
        for label, metrics in comparison.items():
            lines.append(f"### {label}")
            if isinstance(metrics, dict):
                for k, v in metrics.items():
                    lines.append(f"- {k}: {v}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a sub-model against its registered target.")
    p.add_argument("--name", required=True, help="Registry entry name (e.g. run_env_v1)")
    p.add_argument("--compare", default=None,
                   help="Optional second entry to compare against (e.g. run_env_v2)")
    p.add_argument("--coverage-mode", choices=["drop", "impute_with_indicator"],
                   default="drop", help="How to handle partially-available features")
    p.add_argument("--target-window", default="2022-2026",
                   help="Evaluation window as YYYY-YYYY (e.g. 2022-2026)")
    p.add_argument("--output-dir", default=None,
                   help="Directory to write evaluation JSON and Markdown report")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    start_year, end_year = (int(y) for y in args.target_window.split("-"))
    target_window = (start_year, end_year)

    entry = _get_entry(args.name)
    model = _load_artifact(entry)
    feature_cols = _load_feature_columns(entry)
    target_col = entry["target"]["primary_column"]
    cv_metric = entry.get("cv_metric") or "mae"

    print(f"Loading signals for '{args.name}' ({start_year}–{end_year})...")
    signals_df = _load_signals_from_snowflake(args.name, target_window)

    print("Loading target values...")
    target_df = _load_target_from_snowflake(entry, target_window)

    # Merge signals → target
    if entry["target"]["grain"] == "game_pk_side":
        df = signals_df.merge(target_df, on=["game_pk", "game_date", "game_year"], how="inner")
    else:
        df = signals_df.merge(target_df, on=["game_pk", "game_date", "game_year"], how="inner")

    df = df.rename(columns={target_col: "target_value"})
    target_col_local = "target_value"

    df, feature_cols = _apply_coverage_mode(df, feature_cols, args.coverage_mode)

    print("Running walk-forward CV...")
    cv_agg, cv_folds = _walk_forward_cv(
        df, model, feature_cols, target_col_local, cv_metric
    )

    print("Computing calibration...")
    target_type = _detect_target_type(cv_metric)
    X_all = df[feature_cols].values
    if target_type == "binary":
        y_pred_all = model.predict_proba(X_all)[:, 1]
    else:
        y_pred_all = model.predict(X_all)
    calibration = _calibration_table(df[target_col_local].values, y_pred_all)
    ece = _ece(calibration)

    print("Computing season stability...")
    stability = _season_stability(df, y_pred_all, target_col_local, cv_metric)

    comparison = None
    if args.compare:
        print(f"Comparing {args.name} vs {args.compare}...")
        comparison = _compare_versions(
            args.name, args.compare, df, target_col_local, cv_metric, args.coverage_mode
        )

    # Output
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else _DEFAULT_OUTPUT_ROOT / args.name
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics_payload = {
        "name": args.name,
        "generated_at": ts,
        "target_window": args.target_window,
        "coverage_mode": args.coverage_mode,
        "cv_aggregate": cv_agg,
        "cv_folds": cv_folds,
        "calibration": calibration,
        "ece": ece,
        "season_stability": stability,
        "comparison": comparison,
    }
    json_path = output_dir / f"evaluation_{ts}.json"
    with open(json_path, "w") as fh:
        json.dump(metrics_payload, fh, indent=2)

    md = _render_markdown_report(
        args.name, entry, cv_agg, cv_folds, calibration, ece, stability,
        comparison, args.coverage_mode, target_window
    )
    md_path = output_dir / f"evaluation_{ts}.md"
    md_path.write_text(md)

    print(f"\n✓ Evaluation complete.")
    print(f"  JSON:     {json_path}")
    print(f"  Report:   {md_path}")
    print(f"\nCV aggregate ({cv_metric}):")
    for k, v in cv_agg.items():
        print(f"  {k}: {v}")
    if ece is not None:
        print(f"  ECE: {ece}")


if __name__ == "__main__":
    main()
