"""test_plat_cvp1_classify_null_hardening.py — PLAT-CVP1 guards.

FOUR measured defects in one shared instrument, each found by a study that did the right local thing
(fix at the CALL SITE, preserve the instrument's raw output beside it, file the gap) and each saying
the same thing about where the fix belonged — MH2.7's own lesson (i): **a defect corrected N times
downstream is a defect in the INSTRUMENT.**

  1. **NCAAF-VAL1** — `GENUINE_ABSENCE` short-circuited ahead of every power reading, so 5 of 6
     buckets were badged "do NOT re-test", including the one bucket whose interval still ADMITTED
     the pre-registered meaningful effect.
  2. **NCAAF-VAL3** — the classifier took no PBO argument at all, so it could express PBO-UNDEFINED
     but never PBO-EVALUATED-AND-FAILED, and returned `POWER_LIMITED` while PBO was what refused.
  3. **NF-W8-0d R2** — the `DSR_UNREACHABLE` remedy named "a lower-variance design", a lever the
     lockstep invariant makes deterministically void when `SR ≤ SR0`. That sentence sent NF-W7f,
     NF-W7j and NF-W8-0c at the same wall.
  4. **MLB-HV2-1** — with a 6pp bias INJECTED, every metric gate fired and a FIELD-level PBO applied
     as a PER-ARM gate (0.426) vetoed the planted effect.

⭐ **THE FOUR RECORDS ARE THE FIXTURES, AND THEY ARE READ, NEVER EDITED.** Every case below is driven
from the committed artifact — the numbers are not retyped, they are loaded — so a guard cannot drift
from the record it claims to reproduce, and no recorded verdict is recomputed or restated. The
interim hand-record rule those studies followed retires for FUTURE callers only.

⚠️ **EVERY CLAUSE IS RED-PROVEN TWO-SIDED**: the historical case must classify correctly AND a
deliberate regression to the pre-fix behaviour must go red. The mutation harness asserts the break
LANDED and that its target was UNIQUE before re-running anything — a RED proof that silently no-ops
its own break reports a false "the guard caught it" (#682), and one that lands on a byte-identical
sibling reports a false "the guard is vacuous" (the E11.24 prediction_log lesson), which is the more
dangerous direction because it invites weakening a correct guard.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from betting_ml.utils import cv_power
from betting_ml.utils.cv_power import classify_null

ROOT = Path(__file__).resolve().parents[2]
VAL1 = ROOT / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_val1_clv_week_strat.json"
VAL3 = ROOT / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_val3_cold_start_mu.json"
W8_0D = ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_w8_0d_dsr_frontier.json"
HV2_1 = ROOT / "ablation_results/mlb_hv2_1_market_bias.json"

#: numeric reproduction tolerance (the standing 1e-9 pin)
TOL = 1e-9


def _record(path: Path) -> dict:
    assert path.exists(), f"the fixture RECORD is missing: {path} — the guard would pin nothing"
    return json.loads(path.read_text())


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RED-proof harness — mutate the real source in-process, prove the break LANDED and was UNIQUE
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_SRC = Path(cv_power.__file__)


def _mutated(*replacements: tuple[str, str]) -> ModuleType:
    src = _SRC.read_text()
    for old, new in replacements:
        # ⚠️ UNIQUENESS is asserted, not assumed. Two functions with byte-identical tails make a
        # single-count replace land on the WRONG one, and the harness then reports "the guard is
        # vacuous" for a guard that is fine — a FALSE finding that invites weakening it.
        assert src.count(old) == 1, f"mutation target is not uniquely present: {old!r}"
        src = src.replace(old, new)
    assert src != _SRC.read_text(), "the mutation did not change the source — the proof is vacuous"
    name = "cv_power_plat_cvp1_mutated"
    mod = ModuleType(name)
    mod.__file__ = str(_SRC)
    sys.modules[name] = mod          # `@dataclass` resolves annotations via sys.modules
    try:
        exec(compile(src, str(_SRC), "exec"), mod.__dict__)
    finally:
        sys.modules.pop(name, None)
    return mod


#: Defect 1 — delete the interval consultation ⇒ the pre-fix unconditional short-circuit.
_BREAK_THE_INTERVAL_CONSULT = ("        if meaningful_sd_units is None:\n", "        if True:\n")
#: Defect 2 — silence the PBO branch ⇒ a PBO refusal falls through to a POWER state again.
_BREAK_THE_PBO_BRANCH = ("    if pbo is not None:\n", "    if False:\n")
#: Defect 3 — stop consulting the computed lockstep ⇒ the void lever is prescribed again.
_BREAK_THE_LOCKSTEP_CONSULT = ("        if lockstep is not None and lockstep.closed:\n",
                               "        if False:\n")
#: Defect 4 — accept a per-arm-applied PBO as a refusal ⇒ the misapplication is admitted again.
_BREAK_THE_PER_ARM_REFUSAL = ('            if pbo_application == "per_arm":\n', "            if False:\n")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 1 — NCAAF-VAL1: consult the interval before claiming absence
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def _val1_cases():
    """VAL1's six bucket × market cells, loaded from its committed artifact.

    The bar and the interval are expressed the way VAL1 registered them — as a DELTA from the
    breakeven, in percentage points — so `meaningful_sd_units` and `effect_ci_upper_sd_units` share
    one unit and one origin, which is the whole contract of the new input.
    """
    rec = _record(VAL1)
    breakeven = rec["contract"]["breakeven"]
    meaningful = rec["contract"]["meaningful"]
    out = []
    for bucket, markets in rec["primary"]["buckets"].items():
        for market, v in markets.items():
            out.append((f"{market}/{bucket}", v, breakeven, meaningful))
    return out


@pytest.mark.parametrize("name,v,breakeven,meaningful", _val1_cases())
def test_every_val1_bucket_now_classifies_as_its_hand_corrected_state(name, v, breakeven, meaningful):
    """⭐ THE DEFECT-1 FIXTURE. VAL1 corrected 5 of 6 buckets at the call site; the instrument now
    reaches the same reading unaided from the same inputs.

    VAL1's local label for "the interval is wholly below the bar" is `MEASURED_IMMATERIAL`. That is a
    CALL-SITE name and this story does not adopt it: the instrument's state for a decisive
    below-the-bar reading is `GENUINE_ABSENCE`, whose contract ("no re-test") is exactly what
    VAL1 recorded for those cells. The mapping is stated here rather than in the record, because
    ⛔ VAL1's record is a fixture, not a thing to restate.
    """
    ps = v["per_season"]
    got = classify_null(
        metric=name, n_folds=ps["n_folds"], n_arms=3,
        beats_foil=bool(v["hit_rate"] > breakeven),
        observed_sr=ps["observed_sr"], var_trials_sr=0.19,
        skew=ps["skew"], kurt=ps["kurt"],
        mde_sd_units=v["mde_pp"],
        meaningful_sd_units=100.0 * (meaningful - breakeven),
        effect_ci_upper_sd_units=100.0 * (v["upper_bound_bonf"] - breakeven),
        declared_field_size=3, degenerates_excluded_from_v=True)
    recorded = v["null"]["corrected"]["state"]
    expected = "GENUINE_ABSENCE" if recorded == "MEASURED_IMMATERIAL" else recorded
    assert got.state == expected, f"{name}: recorded {recorded}, instrument {got.state}"
    if got.state == "GENUINE_ABSENCE":
        assert got.retest_trigger is None, "a decisive null publishes NO trigger (NF-D18)"


def test_the_val1_fixture_still_exercises_both_sides_of_the_bar():
    """NON-VACUITY. If every recorded cell landed on one side, the parametrized clause above would
    pin a constant. VAL1's own six cells straddle the bar; assert that rather than assume it."""
    states = {v["null"]["corrected"]["state"] for _, v, _, _ in _val1_cases()}
    assert {"MEASURED_IMMATERIAL", "POWER_LIMITED"} <= states, \
        "the record no longer contains both an interval-decisive and an interval-undecidable cell"


def test_a_caller_with_no_meaningful_bar_is_byte_identical_to_the_pre_fix_behaviour():
    """⭐ THE BACK-COMPAT HALF, and it is why no recorded verdict outside VAL1's class moves. With no
    pre-registered bar there is no interval to read one against, so the point-estimate rule is the
    only rule there is — and it is unchanged, reason text included."""
    v = classify_null(metric="m", n_folds=11, n_arms=7, beats_foil=False)
    assert v.state == "GENUINE_ABSENCE" and v.retest_trigger is None
    assert "No sample size rescues a negative point estimate" in v.reason


def test_the_absence_evidence_is_recorded_so_a_weaker_reading_is_never_silent():
    """An MDE-backed absence and an interval-backed one are not the same claim (the MDE asks "what
    would I have caught?", the interval "what is still plausible given what I saw"), and the record
    must say which one certified it — NF1.7 (a): a check that did not run is not a check that
    passed."""
    interval = classify_null(metric="m", n_folds=11, n_arms=5, beats_foil=False,
                             meaningful_sd_units=1.0, effect_ci_upper_sd_units=0.4)
    mde = classify_null(metric="m", n_folds=11, n_arms=5, beats_foil=False,
                        meaningful_sd_units=1.0, mde_sd_units=0.4)
    neither = classify_null(metric="m", n_folds=11, n_arms=5, beats_foil=False,
                            meaningful_sd_units=1.0, mde_sd_units=3.0)
    assert interval.state == "GENUINE_ABSENCE" and interval.detail["absence_evidence"] == "interval"
    assert mde.state == "GENUINE_ABSENCE" and mde.detail["absence_evidence"] == "mde"
    assert neither.state == "POWER_LIMITED"
    assert "interval" in (neither.retest_trigger or "")


def test_an_absence_certified_by_nothing_is_refused():
    """The narrowest case and the one the pre-fix code got most wrong: a bar on record, a negative
    point estimate, and NO power statistic of any kind. That is not an absence — it is an unread
    design, and badging it "do NOT re-test" retires a live mechanism on no evidence."""
    v = classify_null(metric="m", n_folds=11, n_arms=5, beats_foil=False, meaningful_sd_units=1.0)
    assert v.state == "POWER_LIMITED"
    assert v.detail["absence_evidence"].startswith("none")


def test_red_defect1_deleting_the_interval_consult_restores_the_over_claim():
    """RED: with the consultation removed, VAL1's `ats/wk1-3` — the bucket whose interval ADMITS the
    meaningful effect — is badged `GENUINE_ABSENCE` again, exactly as VAL1 recorded of the raw
    instrument."""
    rec = _record(VAL1)
    breakeven, meaningful = rec["contract"]["breakeven"], rec["contract"]["meaningful"]
    v = rec["primary"]["buckets"]["wk1-3"]["ats"]
    assert v["null"]["corrected"]["state"] == "POWER_LIMITED", "the fixture cell moved"
    kw = dict(metric="ats/wk1-3", n_folds=v["per_season"]["n_folds"], n_arms=3, beats_foil=False,
              mde_sd_units=v["mde_pp"],
              meaningful_sd_units=100.0 * (meaningful - breakeven),
              effect_ci_upper_sd_units=100.0 * (v["upper_bound_bonf"] - breakeven))
    assert classify_null(**kw).state == "POWER_LIMITED"
    broken = _mutated(_BREAK_THE_INTERVAL_CONSULT)
    assert broken.classify_null(**kw).state == "GENUINE_ABSENCE", \
        "the deliberate regression did not reinstate the pre-fix over-claim — the guard is vacuous"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — NCAAF-VAL3: a deflation gate that was EVALUATED and FAILED
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def _val3_kwargs() -> dict:
    """VAL3's recorded classifier inputs, read back off its artifact."""
    nc = _record(VAL3)["null_classification"]
    d = nc["instrument_detail"]
    return dict(metric="crps_total_wk1_3", n_folds=d["n_folds"], n_arms=d["n_arms"],
                beats_foil=True, observed_sr=d["observed_sr"], var_trials_sr=d["var_trials_sr"],
                p_one_sided=0.0, bh_cutoff=d["bh_cutoff"],
                declared_field_size=d["declared_field_size"],
                degenerates_excluded_from_v=d["degenerates_excluded_from_v"])


def test_val3s_recorded_inputs_still_reproduce_its_recorded_instrument_state():
    """⭐ THE LOAD-BEARING BACK-COMPAT CHECK for defect 2. VAL3's own call passed no PBO, and its
    recorded state must be UNCHANGED — the fix adds a reading, it does not move a recorded one."""
    nc = _record(VAL3)["null_classification"]
    v = classify_null(**_val3_kwargs())
    assert v.state == nc["instrument_state"] == "POWER_LIMITED"
    assert v.retest_trigger == nc["instrument_retest_trigger"]


def test_supplying_the_pbo_that_actually_refused_names_the_gate_that_bound():
    """⭐ THE DEFECT-2 FIXTURE. VAL3 hand-recorded `DEFLATION_REFUSED_PBO` beside a `POWER_LIMITED`
    the instrument could not have avoided, because it had no PBO input at all. Given one, it names
    the gate itself — and publishes NO fold/season trigger, because no fold count moves a gate
    POPULATION and quoting one is the actively-misleading direction (NF-D18)."""
    rec = _record(VAL3)
    assert rec["null_classification"]["deflation_gates_failed"] == ["pbo"]
    assert rec["null_classification"]["recorded_state"] == "DEFLATION_REFUSED_PBO"
    assert rec["deflation"]["pbo_pass"] is False, "the record no longer shows a failing PBO"
    v = classify_null(**_val3_kwargs(), pbo=rec["deflation"]["pbo"],
                      pbo_gate=rec["deflation"]["pbo_gate"], pbo_application="field")
    assert v.state == "DEFLATION_REFUSED"
    assert "CSCV/PBO" in v.reason
    assert v.retest_trigger is None, "a PBO refusal must NOT carry a fold/season trigger"
    assert v.folds_needed is None and v.extra_seasons is None
    assert "narrower COHERENT family" in v.reason, \
        "the admissible remedy must be named, or the state is a dead end"


def test_a_passing_pbo_moves_no_state():
    """THE TWO-SIDED HALF — a PBO that CLEARS must leave the verdict exactly where it was, or the
    new input is a state-mover rather than a reading."""
    kw = _val3_kwargs()
    base = classify_null(**kw)
    passed = classify_null(**kw, pbo=0.05, pbo_application="field")
    assert passed.state == base.state and passed.retest_trigger == base.retest_trigger
    assert passed.detail["pbo_pass"] is True


def test_a_pbo_refusal_preempts_the_dsr_fold_shortfall_trigger():
    """⭐ THE ORDERING CLAUSE, and it is the point of the whole defect. A design that is BOTH short of
    folds for DSR and refused by its PBO must not be handed "+N folds": the fold trigger is real for
    DSR and irrelevant to the refusal that actually bound, and publishing it tells a reader to buy
    seasons for a gate no season count moves."""
    kw = dict(metric="m", n_folds=11, n_arms=3, beats_foil=True,
              observed_sr=1.0060938409711933, var_trials_sr=0.5930582588508395,
              skew=0.05207384948567502, kurt=1.7721389477213283,
              declared_field_size=3, degenerates_excluded_from_v=True)
    shortfall = classify_null(**kw)
    assert shortfall.state == "POWER_LIMITED" and shortfall.folds_needed is not None
    assert "folds for the DSR gate" in (shortfall.retest_trigger or "")

    refused = classify_null(**kw, pbo=0.53, pbo_application="field")
    assert refused.state == "DEFLATION_REFUSED"
    assert refused.retest_trigger is None and refused.folds_needed is None


def test_dsr_unreachable_still_outranks_a_pbo_refusal():
    """The other side of the ordering: `DSR_UNREACHABLE` says no fold count AND no admissible field
    clears — strictly more specific and less rescuable than "the PBO gate refused" — so it keeps
    precedence. Without this the fix would trade one mislabelled state for another."""
    v = classify_null(metric="m", n_folds=11, n_arms=7, beats_foil=True,
                      observed_sr=0.05, var_trials_sr=0.5,
                      pbo=0.53, pbo_application="field")
    assert v.state == "DSR_UNREACHABLE"


def test_a_negative_point_estimate_outranks_a_pbo_refusal():
    """MLB-HV2-1's lesson, pinned. When every arm's point estimate is negative the null rests on the
    point estimate, and no deflation-gate reading turns a negative estimate positive — so the
    absence/power branch must decide, not the PBO."""
    v = classify_null(metric="m", n_folds=11, n_arms=7, beats_foil=False,
                      pbo=0.53, pbo_application="field")
    assert v.state == "GENUINE_ABSENCE"


def test_red_defect2_silencing_the_pbo_branch_restores_the_unnameable_refusal():
    """RED: with the branch gone, VAL3's inputs + its PBO return the state that structurally cannot
    see the gate that bound — which is the defect VAL3 recorded."""
    rec = _record(VAL3)
    kw = dict(**_val3_kwargs(), pbo=rec["deflation"]["pbo"],
              pbo_gate=rec["deflation"]["pbo_gate"], pbo_application="field")
    assert classify_null(**kw).state == "DEFLATION_REFUSED"
    broken = _mutated(_BREAK_THE_PBO_BRANCH)
    out = broken.classify_null(**kw)
    assert out.state == "POWER_LIMITED", "the deliberate regression did not restore the defect"
    assert "DEFLATION_REFUSED" not in out.state


def test_an_unstated_pbo_application_is_hedged_rather_than_assumed_clean():
    """The MH2.7 provenance shape, reused: an UNSTATED application cannot be told from the per-arm
    misapplication HV2-1 measured, so the refusal stands but is flagged UNVERIFIED. ⛔ Never assumed
    permissive (NF1.7 (a))."""
    kw = _val3_kwargs()
    stated = classify_null(**kw, pbo=0.53, pbo_application="field")
    unstated = classify_null(**kw, pbo=0.53)
    assert stated.pbo_application_admissible is True
    assert unstated.state == "DEFLATION_REFUSED" and unstated.pbo_application_admissible is None
    assert "UNVERIFIED" in unstated.reason


def test_an_unknown_pbo_application_is_refused_rather_than_silently_ignored():
    with pytest.raises(ValueError):
        classify_null(**_val3_kwargs(), pbo=0.53, pbo_application="per-arm")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 3 — NF-W8-0d R2: COMPUTE the lockstep check
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def _w8_0d_inputs():
    rec = _record(W8_0D)
    d = rec["classification"]["detail"]
    ladder = rec["gates"]["G2_lockstep_live"]["ladder"]
    return rec, d, ladder


def test_the_lockstep_ladder_reproduces_nf_w8_0ds_recorded_arithmetic():
    """⭐ THE DEFECT-3 FIXTURE, pinned at 1e-9. NF-W8-0d measured the ladder by hand and filed R2
    asking for it in the instrument; the instrument now computes the same numbers.

    ⚠️ The dispersion factor scales every trial SHARPE by `1/c`, hence their VARIANCE by `1/c²` —
    getting that exponent wrong still produces a plausible monotone ladder, which is why the pin is
    against the recorded values rather than against the ladder's own shape."""
    rec, d, ladder = _w8_0d_inputs()
    sr = ladder[0]["winner_sharpe"]
    got = cv_power.lockstep_variance_lever(
        observed_sr=sr, n_trials=d["n_arms"], var_trials_sr=d["var_trials_sr"],
        n_obs=d["n_folds"])
    assert len(got.ladder) == len(ladder)
    for g, r in zip(got.ladder, ladder):
        for key in ("dispersion_factor", "winner_sharpe", "sr0", "sr_minus_sr0"):
            assert abs(g[key] - r[key]) < TOL, f"{key} drifted from the record at ×{r['dispersion_factor']}"
    assert got.closed is True
    assert got.sign_invariant is True and rec["gates"]["G2_lockstep_live"]["sign_is_invariant"]
    assert got.dsr_falls_as_design_sharpens is True


def test_the_lockstep_is_two_sided_a_positive_gap_leaves_the_lever_OPEN():
    """⭐ THE HALF THAT KEEPS THE FIX FROM BEING A BLANKET "VARIANCE NEVER HELPS". When `SR > SR0`
    the gap is positive, a proportional sharpening scales it UP, and DSR RISES — so the lever is
    genuinely live and the instrument must keep saying so."""
    open_lever = cv_power.lockstep_variance_lever(
        observed_sr=3.0, n_trials=4, var_trials_sr=0.05, n_obs=8)
    assert open_lever.closed is False and open_lever.gap > 0
    dsrs = [r["dsr"] for r in open_lever.ladder]
    assert all(b >= a for a, b in zip(dsrs, dsrs[1:])), "a positive gap must IMPROVE as it sharpens"
    assert open_lever.sign_invariant is True


def test_an_unevaluable_lockstep_is_None_and_never_read_as_open():
    assert cv_power.lockstep_variance_lever(
        observed_sr=None, n_trials=4, var_trials_sr=0.1, n_obs=8).closed is None
    assert cv_power.lockstep_variance_lever(
        observed_sr=1.0, n_trials=4, var_trials_sr=None, n_obs=8).closed is None


def test_dsr_unreachable_no_longer_prescribes_the_void_lever_on_the_recorded_case():
    """⭐ NF-W8-0d's recorded trigger named "a lower-variance design" verbatim, and that one sentence
    sent NF-W7f, NF-W7j and NF-W8-0c at the same wall. The record is quoted, not edited."""
    rec, d, ladder = _w8_0d_inputs()
    assert "lower-variance design" in rec["classification"]["retest_trigger"], \
        "the record no longer contains the sentence this defect is about"
    v = classify_null(metric="qb_abs_level_bias", n_folds=d["n_folds"], n_arms=d["n_arms"],
                      beats_foil=True, observed_sr=ladder[0]["winner_sharpe"],
                      var_trials_sr=d["var_trials_sr"], degenerates_excluded_from_v=True,
                      declared_field_size=d["declared_field_size"])
    assert v.state == rec["classification"]["state"] == "DSR_UNREACHABLE", "the STATE must not move"
    assert v.max_field_size == rec["classification"]["max_field_size"]
    trig = v.retest_trigger or ""
    assert "lower-variance design" not in trig.replace("NEITHER IS A LOWER-VARIANCE DESIGN", "")
    assert "NEITHER IS A LOWER-VARIANCE DESIGN" in trig
    assert "NOT a lever" in trig, "the field-size half of the sentence must survive"
    assert v.lockstep is not None and v.lockstep.closed is True


def test_the_open_lockstep_branch_keeps_naming_the_lever_that_is_still_live():
    """MH2.7's `k_pct` case: `max_field_size == 0` with a POSITIVE gap. The variance lever is real
    there, so the original sentence must survive — otherwise the fix deletes a working diagnostic
    (the two-sided discipline the MH2.7 single-contrast co-fix already applies)."""
    v = classify_null(metric="k_pct", n_folds=11, n_arms=3, beats_foil=True,
                      observed_sr=0.4236, var_trials_sr=0.032822,
                      degenerates_excluded_from_v=True, declared_field_size=3)
    assert v.state == "POWER_LIMITED" and v.max_field_size == 0
    assert v.lockstep is not None and v.lockstep.closed is False
    assert "lower-variance design" in (v.retest_trigger or "")
    assert "NEITHER IS A LOWER-VARIANCE DESIGN" not in (v.retest_trigger or "")


def test_red_defect3_ignoring_the_computed_lockstep_reinstates_the_void_prescription():
    """RED: stop consulting the computed lockstep and NF-W8-0d's case is handed the dead lever again,
    verbatim."""
    rec, d, ladder = _w8_0d_inputs()
    kw = dict(metric="qb_abs_level_bias", n_folds=d["n_folds"], n_arms=d["n_arms"],
              beats_foil=True, observed_sr=ladder[0]["winner_sharpe"],
              var_trials_sr=d["var_trials_sr"], degenerates_excluded_from_v=True,
              declared_field_size=d["declared_field_size"])
    assert "NEITHER IS A LOWER-VARIANCE DESIGN" in (classify_null(**kw).retest_trigger or "")
    broken = _mutated(_BREAK_THE_LOCKSTEP_CONSULT)
    trig = broken.classify_null(**kw).retest_trigger or ""
    assert trig == rec["classification"]["retest_trigger"], \
        "the deliberate regression did not reproduce the recorded pre-fix sentence"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 4 — MLB-HV2-1: field-level vs per-arm PBO, and the control as a CALLABLE
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: HV2-1's registered gate family, in the order its record lists them.
_HV2_1_GATES = ("roi_positive", "fold_consistency", "bh_fdr", "pbo", "dsr")


def _hv2_1_control_runner():
    """Replay HV2-1's recorded positive control as a `run_gates` callable.

    The blocking-gate table is READ from the artifact, so this reproduces what that study measured
    rather than restating it. `inject(0.0)` returns the no-effect payload, on which every arm is
    blocked by `roi_positive` — HV2-1's actual finding (every real arm's ROI is negative), which is
    what makes the two-sided leg of the control non-vacuous here.
    """
    blocking = _record(HV2_1)["controls"]["positive_injected_dog_edge"]["blocking_gates"]

    def run_gates(payload):
        if payload == "no_effect":
            return {a: {g: g not in ("roi_positive", "pbo", "dsr") for g in _HV2_1_GATES}
                    for a in blocking}
        return {a: {g: g not in blocking[a] for g in _HV2_1_GATES} for a in blocking}

    return (lambda e: "no_effect" if e == 0.0 else e), run_gates, blocking


def test_the_positive_control_helper_reproduces_hv2_1s_recorded_verdict():
    """⭐ THE DEFECT-4b FIXTURE. HV2-1 ran this by hand and the finding is the sharpest the program
    has about its own gates: with a 6pp bias INJECTED, no arm survives — but the METRIC gates all
    fire, and six arms are stopped ONLY by the deflation pair. That is the difference between a gate
    family that is BLIND and one whose deflation half is hostile to a correlated field, and it is
    invisible from a leaderboard."""
    inject, run_gates, blocking = _hv2_1_control_runner()
    rep = cv_power.injected_effect_positive_control(inject=inject, run_gates=run_gates, effect=0.06)
    recorded = _record(HV2_1)["controls"]["positive_injected_dog_edge"]

    assert rep.verdict == "DEFLATION_BLOCKED"
    assert list(rep.survivors) == recorded["survivors"] == []
    assert set(rep.deflation_blocked) == {a for a, b in blocking.items() if set(b) <= {"pbo", "dsr"}}
    assert len(rep.deflation_blocked) == 6, "the record's six deflation-only-blocked arms"
    assert rep.null_control_checked is True and rep.null_control_survivors == ()


def test_the_helper_detects_the_field_level_statistic_carried_as_a_per_arm_gate():
    """DEFECT 4(a), MEASURED rather than asserted: `pbo` is one number for the whole field and it is
    on every arm's gate card. `dsr` deliberately does NOT trip this — DSR is per-arm (each arm has
    its own Sharpe) even though its BENCHMARK is field-derived, and flagging it would make the
    detector cry wolf on a legitimate gate."""
    inject, run_gates, _ = _hv2_1_control_runner()
    rep = cv_power.injected_effect_positive_control(inject=inject, run_gates=run_gates, effect=0.06)
    assert rep.field_level_gates_applied_per_arm == ("pbo",)
    assert "dsr" not in rep.field_level_gates_applied_per_arm


@pytest.mark.parametrize("gates,expected", [
    (lambda arms: {a: {g: True for g in _HV2_1_GATES} for a in arms}, "DETECTED"),
    (lambda arms: {a: {g: False for g in _HV2_1_GATES} for a in arms}, "BLIND"),
])
def test_the_control_verdict_is_not_a_constant(gates, expected):
    """NON-VACUITY, both directions. A control that returns one verdict whatever it is handed
    measures nothing — `DEFLATION_BLOCKED` above is only informative because `DETECTED` and `BLIND`
    are reachable from the same call."""
    inject, base, blocking = _hv2_1_control_runner()
    rep = cv_power.injected_effect_positive_control(
        inject=inject,
        run_gates=lambda p: base(p) if p == "no_effect" else gates(blocking),
        effect=0.06)
    assert rep.verdict == expected


def test_a_family_that_certifies_the_NO_EFFECT_payload_is_VACUOUS():
    """⭐ THE LEG THAT MAKES THE CONTROL A CONTROL. A gate family that passes arms on a payload with
    nothing planted in it cannot certify anything on one that has — so nothing about the injected run
    is readable, and the verdict must say so rather than report `DETECTED` (MH2.6's vacuity floor)."""
    _, _, blocking = _hv2_1_control_runner()
    rep = cv_power.injected_effect_positive_control(
        inject=lambda e: e,
        run_gates=lambda p: {a: {g: True for g in _HV2_1_GATES} for a in blocking},
        effect=0.06)
    assert rep.verdict == "VACUOUS"


def test_a_skipped_null_leg_is_recorded_as_not_run_never_as_passed():
    _, run_gates, _ = _hv2_1_control_runner()
    rep = cv_power.injected_effect_positive_control(
        inject=lambda e: e, run_gates=run_gates, effect=0.06, check_null_control=False)
    assert rep.null_control_checked is False and rep.null_control_survivors is None


@pytest.mark.parametrize("kw,why", [
    (dict(effect=0.0), "a zero-effect injection plants nothing"),
    (dict(run_gates=lambda p: {}), "an empty arm table makes every clause vacuously true"),
    (dict(run_gates=lambda p: {"a": {}}), "an arm with no gates passes 'every gate' trivially"),
])
def test_the_helper_refuses_a_vacuous_configuration(kw, why):
    inject, run_gates, _ = _hv2_1_control_runner()
    call = dict(inject=inject, run_gates=run_gates, effect=0.06)
    call.update(kw)
    with pytest.raises(ValueError):
        cv_power.injected_effect_positive_control(**call)


def test_a_per_arm_applied_pbo_refusal_is_REFUSED_not_converted_into_a_verdict():
    """⭐ THE DEFECT-4a FIXTURE. HV2-1 MEASURED that a field-level PBO read per-arm vetoes a real,
    large, uniform effect — the injected 6pp bias made the arms near-clones, so PBO ROSE to 0.426
    BECAUSE the effect was real (NF1.8: a high PBO over near-clones is a TIE, not overfitting). So a
    per-arm-applied PBO must not be convertible into a refusal verdict; it is flagged and the other
    gates decide."""
    recorded_pbo = _record(HV2_1)["controls"]["positive_injected_dog_edge"]["pbo"]
    assert recorded_pbo > cv_power.MAX_PBO, "the record no longer contains a failing PBO"
    kw = dict(metric="m", n_folds=11, n_arms=8, beats_foil=True, pbo=recorded_pbo)
    field_level = classify_null(**kw, pbo_application="field")
    per_arm = classify_null(**kw, pbo_application="per_arm")
    assert field_level.state == "DEFLATION_REFUSED"
    assert per_arm.state != "DEFLATION_REFUSED", \
        "a field-level statistic read per-arm must not produce an arm-level refusal"
    assert per_arm.pbo_application_admissible is False
    assert per_arm.detail["pbo_refusal_admitted"] is False
    assert "FIELD-LEVEL statistic was applied PER ARM" in \
        per_arm.detail["pbo_refusal_refused_because"]


def test_red_defect4_admitting_the_per_arm_application_restores_the_veto():
    """RED: accept the per-arm application and the misapplied gate refuses the arm again — which is
    the behaviour HV2-1 measured blocking a planted effect."""
    recorded_pbo = _record(HV2_1)["controls"]["positive_injected_dog_edge"]["pbo"]
    kw = dict(metric="m", n_folds=11, n_arms=8, beats_foil=True, pbo=recorded_pbo,
              pbo_application="per_arm")
    assert classify_null(**kw).state != "DEFLATION_REFUSED"
    broken = _mutated(_BREAK_THE_PER_ARM_REFUSAL)
    assert broken.classify_null(**kw).state == "DEFLATION_REFUSED", \
        "the deliberate regression did not restore the misapplied veto"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The instrument's own contract — the new state, and the RED harness's own two-sidedness
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_the_new_state_is_declared_and_exported():
    assert "DEFLATION_REFUSED" in cv_power.NULL_STATES
    for name in ("lockstep_variance_lever", "injected_effect_positive_control",
                 "LockstepReport", "PositiveControlReport", "MAX_PBO", "PBO_APPLICATIONS"):
        assert name in cv_power.__all__, f"{name} is not exported — a caller cannot reach it"


def test_the_docstring_cites_all_four_incident_records():
    """The retirement of the interim hand-record rule has to be findable from the instrument itself,
    with its evidence — otherwise the next caller re-derives the workaround."""
    doc = cv_power.__doc__ or ""
    for citation in ("NCAAF-VAL1", "NCAAF-VAL3", "NF-W8-0d", "MLB-HV2-1"):
        assert citation in doc
    assert "FUTURE callers only" in doc


def test_the_red_harness_refuses_a_mutation_that_does_not_land():
    """THE PROOF OF THE PROOF (#682): a break whose target is absent must RAISE, not pass silently."""
    with pytest.raises(AssertionError):
        _mutated(("a string that is definitely not in cv_power.py", "x"))


def test_the_red_harness_refuses_a_mutation_whose_target_is_not_unique():
    """The E11.24 `prediction_log` lesson: a non-unique anchor lands on the WRONG symbol and the
    harness then reports a FALSE vacuity — the dangerous direction, because it invites weakening a
    guard that is fine."""
    with pytest.raises(AssertionError):
        _mutated(("return", "return"))
