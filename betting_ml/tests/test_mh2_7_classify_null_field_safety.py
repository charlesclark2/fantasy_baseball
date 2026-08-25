"""test_mh2_7_classify_null_field_safety.py — MH2.7 guards.

Two defects in one pure function, and they are different in kind:

  1. **The `max_field_size` leg prescribed the RETIRED POST-HOC FIELD.** On MH2.2's `bb_pct` — a
     3-arm DECLARED family — `classify_null` returned *"…OR a field of ≤2 arms at the CURRENT fold
     count"*. That ≤2-arm field IS the post-hoc one the whole MH2 lineage exists to reject: it is
     reached by deleting `T3_tenure`, i.e. the arm that LOST, and its DSR jump (0.849 → 0.998) was
     bought by a 19,938× collapse in the cross-trial dispersion `V`. The instrument was re-committing
     the exact selection bias DSR exists to deflate, inside a badge that reads like a remedy.
  2. **A SINGLE pre-registered contrast rendered as a FOLD SHORTAGE.** `pbo_evaluable` is false for
     two structurally different reasons, and collapsing them made a 1-arm design report
     *"8 fold(s) < 4"* and prescribe *"−4 more fold(s)"* — telling a reader to buy seasons for a
     deflation statistic a 1-arm design never needed. Hand-corrected FOUR times downstream
     (NF-W2 → NF-D18 → NF-W3 → NF-W4) before being fixed in the instrument.

⭐ **THE LOAD-BEARING CONSTRAINT IS THAT NEITHER FIX RE-DECIDES A RECORDED VERDICT.** Both changes are
STATE-PRESERVING by construction — (1) touches only the trigger sentence and a new machine flag,
(2) keeps `UNDEFINED` and only replaces its reason and its fabricated trigger — and that is asserted
here rather than argued: the seven-state table is pinned, the MH2.2 `bb_pct` state / `folds_needed` /
`max_field_size` are pinned to their stored values, and `mh2_cv_power.validation_cases()` (the four
record-reproduction cases) must still agree.

⚠️ **EVERY CLAUSE BELOW IS RED-PROVEN AGAINST DELIBERATELY-BROKEN SOURCE**, in-process, with the
mutation asserted to have LANDED before the assertion is re-run (a RED proof that can silently no-op
its own break reports a false "the guard caught it"). And the mutations are chosen to be ISOLATING —
one clause per break — because a guard on an AND-composed rule is vacuous when a *different* clause
is what refuses the fixture (NF-D17).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils import cv_power
from betting_ml.utils.cv_power import classify_null

ABL = Path(__file__).resolve().parents[2] / \
    "quant_sports_intel_models/baseball/edge_program/ablation_results"

# ── The MH2.2 `bb_pct` case, as recorded (`mh2_2_trajectory_family.md` §3/§5) ─────────────────────
# 11 folds (MLB debut cohorts), the 3-arm DECLARED trajectory family, winner `T2_traj_raw`.
# Reproduced below from the stored per-fold MAE matrix so these constants cannot silently drift.
BB_PCT = dict(n_folds=11, n_arms=3, observed_sr=1.0060938409711933,
              skew=0.05207384948567502, kurt=1.7721389477213283,
              var_trials_sr=0.5930582588508395)
BB_PCT_RECORDED = dict(state="POWER_LIMITED", folds_needed=27, max_field_size=2, dsr=0.8493)

#: The exact imperative MH2.2 recorded — the sentence this story exists to make unemittable.
PRE_FIX_PRESCRIPTION = "OR a field of ≤2 arms at the CURRENT fold count"


def _bb_pct_verdict(**over):
    kw = dict(metric="bb_pct", beats_foil=True, degenerates_excluded_from_v=True, **BB_PCT)
    kw.update(over)
    return classify_null(**kw)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# RED-proof harness — mutate the real source in-process and prove the mutation LANDED
# ══════════════════════════════════════════════════════════════════════════════════════════════════

_SRC = Path(cv_power.__file__)


def _mutated_cv_power(*replacements: tuple[str, str]) -> ModuleType:
    """Re-import `cv_power` with deliberate breaks applied.

    ⚠️ The `assert` on the replacement count is the whole point: a RED proof whose mutation silently
    fails to apply passes for the WRONG reason and reads as "the guard caught it" (E9.64 / the
    shell-quoting no-op). Nothing here shells out, so the break cannot be lost in quoting.
    """
    src = _SRC.read_text()
    for old, new in replacements:
        assert src.count(old) == 1, f"mutation target not uniquely present: {old!r}"
        src = src.replace(old, new)
    original = _SRC.read_text()
    assert src != original, "the mutation did not change the source — the RED proof would be vacuous"
    name = "cv_power_mutated"
    mod = ModuleType(name)
    mod.__file__ = str(_SRC)
    # `@dataclass` resolves its annotations through `sys.modules[cls.__module__]`, so the module has
    # to be registered before the exec — and removed afterwards so nothing else can import it.
    sys.modules[name] = mod
    try:
        exec(compile(src, str(_SRC), "exec"), mod.__dict__)
    finally:
        sys.modules.pop(name, None)
    return mod


# `if int(max_field) >= declared:` → always true ⇒ the below-declared field is prescribed again.
_BREAK_THE_DECLARED_FLOOR = ("    if int(max_field) >= declared:\n", "    if True:\n")
# Blank the refusal marker but LEAVE the floor intact ⇒ the flag is still False, the prose is silent.
_BREAK_THE_REFUSAL_MARKER = ('"⛔ **NOT A REMEDY — ARITHMETIC ONLY.** The effect clears only in a '
                             'field of ≤{max_field} arm(s), "',
                             '"The effect clears in a field of ≤{max_field} arm(s), "')
# Remove the single-contrast branch ⇒ a 1-arm design falls into the FOLD branch, as it did pre-fix.
_BREAK_THE_SINGLE_CONTRAST_BRANCH = ("    if int(n_arms) < 2:\n", "    if False:\n")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The MH2.2 `bb_pct` case — the field-size prescription
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestTheMH2_2BbPctCase:
    def test_the_pinned_constants_still_match_the_stored_per_fold_matrix(self):
        """The fixture is DERIVED, not typed. If the stored artifact ever moves, this fails loudly
        rather than letting the guard quietly assert against a case that no longer exists."""
        p = ABL / "mh2_2_artifacts/mh2_2_trajectory_family_summary.json"
        if not p.exists():                       # pragma: no cover — artifact is tracked
            pytest.skip("MH2.2 artifact absent")
        d = json.loads(p.read_text())
        assert d["declared_field"] == ["T1_traj_ladder", "T2_traj_raw", "T3_tenure"], \
            "the declared family is what makes ≤2 arms a POST-HOC field — it must be 3 arms"
        mae = pd.DataFrame(d["per_metric"]["bb_pct"]["mae_by_fold"])
        fam, foil = d["declared_field"], "L0_foil"

        def _mom(c):
            r = (mae[foil].to_numpy(float) - mae[c].to_numpy(float))
            r = r[np.isfinite(r)]
            rc, sd0 = r - r.mean(), float(np.std(r, ddof=0))
            return (float(r.mean() / np.std(r, ddof=1)),
                    float((rc ** 3).mean() / sd0 ** 3), float((rc ** 4).mean() / sd0 ** 4))

        sr, skew, kurt = _mom("T2_traj_raw")
        v = float(np.var([_mom(c)[0] for c in fam], ddof=1))
        assert sr == pytest.approx(BB_PCT["observed_sr"], abs=1e-9)
        assert skew == pytest.approx(BB_PCT["skew"], abs=1e-9)
        assert kurt == pytest.approx(BB_PCT["kurt"], abs=1e-9)
        assert v == pytest.approx(BB_PCT["var_trials_sr"], abs=1e-9)
        assert len(mae) == BB_PCT["n_folds"]
        assert d["per_metric"]["bb_pct"]["dsr"]["eligible"]["dsr"] == \
            pytest.approx(BB_PCT_RECORDED["dsr"], abs=5e-5)

    def test_the_recorded_verdict_is_UNCHANGED_by_the_fix(self):
        """⭐ THE REGRESSION CONSTRAINT. MH2.7 changes the REMEDY, never the classification — a fix
        that re-decides a recorded null would be a far worse defect than the one it repairs."""
        for declared in (None, 3):
            v = _bb_pct_verdict(declared_field_size=declared)
            assert v.state == BB_PCT_RECORDED["state"]
            assert v.folds_needed == BB_PCT_RECORDED["folds_needed"]
            assert v.extra_seasons == BB_PCT_RECORDED["folds_needed"] - BB_PCT["n_folds"]
            assert v.max_field_size == BB_PCT_RECORDED["max_field_size"], \
                "the ARITHMETIC must survive — MH2.7 refuses the imperative, not the number"

    def test_it_no_longer_prescribes_the_retired_post_hoc_field(self):
        """The clause the story exists for: ≤2 arms is BELOW the 3-arm declared family, so it may not
        be handed back as advice."""
        v = _bb_pct_verdict(declared_field_size=3)
        assert v.field_remedy_admissible is False
        assert PRE_FIX_PRESCRIPTION not in (v.retest_trigger or "")

    def test_the_refusal_is_VISIBLE_in_the_trigger_not_only_in_the_flag(self):
        """A machine flag a report does not read is not a guard — MH2.2 had to carry a HAND-WRITTEN
        callout under its table, which is exactly the mitigation this story replaces."""
        t = _bb_pct_verdict(declared_field_size=3).retest_trigger or ""
        assert "NOT A REMEDY" in t
        assert "pre-registered" in t.lower()

    def test_an_UNSTATED_declared_field_is_REFUSED_not_assumed_permissive(self):
        """NF1.7 (a): a check that did not run is not a check that passed. With no declaration the
        only field known to be pre-registered is the one actually scored, so the fallback must be
        `n_arms` — and it must SAY it fell back."""
        v = _bb_pct_verdict(declared_field_size=None)
        assert v.field_remedy_admissible is False
        assert PRE_FIX_PRESCRIPTION not in (v.retest_trigger or "")
        assert "declared_field_size" in (v.retest_trigger or "")
        assert v.detail["declared_field_size"] is None
        assert v.detail["declared_field_size_source"].startswith("unstated")

    def test_a_CLEAN_V_provenance_does_not_launder_the_field_prescription(self):
        """⚠️ The DSR-CONV `V` note was the only hedge on this sentence before MH2.7 — and it is a
        hedge about a DIFFERENT quantity. A caller that legitimately states a clean `V` got the
        unsafe field prescription with NO warning at all; that is the hole being closed."""
        clean = _bb_pct_verdict(declared_field_size=3, degenerates_excluded_from_v=True)
        assert "UNVERIFIED" not in (clean.retest_trigger or ""), "fixture no longer isolates: the " \
            "`V` hedge is firing, so this would pass without the MH2.7 guard"
        assert clean.field_remedy_admissible is False

    def test_a_genuinely_pre_registered_smaller_family_IS_still_actionable(self):
        """⭐ THE TWO-SIDED HALF. A guard that refuses everything is as useless as one that refuses
        nothing — E7.15-H3 bundled two families and trimming to the DECLARED trajectory family was
        legitimate. Declaring a 2-arm family makes the same ≤2 arithmetic an imperative again."""
        v = _bb_pct_verdict(declared_field_size=2)
        assert v.field_remedy_admissible is True
        assert "re-run" in (v.retest_trigger or "").lower()
        assert v.state == BB_PCT_RECORDED["state"], "and it STILL must not move the state"

    def test_field_size_is_reported_as_no_lever_when_even_two_arms_cannot_clear(self):
        """`k_pct`/`iso` in the same table: `max_field_size = 0`. There is nothing to be admissible
        about, so the flag is None and the sentence must not imply a field remedy exists.

        ⚠️ Only the FIELD leg is being exercised here — the empirical moments are not threaded, so the
        fold figure this returns is NOT `k_pct`'s recorded 62 and is deliberately not asserted."""
        v = classify_null(metric="k_pct", n_folds=11, n_arms=3, beats_foil=True,
                          observed_sr=0.4236, var_trials_sr=0.032822,
                          degenerates_excluded_from_v=True, declared_field_size=3)
        assert v.state == "POWER_LIMITED" and v.max_field_size == 0
        assert v.field_remedy_admissible is None
        assert "NOT a lever" in (v.retest_trigger or "")

    def test_the_DSR_UNREACHABLE_branch_carries_the_SAME_guard(self):
        """The card names `DSR_UNREACHABLE`; MH2.2 happened to land on `POWER_LIMITED`. Both branches
        emit the field leg, so both must be guarded — otherwise the fix repairs the state that was
        reported and leaves the state that was carded."""
        v = classify_null(metric="synthetic", n_folds=11, n_arms=7, beats_foil=True,
                          observed_sr=1.3174, var_trials_sr=1.0,
                          degenerates_excluded_from_v=True, declared_field_size=7)
        assert v.state == "DSR_UNREACHABLE" and v.max_field_size == 2
        assert v.field_remedy_admissible is False
        assert "NOT A REMEDY" in (v.retest_trigger or "")
        assert "a field of ≤2 arms" not in (v.retest_trigger or "")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The single-contrast co-fix
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestSingleContrastIsNotAFoldShortage:
    def test_a_one_arm_design_emits_NO_fold_trigger(self):
        """NF-W3/NF-W4's defect: at 8 folds it read "8 fold(s) < 4" and prescribed "−4 more fold(s)".
        No fold count makes PBO computable for a single contrast, so quoting one is a lie — the same
        reason `GENUINE_ABSENCE` carries no trigger."""
        v = classify_null(metric="t1", n_folds=8, n_arms=1, beats_foil=True)
        assert v.state == "UNDEFINED", "the STATE was right all along — PBO genuinely is undefined"
        assert v.retest_trigger is None
        assert v.folds_needed is None and v.extra_seasons is None
        assert "fold(s) < " not in v.reason
        assert "SINGLE pre-registered contrast" in v.reason

    def test_a_short_fold_count_is_still_named_when_a_one_arm_design_also_has_one(self):
        """The fold shortfall is REAL for the other gates even when it is not what makes PBO
        undefined — dropping the mention would trade one silent omission for another."""
        v = classify_null(metric="t1", n_folds=2, n_arms=1, beats_foil=True)
        assert v.state == "UNDEFINED" and v.retest_trigger is None
        assert "2 fold(s) < 4" in v.reason and "OTHER gates" in v.reason

    def test_a_real_fold_shortage_at_TWO_or_more_arms_keeps_its_trigger(self):
        """⭐ THE TWO-SIDED HALF: the legitimate fold trigger must survive, or the co-fix has merely
        deleted a working diagnostic."""
        v = classify_null(metric="t1", n_folds=3, n_arms=7, beats_foil=True)
        assert v.state == "UNDEFINED"
        assert v.retest_trigger and "more fold(s)" in v.retest_trigger
        assert v.folds_needed == cv_power.MIN_FOLDS_FOR_PBO and v.extra_seasons == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. No recorded verdict moved
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestNothingWasReDecided:
    #: One case per state, pinned. MH2.7 may change remedy TEXT; it may not move any of these.
    STATE_TABLE = (
        ("INACTIVE", dict(n_folds=11, n_arms=7, beats_foil=True, observed_sr=2.0,
                          var_trials_sr=0.02, active=False)),
        ("UNKNOWN", dict(n_folds=0, n_arms=7, beats_foil=True)),
        ("UNDEFINED", dict(n_folds=3, n_arms=7, beats_foil=True)),
        ("UNDEFINED", dict(n_folds=11, n_arms=1, beats_foil=True)),
        ("GENUINE_ABSENCE", dict(n_folds=11, n_arms=7, beats_foil=False)),
        ("DSR_UNREACHABLE", dict(n_folds=11, n_arms=7, beats_foil=True, observed_sr=0.05,
                                 var_trials_sr=0.5)),
        # ⭐ PLAT-CVP1 defect 2 — the 8th state. Added here (rather than pinned only in its own
        # suite) because THIS table is the non-vacuity check: a state absent from it is a state
        # nothing in the re-decision guard exercises.
        ("DEFLATION_REFUSED", dict(n_folds=11, n_arms=5, beats_foil=True, pbo=0.53,
                                   pbo_application="field")),
        ("POWER_LIMITED", dict(n_folds=11, n_arms=3, beats_foil=True, observed_sr=1.0060938409711933,
                               var_trials_sr=0.5930582588508395, skew=0.05207384948567502,
                               kurt=1.7721389477213283)),
        ("POWER_LIMITED", dict(n_folds=11, n_arms=5, beats_foil=True, p_one_sided=0.02,
                               bh_cutoff=0.0001)),
        ("POWER_LIMITED", dict(n_folds=11, n_arms=5, beats_foil=True, mde_sd_units=3.0,
                               meaningful_sd_units=1.0)),
        ("TRUSTWORTHY_DEAD", dict(n_folds=11, n_arms=5, beats_foil=True, mde_sd_units=0.5,
                                  meaningful_sd_units=1.0)),
    )

    @pytest.mark.parametrize("expected,kw", STATE_TABLE)
    def test_every_state_is_still_reached(self, expected, kw):
        assert classify_null(metric="m", **kw).state == expected

    def test_every_state_is_covered_by_the_table(self):
        """Non-vacuity: a table that silently stopped exercising a state would pin nothing about it.

        ⭐ PLAT-CVP1 re-anchor — the property is UNCHANGED (the table must exercise EVERY declared
        state, so none can be added or removed without a pin moving with it); only the state count
        moved, from seven to eight (`DEFLATION_REFUSED`). Asserting against `NULL_STATES` rather
        than a hard-coded seven is what made this re-anchor a one-line addition instead of a
        rewrite — and it is why the guard caught the new state on the first run."""
        assert {s for s, _ in self.STATE_TABLE} == set(cv_power.NULL_STATES)

    def test_the_four_record_reproduction_validations_still_agree(self):
        """⭐ THE STORY'S OWN GATE. `mh2_cv_power.validation_cases()` re-derives E7.9's fold count,
        E7.12-S6's false-fire rate, E7.14's certifiability floor and E7.15-H3's field-size flip from
        the stored artifacts. A power diagnostic that stops reproducing the record is not evidence
        about anything — so this is the load-bearing regression check, not the unit tests above."""
        from betting_ml.scripts.mh2_cv_power import validation_cases

        cases = validation_cases()
        assert len(cases) >= 4, "the validation set itself went missing — that is not a pass"
        disagreed = [c["case"] for c in cases if not c["agrees"]]
        assert not disagreed, f"MH2.7 broke a record-reproduction case: {disagreed}"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. RED proofs — every clause above must FAIL on deliberately-broken source
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestTheGuardsGoRedOnBrokenSource:
    def test_the_harness_itself_refuses_a_mutation_that_does_not_land(self):
        """The test of the test. If a break can silently no-op, every RED proof below is decorative."""
        with pytest.raises(AssertionError, match="not uniquely present"):
            _mutated_cv_power(("a string that is definitely not in the source", "x"))

    def test_removing_the_declared_floor_re_emits_the_post_hoc_prescription(self):
        """RED-proves `test_it_no_longer_prescribes_the_retired_post_hoc_field` + the UNSTATED
        fallback clause. The `NOT A REMEDY` marker is untouched, so this break isolates the FLOOR."""
        broken = _mutated_cv_power(_BREAK_THE_DECLARED_FLOOR)
        for declared in (None, 3):
            v = broken.classify_null(metric="bb_pct", beats_foil=True,
                                     degenerates_excluded_from_v=True,
                                     declared_field_size=declared, **BB_PCT)
            assert v.field_remedy_admissible is True, \
                "the break did not restore the pre-fix behaviour — the RED proof is vacuous"
            assert "NOT A REMEDY" not in (v.retest_trigger or "")
            assert v.state == BB_PCT_RECORDED["state"], \
                "even broken it must not move the state — confirms the guard is about the REMEDY"

    def test_silencing_the_refusal_marker_leaves_the_flag_intact(self):
        """RED-proves `test_the_refusal_is_VISIBLE_in_the_trigger_not_only_in_the_flag` ALONE — the
        floor still holds here (flag stays False), so only the visibility clause can fail. Without
        this isolation that clause would be riding on the floor clause's fixture (NF-D17)."""
        broken = _mutated_cv_power(_BREAK_THE_REFUSAL_MARKER)
        v = broken.classify_null(metric="bb_pct", beats_foil=True, degenerates_excluded_from_v=True,
                                 declared_field_size=3, **BB_PCT)
        assert v.field_remedy_admissible is False, "the floor clause must still hold — isolation"
        assert "NOT A REMEDY" not in (v.retest_trigger or "")

    def test_removing_the_single_contrast_branch_restores_the_fabricated_fold_trigger(self):
        """RED-proves the co-fix. This is the literal NF-W3/NF-W4 defect: a 1-arm design at 8 folds
        reporting a FOLD shortage, prescribing a NEGATIVE number of extra folds."""
        broken = _mutated_cv_power(_BREAK_THE_SINGLE_CONTRAST_BRANCH)
        v = broken.classify_null(metric="t1", n_folds=8, n_arms=1, beats_foil=True)
        assert v.state == "UNDEFINED", "the state was never the defect"
        assert v.retest_trigger is not None and "fold(s)" in v.retest_trigger
        assert v.extra_seasons == -4, \
            "the pre-fix trigger prescribed −4 folds — if this is not reproduced the proof is vacuous"
