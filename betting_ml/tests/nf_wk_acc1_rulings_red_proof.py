"""NF-WK-ACC1 rulings RED proof — break the source; each break must turn its OWN guard red.

Harness body copied from `nf_wk_acc1_part3_red_proof.py` (same discipline, its own backup suffix so
four proofs can never collide): restore-stale-backups-first, unique anchor, landed-on-disk,
token-gone, NOT-SELECTED, `BaseException`, every node resolved.

⛔ THE CENTRAL BREAK IS THE ONE THE PM NAMED: reverting `fumbles_lost` to the three per-phase columns
must turn DJ Moore's 2025 wk1 clause red at 8.40 against his league's published 7.40.

⚠️ EVERY BREAK IS A REPLACEMENT, NEVER AN ADDITION — an additive break leaves its own anchor on disk
and the token-gone check correctly refuses it.

Run:  uv run python betting_ml/tests/nf_wk_acc1_rulings_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_acc1_rulings.py"
_RSF = "app/backend/services/realized_stat_fields.py"
_RW = "quant_sports_intel_models/football/nfl/fantasy/realized_week.py"
_GATE = "quant_sports_intel_models/football/nfl/fantasy/run_nf_wk_acc1_idp_scope_verify.py"
_BAK = ".rulingsbak"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    # ── ruling ①, the change itself ────────────────────────────────────────────────────────────
    ("the lost-fumble term is re-narrowed to the three per-phase columns (the overturned refusal)",
     _RSF,
     '    "fumbles_lost": ("fumbles_lost_total",),',
     '    "fumbles_lost": ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"),',
     "test_dj_moore_2025_wk1_now_reproduces_his_leagues_own_figure"),
    ("the lost-fumble term collapses onto the any-fumble column, agreeing for the wrong reason",
     _RSF,
     '    "fumbles_lost": ("fumbles_lost_total",),',
     '    "fumbles_lost": ("fumbles_total",),',
     "test_the_lost_fumble_term_reads_the_total"),

    # ── ruling ①, the publish path it would otherwise strand ──────────────────────────────────
    ("the per-phase columns are pruned as cruft, shrinking the artifact into a refused restate",
     _RSF,
     'REALIZED_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (\n'
     '    "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost",\n'
     ')',
     'REALIZED_DIAGNOSTIC_COLUMNS: tuple[str, ...] = ()',
     "test_the_diagnostic_columns_are_declared_with_a_reason_not_left_as_cruft"),
    ("the artifact stops carrying the diagnostic columns even though they are declared", _RW,
     "        | set(R.REALIZED_DIAGNOSTIC_COLUMNS)\n    ))",
     "    ))",
     "test_the_per_phase_columns_are_still_carried_so_the_change_can_actually_ship"),

    # ── ruling ①, the amended refusal ─────────────────────────────────────────────────────────
    ("the old refusal's own words are deleted rather than kept beside the amendment", _RSF,
     '"⛔ Do not \'tidy\' this back to the total: it is\nshorter, it reads more natural, and it is wrong."',
     '"(the old wording has been removed)"',
     "test_the_amended_refusal_says_what_the_pm_required_it_to_say"),
    ("the amendment drops the measured cost that forced it", _RSF,
     "Over 2025 REG the two readings differ on 36 rows",
     "Over 2025 REG the two readings differ on some rows",
     "test_the_amended_refusal_says_what_the_pm_required_it_to_say"),

    # ── ruling ②, the NON-change ──────────────────────────────────────────────────────────────
    ("a later session 'finishes the job' on ruling 2 and scopes the team-defence terms away", _RSF,
     '    "def_fumble_rec": ("fumble_recovery_opp",),',
     '    # def_fumble_rec scoped out (NOT RULED — this is the reverted fix)',
     "test_ruling_two_left_the_player_grain_defensive_terms_ALONE"),
    ("the gate reverts to the team-grain keys, so it would pass vacuously again", _GATE,
     '    "def_fumble_rec": ("fumble_recovery_opp", "fum_rec", ("idp_fum_rec", "st_fum_rec")),',
     '    "def_fumble_rec": ("fumble_recovery_opp", "fum_rec", ()),',
     "test_the_pre_registered_gate_and_its_vacuity_control_are_still_present"),
    ("the gate's vacuity control is removed, so a sweep of zeros reads as a PASS", _GATE,
     '            "keyReach": totals, "deadKeys": dead,\n            "instrumentSound": not dead}',
     '            "reach": totals}',
     "test_the_pre_registered_gate_and_its_vacuity_control_are_still_present"),
]


def _run(test: str) -> tuple[bool, str]:
    """RED = the NAMED test fails. A collection error or a NOT-SELECTED miss is a harness fault."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-x", "-q", "--no-header",
         "-p", "no:randomly"],
        cwd=ROOT, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    if "no tests ran" in out or "ERROR" in out.split("\n")[0]:
        return False, f"NOT-SELECTED or collection error for {test}:\n{out[-800:]}"
    return proc.returncode != 0, out[-400:]


def main() -> int:
    for bak in ROOT.rglob(f"*{_BAK}"):
        target = bak.with_suffix("")
        print(f"restoring stale backup {bak.relative_to(ROOT)}")
        target.write_text(bak.read_text())
        bak.unlink()

    cases = list(BREAKS)
    failures: list[str] = []
    for label, rel, old, new, test in cases:
        path = ROOT / rel
        src = path.read_text()
        if src.count(old) != 1:
            failures.append(f"{label}: anchor appears {src.count(old)}x (must be exactly 1)")
            continue
        bak = path.with_suffix(path.suffix + _BAK)
        bak.write_text(src)
        try:
            broken = src.replace(old, new, 1)
            path.write_text(broken)
            on_disk = path.read_text()
            if on_disk == src or old in on_disk:
                failures.append(f"{label}: mutation did not land / anchor still present")
                continue
            red, tail = _run(test)
            print(f"  {'✅ RED ' if red else '❌ GREEN'} {label}  →  {SUITE}::{test}")
            if not red:
                failures.append(f"{label}: {test} stayed GREEN\n{tail}")
        except BaseException as exc:  # noqa: BLE001 — a signal must not leave source mutated
            failures.append(f"{label}: harness raised {type(exc).__name__}: {exc}")
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    assert len(cases) - len(failures) + len(failures) == len(cases)
    print()
    if failures:
        print(f"❌ {len(failures)} of {len(cases)} breaks did not prove their guard:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"✅ all {len(cases)} breaks turned their named guard RED; source restored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
