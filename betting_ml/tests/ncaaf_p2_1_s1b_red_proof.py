"""RED proof for NCAAF-P2.1 S1b's guards — `uv run python betting_ml/tests/ncaaf_p2_1_s1b_red_proof.py`.

Each claim in `test_ncaaf_p2_1_s1b_composite.py` is proved by re-introducing the defect it guards
against and requiring the named test to go RED. Harness contract (the accumulated rules, because a
red proof has at least four ways to lie):

  * ⭐ the mutation anchor must be **UNIQUE** in the file. Two functions with byte-identical tails
    make `replace(old, new, 1)` land on the WRONG one, and the run comes back GREEN reporting a
    FALSE "the guard is vacuous" — the dangerous direction, because it invites weakening a correct
    guard (E11.24 prediction_log);
  * the mutation must be asserted to have **LANDED** — a silently no-op'd break reads as "the guard
    caught it" (E11.24 #682);
  * where the guard asserts on a TOKEN, that token must be asserted **GONE** after the mutation. A
    break that lands but leaves the assertion satisfied is a false GREEN (E11.24 #815);
  * pytest runs in a **SUBPROCESS**, so `pytest.raises`' `Failed` (a `BaseException`, not an
    `Exception`) cannot leak past a too-narrow `except` and be read as a pass (NF-W6c);
  * ⚠️ ONLY exit code 1 (tests FAILED) counts as RED. 2/3/4/5 is a BROKEN HARNESS, never a caught
    break — otherwise a syntax error reads as "the guard caught it" (NF-INFRA1);
  * every file is restored in a `finally`.

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~25 s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_ncaaf_p2_1_s1b_composite.py"
_H = "quant_sports_intel_models/football/ncaaf/models/p2_1_s1b_composite.py"
_P = "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p2_1_s1b_preregistration.md"

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS: list[tuple[str, str, str, str, str, str | None]] = [
    # ── the contrast is the matched pair, not S1's vs-reference delta ────────────────────────────
    ("contrast: measure the gain vs the REFERENCE again (S1's already-recorded statistic)", _H,
     '        gain = foil_crps - a["pooled_crps"]',
     '        gain = arms["reference"]["pooled_crps"] - a["pooled_crps"]',
     "measured_against_the_foil_not_the_reference", 'gain = foil_crps - a["pooled_crps"]'),
    ("contrast: fold_series returns arm − foil (the sign convention inverts)", _H,
     "    return f[:n] - a[:n]\n\n\ndef bucket_series",
     "    return a[:n] - f[:n]\n\n\ndef bucket_series",
     "matched_pair_foil_minus_arm", None),
    ("contrast: the per-arm delta is built from the reference, not the foil", _H,
     "        d_fold = fold_series(foil, a)",
     '        d_fold = fold_series(arms["reference"], a)',
     "measured_against_the_foil_not_the_reference", "d_fold = fold_series(foil, a)"),

    # ── the binding DSR ─────────────────────────────────────────────────────────────────────────
    ("DSR: the BINDING figure is computed on the per-BUCKET series", _H,
     '            "per_fold_declared_field_degenerate_excluded": _dsr(f_series, n_trials, V_clean),',
     '            "per_fold_declared_field_degenerate_excluded": _dsr(b_series, n_trials, V_clean),',
     "binding_dsr_is_computed_on_the_fold_series", "_dsr(f_series, n_trials, V_clean)"),
    ("DSR: V is measured over the anchors too (the oracle sets the bar)", _H,
     "    V_clean = float(np.var(sr_fold_real, ddof=1)) if len(sr_fold_real) > 1 else None",
     "    V_clean = float(np.var(sr_fold_all, ddof=1)) if len(sr_fold_all) > 1 else None",
     "V_is_measured_over_the_real_arms", "np.var(sr_fold_real, ddof=1)"),

    # ── ⭐ defect 1: the Gaussian-moment default ─────────────────────────────────────────────────
    ("moments: classify_null goes back to the Gaussian default (the misleading trigger returns)", _H,
     "            skew=arm_skew, kurt=arm_kurt,\n", "",
     "receives_the_measured_moments", "skew=arm_skew"),
    ("moments: series_moments always returns Gaussian (the fix becomes decoration)", _H,
     "    from scipy import stats\n    x = np.asarray(x, float)\n    if len(x) < 3:\n"
     "        return 0.0, 3.0",
     "    from scipy import stats\n    x = np.asarray(x, float)\n    if True:\n"
     "        return 0.0, 3.0",
     "series_moments_falls_back_to_gaussian", None),

    # ── ⭐ defect 2: the mis-rendered non-positive trigger ───────────────────────────────────────
    ("trigger: stop detecting a non-positive fold requirement (publish '-8 folds')", _H,
     "        degenerate_trigger = bool(\n            not override and v.folds_needed is not None\n"
     "            and (v.extra_seasons is None or v.extra_seasons <= 0))",
     "        degenerate_trigger = False",
     "non_positive_fold_requirement_is_corrected", "v.extra_seasons <= 0"),
    ("trigger: drop the raw instrument string (the defect stops being auditable)", _H,
     '            "retest_trigger_raw_from_instrument": raw_trigger,\n', "",
     "non_positive_fold_requirement_is_corrected", '"retest_trigger_raw_from_instrument": raw_trigger'),

    # ── anchors + the inherited constraint ───────────────────────────────────────────────────────
    ("anchor: drop the no-pace degenerate orientation check", _H,
     '        "no_pace_degenerate_loses_to_foil": _anchor("no_pace_degenerate", "loses_to_foil", False),\n',
     "",
     "no_pace_degenerate_must_lose_to_the_foil", '"no_pace_degenerate_loses_to_foil"'),
    ("constraint: re-implement eligibility instead of delegating (so it can be re-tuned)", _H,
     '        elig, why = p21._eligible(a)',
     '        elig, why = (a["margin_pit_flat_folds"] >= 5, "")',
     "calibration_constraint_is_inherited_verbatim", "elig, why = p21._eligible(a)"),
    ("reproduction: gate R covers only the primary, not the foil and siblings", _H,
     "    for a in (FOIL, *REAL_ARMS, NO_PACE_DEGENERATE):",
     "    for a in (PRIMARY,):",
     "reproduction_gate_covers_the_foil", "(FOIL, *REAL_ARMS, NO_PACE_DEGENERATE)"),
    ("reproduction: a missing target passes instead of failing closed", _H,
     '        return {"holds": False, "reason": f"S1 scores missing at {_S1_SCORES.name}",',
     '        return {"holds": True, "reason": f"S1 scores missing at {_S1_SCORES.name}",',
     "missing_reproduction_FILE_fails_closed", None),
    ("activity: an unmeasurable contrast share scores 100% instead of raising", _H,
     '        raise SystemExit(f"[{_STORY}] cannot measure contrast activity: {probe!r} absent from cache")',
     '        return {"active_share": 1.0, "per_fold": [], "n_eval_rows": 0, "n_active_rows": 0}',
     "contrast_activity_raises", "raise SystemExit(f\"[{_STORY}] cannot measure"),

    # ── the field ───────────────────────────────────────────────────────────────────────────────
    ("field: the foil is also a promotable real arm", _H,
     'REAL_ARMS: tuple[str, ...] = ("pace_axis", "pace_total_axis")',
     'REAL_ARMS: tuple[str, ...] = ("pace_axis", "pace_total_axis", "pace")',
     "the_foil_is_the_eight_column_block", None),
    ("field: trim the tied sibling (the MH2.2 post-hoc trim)", _H,
     'REAL_ARMS: tuple[str, ...] = ("pace_axis", "pace_total_axis")',
     'REAL_ARMS: tuple[str, ...] = ("pace_axis",)',
     "sibling_representation_is_retained or declared_field_size", None),
    ("field: the diagnostic degenerate is counted in n_trials (it sets the gate's bar)", _H,
     "    return 1 + len(REAL_ARMS) + len(GENERIC_ANCHORS)",
     "    return 2 + len(REAL_ARMS) + len(GENERIC_ANCHORS)",
     "n_trials_counts_the_foil_and_the_anchors", None),

    # ── the verdict rule ────────────────────────────────────────────────────────────────────────
    ("verdict: no REVERT trigger (the study cannot fail against the served state)", _H,
     '        verdict = "REVERT_TO_BLOCK"',
     '        verdict = "MARGIN_NOT_EARNED"',
     "sign_flip_triggers_the_pre_registered_revert", 'verdict = "REVERT_TO_BLOCK"'),
    ("verdict: MARGIN_EARNED no longer requires PBO", _H,
     "    elif arm_gates and pbo_ok and dsr_ok:",
     "    elif arm_gates and dsr_ok:",
     "margin_earned_requires_every_gate", "arm_gates and pbo_ok and dsr_ok"),
    ("verdict: drop the nested-form tie band (a collapse onto the foil scores as a win)", _H,
     '            "tie_with_foil": bool(abs(gain) < _TIE_BAND),',
     '            "tie_with_foil": False,',
     "nested_form_tie_band_is_applied", '"tie_with_foil": bool(abs(gain) < _TIE_BAND)'),
    ("verdict: a verdict with no declared served effect", _H,
     '        "REVERT_TO_BLOCK": (\n            "REVERT `SERVED_PACE_COLS` to the 8-column block',
     '        "REVERT_TO_BLOCK_XX": (\n            "REVERT `SERVED_PACE_COLS` to the 8-column block',
     "every_verdict_declares_its_effect", None),

    # ── do not destroy a decided story's audit trail ─────────────────────────────────────────────
    ("paths: the battery writes S1's scores file (overwriting a DECIDED story)", _H,
     "    _SCORES_JSON.write_text(json.dumps(out, indent=2, default=float))",
     "    _S1_SCORES.write_text(json.dumps(out, indent=2, default=float))",
     "writes_only_its_own_output_paths or s1_scores_file_is_only_ever_read", None),

    # ── the pre-registration's load-bearing disclosures ──────────────────────────────────────────
    ("prereg: drop the 'no held-out season' disclosure", _P,
     "**There is NO held-out season, and there cannot be one this cycle.**",
     "**The design uses season-forward folds.**",
     "discloses_that_no_held_out_season_exists", "no held-out season"),
    ("prereg: the declared field size drifts from the code", _P,
     "**Declared field size = 2 real arms**",
     "**Declared field size = 3 real arms**",
     "declared_field_size_is_the_registered_real_arm_count", "Declared field size = 2 real arms"),
]


def main() -> int:
    failures: list[str] = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()

        occurrences = original.count(old)
        if occurrences == 0:
            print(f"{'BROKEN ❌ (anchor not found)':32} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        # ⭐ the anchor must be UNIQUE, or `replace(..., 1)` can mutate the wrong symbol and the run
        # comes back GREEN reporting a FALSE "vacuous guard".
        if occurrences > 1:
            print(f"{'BROKEN ❌ (anchor x%d)' % occurrences:32} {name}")
            failures.append(f"{name}: anchor appears {occurrences}× in {rel} — not unique")
            continue

        mutated = original.replace(old, new, 1)
        if mutated == original:                     # #682 — the break must actually land
            print(f"{'BROKEN ❌ (mutation no-op)':32} {name}")
            failures.append(f"{name}: mutation did not change the file")
            continue
        if gone is not None and gone in mutated:    # #815 — the asserted token must be GONE
            print(f"{'BROKEN ❌ (token survives)':32} {name} -> {gone!r} still present")
            failures.append(f"{name}: asserted token survived the mutation")
            continue

        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                # rc 2/3/4/5 = collection error, no tests matched, etc. NEVER a caught break.
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:32} {name}\n{'':32} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every S1b guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
