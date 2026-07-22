"""f5_distribution.py — Edge Program Story E2.4 (First-5-innings per-side distribution).

WHY THIS EXISTS
---------------
E2.1/E2.2/E2.3 built the FULL-GAME per-side run distribution: a per-side NegBin marginal,
home/away independence (ρ≈0), and a held-out-calibrated dispersion, convolved into an honest
total / team-total distribution. E2.4 does the same thing scoped to the **first five innings
(F5)** — a structurally different distribution:

  * LOWER mean (≈ half a full game → per-side ~2.2 vs ~4.5 runs), so it is more discrete;
  * MORE zero-inflation (a scoreless-through-5 half-game is common), which stresses the tails;
  * STARTER-dominated — the bullpen barely pitches in innings 1–5, so the run-generating
    structure differs from the full game (this is the "softer market" thesis behind E2.4).

Because the distribution is different, E2.4 does NOT assume the E2.1 NegBin form carries. It
bakes off ≥3 pre-registered per-side distributional FORMS (§0.5), each convolved with the SAME
independence machinery E2.3 uses, and picks on the downstream PIT-flatness / calib-floor metric
(the E2.1-r selection-metric hygiene: a randomised-PIT flatness score, calib_80 as a FLOOR not
a target — the inclusive-integer interval-coverage inflation the CLAUDE.md landmine warns about
is WORSE at F5's low mean). This module is the pure distributional core:

  * three per-side FORMS — `poisson`, `negbin`, `betabinom` — each with a sampler, an NLL, and a
    held-out dispersion fit;
  * a unified INDEPENDENT convolution `draw_f5_independent` (ρ=0, per E2.2) that dispatches on
    the form and returns joint (home, away) F5 draws;
  * the served-contract dataclass `F5DistributionParams`.

The calibration diagnostics (`randomized_pit`, `pit_flatness`, `interval_coverage`,
`quantile_grid`, `prob_over`, `derive_distributions`) are form-AGNOSTIC — they operate on a
drawn sample array — so they are imported verbatim from `totals_distribution` (E2.3) rather than
forked. Pure NumPy/SciPy — no Snowflake, no model — so it is fully unit-tested, including a
per-form ORACLE-FLOOR guard (a truth drawn from exactly the form being scored is the best any
model of that form can do; nothing may score better — the E2.1-r inverted-metric tell).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import betabinom

# Form-agnostic calibration + serving machinery — reuse E2.3's tested implementations verbatim
# (they take a drawn (n_games, n_draws) sample array and know nothing about the generating form).
from betting_ml.utils.totals_distribution import (  # noqa: F401  (re-exported for E2.4 consumers)
    DEFAULT_QUANTILES,
    derive_distributions,
    interval_coverage,
    pit_flatness,
    prob_over,
    prob_push,
    quantile_grid,
    randomized_pit,
)

# F5 per-side runs are LOW-mean and zero-heavy, so the mean floor is well below the full-game
# 0.30 (a mu clipped to 0.30 would over-inflate a genuinely near-zero-scoring half-game).
_MIN_MU: float = 0.05
# The three pre-registered per-side distributional forms (the §0.5 ≥3-form bake-off axis).
FORMS: tuple[str, ...] = ("poisson", "negbin", "betabinom")
# NegBin dispersion optimiser band (mirrors totals_distribution / train_perside_negbin).
_R_BOUNDS: tuple[float, float] = (0.1, 500.0)
# Beta-Binomial concentration band. s→∞ ⇒ Binomial (under-dispersed floor); s→0 ⇒ max spread.
_S_BOUNDS: tuple[float, float] = (0.5, 5_000.0)
# Beta-Binomial trials cap. F5 per-side runs realistically top out ≈ 12–13; 25 gives comfortable
# headroom so π = mu/n stays well below 1 and the support covers every observed outcome. It is a
# FIXED structural constant of the form (NOT tuned — tuning n would be an open subset search).
BETABINOM_N_CAP: int = 25


# ---------------------------------------------------------------------------
# Per-form negative log-likelihoods (mean NLL; y, mu are per-observation arrays)
# ---------------------------------------------------------------------------

def poisson_nll(y: np.ndarray, mu: np.ndarray) -> float:
    """Mean Poisson NLL. var = mean — the zero-dispersion form (F5's low-mean baseline)."""
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    y = np.asarray(y, dtype=float)
    ll = y * np.log(mu) - mu - gammaln(y + 1.0)
    return float(-np.mean(ll))


def negbin_nll(y: np.ndarray, mu: np.ndarray, r: float | np.ndarray) -> float:
    """Mean NegBin(mu, r) NLL. var = mu + mu²/r ≥ mu (matches E2.1/E2.3 parameterisation)."""
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    y = np.asarray(y, dtype=float)
    r = np.asarray(r, dtype=float)
    p = r / (r + mu)
    ll = (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
        + r * np.log(p) + y * np.log(1.0 - p + 1e-12)
    )
    return float(-np.mean(ll))


def betabinom_nll(y: np.ndarray, mu: np.ndarray, s: float | np.ndarray, n: int = BETABINOM_N_CAP) -> float:
    """Mean Beta-Binomial(n, a, b) NLL with π = mu/n, a = s·π, b = s·(1−π), concentration s.

    A BOUNDED overdispersed count form: mass can pile at 0 (zero-inflation) and the support is
    capped at n — the property that distinguishes it from the unbounded Poisson/NegBin and the
    reason F5's zero-heavy shape gets it as a pre-registered candidate. As s→∞ it collapses to a
    Binomial(n, π) (under-dispersed vs the count); small s widens the tails.
    """
    y = np.asarray(y, dtype=float)
    a, b = _betabinom_ab(mu, s, n)
    return float(-np.mean(betabinom.logpmf(np.clip(y, 0, n), n, a, b)))


def _betabinom_ab(
    mu: np.ndarray, s: float | np.ndarray, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """(a, b) Beta parameters for a mean-`mu`, concentration-`s` Beta-Binomial over n trials."""
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    pi = np.clip(mu / float(n), 1e-4, 1.0 - 1e-4)
    s = np.asarray(s, dtype=float)
    return s * pi, s * (1.0 - pi)


# ---------------------------------------------------------------------------
# Held-out dispersion fits (one scalar per side; leakage-safe when y/mu are held-out)
# ---------------------------------------------------------------------------

def fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of the NegBin dispersion r given observations y and predicted means mu."""
    res = minimize_scalar(
        lambda log_r: negbin_nll(y, mu, float(np.exp(log_r))),
        bounds=(np.log(_R_BOUNDS[0]), np.log(_R_BOUNDS[1])), method="bounded",
    )
    return float(np.exp(res.x))


def fit_betabinom_s(y: np.ndarray, mu: np.ndarray, n: int = BETABINOM_N_CAP) -> float:
    """MLE of the Beta-Binomial concentration s given observations y and predicted means mu."""
    res = minimize_scalar(
        lambda log_s: betabinom_nll(y, mu, float(np.exp(log_s)), n),
        bounds=(np.log(_S_BOUNDS[0]), np.log(_S_BOUNDS[1])), method="bounded",
    )
    return float(np.exp(res.x))


def fit_dispersion(form: str, y: np.ndarray, mu: np.ndarray, *, n: int = BETABINOM_N_CAP) -> float:
    """Held-out dispersion for a form. `poisson` has none (returns nan — the sampler ignores it)."""
    if form == "poisson":
        return float("nan")
    if form == "negbin":
        return fit_negbin_r(y, mu)
    if form == "betabinom":
        return fit_betabinom_s(y, mu, n)
    raise KeyError(f"unknown F5 form {form!r}; known: {FORMS}")


def sigma_to_negbin_r(mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """Moment-match a native (μ, σ) prediction onto a per-game NegBin r = μ²/(σ²−μ).

    The NGBoost native-joint foil emits (μ, σ) per game; this maps it into the NegBin the
    convolution speaks. σ² ≤ μ (no overdispersion at that game) → the Poisson-limit upper r
    bound. Clipped to the same band the MLE optimises over. Mirrors bakeoff_perside.
    """
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    var = np.asarray(sigma, dtype=float) ** 2
    excess = var - mu
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(excess > 1e-9, mu**2 / np.maximum(excess, 1e-9), _R_BOUNDS[1])
    return np.clip(np.nan_to_num(r, nan=_R_BOUNDS[1]), *_R_BOUNDS)


# ---------------------------------------------------------------------------
# Per-side samplers → (n_games, n_draws) integer count arrays
# ---------------------------------------------------------------------------

def draw_side(
    form: str,
    mu: np.ndarray,
    disp: np.ndarray | float,
    rng: np.random.Generator,
    *,
    n_draws: int = 10_000,
    n_cap: int = BETABINOM_N_CAP,
) -> np.ndarray:
    """Draw `n_draws` per-side F5 run counts per game under `form`. Returns (n_games, n_draws).

    `disp` is the form's dispersion parameter (r for negbin, s for betabinom, ignored for
    poisson); it may be a scalar or a per-game array. All three samplers are pure NumPy
    (vectorised, no scipy per-draw), so a full bake-off fold's draws are cheap.
    """
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    n_games = mu.shape[0]
    size = (n_games, n_draws)
    if form == "poisson":
        return rng.poisson(mu[:, None], size=size).astype(float)
    if form == "negbin":
        r = np.broadcast_to(np.asarray(disp, dtype=float), (n_games,))[:, None]
        p = r / (r + mu[:, None])
        return rng.negative_binomial(r, p, size=size).astype(float)
    if form == "betabinom":
        a, b = _betabinom_ab(mu, disp, n_cap)
        p = rng.beta(a[:, None], b[:, None], size=size)
        return rng.binomial(n_cap, p).astype(float)
    raise KeyError(f"unknown F5 form {form!r}; known: {FORMS}")


def draw_f5_independent(
    mu_home: np.ndarray,
    mu_away: np.ndarray,
    form: str,
    disp_home: np.ndarray | float,
    disp_away: np.ndarray | float,
    rng: np.random.Generator,
    *,
    n_draws: int = 10_000,
    n_cap: int = BETABINOM_N_CAP,
) -> tuple[np.ndarray, np.ndarray]:
    """Independent (ρ=0, per E2.2) per-side convolution → joint (home, away) F5 draws.

    E2.2 established home/away runs are essentially independent; the same holds for the F5
    sub-game (the two halves are disjoint innings), so — as in E2.3 — we convolve the two
    marginals independently. Each side draws under the SAME `form` with its own dispersion. The
    two `draw_side` calls consume the same `rng` sequentially, so the streams are independent by
    construction (no shared latent). Returns two (n_games, n_draws) arrays; feed to
    `derive_distributions` for total / run-diff / team totals.
    """
    y_home = draw_side(form, mu_home, disp_home, rng, n_draws=n_draws, n_cap=n_cap)
    y_away = draw_side(form, mu_away, disp_away, rng, n_draws=n_draws, n_cap=n_cap)
    return y_home, y_away


# ---------------------------------------------------------------------------
# Served / calibration params (consumed by E2.5 backfill + E2.6 efficiency eval)
# ---------------------------------------------------------------------------

@dataclass
class F5DistributionParams:
    """The fitted E2.4 F5 calibration layer + served-contract spec.

    `form` is the bake-off-selected per-side distributional form. `dispersion_home` /
    `dispersion_away` are the served per-side dispersion parameters (r for negbin, s for
    betabinom; unused for poisson) — held-out-calibrated, leakage-safe. `rho` is pinned 0.0
    (E2.2: home/away independent, and the F5 halves are disjoint). JSON-roundtrippable — the μ
    come from the E2.4 mean artifact at score time, exactly as E2.3's params carry no model
    state.
    """
    form: str
    dispersion_home: float | None = None
    dispersion_away: float | None = None
    rho: float = 0.0
    n_cap: int = BETABINOM_N_CAP
    n_draws: int = 10_000
    quantile_levels: tuple[float, ...] = DEFAULT_QUANTILES
    dispersion_calibration: str = "expanding-window held-out residuals (leakage-safe)"
    notes: str = ""
    version: str = "f5_distribution_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "form": self.form,
            "dispersion_home": self.dispersion_home,
            "dispersion_away": self.dispersion_away,
            "rho": self.rho,
            "n_cap": self.n_cap,
            "n_draws": self.n_draws,
            "quantile_levels": list(self.quantile_levels),
            "dispersion_calibration": self.dispersion_calibration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "F5DistributionParams":
        return cls(
            form=str(d["form"]),
            dispersion_home=None if d.get("dispersion_home") is None else float(d["dispersion_home"]),
            dispersion_away=None if d.get("dispersion_away") is None else float(d["dispersion_away"]),
            rho=float(d.get("rho", 0.0)),
            n_cap=int(d.get("n_cap", BETABINOM_N_CAP)),
            n_draws=int(d.get("n_draws", 10_000)),
            quantile_levels=tuple(d.get("quantile_levels", DEFAULT_QUANTILES)),
            dispersion_calibration=d.get("dispersion_calibration", ""),
            notes=d.get("notes", ""),
            version=d.get("version", "f5_distribution_v1"),
        )
