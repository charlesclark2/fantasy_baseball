"""hierarchical.py — re-export shim over the shared cross-vertical solver.

The penalized-Gaussian (mixed-effects) partial-pooling solver that started life behind
NCAAF-P1.2 was promoted to `betting_ml/utils/hierarchical.py` (MLB Edge-E7.3, 2026-07-26) so
there is ONE implementation the whole program reuses — NCAAF-P1.2/P1.2b/P1A and baseball E7.3
all import the same code, not per-vertical copies. This module keeps the football import path
(`from .hierarchical import Block, DesignSpec, Posterior, fit`) working verbatim.

Nothing about the solver changed; it is still the sport-agnostic linear algebra documented in
the shared module's docstring. Import from either path.
"""
from __future__ import annotations

from betting_ml.utils.hierarchical import (  # noqa: F401
    FLAT_PRECISION,
    FLAT_PRIOR_SD_MULTIPLE,
    Block,
    DesignSpec,
    Posterior,
    fit,
    marginal_loglik,
    solve_posterior,
)

__all__ = [
    "FLAT_PRECISION",
    "FLAT_PRIOR_SD_MULTIPLE",
    "Block",
    "DesignSpec",
    "Posterior",
    "fit",
    "marginal_loglik",
    "solve_posterior",
]
