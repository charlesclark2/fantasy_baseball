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

    # ⚠️ ANCHORED ON THE FOLLOWING LINE: the same typename branch now appears in BOTH in_flight()
    # and doomed_runs(), so the bare snippet is an AMBIGUOUS-ANCHOR (the harness caught this).
    # `print(len(...))` is in_flight()'s alone. ⛔ no must_vanish for the same reason — the token
    # legitimately survives in the sibling function; the clause going RED is the proof.
    ("the probe stops branching on __typename, so a PythonError reads as drained",
     DEPLOY,
     "if r.get('__typename') != 'Runs':\n    raise SystemExit(1)\nprint(len(r.get('results', [])))",
     "print(len(r.get('results', [])))",
     DEPLOY_SUITE,
     "TestTheDrainDoesNotFailOpen::test_a_graphql_level_error_is_unknown_rather_than_drained",
     None),

    # The INC-36 clause this change sits inside — proof that widening the filter did not
    # weaken the fail-open guard that was already there.
    ("the INC-36 fail-open returns: a failed probe reads as zero again",
     DEPLOY,
     "\"}' 2>/dev/null)\" \\\n    || { echo unknown; return 0; }",
     "\"}' 2>/dev/null)\" \\\n    || echo 0",
     DEPLOY_SUITE,
     "TestTheDrainDoesNotFailOpen::test_in_flight_does_not_swallow_a_failed_probe_as_zero",
     None),

    # ══ Decision 1 (PM 2026-09-15) — fail-and-attribute ═══════════════════════════════════
    # ⭐ THE ORDERING CONSTRAINT THE PM MADE EXPLICIT: "a run started by the new worker must be
    # untouchable — guard that ordering with a RED proof". Moving the snapshot AFTER the recreate
    # is exactly how that guarantee is lost, and the file still runs.
    ("the victim snapshot moves AFTER the recreate",
     DEPLOY,
     'DOOMED_RUNS="$(doomed_runs)"',
     'DOOMED_RUNS=""  # moved below',
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_the_snapshot_is_taken_before_the_recreate",
     None),

    # ⭐⭐ THE FALSE-ATTRIBUTION TRAP. A QUEUED run is a row in Postgres, NOT a subprocess: it
    # SURVIVES the recreate and the new daemon launches it moments later. Widening the doomed set
    # to match the drain set is the tempting tidy-up, and it would mark a live, working run FAILED.
    ("the doomed set is widened to match the drain set, sweeping in QUEUED runs",
     DEPLOY,
     '--data \'{"query":"{ runsOrError(filter:{statuses:[STARTING,STARTED]}, limit:50)',
     '--data \'{"query":"{ runsOrError(filter:{statuses:[QUEUED,NOT_STARTED,STARTING,STARTED]}, limit:50)',
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_the_doomed_set_excludes_queued_runs",
     None),

    ("the drain is narrowed to the doomed set, so it stops waiting for queued work",
     DEPLOY,
     "statuses:[QUEUED,NOT_STARTED,STARTING,STARTED,CANCELING]",
     "statuses:[STARTING,STARTED]",
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_the_drain_waits_on_strictly_more_than_the_doomed_set",
     "statuses:[QUEUED"),

    # A bare FAILED reproduces the cause-free alert one layer down — the attribution IS the point.
    ("the failure message stops naming the deploy's commit",
     DEPLOY,
     '-e DEPLOY_SHA="${NEW_HEAD}" ',
     "",
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_the_failure_message_names_the_deploy_and_the_commit",
     # ⛔ no must_vanish: `DEPLOY_SHA` still appears in the python body and `NEW_HEAD` all over the
     # script; the clause reads the BLOCK, so the clause going RED is the proof.
     None),

    ("a run that finished on its own is overwritten instead of skipped",
     DEPLOY,
     "        if run.is_finished:",
     "        if False:",
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_a_run_that_finished_on_its_own_is_skipped",
     # ⛔ no must_vanish: `is_finished` also appears in 7b's explanatory COMMENT. That is precisely
     # why _attribution_block strips comments — the raw scan was VACUOUS and this proof found it.
     None),

    # NF1.7(a): an unevaluable probe scored as "nothing to do" is the silent pre-fix behaviour.
    ("an unverifiable snapshot is silently treated as an empty set",
     DEPLOY,
     '  log "  ALERT: could not snapshot in-flight runs before the recreate',
     '  log "  could not snapshot in-flight runs before the recreate',
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_an_unverifiable_snapshot_attributes_nothing_and_says_so",
     None),

    ("a failed attribution rolls back an otherwise healthy deploy",
     DEPLOY,
     '    || log "  WARN: attribution step failed',
     '    || rollback "attribution step failed',
     DEPLOY_SUITE,
     "TestADeployAttributesTheRunsItKills::test_a_failed_attribution_never_rolls_back_a_healthy_deploy",
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
