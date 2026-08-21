"""nf_d22_red_proof.py — prove every NF-D22 guard can actually FAIL (⛔ NOT a pytest module).

A guard that cannot go red is not a guard (NF1.7 (a); INC-38; NF-D17). This harness applies ONE
deliberate break to the source at a time, runs the clause that names it, and reports whether that
clause turned red. A clause that stays GREEN on its own break is VACUOUS and must be rewritten.

⚠️ FOUR WAYS A RED PROOF LIES, all of them recorded in this repo and all guarded against here:
  1. **THE MUTATION NEVER LANDS** (#682) — a shell-quoting or match failure leaves the source
     unchanged and "the guard caught it" is indistinguishable from "the break never happened". ⇒ the
     mutation is applied IN-PROCESS and the file is asserted to have CHANGED.
  2. **THE ANCHOR IS NOT UNIQUE** (#939) — two functions with byte-identical tails make a
     single-occurrence replace land on the WRONG one, and the run reports a FALSE VACUITY, which is
     the dangerous direction because it invites weakening a correct guard. ⇒ every anchor is asserted
     to occur EXACTLY ONCE.
  3. **THE MUTATION LANDS BUT DOES NOT MOVE THE ASSERTED PREDICATE** (#815) — e.g. a suffix rename
     that an `x in src` clause still matches. ⇒ each break states the token it removes and the
     harness asserts that token is GONE afterwards.
  4. **THE PROOF LIVES IN NO WORKFLOW** (E9.64) — a mutation suite nobody runs decays silently. ⇒ it
     is a plain script the closeout runs and whose RED count is recorded in the story report.

⚠️ AND THE FAILURE MODE OF THIS FILE ITSELF: it mutates tracked source, so its worst case is being
killed mid-mutation. Backups are restored AT START-UP as well as in `finally`, and it runs under the
PROJECT interpreter (a bare `python3` with no pytest would make a missing-pytest exit read as a false
RED — NF-INFRA1).

    uv run python betting_ml/tests/nf_d22_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CPF = ROOT / "betting_ml/utils/coverage_power_floor.py"
RV = ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_interval_revalidation.py"
D22 = ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_nf_d22_power_floor.py"
GATES = ROOT / "betting_ml/governance/gates.py"
NF18 = ROOT / "quant_sports_intel_models/football/nfl/fantasy/run_rookie_perposition_ablation.py"
TESTS = "betting_ml/tests/test_nf_d22_power_floor.py"


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    #: the substring that must be GONE after the mutation — defeats lie #3 (a break that lands but
    #: does not move the predicate the clause asserts on)
    gone: str
    tests: tuple[str, ...]


BREAKS: tuple[Break, ...] = (
    Break("the floor reads the observed coverage (E2.1-r, the cardinal error)",
          CPF,
          "def power_floor(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET) -> float:",
          "def power_floor(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET,\n"
          "                coverage: float | None = None) -> float:",
          gone="def power_floor(n: int, *, nominal: float, target: float = FALSE_REJECT_TARGET) "
               "-> float:",
          tests=("test_the_floor_function_has_no_coverage_argument_and_must_never_gain_one",)),

    Break("the target is quietly loosened away from NF1.8's level",
          CPF, "FALSE_REJECT_TARGET: float = 0.05", "FALSE_REJECT_TARGET: float = 0.20",
          gone="FALSE_REJECT_TARGET: float = 0.05",
          tests=("test_the_target_is_nf1_8s_own_pre_registered_level",)),

    Break("the derivation cites the measurement that refused NF-D21",
          CPF, "#: The rule's identity, stamped",
          "#: (the RB coverage that refused NF-D21 was 0.7905)\n#: The rule's identity, stamped",
          gone="",  # an ADD, not a removal — checked by the file-changed assertion alone
          tests=("test_the_derivation_never_mentions_the_measurement_that_refused_nf_d21",)),

    Break("the floor is TIGHTENED above nominal 'for safety' (NF1.8 §1)",
          CPF,
          "    return float(min(nominal, required_covered_rows(n, nominal=nominal, "
          "target=target) / int(n)))",
          "    return float(nominal + 0.01)",
          gone="min(nominal, required_covered_rows(n, nominal=nominal, target=target) / int(n))",
          tests=("test_the_floor_is_never_above_nominal",
                 "test_a_truly_nominal_band_clears_the_new_floor_at_the_pre_registered_rate")),

    # ⚠️ THE MUTATION MUST LAND AFTER THE CORRECTION WALKS. The first attempt here perturbed the
    #    Binomial quantile SEED (`k = ppf(...) - n//3`) and the guard stayed GREEN — not because the
    #    guard is vacuous but because `required_covered_rows` walks the seed back to the boundary,
    #    i.e. the function is robust to exactly that perturbation. That is #815's lie (a break that
    #    lands without moving the asserted predicate) and it is why the break now targets the RETURN.
    Break("the floor is dropped to a level a broken band survives (half B)",
          CPF, "    return int(k)", "    return max(0, int(k) - n // 3)",
          gone="    return int(k)\n",
          tests=("test_a_materially_short_band_still_fails_the_new_floor",
                 "test_a_catastrophically_short_band_is_refused_almost_always",
                 "test_the_floor_matches_an_independent_reimplementation_of_its_own_contract")),

    Break("multiplicity is 'corrected for', loosening every individual floor",
          CPF,
          "        floors[str(g)] = group_floor(n_i, nominal=nominal, target=target,\n"
          "                                     coverage=cov.get(g))",
          "        floors[str(g)] = group_floor(n_i, nominal=nominal,\n"
          "                                     target=target / max(1, len(n_by_group)),\n"
          "                                     coverage=cov.get(g))",
          gone="group_floor(n_i, nominal=nominal, target=target,",
          tests=("test_a_groups_floor_does_not_depend_on_how_many_other_groups_are_in_the_family",)),

    Break("an unreadable coverage is silently scored as met (NF1.7 (a))",
          CPF, "        if g in cov and cov[g] is None:\n            blind.append(str(g))\n", "",
          gone="            blind.append(str(g))",
          tests=("test_a_group_whose_coverage_could_not_be_read_is_not_scored_as_met",)),

    Break("the §0.5 SELECTION floor is relaxed too (re-deciding recorded searches)",
          NF18, "            floors[p] = nominal", "            floors[p] = nominal - 0.05",
          gone="            floors[p] = nominal\n",
          tests=("test_the_bakeoff_selection_floor_is_still_the_hard_nominal_one",)),

    Break("the re-validation stops carrying the PREVIOUS reading (an unauditable floor change)",
          RV,
          '        "floors_at_nominal": nominal_floors,',
          '        "floors_at_nominal": {},',
          gone='"floors_at_nominal": nominal_floors,',
          tests=("test_the_revalidation_block_carries_BOTH_readings_so_a_floor_change_is_auditable",)),

    Break("the gate stops surfacing which floor rule produced the verdict",
          GATES,
          '    return _ok(name, f"all per-group coverage floors met after the change '
          '(floor rule: {rule})",\n               floor_rule=rule)',
          '    return _ok(name, "all per-group coverage floors met after the change")',
          gone='(floor rule: {rule})"',
          tests=("test_the_gate_surfaces_the_floor_rule_but_stays_ADDITIVE_for_older_reports",)),

    Break("§3 is computed BEFORE the two-sided validation passes (the inversion)",
          D22,
          '    if not two_sided["pass"]:',
          '    if False and not two_sided["pass"]:',
          gone='    if not two_sided["pass"]:\n',
          tests=("test_section_3_is_not_computed_unless_the_two_sided_validation_passes",)),

    Break("the runner writes a DECIDED story's artifact path",
          D22,
          '_OUT_JSON = _REPORT_DIR / "nf_d22_power_floor.json"',
          '_OUT_JSON = _REPORT_DIR / "nf_g0_d21_governance_publish.json"',
          gone='_OUT_JSON = _REPORT_DIR / "nf_d22_power_floor.json"',
          tests=("test_the_runner_writes_only_its_own_paths_and_never_a_decided_storys",)),

    Break("the runner flips the serving switch on a CLOSED story",
          D22, "    design = design_table()",
          "    RP.SERVING_ENABLED = True\n    design = design_table()",
          gone="",
          tests=("test_the_runner_does_not_flip_a_serving_switch",)),
)


def _restore_stale_backups() -> None:
    """⚠️ RUN AT START-UP, not only in `finally`. This harness mutates TRACKED source; if a previous
    invocation was killed mid-mutation the working tree is left broken, and the next run would then
    measure a source nobody wrote."""
    for bak in {p.with_suffix(p.suffix + ".redproof")
            for p in (CPF, RV, D22, GATES, NF18)}:
        if bak.exists():
            bak.replace(bak.with_suffix(""))
            print(f"  ⚠️ restored a stale backup: {bak.name}")


def _run(node: str) -> bool:
    """True when the clause turned RED."""
    r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{node}", "-q", "-p", "no:randomly",
                        "--no-header", "-x"], cwd=ROOT, capture_output=True, text=True)
    return r.returncode != 0


def main() -> int:
    _restore_stale_backups()
    results, vacuous = [], []
    for b in BREAKS:
        src = b.path.read_text()
        n_hits = src.count(b.old)
        if n_hits != 1:
            print(f"🚨 ANCHOR NOT UNIQUE ({n_hits} hit(s)) — {b.name}")
            vacuous.append((b.name, "anchor not unique"))
            continue
        bak = b.path.with_suffix(b.path.suffix + ".redproof")
        bak.write_text(src)
        try:
            b.path.write_text(src.replace(b.old, b.new, 1))
            after = b.path.read_text()
            # lie #1 — the mutation never landed; lie #3 — it landed without moving the predicate
            if after == src:
                print(f"🚨 MUTATION DID NOT LAND — {b.name}")
                vacuous.append((b.name, "mutation did not land"))
                continue
            if b.gone and b.gone in after:
                print(f"🚨 MUTATION LANDED BUT LEFT {b.gone!r} — {b.name}")
                vacuous.append((b.name, "mutation did not move the asserted predicate"))
                continue
            reds = [t for t in b.tests if _run(t)]
            greens = [t for t in b.tests if t not in reds]
            results.append((b.name, reds, greens))
            mark = "✅ RED" if reds else "🚨 VACUOUS"
            print(f"{mark:>12}  {b.name}")
            for t in greens:
                print(f"              …green on its own break: {t}")
            if not reds:
                vacuous.append((b.name, "no clause turned red"))
        finally:
            b.path.write_text(bak.read_text())
            bak.unlink()
    print(f"\n{len(results) - len(vacuous)}/{len(BREAKS)} breaks turned a guard RED")
    if vacuous:
        print("\n🚨 VACUOUS GUARDS — a guard that cannot fail is not a guard:")
        for n, why in vacuous:
            print(f"   · {n}  ({why})")
        return 1
    print("✅ every deliberate break turned its own clause red")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
