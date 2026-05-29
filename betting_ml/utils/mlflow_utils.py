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
