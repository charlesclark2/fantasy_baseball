"""Tests for Story E2.3 — independent convolution + dispersion calibration.

Pure-math unit tests (no Snowflake, no model): the held-out dispersion MLE recovers a planted
`r`, the leakage-safe expanding calibration only ever uses strictly-prior seasons, the
independent convolution reproduces sum/difference/marginal moments, the quantile grid and
p_over are monotone/consistent, the randomised PIT of correctly-specified draws is uniform (and
mis-specified — too-tight — draws fail the flatness gate, which is exactly the E2.1→E2.3 fix),
calib_80 ≈ 0.80 when calibrated, and the served params round-trip.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import nbinom

from betting_ml.utils.totals_distribution import (
    DEFAULT_QUANTILES,
    TotalsDistributionParams,
    calibrate_dispersion_expanding,
    derive_distributions,
    draw_independent_samples,
    fit_negbin_dispersion,
    interval_coverage,
    pit_flatness,
    prob_over,
    prob_push,
    quantile_grid,
    randomized_pit,
)


def _nb(mu, r, n, rng):
    p = r / (r + mu)
    return nbinom.rvs(r, p, size=n, random_state=rng).astype(float)


# ---------------------------------------------------------------------------
# Dispersion MLE + leakage-safe expanding calibration
# ---------------------------------------------------------------------------

class TestDispersion:
    @pytest.mark.parametrize("r_true", [2.0, 3.7, 8.5])
    def test_mle_recovers_planted_r(self, r_true):
        rng = np.random.default_rng(3)
        mu = np.full(60_000, 4.5)
        y = _nb(4.5, r_true, 60_000, rng)
        assert fit_negbin_dispersion(y, mu) == pytest.approx(r_true, rel=0.08)

    def test_expanding_window_uses_only_prior_seasons(self):
        """season T's r is fit on seasons < T only; the earliest season is omitted (no prior)."""
        rng = np.random.default_rng(4)
        seasons, mus, ys = [], [], []
        for yr in (2021, 2022, 2023, 2024):
            n = 4000
            seasons.append(np.full(n, yr))
            mus.append(np.full(n, 4.5))
            ys.append(_nb(4.5, 3.7, n, rng))
        season = np.concatenate(seasons); mu = np.concatenate(mus); y = np.concatenate(ys)
        r_by = calibrate_dispersion_expanding(season, mu, y)
        assert 2021 not in r_by                       # earliest = seed, no strictly-prior data
        assert set(r_by) == {2022, 2023, 2024}
        # all ≈ 3.7 (stationary dispersion) → a single global r is justified
        for r in r_by.values():
            assert r == pytest.approx(3.7, rel=0.12)

    def test_expanding_r_is_leakage_safe_not_contaminated_by_future(self):
        """A late-season dispersion SHIFT must NOT bleed into earlier seasons' calibrated r."""
        rng = np.random.default_rng(5)
        # 2021-2022 tight (r=10), 2023-2024 fat (r=2). 2022's r (sees only 2021) should read tight.
        blocks = {2021: 10.0, 2022: 10.0, 2023: 2.0, 2024: 2.0}
        seasons, mus, ys = [], [], []
        for yr, r in blocks.items():
            n = 6000
            seasons.append(np.full(n, yr)); mus.append(np.full(n, 4.5))
            ys.append(_nb(4.5, r, n, rng))
        r_by = calibrate_dispersion_expanding(
            np.concatenate(seasons), np.concatenate(mus), np.concatenate(ys))
        assert r_by[2022] == pytest.approx(10.0, rel=0.2)     # only 2021 seen → tight
        assert r_by[2024] < r_by[2022]                        # fat tail pulls the expanding r down


# ---------------------------------------------------------------------------
# Independent convolution → total / run-diff / team-totals
# ---------------------------------------------------------------------------

class TestConvolution:
    def test_independent_total_variance_is_sum_of_marginals(self):
        rng = np.random.default_rng(6)
        n = 20_000
        mu_h, mu_a, r = np.full(n, 4.6), np.full(n, 4.4), 3.7
        yh, ya = draw_independent_samples(mu_h, mu_a, r, rng, n_draws=5)
        from betting_ml.utils.copula import negbin_var
        expect = negbin_var(4.6, 3.7) + negbin_var(4.4, 3.7)
        assert (yh + ya).ravel().var() == pytest.approx(expect, rel=0.04)

    def test_per_side_dispersion_widens_only_that_side(self):
        """r_away defaults to r_home (shared); setting it independently changes only the away
        marginal's variance — the lever that calibrates run-diff without touching home."""
        rng = np.random.default_rng(60)
        n = 15_000
        mu_h, mu_a = np.full(n, 4.5), np.full(n, 4.5)
        from betting_ml.utils.copula import negbin_var
        # shared r=6 → both tight; drop away to r=2 → away fatter, home unchanged
        yh, ya = draw_independent_samples(mu_h, mu_a, 6.0, rng, r_away=2.0, n_draws=8)
        assert yh.ravel().var() == pytest.approx(negbin_var(4.5, 6.0), rel=0.05)
        assert ya.ravel().var() == pytest.approx(negbin_var(4.5, 2.0), rel=0.05)
        assert ya.ravel().var() > yh.ravel().var() * 1.3
        # r_away=None ⇒ shared (both sides equal variance)
        yh2, ya2 = draw_independent_samples(mu_h, mu_a, 6.0, rng, n_draws=8)
        assert ya2.ravel().var() == pytest.approx(yh2.ravel().var(), rel=0.06)

    def test_derive_distributions_shapes_and_identities(self):
        rng = np.random.default_rng(7)
        yh, ya = draw_independent_samples(np.full(50, 4.5), np.full(50, 4.0), 3.7, rng, n_draws=100)
        d = derive_distributions(yh, ya)
        assert d["total"].shape == (50, 100)
        np.testing.assert_array_equal(d["total"], yh + ya)
        np.testing.assert_array_equal(d["run_diff"], yh - ya)
        np.testing.assert_array_equal(d["home_total"], yh)

    def test_lower_r_widens_the_total(self):
        """The whole point: a smaller (held-out) r → fatter marginals → wider total variance."""
        rng = np.random.default_rng(8)
        n = 12_000
        mu_h, mu_a = np.full(n, 4.6), np.full(n, 4.4)
        tight = (lambda yh, ya: (yh + ya).var())(*draw_independent_samples(mu_h, mu_a, 8.5, rng, n_draws=10))
        fat = (lambda yh, ya: (yh + ya).var())(*draw_independent_samples(mu_h, mu_a, 3.7, rng, n_draws=10))
        assert fat > tight * 1.05


# ---------------------------------------------------------------------------
# Quantile grid + p_over
# ---------------------------------------------------------------------------

class TestGrid:
    def test_quantile_grid_monotone_and_shaped(self):
        rng = np.random.default_rng(9)
        yh, ya = draw_independent_samples(np.full(30, 4.5), np.full(30, 4.5), 3.7, rng, n_draws=2000)
        grid = quantile_grid(yh + ya)
        assert grid.shape == (30, len(DEFAULT_QUANTILES))
        assert np.all(np.diff(grid, axis=1) >= 0)          # non-decreasing across quantile levels

    def test_p_over_decreases_with_line_and_matches_push(self):
        rng = np.random.default_rng(10)
        yh, ya = draw_independent_samples(np.full(4000, 4.6), np.full(4000, 4.4), 3.7, rng, n_draws=1)
        tot = (yh + ya)
        lines = [6.5, 8.5, 10.5, 12.5]
        po = prob_over(tot, lines)
        seq = [float(po[ln].mean()) for ln in lines]
        assert all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))   # P(over) ↓ as line ↑
        # half-lines never push; integer line can
        assert float(np.mean(list(prob_push(tot, [8.5]).values())[0])) == pytest.approx(0.0, abs=1e-9)
        assert float(np.mean(list(prob_push(tot, [9.0]).values())[0])) > 0.0

    def test_run_diff_zero_line_is_home_win_prob(self):
        rng = np.random.default_rng(11)
        # home stronger → P(run_diff > 0) > 0.5
        yh, ya = draw_independent_samples(np.full(5000, 5.5), np.full(5000, 3.8), 3.7, rng, n_draws=1)
        d = derive_distributions(yh, ya)
        p_home = float(prob_over(d["run_diff"], [0.0])[0.0].mean())
        assert p_home > 0.5


# ---------------------------------------------------------------------------
# PIT + calib_80 — the E2.3 calibration gate
# ---------------------------------------------------------------------------

class TestCalibration:
    def test_pit_uniform_when_correctly_specified(self):
        """Realised totals drawn from the SAME predictive the PIT is computed against → uniform."""
        rng = np.random.default_rng(12)
        n = 6000
        mu_h, mu_a, r = np.full(n, 4.6), np.full(n, 4.4), 3.7
        samp_yh, samp_ya = draw_independent_samples(mu_h, mu_a, r, rng, n_draws=2000)
        tot_samp = samp_yh + samp_ya
        # one realised draw per game from the same marginals
        obs = (_nb(4.6, r, n, rng) + _nb(4.4, r, n, rng))
        flat = pit_flatness(randomized_pit(obs, tot_samp, rng))
        assert flat["is_flat"]
        assert flat["mean"] == pytest.approx(0.5, abs=0.02)

    def test_too_tight_dispersion_fails_flatness(self):
        """Truth is fat (r=3.7) but the predictive is the E2.1-style too-tight r=8.5 → PIT
        U-shaped / non-flat. This is exactly the miscalibration E2.3 fixes."""
        rng = np.random.default_rng(13)
        n = 6000
        mu_h, mu_a = np.full(n, 4.6), np.full(n, 4.4)
        samp_yh, samp_ya = draw_independent_samples(mu_h, mu_a, 8.5, rng, n_draws=2000)  # too tight
        obs = (_nb(4.6, 3.7, n, rng) + _nb(4.4, 3.7, n, rng))                            # truth fat
        assert not pit_flatness(randomized_pit(obs, samp_yh + samp_ya, rng))["is_flat"]

    def test_calib_80_at_or_above_floor_when_calibrated(self):
        """A well-calibrated DISCRETE total covers AT LEAST its nominal 80% (integer-valued
        quantiles snap outward → conservative over-coverage), so it clears the E2.3 gate floor
        (calib_80 ≥ 0.80). The randomised PIT is the sharp two-sided calibration check."""
        rng = np.random.default_rng(14)
        n = 6000
        mu_h, mu_a, r = np.full(n, 4.6), np.full(n, 4.4), 3.7
        samp_yh, samp_ya = draw_independent_samples(mu_h, mu_a, r, rng, n_draws=2000)
        obs = (_nb(4.6, r, n, rng) + _nb(4.4, r, n, rng))
        c80 = interval_coverage(obs, samp_yh + samp_ya)
        assert 0.80 <= c80 <= 0.90          # ≥ floor (gate passes); ≤ 0.90 = not absurdly wide


# ---------------------------------------------------------------------------
# Served params round-trip
# ---------------------------------------------------------------------------

class TestParams:
    def test_to_from_dict_roundtrip(self):
        p = TotalsDistributionParams(dispersion_r=3.71, n_draws=10_000, notes="x")
        q = TotalsDistributionParams.from_dict(p.to_dict())
        assert q.dispersion_r == pytest.approx(3.71)
        assert q.rho == 0.0
        assert q.n_draws == 10_000
        assert tuple(q.quantile_levels) == DEFAULT_QUANTILES
        # per-side unset ⇒ both sides fall back to the pooled dispersion_r
        assert q.r_home == pytest.approx(3.71) and q.r_away == pytest.approx(3.71)

    def test_per_side_dispersion_roundtrip_and_accessors(self):
        p = TotalsDistributionParams(dispersion_r=3.70, dispersion_r_home=3.95, dispersion_r_away=3.45)
        q = TotalsDistributionParams.from_dict(p.to_dict())
        assert q.dispersion_r_home == pytest.approx(3.95)
        assert q.dispersion_r_away == pytest.approx(3.45)
        assert q.r_home == pytest.approx(3.95) and q.r_away == pytest.approx(3.45)
