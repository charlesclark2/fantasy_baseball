"""NF-D16 — the per-position LEVEL recalibration of the rookie POINT (RB/TE/WR).

These tests guard the five things that decide whether NF-D16's answer means anything, and whether the
change it ships is the change it measured:

  1. ⛔ **THE QB EXCLUSION IS STRUCTURAL**, in the harness AND on the served path. NF-D14 MEASURED the
     rookie-QB double-pricing; no arm — candidate, degenerate or ORACLE — may route around it.
  2. **THE SHRINK GRID'S ZERO END IS THE NULL, EXACTLY, FOR EVERY FORM.** NF-D15 shrank geometrically
     in a multiplicative scale, which is undefined for an additive or affine arm; NF-D16 blends in
     OUTPUT space so `λ = 0` reproduces the incumbent byte-for-byte whatever the form.
  3. ⭐ **THE PEEKING CEILING IS PER FORM, NOT ONE FOR THE FIELD.** This is a REGRESSION GUARD on a
     real bug in this story's first cut: flooring `mult_tier`/`ols_slope` on the per-position CONSTANT
     ceiling would call a legitimate capacity effect a metric inversion (NF1.7 (b) / NF1.9 (f) — a
     peeking oracle is a floor only at MATCHED FAMILY *and* MATCHED RESOLUTION).
  4. ⭐ **A LEVEL IS A MARGINAL STATISTIC**, so a within-position permutation cannot bite it. The
     additive form is EXACTLY invariant under one, which is why the story reports that anchor as an
     expected tie rather than presenting a near-tie as a passed test.
  5. **NO GATE PASSES VACUOUSLY** — a missing anchor, an absent ceiling, an un-consumed check.

Plus the SERVING contract: the recalibration is OPT-IN, it keeps the displayed point equal to the
scored stat line, and a curve fitted without `recal_hist` is byte-identical to the pre-NF-D16
incumbent (which is what protects NF1.4's pinned "the band does not move the point" test).

Pure/fast: no IO, no network, no bake-off.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RC
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ⛔ The QB exclusion — structural, not a convention every arm has to remember
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestQbExclusionIsStructural:
    def test_qb_passes_through_whatever_adjustment_is_asked_for(self):
        pos = np.array(["QB", "RB", "WR", "TE", "QB"], dtype=object)
        point = np.full(5, 100.0)
        got = RC.apply_position_adjustment(point, pos, np.full(5, 250.0))
        assert got[0] == 100.0 and got[4] == 100.0, "a recalibration reached QB"
        assert got[1] == got[2] == got[3] == 250.0

    def test_even_a_zero_adjustment_cannot_blank_a_qb(self):
        """`zero_scale` is exactly the arm most likely to be written without the exclusion in mind —
        and an anchor that silently recalibrated QB would answer a different question than every
        candidate it is compared against."""
        got = RC.apply_position_adjustment(np.array([50.0, 50.0]),
                                           np.array(["QB", "RB"], dtype=object), np.zeros(2))
        assert got.tolist() == [50.0, 0.0]

    def test_scope_is_inherited_from_nf_d15_by_import_so_the_two_cannot_drift(self):
        from quant_sports_intel_models.football.nfl.fantasy import rookie_point_scaling as PS
        assert RC.RECALIBRATED_POSITIONS is PS.SCALED_POSITIONS
        assert "QB" not in RC.RECALIBRATED_POSITIONS

    def test_a_missing_estimate_leaves_the_projection_alone_rather_than_blanking_it(self):
        """The honest degradation of 'I have no level read for this position' is 'leave it alone',
        never 'project him at zero' — a rookie must not fall off the board because a thin cell had
        nothing to say."""
        got = RC.apply_position_adjustment(np.array([40.0, 40.0]),
                                           np.array(["RB", "WR"], dtype=object),
                                           np.array([np.nan, np.inf]))
        assert got.tolist() == [40.0, 40.0]

    def test_the_output_is_floored_at_zero(self):
        """A fantasy projection cannot be negative, and an ADDITIVE form is the one arm that could
        otherwise emit one."""
        got = RC.apply_position_adjustment(np.array([10.0]), np.array(["RB"], dtype=object),
                                           np.array([-30.0]))
        assert got.tolist() == [0.0]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The shrink grid's zero end IS the null — EXACTLY, and for EVERY form
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestShrinkZeroEndIsTheNull:
    @pytest.mark.parametrize("adjusted", [np.array([10.0, 200.0]), np.array([np.nan, 0.0])])
    def test_lambda_zero_reproduces_the_incumbent_byte_for_byte(self, adjusted):
        point = np.array([100.0, 100.0])
        assert RC.blend_toward_incumbent(point, adjusted, 0.0).tolist() == point.tolist()

    def test_lambda_one_is_the_full_adjustment(self):
        point, adj = np.array([100.0]), np.array([137.0])
        assert RC.blend_toward_incumbent(point, adj, 1.0).tolist() == [137.0]

    def test_the_blend_is_in_output_space_so_every_form_gets_the_same_shaped_knob(self):
        """NF-D15 shrank GEOMETRICALLY in a multiplicative scale, which is undefined for an additive
        or affine arm. If λ meant something different across forms, the grid would be an
        UNCONTROLLED difference between arms rather than the controlled one it exists to be."""
        point = np.array([100.0])
        mult, add = np.array([140.0]), np.array([140.0])   # same output, different provenance
        assert (RC.blend_toward_incumbent(point, mult, 0.5).tolist()
                == RC.blend_toward_incumbent(point, add, 0.5).tolist() == [120.0])

    def test_every_registered_form_appears_at_every_lambda(self):
        cfgs = RC.candidate_configs()
        for form in RC.FORMS:
            lams = sorted(c["lam"] for c in cfgs if c["form"] == form)
            assert lams == sorted(RC.SHRINK_GRID), f"{form} is missing a λ"
        assert sum(1 for c in cfgs if c["form"] == "incumbent") == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⭐ THE PER-FORM PEEKING CEILING — a regression guard on this story's own first-cut bug
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheCeilingIsPerFormNotOneForTheField:
    @staticmethod
    def _arm(label, form, metric):
        return {"label": label, "form": form, "recalibrates": True, "pooled_tier_mae": metric}

    @staticmethod
    def _anchors(**kw):
        base = {"oracle_posconst": 0.90, "oracle_addoffset": 0.91,
                "oracle_tierconst": 0.84, "oracle_ols": 0.78}
        base.update(kw)
        return {k: {"pooled_tier_mae": v} for k, v in base.items()}

    def test_a_richer_family_beating_the_CONSTANT_ceiling_is_NOT_flagged(self):
        """⭐ THE BUG THIS STORY SHIPPED AND THEN FIXED. `mult_tier` and `ols_slope` each CONTAIN the
        per-position constant as a special case, so either can legitimately score better than the best
        possible constant — a capacity effect, the same one NF1.9 documented when its winner beat a
        coarser peeking oracle. A single constant-family ceiling would veto that as a metric
        inversion, i.e. it would kill a REAL result for the wrong reason."""
        arms = [self._arm("ols_slope · λ 1", "ols_slope", 0.85)]   # beats oracle_posconst (0.90)
        got = RC.family_ceiling_check(arms, self._anchors(), metric="pooled_tier_mae")
        assert got["ok"], "a richer family beating the CONSTANT ceiling was wrongly flagged"

    def test_an_arm_beating_ITS_OWN_form_ceiling_IS_flagged(self):
        """Against its own form's peeking parameters, 'peeking can only help' genuinely holds — the
        peeking fit minimises the same objective over the same parameter space on the very rows it is
        scored on. So an in-fold arm beating it IS a metric inversion."""
        arms = [self._arm("ols_slope · λ 1", "ols_slope", 0.70)]   # beats oracle_ols (0.78)
        got = RC.family_ceiling_check(arms, self._anchors(), metric="pooled_tier_mae")
        assert not got["ok"] and got["violations"], "a genuine inversion was not caught"

    def test_every_form_has_a_registered_ceiling(self):
        assert set(RC.FAMILY_CEILING) == set(RC.FORMS)

    def test_a_missing_ceiling_is_a_FAILURE_not_a_skip(self):
        """An absent anchor makes its check VACUOUSLY TRUE — `winner < anchor` against nothing
        compares nothing and reports green (NF1.7 lesson (a))."""
        arms = [self._arm("ols_slope · λ 1", "ols_slope", 0.85)]
        anchors = self._anchors()
        anchors.pop("oracle_ols")
        got = RC.family_ceiling_check(arms, anchors, metric="pooled_tier_mae")
        assert not got["ok"]

    def test_the_incumbent_is_not_checked_against_a_ceiling(self):
        arms = [{"label": "incumbent (NULL)", "form": "incumbent", "recalibrates": False,
                 "pooled_tier_mae": 0.1}]
        got = RC.family_ceiling_check(arms, self._anchors(), metric="pooled_tier_mae")
        assert got["ok"] and got["n_checked"] == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. ⭐ A LEVEL IS A MARGINAL STATISTIC — so a within-position permutation cannot bite it
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePermutationAnchorIsWeakAgainstALevelHypothesis:
    def test_the_additive_offset_is_EXACTLY_invariant_under_a_within_position_permutation(self):
        """`mean(y) − mean(point)` cannot change when `y` is permuted within the position. This is
        why the story REPORTS `permuted_within` as an expected TIE rather than presenting a near-tie
        as a passed permutation test — a check that cannot fail has examined nothing."""
        rng = np.random.default_rng(7)
        pos = np.array(["RB"] * 40 + ["WR"] * 40, dtype=object)
        point = rng.uniform(20, 200, 80)
        real = rng.uniform(0, 300, 80)
        shuffled = real.copy()
        for q in ("RB", "WR"):
            sel = np.flatnonzero(pos == q)
            shuffled[sel] = rng.permutation(shuffled[sel])
        a = RC.fit_add_offset(point, real, pos)
        b = RC.fit_add_offset(point, shuffled, pos)
        for q in a:
            assert a[q] == pytest.approx(b[q], abs=1e-9)

    def test_an_ACROSS_position_permutation_DOES_move_the_estimate(self):
        """The across-position shuffle destroys the per-position level structure while preserving the
        family, the n and the grand mean — so it is the permutation that actually has to be beaten."""
        rng = np.random.default_rng(11)
        pos = np.array(["RB"] * 60 + ["TE"] * 60, dtype=object)
        point = np.r_[rng.uniform(150, 250, 60), rng.uniform(20, 60, 60)]
        real = point * 1.4
        a = RC.fit_add_offset(point, real, pos)
        b = RC.fit_add_offset(point, rng.permutation(real), pos)
        assert abs(a["RB"] - b["RB"]) > 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Ordering — three classes, and the middle one is MEASURED rather than asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestOrderingClasses:
    def test_the_monotone_forms_move_no_rank(self):
        pos = np.array(["RB"] * 6, dtype=object)
        point = np.array([200.0, 150.0, 120.0, 90.0, 60.0, 30.0])
        for form, params in (("mult_const", {"RB": 1.35}), ("add_offset", {"RB": 22.0})):
            adj = RC.predict_form(form, params, point, pos)
            got = RC.ordering_is_structural(form, point, pos, adj)
            assert got["worst_rank_move"] == 0.0 and got["structural_claim_holds"]

    def test_a_tier_varying_constant_CAN_reorder_which_is_why_it_is_carried(self):
        """A field of only monotone forms would leave the do-no-ordering-harm constraint passing
        having examined nothing — the NF1.7 vacuous-check class wearing a different hat."""
        pos = np.array(["RB"] * 4, dtype=object)
        point = np.array([100.0, 95.0, 90.0, 85.0])
        tiers = np.array(["01-15", "101+", "101+", "01-15"], dtype=object)
        adj = RC.predict_form("mult_tier", {("RB", "01-15"): 1.0, ("RB", "101+"): 1.5}, point, pos,
                              tiers)
        assert RC.ordering_is_structural("mult_tier", point, pos, adj)["worst_rank_move"] > 0

    def test_the_learned_foil_is_only_CONDITIONALLY_monotone(self):
        """An affine `a + b·point` moves no rank when `b > 0` and INVERTS a position's whole board
        when `b < 0`. So 'the learned foil does no ordering harm' is a statement about the FITTED
        SLOPES of a particular run, never about the form — which is exactly why the run records the
        slope signs and the ordering CONSTRAINT is what actually protects the board."""
        assert RC.LEARNED_FOIL in RC.CONDITIONALLY_MONOTONE_FORMS
        assert RC.LEARNED_FOIL not in RC.MONOTONE_FORMS
        pos = np.array(["RB"] * 4, dtype=object)
        point = np.array([200.0, 150.0, 100.0, 50.0])
        inverted = RC.predict_form("ols_slope", {"RB": (300.0, -1.0)}, point, pos)
        assert RC.ordering_is_structural("ols_slope", point, pos, inverted)["worst_rank_move"] > 0

    def test_an_unscorable_candidate_rho_is_a_FAILURE_not_a_skip(self):
        got = RC.ordering_check({"RB": None}, {"RB": 0.6}, positions=("RB",))
        assert not got["ok"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. No gate passes vacuously
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestNoGatePassesVacuously:
    def test_a_missing_anchor_raises_rather_than_passing(self):
        scored = {k: {RC.SELECTION_METRIC: 1.0} for k in RC._REQUIRED_ANCHORS}
        RC.require_anchors(scored)                       # complete set → fine
        scored.pop("permuted_across")
        with pytest.raises(SystemExit):
            RC.require_anchors(scored)

    def test_an_anchor_that_scored_None_is_treated_as_missing(self):
        scored = {k: {RC.SELECTION_METRIC: 1.0} for k in RC._REQUIRED_ANCHORS}
        scored["pos_median"] = {RC.SELECTION_METRIC: None}
        with pytest.raises(SystemExit):
            RC.require_anchors(scored)

    @pytest.mark.parametrize("kill", ["pbo", "dsr", "pvalue", "ordering", "beats"])
    def test_every_gate_can_block_the_ship_on_its_own(self, kill):
        kw = dict(winner={"metric": 0.9, "recalibrates": True}, incumbent_metric=1.0,
                  ordering={"per_position": {p: {"ok": True} for p in RC.RECALIBRATED_POSITIONS}},
                  pbo=0.05, dsr=0.99, pvalue=0.01)
        assert RC.pooled_ship(**kw)["ship"], "the all-green case must ship"
        if kill == "pbo":
            kw["pbo"] = 0.5
        elif kill == "dsr":
            kw["dsr"] = 0.1
        elif kill == "pvalue":
            kw["pvalue"] = 0.9
        elif kill == "ordering":
            kw["ordering"]["per_position"]["RB"]["ok"] = False
        else:
            kw["winner"] = {"metric": 1.5, "recalibrates": True}
        assert not RC.pooled_ship(**kw)["ship"], f"{kill} did not block the ship"

    def test_the_ordering_constraint_is_checked_at_EVERY_position_not_pooled(self):
        """A pooled ρ can sit flat while a single position's ordering collapses, and averaging is the
        exact operation that hides the failure the constraint exists to catch (NF1.8, one axis over).
        A POOLED hypothesis about the LEVEL does not license a pooled reading of the ORDER."""
        ordering = {"per_position": {"RB": {"ok": True}, "TE": {"ok": False}, "WR": {"ok": True}}}
        got = RC.pooled_ship(winner={"metric": 0.9, "recalibrates": True}, incumbent_metric=1.0,
                             ordering=ordering, pbo=0.05, dsr=0.99, pvalue=0.01)
        assert not got["ship"] and not got["ordering_ok_every_position"]

    def test_an_EMPTY_ordering_result_cannot_pass(self):
        """`all([])` is True — an ordering check that measured NOTHING would otherwise report green."""
        got = RC.pooled_ship(winner={"metric": 0.9, "recalibrates": True}, incumbent_metric=1.0,
                             ordering={"per_position": {}}, pbo=0.05, dsr=0.99, pvalue=0.01)
        assert not got["ship"]

    @pytest.mark.parametrize("veto", ["degenerates_lose", "permutation_across_beaten",
                                      "oracle_respected", "family_ceiling_respected",
                                      "qb_untouched"])
    def test_every_story_level_anchor_is_a_veto(self, veto):
        kw = dict(pooled_ships=True, degenerates_lose=True, permutation_across_beaten=True,
                  oracle_respected=True, family_ceiling_respected=True, qb_untouched=True)
        assert RC.recalibration_verdict(**kw)["ship"]
        kw[veto] = False
        assert not RC.recalibration_verdict(**kw)["ship"], f"{veto} did not veto"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The pre-registration is DATA, so the report cannot quietly disagree with it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_framing_and_the_dsr_reading_are_recorded_as_constants():
    """NF-D15 was blocked by its FRAMING rather than its effect size and could only say so honestly
    because it computed both readings. NF-D16 pre-registers the pooled framing WITH its reason, in
    one place, so 'what was pre-registered' has exactly one owner."""
    assert RC.PREREGISTERED_FRAMING == "pooled"
    assert RC.PREREGISTERED_DSR_READING == "whole_field"
    assert len(RC.FRAMING_REASON) > 100
    assert RC.SELECTION_METRIC == "tier_mae", "the metric must be NF1.4's, inherited not chosen"


def test_the_ceiling_gap_reads_class_variable_when_the_estimator_has_no_skill():
    """If the in-fold estimate does not predict the held-out class's own constant better than
    'predict 1.0' does, the truth is moving faster than any in-fold estimator can follow — a null
    that no amount of further estimator work would overturn."""
    got = RC.read_the_ceiling_gap(incumbent=1.07, best_candidate=1.06, ceiling=0.90,
                                  constant_stability={"skill_vs_null": -0.2})
    assert got["reading"] == "B_class_variable"


def test_the_ceiling_gap_reads_estimable_when_the_estimator_has_skill_and_captures_headroom():
    got = RC.read_the_ceiling_gap(incumbent=1.07, best_candidate=0.94, ceiling=0.78,
                                  constant_stability={"skill_vs_null": 0.31})
    assert got["reading"] == "A_estimable" and got["captured_share"] > 0.15


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. ⭐ THE SERVING CONTRACT — the shipped change is the change that was measured
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _hist():
    rng = np.random.default_rng(3)
    rows = []
    for pos, base_fp in (("RB", 170), ("WR", 150), ("QB", 240), ("TE", 90)):
        for _ in range(45):
            overall = int(rng.integers(1, 255))
            scale = max(0.05, (260 - overall) / 260.0)
            fp = max(2.0, base_fp * scale * rng.uniform(0.6, 1.4))
            rows.append({
                "position_group": pos, "draft_overall": overall, "games": min(17, 6 + scale * 11),
                "rookie_fp_ppr": fp,
                "pass_att": 450 * scale if pos == "QB" else 0.0,
                "pass_cmp": 300 * scale if pos == "QB" else 0.0,
                "pass_yds": 3600 * scale if pos == "QB" else 0.0,
                "pass_td": 22 * scale if pos == "QB" else 0.0,
                "pass_int": 12 * scale if pos == "QB" else 0.0,
                "rush_att": 200 * scale if pos == "RB" else (60 * scale if pos == "QB" else 0.0),
                "rush_yds": 900 * scale if pos == "RB" else (300 * scale if pos == "QB" else 0.0),
                "rush_td": 7 * scale if pos == "RB" else 0.0,
                "targets": 90 * scale if pos in ("WR", "TE", "RB") else 0.0,
                "rec": 60 * scale if pos in ("WR", "TE", "RB") else 0.0,
                "rec_yds": (850 if pos in ("WR", "TE") else 250) * scale if pos != "QB" else 0.0,
                "rec_td": 5 * scale if pos in ("WR", "TE", "RB") else 0.0,
            })
    return pd.DataFrame(rows)


def _incoming():
    return pd.DataFrame([
        {"gsis_id": f"R{i}", "player_name": f"Rookie {i}", "position_group": p, "nfl_position": p,
         "draft_overall": o, "projected_nfl_z": 0.5}
        for i, (p, o) in enumerate([("RB", 4), ("RB", 40), ("RB", 150), ("WR", 8), ("WR", 60),
                                    ("WR", 200), ("TE", 20), ("TE", 120), ("QB", 1), ("QB", 90)])
    ])


class TestTheServedRecalibration:
    def test_it_is_OPT_IN_so_no_existing_caller_changes_behaviour(self):
        """⚠️ Inferring the recalibration from `band_hist` would silently move the point for every
        existing caller — including NF1.4's pinned 'the calibrated band does NOT move the point
        projection' test, which compares a band-fitted curve against a point-only one."""
        h = _hist()
        assert SP.fit_rookie_slot_curves(h).fp_recal == {}
        assert SP.fit_rookie_slot_curves(h, band_hist=h).fp_recal == {}
        assert SP.fit_rookie_slot_curves(h, recal_hist=h).fp_recal != {}

    def test_a_curve_without_recal_hist_emits_a_byte_identical_point(self):
        h, inc = _hist(), _incoming()
        a = SP.project_rookies(inc, SP.fit_rookie_slot_curves(h), 2026)
        b = SP.project_rookies(inc, SP.fit_rookie_slot_curves(h, band_hist=h), 2026)
        assert np.max(np.abs(a["proj_fp_ppr"].to_numpy() - b["proj_fp_ppr"].to_numpy())) == 0.0

    def test_QB_is_untouched_on_the_SERVED_path(self):
        """The exclusion is proven on emitted projections, not asserted from the code."""
        h, inc = _hist(), _incoming()
        base = SP.project_rookies(inc, SP.fit_rookie_slot_curves(h), 2026).set_index("player_id")
        recal = SP.project_rookies(inc, SP.fit_rookie_slot_curves(h, recal_hist=h), 2026
                                   ).set_index("player_id")
        qb = base.index[base["position"] == "QB"]
        assert len(qb) >= 1
        assert np.max(np.abs(base.loc[qb, "proj_fp_ppr"].to_numpy()
                             - recal.loc[qb, "proj_fp_ppr"].to_numpy())) == pytest.approx(0.0)

    def test_the_displayed_point_still_equals_the_SCORED_stat_line(self):
        """⭐ THE INVARIANT THAT MAKES THE STAT LINE TRUSTWORTHY. `proj_fp_ppr` is SCORED from the
        line, so moving the point without carrying the line would leave a board whose displayed
        points disagree with its own yards and touchdowns."""
        h = _hist()
        out = SP.project_rookies(_incoming(), SP.fit_rookie_slot_curves(h, recal_hist=h), 2026)
        rescored = SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy()
        assert np.max(np.abs(rescored - out["proj_fp_ppr"].to_numpy())) == pytest.approx(0.0,
                                                                                          abs=1e-9)

    def test_games_are_NOT_scaled_by_the_recalibration(self):
        """`proj_games` is a count of games, not production — scaling it with the stat line would
        emit a rookie playing more than a season."""
        h, inc = _hist(), _incoming()
        a = SP.project_rookies(inc, SP.fit_rookie_slot_curves(h), 2026).set_index("player_id")
        b = SP.project_rookies(inc, SP.fit_rookie_slot_curves(h, recal_hist=h), 2026
                               ).set_index("player_id")
        assert np.max(np.abs(a["proj_games"].to_numpy() - b["proj_games"].to_numpy())) == 0.0
        assert float(b["proj_games"].max()) <= 17.0

    def test_the_recalibration_helper_is_identity_when_nothing_was_fitted(self):
        curve = SP.RookieSlotCurve()
        fp = np.array([10.0, 200.0])
        assert curve.recalibrate_fp(np.array(["RB", "WR"], dtype=object), fp).tolist() == fp.tolist()

    def test_a_position_with_no_fitted_parameters_passes_through(self):
        curve = SP.RookieSlotCurve(fp_recal={"RB": (0.0, 1.5)})
        got = curve.recalibrate_fp(np.array(["RB", "WR"], dtype=object), np.array([100.0, 100.0]))
        assert got.tolist() == [150.0, 100.0]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. ⭐ NF-D17 — the PLACEMENT clause, validated against reality (PM ruling off NF-D16)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePlacementClauseIsValidatedAgainstReality:
    """NF1.4's face-validity gate has two halves. Its LEVEL half was CAUGHT MIS-SPECIFIED once (the
    first cut referenced the Q90 of ALL drafted rookies, which the realized top rookie cleared in 25
    of 28 cohort-positions — it fired 7/7 and carried zero information) and was corrected by
    re-anchoring on the per-class BEST rookie. The PLACEMENT half had never had that treatment, and
    NF-D16's recalibrated board is what forced the measurement.

    ⭐ The validation came back the OTHER way — the incumbent clause is approximately correct — and
    these tests pin both that result and, more importantly, the ROBUSTNESS convention that makes a
    breach verdict trustworthy."""

    def test_the_cap_mirrors_NF1_4s_level_clause_into_rank_space(self):
        """Points: cap at the Q90 of realized bests (you may not project ABOVE a strong class). Ranks
        are better when SMALLER, so the aggressive tail mirrors to Q10."""
        cap = SP.placement_reference_cap()
        assert cap == pytest.approx(8.8, abs=0.05)

    def test_the_incumbent_top10_clause_is_NOT_mis_specified(self):
        """⭐ THE FINDING. Reality breaches 'no rookie in the overall top 10' in 2 of 7 seasons —
        indistinguishable from the corrected LEVEL clause's own 9/28 — and the honest re-derivation
        lands ~1 board slot from the incumbent's 10. So the placement clause did NOT need
        re-specifying, which is the opposite of what its sibling's history suggested."""
        got = SP.rookie_placement_breach(12)
        assert got["reality_breach_rate_top10"] == pytest.approx(2 / 7, abs=0.01)
        assert 8.0 <= SP.placement_reference_cap() <= 11.0

    def test_rank_6_breaches_across_the_ENTIRE_defensible_band(self):
        """⭐ THE ROBUSTNESS CONVENTION. A verdict that flips inside the defensible quantile band is a
        verdict resting on a threshold somebody chose. NF-D16's board (rank 6) breaches at EVERY
        quantile in [0.05, 0.25] AND against the observed minimum (7) — it is outside the reference's
        entire support, so the quantile choice cannot have manufactured it."""
        got = SP.rookie_placement_breach(6)
        assert got["breach"] is True
        assert got["breaches_even_the_observed_minimum"] is True
        assert got["verdict_is_threshold_invariant"] is True

    def test_a_rank_inside_the_reference_support_does_NOT_breach(self):
        """The clause must be capable of passing, or it is the 'fires 7/7' failure its sibling had."""
        got = SP.rookie_placement_breach(13)
        assert got["breach"] is False and got["verdict_is_threshold_invariant"] is True

    def test_a_verdict_that_flips_inside_the_band_is_reported_as_NOT_invariant(self):
        """The guard has to be able to say 'this answer DOES rest on the threshold I chose' — a
        robustness flag that is always True would report nothing."""
        got = SP.rookie_placement_breach(10)
        assert got["verdict_is_threshold_invariant"] is False, (
            "rank 10 sits inside the Q-band, so the verdict must be flagged threshold-dependent")

    def test_a_board_with_no_rookies_is_not_a_breach(self):
        assert SP.rookie_placement_breach(None)["breach"] is None
