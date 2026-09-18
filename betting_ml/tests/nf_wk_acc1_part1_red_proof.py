"""NF-WK-ACC1 part 1 RED proof — break the source; each break must turn its OWN guard red.

Harness body copied from `nf_wk_acc1_red_proof.py` (same discipline, its own backup suffix so two
proofs can never collide): unique anchor, landed-on-disk, token-gone, NOT-SELECTED, `BaseException`,
every node resolved. Each break REPRODUCES the defect its guard names rather than editing the
guarded line.

Run:  uv run python betting_ml/tests/nf_wk_acc1_part1_red_proof.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SUITE = "betting_ml/tests/test_nf_wk_acc1_fum.py"
_PF = "app/backend/services/projection_fields.py"
_RSF = "app/backend/services/realized_stat_fields.py"
_EDITOR = "frontend/components/fantasy/league-settings-editor.tsx"
_BAK = ".part1bak"

# (label, file, old, new, the test that MUST go red)
BREAKS = [
    ("the scorer never learns the key, so the league's rule stays unapplied", _PF,
     '    "fum": "fumAny",\n',
     "",
     "test_the_paid_set_gains_exactly_fum_any_and_loses_nothing"),
    ("the realized map does not name the term (the rule is kept, never scored)", _RSF,
     '    "fum": ("fumbles_total",),\n',
     "",
     "test_the_two_fumble_terms_read_different_columns_and_cannot_collapse_into_one"),
    ("the term reads the per-phase LOST columns — the wrong quantity, scoring silently", _RSF,
     '    "fum": ("fumbles_total",),',
     '    "fum": ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"),',
     "test_the_two_fumble_terms_read_different_columns_and_cannot_collapse_into_one"),
    # ⚠️ THE SINGLE-COLUMN BRANCH, which is the one `fum` takes. A first cut broke the summed
    # branch and the guard stayed GREEN — a break in code the term never reaches proves nothing.
    ("a line with no fumble column scores the term as APPLIED at zero", _RSF,
     "        if len(cols) == 1:\n            if cols[0] in row:\n"
     "                out[field] = row[cols[0]]\n            continue",
     "        if len(cols) == 1:\n            out[field] = row.get(cols[0], 0.0)\n            continue",
     "test_a_week_whose_line_does_not_carry_the_column_reports_captured_not_applied"),
    ("the disclosure claims a gap with no measured gap (#1155 undone)", "app/backend/services/weekly_recap.py",
     "    if max_gap is not None and abs(max_gap) <= GAP_EPSILON:\n        return None",
     "    if False:\n        return None",
     "test_the_measured_gap_rule_still_governs_the_narrowed_disclosure"),
    ("the board's captured label becomes a bare \"not supported\"", _EDITOR,
     'captured: "Saved with your league, but NOT applied — we do not project this stat."',
     'captured: "Saved with your league, but not supported."',
     "test_the_captured_label_says_not_projected_rather_than_not_supported"),
]

#: The option-A break lives in the engine package rather than beside the others, so it is expressed
#: separately. ⚠️ IT REPLACES its anchor rather than adding a line: an ADDITIVE break leaves the
#: anchor on disk and the token-gone check correctly refuses it (the documented landmine).
_PROFILE_BREAK = (
    "the term gains a projection column (option A, the reversed rejection)",
    "quant_sports_intel_models/football/nfl/fantasy/league_presets.py",
    '        "fumbles_lost": "proj_fumbles_lost",',
    '        "fum": "proj_fumbles_lost",',
    "test_the_term_gained_no_projection_column_and_no_ts_mirror_entry",
)


def _run(test: str) -> tuple[bool, str]:
    """RED = the NAMED test fails. A collection error or a NOT-SELECTED miss is a harness fault."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-x", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    if "no tests ran" in out or "ERROR" in out.split("\n")[0]:
        return False, f"NOT-SELECTED or collection error for {test}:\n{out[-800:]}"
    return proc.returncode != 0, out[-400:]


def main() -> int:
    # (a) Restore any stale backup FIRST: this harness's own worst case is dying mid-mutation.
    for bak in ROOT.rglob(f"*{_BAK}"):
        target = bak.with_suffix("")
        print(f"restoring stale backup {bak.relative_to(ROOT)}")
        target.write_text(bak.read_text())
        bak.unlink()

    cases = [*BREAKS, _PROFILE_BREAK]
    failures: list[str] = []
    for label, rel, old, new, test in cases:
        path = ROOT / rel
        src = path.read_text()
        # (b) UNIQUE ANCHOR — a substring that appears twice could land on the wrong occurrence.
        if src.count(old) != 1:
            failures.append(f"{label}: anchor appears {src.count(old)}x (must be exactly 1)")
            continue
        bak = path.with_suffix(path.suffix + _BAK)
        bak.write_text(src)
        try:
            broken = src.replace(old, new, 1)
            path.write_text(broken)
            # (c) LANDED + TOKEN-GONE: the mutation is on disk AND the old text is really absent.
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

    # (d) EVERY NODE RESOLVED.
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
