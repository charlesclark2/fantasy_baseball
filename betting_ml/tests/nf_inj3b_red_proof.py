"""nf_inj3b_red_proof.py — prove every NF-INJ3b guard actually FAILS on deliberately-broken source.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / NF-D17). This harness applies ONE
break at a time and asserts the named test goes RED.

⭐ THREE failure modes OF A RED PROOF ITSELF are guarded against, because all three have shipped a
FALSE result in this repo:
  · #682 — the mutation silently NO-OPS ⇒ assert the file CHANGED on disk;
  · #815 — it lands but does not move the asserted predicate ⇒ assert the token is GONE afterwards;
  · E11.24 — it lands on the WRONG symbol ⇒ assert the anchor is UNIQUE before applying.
Backups are restored AT START-UP as well as in `finally`, because this harness's own worst case is
being killed mid-mutation (E11.26).

⚠️ AND THE FOURTH, WHICH IS SPECIFIC TO THIS STORY: NF-INJ3b's whole subject is a REGISTRATION, and
part of that registration lives in a MARKDOWN document, not in code. So some breaks target the
pre-registration file — a registration clause nothing checks is a clause that can silently drift.

RUN:  uv run python betting_ml/tests/nf_inj3b_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_nf_inj3b_injury_games.py"
PREREG = (ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
          / "nf_inj3b_preregistration.md")
TESTS = "betting_ml/tests/test_nf_inj3b_registration.py"

BREAKS: list[tuple[str, Path, str, str, str]] = [
    # ── the field, declared on mechanism ──────────────────────────────────────────────────────
    ("the excluded arm is silently re-admitted to the field", RUN,
     '    "no_cap",           # DEGENERATE\n)',
     '    "no_cap",           # DEGENERATE\n    "sus_regime",\n)',
     "TestTheDeclaredField::test_sus_regime_is_excluded_on_MECHANISM_with_a_recorded_reason"),

    ("an arm the inherited harness cannot score is INVENTED mid-registration", RUN,
     '    "hurdle_transfer",  # PRIMARY',
     '    "hurdle_transfer_v2",  # PRIMARY',
     "TestTheDeclaredField::test_every_declared_arm_is_one_the_inherited_harness_can_actually_score"),

    ("the primary reverts to NF-INJ3's timing arm", RUN,
     'PRIMARY_ARM = "hurdle_transfer"',
     'PRIMARY_ARM = "timing_aware"',
     "TestTheDeclaredField::test_the_primary_is_registered_and_is_the_hurdle_form"),

    # ── V membership: THE specification change this story exists for ──────────────────────────
    ("the REFERENCE arm is put back inside V (NF-INJ3's own defect)", RUN,
     "V_EXCLUDED_ARMS: tuple[str, ...] = DEGENERATE_ARMS + (INCUMBENT_REFERENCE,)",
     "V_EXCLUDED_ARMS: tuple[str, ...] = DEGENERATE_ARMS",
     "TestVMembership::test_the_incumbent_REFERENCE_arm_is_excluded_from_V"),

    ("V silently keeps the degenerates too (DSR-CONV dropped)", RUN,
     '    srs_v = {k: v for k, v in srs_all.items() if k not in V_EXCLUDED_ARMS}\n'
     '    d = np.asarray(lifts[primary], dtype=float)\n    scores = mat.mean(axis=1)',
     '    srs_v = dict(srs_all)\n'
     '    d = np.asarray(lifts[primary], dtype=float)\n    scores = mat.mean(axis=1)',
     "TestVMembership::test_V_is_measured_over_exactly_the_non_degenerate_non_reference_arms"),

    ("n_trials is TRIMMED to V's size — multiplicity quietly escapes (MH2.2)", RUN,
     '        "n_trials": DECLARED_FIELD_SIZE,',
     '        "n_trials": len(srs_v),',
     "TestVMembership::test_n_trials_stays_at_the_FULL_declared_field_so_nothing_escapes_multiplicity"),

    # ── the BH family ─────────────────────────────────────────────────────────────────────────
    ("the BH family becomes the STRICT across-arms reading after the fact", RUN,
     '        "survives": bool(p_primary is not None and p_primary < BH_Q),',
     '        "survives": bool(strict.get(primary)),',
     "TestTheBHFamily::test_the_registered_family_BINDS_even_when_the_strict_reading_disagrees"),

    ("the strict sensitivity is marked ACTIONABLE, licensing a post-hoc swap", RUN,
     '            "admissible_to_act_on": False},\n    }\n\n    perm_lift',
     '            "admissible_to_act_on": True},\n    }\n\n    perm_lift',
     "TestTheBHFamily::test_the_registered_family_BINDS_even_when_the_strict_reading_disagrees"),

    # ── the reproduction pin ──────────────────────────────────────────────────────────────────
    ("the pin rounds to 6dp, capping itself at 1e-6", RUN,
     "            dv = abs(float(f[\"arms\"][a][\"crps\"]) - float(o[\"arms\"][a][\"crps\"]))",
     "            dv = abs(round(float(f[\"arms\"][a][\"crps\"]), 6) - round(float(o[\"arms\"][a][\"crps\"]), 6))",
     "TestTheReproductionPin::test_the_tolerance_is_1e_9_and_is_not_a_rounded_comparison"),

    ("an absent parent artifact is scored as a PASS", RUN,
     '        return {"evaluable": False, "artifact": other_path.name,',
     '        return {"evaluable": True, "passes": True, "artifact": other_path.name,',
     "TestTheReproductionPin::test_a_missing_parent_artifact_is_a_FAILED_check_never_a_pass"),

    ("a VACUOUS (incomplete) comparison passes on almost nothing", RUN,
     '            "passes": bool(n_cmp == expected and n_cmp > 0 and worst < PIN_TOL)}',
     '            "passes": bool(worst < PIN_TOL)}',
     "TestTheReproductionPin::test_an_incomplete_comparison_is_VACUOUS_and_therefore_fails"),

    ("a real drift no longer names WHICH arms diverged", RUN,
     '            "arms_that_diverge": sorted([a for a, v in per_arm.items() if v >= PIN_TOL]),',
     '            "arms_that_diverge": [],',
     "TestTheReproductionPin::test_a_difference_above_the_tolerance_fails_and_names_the_diverging_arms"),

    ("a missing attribution control is scored as clean", RUN,
     '           else {"evaluable": False, "why": "no --parent-control artifact supplied — the "',
     '           else {"evaluable": True, "passes": True, "why": "no --parent-control artifact supplied — the "',
     "TestTheReproductionPin::test_a_missing_attribution_control_is_NOT_scored_as_clean"),

    # ── deflation wiring ──────────────────────────────────────────────────────────────────────
    ("PBO is fed RAW CRPS, ranking the field upside down", RUN,
     '    mat = np.array([[-f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)',
     '    mat = np.array([[f["arms"][a]["crps"] for f in per_fold] for a in arms], dtype=float)',
     "TestDeflationWiring::test_pbo_is_computed_on_NEGATED_crps"),

    ("the winner-deletion refusal is removed (NF-W7h)", RUN,
     "    if far == primary:",
     "    if False:",
     "TestDeflationWiring::test_a_dsr_reached_by_deleting_the_arm_under_test_is_REFUSED"),

    ("the parent-convention diagnostic is marked ACTIONABLE (E2.1-r)", RUN,
     '        "admissible_to_act_on": False,\n        "why": "NF-INJ3\'s convention',
     '        "admissible_to_act_on": True,\n        "why": "NF-INJ3\'s convention',
     "TestDeflationWiring::test_the_parent_convention_diagnostic_is_marked_INADMISSIBLE"),

    # ── gates ─────────────────────────────────────────────────────────────────────────────────
    ("a gate is quietly dropped from the must-pass set", RUN,
     '        "hurdle_attributable": bool(foil["mean_delta"] > 0),\n    }',
     '    }',
     "TestGates::test_all_nine_registered_gates_must_pass_to_ship"),

    ("gate 9 reverts to NF-INJ3's TIMING attribution", RUN,
     '        "hurdle_attributable": bool(foil["mean_delta"] > 0),',
     '        "timing_attributable": bool(foil["mean_delta"] > 0),',
     "TestGates::test_gate_9_measures_the_hurdle_split_not_timing"),

    ("a degenerate that WINS is scored as losing", RUN,
     '             "loses_to_primary": bool(_m(lambda f, dg=dg: f["arms"][dg]["crps"])\n                                      > _m(lambda f: f["arms"][primary]["crps"]) + 1e-9)}',
     '             "loses_to_primary": True}',
     "TestGates::test_a_degenerate_that_WINS_is_fatal"),

    ("an unfittable matched-n control is scored as evaluable", RUN,
     '        {"evaluable": False, "why": "matched-n control unfittable',
     '        {"evaluable": True, "why": "matched-n control unfittable',
     "TestGates::test_an_unevaluable_matched_n_control_fails_the_oracle_gate"),

    ("a missing own-form oracle is scored as a PASS", RUN,
     '            out[a] = {"evaluable": False,\n                      "why": "no own-form peeking oracle',
     '            out[a] = {"evaluable": True, "respects_oracle": True,\n                      "why": "no own-form peeking oracle',
     "TestGates::test_a_missing_own_form_oracle_is_recorded_as_NOT_evaluable"),

    # ── output discipline: never clobber a DECIDED story's audit trail ────────────────────────
    ("the runner writes into the PARENT story's namespace", RUN,
     'stem = args.out or ("nf_inj3b_injury_games_smoke" if args.smoke else "nf_inj3b_injury_games")',
     'stem = args.out or ("nf_inj3_injury_games_smoke" if args.smoke else "nf_inj3_injury_games")',
     "TestOutputDiscipline::test_every_output_stem_this_runner_can_write_is_an_nf_inj3b_path"),

    ("the scoring is RE-IMPLEMENTED instead of inherited (the pin becomes meaningless)", RUN,
     "    per_fold = [R3.score_fold(pop, y) for y in folds]",
     "    def score_fold(pop, y):\n        return R3.score_fold(pop, y)\n    per_fold = [score_fold(pop, y) for y in folds]",
     "TestOutputDiscipline::test_the_parent_harness_is_imported_not_reimplemented"),

    # ── the REGISTRATION document itself ──────────────────────────────────────────────────────
    ("the pre-registration quietly INHERITS the parent's 0.973 diagnostic", PREREG,
     "inherited and is not this study's expected value.",
     "carried forward as this study's expected value.",
     "TestPreRegistrationIsThePrimarySource::test_the_preregistration_refuses_to_inherit_the_parents_diagnostic"),

    ("the pre-registration drops the honesty clause", PREREG,
     "### ⚠️ HONESTY CLAUSE",
     "### Notes",
     "TestPreRegistrationIsThePrimarySource::test_the_preregistration_exists_and_carries_all_six_binding_items"),
]


def _restore(bak: Path, tgt: Path) -> None:
    if bak.exists():
        tgt.write_text(bak.read_text())
        bak.unlink()


def main() -> int:
    for f in (RUN, PREREG):                    # E11.26: restore a stale backup AT START-UP
        _restore(f.with_suffix(f.suffix + ".redbak"), f)
    red = skipped = 0
    for i, (name, target, old, new, test) in enumerate(BREAKS, 1):
        src = target.read_text()
        if src.count(old) != 1:                # E11.24: the anchor must be UNIQUE
            print(f"{i:2d}. ⚠️  SKIP (anchor not unique: {src.count(old)}×) — {name}")
            skipped += 1
            continue
        bak = target.with_suffix(target.suffix + ".redbak")
        bak.write_text(src)
        try:
            target.write_text(src.replace(old, new, 1))
            after = target.read_text()
            assert after != src, "#682: the mutation did not LAND"
            assert old not in after, "#815: the mutation landed but the token survived"
            r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{test}", "-q",
                                "--no-header", "-p", "no:cacheprovider"],
                               cwd=ROOT, capture_output=True, text=True)
            ok = r.returncode != 0
            red += ok
            print(f"{i:2d}. {'✅ RED' if ok else '❌ STAYED GREEN'} — {name}")
            if not ok:
                print("     ⚠️ VACUOUS GUARD:", r.stdout.strip().splitlines()[-1:])
        finally:
            _restore(bak, target)
    print(f"\n{red}/{len(BREAKS)} breaks went RED ({skipped} skipped)")
    return 0 if red == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
