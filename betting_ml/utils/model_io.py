"""Card 4.8 — Model serialization convention for the Phase 4 ML pipeline.

Public API:
    save_model(model, target, model_name, eval_year) -> str
    load_model(target, model_name, eval_year) -> object

Path convention:
    betting_ml/models/{target}/{model_name}_{eval_year}.pkl

Tuned variants use a "_tuned" suffix in model_name, e.g. "xgb_tuned".
"""

from __future__ import annotations

import os
from pathlib import Path

import joblib

# Project root = three levels up from this file (utils/ -> betting_ml/ -> root).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MODELS_ROOT = _PROJECT_ROOT / "betting_ml" / "models"


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


def load_model(
    target: str,
    model_name: str,
    eval_year: int,
) -> object:
    """Deserialize and return the model from the standard path.

    Raises FileNotFoundError with a descriptive message if the file is absent.
    """
    path = _model_path(target, model_name, eval_year)
    if not path.exists():
        raise FileNotFoundError(
            f"No saved model found at {path}. "
            f"Expected target='{target}', model_name='{model_name}', eval_year={eval_year}."
        )
    return joblib.load(path)
