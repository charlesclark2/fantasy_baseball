"""NF-D17 guards — the track-record Δρ population-sensitivity re-computation.

Two jobs, and the second is the one that matters for a PUBLIC claim:
  1. the harness computes what the pre-registration says it computes (population filters, anchors,
     paired bootstrap, admissibility, decision rule);
  2. ⭐ **the pre-registration's own discipline cannot be quietly relaxed** — the decision rule cannot
     recommend a change on a bigger point estimate alone, the forensic leg cannot count a reading the
     pre-registration already ruled inadmissible, and the anchors cannot pass vacuously (NF1.7 (a)).

Every guard below was checked to go RED on deliberately-broken source before being trusted (see the
docstrings that say so explicitly).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import track_record_population as PRE
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_d17_population_sensitivity as H,
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a tiny synthetic universe with a KNOWN answer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _base(n=60, seed=0):
    """A base frame where our projection is a noisy-but-informative read on the realized outcome."""
    rng = np.random.default_rng(seed)
    real = rng.normal(100, 30, n)
    return pd.DataFrame({
        "player_id": [f"p{i:03d}" for i in range(n)],
        "position": np.tile(["QB", "RB", "WR", "TE"], n // 4),
        "proj_fp_ppr": real + rng.normal(0, 12, n),
        "real_fp_ppr": real,
    })


def _system(base, ids, seed=1, noise=25.0):
    rng = np.random.default_rng(seed)
    d = base[base["player_id"].isin(ids)]
    return pd.DataFrame({
        "player_id": d["player_id"].to_numpy(),
        "position": d["position"].to_numpy(),
        "score": d["real_fp_ppr"].to_numpy() + rng.normal(0, noise, len(d)),
    })


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3 — the population filters do what the pre-registration says
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPopulationFilters:
    def test_p0_is_the_pairwise_intersection_only(self):
        base = _base()
        ids = set(base["player_id"][:40])
        systems = {"adp": _system(base, ids)}
        spec = PRE.PopulationSpec("P0_shipped", "P0", ())
        m = H.aligned_frame(base, systems, spec, "adp")
        assert set(m["player_id"]) == ids

    def test_p1_requires_every_co_source_and_is_the_true_intersection(self):
        """RED when `aligned_frame` drops the `require_sources` loop."""
        base = _base()
        ffc = set(base["player_id"][:40])
        mfl = set(base["player_id"][20:55])
        systems = {"adp": _system(base, ffc), "mfl_adp": _system(base, mfl, seed=2)}
        spec = PRE.PopulationSpec("P1_cross_source_matched", "P1", PRE.HEADLINE_ELIGIBLE_SOURCES)
        m = H.aligned_frame(base, systems, spec, "adp")
        assert set(m["player_id"]) == ffc & mfl
        # and it is SYMMETRIC — the same rows whichever source is under test
        m2 = H.aligned_frame(base, systems, spec, "mfl_adp")
        assert set(m2["player_id"]) == set(m["player_id"])

    def test_p1_is_none_not_silently_smaller_when_a_required_source_is_absent(self):
        """A season where a co-source has no data must yield NO P1 row — never a quietly
        different (larger) population wearing the P1 label. RED when the `return None` becomes a
        `continue`."""
        base = _base()
        systems = {"adp": _system(base, set(base["player_id"][:40]))}
        spec = PRE.PopulationSpec("P1_cross_source_matched", "P1", PRE.HEADLINE_ELIGIBLE_SOURCES)
        assert H.aligned_frame(base, systems, spec, "adp") is None

    @pytest.mark.parametrize("side,col", [("by_source", "sys_score"), ("by_us", "proj_fp_ppr")])
    def test_depth_truncation_keeps_the_top_k_of_the_named_side(self, side, col):
        base = _base()
        ids = set(base["player_id"])
        systems = {"adp": _system(base, ids)}
        spec = PRE.PopulationSpec(f"P2_depth20_{side}", "P2", (), depth=20, truncate_by=side)
        m = H.aligned_frame(base, systems, spec, "adp")
        assert len(m) == 20
        full = H.aligned_frame(base, systems, PRE.PopulationSpec("P0", "P0", ()), "adp")
        assert set(m["player_id"]) == set(full.nlargest(20, col)["player_id"])

    def test_depth_truncation_is_deterministic_under_ties(self):
        """A tie at the truncation boundary must resolve the same way every run, or the memo's n and
        Δρ are not reproducible. RED when the `player_id` tie-break is removed."""
        base = _base(n=40)
        systems = {"adp": pd.DataFrame({
            "player_id": base["player_id"], "position": base["position"],
            "score": np.zeros(len(base)),        # every score identical => all ties
        })}
        spec = PRE.PopulationSpec("P2", "P2", (), depth=10, truncate_by="by_source")
        a = H.aligned_frame(base, systems, spec, "adp")
        b = H.aligned_frame(base, systems, spec, "adp")
        assert list(a["player_id"]) == list(b["player_id"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §5 — the anchors are real checks, not decoration
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAnchors:
    def _frames(self):
        base = _base(n=80)
        systems = {"adp": _system(base, set(base["player_id"]))}
        m = H.aligned_frame(base, systems, PRE.PopulationSpec("P0", "P0", ()), "adp")
        return {2024: m}

    def test_identity_anchor_is_exactly_zero_and_oracle_dominates_and_random_loses(self):
        frames = self._frames()
        real = H._pair_delta(frames[2024], "proj_fp_ppr")
        a = H.run_anchors(frames, PRE.PopulationSpec("P0", "P0", ()), "adp", real,
                          np.random.default_rng(7))
        assert a["A1_identity"]["delta"] == pytest.approx(0.0, abs=1e-9)
        assert a["A2_oracle_floor"]["delta"] >= real
        assert a["A3_degenerate_random"]["delta"] < 0
        assert a["A3_degenerate_random"]["delta"] < real
        assert a["all_pass"] is True

    def test_an_anchor_that_cannot_evaluate_FAILS_it_does_not_pass_vacuously(self):
        """NF1.7 (a): a `None` anchor must be a FAILURE, never a silent pass. RED if
        `run_anchors` treats an unevaluable anchor as clean."""
        empty = {2024: pd.DataFrame(columns=["player_id", "position", "proj_fp_ppr",
                                             "real_fp_ppr", "sys_score"])}
        a = H.run_anchors(empty, PRE.PopulationSpec("P0", "P0", ()), "adp", 0.02,
                          np.random.default_rng(7))
        assert a["all_pass"] is False
        for key in ("A1_identity", "A2_oracle_floor", "A3_degenerate_random"):
            assert a[key]["evaluated"] is False
            assert a[key]["pass"] is False


class TestReproductionAnchor:
    def test_reproduction_passes_only_on_the_shipped_values_and_season_counts(self):
        good = [{"population": "P0_shipped", "source": s, "delta_rho_mean": v,
                 "n_seasons": PRE.SHIPPED_N_SEASONS[s]}
                for s, v in PRE.SHIPPED_DELTA_RHO.items()]
        assert H.check_reproduction(good)["all_pass"] is True

    def test_reproduction_fails_on_a_drifted_delta(self):
        bad = [{"population": "P0_shipped", "source": s,
                "delta_rho_mean": v + 10 * PRE.REPRODUCTION_TOLERANCE,
                "n_seasons": PRE.SHIPPED_N_SEASONS[s]}
               for s, v in PRE.SHIPPED_DELTA_RHO.items()]
        assert H.check_reproduction(bad)["all_pass"] is False

    def test_reproduction_fails_on_a_right_number_over_the_wrong_season_count(self):
        """The right Δρ over a different season set is a DIFFERENT claim. RED if the season-count
        clause is dropped from `check_reproduction`."""
        bad = [{"population": "P0_shipped", "source": s, "delta_rho_mean": v,
                "n_seasons": PRE.SHIPPED_N_SEASONS[s] - 1}
               for s, v in PRE.SHIPPED_DELTA_RHO.items()]
        assert H.check_reproduction(bad)["all_pass"] is False

    def test_a_missing_p0_result_is_a_failure_not_an_absent_check(self):
        assert H.check_reproduction([])["all_pass"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §6 — the bootstrap is PAIRED
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestBootstrap:
    def test_a_source_identical_to_us_has_an_interval_pinned_at_zero(self):
        """The paired construction's sharpest test: if the two sides are the SAME column, every draw
        must give Δ = 0 exactly. An UNPAIRED bootstrap (resampling the sides independently) would
        produce a wide interval here — so this is RED on the exact defect it guards."""
        base = _base(n=80)
        m = base.assign(sys_score=base["proj_fp_ppr"])
        b = H.bootstrap_delta({2024: m}, draws=60, seed=1, level=0.90)
        assert b["evaluated"] is True
        assert b["lo"] == pytest.approx(0.0, abs=1e-9)
        assert b["hi"] == pytest.approx(0.0, abs=1e-9)

    def test_a_clearly_better_arm_gets_an_interval_excluding_zero(self):
        base = _base(n=120, seed=3)
        rng = np.random.default_rng(4)
        m = base.assign(sys_score=base["real_fp_ppr"] + rng.normal(0, 200, len(base)))
        b = H.bootstrap_delta({2024: m}, draws=200, seed=1, level=0.90)
        assert b["excludes_zero"] is True and b["lo"] > 0

    def test_bootstrap_reports_unevaluated_rather_than_a_fake_interval(self):
        empty = {2024: pd.DataFrame(columns=["player_id", "position", "proj_fp_ppr",
                                             "real_fp_ppr", "sys_score"])}
        assert H.bootstrap_delta(empty, draws=10, seed=1, level=0.9) == {"evaluated": False}

    def test_bootstrap_is_seeded_and_reproducible(self):
        base = _base(n=80)
        m = base.assign(sys_score=base["real_fp_ppr"] + 5.0)
        a = H.bootstrap_delta({2024: m}, draws=50, seed=99, level=0.9)
        b = H.bootstrap_delta({2024: m}, draws=50, seed=99, level=0.9)
        assert a == b

    def test_overlap_helper_is_none_when_either_side_is_unevaluated(self):
        """An unevaluable comparison must not silently read as 'overlapping' (which the decision rule
        treats as NOT materially different — a fail-open). RED if `intervals_overlap` returns a bool
        for an unevaluated input."""
        ok = {"evaluated": True, "lo": 0.1, "hi": 0.2}
        assert H.intervals_overlap(ok, {"evaluated": False}) is None
        assert H.intervals_overlap(ok, {"evaluated": True, "lo": 0.3, "hi": 0.4}) is False
        assert H.intervals_overlap(ok, {"evaluated": True, "lo": 0.15, "hi": 0.4}) is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §7 — the forensic leg cannot launder an inadmissible reading into a "reproduction"
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestForensicAdmissibility:
    def test_a_one_sided_depth_cell_can_never_count_as_a_reproduction(self):
        """⭐ THE GUARD THAT MATTERS. This run's closest cell to the deferred +0.088 IS a
        `P2_*_by_source` reading (gap 0.009, inside the ±0.02 tolerance) — so without this rule the
        memo would report a REPRODUCTION of the deferred figure by a method the pre-registration
        itself calls meaningless. RED if `place_deferred_figures` stops filtering P2."""
        results = [
            {"population": "P2_depth100_by_source", "source": "mfl_adp", "delta_rho_mean": 0.088},
            {"population": "P0_shipped", "source": "mfl_adp", "delta_rho_mean": 0.173},
        ]
        f = H.place_deferred_figures(results)["mfl_adp"]
        assert f["reproduced"] is False
        assert f["closest_population"] == "P0_shipped"
        # …but the near-match is still DISCLOSED, never hidden
        assert f["closest_inadmissible"]["population"] == "P2_depth100_by_source"
        assert f["closest_inadmissible"]["delta"] == 0.088

    def test_an_admissible_exact_hit_does_count(self):
        results = [{"population": "P1_cross_source_matched", "source": "adp",
                    "delta_rho_mean": PRE.DEFERRED_NF3_2_FIGURES["adp"]}]
        assert H.place_deferred_figures(results)["adp"]["reproduced"] is True

    def test_no_admissible_candidate_reports_not_reproduced_rather_than_raising(self):
        f = H.place_deferred_figures([])["adp"]
        assert f["reproduced"] is False and f["closest_population"] is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §8 — the decision rule cannot be talked into a change
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cell(pop, src, delta, lo, hi):
    return {"population": pop, "source": src, "delta_rho_mean": delta,
            "bootstrap": {"evaluated": True, "lo": lo, "hi": hi,
                          "excludes_zero": bool(lo > 0 or hi < 0)}}


class TestDecisionRule:
    def test_a_bigger_point_estimate_alone_never_earns_a_change(self):
        """⭐ The E2.1-r inversion pointed at our own marketing is exactly 'P1 is bigger, ship it'.
        This is THE run's actual shape: P1 six times P0's point estimate, interval still straddling
        zero. Documents the real case — but note it does NOT isolate the `excludes_zero` clause (the
        `materially different` clause also refuses it); the isolating guard is the next test."""
        res = [_cell("P0_shipped", "adp", 0.022, -0.006, 0.051),
               _cell("P1_cross_source_matched", "adp", 0.144, -0.010, 0.300)]
        d = H.decide(res, anchors_ok=True, repro_ok=True)
        assert d["per_source"]["adp"]["eligible"] is False
        assert d["recommendation"].startswith("KEEP THE SHIPPED NUMBER")

    def test_the_excludes_zero_clause_alone_blocks_a_bigger_but_zero_straddling_p1(self):
        """⭐⭐ ISOLATES the `excludes_zero` clause: intervals do NOT overlap (so the 'materially
        different' clause is SATISFIED and cannot carry the refusal) and P1's point estimate is much
        larger — the ONLY thing standing between this and a public claim change is that P1's interval
        still contains zero. VERIFIED RED when `excludes_zero` is dropped from `decide`.

        (The first draft of the guard above missed this: its scenario was refused by the OTHER clause,
        so deleting `excludes_zero` from the source left the suite green — a guard that could not fail
        on the defect it named. NF1.7 (a), found by deliberately breaking the source.)"""
        res = [_cell("P0_shipped", "adp", -0.100, -0.150, -0.050),
               _cell("P1_cross_source_matched", "adp", 0.100, -0.010, 0.250)]
        d = H.decide(res, anchors_ok=True, repro_ok=True)
        v = d["per_source"]["adp"]
        assert v["p0_p1_materially_different"] is True   # the other clause is SATISFIED here
        assert v["p1_excludes_zero"] is False            # …so only this one can refuse
        assert v["eligible"] is False
        assert d["recommendation"].startswith("KEEP THE SHIPPED NUMBER")

    def test_the_materially_different_clause_alone_blocks_a_significant_but_indistinguishable_p1(self):
        """The mirror: P1 excludes zero (so THAT clause is satisfied) but its interval overlaps P0's,
        so the two populations are indistinguishable and there is nothing to change TO. VERIFIED RED
        when the non-overlap clause is dropped."""
        res = [_cell("P0_shipped", "adp", 0.022, 0.005, 0.051),
               _cell("P1_cross_source_matched", "adp", 0.040, 0.010, 0.090)]
        v = H.decide(res, anchors_ok=True, repro_ok=True)["per_source"]["adp"]
        assert v["p1_excludes_zero"] is True             # the other clause is SATISFIED here
        assert v["p0_p1_materially_different"] is False  # …so only this one can refuse
        assert v["eligible"] is False

    def test_both_conditions_together_do_earn_a_recommendation(self):
        """The rule must be capable of firing — a decision rule that can only ever say no is not a
        decision rule (the two-sided-proof discipline)."""
        res = [_cell("P0_shipped", "adp", 0.022, -0.006, 0.030),
               _cell("P1_cross_source_matched", "adp", 0.144, 0.100, 0.190)]
        d = H.decide(res, anchors_ok=True, repro_ok=True)
        assert d["per_source"]["adp"]["eligible"] is True
        assert "RECOMMEND" in d["recommendation"]

    @pytest.mark.parametrize("anchors_ok,repro_ok", [(False, True), (True, False), (False, False)])
    def test_a_failed_anchor_or_reproduction_voids_the_run_even_when_the_stats_qualify(
        self, anchors_ok, repro_ok
    ):
        res = [_cell("P0_shipped", "adp", 0.022, -0.006, 0.030),
               _cell("P1_cross_source_matched", "adp", 0.144, 0.100, 0.190)]
        d = H.decide(res, anchors_ok=anchors_ok, repro_ok=repro_ok)
        assert d["recommendation"].startswith("VOID")
        assert d["blocking_reasons"]

    def test_only_the_preregistered_primary_is_ever_recommendable(self):
        """§8.3 — a P2 depth cell, however good it looks, can never be recommended. RED if `decide`
        starts scanning populations instead of reading P1 by name."""
        res = [_cell("P0_shipped", "adp", 0.022, -0.006, 0.051),
               _cell("P2_depth100_by_source", "adp", 0.300, 0.200, 0.400)]
        d = H.decide(res, anchors_ok=True, repro_ok=True)
        assert d["recommendation"].startswith("KEEP THE SHIPPED NUMBER")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pre-registration itself is pinned — it may not be edited to fit a result
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPreRegistrationIsPinned:
    def test_the_shipped_figures_the_run_must_reproduce_are_the_public_ones(self):
        """These are the numbers behind the LIVE public track-record headline. Changing them here
        would disable anchor A4 — the one check that proves the harness is measuring the same thing
        the public page claims."""
        assert PRE.SHIPPED_DELTA_RHO == {"adp": 0.022, "mfl_adp": 0.173}
        assert PRE.SHIPPED_N_SEASONS == {"adp": 6, "mfl_adp": 7}

    def test_only_real_draft_adp_sources_are_headline_eligible(self):
        assert PRE.HEADLINE_ELIGIBLE_SOURCES == ("adp", "mfl_adp")
        assert set(PRE.CONTEXT_SOURCES).isdisjoint(PRE.HEADLINE_ELIGIBLE_SOURCES)

    def test_the_depth_curve_is_registered_two_sided(self):
        """A one-sided depth reading is the artifact this story measured at 0.20 wide. If the spec
        list ever emits only one truncation side, the memo's band collapses to a number somebody
        could quote."""
        assert set(PRE.DEPTH_TRUNCATION_SIDES) == {"by_source", "by_us"}
        keys = [s.key for s in PRE.preregistered_specs()]
        for k in PRE.DEPTH_GRID:
            if k is None:
                continue
            assert f"P2_depth{k}_by_source" in keys
            assert f"P2_depth{k}_by_us" in keys

    def test_specs_start_with_the_shipped_and_primary_populations(self):
        specs = PRE.preregistered_specs()
        assert specs[0].key == "P0_shipped" and specs[0].require_sources == ()
        assert specs[1].key == "P1_cross_source_matched"
        assert specs[1].require_sources == PRE.HEADLINE_ELIGIBLE_SOURCES

    def test_the_deferred_figures_under_investigation_are_recorded(self):
        """§7 — recorded in the pre-registration so the memo cannot quietly drop the question it was
        opened to answer."""
        assert PRE.DEFERRED_NF3_2_FIGURES == {"adp": 0.144, "mfl_adp": 0.088}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The harness reuses the shipped scorer rather than re-deriving it (NF1.5b)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_harness_scores_through_benchmark_scorecard_not_a_reimplementation():
    """If this file ever grew its own ρ, a per-population number could differ from the shipped
    scorecard for a reason OTHER than population — which would make the whole memo unattributable."""
    src = (H.__file__).replace(".pyc", ".py")
    text = open(src).read()
    assert "BS._score_pair" in text
    assert "BS._within_position_rho" in text
    # the only bespoke correlation is the bootstrap's inner loop, which must be numerically
    # equivalent to the scorer's Spearman
    a = np.array([3.0, 1.0, 2.0, 5.0, 4.0, 9.0, 7.0, 8.0, 6.0, 10.0])
    b = np.array([1.0, 2.0, 3.0, 4.0, 6.0, 5.0, 8.0, 7.0, 9.0, 10.0])
    assert H._fast_spearman(a, b) == pytest.approx(
        float(pd.Series(a).corr(pd.Series(b), method="spearman")), abs=1e-12
    )


def test_fast_spearman_handles_ties_with_average_ranks():
    """Bootstrap resampling WITH REPLACEMENT guarantees ties; a naive argsort rank would silently
    give a different ρ than the scorer's. RED if `_fast_spearman` stops using `rankdata`."""
    a = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 4.0, 4.0])
    b = np.array([1.0, 2.0, 1.0, 2.0, 3.0, 3.0, 4.0, 3.0, 5.0, 4.0])
    assert H._fast_spearman(a, b) == pytest.approx(
        float(pd.Series(a).corr(pd.Series(b), method="spearman")), abs=1e-12
    )


def test_fast_spearman_returns_nan_on_a_degenerate_resample():
    """A bootstrap draw can produce a constant column; that draw must be DROPPED, not counted as
    ρ=0 (which would bias every interval toward zero)."""
    assert np.isnan(H._fast_spearman(np.ones(10), np.arange(10.0)))
