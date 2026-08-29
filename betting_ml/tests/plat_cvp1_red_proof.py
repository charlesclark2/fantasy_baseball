"""RED proof for PLAT-CVP1's guards — `uv run python betting_ml/tests/plat_cvp1_red_proof.py`.

Each of the four defects is proved by re-introducing it in the SHARED instrument and requiring the
named guards to go RED. The spec's requirement is two-sided and this file is the second half: the
positive suite already shows each defect's HISTORICAL case now classifies correctly; this shows a
deliberate regression to the pre-fix behaviour turns those same clauses red.

⭐ **AND IT SWEEPS THE RE-ANCHORED PINS TOO.** `cv_power` is a cross-vertical instrument, so a break
here must be caught by whatever suite OWNS the property — MH2.7's state table, VAL1's consumer-side
clause, E7.9's two-sided absence clause — not only by this story's own file. A break that is red in
its own suite and green in the suite that has pinned the behaviour for a year is a re-anchor that
quietly narrowed.

Harness contract (the accumulated rules, because a red proof has at least four ways to lie):

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
  * every file is restored in a `finally`, and any stale backup is restored at START-UP, because
    this harness's own worst case is being killed mid-mutation (E11.26).

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~35 s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_C = "betting_ml/utils/cv_power.py"

OWN = "betting_ml/tests/test_plat_cvp1_classify_null_hardening.py"
MH27 = "betting_ml/tests/test_mh2_7_classify_null_field_safety.py"
VAL1 = "betting_ml/tests/test_ncaaf_val1_clv_week_strat.py"
E79 = "betting_ml/tests/test_mh2_1_wide_window_retrain.py"
CVP = "betting_ml/tests/test_cv_power.py"

#: (name, test file, old, new, pytest -k selector, token that must be GONE after the mutation)
BREAKS: list[tuple[str, str, str, str, str, str | None]] = [
    # ── DEFECT 1 (NCAAF-VAL1): the interval is consulted before absence is claimed ───────────────
    ("d1: absence short-circuits before the interval again (VAL1's over-claim)", OWN,
     "        if meaningful_sd_units is None:\n", "        if True:\n",
     "val1_bucket or absence_evidence or absence_certified_by_nothing",
     "if meaningful_sd_units is None:"),
    ("d1: a spanning interval is read as decisive (the wrong side of the bar)", OWN,
     "            if ub < bar:\n", "            if ub <= bar * 10:\n",
     "val1_bucket or absence_evidence", "if ub < bar:"),
    ("d1: an uncertified absence is badged do-not-re-test (no interval, MDE short)", OWN,
     "        if mde_sd_units is not None and float(mde_sd_units) <= bar:\n",
     "        if True:\n",
     "absence_certified_by_nothing or absence_evidence",
     "if mde_sd_units is not None and float(mde_sd_units) <= bar:"),
    # the SAME break, caught by the consumer suites that own the property
    ("d1: …and VAL1's own consumer suite catches it", VAL1,
     "        if meaningful_sd_units is None:\n", "        if True:\n",
     "no_longer_over_claims_absence", "if meaningful_sd_units is None:"),
    ("d1: …and E7.9's two-sided absence clause catches it", E79,
     "        if mde_sd_units is not None and float(mde_sd_units) <= bar:\n",
     "        if True:\n",
     "names_which_of_the_states", "if mde_sd_units is not None and float(mde_sd_units) <= bar:"),

    # ── DEFECT 2 (NCAAF-VAL3): a deflation gate evaluated and failed ─────────────────────────────
    ("d2: the PBO branch is silenced (VAL3's unnameable refusal returns)", OWN,
     "    if pbo is not None:\n", "    if False:\n",
     "pbo or deflation", "if pbo is not None:"),
    # ⭐ the faithful regression is the PRE-FIX STRUCTURE — the DSR block returning its fold
    # shortfall immediately, so nothing downstream can preempt it. (An earlier cut broke the
    # RELEASE instead, which is not the defect: with a FAILING pbo the release is never reached, so
    # that break could not bite and reported a false vacuity.)
    ("d2: the DSR fold shortfall returns early again, so a PBO refusal cannot preempt it", OWN,
     '            pending = NullVerdict("POWER_LIMITED", (',
     '            return NullVerdict("POWER_LIMITED", (',
     "preempts_the_dsr_fold_shortfall", 'pending = NullVerdict("POWER_LIMITED", ('),
    ("d2: the refusal publishes a fold trigger (the misleading direction)", OWN,
     '                    retest_trigger=None, folds_have=int(n_folds),\n'
     '                    pbo_application_admissible=d["pbo_application_admissible"],',
     '                    retest_trigger="+2 folds", folds_have=int(n_folds),\n'
     '                    pbo_application_admissible=d["pbo_application_admissible"],',
     "names_the_gate_that_bound or preempts_the_dsr_fold_shortfall", None),
    ("d2: DSR_UNREACHABLE loses precedence to a PBO refusal", OWN,
     "        if need is None:\n", "        if need is None and pbo is None:\n",
     "dsr_unreachable_still_outranks", None),
    ("d2: an unstated application is assumed clean rather than hedged", OWN,
     '                d["pbo_application_admissible"] = pbo_admissible = (\n'
     '                    True if pbo_application == "field" else None)',
     '                d["pbo_application_admissible"] = pbo_admissible = True',
     "unstated_pbo_application_is_hedged", None),
    ("d2: the new state is dropped from the enumeration", MH27,
     '    "DEFLATION_REFUSED",  # a pre-registered deflation gate was EVALUATED and FAILED — no n moves it\n',
     "", "every_state_is_covered_by_the_table", '"DEFLATION_REFUSED",  #'),

    # ── DEFECT 3 (NF-W8-0d R2): the lockstep is COMPUTED ─────────────────────────────────────────
    ("d3: the computed lockstep is ignored (the void lever is prescribed again)", OWN,
     "        if lockstep is not None and lockstep.closed:\n", "        if False:\n",
     "void_lever or lockstep", "if lockstep is not None and lockstep.closed:"),
    ("d3: the lockstep is never computed at all (every call returns 'not evaluated')", OWN,
     "    if observed_sr is None or var_trials_sr is None or int(n_trials) < 1:\n",
     "    if True:\n",
     "void_lever or lockstep", "if observed_sr is None or var_trials_sr is None"),
    ("d3: the dispersion exponent is wrong (variance scales by 1/c, not 1/c²)", OWN,
     "        row_sr, row_v = sr / c, float(var_trials_sr) / (c * c)",
     "        row_sr, row_v = sr / c, float(var_trials_sr) / c",
     "reproduces_nf_w8_0ds_recorded_arithmetic", "/ (c * c)"),
    ("d3: the lever is declared closed unconditionally (the OPEN half is lost)", OWN,
     "        closed=bool(gap <= 0.0),", "        closed=True,",
     "two_sided_a_positive_gap or open_lockstep_branch", "closed=bool(gap <= 0.0)"),
    ("d3: an unevaluable lockstep reports OPEN rather than None", OWN,
     "        return LockstepReport(closed=None)", "        return LockstepReport(closed=False)",
     "unevaluable_lockstep", "LockstepReport(closed=None)"),
    # ⛔ NOT A SWEEP ROW, and the omission is deliberate. MH2.7's `k_pct` clause asserts
    # "NOT a lever" — a property about the FIELD half of the sentence, which the new closed-lockstep
    # text also satisfies, so that clause is INSENSITIVE to the open/closed distinction. It was never
    # asked to own it. Adding the assertion there would make an older story's guard fail for a newer
    # story's reason (the E9.60 coupling anti-pattern), so the open-branch property is owned by
    # `test_the_open_lockstep_branch_keeps_naming_the_lever_that_is_still_live` in THIS story's
    # suite, which the "declared closed unconditionally" break above turns red.
    ("d3: …and MH2.7's post-hoc-field clause still owns ITS property after the re-anchor", MH27,
     "    if int(max_field) >= declared:\n", "    if True:\n",
     "no_longer_prescribes_the_retired_post_hoc_field", "if int(max_field) >= declared:"),

    # ── DEFECT 4 (MLB-HV2-1): field-level vs per-arm, and the control as a callable ──────────────
    ("d4: a per-arm-applied PBO is admitted as a refusal (HV2-1's veto returns)", OWN,
     '            if pbo_application == "per_arm":\n', "            if False:\n",
     "per_arm_applied_pbo_refusal", 'if pbo_application == "per_arm":'),
    ("d4: DSR is treated as a field-level statistic (the detector cries wolf)", OWN,
     '_FIELD_LEVEL_STATISTICS = frozenset({"pbo", "cscv"})',
     '_FIELD_LEVEL_STATISTICS = frozenset({"pbo", "cscv", "dsr"})',
     "field_level_statistic_carried_as_a_per_arm_gate", '{"pbo", "cscv"})'),
    ("d4: the control cannot report DEFLATION_BLOCKED (it collapses to BLIND)", OWN,
     "    deflation_blocked = tuple(a for a in metric_survivors if blocking[a])",
     "    deflation_blocked = ()",
     "reproduces_hv2_1s_recorded_verdict", "for a in metric_survivors if blocking[a]"),
    ("d4: the control's NO-EFFECT leg is dropped (a family that certifies noise passes)", OWN,
     "    if null_survivors:\n", "    if False:\n",
     "certifies_the_NO_EFFECT_payload", "if null_survivors:"),
    ("d4: an empty gate table is accepted (every clause becomes vacuously true)", OWN,
     '        if not isinstance(got, dict) or not got:\n', "        if False:\n",
     "refuses_a_vacuous_configuration", "if not isinstance(got, dict) or not got:"),
    ("d4: a zero-effect 'injection' is accepted as a positive control", OWN,
     "    if float(effect) == 0.0:\n", "    if False:\n",
     "refuses_a_vacuous_configuration", "if float(effect) == 0.0:"),

    # ── the instrument's standing contract, which none of the four may break ─────────────────────
    ("contract: back-compat — a caller with no bar stops getting the old absence", CVP,
     "        if meaningful_sd_units is None:\n", "        if False:\n",
     "GENUINE_ABSENCE_with_no_trigger", "if meaningful_sd_units is None:"),
    # ⚠️ `NF-W8-0d` and `MLB-HV2-1` each appear TWICE in the module docstring, so breaking one
    # mention leaves the citation present and the row reports a false vacuity. `NCAAF-VAL3` appears
    # once — and `gone` is set, so a surviving token is reported as a BROKEN harness rather than
    # silently read as a caught break (#815). ⚠️ `gone` is FILE-scoped while the guard reads the
    # DOCSTRING, and a bare `NCAAF-VAL3` also appears in a code comment further down — so the token
    # is the docstring-scoped bullet, not the citation alone. A coarser token reported a false
    # BROKEN here, which is the #815 check earning its place rather than failing.
    ("contract: the docstring stops citing one of the four incident records", OWN,
     "  2. **NCAAF-VAL3**", "  2. **A study**",
     "cites_all_four_incident_records", "  2. **NCAAF-VAL3**"),
]


def main() -> int:
    failures: list[str] = []
    # E11.26 — this harness's own worst case is being killed mid-mutation, so restore first.
    for stale in REPO.glob("**/*.plat_cvp1_red_proof.bak"):
        target = stale.with_suffix("")
        target.write_text(stale.read_text())
        stale.unlink()
        print(f"restored a stale backup: {target}")

    for name, test, old, new, selector, gone in BREAKS:
        path = REPO / _C
        original = path.read_text()

        occurrences = original.count(old)
        if occurrences != 1:
            print(f"{'BROKEN ❌ (anchor ×%d)' % occurrences:32} {name}")
            failures.append(f"{name}: anchor appears {occurrences}× in {_C} — must be unique")
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

        backup = path.with_suffix(path.suffix + ".plat_cvp1_red_proof.bak")
        backup.write_text(original)
        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-p", "no:randomly", "-o", "addopts="],
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
            print(f"{verdict:32} {name}\n{'':32} -> {test.rsplit('/', 1)[-1]}: {tail}")
        finally:
            path.write_text(original)
            backup.unlink(missing_ok=True)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every PLAT-CVP1 guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
