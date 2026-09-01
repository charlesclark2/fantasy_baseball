"""NF-INJ2c node 1 — guards for the coherence-violation diagnosis and its carried executions.

⛔ WHAT THESE DO NOT DO. They do not certify a verdict, a gate or an arm — node 1 is a DIAGNOSIS and
the NF-INJ2c spec makes a REFUTED node 1 a hard stop. They pin (a) the diagnosis's own logic, (b) the
committed artifact against the record it reproduces, and (c) the two carried PM executions (D4's
annotation on NF-INJ2's record, D3's CLAUDE.md landmine).

⭐ EVERY ITERATING GUARD ASSERTS NON-VACUITY FIRST. A loop over "the arms the study's evidence turns
on" that matched nothing would pass on nothing — the DSR-CONV #690 defect, where a guard iterated
call sites, matched only a dict KEY, and passed having run its body zero times. The match set is
asserted non-empty before anything is compared.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as RP
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_inj2c_coherence_diagnosis as D,
)

_ART = Path(__file__).resolve().parents[2] / (
    "quant_sports_intel_models/football/nfl/fantasy/ablation_results")
_REPO = Path(__file__).resolve().parents[2]
_DIAG_JSON = _ART / "nf_inj2c_coherence_diagnosis.json"
_DIAG_MD = _ART / "nf_inj2c_coherence_diagnosis.md"
_INJ2_MD = _ART / "nf_inj2_rate_permutation.md"
_INJ2B_JSON = _ART / "nf_inj2b_rate_ordering.json"

#: the arms whose per-fold coherence counts NF-INJ2b's evidence actually turns on. `incumbent` and
#: `feasibility_clamp` are deliberately EXCLUDED: they are the two arms whose UNSTRATIFIED
#: full-position permutation moves points furthest, so the most rows sit near the envelope boundary
#: and a hair of ADP/feature-cache drift flips one — which is a property of the chain, recorded in
#: the report, ⛔ not something a guard should pretend is byte-stable.
_EVIDENCE_ARMS = ("mvp1_null", "points_rate_permute", "rate_refit",
                  "points_rate_stratified", "rate_refit_stratified", "stratified")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. the two floor DEFINITIONS really are different, which is why both are reported
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cap(games, *, eligible=None):
    """A minimal capture stub — `games_audit` reads only `vets.proj_games` and `eligible`."""
    g = list(games)
    return {"vets": pd.DataFrame({"proj_games": g}),
            "eligible": np.ones(len(g), dtype=bool) if eligible is None
            else np.asarray(eligible, dtype=bool)}


def test_the_recorded_binding_count_misses_a_non_finite_row_the_kernel_does_floor():
    """`games_floor_binding()` requires `isfinite(g)`; `gsafe` floors a non-finite row anyway.

    This is the whole reason the report prints two columns. If they were the same measurement the
    node-1 refutation would rest on the NARROWER one, and "the floor is inert" would be read off a
    count that cannot see one of the two ways the floor acts (NF1.7 (a))."""
    audit = D.games_audit(_cap([5.0, float("nan"), 12.0]))
    assert audit["recorded_games_floor_binding"] == 0, (
        "the recorded definition should NOT see the non-finite row — if it does, this guard is "
        "pinning a behaviour that no longer exists and the two-column report is redundant")
    assert audit["kernel_rows_actually_floored"] == 1
    assert audit["floor_can_act"] is True


def test_a_row_exactly_at_the_floor_is_a_value_identical_no_op_and_both_definitions_agree():
    """`gsafe` keeps `g` only on `g > FLOOR`, so `g == FLOOR` takes the substitution branch — but the
    substituted value IS `FLOOR`, so the divisor does not move and the row cannot produce a
    disagreement between the assignment and the check.

    ⭐ Recorded because the boundary reads like a divergence and is not: the report's two columns
    differ on exactly ONE case, the NON-FINITE row. Measuring `moved` by VALUE rather than by which
    branch was taken is what makes the count answer the hypothesis's question — did the divisor
    change? — instead of a question about control flow."""
    audit = D.games_audit(_cap([RP.GAMES_FLOOR, 9.0]))
    assert audit["recorded_games_floor_binding"] == 0
    assert audit["kernel_rows_actually_floored"] == 0
    assert audit["n_at_or_below_floor"] == 1, (
        "the boundary row must still be VISIBLE in the report even though it moves nothing")


def test_a_row_strictly_below_the_floor_fires_both_definitions():
    """The two definitions are not in general different — they diverge on the non-finite row ALONE,
    which is why the report prints both rather than either."""
    audit = D.games_audit(_cap([0.1, 9.0]))
    assert audit["recorded_games_floor_binding"] == 1
    assert audit["kernel_rows_actually_floored"] == 1


def test_a_healthy_games_column_reports_the_floor_as_unable_to_act():
    audit = D.games_audit(_cap([0.81, 3.0, 17.0]))
    assert audit["floor_can_act"] is False
    assert audit["kernel_rows_actually_floored"] == 0
    assert audit["min_games"] == pytest.approx(0.81)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. the node-1 verdict — the gate the spec makes hard
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _folds(*, can_act: bool, m1: int, other: int = 0):
    mech = {}
    if m1:
        mech["M1_GAMES_FLOOR"] = m1
    if other:
        mech["M3_STAT_MIX_OR_PROMOTION"] = other
    return {"2019": {"games_audit": {"floor_can_act": can_act},
                     "arms": {"x": {"by_mechanism": mech, "n_violations": m1 + other}}}}


def test_a_floor_that_cannot_act_refutes_the_hypothesis():
    v = D._verdict(_folds(can_act=False, m1=0, other=7))
    assert v["state"] == "REFUTED"
    assert v["floor_could_act"] is False


def test_a_floor_that_can_act_but_touches_no_violating_row_also_refutes_and_says_so_differently():
    """The STRONG form: the activity check is green, so the refutation is not a dead mechanism."""
    v = D._verdict(_folds(can_act=True, m1=0, other=7))
    assert v["state"] == "REFUTED"
    assert v["floor_could_act"] is True
    assert "activity check green" in v["why"]


def test_one_floor_attributed_violation_establishes_it():
    v = D._verdict(_folds(can_act=True, m1=1, other=6))
    assert v["state"] == "ESTABLISHED"
    assert v["m1_attributed_violations"] == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2b. the mechanism classifier — the PRECEDENCE, isolated one clause at a time (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_attribution_by_control_outranks_the_floor_when_both_clauses_are_true():
    """The isolating fixture: `pre_existing` AND `floored` are BOTH true, so only the ORDER can
    decide. A fixture that trips one clause proves nothing about the precedence (NF-D17)."""
    assert D.classify_mechanism(pre_existing=True, floored=True, clamp_lo=True) == "M4_PRE_EXISTING"


def test_the_floor_outranks_the_clamp_when_both_clauses_are_true():
    assert D.classify_mechanism(pre_existing=False, floored=True, clamp_lo=True) == "M1_GAMES_FLOOR"


def test_the_clamp_is_named_when_it_is_the_only_clause_that_fires():
    assert D.classify_mechanism(pre_existing=False, floored=False, clamp_lo=True) == "M2_CLAMP_LO"


def test_a_row_no_clause_explains_falls_to_stat_mix_rather_than_to_the_hypothesis():
    """⛔ The residual category must NOT be the hypothesis. A classifier whose default is
    `M1_GAMES_FLOOR` would attribute every unexplained row to the thing under test."""
    assert (D.classify_mechanism(pre_existing=False, floored=False, clamp_lo=False)
            == "M3_STAT_MIX_OR_PROMOTION")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. residual_profile — the SHAPE reading, which is what separates the two populations
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _viol(times_over, games):
    return {"times_over": times_over, "proj_games": games, "id": f"p{times_over}{games}"}


def test_the_under_two_games_share_is_over_the_violating_rows_not_the_board():
    """A share computed over every row would be diluted by the whole board and could never separate
    a low-availability residual from an edge one — the measurement the reading turns on."""
    folds = {"2019": {"arms": {"a": {"n_violations": 4, "n_violating_players": 4,
                                     "violations": [_viol(1.8, 0.9), _viol(1.1, 16.5),
                                                    _viol(1.2, 1.5), _viol(1.05, 12.0)]}}}}
    p = D.residual_profile(folds)["a"]
    assert p["n_rows_under_2_games"] == 2
    assert p["share_rows_under_2_games"] == pytest.approx(0.5)
    assert p["max_times_over"] == pytest.approx(1.8)
    assert p["min_games_on_a_violating_row"] == pytest.approx(0.9)


def test_an_arm_with_no_violation_profiles_as_empty_rather_than_as_clean_numbers():
    """`None`, not 0 — a zero worst-breach reads as "the worst breach was 1.0×", which is a
    measurement; there was no breach to measure (NF1.7 (a))."""
    p = D.residual_profile({"2019": {"arms": {"a": {"n_violations": 0, "n_violating_players": 0,
                                                    "violations": []}}}})["a"]
    assert p["max_times_over"] is None
    assert p["share_rows_under_2_games"] is None
    assert p["n_folds_with_any"] == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. the COMMITTED artifact — pinned to the record it reproduces
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def diag():
    if not _DIAG_JSON.exists():
        pytest.skip("the node-1 diagnosis artifact is not committed in this checkout")
    return json.loads(_DIAG_JSON.read_text())


def test_the_committed_verdict_is_refuted_and_the_report_says_so(diag):
    """A rendered report and its JSON disagreeing is the NF-INJ2b `GATE_STATUS` defect — a policy
    surface claiming a different outcome from the run that produced it."""
    assert diag["verdict"]["state"] == "REFUTED"
    md = _DIAG_MD.read_text()
    assert "the games-floor hypothesis: **REFUTED**" in md


def test_no_violation_anywhere_is_attributed_to_the_games_floor(diag):
    total = 0
    for f in diag["folds_detail"].values():
        for r in f["arms"].values():
            assert r["by_mechanism"].get("M1_GAMES_FLOOR", 0) == 0
            total += r["n_violations"]
    assert total > 0, ("no violation was found at all — the diagnosis would then be REFUTED "
                       "vacuously, which is not the finding it records")


def test_the_floor_is_measured_inert_on_every_fold_by_both_definitions(diag):
    assert diag["folds_detail"], "no fold was diagnosed — this guard would pass on nothing"
    for y, f in diag["folds_detail"].items():
        a = f["games_audit"]
        assert a["kernel_rows_actually_floored"] == 0, f"fold {y}"
        assert a["recorded_games_floor_binding"] == 0, f"fold {y}"
        assert a["min_games"] > RP.GAMES_FLOOR, f"fold {y}"


def test_the_diagnosis_reproduces_the_2b_record_on_every_evidence_arm(diag):
    """The reproduction pin for this node. ⚠️ Scoped to `_EVIDENCE_ARMS` for a MEASURED reason (see
    that constant), and the comparison set is asserted non-empty first."""
    if not _INJ2B_JSON.exists():
        pytest.skip("NF-INJ2b's record is not committed in this checkout")
    rec = json.loads(_INJ2B_JSON.read_text())["per_fold"]
    compared, mismatches = 0, []
    for arm in _EVIDENCE_ARMS:
        for y, f in diag["folds_detail"].items():
            if arm not in f["arms"] or arm not in rec or y not in rec[arm]:
                continue
            compared += 1
            got = f["arms"][arm]["n_violating_players"]
            want = rec[arm][y]["coherence_violating_players"]
            if got != want:
                mismatches.append((arm, y, want, got))
    assert compared >= len(_EVIDENCE_ARMS) * 7, (
        f"only {compared} arm×fold cells were compared — a reproduction pin that matched almost "
        "nothing passes on almost nothing (the DSR-CONV #690 vacuous-iteration class)")
    assert not mismatches, f"the diagnosis does not reproduce NF-INJ2b's record: {mismatches}"


def test_the_two_residual_populations_are_separated_by_the_committed_numbers(diag):
    """The reading is DERIVED, so this guard checks the numbers it is derived from still separate.

    ⛔ Not a threshold invented here: "under 2 expected games" is NF-INJ1's own founding row (Easton
    Stick at 1.9 games), and the comparison is `stratified` against the INCUMBENT it would replace."""
    p = diag["residual_profile"]
    strat, inc = p["stratified"], p["incumbent"]
    rate = [p[a] for a in ("points_rate_permute", "rate_refit", "points_rate_stratified",
                           "rate_refit_stratified") if a in p]
    assert len(rate) == 4, "the rate-arm set is incomplete — the separation would be read off a subset"
    assert all(r["n_rows_under_2_games"] == 0 for r in rate)
    assert max(r["max_times_over"] for r in rate) < 1.25
    # `stratified` shares the incumbent's SHAPE — that is the finding, and it is what forbids a
    # tolerance from absorbing it.
    assert strat["n_rows_under_2_games"] > 0
    assert strat["max_times_over"] > 1.5
    assert strat["share_rows_under_2_games"] == pytest.approx(inc["share_rows_under_2_games"],
                                                              abs=0.10)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. the carried PM executions (D4, D3)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_d4_annotation_is_on_nf_inj2s_record_and_is_marked_as_an_annotation():
    md = _INJ2_MD.read_text()
    assert "## ⚠️ ANNOTATION — added 2026-08-29 by NF-INJ2c (PM ruling D4" in md
    assert "POST-HOC ANNOTATION" in md


def test_the_d4_annotation_leaves_nf_inj2s_verdict_and_giveback_figures_verbatim():
    """E2.1-r: a record is annotated, ⛔ never rewritten. Both figures the annotation discusses must
    still read exactly as the decisive run produced them."""
    md = _INJ2_MD.read_text()
    head = md.split("## ⚠️ ANNOTATION")[0]
    assert "**VERDICT: CONSTRAINT_REFUSED**" in head
    assert "| incumbent | 10 | 9 | 33.9600 | 1.2280 | 18 | 6 | -0.2120 | 7/24 |" in head
    assert "| rate_permute | 1 | 0 | -11.9900 | 0.9293 | 7 | 18 | 0.2070 | 1/7 |" in head


def test_the_d4_annotation_records_the_measurement_that_settles_the_baseline_question():
    """The ruling asked for a flag; the record supports a stronger, MEASURED statement, and the
    annotation must carry the evidence rather than the suspicion."""
    md = _INJ2_MD.read_text()
    ann = md.split("## ⚠️ ANNOTATION")[1]
    assert "reproduction_pin` is PRESENT" in ann
    assert "33.96 on all seven arms" in ann


def test_the_d3_pin_against_capture_landmine_is_in_claude_md():
    """RE-ANCHORED 2026-09-01 onto the CORRECTED entry (PM ruling on decision request #3 (c)).

    The first cut pinned the headline "MUST BIND A *CAPTURED* ARTIFACT, NEVER A RE-PULL" and the
    40.58 measurement. Both were real, and the entry's MECHANISM around them was measured WRONG:
    NF-INJ2b's failure was a 4-day-stale ECR cache, not intraday drift over its 7.30h lag. CLAUDE.md
    is operational GUIDANCE, so it was corrected in place rather than annotated — guidance stating a
    refuted mechanism manufactures the next failure, as it did.

    ⛔ Re-anchored onto the new wording, NOT weakened: the guard now pins the CORRECTED mechanism,
    which is a stronger claim than the one it replaced (MH2.7 — a guard suite can encode a retired
    world; re-anchor it, never delete it).
    """
    txt = (_REPO / "CLAUDE.md").read_text()
    flat = re.sub(r"\s+", " ", txt)
    assert "BINDS ON THE *MARKET-INPUT CACHES* MATCHING THE SERVED BOARD'S VINTAGE" in flat, (
        "the D3 landmine no longer states the measured binding condition")
    assert "SAME-DAY REBUILD IS NECESSARY BUT **NOT SUFFICIENT**" in flat, (
        "the counterexample is the whole correction — same-day was the prescription that failed")
    # both measurements that license the correction, and the misattribution it replaced
    assert "40.58" in flat and "84.72" in flat
    assert "MECHANISM CORRECTED IN PLACE 2026-09-01" in flat, (
        "a corrected entry must SAY it was corrected and where the evidence is — a silent rewrite "
        "leaves the next reader unable to tell guidance from a claim nobody re-measured")
    assert "nf_inj2c_node3b_void_diagnosis.md" in flat


def test_the_fresh_worktree_cache_rebuild_landmine_is_in_claude_md():
    txt = (_REPO / "CLAUDE.md").read_text()
    assert "SILENTLY REBUILDS THE GITIGNORED FEATURE CACHES FROM A LIVE UPSTREAM" in txt
