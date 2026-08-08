"""nf_recal1_red_proof.py — prove every NF-RECAL1 guard can actually FAIL.

⚠️ NOT PYTEST-COLLECTED (no `test_` prefix on the module) — this is an operator/CI-adjacent harness,
run explicitly:

    uv run python betting_ml/tests/nf_recal1_red_proof.py

WHY IT EXISTS. A guard that cannot fail is worse than none (INC-38/INC-39), and this programme has
shipped vacuous guards repeatedly — NF-TR1 found FOUR on one story, all by breaking the source and
none by review. Reading a green suite tells you nothing about whether it would go red. Each case
below applies a SURGICAL break to the real source, re-imports the module, runs the specific guard,
and requires it to FAIL. Every break is reverted in a `finally`, so a crash cannot leave the tree
dirty.

⭐ The breaks are chosen to be the plausible FUTURE EDIT, not an absurd one: deleting a clause from
an `and`-gate, re-anchoring the tier on the outcome, dropping the incumbent term from C3, reverting
the ceiling to a least-squares fit. A red-proof against an absurd break proves only that the test
reads the file.
"""
from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MOD = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/level_recalibration.py"
_RPR = _ROOT / "quant_sports_intel_models/football/nfl/fantasy/rookie_point_recalibration.py"
_SUITE = "betting_ml/tests/test_nf_recal1_level_recalibration.py"

def _code_only(src: str) -> str:
    """The source with its MODULE DOCSTRING blanked out (line-for-line, so offsets are preserved).

    ⭐⭐ THIS FUNCTION EXISTS BECAUSE THE HARNESS BIT ITSELF. Three breaks below "applied" cleanly and
    the guards stayed GREEN — because `str.replace(old, new, 1)` had hit an occurrence of the anchor
    inside the module's own DOCSTRING (this file's pre-registration quotes its constants in prose:
    ``SELECTION_METRIC = "crps"`` appears at line 130 and the real assignment at line 354). The break
    edited a sentence and left the code untouched, so a vacuous guard reported as proven.

    That is the repo's own documented lesson — a source-inspection check is vacuous if PROSE can
    satisfy it (INC-38) — landing on the instrument built to catch vacuous checks. The cure is the
    same one: strip the prose FIRST, and make an anchor that is not uniquely locatable in CODE a
    hard error rather than a silent mis-patch."""
    out, in_doc, seen = [], False, False
    for line in src.splitlines(keepends=True):
        blanked = re.sub(r"[^\n]", " ", line)     # same LENGTH, same newlines ⇒ offsets preserved
        if not seen and line.lstrip().startswith('"""'):
            seen, in_doc = True, True
            out.append(blanked)
            if line.strip() != '"""' and line.rstrip().endswith('"""'):
                in_doc = False
            continue
        if in_doc:
            out.append(blanked)
            if line.rstrip().endswith('"""'):
                in_doc = False
            continue
        out.append(line)
    return "".join(out)


# (case name, old source fragment, replacement, the test that MUST go red)
# Cases whose anchor lives in an IMPORTED module rather than in `level_recalibration`.
FILE_OVERRIDE = {"lambda-zero-stops-reproducing-the-incumbent": _RPR}

CASES: list[tuple[str, str, str, str]] = [
    (
        "c3-drops-the-incumbent-term (the clause becomes a bare floor again)",
        'bind = min(float(floor), float(inc[q])) if q in inc and inc[q] is not None else float(floor)',
        'bind = float(floor)',
        "test_c3_governs_the_change_so_the_incumbent_is_admissible_at_its_own_coverage",
    ),
    (
        "c3-loses-its-teeth (the clause stops binding at all)",
        'need = int(np.ceil(bind * n))',
        'need = 0',
        "test_c3_still_refuses_an_arm_that_makes_a_shortfall_worse",
    ),
    (
        "c3-becomes-a-pooled-mean (one position can breach unseen)",
        '"ok": bool(per) and all(v["ok"] for v in per.values()),',
        '"ok": bool(per) and (sum(v["coverage"] for v in per.values()) / len(per)) >= float(floor),',
        "test_c3_refuses_a_single_position_and_is_never_a_pooled_mean",
    ),
    (
        "the-floor-is-raised-above-nominal (NF1.8's prohibition)",
        'COVERAGE_FLOOR = 0.80',
        'COVERAGE_FLOOR = 0.85',
        "test_the_coverage_floor_is_never_raised_above_nominal",
    ),
    (
        "the-tier-is-re-anchored-on-the-realized-outcome (§0's whole hazard)",
        'TIER_ANCHOR = "incumbent_projection"',
        'TIER_ANCHOR = "realized_outcome"',
        "test_the_tier_anchor_is_the_incumbent_and_outcome_anchors_are_forbidden",
    ),
    (
        "the-tier-size-is-hard-coded-instead-of-derived",
        # ⚠️ `n = 13` would be NO BREAK AT ALL — 13 IS the correct slot count, so the guard was
        #    right to stay green and the CASE was the defect. A red-proof case that does not change
        #    behaviour proves nothing, which is the same vacuity one level up.
        'n = sum(int(s.count) for s in roster if skill.intersection(set(s.eligible)))',
        'n = 14',
        "test_the_draftable_tier_is_derived_from_the_shipped_preset",
    ),
    (
        "the-rookie-scope-gate-stops-raising",
        'if col in frame.columns and bool(pd.Series(frame[col]).fillna(False).astype(bool).any()):',
        'if False:',
        "test_a_rookie_row_in_the_population_is_a_hard_failure",
    ),
    (
        "the-scope-gate-stops-re-reading-the-imported-disposition",
        'if RPP.DISPOSITION != "CONSTRAINT_REFUSED" or bool(getattr(RPP, "SERVING_ENABLED", False)):',
        'if False:',
        "test_the_scope_gate_re_reads_the_imported_disposition",
    ),
    (
        "mae-is-quietly-restored-as-the-selection-metric",
        'SELECTION_METRIC = "crps"',
        'SELECTION_METRIC = "mae"',
        "test_mae_is_forbidden_as_the_selection_metric",
    ),
    (
        "the-quantile-function-stops-clipping-at-zero",
        'return np.clip(q, 0.0, None)',
        'return q',
        "test_the_quantile_function_is_clipped_at_zero",
    ),
    (
        "lambda-zero-stops-reproducing-the-incumbent",
        '    if lam == 0.0:\n        return p.copy()',
        '    if lam == 0.0:\n        return p * 1.001',
        "test_lambda_zero_reproduces_the_incumbent_exactly_for_every_form",
    ),
    (
        "an-empty-evidence-set-becomes-a-free-grid (NF1.7 (a))",
        '        return (float(EMPTY_EVIDENCE_LAMBDA),)',
        '        return tuple(float(x) for x in grid)',
        "test_an_empty_evidence_set_yields_no_correction_rather_than_a_free_grid",
    ),
    (
        "ties-break-toward-MORE-correction",
        '    best = min(cands)',
        '    best = max(cands, key=lambda t: (-t[0], t[1]))',
        "test_select_lambda_breaks_ties_toward_less_correction",
    ),
    (
        "the-ceiling-reverts-to-a-least-squares-fit (matched-objective lost)",
        '    from scipy.optimize import minimize',
        '    from scipy.optimize import minimize\n    return dict(init or {})',
        "test_a_metric_fitted_ceiling_bounds_its_own_form_where_a_least_squares_one_need_not",
    ),
    (
        "two-forms-share-one-peeking-ceiling (NF-D16 (g‴))",
        'FAMILY_CEILING = {f: f"oracle_{f}" for f in FORMS}',
        'FAMILY_CEILING = {f: "oracle_pos_const" for f in FORMS}',
        "test_every_form_has_its_own_peeking_ceiling",
    ),
    (
        "a-missing-anchor-becomes-a-pass (NF1.7 (a))",
        '        raise SystemExit(\n            f"the anchor(s) {missing} did not score',
        '        return None\n        raise SystemExit(\n            f"the anchor(s) {missing} did not score',
        "test_a_missing_anchor_is_a_hard_failure_not_a_pass",
    ),
    (
        "the-sanity-degenerate-flag-is-re-bundled-with-the-magnitude-hypothesis (NF-D20)",
        '        "sanity_degenerates_lose": bool(sanity_degenerates_lose),',
        '        "sanity_degenerates_lose": bool(sanity_degenerates_lose and over_scale_loses),',
        "test_the_sanity_degenerate_flag_is_split_from_the_magnitude_hypothesis",
    ),
    (
        "the-pooled-gate-stops-reading-C3",
        '        "coverage_floors_hold": bool((coverage or {}).get("ok")),',
        '        "coverage_floors_hold": True,',
        "test_the_pooled_gate_requires_all_three_constraints",
    ),
    (
        "the-deflation-bars-are-re-typed-instead-of-inherited",
        'from quant_sports_intel_models.football.nfl.fantasy.rookie_point_recalibration import (\n    ALPHA,',
        'ALPHA = 0.25\nfrom quant_sports_intel_models.football.nfl.fantasy.rookie_point_recalibration import (\n    ALPHA as _UNUSED_ALPHA,',
        "test_the_framing_and_deflation_bars_are_inherited_not_re_chosen",
    ),
    (
        "the-attribution-signature-stops-reading-the-bias-direction (NF-D15 (g′))",
        '    toward_zero = abs(float(winner_bias)) < abs(float(incumbent_bias))',
        '    toward_zero = True',
        "test_the_attribution_signature_separates_a_level_fix_from_a_per_player_effect",
    ),
    (
        "leg-monotone-is-renamed-back-to-an-unscoped-whole-board-claim",
        'LEG_MONOTONE_FORMS = ("global_const",)',
        'GLOBAL_MONOTONE_FORMS = LEG_MONOTONE_FORMS = ("global_const",)',
        "test_leg_monotone_is_named_for_its_scope_because_the_board_holds_untouched_rows",
    ),
    (
        "a-space-invariant-form-is-mis-declared-as-acting",
        'SPACE_INVARIANT_FORMS = ("global_const", "pos_const", "avail_cond")',
        'SPACE_INVARIANT_FORMS = ("global_const", "pos_const", "avail_cond", "pos_offset")',
        "test_space_invariance_is_exact",
    ),
    (
        "the-per-game-space-collapses-into-the-season-total-one (the foil goes vacuous)",
        "out[sel] = p[sel] + (float(c) * g[sel] if space == \"per_game\" else float(c))",
        "out[sel] = p[sel] + float(c)",
        "test_the_per_game_channel_actually_acts_on_the_forms_that_carry_an_intercept",
    ),
    (
        "an-inverted-band-is-no-longer-re-sorted",
        '    return p, np.minimum(lo, hi), np.maximum(lo, hi)',
        '    return p, lo, hi',
        "test_an_inverted_band_is_re_sorted_so_the_score_stays_well_defined",
    ),
]


def _run(test: str) -> bool:
    """True when the named guard PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{_SUITE}::{test}", "-q", "--no-header", "-p",
         "no:cacheprovider"],
        cwd=_ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main() -> int:
    originals = {p: p.read_text() for p in (_MOD, _RPR)}
    importlib.invalidate_caches()

    print(f"NF-RECAL1 red-proof — {len(CASES)} cases\n")
    ok, bad = 0, []
    for name, old, new, test in CASES:
        target = FILE_OVERRIDE.get(name, _MOD)
        original = originals[target]
        # ⭐ MATCH AGAINST THE CODE-ONLY VIEW so a break can never land in the module docstring, and
        #   REFUSE an anchor that is not uniquely locatable in code rather than mis-patching it.
        code = _code_only(original)
        hits = code.count(old)
        if hits == 0:
            bad.append((name, f"the anchor is not present in {target.name}'s CODE (it may exist only "
                              "in prose) — this case is silently testing nothing"))
            print(f"  ✗ {name}\n      anchor missing from code; case is vacuous")
            continue
        if hits > 1:
            bad.append((name, f"the anchor occurs {hits}x in code — an ambiguous patch is not a "
                              "surgical break"))
            print(f"  ✗ {name}\n      anchor is ambiguous ({hits} code hits)")
            continue
        at = code.index(old)                      # valid in the ORIGINAL: `_code_only` blanks the
        try:                                      # docstring CHARACTER-for-character (see its note)
            target.write_text(original[:at] + new + original[at + len(old):])
            passed = _run(test)
        finally:
            target.write_text(original)
        if passed:
            bad.append((name, f"{test} still PASSES with the clause broken — the guard is VACUOUS"))
            print(f"  ✗ {name}\n      {test} stayed GREEN")
        else:
            ok += 1
            print(f"  ✓ {name}\n      {test} → RED")

    # ⭐ The suite must be GREEN on the restored source, or a failed revert would look like a pass.
    print("\nrestored source: re-running the full suite …")
    green = subprocess.run(
        [sys.executable, "-m", "pytest", _SUITE, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=_ROOT, capture_output=True, text=True)
    if green.returncode != 0:
        print("  ✗ the suite is RED on the restored source — the revert did not work")
        return 2
    print("  ✓ green on restored source")

    print(f"\n{ok}/{len(CASES)} guards proven RED")
    for n, why in bad:
        print(f"  ⚠️ {n}: {why}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
