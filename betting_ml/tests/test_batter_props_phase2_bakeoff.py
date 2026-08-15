"""
Guards for the Phase-2 batter-props §0.5 bake-off harness
(`betting_ml/scripts/batter_props_phase2_bakeoff.py`).

What is pinned, and why each clause is independently falsifiable (the NF-D17 rule — every
fixture satisfies the OTHER clauses of the invariant it tests, so only the named clause can
flip the result):

  1. CRPS is EXACT for discrete counts (cross-checked against the closed-form Bernoulli case
     and a brute-force integral) — the primary metric being wrong invalidates everything else.
  2. The NB/truncated-NB dispersion MLE RECOVERS a known α (and RAISES rather than returning a
     silent default on failure — NF1.7 (a)).
  3. The structural compound pmf matches brute-force enumeration — the analytic replacement for
     `draw_batter_bases_hits`'s Monte-Carlo must be the same distribution.
  4. Randomized PIT is uniform under the true model (calibration instrument sanity).
  5. ⛔ The market-blind contract: no price column can enter the design matrix, and the guard
     RAISES if the contract is edited to include one.
  6. ⛔ The pooled-HR-benchmark guard RAISES (prereg §9.1) — and passes per-fold scope, so the
     clause is two-sided, not vacuously red.
  7. The registered fold frame: 6 eval folds, expanding train, embargo actually removes the
     boundary window, and 2026H2 rows land in NO fold (never trained on, never evaluated).
  8. DSR-CONV wiring: the two degenerates are declared forward and reach `dsr_gate` as
     `degenerate_arms` (in `n_trials`, out of `V`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.batter_props_phase2_bakeoff import (
    DEGENERATE_ARMS,
    EVAL_FOLDS,
    FORBIDDEN_FEATURES,
    NUMERIC_FEATURES,
    binomial_mixture_pmf,
    build_design,
    compound_tb_pmf,
    crps_discrete,
    fit_nb_alpha,
    fit_trunc_nb_alpha,
    guard_no_pooled_hr_benchmark,
    half_label,
    hurdle_pmf,
    make_folds,
    marginal_pmf,
    model_p_over,
    nb_pmf_grid,
    pit_max_decile_dev,
    poisson_pmf_grid,
    randomized_pit,
    zero_pmf,
)


# ── 1. CRPS exactness ─────────────────────────────────────────────────────────

class TestCRPSExact:
    def test_bernoulli_closed_form(self):
        """On a {0,1} predictive, discrete CRPS must equal the Brier score of P(y=1)
        (NF-W4: the Bernoulli CRPS closed form)."""
        p1 = np.array([0.3, 0.7, 0.05])
        y = np.array([1.0, 0.0, 0.0])
        pmf = np.column_stack([1 - p1, p1, np.zeros(3), np.zeros(3)])
        got = crps_discrete(pmf, y)
        want = (p1 - y) ** 2  # Σ_k (F(k)−1[y≤k])² collapses to the single Brier term
        np.testing.assert_allclose(got, want, atol=1e-12)

    def test_brute_force_integral(self):
        """CRPS via the cdf-sum must equal the brute-force ∫(F−1[y≤x])²dx on a fine grid."""
        rng = np.random.default_rng(0)
        pmf = rng.dirichlet(np.ones(6), size=4)
        y = np.array([0.0, 2.0, 5.0, 3.0])
        got = crps_discrete(pmf, y)
        xs = np.arange(0, 6, 1e-3)
        cdf = np.cumsum(pmf, axis=1)
        for i in range(4):
            F = cdf[i][np.minimum(np.floor(xs).astype(int), 5)]
            ind = (y[i] <= xs).astype(float)
            brute = np.trapezoid((F - ind) ** 2, xs)
            # brute integral stops at 5.0 where F=1 and ind=1 ⇒ no missing mass
            assert abs(got[i] - brute) < 1e-2

    def test_refuses_unnormalized_pmf(self):
        """A non-normalized predictive is REFUSED, never scored (the NF-W3 nan-mean lesson)."""
        pmf = np.array([[0.5, 0.3, 0.0]])  # sums to 0.8
        with pytest.raises(ValueError, match="sum to 1"):
            crps_discrete(pmf, np.array([1.0]))

    def test_perfect_prediction_scores_zero(self):
        pmf = np.zeros((1, 4))
        pmf[0, 2] = 1.0
        assert crps_discrete(pmf, np.array([2.0]))[0] == pytest.approx(0.0)


# ── 2. dispersion MLE ─────────────────────────────────────────────────────────

class TestDispersionMLE:
    def test_recovers_known_alpha(self):
        rng = np.random.default_rng(1)
        mu, alpha = 1.4, 0.5
        r = 1 / alpha
        y = rng.negative_binomial(r, r / (r + mu), size=40_000).astype(float)
        got = fit_nb_alpha(y, np.full_like(y, mu))
        assert abs(got - alpha) < 0.08

    def test_poisson_data_drives_alpha_to_floor(self):
        rng = np.random.default_rng(2)
        y = rng.poisson(1.2, size=20_000).astype(float)
        got = fit_nb_alpha(y, np.full_like(y, 1.2))
        # equidispersed ⇒ α̂ near the floor (true α = 0; the estimate carries O(1/√n) noise,
        # measured 0.024 at n=20k — the bound is meaningful vs the 0.5-scale real-data values)
        assert got < 0.06

    def test_truncated_alpha_recovers_on_positives(self):
        rng = np.random.default_rng(3)
        mu, alpha = 1.8, 0.6
        r = 1 / alpha
        y = rng.negative_binomial(r, r / (r + mu), size=80_000).astype(float)
        pos = y[y > 0]
        got = fit_trunc_nb_alpha(pos, np.full_like(pos, mu))
        assert abs(got - alpha) < 0.12


# ── 3. predictive builders ────────────────────────────────────────────────────

class TestPmfBuilders:
    def test_poisson_grid_matches_scipy(self):
        from scipy.stats import poisson
        mu = np.array([0.4, 1.7])
        pmf = poisson_pmf_grid(mu, 8)
        for i, m in enumerate(mu):
            np.testing.assert_allclose(pmf[i, :8], poisson.pmf(np.arange(8), m), atol=1e-12)
        np.testing.assert_allclose(pmf.sum(axis=1), 1.0, atol=1e-12)

    def test_nb_grid_matches_scipy(self):
        from scipy.stats import nbinom
        mu, alpha = np.array([1.3]), 0.7
        r = 1 / alpha
        pmf = nb_pmf_grid(mu, alpha, 10)
        np.testing.assert_allclose(pmf[0, :10],
                                   nbinom.pmf(np.arange(10), r, r / (r + mu[0])), atol=1e-10)

    def test_hurdle_zero_prob_is_exactly_one_minus_p_pos(self):
        pmf = hurdle_pmf(np.array([0.35]), np.array([1.2]), 0.4, 8)
        assert pmf[0, 0] == pytest.approx(0.65)
        assert pmf.sum() == pytest.approx(1.0)

    def test_degenerates(self):
        z = zero_pmf(5, 3)
        assert (z[:, 0] == 1).all()
        m = marginal_pmf(np.array([0, 0, 1, 2]), 5, 2)
        assert m.shape == (2, 6)
        np.testing.assert_allclose(m.sum(axis=1), 1.0)
        assert np.allclose(m[0], m[1])  # no per-row content by construction

    def test_binomial_mixture_matches_enumeration(self):
        """hits | PA ~ Binomial(PA, p) mixed over an explicit PA distribution."""
        from scipy.stats import binom
        pa_dist = np.array([[0.0, 0.2, 0.5, 0.3]])  # PA ∈ {1,2,3}
        p = np.array([0.31])
        pmf = binomial_mixture_pmf(pa_dist, p, 5)
        want = sum(w * binom.pmf(np.arange(6), n, p[0])
                   for n, w in enumerate(pa_dist[0]))
        np.testing.assert_allclose(pmf[0], want, atol=1e-9)

    def test_compound_tb_matches_brute_force(self):
        """TB pmf must equal exhaustive enumeration of per-PA multinomial outcomes."""
        from itertools import product
        p1, p2, p3, ph = 0.15, 0.05, 0.01, 0.04
        pa_dist = np.array([[0.0, 0.3, 0.7]])       # PA ∈ {1,2}
        pmf = compound_tb_pmf(pa_dist, np.array([p1]), np.array([p2]),
                              np.array([p3]), np.array([ph]), 10)
        base = {0: 1 - (p1 + p2 + p3 + ph), 1: p1, 2: p2, 3: p3, 4: ph}
        want = np.zeros(11)
        for n, w in [(1, 0.3), (2, 0.7)]:
            for outcome in product(base, repeat=n):
                prob = w * np.prod([base[o] for o in outcome])
                want[sum(outcome)] += prob
        np.testing.assert_allclose(pmf[0], want, atol=1e-9)

    def test_model_p_over_half_line(self):
        pmf = np.array([[0.4, 0.35, 0.25]])
        # line 0.5 ⇒ P(y ≥ 1) = 0.6; line 1.5 ⇒ P(y ≥ 2) = 0.25
        np.testing.assert_allclose(model_p_over(pmf, np.array([0.5])), [0.6], atol=1e-12)
        np.testing.assert_allclose(model_p_over(pmf, np.array([1.5])), [0.25], atol=1e-12)


# ── 4. PIT instrument ─────────────────────────────────────────────────────────

class TestPIT:
    def test_uniform_under_true_model(self):
        rng = np.random.default_rng(11)
        mu = np.full(30_000, 1.1)
        y = rng.poisson(mu)
        pmf = poisson_pmf_grid(mu, 12)
        pit = randomized_pit(pmf, y, rng)
        assert pit_max_decile_dev(pit) < 0.012

    def test_detects_a_wrong_model(self):
        """Two-sided: the instrument must FIRE on a known-bad predictive (a flatness check
        that cannot fail is not a check — INC-38)."""
        rng = np.random.default_rng(12)
        y = rng.poisson(2.0, size=30_000)
        pmf = poisson_pmf_grid(np.full(30_000, 0.8), 14)   # badly mis-located
        pit = randomized_pit(pmf, y, rng)
        assert pit_max_decile_dev(pit) > 0.05


# ── 5. market-blind contract ──────────────────────────────────────────────────

class TestMarketBlind:
    def test_no_price_column_in_contract(self):
        assert not (FORBIDDEN_FEATURES & set(NUMERIC_FEATURES))

    def test_design_raises_if_contract_gains_a_price_column(self, monkeypatch):
        """RED-proved live: injecting a price column into the contract must RAISE."""
        import betting_ml.scripts.batter_props_phase2_bakeoff as mod
        monkeypatch.setattr(mod, "NUMERIC_FEATURES",
                            mod.NUMERIC_FEATURES + ["p_over_consensus"])
        df = _tiny_frame()
        with pytest.raises(RuntimeError, match="market-blind"):
            mod.build_design(df)

    def test_design_matrix_builds_on_clean_contract(self):
        X, d = build_design(_tiny_frame())
        assert X.shape[0] == 6 and np.isfinite(X).all()


# ── 6. pooled-HR guard (prereg §9.1) ──────────────────────────────────────────

class TestPooledHRGuard:
    def test_pooled_hr_raises(self):
        with pytest.raises(RuntimeError, match="forbidden"):
            guard_no_pooled_hr_benchmark("batter_home_runs", "pooled")

    def test_per_fold_hr_passes_and_pooled_hits_passes(self):
        """Two-sided: the guard permits the two legitimate scopes, so the raise above is
        attributable to the pooled-HR combination alone."""
        guard_no_pooled_hr_benchmark("batter_home_runs", "per_fold")
        guard_no_pooled_hr_benchmark("batter_hits", "pooled")

    def test_report_path_carries_the_guard(self):
        """The guard must be CALLED on the report path, not merely exist (wired ≠ invoked —
        NF-C0e). Source-inspection on comment-stripped lines with a call-site regex."""
        import inspect
        import re
        import betting_ml.scripts.batter_props_phase2_bakeoff as mod
        src = inspect.getsource(mod.write_report)
        code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
        assert re.search(r"guard_no_pooled_hr_benchmark\s*\(", code), \
            "write_report no longer calls the pooled-HR guard"


# ── 7. the registered fold frame ──────────────────────────────────────────────

def _fold_frame() -> pd.DataFrame:
    """Synthetic frame spanning 2023H1..2026H2 with rows in every half."""
    rows = []
    for season, months in [(2023, range(5, 11)), (2024, range(4, 10)),
                           (2025, range(4, 10)), (2026, range(4, 9))]:
        for m in months:
            for day in (5, 20):
                rows.append({"game_date": pd.Timestamp(season, m, day), "season": season})
    df = pd.DataFrame(rows)
    df["y_actual"] = 1.0
    return df


class TestFoldFrame:
    def test_six_registered_folds(self):
        folds = make_folds(_fold_frame())
        assert [f["fold"] for f in folds] == EVAL_FOLDS
        assert len(folds) == 6

    def test_expanding_and_embargoed(self):
        df = _fold_frame()
        dates = pd.to_datetime(df["game_date"])
        for f in make_folds(df):
            tr, ev = dates[f["train"]], dates[f["eval"]]
            assert tr.max() < ev.min()
            # the embargo strictly removes the 10-day window before the eval start
            assert (ev.min() - tr.max()).days > 10

    def test_2026H2_rows_land_in_no_fold(self):
        """2026H2 exists in the substrate (in-progress season) and is not a registered fold;
        it must appear on NEITHER side of any fold."""
        df = _fold_frame()
        labels = half_label(df["game_date"], df["season"])
        h2_2026 = (labels == "2026H2").to_numpy()
        assert h2_2026.sum() > 0, "fixture must actually contain 2026H2 rows"
        for f in make_folds(df):
            assert not (f["train"] & h2_2026).any()
            assert not (f["eval"] & h2_2026).any()

    def test_missing_registered_fold_raises(self):
        """A substrate that lost a registered fold must REFUSE, not silently skip (a fold
        that did not run is not a fold that passed — NF1.7 (a))."""
        df = _fold_frame()
        df = df[half_label(df["game_date"], df["season"]) != "2024H2"]
        with pytest.raises(RuntimeError, match="zero rows"):
            make_folds(df)


# ── 8. DSR-CONV wiring ────────────────────────────────────────────────────────

class TestDSRConvWiring:
    def test_degenerates_reach_dsr_gate_as_declared_arms(self):
        """The run_market source must pass DEGENERATE_ARMS to dsr_gate (call-site regex on
        comment-stripped source; a grep on the constant's DEFINITION would be vacuous)."""
        import inspect
        import betting_ml.scripts.batter_props_phase2_bakeoff as mod
        src = inspect.getsource(mod.run_market)
        code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
        assert "degenerate_arms=DEGENERATE_ARMS" in code
        assert DEGENERATE_ARMS == ["degenerate_zero", "degenerate_marginal"]

    def test_dsr_gate_excludes_degenerates_from_v(self):
        """End-to-end: with a declared degenerate in the field, the binding figure is the
        degenerate-excluded one and n_trials keeps the full count."""
        from betting_ml.scripts.e7_9_train_serve_consistency import dsr_gate
        rng = np.random.default_rng(5)
        folds = 6
        fold_scores = {
            "foil": list(1.00 + 0.01 * rng.standard_normal(folds)),
            "winner": list(0.90 + 0.01 * rng.standard_normal(folds)),
            "other": list(0.97 + 0.01 * rng.standard_normal(folds)),
            "degenerate_zero": list(1.50 + 0.01 * rng.standard_normal(folds)),
        }
        out = dsr_gate(fold_scores, incumbent_arm="foil", leader_arm="winner",
                       n_trials=4, degenerate_arms=["degenerate_zero"])
        assert out["available"]
        assert out["binds"] == "degenerate_excluded_whole_field"
        assert out["n_trials"] == 4
        assert out["declared_degenerate_arms"] == ["degenerate_zero"]


def _tiny_frame() -> pd.DataFrame:
    """Minimal frame carrying the full feature contract (some NaNs to exercise imputation)."""
    n = 6
    rng = np.random.default_rng(7)
    df = pd.DataFrame({c: rng.uniform(0.1, 1.0, n) for c in NUMERIC_FEATURES})
    df.loc[0, "eb_woba"] = np.nan
    df["batter_hand"] = ["L", "R", "S", "R", "L", "R"]
    df["p_over_consensus"] = 0.55  # present on the frame, must never be READ by the design
    return df
