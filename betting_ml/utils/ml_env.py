"""A1.12 — single source of truth for which ``betting_ml`` schema the prediction
scorers WRITE to.

Three writers historically resolved this three different ways:
  * ``scripts/predict_today.py``          — keyed off ``TARGET_ENV`` (dev default)
  * ``betting_ml/scripts/predict_today.py`` — HARDCODED prod (wrote prod from any
                                              CLI run, ignoring ``TARGET_ENV``)
  * the Streamlit app                     — read prod, then band-aided each button
                                            with an inline ``TARGET_ENV=prod``.

That mismatch meant a local run could silently write ``betting_ml_dev`` while the
app read ``betting_ml`` (prod) — predictions "vanished". Resolve it here so every
writer agrees and read/write targets cannot diverge.

Contract: ``TARGET_ENV=prod`` → prod (``betting_ml``); anything else → dev
(``betting_ml_dev``). The deployed Streamlit app and the Dagster jobs set
``TARGET_ENV=prod``; bare CLI runs default to dev isolation.
"""

from __future__ import annotations

import os

_PROD_SCHEMA = "baseball_data.betting_ml"
_DEV_SCHEMA = "baseball_data.betting_ml_dev"


def is_prod() -> bool:
    """True when the environment selects the production schema."""
    return os.getenv("TARGET_ENV") == "prod"


def ml_schema() -> str:
    """Fully-qualified ``database.schema`` the scorers write predictions to."""
    return _PROD_SCHEMA if is_prod() else _DEV_SCHEMA
