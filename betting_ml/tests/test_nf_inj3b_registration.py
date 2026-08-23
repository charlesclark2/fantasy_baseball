"""test_nf_inj3b_registration.py — guards on NF-INJ3b's REGISTRATION, which is what the story is.

NF-INJ3b changes nothing about the DATA or the SCORING: it re-registers NF-INJ3 with the two
specification items that story left unstated — `V`'s membership and the BH family — named up front.
So the things worth guarding are exactly those: the declared field, `V`'s membership, the BH family,
the registered primary, the era floor, the reproduction pin's tolerance, and the output discipline
that keeps a post-decision story out of a decided story's artifacts.

⭐ Every guard here is RED-proven by `betting_ml/tests/nf_inj3b_red_proof.py` — a guard that cannot
fail is not a guard (NF1.7 (a) / INC-38 / NF-D17), and each RED break asserts it LANDED on disk,
REMOVED the asserted token, and anchored UNIQUELY (#682 / #815 / E11.24).
"""
from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj3b_injury_games as B

_HERE = Path(B.__file__).resolve().parent
_PREREG = _HERE / "ablation_results" / "nf_inj3b_preregistration.md"
_SRC = Path(B.__file__).read_text()


def _code_only(src: str) -> str:
    """Strip comments AND docstrings before scanning source.

    ⭐ INC-38: a source-inspection guard that PROSE can satisfy is vacuous — and it bites BOTH ways.
    Here the `_compare_crps` docstring literally contains "round(..., 6)" while EXPLAINING why the
    comparison must not round, so an un-stripped scan fails on a correct implementation."""
    try:
        tree = ast.parse(src)
    except SyntaxError:                                   # a mid-mutation red-proof source
        return "\n".join(l.split("#")[0] for l in src.splitlines())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _fold(year, crps_by_arm, oracle_delta=0.5):
    """A minimal per-fold record shaped like `run_nf_inj3_injury_games.score_fold`'s output."""
    return {
        "year": year,
        "arms": {a: {"crps": c, "mae": c, "mean_mu": 1.0, "n": 40}
                 for a, c in crps_by_arm.items()},
        "oracles": {a: {"crps": c - oracle_delta} for a, c in crps_by_arm.items()},
        "anchors": {"pooled_mean": {"crps": 3.0},
                    "permuted_timing": {"crps": crps_by_arm[B.PRIMARY_ARM] + 0.1}},
        "matched_n": {"crps": 2.5},
    }


#: per-fold LIFTS over the incumbent, chosen so the fixture exercises the real statistics rather
#: than degenerating: the lifts VARY across folds (a constant lift gives every arm a trial Sharpe of
#: exactly 0 and `dsr_conv` returns None, which would make several gate tests vacuous), the primary
#: has the highest and steadiest lift, and the two degenerates lose everywhere.
_LIFTS: dict[str, list[float]] = {
    "incumbent":       [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    "fitted_status":   [0.10, 0.30, -0.05, 0.25, 0.15, 0.20, 0.28],
    "timing_aware":    [0.12, 0.32, -0.02, 0.27, 0.17, 0.22, 0.30],
    "hurdle_transfer": [0.28, 0.30, 0.26, 0.32, 0.29, 0.31, 0.27],
    "all_zero":        [-0.50, -0.60, -0.55, -0.52, -0.58, -0.54, -0.56],
    "no_cap":          [-1.70, -1.80, -1.60, -1.75, -1.65, -1.72, -1.68],
}
_INCUMBENT_CRPS = [2.40, 2.41, 2.39, 2.42, 2.40, 2.43, 2.38]


def _field(i: int) -> dict:
    return {a: _INCUMBENT_CRPS[i] - lifts[i] for a, lifts in _LIFTS.items()}


PER_FOLD = [_fold(2019 + i, _field(i)) for i in range(7)]


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheDeclaredField:
    def test_the_field_is_six_arms_and_the_size_is_derived_not_restated(self):
        assert B.DECLARED_FIELD_SIZE == len(B.ARMS) == 6

    def test_sus_regime_is_excluded_on_MECHANISM_with_a_recorded_reason(self):
        """⭐ The narrowing must be justified in the REGISTRATION, not discovered from scores."""
        assert "sus_regime" not in B.ARMS
        assert "sus_regime" in B.EXCLUDED_ON_MECHANISM
        why = B.EXCLUDED_ON_MECHANISM["sus_regime"].lower()
        assert "inactive" in why or "0 rows" in why

    def test_every_declared_arm_is_one_the_inherited_harness_can_actually_score(self):
        """A registration may narrow the parent's field; it may not INVENT an arm mid-run."""
        assert set(B.ARMS) <= set(IG.ARMS)

    def test_the_primary_is_registered_and_is_the_hurdle_form(self):
        assert B.PRIMARY_ARM == "hurdle_transfer"
        assert B.PRIMARY_ARM in B.ARMS

    def test_the_matched_foil_shares_the_primarys_covariates_so_the_delta_is_the_split(self):
        """`timing_aware` and `hurdle_transfer` differ ONLY in the availability split — that is what
        makes gate 9 an attribution rather than a comparison of two different models."""
        assert B.MATCHED_FOIL == "timing_aware"
        assert B.MATCHED_FOIL in B.ARMS
        src = Path(IG.__file__).read_text()
        assert 'if arm == "timing_aware":\n        f = TIMING_FEATURES + BASE_FEATURES' in src
        assert 'feats = TIMING_FEATURES + BASE_FEATURES' in src   # fit_hurdle's covariates


class TestVMembership:
    """preregistration §3 — binding registration item (1)."""

    def test_the_incumbent_REFERENCE_arm_is_excluded_from_V(self):
        """⭐ THE SINGLE SPECIFICATION CHANGE vs NF-INJ3 (MH2.1 (a)): the reference arm's skill
        series is identically ZERO by construction, so it inflates a small family's `V`."""
        assert B.INCUMBENT_REFERENCE in B.V_EXCLUDED_ARMS

    def test_the_pre_registered_degenerates_are_excluded_from_V(self):
        for d in B.DEGENERATE_ARMS:
            assert d in B.V_EXCLUDED_ARMS

    def test_V_is_measured_over_exactly_the_non_degenerate_non_reference_arms(self):
        """⭐ Asserts the VALUE, not only the reported membership. A first cut checked `V_arms`
        alone — and the RED proof showed that breaking the `srs_v` DSR actually consumes left the
        reported list untouched, i.e. the guard passed while the computation was wrong (#815)."""
        d = B.deflation(PER_FOLD, B.PRIMARY_ARM)
        expected = {"fitted_status", "timing_aware", "hurdle_transfer"}
        assert set(d["V_arms"]) == expected
        # rel tolerance, because `trial_sharpes` is reported at 4dp while `V_registered` is
        # computed from the raw series — far tighter than any membership change could hide in
        # (adding either degenerate moves V by orders of magnitude, asserted below).
        v = float(np.var([d["trial_sharpes"][a] for a in sorted(expected)], ddof=1))
        assert d["V_registered"] == pytest.approx(v, rel=1e-3), (
            "the REPORTED V membership and the V the DSR consumes have diverged")
        v_all = float(np.var(list(d["trial_sharpes"].values()), ddof=1))
        assert abs(d["V_registered"] - v_all) > 1.0, (
            "V is indistinguishable from the whole-field variance — the exclusions did nothing")

    def test_n_trials_stays_at_the_FULL_declared_field_so_nothing_escapes_multiplicity(self):
        """DSR-CONV: an excluded-from-`V` arm still pays FULL multiplicity through `N`."""
        d = B.deflation(PER_FOLD, B.PRIMARY_ARM)
        assert d["n_trials"] == B.DECLARED_FIELD_SIZE == 6

    def test_the_reference_arms_trial_sharpe_really_is_structurally_zero(self):
        """The reason MH2.1 (a) exists, measured rather than asserted."""
        d = B.deflation(PER_FOLD, B.PRIMARY_ARM)
        assert d["trial_sharpes"][B.INCUMBENT_REFERENCE] == 0.0


class TestTheBHFamily:
    """preregistration §6 — binding registration item (2)."""

    def test_the_family_is_declared_single_hypothesis_at_the_repo_q(self):
        assert B.BH_FAMILY == "single_hypothesis"
        assert B.BH_FAMILY_SIZE == 1
        assert B.BH_Q == pytest.approx(0.10)

    def test_the_registered_family_BINDS_even_when_the_strict_reading_disagrees(self):
        """⭐ The whole point of naming a family BEFORE the p-value: the registered reading binds
        whichever way it falls. On the real data the two DISAGREE (single passes at p=0.0501, strict
        fails at a rank-1 cutoff of 0.0333), so this is not a hypothetical."""
        # ⭐ ISOLATE THE BH BLOCK. `"admissible_to_act_on": False` occurs TWICE in the runner (here
        #    and in the deflation diagnostics), so scanning the WHOLE source lets the OTHER
        #    occurrence satisfy this clause — a vacuous guard the RED proof caught (NF-D17).
        block = re.search(r'"disclosed_not_binding": \{(.*?)\n    \}', _SRC, re.S)
        assert block, "the disclosed sensitivity block is gone — this guard would pass on nothing"
        assert '"admissible_to_act_on": False' in block.group(1)
        # the binding verdict is computed from the SINGLE-hypothesis cutoff, not the strict one
        m = re.search(r'"survives": bool\(p_primary is not None and p_primary < (\w+)\)', _SRC)
        assert m and m.group(1) == "BH_Q"

    def test_the_strict_across_arms_reading_is_DISCLOSED_not_silently_dropped(self):
        assert "rank1_cutoff" in _SRC and "all_pvalues" in _SRC


class TestTheReproductionPin:
    """preregistration §8 — the pin is what makes "only the REGISTRATION changed" a MEASUREMENT."""

    def test_the_tolerance_is_1e_9_and_is_not_a_rounded_comparison(self):
        assert B.PIN_TOL == 1e-9
        body = _code_only(inspect.getsource(B._compare_crps))
        assert body.strip(), "empty body — this guard would pass on nothing"
        assert "round(" not in body, "the pin must compare RAW floats: rounding caps it at 1e-6"
        assert "PIN_TOL" in body

    def test_a_missing_parent_artifact_is_a_FAILED_check_never_a_pass(self, tmp_path):
        out = B.reproduction_pin_vs_parent(PER_FOLD, tmp_path / "nope.json", None)
        assert out["evaluable"] is False
        assert out.get("passes") is not True

    def test_an_incomplete_comparison_is_VACUOUS_and_therefore_fails(self, tmp_path):
        """⭐ NON-VACUITY FIRST: a parent artifact missing arms would otherwise compare a handful of
        values, find them equal, and report a PASS on almost nothing."""
        thin = {"per_fold": [{"year": f["year"],
                              "arms": {"incumbent": f["arms"]["incumbent"]}} for f in PER_FOLD]}
        p = tmp_path / "thin.json"
        p.write_text(json.dumps(thin))
        out = B._compare_crps(PER_FOLD, p)
        assert out["non_vacuous"] is False
        assert out["passes"] is False
        assert out["max_abs_crps_difference"] == 0.0     # every compared value AGREED

    def test_a_difference_above_the_tolerance_fails_and_names_the_diverging_arms(self, tmp_path):
        drift = {"per_fold": [{"year": f["year"],
                               "arms": {a: {"crps": v["crps"] + (1e-6 if a == "timing_aware" else 0.0)}
                                        for a, v in f["arms"].items()}} for f in PER_FOLD]}
        p = tmp_path / "drift.json"
        p.write_text(json.dumps(drift))
        out = B._compare_crps(PER_FOLD, p)
        assert out["passes"] is False
        assert out["arms_that_diverge"] == ["timing_aware"]

    def test_a_missing_attribution_control_is_NOT_scored_as_clean(self, tmp_path):
        """A pin miss with no control cannot be attributed — and an unevaluable control is never a
        pass (NF1.7 (a))."""
        parent = tmp_path / "p.json"
        parent.write_text(json.dumps({"per_fold": [
            {"year": f["year"], "arms": {a: {"crps": v["crps"]} for a, v in f["arms"].items()}}
            for f in PER_FOLD]}))
        out = B.reproduction_pin_vs_parent(PER_FOLD, parent, None)
        assert out["environment_control"]["evaluable"] is False
        assert "divergence_attribution" not in out


class TestDeflationWiring:
    def test_pbo_is_computed_on_NEGATED_crps(self):
        """CRPS is a LOSS and `cscv_pbo` picks the in-sample ARGMAX — the sign being wrong reports
        the field upside-down, and the result still looks like a number."""
        assert '[[-f["arms"][a]["crps"] for f in per_fold] for a in arms]' in _SRC

    def test_a_dsr_reached_by_deleting_the_arm_under_test_is_REFUSED(self):
        """NF-W7h: `V` is a sample variance, so 'drop the most extreme trial Sharpe' can drop the
        WINNER. Here the primary IS the most extreme, so the 2×2 must refuse."""
        dg = B.deflation_diagnostics(PER_FOLD, B.PRIMARY_ARM,
                                     B.deflation(PER_FOLD, B.PRIMARY_ARM))
        assert dg["nf_w7h_drop_most_extreme"]["evaluable"] is False
        assert dg["nf_w7h_drop_most_extreme"]["dropped_arm"] == B.PRIMARY_ARM

    def test_the_parent_convention_diagnostic_is_marked_INADMISSIBLE(self):
        dg = B.deflation_diagnostics(PER_FOLD, B.PRIMARY_ARM,
                                     B.deflation(PER_FOLD, B.PRIMARY_ARM))
        assert dg["parent_convention_reference_inside_v"]["admissible_to_act_on"] is False

    def test_the_whole_field_figure_is_reported_beside_the_binding_one(self):
        d = B.deflation(PER_FOLD, B.PRIMARY_ARM)
        assert "dsr_whole_field" in d and "V_whole_field" in d


class TestGates:
    def test_all_nine_registered_gates_must_pass_to_ship(self):
        anchors = B.anchor_audit(PER_FOLD, B.PRIMARY_ARM)
        pooled = {a: {"mean_lift": 0.28 if a == B.PRIMARY_ARM else 0.1,
                      "crps": 2.1, "folds_beating_incumbent": 6,
                      "per_fold_lift": [0.28] * 7} for a in B.ARMS}
        v = B.verdict(primary=B.PRIMARY_ARM, pooled=pooled,
                      defl=B.deflation(PER_FOLD, B.PRIMARY_ARM), anchors=anchors,
                      fold_clause={"passes": True}, bh={"survives": True},
                      permutation={"beats": True}, foil={"mean_delta": 0.05})
        assert len(v["gates"]) == 9
        assert v["ship"] is True
        for g in v["gates"]:
            broken = dict(v["gates"], **{g: False})
            assert not all(x is True for x in broken.values()), f"gate {g} does not gate"

    def test_gate_9_measures_the_hurdle_split_not_timing(self):
        """NF-INJ3's gate 9 attributed TIMING. NF-INJ3b's primary is the hurdle, so its foil — and
        therefore its attribution — is a DIFFERENT quantity, and the name must say so."""
        assert "hurdle_attributable" in _SRC
        assert "timing_attributable" not in _SRC

    def test_a_degenerate_that_WINS_is_fatal(self):
        bad = [_fold(2019 + i, dict(_field(i), all_zero=1.0)) for i in range(7)]
        anchors = B.anchor_audit(bad, B.PRIMARY_ARM)
        assert anchors["_degenerates"]["all_zero"]["loses_to_primary"] is False

    def test_an_unevaluable_matched_n_control_fails_the_oracle_gate(self):
        no_mn = [dict(f, matched_n=None) for f in PER_FOLD]
        anchors = B.anchor_audit(no_mn, B.PRIMARY_ARM)
        assert anchors["_matched_n_control"]["evaluable"] is False

    def test_a_missing_own_form_oracle_is_recorded_as_NOT_evaluable(self):
        blind = [dict(f, oracles={k: v for k, v in f["oracles"].items()
                                  if k != "fitted_status"}) for f in PER_FOLD]
        anchors = B.anchor_audit(blind, B.PRIMARY_ARM)
        assert anchors["fitted_status"]["evaluable"] is False


class TestOutputDiscipline:
    """A post-decision story never clobbers a DECIDED story's audit trail."""

    def test_every_output_stem_this_runner_can_write_is_an_nf_inj3b_path(self):
        """⛔ `nf_inj3_*` is a DECIDED story's namespace. Every literal this runner can hand to its
        writer must be in its OWN."""
        q = r"['\"]"                       # ast.unparse normalises quote style
        stems = re.findall(
            rf"stem = args\.out or \({q}([a-z0-9_]+){q}\s*if .*? else {q}([a-z0-9_]+){q}\)",
            _code_only(_SRC))
        assert stems, "no output stem found — this guard would pass on NOTHING"
        flat = [s for pair in stems for s in pair]
        assert len(flat) == 2
        assert all(s.startswith("nf_inj3b_") for s in flat), flat

    def test_the_parent_artifacts_are_only_ever_READ(self):
        code = _code_only(_SRC)
        for name in B.PARENT_JSON.values():
            assert name.startswith("nf_inj3_"), name
            assert re.search(rf"['\"]{re.escape(name)}['\"]", code), name
        # the ONLY writer in this module targets `stem`, which the guard above pins to nf_inj3b_*
        writes = re.findall(r'\(_REPORT_DIR / ([^)]+)\)\.write_text', code)
        assert writes, "no write site found — this guard would pass on NOTHING"
        assert all("stem" in w for w in writes), writes

    def test_the_parent_harness_is_imported_not_reimplemented(self):
        """The reproduction pin is only meaningful because the SCORING is inherited, not copied."""
        assert "run_nf_inj3_injury_games as R3" in _SRC
        assert "R3.score_fold(pop, y)" in _SRC
        assert "def score_fold" not in _SRC


class TestPreRegistrationIsThePrimarySource:
    def test_the_preregistration_exists_and_carries_all_six_binding_items(self):
        t = _PREREG.read_text()
        assert "binding registration item (1)" in t.lower() or "item (1)" in t.lower()
        for needle in ("MH2.1 (a)", "single_hypothesis" if False else "SINGLE hypothesis",
                       "hurdle_transfer", "ON MECHANISM", "2016", "HONESTY CLAUSE"):
            assert needle in t, needle

    def test_the_preregistration_refuses_to_inherit_the_parents_diagnostic(self):
        """⭐ The landmine this story exists to encode: a diagnostic DSR does not transfer to a
        narrower field."""
        t = " ".join(_PREREG.read_text().split())          # the document is line-wrapped
        assert "0.973" in t
        assert "not inherited" in t.lower()
        assert "menu" in t.lower()                            # ⛔ no per-candidate-family DSR menu

    def test_the_era_floor_is_the_inherited_data_fidelity_quantity(self):
        assert IG.ERA_MIN_SEASON == 2016
        assert "2016" in _PREREG.read_text()
