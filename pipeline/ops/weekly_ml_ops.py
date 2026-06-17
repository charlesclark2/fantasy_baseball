"""Weekly ML ops (Epic 9 Story 9.6 / Epic O.3; Epic O.5).

`compute_stacking_weights_op` recomputes Layer 3 pseudo-BMA stacking weights on a
weekly cadence (NLL scores only change when a sub-model is retrained or a signal
is promoted) and uploads the result to S3 for runtime consumers.

`train_bayesian_meta_model_op` reruns the Story 12.4 Bayesian CLV meta-model MCMC on
the accumulated live-CLV population weekly and uploads the updated trace to S3 (Epic O.5).
"""

import json
import os

from dagster import MetadataValue, Out, op

# Reuse the canonical subprocess + env helpers from the daily ops module.
from pipeline.ops.daily_ingestion_ops import APP_DIR, _run_script, _target_env

_SCRIPT = f"{APP_DIR}/betting_ml/scripts/compute_stacking_weights.py"
_WEIGHTS_JSON = f"{APP_DIR}/betting_ml/models/layer3/stacking_weights.json"

_META_SCRIPT = f"{APP_DIR}/betting_ml/scripts/train_bayesian_meta_model.py"
_META_SUMMARY = f"{APP_DIR}/betting_ml/models/meta_model/meta_model_latest.json"


@op(out=Out())
def compute_stacking_weights_op(context):
    """Run compute_stacking_weights.py and surface the weights to run metadata.

    Stub-mode (Epic O.3): if the Story 9.3 script is absent, log and succeed
    without writing — lets the schedule exist before Epic 9 ships without weekly
    failures. With 9.3 shipped this is the active path.
    """
    if not os.path.exists(_SCRIPT):
        context.log.warning(
            "Stacking weights not yet available — Epic 9 Story 9.3 pending. "
            "Skipping (stub mode).")
        return {"status": "stub"}

    # --s3-upload writes layer3/stacking_weights.json to S3 for runtime consumers.
    _run_script(context, _SCRIPT, ["--env", _target_env(), "--s3-upload"])

    # Read the freshly-written weights and attach to Dagster run metadata so they
    # are auditable from run history without opening S3 (Story 9.6 AC).
    try:
        with open(_WEIGHTS_JSON) as fh:
            weights = json.load(fh)
        targets = weights.get("targets", {})
        metadata = {"generated_at": weights.get("meta", {}).get("generated_at", "unknown")}
        for target, groups in targets.items():
            metadata[f"{target}__weights"] = MetadataValue.json(
                {g: round(info["weight"], 4) for g, info in groups.items()})
            metadata[f"{target}__fold_weight_std"] = MetadataValue.json(
                {g: round(info["fold_weight_std"], 4) for g, info in groups.items()})
        context.add_output_metadata(metadata)
        context.log.info(
            f"Stacking weights recomputed ({metadata['generated_at']}); "
            f"targets={list(targets)}")
        return {"status": "ok", "targets": list(targets)}
    except Exception as exc:  # noqa: BLE001 — weights are written+uploaded; metadata is best-effort
        context.log.warning(f"Weights written and uploaded, but metadata logging failed: {exc}")
        return {"status": "ok"}


@op(out=Out())
def train_bayesian_meta_model_op(context):
    """Weekly Bayesian CLV meta-model retrain (Story 12.4 / Epic O.5).

    Reruns the MCMC on the accumulated live-CLV population and uploads the updated
    trace/scaler/summary to S3. The script owns all gating, so the op stays thin:
      • count gate (`--min-games 50`): below threshold the script logs
        "Insufficient CLV labels (n/50) — skipping MCMC" and exits 0 (op stays green);
      • convergence gate: R-hat > 1.10 → the script exits non-zero WITHOUT uploading
        (serving keeps the last-good trace) → `_run_script` raises → Dagster alert fires;
        R-hat > 1.05 logs a WARNING but still uploads.

    Reads CLV from the Story 12.4 pre-test surface (daily_model_predictions ⋈
    mart_odds_line_movement), NOT mart_clv_labeled_games — the backfill mart is
    contaminated for 2026 and deliberately bypassed by the trainer.
    """
    if not os.path.exists(_META_SCRIPT):
        context.log.warning(
            "Bayesian meta-model trainer not found — Epic 12 Story 12.4 pending. "
            "Skipping (stub mode).")
        return {"status": "stub"}

    # --s3-upload writes meta_model/* to S3 for runtime consumers; the script exits
    # non-zero (→ raise → alert) on a non-converged trace without uploading.
    _run_script(context, _META_SCRIPT, ["--s3-upload", "--min-games", "50"])

    # Surface n_games / mean_ci_width / max_rhat to run metadata so the weekly
    # convergence history is auditable from run history without opening S3 (O.5 AC).
    try:
        with open(_META_SUMMARY) as fh:
            summary = json.load(fh)
        context.add_output_metadata({
            "n_games": summary.get("n_games"),
            "mean_ci_width": summary.get("mean_ci_width"),
            "max_rhat": summary.get("max_rhat"),
            "quartile_spread": summary.get("quartile_spread"),
            "gates": MetadataValue.json(summary.get("gates", {})),
            "generated_at": summary.get("generated_at", "unknown"),
        })
        context.log.info(
            f"Meta-model retrained: n_games={summary.get('n_games')}, "
            f"mean_ci_width={summary.get('mean_ci_width')}, max_rhat={summary.get('max_rhat')}")
        return {"status": "ok", "n_games": summary.get("n_games")}
    except FileNotFoundError:
        # Count gate skipped MCMC (no summary written this run) — expected below 50 games.
        context.log.info("No summary written — count gate skipped MCMC (below threshold).")
        return {"status": "skipped"}
    except Exception as exc:  # noqa: BLE001 — trace uploaded; metadata is best-effort
        context.log.warning(f"Trace uploaded, but metadata logging failed: {exc}")
        return {"status": "ok"}
