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
_META_MARKETS = ("h2h", "totals")  # Story 12.4 H2H + Story 12.12 totals


def _meta_summary_path(market: str) -> str:
    """h2h summary at the flat meta_model/ path; totals at meta_model/totals/."""
    base = f"{APP_DIR}/betting_ml/models/meta_model"
    return f"{base}/meta_model_latest.json" if market == "h2h" else f"{base}/{market}/meta_model_latest.json"


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
    """Weekly Bayesian CLV meta-model retrain — both markets (Story 12.4 H2H + 12.12 totals / Epic O.5).

    Reruns the MCMC per market on the accumulated live-CLV population and uploads each
    updated trace/scaler/summary to S3 (h2h → meta_model/, totals → meta_model/totals/).
    The script owns all gating, so the op stays thin:
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

    # Retrain BOTH markets (Story 12.4 H2H + Story 12.12 totals) as independent failure
    # domains: each runs --s3-upload, owns its own count/convergence gate, and writes a
    # per-market summary. One market's convergence FAILURE (R-hat > 1.10 → non-zero exit)
    # does not block the other; we attempt both, then raise at the end if any failed so the
    # Dagster alert still fires.
    results: dict[str, dict] = {}
    failures: list[str] = []
    metadata: dict = {}
    for market in _META_MARKETS:
        try:
            _run_script(context, _META_SCRIPT,
                        ["--s3-upload", "--min-games", "50", "--market", market])
            try:
                with open(_meta_summary_path(market)) as fh:
                    summary = json.load(fh)
                metadata[f"{market}__n_games"] = summary.get("n_games")
                metadata[f"{market}__mean_ci_width"] = summary.get("mean_ci_width")
                metadata[f"{market}__max_rhat"] = summary.get("max_rhat")
                metadata[f"{market}__gates"] = MetadataValue.json(summary.get("gates", {}))
                results[market] = {"status": "ok", "n_games": summary.get("n_games")}
                context.log.info(
                    f"[{market}] meta retrained: n_games={summary.get('n_games')}, "
                    f"mean_ci_width={summary.get('mean_ci_width')}, max_rhat={summary.get('max_rhat')}")
            except FileNotFoundError:
                # Count gate skipped MCMC (no summary written) — expected below threshold.
                results[market] = {"status": "skipped"}
                context.log.info(f"[{market}] count gate skipped MCMC (below threshold).")
        except Exception as exc:  # noqa: BLE001 — record + continue; re-raise after both attempted
            results[market] = {"status": "failed", "error": str(exc)}
            failures.append(market)
            context.log.error(f"[{market}] meta retrain failed: {exc}")

    if metadata:
        context.add_output_metadata(metadata)
    if failures:
        raise Exception(f"Meta-model retrain failed for market(s): {failures}")
    return {"status": "ok", "markets": results}
