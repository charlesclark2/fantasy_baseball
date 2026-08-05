"""NF-D20 guards — the in-fold global-shrink selection under a per-fold whole-board placement cap.

⭐ EVERY GUARD HERE WAS RED-PROVEN AGAINST DELIBERATELY BROKEN SOURCE BEFORE BEING TRUSTED, and the
AND-composed gates get ONE ISOLATING FIXTURE PER CLAUSE (NF-D17's lesson: a fixture that trips two
clauses at once proves neither, because deleting either one leaves the guard green).

The invariants that matter most, in order:
  1. the SERVING board is never evidence — the structural claim the whole story rests on;
  2. λ is never a typed number — the grid is NF-D16's, by IMPORT, and NF-D18's frontier value is
     unreachable as a literal anywhere in the pre-registration;
  3. C2's two readings are exactly the pre-registered inequality, including the case that motivated
     the incumbent term (a board the SHIPPED product already breaches);
  4. an unevaluable check is never a pass (NF1.7 (a));
  5. the matched foil is non-shippable and is not a candidate.
"""
from __future__ import annotations

import inspect
import re

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import rookie_shrink_selection as SS
from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RPR


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. THE ANTI-LEAK INVARIANT — the serving board is not evidence
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheServingBoardIsNeverEvidence:
    def test_held_out_evidence_removes_the_serving_season(self):
        ev = SS.held_out_evidence({2019: "a", 2024: "b", 2026: "SERVING"}, 2026)
        assert 2026 not in ev, "the serving board reached the evidence set — every rule could see it"
        assert set(ev) == {2019, 2024}

    def test_it_removes_the_serving_season_even_when_the_key_is_a_string(self):
        # the boards are read from filenames, so a str/int key drift is a live way for the guard to
        # be quietly bypassed — the comparison is on int() for exactly this reason
        ev = SS.held_out_evidence({"2019": "a", "2026": "SERVING"}, 2026)
        assert list(ev) == ["2019"]

    def test_the_runner_builds_its_evidence_through_that_function_and_not_a_comprehension(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_d20_infold_shrink as R

        src = inspect.getsource(R.main)
        assert "SS.held_out_evidence(evidence_all" in src, (
            "the runner stopped routing its evidence through `held_out_evidence` — the anti-leak "
            "invariant is then a comprehension nobody tests")

    def test_no_rule_can_see_a_board_at_or_after_its_own_fold(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_d20_infold_shrink as R

        evidence = {y: {"admissible": (0.0, 0.25, 0.5, 0.75, 1.0)} for y in (2019, 2020, 2021)}
        lam_scored = {lam: {"pooled_tier_mae": 1.0 - lam,
                            "per_cohort_pooled": {2019: 1.0 - lam, 2020: 1.0 - lam}}
                      for lam in SS.LAMBDA_GRID}
        picks = R.rule_lambdas({"evidence": "all"}, [2019, 2020, 2021], evidence, lam_scored)
        assert picks[2020]["boards_seen"] == [2019]
        assert picks[2021]["boards_seen"] == [2019, 2020]
        for y, p in picks.items():
            assert all(s < y for s in p["boards_seen"]), (
                f"fold {y} consulted a board at or after its own season — that is leakage")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. λ IS NEVER A TYPED NUMBER
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheLambdaGridIsInheritedNotChosen:
    def test_the_grid_is_derived_from_nf_d16s_own_shrink_grid(self):
        assert SS.LAMBDA_GRID == (0.0,) + tuple(RPR.SHRINK_GRID), (
            "the λ grid stopped being NF-D16's imported SHRINK_GRID — a successor that invents its "
            "own grid can place a point wherever it wants the answer")

    def test_lambda_zero_reproduces_the_incumbent_exactly(self):
        # λ=0 must be the NULL byte-for-byte or the grid is not an honest shrink toward "no change"
        import numpy as np
        p = np.array([10.0, 50.0, 120.0])
        out = SS.blend_toward_incumbent(p, np.array([99.0, 99.0, 99.0]), 0.0)
        assert np.array_equal(out, p)

    def test_the_preregistration_hardcodes_no_frontier_value(self):
        """⛔ NF-D18's frontier λ was read off the 2026 board with the answer in view. It may appear
        in PROSE (the module explains why it may not be used) but never as a numeric literal that
        code could reach."""
        src = inspect.getsource(SS)
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        code = re.sub(r'"""(?:.|\n)*?"""', "", code)          # strip every docstring
        assert not re.search(r"(?<![\w.])0\.75(?![\w])", code), (
            "a frontier value appears as a numeric LITERAL in the pre-registration — the only "
            "legitimate route for 0.75 into this story is NF-D16's imported SHRINK_GRID")

    def test_the_two_degenerate_lambdas_are_outside_the_candidate_interval(self):
        assert SS.OVER_SCALE_LAMBDA > max(SS.LAMBDA_GRID)
        assert SS.EMPTY_EVIDENCE_LAMBDA == min(SS.LAMBDA_GRID) == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. C2 — the per-fold placement constraint, exactly as pre-registered
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestC2IsTheRegisteredInequality:
    def test_the_cap_is_the_strictest_of_the_band_and_the_observed_minimum(self):
        cap = SS.strictest_placement_cap()
        br = SS.placement_clearance(999)
        assert cap == max(list(br["caps_over_q_band"].values()) + [br["observed_minimum"]])

    def test_the_cap_is_delegated_not_transcribed(self, monkeypatch):
        """A story that re-types its bar has two owners for one fact. Move the UPSTREAM CLAUSE and the
        cap must move with it — that is what proves the delegation is real.

        ⚠️ The reference distribution itself is bound as a DEFAULT ARGUMENT of
        `rookie_placement_breach`, so patching the module constant would silently change nothing and
        the guard would pass on a transcribed cap anyway. Patching the CLAUSE is the only version of
        this test that can fail (the NF-D17 vacuous-guard lesson, on a guard rather than a gate)."""
        from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

        before = SS.strictest_placement_cap()
        monkeypatch.setattr(SP, "rookie_placement_breach",
                            lambda rank, *a, **k: {"caps_over_q_band": {"Q10": 41.0},
                                                   "observed_minimum": 40.0,
                                                   "verdict_is_threshold_invariant": True})
        after = SS.strictest_placement_cap()
        assert before == 11.5, "the validated NF-D17 cap moved — check the upstream reference"
        assert after == 41.0, (
            "the cap did not follow its upstream clause — it has been transcribed rather than "
            "delegated, and the two owners will drift")

    def test_a_board_the_incumbent_clears_uses_the_bare_cap(self):
        cap = SS.strictest_placement_cap()
        v = SS.board_admits(cap, 22)
        assert v["admits"] and v["admits_strict"]
        assert SS.board_admits(cap - 1, 22)["admits"] is False

    def test_a_board_the_incumbent_breaches_forbids_making_it_worse_but_not_the_null(self):
        """⭐ THE CASE THAT MOTIVATED THE INCUMBENT TERM, and the reason it is not a loosening chosen
        to get an answer: without it a bare cap refuses λ=0 — i.e. the NULL — on such a board, and a
        constraint that refuses everything has examined nothing (NF1.7 (a))."""
        v_null = SS.board_admits(10, 10)                      # the incumbent, on its own board
        assert v_null["admits"] is True, "C2 refused the NULL — the constraint would be vacuous"
        assert v_null["admits_strict"] is False               # ...and the strict reading does refuse
        assert v_null["incumbent_itself_breaches"] is True
        assert SS.board_admits(7, 10)["admits"] is False, "C2 allowed a pre-existing breach to worsen"
        assert SS.board_admits(11, 10)["admits"] is True      # improving the placement is fine

    def test_an_unevaluable_rank_is_a_refusal_and_never_a_pass(self):
        for args in ((None, 12), (12, None), (None, None)):
            v = SS.board_admits(*args)
            assert v["evaluable"] is False
            assert v["admits"] is False and v["admits_strict"] is False

    def test_admissible_lambdas_reports_both_readings(self):
        ranks = {0.0: 10, 0.25: 10, 0.5: 8}
        assert SS.admissible_lambdas(ranks, 10) == (0.0, 0.25)
        assert SS.admissible_lambdas(ranks, 10, strict=True) == ()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The aggregation rules and the empty-evidence default
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheSelectionRules:
    PER_BOARD = {2019: (0.0, 0.25, 0.5, 0.75, 1.0), 2020: (0.0, 0.25, 0.5), 2021: (0.0, 0.25, 1.0)}

    def test_all_boards_is_the_intersection(self):
        assert SS.aggregate_admissible(self.PER_BOARD, "all") == (0.0, 0.25)

    def test_last_board_reads_only_the_most_recent(self):
        assert SS.aggregate_admissible(self.PER_BOARD, "last") == (0.0, 0.25, 1.0)

    def test_the_reference_arm_sees_no_placement_evidence_at_all(self):
        assert SS.aggregate_admissible(self.PER_BOARD, "none") == tuple(SS.LAMBDA_GRID)

    def test_empty_evidence_falls_back_to_no_correction_not_to_the_whole_grid(self):
        """⭐ THE DIFFERENCE BETWEEN 'nothing refused it' AND 'nothing examined it'. Registered in
        advance precisely so it could not be decided by whichever answer it produced."""
        assert SS.aggregate_admissible({}, "all") == (SS.EMPTY_EVIDENCE_LAMBDA,)
        assert SS.aggregate_admissible({}, "last") == (SS.EMPTY_EVIDENCE_LAMBDA,)

    def test_the_null_is_always_available_so_a_rule_always_has_an_answer(self):
        assert 0.0 in SS.aggregate_admissible({2019: (1.0,)}, "all")

    def test_an_unknown_aggregation_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError):
            SS.aggregate_admissible(self.PER_BOARD, "median")

    def test_select_lambda_is_the_argmin_over_the_allowed_set(self):
        got = SS.select_lambda((0.0, 0.25, 0.5), {0.0: 1.07, 0.25: 1.03, 0.5: 1.10})
        assert got["lam"] == 0.25

    def test_a_tie_breaks_toward_less_correction(self):
        got = SS.select_lambda((0.0, 0.25, 0.5), {0.0: 1.07, 0.25: 1.03, 0.5: 1.03})
        assert got["lam"] == 0.25, "a tie broke toward MORE correction — the unregistered direction"

    def test_it_never_reaches_outside_the_allowed_set(self):
        got = SS.select_lambda((0.0, 0.25), {0.0: 1.07, 0.25: 1.03, 1.0: 0.90})
        assert got["lam"] == 0.25

    def test_an_unscorable_inner_metric_falls_back_to_the_incumbent(self):
        got = SS.select_lambda((0.0, 0.5, 1.0), {})
        assert got["lam"] == SS.EMPTY_EVIDENCE_LAMBDA


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Board provenance — this story reads artifacts it did not build
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestBoardProvenanceIsCheckedNotAssumed:
    @staticmethod
    def _board(base_season, n_rookies=5):
        return pd.DataFrame({
            "player_name": [f"p{i}" for i in range(10)],
            "position": ["RB"] * 10, "proj_fp_ppr": list(range(10, 0, -1)),
            "is_rookie": [True] * n_rookies + [False] * (10 - n_rookies),
            "base_season": [base_season] * 10,
        })

    def test_a_walk_forward_board_passes(self):
        assert SS.board_is_walk_forward(self._board(2024), 2025)["ok"] is True

    def test_a_board_rebuilt_with_later_data_is_refused(self):
        v = SS.board_is_walk_forward(self._board(2025), 2025)
        assert v["walk_forward"] is False and v["ok"] is False

    def test_a_board_with_no_rookie_leg_is_refused(self):
        """`board_placement` is unevaluable without a rookie leg, and C2 treats unevaluable as a
        refusal — so this must be traceable to the DATA rather than look like a constraint result."""
        v = SS.board_is_walk_forward(self._board(2024, n_rookies=0), 2025)
        assert v["has_rookies"] is False and v["ok"] is False

    def test_a_board_with_no_base_season_column_is_refused(self):
        b = self._board(2024).drop(columns=["base_season"])
        assert SS.board_is_walk_forward(b, 2025)["ok"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Anchors, the field, and the matched foil
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAnchorsAndField:
    def test_a_missing_anchor_is_a_hard_failure_not_a_pass(self):
        scored = {k: {SS.SELECTION_METRIC: 1.0} for k in SS._REQUIRED_ANCHORS}
        SS.require_anchors(scored)                            # complete set: no raise
        scored.pop("oracle_ols")
        with pytest.raises(SystemExit):
            SS.require_anchors(scored)

    def test_an_anchor_that_scored_none_is_also_a_hard_failure(self):
        scored = {k: {SS.SELECTION_METRIC: 1.0} for k in SS._REQUIRED_ANCHORS}
        scored["zero_scale"] = {SS.SELECTION_METRIC: None}
        with pytest.raises(SystemExit):
            SS.require_anchors(scored)

    def test_the_two_sided_anchor_set_is_registered(self):
        """NF1.7 (d) (3): one degenerate leaves the metric gameable from the other side. The
        over-correction anchor is what gives the CONSTRAINT something measurable to refuse."""
        for tag in ("zero_scale", "pos_median", "over_scale", "oracle_perplayer", "oracle_ols",
                    "permuted_within", "permuted_across"):
            assert tag in SS._REQUIRED_ANCHORS

    def test_every_candidate_is_shippable_and_the_reference_is_among_them(self):
        cfgs = SS.candidate_configs()
        assert all(c["shippable"] for c in cfgs)
        assert any(c.get("rule") == "unconstrained" for c in cfgs), (
            "the REFERENCE arm left the field — the constraint would then pass having examined "
            "nothing (NF1.7 (a) in an eligibility rule's clothing)")
        assert cfgs[0]["form"] == "incumbent" and cfgs[0]["recalibrates"] is False

    def test_the_field_is_rules_and_never_a_bare_lambda(self):
        for c in SS.candidate_configs():
            assert "lam" not in c, (
                "a candidate carries a fixed λ — the field must be SELECTION RULES, or λ is a knob "
                "and the winner is a re-pick of NF-D16's selected shrink")

    def test_the_matched_foil_is_not_a_candidate(self):
        assert all(c.get("rule") != "blind" for c in SS.candidate_configs())
        assert SS.FOIL_LAMBDA not in [c.get("lam") for c in SS.candidate_configs()]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. THE GATES — one ISOLATING fixture per clause (NF-D17's lesson)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_ship_kwargs():
    """Every clause of `pooled_ship` SATISFIED. Each test below flips exactly ONE — which is what
    makes the guard a test of that clause rather than of whichever clause happens to fail first."""
    return dict(
        winner={"label": "w", "metric": 0.9, "recalibrates": True},
        incumbent_metric=1.0,
        ordering={"per_position": {"RB": {"ok": True}, "TE": {"ok": True}, "WR": {"ok": True}}},
        placement={"holds_out": True}, serving_placement={"clears": True},
        pbo=0.01, dsr=0.99, pvalue=0.01)


class TestPooledShipEachClauseInIsolation:
    def test_the_baseline_fixture_actually_ships(self):
        """⚠️ IF THIS FAILS EVERY TEST BELOW IS VACUOUS — they would all be passing on a fixture that
        was already blocked by some other clause (NF-D17's exact defect)."""
        assert SS.pooled_ship(**_passing_ship_kwargs())["ship"] is True

    @pytest.mark.parametrize("field,value,clause", [
        ("winner", None, "has_eligible_winner"),
        ("placement", {"holds_out": False}, "per_fold_placement_holds_out"),
        ("serving_placement", {"clears": False}, "serving_placement_ok"),
        ("pbo", 0.9, "pbo_ok"),
        ("dsr", 0.1, "dsr_ok"),
        ("pvalue", 0.9, "significant"),
    ])
    def test_one_clause_at_a_time_blocks_the_ship(self, field, value, clause):
        kw = _passing_ship_kwargs()
        kw[field] = value
        got = SS.pooled_ship(**kw)
        assert got["ship"] is False and got[clause] is False

    def test_a_non_recalibrating_winner_blocks(self):
        kw = _passing_ship_kwargs()
        kw["winner"] = {**kw["winner"], "recalibrates": False}
        assert SS.pooled_ship(**kw)["recalibrates"] is False

    def test_a_winner_that_does_not_beat_the_incumbent_blocks(self):
        kw = _passing_ship_kwargs()
        kw["winner"] = {**kw["winner"], "metric": 1.5}
        assert SS.pooled_ship(**kw)["beats_incumbent"] is False

    def test_ordering_is_checked_per_position_and_never_averaged(self):
        """A pooled ρ can sit flat while ONE position's ordering collapses — averaging is the exact
        operation the constraint exists to prevent."""
        kw = _passing_ship_kwargs()
        kw["ordering"] = {"per_position": {"RB": {"ok": True}, "TE": {"ok": False},
                                           "WR": {"ok": True}}}
        assert SS.pooled_ship(**kw)["ordering_ok_every_position"] is False

    def test_an_empty_ordering_report_is_not_a_pass(self):
        kw = _passing_ship_kwargs()
        kw["ordering"] = {"per_position": {}}
        assert SS.pooled_ship(**kw)["ordering_ok_every_position"] is False


def _passing_verdict_kwargs():
    return dict(pooled_ships=True, degenerates_lose=True, permutation_across_beaten=True,
                permutation_within_beaten=True, oracle_respected=True,
                family_ceiling_respected=True, over_scale_breaches=True,
                degenerate_satisfies_constraint=True, boards_walk_forward=True, qb_untouched=True)


class TestStoryVerdictEachAnchorIsAVeto:
    def test_the_baseline_fixture_actually_ships(self):
        assert SS.shrink_verdict(**_passing_verdict_kwargs())["ship"] is True

    @pytest.mark.parametrize("clause", list(_passing_verdict_kwargs()))
    def test_each_anchor_alone_vetoes(self, clause):
        kw = {**_passing_verdict_kwargs(), clause: False}
        assert SS.shrink_verdict(**kw)["ship"] is False

    def test_both_directions_of_the_constraint_check_are_required(self):
        """NF1.8 read BOTH ways: a CONSTRAINT a degenerate satisfies is fine (the metric eliminates
        it), and a constraint nothing is ever measured FAILING has examined nothing either."""
        assert SS.shrink_verdict(**{**_passing_verdict_kwargs(),
                                    "degenerate_satisfies_constraint": False})["ship"] is False
        assert SS.shrink_verdict(**{**_passing_verdict_kwargs(),
                                    "over_scale_breaches": False})["ship"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Monotonicity is MEASURED, never assumed (NF-D16 method lock 2)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestMonotonicityIsMeasured:
    def test_a_monotone_metric_is_reported_as_such(self):
        got = SS.monotonicity({0.0: 1.07, 0.5: 0.99, 1.0: 0.94})
        assert got["metric_monotone_decreasing"] is True and got["metric_argmin_lambda"] == 1.0

    def test_a_non_monotone_metric_is_caught_and_the_argmin_is_still_right(self):
        got = SS.monotonicity({0.0: 1.07, 0.5: 0.90, 1.0: 0.94})
        assert got["metric_monotone_decreasing"] is False and got["metric_argmin_lambda"] == 0.5

    def test_rank_monotonicity_is_reported_when_ranks_are_supplied(self):
        got = SS.monotonicity({0.0: 1.0, 1.0: 0.9}, {0.0: 12, 1.0: 6})
        assert got["rank_monotone_nonincreasing"] is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. Scope — QB is excluded by the ONE gate every arm passes through
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestQbIsUntouchableByConstruction:
    def test_no_lambda_can_move_a_qb(self):
        import numpy as np
        point = np.array([200.0, 150.0, 120.0])
        pos = np.array(["QB", "RB", "WR"], dtype=object)
        adj = np.array([999.0, 999.0, 999.0])
        for lam in tuple(SS.LAMBDA_GRID) + (SS.OVER_SCALE_LAMBDA,):
            out = SS.apply_position_adjustment(
                point, pos, SS.blend_toward_incumbent(point, adj, lam))
            assert out[0] == point[0], f"QB moved at λ={lam} — the exclusion is not structural"

    def test_qb_is_not_in_the_recalibrated_scope(self):
        assert "QB" not in SS.SHRINK_POSITIONS and SS.EXCLUDED_POSITIONS == ("QB",)
