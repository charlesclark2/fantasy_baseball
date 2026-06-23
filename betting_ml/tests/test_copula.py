"""Tests for Story E2.2 — the Gaussian copula over two NegBin marginals.

Pure-math unit tests (no Snowflake, no model): the discrete distributional transform is
uniform, the normal-scores estimator recovers a planted ρ, the sampler reproduces a planted
ρ AND inflates the total-runs variance/tails over the independent (ρ=0) convolution, and the
serialisable params round-trip. These pin the load-bearing behaviour the E2.2 AC depends on.
"""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.utils.copula import (
    GaussianCopulaParams,
    analytic_total_variance,
    distributional_transform,
    fit_gaussian_copula_rho,
    kendall_tau_to_rho,
    negbin_var,
    normal_scores,
    sample_gaussian_copula_negbin,
)


# ---------------------------------------------------------------------------
# Distributional transform (discrete PIT)
# ---------------------------------------------------------------------------

class TestDistributionalTransform:
    def test_uniform_under_true_marginal(self):
        """Counts drawn from NegBin(mu, r), PIT'd under the SAME (mu, r), are ~Uniform(0,1)."""
        from scipy.stats import nbinom

        rng = np.random.default_rng(0)
        mu, r = 4.5, 7.0
        p = r / (r + mu)
        y = nbinom.rvs(r, p, size=40_000, random_state=rng)
        u = distributional_transform(y, np.full_like(y, mu, dtype=float), r, rng)
        assert u.min() >= 0.0 and u.max() <= 1.0
        # mean ≈ 0.5 and roughly even decile occupancy → uniform
        assert u.mean() == pytest.approx(0.5, abs=0.01)
        counts, _ = np.histogram(u, bins=10, range=(0, 1))
        assert counts.max() / counts.min() < 1.15

    def test_normal_scores_are_standard_normal(self):
        from scipy.stats import nbinom

        rng = np.random.default_rng(1)
        mu, r = 4.5, 7.0
        p = r / (r + mu)
        y = nbinom.rvs(r, p, size=40_000, random_state=rng)
        z = normal_scores(distributional_transform(y, np.full_like(y, mu, dtype=float), r, rng))
        assert np.isfinite(z).all()
        assert z.mean() == pytest.approx(0.0, abs=0.03)
        assert z.std() == pytest.approx(1.0, abs=0.03)


# ---------------------------------------------------------------------------
# ρ recovery — estimator and sampler agree on a planted ρ
# ---------------------------------------------------------------------------

class TestRhoRecovery:
    @pytest.mark.parametrize("rho_true", [-0.3, 0.0, 0.25, 0.5])
    def test_sampler_then_estimator_roundtrip(self, rho_true):
        """Sample joint counts at a known ρ, then re-estimate it from the samples."""
        rng = np.random.default_rng(7)
        n = 6000
        mu_h = np.full(n, 4.6)
        mu_a = np.full(n, 4.4)
        r_h = np.full(n, 7.0)
        r_a = np.full(n, 8.0)
        yh, ya = sample_gaussian_copula_negbin(mu_h, r_h, mu_a, r_a, rho_true, rng, n_draws=1)
        yh, ya = yh.ravel(), ya.ravel()
        rho_hat = fit_gaussian_copula_rho(yh, mu_h, ya, mu_a, r_h, r_a, rng, n_reps=5)
        assert rho_hat == pytest.approx(rho_true, abs=0.05)

    def test_kendall_tau_to_rho_identity(self):
        assert kendall_tau_to_rho(0.0) == pytest.approx(0.0)
        # ρ = sin(πτ/2): τ=2/π·asin(ρ)
        rho = 0.5
        tau = 2.0 / np.pi * np.arcsin(rho)
        assert kendall_tau_to_rho(tau) == pytest.approx(rho, abs=1e-6)


# ---------------------------------------------------------------------------
# The whole point: ρ>0 inflates total variance + tails vs independent ρ=0
# ---------------------------------------------------------------------------

class TestIndependentInsufficient:
    def _totals(self, rho, rng):
        n = 8000
        mu_h = np.full(n, 4.6)
        mu_a = np.full(n, 4.4)
        r_h = np.full(n, 7.0)
        r_a = np.full(n, 7.0)
        yh, ya = sample_gaussian_copula_negbin(mu_h, r_h, mu_a, r_a, rho, rng, n_draws=20)
        return (yh + ya).ravel()

    def test_positive_rho_increases_total_variance(self):
        rng = np.random.default_rng(11)
        var_indep = self._totals(0.0, rng).var()
        var_coupled = self._totals(0.35, rng).var()
        assert var_coupled > var_indep * 1.02   # coupling adds the 2·cov term

    def test_positive_rho_fattens_upper_tail(self):
        rng = np.random.default_rng(12)
        tot_indep = self._totals(0.0, rng)
        tot_coupled = self._totals(0.35, rng)
        hi = 14
        assert (tot_coupled >= hi).mean() > (tot_indep >= hi).mean()

    def test_independent_total_variance_is_sum_of_marginals(self):
        """ρ=0 ⇒ var(total) ≈ var(home) + var(away) (no coupling term)."""
        rng = np.random.default_rng(13)
        n = 20000
        mu_h, mu_a, r = np.full(n, 4.6), np.full(n, 4.4), np.full(n, 7.0)
        yh, ya = sample_gaussian_copula_negbin(mu_h, r, mu_a, r, 0.0, rng, n_draws=5)
        expect = negbin_var(4.6, 7.0) + negbin_var(4.4, 7.0)
        got = (yh + ya).ravel().var()
        assert got == pytest.approx(expect, rel=0.04)


# ---------------------------------------------------------------------------
# Analytic decomposition
# ---------------------------------------------------------------------------

class TestAnalyticVariance:
    def test_coupling_term_sign_and_drop(self):
        n = 1000
        mu_h = np.full(n, 4.6)
        mu_a = np.full(n, 4.4)
        d = analytic_total_variance(mu_h, 7.0, mu_a, 7.0, 0.3)
        assert d["coupling_2cov"] > 0
        # ρ=0 total = total − coupling
        assert d["total_variance_rho0"] == pytest.approx(d["total_variance"] - d["coupling_2cov"], abs=1e-6)

    def test_between_game_variance_from_mean_spread(self):
        # constant means ⇒ zero between-game variance
        n = 500
        d = analytic_total_variance(np.full(n, 4.5), 7.0, np.full(n, 4.5), 7.0, 0.0)
        assert d["between_game_means"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Params round-trip
# ---------------------------------------------------------------------------

class TestParams:
    def test_to_from_dict_roundtrip(self):
        p = GaussianCopulaParams(
            rho_global=0.12, bucket_scheme="park_run_factor_tercile",
            rho_by_bucket={"park_low": 0.08, "park_high": 0.17},
            conditioning="park_run_factor_tercile", r_decision="per-period", notes="x",
        )
        q = GaussianCopulaParams.from_dict(p.to_dict())
        assert q.rho_global == pytest.approx(0.12)
        assert q.rho_by_bucket["park_high"] == pytest.approx(0.17)
        assert q.conditioning == "park_run_factor_tercile"

    def test_rho_for_bucket_fallback(self):
        p = GaussianCopulaParams(rho_global=0.10, conditioning="roof",
                                 rho_by_bucket={"dome": 0.05})
        assert p.rho_for("dome") == pytest.approx(0.05)
        assert p.rho_for("open") == pytest.approx(0.10)    # unseen key → global
        g = GaussianCopulaParams(rho_global=0.10)          # global scheme ignores the key
        assert g.rho_for("dome") == pytest.approx(0.10)
