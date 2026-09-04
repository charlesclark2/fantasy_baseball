"""RED proof for PLAT-CVP2's guards — `uv run python betting_ml/tests/plat_cvp2_red_proof.py`.

Each of the four defects is proved by RE-INTRODUCING it in the shared instrument and requiring the
named clause to go RED. The spec's requirement is two-sided and this file is the second half: the
positive suite shows each defect's HISTORICAL case now classifies correctly; this shows a deliberate
regression to the pre-fix behaviour turns those same clauses red.

⭐ **AND IT SWEEPS THE RE-ANCHORED PINS, NOT ONLY THIS STORY'S FILE.** `cv_power` is a cross-vertical
instrument and `nf_inj2_rate_permutation` is a two-vertical one, so a break must be caught by
whatever suite OWNS the property — NF-INJ2c's prereg tripwire, its coherence diagnosis, the CVP1
hardening suite. A break that is red in its own suite and green in the suite that has pinned the
behaviour is a re-anchor that quietly narrowed (PLAT-CVP1 finding 1).

Harness contract — the accumulated rules, because a RED proof has at least six ways to lie:

  * ⭐ **BASELINE-PASS**, first, before anything is patched: a clause that is ALREADY FAILING would
    be reported RED by every break. Measured (`nf_rate1_red_proof`).
  * ⭐ **NOT-SELECTED** is a third outcome, not a red: a stale or mistyped selector makes pytest run
    nothing and exit NON-ZERO, which a naive `rc != 0` reads as "the clause went red" — the harness
    reporting its strongest result for a clause it never ran (`nf_rate1_red_proof`, measured there).
  * the mutation anchor must be **UNIQUE** in the file — a `replace(old, new, 1)` against a
    non-unique anchor lands on the WRONG symbol and reports a FALSE vacuity, which is the dangerous
    direction because it invites weakening a correct guard (E11.24 prediction_log);
  * the mutation must be asserted to have **LANDED** — a silently no-op'd break reads as "caught"
    (E11.24 #682);
  * where the clause asserts on a TOKEN, that token must be asserted **GONE** after the mutation —
    a break that lands but leaves the assertion satisfied is a false GREEN (E11.24 #815);
  * pytest runs in a **SUBPROCESS**, so `pytest.raises`' `Failed` (a `BaseException`) cannot leak
    past a too-narrow `except` and be read as a pass (NF-W6c);
  * ⚠️ only exit code 1 counts as RED. 2/3/4/5 is a BROKEN harness, never a caught break (NF-INFRA1);
  * every file is restored in a `finally`, and any stale backup is restored at START-UP, because
    this harness's own worst case is being killed mid-mutation (E11.26).

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~60 s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

CV = "betting_ml/utils/cv_power.py"
RP = "quant_sports_intel_models/football/nfl/fantasy/nf_inj2_rate_permutation.py"

OWN = "betting_ml/tests/test_plat_cvp2_instrument_hardening.py"
INJ2C_PRE = "betting_ml/tests/test_nf_inj2c_preregistration.py"
INJ2C_DIAG = "betting_ml/tests/test_nf_inj2c_coherence_diagnosis.py"
INJ2_RP = "betting_ml/tests/test_nf_inj2_rate_permutation.py"
CVP1 = "betting_ml/tests/test_plat_cvp1_classify_null_hardening.py"

#: (name, source file to break, old, new, suite to run, `-k` selector, token that must be GONE)
BREAKS: list[tuple[str, str, str, str, str, str, str | None]] = [
    # ── DEFECT 1 (NF-INJ2b D2): CONSTRAINT_BLOCKED, and BLIND kept for movable gates ─────────────
    ("d1: the constraint state is unreachable again (it collapses back to BLIND)", CV,
     "    constraint_blocked = tuple(a for a in metric_survivors\n"
     "                               if blocking[a] and set(blocking[a]) <= inv)",
     "    constraint_blocked = ()",
     OWN, "defect1", "if blocking[a] and set(blocking[a]) <= inv"),
    ("d1: an invariant gate is filed as a metric gate again (the pre-fix partition)", CV,
     '               for g in names}\n    # a vocabulary that names NOTHING',
     '               for g in names}\n    classes = {g: ("deflation" if g in defl else "metric") for g in names}\n'
     '    # a vocabulary that names NOTHING',
     OWN, "defect1", None),
    ("d1: `metric_survivors` counts invariant gates, so a constrained arm is not one", CV,
     '    metric_survivors = tuple(a for a, b in blocking.items() if not any(classes[g] == "metric"\n'
     '                                                                      for g in b))',
     "    metric_survivors = tuple(a for a, b in blocking.items()\n"
     "                             if not any(g not in defl for g in b))",
     OWN, "defect1", 'blocking.items() if not any(classes[g] == "metric"'),
    ("d1: the declared invariant set is silently dropped", CV,
     '    inv = frozenset(str(g) for g in (invariant_gates or ()))',
     "    inv = frozenset()",
     OWN, "defect1", "for g in (invariant_gates or ())"),
    ("d1: BLIND stops saying which half failed to fire (the reader is back to guessing)", CV,
     '            + (f" ⚠️ {len(inv_names)} gate(s) are DECLARED injection-invariant "\n'
     '               f"(`{\'`, `\'.join(inv_names)}`) and were excluded from that reading, so BLIND here "\n'
     '               f"means the MOVABLE half genuinely failed to fire." if inv_names else ""))',
     '            + "")',
     OWN, "BLIND_keeps_its_meaning", "were excluded from that reading"),
    # …and the suite that OWNS the NF-INJ2c consumption of it
    ("d1: …and NF-INJ2c's prereg tripwire catches the unreachable state", CV,
     "    constraint_blocked = tuple(a for a in metric_survivors\n"
     "                               if blocking[a] and set(blocking[a]) <= inv)",
     "    constraint_blocked = ()",
     INJ2C_PRE, "plat_cvp2_status_claim", "if blocking[a] and set(blocking[a]) <= inv"),

    # ── DEFECT 2 (MLB-TV2-2 §17): the zero-intersection inversion ────────────────────────────────
    ("d2: a zero-overlap partition returns a substantive verdict again (the inversion)", CV,
     "    return classes, source, overlap",
     "    return classes, source, True",
     OWN, "defect2", "return classes, source, overlap"),
    ("d2: the UNVERIFIED branch is skipped, so BLIND is returned from an unclassified field", CV,
     "    elif not partition_ok:",
     "    elif False:",
     OWN, "defect2", "elif not partition_ok:"),
    ("d2: the refusal stops naming the input that fixes it", CV,
     'f"`gate_classes={{gate: \\"metric\\"|\\"deflation\\"|\\"invariant\\"}}` covering every gate "',
     'f"a different partition covering every gate "',
     OWN, "tells_the_caller_how_to_declare", "gate_classes={{gate:"),
    ("d2: a PARTIAL gate-class declaration is completed by the heuristic instead of refused", CV,
     "        missing = sorted(set(names) - set(declared))\n        if missing:",
     "        missing = sorted(set(names) - set(declared))\n        if False:",
     OWN, "partially_declared", "if missing:"),
    ("d2: an unknown gate class is accepted", CV,
     "        if bad:\n            raise ValueError(",
     "        if False:\n            raise ValueError(",
     OWN, "partially_declared", None),
    ("d2: the name heuristic stops announcing itself", CV,
     "    if partition_source == _SRC_NAME_HEURISTIC and partition_ok and verdict != \"VACUOUS\":",
     "    if False:",
     OWN, "announces_itself", "partition_source == _SRC_NAME_HEURISTIC and partition_ok"),
    ("d2: a declared vocabulary is misreported as the heuristic (the announcement cries wolf)", CV,
     '    vocabulary_declared = deflation_gates is not None or invariant_gates is not None',
     "    vocabulary_declared = False",
     OWN, "announces_itself", "deflation_gates is not None or invariant_gates is not None"),
    ("d2: a partition-DEPENDENT verdict escapes an unverified partition", CV,
     "    elif not partition_ok:",
     "    elif not partition_ok and False:",
     OWN, "withheld_when_unverified", None),
    # …and the suite that OWNS the shipped-default property
    ("d2: …and NF-INJ2c's prereg catches the shipped deflation default moving", CV,
     'DEFLATION_CLASS_GATES = frozenset({"pbo", "cscv", "dsr", "deflated_sharpe"})',
     'DEFLATION_CLASS_GATES = frozenset({"pbo", "cscv", "dsr"})',
     INJ2C_PRE, "deflation_gate_partition", '"deflated_sharpe"})'),
    # …and CVP1's own control guards, which must still own their properties after the re-anchor
    ("d2: …and PLAT-CVP1's HV2-1 control guard catches a broken deflation partition", CV,
     "    defl = frozenset(g for g, c in classes.items() if c == \"deflation\")",
     "    defl = frozenset()",
     CVP1, "reproduces_hv2_1s_recorded_verdict or field_level_statistic", None),

    # ── DEFECT 3 (MLB-TV2-2 §14.1 / E7.14): the unpassable multiplicity clause ───────────────────
    ("d3: an unpassable gate set is no longer refused", CV,
     "    if strict and not ok:\n        raise ValueError(why)",
     "    if False:\n        raise ValueError(why)",
     OWN, "defect3", "if strict and not ok:"),
    ("d3: the refusal loses its arithmetic (a bar with no numbers is a wall)", CV,
     '             + (" x 2" if two_sided else "") + f" = {floor:.5f}, against a BH cutoff of "',
     '             + (" x 2" if two_sided else "") + f" = (redacted), against a BH cutoff of "',
     OWN, "refused_with_the_arithmetic", "{floor:.5f}, against a BH cutoff"),
    ("d3: the certifiability test is inverted (it refuses the certifiable designs)", CV,
     "    ok = bool(floor <= cut)",
     "    ok = bool(floor >= cut)",
     OWN, "defect3", "floor <= cut"),
    ("d3: it invents the bar it is checking against instead of refusing to", CV,
     "    if bh_cutoff is None and n_arms is None:\n        raise ValueError(",
     "    if False:\n        raise ValueError(",
     OWN, "invent_the_bar", "if bh_cutoff is None and n_arms is None:"),
    ("d3: the no-margin reading is dropped, so n=7 reads as comfortably certifiable", CV,
     '               + ("" if floor <= 0.5 * cut else',
     '               + ("" if True else',
     OWN, "reproduces_the_preregs_own_recorded_numbers", "if floor <= 0.5 * cut else"),

    # ── DEFECT 4 (NF-INJ2c §6.3): one floor predicate, one owner ─────────────────────────────────
    ("d4: the census requires isfinite again, so it cannot see a floored non-finite row", RP,
     "    return ~np.isfinite(g) | (g < GAMES_FLOOR)",
     "    return np.isfinite(g) & (g < GAMES_FLOOR)",
     OWN, "defect4", "~np.isfinite(g) | (g < GAMES_FLOOR)"),
    ("d4: the kernel re-implements its own predicate (the two can drift apart again)", RP,
     "    gsafe = np.where(games_floored_mask(g), GAMES_FLOOR, g)",
     "    gsafe = np.where(np.isfinite(g) & (g > GAMES_FLOOR), g, GAMES_FLOOR)",
     OWN, "no_second_floor_predicate", None),
    ("d4: the boundary row is counted by BRANCH not by VALUE (NF-INJ2c's choice, reversed)", RP,
     "    return ~np.isfinite(g) | (g < GAMES_FLOOR)",
     "    return ~np.isfinite(g) | (g <= GAMES_FLOOR)",
     OWN, "boundary_row_is_still_a_no_op", "(g < GAMES_FLOOR)"),
    # …and the suites that OWN the floor census
    ("d4: …and NF-INJ2c's coherence-diagnosis suite catches the split predicate", RP,
     "    return ~np.isfinite(g) | (g < GAMES_FLOOR)",
     "    return np.isfinite(g) & (g < GAMES_FLOOR)",
     INJ2C_DIAG, "non_finite_row or two_floor_columns", "~np.isfinite(g) | (g < GAMES_FLOOR)"),
    ("d4: …and NF-INJ2's own rate-permutation suite catches a broken binding count", RP,
     "    return ~np.isfinite(g) | (g < GAMES_FLOOR)",
     "    return ~np.isfinite(g) | (g > GAMES_FLOOR)",
     INJ2_RP, "games_floor or feasib or assign", "(g < GAMES_FLOOR)"),

    # ── the standing contract, which none of the four may break ──────────────────────────────────
    ("contract: back-compat — a new input stops being opt-in", CV,
     "        invariant_gates: Iterable[str] | None = None,",
     "        invariant_gates: Iterable[str] = (),",
     OWN, "keeps_its_behaviour_without_the_new_inputs",
     "invariant_gates: Iterable[str] | None = None,"),
    ("contract: the docstring stops citing one of the four incident records", CV,
     "      4. **NF-INJ2c §6.3**", "      4. **A study**",
     OWN, "cites_all_four_incident_records", "      4. **NF-INJ2c §6.3**"),
]


def _run(suite: str, selector: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED" | "BROKEN(rc)"."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", suite, "-q", "--no-header", "-k", selector,
         "-p", "no:cacheprovider", "-p", "no:randomly", "-o", "addopts="],
        cwd=REPO, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if "no tests ran" in out or "ERROR: not found" in out:
        return "NOT-SELECTED"
    if proc.returncode == 0:
        return "PASSED"
    if proc.returncode == 1:
        return "FAILED"
    return f"BROKEN(rc={proc.returncode})"


def main() -> int:
    # E11.26 — this harness's own worst case is being killed mid-mutation, so restore first.
    for stale in REPO.glob("**/*.plat_cvp2_red_proof.bak"):
        target = stale.with_suffix("")
        target.write_text(stale.read_text())
        stale.unlink()
        print(f"restored a stale backup: {target}")

    # ── BASELINE. A clause already failing would be reported RED by every break. ─────────────────
    print("baseline (every named clause must be GREEN on unbroken source):")
    baseline_bad: list[str] = []
    for suite, selector in sorted({(b[4], b[5]) for b in BREAKS}):
        outcome = _run(suite, selector)
        if outcome != "PASSED":
            baseline_bad.append(f"{suite} -k {selector!r} -> {outcome}")
            print(f"  🚨 {suite.rsplit('/', 1)[-1]} -k {selector!r} -> {outcome}")
    if baseline_bad:
        print("\n🚨 A break cannot prove anything about a clause that is not green to begin with.")
        for b in baseline_bad:
            print(f"  - {b}")
        return 1
    print(f"  ✅ all {len({(b[4], b[5]) for b in BREAKS})} (suite, selector) pairs green\n")

    failures: list[str] = []
    for name, srcfile, old, new, suite, selector, gone in BREAKS:
        path = REPO / srcfile
        original = path.read_text()

        occurrences = original.count(old)
        if occurrences != 1:                        # unique anchor (E11.24 prediction_log)
            print(f"{'BROKEN ❌ (anchor x%d)' % occurrences:34} {name}")
            failures.append(f"{name}: anchor appears {occurrences}x in {srcfile} — must be unique")
            continue
        mutated = original.replace(old, new, 1)
        if mutated == original:                     # the break must LAND (#682)
            print(f"{'BROKEN ❌ (mutation no-op)':34} {name}")
            failures.append(f"{name}: mutation did not change the file")
            continue
        if gone is not None and gone in mutated:    # the asserted token must be GONE (#815)
            print(f"{'BROKEN ❌ (token survives)':34} {name} -> {gone!r} still present")
            failures.append(f"{name}: asserted token survived the mutation")
            continue

        backup = path.with_suffix(path.suffix + ".plat_cvp2_red_proof.bak")
        backup.write_text(original)
        path.write_text(mutated)
        try:
            outcome = _run(suite, selector)
        finally:
            path.write_text(original)
            backup.unlink(missing_ok=True)

        if outcome == "FAILED":
            verdict = "RED ✅"
        elif outcome == "PASSED":
            verdict = "GREEN ❌ (VACUOUS GUARD)"
            failures.append(name)
        elif outcome == "NOT-SELECTED":
            verdict = "BROKEN ❌ (selector ran nothing)"
            failures.append(f"{name}: -k {selector!r} selected no test in {suite}")
        else:
            verdict = f"BROKEN ❌ ({outcome})"
            failures.append(f"{name}: {outcome}")
        print(f"{verdict:34} {name}\n{'':34} -> {suite.rsplit('/', 1)[-1]} -k {selector!r}")

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every PLAT-CVP2 guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
