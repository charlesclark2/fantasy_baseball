"""MH2.8 RED proof — every load-bearing guard is shown to FAIL on deliberately-broken source.

A guard that cannot fail is not a guard (NF1.7 (a) / INC-38 / NF-D17). This file breaks one thing at
a time and asserts the matching clause goes RED.

Three traps this file is written to avoid, each of which has produced a FALSE "the guard caught it"
in this repo before:

1. ⭐ **The mutation must be PROVEN to have landed** (E11.24 #682). A shell-quoting bug once meant
   the breaks never applied and the suite passed on UNCHANGED source, which reads as a finding. Here
   the mutation is applied IN-PROCESS on the module object and the changed attribute is asserted
   before the clause is invoked.
2. ⭐ **`pytest.raises` raises `Failed`, which derives from `BaseException`** (NF-W6c), so an outer
   `except Exception` lets a deliberate break sail straight through. Nothing here wraps pytest.
3. ⭐ **It must run under the PROJECT interpreter** (NF-INFRA1) — a bare `python3` with no pytest
   turns "no pytest installed" into a non-zero exit that reads as a caught break. This file is a
   normal pytest module, so it runs under whatever runs the suite.

⚠️ It is marked `slow` so it stays off the fast gate, and it is deliberately CHEAP: no IO, no fits.
"""
from __future__ import annotations

import numpy as np
import pytest

from betting_ml.scripts import mh2_8_skew_predictive as M
from betting_ml.tests import test_mh2_8_skew_predictive as G

pytestmark = pytest.mark.slow


def _fails(fn, *args) -> bool:
    """Did the guard REJECT? An `AssertionError` is the reject; anything else is a broken proof."""
    try:
        fn(*args)
    except AssertionError:
        return True
    return False


def test_red_the_alpha_multi_start_guard_fires_when_the_multi_start_is_removed(monkeypatch):
    """⭐ THE ONE THAT MATTERS. Restoring the single α = 0 start reproduces the exact defect this
    harness shipped with on its first smoke run: α̂ = 0.000 in every fold, `success=True`, and a
    study that reports "no skew arm helps" with every gate green."""
    assert M.ALPHA_STARTS, "pre-condition: the multi-start must exist to be removed"
    monkeypatch.setattr(M, "ALPHA_STARTS", ())
    assert M.ALPHA_STARTS == (), "the mutation did NOT land — this proof would be vacuous"

    # the estimator now genuinely returns ~0 on decisively skewed data ...
    rng = np.random.default_rng(11)
    n = 3000
    mu, sg = rng.normal(9.0, 0.5, n), np.full(n, 4.4)
    y = np.round(M.SkewNormalPred(mu, sg, 2.5).ppf(rng.uniform(size=n)))
    assert abs(M.fit_shape_recal(mu, sg, y, allow_skew=True)["alpha"]) < 0.05, (
        "the broken estimator must actually be broken, or the proof below proves nothing")
    # ... and the guard catches it.
    assert _fails(G.test_the_shape_fit_recovers_a_known_skew_and_does_not_invent_one, 2.5)


def test_red_the_straddle_guard_fires_on_a_one_sided_multi_start(monkeypatch):
    """A one-sided start set can only ever find skew of one sign — silently, and in the direction
    the author expected. That is the shape of an assumption dressed as a measurement."""
    monkeypatch.setattr(M, "ALPHA_STARTS", (0.5, 2.0, 4.0))
    assert all(a > 0 for a in M.ALPHA_STARTS), "the mutation did NOT land"
    assert _fails(G.test_the_multi_start_straddles_zero_on_both_sides)


def test_red_the_contract_no_op_guard_fires_if_the_swap_touched_the_contract(monkeypatch):
    """LOCK 1b's justification is a claim about DATA. If the Stuff+ swap ever touched a contract
    column the guard must refuse — the deviation would then need a different justification, not a
    different sentence."""
    from betting_ml.scripts.e7_9_train_serve_consistency import SERVED_CONTRACTS, _read_contract

    contract = _read_contract(SERVED_CONTRACTS[(M.TARGET, M.TIER)])
    assert contract, "pre-condition: the contract must be readable"
    victim = contract[0]
    side, _, suffix = victim.partition("_")
    monkeypatch.setattr(M, "MH28_STUFF_SWAP_SUFFIXES", (suffix,))
    assert M.MH28_STUFF_SWAP_SUFFIXES == (suffix,), "the mutation did NOT land"
    assert _fails(G.test_the_skipped_stuff_plus_swap_touches_no_contract_column)


def test_red_the_served_asymmetry_guard_fires_if_a_learned_family_is_declared_servable(monkeypatch):
    """Letting a learned family into the served set is exactly MH2.1's rollback substitution — a
    CEILING scored as if it were the served number."""
    monkeypatch.setattr(M, "MH28_SERVED_EVALUABLE",
                        M.MH28_SERVED_EVALUABLE + ("lgbm_quantile",))
    assert "lgbm_quantile" in M.MH28_SERVED_EVALUABLE, "the mutation did NOT land"
    assert _fails(G.test_the_learned_families_are_declared_served_unvalidatable)


def test_red_the_clause_10_isolation_guard_fires_when_the_served_clause_is_deleted(monkeypatch):
    """⭐ NF-D17's lesson, applied to this harness's own `and`-gate: the clause-10 fixture satisfies
    every OTHER clause, so deleting clause 10 must be OBSERVABLE. If it is not, the guard was being
    satisfied by a different clause and proved nothing about clause 10."""
    real = M._clauses

    def no_clause_10(arm, R):
        out = dict(real(arm, R))
        out["10_served_gate"] = True             # the deletion, expressed as an always-pass
        return out

    monkeypatch.setattr(M, "_clauses", no_clause_10)
    probe = M._clauses("lgbm_quantile", G._all_clauses_passing_fixture(winner="lgbm_quantile"))
    assert probe["10_served_gate"] is True, "the mutation did NOT land"
    assert _fails(G.test_a_served_unvalidatable_arm_can_never_ship)


def test_red_the_inversion_guard_fires_when_the_nihilist_check_is_disabled(monkeypatch):
    """If clause 1 stopped reading the nihilist, a feature-blind predictive could be handed to the
    operator as a winner — the failure this whole metric design exists to prevent."""
    # The break models the DESIGN FLAW this harness had before the fix: folding the deployability
    # clause into the inversion check. The nihilist is SERVED_UNVALIDATABLE by construction, so
    # clause 10 alone would then "stop" it — and the check would pass for a reason that has nothing
    # to do with the metric, i.e. it would be satisfied without ever testing anything.
    monkeypatch.setattr(M, "MH28_INVERSION_EXCLUDED_CLAUSES", ("1_nihilist_did_not_clear",))
    assert "10_served_gate" not in M.MH28_INVERSION_EXCLUDED_CLAUSES, "the mutation did NOT land"
    assert _fails(G.test_the_nihilist_clearing_the_rule_reports_metric_inverted_not_a_ship)


def test_red_the_coverage_floor_guard_fires_if_a_floor_is_tightened_above_nominal(monkeypatch):
    """NF1.8 (a): every notch above nominal moves the eligible set toward the `max_width`
    degenerate. A floor tightened 'for safety' is the coverage-as-a-target inversion."""
    monkeypatch.setattr(M, "MH28_COV80_FLOOR", 0.85)
    assert M.MH28_COV80_FLOOR == 0.85, "the mutation did NOT land"
    assert _fails(G.test_the_coverage_bars_are_floors_never_tightened_above_nominal)


def test_red_the_mc_p_floor_guard_fires_on_too_few_reps(monkeypatch):
    """A p-value that cannot reach its own BH cutoff is a vacuous test."""
    monkeypatch.setattr(M, "MH28_NULL_REPS", 10)
    assert M.MH28_NULL_REPS == 10, "the mutation did NOT land"
    assert _fails(G.test_the_mc_p_floor_is_non_degenerate)


def test_red_the_nesting_guard_fires_if_the_skew_normal_stops_nesting_the_normal(monkeypatch):
    """`skewnorm_recal` must NEST `normal_recal`, or clause 5's paired delta measures the
    parameterisation rather than the skew (NF-D15 g′)."""
    real = M.SkewNormalPred

    class Broken(real):
        def __post_init__(self):
            super().__post_init__()
            self.omega = self.omega * 1.10        # a scale drift that breaks the nesting

    monkeypatch.setattr(M, "SkewNormalPred", Broken)
    probe = M.SkewNormalPred(np.array([9.0]), np.array([4.4]), 0.0)
    assert not np.allclose(probe.omega, 4.4), "the mutation did NOT land"
    assert _fails(G.test_the_skew_normal_at_alpha_zero_is_exactly_the_normal)


def test_red_the_degenerate_declaration_guard_fires_on_an_undeclared_degenerate(monkeypatch):
    """DSR-CONV is forward-only: a degenerate named outside the declared field is a post-hoc trim,
    which is the second layer of the selection bias DSR exists to deflate (MH2.2)."""
    monkeypatch.setattr(M, "MH28_DEGENERATES", ("climo", "some_arm_invented_after_the_run"))
    assert "some_arm_invented_after_the_run" in M.MH28_DEGENERATES, "the mutation did NOT land"
    assert _fails(G.test_the_degenerates_are_declared_in_advance_and_are_in_the_field)


def test_red_the_field_size_guard_fires_if_an_arm_is_dropped_after_the_fact(monkeypatch):
    monkeypatch.setattr(M, "MH28_CANDIDATES", M.MH28_CANDIDATES[:2])
    assert len(M.MH28_CANDIDATES) == 2, "the mutation did NOT land"
    assert _fails(G.test_the_field_is_the_declared_eight_and_nothing_was_added_after_the_fact)
    assert _fails(G.test_the_field_has_at_least_three_skew_capable_candidates)


def test_the_red_proof_is_not_itself_vacuous():
    """⭐ The proof-of-the-proof: with NOTHING broken, every guard above must PASS.

    Without this, a `_fails` helper that always returned True — or a suite whose guards were all
    already red for an unrelated reason — would report a clean sweep of caught breaks.
    """
    for fn in (G.test_the_multi_start_straddles_zero_on_both_sides,
               G.test_the_skipped_stuff_plus_swap_touches_no_contract_column,
               G.test_the_learned_families_are_declared_served_unvalidatable,
               G.test_a_served_unvalidatable_arm_can_never_ship,
               G.test_the_nihilist_clearing_the_rule_reports_metric_inverted_not_a_ship,
               G.test_the_coverage_bars_are_floors_never_tightened_above_nominal,
               G.test_the_mc_p_floor_is_non_degenerate,
               G.test_the_skew_normal_at_alpha_zero_is_exactly_the_normal,
               G.test_the_degenerates_are_declared_in_advance_and_are_in_the_field,
               G.test_the_field_is_the_declared_eight_and_nothing_was_added_after_the_fact):
        assert not _fails(fn), f"{fn.__name__} is red on UNBROKEN source — the proof is unsound"
    assert not _fails(G.test_the_shape_fit_recovers_a_known_skew_and_does_not_invent_one, 2.5)
