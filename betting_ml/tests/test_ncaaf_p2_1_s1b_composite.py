"""Guards for NCAAF-P2.1 S1b — is the composite's margin over the 8-column block EARNED?

What these pin, and why each one exists:

* the pre-registration matches the code (primary, foil, declared field size, both series) — a
  registration that has drifted from the harness is not a registration;
* the contrast is the **matched pair against the FOIL**, not the vs-reference delta S1 gated. This
  is the whole point of the story, so it is pinned at the CALL SITE, not only in the series helpers
  (P2.1's own lesson: a guard on the clause functions alone is vacuous when the defect lives at the
  call site);
* `V` excludes the anchors while `n_trials` keeps them (DSR-CONV), and the diagnostic no-pace
  degenerate is excluded from `n_trials` (MH2.1 (a): an anchor must never set the gate's own bar);
* ⭐ `classify_null` receives the MEASURED higher moments. Without them it defaults to Gaussian and,
  on this platykurtic series, publishes a "+1 more season" trigger for a gate that already passed —
  the actively-misleading trigger MH2/NF-D18 forbid;
* ⭐ a NON-POSITIVE fold requirement is corrected and the raw instrument string is preserved. A
  mis-rendered state must never reach the record as a re-test instruction, and must never be
  silently dropped either;
* the calibration constraint is INHERITED verbatim and never tightened (NF1.8), and PIT is a GATE,
  never a rank;
* S1b never writes a DECIDED story's output paths (the S1-serve defect-3 class);
* the pre-registered REVERT trigger exists, so the study can genuinely fail against the served state.

⚠️ Every clause here is proved to go RED on deliberately-broken source by
`betting_ml/tests/ncaaf_p2_1_s1b_red_proof.py`. A guard that cannot fail is worse than none
(NF1.7 (a) / INC-38).

Fast-gate discipline (E11.23): nothing here imports `pipeline`.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import numpy as np
import pytest

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.ncaaf.models import p2_1_s1b_composite as s1b

_ROOT = Path(__file__).resolve().parents[2]
_NCAAF = _ROOT / "quant_sports_intel_models" / "football" / "ncaaf"
_PREREG = _NCAAF / "ablation_results" / "ncaaf_p2_1_s1b_preregistration.md"
_HARNESS = _NCAAF / "models" / "p2_1_s1b_composite.py"
_DECISION = _NCAAF / "ablation_results" / "ncaaf_p2_1_s1b_composite.json"


def _strip_comments(src: str) -> str:
    """Comments must not satisfy a source-inspection guard (INC-38: prose cannot satisfy a check)."""
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


def _src() -> str:
    return _strip_comments(_HARNESS.read_text())


def _call_args(src: str, opener: str) -> str:
    """Extract a call's argument text by BALANCED parens.

    A naive `src[i:src.index(")", i)]` truncates at the first nested `)` — here that would cut the
    argument list off before the very kwargs under test, and the guard would fail for a reason
    unrelated to what it asserts."""
    i = src.index(opener) + len(opener)
    depth, out = 1, []
    for ch in src[i:]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        out.append(ch)
    assert depth == 0, f"unbalanced parens after {opener!r}"
    return "".join(out)


def _written_paths(src: str) -> set[str]:
    """Every expression this module WRITES to (as opposed to reads)."""
    return set(re.findall(r"(\w+)\.write_(?:text|bytes)\(", src))


# ---------------------------------------------------------------------------
# The pre-registration IS the contract
# ---------------------------------------------------------------------------

def test_preregistration_is_committed_and_names_the_primary_the_foil_and_every_real_arm():
    assert _PREREG.exists(), "the S1b pre-registration must be committed"
    text = _PREREG.read_text()
    assert f"`{s1b.PRIMARY}`" in text
    assert f"`{s1b.FOIL}`" in text
    for arm in s1b.REAL_ARMS:
        assert f"`{arm}`" in text, f"arm {arm!r} is scored but absent from the pre-registration"


def test_the_primary_is_the_composite_and_the_foil_is_the_eight_column_block():
    """The whole story: the 2-col composite is the candidate, the 8-col block is the incumbent."""
    assert s1b.PRIMARY == "pace_axis"
    assert s1b.FOIL == "pace"
    assert s1b.PRIMARY != s1b.FOIL
    assert s1b.PRIMARY in s1b.REAL_ARMS
    assert s1b.FOIL not in s1b.REAL_ARMS, "the foil is the incumbent, never a promotable real arm"


def test_declared_field_size_is_the_registered_real_arm_count():
    assert s1b.DECLARED_FIELD_SIZE_S1B == len(s1b.REAL_ARMS) == 2
    assert "Declared field size = 2 real arms" in _PREREG.read_text()


def test_n_trials_counts_the_foil_and_the_anchors_but_not_the_diagnostic_degenerate():
    """MH2.1 (a): a DIAGNOSTIC anchor must never join the trial field — the anchor that polices the
    metric must not set the gate's own bar. The no-pace degenerate is an orientation check."""
    assert s1b.n_trials_declared() == 1 + len(s1b.REAL_ARMS) + len(s1b.GENERIC_ANCHORS) == 7
    # it IS scored (so the check can run) but does NOT inflate the multiplicity count
    assert s1b.NO_PACE_DEGENERATE in s1b.scored_arms()
    assert s1b.NO_PACE_DEGENERATE not in s1b.REAL_ARMS
    assert s1b.NO_PACE_DEGENERATE not in s1b.GENERIC_ANCHORS


def test_the_sibling_representation_is_retained_so_the_field_is_not_trimmed():
    """MH2.2: a post-hoc trim re-commits the selection bias DSR exists to deflate. `pace_total_axis`
    is expected to tie and is kept anyway."""
    assert "pace_total_axis" in s1b.REAL_ARMS


# ---------------------------------------------------------------------------
# The contrast is the MATCHED PAIR — the thing S1 never gated
# ---------------------------------------------------------------------------

def test_fold_series_is_the_matched_pair_foil_minus_arm():
    foil = {"fold_crps": [10.0, 10.0, 10.0], "buckets": [10.0] * 6}
    arm = {"fold_crps": [9.0, 11.0, 9.5], "buckets": [9.0] * 6}
    got = s1b.fold_series(foil, arm)
    assert np.allclose(got, [1.0, -1.0, 0.5]), "must be foil − arm (>0 ⇔ the arm beats the block)"


def test_the_gain_and_both_series_are_measured_against_the_foil_not_the_reference():
    """⭐ The call-site guard. S1 measured every arm against the 25-col `reference`; S1b's entire
    contribution is that the contrast is against the FOIL. A defect here would silently reproduce
    S1's already-recorded statistic under a new name."""
    src = _src()
    assert re.search(r'gain\s*=\s*foil_crps\s*-\s*a\["pooled_crps"\]', src), \
        "the arm-level gain must be measured against the FOIL"
    assert re.search(r"d_fold\s*=\s*fold_series\(foil,\s*a\)", src)
    assert re.search(r"d_bucket\s*=\s*bucket_series\(foil,\s*a\)", src)
    # and the reference must NOT be the comparison basis anywhere in the arm loop
    assert 'ref_crps - a["pooled_crps"]' not in src


def test_the_binding_dsr_is_computed_on_the_fold_series_at_the_call_site():
    src = _src()
    m = re.search(r'"per_fold_declared_field_degenerate_excluded":\s*_dsr\((\w+),', src)
    assert m, "the binding DSR entry must be present"
    assert m.group(1) == "f_series", "the BINDING DSR must be computed on the per-FOLD series"
    assert re.search(r"f_series\s*=\s*fold_series\(foil,\s*arms\[PRIMARY\]\)", src)
    assert re.search(r'"binding":\s*"per_fold_declared_field_degenerate_excluded"', src)
    assert re.search(r'dsr_binding\s*=\s*dsr\.get\("per_fold_declared_field_degenerate_excluded"',
                     src)


def test_V_is_measured_over_the_real_arms_but_n_trials_keeps_the_anchors():
    """DSR-CONV / MH2.1 (a), declared forward."""
    src = _src()
    assert re.search(r"sr_fold_real\s*=\s*\[sharpe\(fold_series\(foil,\s*arms\[a\]\)\)\s*for a in real\]",
                     src)
    assert re.search(r"V_clean\s*=.*np\.var\(sr_fold_real,\s*ddof=1\)", src)
    assert re.search(r"n_trials\s*=\s*n_trials_declared\(\)", src)


# ---------------------------------------------------------------------------
# ⭐ The two defects this story found — both are the "same gate, two ways" class
# ---------------------------------------------------------------------------

def test_classify_null_receives_the_measured_moments_not_the_gaussian_default():
    """⭐ Without this, `cv_power`'s reachability arithmetic assumes skew 0 / kurt 3 while the
    BINDING `deflated_sharpe` estimates them from the series. On S1b's platykurtic series the two
    disagree by three folds, and the record would publish a "+1 more season" re-test trigger for a
    gate that has ALREADY PASSED."""
    src = _src()
    call = _call_args(src, "v = cv_power.classify_null(")
    assert "skew=arm_skew" in call and "kurt=arm_kurt" in call, \
        "the MEASURED higher moments must be passed to classify_null"
    assert re.search(r"arm_skew,\s*arm_kurt\s*=\s*series_moments\(fold_series\(foil,\s*arms\[arm\]\)\)",
                     src), "the moments must come from THIS arm's own matched-pair series"
    assert "declared_field_size=DECLARED_FIELD_SIZE_S1B" in call
    assert 'observed_sr=r["sharpe_per_fold"]' in call, "classified on the DECLARED series"


def test_the_measured_moments_actually_differ_from_gaussian_on_the_recorded_series():
    """Non-vacuity: the guard above is only meaningful because the moments genuinely move the
    answer. If the series were Gaussian, passing them would be decoration."""
    if not _DECISION.exists():
        pytest.skip("decision artifact absent — run `--stage decide`")
    ms = json.loads(_DECISION.read_text()).get("moment_sensitivity") or {}
    assert ms, "the moment-sensitivity disclosure must be recorded"
    assert ms["folds_needed_for_dsr_measured_moments"] != ms["folds_needed_for_dsr_gaussian_moments"], \
        "if the two agree, the moment fix is decoration and this story's claim about it is wrong"
    assert ms["series_kurtosis"] != 3.0


def test_series_moments_falls_back_to_gaussian_only_when_it_cannot_estimate():
    assert s1b.series_moments(np.array([1.0, 2.0])) == (0.0, 3.0)
    sk, ku = s1b.series_moments(np.array([1.0, 2.0, 10.0, 3.0, 2.5]))
    assert sk != 0.0 and ku != 3.0


def test_a_non_positive_fold_requirement_is_corrected_and_the_raw_string_is_preserved():
    """⭐ A negative fold requirement is a MIS-RENDER of a state, not a re-test instruction. It must
    not reach the record as one — and it must not be silently dropped either (the raw instrument
    output is the evidence that the correction was needed)."""
    src = _src()
    assert re.search(r"degenerate_trigger\s*=\s*bool\(", src)
    assert re.search(r"v\.extra_seasons\s*is None or v\.extra_seasons\s*<=\s*0", src), \
        "a non-positive fold delta must be detected"
    assert '"retest_trigger_raw_from_instrument": raw_trigger' in src, \
        "the raw instrument string must be preserved verbatim, never dropped"
    assert '"retest_trigger": corrected if degenerate_trigger else raw_trigger' in src


def test_the_recorded_run_actually_exercised_the_degenerate_trigger_correction():
    """Non-vacuity for the clause above (NF-D17: a fixture must be able to trip the clause it
    names). The recorded run DID hit the degenerate case, so the correction is live, not theoretical."""
    if not _DECISION.exists():
        pytest.skip("decision artifact absent — run `--stage decide`")
    nulls = json.loads(_DECISION.read_text())["nulls"]
    assert nulls, "the run must classify at least one arm"
    corrected = [a for a, v in nulls.items() if v.get("retest_trigger_corrected")]
    assert corrected, "the recorded run is expected to have hit the degenerate-trigger path"
    for a in corrected:
        raw = nulls[a]["retest_trigger_raw_from_instrument"]
        assert raw and "-" in raw, "the raw string must be kept so the defect is auditable"
        assert "UNDEFINED" in nulls[a]["retest_trigger"]


def test_the_binding_shortfall_is_stated_in_the_unit_that_binds_not_in_folds():
    """NF-D15 (g″): a real-but-underpowered null states its shortfall in the unit that grows. Here
    the binding gate is BH-FDR, so a fold count would be the wrong unit entirely."""
    if not _DECISION.exists():
        pytest.skip("decision artifact absent — run `--stage decide`")
    d = json.loads(_DECISION.read_text())
    sf = d["nulls"][s1b.PRIMARY]["bh_shortfall"]
    assert sf["m_registered_arms"] == s1b.DECLARED_FIELD_SIZE_S1B
    # the BH step for rank i of m at alpha
    assert sf["bh_step_required"] == pytest.approx(
        d["fdr_alpha"] * sf["rank_by_p"] / sf["m_registered_arms"])
    assert sf["shortfall"] == pytest.approx(sf["p_observed"] - sf["bh_step_required"])


# ---------------------------------------------------------------------------
# Anchors, constraint, and the reproduction gate
# ---------------------------------------------------------------------------

def test_the_no_pace_degenerate_must_lose_to_the_foil_and_is_an_anchor_check():
    """The S1b-specific orientation anchor: a contract carrying NO pace beating the block would mean
    the contrast's sign convention is inverted."""
    src = _src()
    assert '"no_pace_degenerate_loses_to_foil"' in src
    assert re.search(r'anchor_report\["no_pace_degenerate"\]', src)
    assert re.search(r"anchors_ok\s*=\s*all\(anchor_checks\.values\(\)\)", src)


def test_the_calibration_constraint_is_inherited_verbatim_and_never_tightened():
    """NF1.8: a floor is a CONSTRAINT, never a target, and tightening it after seeing a result is
    the E2.1-r inversion. S1b must delegate to P2.1's predicate rather than defining its own."""
    src = _src()
    assert re.search(r"elig,\s*why\s*=\s*p21\._eligible\(a\)", src), \
        "eligibility must delegate to the inherited predicate"
    assert not re.search(r"margin_pit_flat_folds\"\]\s*>=\s*\d", src), \
        "S1b must not re-implement (and so risk re-tuning) the PIT clause"
    assert "_CALIB_TARGET" not in src and "_CALIB_TOL" not in src, \
        "S1b must not restate the calibration constants"


def test_pit_is_reported_as_a_gate_and_never_used_to_rank():
    """PIT is a GATE, never a rank (the story's own instruction). It may appear in eligibility and in
    the report, but never in a sort key or a gain."""
    src = _src()
    for bad in ("key=lambda r: -r['margin_pit", 'key=lambda r: -r["margin_pit',
                "sort(key=lambda a: a['margin_pit"):
        assert bad not in src
    # the arm-level gate is composed of the registered clauses only
    m = re.search(r"arm_gates\s*=\s*bool\((.*?)\)\n", src, re.S)
    assert m, "the arm-gate composition must be present"
    assert "margin_pit_flat_folds" not in m.group(1), \
        "PIT enters through `_eligible` only — never as a separate ranking clause"


def test_the_reproduction_gate_covers_the_foil_both_real_arms_and_the_degenerate():
    """Gate R is what converts \"S1b shares S1's substrate\" from an admission into a VERIFIED
    statement — so it must cover every arm the verdict reads, not just the primary."""
    src = _src()
    assert re.search(r"for a in \(FOIL, \*REAL_ARMS, NO_PACE_DEGENERATE\):", src)
    assert "_S1_SCORES" in src


def test_a_missing_reproduction_ARM_fails_closed_rather_than_passing():
    """NF1.7 (a): a check that did not run is never a pass.

    ⚠️ This fixture reaches the *missing-arm* branch only — the S1 scores file exists, so it can
    never exercise the *missing-file* branch. NF-D17: one isolating fixture PER clause, or the
    untested clause can be deleted with the suite still green (which is exactly what the RED proof
    caught here)."""
    out = s1b.reproduction_check({}, tol=1e-4)
    assert out["holds"] is False


def test_a_missing_reproduction_FILE_fails_closed_rather_than_passing(monkeypatch, tmp_path):
    """The sibling clause: with no reproduction target on disk at all, gate R must fail closed.
    Isolated from the arm branch above by supplying arms that WOULD otherwise reproduce."""
    monkeypatch.setattr(s1b, "_S1_SCORES", tmp_path / "definitely-absent.json")
    arms = {a: {"fold_crps": [1.0, 2.0, 3.0]}
            for a in (s1b.FOIL, *s1b.REAL_ARMS, s1b.NO_PACE_DEGENERATE)}
    out = s1b.reproduction_check(arms, tol=1e-4)
    assert out["holds"] is False, "an absent reproduction target must never score as reproduced"
    assert "missing" in out["reason"].lower()


def test_reproduction_actually_held_on_the_recorded_run():
    if not _DECISION.exists():
        pytest.skip("decision artifact absent — run `--stage decide`")
    repro = json.loads(_DECISION.read_text())["reproduction"]
    assert repro["holds"] is True
    assert repro["max_abs_dev"] == 0.0, \
        "the harness is deterministic — anything but an exact reproduction means it drifted"


def test_contrast_activity_raises_when_it_cannot_be_measured():
    """NF1.7 (a) again: an unmeasurable activity share must RAISE, never silently score 100%."""
    import pandas as pd
    with pytest.raises(SystemExit):
        s1b.contrast_active_share(pd.DataFrame({"other": [1, 2]}), [])


# ---------------------------------------------------------------------------
# The verdict rule, and the promise that the study can fail against the served state
# ---------------------------------------------------------------------------

def test_a_sign_flip_triggers_the_pre_registered_revert_to_the_block():
    """Without this the study would be unfalsifiable against the served artifact: the composite
    already serves, so a verdict that never says "revert" cannot fail."""
    src = _src()
    assert re.search(r'verdict\s*=\s*"REVERT_TO_BLOCK"', src)
    assert re.search(r'prim\["sign_flipped_vs_foil"\]', src)
    assert re.search(r'"sign_flipped_vs_foil":\s*bool\(gain\s*<\s*-_TIE_BAND\)', src)
    assert "REVERT_TO_BLOCK" in _PREREG.read_text()


def test_margin_earned_requires_every_gate_including_pbo_and_dsr():
    src = _src()
    m = re.search(r'elif arm_gates and pbo_ok and dsr_ok:\s*\n\s*verdict\s*=\s*"MARGIN_EARNED"', src)
    assert m, "MARGIN_EARNED must require the arm gates AND PBO AND DSR"
    assert re.search(r'if not interpretable:\s*\n\s*verdict\s*=\s*"NOT_INTERPRETABLE"', src), \
        "an uninterpretable run must state no verdict at all"


def test_the_nested_form_tie_band_is_applied_because_the_composite_is_a_subset_of_the_block():
    """The composite's columns are a strict SUBSET of the block's, so under a ridge that zeroed the
    six level coefficients the two arms would collapse. A near-zero margin is a TIE, refused as a
    win."""
    src = _src()
    assert re.search(r'"tie_with_foil":\s*bool\(abs\(gain\)\s*<\s*_TIE_BAND\)', src)
    assert "not prim[\"tie_with_foil\"]" in src


def test_every_verdict_declares_its_effect_on_the_served_artifact():
    """The composite ALREADY serves, so each verdict must say what it does to the served state or
    the study is unfalsifiable in practice."""
    for v in ("MARGIN_EARNED", "MARGIN_NOT_EARNED", "REVERT_TO_BLOCK", "NOT_INTERPRETABLE"):
        eff = s1b._served_effect(v)
        assert isinstance(eff, str) and eff, f"verdict {v} declares no served effect"
    assert "REVERT" in s1b._served_effect("REVERT_TO_BLOCK")
    assert "NO CHANGE" in s1b._served_effect("MARGIN_NOT_EARNED")


# ---------------------------------------------------------------------------
# Do not destroy a decided story's audit trail
# ---------------------------------------------------------------------------

def test_s1b_writes_only_its_own_output_paths():
    """NCAAF-P2.1 S1-serve defect 3: a story run that overwrites a DECIDED story's outputs destroys
    evidence, and `git status` was the only thing that caught it last time."""
    src = _src()
    written = _written_paths(src)
    assert written, "non-vacuity: the module must write SOMETHING, or this guard checks nothing"
    for const in sorted(written):
        target = getattr(s1b, const, None)
        assert target is not None, f"{const} is written but is not a module-level path constant"
        assert target.name not in s1b._DECIDED_STORY_PATHS_NEVER_WRITTEN, \
            f"S1b writes {target.name} — a DECIDED story's artifact"
        assert "s1b" in target.name, f"{const} must be an S1b-owned path, got {target.name}"
    # and the reproduction target specifically is never among them
    assert "_S1_SCORES" not in written


def test_the_s1_scores_file_is_only_ever_read():
    """S1's scores are the reproduction TARGET — reading is required, writing would be the defect."""
    src = _src()
    assert "_S1_SCORES.read_text()" in src
    assert "_S1_SCORES.write_text" not in src


# ---------------------------------------------------------------------------
# Honest framing
# ---------------------------------------------------------------------------

def test_the_run_records_best_alpha_zero_and_claims_no_edge():
    if not _DECISION.exists():
        pytest.skip("decision artifact absent — run `--stage decide`")
    assert json.loads(_DECISION.read_text())["best_alpha"] == 0


def test_the_preregistration_discloses_that_no_held_out_season_exists():
    """The single most important limit on what S1b can claim. If this disclosure is ever dropped the
    record starts implying an independent replication that does not exist."""
    text = _PREREG.read_text()
    assert "no held-out season" in text.lower()
    assert "2018" in text and "2025" in text
    assert "byte-identical" in text, "the determinism disclosure must survive too"


def test_the_dossier_reports_the_pbo_companions_that_separate_a_tie_from_an_unstable_pick():
    """NF1.8: a rank statistic alone cannot tell "unstable" from "tied", and the two readings imply
    opposite things for a representation that already serves."""
    if not _DECISION.exists():
        pytest.skip("decision artifact absent — run `--stage decide`")
    pc = json.loads(_DECISION.read_text())["pbo_companions"]
    assert pc["available"] is True
    for k in ("contender_spread_pct_of_foil", "fold_flip_distribution",
              "median_oos_rank_of_is_best", "n_candidates"):
        assert k in pc, f"the PBO companion {k!r} must be reported"


def test_classify_null_signature_still_accepts_the_moments_this_harness_passes():
    """If the shared instrument ever drops these parameters, the Gaussian default returns silently
    and the misleading trigger comes back. Fail loudly instead."""
    p = inspect.signature(cv_power.classify_null).parameters
    assert "skew" in p and "kurt" in p and "declared_field_size" in p
