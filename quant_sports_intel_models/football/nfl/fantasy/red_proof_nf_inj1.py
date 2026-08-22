"""red_proof_nf_inj1.py — prove the NF-INJ1 guards actually FAIL on deliberately-broken source.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / INC-39). This applies one mutation
at a time to the real modules on disk, re-runs the suite, and asserts it goes RED.

Three ways a RED proof itself lies, all closed here (CLAUDE.md's RED-proof-lies family):
  * #682 — THE MUTATION NEVER LANDED. Every break asserts the file CHANGED on disk before pytest runs.
  * #815 — IT LANDED BUT DID NOT MOVE THE ASSERTED PREDICATE. Every break asserts the ORIGINAL token
           is GONE afterwards, not merely that the bytes differ.
  * E11.24 — IT LANDED ON THE WRONG SYMBOL. Every anchor is asserted UNIQUE in its file first.

⛔ Restores stale backups AT START-UP (E11.26): this file's own worst case is being killed mid-
mutation, which would otherwise leave broken source on disk.

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.red_proof_nf_inj1
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
COH = ROOT / "quant_sports_intel_models/football/nfl/fantasy/projection_coherence.py"
EXP = ROOT / "quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py"
TESTS = "betting_ml/tests/test_nf_inj1_projection_coherence.py"

#: (label, file, old, new, the test that MUST go red)
BREAKS: list[tuple[str, pathlib.Path, str, str, str]] = [
    ("envelope widened to swallow the live defect (the E2.1-r inversion)", COH,
     '"QB": {"passAtt": 45.44, "passYds": 371.20,',
     '"QB": {"passAtt": 999.0, "passYds": 9999.0,',
     "test_the_measured_live_defect_is_caught"),
    ("the ratio is dropped — compare the SEASON TOTAL instead of the per-game rate", COH,
     "        rate = v / g\n", "        rate = v\n",
     "test_a_real_starter_line_is_coherent"),
    ("applicability dropped — a stat-line-less blob reports a CLEAN board", COH,
     '"applicable": bool(with_line),', '"applicable": True,',
     "test_a_board_blob_reports_NOT_APPLICABLE_rather_than_clean"),
    ("unevaluable rows silently treated as fine", COH,
     "    unevaluable = [r for r in in_scope if not _is_evaluable(r)]\n",
     "    unevaluable = []\n",
     "test_rows_without_usable_games_are_counted_unevaluable"),
    ("a missing injury stamp scored OK instead of UNKNOWN", COH,
     'return {"verdict": "UNKNOWN", "lag_hours": None, "as_of": stamp,',
     'return {"verdict": "OK", "lag_hours": None, "as_of": stamp,',
     "test_a_missing_stamp_is_UNKNOWN_never_OK"),
    ("the freshness bar decoupled from the feed's declared SLA", COH,
     "INJURY_INPUT_MAX_LAG_HOURS = 72.0", "INJURY_INPUT_MAX_LAG_HOURS = 5000.0",
     "test_the_bar_is_derived_from_the_feeds_own_declared_SLA"),
    ("strict mode stops refusing (the guard becomes decorative)", EXP,
     "    if strict and (total or fresh[\"verdict\"] != \"OK\" or not scored):",
     "    if False:",
     "test_exporter_guard_refuses_under_strict"),
    ("strict stops refusing on a STALE injury input alone", EXP,
     'if strict and (total or fresh["verdict"] != "OK" or not scored):',
     'if strict and (total or not scored):',
     "test_strict_refuses_on_a_STALE_injury_input_even_when_every_line_is_coherent"),
]


def _restore_all() -> None:
    for f in (COH, EXP):
        bak = f.with_suffix(f.suffix + ".redbak")
        if bak.exists():
            f.write_text(bak.read_text())
            bak.unlink()
            print(f"  (restored stale backup for {f.name})")


def main() -> int:
    _restore_all()                      # E11.26: never start on top of a half-applied mutation
    reds = 0
    for label, path, old, new, test in BREAKS:
        src = path.read_text()
        # E11.24: the anchor must be UNIQUE, or the break can land on the wrong symbol
        n = src.count(old)
        if n != 1:
            print(f"❌ ANCHOR NOT UNIQUE ({n} occurrences) for: {label}")
            return 1
        bak = path.with_suffix(path.suffix + ".redbak")
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            after = path.read_text()
            assert after != src, f"#682: mutation did not land — {label}"
            assert old not in after, f"#815: original token survived — {label}"
            r = subprocess.run([sys.executable, "-m", "pytest", f"{TESTS}::{test}", "-q",
                                "--no-header", "-p", "no:cacheprovider"],
                               cwd=ROOT, capture_output=True, text=True)
            ok = r.returncode != 0
            reds += ok
            print(f"{'✅ RED  ' if ok else '❌ GREEN'}  {test}\n           break: {label}")
            if not ok:
                print("           ⚠️ THE GUARD DID NOT CATCH THIS — it is vacuous for this clause.")
        finally:
            path.write_text(bak.read_text())
            bak.unlink()
    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    # the suite must be green again once every mutation is reverted
    r = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q", "--no-header",
                        "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
    print("restored suite:", "GREEN ✅" if r.returncode == 0 else "RED ❌ (source not restored!)")
    return 0 if reds == len(BREAKS) and r.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
