#!/usr/bin/env python
"""ncaaf_lake1_red_proof.py — prove the absent-table classifier's guards actually FAIL on a break.

This helper decides whether a lake read means "nothing is there yet", and that verdict is a licence
to OVERWRITE for every READ-MERGE-WRITE writer in the vertical. So both directions must be pinned,
and BOTH must be shown to go red:

  * report ABSENT when the table exists            -> a merge writer deletes a season of paid odds
  * report PRESENT when the table is genuinely new -> a first-ever write is impossible (the live
                                                      incident: NCAAF-PS could not bootstrap)

The harness carries the three anti-lying guards this repo has been bitten by: the mutation must
LAND on disk (#682), its anchor must be UNIQUE so it cannot land on the wrong symbol (#815 sibling,
where a FALSE VACUITY report is the dangerous direction), and where a break is meant to REMOVE a
token, that token's absence is asserted (#815). A stale backup from a killed run is restored at
start-up (E11.26).

Run:  uv run python betting_ml/tests/ncaaf_lake1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
QL = _REPO / "quant_sports_intel_models/football/ncaaf/ingest/query_lake.py"

_SUITES = [
    "betting_ml/tests/test_ncaaf_odds_recurring_capture.py",
    "betting_ml/tests/test_ncaaf_game_prediction_snapshot.py",
    "betting_ml/tests/test_ncaaf_p3_1_serving.py",
]

#: (label, file, old, new, pytest -k selector, token that must DISAPPEAR or None)
BREAKS: list[tuple[str, Path, str, str, str, str | None]] = [
    # ── direction 1: a genuinely-absent table must be reported absent ───────────────────────
    ("an absent table is reported as a read failure (the live incident: no first write possible)",
     QL, "            if table_is_absent(sql):", "            if False:",
     "bootstrap or unwritten_snapshot_table or returns_none_only_for_a_genuinely_missing", None),

    ("absence is decided by the ERROR TEXT again instead of by the store",
     QL, "    verdicts = [_table_has_commits(uri) for uri in targets]",
     '    verdicts = [None if "log segment" in uri else True for uri in targets]',
     "answers_from_the_store or unwritten_snapshot_table", "_table_has_commits(uri) for uri"),

    # ── direction 2: anything not PROVEN absent must raise ──────────────────────────────────
    ("an UNDETERMINABLE listing is reported as absent (the destructive direction)",
     QL, "    if any(v is None for v in verdicts):\n        return False",
     "    if any(v is None for v in verdicts):\n        return True",
     "undeterminable_listing_is_never_reported_as_absent", None),

    ("SQL whose tables cannot be identified is reported as absent",
     QL, "    if not targets:\n        return False", "    if not targets:\n        return True",
     "cannot_be_identified_is_never_reported_as_absent", None),

    ("a table that EXISTS is reported as absent",
     QL, "    return any(v is False for v in verdicts)", "    return True",
     "raises_when_the_table_exists or genuine_read_failure_still_raises", None),

    ("a failed listing is swallowed into 'absent' instead of 'undetermined'",
     QL, "        return None\n\n\ndef table_is_absent", "        return False\n\n\ndef table_is_absent",
     "undeterminable_listing_is_never_reported_as_absent or listing_that_fails_is_UNDETERMINED",
     None),

    # ── the store probe itself ──────────────────────────────────────────────────────────────
    ("the S3 probe reports a commit that is not there (MaxKeys/KeyCount misread)",
     QL, "            return int(resp.get(\"KeyCount\", 0)) > 0",
     "            return True",
     "s3_probe_reports_absent_only_when", "int(resp.get(\"KeyCount\", 0)) > 0"),

    ("the local probe stops looking for a _delta_log at all",
     QL, "        if not os.path.isdir(log_dir):\n            return False",
     "        if not os.path.isdir(log_dir):\n            return True",
     "bootstrap or local_probe_reads_the_real_filesystem", None),
]


def _run(selector: str) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *_SUITES, "-q", "-k", selector, "--no-header",
         "-p", "no:cacheprovider"],
        cwd=_REPO, capture_output=True, text=True)
    if "no tests ran" in proc.stdout or "collected 0 items" in proc.stdout:
        print(f"      ⚠️  selector {selector!r} matched NO tests — the proof would be vacuous")
        return False
    return proc.returncode != 0


def main() -> int:
    backup = QL.with_suffix(QL.suffix + ".redproof.bak")
    if backup.exists():
        print(f"⚠️  restoring stale backup for {QL.name}")
        QL.write_text(backup.read_text())
        backup.unlink()

    print("baseline (all three suites, unbroken source) …", end=" ", flush=True)
    base = subprocess.run([sys.executable, "-m", "pytest", *_SUITES, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    if base.returncode != 0:
        print("FAILED — fix the suites before RED-proving them")
        print(base.stdout[-3000:])
        return 1
    print("green ✅")

    reds = 0
    for label, path, old, new, selector, must_vanish in BREAKS:
        src = path.read_text()
        n = src.count(old)
        if n != 1:
            print(f"❌ {label}\n      anchor occurs {n}× — a non-unique anchor can land the break "
                  "on the WRONG symbol (#815)")
            continue
        backup.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            landed = path.read_text()
            assert landed != src, f"the mutation for {label!r} did not land on disk"
            if must_vanish is not None and must_vanish in landed:
                print(f"❌ {label}\n      landed but {must_vanish!r} survives — it would not move "
                      "the asserted predicate (#815)")
                continue
            went_red = _run(selector)
        finally:
            path.write_text(backup.read_text())
            backup.unlink()
        print(("🔴 RED  " if went_red else "❌ GREEN") + f"  {label}")
        reds += int(went_red)

    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    return 0 if reds == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
