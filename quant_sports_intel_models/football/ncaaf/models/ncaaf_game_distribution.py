"""ncaaf_game_distribution.py — NCAAF-P1.4 (the JOINT game scoring distribution).

WHY THIS EXISTS
---------------
P1.4 is the NCAAF game model. Per the story it is built LEAN: model the JOINT scoring
distribution ONCE and DERIVE all three markets, mirroring the MLB E2 pattern (predict the
per-side distribution, convolve, read off total / team-total / run-diff) rather than training
three unlinked target models. For football the natural joint object is the pair

    (margin, total)   where margin = home_points − away_points,  total = home_points + away_points

because those two axes are what the three markets read off directly:

    * H2H (moneyline)  →  P(home wins)    = P(margin > 0)
    * spread           →  P(home covers)  = P(margin > line)     (line = −closing home spread)
    * total (O/U)      →  P(over)         = P(total > line)

The margin distribution alone prices H2H + spread; the total distribution prices the over/under.
Keeping them JOINT (a shared bivariate draw) is what makes a same-game parlay coherent and lets
the two axes carry a small but real correlation (favourites tend to appear in higher-scoring
games). The single-market probabilities are marginal, so ρ never changes them — it only matters
for joint/parlay reads and is carried for that.

This module is the pure distributional CORE (no learners, no IO — fully unit-tested):

  * FOUR pre-registered per-game distributional FORMS (the §0.5 ≥3-form axis), each a sampler
    over (margin, total) given the learner's point predictions (μ_margin, μ_total):
      - `gaussian`  — bivariate Normal(μ, Σ); the textbook football form (Massey/Sagarin), and
                      the one that recalibrates the P1.2 `strength_margin_sd` from "1.5× too
                      tight parameter uncertainty" into a held-out-calibrated predictive σ.
      - `student_t` — bivariate Student-t (heavier tails); CFB has fat-tailed blowouts and
                      back-door covers a Normal under-weights. df fit on held-out residuals.
      - `native`    — per-game σ from a native-distributional learner (NGBoost), the
                      heteroscedastic foil (a pick'em and a 40-point mismatch are not equally
                      certain).
      - `count`     — model home/away POINTS as NegBin counts (means derived from the same two
                      predictions: μ_home=(μ_total+μ_margin)/2, μ_away=(μ_total−μ_margin)/2) and
                      convolve → margin=h−a, total=h+a. The MLB-style count foil: does a discrete
                      point-count structure beat the Gaussian margin/total?
  * held-out dispersion CALIBRATION (the E13.6 pattern): σ_margin, σ_total, ρ, dof, or NegBin r
    fit on OOS residuals — never parameter uncertainty, never in-sample.
  * `derive_markets` → the three market sample arrays; the calibration diagnostics
    (`randomized_pit`, `pit_flatness`, `interval_coverage`, `prob_over`) are form-AGNOSTIC and
    reused verbatim from the MLB E2.3 `totals_distribution`.

SELECTION-METRIC HYGIENE (carried from MLB E2.1-r): margin/total are wide-support integers, so
the inclusive-integer interval-coverage inflation is mild here — but the discipline still holds:
gate on randomised-PIT FLATNESS (`max_decile_dev`), keep `calib_80 ≥ 0.80` as a FLOOR not a
target, and SANITY-CHECK against an ORACLE FLOOR (truth drawn from exactly the form being scored
is the best any model of that form can do — nothing may score better; the inverted-metric tell).
`test_oracle_is_the_scoring_floor` is the permanent guard.

HONEST FRAME: a market-BLIND joint distribution is PRODUCT value (calibrated 3-market
probabilities), NOT an edge claim. Whether it beats a closing line is P1.4's vs-market leg under
full deflation; `best_alpha = 0` until that gate clears.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln
from scipy.stats import t as student_t

# Form-agnostic calibration + serving machinery — reuse the MLB E2.3 tested implementations
# verbatim (they take a drawn (n_games, n_draws) sample array and know nothing about the form).
from betting_ml.utils.totals_distribution import (  # noqa: F401  (re-exported for P1.4 consumers)
    DEFAULT_QUANTILES,
    interval_coverage,
    pit_flatness,
    prob_over,
    prob_push,
    quantile_grid,
    randomized_pit,
)

# The pre-registered per-game distributional forms (the §0.5 ≥3-form bake-off axis).
#   gaussian / student_t / native / count — see the module docstring.
#   strength_posterior — the POSTERIOR-PREDICTIVE form (added 2026-07-22 per the PM small-sample
#     nudge): the predictive width PROPAGATES the P1.2 team-strength posterior per game, so a
#     thin-sample early-season game (wide strength posterior) is honestly WIDER than a week-14
#     game (tight posterior). At 12–15 games/team a point-estimate + HOMOSCEDASTIC σ understates
#     early-season uncertainty (the "strength_margin_sd is ~1.5× too tight" trap) — this form is
#     the principled fix, and (per §0.5) it is a CANDIDATE that must beat the homoscedastic
#     gaussian on PIT-flatness, not an assumed win. Its per-game σ combines an irreducible game
#     σ₀ with a RECALIBRATED (E13.6) strength-posterior term: σ_g² = σ₀² + k²·(home_sd² + away_sd²),
#     with (σ₀, k) MLE'd on HELD-OUT residuals — k is exactly the recalibration factor the raw
#     P1.2 sd needs. It is heteroscedastic but PRINCIPLED (the posterior width), distinct from the
#     `native` foil's LEARNED σ (which the bake-off found under-covers).
FORMS: tuple[str, ...] = ("gaussian", "student_t", "native", "count", "strength_posterior")

# The three markets the joint distribution is responsible for. `home_win` is a point event
# derived from the margin marginal; the two DISTRIBUTIONS that carry a shape to calibrate are
# `margin` and `total`, so those are what the PIT gate scores.
SCORED_DISTS: tuple[str, ...] = ("margin", "total")

# NegBin dispersion optimiser band (the count foil); r large ⇒ Poisson limit.
_R_BOUNDS: tuple[float, float] = (1.0, 5_000.0)
# Student-t degrees-of-freedom band. ν→∞ ⇒ Normal; small ν ⇒ heavy tails. Below ~3 the variance
# is undefined, so the floor keeps the moment-matched scale meaningful.
_DOF_BOUNDS: tuple[float, float] = (3.0, 60.0)
# Predictive σ floors — a college game's margin/total sd never collapses near zero, and a tiny
# σ would make the PIT explode on a single surprising result.
_MIN_SIGMA_MARGIN: float = 3.0
_MIN_SIGMA_TOTAL: float = 3.0
# Points are non-negative; clip a NegBin mean off zero for a well-defined draw.
_MIN_MU_POINTS: float = 0.5


# ---------------------------------------------------------------------------
# Held-out dispersion fits (leakage-safe when the residuals are OOS)
# ---------------------------------------------------------------------------

@dataclass
class JointDispersion:
    """The held-out-calibrated spread of the joint (margin, total) predictive.

    `sigma_margin`/`sigma_total` are residual standard deviations; `rho` their correlation;
    `dof` the Student-t degrees of freedom (student_t only); `r_home`/`r_away` the NegBin point
    dispersions (count only). Every field is fit on OUT-OF-SAMPLE residuals — this is the E13.6
    recalibration the P1.2 `strength_margin_sd` deliberately did not do.
    """

    sigma_margin: float
    sigma_total: float
    rho: float = 0.0
    dof: float = 30.0
    r_home: float = 200.0
    r_away: float = 200.0
    # strength_posterior form only: σ_g² = σ0² + k²·strength_var (E13.6-recalibrated propagation)
    sigma0_margin: float = 0.0
    k_margin: float = 0.0
    sigma0_total: float = 0.0
    k_total: float = 0.0


def fit_gaussian_dispersion(resid_margin: np.ndarray, resid_total: np.ndarray) -> JointDispersion:
    """σ_margin, σ_total and their correlation ρ from held-out (OOS) residuals.

    resid_* = realised − predicted on held-out games. The plain sample sd/corr IS the MLE of a
    zero-mean bivariate Normal's scale, so no optimiser is needed for the Gaussian form.
    """
    rm = np.asarray(resid_margin, dtype=float)
    rt = np.asarray(resid_total, dtype=float)
    sm = max(float(rm.std(ddof=1)), _MIN_SIGMA_MARGIN)
    st = max(float(rt.std(ddof=1)), _MIN_SIGMA_TOTAL)
    if rm.size < 3 or rm.std() == 0 or rt.std() == 0:
        rho = 0.0
    else:
        rho = float(np.clip(np.corrcoef(rm, rt)[0, 1], -0.95, 0.95))
    return JointDispersion(sigma_margin=sm, sigma_total=st, rho=rho)


def fit_student_t_dof(resid: np.ndarray, sigma: float) -> float:
    """MLE of the Student-t degrees of freedom for a zero-mean, scale-`sigma` residual series.

    Fits ν on the STANDARDISED residuals z = resid / sigma so the scale is factored out — the t
    density is over z with unit scale. Returns a ν in `_DOF_BOUNDS`; a large ν means the tails
    are effectively Normal (no fat-tail benefit), a small ν means heavy tails are real.
    """
    z = np.asarray(resid, dtype=float) / max(float(sigma), 1e-6)

    def nll(log_dof: float) -> float:
        dof = float(np.exp(log_dof))
        return float(-np.sum(student_t.logpdf(z, df=dof)))

    res = minimize_scalar(
        nll, bounds=(np.log(_DOF_BOUNDS[0]), np.log(_DOF_BOUNDS[1])), method="bounded"
    )
    return float(np.clip(np.exp(res.x), *_DOF_BOUNDS))


def fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of a NegBin dispersion r for point counts y with predicted means mu (count form)."""
    y = np.asarray(y, dtype=float)
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU_POINTS, None)

    def nll(log_r: float) -> float:
        r = float(np.exp(log_r))
        p = r / (r + mu)
        ll = gammaln(y + r) - gammaln(r) - gammaln(y + 1.0) + r * np.log(p) + y * np.log1p(-p + 1e-12)
        return float(-np.mean(ll))

    res = minimize_scalar(
        nll, bounds=(np.log(_R_BOUNDS[0]), np.log(_R_BOUNDS[1])), method="bounded"
    )
    return float(np.clip(np.exp(res.x), *_R_BOUNDS))


def sigma_from_native(mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Clip a native learner's per-game σ to a sane floor (the heteroscedastic `native` form)."""
    return np.clip(np.asarray(sigma, dtype=float), _MIN_SIGMA_MARGIN, None)


# strength_posterior: the recalibration factor k is bounded so a degenerate fit can't blow the
# propagated width up without limit (k≈1 means the raw P1.2 posterior sd is used as-is; the E13.6
# finding is it is ~1.5× too tight, so k is expected to land ABOVE 1 if the propagation helps).
_K_BOUNDS: tuple[float, float] = (0.0, 4.0)


def fit_strength_posterior_scale(
    resid: np.ndarray, strength_var: np.ndarray, *, sigma_floor: float = _MIN_SIGMA_MARGIN,
) -> tuple[float, float]:
    """E13.6-recalibrate the strength-posterior propagation on HELD-OUT residuals.

    Fits (σ₀, k) so the per-game predictive variance σ_g² = σ₀² + k²·strength_var makes the
    standardised held-out residual z = resid/σ_g ~ N(0,1) (Gaussian NLL MLE). σ₀ is the
    irreducible game σ (score noise a perfect strength model still can't predict); k RECALIBRATES
    the raw P1.2 posterior sd — k→0 collapses the form to the homoscedastic gaussian (the honest
    outcome if the held-out residual already absorbs the posterior width), k>0 means propagating
    the per-game posterior genuinely widens the thin-sample games. `strength_var` = the summed
    home/away strength posterior variance per game.
    """
    resid = np.asarray(resid, dtype=float)
    sv = np.clip(np.asarray(strength_var, dtype=float), 0.0, None)

    def nll(theta: np.ndarray) -> float:
        s0 = float(np.exp(theta[0]))
        k = float(np.clip(np.exp(theta[1]), *_K_BOUNDS))
        var = np.maximum(s0 * s0 + k * k * sv, 1e-6)
        return 0.5 * float(np.sum(np.log(2.0 * np.pi * var) + resid * resid / var))

    x0 = np.array([np.log(max(0.7 * resid.std(ddof=1), sigma_floor)), np.log(1.0)])
    res = minimize(nll, x0, method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 400})
    s0 = max(float(np.exp(res.x[0])), sigma_floor)
    k = float(np.clip(np.exp(res.x[1]), *_K_BOUNDS))
    return s0, k


def strength_posterior_sigma(sigma0: float, k: float, strength_var: np.ndarray,
                             *, floor: float = _MIN_SIGMA_MARGIN) -> np.ndarray:
    """Per-game predictive σ from the fitted (σ₀, k): σ_g = √(σ₀² + k²·strength_var), floored."""
    sv = np.clip(np.asarray(strength_var, dtype=float), 0.0, None)
    return np.clip(np.sqrt(sigma0 * sigma0 + k * k * sv), floor, None)


# ---------------------------------------------------------------------------
# Samplers → (margin, total) draws, one (n_games, n_draws) array each
# ---------------------------------------------------------------------------

def _bivariate_normal(
    mu_margin: np.ndarray, mu_total: np.ndarray,
    sigma_margin: np.ndarray | float, sigma_total: np.ndarray | float, rho: float,
    rng: np.random.Generator, n_draws: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Correlated (margin, total) Normal draws via a Cholesky of the 2×2 correlation matrix.

    σ may be scalar (homoscedastic `gaussian`) or per-game (heteroscedastic `native`). The two
    standard-normal streams z1,z2 are combined as m = z1, t = ρ·z1 + √(1−ρ²)·z2 so Corr(m,t)=ρ,
    then scaled by the per-side σ and shifted by the per-side μ.
    """
    n_games = mu_margin.shape[0]
    z1 = rng.standard_normal((n_games, n_draws))
    z2 = rng.standard_normal((n_games, n_draws))
    m_std = z1
    t_std = rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2
    sm = np.asarray(sigma_margin, dtype=float)
    st = np.asarray(sigma_total, dtype=float)
    sm = sm[:, None] if sm.ndim else sm
    st = st[:, None] if st.ndim else st
    margin = mu_margin[:, None] + m_std * sm
    total = mu_total[:, None] + t_std * st
    return margin, total


def _bivariate_t(
    mu_margin: np.ndarray, mu_total: np.ndarray,
    sigma_margin: float, sigma_total: float, rho: float, dof: float,
    rng: np.random.Generator, n_draws: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Bivariate Student-t: a Normal scale-mixed by an inverse-chi-square (the standard
    construction). Same correlation structure as the Normal, heavier tails via the shared
    per-draw scaling w = √(dof / χ²_dof). Scale chosen so Var → σ² as dof → ∞ (unit t-variance
    is dof/(dof−2), so we divide the standardised t by √(dof/(dof−2)))."""
    n_games = mu_margin.shape[0]
    z1 = rng.standard_normal((n_games, n_draws))
    z2 = rng.standard_normal((n_games, n_draws))
    g = rng.chisquare(dof, size=(n_games, n_draws))
    w = np.sqrt(dof / np.maximum(g, 1e-9))
    var_scale = np.sqrt(dof / (dof - 2.0)) if dof > 2.0 else 1.0
    m_std = z1 * w / var_scale
    t_std = (rho * z1 + np.sqrt(max(1.0 - rho * rho, 0.0)) * z2) * w / var_scale
    margin = mu_margin[:, None] + m_std * sigma_margin
    total = mu_total[:, None] + t_std * sigma_total
    return margin, total


def _count_convolution(
    mu_margin: np.ndarray, mu_total: np.ndarray, r_home: float, r_away: float,
    rng: np.random.Generator, n_draws: int,
) -> tuple[np.ndarray, np.ndarray]:
    """The count foil: split the two mean predictions into home/away point means, draw each side
    as an INDEPENDENT NegBin point count, and read off margin = home − away, total = home + away.

    μ_home = (μ_total + μ_margin) / 2,  μ_away = (μ_total − μ_margin) / 2. Independence mirrors the
    MLB E2.2 ρ=0 convolution; football home/away scoring is close to independent given the
    strengths already in the mean.
    """
    mu_home = np.clip((mu_total + mu_margin) / 2.0, _MIN_MU_POINTS, None)
    mu_away = np.clip((mu_total - mu_margin) / 2.0, _MIN_MU_POINTS, None)
    y_home = _negbin_draw(mu_home, r_home, rng, n_draws)
    y_away = _negbin_draw(mu_away, r_away, rng, n_draws)
    return y_home - y_away, y_home + y_away


def _negbin_draw(mu: np.ndarray, r: float, rng: np.random.Generator, n_draws: int) -> np.ndarray:
    r = float(r)
    p = r / (r + mu[:, None])
    return rng.negative_binomial(r, p, size=(mu.shape[0], n_draws)).astype(float)


def draw_joint(
    form: str,
    mu_margin: np.ndarray,
    mu_total: np.ndarray,
    disp: JointDispersion,
    rng: np.random.Generator,
    *,
    n_draws: int = 10_000,
    sigma_margin_native: np.ndarray | None = None,
    sigma_total_native: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw `n_draws` joint (margin, total) samples per game under `form`.

    Returns (margin_samples, total_samples), each (n_games, n_draws). `disp` carries the held-out
    dispersion; for `native` the per-game σ arrays override the scalar σ in `disp`.
    """
    mu_margin = np.asarray(mu_margin, dtype=float)
    mu_total = np.asarray(mu_total, dtype=float)
    if form == "gaussian":
        return _bivariate_normal(mu_margin, mu_total, disp.sigma_margin, disp.sigma_total,
                                 disp.rho, rng, n_draws)
    if form == "student_t":
        return _bivariate_t(mu_margin, mu_total, disp.sigma_margin, disp.sigma_total,
                            disp.rho, disp.dof, rng, n_draws)
    if form in ("native", "strength_posterior"):
        # both are heteroscedastic Gaussians consuming a PER-GAME σ: `native` from the learner,
        # `strength_posterior` from the propagated strength posterior (computed by the caller).
        sm = sigma_from_native(mu_margin, sigma_margin_native) if sigma_margin_native is not None \
            else np.full_like(mu_margin, disp.sigma_margin)
        st = sigma_from_native(mu_total, sigma_total_native) if sigma_total_native is not None \
            else np.full_like(mu_total, disp.sigma_total)
        return _bivariate_normal(mu_margin, mu_total, sm, st, disp.rho, rng, n_draws)
    if form == "count":
        return _count_convolution(mu_margin, mu_total, disp.r_home, disp.r_away, rng, n_draws)
    raise KeyError(f"unknown NCAAF form {form!r}; known: {FORMS}")


# ---------------------------------------------------------------------------
# Derive the three markets + calibration scoring
# ---------------------------------------------------------------------------

def sample_joint_normal(
    mu_margin: np.ndarray, mu_total: np.ndarray,
    sigma_margin: np.ndarray | float, sigma_total: np.ndarray | float, rho: float,
    rng: np.random.Generator, *, n_draws: int = 10_000,
) -> tuple[np.ndarray, np.ndarray]:
    """Public bivariate-Normal (margin, total) sampler accepting SCALAR or PER-GAME σ.

    The serving/P1.5 entry point for the gaussian / native / strength_posterior forms (all of
    which are bivariate Normals differing only in how σ is set). Exposed so a downstream
    season-simulation can draw a matchup with a caller-supplied per-game σ — e.g. the
    irreducible game σ₀ ALONE, once the sim has already drawn team strength for the season.
    """
    return _bivariate_normal(mu_margin, mu_total, sigma_margin, sigma_total, rho, rng, n_draws)


def derive_markets(margin_s: np.ndarray, total_s: np.ndarray) -> dict[str, np.ndarray]:
    """Joint (margin, total) draws → the sample arrays the three markets read off.

    margin      = home − away  (H2H: P(margin>0);  spread: P(margin>line))
    total       = home + away  (over/under: P(total>line))
    home_win    = the {0,1} indicator sample (a distributional H2H — mean = P(home wins))
    """
    return {
        "margin": margin_s,
        "total": total_s,
        "home_win": (margin_s > 0).astype(float),
    }


def score_calibration(
    dists: dict[str, np.ndarray],
    obs: dict[str, np.ndarray],
    rng: np.random.Generator,
    *,
    rows: np.ndarray | None = None,
) -> dict[str, dict[str, float]]:
    """Calibration diagnostics for the drawn predictive, optionally on a ROW SUBSET (a PBO
    bucket). Only the shape-bearing SCORED_DISTS (margin, total) get a PIT; home_win is a point
    event (scored by Brier elsewhere)."""
    out: dict[str, dict[str, float]] = {}
    for key in SCORED_DISTS:
        s = dists[key] if rows is None else dists[key][rows]
        o = obs[key] if rows is None else obs[key][rows]
        pit = pit_flatness(randomized_pit(o, s, rng))
        out[key] = {
            "calib_80": round(interval_coverage(o, s), 4),
            "pit_max_decile_dev": pit["max_decile_dev"],
            "pit_mean_dev": pit["mean_dev_from_half"],
            "pit_is_flat": bool(pit["is_flat"]),
        }
    # home_win: Brier + realised-vs-predicted win rate (a scalar, not a PIT).
    if "home_win" in obs:
        p_home = dists["home_win"].mean(axis=1) if rows is None else dists["home_win"][rows].mean(axis=1)
        y = obs["home_win"] if rows is None else obs["home_win"][rows]
        out["home_win"] = {
            "brier": round(float(np.mean((p_home - y) ** 2)), 4),
            "pred_rate": round(float(p_home.mean()), 4),
            "obs_rate": round(float(np.mean(y)), 4),
        }
    return out


def downstream_score(metrics: dict[str, dict[str, float]]) -> float:
    """Scalar SELECTION metric (LOWER IS BETTER; 0 = perfectly calibrated margin AND total).

        Σ_{j ∈ margin, total} PIT_max_decile_dev_j

    PIT-only, exactly as the MLB E2.1-r metric CORRECTION established: the randomised PIT is
    discreteness-correct by construction and is the stricter whole-shape check, whereas
    `|calib_80 − 0.80|` rewards under-dispersion because inclusive-integer interval coverage is
    inflated above nominal (an ORACLE covers > 0.80). `calib_80` is measured and enforced only as
    a FLOOR (`passes_calibration_floor`). home_win's Brier is a secondary diagnostic, not scored
    (it is a deterministic function of the margin marginal already in the PIT).
    """
    return float(sum(metrics[j]["pit_max_decile_dev"] for j in SCORED_DISTS))


# Sampling tolerance on the calib_80 floor. ⭐ NCAAF selection-metric-hygiene finding (P1.4): the
# MLB landmine (CLAUDE.md E2.1-r) is that inclusive-integer interval coverage INFLATES a correct
# DISCRETE/low-mean predictive's calib_80 to ~0.82–0.86, so `|calib_80 − 0.80|` rewards under-
# dispersion. That inflation is a LOW-MEAN effect. NCAAF margin/total are WIDE-support integers
# (σ ≈ 13 / 17, so ±0.5 rounding is negligible against a ±17-point interval), so a CORRECTLY
# specified oracle here covers ≈ 0.80 EXACTLY — there is NO inflation to exploit. Verified by
# `test_oracle_is_the_scoring_floor` (the oracle lands at 0.79–0.80, not 0.82+). Consequently a
# strict `≥ 0.80` floor would reject a perfect oracle purely on Monte-Carlo / finite-n noise, so
# the floor carries a small sampling tolerance. The metric is STILL PIT-only (`downstream_score`);
# calib_80 remains a floor, never a target — an under-dispersed model (σ halved) sits FAR below
# even the tolerant floor and is still disqualified.
_CALIB_FLOOR_TOL: float = 0.02


def passes_calibration_floor(
    metrics: dict[str, dict[str, float]], target: float = 0.80, tol: float = _CALIB_FLOOR_TOL,
) -> bool:
    """Every shape-bearing distribution must cover AT LEAST the nominal 80% within sampling noise
    (a floor, never a target — too wide is merely conservative; too narrow under-prices tails).
    The `tol` absorbs the finite-n / discreteness wobble that for WIDE-support predictives runs in
    the DEFLATIONARY direction (a correct oracle covers ≈ 0.80, not > 0.80 as in low-mean discrete
    counts) — see `_CALIB_FLOOR_TOL`."""
    return all(metrics[j]["calib_80"] >= target - tol for j in SCORED_DISTS)


# ---------------------------------------------------------------------------
# Served / calibration params (consumed by P1.4 serving + the vs-market leg)
# ---------------------------------------------------------------------------

@dataclass
class NcaafGameDistributionParams:
    """The fitted P1.4 joint-distribution calibration layer + served-contract spec.

    JSON-roundtrippable. The μ_margin / μ_total come from the P1.4 mean artifact at score time;
    this object carries only the held-out-calibrated SPREAD, exactly as the MLB E2.3 params carry
    no model state. `form` is the bake-off-selected form; the dispersion fields are populated per
    form (σ+ρ for gaussian/native, +dof for student_t, r_home/r_away for count).
    """

    form: str
    sigma_margin: float
    sigma_total: float
    rho: float = 0.0
    dof: float = 30.0
    r_home: float = 200.0
    r_away: float = 200.0
    sigma0_margin: float = 0.0
    k_margin: float = 0.0
    sigma0_total: float = 0.0
    k_total: float = 0.0
    learner: str = ""
    contract: str = ""
    n_draws: int = 10_000
    quantile_levels: tuple[float, ...] = DEFAULT_QUANTILES
    dispersion_calibration: str = "held-out OOS residuals (leakage-safe; E13.6 pattern)"
    notes: str = ""
    version: str = "ncaaf_game_distribution_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "form": self.form,
            "sigma_margin": self.sigma_margin,
            "sigma_total": self.sigma_total,
            "rho": self.rho,
            "dof": self.dof,
            "r_home": self.r_home,
            "r_away": self.r_away,
            "sigma0_margin": self.sigma0_margin,
            "k_margin": self.k_margin,
            "sigma0_total": self.sigma0_total,
            "k_total": self.k_total,
            "learner": self.learner,
            "contract": self.contract,
            "n_draws": self.n_draws,
            "quantile_levels": list(self.quantile_levels),
            "dispersion_calibration": self.dispersion_calibration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NcaafGameDistributionParams":
        return cls(
            form=str(d["form"]),
            sigma_margin=float(d["sigma_margin"]),
            sigma_total=float(d["sigma_total"]),
            rho=float(d.get("rho", 0.0)),
            dof=float(d.get("dof", 30.0)),
            r_home=float(d.get("r_home", 200.0)),
            r_away=float(d.get("r_away", 200.0)),
            sigma0_margin=float(d.get("sigma0_margin", 0.0)),
            k_margin=float(d.get("k_margin", 0.0)),
            sigma0_total=float(d.get("sigma0_total", 0.0)),
            k_total=float(d.get("k_total", 0.0)),
            learner=str(d.get("learner", "")),
            contract=str(d.get("contract", "")),
            n_draws=int(d.get("n_draws", 10_000)),
            quantile_levels=tuple(d.get("quantile_levels", DEFAULT_QUANTILES)),
            dispersion_calibration=d.get("dispersion_calibration", ""),
            notes=d.get("notes", ""),
            version=d.get("version", "ncaaf_game_distribution_v1"),
        )

    def dispersion(self) -> JointDispersion:
        return JointDispersion(
            sigma_margin=self.sigma_margin, sigma_total=self.sigma_total, rho=self.rho,
            dof=self.dof, r_home=self.r_home, r_away=self.r_away,
            sigma0_margin=self.sigma0_margin, k_margin=self.k_margin,
            sigma0_total=self.sigma0_total, k_total=self.k_total,
        )


# ---------------------------------------------------------------------------
# Oracle helper — the inverted-metric guard's scoring floor
# ---------------------------------------------------------------------------

def oracle_observations(
    form: str, mu_margin: np.ndarray, mu_total: np.ndarray, disp: JointDispersion,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Draw ONE realised (margin, total) per game from EXACTLY `form` — a zero-misspecification
    truth. Rounded to integers (real scores are integer) so the PIT sees the same discreteness a
    real observation carries. Used by `test_oracle_is_the_scoring_floor`: a candidate that scores
    BETTER than this oracle is mathematically impossible ⇒ the metric is inverted.
    """
    m, t = draw_joint(form, mu_margin, mu_total, disp, rng, n_draws=1)
    margin = np.rint(m[:, 0])
    total = np.rint(t[:, 0])
    return {"margin": margin, "total": total, "home_win": (margin > 0).astype(float)}
