"""hierarchical.py — the penalized-Gaussian (mixed-effects) solver behind NCAAF-P1.2.

Sport-agnostic linear algebra. Nothing in this module knows what football is; it knows how
to fit a Gaussian linear model in which some coefficient blocks carry a shared N(0, tau^2)
prior (random effects / partial pooling) and others are effectively flat (fixed effects),
and how to choose those tau's by maximizing the marginal likelihood.

WHY A CLOSED-FORM SOLVER AND NOT PyMC
-------------------------------------
P1.2 must emit a posterior for EVERY (season, as-of week) — ~200 leakage-safe refits over
2014-present, each on a window that ends strictly before the week it describes. NUTS would
make that a multi-hour job that nobody re-runs. The model here is conditionally Gaussian
(Normal likelihood, Normal priors), so the posterior is Gaussian IN CLOSED FORM and each
refit is one Cholesky of a p x p matrix — milliseconds. We pay for that with an empirical-
Bayes plug-in for the variance components (they are optimized, then treated as known)
rather than integrating over them, which understates uncertainty slightly. That trade is
stated in the model's own docstring and in the P1.2 report; it is the same empirical-Bayes
posture as MLB's `compute_bullpen_posteriors.py`.

THE MODEL
---------
    y = X b + e,     e ~ N(0, sigma^2 W^-1)          (W = diag of observation weights)
    b_j ~ N(0, tau_g(j)^2)                            (g(j) = the block j belongs to)

with `Lambda` = the diagonal prior-precision matrix (1/tau^2 per entry; a tiny constant for
"flat" fixed-effect blocks). Then, exactly:

    A      = X^T W X / sigma^2 + Lambda          (posterior precision, p x p)
    mean   = A^-1 X^T W y / sigma^2
    cov    = A^-1
    log|S| = n log sigma^2 - sum(log w) + log|A| - log|Lambda|
    y'S^-1 y = (y'Wy)/sigma^2 - (X'Wy)' A^-1 (X'Wy) / sigma^4

(the last two are Woodbury / matrix-determinant-lemma identities for the marginal
covariance S = sigma^2 W^-1 + X Lambda^-1 X^T, so the marginal likelihood costs one p x p
Cholesky rather than an n x n one).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

# ⚠️ THE "FLAT" FIXED-EFFECT PRIOR IS WEAKLY INFORMATIVE, NOT IMPROPER — and that matters.
#
# A fixed-effect block still needs a finite prior precision so log|Lambda| is defined and A
# is never singular. The obvious choice (1e-6) is an implied prior SD of 1,000 POINTS on a
# football coefficient, which is not "uninformative", it is nonsense — and it leaks: a
# covariate that is only weakly identified in the fit window (e.g. a `_missing` indicator
# true for two expansion teams) inherits essentially that whole variance, and every team
# carrying that indicator then reports a posterior SD around 1,000 points. That was live:
# 2021 New Mexico State came out at strength_margin_sd = 913.
#
# So the flat prior is instead scaled to the RESPONSE: prior sd = FLAT_PRIOR_SD_MULTIPLE x
# sd(y). At 2x that is ~34 points of margin — far wider than any real coefficient (they run
# 1-10 points per sd of covariate), so identified coefficients are untouched, while an
# unidentified one can no longer claim absurd uncertainty. `fit(fixed_prior_sd=...)`
# overrides it; FLAT_PRECISION remains the fallback when there is no response to scale to.
FLAT_PRECISION = 1e-6
FLAT_PRIOR_SD_MULTIPLE = 2.0

# Variance components are optimized in log space; these bounds keep the optimizer inside a
# physically sensible range (a standard deviation between ~0.05 and ~100 points).
_LOG_VAR_MIN = math.log(1e-3)
_LOG_VAR_MAX = math.log(1e4)


@dataclass(frozen=True)
class Block:
    """One contiguous group of design-matrix columns that share a prior.

    `penalized=False` marks a fixed effect (flat prior). `penalized=True` marks a random
    effect whose prior variance `tau^2` is a free variance component named by `name`.
    """

    name: str
    columns: tuple[str, ...]
    penalized: bool = True

    @property
    def size(self) -> int:
        return len(self.columns)


@dataclass
class DesignSpec:
    """The column layout of a design matrix: an ordered list of blocks."""

    blocks: tuple[Block, ...]

    @property
    def columns(self) -> list[str]:
        return [c for b in self.blocks for c in b.columns]

    @property
    def n_params(self) -> int:
        return sum(b.size for b in self.blocks)

    @property
    def variance_component_names(self) -> list[str]:
        return [b.name for b in self.blocks if b.penalized]

    def slice_of(self, block_name: str) -> slice:
        start = 0
        for b in self.blocks:
            if b.name == block_name:
                return slice(start, start + b.size)
            start += b.size
        raise KeyError(f"no block named {block_name!r} (have {[b.name for b in self.blocks]})")

    def index_of(self, column: str) -> int:
        return self.columns.index(column)

    def prior_precision(
        self, variances: dict[str, float], flat_precision: float = FLAT_PRECISION
    ) -> np.ndarray:
        """Build the diagonal of Lambda from a {block_name: tau^2} mapping."""
        parts = []
        for b in self.blocks:
            if b.penalized:
                tau2 = variances[b.name]
                if not (tau2 > 0):
                    raise ValueError(f"variance component {b.name!r} must be > 0, got {tau2}")
                parts.append(np.full(b.size, 1.0 / tau2))
            else:
                parts.append(np.full(b.size, flat_precision))
        return np.concatenate(parts) if parts else np.zeros(0)


@dataclass
class Posterior:
    """A fitted Gaussian posterior over the design's coefficients."""

    spec: DesignSpec
    mean: np.ndarray
    cov: np.ndarray
    sigma2: float
    variances: dict[str, float]
    n_obs: int
    loglik: float
    converged: bool = True
    notes: list[str] = field(default_factory=list)

    def block(self, name: str) -> np.ndarray:
        return self.mean[self.spec.slice_of(name)]

    def coef(self, column: str) -> float:
        return float(self.mean[self.spec.index_of(column)])

    def coef_sd(self, column: str) -> float:
        i = self.spec.index_of(column)
        return float(math.sqrt(max(self.cov[i, i], 0.0)))

    def linear_combination(self, weights: np.ndarray) -> tuple[float, float]:
        """Posterior mean and sd of `weights @ b` — how a team strength is read off."""
        mean = float(weights @ self.mean)
        var = float(weights @ self.cov @ weights)
        return mean, math.sqrt(max(var, 0.0))


@dataclass
class _SufficientStats:
    """X'WX, X'Wy, y'Wy — everything the marginal likelihood needs from the DATA.

    ⚡ WHY THIS EXISTS. The variance-component search evaluates the marginal likelihood
    hundreds of times, and NONE of these quantities depend on the variance components —
    only the added diagonal `Lambda` does. Recomputing `X.T * w @ X` inside the objective
    made a real 2014-2025 run take hours (X is ~3,200 x 1,200 for the offense/defense stage
    A, so each recomputation is billions of flops). Hoisting it out turns each evaluation
    into "add a diagonal, Cholesky" and is the difference between a script the operator can
    run and one nobody ever runs.
    """

    XtWX: np.ndarray
    XtWy: np.ndarray
    yWy: float
    sum_log_w: float
    n: int

    @classmethod
    def build(cls, X: np.ndarray, y: np.ndarray, w: np.ndarray) -> "_SufficientStats":
        XtW = X.T * w
        return cls(
            XtWX=XtW @ X,
            XtWy=XtW @ y,
            yWy=float(y @ (w * y)),
            sum_log_w=float(np.sum(np.log(w))),
            n=int(y.shape[0]),
        )


def _cholesky_solve(A: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, float]:
    """Solve A x = b for symmetric positive-definite A; also return log|A|.

    Uses triangular back-substitution against the Cholesky factor. `np.linalg.solve(L, b)`
    would re-LU-decompose L even though it is already triangular — an easy p^3 to leave on
    the floor, and it shows up badly when b is the identity (the covariance inverse).

    Falls back to an eigenvalue-floored solve if the Cholesky fails, so a degenerate design
    (a duplicated column, an all-zero covariate) degrades instead of crashing.
    """
    from scipy.linalg import solve_triangular

    try:
        L = np.linalg.cholesky(A)
    except np.linalg.LinAlgError:
        w, V = np.linalg.eigh(A)
        w = np.maximum(w, 1e-10)
        A = (V * w) @ V.T
        L = np.linalg.cholesky(A)
    logdet = 2.0 * float(np.sum(np.log(np.diag(L))))
    z = solve_triangular(L, b, lower=True, check_finite=False)
    x = solve_triangular(L.T, z, lower=False, check_finite=False)
    return x, logdet


def _marginal_loglik_from_stats(
    stats: _SufficientStats,
    spec: DesignSpec,
    sigma2: float,
    variances: dict[str, float],
    flat_precision: float = FLAT_PRECISION,
) -> float:
    lam = spec.prior_precision(variances, flat_precision)
    A = stats.XtWX / sigma2 + np.diag(lam)
    sol, logdet_A = _cholesky_solve(A, stats.XtWy)
    logdet_sigma = (
        stats.n * math.log(sigma2) - stats.sum_log_w + logdet_A - float(np.sum(np.log(lam)))
    )
    quad = stats.yWy / sigma2 - float(stats.XtWy @ sol) / (sigma2 ** 2)
    return -0.5 * (stats.n * math.log(2.0 * math.pi) + logdet_sigma + quad)


def _inverse_from_cholesky(A: np.ndarray) -> np.ndarray:
    p = A.shape[0]
    inv, _ = _cholesky_solve(A, np.eye(p))
    return inv


def marginal_loglik(
    X: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    spec: DesignSpec,
    sigma2: float,
    variances: dict[str, float],
) -> float:
    """log p(y | sigma^2, tau^2) with the coefficients integrated out."""
    return _marginal_loglik_from_stats(_SufficientStats.build(X, y, w), spec, sigma2, variances)


def solve_posterior(
    X: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    spec: DesignSpec,
    sigma2: float,
    variances: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Posterior mean and covariance at FIXED variance components."""
    return _solve_posterior_from_stats(_SufficientStats.build(X, y, w), spec, sigma2, variances)


def _solve_posterior_from_stats(
    stats: _SufficientStats,
    spec: DesignSpec,
    sigma2: float,
    variances: dict[str, float],
    flat_precision: float = FLAT_PRECISION,
) -> tuple[np.ndarray, np.ndarray]:
    lam = spec.prior_precision(variances, flat_precision)
    A = stats.XtWX / sigma2 + np.diag(lam)
    mean, _ = _cholesky_solve(A, stats.XtWy / sigma2)
    cov = _inverse_from_cholesky(A)
    return mean, cov


def fit(
    X: np.ndarray,
    y: np.ndarray,
    spec: DesignSpec,
    *,
    weights: np.ndarray | None = None,
    init_sigma2: float = 100.0,
    init_tau2: float = 25.0,
    fixed_variances: dict[str, float] | None = None,
    fixed_sigma2: float | None = None,
    boundary_avoiding: bool = True,
    fixed_prior_sd: float | None = None,
    max_iter: int = 60,
) -> Posterior:
    """Fit the model, choosing variance components by marginal likelihood (empirical Bayes).

    Pass `fixed_variances` / `fixed_sigma2` to SKIP the optimization and solve at known
    components — that is the second stage of P1.2 (hyperparameters learned on strictly
    prior seasons, then held fixed while each week's posterior is solved).
    """
    n, p = X.shape
    if y.shape[0] != n:
        raise ValueError(f"X has {n} rows but y has {y.shape[0]}")
    if p != spec.n_params:
        raise ValueError(f"X has {p} columns but spec declares {spec.n_params}")
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    if np.any(w <= 0):
        raise ValueError("observation weights must be strictly positive")

    vc_names = spec.variance_component_names
    notes: list[str] = []
    # Built ONCE and reused by every likelihood evaluation and the final solve — see
    # _SufficientStats for why this hoist is load-bearing rather than cosmetic.
    stats = _SufficientStats.build(X, y, w) if n else None

    # The weakly-informative flat prior, scaled to the response (see FLAT_PRECISION above).
    if fixed_prior_sd is None and n:
        y_sd = float(np.sqrt(np.average((y - np.average(y, weights=w)) ** 2, weights=w)))
        fixed_prior_sd = FLAT_PRIOR_SD_MULTIPLE * y_sd if y_sd > 0 else None
    flat_precision = 1.0 / (fixed_prior_sd ** 2) if fixed_prior_sd else FLAT_PRECISION

    if fixed_variances is not None and fixed_sigma2 is not None:
        variances = {k: float(fixed_variances[k]) for k in vc_names}
        sigma2 = float(fixed_sigma2)
        converged = True
    elif n == 0:
        # No observations at all (e.g. as-of week 1). The posterior IS the prior; the
        # solver handles it correctly (A = Lambda, mean = 0) but the optimizer cannot
        # learn variance components from nothing, so fall back to the inits.
        variances = {k: float(init_tau2) for k in vc_names}
        sigma2 = float(init_sigma2)
        converged = True
        notes.append("no observations in window; posterior = prior")
    else:
        from scipy.optimize import minimize

        # ⚠️ BOUNDARY-AVOIDING PRIOR — this is not decoration, it fixes a real collapse.
        # Maximum-likelihood variance components in a hierarchical model with few groups
        # and many nuisance parameters are biased toward ZERO, and the bias is not subtle:
        # on a single NCAAF season (~800 games, ~136 team effects) the likelihood genuinely
        # PEAKS at tau_team = 0 — i.e. "every team in a conference is identical", which we
        # know is false, and which silently deletes the team level of the model. Verified
        # on a synthetic league where the true within-conference sd was 6.0 and ML returned
        # 0.03.
        #
        # The standard cure (Chung/Gelman's boundary-avoiding prior for variance
        # components) is a Gamma(shape=2, scale=A) prior on tau — the STANDARD DEVIATION,
        # not the variance. Its density is zero at tau = 0 and it is otherwise weakly
        # informative, so it removes the degenerate corner without meaningfully moving a
        # well-identified fit. log p(tau) = log(tau) - tau/A + const. The scale A is set
        # from the data (half the response sd), so this carries no hardcoded unit.
        # Turn it off with boundary_avoiding=False to get the raw ML fit.
        wvar = float(np.average((y - np.average(y, weights=w)) ** 2, weights=w))
        tau_prior_scale = max(math.sqrt(wvar) / 2.0, 1e-3)

        def _log_tau_prior(var: dict[str, float]) -> float:
            if not boundary_avoiding:
                return 0.0
            total = 0.0
            for v in var.values():
                tau = math.sqrt(v)
                total += math.log(max(tau, 1e-12)) - tau / tau_prior_scale
            return total

        def negloglik(theta: np.ndarray) -> float:
            theta = np.clip(theta, _LOG_VAR_MIN, _LOG_VAR_MAX)
            s2 = math.exp(theta[0])
            var = {name: math.exp(theta[i + 1]) for i, name in enumerate(vc_names)}
            try:
                return -(
                    _marginal_loglik_from_stats(stats, spec, s2, var, flat_precision)
                    + _log_tau_prior(var)
                )
            except (np.linalg.LinAlgError, ValueError, FloatingPointError):
                return 1e12

        # ⚠️ MULTI-START, AND WHY IT IS NOT OPTIONAL.
        # With several variance components the marginal likelihood is genuinely FLAT along
        # the directions that trade conference-level variance against team-level variance —
        # on one season of the offense/defense model the difference between a sensible
        # optimum and a degenerate corner (tau_team -> 0, tau_conf -> the bound) was under
        # 3 nats. A single Nelder-Mead run from a fixed start walks into that corner and
        # silently returns a model in which no team differs from its conference. So: start
        # from several points spanning "most variance is noise" to "most variance is real",
        # scale the starts to the data rather than to a hardcoded guess, and keep the best.
        scale = wvar if wvar > 0 else float(init_sigma2)
        starts = [
            (0.5 * scale, 0.25 * scale),
            (0.9 * scale, 0.05 * scale),
            (0.2 * scale, 0.50 * scale),
        ]
        best = None
        for s2_0, tau2_0 in starts:
            theta0 = np.array(
                [math.log(max(s2_0, 1e-3))] + [math.log(max(tau2_0, 1e-3))] * len(vc_names)
            )
            res = minimize(
                negloglik,
                theta0,
                method="Nelder-Mead",
                # Capped deliberately. The surface is flat near the optimum (that is WHY
                # multi-start is needed), so extra iterations buy fractions of a nat while
                # multiplying runtime by the number of starts. Coverage comes from the
                # starts, not from grinding each one to convergence.
                options={
                    "maxiter": max_iter * (len(vc_names) + 1),
                    "maxfev": max_iter * (len(vc_names) + 1),
                    "xatol": 1e-2,
                    "fatol": 1e-1,
                },
            )
            if best is None or res.fun < best.fun:
                best = res
        theta = np.clip(best.x, _LOG_VAR_MIN, _LOG_VAR_MAX)
        sigma2 = math.exp(theta[0])
        variances = {name: math.exp(theta[i + 1]) for i, name in enumerate(vc_names)}
        converged = bool(best.success)
        if not converged:
            notes.append(f"variance-component optimizer did not converge: {best.message}")
        # A component pinned to a bound means the data could not identify it. That is a
        # real finding about the fit, not a detail to swallow.
        for name, v in variances.items():
            if math.log(v) <= _LOG_VAR_MIN + 1e-6 or math.log(v) >= _LOG_VAR_MAX - 1e-6:
                notes.append(f"variance component {name!r} hit a bound at {v:.4g} (unidentified)")

    if stats is None:
        stats = _SufficientStats(
            XtWX=np.zeros((p, p)), XtWy=np.zeros(p), yWy=0.0, sum_log_w=0.0, n=0
        )
    mean, cov = _solve_posterior_from_stats(stats, spec, sigma2, variances, flat_precision)
    ll = (
        _marginal_loglik_from_stats(stats, spec, sigma2, variances, flat_precision)
        if n
        else float("nan")
    )
    return Posterior(
        spec=spec,
        mean=mean,
        cov=cov,
        sigma2=float(sigma2),
        variances=variances,
        n_obs=int(n),
        loglik=float(ll),
        converged=converged,
        notes=notes,
    )
