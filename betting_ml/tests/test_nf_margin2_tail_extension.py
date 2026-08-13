"""Guards for NF-MARGIN2 — tail-extension-ONLY recalibration vs the champion (1-arm family).

Fast-gate, no IO: everything here exercises the PURE module
(`quant_sports_intel_models.football.nfl.fantasy.margin2_tail_extension`); the runner is never
imported (it pulls the lake-reading story runners).

Discipline inherited from the NF-MARGIN1/NF-W3/W4/W5 suites:
  · every gate clause has an ISOLATING fixture — a base selection where every clause passes and
    a per-clause mutation that flips exactly that clause (NF-D17);
  · the structural invariant behind the declared-inactive clauses (within-grid byte identity) is
    PROVED, and so is the blindness of the 39-level PIT instrument — the reason
    `randomized_pit_levels` exists;
  · the tail-mass gate statistic is proved TWO-SIDED (an over-extended tail fails it from the
    other side) and proved to live at the EVAL-grid ends (the champion-grid-end statistic is
    proved ARM-INVARIANT — the NF-D20 (g⁗) trap this story caught at design time);
  · fail-closed clauses are RED-proved (NF1.7 (a)).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import margin2_tail_extension as M2
from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_RNG = np.random.default_rng(20260813)


def _bank(n: int = 200, loc: float = 10.0, scale: float = 5.0,
          rng: np.random.Generator | None = None) -> np.ndarray:
    """A monotone synthetic 39-level quantile bank: N(loc, scale) quantiles + row jitter."""
    rng = rng or _RNG
    from scipy.stats import norm
    base = norm.ppf(WP.Q_LEVELS, loc=loc, scale=scale)
    shift = rng.normal(0, 1, size=(n, 1))
    return np.sort(base[None, :] + shift, axis=1)


_TAIL = {"beta_hi": 3.0, "beta_lo": 1.0, "n_hi": 99, "n_lo": 99,
         "thin_hi": False, "thin_lo": False}


# ── Field + pre-registration ────────────────────────────────────────────────────────────────────
class TestFieldAndPreregistration:
    def test_the_field_is_one_arm_one_foil_by_declaration(self):
        assert M2.REAL_ARMS == ("tail_ext",)
        assert M2.FOILS == ("incumbent",)
        assert M2.eligible_labels() == ["tail_ext", "incumbent"]

    def test_anchors_never_enter_the_eligible_field(self):
        eligible = set(M2.eligible_labels())
        assert eligible.isdisjoint(M2.anchors())
        assert set(M2.anchors()) == {"zero_width", "max_width", "over_ext", "permuted_tail",
                                     "pooled_tail", "oracle__tail_ext", "matched_n__tail_ext"}

    def test_pbo_is_undefined_by_design_at_a_one_arm_family(self):
        """The NF-W4 Layer-B precedent: CSCV resamples a FIELD; one pre-registered contrast has
        no search to overfit — PBO must be declared UNDEFINED, never gated."""
        assert not GE.pbo_is_evaluable(len(M2.REAL_ARMS))
        assert "pbo_ok" not in M2.M2_STATISTICAL_CHECKS

    def test_fdr_is_one_position_keyed_family(self):
        assert len(M2.FDR_FAMILY) == len(M2.POSITIONS)
        assert all(k.startswith("margin2_tail_") for k in M2.FDR_FAMILY)

    def test_the_magnitude_degenerate_is_a_genuine_over_extension(self):
        assert M2.OVER_SCALE > 1.0

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        pre = Path(__file__).resolve().parents[2] / (
            "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
            "nf_margin2_preregistration.md")
        assert pre.exists(), "the narrative pre-registration must be committed before the run"
        text = pre.read_text()
        for token in ("tail_ext", "crps_q199", "MH2.2", "UNDEFINED", "deploy-held",
                      "best_alpha = 0", "ARM-INVARIANT", "0.005", "over_ext",
                      "randomized_pit_levels", "20260813"):
            assert token in text, f"pre-registration is missing `{token}`"

    def test_coverage_is_a_floor_never_a_target(self):
        """⛔ E2.1-r: no objective may reference |coverage − floor|. Source-inspected with
        comments stripped so prose can neither satisfy nor trip it (INC-38)."""
        src = Path(M2.__file__).read_text()
        code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
        assert not re.search(r"abs\([^)]*coverage[^)]*-\s*(0\.8|COVERAGE_FLOOR)", code)

    def test_seed_is_fresh_and_distinct_from_margin1(self):
        assert M2._SEED != MC._SEED


# ── The PIT instrument (levels-generalized) ─────────────────────────────────────────────────────
class TestPitInstrument:
    def test_reproduces_oa_randomized_pit_byte_for_byte_on_the_39_grid(self):
        """The no-op reproduction rule applied to the INSTRUMENT: on a 39-level bank with the
        same rng state, the generalized PIT must equal `OA.randomized_pit` exactly."""
        q39 = _bank(500)
        y = q39.mean(axis=1) + _RNG.normal(0, 6, 500)
        u_ref = OA.randomized_pit(q39, y, np.random.default_rng(99))
        u_new = M2.randomized_pit_levels(q39, y, np.random.default_rng(99), WP.Q_LEVELS)
        assert np.array_equal(u_ref, u_new)

    def test_refuses_mismatched_levels(self):
        with pytest.raises(ValueError, match="mismatched levels"):
            M2.randomized_pit_levels(_bank(5), np.zeros(5), _RNG, M2.EVAL_LEVELS)

    def test_the_39_level_instrument_is_blind_to_the_arm(self):
        """WHY `randomized_pit_levels` exists: the arm's champion-grid columns are byte-identical
        to the incumbent's, so the 39-level PIT of both is IDENTICAL — a flatness or tail check
        computed there is structurally inactive (NF-D20 (g⁗))."""
        q39 = _bank(300)
        y = q39.mean(axis=1) + _RNG.standard_t(3, 300) * 6
        inc = M2.build_bank_m2("incumbent", None, q39)
        arm = M2.build_bank_m2("tail_ext", _TAIL, q39)
        assert np.array_equal(arm[:, M2.IDX_Q39], inc[:, M2.IDX_Q39])
        u_inc = M2.randomized_pit_levels(inc[:, M2.IDX_Q39], y,
                                         np.random.default_rng(7), WP.Q_LEVELS)
        u_arm = M2.randomized_pit_levels(arm[:, M2.IDX_Q39], y,
                                         np.random.default_rng(7), WP.Q_LEVELS)
        assert np.array_equal(u_inc, u_arm)

    def test_champion_grid_tail_mass_is_arm_invariant_but_eval_grid_mass_is_not(self):
        """The design-time NF-D20 catch, proved: P(u beyond 0.025/0.975) cannot distinguish the
        arm from the incumbent; P(u beyond 0.005/0.995) can — the gate lives at the EVAL ends."""
        rng = np.random.default_rng(41)
        n = 8000
        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0  # fat-tailed reality
        # betas fit honestly on a calibration draw of the same law
        y_cal = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0
        tail = M2.fit_tail_betas(q39, y_cal)
        assert tail["beta_hi"] > 0 and tail["beta_lo"] > 0
        inc = M2.build_bank_m2("incumbent", None, q39)
        arm = M2.build_bank_m2("tail_ext", tail, q39)
        s_inc = M2.pit_stats_m2(M2.randomized_pit_levels(inc, y, np.random.default_rng(1)))
        s_arm = M2.pit_stats_m2(M2.randomized_pit_levels(arm, y, np.random.default_rng(1)))
        # champion-grid mass: identical BY CONSTRUCTION (the invariant statistic)
        assert s_inc["n_above_grid"] == s_arm["n_above_grid"]
        assert s_inc["n_below_grid"] == s_arm["n_below_grid"]
        # eval-grid mass: the incumbent piles beyond-mass into the end cells; the arm spreads it
        p_inc, p_arm = M2.pool_pit_stats_m2([s_inc]), M2.pool_pit_stats_m2([s_arm])
        assert p_inc["p_above_eval"] > 3 * M2.NOMINAL_EXTREME
        assert p_arm["p_above_eval"] < p_inc["p_above_eval"]
        assert M2.tail_mass_deviation(p_arm) < M2.tail_mass_deviation(p_inc)

    def test_tail_mass_deviation_is_two_sided(self):
        """An OVER-extended tail pushes beyond-eval mass BELOW nominal — the deviation must rise
        again (the gate fails from either side, E2.1-r)."""
        nominal = M2.NOMINAL_EXTREME
        perfect = {"p_below_eval": nominal, "p_above_eval": nominal}
        under = {"p_below_eval": 0.04, "p_above_eval": 0.04}       # flat/truncated
        over = {"p_below_eval": 0.0, "p_above_eval": 0.0}          # over-extended
        assert M2.tail_mass_deviation(perfect) == 0.0
        assert M2.tail_mass_deviation(under) > 0
        assert M2.tail_mass_deviation(over) > 0

    def test_pit_stats_m2_counts_the_eval_ends(self):
        u = np.concatenate([np.full(30, 0.001), np.full(20, 0.999), np.full(950, 0.5)])
        s = M2.pit_stats_m2(u)
        assert s["n_below_eval"] == 30 and s["n_above_eval"] == 20
        pooled = M2.pool_pit_stats_m2([s, s])
        assert pooled["p_below_eval"] == round(60 / 2000, 5)


# ── Constructions ───────────────────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_within_grid_byte_identity_holds_for_every_tail_family_label(self):
        q39 = _bank(80)
        inc = M2.build_bank_m2("incumbent", None, q39)
        for label, params in [("tail_ext", _TAIL), ("permuted_tail", _TAIL),
                              ("pooled_tail", _TAIL), ("over_ext", _TAIL),
                              ("oracle__tail_ext", _TAIL), ("matched_n__tail_ext", _TAIL)]:
            bank = M2.build_bank_m2(label, params, q39)
            M2.assert_within_grid_identity(bank, inc, label)  # must not raise
            assert not np.array_equal(bank, inc), (
                f"{label} must actually differ beyond the grid, else the identity check "
                f"passes on nothing (non-vacuity)")

    def test_identity_assert_fires_on_a_within_grid_modification(self):
        q39 = _bank(30)
        inc = M2.build_bank_m2("incumbent", None, q39)
        bad = M2.build_bank_m2("tail_ext", _TAIL, q39)
        mid = int(np.searchsorted(M2.EVAL_LEVELS, 0.5))
        bad[:, mid] += 0.01
        with pytest.raises(ValueError, match="tail-ONLY"):
            M2.assert_within_grid_identity(bad, inc, "tail_ext")

    def test_declared_inactive_metrics_are_identically_zero_and_the_primary_moves(self):
        """The construction facts behind §4: Winkler-80 and coverage(50/80/95) deltas are exactly
        zero; crps_q199 and coverage_99 move — the ONLY active channels."""
        rng = np.random.default_rng(42)
        n = 6000
        q39 = _bank(n, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0
        tail = M2.fit_tail_betas(q39, q39.mean(axis=1) + rng.standard_t(3, n) * 4.0)
        s_inc = M2.score_bank(M2.build_bank_m2("incumbent", None, q39), y)
        s_arm = M2.score_bank(M2.build_bank_m2("tail_ext", tail, q39), y)
        for m in ("winkler_80", "coverage_50", "coverage_80", "coverage_95"):
            assert s_inc[m] == s_arm[m], f"{m} must be identical by construction"
        assert s_inc["crps_q199"] != s_arm["crps_q199"]
        assert s_arm["coverage_99"] > s_inc["coverage_99"]
        assert s_arm["crps_q199"] < s_inc["crps_q199"], (
            "on fat-tailed reality the honest tail must win the primary — the channel the "
            "199-level metric exists to see")

    def test_scale_tail_scales_and_keeps_thin_sides_zero(self):
        scaled = M2.scale_tail({"beta_hi": 2.0, "beta_lo": 0.0, "n_hi": 50, "n_lo": 3,
                                "thin_hi": False, "thin_lo": True})
        assert scaled["beta_hi"] == 2.0 * M2.OVER_SCALE
        assert scaled["beta_lo"] == 0.0, "the degenerate cannot invent a tail the fit refused"

    def test_over_ext_extends_strictly_beyond_the_arm_where_the_tail_engages(self):
        q39 = _bank(20)
        arm = M2.build_bank_m2("tail_ext", _TAIL, q39)
        over = M2.build_bank_m2("over_ext", _TAIL, q39)
        above = M2.EVAL_LEVELS > WP.Q_LEVELS[-1]
        assert above.any()
        assert (over[:, above] > arm[:, above]).all()

    def test_unknown_label_raises(self):
        with pytest.raises(ValueError, match="unknown construction"):
            M2.build_bank_m2("mystery_arm", None, _bank(3))

    def test_over_extension_loses_to_the_honest_fit_on_matched_reality(self):
        """The NF-D20 magnitude degenerate must be BEATABLE: when reality is CONSISTENT with the
        bank within the grid (exceeds q975 at its nominal 2.5%) and carries an exponential
        excess, the fitted betas approximate truth and betas × OVER_SCALE score worse. (A first
        fixture drew 10% exceedances — inconsistent with the bank's own within-grid claim — and
        over-extension legitimately WON there; the degenerate is a real probe, not decoration.)"""
        rng = np.random.default_rng(43)
        n = 12000
        beta_true = 3.0

        def _draw(q39: np.ndarray) -> np.ndarray:
            u = rng.random(len(q39))
            y = np.array([np.interp(ui, WP.Q_LEVELS, row) for ui, row in zip(u, q39)])
            hi, lo = u > WP.Q_LEVELS[-1], u < WP.Q_LEVELS[0]
            y[hi] = q39[hi, -1] + rng.exponential(beta_true, int(hi.sum()))
            y[lo] = q39[lo, 0] - rng.exponential(beta_true, int(lo.sum()))
            return y

        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y = _draw(q39)
        tail = M2.fit_tail_betas(q39, _draw(q39))
        assert abs(tail["beta_hi"] - beta_true) < 0.6, "fixture must recover the true scale"
        s_arm = M2.score_bank(M2.build_bank_m2("tail_ext", tail, q39), y)["crps_q199"]
        s_over = M2.score_bank(M2.build_bank_m2("over_ext", tail, q39), y)["crps_q199"]
        assert s_over > s_arm


# ── Gate clauses (isolating fixtures — NF-D17) ──────────────────────────────────────────────────
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"passes": True},
        "dsr": 0.99,
        "anchors": {"zero_width_loses": True, "max_width_loses": True,
                    "over_ext_loses": True,
                    "permuted_not_significantly_better": True,
                    "oracle_floor_respected_at_matched_n": True},
        "coverage": {"blocking_shortfall": False},
        "calibration": {"tail_mass_delta_vs_incumbent": 0.01},
    }


class TestGateClauses:
    def test_the_passing_fixture_ships(self):
        gate = M2.compose_gate_margin2(_passing_sel(), True)
        assert gate["ship"], gate["checks"]

    def test_pbo_is_absent_from_the_gate(self):
        checks = M2.compose_gate_margin2(_passing_sel(), True)["checks"]
        assert "pbo_ok" not in checks, "PBO is UNDEFINED by design at a 1-arm family (§6)"

    @pytest.mark.parametrize("mutate,expect_check", [
        (lambda s: s.update(beats_foil=False), "beats_champion"),
        (lambda s: s["fold_clause"].update(passes=False), "fold_consistency"),
        (lambda s: s.update(dsr=0.5), "dsr_ok"),
        (lambda s: s.update(dsr=None), "dsr_ok"),
        (lambda s: s["coverage"].update(blocking_shortfall=True), "coverage_floor_ok"),
        (lambda s: s["anchors"].update(zero_width_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(max_width_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(over_ext_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(permuted_not_significantly_better=False),
         "permutation_not_better"),
        (lambda s: s["anchors"].update(oracle_floor_respected_at_matched_n=False),
         "oracle_floor_respected"),
        (lambda s: s["calibration"].update(tail_mass_delta_vs_incumbent=-0.001),
         "tail_mass_toward_nominal"),
    ])
    def test_each_clause_flips_only_itself(self, mutate, expect_check):
        sel = _passing_sel()
        mutate(sel)
        gate = M2.compose_gate_margin2(sel, True)
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == [expect_check], (
            f"mutation must flip exactly `{expect_check}`, flipped {failed} — a fixture that "
            f"trips several clauses proves none of them (NF-D17)")
        assert not gate["ship"]

    def test_fdr_clause_flips_only_fdr(self):
        gate = M2.compose_gate_margin2(_passing_sel(), False)
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == ["fdr_ok"]

    def test_permutation_clause_fails_closed_on_an_unevaluable_p(self):
        """NF1.7 (a): a positive permuted advantage with no evaluable p is NOT a pass."""
        assert not M2.permuted_not_significantly_better(0.01, None)
        assert M2.permuted_not_significantly_better(-0.01, None)
        assert M2.permuted_not_significantly_better(0.01, 0.20)
        assert not M2.permuted_not_significantly_better(0.01, 0.01)

    def test_anchor_only_refusal_is_constraint_refused(self):
        sel = _passing_sel()
        sel["anchors"]["over_ext_loses"] = False
        checks = M2.compose_gate_margin2(sel, True)["checks"]
        verdict = M2.hand_classify_refusal_margin2(checks)
        assert verdict is not None and verdict["state"] == "CONSTRAINT_REFUSED"
        assert verdict["retest_trigger"] is None

    def test_calibration_only_refusal_is_constraint_refused_and_named(self):
        sel = _passing_sel()
        sel["calibration"]["tail_mass_delta_vs_incumbent"] = -0.02
        checks = M2.compose_gate_margin2(sel, True)["checks"]
        verdict = M2.hand_classify_refusal_margin2(checks)
        assert verdict is not None and verdict["state"] == "CONSTRAINT_REFUSED"
        assert "tail_mass_toward_nominal" in verdict["failing_anchor_checks"]

    def test_statistical_refusal_delegates_to_the_layer_b_classifier(self):
        sel = _passing_sel()
        sel["beats_foil"] = False
        checks = M2.compose_gate_margin2(sel, True)["checks"]
        assert M2.hand_classify_refusal_margin2(checks) is None


# ── Null classification (the 1-arm hand path) ───────────────────────────────────────────────────
def _sel_for_classifier(beats: bool) -> dict:
    return {
        "beats_foil": beats, "mean_delta": 0.003 if beats else -0.002,
        "ci95": [-0.001, 0.007] if beats else [-0.005, 0.001],
        "fold_wins": 6 if beats else 3,
        "fold_clause": {"required": 6},
        "p_one_sided": 0.08 if beats else 0.7,
        "observed_sr": 0.45 if beats else -0.2,
    }


class TestNullClassification:
    def test_a_losing_arm_is_genuine_absence_with_no_trigger(self):
        out = M2.classify_layer_b(_sel_for_classifier(False), n_folds=8)
        assert out["state"] == "GENUINE_ABSENCE"
        assert out["retest_trigger"] is None

    def test_a_positive_underpowered_arm_is_power_limited_in_folds(self):
        out = M2.classify_layer_b(_sel_for_classifier(True), n_folds=8)
        assert out["state"] == "POWER_LIMITED"
        assert "fold" in (out["retest_trigger"] or "")

    def test_the_instrument_verdict_is_recorded_never_discarded(self):
        iv = {"state": "UNDEFINED", "reason": "8 fold(s) < 4", "retest_trigger": "-4 folds"}
        out = M2.classify_layer_b(_sel_for_classifier(True), n_folds=8, instrument_verdict=iv)
        assert out["instrument_verdict"] == iv
        assert out["hand_corrected"] is True
