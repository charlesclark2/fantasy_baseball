"""Tests for Story E5.2 — per-prop distributional pricing (⭐ pitcher strikeouts).

Pure-math unit tests (no Snowflake, no model, no market data):
  * EB shrinkage converges to the raw rate as n→∞ and to the prior at n=0.
  * log5 preserves identity (reduces to one rate when the other == league) and is symmetric.
  * the framing logit nudge moves p in the framing direction and is monotone in gamma.
  * the batters-faced compound has mean ≈ outs/(1−reach) and is overdispersed vs Poisson.
  * K | BF ~ Beta-Binomial has mean ≈ BF·p_k, K ≤ BF, and overdispersion grows as the
    concentration s falls; s→∞ recovers the Binomial variance.
  * the Beta-Binomial concentration MLE recovers a planted s; the leakage-safe expanding
    calibration only ever uses strictly-prior seasons.
  * the full strikeout price is PIT-uniform under the correct spec and FAILS the flatness gate
    when mis-specified (too tight) — the E5.2 calibration is the lever, exactly as in E2.3.
  * pitcher_outs NegBin survival pricing is monotone in the line.
  * batter total-bases ≥ hits, both grow with expected PA.
  * served params round-trip through to_dict/from_dict.
"""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.utils.prop_pricing import (
    StrikeoutPricingParams,
    calibrate_concentration_expanding,
    draw_batter_bases_hits,
    draw_batters_faced,
    draw_strikeouts,
    eb_shrink_rate,
    effective_k_rate,
    fit_betabinom_concentration,
    framing_logit_adjust,
    log5,
    price_strikeouts,
    prob_over_negbin,
    scale_spread,
)
from betting_ml.utils.totals_distribution import (
    pit_flatness,
    prob_over,
    quantile_grid,
    randomized_pit,
)


# ---------------------------------------------------------------------------
# K-rate component: EB shrinkage, log5, framing
# ---------------------------------------------------------------------------

class TestKRate:
    def test_eb_shrink_converges_to_raw_at_large_n(self):
        r = eb_shrink_rate(successes=2200.0, trials=10_000.0, prior_rate=0.18, prior_strength=200.0)
        assert float(r) == pytest.approx(0.22, abs=0.005)   # raw 0.22 dominates the 0.18 prior

    def test_eb_shrink_is_prior_at_zero_trials(self):
        r = eb_shrink_rate(successes=0.0, trials=0.0, prior_rate=0.23, prior_strength=200.0)
        assert float(r) == pytest.approx(0.23, abs=1e-6)

    def test_eb_shrink_pulls_small_sample_toward_prior(self):
        # 3-for-10 (0.30) with a strong 0.22 prior lands much nearer the prior than the raw rate.
        r = float(eb_shrink_rate(3.0, 10.0, 0.22, prior_strength=200.0))
        assert 0.22 <= r < 0.235

    def test_log5_reduces_to_pitcher_when_batter_is_league(self):
        assert float(log5(0.28, 0.22, 0.22)) == pytest.approx(0.28, abs=1e-6)

    def test_log5_reduces_to_batter_when_pitcher_is_league(self):
        assert float(log5(0.22, 0.31, 0.22)) == pytest.approx(0.31, abs=1e-6)

    def test_log5_symmetric_in_the_two_rates(self):
        assert float(log5(0.28, 0.31, 0.22)) == pytest.approx(float(log5(0.31, 0.28, 0.22)), abs=1e-9)

    def test_log5_above_both_when_both_above_league(self):
        # two above-average K rates combine to something above the higher of them.
        p = float(log5(0.28, 0.30, 0.22))
        assert p > 0.30

    def test_framing_nudges_in_the_right_direction_and_is_monotone(self):
        base = 0.24
        up = float(framing_logit_adjust(base, framing_z=1.5, gamma=0.05))
        dn = float(framing_logit_adjust(base, framing_z=-1.5, gamma=0.05))
        none = float(framing_logit_adjust(base, framing_z=0.0, gamma=0.05))
        assert none == pytest.approx(base, abs=1e-9)
        assert dn < none < up

    def test_effective_k_rate_no_framing_equals_log5(self):
        p = effective_k_rate(0.27, 0.25, 0.22)
        assert float(p) == pytest.approx(float(log5(0.27, 0.25, 0.22)), abs=1e-9)


# ---------------------------------------------------------------------------
# Batters-faced compound
# ---------------------------------------------------------------------------

class TestBattersFaced:
    def test_bf_mean_matches_outs_over_one_minus_reach(self):
        rng = np.random.default_rng(0)
        mu_outs = np.array([18.0])           # ~6 IP
        bf = draw_batters_faced(mu_outs, r_outs=20.0, reach_rate=0.30, rng=rng, n_draws=40_000)
        # E[BF] = E[outs]/(1−reach) = 18/0.70 ≈ 25.7
        assert bf.mean() == pytest.approx(18.0 / 0.70, rel=0.04)

    def test_bf_at_least_outs_floor(self):
        rng = np.random.default_rng(1)
        bf = draw_batters_faced(np.array([15.0]), 20.0, 0.0, rng, n_draws=5000)
        # reach_rate≈0 ⇒ BF ≈ outs (clipped at _EPS reach, so a hair above)
        assert bf.mean() == pytest.approx(15.0, rel=0.05)

    def test_bf_overdispersed_vs_outs_only(self):
        rng = np.random.default_rng(2)
        mu = np.full(1, 18.0)
        bf = draw_batters_faced(mu, 20.0, 0.31, rng, n_draws=40_000)
        # adding the reach process strictly inflates variance beyond the outs NegBin alone
        assert bf.var() > 18.0  # NegBin(mu=18,r=20) var ≈ 34; +reaches pushes it higher
        assert bf.var() > 34.0


# ---------------------------------------------------------------------------
# Beta-Binomial strikeout convolution
# ---------------------------------------------------------------------------

class TestStrikeouts:
    def test_k_mean_matches_bf_times_pk(self):
        rng = np.random.default_rng(3)
        bf = np.full((1, 60_000), 25, dtype=np.int64)
        k = draw_strikeouts(bf, p_k=np.array([0.26]), concentration=120.0, rng=rng)
        assert k.mean() == pytest.approx(25 * 0.26, rel=0.03)

    def test_k_never_exceeds_bf(self):
        rng = np.random.default_rng(4)
        bf = rng.integers(10, 30, size=(5, 2000)).astype(np.int64)
        k = draw_strikeouts(bf, p_k=np.full(5, 0.3), concentration=50.0, rng=rng)
        assert np.all(k <= bf)

    def test_lower_concentration_is_more_overdispersed(self):
        rng = np.random.default_rng(5)
        bf = np.full((1, 80_000), 25, dtype=np.int64)
        tight = draw_strikeouts(bf, np.array([0.26]), concentration=400.0, rng=rng)
        loose = draw_strikeouts(bf, np.array([0.26]), concentration=8.0, rng=rng)
        assert loose.var() > tight.var()

    def test_scale_spread_preserves_mean_and_scales_variance(self):
        rng = np.random.default_rng(15)
        samp = rng.poisson(6.0, size=(3, 40_000)).astype(float)
        scaled = scale_spread(samp, 0.7)
        # mean preserved (rounding noise small), variance ≈ λ²·var
        assert scaled.mean(axis=1) == pytest.approx(samp.mean(axis=1), abs=0.2)
        assert (scaled.var(axis=1) / samp.var(axis=1)).mean() == pytest.approx(0.49, abs=0.06)

    def test_scale_spread_identity_at_one(self):
        rng = np.random.default_rng(16)
        samp = rng.poisson(6.0, size=(2, 5000)).astype(float)
        assert np.array_equal(scale_spread(samp, 1.0), np.rint(samp))

    def test_scale_spread_tightens_overdispersed_pit(self):
        # An over-wide predictive (truth tighter than draws) → λ<1 flattens its PIT.
        rng = np.random.default_rng(17)
        truth = rng.poisson(6.0, size=4000).astype(float)
        wide = rng.poisson(6.0, size=(4000, 3000)).astype(float) * 1.0
        wide = wide.mean(axis=1, keepdims=True) + 1.7 * (wide - wide.mean(axis=1, keepdims=True))
        dev_raw = pit_flatness(randomized_pit(truth, np.rint(np.clip(wide, 0, None)), rng))["max_decile_dev"]
        dev_cal = pit_flatness(randomized_pit(truth, scale_spread(wide, 0.6), rng))["max_decile_dev"]
        assert dev_cal < dev_raw

    def test_high_concentration_approaches_binomial_variance(self):
        rng = np.random.default_rng(6)
        n, p = 25, 0.26
        bf = np.full((1, 120_000), n, dtype=np.int64)
        k = draw_strikeouts(bf, np.array([p]), concentration=480.0, rng=rng)
        binom_var = n * p * (1 - p)
        assert k.var() == pytest.approx(binom_var, rel=0.10)


# ---------------------------------------------------------------------------
# Concentration MLE + leakage-safe expanding calibration
# ---------------------------------------------------------------------------

class TestConcentrationCalibration:
    @pytest.mark.parametrize("s_true", [8.0, 40.0, 150.0])
    def test_mle_recovers_planted_concentration(self, s_true):
        rng = np.random.default_rng(7)
        n = np.full(40_000, 25.0)
        mu = np.full(40_000, 0.25)
        p = rng.beta(mu * s_true, (1 - mu) * s_true)
        k = rng.binomial(n.astype(int), p).astype(float)
        assert fit_betabinom_concentration(k, n, mu) == pytest.approx(s_true, rel=0.20)

    def test_expanding_window_uses_only_prior_seasons(self):
        rng = np.random.default_rng(8)
        seasons, ns, mus, ks = [], [], [], []
        s_true = 40.0
        for yr in (2021, 2022, 2023, 2024):
            n = np.full(3000, 25.0)
            mu = np.full(3000, 0.25)
            p = rng.beta(mu * s_true, (1 - mu) * s_true)
            seasons.append(np.full(3000, yr)); ns.append(n); mus.append(mu)
            ks.append(rng.binomial(n.astype(int), p).astype(float))
        season = np.concatenate(seasons)
        s_by = calibrate_concentration_expanding(
            season, np.concatenate(ks), np.concatenate(ns), np.concatenate(mus)
        )
        assert 2021 not in s_by                     # earliest season has no prior residuals
        assert set(s_by) == {2022, 2023, 2024}
        assert all(20.0 < v < 80.0 for v in s_by.values())


# ---------------------------------------------------------------------------
# Full strikeout price: PIT calibration is the gate (mirror E2.3)
# ---------------------------------------------------------------------------

class TestStrikeoutPriceCalibration:
    def _truth_and_inputs(self, rng, n_games=6000, s_true=45.0):
        mu_outs = rng.uniform(12.0, 21.0, size=n_games)
        p_k = rng.uniform(0.18, 0.32, size=n_games)
        reach = 0.31
        # Generate a TRUTH K from the same generative model the pricer assumes.
        outs = rng.poisson(mu_outs)
        reaches = rng.negative_binomial(np.clip(outs, 1, None), 1 - reach)
        bf_true = np.clip(outs, 1, None) + reaches
        pp = rng.beta(p_k * s_true, (1 - p_k) * s_true)
        k_true = rng.binomial(bf_true, pp).astype(float)
        return mu_outs, p_k, reach, bf_true, k_true

    def test_correctly_specified_price_is_pit_flat(self):
        rng = np.random.default_rng(11)
        mu_outs, p_k, reach, _bf, k_true = self._truth_and_inputs(rng, s_true=45.0)
        samp = price_strikeouts(mu_outs, 30.0, reach, p_k, concentration=45.0, rng=rng, n_draws=4000)
        u = randomized_pit(k_true, samp, rng)
        assert pit_flatness(u)["is_flat"]

    def test_overconfident_price_fails_flatness(self):
        rng = np.random.default_rng(12)
        mu_outs, p_k, reach, _bf, k_true = self._truth_and_inputs(rng, s_true=12.0)
        # Truth is heavily overdispersed (s=12) but we price as near-Binomial (s=480) → too tight.
        samp = price_strikeouts(mu_outs, 30.0, reach, p_k, concentration=480.0, rng=rng, n_draws=4000)
        u = randomized_pit(k_true, samp, rng)
        assert not pit_flatness(u)["is_flat"]

    def test_prob_over_monotone_decreasing_in_line(self):
        rng = np.random.default_rng(13)
        mu_outs, p_k, reach, _bf, _k = self._truth_and_inputs(rng, n_games=200)
        samp = price_strikeouts(mu_outs, 30.0, reach, p_k, concentration=45.0, rng=rng, n_draws=3000)
        po = prob_over(samp, [4.5, 5.5, 6.5, 7.5])
        assert np.all(po[4.5] >= po[5.5]) and np.all(po[5.5] >= po[6.5]) and np.all(po[6.5] >= po[7.5])

    def test_quantile_grid_monotone(self):
        rng = np.random.default_rng(14)
        samp = price_strikeouts(np.array([18.0]), 30.0, 0.31, np.array([0.26]),
                                concentration=45.0, rng=rng, n_draws=5000)
        grid = quantile_grid(samp)
        assert np.all(np.diff(grid[0]) >= 0)


# ---------------------------------------------------------------------------
# pitcher_outs NegBin survival pricing
# ---------------------------------------------------------------------------

class TestPitcherOuts:
    def test_prob_over_monotone_in_line(self):
        mu = np.array([16.0, 18.0, 20.0])
        po = prob_over_negbin(mu, r=20.0, lines=[14.5, 16.5, 18.5, 20.5])
        assert np.all(po[14.5] >= po[16.5]) and np.all(po[16.5] >= po[18.5])

    def test_higher_mu_has_higher_prob_over(self):
        po = prob_over_negbin(np.array([14.0, 20.0]), r=20.0, lines=[17.5])
        assert po[17.5][1] > po[17.5][0]


# ---------------------------------------------------------------------------
# batter total bases / hits
# ---------------------------------------------------------------------------

class TestBatterProps:
    def test_total_bases_at_least_hits(self):
        rng = np.random.default_rng(20)
        tb, hits = draw_batter_bases_hits(
            np.array([4.3]), 0.15, 0.045, 0.004, 0.035, rng, n_draws=20_000
        )
        assert tb.mean() >= hits.mean()

    def test_more_pa_more_output(self):
        rng = np.random.default_rng(21)
        tb_lo, _ = draw_batter_bases_hits(np.array([3.0]), 0.15, 0.045, 0.004, 0.035, rng, n_draws=20_000)
        tb_hi, _ = draw_batter_bases_hits(np.array([5.0]), 0.15, 0.045, 0.004, 0.035, rng, n_draws=20_000)
        assert tb_hi.mean() > tb_lo.mean()


# ---------------------------------------------------------------------------
# Served params round-trip
# ---------------------------------------------------------------------------

class TestRecencyRateConstruction:
    """The in-season-stuff-change fix: rate_mode controls whether the K-rate tracks recent form."""

    def _frame(self):
        import pandas as pd
        rng = np.random.default_rng(0)
        n = 400
        return pd.DataFrame(dict(
            game_pk=np.arange(n), game_date=pd.to_datetime("2024-04-01") + pd.to_timedelta(np.arange(n), "D"),
            game_year=np.full(n, 2024), pitcher_id=rng.integers(1, 50, n),
            side=rng.choice(["home", "away"], n), is_home_team=rng.choice([True, False], n),
            strikeouts=rng.uniform(3, 9, n), batters_faced=rng.uniform(18, 28, n),
            outs_recorded=rng.uniform(12, 21, n),
            k_career=np.full(n, 200.0), bf_career=np.full(n, 1000.0),     # career rate 0.20
            k_season=np.full(n, 30.0), bf_season=np.full(n, 150.0),       # season rate 0.20
            outs_season=np.full(n, 100.0),
            starter_ip_mu=rng.uniform(14, 19, n), starter_ip_dispersion=np.full(n, 25.0),
            opp_lineup_k_pct=np.full(n, 0.22), catcher_framing_runs=rng.normal(0, 5, n),
            k_pct_7d=np.full(n, 0.32), k_pct_30d=np.full(n, 0.30),        # HOT recent form (≫ career 0.20)
            whiff_rate_30d=np.full(n, 0.28), csw_pct_3start=np.full(n, 0.30),
            velo_delta_3start=np.full(n, 1.0), fastball_velo_trend=np.full(n, 0.5),
        ))

    def test_recency_rate_higher_than_flat_when_pitcher_is_hot(self):
        from betting_ml.scripts.prop_pricing.fit_prop_pricing import build_predictors
        frame = self._frame()
        flat = build_predictors(frame, rate_mode="season_career")["eb_pitcher_k"].mean()
        rec = build_predictors(frame, rate_mode="recency_blend")["eb_pitcher_k"].mean()
        # A pitcher whose last-month K% (0.30) ≫ his season/career (0.20) reads HOTTER under recency.
        assert rec > flat

    def test_career_only_ignores_in_season_form(self):
        from betting_ml.scripts.prop_pricing.fit_prop_pricing import build_predictors
        frame = self._frame()
        career = build_predictors(frame, rate_mode="career_only")["eb_pitcher_k"].mean()
        rec = build_predictors(frame, rate_mode="recency_blend")["eb_pitcher_k"].mean()
        assert rec > career   # career-only can't see the hot streak; recency can

    def test_framing_toggle_changes_pk(self):
        from betting_ml.scripts.prop_pricing.fit_prop_pricing import build_predictors
        frame = self._frame()
        on = build_predictors(frame, framing=True)["p_k"].to_numpy()
        off = build_predictors(frame, framing=False)["p_k"].to_numpy()
        assert not np.allclose(on, off)   # framing nudge actually moves p_k

    def test_cold_start_recency_yields_finite_pk(self):
        """Cold-start rows (NaN trailing-30d/season history) must NOT produce NaN/out-of-range p_k —
        the recency-fold failure (`p<0/NaN`) the bake-off hit. Fallback bottoms out at league rate."""
        import pandas as pd
        from betting_ml.scripts.prop_pricing.fit_prop_pricing import build_predictors
        frame = self._frame()
        # Make the first 50 rows true cold-starts: no season/career counts, no recency windows.
        for col in ["k_season", "bf_season", "outs_season", "k_career", "bf_career",
                    "k_pct_7d", "k_pct_30d"]:
            frame.loc[:49, col] = np.nan
        for mode in ("recency_blend", "recency_30d", "recency_7d", "season_career", "career_only"):
            pk = build_predictors(frame, rate_mode=mode)["p_k"].to_numpy()
            assert np.all(np.isfinite(pk)), f"{mode} produced non-finite p_k"
            assert np.all((pk > 0) & (pk < 1)), f"{mode} produced out-of-range p_k"


class TestParams:
    def test_round_trip(self):
        p = StrikeoutPricingParams(
            concentration=45.0, league_k_rate=0.225, framing_gamma=0.04, notes="x"
        )
        p2 = StrikeoutPricingParams.from_dict(p.to_dict())
        assert p2.concentration == p.concentration
        assert p2.league_k_rate == p.league_k_rate
        assert p2.framing_gamma == p.framing_gamma
        assert p2.version == p.version
