"""NF-D18 — ATTENUATE-AT-THE-TOP rookie-point recalibration (RB/TE/WR).

NF-D18 asks whether a correction exists that keeps NF-D16's accuracy gain while leaving the top rookie
where NF-D17's VALIDATED placement clause admits. These tests guard the six things that decide whether
its answer means anything:

  1. ⛔ **λ IS NOT A KNOB.** NF-D16 pre-registered a shrink grid and SELECTED λ = 1, so re-picking it
     after seeing a constraint result is the E2.1-r inversion. Every candidate here runs at λ = 1, the
     globally-shrunk affine exists ONLY as a non-shippable matched foil, and this is pinned so a
     future edit cannot quietly re-open the knob.
  2. ⭐ **THE PLACEMENT CLEARANCE IS THRESHOLD-INVARIANT**, mirroring the VETO it has to overturn.
     NF-D17's veto held across the whole Q05–Q25 band AND against the observed minimum, so a clearance
     must too — otherwise a ship could be manufactured by choosing the kind quantile.
  3. ⭐ **A CHECK NEVER PASSES ON NOTHING** (NF1.7 (a)) — an unevaluable placement, a missing anchor
     and an absent per-form ceiling are all FAILURES, never skips. Two of these are REGRESSION guards
     on real defects this story's first run surfaced.
  4. ⭐ **THE MATCHED FOIL IS A REAL CONTROL, NOT A LABEL.** Its λ must be computable from point
     projections ALONE (no outcome may enter it), and an arm that corrects MORE than the reference
     must not silently collapse the foil onto the reference arm itself — the second defect the first
     run surfaced, and the one that would have made the attribution examine nothing.
  5. ⛔ **THE QB EXCLUSION IS STRUCTURAL** and INHERITED BY IMPORT through NF-D16, so this story
     cannot drift on scope.
  6. **THE GATES ARE INHERITED, NOT COPIED** — PBO/DSR/α come from NF-D16 by import, so the bar cannot
     drift between the story that shipped the correction and the story trying to publish it.

Pure/fast: no IO, no network, no bake-off, no artifacts (the pool and the board are gitignored, so a
test that needed them would be un-runnable in CI by construction).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RC
from quant_sports_intel_models.football.nfl.fantasy import rookie_top_attenuation as TA


def _pool(n: int = 90, seed: int = 7) -> tuple:
    """A synthetic in-fold population with the two properties that actually drive this story: a real
    ZERO ATOM (~20% of drafted rookies never produce) and a cold point projection at the top."""
    rng = np.random.default_rng(seed)
    pos = np.array(["RB", "TE", "WR"] * (n // 3), dtype=object)
    point = np.abs(rng.normal(90.0, 45.0, len(pos))) + 6.0
    real = point * 1.25 + rng.normal(0.0, 25.0, len(pos))
    real = np.clip(real, 0.0, None)
    real[rng.random(len(pos)) < 0.20] = 0.0
    return point, real, pos


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ⛔ λ is not a knob in this story
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestLambdaIsNotAKnob:
    def test_every_candidate_runs_at_lambda_one(self):
        """§6's rule made mechanical. A shrink GRID in this field would be a λ re-pick wearing a
        pre-registration's clothes, so the constant is pinned and every non-null arm reads it."""
        assert TA.FIXED_LAMBDA == 1.0
        cfgs = TA.candidate_configs()
        recal = [c for c in cfgs if c["form"] != "incumbent"]
        assert recal, "the field must contain at least one correction"
        assert {c["lam"] for c in recal} == {1.0}, (
            "a candidate is running at a λ other than 1 — that re-opens the selection parameter "
            "NF-D16 already chose (E2.1-r)")

    def test_the_field_contains_no_shrink_grid_constant(self):
        assert not hasattr(TA, "SHRINK_GRID"), (
            "NF-D18 must not define a shrink grid — the globally-shrunk affine is a MATCHED FOIL, "
            "never a candidate")

    def test_the_reference_arm_is_carried_at_full_strength_so_the_constraint_can_refuse_it(self):
        """A field of only attenuated forms would leave the placement constraint passing having
        examined nothing — the NF1.7 vacuous-check class wearing NF-D16's `mult_tier` hat."""
        cfgs = TA.candidate_configs()
        ref = [c for c in cfgs if c["form"] == TA.REFERENCE_FORM]
        assert len(ref) == 1 and ref[0]["shippable"] and ref[0]["lam"] == 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⭐ The placement clearance is threshold-invariant — it mirrors the veto
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPlacementClearanceIsThresholdInvariant:
    def test_the_ranks_nf_d17_vetoed_do_not_clear(self):
        """NF-D16's board placed its top rookie at overall rank 6 and NF-D17 measured that as outside
        reality's ENTIRE observed support (minimum 7). It must not clear here either."""
        for rank in (1, 5, 6, 7, 8, 9, 10, 11):
            assert not TA.placement_clearance(rank)["clears"], (
                f"rank {rank} cleared — but the strictest cap in NF-D17's own band is 11.5, so any "
                f"rank better than 12 breaches at SOME quantile in the band")

    def test_the_incumbent_boards_rank_clears(self):
        got = TA.placement_clearance(12)
        assert got["clears"] and got["evaluable"]
        assert got["strictest_cap"] == pytest.approx(11.5)

    def test_a_clearance_must_hold_at_every_quantile_in_the_band_not_just_the_headline_one(self):
        """⭐ THE GUARD AGAINST THE E2.1-r INVERSION FACING THE OTHER WAY. Rank 9 passes the HEADLINE
        Q10 cap of 8.8 — so a naive `rank >= cap` check would call it a clearance — while breaching
        Q15/Q20/Q25. Clearing only at a cap you would pick after seeing the result is exactly what
        NF-D17's threshold-invariance requirement exists to forbid."""
        from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
        assert 9.0 >= SP.placement_reference_cap(q=0.10)      # passes the headline cap...
        assert not TA.placement_clearance(9)["clears"]         # ...and is still refused

    def test_an_unevaluable_placement_is_a_failure_and_never_a_pass(self):
        """NF1.7 (a): a check that did not run is not a check that passed."""
        got = TA.placement_clearance(None)
        assert got["clears"] is False and got["evaluable"] is False

    def test_the_cap_is_imported_rather_than_re_derived(self):
        """NF-D18 introduces NO new threshold and NO new reference — re-deriving the very bar it is
        trying to clear would be the story marking its own homework."""
        from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
        assert not hasattr(TA, "REALIZED_BEST_ROOKIE_OVERALL_RANK")
        assert TA.placement_clearance(12)["caps_over_q_band"] == \
            SP.rookie_placement_breach(12)["caps_over_q_band"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⭐ Nothing passes on nothing — including two REGRESSION guards on real first-run defects
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestNoCheckPassesVacuously:
    def test_a_missing_anchor_raises_rather_than_reporting_green(self):
        with pytest.raises(SystemExit):
            TA.require_anchors({"oracle_perplayer": {"tier_mae": 0.0}})

    def test_an_anchor_that_scored_none_is_missing_not_present(self):
        scored = {t: {"tier_mae": 1.0} for t in TA._REQUIRED_ANCHORS}
        scored["oracle_isotonic"]["tier_mae"] = None
        with pytest.raises(SystemExit):
            TA.require_anchors(scored)

    def test_the_full_required_anchor_set_passes(self):
        TA.require_anchors({t: {"tier_mae": 1.0} for t in TA._REQUIRED_ANCHORS})

    def test_every_form_in_the_field_has_its_own_peeking_ceiling(self):
        """⭐ NF1.7 (b) / NF1.9 (f): a peeking oracle is a floor only at MATCHED FAMILY. The families
        here NEST — `isotonic` contains every other form — so one ceiling for the field would veto a
        legitimately-better nested form as a false metric inversion (the bug NF-D16's first cut
        shipped)."""
        assert set(TA.FAMILY_CEILING) == set(TA.FORMS)
        assert len(set(TA.FAMILY_CEILING.values())) == len(TA.FORMS)

    def test_the_shared_ceiling_check_must_be_told_which_family_map_to_use(self):
        """⭐ REGRESSION GUARD ON A REAL DEFECT THIS STORY'S FIRST RUN SURFACED. `family_ceiling_check`
        is NF-D16's and defaults to NF-D16's form → anchor map, which does not contain NF-D18's forms.
        Called without `family_ceiling=`, every attenuating arm resolves to a `None` ceiling — and the
        check correctly reports a HARD FAILURE rather than a silent skip, which is the NF1.7 (a) rule
        earning its keep. Both halves are pinned: the failure WITHOUT the map, and the pass WITH it."""
        arms = [{"label": "power", "form": "power", "recalibrates": True, "pooled_tier_mae": 2.0}]
        anchors = {"oracle_power": {"pooled_tier_mae": 1.5}}

        blind = RC.family_ceiling_check(arms, anchors, metric="pooled_tier_mae")
        assert not blind["ok"], "the check passed on a ceiling it could not even look up"
        assert blind["violations"][0]["ceiling_anchor"] is None

        told = RC.family_ceiling_check(arms, anchors, metric="pooled_tier_mae",
                                       family_ceiling=TA.FAMILY_CEILING)
        assert told["ok"] and told["per_arm"][0]["ceiling_anchor"] == "oracle_power"

    def test_nf_d16s_own_callers_are_unaffected_by_the_new_parameter(self):
        """The parameter is additive: NF-D16's default map must still be what it gets."""
        arms = [{"label": "ols_slope · λ 1", "form": "ols_slope", "recalibrates": True,
                 "pooled_tier_mae": 0.94}]
        got = RC.family_ceiling_check(arms, {"oracle_ols": {"pooled_tier_mae": 0.77}},
                                      metric="pooled_tier_mae")
        assert got["ok"] and got["per_arm"][0]["ceiling_anchor"] == "oracle_ols"

    def test_an_arm_beating_its_own_forms_ceiling_is_refused(self):
        arms = [{"label": "qmap", "form": "qmap", "recalibrates": True, "pooled_tier_mae": 0.5}]
        got = RC.family_ceiling_check(arms, {"oracle_qmap": {"pooled_tier_mae": 0.8}},
                                      metric="pooled_tier_mae", family_ceiling=TA.FAMILY_CEILING)
        assert not got["ok"], "an in-fold arm beat its own peeking fit — that IS a metric inversion"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. ⭐ The matched foil is a real control, not a label
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheMatchedFoilIsARealControl:
    def test_the_foils_lambda_is_computable_from_projections_alone(self):
        """⭐ NO OUTCOME MAY ENTER IT. That is what makes 'the arm cleared and its matched foil did
        not' a statement about SHAPE rather than about something the foil was told."""
        import inspect
        sig = inspect.signature(TA.matched_global_lambda)
        assert "real" not in sig.parameters and "outcome" not in sig.parameters
        assert list(sig.parameters)[:4] == ["point", "positions", "arm_adjusted",
                                            "reference_adjusted"]

    def test_it_matches_the_mean_absolute_tier_correction(self):
        pos = np.array(["RB"] * 12, dtype=object)
        point = np.linspace(50.0, 200.0, 12)
        ref = point + 40.0                                  # reference adds 40 everywhere
        arm = point + 20.0                                  # the arm adds half as much
        assert TA.matched_global_lambda(point, pos, arm, ref) == pytest.approx(0.5)

    def test_an_arm_that_corrects_more_than_the_reference_is_still_matched(self):
        """⭐ REGRESSION GUARD ON THE SECOND FIRST-RUN DEFECT. The λ was clipped to [0, 1], so an arm
        applying MORE correction than the reference pinned at 1.0 and its 'matched foil' became the
        REFERENCE ARM ITSELF, byte-identical — a control that examined nothing while reporting a clean
        pairing. Three of this field's four attenuating arms correct more than the reference."""
        pos = np.array(["RB"] * 12, dtype=object)
        point = np.linspace(50.0, 200.0, 12)
        ref, arm = point + 20.0, point + 50.0
        lam = TA.matched_global_lambda(point, pos, arm, ref)
        assert lam == pytest.approx(2.5), "the foil silently collapsed onto the reference arm"
        assert TA.MATCHED_FOIL_LAMBDA_CLIP[1] > 1.0

    def test_an_unmatched_foil_is_none_rather_than_a_silent_identity(self):
        pos = np.array(["RB"] * 8, dtype=object)
        point = np.linspace(50.0, 200.0, 8)
        assert TA.matched_global_lambda(point, pos, point + 10.0, point) is None

    def test_the_foils_are_never_shippable_and_never_candidates(self):
        """A DIAGNOSTIC ANCHOR IS NEVER A TRIAL (MH2 (a)) — a foil that priced the multiplicity of a
        search nobody ran would tax a real finding for the presence of its own control."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_d18_top_attenuation as R18)
        foils = [c for c in R18.all_configs() if c.get("matched_foil")]
        assert foils, "the attribution control is missing entirely"
        assert all(not c["shippable"] for c in foils)
        assert {c["matches"] for c in foils} == set(TA.ATTENUATION_FORMS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. ⛔ The QB exclusion is structural and inherited
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestQbExclusionIsStructural:
    def test_scope_is_inherited_by_import_through_nf_d16(self):
        assert TA.ATTENUATED_POSITIONS is RC.RECALIBRATED_POSITIONS
        assert "QB" not in TA.ATTENUATED_POSITIONS

    def test_no_form_can_route_around_the_gate(self):
        pos = np.array(["QB", "RB", "TE", "WR"], dtype=object)
        point = np.full(4, 120.0)
        for adj in (np.full(4, 400.0), np.zeros(4), np.full(4, np.nan)):
            got = TA.apply_position_adjustment(point, pos, adj)
            assert got[0] == 120.0, "a correction reached QB"

    def test_a_missing_estimate_degrades_to_the_incumbent_never_to_zero(self):
        pos = np.array(["RB", "WR"], dtype=object)
        point = np.array([100.0, 80.0])
        got = TA.predict_form("ols_slope", {"RB": (0.0, 1.5)}, point, pos)
        assert got[0] == pytest.approx(150.0)
        assert np.isnan(got[1]), "an unfitted position must yield NaN, which the gate turns back "\
                                 "into the incumbent"
        assert TA.apply_position_adjustment(point, pos, got)[1] == pytest.approx(80.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The gates are INHERITED, not copied
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestGatesAreInherited:
    def test_pbo_dsr_alpha_come_from_nf_d16_by_import(self):
        assert (TA.PBO_MAX, TA.DSR_MIN, TA.ALPHA) == (RC.PBO_MAX, RC.DSR_MIN, RC.ALPHA)

    def test_the_metric_and_the_ordering_tolerance_are_nf1_4s(self):
        from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14
        assert TA.SELECTION_METRIC == M14.SELECTION_METRIC == "tier_mae"
        assert TA.ORDERING_DO_NO_HARM == M14.ORDERING_DO_NO_HARM

    def test_the_framing_is_pooled_and_says_it_is_inherited(self):
        assert TA.PREREGISTERED_FRAMING == RC.PREREGISTERED_FRAMING == "pooled"
        assert TA.PREREGISTERED_DSR_READING == RC.PREREGISTERED_DSR_READING == "whole_field"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The forms behave the way the pre-registration says they do — MEASURED, not asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheFormsDoWhatTheyClaim:
    def test_the_quantile_map_is_non_decreasing(self):
        point, real, pos = _pool()
        params = TA.fit_qmap(point, real, pos)
        x = np.linspace(5.0, 260.0, 60)
        got = TA.predict_form("qmap", params, x, np.array(["RB"] * 60, dtype=object))
        assert np.all(np.diff(got) >= -1e-9), "the quantile map moved a rank"

    def test_the_quantile_map_ties_at_the_zero_atom_and_the_story_MEASURES_that(self):
        """⭐ THE PRE-REGISTRATION CLAIMED `qmap` IS 'rank-preserving by construction' AND THE RUN
        MEASURED THAT CLAIM FALSE — ~20% of drafted rookies realize exactly 0, so the realized quantile
        function is FLAT at the bottom and the map TIES there. A tie IS rank movement. This is NF-D16's
        method lock 2 (measure it, don't assert it) catching this story's own registered claim, and the
        guard pins the measurement rather than the claim."""
        point, real, pos = _pool()
        params = TA.fit_qmap(point, real, pos)
        rb = pos == "RB"
        adj = TA.predict_form("qmap", params, point[rb], pos[rb])
        assert (adj <= 1e-9).sum() >= 2, "the synthetic pool lost its zero atom — the test is vacuous"
        m = TA.ordering_is_structural("qmap", point[rb], pos[rb], adj)
        assert m["expected_monotone"] is True
        assert m["worst_rank_move"] > 0.0, (
            "the zero atom produced no ties, so this guard is not measuring what it claims")
        assert m["structural_claim_holds"] is False, (
            "a by-construction claim that the numbers refute must be REPORTED false, not smoothed")

    def test_the_power_form_carries_duans_smearing_and_is_monotone_for_positive_gamma(self):
        """Without the smearing factor the log-scale fit predicts a conditional MEDIAN and sits
        systematically LOW at every x — which would make the arm 'attenuate everywhere' and confound
        the SHAPE mechanism with a plain magnitude reduction, the exact confound the matched foil
        exists to detect."""
        point, real, pos = _pool()
        params = TA.fit_power(point, real, pos)
        assert params, "the power form failed to fit the synthetic pool"
        for _q, (_c, gamma, smear) in params.items():
            assert TA.POWER_GAMMA_CLIP[0] <= gamma <= TA.POWER_GAMMA_CLIP[1]
            assert TA.POWER_SMEAR_CLIP[0] <= smear <= TA.POWER_SMEAR_CLIP[1]
        x = np.linspace(5.0, 260.0, 60)
        got = TA.predict_form("power", params, x, np.array(["RB"] * 60, dtype=object))
        assert np.all(np.diff(got) > 0), "a positive exponent must not move a rank"

    def test_a_concave_power_attenuates_the_top_and_a_convex_one_does_not(self):
        """The form's registered PURPOSE is top-attenuation, and whether it delivers is a property of
        the FITTED exponent rather than of the form — so both directions are pinned. (The run found
        γ ≈ 2 on real data, i.e. the data fits an AMPLIFIER; that is a finding about the data, and it
        is only readable because the two cases are distinguishable here.)"""
        x = np.array([20.0, 200.0])
        pos = np.array(["RB", "RB"], dtype=object)
        conc = TA.predict_form("power", {"RB": (0.6, 0.8, 1.0)}, x, pos)
        conv = TA.predict_form("power", {"RB": (0.6, 1.4, 1.0)}, x, pos)
        assert conc[1] / x[1] < conc[0] / x[0], "γ < 1 must lift the top proportionally LESS"
        assert conv[1] / x[1] > conv[0] / x[0], "γ > 1 must lift the top proportionally MORE"

    def test_the_learned_foil_is_the_richest_family_and_is_monotone(self):
        point, real, pos = _pool()
        params = TA.fit_isotonic(point, real, pos)
        x = np.linspace(5.0, 260.0, 60)
        got = TA.predict_form("isotonic", params, x, np.array(["RB"] * 60, dtype=object))
        assert np.all(np.diff(got) >= -1e-9)
        assert TA.LEARNED_FOIL == "isotonic"
        assert "isotonic" in TA.REORDERING_FORMS, (
            "isotonic is only WEAKLY monotone — its flat segments tie, and a tie IS rank movement")

    def test_the_robust_affine_returns_the_same_shape_as_the_reference(self):
        """The two arms must be interchangeable everywhere downstream so the ONLY difference between
        them is the loss — otherwise 'the estimator channel' is not what is being tested."""
        point, real, pos = _pool()
        h, o = TA.fit_huber(point, real, pos), TA.fit_ols(point, real, pos)
        assert set(h) == set(o)
        assert all(len(v) == 2 for v in h.values())

    def test_a_thin_cell_yields_no_estimate_rather_than_a_wild_one(self):
        point = np.array([50.0, 60.0, 70.0])
        real = np.array([40.0, 90.0, 10.0])
        pos = np.array(["RB", "RB", "RB"], dtype=object)
        for form in TA.FORMS:
            assert TA.fit_form(form, point, real, pos) == {}, (
                f"{form} emitted a correction from three rows")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The board placement reads the merged board the way serving would
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestBoardPlacement:
    @staticmethod
    def _board() -> pd.DataFrame:
        return pd.DataFrame({
            "player_name": ["VetA", "VetB", "VetC", "RookA", "RookB"],
            "position": ["QB", "RB", "WR", "RB", "WR"],
            "is_rookie": [False, False, False, True, True],
            "proj_fp_ppr": [300.0, 250.0, 200.0, 180.0, 120.0],
        })

    def test_the_incumbent_boards_best_rookie_rank_is_read_correctly(self):
        got = TA.board_placement(self._board())
        assert got["best_rookie_overall_rank"] == 4 and got["best_rookie"] == "RookA"
        assert got["top1_is_rookie"] is False

    def test_a_correction_moves_rookies_through_a_FIXED_veteran_field(self):
        """⭐ THE STRUCTURAL FACT NF-D16's 'moves no ranks' argument missed: rookies and veterans share
        ONE board, so a within-position-monotone correction still reorders rookies ACROSS the board."""
        board = self._board()
        got = TA.board_placement(board, np.array([320.0, 120.0]))
        assert got["best_rookie_overall_rank"] == 1 and got["top1_is_rookie"] is True
        assert TA.board_placement(board)["best_rookie_overall_rank"] == 4, \
            "the helper mutated the caller's board"

    def test_veterans_are_never_touched(self):
        board = self._board()
        TA.board_placement(board, np.array([999.0, 999.0]))
        assert board.loc[0, "proj_fp_ppr"] == 300.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The verdict cannot ship without BOTH constraints, and the anchors are real vetoes
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheVerdictGates:
    @staticmethod
    def _passing() -> dict:
        return dict(winner={"label": "x", "metric": 0.90, "recalibrates": True},
                    incumbent_metric=1.07,
                    ordering={"per_position": {"RB": {"ok": True}, "TE": {"ok": True},
                                               "WR": {"ok": True}}},
                    placement={"clears": True}, pbo=0.05, dsr=0.99, pvalue=0.01)

    def test_the_happy_path_ships(self):
        assert TA.pooled_ship(**self._passing())["ship"] is True

    def test_a_breached_placement_blocks_the_ship(self):
        kw = self._passing()
        kw["placement"] = {"clears": False}
        got = TA.pooled_ship(**kw)
        assert got["ship"] is False and got["placement_clears_threshold_invariant"] is False

    def test_a_missing_placement_reading_blocks_the_ship(self):
        """NF1.7 (a) again: an absent constraint reading is not a satisfied one."""
        kw = self._passing()
        kw["placement"] = None
        assert TA.pooled_ship(**kw)["ship"] is False

    def test_one_positions_ordering_collapse_blocks_the_ship(self):
        kw = self._passing()
        kw["ordering"]["per_position"]["WR"]["ok"] = False
        assert TA.pooled_ship(**kw)["ship"] is False

    def test_the_within_permutation_is_a_real_gate_in_this_story(self):
        """⭐ THE ANCHOR THAT WAS VACUOUS IN NF-D16 AND BITES HERE. A LEVEL is a marginal statistic so a
        within-position shuffle preserves it exactly; every NF-D18 form estimates a SHAPE, which that
        shuffle destroys. So it is pre-registered as a GATE rather than as an expected tie."""
        ok = dict(pooled_ships=True, degenerates_lose=True, permutation_across_beaten=True,
                  permutation_within_beaten=True, oracle_respected=True,
                  family_ceiling_respected=True, qb_untouched=True)
        assert TA.attenuation_verdict(**ok)["ship"] is True
        assert TA.attenuation_verdict(**{**ok, "permutation_within_beaten": False})["ship"] is False

    def test_every_global_anchor_is_a_veto(self):
        ok = dict(pooled_ships=True, degenerates_lose=True, permutation_across_beaten=True,
                  permutation_within_beaten=True, oracle_respected=True,
                  family_ceiling_respected=True, qb_untouched=True)
        for k in ok:
            assert TA.attenuation_verdict(**{**ok, k: False})["ship"] is False, \
                f"{k} is not actually vetoing"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The attenuation profile MEASURES the field's own labels rather than trusting them
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAttenuationProfileIsMeasured:
    def test_a_form_that_expands_the_top_is_reported_as_not_attenuating(self):
        pos = np.array(["RB"] * 10, dtype=object)
        point = np.linspace(40.0, 200.0, 10)
        assert TA.attenuation_profile(point, pos, point * 1.5)["attenuates_at_top"] is False

    def test_an_affine_with_a_positive_intercept_reads_as_ratio_attenuating(self):
        """An affine's correction RATIO falls with x by construction (a/x + b), so the reference itself
        reads as ratio-attenuating — which is exactly why the story reads the BOARD RANK and the
        absolute top delta rather than this flag alone."""
        pos = np.array(["RB"] * 10, dtype=object)
        point = np.linspace(40.0, 200.0, 10)
        prof = TA.attenuation_profile(point, pos, 30.0 + point)
        assert prof["attenuates_at_top"] is True
        assert prof["per_position"]["RB"]["top_delta_ppr"] == pytest.approx(30.0)

    def test_the_tier_is_fixed_by_the_incumbent_anchor(self):
        """NF1.1's fixed-anchor rule: every arm is matched on the identical rows, so a foil cannot be
        matched on a subset its own correction chose."""
        pos = np.array(["RB"] * 10, dtype=object)
        point = np.linspace(40.0, 200.0, 10)
        keep = TA.tier_mask(point, pos)
        assert int(keep.sum()) == TA.SCALED_TIER_K["RB"]
        assert keep[-1] and not keep[0], "the tier must be the TOP of the incumbent's board"
