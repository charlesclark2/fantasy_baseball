"""Card 8.P — Train LightGBM quantile models for total_runs.

Trains 5 LightGBM models (q=0.10, 0.25, 0.50, 0.75, 0.90) on the same temporal
CV splits as NGBoost v2 total_runs. Compares q50 CV metrics against the production
NGBoost v2 baseline from model_registry.yaml and conditionally promotes.

Promotion gates (ALL must pass to replace NGBoost v2):
  1. CV MAE (q50) <= NGBoost v2 total_runs MAE (from registry)
  2. std(OOF pred_q50) >= 1.5  (vs NGBoost std of 0.77 — must improve variance)
  3. |mean_residual (q50)| <= 0.5

IF PROMOTED: model_registry.yaml updated; artifacts at models/total_runs/lgb_quantile_*.pkl.
IF NOT:      artifacts archived to models/total_runs/archive/; NGBoost v2 unchanged.

Run from project root:
    uv run python betting_ml/scripts/train_quantile_totals.py [--weighted]

Story 31.4b — weather ABLATION in the quantile family (the monotone-LightGBM plan is
not buildable: LightGBM rejects monotone_constraints under the quantile objective).
The 4 weather features are already in the retained pool, so:
    uv run python betting_ml/scripts/train_quantile_totals.py --force-weather   # weather IN  (_wx)
    uv run python betting_ml/scripts/train_quantile_totals.py --drop-weather    # weather OUT (_noweather)
Compare CV MAE(q50) / std(pred) / coverage between the two to isolate weather's
effect on the (variance-healthy) quantile model now that weather is populated.
Distinct `_wx` / `_noweather` artifacts + reports leave the 10.10 baseline untouched.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.sample_weights import compute_sample_weights

_MODEL_DIR     = PROJECT_ROOT / "betting_ml" / "models" / "total_runs"
_EVAL_DIR      = PROJECT_ROOT / "betting_ml" / "evaluation"
_REGISTRY_PATH = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
_REPORT_PATH   = _EVAL_DIR / "quantile_regression_vs_ngboost.md"
# (Story 31.4b: reassigned to a distinct report path under --force-weather; see below.)

ALPHAS = [0.10, 0.25, 0.50, 0.75, 0.90]

_LGB_PARAMS = dict(
    objective="quantile",
    n_estimators=300,
    learning_rate=0.05,
    max_depth=5,
    num_leaves=31,
    n_jobs=-1,
    verbose=-1,
)

_WEIGHTED_FLAG = "--weighted" in sys.argv

# Story 31.4b — weather ablation in the quantile family.
#
# ORIGINAL PLAN (monotone-constrained LightGBM-quantile) is NOT BUILDABLE: LightGBM
# rejects `monotone_constraints` under `objective='quantile'` ("Cannot use
# monotone_constraints in quantile objective"). So the one inductive bias NGBoost
# couldn't express can't be added here either — a true-monotone weather model would
# need XGBoost (`reg:quantileerror` + monotone) or a monotone MEAN regressor with a
# separate spread, both a bigger build (see 31.4b notes).
#
# ALSO: the 4 weather features are ALREADY in the retained candidate pool
# (evaluation/feature_selection.md), so the quantile model already trains on weather
# — 10.10 just had ~null weather pre-repair (Story 31.4). The honest remaining cheap
# test is therefore a clean ABLATION on the NOW-POPULATED weather, unconstrained:
#   --force-weather  → weather IN  (tag `_wx`)      } same folds; compare CV MAE(q50)/
#   --drop-weather   → weather OUT (tag `_noweather`)} std/coverage to isolate weather.
_WEATHER_FEATURES = ["temp_f", "wind_speed_mph", "wind_component_mph", "humidity_pct"]
_FORCE_WEATHER = "--force-weather" in sys.argv
_DROP_WEATHER = "--drop-weather" in sys.argv
_MODEL_TAG = "_noweather" if _DROP_WEATHER else ("_wx" if _FORCE_WEATHER else "")
if _FORCE_WEATHER or _DROP_WEATHER:
    _REPORT_PATH = _EVAL_DIR / f"quantile_weather_31_4b{_MODEL_TAG}.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ngboost_baseline() -> float:
    reg = yaml.safe_load(_REGISTRY_PATH.read_text())
    return float(reg["total_runs"]["cv_mae"])


def _train_fold(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_ev: np.ndarray,
    sample_weights: np.ndarray | None = None,
) -> dict[float, np.ndarray]:
    """Train 5 quantile models for one CV fold; return OOF predictions."""
    preds = {}
    for alpha in ALPHAS:
        model = lgb.LGBMRegressor(alpha=alpha, **_LGB_PARAMS)
        model.fit(X_tr, y_tr, sample_weight=sample_weights)
        preds[alpha] = model.predict(X_ev)
    return preds


def _write_report(
    cv_mae: float,
    cv_std: float,
    cv_resid: float,
    pct_pred_over: float | None,
    coverage: dict[float, float],
    fold_results: list[dict],
    ngboost_mae: float,
    gate_mae: bool,
    gate_std: bool,
    gate_resid: bool,
    promoted: bool,
) -> None:
    gates_table = (
        "| Gate | Threshold | LightGBM q50 | NGBoost v2 | Pass? |\n"
        "|------|-----------|--------------|------------|-------|\n"
        f"| CV MAE (q50) | ≤ {ngboost_mae:.4f} | {cv_mae:.4f} | {ngboost_mae:.4f} | {'Y ✓' if gate_mae else 'N ✗'} |\n"
        f"| std(pred_q50) | ≥ 1.5 | {cv_std:.4f} | 0.77 | {'Y ✓' if gate_std else 'N ✗'} |\n"
        f"| abs(mean_residual) | ≤ 0.5 | {abs(cv_resid):.4f} | — | {'Y ✓' if gate_resid else 'N ✗'} |"
    )

    cov_rows = "\n".join(
        f"| {a:.2f} | {coverage[a]:.3f} | {a:.2f} |"
        for a in ALPHAS
    )
    coverage_table = (
        "| Alpha | OOF Coverage Rate | Expected |\n"
        "|-------|------------------|----------|\n"
        + cov_rows
    )

    fold_rows = "\n".join(
        f"| {f['eval_year']} | {f['n_train']:,} | {f['n_eval']:,} | {f['mae_q50']:.4f} |"
        for f in fold_results
    )
    fold_table = (
        "| Eval Year | Train N | Eval N | MAE(q50) |\n"
        "|-----------|---------|--------|----------|\n"
        + fold_rows
    )

    over_line = f"\n**pct_pred_q50 > market_totals_line**: {pct_pred_over:.3f}" if pct_pred_over is not None else ""

    conclusion = (
        "All three gates pass — LightGBM quantile models **promoted** to production. "
        "Update `predict_today.py` to dispatch `quantile_inference.predict_prob_over_line` for total_runs."
        if promoted else
        "At least one gate failed — NGBoost v2 remains in production. "
        "LightGBM quantile artifacts archived. Failed gates: "
        + ", ".join(g for g, p in [("MAE", gate_mae), ("std", gate_std), ("residual", gate_resid)] if not p)
        + "."
    )

    report = f"""# Quantile Regression vs. NGBoost v2 — Total Runs

## Method

LightGBM quantile regression (`objective='quantile'`) at 5 alpha levels: {ALPHAS}.
Training uses the same temporal CV splits as NGBoost v2 (`all_season_splits`, `min_train_seasons=3`).
Same retained feature set; same `build_imputation_pipeline()` preprocessing.
Half-life decay sample_weights applied: {'yes (--weighted)' if _WEIGHTED_FLAG else 'no'}.

## Promotion Gates

{gates_table}
{over_line}

## Per-Fold CV Results

{fold_table}

Mean CV MAE (q50): **{cv_mae:.4f}**  |  std(OOF pred_q50): **{cv_std:.4f}**  |  mean_residual: **{cv_resid:+.4f}**

## All-Quantile Coverage

{coverage_table}

*(Coverage rate = fraction of actuals below the predicted quantile. Ideally matches alpha.)*

## Conclusion

{conclusion}
"""
    _EVAL_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(report)
    print(f"\nReport written → {_REPORT_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if _WEIGHTED_FLAG:
        print("=== WEIGHTED MODE (Card 8.N time-decay sample_weights) ===\n")

    print("=== Card 8.P — LightGBM Quantile Regression for total_runs ===\n")

    print("Loading features (2021+)...")
    df = load_features(min_games_played=15)
    print(f"  {len(df):,} rows; seasons {sorted(df['game_year'].unique())}")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    # Story 31.4b — weather ablation. NOTE: monotone constraints are UNSUPPORTED under
    # LightGBM's quantile objective, so the run is unconstrained (true-monotone needs
    # XGBoost / a mean-model variant). The 4 weather cols are already in the retained
    # pool, so --force-weather is the "weather IN" arm and --drop-weather the baseline.
    if _FORCE_WEATHER:
        missing = [c for c in _WEATHER_FEATURES if c not in df.columns]
        if missing:
            sys.exit(
                f"--force-weather: {missing} not in feature_pregame_game_features. "
                "Rebuild the dbt weather feature (Story 31.4: "
                "`dbtf run --select feature_pregame_weather_features+ --full-refresh`) first."
            )
        present = [c for c in _WEATHER_FEATURES if c in feature_cols]
        added = [c for c in _WEATHER_FEATURES if c not in feature_cols]
        feature_cols += added
        print(f"  Story 31.4b [weather IN]: {len(present)} weather cols already retained, "
              f"{len(added)} force-added → {sorted(set(present) | set(added))}")
        print("  NOTE: monotone constraints SKIPPED — unsupported with LightGBM quantile objective.")
    elif _DROP_WEATHER:
        dropped = [c for c in _WEATHER_FEATURES if c in feature_cols]
        feature_cols = [c for c in feature_cols if c not in _WEATHER_FEATURES]
        print(f"  Story 31.4b [weather OUT — baseline]: dropped {len(dropped)} weather cols: {dropped}")
    print(f"  {len(feature_cols)} retained features")

    ngboost_mae = _ngboost_baseline()
    print(f"\nNGBoost v2 baseline CV MAE (from registry): {ngboost_mae:.4f}")

    # -------------------------------------------------------------------------
    # Season-forward CV
    # -------------------------------------------------------------------------
    print("\nRunning temporal CV...")

    oof_pred_q50: list[float]    = []
    oof_actual:   list[float]    = []
    oof_q_preds:  dict[float, list[float]] = {a: [] for a in ALPHAS}
    oof_totals_line: list[float] = []
    fold_results: list[dict]     = []

    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values
        yev = df.loc[eval_idx, "total_runs"].values

        pipe = build_imputation_pipeline()
        Xtr  = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev  = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        sw = (
            compute_sample_weights(df.loc[train_idx], date_col="game_date").astype(np.float32)
            if _WEIGHTED_FLAG and "game_date" in df.columns
            else None
        )

        t0 = time.time()
        fold_preds = _train_fold(Xtr.values, ytr, Xev.values, sample_weights=sw)
        elapsed = time.time() - t0

        q50 = fold_preds[0.50]
        mae_fold = float(np.mean(np.abs(q50 - yev)))
        print(f"  Fold {eval_year}: n_train={len(train_idx):,}  n_eval={len(eval_idx):,}  "
              f"MAE(q50)={mae_fold:.4f}  ({elapsed:.0f}s)")

        oof_pred_q50.extend(q50.tolist())
        oof_actual.extend(yev.tolist())
        for a in ALPHAS:
            oof_q_preds[a].extend(fold_preds[a].tolist())

        if "total_line_consensus" in df.columns:
            oof_totals_line.extend(df.loc[eval_idx, "total_line_consensus"].values.astype(float).tolist())

        fold_results.append({
            "eval_year": eval_year,
            "mae_q50":   mae_fold,
            "n_train":   len(train_idx),
            "n_eval":    len(eval_idx),
        })

    # -------------------------------------------------------------------------
    # Aggregate CV metrics
    # -------------------------------------------------------------------------
    oof_pred_q50_arr = np.array(oof_pred_q50)
    oof_actual_arr   = np.array(oof_actual)

    cv_mae   = float(np.mean(np.abs(oof_pred_q50_arr - oof_actual_arr)))
    cv_std   = float(np.std(oof_pred_q50_arr))
    cv_resid = float(np.mean(oof_pred_q50_arr - oof_actual_arr))

    coverage = {
        a: float(np.mean(oof_actual_arr < np.array(oof_q_preds[a])))
        for a in ALPHAS
    }

    pct_pred_over: float | None = None
    if oof_totals_line:
        tl = np.array(oof_totals_line)
        valid = ~np.isnan(tl)
        if valid.sum() > 0:
            pct_pred_over = float(np.mean(oof_pred_q50_arr[valid] > tl[valid]))

    print(f"\nCV MAE (q50):     {cv_mae:.4f}  (baseline {ngboost_mae:.4f})")
    print(f"std(pred_q50):    {cv_std:.4f}  (threshold ≥ 1.5)")
    print(f"mean_residual:    {cv_resid:+.4f}  (threshold |x| ≤ 0.5)")
    if pct_pred_over is not None:
        print(f"pct_pred > line:  {pct_pred_over:.3f}")

    # -------------------------------------------------------------------------
    # Promotion gates
    # -------------------------------------------------------------------------
    gate_mae   = cv_mae <= ngboost_mae
    gate_std   = cv_std >= 1.5
    gate_resid = abs(cv_resid) <= 0.5
    all_pass   = gate_mae and gate_std and gate_resid

    print(f"\nPromotion gates:")
    print(f"  MAE(q50) ≤ {ngboost_mae:.4f}:  {'PASS' if gate_mae else 'FAIL'}  ({cv_mae:.4f})")
    print(f"  std(pred) ≥ 1.5:          {'PASS' if gate_std else 'FAIL'}  ({cv_std:.4f})")
    print(f"  |mean_residual| ≤ 0.5:    {'PASS' if gate_resid else 'FAIL'}  ({abs(cv_resid):.4f})")
    print(f"  → {'ALL PASS — PROMOTE' if all_pass else 'GATE(S) FAILED — ARCHIVE'}")

    # -------------------------------------------------------------------------
    # Final models (full training set)
    # -------------------------------------------------------------------------
    print("\nTraining final models on full 2021+ dataset...")
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    pipe_full  = build_imputation_pipeline()
    X_full_raw = df[feature_cols]
    y_full     = df["total_runs"].values
    X_full     = pipe_full.fit_transform(X_full_raw).select_dtypes(include=[np.number])
    final_feature_cols = X_full.columns.tolist()

    sw_full = (
        compute_sample_weights(df, date_col="game_date").astype(np.float32)
        if _WEIGHTED_FLAG and "game_date" in df.columns
        else None
    )

    final_models: dict[float, lgb.LGBMRegressor] = {}
    artifact_paths: dict[float, Path] = {}
    for alpha in ALPHAS:
        t0 = time.time()
        model = lgb.LGBMRegressor(alpha=alpha, **_LGB_PARAMS)
        model.fit(X_full.values, y_full, sample_weight=sw_full)
        elapsed = time.time() - t0
        path = _MODEL_DIR / f"lgb_quantile{_MODEL_TAG}_{alpha:.2f}.pkl"
        joblib.dump(model, path)
        final_models[alpha]   = model
        artifact_paths[alpha] = path
        print(f"  q={alpha:.2f}: {elapsed:.0f}s  → {path.name}")

    feat_cols_path = _MODEL_DIR / f"lgb_quantile{_MODEL_TAG}_feature_columns.json"
    feat_cols_path.write_text(json.dumps(final_feature_cols, indent=0))
    print(f"  Feature columns: {feat_cols_path.name} ({len(final_feature_cols)} cols)")

    # -------------------------------------------------------------------------
    # Promotion / archive + model_registry.yaml update
    # -------------------------------------------------------------------------
    reg = yaml.safe_load(_REGISTRY_PATH.read_text())
    now_str = datetime.now(timezone.utc).isoformat()

    if all_pass:
        reg[f"total_runs_quantile{_MODEL_TAG}"] = {
            "model_type": "lgb_quantile",
            "alphas": ALPHAS,
            "artifacts": [str(artifact_paths[a].relative_to(PROJECT_ROOT)) for a in ALPHAS],
            "feature_columns_path": str(feat_cols_path.relative_to(PROJECT_ROOT)),
            "cv_mae_q50":       round(cv_mae, 4),
            "cv_std_q50":       round(cv_std, 4),
            "cv_mean_residual": round(cv_resid, 4),
            "promoted": True,
            "training_date": now_str,
            "notes": (
                "Card 8.P — quantile LightGBM promoted over NGBoost v2. "
                "predict_today.py must be updated to dispatch quantile_inference.predict_prob_over_line "
                "for total_runs."
            ),
        }
        _REGISTRY_PATH.write_text(yaml.dump(reg, default_flow_style=False, sort_keys=False))
        print(f"\nmodel_registry.yaml updated — quantile models promoted.")
        print("\nNEXT STEP: update predict_today.py to dispatch quantile_inference for total_runs.")
    else:
        archive_dir = _MODEL_DIR / "archive"
        archive_dir.mkdir(exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        for alpha in ALPHAS:
            src = artifact_paths[alpha]
            dst = archive_dir / f"lgb_quantile{_MODEL_TAG}_{alpha:.2f}_{ts}.pkl"
            src.rename(dst)
            artifact_paths[alpha] = dst

        failed_gates = [g for g, p in [("MAE", gate_mae), ("std", gate_std), ("residual", gate_resid)] if not p]
        reg[f"total_runs_quantile{_MODEL_TAG}"] = {
            "model_type": "lgb_quantile",
            "promoted": False,
            "gate_mae_pass":   gate_mae,
            "gate_std_pass":   gate_std,
            "gate_resid_pass": gate_resid,
            "cv_mae_q50":       round(cv_mae, 4),
            "cv_std_q50":       round(cv_std, 4),
            "cv_mean_residual": round(cv_resid, 4),
            "archive_path": str(archive_dir.relative_to(PROJECT_ROOT)),
            "archived_at": now_str,
            "notes": f"Card 8.P — not promoted. Failed gates: {', '.join(failed_gates)}. NGBoost v2 remains.",
        }
        _REGISTRY_PATH.write_text(yaml.dump(reg, default_flow_style=False, sort_keys=False))
        print(f"\nArchived to {archive_dir.relative_to(PROJECT_ROOT)} — model_registry.yaml updated.")
        print("NGBoost v2 remains in production for total_runs.")

    # -------------------------------------------------------------------------
    # Comparison report
    # -------------------------------------------------------------------------
    _write_report(
        cv_mae=cv_mae, cv_std=cv_std, cv_resid=cv_resid,
        pct_pred_over=pct_pred_over, coverage=coverage,
        fold_results=fold_results, ngboost_mae=ngboost_mae,
        gate_mae=gate_mae, gate_std=gate_std, gate_resid=gate_resid,
        promoted=all_pass,
    )


def _write_report(
    cv_mae: float,
    cv_std: float,
    cv_resid: float,
    pct_pred_over: float | None,
    coverage: dict[float, float],
    fold_results: list[dict],
    ngboost_mae: float,
    gate_mae: bool,
    gate_std: bool,
    gate_resid: bool,
    promoted: bool,
) -> None:
    gates_table = (
        "| Gate | Threshold | LightGBM q50 | NGBoost v2 | Pass? |\n"
        "|------|-----------|--------------|------------|-------|\n"
        f"| CV MAE (q50) | ≤ {ngboost_mae:.4f} | {cv_mae:.4f} | {ngboost_mae:.4f} | {'Y ✓' if gate_mae else 'N ✗'} |\n"
        f"| std(pred_q50) | ≥ 1.5 | {cv_std:.4f} | 0.77 | {'Y ✓' if gate_std else 'N ✗'} |\n"
        f"| abs(mean_residual) | ≤ 0.5 | {abs(cv_resid):.4f} | — | {'Y ✓' if gate_resid else 'N ✗'} |"
    )

    cov_rows = "\n".join(
        f"| {a:.2f} | {coverage.get(a, float('nan')):.3f} | {a:.2f} |"
        for a in ALPHAS
    )
    coverage_table = (
        "| Alpha | OOF Coverage Rate | Expected |\n"
        "|-------|------------------|----------|\n"
        + cov_rows
    )

    fold_rows = "\n".join(
        f"| {f['eval_year']} | {f['n_train']:,} | {f['n_eval']:,} | {f['mae_q50']:.4f} |"
        for f in fold_results
    )
    fold_table = (
        "| Eval Year | Train N | Eval N | MAE(q50) |\n"
        "|-----------|---------|--------|----------|\n"
        + fold_rows
    )

    over_line_str = (
        f"\n**pct_pred_q50 > total_line_consensus**: {pct_pred_over:.3f}"
        if pct_pred_over is not None
        else ""
    )

    if promoted:
        conclusion = (
            "All three gates pass — LightGBM quantile models **promoted** to production. "
            "`predict_today.py` must be updated to dispatch `quantile_inference.predict_prob_over_line` "
            "for total_runs instead of NGBoost."
        )
    else:
        failed = [g for g, p in [("MAE", gate_mae), ("std", gate_std), ("residual", gate_resid)] if not p]
        conclusion = (
            f"Gate(s) failed: **{', '.join(failed)}** — NGBoost v2 remains in production for total_runs. "
            "LightGBM quantile artifacts archived to `models/total_runs/archive/`."
        )

    report = f"""# Quantile Regression vs. NGBoost v2 — Total Runs

## Method

LightGBM quantile regression (`objective='quantile'`) at 5 alpha levels: {ALPHAS}.
Trained on the same temporal CV splits as NGBoost v2 (`all_season_splits`, `min_train_seasons=3`).
Same retained feature set and `build_imputation_pipeline()` preprocessing.
Half-life decay sample_weights: {'applied (--weighted)' if _WEIGHTED_FLAG else 'not applied'}.

## Promotion Gates

{gates_table}
{over_line_str}

## Per-Fold CV Results

{fold_table}

**Mean CV MAE (q50)**: {cv_mae:.4f}  |  **std(OOF pred_q50)**: {cv_std:.4f}  |  **mean_residual**: {cv_resid:+.4f}

## All-Quantile Coverage

{coverage_table}

*(Coverage rate = fraction of actuals below the predicted quantile. Should match alpha if well-calibrated.)*

## Conclusion

{conclusion}
"""
    _EVAL_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(report)
    print(f"Report written → {_REPORT_PATH}")


if __name__ == "__main__":
    main()
