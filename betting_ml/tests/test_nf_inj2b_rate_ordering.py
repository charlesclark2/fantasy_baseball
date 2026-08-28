"""NF-INJ2b guards — the registration's own claims, PROVEN rather than commented.

Every clause here is RED-proven by `betting_ml/tests/nf_inj2b_red_proof.py`: the deliberate break is
asserted to LAND ON DISK, the asserted predicate is asserted to have MOVED, and the mutation anchor
is asserted UNIQUE in its file. The three ways a RED proof lies (#682 the mutation did not land,
#815 it landed but did not move the predicate, E11.24 it landed on the WRONG symbol) each have a
clause here that would otherwise go green through them.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as RP
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B

_FANTASY = Path(__file__).resolve().parents[2] / "quant_sports_intel_models/football/nfl/fantasy"
_RUNNER = _FANTASY / "run_nf_inj2b_rate_ordering.py"
_MODULE = _FANTASY / "nf_inj2b_rate_ordering.py"
_NF1_5 = _FANTASY / "run_nf1_5.py"
_REPORT = _FANTASY / "ablation_results" / "nf_inj2b_rate_ordering.json"
_PREREG = _FANTASY / "ablation_results" / "nf_inj2b_preregistration.md"


def _frame(n=140, seed=11):
    rng = np.random.default_rng(seed)
    return dict(
        base=rng.uniform(10, 320, n), games=rng.uniform(1, 17, n), score=rng.normal(size=n),
        positions=np.array(rng.choice(["QB", "RB", "WR", "TE"], n), dtype=object),
        eligible=rng.random(n) > 0.08, learn_positions=("QB", "RB", "WR", "TE"),
        line=pd.DataFrame({"proj_pass_att": rng.uniform(0, 600, n),
                           "proj_rec": rng.uniform(0, 130, n),
                           "proj_rush_att": rng.uniform(0, 300, n)}))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The declared field
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_declared_field_matches_the_preregistration():
    assert B.DECLARED_FIELD_SIZE == 10 == len(set(B.ARMS))
    assert B.PRIMARY_ARM == "rate_refit" and B.PRIMARY_ARM in B.ARMS
    assert set(B.DEGENERATE_ARMS) == {"mvp1_null", "random_order"}
    assert set(B.REFERENCE_ARMS) == {"incumbent"}
    # the 2×2 the pre-registration §2 declares must actually be present as four cells
    for arm in ("points_rate_permute", "rate_refit",
                "points_rate_stratified", "rate_refit_stratified"):
        assert arm in B.ARMS, f"the declared 2×2 is missing its {arm} cell"


def test_every_matched_pair_differs_on_exactly_one_factor():
    """⭐ NF-D15 g′ / NF-D17: a pair that moves TWO things at once attributes nothing. This is the
    claim `MATCHED_PAIRS`'s comment makes, proven instead of trusted."""
    assert B.MATCHED_PAIRS, "the registration declares no matched pair — nothing is attributable"
    for a, b, why in B.MATCHED_PAIRS:
        same_rule = B.ASSIGNMENT_OF[a] == B.ASSIGNMENT_OF[b]
        same_score = B.SCORE_OF[a] == B.SCORE_OF[b]
        assert same_rule != same_score, (
            f"({a}, {b}) — {why} — differs on both factors or on neither")


def test_assert_coherent_refuses_a_pair_that_moves_two_factors(monkeypatch):
    """The isolating fixture for the clause above: every OTHER clause of `assert_coherent` is
    satisfied, so only the matched-pair clause can flip the result (NF-D17 — a guard on a
    conjunction is vacuous unless its fixture satisfies every other clause)."""
    monkeypatch.setattr(B, "MATCHED_PAIRS",
                        (("rate_refit", "stratified", "moves target AND assignment"),))
    with pytest.raises(RuntimeError, match="differs on BOTH factors or on NEITHER"):
        B.assert_coherent()


def test_assert_coherent_refuses_two_owners_of_the_served_arm(monkeypatch):
    """INC-30 / INC-36 / INC-38: one logical thing, two execution owners."""
    monkeypatch.setattr(B, "SERVED_ARM", "rate_refit")
    monkeypatch.setattr(B, "GATE_STATUS", "CLEARED")
    monkeypatch.setattr(B, "PM_DISPOSITION_RECORDED", True)
    monkeypatch.setattr(RP, "SERVED_ARM", "rate_permute")
    with pytest.raises(RuntimeError, match="two owners"):
        B.assert_coherent()


def test_a_non_incumbent_arm_cannot_be_served_without_cleared_gates(monkeypatch):
    monkeypatch.setattr(B, "SERVED_ARM", "rate_refit")
    monkeypatch.setattr(B, "GATE_STATUS", "CONSTRAINT_REFUSED")
    with pytest.raises(RuntimeError, match="GATE_STATUS"):
        B.assert_coherent()


def test_a_non_incumbent_arm_cannot_be_served_without_a_pm_disposition(monkeypatch):
    """Clearing the gates and deciding to ship are DIFFERENT FACTS (NF-D21 / NF-D22)."""
    monkeypatch.setattr(B, "SERVED_ARM", "rate_refit")
    monkeypatch.setattr(B, "GATE_STATUS", "CLEARED")
    monkeypatch.setattr(B, "PM_DISPOSITION_RECORDED", False)
    with pytest.raises(RuntimeError, match="no PM disposition"):
        B.assert_coherent()


def test_a_degenerate_can_never_be_served(monkeypatch):
    monkeypatch.setattr(B, "SERVED_ARM", "random_order")
    with pytest.raises(RuntimeError, match="DEGENERATE"):
        B.assert_coherent()


def test_the_story_ships_deploy_held():
    """The state this §0.5 story is allowed to ship in."""
    assert B.SERVED_ARM is None
    assert B.resolve_served_arm() == RP.SERVED_ARM == "incumbent"
    assert B.PM_DISPOSITION_RECORDED is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The kernel — delegation, and the ONE rule this story adds
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("ours,theirs", [
    ("incumbent", "incumbent"), ("points_rate_permute", "rate_permute"),
    ("rate_refit", "rate_permute"), ("stratified", "stratified"),
    ("feasibility_clamp", "feasibility_clamp"), ("mvp1_null", "mvp1_null"),
    ("random_order", "random_order"),
])
def test_delegation_is_byte_identical(ours, theirs):
    """⭐ NF-C0e: one kernel per rule. An arm must not be able to win on a quietly different
    tie-break, clamp or seed, so every rule NF-INJ2 already owns is DELEGATED, not re-written."""
    kw = _frame()
    assert np.max(np.abs(B.assign_targets(arm=ours, **kw)
                         - RP.assign_targets(arm=theirs, **kw))) == 0.0


def test_nf_inj2_arm_names_still_route_through_the_new_owner():
    """`apply_learned_ordering` now dispatches through NF-INJ2b, so NF-INJ2's own runner and every
    existing caller must keep working unchanged."""
    kw = _frame()
    for arm in RP.ALL_ARMS:
        assert np.max(np.abs(B.assign_targets(arm=arm, **kw)
                             - RP.assign_targets(arm=arm, **kw))) == 0.0


def test_the_stratified_rate_rule_is_genuinely_different():
    kw = _frame()
    assert np.max(np.abs(B.assign_targets(arm="rate_refit_stratified", **kw)
                         - B.assign_targets(arm="rate_refit", **kw))) > 1e-6


def test_the_stratified_rate_rule_is_coherent_by_construction():
    """Every target is (a rate drawn from the row's OWN position+stratum) × (the row's OWN games),
    so `games_i` never leaves row `i` — the property the whole story turns on. Proven by
    reconstructing the implied rate and checking it is a MEMBER of that stratum's rate multiset."""
    kw = _frame()
    tgt = B.assign_targets(arm="rate_refit_stratified", **kw)
    g = np.asarray(kw["games"], float)
    gs = np.where(np.isfinite(g) & (g > B.GAMES_FLOOR), g, B.GAMES_FLOOR)
    implied = tgt / gs
    pos = np.asarray(kw["positions"], dtype=object)
    elig = np.asarray(kw["eligible"], bool)
    checked = 0
    for p in ("QB", "RB", "WR", "TE"):
        idx = np.where((pos == p) & elig)[0]
        if len(idx) < 2:
            continue
        pool = np.sort(np.asarray(kw["base"], float)[idx] / gs[idx])
        for i in idx:
            assert np.min(np.abs(pool - implied[i])) < 1e-9, (
                f"row {i} was handed a rate that is not in its own position's rate multiset")
            checked += 1
    assert checked > 50, "the coherence check ran on too few rows to mean anything"


def test_an_unknown_arm_raises_rather_than_scoring_the_incumbent():
    """A typo that silently scores the incumbent under another arm's name would make the whole
    bake-off vacuous."""
    with pytest.raises(ValueError, match="unknown arm"):
        B.assign_targets(arm="rate_refit_typo", **_frame())


def test_apply_learned_ordering_routes_through_the_single_owner():
    """⛔ The served-arm decision must have exactly ONE owner. `nf1_model` must reach
    `nf_inj2b_rate_ordering.resolve_served_arm`, never `nf_inj2_rate_permutation.SERVED_ARM`."""
    src = (_FANTASY / "nf1_model.py").read_text()
    fn = src[src.index("def apply_learned_ordering"):src.index("def apply_learned_level")]
    fn = "\n".join(ln for ln in fn.splitlines() if not ln.lstrip().startswith("#"))
    assert "resolve_served_arm()" in fn, "the single served-arm owner is not called"
    assert "_RP.SERVED_ARM" not in fn, "a SECOND owner still names the served arm"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The fit target — the one line the whole story turns on
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_rate_target_is_points_over_games():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15
    tr = pd.DataFrame({"real_fp_ppr": [300.0, 90.0, 12.0], "real_games": [17.0, 9.0, 6.0]})
    assert np.allclose(N15._fit_target_values(tr, "points"), [300.0, 90.0, 12.0])
    assert np.allclose(N15._fit_target_values(tr, "rate"), [300 / 17, 10.0, 2.0])


def test_the_rate_target_refuses_a_pool_with_no_realized_games():
    """⛔ A silent fallback to the POINTS target would score an arm under another arm's name — the
    failure mode that makes a bake-off vacuous."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15
    with pytest.raises(KeyError, match="real_games"):
        N15._fit_target_values(pd.DataFrame({"real_fp_ppr": [1.0, 2.0]}), "rate")


def test_an_unknown_score_target_raises():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15
    with pytest.raises(ValueError, match="score_target"):
        N15.score_from_frames(pd.DataFrame(), pd.DataFrame(), {}, {}, 2026,
                              score_target="rate_typo")


def test_the_in_fold_reselection_never_reads_the_evaluation_fold():
    """⭐ NCAAF-P2.1: select IN-FOLD or the result is an estimator artefact, not a verdict. The
    split boundary IS the whole claim, so it is proven on the source — but on the EXECUTABLE source
    only. The docstring discusses the boundaries in prose, and a scan that let prose satisfy (or
    break) it would be the INC-38 vacuous-guard class."""
    tree = ast.parse(_NF1_5.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_reselect_in_fold")
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]                                   # drop the docstring — prose, not code
    code = "\n".join(ast.unparse(n) for n in body)
    assert "projection_season - 2" in code, "the candidate fit does not stop at projection − 2"
    assert "projection_season - 1" in code, "the ranking split is not projection − 1"
    # ⭐ AND NOTHING MAY REFERENCE THE EVALUATION SEASON ITSELF. Every use inside the executable
    # body must be OFFSET backwards — a guard checking only the two boundaries above would stay
    # green if a THIRD, un-offset use were added later.
    import re as _re
    bare = [m.group(0) for m in _re.finditer(r"projection_season(?!\s*-\s*[12])", code)]
    assert not bare, f"the in-fold selector reads the EVALUATION season un-offset: {bare}"


def test_score_from_frames_is_the_single_fit_implementation():
    """NF-C0e: the harness must not re-derive the shipped fit. `learned_scores_by_player` has to
    DELEGATE, so the study and the serving path cannot drift."""
    src = _NF1_5.read_text()
    fn = src[src.index("def learned_scores_by_player"):src.index("def score_from_frames")]
    assert "score_from_frames(" in fn
    assert ".fit(" not in fn, "the shipped entrypoint fits a learner of its own — two owners"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_pbo_is_never_carried_as_a_per_arm_gate():
    """⭐ PLAT-CVP1 defect 4(a). CSCV/PBO has ONE value for the whole field and answers whether the
    SELECTION overfit; reading it per-arm converts "the search was unstable" into "this arm failed",
    which is not a statement the statistic makes — and MLB-HV2-1 MEASURED the cost."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as R
    folds = tuple(range(2019, 2026))
    pf = {a: {y: {"crps": 26.0, "n": 500, "tier_rho_by_position": {"QB": 0.5},
                  "rho_by_position": {"QB": 0.7}} for y in folds} for a in B.ARMS}
    pl = R.build_payload(pf, folds, {a: {"crps": 26.0} for a in B.ARMS},
                         {a: 0 for a in B.ARMS})
    table = R.gate_table(pl)
    assert table, "the gate table is empty — every clause below would be vacuously true"
    for arm, gates in table.items():
        assert gates, f"arm {arm} has an EMPTY gate dict — it would pass 'every gate' trivially"
        assert not any("pbo" in g or "cscv" in g for g in gates), (
            f"arm {arm} carries a FIELD-level statistic as a per-arm pass/fail")


def test_classify_null_is_told_the_pbo_application_and_the_declared_field():
    src = _RUNNER.read_text()
    call = src[src.index("cv_power.classify_null("):]
    call = call[:call.index("\n\n")]
    assert 'pbo_application="field"' in call, "PLAT-CVP1: the PBO application must be STATED"
    assert "declared_field_size=B.DECLARED_FIELD_SIZE" in call, "MH2.7: the declaration is auditable"


def test_the_positive_control_runs_the_studys_own_gate_function():
    """⭐ The addendum's requirement, and the NF-C0e rule: the control must drive the REAL registered
    gate function, not a re-implementation that would restate this harness's assumptions."""
    src = _RUNNER.read_text()
    fn = src[src.index("def positive_control"):src.index("def _pbo_injection_activity")]
    assert "run_gates=gate_table" in fn, "the control does not run the study's own gate function"
    assert "check_null_control=True" in fn, "the two-sided (vacuity) leg does not run"
    assert "inject=inject" in fn


def test_the_injection_null_leg_plants_nothing():
    """`inject(0.0)` MUST return the real payload — otherwise the control's own vacuity check is
    vacuous (NF1.7 (a))."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as R
    folds = (2019, 2020, 2021, 2022)
    pf = {a: {y: {"crps": 26.0 + i, "n": 500, "tier_rho_by_position": {"QB": 0.5},
                  "rho_by_position": {}} for y in folds} for i, a in enumerate(B.ARMS)}
    pl = R.build_payload(pf, folds, {a: {"crps": 26.0} for a in B.ARMS}, {a: 0 for a in B.ARMS})
    inject = R.make_injector(pl)
    zero = inject(0.0)
    for a in B.ARMS:
        for y in folds:
            # ⭐ EVERY field the injector can touch, not just the metric one. The first cut of this
            # clause checked `crps` alone and stayed GREEN on a break that planted the tier-ρ half —
            # found by the RED proof, which is exactly what it is for (a guard that cannot fail on
            # its own break is not a guard).
            assert zero["per_fold"][a][y]["crps"] == pl["per_fold"][a][y]["crps"], f"crps {a} {y}"
            assert zero["tier_rho"][a][y] == pl["tier_rho"][a][y], f"tier_rho {a} {y}"
        assert zero["scored"][a]["crps"] == pl["scored"][a]["crps"], f"scored {a}"


def test_the_injection_treats_every_arm_except_the_degenerates_and_the_reference():
    """UNIFORM across the treated arms ON PURPOSE — uniformity is what preserves the near-clone
    geometry the control exists to probe."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as R
    folds = (2019, 2020, 2021, 2022)
    pf = {a: {y: {"crps": 26.0, "n": 500, "tier_rho_by_position": {"QB": 0.5},
                  "rho_by_position": {}} for y in folds} for a in B.ARMS}
    pl = R.build_payload(pf, folds, {a: {"crps": 26.0} for a in B.ARMS}, {a: 0 for a in B.ARMS})
    inj = R.make_injector(pl)(R.INJECTED_EFFECT)
    treated = set(B.ARMS) - set(B.DEGENERATE_ARMS) - set(B.REFERENCE_ARMS)
    assert treated, "nothing is treated — the control would plant nothing"
    for a in B.ARMS:
        moved = pl["per_fold"][a][2019]["crps"] - inj["per_fold"][a][2019]["crps"]
        assert (abs(moved - R.INJECTED_EFFECT) < 1e-12) == (a in treated), a
        rho = inj["tier_rho"][a][2019]["QB"]
        assert (abs(rho - (0.5 + R.INJECTED_TIER_RHO)) < 1e-12) == (a in treated), a


def test_v_excludes_the_degenerates_and_the_reference_arm():
    """⭐ The pre-registration §3 convention, declared before any score: DSR-CONV drops the two
    lose-by-construction degenerates and MH2.1 (a) drops the reference arm, whose lift series is
    identically zero by construction; `n_trials` stays at the FULL declared field."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as R
    srs = {a: float(i) for i, a in enumerate(B.ARMS)}
    members = R._v_members(srs)
    assert set(members) == set(B.ARMS) - set(B.DEGENERATE_ARMS) - set(B.REFERENCE_ARMS)
    src = _RUNNER.read_text()
    assert "R2.dsr_conv(deltas, list(v_members.values()), B.DECLARED_FIELD_SIZE)" in src, (
        "the BINDING DSR must be computed over the reference-excluded V at the full declared field")


def test_the_joint_criterion_does_not_pass_on_inactive_positions_alone():
    """⛔ The spec's own clause: a run that clears (a) only where the mechanism is INACTIVE has not
    cleared (a). The active-cell count must be reported beside the pass count (NF-D20)."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as R
    activity = {"QB": {"rate": {"can_act": False}}, "RB": {"rate": {"can_act": False}},
                "WR": {"rate": {"can_act": True}}, "TE": {"rate": {"can_act": True}}}
    j = R.joint_success(arm="rate_refit", gates={"ordering_not_regressed": True},
                        app2026=None, activity=activity)
    assert j["a_inactive_positions"] == ["QB", "RB"]
    assert j["a_active_positions"] == ["TE", "WR"]
    assert "INACTIVE" in j["a_note"] and "NF-D20" in j["a_note"]


def test_the_2026_section_reads_the_giveback_keys_the_reducer_actually_writes():
    """⭐ A wrong key does not error — it renders an em-dash, and a silently blank column in the
    story's headline table is a number the reader never learns is missing (the NF-C0e wrong-key
    class, on the render side; the first cut read `median_ratio` and the reducer writes
    `median_point_ratio`). Asserted against the REDUCER's own output keys, ⛔ never against a list
    a test author typed."""
    import inspect
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2_rate_permutation as R2
    produced = set(re.findall(r'"([a-z0-9_]+)":', inspect.getsource(R2.injury_giveback)))
    src = _RUNNER.read_text()
    block = src[src.index('for a, r in app["arms"].items():'):src.index('⭐ **ATTRIBUTION BY CONTROL')]
    for key in re.findall(r'gb\.get\("([a-z0-9_]+)"\)', block):
        assert key in produced, (
            f"the 2026 table reads gb[{key!r}], which `injury_giveback` never writes — it renders "
            f"an em-dash and the number silently vanishes. It writes: {sorted(produced)}")


def test_an_uncomputable_gate_renders_as_UNDEFINED_not_as_a_failure():
    """⭐ MH2: a statistic that could not be COMPUTED is UNDEFINED, ⛔ never FAILED. `gate_table` must
    stay strictly boolean (that is `injected_effect_positive_control`'s contract), so the report has
    to carry undefinedness beside it — otherwise a low-fold run prints "PBO … False" for a number
    that was never computable, which is the conflation the seven-state taxonomy exists to prevent."""
    src = _RUNNER.read_text()
    assert '"gate_undefined": gate_undefined,' in src, "undefinedness is not carried on the report"
    assert 'def _gv(key: str)' in src, "the report has no UNDEFINED renderer"
    assert 'return "UNDEFINED (not computable at this n — ⛔ not a failure)"' in src
    # …and it must actually be USED for every gate whose statistic can come back None
    for key in ("pbo_field_level", "dsr", "fold_consistency", "bh_fdr",
                "ordering_not_regressed", "own_form_ceiling"):
        assert f'_gv("{key}")' in src, f"the {key} row still renders a None as a plain False"


def test_an_uncomputable_gate_is_never_reported_as_a_deflation_refusal():
    """⭐ MH2, in the VERDICT rather than the rendering. `gate_table` is strictly boolean (the
    positive control's contract), so an UNCOMPUTABLE statistic arrives as `False` — and the first
    cut of `verdict()` read that as a refusal and published `DEFLATION_REFUSED` for a gate that
    never ran. `classify_null` returns `UNDEFINED` on the same input; the two must not disagree,
    because a refusal carries a REMEDY and an undefined gate has none."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as R
    common = dict(
        winner="rate_refit",
        pooled={"mean_lift_vs_incumbent": 1.0, "tie_band": 0.01},
        defl={"declared_field_size": 10, "trial_sharpes": {"rate_refit": 2.0, "stratified": 1.0,
                                                           "feasibility_clamp": 0.5}},
        anchors={}, ordering={"regression_significant_by_position": {}},
        joint={"c_coherence_restored": True}, pair_reads={})
    gates = {"dsr": False, "bh_fdr": True, "ordering_not_regressed": True,
             "coherence_restored": True, "degenerates_lose": True}
    # EVALUATED and failed ⇒ a genuine refusal
    assert R.verdict(gates=gates, gate_undefined={"dsr": False}, **common)["state"] \
        == "DEFLATION_REFUSED"
    # NOT COMPUTABLE ⇒ UNDEFINED, and ⛔ never a refusal
    v = R.verdict(gates=gates, gate_undefined={"dsr": True}, **common)
    assert v["state"] == "UNDEFINED", v["state"]
    assert "not failed, not passed" in v["why"]
    assert v["gates_unevaluated_blocking_a_ship"] == ["dsr"]
    # ⛔ …AND IT MUST BLOCK A SHIP. An arm that WINS the metric while a pre-registered gate never
    # ran has not passed that gate (NF1.7 (a)); the first cut placed this branch below the ship
    # branches and returned SHIP.
    passing = dict(gates, dsr=True)
    assert R.verdict(gates=passing, gate_undefined={}, **common)["state"] == "SHIP"
    assert R.verdict(gates=passing, gate_undefined={"dsr": True}, **common)["state"] == "UNDEFINED"
    # an INACTIVE own-form ceiling is UNINFORMATIVE, not a blocker (NF-W6d)
    assert R.verdict(gates=passing, gate_undefined={"own_form_ceiling": True},
                     **common)["state"] == "SHIP"


def test_the_shipped_score_target_addition_is_strictly_additive():
    """⚠️ NF-C0 / E8.6: this story edits SERVING code (`run_nf1_5`, `nf1_model`). Every addition must
    DEFAULT to the shipped behaviour, or a caller that never heard of NF-INJ2b silently changes what
    it serves."""
    import inspect
    from quant_sports_intel_models.football.nfl.fantasy import run_nf1_5 as N15
    for fn in (N15.learned_scores_by_player, N15.build_season_projection):
        params = inspect.signature(fn).parameters
        assert params["score_target"].default == "points", (
            f"{fn.__name__} does not default to the SHIPPED fit target")
        assert params["capture"].default is None, f"{fn.__name__}'s capture is not opt-in"
    assert N15.score_from_frames.__defaults__[-1] == "points"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Provenance
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_recorded_gate_status_matches_the_committed_report():
    """⭐ NF-INJ2's own module shipped as "UNRUN" after its decisive run had landed and been refused
    — a policy module claiming the study had never run. A re-run that changes the verdict must
    change `GATE_STATUS` in the SAME commit."""
    if not _REPORT.exists():
        assert B.GATE_STATUS == "UNRUN", (
            "no committed report exists, so the policy module must say the study has not run")
        return
    state = json.loads(_REPORT.read_text())["verdict"]["state"]
    assert B.GATE_STATUS == state, (
        f"GATE_STATUS={B.GATE_STATUS!r} but the committed report says {state!r}")


def test_the_preregistration_records_its_deflation_conventions():
    """The NF-INJ3 lesson, made mechanical: a pre-registration must name `V`'s membership, the BH
    family and the PBO application — the specification items that only become interesting AFTER a
    result, i.e. the ones you can no longer set (E2.1-r)."""
    text = _PREREG.read_text()
    for claim in ("declared_field_size = 10", "MH2.1 (a)", 'pbo_application="field"',
                  "SINGLE hypothesis", "DSR-CONV"):
        assert claim in text, f"the pre-registration does not name {claim!r}"


def test_the_preregistration_amendment_is_marked_and_keeps_the_original():
    """E2.1-r / NF-W7f: a pre-registration is not edited, it is AMENDED on the record, and the
    superseded text stays verbatim above the amendment."""
    text = _PREREG.read_text()
    assert "AMENDMENT 1" in text and "BEFORE ANY SCORING" in text
    i_orig = text.index("The injected effect is **+0.75 CRPS**")
    assert i_orig < text.index("AMENDMENT 1"), "the amendment must not replace the original clause"


def test_the_runner_never_reruns_a_smoke_as_a_gate():
    """A smoke is a code-path proof, ⛔ never a gate — so it must write to its own artifact stem and
    never overwrite the decisive record (the runner-clobber family)."""
    src = _RUNNER.read_text()
    assert 'suffix = "_smoke" if args.smoke else ""' in src
    assert 'f"{_STEM}{suffix}.json"' in src


def test_the_module_docstrings_do_not_claim_an_unproven_zero_harm():
    """NF-D16 g‴: "zero harm BY CONSTRUCTION" is the kind of sentence that turns out to be false.
    The coherence property is PROVEN by a test above; nothing may assert it as free."""
    tree = ast.parse(_MODULE.read_text())
    doc = (ast.get_docstring(tree) or "").lower()
    assert "zero violations" not in doc
