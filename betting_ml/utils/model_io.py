"""Phase 5 — Model I/O utility.

Public API:
    load_model(target: str, variant: str = "prod") -> Any
        Reads betting_ml/models/model_registry.yaml, resolves the artifact_path
        for the requested variant, and returns the deserialized object via
        joblib.load. Raises ValueError if the target is unknown, the variant
        is not found in the registry entry, or the artifact file is absent.

    save_model(model, target, model_name, eval_year) -> str
        Retained for training scripts: serializes a model to the standard
        path convention and returns the absolute path string.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import joblib
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MODELS_ROOT = _PROJECT_ROOT / "betting_ml" / "models"
_REGISTRY_PATH = _MODELS_ROOT / "model_registry.yaml"


def _load_registry() -> dict:
    if not _REGISTRY_PATH.exists():
        raise ValueError(
            f"Model registry not found at {_REGISTRY_PATH}. "
            "Run the Phase 5 model selection and registry tasks first."
        )
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f) or {}


def load_model(target: str, variant: str = "prod") -> Any:
    """Load a production model artifact via the model registry.

    Parameters
    ----------
    target:
        One of 'total_runs', 'run_differential', 'home_win'.
    variant:
        Registry variant key. Currently only 'prod' is supported; any other
        value raises ValueError unless explicitly added to the registry entry.

    Returns
    -------
    Deserialized model object (NGBRegressor or CalibratedClassifierCV).
    """
    registry = _load_registry()

    if target not in registry:
        raise ValueError(
            f"Target '{target}' not found in model registry. "
            f"Available targets: {sorted(registry.keys())}"
        )

    entry = registry[target]

    # Resolve artifact path for the requested variant.
    if variant == "prod":
        artifact_path = entry.get("artifact_path")
        if not artifact_path:
            raise ValueError(
                f"Registry entry for '{target}' has no 'artifact_path' field."
            )
    else:
        # Support future variants stored as entry-level keys (e.g. "dev", "shadow").
        artifact_path = entry.get(variant)
        if not artifact_path:
            raise ValueError(
                f"Variant '{variant}' not found in registry entry for '{target}'. "
                f"Available keys: {sorted(entry.keys())}"
            )

    path = Path(artifact_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path

    if not path.exists():
        raise ValueError(
            f"Artifact file does not exist on disk: {path} "
            f"(target='{target}', variant='{variant}')"
        )

    return joblib.load(path)


# ---------------------------------------------------------------------------
# Retained for training scripts — do not use in downstream consumers.
# ---------------------------------------------------------------------------

def _model_path(target: str, model_name: str, eval_year: int) -> Path:
    return _MODELS_ROOT / target / f"{model_name}_{eval_year}.pkl"


def save_model(
    model: object,
    target: str,
    model_name: str,
    eval_year: int,
) -> str:
    """Serialize model to the standard path and return the absolute path string."""
    path = _model_path(target, model_name, eval_year)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return str(path)
