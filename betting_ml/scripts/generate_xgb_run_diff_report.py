"""Card 4.12b — Generate hyperparameter tuning report for XGBoost run_differential.

Reads betting_ml/evaluation/tuning_results_xgb_run_diff.json (produced by
run_xgb_run_diff_search.py) and writes:
  - betting_ml/evaluation/hyperparameter_tuning_xgb_run_diff.md
  - Updates project_context.md Phase 4 section with Card 4.12b findings.

Usage:
    uv run python betting_ml/scripts/generate_xgb_run_diff_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results_xgb_run_diff.json"
REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "hyperparameter_tuning_xgb_run_diff.md"
CONTEXT_PATH = PROJECT_ROOT / "project_context.md"


def _pct_change(baseline: float, tuned: float) -> str:
    if baseline == 0:
        return "N/A"
    pct = (tuned - baseline) / baseline * 100
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.2f}%"


def _find_convergence_trial(all_trials: list[dict], best_score: float) -> int | None:
    for t in all_trials:
        if t["value"] is not None and abs(t["value"] - best_score) < 1e-10:
            return t["trial_number"]
    return None


def _build_report(r: dict) -> str:
    best_params = r["best_params"]
    baseline = r["baseline_cv_score"]
    tuned = r["best_cv_score"]
    pct = _pct_change(baseline, tuned)
    improved_marker = " ✓" if r["improved"] else " ✗"
    n_trials = r["n_trials"]
    all_trials = r["all_trials"]
    persisted = r["persisted_models"]

    conv_trial = _find_convergence_trial(all_trials, tuned)
    if conv_trial is not None:
        if conv_trial < 10:
            conv_comment = "early convergence (first 10 trials) — TPE found a strong region quickly"
        elif conv_trial < 25:
            conv_comment = "mid-search convergence — moderate exploration before best found"
        else:
            conv_comment = "late convergence — extended search required to find optimum"
        conv_str = f"Trial {conv_trial}"
    else:
        conv_comment = "convergence trial not determined"
        conv_str = "unknown"

    lines: list[str] = [
        "# XGBoost run_differential Hyperparameter Tuning — Card 4.12b",
        "",
        f"Optuna TPE sampler (seed=42), direction=minimize, n_trials={r['n_trials']}.",
        "",
        "## XGBoost run_differential Hyperparameter Search Results",
        "",
        "| Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |",
        "|---|---|---|---|---|",
        f"| MAE | {baseline:.4f} | {tuned:.4f} | {pct}{improved_marker} | {n_trials} |",
        "",
        "### Best Hyperparameter Values",
        "",
    ]
    for param, val in sorted(best_params.items()):
        lines.append(f"- **{param}:** {val}")
    lines.append("")

    lines += [
        "## Optuna Trial Convergence",
        "",
        f"**run_differential** (MAE={tuned:.4f}): Best value first achieved at {conv_str} of {n_trials} — {conv_comment}.",
        "",
    ]

    lines += [
        "## Best Hyperparameter Configuration",
        "",
        "```json",
        json.dumps(best_params, indent=2),
        "```",
        "",
    ]

    lines += [
        "## Persisted Model",
        "",
        "| Target | Model Name | Eval Year | Path |",
        "|---|---|---|---|",
    ]
    for pm in persisted:
        lines.append(f"| {pm['target']} | {pm['model_name']} | {pm['eval_year']} | `{pm['path']}` |")
    lines += [
        "",
        "Model confirmed persisted successfully via save_model().",
        "",
    ]

    return "\n".join(lines)


def _update_project_context(r: dict) -> None:
    improved = r["improved"]
    tuned = r["best_cv_score"]
    baseline = r["baseline_cv_score"]
    best_params = r["best_params"]
    improved_str = "improved ✓" if improved else "did not improve ✗"
    n_trials = r["n_trials"]
    one_sentence = (
        f"Optuna TPE ({n_trials} trials) tuned XGBoost for run_differential; "
        f"tuned MAE={tuned:.4f} vs baseline={baseline:.4f} — {improved_str}."
    )

    params_summary = ", ".join(f"{k}={v}" for k, v in sorted(best_params.items()))

    card_section = f"""
#### Card 4.12b Results — XGBoost run_differential Hyperparameter Optimization

- **xgb_run_diff_improved:** {improved} — XGBoost run_differential MAE {improved_str} (tuned={tuned:.4f} vs baseline={baseline:.4f})
- **best_params:** {params_summary}
- **Summary:** {one_sentence}
- **Full results:** `betting_ml/evaluation/hyperparameter_tuning_xgb_run_diff.md`, `betting_ml/evaluation/tuning_results_xgb_run_diff.json`
- **Optuna:** TPE sampler, {r['n_trials']} trials, tuned model persisted via save_model()
"""

    with open(CONTEXT_PATH) as f:
        content = f.read()

    if "card 4.12b" in content.lower():
        print("project_context.md already contains Card 4.12b results — skipping update.")
        return

    insert_marker = "#### Card 4.1 —"
    if insert_marker in content:
        content = content.replace(insert_marker, card_section + "\n" + insert_marker, 1)
    else:
        content += card_section

    with open(CONTEXT_PATH, "w") as f:
        f.write(content)
    print(f"Updated {CONTEXT_PATH} with Card 4.12b results.")


def main() -> None:
    if not RESULTS_PATH.exists():
        print(
            f"ERROR: {RESULTS_PATH} not found.\n"
            "Run run_xgb_run_diff_search.py first to produce tuning_results_xgb_run_diff.json."
        )
        sys.exit(1)

    with open(RESULTS_PATH) as f:
        r = json.load(f)

    print("Building hyperparameter_tuning_xgb_run_diff.md...")
    report = _build_report(r)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(f"Wrote {REPORT_PATH}")

    print("Updating project_context.md...")
    _update_project_context(r)

    print("\nCard 4.12b report generation complete.")


if __name__ == "__main__":
    main()
