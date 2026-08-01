"""NF-D15 — the AVAILABILITY-SCALED rookie POINT projection (RB/TE/WR).

These tests guard the four things that decide whether NF-D15's answer means anything:

  1. ⛔ **THE QB EXCLUSION IS STRUCTURAL.** NF-D14 MEASURED the QB double-pricing (+16.8% MAE, bias
     −10.66 COLD → +11.36 HOT); NF-D15 is forbidden to re-open it. The exclusion lives in exactly one
     function, and these tests prove no arm — candidate, degenerate or ORACLE — can route around it.
  2. ⭐ **THE MATCHED FOIL IS ACTUALLY MATCHED.** The story's whole attribution rests on the foil
     having the IDENTICAL per-position mean scale as its partner, so the paired delta is the
     per-player content and cannot be a level difference in disguise (NF-D10).
  3. **THE SHRINK GRID'S ZERO END IS THE NULL, EXACTLY** — not approximately. That is what makes the
     grid an honest shrink toward "no availability information" rather than a knob that quietly
     changes shape at its end (NF-D14's `blend` convention).
  4. **NO GATE PASSES VACUOUSLY.** A missing anchor, an unscorable ρ, an un-consumed BH-FDR — every
     one of those is a check that reports green having examined nothing, and each has burned this
     program before (NF1.7 lesson (a), E7.12's computed-but-unconsumed statistic).

Pure/fast: no IO, no fixtures on disk, no bake-off.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import rookie_point_scaling as PS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ⛔ The QB exclusion — structural, not a convention every arm has to remember
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestQbExclusionIsStructural:
    def test_qb_is_passed_through_whatever_scale_is_asked_for(self):
        pos = np.array(["QB", "RB", "WR", "TE", "QB"], dtype=object)
        point = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
        got = PS.apply_position_scale(point, pos, np.full(5, 2.0))
        assert got[0] == 100.0 and got[4] == 100.0, "a scale reached QB"
        assert got[1] == got[2] == got[3] == 200.0, "the scaled positions were not scaled"

    def test_even_a_zero_scale_cannot_blank_a_qb(self):
        """The `zero_scale` degenerate is exactly the arm most likely to be written without the
        exclusion in mind — and an anchor that silently scaled QB would be answering a different
        question than every candidate it is compared against."""
        pos = np.array(["QB", "RB"], dtype=object)
        got = PS.apply_position_scale(np.array([50.0, 50.0]), pos, np.zeros(2))
        assert got[0] == 50.0
        assert got[1] == 0.0

    def test_a_nan_scale_leaves_the_projection_alone_rather_than_blanking_it(self):
        """The honest degradation of 'I have no availability read for this player' is 'leave his
        projection alone', never 'project him at zero' — a rookie must not fall off the board because
        a thin in-fold cell had nothing to say about him."""
        got = PS.apply_position_scale(np.array([40.0, 40.0]), np.array(["RB", "WR"], dtype=object),
                                      np.array([np.nan, np.inf]))
        assert got.tolist() == [40.0, 40.0]

    def test_the_scale_is_clipped_into_its_physical_band(self):
        got = PS.apply_position_scale(np.array([10.0, 10.0]), np.array(["RB", "RB"], dtype=object),
                                      np.array([-5.0, 99.0]))
        assert got[0] == 0.0
        assert got[1] == 10.0 * PS.SCALE_CLIP[1]

    def test_scaled_and_excluded_positions_partition_the_rookie_universe(self):
        assert not set(PS.SCALED_POSITIONS) & set(PS.EXCLUDED_POSITIONS)
        assert "QB" in PS.EXCLUDED_POSITIONS
        assert set(PS.SCALED_POSITIONS) | set(PS.EXCLUDED_POSITIONS) == {"QB", "RB", "WR", "TE"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The shrink grid — its zero end IS the null, exactly
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestShrinkGrid:
    def test_lambda_zero_reproduces_the_incumbent_exactly(self):
        k = np.array([0.1, 0.5, 1.0, 2.0, 7.3])
        assert np.array_equal(PS.shrink_scale(k, 0.0), np.ones(5))

    def test_lambda_one_is_the_identity(self):
        k = np.array([0.1, 0.5, 1.0, 2.0])
        assert np.allclose(PS.shrink_scale(k, 1.0), k)

    def test_shrink_is_monotone_toward_one_and_never_crosses_it(self):
        """A geometric shrink cannot turn a scale below 1 into one above it (or vice versa) at any
        λ ≥ 0 — a linear shrink toward 1 has the same property, but a linear shrink of a
        MULTIPLICATIVE quantity is the wrong operation and would make λ non-comparable across arms
        whose ratios sit on opposite sides of 1."""
        for k in (0.4, 0.9, 1.1, 2.5):
            vals = [float(PS.shrink_scale(np.array([k]), lam)[0]) for lam in (0.25, 0.5, 0.75, 1.0)]
            assert all(np.sign(v - 1.0) == np.sign(k - 1.0) for v in vals)
            assert vals == sorted(vals, reverse=k < 1.0)

    def test_a_zero_scale_is_not_shrunk_into_respectability(self):
        assert PS.shrink_scale(np.array([0.0]), 0.5)[0] == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. ⭐ The matched foil — the story's attribution instrument
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestMatchedFoil:
    def test_the_foil_carries_the_identical_per_position_mean_scale(self):
        """⭐ THE PROPERTY THE WHOLE ATTRIBUTION RESTS ON. If the foil's average level differed from
        its partner's, the paired delta between them would be a LEVEL difference wearing the clothes
        of a per-player one, and the story's central claim would be unfalsifiable.

        ⚠️ The fixture is deliberately SKEWED (mean ≠ median at every position). A symmetric fixture
        makes this test pass against a median-based foil too — i.e. it would pin the *shape* of the
        answer while pinning none of its content. Verified by mutation: swapping `mean` for `median`
        in `position_mean_scale` must fail this test."""
        pos = np.array(["RB", "RB", "RB", "WR", "WR", "WR", "TE", "TE", "TE"], dtype=object)
        k = np.array([0.5, 0.6, 3.0, 0.4, 2.0, 2.4, 0.7, 0.8, 2.7])
        foil = PS.position_mean_scale(k, pos)
        for p in ("RB", "WR", "TE"):
            sel = pos == p
            assert not np.isclose(k[sel].mean(), np.median(k[sel])), "fixture is not skewed"
            assert np.isclose(foil[sel].mean(), k[sel].mean())
            assert not np.isclose(foil[sel][0], np.median(k[sel])), "the foil is a MEDIAN, not a MEAN"

    def test_the_foil_is_constant_within_a_position(self):
        pos = np.array(["RB", "RB", "RB", "WR"], dtype=object)
        foil = PS.position_mean_scale(np.array([0.2, 3.0, 1.0, 5.0]), pos)
        assert len(set(foil[pos == "RB"].tolist())) == 1

    def test_the_foil_does_zero_ordering_harm_by_construction(self):
        """A constant within a position preserves the within-position order exactly — which is why a
        foil that MATCHES the availability arm's score is the worse outcome for this story, not a
        consolation: it would deliver the same accuracy with none of the ordering risk."""
        pos = np.array(["RB"] * 5, dtype=object)
        point = np.array([90.0, 80.0, 70.0, 60.0, 50.0])
        foil = PS.position_mean_scale(np.array([0.5, 2.0, 1.0, 1.4, 0.7]), pos)
        got = PS.apply_position_scale(point, pos, foil)
        assert list(np.argsort(-got)) == list(np.argsort(-point))

    def test_a_position_with_no_finite_scale_falls_back_to_the_incumbent_not_nan(self):
        """A NaN foil would be UNSCORABLE, and an unscorable foil makes the attribution check pass on
        nothing — the NF1.7 vacuous-anchor failure in the one place this story can least afford it."""
        pos = np.array(["RB", "RB"], dtype=object)
        assert PS.position_mean_scale(np.array([np.nan, np.nan]), pos).tolist() == [1.0, 1.0]

    def test_every_availability_arm_has_a_matched_foil_at_the_same_base_and_lambda(self):
        cfgs = PS.candidate_configs()
        foils = {(c["base"], c["lam"]) for c in cfgs if c["family"] == "mean_ratio"}
        avail = [c for c in cfgs if c["uses_availability"]]
        assert avail, "the field carries no availability arms at all"
        missing = [c["label"] for c in avail if (c["base"], c["lam"]) not in foils]
        assert not missing, f"availability arms with no matched foil: {missing}"

    def test_the_foil_is_never_counted_as_an_availability_arm(self):
        for c in PS.candidate_configs():
            if c["family"] == "mean_ratio":
                assert c["uses_availability"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The pre-registered field
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestCandidateField:
    def test_the_null_is_in_the_field_and_is_the_identity(self):
        cfgs = PS.candidate_configs()
        null = [c for c in cfgs if c["family"] == "incumbent"]
        assert len(null) == 1
        k = PS.shrink_scale(np.array([2.0, 0.3]), null[0]["lam"])
        assert k.tolist() == [1.0, 1.0]

    def test_the_field_carries_at_least_three_candidate_classes_plus_a_learned_foil(self):
        """§0.5: ≥3 pre-registered candidate model classes AND a direct-learned foil."""
        bases = {c["base"] for c in PS.candidate_configs() if c["family"] == "ratio"}
        assert len(bases) >= 3, bases
        assert any(c["family"] == "learned" for c in PS.candidate_configs())

    def test_config_keys_are_unique(self):
        keys = [PS.config_key(c) for c in PS.candidate_configs()]
        assert len(keys) == len(set(keys))

    def test_smoke_is_a_strict_subset_of_the_real_search(self):
        real = {PS.config_key(c) for c in PS.candidate_configs()}
        smoke = {PS.config_key(c) for c in PS.candidate_configs(smoke=True)}
        assert smoke < real


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The REUSE guard — NF-D15 consumes NF-D14's prior, it does not refit it
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestReuseGuard:
    def test_the_nf_d14_winner_passes(self):
        PS.require_reused_prior(dict(PS.NF_D14_PRIOR))

    def test_a_different_prior_fails_loudly(self):
        """A regenerated NF-D14 with a new leg-1 winner would make every NF-D15 number a statement
        about a prior nobody selected, and nothing else in the harness would notice."""
        with pytest.raises(SystemExit, match="does NOT refit"):
            PS.require_reused_prior({**PS.NF_D14_PRIOR, "tier": "round"})

    def test_the_capital_sibling_is_not_the_winner(self):
        """`ratio_residual`'s denominator has to be a DIFFERENT (capital-only) read, or the arm would
        be the constant 1 and would silently be the null."""
        assert PS.NF_D14_CAPITAL_SIBLING != PS.NF_D14_PRIOR


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The anchor guard — a missing anchor is a hard failure, never a pass
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAnchorGuard:
    def _full(self):
        return {k: {PS.SELECTION_METRIC: 1.0} for k in
                ("oracle_perplayer", "oracle_posconst", "permuted", "zero_scale", "pos_median")}

    def test_a_complete_anchor_set_passes(self):
        PS.require_anchors(self._full())

    def test_a_missing_anchor_raises(self):
        d = self._full()
        d.pop("permuted")
        with pytest.raises(SystemExit, match="pass on NOTHING"):
            PS.require_anchors(d)

    def test_an_anchor_that_scored_none_raises(self):
        """NF1.7 lesson (a) exactly: the anchor is PRESENT but unscored, so `winner < anchor` compares
        nothing and reports green. Presence is not the check — a score is."""
        d = self._full()
        d["zero_scale"] = {PS.SELECTION_METRIC: None}
        with pytest.raises(SystemExit, match="pass on NOTHING"):
            PS.require_anchors(d)

    def test_both_oracle_resolutions_are_required(self):
        """A per-player arm may legitimately beat a per-position CONSTANT oracle (NF1.7 (b)/NF1.9 (f):
        matched family AND matched resolution), so the constant oracle alone cannot be the floor. Both
        resolutions are required so the run can tell a capacity effect from an inversion."""
        for missing in ("oracle_perplayer", "oracle_posconst"):
            d = self._full()
            d.pop(missing)
            with pytest.raises(SystemExit):
                PS.require_anchors(d)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Do-no-ordering-harm
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestOrderingCheck:
    def test_an_improvement_passes(self):
        got = PS.ordering_check({"RB": 0.62, "TE": 0.61, "WR": 0.63},
                                {"RB": 0.59, "TE": 0.60, "WR": 0.62})
        assert got["ok"] and got["strict_ok"]

    def test_a_drop_inside_the_tolerance_passes_but_is_not_strict(self):
        got = PS.ordering_check({"RB": 0.58, "TE": 0.61, "WR": 0.63},
                                {"RB": 0.59, "TE": 0.60, "WR": 0.62})
        assert got["ok"] and not got["strict_ok"]

    def test_a_drop_past_the_tolerance_fails(self):
        got = PS.ordering_check({"RB": 0.40, "TE": 0.61, "WR": 0.63},
                                {"RB": 0.59, "TE": 0.60, "WR": 0.62})
        assert not got["ok"]
        assert got["per_position"]["RB"]["ok"] is False

    def test_one_position_collapsing_cannot_be_averaged_away(self):
        """⭐ THE REASON THIS IS PER POSITION. Pooled, these three ρ average ABOVE the incumbent's
        pooled ρ — a mean-based constraint would wave through an arm that destroyed RB's ordering."""
        cand = {"RB": 0.10, "TE": 0.90, "WR": 0.90}
        inc = {"RB": 0.59, "TE": 0.60, "WR": 0.62}
        assert np.mean(list(cand.values())) > np.mean(list(inc.values()))
        assert not PS.ordering_check(cand, inc)["ok"]

    def test_an_unscorable_candidate_rho_is_a_failure_not_a_skip(self):
        """The way a scale arm loses its ρ is by going CONSTANT within a position — which is exactly
        the collapse the constraint exists to catch. Treating it as 'no measurement, carry on' would
        let the worst arm through unexamined."""
        got = PS.ordering_check({"RB": None, "TE": 0.61, "WR": 0.63},
                                {"RB": 0.59, "TE": 0.60, "WR": 0.62})
        assert not got["ok"]
        assert "UNSCORABLE" in got["per_position"]["RB"]["note"]

    def test_the_tolerance_is_nf1_4s_own_constant(self):
        from quant_sports_intel_models.football.nfl.fantasy import nf1_4_rookie as M14
        assert PS.ORDERING_DO_NO_HARM == M14.ORDERING_DO_NO_HARM


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The ship decisions — and the BH-FDR being CONSUMED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ship(**over):
    base = dict(position="RB",
                winner={"uses_availability": True, "metric": 60.0},
                incumbent_metric=70.0,
                ordering={"per_position": {"RB": {"ok": True}}},
                pbo=0.05, dsr=0.99, fdr_survives=True)
    return PS.per_position_ship(**{**base, **over})


class TestPerPositionShip:
    def test_a_clean_position_ships(self):
        assert _ship()["ship"] is True

    def test_a_failed_bh_fdr_blocks_the_ship(self):
        """⭐ E7.12's landmine closed: a BH-FDR that is computed, printed, and then never allowed to
        gate anything is a statistic that does no work. Here it is an ARGUMENT to the decision."""
        got = _ship(fdr_survives=False)
        assert got["ship"] is False and got["fdr_ok"] is False

    def test_a_matched_foil_winner_cannot_ship_as_an_availability_result(self):
        """A `mean_ratio` win is a RECALIBRATION finding — a different change with a different risk
        profile — and must not be reported as this story's claim."""
        got = _ship(winner={"uses_availability": False, "metric": 60.0})
        assert got["ship"] is False and got["uses_availability"] is False

    def test_not_beating_the_incumbent_blocks_the_ship(self):
        assert _ship(winner={"uses_availability": True, "metric": 80.0})["ship"] is False

    def test_ordering_harm_blocks_the_ship(self):
        got = _ship(ordering={"per_position": {"RB": {"ok": False}}})
        assert got["ship"] is False and got["ordering_ok"] is False

    def test_a_missing_ordering_record_blocks_rather_than_passes(self):
        """An absent measurement must never read as a pass."""
        assert _ship(ordering={"per_position": {}})["ship"] is False

    def test_each_deflation_gate_blocks_on_its_own(self):
        assert _ship(pbo=0.5)["ship"] is False
        assert _ship(dsr=0.5)["ship"] is False
        assert _ship(pbo=None)["ship"] is False
        assert _ship(dsr=None)["ship"] is False

    def test_no_eligible_winner_is_a_recorded_result_not_a_crash(self):
        got = _ship(winner=None)
        assert got["ship"] is False and got["has_eligible_winner"] is False


class TestStoryVerdict:
    def _v(self, **over):
        base = dict(positions_shipped=("RB",), degenerates_lose=True, permutation_beaten=True,
                    oracle_respected=True, qb_untouched=True)
        return PS.point_scaling_verdict(**{**base, **over})

    def test_a_clean_run_ships(self):
        assert self._v()["ship"] is True

    def test_nothing_shipping_is_a_null(self):
        assert self._v(positions_shipped=())["ship"] is False

    @pytest.mark.parametrize("veto", ["degenerates_lose", "permutation_beaten", "oracle_respected",
                                      "qb_untouched"])
    def test_each_global_anchor_vetoes_the_whole_run(self, veto):
        """⭐ A degenerate winning the metric does not mean one position was unlucky — it means the
        MEASUREMENT is untrustworthy everywhere, so no per-position result computed from it may ship."""
        assert self._v(**{veto: False})["ship"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. `safe_ratio` — a thin in-fold cell must not emit a 100× scale
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestSafeRatio:
    def test_a_normal_ratio_is_just_a_ratio(self):
        assert np.allclose(PS.safe_ratio(np.array([6.0]), np.array([12.0])), [0.5])

    def test_a_tiny_denominator_returns_nan_rather_than_a_blow_up(self):
        """A 0.1-game denominator off a thin position × depth-tier cell would emit a 100× scale that
        single-handedly decides a position's MAE. That is a fitting artefact, not availability."""
        assert np.isnan(PS.safe_ratio(np.array([10.0]), np.array([0.1]))[0])

    def test_missing_inputs_return_nan(self):
        got = PS.safe_ratio(np.array([np.nan, 5.0]), np.array([10.0, np.nan]))
        assert np.isnan(got).all()

    def test_nan_from_safe_ratio_degrades_to_the_incumbent(self):
        """The two halves compose: an unusable ratio becomes NaN here and NaN becomes 'leave the
        projection alone' in `apply_position_scale`."""
        k = PS.safe_ratio(np.array([10.0]), np.array([0.1]))
        assert PS.apply_position_scale(np.array([42.0]), np.array(["RB"], dtype=object), k)[0] == 42.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The NF-D14 §6 wiring proof
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestNfD14Reproduction:
    def test_an_exact_reproduction_passes(self):
        assert PS.reproduces_nf_d14_section6(
            {p: dict(v) for p, v in PS.NF_D14_SECTION6.items()})["ok"]

    def test_a_drifted_rebuild_fails(self):
        m = {p: dict(v) for p, v in PS.NF_D14_SECTION6.items()}
        m["RB"]["mae_scaled"] += 1.0
        assert not PS.reproduces_nf_d14_section6(m)["ok"]

    def test_qb_is_reported_but_never_checked(self):
        """NF-D14 §6 scaled QB; NF-D15 cannot. Checking the QB row would be a check that fails for the
        one reason this story is proud of."""
        m = {p: dict(v) for p, v in PS.NF_D14_SECTION6.items()}
        m["QB"]["mae_scaled"] = 999.0
        got = PS.reproduces_nf_d14_section6(m)
        assert got["ok"]
        assert "QB" not in got["per_position"]

    def test_an_unmeasured_position_is_a_failure_not_a_pass(self):
        m = {p: dict(v) for p, v in PS.NF_D14_SECTION6.items() if p != "TE"}
        assert not PS.reproduces_nf_d14_section6(m)["ok"]

    def test_the_transcribed_qb_row_still_carries_nf_d14s_finding(self):
        """The QB numbers are the reason QB is out of scope; if they were ever edited to something
        benign the exclusion would look arbitrary."""
        qb = PS.NF_D14_SECTION6["QB"]
        assert qb["mae_scaled"] > qb["mae_base"], "the QB double-pricing has been edited away"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 11. End-to-end on synthetic data — the scale composes into a real projection change
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_scaled_board_moves_only_the_scaled_positions_and_preserves_totals_shape():
    rng = np.random.default_rng(0)
    n = 200
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n)
    point = rng.uniform(10, 250, size=n)
    k = rng.uniform(0.6, 1.6, size=n)
    got = PS.apply_position_scale(point, pos, k)
    qb = pos == "QB"
    assert np.array_equal(got[qb], point[qb])
    assert not np.allclose(got[~qb], point[~qb])
    # the change is multiplicative, so nothing can go negative or NaN
    assert np.isfinite(got).all() and (got >= 0).all()


def test_scaled_positions_only_selects_the_rows_the_story_may_touch():
    df = pd.DataFrame({"position_group": ["QB", "rb", "WR", "TE", "K"]})
    got = PS.scaled_positions_only(df)
    assert sorted(got["position_group"].str.upper()) == ["RB", "TE", "WR"]
