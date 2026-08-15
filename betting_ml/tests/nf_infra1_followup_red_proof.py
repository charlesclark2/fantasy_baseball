"""RED proof for the NF-INFRA1 follow-up guards —
`uv run python betting_ml/tests/nf_infra1_followup_red_proof.py`.

The defect this story fixes produced NO page: `sports_nfl_board_publish_schedule` and
`sports_nfl_sleeper_injuries_schedule` shipped `default_status=STOPPED` and were absent from
`check_monitors_healthy_op`'s required-RUNNING set, so a silent revert to STOPPED (a Dagster-DB
reset / box re-host) would freeze the board or dark the Sleeper feed with nothing alerting. A test
suite over a defect whose signature is "everything looks fine" is worth exactly its falsifiability,
so each claim below is proved by re-introducing a real regression and requiring the named test to
go RED.

Applies each break IN-PROCESS and ASSERTS THE SOURCE ACTUALLY CHANGED before running pytest — a
red proof whose mutation silently no-ops reports a triumphant, false "the guard caught it" (the
E11.24 #682 lesson). Restores the file in a `finally`, so an interrupted run cannot leave a break
on disk.

Runtime ~10s. Prints one line per case; exits non-zero if ANY break stays green.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_infra1_followup_heartbeat.py"

MONITOR_HEALTH = "betting_ml/monitoring/monitor_health.py"
SCHEDULES = "pipeline/schedules/sports_rollforward_schedules.py"
BOX_OPS = "services/dagster/aws/BOX_OPERATIONS.md"
# Manifest-guarded (imports `pipeline`, needs a compiled dbt manifest — absent in the fast gate),
# so the self-start (default_status=RUNNING) AC can only be caught here, not by TEST above.
WIRING_TEST = "betting_ml/tests/test_monitor_health_wiring.py"

# (label, file, old, new, "<test file>::<test name>")
BREAKS = [
    # ── the required-RUNNING set must actually contain both schedules ───────────────────────
    ("board-publish schedule dropped from CRITICAL_SCHEDULES", MONITOR_HEALTH,
     '    "sports_nfl_board_publish_schedule",\n    "sports_nfl_sleeper_injuries_schedule",\n})',
     '    "sports_nfl_sleeper_injuries_schedule",\n})',
     f"{TEST}::test_board_publish_and_sleeper_are_in_the_required_running_set"),
    ("sleeper-injuries schedule dropped from CRITICAL_SCHEDULES", MONITOR_HEALTH,
     '    "sports_nfl_board_publish_schedule",\n    "sports_nfl_sleeper_injuries_schedule",\n})',
     '    "sports_nfl_board_publish_schedule",\n})',
     f"{TEST}::test_board_publish_and_sleeper_are_in_the_required_running_set"),
    # ── the NCAAF exclusion must not silently disappear (scope creep the story forbids) ──────
    ("an NCAAF schedule leaks into CRITICAL_SCHEDULES", MONITOR_HEALTH,
     '    "sports_nfl_sleeper_injuries_schedule",\n})',
     '    "sports_nfl_sleeper_injuries_schedule",\n    "sports_ncaaf_dbt_schedule",\n})',
     f"{TEST}::test_ncaaf_schedules_are_not_yet_in_the_required_running_set"),
    # ── the doc (§10) must actually be kept in sync, not just the code ──────────────────────
    ("BOX_OPERATIONS.md's board-publish row stops claiming heartbeat coverage", BOX_OPS,
     "**RUNNING** — self-start (`default_status=RUNNING`) as of the NF-INFRA1 follow-up "
     "(2026-08-15) **and heartbeat-checked** (`CRITICAL_SCHEDULES`). NF-INFRA1 landed the prereq",
     "**RUNNING** — self-start (`default_status=RUNNING`) as of the NF-INFRA1 follow-up "
     "(2026-08-15). NF-INFRA1 landed the prereq",
     f"{TEST}::test_box_operations_doc_marks_both_schedules_running_and_heartbeat_checked"),
    ("BOX_OPERATIONS.md's sleeper row stops claiming heartbeat coverage", BOX_OPS,
     "**RUNNING** — self-start (`default_status=RUNNING`) as of the NF-INFRA1 follow-up "
     "(2026-08-15) **and heartbeat-checked** (`CRITICAL_SCHEDULES`). ✅ the 19-green-runs break",
     "**RUNNING** — self-start (`default_status=RUNNING`) as of the NF-INFRA1 follow-up "
     "(2026-08-15). ✅ the 19-green-runs break",
     f"{TEST}::test_box_operations_doc_marks_both_schedules_running_and_heartbeat_checked"),
    ("BOX_OPERATIONS.md's NCAAF dbt-schedule row silently claims heartbeat coverage", BOX_OPS,
     "NOT heartbeat-checked (nothing serving-critical depends on them yet)",
     "heartbeat-checked (nothing serving-critical depends on them yet)",
     f"{TEST}::test_box_operations_doc_still_marks_ncaaf_schedules_not_heartbeat_checked"),
    # ── the self-start AC: both schedules must actually declare default_status=RUNNING ───────
    # Caught by the EXISTING test_monitor_health_wiring.py::test_critical_instigators_self_start
    # sweep (it iterates every name in CRITICAL_SCHEDULES against the real registered schedule
    # objects) — no new test was needed there, only these two names joining CRITICAL_SCHEDULES.
    ("board-publish schedule reverts to default_status=STOPPED in code", SCHEDULES,
     "    # NF-INFRA1 follow-up (2026-08-15): self-starts + heartbeat-checked — see below.\n"
     "    default_status=DefaultScheduleStatus.RUNNING,\n)\ndef sports_nfl_board_publish_schedule",
     "    default_status=DefaultScheduleStatus.STOPPED,\n)\ndef sports_nfl_board_publish_schedule",
     f"{WIRING_TEST}::test_critical_instigators_self_start"),
    ("sleeper-injuries schedule reverts to default_status=STOPPED in code", SCHEDULES,
     "    # NF-INFRA1 follow-up (2026-08-15): self-starts + heartbeat-checked — see module "
     "docstring.\n    default_status=DefaultScheduleStatus.RUNNING,\n)\n"
     "def sports_nfl_sleeper_injuries_schedule",
     "    default_status=DefaultScheduleStatus.STOPPED,\n)\n"
     "def sports_nfl_sleeper_injuries_schedule",
     f"{WIRING_TEST}::test_critical_instigators_self_start"),
]


def main() -> int:
    failures = []
    for label, rel, old, new, test in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if old not in original:
            print(f"SETUP-ERROR  {label}\n             pattern absent from {rel} — the proof is "
                  "stale, NOT passing")
            failures.append(label)
            continue
        path.write_text(original.replace(old, new, 1))
        try:
            # The mutation must be OBSERVABLE before the test runs, or "the guard caught it" and
            # "the break never happened" are indistinguishable (E11.24 #682).
            assert path.read_text() != original, f"mutation did not land for {label}"
            proc = subprocess.run(
                ["uv", "run", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True)
            red = proc.returncode != 0
        finally:
            path.write_text(original)
        print(f"{'RED  ✅' if red else 'GREEN ❌'}  {label}")
        if not red:
            failures.append(label)

    print(f"\n{len(BREAKS) - len(failures)}/{len(BREAKS)} breaks caught")
    if failures:
        print("STAYED GREEN (the guard is vacuous — fix the guard, not the proof):")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("every NF-INFRA1 follow-up guard is falsifiable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
