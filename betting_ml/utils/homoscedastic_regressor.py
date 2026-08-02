"""Serving adapter: a POINT regressor → the NGBoost-shaped predictive-distribution API.

WHY THIS EXISTS (MH2.1 promotion, 2026-08-02)
---------------------------------------------
`predict_today` and `backfill_predictions` score the regression targets through NGBoost's
API verbatim::

    pred_dist = model.pred_dist(X)
    loc, scale = pred_dist.params["loc"], pred_dist.params["scale"]

The MH2.1 champion for ``total_runs``/``post_lineup`` is a **point** learner
(``Pipeline(StandardScaler, ElasticNet)``), which has no ``pred_dist``. Dropping that
estimator at the registry ``artifact_path`` would raise ``AttributeError`` inside a
HALT-tier op and cost the whole slate.

The bake-off never scored a bare point estimate either: ``model_bakeoff.PointNormalSpec``
wraps every point learner in ``Normal(pred(X), σ̂)`` with ``σ̂`` frozen at the training
residual std, precisely so point learners are comparable to NGBoost on CRPS/NLL. **This
class is that wrapper, persisted** — so the object that serves is the object that was
validated, not a re-derivation of it.

This mirrors ``calibrated_classifier.PlattCalibratedLinearClassifier``, which exists for
the same reason on the ``home_win`` side (E13.11 swapped XGBoost → glm_elasticnet and kept
``predict_proba`` as the class-agnostic serving surface).

⚠️ THE CONSEQUENCE, STATED PLAINLY: ``scale`` IS CONSTANT ACROSS GAMES
----------------------------------------------------------------------
A homoscedastic predictive emits the SAME σ for every game, so every downstream consumer of
``pred_total_runs_scale`` changes behaviour — most visibly Story 22.4's σ-gate, whose totals
``ci_width`` stops varying with model uncertainty and becomes a function of |μ − line| alone.

That is a deliberate, evidence-backed trade, not an oversight. MH2.1's conditional-calibration
check scored RMS |Var(z) − 1| across σ-deciles (``Var(z) = 1`` in every stratum is the analytic
truth for a conditionally calibrated predictive):

    incumbent ngboost_normal (served)  0.158   pooled Var(z) 1.124
    plus_eb   ngboost_normal           0.180   pooled Var(z) 1.111
    plus_eb   glm_elasticnet (this)    0.050   pooled Var(z) 0.997
    ngboost with σ deliberately FLAT   0.107   pooled Var(z) 1.090

The served NGBoost under-estimates σ, worst in the games it calls calm (Var(z) 1.44 in the
calmest decile), and FLATTENING its σ *improves* its calibration. So the per-game σ being
replaced was not merely uninformative — it was actively miscalibrated. A constant, honest σ
is better calibrated than a varying, wrong one.

⚠️ ``best_alpha = 0``. This is a PRICING/CALIBRATION change. No edge, win-rate, or ROI claim
is made or implied by anything in this module.

PICKLE STABILITY (the 2026-07-03 unpinned-deps landmine)
--------------------------------------------------------
Lives in a stable importable module — never a script's ``__main__`` — so the promoted artifact
resolves at load time in ``predict_today``/``backfill_predictions``, the same constraint that
governs ``PlattCalibratedLinearClassifier`` / ``TemperatureCalibrator``. The wrapped estimator
is a scikit-learn pipeline, so the artifact is only loadable under the pinned ``scikit-learn``
version; re-fit whenever those pins move.
"""
from __future__ import annotations

import numpy as np


class FrozenNormal:
    """The subset of an NGBoost frozen ``Normal`` distribution the serving path actually uses.

    ``predict_today`` / ``backfill_predictions`` read ``.params["loc"]`` and ``.params["scale"]``
    and pass that same dict to ``total_runs_trainer.p_over_line`` — nothing else. Keeping this
    deliberately minimal means the adapter cannot silently diverge from NGBoost on some richer
    API that only one of the two implements.
    """

    __slots__ = ("params", "loc", "scale")

    def __init__(self, loc: np.ndarray, scale: np.ndarray) -> None:
        loc = np.asarray(loc, dtype=float)
        scale = np.asarray(scale, dtype=float)
        if loc.shape != scale.shape:
            raise ValueError(f"loc {loc.shape} and scale {scale.shape} must have the same shape")
        self.loc = loc
        self.scale = scale
        self.params = {"loc": loc, "scale": scale}

    def __len__(self) -> int:
        return int(self.loc.shape[0])

    def mean(self) -> np.ndarray:
        return self.loc


class HomoscedasticNormalRegressor:
    """A fitted point regressor + a frozen σ̂, exposing NGBoost's ``pred_dist`` surface.

    Parameters
    ----------
    estimator:
        Any fitted regressor with ``predict(X)`` — for MH2.1 a
        ``Pipeline(StandardScaler, ElasticNet)``.
    sigma:
        The frozen predictive σ. Must be finite and strictly positive: a zero/NaN σ would make
        every downstream ``P(over)`` degenerate to 0/1 or NaN, and it would do so *silently*
        (``scipy.stats.norm.sf`` returns a step function at σ=0 rather than raising), so it is
        rejected at construction instead.
    sigma_method / n_train / provenance:
        Recorded so a served σ can be traced to how it was estimated without re-reading the fit
        script. ``sigma_method`` is free text (e.g. ``"train_residual_std"``).
    """

    def __init__(
        self,
        estimator,
        sigma: float,
        *,
        sigma_method: str = "train_residual_std",
        n_train: int | None = None,
        provenance: dict | None = None,
    ) -> None:
        sigma = float(sigma)
        if not np.isfinite(sigma) or sigma <= 0.0:
            raise ValueError(
                f"sigma must be finite and > 0, got {sigma!r}. A non-positive or NaN σ makes "
                "every served P(over) degenerate (0/1 or NaN) WITHOUT raising downstream — "
                "scipy's norm.sf is a step function at σ=0 — so it is rejected here."
            )
        self.estimator = estimator
        self.sigma = sigma
        self.sigma_method = sigma_method
        self.n_train = n_train
        self.provenance = dict(provenance or {})

    # ── the CONTRACT-GUARD surface ────────────────────────────────────────────────────────
    @property
    def n_features_in_(self) -> int:
        """predict_today's CONTRACT-GUARD reads this to assert contract width == model width.

        It is a hard error rather than a graceful ``None`` because the guard SKIPS any model
        whose width it cannot read — so a missing attribute would silently disable the very
        check that catches a contract/model mismatch (the models score by column POSITION).
        """
        n = getattr(self.estimator, "n_features_in_", None)
        if n is None:
            raise AttributeError(
                f"wrapped estimator {type(self.estimator).__name__} exposes no n_features_in_, "
                "so predict_today's CONTRACT-GUARD would skip this model and a contract/model "
                "width mismatch would score by position undetected."
            )
        return int(n)

    # ── the serving surface ───────────────────────────────────────────────────────────────
    def predict(self, X) -> np.ndarray:
        return np.asarray(self.estimator.predict(X), dtype=float)

    def pred_dist(self, X) -> FrozenNormal:
        """NGBoost-shaped predictive: ``Normal(estimator.predict(X), σ̂)``, σ̂ constant."""
        loc = self.predict(X)
        return FrozenNormal(loc, np.full(loc.shape, self.sigma, dtype=float))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"HomoscedasticNormalRegressor(estimator={type(self.estimator).__name__}, "
            f"sigma={self.sigma:.4f}, sigma_method={self.sigma_method!r})"
        )
