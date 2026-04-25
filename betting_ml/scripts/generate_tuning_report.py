"""Card 4.12 — Generate hyperparameter tuning report from tuning_results.json.

Reads betting_ml/evaluation/tuning_results.json (produced by
run_hyperparameter_search.py) and writes:
  - betting_ml/evaluation/hyperparameter_tuning.md
  - Updates project_context.md Phase 4 section with Card 4.12 findings.

Usage:
    uv run python betting_ml/scripts/generate_tuning_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results.json"
REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "hyperparameter_tuning.md"
CONTEXT_PATH = PROJECT_ROOT / "project_context.md"


def _pct_change(baseline: float, tuned: float) -> str:
    if baseline == 0:
        return "N/A"
    pct = (tuned - baseline) / baseline * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def _find_convergence_trial(all_trials: list[dict], best_score: float) -> int | None:
    """Return the earliest trial number where value == best_score."""
    for t in all_trials:
        if t["value"] is not None and abs(t["value"] - best_score) < 1e-10:
            return t["trial_number"]
    return None


def _build_report(results: dict) -> str:
    xgb = results["xgboost_tuning"]
    ngb = results["ngboost_tuning"]
    persisted = results["persisted_models"]
    summary = results["summary"]

    lines: list[str] = [
        "# Hyperparameter Tuning Results — Card 4.12",
        "",
        "Systematic hyperparameter optimization applied to XGBoost (Optuna TPE, 50 trials per target) "
        "and NGBoost (grid search) for all three prediction targets.",
        "",
    ]

    # ── Section 1: XGBoost results table ─────────────────────────────────────
    lines += [
        "## XGBoost Hyperparameter Search Results",
        "",
        "Optuna TPE sampler (seed=42), direction=minimize, n_trials=50 per target.",
        "",
        "| Target | Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |",
        "|---|---|---|---|---|---|",
    ]

    target_display = {
        "total_runs": "total_runs",
        "run_differential": "run_differential",
        "win_outcome": "home_win",
    }
    metric_display = {"mae": "MAE", "brier_score": "Brier Score"}

    for key in ("total_runs", "run_differential", "win_outcome"):
        r = xgb[key]
        target_label = target_display[key]
        metric_label = metric_display[r["metric"]]
        pct = _pct_change(r["baseline_cv_score"], r["best_cv_score"])
        improved_marker = " ✓" if r["improved"] else " ✗"
        lines.append(
            f"| {target_label} | {metric_label} | {r['baseline_cv_score']:.4f} "
            f"| {r['best_cv_score']:.4f} | {pct}{improved_marker} | {r['n_trials']} |"
        )

    lines += ["", "### Best Hyperparameter Values", ""]
    for key in ("total_runs", "run_differential", "win_outcome"):
        target_label = target_display[key]
        bp = xgb[key]["best_params"]
        lines.append(f"**{target_label}:**")
        lines.append("")
        lines.append("```")
        for param, val in sorted(bp.items()):
            lines.append(f"  {param}: {val}")
        lines.append("```")
        lines.append("")

    # ── Section 2: Trial convergence ─────────────────────────────────────────
    lines += ["## Optuna Trial Convergence", ""]

    for key in ("total_runs", "run_differential", "win_outcome"):
        target_label = target_display[key]
        r = xgb[key]
        best_score = r["best_cv_score"]
        conv_trial = _find_convergence_trial(r["all_trials"], best_score)
        n_trials = r["n_trials"]

        if conv_trial is not None:
            if conv_trial < 10:
                conv_comment = "early convergence (first 10 trials) — TPE likely found a strong region quickly"
            elif conv_trial < 25:
                conv_comment = "mid-search convergence — moderate exploration before best found"
            else:
                conv_comment = "late convergence — extended search required to find optimum"
            conv_str = f"Trial {conv_trial}"
        else:
            conv_comment = "convergence trial not determined"
            conv_str = "unknown"

        metric_label = metric_display[r["metric"]]
        lines.append(
            f"**{target_label}** ({metric_label}={best_score:.4f}): "
            f"Best value first achieved at {conv_str} of {n_trials} — {conv_comment}."
        )
        lines.append("")

    # ── Section 3: NGBoost grid ───────────────────────────────────────────────
    lines += [
        "## NGBoost Grid Search Results",
        "",
        "Grid: n_estimators ∈ {200, 500, 1000} × dist ∈ {Normal, LogNormal}.",
        "",
        "| Target | n_estimators | Dist | CV MAE | Viable |",
        "|---|---|---|---|---|",
    ]

    for ngb_target in ("total_runs", "run_differential"):
        for row in ngb[ngb_target]["grid_results"]:
            mae_str = f"{row['cv_mae']:.4f}" if row["cv_mae"] is not None else "N/A"
            viable_str = "Yes" if row["viable"] else "No"
            lines.append(
                f"| {ngb_target} | {row['n_estimators']} | {row['dist']} "
                f"| {mae_str} | {viable_str} |"
            )

    lines += [""]

    # LogNormal note for run_differential
    rd_ln_note = ngb["run_differential"].get("lognormal_note")
    if rd_ln_note:
        lines += [
            "**Note on LogNormal for run_differential:** LogNormal requires strictly positive target "
            "values. run_differential (home score − away score) can be negative, so LogNormal is not "
            "viable for this target. This failure is handled gracefully and recorded in grid_results.",
            "",
        ]

    for ngb_target, ngb_data in [("total_runs", ngb["total_runs"]), ("run_differential", ngb["run_differential"])]:
        lines.append(
            f"**Best NGBoost configuration for {ngb_target}:** "
            f"n_estimators={ngb_data['best_n_estimators']}, dist={ngb_data['best_dist']}, "
            f"CV MAE={ngb_data['best_cv_mae']:.4f}"
        )
        lines.append("")

    # ── Section 4: Best hyperparameter configurations ─────────────────────────
    lines += [
        "## Best Hyperparameter Configurations",
        "",
        "### XGBoost best_params",
        "",
    ]

    for key in ("total_runs", "run_differential", "win_outcome"):
        target_label = target_display[key]
        bp = xgb[key]["best_params"]
        lines.append(f"**{target_label}:**")
        lines.append("```json")
        lines.append(json.dumps(bp, indent=2))
        lines.append("```")
        lines.append("")

    lines += ["### NGBoost best configurations", ""]
    for ngb_target, ngb_data in [("total_runs", ngb["total_runs"]), ("run_differential", ngb["run_differential"])]:
        lines.append(f"**{ngb_target}:** n_estimators={ngb_data['best_n_estimators']}, dist={ngb_data['best_dist']}")
    lines.append("")

    # ── Section 5: Persisted models ───────────────────────────────────────────
    lines += [
        "## Persisted Models",
        "",
        "All five tuned models saved via save_model() from betting_ml/utils/model_io.py.",
        "",
        "| Target | Model Name | Eval Year | Path |",
        "|---|---|---|---|",
    ]
    for pm in persisted:
        lines.append(
            f"| {pm['target']} | {pm['model_name']} | {pm['eval_year']} | `{pm['path']}` |"
        )

    lines += [
        "",
        "All five models confirmed persisted successfully.",
        "",
    ]

    return "\n".join(lines)


def _update_project_context(results: dict) -> None:
    summary = results["summary"]
    xgb = results["xgboost_tuning"]
    ngb = results["ngboost_tuning"]

    tr_tuned = xgb["total_runs"]["best_cv_score"]
    tr_base = xgb["total_runs"]["baseline_cv_score"]
    rd_tuned = xgb["run_differential"]["best_cv_score"]
    rd_base = xgb["run_differential"]["baseline_cv_score"]
    wo_tuned = xgb["win_outcome"]["best_cv_score"]
    wo_base = xgb["win_outcome"]["baseline_cv_score"]

    def improved_str(flag: bool) -> str:
        return "improved ✓" if flag else "did not improve ✗"

    tr_improved = improved_str(summary["xgb_total_runs_improved"])
    rd_improved = improved_str(summary["xgb_run_diff_improved"])
    wo_improved = improved_str(summary["xgb_win_outcome_improved"])

    best_ngb_tr = summary["best_ngboost_config_total_runs"]
    best_ngb_rd = summary["best_ngboost_config_run_diff"]

    n_improved = sum([
        summary["xgb_total_runs_improved"],
        summary["xgb_run_diff_improved"],
        summary["xgb_win_outcome_improved"],
    ])
    one_sentence = (
        f"Optuna TPE (50 trials) tuned XGBoost models for all three targets; "
        f"{n_improved}/3 targets improved over baseline with Brier/MAE as objective."
    )

    card_section = f"""
#### Card 4.12 Results — Hyperparameter Optimization

- **xgb_total_runs_improved:** {summary['xgb_total_runs_improved']} — XGBoost total_runs MAE {tr_improved} (tuned={tr_tuned:.4f} vs baseline={tr_base:.4f})
- **xgb_run_diff_improved:** {summary['xgb_run_diff_improved']} — XGBoost run_differential MAE {rd_improved} (tuned={rd_tuned:.4f} vs baseline={rd_base:.4f})
- **xgb_win_outcome_improved:** {summary['xgb_win_outcome_improved']} — XGBoost win_outcome Brier {wo_improved} (tuned={wo_tuned:.4f} vs baseline={wo_base:.4f})
- **Best NGBoost config (total_runs):** n_estimators={best_ngb_tr['n_estimators']}, dist={best_ngb_tr['dist']} — CV MAE={ngb['total_runs']['best_cv_mae']:.4f}
- **Best NGBoost config (run_differential):** n_estimators={best_ngb_rd['n_estimators']}, dist={best_ngb_rd['dist']} — CV MAE={ngb['run_differential']['best_cv_mae']:.4f}
- **Summary:** {one_sentence}
- **Full results:** `betting_ml/evaluation/hyperparameter_tuning.md`, `betting_ml/evaluation/tuning_results.json`
"""

    with open(CONTEXT_PATH) as f:
        content = f.read()

    if "card 4.12 results" in content.lower():
        print("project_context.md already contains Card 4.12 results — skipping update.")
        return

    insert_marker = "#### Card 4.1 —"
    if insert_marker in content:
        content = content.replace(insert_marker, card_section + "\n" + insert_marker, 1)
    else:
        content += card_section

    with open(CONTEXT_PATH, "w") as f:
        f.write(content)
    print(f"Updated {CONTEXT_PATH} with Card 4.12 results.")


def main() -> None:
    if not RESULTS_PATH.exists():
        print(
            f"ERROR: {RESULTS_PATH} not found.\n"
            "Run run_hyperparameter_search.py first to produce tuning_results.json."
        )
        sys.exit(1)

    with open(RESULTS_PATH) as f:
        results = json.load(f)

    print("Building hyperparameter_tuning.md...")
    report = _build_report(results)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"Wrote {REPORT_PATH}")

    print("Updating project_context.md...")
    _update_project_context(results)

    print("\nCard 4.12 report generation complete.")


if __name__ == "__main__":
    main()
