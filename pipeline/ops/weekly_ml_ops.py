"""Weekly ML ops (Epic 9 Story 9.6 / Epic O.3).

`compute_stacking_weights_op` recomputes Layer 3 pseudo-BMA stacking weights on a
weekly cadence (NLL scores only change when a sub-model is retrained or a signal
is promoted) and uploads the result to S3 for runtime consumers.
"""

import json
import os

from dagster import MetadataValue, Out, op

# Reuse the canonical subprocess + env helpers from the daily ops module.
from pipeline.ops.daily_ingestion_ops import APP_DIR, _run_script, _target_env

_SCRIPT = f"{APP_DIR}/betting_ml/scripts/compute_stacking_weights.py"
_WEIGHTS_JSON = f"{APP_DIR}/betting_ml/models/layer3/stacking_weights.json"


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
