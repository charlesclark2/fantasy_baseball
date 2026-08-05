"""test_nf_d21_rookie_publish.py — NF-D21: the λ=0.5 PM-judgment rookie-point publish.

The discipline this story turns on is not a number, it is a CLASSIFICATION: λ=0.5 is a judgment,
not a selection. So most of these tests guard the honesty machinery (the stamp, the prohibition on
the board-fitted λ, the QB exclusion) rather than the arithmetic — the arithmetic is the easy part
and the classification is what a future reader will get wrong.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RC
from quant_sports_intel_models.football.nfl.fantasy import rookie_publish_policy as RP
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The λ shrink — exact, and exactly equivalent to NF-D20's output-space blend
# ══════════════════════════════════════════════════════════════════════════════════════════════
_PARAMS = {"RB": (4.8516, 1.3758), "TE": (3.0232, 1.2759), "WR": (18.4402, 1.0021)}


@pytest.mark.parametrize("lam", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_parameter_space_shrink_equals_the_output_space_blend(lam):
    """⭐ THE ALGEBRA IS TESTED, NOT ASSERTED. Serving folds λ into the fitted affine ONCE at fit
    time (`shrink_affine_params`) instead of blending at predict time. That is only legitimate
    because a λ-blend of an affine with the identity IS an affine — the same algebra NF-D20 relied
    on. If a future edit breaks it, serving would silently ship a DIFFERENT shrink than the one the
    evidence base describes, with no other symptom."""
    rng = np.random.default_rng(20260804)
    point = rng.uniform(5, 300, 400)
    pos = rng.choice(["RB", "TE", "WR", "QB"], 400)

    affine = np.full(len(point), np.nan)
    for q, (a, b) in _PARAMS.items():
        affine[pos == q] = a + b * point[pos == q]
    reference = RC.apply_position_adjustment(
        point, pos, RC.blend_toward_incumbent(point, affine, lam))

    shrunk = RC.shrink_affine_params(_PARAMS, lam)
    folded = np.full(len(point), np.nan)
    for q, (a, b) in shrunk.items():
        folded[pos == q] = a + b * point[pos == q]
    folded = RC.apply_position_adjustment(point, pos, folded)

    assert np.max(np.abs(reference - folded)) < 1e-9


def test_lambda_zero_folds_to_the_identity_so_rollback_needs_no_second_code_path():
    """This is WHY the rollback proof works: turning the flip off is not a different branch, it is
    λ=0, which is the identity affine and therefore a mathematical no-op."""
    identity = RC.shrink_affine_params(_PARAMS, 0.0)
    assert identity == {"RB": (0.0, 1.0), "TE": (0.0, 1.0), "WR": (0.0, 1.0)}


def test_the_shrink_is_monotone_in_lambda_between_the_incumbent_and_the_full_correction():
    point = np.array([50.0, 120.0, 250.0])
    pos = np.array(["RB", "RB", "RB"])

    def at(lam):
        a, b = RC.shrink_affine_params(_PARAMS, lam)["RB"]
        return RC.apply_position_adjustment(point, pos, a + b * point)

    seq = [at(l) for l in (0.0, 0.25, 0.5, 0.75, 1.0)]
    for lo, hi in zip(seq, seq[1:]):
        assert np.all(hi >= lo - 1e-9), "the RB correction is a lift; λ must move toward it"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⛔ QB is never touched — inherited by IMPORT so the stories cannot drift
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_qb_is_excluded_and_the_exclusion_is_inherited_not_restated():
    assert RP.recalibrated_positions() == tuple(RC.RECALIBRATED_POSITIONS)
    assert RP.excluded_positions() == tuple(RC.EXCLUDED_POSITIONS)
    assert "QB" in RP.excluded_positions()
    assert "QB" not in RP.recalibrated_positions()


@pytest.mark.parametrize("lam", [0.25, 0.5, 1.0])
def test_no_lambda_moves_a_qb_projection_by_any_amount(lam):
    """⚠️ ISOLATING FIXTURE (NF-D17), and the first cut of this test was VACUOUS.

    It fitted only RB/TE/WR, so a QB row's adjustment was NaN and `apply_position_adjustment`'s
    non-finite fallback protected it — meaning deleting the POSITION MASK (the clause this test is
    named for) left the suite green. The params below deliberately include a QB entry with a
    FINITE, large adjustment, so the NaN fallback cannot fire and only the position mask can hold
    the QB projection still."""
    params = {**_PARAMS, "QB": (50.0, 1.5)}
    point = np.array([300.0, 250.0, 180.0, 90.0])
    pos = np.array(["QB", "QB", "RB", "QB"])
    shrunk = RC.shrink_affine_params(params, lam)
    adj = np.full(len(point), np.nan)
    for q, (a, b) in shrunk.items():
        adj[pos == q] = a + b * point[pos == q]
    assert np.all(np.isfinite(adj)), "the fixture must leave NO NaN, or the mask is untested"
    out = RC.apply_position_adjustment(point, pos, adj)
    qb = pos == "QB"
    assert np.max(np.abs(out[qb] - point[qb])) == 0.0
    assert out[~qb][0] != point[~qb][0], (
        "the fixture must actually EXERCISE the correction, or the QB check is vacuous")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The PM-judgment classification — the honesty machinery
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_lambda_is_the_declared_interval_midpoint_computed_not_typed():
    """"Board-blind" must be a property of the CODE. A literal `0.5` would be indistinguishable
    from a number someone picked after seeing a result; deriving it from the declared interval makes
    it visibly impossible for any board or fold to have produced it."""
    lo, hi = RP.SHRINK_LAMBDA_INTERVAL
    assert RP.SHRINK_LAMBDA == (lo + hi) / 2.0
    src = inspect.getsource(RP)
    assert re.search(r"SHRINK_LAMBDA:\s*float\s*=\s*\(SHRINK_LAMBDA_INTERVAL", src), (
        "SHRINK_LAMBDA must be COMPUTED from the interval, not typed as a literal")


def test_the_stamp_records_the_publish_as_a_judgment_not_a_selection():
    s = RP.stamp()
    assert s["selection_status"] == "PM_JUDGMENT"
    assert s["statistically_selected"] is False
    assert s["shrink_lambda"] == 0.5
    assert s["source_model"] == "NF-D16" and s["decision_story"] == "NF-D21"


def test_the_board_fitted_frontier_lambda_is_recorded_as_prohibited_and_is_not_the_served_one():
    """⛔ NF-D18 measured λ=0.75 on the 2026 board WITH THE ANSWER IN VIEW. Publishing it would be
    the E2.1-r inversion wearing a successor's badge. The trap is live: 0.75 is also the nearest
    grid value that CLEARS the interval floor λ=0.5 misses, so "just nudge λ" leads straight to the
    one number that may not be used."""
    assert RP.NF_D20_FRONTIER_LAMBDA == 0.75
    assert RP.SHRINK_LAMBDA != RP.NF_D20_FRONTIER_LAMBDA


def test_the_honest_framing_makes_no_market_or_selection_claim():
    from betting_ml.governance import gates as G
    assert G.track_record_copy_compatible([RP.HONEST_FRAMING]).passed
    low = RP.HONEST_FRAMING.lower()
    assert "judgment" in low, "the framing must NAME the decision as a judgment"
    assert "board-blind" in low
    # ⚠️ The words "selection"/"optimised" DO appear — inside an explicit NEGATION ("NOT an
    #    optimised in-fold selection"), which is the point of the sentence. A crude
    #    "these words must be absent" check would fail on the very disclaimer it wants; assert
    #    instead that every occurrence is negated.
    for term in ("selection", "optimised", "optimized"):
        for m in re.finditer(term, low):
            window = low[max(0, m.start() - 40):m.start()]
            assert "not " in window, (
                f"the framing uses {term!r} without a negation — that would claim λ=0.5 was chosen "
                f"by a search, which is exactly what this story must never say")


def test_serving_lambda_is_zero_while_the_flip_is_held():
    """The flip is HELD by the interval-floor gate (rookie RB, 2 covered rows short at λ=0.5).
    While it is held the served λ must be 0 — i.e. the incumbent — so the whole system (the board
    stamp, the registry, the standing re-validation) agrees on ONE answer."""
    assert RP.SERVING_ENABLED is False
    assert RP.serving_lambda() == 0.0


def test_the_held_flip_is_documented_with_its_measured_reason():
    """A held flip with no recorded reason becomes an unexplained `False` that someone flips back."""
    src = inspect.getsource(RP)
    assert "interval_floors" in src or "INTERVAL-FLOOR" in src
    assert "0.7905" in src, "the measured breach value must be recorded beside the held flip"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Serving wiring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _rookie_history(n: int = 240) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    pos = rng.choice(["RB", "WR", "TE", "QB"], n)
    overall = rng.integers(1, 260, n).astype(float)
    return pd.DataFrame({
        "draft_year": rng.integers(2015, 2025, n),
        "position_group": pos,
        "draft_overall": overall,
        "games": rng.integers(1, 17, n).astype(float),
        "rookie_fp_ppr": np.clip(260 - overall + rng.normal(0, 35, n), 0, None),
        "rookie_pass_att": 0.0, "rookie_pass_cmp": 0.0, "rookie_pass_yds": 0.0,
        "rookie_pass_td": 0.0, "rookie_pass_int": 0.0,
        "rookie_rush_att": rng.uniform(0, 200, n), "rookie_rush_yds": rng.uniform(0, 900, n),
        "rookie_rush_td": rng.uniform(0, 8, n), "rookie_targets": rng.uniform(0, 120, n),
        "rookie_rec": rng.uniform(0, 80, n), "rookie_rec_yds": rng.uniform(0, 900, n),
        "rookie_rec_td": rng.uniform(0, 8, n),
    })


def test_a_curve_built_without_recal_hist_carries_no_recalibration():
    """The opt-in property NF-D16 shipped, still intact — it is what makes λ=0 byte-identical."""
    curve = SP.fit_rookie_slot_curves(_rookie_history())
    assert curve.fp_recal == {}
    assert curve.fp_recal_lambda == 0.0


def test_the_served_curve_stores_the_shrink_folded_into_its_parameters():
    hist = _rookie_history()
    full = SP.fit_rookie_slot_curves(hist, recal_hist=hist, recal_lambda=1.0)
    half = SP.fit_rookie_slot_curves(hist, recal_hist=hist, recal_lambda=0.5)
    assert half.fp_recal_lambda == 0.5
    for pos, (a, b) in full.fp_recal.items():
        ha, hb = half.fp_recal[pos]
        assert ha == pytest.approx(0.5 * a)
        assert hb == pytest.approx(1.0 - 0.5 + 0.5 * b)


def test_a_curve_at_lambda_zero_reproduces_the_incumbent_point_byte_for_byte():
    """The ROLLBACK proof, at the model layer: λ=0 is the identity, so the recalibrated path and the
    incumbent path emit the same numbers — no second code path to keep in sync."""
    hist = _rookie_history()
    plain = SP.fit_rookie_slot_curves(hist)
    zero = SP.fit_rookie_slot_curves(hist, recal_hist=hist, recal_lambda=0.0)
    pos = np.array(["RB", "WR", "TE", "QB"] * 5)
    fp = np.linspace(10, 280, len(pos))
    assert np.array_equal(plain.recalibrate_fp(pos, fp), zero.recalibrate_fp(pos, fp))


def test_the_serving_call_site_reads_lambda_from_the_policy_and_never_hardcodes_it():
    """One switch. If `run_season_projection` typed its own λ, flipping the policy would change the
    stamp and the re-validation while the BOARD kept its old shrink — a stamp describing a board it
    was not built from (the NF-C0e 'declaration outruns its production' class)."""
    src = Path(SP.__file__).with_name("run_season_projection.py").read_text()
    assert "_ROOKIE_POLICY.serving_lambda()" in src
    assert re.search(r"recal_lambda\s*=\s*0\.\d", src) is None, (
        "a hardcoded λ at the serving call site would fork the switch")


def test_the_board_stamp_columns_are_emitted_and_named_consistently():
    from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RSP
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    for col in EX._ROOKIE_POLICY_COLUMNS:
        assert col in RSP.OUTPUT_COLS, f"{col} is mapped for export but never emitted on the board"


def test_the_payload_stamp_is_read_off_the_board_not_off_the_policy_module():
    """⭐ NF-C0e: a stamp sourced from the CODE keeps reading correct while the served ARTIFACT
    drifts. Reading the board's own columns means the payload can only claim the policy the board
    was actually built at."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    board = pd.DataFrame({
        "rookie_selection_status": ["PM_JUDGMENT"] * 3,
        "rookie_shrink_lambda": [0.5] * 3,
        "rookie_statistically_selected": [False] * 3,
        "rookie_source_model": ["NF-D16"] * 3,
        "rookie_decision_story": ["NF-D21"] * 3,
    })
    stamp = EX.rookie_policy_stamp(board)
    assert stamp == {"selection_status": "PM_JUDGMENT", "shrink_lambda": 0.5,
                     "statistically_selected": False, "source_model": "NF-D16",
                     "decision_story": "NF-D21"}
    # a board that predates the policy stamps NOTHING rather than inventing a policy
    assert EX.rookie_policy_stamp(pd.DataFrame({"player_id": ["a"]})) is None


def test_a_board_carrying_two_policies_is_refused_rather_than_majority_voted():
    """Two concatenated builds: stamping one of them would publish a claim true of half the board."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    mixed = pd.DataFrame({"rookie_shrink_lambda": [0.0, 0.5, 0.5]})
    with pytest.raises(ValueError, match="distinct values"):
        EX.rookie_policy_stamp(mixed)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The standing re-validation must track what is SERVED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_interval_revalidation_folds_resolve_lambda_from_the_served_policy():
    """⭐ THE DRIFT THIS FIXES WAS REAL AND SILENT. `build_folds` recalibrated at λ=1 while serving
    ran the correction OFF entirely, so the standing coverage check was validating a band centred on
    a point the product did not serve — while its own docstring claimed it matched serving."""
    from quant_sports_intel_models.football.nfl.fantasy import run_rookie_interval_ablation as NF17
    sig = inspect.signature(NF17.build_folds)
    assert "recal_lambda" in sig.parameters
    assert sig.parameters["recal_lambda"].default is None, (
        "the default must RESOLVE to the served λ, not pin a literal")
    # ⚠️ Strip the docstring first. The first cut matched "serving_lambda()" anywhere in the source
    # and stayed GREEN when the real assignment was replaced by a literal — because the DOCSTRING
    # still mentioned it. That is INC-38's "prose must not be able to SATISFY a source-inspection
    # guard", and it was caught only by deliberately breaking the source.
    src = inspect.getsource(NF17.build_folds)
    body = src.split('"""')[-1]
    assert re.search(r"recal_lambda\s*=\s*_?RP?\.?\w*\.?serving_lambda\(\)", body), (
        "the λ default must be ASSIGNED from the served policy in the function BODY")


def test_the_revalidation_report_records_which_lambda_it_validated():
    """"The floors held" is meaningless without saying which point they held around."""
    from quant_sports_intel_models.football.nfl.fantasy import run_interval_revalidation as RV
    src = inspect.getsource(RV.revalidate_rookies)
    assert "rookie_point_shrink_lambda" in src


def test_nf_d16s_own_post_ship_harness_still_pins_its_historical_lambda():
    """A historical result is scored at ITS OWN λ. NF-D16's `--recalibrated-incumbent` re-read asks
    "how much level effect is left once the FULL correction is applied" — re-running it at the
    served λ would answer a different question while reproducing its published table."""
    src = (Path(SP.__file__).with_name("run_nf_d16_point_recalibration.py")).read_text()
    assert "recal_lambda=1.0" in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The PM DISPOSITION (2026-08-05) — NF-D21 CLOSED as CONSTRAINT_REFUSED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_disposition_is_recorded_as_a_closure_not_a_pending_decision():
    """⭐ "Closed" and "open pending a fix" are DIFFERENT STATES with different pressures, and the
    difference IS the decision: a story left open pending the floor work is exactly the pressure
    that would bias that floor toward clearing λ=0.5. A record that loses the distinction loses the
    reason, so both halves are asserted."""
    assert RP.DISPOSITION == "CONSTRAINT_REFUSED"
    assert RP.DISPOSITION_IS_NOT_PENDING is True
    assert RP.DISPOSITION_REVIEWED_BY.strip(), "a disposition with no named reviewer is unowned"
    assert RP.DISPOSITION_DECIDED_ON >= RP.DECIDED_ON, (
        "the disposition cannot predate the decision it disposes of")


def test_the_registry_carries_the_pm_rationale_VERBATIM():
    """⭐ The registry is the NAMED AUTHORITY for why the served board is what it is. If the reason
    lives only in a story doc, the artifact and its justification can drift apart silently — the
    NF-C0e "declaration outruns its production" class. Asserting VERBATIM (not "mentions the
    floor") is what makes a paraphrase-away impossible."""
    import yaml
    reg = yaml.safe_load(Path(
        "betting_ml/models/model_family_registry.yaml").read_text())
    entry = reg["nfl_fantasy__season_projection__nfl_fantasy_nf1_5_v1"]
    assert RP.DISPOSITION_RATIONALE in entry["validation_report"], (
        "the registry's validation_report must carry the PM rationale verbatim")
    assert entry["promotion_status"] == "champion", "no challenger was promoted"
    assert entry["rookie_selection_status"] == "incumbent"
    assert entry["rookie_shrink_lambda"] == 0.0, "the served λ is 0 — the incumbent"


def test_serving_on_a_constraint_refused_disposition_is_REFUSED_at_import(monkeypatch):
    """Two-sided, because a one-sided version would be VACUOUS today: `SERVING_ENABLED` is False, so
    the incoherent branch is never reached in the live module and a "the live state is fine" assert
    would pass with the rule deleted. The realistic future failure is a session flipping the flip
    because NF-D22 landed, WITHOUT re-gating or re-deciding — producing a served artifact whose own
    provenance record contradicts it."""
    RP.assert_coherent()  # (a) the live state is coherent

    # (b) the rule actually FIRES — `assert_coherent` reads module globals, so substituting them
    #     exercises the real function rather than a re-implementation of it.
    monkeypatch.setattr(RP, "SERVING_ENABLED", True)
    with pytest.raises(ValueError, match="INCOHERENT"):
        RP.assert_coherent()

    # (c) and it is the DISPOSITION that holds it, not merely the flip — a genuine future publish
    #     (re-gated + re-decided) must be ALLOWED through, or the guard becomes a permanent block.
    monkeypatch.setattr(RP, "DISPOSITION", "PUBLISHED")
    RP.assert_coherent()


def test_the_follow_on_is_carded_separately_with_its_prohibitions_recorded():
    """The follow-on floor story is only admissible if it is derived from n and a PRE-STATED
    false-reject target — with ZERO reference to the breach measured here. That prohibition has to
    live beside the flip, because reading this file is the exact moment someone is tempted to
    "just fix the floor so NF-D21 can ship"."""
    assert RP.FOLLOW_ON_STORY, "the follow-on must be NAMED, so it can be tracked as its own story"
    assert RP.REJECTED_REMEDY, "the rejected remedy must be recorded, not silently dropped"
    src = inspect.getsource(RP)
    low = src.lower()
    assert "post-launch" in low, "the follow-on must be recorded as temporally separated"
    assert "out of scope" in low, "NF-D21 must be explicitly out of the follow-on's scope"
    assert "zero reference" in low, "the no-reference-to-the-measured-breach rule must be recorded"
