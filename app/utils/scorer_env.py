"""A1.12 — keep the Streamlit app's read schema and its scorer writes in lockstep.

The deployed app is the production dashboard: its pages read
``baseball_data.betting_ml`` (prod). Any ``predict_today.py`` it launches must
therefore WRITE prod too, or predictions silently land in ``betting_ml_dev`` and
the page never updates (the original "vanished predictions" foot-gun).

Both scorers now resolve their write schema from ``TARGET_ENV`` via
``betting_ml.utils.ml_env`` (TARGET_ENV=prod → betting_ml; else betting_ml_dev).
Routing every scorer subprocess through :func:`scorer_env` stamps the same
``TARGET_ENV`` the app reads with, so no individual button can forget it and
read/write can't diverge.
"""

from __future__ import annotations

import os

# The app reads prod; its scorer launches must write prod. One declaration.
_APP_TARGET_ENV = "prod"


def scorer_env(base: dict | None = None) -> dict:
    """Return the subprocess env that makes a launched scorer write to the schema
    the app reads. Pass ``base`` to extend a custom env; defaults to ``os.environ``.
    """
    env = dict(base if base is not None else os.environ)
    env["TARGET_ENV"] = _APP_TARGET_ENV
    return env
