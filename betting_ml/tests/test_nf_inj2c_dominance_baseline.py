"""NF-INJ2c nodes 3a/3b/3c — guards for the margin rule, the capture-pin, and the fold ruling.

⛔ These certify no verdict. They pin (a) that the margin CONSTRUCTION RULE was committed and says
what the runner reads, (b) that the D3 capture-pin actually refuses a re-pull rather than warning,
(c) that the dominance verdicts are computed from the rule's bands and never score an unevaluable
measure as a pass, and (d) the node-3c fold ruling and its licensing measurements.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_inj2c_dominance_baseline as DB,
)

_REPO = Path(__file__).resolve().parents[2]
_ART = _REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_RULE = _ART / "nf_inj2c_margin_construction_rule.md"
_FOLD = _ART / "nf_inj2c_fold_fidelity_finding.md"
_SPEC = _REPO / "plan_specs/nfl_fantasy/nf-inj2c.yaml"


def _flat(path: Path) -> str:
    """Whitespace-normalised text. A prose guard that matches a SINGLE-LINE substring goes red the
    moment the sentence it pins is re-wrapped — which is a formatting change, not a meaning change,
    and a guard that fires on one teaches people to weaken it."""
    return re.sub(r"\s+", " ", path.read_text())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3a — the margin construction rule exists, is committed, and OWNS the bands
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_margin_rule_is_committed_before_the_baseline_runner_can_quote_it():
    assert _RULE.exists(), (
        "the margin CONSTRUCTION RULE must be committed BEFORE the re-measure — it is the whole "
        "protection against margins reverse-engineered from the numbers the re-measure shows")


def test_every_band_the_runner_applies_is_named_in_the_rule():
    """⭐ The runner READS bands; it must not define one. A band in code that the rule does not name
    is exactly the margin-set-after-the-fact this sequencing exists to prevent."""
    txt = _flat(_RULE)
    for label, band in (("M3", DB.M3_TIE_BAND), ("M4", DB.M4_TIE_BAND)):
        assert f"| {label} |" in txt, f"{label} is not a declared measure in the rule"
        assert str(band) in txt, (
            f"the runner applies a {label} tie band of {band} that the committed rule does not name")


def test_the_rule_forbids_a_band_derived_from_an_observed_gap():
    txt = _flat(_RULE)
    assert "not a threshold chosen to reach a verdict" in txt
    assert "no band may be derived from an observed arm-vs-incumbent gap" in txt


def test_the_rule_carries_the_pms_null_branch_verbatim():
    """PM ruling 3's branch is what makes it safe to see the arm's numbers before the prereg."""
    assert "that is a NULL, not a margin to adjust" in _flat(_RULE)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3b — the D3 capture-pin REFUSES, and refuses for the right reasons
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def staged(tmp_path, monkeypatch):
    served = tmp_path / "served_projections_2026.json"
    served.write_text(json.dumps({"generated_at": "2026-08-31T12:00:00Z",
                                  "players": [{"id": "x", "fpPpr": 10.0, "g": 17.0}]}))
    monkeypatch.setattr(DB, "_SERVED_JSON", served)
    monkeypatch.setattr(DB, "_CAPTURE_STAMP", tmp_path / "nf_inj2c_capture.json")
    return served


def test_a_missing_capture_refuses_and_names_the_staging_command(staged, monkeypatch):
    with pytest.raises(SystemExit) as e:
        DB.assert_capture_intact()
    msg = str(e.value)
    assert "aws s3 cp s3://credence-prod-s3-api-cache" in msg, (
        "a refusal an operator cannot act on is a worse refusal (the NF-INFRA1 cure)")
    assert "--capture" in msg


def test_a_capture_then_an_unchanged_board_passes(staged):
    stamp = DB.capture()
    again = DB.assert_capture_intact()
    assert again["sha256"] == stamp["sha256"] == hashlib.sha256(staged.read_bytes()).hexdigest()


def test_a_REPULLED_board_is_refused_which_is_the_whole_point_of_D3(staged):
    """⭐ The two-sided half. A capture-pin that only ever passes is not a pin (NF1.7 (a))."""
    DB.capture()
    staged.write_text(json.dumps({"generated_at": "2026-08-31T19:00:00Z",
                                  "players": [{"id": "x", "fpPpr": 10.4, "g": 17.0}]}))
    with pytest.raises(SystemExit) as e:
        DB.assert_capture_intact()
    assert "CHANGED since it was captured" in str(e.value)
    assert "40.58" in str(e.value), "the refusal should carry the measurement that motivates it"


def test_recapturing_mid_study_is_refused_without_an_explicit_flag(staged):
    DB.capture()
    with pytest.raises(SystemExit) as e:
        DB.capture()
    assert "--recapture" in str(e.value)
    DB.capture(force=True)          # the explicit start-over path still works


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3b — the dominance verdicts
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _arm(*, attributable, worst_over, giveback):
    return {
        "coherence_violating_players_attributable": attributable,
        "coherence_violating_players": attributable,
        "coherence_by_position": {}, "clamp_saturation_high": 0, "clamp_saturation_low": 0,
        "injury_giveback": {"giveback_pct": giveback},
        "worst_violations": ([] if worst_over is None
                             else [{"implied_per_game": worst_over, "max_ever_per_game": 1.0}]),
    }


def test_an_arm_better_on_every_board_measure_reads_IMPROVES():
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.51, giveback=82.70),
                    "stratified": _arm(attributable=7, worst_over=1.85, giveback=27.85)}}
    r = DB.dominance_table(app)["arms"]["stratified"]
    assert (r["M2_verdict"], r["M3_verdict"], r["M4_verdict"]) == ("IMPROVES",) * 3


def test_a_single_regression_is_reported_as_one_and_not_averaged_away():
    """Strict dominance is per-measure: one regression is the verdict, ⛔ not a net score."""
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.51, giveback=82.70),
                    "arm": _arm(attributable=11, worst_over=1.85, giveback=27.85)}}
    r = DB.dominance_table(app)["arms"]["arm"]
    assert r["M2_verdict"] == "REGRESSES"
    assert r["M3_verdict"] == "IMPROVES"       # ⛔ and it does NOT rescue M2


def test_a_measure_with_no_value_is_UNEVALUABLE_and_never_a_pass():
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.51, giveback=82.70),
                    "clean": _arm(attributable=0, worst_over=None, giveback=27.85)}}
    r = DB.dominance_table(app)["arms"]["clean"]
    assert r["M3_verdict"] == "UNEVALUABLE", (
        "an arm with no violation has no worst-breach to compare; scoring that as IMPROVES would "
        "read a missing measurement as a win (NF1.7 (a))")


def test_the_giveback_measure_does_not_reward_over_discounting():
    """M4 = max(pct, 0) — the rule §3(a) judgment, pinned so it cannot drift back to the signed
    value, which would let an arm bank credit for a DIFFERENT defect."""
    assert DB._giveback_measure(-16.31) == 0.0
    assert DB._giveback_measure(27.85) == pytest.approx(27.85)
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.0, giveback=82.70),
                    "over": _arm(attributable=9, worst_over=2.0, giveback=-16.31),
                    "zero": _arm(attributable=9, worst_over=2.0, giveback=0.0)}}
    d = DB.dominance_table(app)["arms"]
    assert d["over"]["M4_giveback_measure"] == d["zero"]["M4_giveback_measure"]
    assert d["over"]["M4_giveback_signed"] == -16.31    # the signed value is still reported


def test_the_fold_measures_are_named_unevaluated_rather_than_omitted():
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.0, giveback=1.0)}}
    r = DB.dominance_table(app)["arms"]["incumbent"]
    assert "UNEVALUATED" in r["M1_M5_M6"], (
        "a dominance table silently missing three of its six measures reads as a complete one")


def test_the_attribution_control_arm_cannot_be_dropped_from_a_run():
    import inspect
    src = inspect.getsource(DB.main)
    assert 'if "incumbent" not in arms or "mvp1_null" not in arms:' in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3c — the fold ruling and the measurements licensing it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_fold_finding_is_committed_and_states_the_ruling_either_way():
    assert _FOLD.exists()
    txt = _flat(_FOLD)
    assert "2018 IS NOT ADMITTED" in txt
    assert "state the finding either way" in txt


def test_the_empty_pool_arithmetic_the_finding_rests_on_still_holds():
    """⭐ The finding's first leg is arithmetic on the SHIPPED `base_from`, so it is checkable here
    rather than only in prose — if `build_season_projection`'s window ever changes, this goes red."""
    def base_seasons(projection_season, base_from=2017):
        return [b for b in range(base_from, projection_season - 1) if b + 1 < projection_season]
    assert base_seasons(2018) == [], "a 2018 fold would no longer be empty — re-open the ruling"
    assert base_seasons(2019) == [2017]
    assert base_seasons(2025) == [2017, 2018, 2019, 2020, 2021, 2022, 2023]


def test_the_finding_records_that_the_eighth_fold_moves_the_gate_the_WRONG_way():
    txt = _flat(_FOLD)
    assert "2.0101" in txt and "1.6418" in txt
    assert "−0.3682" in txt, "the Sharpe DELTA is the statistic the finding turns on"
    assert "DILUTES" in txt


def test_the_finding_refuses_to_pick_the_declared_field():
    """A field chosen by which one clears is the selection bias DSR exists to deflate (MH2.2)."""
    txt = _flat(_FOLD)
    assert "no per-candidate-family DSR has been computed" in txt


def test_the_spec_carries_the_pm_rescope():
    txt = _flat(_SPEC)
    assert "PM RE-SCOPE RULING 2026-08-31" in txt
    assert "STRICT-DOMINANCE disposition, alone" in txt


def test_the_spec_records_the_field_declaration_and_who_made_it():
    """⭐ RE-ANCHORED (2026-09-01), not deleted. This guard was written to pin the HOLD; the PM has
    since RULED, so it now pins the same invariant on the other side of that ruling — the field
    declaration lives in the SPEC and is attributed to the PM.

    The invariant is unchanged and is the reason the guard exists: a question that lives only in a
    handoff message is one a later session answers by not noticing it, and the thing it would
    answer by accident (which field the deflation gates run over) is precisely the selection bias
    DSR exists to deflate (MH2.2). ⛔ Weakening or deleting a guard because the world moved past
    it is what re-anchoring exists to prevent (MH2.7)."""
    txt = _flat(_SPEC)
    assert "PM ruling (2026-09-01, NF-INJ2c prereg)" in txt, (
        "the field declaration is no longer attributed to the PM in the spec")
    assert "the deflation gates' BINDING field is NF-INJ2c's own coherent family" in txt
    assert "per-candidate-family DSR was computed" in txt, (
        "the record must still state that no per-family DSR preceded the declaration (NF-INJ3b-M)")
    assert "HELD FOR A PM RULING — THE DSR FIELD DECLARATION" not in txt, (
        "a stale HELD marker survives the ruling — the spec would misreport the story's state")
