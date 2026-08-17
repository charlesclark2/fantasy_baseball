"""MH2.8 guards — the pre-registered constants, and the claims that are MEASURED not asserted.

Fast-gate safe: imports only from `betting_ml`, never `pipeline` (E11.23), and does no IO.

⚠️ **Each clause here is written so that it can FAIL.** A guard that cannot fail is the
NF1.7 (a) / INC-38 / NF-D17 vacuous-guard class, and this file's clauses were each RED-proven
against deliberately-broken source before being trusted (see `test_mh2_8_red_proof.py`).
"""
from __future__ import annotations

import numpy as np
import pytest

from betting_ml.scripts import mh2_8_skew_predictive as M


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registered constants (LOCK 1 … LOCK 10)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_field_is_the_declared_eight_and_nothing_was_added_after_the_fact():
    assert M.MH28_FIELD == M.MH28_ANCHORS + M.MH28_CANDIDATES
    assert len(M.MH28_FIELD) == 8
    assert len(set(M.MH28_FIELD)) == 8
    assert M.MH28_INCUMBENT_ARM in M.MH28_ANCHORS
    assert M.MH28_MATCHED_FOIL in M.MH28_ANCHORS
    assert M.MH28_NIHILIST in M.MH28_ANCHORS


def test_the_field_has_at_least_three_skew_capable_candidates():
    """The story's own bar: ≥3 skew-capable predictives beside the symmetric-Normal incumbent."""
    assert len(M.MH28_CANDIDATES) >= 3
    assert M.MH28_INCUMBENT_ARM not in M.MH28_CANDIDATES


def test_the_diagnostics_are_never_trials():
    """MH2.1 (a): an arm that SEES the target drives `V`, so the anchor that POLICES the gate would
    silently SET its bar. Diagnostics must be disjoint from the field."""
    assert not set(M.MH28_DIAGNOSTICS) & set(M.MH28_FIELD)


def test_the_degenerates_are_declared_in_advance_and_are_in_the_field():
    """DSR-CONV is forward-only: a degenerate stays in `n_trials` and leaves `V`, and it only ever
    qualifies BY DESIGN. A degenerate named outside the declared field would be a post-hoc trim."""
    assert set(M.MH28_DEGENERATES) <= set(M.MH28_FIELD)
    assert M.MH28_NIHILIST in M.MH28_DEGENERATES


def test_the_meaningful_effects_are_the_pre_registered_values():
    assert M.MH28_MEANINGFUL_PIT_MDD_GAIN == 0.012
    assert M.MH28_MEANINGFUL_P_OVER_GAP == 0.020
    assert M.MH28_CRPS_TOLERANCE == 0.020


def test_the_coverage_bars_are_floors_never_tightened_above_nominal():
    """NF1.8 (a): never tighten a coverage floor above nominal 'for safety' — every notch above
    nominal moves the eligible set toward the `max_width` degenerate."""
    assert M.MH28_COV80_FLOOR < 0.80
    assert M.MH28_COV50_FLOOR < 0.50


def test_the_primaries_are_the_two_pre_registered_statistics():
    assert M.MH28_PRIMARIES == ("pit_mdd", "p_over_gap")


def test_the_gates_are_the_programs_standing_bars():
    assert M.PBO_MAX == 0.2
    assert M.DSR_MIN_CONF == 0.95
    assert M.BH_Q == 0.05


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 1b — the "provable no-op" claim is MEASURED against the real contract, never asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_skipped_stuff_plus_swap_touches_no_contract_column():
    """⭐ LOCK 1b's load-bearing claim, checked mechanically.

    The pre-registration justifies skipping `_swap_stuff_plus_deleaked` on the grounds that it
    rewrites NO column of the 13-column served contract. That is a claim about data, and a claim
    about data stated only in prose is the class of thing this repo keeps getting wrong — so it is
    measured here against the contract file the harness actually reads.
    """
    from betting_ml.scripts.e7_9_train_serve_consistency import SERVED_CONTRACTS, _read_contract

    contract = set(_read_contract(SERVED_CONTRACTS[(M.TARGET, M.TIER)]))
    assert contract, "the served contract must be non-empty or this guard passes on nothing"
    touched = {f"{side}_{suffix}"
               for side in ("home", "away") for suffix in M.MH28_STUFF_SWAP_SUFFIXES}
    assert not (contract & touched), (
        "LOCK 1b's 'provable no-op' is FALSE — the Stuff+ de-leak swap touches contract "
        f"column(s) {sorted(contract & touched)}; the deviation would then need a different "
        "justification, not a different sentence."
    )


def test_the_deleak_swaps_are_declared_off_not_silently_off():
    assert M.MH28_APPLY_DELEAK_SWAPS is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ The α = 0 stationary point — the defect that would have produced a clean FALSE NULL
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_multi_start_straddles_zero_on_both_sides():
    """The Azzalini skew-normal's profile likelihood is FLAT at α = 0, so a single start there
    reports α̂ = 0 with `success=True` and never moves. Seeds must exist on BOTH sides, or the
    estimator is one-sided and can only ever find skew of one sign."""
    assert any(a < 0 for a in M.ALPHA_STARTS)
    assert any(a > 0 for a in M.ALPHA_STARTS)
    assert 0.0 not in M.ALPHA_STARTS


@pytest.mark.parametrize("true_alpha", [0.0, 2.5, -2.5])
def test_the_shape_fit_recovers_a_known_skew_and_does_not_invent_one(true_alpha):
    """⭐ The guard that would have caught the false null.

    On data drawn from a KNOWN skew-normal the fit must recover the sign and rough magnitude; on
    symmetric data it must return ≈ 0. Without the multi-start this returns 0.000 for every case —
    which reads, downstream, as 'no skew arm helps' with every gate green.
    """
    rng = np.random.default_rng(11)
    n = 3000
    mu = rng.normal(9.0, 0.5, n)
    sg = np.full(n, 4.4)
    y = np.round(M.SkewNormalPred(mu, sg, true_alpha).ppf(rng.uniform(size=n)))
    fit = M.fit_shape_recal(mu, sg, y, allow_skew=True)
    if true_alpha == 0.0:
        assert abs(fit["alpha"]) < 1.0
    else:
        assert np.sign(fit["alpha"]) == np.sign(true_alpha)
        assert abs(fit["alpha"] - true_alpha) < 1.5


def test_the_matched_foil_is_the_same_machinery_with_alpha_clamped():
    """NF-D15 g′: a separately-written foil could differ in an optimiser, a bound or a start, and
    then the paired delta would no longer isolate SKEW. One function, one clamp."""
    rng = np.random.default_rng(3)
    mu, sg = rng.normal(9, 0.4, 800), np.full(800, 4.4)
    y = np.round(M.SkewNormalPred(mu, sg, 3.0).ppf(rng.uniform(size=800)))
    assert M.fit_shape_recal(mu, sg, y, allow_skew=False)["alpha"] == 0.0
    assert M.fit_shape_recal(mu, sg, y, allow_skew=True)["alpha"] != 0.0


def test_the_skew_normal_at_alpha_zero_is_exactly_the_normal():
    """`skewnorm_recal` NESTS `normal_recal`. If it did not, clause 5's paired delta would be
    measuring the parameterisation rather than the skew."""
    mu, sg = np.array([9.0, 8.0]), np.array([4.4, 4.0])
    x = np.array([7.5, 10.5])
    assert np.allclose(M.SkewNormalPred(mu, sg, 0.0).cdf(x), M.NormalPred(mu, sg).cdf(x))


def test_the_moment_match_holds_the_mean_and_sd_so_only_the_shape_moves():
    """The whole point of the (mean, sd, α) parameterisation: α changes SHAPE ONLY."""
    mu, sg = np.full(3, 9.0), np.full(3, 4.4)
    p = M.SkewNormalPred(mu, sg, 4.0)
    assert np.allclose(p.mean(), mu, atol=0.02)
    assert np.allclose(p.sd(), sg, rtol=0.02)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The metric is two-sided, and the nihilist really does win the marginal primaries
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_nihilist_wins_the_primaries_which_is_why_the_sharpness_constraint_exists():
    """⭐ LOCK 4, measured rather than reasoned about.

    A feature-blind predictive has a flat PIT by construction. If this ever stopped being true the
    `climo` arm would no longer be testing anything, and the ship rule's clause 1 would be a
    decoration rather than an inversion check.
    """
    rng = np.random.default_rng(5)
    n = 8000
    # a decisively right-skewed target, exactly the shape MH2.6 found in the real residuals
    y = np.round(rng.gamma(shape=4.0, scale=2.25, size=n))
    climo = M.ClimoPred(y, n)
    # the mis-shaped predictive under test: a symmetric Normal matched on MEAN and SD — i.e. it has
    # the level and the scale exactly right and only the SHAPE wrong, which is the incumbent's defect
    bad = M.NormalPred(np.full(n, y.mean()), np.full(n, y.std()))
    u_c = M.randomized_pit(y, climo, np.random.default_rng(1))
    u_b = M.randomized_pit(y, bad, np.random.default_rng(1))
    assert M.pit_mdd(u_c) < M.pit_mdd(u_b), (
        "the nihilist no longer wins the flatness primary — clause 1 would be vacuous"
    )


def test_the_nihilist_loses_the_sharpness_constraint_on_conditional_data():
    """The other half of LOCK 4: the nihilist wins the MARGINAL primaries and must LOSE CRPS as soon
    as the features carry real conditional information — which is what makes the constraint bite."""
    rng = np.random.default_rng(6)
    n = 6000
    mu = rng.normal(9.0, 1.6, n)                      # a genuinely informative conditional mean
    y = np.round(np.maximum(rng.normal(mu, 3.5), 0))
    conditional = M.NormalPred(mu, np.full(n, 3.5))
    climo = M.ClimoPred(y, n)
    assert np.mean(climo.crps(y)) > np.mean(conditional.crps(y)), (
        "the nihilist no longer loses CRPS — the sharpness constraint would stop nothing"
    )


def test_the_pit_of_a_correctly_specified_predictive_is_uniform():
    rng = np.random.default_rng(9)
    n = 20000
    mu, sg = np.full(n, 9.0), np.full(n, 4.4)
    y = np.round(M.NormalPred(mu, sg).ppf(rng.uniform(size=n)))
    u = M.randomized_pit(y, M.NormalPred(mu, sg), rng)
    assert M.pit_mdd(u) < 0.02


def test_the_construction_floor_is_a_construction_not_a_fit():
    """Nothing may beat it. It must therefore be positive, ordered, and shrink with n."""
    small = M.uniform_mdd_null(200, 300, 42)
    big = M.uniform_mdd_null(4000, 300, 42)
    assert 0 < small["p001"] < small["median"] < small["p975"]
    assert big["median"] < small["median"]


def test_the_crps_grid_estimator_agrees_with_the_normal_closed_form():
    """CRPS is computed IDENTICALLY for every arm on one shared grid, so a per-arm mix of closed
    forms and approximations cannot put a systematic bias inside a non-inferiority constraint."""
    rng = np.random.default_rng(4)
    n = 500
    mu, sg = rng.normal(9, 0.5, n), np.full(n, 4.4)
    p = M.NormalPred(mu, sg)
    y = np.round(p.ppf(rng.uniform(size=n)))
    assert np.allclose(np.mean(p.crps(y)), np.mean(p.crps_closed_form(y)), atol=1e-3)


def test_the_mc_p_floor_is_non_degenerate():
    """A p-value that cannot reach its own BH cutoff is a vacuous test (NF1.7 (a))."""
    need = M.min_null_reps(len(M.MH28_PRIMARIES) + 2)
    assert M.MH28_NULL_REPS >= need
    assert 1.0 / (M.MH28_NULL_REPS + 1) < M.BH_Q / (len(M.MH28_PRIMARIES) + 2)


def test_the_mc_pvalue_can_never_return_a_vacuous_zero():
    draws = np.zeros(100)
    assert M.mc_pvalue(draws, 99.0) > 0.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 9 — the served asymmetry, and LOCK 10 — the ship rule
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_learned_families_are_declared_served_unvalidatable():
    """A learned family would need a re-score from a matrix that is NOT point-in-time, which is the
    exact substitution MH2.1's rollback punished ⇒ it cannot ship."""
    for arm in ("ngb_lognormal", "ngb_gamma", "lgbm_quantile"):
        assert arm not in M.MH28_SERVED_EVALUABLE
    for arm in ("incumbent", "normal_recal", "skewnorm_recal", "overskew"):
        assert arm in M.MH28_SERVED_EVALUABLE


def test_a_served_unvalidatable_arm_can_never_ship():
    """⭐ Clause 10, isolated. Every OTHER clause is satisfied in this fixture, so ONLY the served
    clause can decide — which is what makes this a test of clause 10 rather than a restatement of
    the ship rule (NF-D17: a fixture that trips several clauses proves none of them)."""
    arm = "lgbm_quantile"
    assert arm not in M.MH28_SERVED_EVALUABLE
    R = _all_clauses_passing_fixture(winner=arm)
    got = M._clauses(arm, R)
    passing = {k: v for k, v in got.items() if k != "10_served_gate"}
    assert all(v is not False for v in passing.values()), (
        f"the fixture must satisfy every OTHER clause or this proves nothing: {passing}")
    assert got["10_served_gate"] is False


def test_the_nihilist_clearing_the_rule_reports_metric_inverted_not_a_ship():
    """⭐ Clause 1, isolated. If the constraints ever failed to stop a feature-blind predictive,
    the run must say the METRIC is what it measured — never hand the leaderboard a winner."""
    R = _all_clauses_passing_fixture(winner=M.MH28_NIHILIST, served_ok=True)
    d = M._decide(R)
    assert d["nihilist_cleared_the_rule"] is True
    assert d["verdict"] == "METRIC_INVERTED"
    assert d["shippable_arms"] == []


def test_an_arm_below_the_construction_floor_halts():
    R = _all_clauses_passing_fixture(winner="skewnorm_recal", served_ok=True)
    R["inversion_arms"] = ["skewnorm_recal"]
    assert M._decide(R)["verdict"] == "HALT_METRIC_INVERSION"


def test_the_default_verdict_is_incumbent_stands():
    """Nothing ships by accident: with no arm clearing, the verdict is the pre-registered default."""
    R = _all_clauses_passing_fixture(winner=None)
    assert M._decide(R)["verdict"] == "INCUMBENT_STANDS"


def test_promotion_is_deploy_held_and_the_landmines_are_carried():
    R = _all_clauses_passing_fixture(winner="skewnorm_recal", served_ok=True)
    assert M._decide(R)["deploy_held"] is True
    joined = " ".join(M.MH28_PROMOTION_LANDMINES)
    for token in ("model_version", "mart_clv_labeled_games", "COPY . .", "best_alpha"):
        assert token in joined


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The fixture
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _all_clauses_passing_fixture(*, winner: str | None, served_ok: bool = False) -> dict:
    """A results dict in which EVERY clause passes for `winner` except the one under test.

    NF-D17: a guard on an `and`-composed rule is vacuous unless its fixture satisfies every OTHER
    clause — otherwise a second clause is already refusing the fixture and deleting the clause you
    named changes nothing observable.
    """
    def arm(pit, gap, crps):
        return {"pit_mdd": pit, "p_over_gap": gap, "crps": crps, "cov80": 0.80, "cov50": 0.50,
                "p_over_stated": 0.5, "p_over_realized": 0.5, "z_skew": 0.0}

    pooled = {a: arm(0.050, 0.070, 2.55) for a in M.MH28_FIELD}
    pooled[M.MH28_INCUMBENT_ARM] = arm(0.050, 0.070, 2.55)
    pooled[M.MH28_MATCHED_FOIL] = arm(0.045, 0.060, 2.55)
    if winner:
        pooled[winner] = arm(0.010, 0.001, 2.54)

    served_arm = {"pit_mdd": 0.020, "p_over_gap": 0.001, "crps": 2.50,
                  "cov80": 0.80, "cov50": 0.50}
    served = {
        "arms": {M.MH28_INCUMBENT_ARM: {"pit_mdd": 0.042, "p_over_gap": 0.070, "crps": 2.53,
                                        "cov80": 0.79, "cov50": 0.47}},
        "mh2_6_null_band_pit_mdd": [0.0117, 0.0356],
        "at_posted_line": {"consensus": {
            "evaluable": True, "coverage": 0.99,
            M.MH28_INCUMBENT_ARM: {"p_over_gap": 0.056},
        }},
    }
    if winner and served_ok:
        served["arms"][winner] = served_arm
        served["at_posted_line"]["consensus"][winner] = {"p_over_gap": 0.001}

    return {
        "pooled": pooled,
        "served": served,
        "inversion_arms": [],
        "pbo": 0.05,
        "dsr": {"dsr": 0.99, "var_trials_sr": 0.1},
        "fold_consistency": {"passed": True, "wins": 8, "required": 6},
        "fold_primary": {a: [0.05] * 8 for a in M.MH28_FIELD},
        "n_folds": 8, "n_arms": len(M.MH28_FIELD),
        "leader": winner or "skewnorm_recal",
    }
