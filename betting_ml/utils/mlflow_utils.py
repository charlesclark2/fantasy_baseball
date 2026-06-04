"""
mlflow_utils.py — Epic I, Story I.1

Thin MLflow wrapper for consistent experiment tracking across all training scripts.

Tracking backend: local file-based (mlruns/) by default; set MLFLOW_TRACKING_URI
to switch to a remote server without code changes.

Artifact store: s3://baseball-betting-ml-artifacts/mlflow/ — set via
MLFLOW_ARTIFACT_ROOT or pass artifact_location when creating experiments.
"""
from __future__ import annotations

import mlflow


def get_or_create_experiment(name: str) -> str:
    """Idempotently return the MLflow experiment ID, creating it if needed."""
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is None:
        experiment_id = mlflow.create_experiment(name)
    else:
        experiment_id = experiment.experiment_id
    return experiment_id


def log_cv_fold(fold: int, eval_year: int, metrics: dict) -> None:
    """Log per-fold metrics under two schemes for flexibility:
    - Named: fold_{i}_{metric}  (queryable by exact fold)
    - Step-indexed: metric logged at step=fold (timeline charting in MLflow UI)
    None values are skipped.
    """
    for key, val in metrics.items():
        if val is None:
            continue
        mlflow.log_metric(f"fold_{fold}_{key}", float(val))
        mlflow.log_metric(key, float(val), step=fold)


def log_search_run(
    experiment: str,
    run_name: str,
    params: dict,
    metrics: dict,
    tags: dict | None = None,
    artifacts: list[str] | None = None,
    enabled: bool = True,
) -> str | None:
    """Document a production hyperparameter-search/retrain run in MLflow.

    Single entry point used by the production champion/challenger search scripts
    so that every training run is recorded with its full feature contract
    (n_features + the resolved feature list), CV score, and the persisted model
    artifact. Returns the run_id (or None when disabled via --no-mlflow).

    None-valued params/metrics are dropped so partial results still log cleanly.
    Each artifact path is logged with mlflow.log_artifact; the model .pkl belongs
    here so the binary is recoverable from the run (avoids the S3↔registry drift
    that left the prior deployed champions un-scoreable).
    """
    if not enabled:
        return None

    clean_params = {k: v for k, v in params.items() if v is not None}
    clean_metrics = {k: float(v) for k, v in metrics.items() if v is not None}

    mlflow.set_experiment(experiment)
    get_or_create_experiment(experiment)
    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        mlflow.log_params(clean_params)
        mlflow.log_metrics(clean_metrics)
        for key, val in (tags or {}).items():
            mlflow.set_tag(key, val)
        for path in artifacts or []:
            try:
                mlflow.log_artifact(path)
            except Exception as exc:  # artifact store may be offline locally
                print(f"  WARNING: MLflow log_artifact failed for {path}: {exc}")
        return run_id
