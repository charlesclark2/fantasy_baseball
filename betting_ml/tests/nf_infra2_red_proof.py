"""RED proof for NF-INFRA2's guards — `uv run python betting_ml/tests/nf_infra2_red_proof.py`.

The defect this story guards against produces NO error and NO log line: the board publish schedule
stops, and every producer-side instrument stays green because there is no run to be red. A suite
over a failure whose signature is "everything looks fine" is worth exactly its falsifiability, so
each claim is proved by re-introducing a real defect and requiring the named test to go RED.

Applies each break IN-PROCESS and ASSERTS THE SOURCE ACTUALLY CHANGED before running pytest — a
red proof whose mutation silently no-ops reports a triumphant, false "the guard caught it"
(E11.24 #682). It also asserts the mutated token is GONE where the guard reads a token, because a
break that lands but does not move the asserted predicate is a false GREEN (E11.24 #815), and that
the anchor is UNIQUE in the file, because two byte-identical tails make `replace(...,1)` mutate the
WRONG function and report a false VACUITY (E11.24 prediction_log). Restores the file in a
`finally`, and sweeps stale `.orig` backups at start-up, so an interrupted run cannot leave a break
on disk.

⚠️ NOT SCHEDULED — the known limitation `nf_infra1_red_proof.py` / `nf_fresh2_red_proof.py` both
record: like the repo's other `*_red_proof.py` harnesses this runs only when somebody types the
command, and E9.64 measured what that costs (six red-proof cases had silently gone vacuous).
Wiring the Python red proofs into a scheduled workflow is worth doing and is deliberately not
smuggled into this story.

Runtime ~30s. Prints one line per case; exits non-zero if ANY break stays green.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
T = "betting_ml/tests/test_nf_infra2_board_publish_sla.py"
# The NF-INFRA1 guard this story RE-ANCHORED (its job-graph node set now includes the
# board SLA leg). Re-anchoring a guard onto a new implementation is only honest if the
# re-anchored clause is still falsifiable — MH2.7's "re-anchor, don't weaken".
T_INFRA1 = "betting_ml/tests/test_nf_infra1_sleeper_hardening.py"

NBF = "betting_ml/monitoring/nfl_board_freshness.py"
SLEEPER_JOB = "pipeline/jobs/sports_nfl_sleeper_injuries_job.py"
PUBLISH_JOB = "pipeline/jobs/sports_nfl_board_publish_job.py"
SCHEDULES = "pipeline/schedules/sports_rollforward_schedules.py"

# (label, file, old, new, "<test file>::<test name>")
BREAKS = [
    # ── the SLA must be sized against the OBSERVED lag, not the cadence ─────────────────────
    ("the grace is dropped, so the SLA tolerates 45 min of lateness", NBF,
     "DAILY_GRACE_HOURS = 6.75", "DAILY_GRACE_HOURS = 0.0",
     f"{T}::test_the_sla_exceeds_the_lag_a_perfectly_healthy_board_already_carries"),
    ("the SLA is inflated past a skipped cycle (the event it exists for)", NBF,
     "DAILY_GRACE_HOURS = 6.75", "DAILY_GRACE_HOURS = 600.0",
     f"{T}::test_a_skipped_publish_is_over_the_sla_on_both_cadences"),
    ("the draft-season boundary lookback is removed (false page on Aug 1)", NBF,
     "CADENCE_BOUNDARY_LOOKBACK_DAYS = 2", "CADENCE_BOUNDARY_LOOKBACK_DAYS = 0",
     f"{T}::test_the_draft_season_boundary_uses_the_LOOSER_weekly_sla"),

    # ── classify: the stopped-schedule detector ─────────────────────────────────────────────
    ("a stale published board never fires", NBF,
     "    if lag_hours > bar:", "    if lag_hours > 1e9:",
     f"{T}::test_a_frozen_board_is_STALE_and_carries_a_paging_severity"),
    ("a long freeze stops escalating to CRITICAL", NBF,
     '        severity = "WARN" if lag_hours <= 2 * bar else "CRITICAL"',
     '        severity = "WARN"',
     f"{T}::test_a_long_freeze_escalates_to_CRITICAL"),
    ("an unreadable published board is scored HEALTHY (NF1.7(a))", NBF,
     '            "name": "nfl_published_board", "verdict": "UNKNOWN", "severity": "WARN",',
     '            "name": "nfl_published_board", "verdict": "OK", "severity": None,',
     f"{T}::test_an_unreadable_board_is_UNVERIFIED_never_healthy"),
    ("the stale page stops naming the schedule to check (INC-40 anchoring)", NBF,
     '                "sports_nfl_board_publish_schedule is RUNNING in Dagit and read its most recent "',
     '                "the pipeline is healthy and read its most recent "',
     f"{T}::test_the_stale_page_names_the_stopped_schedule_as_the_first_thing_to_check"),

    # ── verify_manifest: the publish-time artifact guards ───────────────────────────────────
    ("a naive stamp is rejected, so the REAL board fails to publish", NBF,
     "    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)",
     "    return stamp if stamp.tzinfo else None",
     f"{T}::test_the_REAL_published_manifest_passes_clean"),
    ("a REUSED stale export is no longer fatal", NBF,
     "    elif generated < started - timedelta(minutes=2):", "    elif False:",
     f"{T}::test_a_REUSED_stale_export_is_FATAL"),
    ("a MISSING feed stamp is downgraded to an alert", NBF,
     "            stamps[stamp.name] = None\n            fatal.append(",
     "            stamps[stamp.name] = None\n            alerts.append(",
     f"{T}::test_a_MISSING_feed_stamp_is_FATAL"),
    ("a MISSING coherence block is downgraded to an alert (the guard vanishes silently)", NBF,
     '    if not isinstance(coherence, dict):\n        fatal.append(',
     '    if not isinstance(coherence, dict):\n        alerts.append(',
     f"{T}::test_a_MISSING_coherence_block_is_FATAL"),
    ("a STALE feed stamp is made FATAL, freezing the board over one late feed", NBF,
     "        if lag > stamp.max_lag_hours:\n            alerts.append(",
     "        if lag > stamp.max_lag_hours:\n            fatal.append(",
     f"{T}::test_a_STALE_but_present_stamp_ALERTS_and_does_NOT_block_the_publish"),
    ("a non-OK injury coherence verdict stops alerting", NBF,
     '        elif verdict != "OK":', "        elif False:",
     f"{T}::test_a_non_OK_injury_coherence_verdict_ALERTS"),
    ("an ABSENT injury verdict is treated as fine rather than UNVERIFIED", NBF,
     "        if verdict is None:", "        if False:",
     f"{T}::test_an_injury_verdict_that_is_ABSENT_is_reported_UNVERIFIED_not_healthy"),

    # ── wiring: where the monitor lives, and what it is NOT downstream of ───────────────────
    ("the board SLA op is never invoked by the daily job", SLEEPER_JOB,
     "    nfl_published_board_freshness_op()\n", "    pass\n",
     f"{T}::test_the_board_sla_op_is_INVOKED_by_the_daily_job_not_merely_defined"),
    ("the board SLA leg is dropped from the daily job's compiled graph", SLEEPER_JOB,
     "    nfl_published_board_freshness_op()\n", "    pass\n",
     f"{T_INFRA1}::test_the_freshness_check_runs_downstream_of_the_land_as_a_graph_edge"),
    ("the board SLA op is hung off the Sleeper ingest (an outage blinds it)", SLEEPER_JOB,
     "    nfl_published_board_freshness_op()", "    nfl_published_board_freshness_op(start=landed)",
     f"{T}::test_the_board_sla_op_is_INDEPENDENT_so_a_sleeper_outage_cannot_blind_it"),
    ("publish verification stops delegating to the pure policy (un-RED-provable again)",
     PUBLISH_JOB,
     "    result = NBF.verify_manifest(blob, started=started)",
     '    result = {"fatal": [], "alerts": [], "stamps": {}}',
     f"{T}::test_the_publish_verification_delegates_to_the_pure_policy"),
    ("a degraded input publishes SILENTLY (the alert page is removed)", PUBLISH_JOB,
     '    if result["alerts"]:', "    if False:",
     f"{T}::test_the_REAL_op_pages_on_a_degraded_input_and_still_publishes"),
    ("the build stops checking the Sleeper feed it is about to build on (INC-25)", PUBLISH_JOB,
     '        contract = SDF.by_name("nfl_sleeper_injuries")',
     "        contract = None",
     f"{T}::test_the_input_refresh_asserts_the_sleeper_feed_it_is_about_to_build_on"),

    # ── the schedule's own properties ───────────────────────────────────────────────────────
    ("the publish schedule reverts to shipping STOPPED (E11.23)", SCHEDULES,
     "    # NF-INFRA1 follow-up (2026-08-15): self-starts + heartbeat-checked — see below.\n"
     "    default_status=DefaultScheduleStatus.RUNNING,\n"
     ")\ndef sports_nfl_board_publish_schedule",
     "    default_status=DefaultScheduleStatus.STOPPED,\n"
     ")\ndef sports_nfl_board_publish_schedule",
     f"{T}::test_the_publish_schedule_still_self_starts"),
    ("the schedule re-declares its own cadence predicate (two owners drift apart)", SCHEDULES,
     "from betting_ml.monitoring.nfl_board_freshness import is_draft_season",
     "def is_draft_season(today):\n    return today.month == 8",
     f"{T}::test_the_schedule_and_the_sla_read_the_SAME_cadence_predicate"),
]


def _sweep_stale_backups() -> None:
    """A source-mutating proof's own worst case is being killed mid-mutation, which skips the
    `finally`. Restore anything a previous interrupted run left behind (E11.26)."""
    for orig in REPO.glob("**/*.nf_infra2_red_proof.orig"):
        target = orig.with_suffix("")
        target.write_text(orig.read_text())
        orig.unlink()
        print(f"restored a stale backup: {target.relative_to(REPO)}")


def _purge_pyc(path: Path) -> None:
    """Drop any cached bytecode for `path`, so the child process cannot import a pre-mutation
    version of the module we just broke. `.pyc` validity is (mtime, size) and both can collide."""
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(f"{path.stem}.*.pyc"):
            pyc.unlink(missing_ok=True)


def main() -> int:
    _sweep_stale_backups()
    failures = []
    for label, rel, old, new, test in BREAKS:
        path = REPO / rel
        original = path.read_text()
        # ⭐ A non-unique anchor makes `replace(..., 1)` mutate the WRONG occurrence and report a
        # FALSE vacuity — which reads as a real finding and invites weakening a correct guard.
        if original.count(old) != 1:
            print(f"SETUP-ERROR  {label}\n             anchor occurs {original.count(old)}x in "
                  f"{rel} (need exactly 1) — the proof is stale, NOT passing")
            failures.append(label)
            continue
        backup = path.with_suffix(path.suffix + ".nf_infra2_red_proof.orig")
        backup.write_text(original)
        path.write_text(original.replace(old, new, 1))
        try:
            mutated = path.read_text()
            # The mutation must be OBSERVABLE, and the asserted token must actually be GONE.
            assert mutated != original, f"mutation did not land for {label}"
            assert old not in mutated, f"mutation landed but left the token in place for {label}"
            _purge_pyc(path)
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test, "-q", "--no-header",
                 "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True,
                # ⛔ A stale `__pycache__` entry for the MUTATED module makes the child import the
                # PRE-BREAK code and report a triumphant "the guard is vacuous" — a FALSE FINDING,
                # which is the dangerous direction: it invites weakening a guard that is actually
                # fine. Measured on this harness's first run (one case flipped GREEN then RED on a
                # re-run with nothing changed). Belt and braces: purge the module's pyc above, and
                # forbid the child writing new ones.
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            red = proc.returncode != 0
        finally:
            path.write_text(original)
            backup.unlink(missing_ok=True)
        print(f"{'RED  ✅' if red else 'GREEN ❌'}  {label}")
        if not red:
            failures.append(label)

    print(f"\n{len(BREAKS) - len(failures)}/{len(BREAKS)} breaks caught")
    if failures:
        print("STAYED GREEN (the guard is vacuous — fix the guard, not the proof):")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("every NF-INFRA2 guard is falsifiable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
