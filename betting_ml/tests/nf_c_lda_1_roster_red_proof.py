"""RED proof for the NF-C-LDA-1 roster-accounting guards —
`uv run python betting_ml/tests/nf_c_lda_1_roster_red_proof.py`.

Each claim in `test_nf_c_lda_1_roster_constraints.py` is proved by RE-INTRODUCING the defect a live
2026 ESPN mock draft surfaced and requiring the named test to go RED. Same harness contract as
`nf_k1_red_proof.py`:

  * the mutation is applied to the SOURCE FILE and asserted to have LANDED (E11.24 #682);
  * where a guard asserts on a TOKEN, that token is asserted GONE afterwards (E11.24 #815);
  * ⭐ and the anchor is asserted UNIQUE in the file before it is used — `draft.py` and
    `draft-optimizer.ts` are deliberate line-by-line mirrors, so a `replace(old, new, 1)` can
    silently land on the WRONG occurrence and report a false "the guard is vacuous" (E11.24
    prediction_log, the third way a red proof lies);
  * pytest runs in a SUBPROCESS so `pytest.raises`' `Failed` cannot leak past a narrow `except`
    (NF-W6c);
  * ⚠️ ONLY exit code 1 (tests FAILED) counts as RED — 2/3/4/5 is a BROKEN HARNESS (NF-INFRA1);
  * the file is restored in a `finally`.

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~10s.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_c_lda_1_roster_constraints.py"
_CFG = "quant_sports_intel_models/fantasy_engine/league_config.py"
_DRAFT = "quant_sports_intel_models/fantasy_engine/draft.py"
_ESPN = "app/backend/services/platform_import/espn.py"
_TS = "frontend/lib/draft-optimizer.ts"
_MOCK = "frontend/lib/mock-draft.ts"

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS = [
    # ── 1. an IR spot is not a pick ─────────────────────────────────────────────────────────────
    ("draftable count: go back to counting EVERY slot (the live defect)", _DRAFT,
     "    total_slots = draftable_slot_count(config.roster)",
     "    total_slots = sum(s.count for s in config.roster)",
     "fires_in_time or stays_inert", "draftable_slot_count(config.roster)"),
    ("RESERVE_SLOT_NAMES: drop IR, so an ESPN league counts it as draftable", _CFG,
     'RESERVE_SLOT_NAMES = frozenset({"IR", "TAXI"})',
     'RESERVE_SLOT_NAMES = frozenset({"TAXI"})',
     "reserve_slots_are_excluded or every_adapter_emits or fires_in_time", '"IR"'),
    ("RESERVE_SLOT_NAMES: drop TAXI, so a Sleeper dynasty roster over-counts", _CFG,
     'RESERVE_SLOT_NAMES = frozenset({"IR", "TAXI"})',
     'RESERVE_SLOT_NAMES = frozenset({"IR"})',
     "every_adapter_emits", '"TAXI"'),
    ("draftable count: exclude the BENCH too (over-eager — fires the constraint EARLY)", _CFG,
     "    return sum(s.count for s in roster if s.name.upper() not in RESERVE_SLOT_NAMES)",
     "    return sum(s.count for s in roster if not s.bench)",
     "reserve_slots_are_excluded or unknown_slot_stays_draftable or stays_inert", None),
    ("draftable count: treat an UNKNOWN bench slot as reserve (under-counts)", _CFG,
     "    return sum(s.count for s in roster if s.name.upper() not in RESERVE_SLOT_NAMES)",
     "    return sum(s.count for s in roster if not (s.bench and s.name.upper() != 'BN'))",
     "unknown_slot_stays_draftable", None),
    ("ESPN adapter: map IR to a name the rule does not recognise", _ESPN,
     '    21: ("IR", (), True),',
     '    21: ("RESERVE", (), True),',
     "every_adapter_emits", '21: ("IR", (), True),'),

    # ── 2. a filled flex seat is not capacity ───────────────────────────────────────────────────
    ("surplus penalty: restore the held>=capacity binary (the 3.3x backup-TE boost)", _DRAFT,
     "        surplus_pen = 0.0\n"
     "        if level == 0 and vor > 0:\n"
     "            surplus_pen = min(SURPLUS_CAP, SURPLUS_BASE + SURPLUS_OVER) * vor",
     "        held = len([1 for p in my_positions if p == pos])\n"
     "        capacity = req.dedicated.get(pos, 0) + sum(n for elig, n in req.flex if pos in elig)\n"
     "        surplus_pen = 0.0\n"
     "        if level == 0 and vor > 0:\n"
     "            frac = SURPLUS_BASE + (SURPLUS_OVER if held >= capacity else 0.0)\n"
     "            surplus_pen = min(SURPLUS_CAP, frac) * vor",
     "discounted_identically or ranks_by_player_value or second_tight_end",
     "SURPLUS_BASE + SURPLUS_OVER) * vor"),
    ("surplus penalty: keep it uniform but at the LIGHT rate (bench depth barely discounted)", _DRAFT,
     "            surplus_pen = min(SURPLUS_CAP, SURPLUS_BASE + SURPLUS_OVER) * vor",
     "            surplus_pen = min(SURPLUS_CAP, SURPLUS_BASE) * vor",
     "discounted_identically", "SURPLUS_BASE + SURPLUS_OVER"),
    ("surplus penalty: exempt TE, the position the live draft over-recommended", _DRAFT,
     "        if level == 0 and vor > 0:\n"
     "            surplus_pen = min(SURPLUS_CAP, SURPLUS_BASE + SURPLUS_OVER) * vor",
     "        if level == 0 and vor > 0 and pos != 'TE':\n"
     "            surplus_pen = min(SURPLUS_CAP, SURPLUS_BASE + SURPLUS_OVER) * vor",
     "discounted_identically or ranks_by_player_value or second_tight_end", None),

    # ── 3. one rule, three owners ───────────────────────────────────────────────────────────────
    ("mock-draft simulator: its OWN copy goes back to counting every slot", _MOCK,
     "  const totalSlots = draftableSlotCount(config.roster)",
     "  const totalSlots = config.roster.reduce((a, s) => a + s.count, 0)",
     "every_owner or no_further_implementation", "draftableSlotCount(config.roster)"),
    ("TS engine: its copy goes back to counting every slot", _TS,
     "  const totalSlots = draftableSlotCount(config.roster)",
     "  const totalSlots = config.roster.reduce((a, s) => a + s.count, 0)",
     "every_owner or no_further_implementation", "draftableSlotCount(config.roster)"),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        occurrences = original.count(old)
        if occurrences == 0:
            print(f"{'BROKEN ❌ (anchor not found)':34} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        # ⭐ The mirrored-engine hazard: an anchor present TWICE means `replace(..., 1)` may mutate a
        # different site than the one under test, and the guard's GREEN would mean nothing.
        if occurrences > 1:
            print(f"{'BROKEN ❌ (anchor not unique)':34} {name} -> {occurrences}x in {rel}")
            failures.append(f"{name}: anchor appears {occurrences}x in {rel}")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name
        if gone is not None and gone in mutated:
            print(f"{'BROKEN ❌ (token survives)':34} {name} -> {gone!r} still present")
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
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:34} {name}\n{'':34} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — every guard here is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
