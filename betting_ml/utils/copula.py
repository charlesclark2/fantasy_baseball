"""copula.py — Gaussian copula over two NegBin marginals (Edge Program Story E2.2).

WHY THIS EXISTS
---------------
E2.1 gives us a per-SIDE Negative-Binomial marginal over runs scored (one for the home
side, one for the away side, each conditioned on the matchup). To turn two marginals into
an honest TOTAL / run-diff / team-total distribution (E2.3) we must couple them: home and
away runs are *not* independent — they share park, weather, umpire, game pace and a weak
game-state coupling, so an independent convolution misestimates exactly the tails the
derivative markets (F5 / team totals / alt lines) are priced on. This module is the
dependence layer: a **Gaussian copula** with a single latent correlation ρ (optionally
conditioned on park/weather/run-env buckets) over the two NegBin marginals.

THE ONE SUBTLETY THAT MAKES OR BREAKS IT (the "load-bearing" warning in the story)
----------------------------------------------------------------------------------
ρ is fit on the *residual* dependence that remains AFTER each side's conditional NegBin mean
has absorbed the shared covariates — NOT on the raw correlation of (home_runs, away_runs).
The E2.1 marginals already condition on the shared park/weather/umpire context, so a chunk
of the raw same-game run correlation is already explained by *correlated conditional means*
across games. If you fit ρ on the raw pairs and then ALSO apply correlated conditional means
in the convolution, you double-count the shared-environment coupling and over-inflate the
total variance. So the estimator here works on the **distributional transform** (randomized
PIT) of each observed count under its own conditional NegBin, mapped to normal scores — the
standard semiparametric Gaussian-copula correlation estimator, correct for *discrete*
marginals. `fit_copula.py` reports the naive raw-pairs ρ alongside, purely as a contrast.

DISCRETE MARGINALS
------------------
A plain PIT `F(y)` of a count is not uniform (it lands on the CDF's step tops). We use the
**distributional transform** (Brockwell 2007 / Kazianka & Pilz): u = F(y-1) + V·(F(y)−F(y-1)),
V ~ U(0,1). That spreads each count's probability mass across its CDF step → u is exactly
Uniform(0,1) under the true marginal, so z = Φ⁻¹(u) is standard normal and Pearson-corr(z) is
the Gaussian-copula MLE for ρ. Sampling inverts the chain: latent bivariate normal → Φ →
NegBin inverse-CDF per game.

This module is pure NumPy/SciPy (no Snowflake, no model) so it is fully unit-tested; the
orchestration (CV marginals, bucketing, the AC validation) lives in `fit_copula.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.stats import nbinom, norm

# Counts/means require mu > 0; mirror the E2.1 per-side floor so the two layers agree.
_MIN_MU = 0.30
_U_EPS = 1e-9            # clip uniforms off {0,1} before Φ⁻¹ (avoids ±inf normal scores)
_RHO_CAP = 0.999        # keep |ρ| < 1 so the Cholesky factor sqrt(1−ρ²) stays real


# ---------------------------------------------------------------------------
# NegBin parameterisation (mean / dispersion), matching train_perside_negbin
# ---------------------------------------------------------------------------

def _nb_p(mu: np.ndarray | float, r: np.ndarray | float) -> np.ndarray:
    """SciPy nbinom success-prob p for mean `mu`, dispersion `r` (n=r): var = mu + mu²/r."""
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    return r / (r + mu)


def negbin_var(mu: np.ndarray | float, r: np.ndarray | float) -> np.ndarray:
    """Variance of NegBin(mu, r): mu + mu²/r (≥ mu; the overdispersion E2.1 recovered)."""
    mu = np.clip(np.asarray(mu, dtype=float), _MIN_MU, None)
    return mu + mu * mu / r


# ---------------------------------------------------------------------------
# Distributional transform (discrete PIT) → normal scores
# ---------------------------------------------------------------------------

def distributional_transform(
    y: np.ndarray, mu: np.ndarray, r: np.ndarray | float, rng: np.random.Generator
) -> np.ndarray:
    """Randomised PIT of counts `y` under conditional NegBin(mu, r) → Uniform(0,1).

    u = F(y-1) + V·(F(y) − F(y-1)), V ~ U(0,1). Exactly uniform under the true marginal,
    unlike the plain `F(y)` of a discrete variable. The per-row `r` may be a scalar or array.
    """
    y = np.asarray(y, dtype=float)
    p = _nb_p(mu, r)
    r_arr = np.broadcast_to(np.asarray(r, dtype=float), p.shape)
    f_hi = nbinom.cdf(y, r_arr, p)
    f_lo = nbinom.cdf(y - 1.0, r_arr, p)          # = f_hi − pmf(y); 0 at y=0
    v = rng.random(size=y.shape)
    return f_lo + v * (f_hi - f_lo)


def normal_scores(u: np.ndarray) -> np.ndarray:
    """Φ⁻¹ of uniforms, clipped off {0,1}. Maps copula uniforms to standard-normal scores."""
    return norm.ppf(np.clip(u, _U_EPS, 1.0 - _U_EPS))


# ---------------------------------------------------------------------------
# ρ estimation
# ---------------------------------------------------------------------------

def fit_gaussian_copula_rho(
    y_home: np.ndarray,
    mu_home: np.ndarray,
    y_away: np.ndarray,
    mu_away: np.ndarray,
    r_home: np.ndarray | float,
    r_away: np.ndarray | float,
    rng: np.random.Generator,
    *,
    n_reps: int = 9,
) -> float:
    """Latent Gaussian-copula correlation ρ from paired counts under conditional NegBins.

    Distributional-transform each side to uniforms, map to normal scores, take Pearson corr.
    The randomised PIT injects a little Monte-Carlo noise (the `V`), so we average the
    estimate over `n_reps` independent V-draws for stability. Returns ρ ∈ (−RHO_CAP, RHO_CAP).
    """
    rhos = []
    for _ in range(max(1, n_reps)):
        zh = normal_scores(distributional_transform(y_home, mu_home, r_home, rng))
        za = normal_scores(distributional_transform(y_away, mu_away, r_away, rng))
        ok = np.isfinite(zh) & np.isfinite(za)
        if ok.sum() < 3:
            continue
        rhos.append(float(np.corrcoef(zh[ok], za[ok])[0, 1]))
    if not rhos:
        return 0.0
    return float(np.clip(np.mean(rhos), -_RHO_CAP, _RHO_CAP))


def kendall_tau_to_rho(tau: float) -> float:
    """Gaussian-copula ρ implied by Kendall's τ: ρ = sin(πτ/2). A rank-based, V-noise-free
    cross-check on the normal-scores estimate (robust to the marginal mis-spec)."""
    return float(np.clip(np.sin(np.pi * tau / 2.0), -_RHO_CAP, _RHO_CAP))


# ---------------------------------------------------------------------------
# Sampling: Gaussian copula → NegBin counts
# ---------------------------------------------------------------------------

def sample_gaussian_copula_negbin(
    mu_home: np.ndarray,
    r_home: np.ndarray | float,
    mu_away: np.ndarray,
    r_away: np.ndarray | float,
    rho: np.ndarray | float,
    rng: np.random.Generator,
    *,
    n_draws: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw `n_draws` joint (home, away) run counts per game from the copula-coupled NegBins.

    Per game g: latent (z₁,z₂) bivariate-normal with corr ρ(g) → uniforms via Φ → NegBin
    inverse-CDF with that game's (mu, r). `rho` may be a scalar (single global ρ) or a
    per-game array (bucket-conditioned ρ). Returns two arrays of shape (n_games, n_draws).
    """
    mu_home = np.clip(np.asarray(mu_home, dtype=float), _MIN_MU, None)
    mu_away = np.clip(np.asarray(mu_away, dtype=float), _MIN_MU, None)
    n = mu_home.shape[0]
    rho_arr = np.clip(np.broadcast_to(np.asarray(rho, dtype=float), (n,)), -_RHO_CAP, _RHO_CAP)

    # Latent standard normals, coupled per game: z2 = ρ·z1 + sqrt(1−ρ²)·e.
    z1 = rng.standard_normal(size=(n, n_draws))
    e = rng.standard_normal(size=(n, n_draws))
    rc = rho_arr[:, None]
    z2 = rc * z1 + np.sqrt(1.0 - rc * rc) * e

    u1 = norm.cdf(z1)
    u2 = norm.cdf(z2)

    p_home = _nb_p(mu_home, r_home)[:, None]
    p_away = _nb_p(mu_away, r_away)[:, None]
    r_home_b = np.broadcast_to(np.asarray(r_home, dtype=float), (n,))[:, None]
    r_away_b = np.broadcast_to(np.asarray(r_away, dtype=float), (n,))[:, None]

    y_home = nbinom.ppf(np.clip(u1, _U_EPS, 1.0 - _U_EPS), r_home_b, p_home)
    y_away = nbinom.ppf(np.clip(u2, _U_EPS, 1.0 - _U_EPS), r_away_b, p_away)
    return y_home, y_away


def analytic_total_variance(
    mu_home: np.ndarray,
    r_home: np.ndarray | float,
    mu_away: np.ndarray,
    r_away: np.ndarray | float,
    rho: np.ndarray | float,
) -> dict[str, float]:
    """Law-of-total-variance decomposition of the predictive TOTAL-runs variance.

    var(total) = E_g[var(home|g) + var(away|g) + 2·ρ·sd_home·sd_away]   (within-game)
               + var_g(mu_home + mu_away)                               (between-game means)

    The `2·ρ·sd·sd` term is the copula contribution: drop it (ρ=0) and you underestimate the
    total variance and its tails — the entire reason E2 needs a dependence layer. Returns the
    component breakdown so `fit_copula.py` can show the ρ=0 gap analytically (not only by MC).

    NB: this uses ρ as a linear correlation on the latent scale as a first-order proxy for the
    count-scale covariance; the simulation in `fit_copula.py` is the exact check.
    """
    mu_home = np.clip(np.asarray(mu_home, dtype=float), _MIN_MU, None)
    mu_away = np.clip(np.asarray(mu_away, dtype=float), _MIN_MU, None)
    rho = np.broadcast_to(np.asarray(rho, dtype=float), mu_home.shape)
    var_h = negbin_var(mu_home, r_home)
    var_a = negbin_var(mu_away, r_away)
    cov_term = 2.0 * rho * np.sqrt(var_h) * np.sqrt(var_a)
    within = float(np.mean(var_h + var_a + cov_term))
    between = float(np.var(mu_home + mu_away))
    coupling = float(np.mean(cov_term))
    return {
        "within_game": within,
        "between_game_means": between,
        "coupling_2cov": coupling,
        "total_variance": within + between,
        "total_variance_rho0": within - coupling + between,
    }


# ---------------------------------------------------------------------------
# Serialisable fitted-copula parameters (consumed by E2.3 convolution)
# ---------------------------------------------------------------------------

@dataclass
class GaussianCopulaParams:
    """The fitted dependence layer E2.3 needs to convolve the marginals.

    `rho_global` is the single latent correlation. `rho_by_bucket` (optional) maps a
    bucket-key → ρ for the conditioned variant; `bucket_scheme` names how the key is built
    (e.g. "park_run_factor_tercile"). `conditioning` records the E2.2 decision ("global" vs a
    scheme) with the evidence summary that justified it. JSON-roundtrippable (no model state).
    """
    rho_global: float
    bucket_scheme: str = "global"
    rho_by_bucket: dict[str, float] = field(default_factory=dict)
    conditioning: str = "global"
    r_decision: str = "global"
    notes: str = ""
    version: str = "copula_v1"

    def rho_for(self, bucket_key: str | None = None) -> float:
        """ρ for a bucket key (falls back to the global ρ when un-bucketed / key unseen)."""
        if self.conditioning != "global" and bucket_key is not None:
            return self.rho_by_bucket.get(bucket_key, self.rho_global)
        return self.rho_global

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "rho_global": self.rho_global,
            "bucket_scheme": self.bucket_scheme,
            "rho_by_bucket": self.rho_by_bucket,
            "conditioning": self.conditioning,
            "r_decision": self.r_decision,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GaussianCopulaParams":
        return cls(
            rho_global=float(d["rho_global"]),
            bucket_scheme=d.get("bucket_scheme", "global"),
            rho_by_bucket={str(k): float(v) for k, v in d.get("rho_by_bucket", {}).items()},
            conditioning=d.get("conditioning", "global"),
            r_decision=d.get("r_decision", "global"),
            notes=d.get("notes", ""),
            version=d.get("version", "copula_v1"),
        )
