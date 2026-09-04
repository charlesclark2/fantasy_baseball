"""NF-INJ2c node 4 — guards for the decisive run.

⛔ These certify no verdict. They pin that the runner COMPUTES what `nf_inj2c_preregistration.md`
and `nf_inj2c_margin_construction_rule.md` (node 3a, BINDING) declare, and that it cannot reach a
dominance claim by a route those documents forbid:

  · the primary arm is FIXED by the registration and is ⛔ never selected as "the best CRPS";
  · M3, M4 and M2's BASELINE are READ from node 3b, ⛔ never recomputed, and a failed pin is VOID;
  · every band is one of node 3a's three rules, and ⛔ none is derived from an observed gap;
  · an UNEVALUABLE measure is ⛔ never a pass, and one regression is a NULL;
  · the BINDING deflation field is the declared five, the inherited ten is NON-BINDING, and there
    is ⛔ no third field;
  · the field-trim 2x2 is STRUCTURALLY UNAVAILABLE at two V members, stated a fortiori;
  · the calendar-bound fold trigger is WITHHELD when SR <= SR0.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from betting_ml.utils import coverage_power_floor as CPF
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2c_assignment_rule as C
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2c_decisive as D

_RUNNER = Path(D.__file__)
_REG = Path(C.__file__)
_POS = ("QB", "RB", "WR", "TE")


def _strip_comments(src: str) -> str:
    """INC-38: a source-inspection guard that PROSE can satisfy is not a guard."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def _stub(monkeypatch, **fields):
    """Stub `cv_power.injected_effect_positive_control` with a report carrying EVERY field the
    reader unpacks — so a field the instrument adds later fails loudly here rather than silently
    vanishing from the record."""
    base = {"verdict": "BLIND", "reason": "", "effect": 0.75, "survivors": [],
            "metric_survivors": [], "deflation_blocked": [], "deflation_gates": [],
            "metric_gates": [], "blocking_gates": {}, "field_level_gates_applied_per_arm": [],
            "null_control_checked": True, "null_control_survivors": []}
    base.update(fields)
    monkeypatch.setattr(RB, "build_payload", lambda *a, **k: {})
    monkeypatch.setattr(RB, "make_injector", lambda p: (lambda e: {}))
    monkeypatch.setattr(D.cv_power, "injected_effect_positive_control",
                        lambda **k: type("R", (), base)())


def _pf(*, arm_crps, inc_crps, arm_viol, inc_viol, null_viol=0, arm_rho=0.55, inc_rho=0.50,
        cov=0.81, n_group=60, folds=(2019, 2020, 2021, 2022, 2023, 2024, 2025)):
    """A per-fold frame carrying only what the measures read. Every arm is scored by the SAME
    shape, so an anchor and a candidate cannot answer different questions."""
    out: dict = {}
    spec = {"stratified": (arm_crps, arm_viol, arm_rho), C.INCUMBENT_ARM: (inc_crps, inc_viol,
                                                                           inc_rho),
            "mvp1_null": (inc_crps, null_viol, inc_rho)}
    for a, (crps, viol, rho) in spec.items():
        out[a] = {}
        for j, y in enumerate(folds):
            out[a][y] = {
                "crps": (crps[j] if isinstance(crps, (list, tuple)) else crps),
                "coherence_violating_players": (viol[j] if isinstance(viol, (list, tuple)) else viol),
                "tier_rho_by_position": {p: (rho[j] if isinstance(rho, (list, tuple)) else rho)
                                         for p in _POS},
                "coverage80_by_position": {p: cov for p in _POS},
                "coverage_n_by_position": {p: n_group for p in _POS},
                "n": 400,
            }
    return out, folds


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The registration transcribes the documents
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheRegistration:

    def test_the_binding_field_is_the_declared_five(self):
        assert C.ARMS == ("incumbent", "stratified", "feasibility_clamp", "mvp1_null",
                          "random_order")
        assert C.DECLARED_FIELD_SIZE == 5

    def test_V_has_exactly_two_members_as_section_2_3a_declares(self):
        """⭐ §2.3(a) reasons about a 1-df variance estimate. If `V` ever stops being two members,
        the declared fragility no longer describes the design being run.

        ⚠️ This asserts the DATA. It does NOT test that `assert_coherent` enforces it — the two are
        different claims, and an earlier cut had only this one, so deleting the enforcing clause
        left the guard green (the RED proof caught it). The enforcement is tested below."""
        v = [a for a in C.ARMS if a not in set(C.DEGENERATE_ARMS) | set(C.REFERENCE_ARMS)]
        assert v == ["stratified", "feasibility_clamp"]

    def test_assert_coherent_REFUSES_a_field_whose_V_is_not_two_members(self, monkeypatch):
        """The ENFORCEMENT half. A field with three contenders would make §2.3(a)'s reasoning — and
        §2.3(b)'s structural-unavailability argument — describe a design nobody is running."""
        monkeypatch.setattr(C, "ARMS", ("incumbent", "stratified", "feasibility_clamp",
                                        "points_rate_permute", "mvp1_null", "random_order"))
        monkeypatch.setattr(C, "DECLARED_FIELD_SIZE", 6)
        monkeypatch.setattr(C, "EXCLUDED_RATE_SPACE_ARMS",
                            ("rate_refit", "points_rate_stratified", "rate_refit_stratified",
                             "rate_refit_reselect"))
        with pytest.raises(RuntimeError, match="declares exactly two"):
            C.assert_coherent()

    def test_the_exclusions_account_for_every_inherited_arm_exactly_once(self):
        """Nothing quietly dropped, nothing invented — the exclusion is auditable against the
        inherited field rather than asserted."""
        assert set(C.ARMS) | set(C.EXCLUDED_RATE_SPACE_ARMS) == set(B.ARMS)
        assert not set(C.ARMS) & set(C.EXCLUDED_RATE_SPACE_ARMS)

    def test_the_primary_arm_is_stratified_and_is_not_a_degenerate(self):
        assert C.PRIMARY_ARM == "stratified"
        assert C.PRIMARY_ARM not in C.DEGENERATE_ARMS and C.PRIMARY_ARM not in C.REFERENCE_ARMS

    def test_the_registration_declares_no_served_arm(self):
        """⛔ A third owner for one logical thing is the INC-30 / INC-36 / INC-38 class."""
        assert not hasattr(C, "SERVED_ARM")
        assert C.resolve_served_arm() == B.resolve_served_arm()

    def test_assert_coherent_runs_at_import(self):
        src = _strip_comments(_REG.read_text())
        assert re.search(r"^assert_coherent\(\)\s*$", src, re.M), (
            "the registration's own consistency check is no longer invoked at import, so a state "
            "the documents do not support would ship rather than failing the process (NF-C0e)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The primary arm is FIXED — ⛔ never selected
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePrimaryArmIsNotSelected:

    def test_the_runner_reads_the_registered_arm_and_never_argmins_crps(self):
        """⭐ Choosing the arm after seeing the scores is the E2.1-r inversion in the one place a
        DOMINANCE claim is most exposed to it. NF-INJ2b legitimately picks a CRPS winner; this story
        may not, because its disposition names the arm in advance."""
        src = _strip_comments(_RUNNER.read_text())
        assert "arm = C.PRIMARY_ARM" in src, "the run no longer takes its arm from the registration"
        for forbidden in ("min(cands", "min(candidates", "key=lambda a: (scored[a]"):
            assert forbidden not in src, (
                f"{forbidden!r} selects an arm from the scores — this story's arm is REGISTERED")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# M3 / M4 / M2's baseline are READ from node 3b, and a failed pin is VOID
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheBoardMeasuresAreRead:

    def test_an_absent_node_3b_report_REFUSES_and_names_the_command(self, tmp_path):
        with pytest.raises(SystemExit) as e:
            D.board_measures(tmp_path / "nope.json")
        msg = str(e.value)
        assert "never recomputed" in msg and "run_nf_inj2c_dominance_baseline" in msg, (
            "a refusal that does not name its own remedy is why the precondition exists at all")

    def test_a_failed_reproduction_pin_is_VOID_not_a_null(self, tmp_path):
        """node 3a §5 branch 3: a dominance claim against a board nobody is served is not a
        measurement — and VOID and NULL are different findings."""
        p = tmp_path / "b.json"
        p.write_text(json.dumps({"application_2026": {"reproduction_pin": {
            "reproduces": False, "worst_abs_diff": 1.82, "n": 797, "tolerance": 0.05}},
            "dominance": {"arms": {"stratified": {}}}}))
        with pytest.raises(SystemExit) as e:
            D.board_measures(p)
        assert "VOID, not a null" in str(e.value)

    def test_a_report_with_no_dominance_table_REFUSES(self, tmp_path):
        p = tmp_path / "b.json"
        p.write_text(json.dumps({"application_2026": {"reproduction_pin": {"reproduces": True}},
                                 "dominance": {}}))
        with pytest.raises(SystemExit) as e:
            D.board_measures(p)
        assert "never computed" in str(e.value)

    def test_M3_and_M4_are_read_from_the_report_not_recomputed(self):
        src = _strip_comments(_RUNNER.read_text())
        body = src.split("def _board_measure(", 1)[1].split("\ndef ", 1)[0]
        # ⛔ the RAW SOURCES a recomputation would need. The DERIVED key names ("M3_worst_times_over")
        # legitimately appear — they are what is READ — so forbidding those would fail on the
        # correct implementation. This forbids the INPUTS, which is the thing that distinguishes
        # reading a committed baseline from computing a second one.
        for forbidden in ("worst_violations", "injury_giveback", "implied_per_game",
                          "max_ever_per_game", "mvp1_total", "arm_total"):
            assert forbidden not in body, (
                f"{forbidden!r} — a RAW board input — appears in the board-measure reader. M3/M4 are "
                "READ from node 3b; a second computation of a committed baseline is a second answer "
                "to one question, and the two would drift (E9.61)")

    def test_a_missing_board_figure_is_UNEVALUABLE_never_a_pass(self):
        board = {"arms": {"stratified": {}}, "served_incumbent_baseline": {}}
        for k in ("M3", "M4"):
            r = D._board_measure(board, "stratified", k)
            assert r["evaluable"] is False and r["verdict"] != "IMPROVES" if "verdict" in r else True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The bands are node 3a's, and none is derived from an observed gap
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheBands:

    def test_M1s_band_is_the_per_fold_SE_of_its_own_lift_series(self):
        pf, folds = _pf(arm_crps=[9.0, 9.4, 9.1, 9.5, 9.2, 9.3, 9.6],
                        inc_crps=10.0, arm_viol=2, inc_viol=4)
        r = D.m1_crps_lift(pf, folds, "stratified")
        lifts = np.asarray([10.0 - c for c in [9.0, 9.4, 9.1, 9.5, 9.2, 9.3, 9.6]])
        assert r["tie_band"] == pytest.approx(lifts.std(ddof=1) / np.sqrt(len(lifts)), abs=1e-4)
        assert r["band_rule"] == "R1"

    def test_M3_and_M4_bands_are_the_RECORDED_PRECISION_and_nothing_else(self):
        board = D.board_measures()
        assert D._board_measure(board, "stratified", "M3")["tie_band"] == C.M3_RECORDED_PRECISION
        assert D._board_measure(board, "stratified", "M4")["tie_band"] == C.M4_RECORDED_PRECISION

    def test_a_single_fold_cannot_form_an_R1_band_and_is_UNEVALUABLE(self):
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, folds=(2019,))
        assert D.m1_crps_lift(pf, folds, "stratified")["evaluable"] is False

    def test_no_band_is_derived_from_an_observed_gap(self):
        """node 3a §1: ⛔ no band may be derived from an observed arm-vs-incumbent gap. The R1 band
        must read the DISPERSION of the series, never its mean."""
        src = _strip_comments(_RUNNER.read_text())
        for fn in ("def m1_crps_lift(", "def m2_coherence("):
            body = src.split(fn, 1)[1].split("\ndef ", 1)[0]
            band_line = [ln for ln in body.splitlines() if "band = " in ln]
            assert band_line, f"{fn} no longer computes a band"
            assert all("std(ddof=1)" in ln for ln in band_line), (
                f"{fn}'s band is not a standard error of its own series")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# M2 — attribution-controlled, with a FOLD band
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestM2:

    def test_violations_the_control_also_produces_are_subtracted(self):
        """3a §3(b): a defect present with the ordering step OFF is not caused by it.

        ⭐ THE FIXTURE MUST MAKE THE CLAUSE OBSERVABLE (NF-D17). An earlier cut used
        arm = incumbent = control = 5, where the controlled reading (0) and the UNCONTROLLED one
        (5 − 5 = 0) are IDENTICAL — so the guard stayed green with the control deleted, and the RED
        proof caught it. Here arm=8, incumbent=6, control=7 ⇒ controlled +1, uncontrolled +2, so
        only the control's presence can produce the asserted number."""
        board = D.board_measures()
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=8, inc_viol=6, null_viol=7)
        r = D.m2_coherence(pf, folds, "stratified", board)
        assert r["mean_paired_diff_vs_incumbent"] == pytest.approx(1.0), (
            "the attributable difference is max(8−7,0) − max(6−7,0) = 1; an UNCONTROLLED reading "
            "would be 8 − 6 = 2")
        assert r["control_inert"] is False

    def test_the_inert_control_is_STATED_not_discovered(self):
        board = D.board_measures()
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, null_viol=0)
        assert D.m2_coherence(pf, folds, "stratified", board)["control_inert"] is True

    def test_the_board_reading_is_carried_as_the_BASELINE_not_the_verdict(self):
        board = D.board_measures()
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4)
        r = D.m2_coherence(pf, folds, "stratified", board)
        blk = r["board_baseline_from_node_3b"]
        assert blk["incumbent_attributable"] == 10 and blk["arm_attributable"] == 6
        assert "authoritative M2 verdict is this run's" in blk["note"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# M6 — pooled over ROWS, against a POWER floor
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestM6:

    def test_coverage_is_pooled_over_ROWS_not_averaged_over_folds(self):
        """NF1.8: a mean of per-fold rates re-weights a thin fold equal to a fat one."""
        folds = (2019, 2020)
        pf = {"stratified": {
            2019: {"coverage80_by_position": {"QB": 1.0}, "coverage_n_by_position": {"QB": 10}},
            2020: {"coverage80_by_position": {"QB": 0.5}, "coverage_n_by_position": {"QB": 190}}}}
        g = D.m6_interval_floor(pf, folds, "stratified")["groups"]["QB"]
        assert g["n_rows"] == 200
        assert g["coverage"] == pytest.approx((10 * 1.0 + 190 * 0.5) / 200, abs=1e-6)
        assert g["coverage"] != pytest.approx(0.75, abs=1e-6), "that would be the mean-of-means"

    def test_the_floor_is_DERIVED_from_n_and_is_below_nominal(self):
        """⛔ NF-D22: a flat point-floor at nominal is a ~50% coin flip on a perfectly calibrated
        band at ANY n, and does not improve with n."""
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, n_group=60)
        g = D.m6_interval_floor(pf, folds, "stratified")["groups"]["QB"]
        # rendered and compared at the SAME precision, so the table and the gate cannot disagree
        # about one number (E9.61) — the guard reads it the way the verdict does.
        assert g["power_floor"] == pytest.approx(
            round(CPF.power_floor(g["n_rows"], nominal=D.NOMINAL_COVERAGE), 4), abs=1e-12)
        assert g["power_floor"] < D.NOMINAL_COVERAGE

    def test_a_materially_short_band_still_FAILS(self):
        """The two-sided half: a floor that nothing can fail is not a floor (NF-D22)."""
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, cov=0.55)
        r = D.m6_interval_floor(pf, folds, "stratified")
        assert r["verdict"] == "REGRESSES" and set(r["groups_below_floor"]) == set(_POS)

    def test_a_group_with_no_scored_interval_is_UNEVALUABLE_never_clearing(self):
        folds = (2019,)
        pf = {"stratified": {2019: {"coverage80_by_position": {},
                                    "coverage_n_by_position": {}}}}
        g = D.m6_interval_floor(pf, folds, "stratified")["groups"]["QB"]
        assert g["evaluable"] is False and "clears" not in g


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The dominance rule
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDominance:

    def _m(self, **over):
        base = {"M1": {"verdict": "IMPROVES"}, "M2": {"verdict": "TIES"},
                "M3": {"verdict": "IMPROVES"}, "M4": {"verdict": "IMPROVES"},
                "M5": {"verdict": "TIES_OR_BETTER"}, "M6": {"verdict": "CLEARS"}}
        base.update({k: {"verdict": v} for k, v in over.items()})
        return base

    def test_improve_or_tie_everywhere_DOMINATES(self):
        assert D.dominance_verdict(self._m())["state"] == "DOMINATES"

    @pytest.mark.parametrize("m", ["M1", "M2", "M3", "M4"])
    def test_one_regression_beyond_its_band_is_a_REGRESSION(self, m):
        v = D.dominance_verdict(self._m(**{m: "REGRESSES"}))
        assert v["state"] == "REGRESSES" and v["regressed_measures"] == [m]

    def test_an_ordering_regression_is_a_REGRESSION(self):
        assert D.dominance_verdict(self._m(M5="REGRESSES"))["state"] == "REGRESSES"

    def test_a_group_below_its_interval_floor_is_a_REGRESSION(self):
        assert D.dominance_verdict(self._m(M6="REGRESSES"))["state"] == "REGRESSES"

    @pytest.mark.parametrize("m", ["M1", "M2", "M3", "M4", "M5", "M6"])
    def test_an_UNEVALUABLE_measure_is_NEVER_a_pass(self, m):
        """⭐ NF1.7 (a). A dominance claim missing a measure is not a dominance claim."""
        v = D.dominance_verdict(self._m(**{m: "UNEVALUABLE"}))
        assert v["state"] == "UNEVALUABLE" and m in v["unevaluable_measures"]

    def test_a_missing_measure_is_NEVER_a_pass(self):
        m = self._m()
        del m["M6"]
        assert D.dominance_verdict(m)["state"] == "UNEVALUABLE"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict's pre-committed branches
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheVerdict:

    def _defl(self, dsr=0.99, pbo=0.05):
        return {"binding": {"dsr_binding": dsr, "dsr_min": 0.95, "pbo": pbo, "pbo_max": 0.2,
                            "trial_sharpes": {}, "v_members": []},
                "lockstep_variance_lever": {"field_trim_status": D._FIELD_TRIM_STATUS}}

    def test_dominance_plus_clear_gates_is_DOMINATES(self):
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(),
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "DOMINATES" and v["deploy_held"] is True and v["best_alpha"] == 0

    def test_a_regression_is_a_NULL_even_when_every_gate_passes(self):
        """PM ruling 3, verbatim: 'that is a NULL, not a margin to adjust.'"""
        v = D.verdict(dominance={"state": "REGRESSES"}, defl=self._defl(),
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "NULL"

    def test_dominance_with_a_failing_DSR_is_DEFLATION_REFUSED(self):
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(dsr=0.40),
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "DEFLATION_REFUSED" and v["gates_failed"] == ["dsr"]

    def test_an_UNCOMPUTABLE_gate_is_UNDEFINED_never_FAILED(self):
        """MH2: a statistic that could not be computed is UNDEFINED, ⛔ never a failure."""
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(dsr=None),
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "UNEVALUABLE" and v["gates_undefined"] == ["dsr"]

    def test_the_fold_consistency_clause_is_the_CALIBRATED_one(self):
        """⛔ Never the raw 0.60 rate (MH2 H8) — at seven folds the calibrated clause needs 6."""
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(),
                      control={}, fold_wins=5, folds=7)
        assert v["fold_consistency_required_wins"] == 6
        assert v["state"] == "DEFLATION_REFUSED" and "fold_consistency" in v["gates_failed"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The deflation fields
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheFields:

    def test_the_binding_field_is_the_five_and_the_diagnostic_is_the_inherited_ten(self):
        assert D.BINDING_FIELD.arms == tuple(C.ARMS)
        assert D.BINDING_FIELD.declared_field_size == 5
        assert D.DIAGNOSTIC_FIELD.arms == tuple(B.ARMS)
        assert D.DIAGNOSTIC_FIELD is RB.NF_INJ2B_FIELD

    def test_there_is_no_THIRD_field(self):
        """The PM's ruling permits exactly two and forbids a third."""
        src = _strip_comments(_RUNNER.read_text())
        assert len(re.findall(r"RB\.FieldSpec\(", src)) == 1, (
            "more than one FieldSpec is constructed here — the ruling permits the BINDING field and "
            "the inherited DIAGNOSTIC one, and forbids a third")

    def test_the_field_trim_2x2_is_STRUCTURALLY_UNAVAILABLE_at_two_V_members(self):
        """§2.3(b): with two contributors the only drops are the arm under test (inadmissible,
        NF-W7h) or the sole other contributor (leaving `V` undefined)."""
        srs = {"stratified": 1.2, "feasibility_clamp": 0.4,
               "incumbent": 0.0, "mvp1_null": -2.0, "random_order": -3.0}
        out = RB._dsr_2x2(np.asarray([0.1] * 7), srs, "stratified", D.BINDING_FIELD)
        assert out["evaluable"] is False and out["structurally_unavailable"] is True
        assert out["v_member_count"] == 2 and "a fortiori" in out["why"]

    def test_the_declared_v_exclusion_drops_the_degenerates_AND_the_reference(self):
        srs = {a: float(i) for i, a in enumerate(C.ARMS)}
        members = RB._v_members(srs, D.BINDING_FIELD)
        assert set(members) == {"stratified", "feasibility_clamp"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The lockstep lever and the calendar-bound trigger
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheLockstepLever:

    def test_the_trigger_is_WITHHELD_when_SR_does_not_exceed_SR0(self):
        """⭐ NF-W8-0d: `n` enters through √(n−1), which scales a positive gap but cannot CREATE
        one. Publishing a fold trigger there is the NF-D18 misleading direction."""
        binding = {"trial_sharpes": {"stratified": 0.05, "feasibility_clamp": -3.0},
                   "v_members": ["stratified", "feasibility_clamp"]}
        out = D._lockstep(np.asarray([0.01, -0.02, 0.005, 0.0, 0.01, -0.01, 0.002]), binding)
        assert out["evaluable"] is True
        assert out["sr_gt_sr0"] is False and out["fold_trigger_publishable"] is False
        assert "never published" in out["why"]

    def test_an_unevaluable_lever_is_not_a_pass_and_still_names_the_trim_status(self):
        out = D._lockstep(np.asarray([0.1]), {"trial_sharpes": {}, "v_members": []})
        assert out["evaluable"] is False and "STRUCTURALLY UNAVAILABLE" in out["field_trim_status"]

    def test_the_lever_runs_BEFORE_any_remedy_is_named(self):
        src = _strip_comments(_RUNNER.read_text())
        body = src.split("def deflation_blocks(", 1)[1].split("\ndef ", 1)[0]
        assert "_lockstep(" in body, "the lever is no longer computed with the deflation block"
        for prescribed in ("more seasons", "more rows", "more draws", "lower-variance design"):
            assert prescribed not in body.lower(), (
                f"a remedy ({prescribed!r}) is named in the deflation block — the lever is what "
                "decides whether any such remedy exists (NF-W8-0d)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The positive control's declared partition
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePositiveControlPartition:

    def test_the_two_halves_are_disjoint_and_the_sensitive_half_is_non_empty(self):
        assert not set(C.INJECTION_SENSITIVE_GATES) & set(C.INJECTION_INVARIANT_GATES)
        assert C.INJECTION_SENSITIVE_GATES, "a control evaluated over nothing is a vacuous pass"

    def test_the_board_measures_are_declared_INJECTION_INVARIANT(self):
        """An injected CRPS effect cannot reach a property of a board."""
        for g in ("m2_coherence", "m3_worst_times_over", "m4_giveback", "m6_interval_floor"):
            assert g in C.INJECTION_INVARIANT_GATES


class TestASmokeCannotClobberTheDecisiveRecord:
    """NF-INJ3b-M D4 / NF-W2c-CBS: a runner with a fixed output path overwrites a DECIDED story's
    artifact on any partial re-run. The decided stem must be reachable ONLY by the registered folds."""

    def test_a_non_registered_fold_set_writes_its_own_stem(self):
        src = _strip_comments(_RUNNER.read_text())
        body = src.split("def main(", 1)[1]
        assert "smoke = tuple(folds) != tuple(C.FOLDS)" in body
        assert 'stem = f"{_STEM}_smoke" if smoke else _STEM' in body
        assert f'{{stem}}.json' in body and f'{{stem}}.md' in body, (
            "the report is still written to a FIXED stem — a smoke would clobber the decisive record")

    def test_the_smoke_stem_is_gitignored(self):
        ignored = [ln.strip() for ln in (Path(__file__).resolve().parents[2] / ".gitignore"
                                         ).read_text().splitlines()
                   if ln.strip() and not ln.lstrip().startswith("#")]
        for suffix in ("json", "md"):
            assert ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                    f"nf_inj2c_decisive_smoke.{suffix}") in ignored


class TestAnUndefinedFoldClauseIsNotAPass:
    """MH2 H8 (2): at n ≤ 2 the sign test's smallest attainable false-fire rate `2⁻ⁿ` already
    exceeds α, so the clause DECLARES ITSELF UNDEFINED and `wins_required` is None. An UNDEFINED
    clause is ⛔ never a pass and ⛔ never a failure — the distinction MH2's seven-state taxonomy
    exists to preserve. Found by the 2-fold code-path smoke, which is what a smoke is for."""

    def test_two_folds_make_the_clause_UNDEFINED_and_the_verdict_UNEVALUABLE(self):
        from betting_ml.utils import cv_power
        assert cv_power.fold_consistency_clause(2).wins_required is None
        v = D.verdict(dominance={"state": "DOMINATES"},
                      defl={"binding": {"dsr_binding": 0.99, "dsr_min": 0.95, "pbo": 0.05,
                                        "pbo_max": 0.2, "trial_sharpes": {}, "v_members": []},
                            "lockstep_variance_lever": {}},
                      control={}, fold_wins=2, folds=2)
        assert v["gates"]["fold_consistency"] is None
        assert "fold_consistency" in v["gates_undefined"] and v["gates_failed"] == []
        assert v["state"] == "UNEVALUABLE"

    def test_the_registered_seven_folds_require_six(self):
        from betting_ml.utils import cv_power
        assert cv_power.fold_consistency_clause(len(C.FOLDS)).wins_required == 6


class TestTheControlReadsGateNamesNotArmNames:
    """`cv_power`'s `blocking_gates` is a {arm -> [gate names]} MAPPING. Reading it as a flat list
    collects ARM names, which then all land in `blockers_unclassified` — making a CORRECT partition
    look broken. Found by the 2-fold code-path smoke; a fixture-only suite would not have seen it."""

    def test_a_mapping_is_flattened_to_its_GATE_names(self, monkeypatch):
        # RE-ANCHORED: the control now drives `cv_power` directly with THIS story's own gate table
        # (NF-INJ2b's emits `coherence_restored`, the gate PM ruling 2 removed), so the stub moves
        # to the instrument. The asserted property is unchanged (MH2.7).
        _stub(monkeypatch, verdict="BLIND",
              blocking_gates={"incumbent": ["m1_crps_lift", "m2_coherence"],
                              "stratified": ["m2_coherence"]})
        out = D.positive_control({}, (2019,), {}, {}, board={})
        assert out["blockers_on_sensitive_side"] == ["m1_crps_lift"]
        assert out["blockers_on_invariant_side"] == ["m2_coherence"]
        assert out["blockers_unclassified"] == [], (
            "arm names leaked into the blocker set — the mapping was read as a flat list")

    def test_an_unclassified_blocker_is_reported_as_UNREADABLE_never_as_a_pass(self, monkeypatch):
        _stub(monkeypatch, verdict="BLIND",
              blocking_gates={"stratified": ["a_gate_nobody_declared"]})
        out = D.positive_control({}, (2019,), {}, {}, board={})
        assert out["blockers_unclassified"] == ["a_gate_nobody_declared"]
        assert "cannot be read against it" in (out["reading"] or "")


class TestAVacuousBadgeIsRecordedNotReinterpreted:
    """⚠️ `inject(0.0)` returns the REAL payload, so "an arm survives the no-effect payload" is
    measured on real data — where H1 asserts exactly that. The instrument reads it as "the family
    certifies noise"; on a DOMINANCE disposition it is also what a TRUE hypothesis looks like.

    ⛔ The record must state both readings and choose NEITHER, and must never re-run the control
    with the null check disabled to obtain a nicer badge (§7 forbids it by name; E2.1-r)."""

    def test_a_VACUOUS_verdict_states_both_readings_and_names_the_survivors(self, monkeypatch):
        _stub(monkeypatch, verdict="VACUOUS", null_control_survivors=["stratified"])
        out = D.positive_control({}, (2019,), {}, {}, board={})
        r = out["reading"] or ""
        assert "stratified" in r, "the surviving arm is not named"
        assert "chooses NEITHER" in r and "(a)" in r and "(b)" in r, (
            "a VACUOUS badge must carry BOTH readings; picking one is the E2.1-r inversion")
        assert "PM decision" in r

    def test_the_null_control_is_never_disabled(self):
        src = _strip_comments(_RUNNER.read_text())
        assert "check_null_control=True" in src
        assert "check_null_control=False" not in src, (
            "the null check is disabled — that is re-running the control to obtain a nicer badge, "
            "which the pre-registration §7 forbids by name (E2.1-r)")
