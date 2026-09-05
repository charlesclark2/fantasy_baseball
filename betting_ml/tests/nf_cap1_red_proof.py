"""NF-CAP1 RED proof — deliberately break each guarded property and prove the suite goes RED.

A guard that cannot fail is not a guard (NF1.7 (a) / INC-38 / INC-39). This harness applies one
mutation at a time to the REAL source, runs the suite, and asserts it fails — and it carries the
three defences this repo has learned the hard way about RED proofs themselves:

  #682  the mutation must be proven to LAND ON DISK (a shell-quoting slip made a harness report
        "the guard is vacuous" when the break had never been written);
  #815  the mutation must be proven to MOVE THE ASSERTED PREDICATE — a break that writes but
        leaves the asserted token present comes back green and reads as a real finding;
  E11.24 the mutation ANCHOR must be UNIQUE in the file — two byte-identical tails make a
        single-occurrence replace land on the WRONG symbol, producing a FALSE vacuity report,
        which is the dangerous direction because it invites weakening a correct guard.

Restores stale backups AT START-UP: this harness's own worst case is being killed mid-mutation
(E11.26), which would otherwise leave a deliberate break on disk.

    uv run python betting_ml/tests/nf_cap1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SUITE = "betting_ml/tests/test_nf_cap1_capture_health.py"


@dataclass(frozen=True)
class Break:
    what: str            # the property being disabled
    path: str            # repo-relative file
    old: str             # anchor — must appear EXACTLY once
    new: str             # the mutation
    gone: str | None = None   # a token that must DISAPPEAR (proves the predicate moved, #815)


BREAKS = (
    Break(
        "an UNDECLARED props flag is treated as a deliberate OFF (the pre-NF-CAP1 collapse)",
        "quant_sports_intel_models/football/nfl/pit/market_capture.py",
        '    raw = env.get(PROPS_ENV_FLAG)\n    if raw is None or not raw.strip():\n        return PROPS_UNDECLARED',
        '    raw = env.get(PROPS_ENV_FLAG)\n    if raw is None or not raw.strip():\n        return PROPS_OFF',
        gone="        return PROPS_UNDECLARED",
    ),
    Break(
        "the props tier's own zero-check (the game-line tier satisfies the shared one)",
        "quant_sports_intel_models/football/nfl/pit/market_capture.py",
        '    if declared == PROPS_UNDECLARED:\n        manifest["escalate"] = True',
        '    if False:\n        manifest["escalate"] = True',
        gone='    if declared == PROPS_UNDECLARED:',
    ),
    Break(
        # `declared` is what makes an EXPLICIT `capture_props=` argument count as a declaration.
        # Revert it to reading the env unconditionally and a hand-run that chose is paged at
        # about a flag it never consulted.
        "an explicit capture_props= argument counting as a declaration",
        "quant_sports_intel_models/football/nfl/pit/market_capture.py",
        '    declared = props_state() if capture_props is None else (\n'
        '        PROPS_ON if capture_props else PROPS_OFF\n    )',
        '    declared = props_state()',
        gone='        PROPS_ON if capture_props else PROPS_OFF',
    ),
    Break(
        "props-enabled-but-zero-events escalation",
        "quant_sports_intel_models/football/nfl/pit/market_capture.py",
        '    elif capture_props and not manifest["prop_events"]:',
        '    elif False:',
        gone='    elif capture_props and not manifest["prop_events"]:',
    ),
    Break(
        "the zero-ROW injury landing escalation past the data-expected bar",
        "quant_sports_intel_models/football/nfl/pit/injury_capture.py",
        '        else:\n            manifest["escalate"] = True\n            log.warning(\n                "ALERT [nfl/pit/injuries] injuries_%s.parquet read OK but returned ZERO ROWS on "',
        '        else:\n            manifest["escalate"] = False\n            log.warning(\n                "ALERT [nfl/pit/injuries] injuries_%s.parquet read OK but returned ZERO ROWS on "',
        gone='        else:\n            manifest["escalate"] = True',
    ),
    Break(
        "the weekday axis of the active window (a Tue/Fri contract reverts to every day)",
        "betting_ml/monitoring/artifact_freshness.py",
        "        if (weekdays is None or day.weekday() in weekdays) and (\n            months is None or day.month in months\n        ):",
        "        if True:",
        gone="            months is None or day.month in months",
    ),
    Break(
        "the day-bucketed scan (reverts to the flat cap that false-pages a seasonal contract)",
        "betting_ml/monitoring/artifact_freshness.py",
        "        if scanned_days > _MAX_SCAN_DAYS:\n            # Anything this stale is far past every SLA in the registry; report at the cap.\n            return float(_MAX_SCAN_DAYS * 24 * 60)",
        "        if scanned_days > 30:\n            return float(30 * 24 * 60)",
        gone="        if scanned_days > _MAX_SCAN_DAYS:",
    ),
    Break(
        "the nfl_pit_market freshness contract",
        "betting_ml/monitoring/artifact_freshness.py",
        '        name="nfl_pit_market",\n        ts_table="nfl_pit_market",\n        pit_source="market",',
        '        name="nfl_pit_market_DISABLED",\n        ts_table="nfl_pit_market_DISABLED",\n        pit_source="market",',
        gone='        name="nfl_pit_market",',
    ),
    Break(
        "the metadata schedule's heartbeat entry (STOPPED-drift stops paging)",
        "betting_ml/monitoring/monitor_health.py",
        '    "sports_nfl_pit_metadata_schedule",\n})',
        '})',
        gone='    "sports_nfl_pit_metadata_schedule",',
    ),
    Break(
        # The PAID schedule has NO heartbeat entry by design (the entry would be vacuous against
        # a default-STOPPED instigator), so its ONLY coverage is the artifact contract. Prove the
        # suite notices if someone removes that contract while leaving the exclusion in place —
        # i.e. that the two halves of the argument cannot be separated silently.
        "the PAID schedule's ONLY coverage — its artifact contract — while it stays out of the heartbeat",
        "betting_ml/monitoring/artifact_freshness.py",
        '        name="nfl_pit_market",\n        ts_table="nfl_pit_market",',
        '        name="nfl_pit_market_GONE",\n        ts_table="nfl_pit_market_GONE",',
        gone='        name="nfl_pit_market",',
    ),
    Break(
        "the props flag's env.required registration",
        "services/dagster/aws/env.required",
        "\nNFL_PIT_CAPTURE_PROPS\n",
        "\n# NFL_PIT_CAPTURE_PROPS\n",
        gone="\nNFL_PIT_CAPTURE_PROPS\n",
    ),
    Break(
        "the measured game-line credit cost in BOX_OPERATIONS §10",
        "services/dagster/aws/BOX_OPERATIONS.md",
        "**3 credits/snapshot**",
        "**~30 credits/snapshot**",
        gone="**3 credits/snapshot**",
    ),
)


def _run_suite() -> bool:
    """True when the suite PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", _SUITE, "-q", "--no-header", "-x"],
        cwd=_REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    # Restore anything a previous killed run left behind, BEFORE touching source.
    for b in BREAKS:
        bak = _REPO / (b.path + ".nf_cap1_bak")
        if bak.exists():
            (_REPO / b.path).write_text(bak.read_text())
            bak.unlink()
            print(f"  restored a stale backup for {b.path}")

    print("BASELINE (unbroken source) ...", end=" ", flush=True)
    if not _run_suite():
        print("FAIL — the suite is red before any mutation; fix that first.")
        return 2
    print("PASS\n")

    failures = 0
    for i, b in enumerate(BREAKS, 1):
        target = _REPO / b.path
        original = target.read_text()

        # #E11.24 — the anchor must be UNIQUE, or the mutation can land on the wrong symbol.
        n = original.count(b.old)
        if n != 1:
            print(f"{i:>2}. {b.what}\n    ANCHOR NOT UNIQUE ({n} occurrences) — cannot trust this case")
            failures += 1
            continue

        bak = _REPO / (b.path + ".nf_cap1_bak")
        bak.write_text(original)
        try:
            mutated = original.replace(b.old, b.new, 1)
            target.write_text(mutated)
            on_disk = target.read_text()
            # #682 — prove the mutation LANDED.
            assert on_disk != original, "mutation did not change the file"
            # #815 — prove it MOVED THE ASSERTED PREDICATE, not merely wrote bytes.
            gone = b.gone if b.gone is not None else b.old
            assert gone not in on_disk, f"the token {gone!r} survived the mutation"

            red = not _run_suite()
            print(f"{i:>2}. {'RED  ' if red else 'GREEN'}  {b.what}")
            if not red:
                failures += 1
                print("      ^^ the guard did NOT catch this — it is vacuous")
        finally:
            target.write_text(original)
            bak.unlink(missing_ok=True)

    print()
    if failures:
        print(f"{failures} of {len(BREAKS)} deliberate breaks were NOT caught.")
        return 1
    print(f"All {len(BREAKS)} deliberate breaks turned the suite RED; baseline passes clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
