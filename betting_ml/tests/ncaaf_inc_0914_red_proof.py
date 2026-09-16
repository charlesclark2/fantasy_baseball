#!/usr/bin/env python3
"""NCAAF-INC-0914 RED PROOF — break the source one defect at a time, require the NAMED clause to fail.

    uv run python betting_ml/tests/ncaaf_inc_0914_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`).

WHY THIS SUITE NEEDS IT. Every clause here is a SOURCE-INSPECTION clause over a shell script and a
job module — the exact shape this repo has repeatedly found to be satisfiable by prose. The
incident's own root cause was a probe that returned a plausible number for a state it could not
see; a guard that returns a plausible pass for a defect it cannot see is the same failure one
level up.

THE FOUR CONTROLS (the house idiom — see ncaaf_p1_2w_red_proof.py for the full rationale):
  1. BASELINE-PASS   — every named clause is green on unbroken source first.
  2. NOT-SELECTED    — a stale test id makes pytest exit non-zero, which a naive check reads as
                       "went red". A false RED is the dangerous direction.
  3. UNIQUE ANCHOR   — a non-unique anchor lands wherever the first match is and reports a FALSE
                       "GREEN — VACUOUS".
  4. MUST-VANISH     — a removal break must be proven to have actually removed the token; a
                       mutation that lands without moving the asserted predicate reads as a finding.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

DEPLOY = REPO / "services/dagster/aws/deploy.sh"
JOB = REPO / "pipeline/jobs/sports_dbt_job.py"

DEPLOY_SUITE = "betting_ml/tests/test_deploy_concurrency_guard.py"
CEILING_SUITE = "betting_ml/tests/test_ncaaf_inc_0914_run_ceiling.py"

#: (label, file, find, replace, suite, test id, token-that-must-vanish-or-None)
CASES: list[tuple[str, Path, str, str, str, str, str | None]] = [
    # ══ the CAUSE — the drain could not see a run that had not reached STARTED ═════════════
    # ⭐ THE ONE THIS INCIDENT EXISTS FOR. Reverting to the shipped filter is exactly the state
    # the box was in at 18:00:23 on 2026-09-14, when it reported "no in-flight runs" over a run
    # that was in STARTING and 24 seconds from executing dbt.
    ("the drain reverts to a STARTED-only filter (the shipped state)",
     DEPLOY,
     "statuses:[QUEUED,NOT_STARTED,STARTING,STARTED,CANCELING]",
     "statuses:[STARTED]",
     DEPLOY_SUITE,
     "TestTheDrainDoesNotFailOpen::test_the_drain_waits_for_runs_that_have_not_reached_started_yet",
     "statuses:[QUEUED"),

    ("the probe stops branching on __typename, so a PythonError reads as drained",
     DEPLOY,
     "if r.get('__typename') != 'Runs':\n    raise SystemExit(1)\n",
     "",
     DEPLOY_SUITE,
     "TestTheDrainDoesNotFailOpen::test_a_graphql_level_error_is_unknown_rather_than_drained",
     "!= 'Runs'"),

    # The INC-36 clause this change sits inside — proof that widening the filter did not
    # weaken the fail-open guard that was already there.
    ("the INC-36 fail-open returns: a failed probe reads as zero again",
     DEPLOY,
     "\"}' 2>/dev/null)\" \\\n    || { echo unknown; return 0; }",
     "\"}' 2>/dev/null)\" \\\n    || echo 0",
     DEPLOY_SUITE,
     "TestTheDrainDoesNotFailOpen::test_in_flight_does_not_swallow_a_failed_probe_as_zero",
     None),

    # ══ the DETECTION-LATENCY bound — the ceiling this job family never had ════════════════
    ("the NCAAF build loses its run tags and inherits the instance-wide 4h cap",
     JOB,
     "@job(executor_def=in_process_executor, tags=_SPORTS_DBT_JOB_TAGS)\ndef sports_ncaaf_dbt_build_job():",
     "@job(executor_def=in_process_executor)\ndef sports_ncaaf_dbt_build_job():",
     CEILING_SUITE,
     "TestEverySportsDbtBuildCarriesItsOwnCeiling::test_the_job_declares_a_max_runtime[sports_ncaaf_dbt_build_job]",
     None),

    ("the NFL build loses its run tags",
     JOB,
     "@job(executor_def=in_process_executor, tags=_SPORTS_DBT_JOB_TAGS)\ndef sports_nfl_dbt_build_job():",
     "@job(executor_def=in_process_executor)\ndef sports_nfl_dbt_build_job():",
     CEILING_SUITE,
     "TestEverySportsDbtBuildCarriesItsOwnCeiling::test_the_job_declares_a_max_runtime[sports_nfl_dbt_build_job]",
     None),

    # A ceiling BELOW the legs is worse than none: it preempts a slow-but-healthy build and
    # replaces its diagnosable leg timeout with the cause-free forcible-failure message.
    ("the ceiling is hardcoded below the worst case the legs can take",
     JOB,
     'str(_DBT_LEGS_PER_JOB * DBT_TIMEOUT_SECONDS + 1200)',
     '"600"',
     CEILING_SUITE,
     "TestEverySportsDbtBuildCarriesItsOwnCeiling::test_the_ceiling_is_sized_from_the_legs_rather_than_guessed",
     "_DBT_LEGS_PER_JOB * DBT_TIMEOUT_SECONDS"),

    # ══ the shared DuckDB file ════════════════════════════════════════════════════════════
    ("the two builds get PER-JOB groups, leaving the cross-sport DuckDB collision open",
     JOB,
     "@job(executor_def=in_process_executor, tags=_SPORTS_DBT_JOB_TAGS)\ndef sports_ncaaf_dbt_build_job():",
     '@job(executor_def=in_process_executor, tags={"concurrency_group": "ncaaf_dbt_build",\n'
     "                                             MAX_RUNTIME_SECONDS_TAG: str(JOB_MAX_RUNTIME_SECONDS)})\n"
     "def sports_ncaaf_dbt_build_job():",
     CEILING_SUITE,
     "TestTheTwoBuildsCannotRaceOnTheSharedDuckDB::test_both_builds_share_one_group",
     None),
]


def run_one(suite: str, test_id: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED"."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{suite}::{test_id}", "-q", "--no-header",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=REPO, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    if "no tests ran" in out or "ERROR: not found" in out or "not found:" in out:
        return "NOT-SELECTED"
    return "PASSED" if r.returncode == 0 else "FAILED"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}

    print("baseline (every named clause, unbroken source) …")
    baseline = {(s, t): run_one(s, t) for *_, s, t, _ in CASES}
    bad = {k: v for k, v in baseline.items() if v != "PASSED"}
    if bad:
        for (s, t), v in bad.items():
            print(f"🚨 baseline: {s}::{t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1
    print(f"  all {len(baseline)} green ✅\n")

    results = []
    try:
        for label, path, find, replace, suite, test_id, must_vanish in CASES:
            original = backups[path]
            n = original.count(find)
            if n == 0:
                results.append((label, "ANCHOR-MISSING"))
                continue
            if n > 1:
                results.append((label, f"AMBIGUOUS-ANCHOR (x{n})"))
                continue
            patched = original.replace(find, replace, 1)
            if patched == original:
                results.append((label, "BREAK-IS-A-NO-OP"))
                continue
            if must_vanish is not None and must_vanish in patched:
                results.append((label, f"BREAK-DID-NOT-REMOVE {must_vanish!r}"))
                continue
            path.write_text(patched)
            try:
                outcome = run_one(suite, test_id)
            finally:
                path.write_text(original)
            results.append((label, {
                "PASSED": "GREEN — VACUOUS",
                "FAILED": "RED",
                "NOT-SELECTED": "NOT-SELECTED (the named clause does not exist)",
            }[outcome]))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _ in results)
    red = sum(1 for _, s in results if s == "RED")
    for label, status in results:
        print(f"{'✅' if status == 'RED' else '🚨'} {label.ljust(width)}  →  {status}")
    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
