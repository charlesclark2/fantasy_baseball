"""RED proof for the E11.26 guards — `uv run python betting_ml/tests/e11_26_red_proof.py`.

The defect this story fixes has no visible signature in source: every subprocess on
`intraday_schedule_job`'s chain ALREADY passed `timeout=`, and the job still ran >1h. A guard
suite over a defect that looks like working code is worth exactly its falsifiability, so each
claim is proved by re-introducing a real regression and requiring the named test to go RED.

Three ways a RED proof lies, all guarded here:
  * the mutation never LANDS (E11.24 #682)          → the source is re-read and diffed.
  * the anchor is NOT UNIQUE (E11.24 prediction_log) → each anchor must occur exactly once.
  * the mutation lands but does not MOVE the asserted predicate (E11.24 #815) → where the
    assertion is "token X is present", the post-mutation source is checked for X's ABSENCE.

⚠️ I1 is deliberately absent below: with three live legs it is IMPLIED by I3, so no mutation
breaks it alone (see intraday_tick_budget's docstring). Claiming a fixture for it would be the
vacuous-isolation shape this repo keeps hitting.

Restores every file in a `finally`, so an interrupted run cannot leave a break on disk.
Runtime ~2 min (each case spawns a pytest). Exits non-zero if ANY break stays green.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_e11_26_intraday_tick_budget.py"

OPS = "pipeline/ops/intraday_ops.py"
JOBS = "pipeline/jobs/intraday_jobs.py"
BUDGET = "betting_ml/monitoring/intraday_tick_budget.py"
RUNNER = "betting_ml/utils/bounded_subprocess.py"
ALERTING = "pipeline/utils/alerting.py"
DAGSTER_YAML = "services/dagster/dagster.yaml"
SCHEDULES = "pipeline/schedules/intraday_schedules.py"

# (label, file, old, new, "<test file>::<test name>", gone_token_or_None)
#   gone_token: a substring that MUST disappear from the file after the mutation. Only meaningful
#   where the guard asserts presence — it is what distinguishes "the break landed" from "the break
#   landed somewhere that does not move the assertion".
BREAKS = [
    # ── the mechanism: the child (and its tree) really dies ─────────────────────────────────
    ("run_bounded stops isolating the process group (grandchildren orphaned)", RUNNER,
     "        start_new_session=True,  # own process group → the whole tree is killable\n",
     "",
     f"{TEST}::test_the_grandchild_is_killed_too", "        start_new_session=True,"),
    ("run_bounded stops killing on a non-timeout interruption (Dagster termination)", RUNNER,
     "    except BaseException:\n"
     "        # Dagster run-monitoring termination / KeyboardInterrupt / anything else. The child must\n"
     "        # NOT survive the op that started it.\n"
     "        _terminate_group(proc)\n"
     "        _drain(proc)\n"
     "        raise\n",
     "",
     f"{TEST}::test_an_interruption_also_kills_the_child", None),
    ("run_bounded escalates only to SIGTERM, never SIGKILL", RUNNER,
     "    for sig in (signal.SIGTERM, signal.SIGKILL):",
     "    for sig in (signal.SIGTERM,):",
     f"{TEST}::test_a_child_that_IGNORES_sigterm_is_still_killed", "signal.SIGKILL)"),
    ("run_bounded stops guarding against signalling the CALLER's own process group", RUNNER,
     "    if pgid == os.getpgid(0):",
     "    if False:",
     f"{TEST}::test_it_never_signals_the_callers_own_process_group", "if pgid == os.getpgid(0):"),
    ("run_bounded gains an unbounded default timeout", RUNNER,
     "    if timeout is None or timeout <= 0:\n"
     "        raise ValueError(\"run_bounded requires a finite positive timeout\")\n",
     "",
     f"{TEST}::test_run_bounded_refuses_an_unbounded_call", None),

    # ── the wiring: _run_script must delegate to it ──────────────────────────────────────────
    ("_run_script reverts to subprocess.run (kills only the direct child)", OPS,
     "        result = run_bounded(cmd, env=env, cwd=APP_DIR, timeout=timeout)",
     "        result = subprocess.run(cmd, env=env, capture_output=True, text=True, "
     "cwd=APP_DIR, timeout=timeout)",
     f"{TEST}::test_run_script_delegates_to_the_process_group_killer", "run_bounded(cmd"),

    # ── the budget reaches every leg (I4) ───────────────────────────────────────────────────
    ("the two lakehouse rebuild legs fall back to the 1800s module default", OPS,
     '            _run_script(context, "run_w1_lakehouse.py", [_flag], timeout=_TICK_LEG_TIMEOUT)',
     '            _run_script(context, "run_w1_lakehouse.py", [_flag])',
     f"{TEST}::test_every_tick_leg_passes_the_cadence_derived_timeout", None),
    ("the ext-table refresh leg falls back to the 1800s module default", OPS,
     '            _run_script(context, "refresh_w1_external_tables.py", timeout=_TICK_LEG_TIMEOUT)',
     '            _run_script(context, "refresh_w1_external_tables.py")',
     f"{TEST}::test_every_tick_leg_passes_the_cadence_derived_timeout", None),
    ("the schedule-ingest leg falls back to the 1800s module default", OPS,
     '        "--capture-reason", "intraday_gameday",\n    ], timeout=_TICK_LEG_TIMEOUT)',
     '        "--capture-reason", "intraday_gameday",\n    ])',
     f"{TEST}::test_every_tick_leg_passes_the_cadence_derived_timeout", None),
    ("the SF lineup dbt leg falls back to the 1800s module default", OPS,
     '        "--target", "baseball_betting_and_fantasy",\n    ], timeout=_TICK_LEG_TIMEOUT)',
     '        "--target", "baseball_betting_and_fantasy",\n    ])',
     f"{TEST}::test_every_tick_leg_passes_the_cadence_derived_timeout", None),
    ("a leg is hand-tuned to a literal instead of the cadence-derived constant", OPS,
     '            _run_script(context, "run_w1_lakehouse.py", [_flag], timeout=_TICK_LEG_TIMEOUT)',
     '            _run_script(context, "run_w1_lakehouse.py", [_flag], timeout=900)',
     f"{TEST}::test_every_tick_leg_passes_the_cadence_derived_timeout", None),

    # ── the job-level ceiling + the anti-stacking tag ────────────────────────────────────────
    ("intraday_schedule_job loses its dagster/max_runtime ceiling", JOBS,
     "        MAX_RUNTIME_SECONDS_TAG: str(_TICK_MAX_RUNTIME),\n",
     "",
     f"{TEST}::test_the_job_carries_a_ceiling_below_its_cadence", "MAX_RUNTIME_SECONDS_TAG:"),
    ("the ceiling is hard-coded instead of derived from the cadence", JOBS,
     "        MAX_RUNTIME_SECONDS_TAG: str(_TICK_MAX_RUNTIME),",
     "        MAX_RUNTIME_SECONDS_TAG: \"1500\",",
     f"{TEST}::test_the_job_carries_a_ceiling_below_its_cadence", "str(_TICK_MAX_RUNTIME)"),
    ("intraday_schedule_job loses its concurrency_group (ticks may stack again)", JOBS,
     '        "concurrency_group": "intraday_schedule",\n',
     "",
     f"{TEST}::test_the_job_carries_a_ceiling_below_its_cadence",
     '"concurrency_group": "intraday_schedule"'),
    ("the Dagster instance stops enforcing concurrency_group (the tag goes inert)", DAGSTER_YAML,
     '      - key: "concurrency_group"',
     '      - key: "some_other_key"',
     f"{TEST}::test_the_dagster_instance_actually_enforces_the_concurrency_group",
     'key: "concurrency_group"'),

    # ── the invariants (I2 and I3 only — see the module note on I1) ──────────────────────────
    ("I2: the ceiling is raised to the tick cadence, so a run can outlive its successor", BUDGET,
     "MAX_RUNTIME_SECONDS = 1500",
     "MAX_RUNTIME_SECONDS = 1800",
     f"{TEST}::test_the_budget_invariants_hold", None),
    ("I3: leg caps are raised until the live budget exceeds the ceiling", BUDGET,
     "LEG_TIMEOUT_SECONDS = 480",
     "LEG_TIMEOUT_SECONDS = 600",
     f"{TEST}::test_the_budget_invariants_hold", None),
    ("the cadence constant drifts away from the actual cron", BUDGET,
     "TICK_CADENCE_SECONDS = 1800",
     "TICK_CADENCE_SECONDS = 3600",
     f"{TEST}::test_the_cadence_constant_matches_the_actual_cron", None),
    ("the cron is shortened without re-deriving the budget", SCHEDULES,
     '    job=intraday_schedule_job,\n    cron_schedule="*/30 14-23 * * *",',
     '    job=intraday_schedule_job,\n    cron_schedule="*/15 14-23 * * *",',
     f"{TEST}::test_the_cadence_constant_matches_the_actual_cron", None),

    # ── the two PRE-EXISTING guards this story re-anchored must still bite ───────────────────
    # E11.26 moved their anchors (the call gained `timeout=`). A re-anchor that quietly stops
    # falsifying is indistinguishable from deleting the guard, so both are re-proved here.
    ("(re-anchored) the ext refresh is removed outright instead of gated", OPS,
     '            _run_script(context, "refresh_w1_external_tables.py", timeout=_TICK_LEG_TIMEOUT)',
     "            pass",
     "betting_ml/tests/test_cost_wake_gates.py::TestTickSfFreeStep3::"
     "test_ext_refresh_is_gated_not_removed",
     '"refresh_w1_external_tables.py", timeout=_TICK_LEG_TIMEOUT)'),
    ("(re-anchored) the ext refresh is removed, breaking the tick's ordering invariant", OPS,
     '            _run_script(context, "refresh_w1_external_tables.py", timeout=_TICK_LEG_TIMEOUT)',
     "            pass",
     "betting_ml/tests/test_lineup_intraday_wide_rebuild.py::"
     "test_intraday_schedule_rebuilds_lineups_wide_after_games_and_before_refresh",
     '"refresh_w1_external_tables.py", timeout=_TICK_LEG_TIMEOUT)'),

    # ── the alerting path stays bounded ──────────────────────────────────────────────────────
    ("the SNS publish reverts to botocore's ~5-minute defaults", ALERTING,
     '        boto3.client("sns", region_name=_region(), config=_sns_cfg).publish(',
     '        boto3.client("sns", region_name=_region()).publish(',
     f"{TEST}::test_the_sns_publish_is_bounded", "config=_sns_cfg"),
]


_BAK = ".e11_26_red_proof.bak"


def _restore_stale_backups() -> None:
    """A signal-killed run does not execute `finally`, so it can leave a deliberate break ON DISK
    where it is one `git add` away from being committed. This happened during E11.26's own
    development: deleting `start_new_session=True` made `killpg` reach this very process. The
    same-group guard now makes that impossible, but a proof that mutates source must be safe
    against its own worst case, not against the one bug it happens to know about."""
    for rel in {b[1] for b in BREAKS}:
        bak = REPO / (rel + _BAK)
        if bak.exists():
            (REPO / rel).write_text(bak.read_text())
            bak.unlink()
            print(f"RESTORED     {rel} from a stale backup (a previous run died mid-mutation)")


def main() -> int:
    _restore_stale_backups()
    failures = []
    for label, rel, old, new, test, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        occurrences = original.count(old)
        if occurrences != 1:
            print(f"SETUP-ERROR  {label}\n             anchor occurs {occurrences}x in {rel} "
                  f"(need exactly 1) — the proof is stale/ambiguous, NOT passing")
            failures.append(label)
            continue
        bak = REPO / (rel + _BAK)
        bak.write_text(original)
        path.write_text(original.replace(old, new, 1))
        try:
            mutated = path.read_text()
            # The mutation must be OBSERVABLE, or "the guard caught it" and "the break never
            # happened" are indistinguishable (E11.24 #682).
            assert mutated != original, f"mutation did not land for {label}"
            # ...and where the guard asserts a token is PRESENT, that token must now be ABSENT,
            # or the break landed somewhere the assertion cannot see (E11.24 #815).
            if gone is not None and gone in mutated:
                print(f"SETUP-ERROR  {label}\n             {gone!r} survived the mutation — the "
                      "break does not move the asserted predicate, NOT passing")
                failures.append(label)
                continue
            proc = subprocess.run(
                ["uv", "run", "pytest", test, "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True)
            red = proc.returncode != 0
        finally:
            path.write_text(original)
            bak.unlink(missing_ok=True)
        print(f"{'RED  ✅' if red else 'GREEN ❌'}  {label}")
        if not red:
            failures.append(label)

    print(f"\n{len(BREAKS) - len(failures)}/{len(BREAKS)} breaks caught")
    if failures:
        print("STAYED GREEN (the guard is vacuous — fix the guard, not the proof):")
        for label in failures:
            print(f"  - {label}")
        return 1
    print("every E11.26 guard is falsifiable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
