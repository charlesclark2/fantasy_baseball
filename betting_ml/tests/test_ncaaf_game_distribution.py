"""NCAAF-P1.4 — joint game-distribution guards (the H2H · spread · total core).

Fast-gate only: pure numpy/scipy over SYNTHETIC data, no DuckDB, no S3, no `pipeline` import
(the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule). The module under test imports
only `betting_ml.utils.totals_distribution`, so it is import-safe here.

What these guards are actually for:
  * the ORACLE-FLOOR guard (the MLB E2.1-r inverted-metric tell): truth drawn from EXACTLY the
    form being scored is the best any model of that form can do — nothing may score better, and
    an under-dispersed model must score WORSE. A candidate beating the oracle = the metric is
    inverted, not the model good;
  * the three markets are DERIVED coherently from the one joint draw (P(home win) matches the
    margin marginal; totals P(over) is monotone in the line);
  * the held-out dispersion FITS recover a known truth (σ/ρ and the Student-t dof) — otherwise
    every served interval is decoration;
  * the CV axis is `season_order_week` / `game_date`, NEVER raw `week` (the single most important
    P1.1 carry-over — a source guard so the postseason week=1 collision can't silently return).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    FORMS,
    JointDispersion,
    NcaafGameDistributionParams,
    derive_markets,
    downstream_score,
    draw_joint,
    fit_gaussian_dispersion,
    fit_strength_posterior_scale,
    fit_student_t_dof,
    oracle_observations,
    passes_calibration_floor,
    score_calibration,
    strength_posterior_sigma,
)

_SEED = 7


def _synthetic_means(n_games: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Realistic NCAAF per-game means: margin ~ N(4, 14) (home edge, wide), total ~ N(55, 9)."""
    mu_margin = rng.normal(4.0, 14.0, n_games)
    mu_total = np.clip(rng.normal(55.0, 9.0, n_games), 20.0, None)
    return mu_margin, mu_total


# ══════════════════════════════════════════════════════════════════════════════════════
# The oracle-floor guard — the inverted-metric tell, per form
# ══════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("form", ["gaussian", "student_t", "count"])
def test_oracle_is_the_scoring_floor(form: str) -> None:
    """A model whose form + dispersion EXACTLY match the data-generating truth is an oracle —
    the best achievable. An UNDER-dispersed model (σ halved) must NOT score better; the oracle
    must be at/near the floor and pass the calib_80 floor. If an under-dispersed model scored
    LOWER (better), the selection metric would be inverted (the E2.1-r landmine)."""
    rng = np.random.default_rng(_SEED)
    n = 1200
    mu_margin, mu_total = _synthetic_means(n, rng)
    truth_disp = JointDispersion(sigma_margin=13.0, sigma_total=17.0, rho=0.1, dof=6.0,
                                 r_home=120.0, r_away=120.0)

    # realised outcomes drawn from EXACTLY this form + dispersion (integer, like a real score)
    obs = oracle_observations(form, mu_margin, mu_total, truth_disp, np.random.default_rng(_SEED + 1))

    def score(disp: JointDispersion) -> tuple[float, dict]:
        m_s, t_s = draw_joint(form, mu_margin, mu_total, disp, np.random.default_rng(_SEED + 2), n_draws=3000)
        metrics = score_calibration(derive_markets(m_s, t_s), obs, np.random.default_rng(_SEED + 3))
        return downstream_score(metrics), metrics

    oracle_score, oracle_metrics = score(truth_disp)
    under = JointDispersion(sigma_margin=6.5, sigma_total=8.5, rho=0.1, dof=6.0, r_home=1000.0, r_away=1000.0)
    under_score, _ = score(under)

    # the tell: nothing beats the oracle. A tiny sampling wobble is allowed but a real inversion is not.
    assert oracle_score <= under_score + 1e-3, (
        f"[{form}] under-dispersed model scored {under_score:.4f} ≤ oracle {oracle_score:.4f} "
        "— the selection metric is INVERTED (rewards under-dispersion)")
    # the oracle covers AT LEAST nominal 80% (calib_80 is a floor, never a target)
    assert passes_calibration_floor(oracle_metrics), (
        f"[{form}] the oracle fails its own calib_80 floor: "
        f"{ {j: oracle_metrics[j]['calib_80'] for j in ('margin', 'total')} }")


# ══════════════════════════════════════════════════════════════════════════════════════
# The three markets are coherent reads off the one joint draw
# ══════════════════════════════════════════════════════════════════════════════════════

def test_home_win_prob_matches_margin_marginal() -> None:
    """P(home win) derived from the sample = P(margin>0). For a Gaussian margin that is Φ(μ/σ);
    the sampled home-win rate must track the analytic value."""
    from scipy.stats import norm
    rng = np.random.default_rng(_SEED)
    mu_margin = np.array([-7.0, 0.0, 3.0, 10.0, 21.0])
    mu_total = np.full(5, 55.0)
    disp = JointDispersion(sigma_margin=13.5, sigma_total=17.0, rho=0.0)
    m_s, t_s = draw_joint("gaussian", mu_margin, mu_total, disp, rng, n_draws=40000)
    markets = derive_markets(m_s, t_s)
    p_home_sampled = markets["home_win"].mean(axis=1)
    p_home_analytic = norm.cdf(mu_margin / disp.sigma_margin)
    assert np.allclose(p_home_sampled, p_home_analytic, atol=0.01)
    # a pick'em (μ=0) is ~50/50; a 21-point favourite is a heavy home favourite
    assert abs(p_home_sampled[1] - 0.5) < 0.01
    assert p_home_sampled[-1] > 0.9


def test_prob_over_monotone_in_line() -> None:
    rng = np.random.default_rng(_SEED)
    mu_margin = np.zeros(3)
    mu_total = np.array([48.0, 55.0, 62.0])
    disp = JointDispersion(sigma_margin=13.0, sigma_total=16.0, rho=0.0)
    _, t_s = draw_joint("gaussian", mu_margin, mu_total, disp, rng, n_draws=20000)
    p_over45 = (t_s > 45).mean(axis=1)
    p_over65 = (t_s > 65).mean(axis=1)
    assert np.all(p_over45 > p_over65)                 # a lower line is easier to go over
    assert p_over45[2] > p_over45[1] > p_over45[0]     # higher μ_total ⇒ higher P(over the same line)


def test_count_form_margin_total_consistency() -> None:
    """The count foil draws integer home/away points; total = h+a ≥ 0 and |margin| ≤ total."""
    rng = np.random.default_rng(_SEED)
    mu_margin = np.array([3.0, -10.0, 0.0])
    mu_total = np.array([55.0, 60.0, 48.0])
    disp = JointDispersion(sigma_margin=13.0, sigma_total=16.0, rho=0.0, r_home=100.0, r_away=100.0)
    m_s, t_s = draw_joint("count", mu_margin, mu_total, disp, rng, n_draws=5000)
    assert np.all(t_s >= 0)
    assert np.all(np.abs(m_s) <= t_s + 1e-9)           # |home−away| ≤ home+away for non-negatives
    assert np.all(m_s == np.rint(m_s))                 # integer counts


# ══════════════════════════════════════════════════════════════════════════════════════
# Held-out dispersion fits recover truth
# ══════════════════════════════════════════════════════════════════════════════════════

def test_gaussian_dispersion_recovers_sigma_and_rho() -> None:
    rng = np.random.default_rng(_SEED)
    n = 20000
    z1 = rng.standard_normal(n)
    z2 = rng.standard_normal(n)
    true_rho = 0.35
    rm = 12.0 * z1
    rt = 16.0 * (true_rho * z1 + np.sqrt(1 - true_rho**2) * z2)
    d = fit_gaussian_dispersion(rm, rt)
    assert abs(d.sigma_margin - 12.0) < 0.5
    assert abs(d.sigma_total - 16.0) < 0.5
    assert abs(d.rho - true_rho) < 0.03


def test_student_t_dof_distinguishes_heavy_from_normal() -> None:
    rng = np.random.default_rng(_SEED)
    from scipy.stats import t as student_t
    heavy = student_t.rvs(df=4.0, size=15000, random_state=rng) * 12.0
    dof_heavy = fit_student_t_dof(heavy, sigma=float(np.std(heavy)))
    normal = rng.standard_normal(15000) * 12.0
    dof_normal = fit_student_t_dof(normal, sigma=float(np.std(normal)))
    assert dof_heavy < 12.0            # heavy tails → low dof
    assert dof_normal > dof_heavy      # a Normal is pushed toward the high-dof (Normal) limit


def test_correctly_specified_gaussian_is_pit_flat() -> None:
    rng = np.random.default_rng(_SEED)
    n = 4000
    mu_margin, mu_total = _synthetic_means(n, rng)
    disp = JointDispersion(sigma_margin=13.0, sigma_total=16.0, rho=0.1)
    obs = oracle_observations("gaussian", mu_margin, mu_total, disp, np.random.default_rng(_SEED + 1))
    m_s, t_s = draw_joint("gaussian", mu_margin, mu_total, disp, np.random.default_rng(_SEED + 2), n_draws=4000)
    metrics = score_calibration(derive_markets(m_s, t_s), obs, np.random.default_rng(_SEED + 3))
    assert metrics["margin"]["pit_is_flat"]
    assert metrics["total"]["pit_is_flat"]


# ══════════════════════════════════════════════════════════════════════════════════════
# The posterior-predictive form propagates the strength posterior (the PM small-sample nudge)
# ══════════════════════════════════════════════════════════════════════════════════════

def test_strength_posterior_is_wider_for_thin_sample_games() -> None:
    """A game with a WIDE strength posterior (few games played) must get a WIDER predictive σ
    than a game with a tight posterior — the whole point of propagating the posterior at
    12–15 games/team. σ_g = √(σ0² + k²·strength_var)."""
    strength_var = np.array([10.0, 40.0, 120.0])   # tight → wide (early season) posterior
    sig = strength_posterior_sigma(sigma0=13.0, k=1.0, strength_var=strength_var)
    assert sig[0] < sig[1] < sig[2]                # monotone in posterior width
    assert sig[2] > 13.0                           # wider than the irreducible σ0 alone


def test_strength_posterior_scale_recovers_k_and_is_pit_flat() -> None:
    """Data generated with a KNOWN heteroscedastic width (σ_g² = σ0² + k²·strength_var) — the
    E13.6 fit must recover k>0 (propagation is real, not collapsed) and the correctly-specified
    posterior-predictive must be PIT-flat. If k collapsed to 0 the thin-sample games would be
    under-dispersed."""
    rng = np.random.default_rng(_SEED)
    n = 6000
    strength_var = rng.uniform(10.0, 130.0, n)     # the real week-1→week-14 posterior spread
    sigma0, k_true = 12.0, 1.3
    sig = strength_posterior_sigma(sigma0, k_true, strength_var)
    resid = rng.standard_normal(n) * sig           # zero-mean heteroscedastic residuals
    s0_hat, k_hat = fit_strength_posterior_scale(resid, strength_var)
    assert k_hat > 0.5, f"k collapsed to {k_hat:.3f} — propagation lost"
    assert abs(k_hat - k_true) < 0.4 and abs(s0_hat - sigma0) < 3.0

    # correctly-specified posterior-predictive is PIT-flat
    mu = np.zeros(n)
    disp = JointDispersion(sigma_margin=13.0, sigma_total=16.0, rho=0.0)
    m_s, t_s = draw_joint("strength_posterior", mu, mu + 55.0, disp, np.random.default_rng(_SEED + 1),
                          n_draws=3000, sigma_margin_native=sig, sigma_total_native=sig)
    obs = {"margin": np.rint(resid), "total": np.rint(55.0 + rng.standard_normal(n) * sig),
           "home_win": (resid > 0).astype(float)}
    metrics = score_calibration(derive_markets(m_s, t_s), obs, np.random.default_rng(_SEED + 2))
    assert metrics["margin"]["pit_is_flat"]


def test_strength_posterior_is_a_registered_form() -> None:
    assert "strength_posterior" in FORMS


def test_params_roundtrip() -> None:
    p = NcaafGameDistributionParams(form="student_t", sigma_margin=13.1, sigma_total=16.2,
                                    rho=0.12, dof=7.5, learner="lgbm", contract="full")
    q = NcaafGameDistributionParams.from_dict(p.to_dict())
    assert q.form == "student_t" and abs(q.sigma_margin - 13.1) < 1e-9 and abs(q.dof - 7.5) < 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════
# The P1.5-facing predictor interface + the strength-decomposition (no double-count) contract
# ══════════════════════════════════════════════════════════════════════════════════════

def test_predictor_fixed_strength_narrows_to_game_noise_only() -> None:
    """The season-sim contract: `fixed_strength=True` must use σ₀ ALONE (the strength uncertainty
    is already in μ because the sim drew it once for the season) — so its interval is NARROWER
    than the full posterior-predictive, which ADDS k²·strength_var. Using the full width inside
    the sim would DOUBLE-COUNT the strength posterior."""
    from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_predictor import (
        matchup_sigma, sample_matchup,
    )
    from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
        NcaafGameDistributionParams,
    )
    p = NcaafGameDistributionParams(form="strength_posterior", sigma_margin=16.0, sigma_total=17.0,
                                    rho=0.05, sigma0_margin=14.0, k_margin=1.0,
                                    sigma0_total=15.0, k_total=1.0)
    strength_var = 80.0                       # a wide (early-season) strength posterior
    sig_full, _ = matchup_sigma(p, strength_var, fixed_strength=False)
    sig_fixed, _ = matchup_sigma(p, strength_var, fixed_strength=True)
    assert sig_fixed[0] < sig_full[0]                              # game-noise-only is narrower
    assert np.isclose(sig_fixed[0], 14.0)                         # exactly σ₀
    assert np.isclose(sig_full[0], np.sqrt(14.0**2 + 1.0**2 * 80.0))

    rng = np.random.default_rng(_SEED)
    full = sample_matchup(p, 3.0, 55.0, strength_var, rng, n_draws=20000, fixed_strength=False)
    fixed = sample_matchup(p, 3.0, 55.0, strength_var, rng, n_draws=20000, fixed_strength=True)
    assert fixed["margin"].std() < full["margin"].std()          # sim mode is tighter per game


def test_predictor_market_probabilities_are_coherent() -> None:
    from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_predictor import (
        market_probabilities, sample_matchup,
    )
    from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
        NcaafGameDistributionParams,
    )
    p = NcaafGameDistributionParams(form="gaussian", sigma_margin=13.5, sigma_total=16.0, rho=0.0)
    rng = np.random.default_rng(_SEED)
    mk = sample_matchup(p, 7.0, 55.0, 0.0, rng, n_draws=40000)     # home favoured by 7
    probs = market_probabilities(mk, home_spread=-3.0, total_line=52.5)
    assert 0.5 < probs["p_home_win"] < 1.0                        # a 7-pt favourite wins > 50%
    assert probs["p_home_win"] > probs["p_home_cover"]            # covering −3 is harder than winning
    assert 0.5 < probs["p_over"] < 1.0                            # μ_total 55 > line 52.5


# ══════════════════════════════════════════════════════════════════════════════════════
# The CV axis is season_order_week / game_date, NEVER raw week (P1.1 carry-over — source guard)
# ══════════════════════════════════════════════════════════════════════════════════════

def test_bakeoff_cv_axis_is_season_order_not_raw_week() -> None:
    """A source guard: the harness must order/purge folds by `season_order_week` + `game_date`
    (monotone with the season order, immune to the postseason `week`=1 collision) and must NEVER
    sort by the raw `week`. Enforced mechanically so the P1.1 landmine can't silently reappear."""
    src = (Path(__file__).resolve().parents[2] / "quant_sports_intel_models" / "football" /
           "ncaaf" / "models" / "bakeoff_ncaaf_game.py").read_text()
    # the fold builder sorts by season_order_week + game_date
    assert 'sort_values([_YEAR, "season_order_week", _DATE])' in src
    # and never sorts by a bare raw-week key
    assert not re.search(r'sort_values\(\s*\[?["\']week["\']', src), "harness must not sort by raw week"
    # the split is date-purged (season_order-monotone), not week-keyed
    assert 'date_col=_DATE' in src
