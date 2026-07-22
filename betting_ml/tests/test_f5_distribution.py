"""Tests for the E2.4 F5 per-side distribution core + bake-off harness (pure logic only).

The heavy paths (the lakehouse pull, the multi-fold learner fits) are the operator's job and are
never exercised here — every test is Snowflake/S3-free. What IS pinned:

  * each pre-registered FORM's NLL MLE recovers a planted dispersion (poisson/negbin/betabinom);
  * each form's sampler has the right shape, support, and moments;
  * the independent convolution reproduces var(total) = var(home) + var(away);
  * the ORACLE-FLOOR guard PER FORM — truth drawn from exactly the form being scored is the best
    any model of that form can do (PIT-flat, over-covers the discrete 80% interval); nothing may
    score better. This is the E2.1-r inverted-metric regression test, replicated for F5's three
    forms because F5's LOWER mean makes the interval-coverage inflation WORSE;
  * the harness's pre-registration (4 forms, 4 contracts incl. the F5 no_bullpen drop) and its
    form-aware draw path.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils import f5_distribution as f5
from betting_ml.scripts.totals_generative import bakeoff_f5_perside as bo5
from betting_ml.scripts.totals_generative import bakeoff_perside as bo


# ---------------------------------------------------------------------------
# Per-form NLL + dispersion MLE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("r_true", [1.5, 3.7, 12.0])
def test_negbin_mle_recovers_planted_r(r_true):
    rng = np.random.default_rng(0)
    mu = rng.uniform(1.0, 4.0, size=40_000)
    y = rng.negative_binomial(r_true, r_true / (r_true + mu)).astype(float)
    assert f5.fit_negbin_r(y, mu) == pytest.approx(r_true, rel=0.15)


@pytest.mark.parametrize("s_true", [3.0, 15.0, 60.0])
def test_betabinom_mle_recovers_planted_s(s_true):
    rng = np.random.default_rng(1)
    n = f5.BETABINOM_N_CAP
    mu = rng.uniform(1.5, 3.5, size=40_000)
    pi = mu / n
    p = rng.beta(s_true * pi, s_true * (1 - pi))
    y = rng.binomial(n, p).astype(float)
    assert f5.fit_betabinom_s(y, mu, n) == pytest.approx(s_true, rel=0.2)


def test_fit_dispersion_dispatches_and_poisson_has_none():
    y = np.array([0.0, 1, 2, 3, 2, 1, 0, 4])
    mu = np.full_like(y, 2.0)
    assert np.isnan(f5.fit_dispersion("poisson", y, mu))
    assert f5.fit_dispersion("negbin", y, mu) > 0
    assert f5.fit_dispersion("betabinom", y, mu) > 0
    with pytest.raises(KeyError):
        f5.fit_dispersion("nope", y, mu)


def test_poisson_nll_minimised_at_true_mean():
    rng = np.random.default_rng(2)
    y = rng.poisson(2.3, size=20_000).astype(float)
    at_truth = f5.poisson_nll(y, np.full_like(y, 2.3))
    off = f5.poisson_nll(y, np.full_like(y, 3.3))
    assert at_truth < off


# ---------------------------------------------------------------------------
# Samplers — shape, support, moments
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form", list(f5.FORMS))
def test_sampler_shape_and_nonnegative(form):
    rng = np.random.default_rng(3)
    mu = np.array([1.0, 2.0, 3.0, 4.0])
    disp = np.full(4, 5.0)
    s = f5.draw_side(form, mu, disp, rng, n_draws=500)
    assert s.shape == (4, 500)
    assert (s >= 0).all()


def test_betabinom_support_is_bounded_by_n_cap():
    rng = np.random.default_rng(4)
    mu = np.full(50, 3.0)
    s = f5.draw_side("betabinom", mu, np.full(50, 10.0), rng, n_draws=2000, n_cap=25)
    assert s.max() <= 25


def test_poisson_variance_equals_mean():
    rng = np.random.default_rng(5)
    mu = np.full(4000, 2.5)
    s = f5.draw_side("poisson", mu, np.ones(4000), rng, n_draws=400)
    assert s.mean() == pytest.approx(2.5, rel=0.05)
    assert s.var() == pytest.approx(2.5, rel=0.1)


def test_negbin_is_overdispersed_vs_poisson():
    rng = np.random.default_rng(6)
    mu = np.full(4000, 2.5)
    nb = f5.draw_side("negbin", mu, np.full(4000, 3.0), rng, n_draws=400)
    assert nb.var() > nb.mean()  # var = mu + mu^2/r > mu


def test_lower_betabinom_s_widens_the_distribution():
    rng = np.random.default_rng(7)
    mu = np.full(3000, 3.0)
    tight = f5.draw_side("betabinom", mu, np.full(3000, 200.0), rng, n_draws=400)
    wide = f5.draw_side("betabinom", mu, np.full(3000, 2.0), rng, n_draws=400)
    assert wide.var() > tight.var()


def test_unknown_form_raises():
    with pytest.raises(KeyError):
        f5.draw_side("nope", np.array([1.0]), np.array([1.0]), np.random.default_rng(0))


# ---------------------------------------------------------------------------
# Independent convolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("form,disp", [("poisson", 1.0), ("negbin", 4.0), ("betabinom", 8.0)])
def test_total_variance_is_sum_of_side_variances(form, disp):
    """ρ=0 independence ⇒ var(home+away) = var(home) + var(away), per game."""
    rng = np.random.default_rng(8)
    mu_h = np.full(2, 2.6)
    mu_a = np.full(2, 2.4)
    yh, ya = f5.draw_f5_independent(mu_h, mu_a, form, np.full(2, disp), np.full(2, disp),
                                    rng, n_draws=60_000)
    dists = f5.derive_distributions(yh, ya)
    var_total = dists["total"].var(axis=1)
    var_sum = yh.var(axis=1) + ya.var(axis=1)
    assert var_total == pytest.approx(var_sum, rel=0.03)


def test_sigma_to_r_moment_matches_negbin_variance():
    mu = np.array([2.0, 3.0, 4.0])
    r_true = np.array([3.0, 8.0, 2.5])
    sigma = np.sqrt(mu + mu**2 / r_true)
    assert f5.sigma_to_negbin_r(mu, sigma) == pytest.approx(r_true, rel=1e-6)


# ---------------------------------------------------------------------------
# The oracle-floor guard — PER FORM (the E2.1-r inverted-metric regression, F5 edition)
# ---------------------------------------------------------------------------

def _oracle_games(form: str, disp: float, n: int, rng) -> pd.DataFrame:
    """A per-game frame whose realised (y_home, y_away) are drawn from EXACTLY the scored form."""
    mu_h, mu_a = 2.6, 2.4
    yh = f5.draw_side(form, np.full(n, mu_h), np.full(n, disp), rng, n_draws=1)[:, 0]
    ya = f5.draw_side(form, np.full(n, mu_a), np.full(n, disp), rng, n_draws=1)[:, 0]
    return pd.DataFrame({
        "mu_home": np.full(n, mu_h), "mu_away": np.full(n, mu_a),
        "r_home": np.full(n, disp), "r_away": np.full(n, disp),
        "y_home": yh.astype(float), "y_away": ya.astype(float),
    })


@pytest.mark.slow
@pytest.mark.parametrize("form,disp", [("poisson", 1.0), ("negbin", 3.0), ("betabinom", 8.0)])
def test_oracle_is_the_scoring_floor(form, disp):
    """No model may score BETTER than a perfectly-specified one, for ANY F5 form.

    Truth drawn from exactly the form being scored is the oracle: it is PIT-flat and passes the
    calib floor by construction, and — because F5 runs are discrete integers with inclusive
    interval bounds — it OVER-covers the nominal 80% interval. A candidate that scored below the
    oracle (on PIT max-decile-dev) or a metric that rewarded UNDER-covering would be the E2.1-r
    inversion tell. This guards the selection metric for all three F5 forms.
    """
    rng = np.random.default_rng(0)
    g = _oracle_games(form, disp, 3000, rng)
    dists, obs = bo5.draw_predictive(g, {"poisson": "poisson", "negbin": "heldout",
                                         "betabinom": "betabinom"}[form], rng, n_draws=3000)
    m = bo.score_predictive(dists, obs, rng)

    assert bo.passes_calibration_floor(m), f"{form} oracle must clear the 0.80 floor"
    for j in bo.SCORED_DISTS:
        assert m[j]["pit_max_decile_dev"] < 0.03, f"{form}/{j} oracle PIT should be flat"
    # The discreteness inflation the CLAUDE.md landmine warns about is REAL and must stay
    # documented: a perfect discrete F5 model over-covers its 80% interval (worse at low mean).
    assert m["total"]["calib_80"] > 0.80


# ---------------------------------------------------------------------------
# Served params roundtrip
# ---------------------------------------------------------------------------

def test_params_roundtrip():
    p = f5.F5DistributionParams(form="betabinom", dispersion_home=12.3, dispersion_away=9.8,
                                n_cap=25, notes="x")
    q = f5.F5DistributionParams.from_dict(p.to_dict())
    assert q.form == "betabinom" and q.dispersion_home == 12.3 and q.n_cap == 25 and q.rho == 0.0


def test_params_poisson_has_no_dispersion():
    p = f5.F5DistributionParams(form="poisson")
    d = p.to_dict()
    assert d["form"] == "poisson" and d["dispersion_home"] is None


# ---------------------------------------------------------------------------
# Harness pre-registration + form-aware plumbing
# ---------------------------------------------------------------------------

def test_pre_registered_forms_and_contracts():
    assert set(bo5.FORM_MODES) == {"poisson", "heldout", "native", "betabinom"}
    assert len(f5.FORMS) >= 3, "§0.5 requires ≥3 distributional forms"
    assert "no_bullpen" in bo5.CONTRACTS, "the F5-specific starter-heavy contract must be registered"
    # the reference/foil is the E2.1-r minimal-fix winner carried to F5
    assert bo5._REFERENCE == ("lgbm_poisson", "full", "heldout")


def test_default_form_native_only_for_ngboost():
    for mc in bo5.MODEL_CLASSES:
        want = "native" if bo5.build_candidate(mc).native else "heldout"
        assert bo5.default_form(mc) == want


def test_form_of_maps_modes_to_samplers():
    assert bo5.form_of("poisson") == "poisson"
    assert bo5.form_of("heldout") == "negbin"
    assert bo5.form_of("native") == "negbin"
    assert bo5.form_of("betabinom") == "betabinom"


def test_no_bullpen_contract_drops_only_bullpen_features():
    feat = ["off_avg_eb_woba", "opp_starter_k_pct_30d", "opp_bp_eb_xwoba",
            "opp_bullpen_ip_prev_1d", "opp_closer_used_prev_1d", "opp_reliever_appearances_prev_7d",
            "opp_high_leverage_used_prev_2d", "elevation_ft"]
    kept = bo5.resolve_contract_f5("no_bullpen", None, feat, feat, top_k=120)
    assert "opp_bp_eb_xwoba" not in kept and "opp_bullpen_ip_prev_1d" not in kept
    assert "opp_closer_used_prev_1d" not in kept and "opp_reliever_appearances_prev_7d" not in kept
    assert "opp_high_leverage_used_prev_2d" not in kept
    # non-bullpen features (incl. the starter, who dominates F5) survive
    assert "off_avg_eb_woba" in kept and "opp_starter_k_pct_30d" in kept and "elevation_ft" in kept


@pytest.mark.parametrize("form_mode", ["poisson", "heldout", "betabinom"])
def test_harness_draw_predictive_runs_for_each_form(form_mode):
    """The form-aware draw path produces (n_games, n_draws) dists + (n_games,) obs — no IO."""
    rng = np.random.default_rng(9)
    n = 100
    g = pd.DataFrame({
        "mu_home": np.full(n, 2.6), "mu_away": np.full(n, 2.4),
        "r_home": np.full(n, 6.0), "r_away": np.full(n, 6.0),
        "y_home": rng.poisson(2.6, n).astype(float), "y_away": rng.poisson(2.4, n).astype(float),
    })
    dists, obs = bo5.draw_predictive(g, form_mode, rng, n_draws=200)
    for k in ("total", "run_diff", "home_total", "away_total"):
        assert dists[k].shape == (n, 200)
        assert obs[k].shape == (n,)
    m = bo.score_predictive(dists, obs, rng)
    assert 0.0 <= bo.downstream_score(m) < 3.0
