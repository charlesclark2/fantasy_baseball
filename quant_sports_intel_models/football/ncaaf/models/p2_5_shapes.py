"""p2_5_shapes.py — NCAAF-P2.5: the pre-registered DISTRIBUTIONAL SHAPE families.

WHAT THIS IS
------------
NCAAF-P2.5 repairs the SHAPE of the served joint (margin, total) predictive. P1.4 built the joint
object and P2.1-S1 repointed its MEAN; what is left is the conditional predictive SHAPE around that
mean. This module is the pure, IO-free, unit-testable core: ten shape families, their leakage-safe
fits, their samplers, and the four scoring instruments the pre-registration gates on.

⭐ THE LOAD-BEARING DESIGN CHOICE — **THE MEAN IS FROZEN.**
Every arm consumes the SAME per-game (μ_margin, μ_total) from the served config and differs ONLY in
the conditional shape. Three reasons, all pre-registered (`ncaaf_p2_5_preregistration.md` §1):
  * it is the story's actual scope (the mean is P2.1/P2.6's);
  * ΔCRPS is then attributable to SHAPE alone — a "shape win" cannot be a disguised mean win; and
  * the field is COHERENT, which is what `SR0` is taxed by. A heterogeneous field inflates the DSR
    bar and can veto a real effect (MH2.5 / NF-W6b-C), so coherence is a design decision, not tidiness.
The invariant is ENFORCED, not asserted: `mean_preservation` runs on the SCORED sample arrays inside
the scoring path (NF-W7d — a self-validating check that owns its own copy of the logic passes
silently while the scored path breaks).

THE FAMILIES (doc §4.1 verbatim; `SHAPES` is the registry a guard pins)
----------------------------------------------------------------------
  incumbent      the served `strength_posterior` bivariate Normal — the FOIL every arm must beat
  cond_het       bivariate Gaussian + a conditional-variance sub-model  log σ² = X_var·γ
  student_t      a TRUE bivariate t (tail DEPENDENCE — not reproducible by a Gaussian copula)
  skew_normal    Gaussian copula ⊗ standardized skew-normal marginals
  skew_t         Gaussian copula ⊗ standardized skew-t marginals
  mixture        Gaussian copula ⊗ standardized 2-component Normal mixture (the regime foil)
  copula         Gaussian copula ⊗ EMPIRICAL standardized marginals (fully non-parametric)
  home_away      correlated NegBin TEAM POINTS → (h−a, h+a); the per-side form P1.4's `count`
                 forced to independence
  key_number     discrete-score simulation: the EMPIRICAL score lattice (which carries football's
                 mass at 3/7/10/14/17/21/24/28 by construction) tilted to this game's (μ, σ)
  quantile_boost LightGBM quantile regression of the RESIDUAL on the variance drivers

Arms 3–6 share ONE engine (`draw_copula`): correlated standard normals pushed through a per-axis
monotone STANDARDIZED quantile grid. The families then differ only in how that grid is built, so no
family gets an implementation advantage — and `student_t` is deliberately kept OUT of that engine
because a bivariate t is NOT a Gaussian copula with t marginals (it has tail dependence, which is
exactly the thing worth testing separately).

ESTIMATION (pre-registration §2.1) — ONE objective across the marginal families
------------------------------------------------------------------------------
Every standardized marginal's shape parameters are fitted by minimising the empirical **CRPS of the
standardized marginal against the standardized inner-holdout residuals**: proper, density-free, and
usable identically for skew-normal / skew-t / mixture / empirical, so no family gets an estimator
edge from a more convenient likelihood. `cond_het` (a variance FUNCTION, not a shape family) uses
Gaussian NLL; `home_away` NegBin MLE; `key_number` / `quantile_boost` their native objectives.

⚠️ E2.1-r DISCRETENESS: `home_away` and `key_number` draw INTEGER points, so their PIT MUST be the
RANDOMIZED PIT (`randomized_pit`) — a plain F(y) lands on CDF step-tops and reads as non-flat for a
perfectly-specified count model. That is the harness default and is guarded.

HONEST FRAME: `best_alpha = 0`. A better-shaped predictive is calibration/product value, never an
edge claim. Market-blind — no closing line enters any driver, fit, or sampler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar

from betting_ml.utils.totals_distribution import randomized_pit, pit_flatness

# ---------------------------------------------------------------------------
# Constants — every one pre-registered; ⛔ none may be re-chosen after the run
# ---------------------------------------------------------------------------

#: the standardized-marginal quantile grid. 2001 knots over (0,1) exclusive: fine enough that the
#: inverse-CDF transform is not the binding approximation, cheap enough to rebuild per fold.
_N_GRID: int = 2001
_GRID_TAUS: np.ndarray = (np.arange(1, _N_GRID + 1) / (_N_GRID + 1.0))

#: draws used to build a parametric family's standardized grid by simulation. A family whose
#: quantile function has no closed form (skew-normal, skew-t, mixture) is represented by its own
#: simulated order statistics — ONE code path for every family, so the representation cannot become
#: a per-family advantage.
_GRID_SIM: int = 200_000

#: σ floors — inherited verbatim from `ncaaf_game_distribution` so a shape arm can never buy a win
#: by collapsing the scale below what the incumbent is allowed.
MIN_SIGMA: float = 3.0
#: NegBin mean floor (points are non-negative).
MIN_MU_POINTS: float = 0.5
#: the score lattice `key_number` samples on. College games have run past 90 but the empirical mass
#: beyond it is negligible and the tilt handles the tail.
LATTICE_MAX: int = 100

#: fitted-parameter bands. ν below 3 has undefined variance (so the moment-matched scale stops
#: meaning anything); |α| beyond 8 is numerically indistinguishable from the half-normal limit.
DOF_BOUNDS: tuple[float, float] = (3.0, 60.0)
ALPHA_BOUNDS: tuple[float, float] = (-8.0, 8.0)

#: `quantile_boost`'s quantile knots, and its regularisation — both set by what the sample size can
#: actually estimate (amendment A8.4).
#:
#: ⭐ AN α-QUANTILE CANNOT BE ESTIMATED INSIDE A LEAF SMALLER THAN 1/α ROWS. At ~736 inner-holdout
#: rows a 0.01 knot needs a ~100-row leaf just to have one point below it, so the leaf-level quantile
#: is biased toward the middle and the bias ACCUMULATES over boosting rounds. Measured on
#: informationless drivers (where the arm must collapse onto the empirical marginal): the 17-knot
#: 0.01→0.99 configuration missed by **6.63 points**, i.e. the foil would have lost for an ESTIMATOR
#: reason rather than for its hypothesis. Restricted to the band the n supports, with leaves large
#: enough to hold it, the same probe reads **1.28**.
#:
#: ⚠️ The tails therefore come entirely from the EXPONENTIAL extension anchored at the 0.05/0.95
#: knots — never a flat extension, which would leave the arm with literally no tails (NF-MARGIN1)
#: and make it unable to compete on the very thing this story is looking for.
QB_LEVELS: np.ndarray = np.array(
    [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95])
QB_NUM_LEAVES: int = 4
QB_MIN_CHILD: int = 150
QB_N_ESTIMATORS: int = 60

#: C7 — the mean-preservation tolerance, in POINTS, on the pooled drawn sample per axis.
MEAN_PRESERVATION_TOL: float = 0.15

#: the tail-CRPS weight region: the central 80% of the fold's own realised marginal is EXCLUDED, so
#: the statistic reads only the tails (C5).
TAIL_Q: tuple[float, float] = (0.10, 0.90)


# ===========================================================================
# §2.2 — the pre-registered VARIANCE DRIVERS
# ===========================================================================

#: ⛔ WEATHER IS ABSENT FROM THE NCAAF LAKEHOUSE AND IS THEREFORE NOT REGISTERED.
#: Measured, not assumed: the assembled P1.3 matrix carries 207 columns and ZERO matching
#: `weather|temp|wind|precip|humid`, and neither `ncaaf_data_inventory.md` nor
#: `ncaaf_mart_inventory.md` documents a weather feed. The card conditions weather-driven variance
#: terms on confirming availability first; this constant records the answer so a later session
#: cannot quietly re-add a fabricated feature (`ncaaf_p2_5_preregistration.md` §0.1).
WEATHER_DRIVERS_ABSENT: tuple[str, ...] = ()
WEATHER_ABSENCE_NOTE: str = (
    "no weather feed exists in the NCAAF lakehouse (0 of 207 matrix columns match "
    "weather|temp|wind|precip|humid; absent from both inventories) ⇒ the card's weather-driven "
    "variance terms are DROPPED, not fabricated. `game_venue_is_dome` / `game_venue_elevation_m` "
    "are registered as PARTIAL environment proxies and labelled as such."
)

#: (driver group → the raw columns it contributes). The card's list, minus weather.
VAR_DRIVER_GROUPS: dict[str, tuple[str, ...]] = {
    "pace":          ("pace_sum", "pace_diff"),
    "mismatch":      ("strength_margin_diff", "adj_net_ppa_diff"),
    "explosiveness": ("home_off_explosiveness", "away_off_explosiveness"),
    "qb_uncertainty": ("home_qb_starter_changed_recent", "away_qb_starter_changed_recent",
                       "home_qb_starts_prior", "away_qb_starts_prior"),
    "early_season":  ("season_order_week", "home_games_played", "away_games_played"),
    "environment_proxy": ("game_venue_is_dome", "game_venue_elevation_m"),
}

#: drivers the frame does not carry as columns — built inside `build_driver_matrix`.
#:   `abs_mu_margin`  — FAVOURITE SIZE, read off the model's OWN predicted margin (market-blind:
#:                      it is our μ, never a line).
#:   `log_strength_var` — the EARLY-SEASON / thin-sample driver. ⭐ Registered deliberately so
#:                      `cond_het` NESTS the incumbent: the incumbent IS `cond_het` restricted to
#:                      this single driver. A nested arm that ties is a TIE, never a win (§5.3).
DERIVED_DRIVERS: tuple[str, ...] = ("abs_mu_margin", "log_strength_var")

#: the columns whose driver is |x| rather than x (a mismatch is symmetric — a 20-point favourite and
#: a 20-point underdog are the same uncertainty regime).
_ABS_DRIVERS: frozenset[str] = frozenset({"strength_margin_diff", "adj_net_ppa_diff"})


def declared_driver_columns() -> list[str]:
    """Every raw frame column the registered driver set consumes (⛔ pinned by a guard)."""
    out: list[str] = []
    for cols in VAR_DRIVER_GROUPS.values():
        out.extend(cols)
    return out


def build_driver_matrix(
    tr: pd.DataFrame, ev: pd.DataFrame,
    mu_margin_tr: np.ndarray, mu_margin_ev: np.ndarray,
    strength_var_tr: np.ndarray, strength_var_ev: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """(Z_train, Z_eval, names) — the standardized variance-driver design, TRAIN-fit throughout.

    Standardisation (mean/sd) and the NaN fill are computed on TRAIN rows ONLY, so an eval row can
    never inform its own scaling. A zero-variance train column maps to zeros rather than infinities.
    An intercept is NOT included here — every consumer adds its own.
    """
    names: list[str] = []
    cols_tr: list[np.ndarray] = []
    cols_ev: list[np.ndarray] = []

    def _add(name: str, a: np.ndarray, b: np.ndarray) -> None:
        names.append(name)
        cols_tr.append(np.asarray(a, float))
        cols_ev.append(np.asarray(b, float))

    for col in declared_driver_columns():
        if col not in tr.columns:
            raise KeyError(
                f"NCAAF-P2.5: registered variance driver {col!r} is absent from the frame. A missing "
                "driver must RAISE — silently scoring a smaller driver set would make the "
                "conditional-variance arm a different, un-registered mechanism (NF1.7 a).")
        a = pd.to_numeric(tr[col], errors="coerce").to_numpy(float)
        b = pd.to_numeric(ev[col], errors="coerce").to_numpy(float)
        if col in _ABS_DRIVERS:
            a, b = np.abs(a), np.abs(b)
        _add(col if col not in _ABS_DRIVERS else f"abs_{col}", a, b)

    _add("abs_mu_margin", np.abs(mu_margin_tr), np.abs(mu_margin_ev))
    _add("log_strength_var", np.log(np.clip(strength_var_tr, 1e-6, None)),
         np.log(np.clip(strength_var_ev, 1e-6, None)))

    A = np.column_stack(cols_tr)
    B = np.column_stack(cols_ev)
    # TRAIN-only fill then TRAIN-only scale
    fill = np.nanmean(np.where(np.isfinite(A), A, np.nan), axis=0)
    fill = np.where(np.isfinite(fill), fill, 0.0)
    A = np.where(np.isfinite(A), A, fill)
    B = np.where(np.isfinite(B), B, fill)
    mu = A.mean(axis=0)
    sd = A.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    return (A - mu) / sd, (B - mu) / sd, names


# ===========================================================================
# Standardized-marginal machinery — ONE representation for every family
# ===========================================================================

def standardize_grid(values: np.ndarray) -> np.ndarray:
    """Sorted `values` → a mean-0 / sd-1 quantile grid on `_GRID_TAUS`.

    Standardising here is what keeps every family on the SAME footing: a shape arm may re-shape the
    predictive but may not silently re-scale it, because the per-game σ is supplied separately and
    identically. (A family that could smuggle in a wider scale would be competing on dispersion, not
    on shape — and the metric would then be measuring the wrong thing.)
    """
    v = np.sort(np.asarray(values, float))
    v = v[np.isfinite(v)]
    if v.size < 8:
        raise ValueError("NCAAF-P2.5: too few finite values to build a standardized grid")
    g = np.quantile(v, _GRID_TAUS)
    g = g - g.mean()
    sd = float(np.sqrt(np.mean(g * g)))
    return g / (sd if sd > 1e-9 else 1.0)


def grid_crps_vs_sample(grid: np.ndarray, z: np.ndarray) -> float:
    """Mean CRPS of the grid-represented distribution against the observed standardized sample.

    CRPS(F, y) = 2·∫₀¹ ρ_τ(y − F⁻¹(τ)) dτ (the pinball integral). This is the ONE estimation
    objective every standardized marginal family is fitted on (pre-registration §2.1) — proper,
    density-free, and identical across families, so a family with a convenient likelihood gains no
    estimator advantage over one without.
    """
    z = np.asarray(z, float)[:, None]
    q = np.asarray(grid, float)[None, :]
    tau = _GRID_TAUS[None, :]
    d = z - q
    pin = np.where(d >= 0, tau * d, (tau - 1.0) * d)
    return float(2.0 * pin.mean())


def sample_from_grid(u: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Inverse-CDF sample: uniforms `u` → standardized values, with EXPONENTIAL tails.

    ⚠️ Beyond the outermost knots the grid is extended EXPONENTIALLY, never flat. A knot-quantile
    predictive extended flat has literally no tails — the exact serving-representation defect
    NF-MARGIN1 found in the fantasy champion — and this story is looking for tail defects, so
    building one into the instrument would make the study unable to see its own subject.
    """
    u = np.asarray(u, float)
    g = np.asarray(grid, float)
    out = np.interp(u, _GRID_TAUS, g)
    lo_t, hi_t = _GRID_TAUS[0], _GRID_TAUS[-1]
    # exponential mean-excess extension, scale = the outer inter-knot gap of the fitted grid
    lo_scale = max(float(g[4] - g[0]), 1e-6)
    hi_scale = max(float(g[-1] - g[-5]), 1e-6)
    lo = u < lo_t
    hi = u > hi_t
    if lo.any():
        out[lo] = g[0] + lo_scale * np.log(np.clip(u[lo] / lo_t, 1e-12, 1.0))
    if hi.any():
        out[hi] = g[-1] + hi_scale * np.log(np.clip((1.0 - hi_t) / np.clip(1.0 - u[hi], 1e-12, None),
                                                    1.0, None))
    return out


# ── the parametric standardized families (simulated grids, one code path) ──────────────────────

def _skew_normal_draws(alpha: float, size: int, rng: np.random.Generator) -> np.ndarray:
    d = alpha / np.sqrt(1.0 + alpha * alpha)
    z0 = np.abs(rng.standard_normal(size))
    z1 = rng.standard_normal(size)
    return d * z0 + np.sqrt(max(1.0 - d * d, 0.0)) * z1


def _skew_t_draws(alpha: float, dof: float, size: int, rng: np.random.Generator) -> np.ndarray:
    x = _skew_normal_draws(alpha, size, rng)
    w = np.sqrt(dof / np.maximum(rng.chisquare(dof, size=size), 1e-9))
    return x * w


def _mixture_draws(w1: float, shift: float, s1: float, s2: float,
                   size: int, rng: np.random.Generator) -> np.ndarray:
    """2-component Normal mixture, means placed so the MIXTURE mean is 0 by construction."""
    w1 = float(np.clip(w1, 0.02, 0.98))
    m1 = shift * (1.0 - w1)
    m2 = -shift * w1
    pick = rng.random(size) < w1
    out = np.where(pick, m1 + s1 * rng.standard_normal(size), m2 + s2 * rng.standard_normal(size))
    return out


def _student_t_draws(dof: float, size: int, rng: np.random.Generator) -> np.ndarray:
    w = np.sqrt(dof / np.maximum(rng.chisquare(dof, size=size), 1e-9))
    return rng.standard_normal(size) * w


def fit_standardized_marginal(
    family: str, z: np.ndarray, rng: np.random.Generator,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit one standardized-marginal family to standardized residuals `z` on the CRPS objective.

    Returns (grid, params). `params` always carries the family's COLLAPSE parameter so §5.3's
    nested-tie rule can be read off the record rather than inferred — an arm that ties the incumbent
    with its shape parameter sitting at the Normal limit is a collapse, not a finding.
    """
    z = np.asarray(z, float)
    z = z[np.isfinite(z)]

    if family == "empirical":
        # fully non-parametric: the residuals ARE the shape. No parameter, so no collapse value.
        return standardize_grid(z), {"family": "empirical", "n_fit": int(z.size)}

    if family == "normal":
        return standardize_grid(rng.standard_normal(_GRID_SIM)), {"family": "normal"}

    def grid_for(params: tuple[float, ...]) -> np.ndarray:
        g = np.random.default_rng(20260819)          # a FIXED grid rng: the objective must be
        if family == "skew_normal":                  # deterministic in the parameters, or the
            raw = _skew_normal_draws(params[0], _GRID_SIM, g)   # optimiser chases Monte-Carlo noise
        elif family == "skew_t":
            raw = _skew_t_draws(params[0], params[1], _GRID_SIM, g)
        elif family == "mixture":
            raw = _mixture_draws(params[0], params[1], params[2], params[3], _GRID_SIM, g)
        elif family == "student_t":
            raw = _student_t_draws(params[0], _GRID_SIM, g)
        else:
            raise KeyError(f"NCAAF-P2.5: unknown standardized-marginal family {family!r}")
        return standardize_grid(raw)

    if family == "skew_normal":
        r = minimize_scalar(lambda a: grid_crps_vs_sample(grid_for((a,)), z),
                            bounds=ALPHA_BOUNDS, method="bounded",
                            options={"xatol": 1e-3})
        a = float(np.clip(r.x, *ALPHA_BOUNDS))
        return grid_for((a,)), {"family": family, "alpha": round(a, 4), "collapse_at": "alpha=0"}

    if family == "student_t":
        r = minimize_scalar(lambda ld: grid_crps_vs_sample(grid_for((float(np.exp(ld)),)), z),
                            bounds=(np.log(DOF_BOUNDS[0]), np.log(DOF_BOUNDS[1])),
                            method="bounded", options={"xatol": 1e-3})
        nu = float(np.clip(np.exp(r.x), *DOF_BOUNDS))
        return grid_for((nu,)), {"family": family, "dof": round(nu, 3), "collapse_at": "dof→∞"}

    if family == "skew_t":
        best, best_p = np.inf, (0.0, 30.0)
        # a coarse grid then a local polish: the 2-D CRPS surface is smooth but flat near α=0, so a
        # bare local optimiser from one start is not trustworthy here.
        for a in np.linspace(-2.0, 2.0, 9):
            for nu in (4.0, 6.0, 10.0, 20.0, 40.0):
                v = grid_crps_vs_sample(grid_for((float(a), float(nu))), z)
                if v < best:
                    best, best_p = v, (float(a), float(nu))
        res = minimize(lambda p: grid_crps_vs_sample(
            grid_for((float(np.clip(p[0], *ALPHA_BOUNDS)),
                      float(np.clip(np.exp(p[1]), *DOF_BOUNDS)))), z),
            np.array([best_p[0], np.log(best_p[1])]), method="Nelder-Mead",
            options={"xatol": 1e-2, "fatol": 1e-6, "maxiter": 120})
        a = float(np.clip(res.x[0], *ALPHA_BOUNDS))
        nu = float(np.clip(np.exp(res.x[1]), *DOF_BOUNDS))
        return grid_for((a, nu)), {"family": family, "alpha": round(a, 4), "dof": round(nu, 3),
                                   "collapse_at": "alpha=0 and dof→∞"}

    if family == "mixture":
        best, best_p = np.inf, (0.5, 0.0, 1.0, 1.0)
        for w1 in (0.2, 0.35, 0.5, 0.65, 0.8):
            for shift in (0.0, 0.3, 0.6, 1.0):
                for s1 in (0.6, 0.9):
                    for s2 in (1.0, 1.5, 2.0):
                        v = grid_crps_vs_sample(grid_for((w1, shift, s1, s2)), z)
                        if v < best:
                            best, best_p = v, (w1, shift, s1, s2)
        res = minimize(lambda p: grid_crps_vs_sample(grid_for((
            float(np.clip(p[0], 0.02, 0.98)), float(p[1]),
            float(np.clip(np.exp(p[2]), 0.05, 5.0)), float(np.clip(np.exp(p[3]), 0.05, 5.0)))), z),
            np.array([best_p[0], best_p[1], np.log(best_p[2]), np.log(best_p[3])]),
            method="Nelder-Mead", options={"xatol": 1e-2, "fatol": 1e-6, "maxiter": 200})
        w1 = float(np.clip(res.x[0], 0.02, 0.98))
        shift = float(res.x[1])
        s1 = float(np.clip(np.exp(res.x[2]), 0.05, 5.0))
        s2 = float(np.clip(np.exp(res.x[3]), 0.05, 5.0))
        return grid_for((w1, shift, s1, s2)), {
            "family": family, "w1": round(w1, 4), "shift": round(shift, 4),
            "s1": round(s1, 4), "s2": round(s2, 4),
            "collapse_at": "shift=0 and s1=s2 (one component)"}

    raise KeyError(f"NCAAF-P2.5: unknown standardized-marginal family {family!r}")


# ===========================================================================
# Dependence + the copula engine
# ===========================================================================

def normal_scores_rho(a: np.ndarray, b: np.ndarray) -> float:
    """Gaussian-copula dependence: Pearson correlation of the two NORMAL SCORES.

    The right estimator for a copula arm — the Pearson correlation of raw residuals confounds the
    dependence with the marginal shapes the copula arms deliberately change.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if a.size < 8:
        return 0.0
    from scipy.stats import norm, rankdata
    n = a.size
    za = norm.ppf(rankdata(a) / (n + 1.0))
    zb = norm.ppf(rankdata(b) / (n + 1.0))
    return float(np.clip(np.corrcoef(za, zb)[0, 1], -0.95, 0.95))


def draw_copula(
    mu_m: np.ndarray, mu_t: np.ndarray, sig_m: np.ndarray, sig_t: np.ndarray,
    grid_m: np.ndarray, grid_t: np.ndarray, rho: float,
    rng: np.random.Generator, n_draws: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Gaussian copula ⊗ arbitrary standardized marginals → (margin, total) draws.

    Correlated standard normals → uniforms → the per-axis standardized quantile grid → shifted by μ
    and scaled by the per-game σ. Because both grids are mean-0/sd-1 the drawn predictive has mean μ
    and sd σ BY CONSTRUCTION, which is what makes C7 (mean preservation) hold for every arm that
    routes through here.
    """
    from scipy.stats import norm
    n = mu_m.shape[0]
    z1 = rng.standard_normal((n, n_draws))
    z2 = rng.standard_normal((n, n_draws))
    z2 = rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2
    u1 = norm.cdf(z1)
    u2 = norm.cdf(z2)
    e_m = sample_from_grid(u1.ravel(), grid_m).reshape(u1.shape)
    e_t = sample_from_grid(u2.ravel(), grid_t).reshape(u2.shape)
    return (mu_m[:, None] + sig_m[:, None] * e_m,
            mu_t[:, None] + sig_t[:, None] * e_t)


# ===========================================================================
# The conditional-variance sub-model (arm `cond_het`)
# ===========================================================================

def fit_log_variance(resid: np.ndarray, Z: np.ndarray, *, ridge: float = 1.0) -> np.ndarray:
    """γ for  log σ² = γ₀ + Z·γ  by Gaussian NLL on held-out residuals, ridge-penalised.

    The ridge penalty is on the SLOPES only (never the intercept): at ~700 inner-holdout rows an
    unpenalised 15-driver log-variance fit is free to chase noise, and an over-fitted variance model
    would present as a shape win that does not reproduce. It is a design quantity fixed before the
    run, not tuned on the result.
    """
    r = np.asarray(resid, float)
    Z = np.asarray(Z, float)
    n, p = Z.shape
    X = np.column_stack([np.ones(n), Z])
    r2 = r * r

    def nll(theta: np.ndarray) -> float:
        lv = np.clip(X @ theta, -6.0, 12.0)
        v = np.exp(lv)
        pen = ridge * float(np.sum(theta[1:] ** 2))
        return 0.5 * float(np.sum(lv + r2 / v)) + pen

    theta0 = np.zeros(p + 1)
    theta0[0] = np.log(max(float(np.mean(r2)), 1e-6))
    res = minimize(nll, theta0, method="L-BFGS-B",
                   options={"maxiter": 500, "ftol": 1e-10})
    return np.asarray(res.x, float)


def apply_log_variance(theta: np.ndarray, Z: np.ndarray, floor: float = MIN_SIGMA) -> np.ndarray:
    """γ, drivers → per-game σ (floored at the same MIN_SIGMA the incumbent obeys)."""
    Z = np.asarray(Z, float)
    X = np.column_stack([np.ones(Z.shape[0]), Z])
    return np.clip(np.exp(0.5 * np.clip(X @ np.asarray(theta, float), -6.0, 12.0)), floor, None)


# ===========================================================================
# Per-side score forms (arms `home_away`, `key_number`)
# ===========================================================================

def fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """NegBin dispersion MLE for team points (the same estimator P1.4's `count` form uses)."""
    y = np.asarray(y, float)
    mu = np.clip(np.asarray(mu, float), MIN_MU_POINTS, None)
    from scipy.special import gammaln

    def nll(log_r: float) -> float:
        r = float(np.exp(log_r))
        p = r / (r + mu)
        ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
              + r * np.log(p) + y * np.log1p(-p + 1e-12))
        return float(-np.mean(ll))

    res = minimize_scalar(nll, bounds=(np.log(1.0), np.log(5_000.0)), method="bounded")
    return float(np.clip(np.exp(res.x), 1.0, 5_000.0))


def draw_correlated_negbin(
    mu_home: np.ndarray, mu_away: np.ndarray, r_home: float, r_away: float,
    rho: float, rng: np.random.Generator, n_draws: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Correlated NegBin team points via a Gaussian copula → (home_pts, away_pts).

    ⭐ The difference from P1.4's `count` form, which FORCED independence: the two sides of one
    football game are not independent given the strengths (a shootout raises both), and forcing
    ρ_sides = 0 constrains the derived total's dispersion. NegBin means are exact, so C7 holds.
    """
    from scipy.stats import norm, nbinom
    n = mu_home.shape[0]
    z1 = rng.standard_normal((n, n_draws))
    z2 = rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * rng.standard_normal((n, n_draws))
    mh = np.clip(mu_home, MIN_MU_POINTS, None)[:, None]
    ma = np.clip(mu_away, MIN_MU_POINTS, None)[:, None]
    yh = nbinom.ppf(np.clip(norm.cdf(z1), 1e-9, 1 - 1e-9), r_home, r_home / (r_home + mh))
    ya = nbinom.ppf(np.clip(norm.cdf(z2), 1e-9, 1 - 1e-9), r_away, r_away / (r_away + ma))
    return yh.astype(float), ya.astype(float)


def score_lattice_pmf(points: np.ndarray, *, smooth: float = 1.0) -> np.ndarray:
    """The EMPIRICAL team-score lattice pmf over 0..LATTICE_MAX (the key-number substrate).

    This is where football's key numbers live: the empirical mass at 3/7/10/13/14/17/20/21/24/28 is
    several times the mass at 1/2/4/5/8/11. `key_number` samples on THIS lattice, so it reproduces
    the key numbers BY CONSTRUCTION rather than by a hand-written bump table (which would be a
    parameter chosen to produce the answer). `smooth` is a Laplace count so an unobserved score is
    improbable, never impossible.
    """
    p = np.asarray(points, float)
    p = p[np.isfinite(p)]
    counts = np.bincount(np.clip(np.rint(p), 0, LATTICE_MAX).astype(int), minlength=LATTICE_MAX + 1)
    pmf = counts.astype(float) + float(smooth)
    return pmf / pmf.sum()


def tilted_lattice_pmf(
    pmf: np.ndarray, mu: np.ndarray, target_var: np.ndarray, *, n_iter: int = 8,
) -> np.ndarray:
    """The empirical score lattice TILTED to hit this game's target (mean, variance) EXACTLY.

        p_g(s)  ∝  pmf_emp(s) · exp( −(s − c_g)² / (2 b_g²) )

    ⚠️ **THE BANDWIDTH IS NOT THE RESULTING SD.** Composing a Gaussian kernel of width `b` with an
    empirical pmf of spread `s_e` gives `1/var = 1/s_e² + 1/b²`, so a tilt at `b = σ_target`
    systematically UNDER-disperses (measured on the smoke: a 11.8-point target came out at ~9.0 and
    the arm's `calib_80` read 0.694). An arm crippled that way is not a test of the key-number
    hypothesis — it is a straw man that would lose for an implementation reason. So BOTH the centre
    and the bandwidth are solved:

      * `c_g` by Newton on  dE[s]/dc = Var(s)/b²  → the mean lands on μ_g. Without it the tilt drags
        the mean toward the empirical average and this arm competes on the MEAN, which C7 forbids;
      * `b_g` by the Gaussian-composition identity `1/b² ← 1/b² + (1/v_target − 1/v_achieved)`,
        which is exact for a Gaussian pmf and converges in a few passes for a real one.

    ⭐ What survives the correction is the arm's actual hypothesis: the empirical lattice carries
    football's key-number mass (3/7/10/14/17/21/24/28) BY CONSTRUCTION, and this asks whether that
    discrete structure beats a continuous predictive at the SAME mean and variance.
    """
    s = np.arange(LATTICE_MAX + 1, dtype=float)
    mu = np.asarray(mu, float)
    v_t = np.clip(np.asarray(target_var, float), 1.0, None)
    log_pmf = np.log(np.asarray(pmf, float))[None, :]
    # analytic initialisation from the composition identity (s_e = the empirical pmf's own spread)
    pe = np.asarray(pmf, float)
    m_e = float(pe @ s)
    v_e = float(pe @ (s * s) - m_e * m_e)
    inv_b2 = np.clip(1.0 / v_t - 1.0 / max(v_e, 1e-6), 1e-6, 1.0)
    c = mu.copy()

    def _moments(c_, inv_b2_):
        w = log_pmf - 0.5 * inv_b2_[:, None] * (s[None, :] - c_[:, None]) ** 2
        w -= w.max(axis=1, keepdims=True)
        p = np.exp(w)
        p /= p.sum(axis=1, keepdims=True)
        m1 = p @ s
        return p, m1, np.clip(p @ (s * s) - m1 * m1, 1e-6, None)

    def _solve_mean(c_, inv_b2_, n=6):
        for _ in range(n):
            _, m1, var = _moments(c_, inv_b2_)
            c_ = np.clip(c_ + (mu - m1) / np.clip(inv_b2_, 1e-9, None) / var,
                         -60.0, LATTICE_MAX + 60.0)
        return c_

    for _ in range(n_iter):
        c = _solve_mean(c, inv_b2)               # inner: land the MEAN at μ
        _, _, var = _moments(c, inv_b2)          # outer: land the VARIANCE at v_target
        inv_b2 = np.clip(inv_b2 + (1.0 / v_t - 1.0 / var), 1e-6, 1.0)
    # ⚠️ the loop MUST end on a mean pass. Ending on the variance update leaves `c` stale against the
    # new bandwidth, and the mean drifts — measured at 2.29 points on the smoke and caught by C7
    # (which is exactly what a design invariant enforced on the SCORED samples is for).
    c = _solve_mean(c, inv_b2, n=10)
    p, _, _ = _moments(c, inv_b2)
    return p


def tilted_lattice_draw(
    pmf: np.ndarray, mu: np.ndarray, target_var: np.ndarray, u: np.ndarray,
) -> np.ndarray:
    """Inverse-CDF sample from `tilted_lattice_pmf`. `u` is (n_games, n_draws) uniforms."""
    p = tilted_lattice_pmf(pmf, mu, target_var)
    cdf = np.cumsum(p, axis=1)
    cdf[:, -1] = 1.0
    idx = np.array([np.searchsorted(cdf[i], u[i], side="left") for i in range(cdf.shape[0])])
    return np.clip(idx, 0, LATTICE_MAX).astype(float)


# ===========================================================================
# The true bivariate Student-t (arm `student_t`) — per-game σ
# ===========================================================================

def draw_bivariate_t(
    mu_m: np.ndarray, mu_t: np.ndarray, sig_m: np.ndarray, sig_t: np.ndarray,
    rho: float, dof: float, rng: np.random.Generator, n_draws: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Bivariate Student-t: a Normal scale-mixed by an inverse-chi-square, scaled to unit variance.

    ⭐ Deliberately NOT routed through `draw_copula`. A bivariate t is **not** a Gaussian copula with
    t marginals — it carries TAIL DEPENDENCE (both axes blow out together), and whether football's
    (margin, total) pair does that is exactly the thing worth testing separately from the marginal
    shape. Folding it into the copula engine would delete the hypothesis.

    This is the per-game-σ generalisation of the shipped scalar-σ `_bivariate_t` in
    `ncaaf_game_distribution`; a guard asserts the two agree when σ is constant, so this cannot
    silently become a second, divergent implementation (the E9.61 two-renderers hazard).
    """
    n = np.asarray(mu_m).shape[0]
    z1 = rng.standard_normal((n, n_draws))
    z2 = rng.standard_normal((n, n_draws))
    g = rng.chisquare(dof, size=(n, n_draws))
    w = np.sqrt(dof / np.maximum(g, 1e-9))
    var_scale = np.sqrt(dof / (dof - 2.0)) if dof > 2.0 else 1.0
    m_std = z1 * w / var_scale
    t_std = (rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2) * w / var_scale
    sm = np.asarray(sig_m, float)
    st = np.asarray(sig_t, float)
    sm = sm[:, None] if sm.ndim else sm
    st = st[:, None] if st.ndim else st
    return np.asarray(mu_m)[:, None] + m_std * sm, np.asarray(mu_t)[:, None] + t_std * st


# ===========================================================================
# The distributional-boosting foil (arm `quantile_boost`)
# ===========================================================================

def fit_quantile_boost(
    resid: np.ndarray, Z_fit: np.ndarray, Z_apply: np.ndarray,
    *, levels: np.ndarray = QB_LEVELS, n_estimators: int = QB_N_ESTIMATORS,
) -> np.ndarray:
    """LightGBM quantile regression of the RESIDUAL on the variance drivers → (n_apply, n_levels).

    The doc's "quantile / distributional-boosting foil": instead of assuming a shape, LEARN the whole
    conditional residual distribution from the drivers. Two disciplines applied here:

      * the returned quantile rows are made **MONOTONE** (`np.maximum.accumulate`) — independent
        per-level fits can cross, and a crossed quantile function is not a distribution; and
      * each row is **RE-CENTRED to mean 0** so the arm stays inside the frozen-mean family (§1). A
        quantile fit carries no mean guarantee, so without this the arm would be competing on the
        MEAN and its ΔCRPS would be uninterpretable. The centring is declared, not incidental.
    """
    import lightgbm as lgb
    r = np.asarray(resid, float)
    Zf, Za = np.asarray(Z_fit, float), np.asarray(Z_apply, float)
    out = np.empty((Za.shape[0], len(levels)), float)
    for j, q in enumerate(levels):
        # ⭐ `init_score` = the UNCONDITIONAL residual quantile, so the booster only ever learns the
        # DEPARTURE from the marginal. Without it a 17-level quantile fit on ~700 rows shrinks its
        # extreme quantiles toward the middle and the arm reads as badly under-dispersed
        # (measured on the smoke: calib_80 0.687) — i.e. the foil would lose for an estimator
        # reason rather than for its hypothesis. With it, a driver set carrying NO information
        # collapses the arm onto the empirical marginal, which is the correct null behaviour for a
        # foil and makes its loss (or win) attributable.
        base = float(np.quantile(r, float(q)))
        m = lgb.LGBMRegressor(objective="quantile", alpha=float(q), num_leaves=QB_NUM_LEAVES,
                              learning_rate=0.05, n_estimators=n_estimators,
                              min_child_samples=QB_MIN_CHILD, random_state=42, verbose=-1)
        m.fit(Zf, r, init_score=np.full(len(r), base))
        out[:, j] = base + m.predict(Za)
    out = np.maximum.accumulate(out, axis=1)
    return out - quantile_function_mean(out, levels)[:, None]


def tail_scales(Q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The exponential tail scales of a per-game quantile matrix — ONE definition, two consumers.

    `quantile_function_mean` (which re-centres the arm) and `draw_pergame_quantiles` (which samples
    it) MUST agree about the tails, or the centring is computed for a different distribution than the
    one drawn and the arm silently leaves the frozen-mean family (measured 0.238 points on the smoke,
    caught by C7). Two renderers of one rule is the E9.61 hazard, so there is only one.
    """
    Q = np.asarray(Q, float)
    lo = np.maximum(Q[:, 2] - Q[:, 0], 1e-6)
    hi = np.maximum(Q[:, -1] - Q[:, -3], 1e-6)
    return lo, hi


def quantile_function_mean(Q: np.ndarray, levels: np.ndarray = QB_LEVELS) -> np.ndarray:
    """Exact mean of the per-game quantile function INCLUDING the exponential tails.

    ∫₀¹ F⁻¹(τ)dτ over the three regions the sampler actually uses:
      lower tail  ∫₀^{τ₀} (q₀ + s_lo·log(u/τ₀)) du = τ₀·q₀ − s_lo·τ₀
      body        the trapezoid over the knots
      upper tail  ∫_{τ_k}^{1} (q_k + s_hi·log((1−τ_k)/(1−u))) du = (1−τ_k)·q_k + s_hi·(1−τ_k)
    """
    Q = np.asarray(Q, float)
    tau = np.asarray(levels, float)
    lo_s, hi_s = tail_scales(Q)
    t0, tk = float(tau[0]), float(tau[-1])
    trap = np.trapezoid(Q, tau, axis=1) if hasattr(np, "trapezoid") else np.trapz(Q, tau, axis=1)
    return trap + t0 * Q[:, 0] - lo_s * t0 + (1.0 - tk) * Q[:, -1] + hi_s * (1.0 - tk)


def draw_pergame_quantiles(
    mu_m: np.ndarray, mu_t: np.ndarray, Q_m: np.ndarray, Q_t: np.ndarray,
    rho: float, rng: np.random.Generator, n_draws: int,
    *, levels: np.ndarray = QB_LEVELS,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample from PER-GAME residual quantile functions, joined by a Gaussian copula.

    ⚠️ Beyond the outer knots the tail is EXPONENTIAL, never flat. A knot-quantile predictive
    extended flat has literally no tails (NF-MARGIN1) — and since half of what this story is looking
    for IS a tail defect, building a tail-less foil would make the comparison meaningless.
    """
    from scipy.stats import norm
    n = np.asarray(mu_m).shape[0]
    z1 = rng.standard_normal((n, n_draws))
    z2 = rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * rng.standard_normal((n, n_draws))
    u1, u2 = norm.cdf(z1), norm.cdf(z2)
    tau = np.asarray(levels, float)

    def _draw(Q: np.ndarray, u: np.ndarray, mu: np.ndarray) -> np.ndarray:
        out = np.empty_like(u)
        lo_t, hi_t = float(tau[0]), float(tau[-1])
        lo_s, hi_s = tail_scales(Q)          # ⭐ the SHARED definition — see `tail_scales`
        for i in range(Q.shape[0]):
            q = Q[i]
            v = np.interp(u[i], tau, q)
            lo_scale, hi_scale = float(lo_s[i]), float(hi_s[i])
            lo = u[i] < lo_t
            hi = u[i] > hi_t
            if lo.any():
                v[lo] = q[0] + lo_scale * np.log(np.clip(u[i][lo] / lo_t, 1e-12, 1.0))
            if hi.any():
                v[hi] = q[-1] + hi_scale * np.log(
                    np.clip((1.0 - hi_t) / np.clip(1.0 - u[i][hi], 1e-12, None), 1.0, None))
            out[i] = v
        return np.asarray(mu, float)[:, None] + out

    return _draw(Q_m, u1, mu_m), _draw(Q_t, u2, mu_t)


# ===========================================================================
# The four scoring instruments the pre-registration gates on
# ===========================================================================

def crps_ensemble(y: np.ndarray, samples: np.ndarray) -> np.ndarray:
    """Per-game CRPS from predictive SAMPLES: E|X−y| − ½E|X−X'| (the sorted-sample identity).

    Vendored from `betting_ml.utils.promotion_gate` so this module stays import-light for the fast
    gate (that module pulls the whole promotion stack). Pinned byte-equivalent by a guard test — one
    policy, two call sites is exactly the E9.61 two-renderers hazard, so the guard asserts they
    AGREE numerically rather than trusting the copy.
    """
    y = np.asarray(y, float)
    S = np.asarray(samples, float)
    if S.ndim == 1:
        S = S[:, None]
    m = S.shape[1]
    term1 = np.mean(np.abs(S - y[:, None]), axis=1)
    Ss = np.sort(S, axis=1)
    coef = 2 * np.arange(1, m + 1) - m - 1
    term2 = (2.0 / (m * m)) * np.sum(coef[None, :] * Ss, axis=1)
    return term1 - 0.5 * term2


def tail_crps(y: np.ndarray, samples: np.ndarray, *, q: tuple[float, float] = TAIL_Q,
              n_grid: int = 160) -> float:
    """Threshold-weighted CRPS reading ONLY the tails (clause C5).

        twCRPS = ∫ (F(z) − 1{y ≤ z})² w(z) dz ,   w(z) = 1 OUTSIDE the central 80% of the
                                                  realised marginal, 0 inside.

    ⭐ Why a separate statistic: plain CRPS is dominated by the bulk, so an arm can improve it while
    leaving the tails wrong — and tail thickness is half of what this story is looking for. The
    weight region is set from the REALISED marginal (identical for every arm on a fold), so no arm
    can move its own goalposts.
    """
    y = np.asarray(y, float)
    S = np.asarray(samples, float)
    lo, hi = np.quantile(y, q[0]), np.quantile(y, q[1])
    span = max(float(np.quantile(y, 0.995) - np.quantile(y, 0.005)), 1.0)
    grid = np.concatenate([
        np.linspace(lo - 1.5 * span, lo, n_grid // 2),
        np.linspace(hi, hi + 1.5 * span, n_grid // 2),
    ])
    dz = np.gradient(grid)
    F = (S[:, :, None] <= grid[None, None, :]).mean(axis=1) if S.shape[1] <= 1200 else None
    if F is None:                       # memory-safe path for a wide draw array
        F = np.empty((S.shape[0], grid.size), float)
        for j, z in enumerate(grid):
            F[:, j] = (S <= z).mean(axis=1)
    ind = (y[:, None] <= grid[None, :]).astype(float)
    return float((((F - ind) ** 2) * dz[None, :]).sum(axis=1).mean())


def joint_pit_dev(
    margin_s: np.ndarray, total_s: np.ndarray,
    y_margin: np.ndarray, y_total: np.ndarray, rng: np.random.Generator,
) -> dict[str, float]:
    """JOINT calibration (clause C6) via the 45° projections of the (margin, total) plane.

    `home_pts = (total + margin)/2` and `away_pts = (total − margin)/2` are the two directions the
    joint is actually *made of*, and a predictive whose two marginals are individually flat can still
    get the pair wrong (wrong ρ, or the right ρ with the wrong tail dependence) — which shows up
    exactly here and nowhere in a per-axis PIT. This is the same "derive the markets from the joint"
    coherence the model claims, read as a calibration statistic.
    """
    hp_s = (total_s + margin_s) / 2.0
    ap_s = (total_s - margin_s) / 2.0
    hp_y = (np.asarray(y_total, float) + np.asarray(y_margin, float)) / 2.0
    ap_y = (np.asarray(y_total, float) - np.asarray(y_margin, float)) / 2.0
    hp = pit_flatness(randomized_pit(hp_y, hp_s, rng))
    ap = pit_flatness(randomized_pit(ap_y, ap_s, rng))
    return {
        "home_pts_pit_dev": float(hp["max_decile_dev"]),
        "away_pts_pit_dev": float(ap["max_decile_dev"]),
        "joint_pit_dev": float(max(hp["max_decile_dev"], ap["max_decile_dev"])),
        "home_pts_pit_flat": bool(hp["is_flat"]),
        "away_pts_pit_flat": bool(ap["is_flat"]),
    }


def mean_preservation(
    margin_s: np.ndarray, total_s: np.ndarray, mu_margin: np.ndarray, mu_total: np.ndarray,
) -> dict[str, Any]:
    """Clause C7 — the FROZEN-MEAN design invariant, measured on the SCORED samples.

    Every arm must leave the pooled predictive mean where the frozen μ put it. An arm that drifts has
    left the declared shape family and its ΔCRPS is a mean effect wearing a shape costume, so this
    is a REFUSAL condition, not a diagnostic. Measured here, on the arrays the metric is computed
    from — a check that re-derives the samples itself would pass while the scored path broke
    (NF-W7d).
    """
    dm = float(np.mean(margin_s) - np.mean(mu_margin))
    dt = float(np.mean(total_s) - np.mean(mu_total))
    return {"mean_shift_margin": round(dm, 4), "mean_shift_total": round(dt, 4),
            "tol": MEAN_PRESERVATION_TOL,
            "ok": bool(abs(dm) <= MEAN_PRESERVATION_TOL and abs(dt) <= MEAN_PRESERVATION_TOL)}


# ===========================================================================
# The registry — ⛔ CLOSED at pre-registration; a guard pins it
# ===========================================================================

@dataclass(frozen=True)
class Shape:
    """One pre-registered shape family."""
    arm: str
    doc_item: str            # the doc §4.1 line it implements
    nests_incumbent: bool    # §5.3 — does it contain the incumbent as a limit?
    collapse: str            # the parameter value at which it becomes the incumbent
    uses_drivers: bool       # does it consume the §2.2 variance drivers?


SHAPES: tuple[Shape, ...] = (
    Shape("incumbent", "the served strength_posterior form (the FOIL)", True, "—", False),
    Shape("cond_het", "bivariate Gaussian w/ conditional heteroskedasticity", True,
          "γ = the log_strength_var term alone", True),
    Shape("student_t", "bivariate Student-t", True, "dof → ∞", False),
    Shape("skew_normal", "skew-normal", True, "alpha = 0", False),
    Shape("skew_t", "skew-t", True, "alpha = 0 and dof → ∞", False),
    Shape("mixture", "Gaussian / regime mixture", True, "shift = 0 and s1 = s2", False),
    Shape("copula", "copula w/ independent (non-parametric) marginals", False,
          "the empirical marginal happens to be Normal", False),
    Shape("home_away", "separate home/away score distributions → transform", False,
          "r → ∞ with rho_sides = 0 (the P1.4 `count` form)", False),
    Shape("key_number", "discrete-score simulation (mass at 3/7/10/14)", False,
          "a flat empirical lattice", False),
    Shape("quantile_boost", "quantile / distributional-boosting foil", False,
          "constant quantiles ⇒ a homoscedastic empirical marginal", True),
)

#: the FOIL every candidate is measured against (the served config).
FOIL_ARM: str = "incumbent"
#: the nine candidates.
CANDIDATE_ARMS: tuple[str, ...] = tuple(s.arm for s in SHAPES if s.arm != FOIL_ARM)
#: ⭐ the DECLARED FIELD for DSR multiplicity — foil + candidates, anchors EXCLUDED.
DECLARED_FIELD_SIZE: int = len(SHAPES)

#: the run-validity anchors. ⛔ DIAGNOSTIC, never trials: an anchor that polices the metric must not
#: set the gate's own bar (MH2.1 a — a peeking oracle's Sharpe drove `V` and made DSR unclearable
#: for a purely arithmetic reason). They are excluded from BOTH `n_trials` and `V`.
GENERIC_ANCHORS: tuple[str, ...] = ("permute", "zero_width", "max_width", "coverage_target")

#: what each anchor is REQUIRED to do, declared before the run so a surprise cannot be re-read as a
#: finding. `permute` is the only one that can be a TIE — the marginal-shape arms are
#: permutation-INVARIANT by construction (NF-D16: register a near-vacuous anchor as an expected tie
#: in advance and prove it, rather than presenting the tie as a passed test).
ANCHOR_EXPECTATION: dict[str, str] = {
    "permute": "must LOSE to cond_het (it destroys the conditional structure while preserving the "
               "marginal); it lands at/near the incumbent, and beating cond_het would mean the "
               "conditional-variance channel is not real",
    "zero_width": "must LOSE the metric AND FAIL the coverage floor (maximally sharp)",
    "max_width": "must SATISFY the coverage floor and LOSE the metric — the NF1.8 proof that the "
                 "floor is a CONSTRAINT a degenerate satisfies, not a criterion it wins",
    "coverage_target": "must SATISFY the coverage constraint and LOSE the metric — the E2.1-r proof "
                       "that calib_80 is a FLOOR and never a target",
}
