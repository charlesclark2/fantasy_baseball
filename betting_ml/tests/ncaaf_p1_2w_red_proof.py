#!/usr/bin/env python3
"""NCAAF-P1.2W RED PROOF — break the source one defect at a time, require the NAMED clause to fail.

    uv run python betting_ml/tests/ncaaf_p1_2w_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_ncaaf_p1_2w_weekly_refit.py` is refactored.

WHY THIS SUITE IN PARTICULAR NEEDS IT. Its subject is a job that PASSES while doing nothing — the
whole defect class is "green and wrong" — so a guard that is itself green and wrong would be
invisible in exactly the same way. Two of these clauses were ALREADY vacuous when first written and
neither was found by reading them: the `LastModified` ban was satisfied by the module docstring
SAYING it never reads an mtime, and the "never raises" ban was satisfied by a docstring containing
the word. Both are in `CASES` below, so a future refactor that re-introduces a prose-satisfiable
scan is caught rather than discovered.

THE FOUR CONTROLS, all of which this repo has paid for:

  1. **BASELINE-PASS** — every named clause is proven GREEN on unbroken source first. A clause
     already failing would be reported RED by every break.
  2. **NOT-SELECTED** — a mistyped or stale test id makes pytest select nothing and exit NON-ZERO,
     which a naive `returncode != 0` reads as "the clause went red": the harness reporting its
     strongest result for a clause it never ran. A false RED is the dangerous direction.
  3. **UNIQUE ANCHOR** — a `replace(old, new, 1)` against a non-unique anchor lands wherever the
     first match happens to be, leaving the clause untouched and the harness reporting a FALSE
     "GREEN — VACUOUS" (NF-INJ2b). An anchor seen more than once is AMBIGUOUS-ANCHOR, never applied.
  4. **THE BREAK MUST MOVE THE ASSERTED PREDICATE** (#815) — a mutation that lands on disk but does
     not change what the clause reads comes back GREEN and reads as a real finding. Where a break
     removes a token, the harness asserts the token is actually GONE from the patched source.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`,
which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

POLICY = REPO / "betting_ml/monitoring/ncaaf_strength_refit.py"
FRESH = REPO / "betting_ml/monitoring/sports_delta_freshness.py"
JOB = REPO / "pipeline/jobs/sports_ncaaf_strength_refit_job.py"
SCHEDULE = REPO / "pipeline/schedules/sports_ncaaf_strength_refit_schedules.py"
SNAPSHOT = REPO / "pipeline/jobs/sports_ncaaf_prediction_snapshot_job.py"
HEALTH = REPO / "betting_ml/monitoring/monitor_health.py"
BOX_OPS = REPO / "services/dagster/aws/BOX_OPERATIONS.md"

SUITE = "betting_ml/tests/test_ncaaf_p1_2w_weekly_refit.py"

#: (label, file, find, replace, test id, token-that-must-vanish-or-None)
CASES: list[tuple[str, Path, str, str, str, str | None]] = [
    # ══ the discriminator ══════════════════════════════════════════════════════════════════
    # ⭐ THE ONE THIS STORY EXISTS FOR. The NCAAF-PS report's operator SQL is the obvious check to
    # schedule, and ON ITS OWN it certifies the frozen artifact (measured: 136/136/138 with
    # as_of_week 1 and a vintage that had not moved since 2026-08-18).
    ("the vintage-advance reading is dropped, leaving only the covariate check",
     POLICY,
     "    if before.readable and not _advanced(before, after):",
     "    if False:",
     "test_the_covariate_check_alone_would_certify_the_frozen_artifact", None),

    ("the cold-start reading is dropped",
     POLICY,
     "    zero = [g for g in DISCRIMINATING_COVARIATES if not after.covariate_nonzero.get(g)]",
     "    zero = []",
     "test_a_cold_start_reproduction_fails_the_run_rather_than_passing_it", None),

    # NF1.7(a)/NF-D20: the check that would have caught THIS story's gap.
    ("the week-index reading is dropped",
     POLICY,
     "    if completed_games > 0 and (after.max_as_of_week or 0) <= 1:",
     "    if False:",
     "test_the_week_index_check_refuses_a_prior_that_absorbed_no_played_week", None),

    # ⚠️ THIS BREAK WAS TOO WEAK ON ITS FIRST CUT and the harness reported GREEN — VACUOUS: it
    # deleted the phrase "Inactive, not passed." while the word INACTIVE survived a few characters
    # earlier, so the mutation LANDED without moving the predicate the clause reads (#815). The
    # `must_vanish` column is the control for exactly that, and it now names the real token.
    ("a pre-season run reports the inactive week check as a pass",
     POLICY,
     'f"{_landed(after)} \u2139\ufe0f the week-index check is INACTIVE: the marts hold no "',
     'f"{_landed(after)} The run is green. Ignoring: "',
     "test_the_week_index_check_declares_itself_inactive_pre_season_rather_than_passing",
     # ⛔ no `must_vanish` here, and deliberately: that control scans the PATCHED SOURCE, and the
     # word INACTIVE also appears in this module's docstring explaining the rule. The clause is
     # BEHAVIOURAL — it reads the returned `detail` string — so the break is proven by the clause
     # going red, not by the token leaving the file.
     None),

    ("an unreadable marts count silently disables the week check",
     POLICY,
     "    except Exception:  # noqa: BLE001 — UNEVALUABLE, reported by the caller, never a silent 0\n        return None",
     "    except Exception:  # noqa: BLE001\n        return 0",
     "test_an_unreadable_completed_game_count_is_unevaluable_not_a_free_pass", None),

    ("the vintage advance is decided on the clock instead of the Delta version",
     POLICY,
     "    return after.version > before.version",
     "    return (after.commit or before.commit) > before.commit",
     "test_the_vintage_advance_is_decided_on_the_delta_version_not_a_clock", None),

    # ⭐ THE CLAUSE THAT WAS VACUOUS WHEN FIRST WRITTEN: the module docstring says "never an S3
    # LastModified", which a comment-only strip left in place and which satisfied the ban. This
    # break puts a real mtime read in the CODE; a prose-satisfiable scan stays green on it.
    ("the vintage is read from an S3 LastModified",
     POLICY,
     "    reading = SDF.read_contract(contract, bucket=bucket, local_root=local_root)",
     "    reading = SDF.read_contract(contract, bucket=bucket, local_root=local_root)\n"
     "    _ = {'LastModified': None}",
     "test_the_vintage_is_read_from_the_delta_log_and_never_from_an_mtime", None),

    # ══ the job ════════════════════════════════════════════════════════════════════════════
    # INC-40: source ORDER is not execution order under in_process_executor; only the edge is.
    ("the fit stops being downstream of the marts rebuild",
     JOB,
     "            start=ncaaf_strength_fit_op(\n                start=ncaaf_strength_marts_rebuild_op(\n                    start=ncaaf_strength_precondition_op()))",
     "            start=ncaaf_strength_fit_op(\n                start=ncaaf_strength_precondition_op()))",
     "test_the_marts_rebuild_runs_before_the_fit_inside_this_job", None),

    ("the serving publish moves upstream of the verification",
     JOB,
     "    ncaaf_serving_write_after_snapshot_op(\n        start=ncaaf_strength_verify_op(",
     "    ncaaf_strength_verify_op(\n        start=ncaaf_serving_write_after_snapshot_op(",
     "test_every_node_in_the_job_resolves_and_the_serving_write_is_last", None),

    ("a cold-start reproduction pages but leaves the run green",
     JOB,
     '    raise Exception(f"NCAAF strength re-fit verification FAILED ({verdict[\'verdict\']}): "\n                    f"{verdict[\'detail\']}")',
     "    return",
     "test_the_verify_step_raises_rather_than_logging_a_warning", None),

    ("the job re-implements the fit instead of invoking the shipped CLI",
     JOB,
     '        "quant_sports_intel_models.football.ncaaf.models.run_team_strength",',
     '        "quant_sports_intel_models.football.ncaaf.models.team_strength",  # run_strength(',
     "test_the_fit_invokes_the_shipped_p1_2_cli_rather_than_reimplementing_it", None),

    ("the fit subprocess goes back to an unbounded-group kill",
     JOB,
     "        result = run_bounded(cmd, env=env, cwd=_repo_root(), timeout=REFIT_TIMEOUT_SECONDS)",
     "        result = subprocess.run(cmd, env=env, cwd=_repo_root(), capture_output=True,\n"
     "                                text=True, timeout=REFIT_TIMEOUT_SECONDS)",
     "test_the_fit_subprocess_is_bounded_and_kills_its_process_group", "run_bounded("),

    # NF-INFRA1: four owners each with their own default is how a build wrote one file while the
    # consumer read another.
    ("the job hardcodes a DuckDB path instead of resolving it",
     JOB,
     '    duckdb_path = resolve_sports_duckdb()',
     '    duckdb_path = Path("/tmp/sports_ncaaf.duckdb")',
     "test_the_job_resolves_the_duckdb_path_through_the_one_owner", None),

    ("the runtime ceiling drops below the legs it is supposed to bound",
     JOB,
     'os.environ.get("NCAAF_STRENGTH_REFIT_MAX_RUNTIME_S", "10800")',
     'os.environ.get("NCAAF_STRENGTH_REFIT_MAX_RUNTIME_S", "600")',
     "test_the_job_carries_a_runtime_ceiling_above_its_own_legs_and_below_its_cadence", None),

    # ══ sequencing ═════════════════════════════════════════════════════════════════════════
    # INC-25: the cron offset is a courtesy; a re-fit over stale raw SUCCEEDS and stamps a fresh
    # date on the served "ratings as of" line, which is worse than failing.
    ("the raw-freshness precondition stops refusing",
     JOB,
     '        raise Exception(f"NCAAF strength re-fit precondition failed — {raw_verdict[\'detail\']}")',
     "        pass",
     "test_the_job_refuses_to_fit_on_stale_raw_rather_than_trusting_the_cron_offset", None),

    ("the re-fit is moved onto the roll-forward's own instant",
     SCHEDULE,
     'NCAAF_STRENGTH_REFIT_CRON = "30 7 * " + ",".join(str(m) for m in SEASON_MONTHS) + " 1"',
     'NCAAF_STRENGTH_REFIT_CRON = "0 6 * " + ",".join(str(m) for m in SEASON_MONTHS) + " 1"',
     "test_the_refit_fires_after_the_roll_forward_and_not_at_its_instant", None),

    ("the cron fires daily instead of weekly in season",
     SCHEDULE,
     '+ " 1"',
     '+ " *"',
     "test_the_refit_fires_on_a_monday_inside_the_declared_season", None),

    ("the cron re-types its month range beside the SLA's",
     SCHEDULE,
     '"30 7 * " + ",".join(str(m) for m in SEASON_MONTHS) + " 1"',
     '"30 7 * 8-12,1 1"',
     "test_the_cron_month_field_is_built_from_the_season_window_not_retyped", "SEASON_MONTHS)"),

    # ══ monitoring ═════════════════════════════════════════════════════════════════════════
    ("the SLA is tightened below the weekly cadence it judges",
     FRESH,
     "        max_lag_hours=192.0,",
     "        max_lag_hours=24.0,",
     "test_the_ratings_have_a_freshness_contract_sized_to_the_weekly_cadence", None),

    # ⚠️ ALSO TOO WEAK ON ITS FIRST CUT (170.0 still clears a 168h week, so the clause was right to
    # stay green). The break has to cross the cadence it judges to test the two-sided assertion.
    ("a healthy Monday-to-Monday gap starts paging",
     FRESH,
     "        max_lag_hours=192.0,",
     "        max_lag_hours=120.0,",
     "test_a_missed_monday_is_stale_and_a_healthy_week_is_not", None),

    # ⭐ The off-season half, broken the way it is easiest to get wrong: SUPPRESS the check while
    # `now` is out of window instead of counting only active time. That passes the May clause and
    # false-pages on the FIRST August read, which is what the two-sided fixture exists to catch.
    ("the off-season is a suppressed check rather than an active-window clock",
     FRESH,
     "    start = max(last_commit, active_window_start(now, active_months))\n    return active_minutes_between(start, now, None, None, active_months) / 60.0",
     "    return max(0.0, (now - last_commit).total_seconds() / 3600.0)",
     "test_the_off_season_gap_is_idle_by_declaration_rather_than_a_breach", None),

    # MH2.7: a shared instrument's change must not re-decide the guards that pin its output.
    ("the active window leaks into contracts that never declared one",
     FRESH,
     "    if active_months is None:\n        return max(0.0, (now - last_commit).total_seconds() / 3600.0)",
     "    if active_months is None:\n        active_months = _NCAAF_SEASON_MONTHS",
     "test_the_active_window_does_not_change_any_pre_existing_contract", None),

    # NF-INFRA2: a monitor hosted inside its own subject cannot see its subject stop.
    ("the ratings monitor is moved inside the job it watches",
     SNAPSHOT,
     "    ncaaf_ratings_freshness_op()",
     "    pass",
     "test_the_ratings_monitor_is_not_hosted_inside_the_job_it_watches", None),

    ("the ratings monitor becomes downstream of the snapshot that can raise",
     SNAPSHOT,
     "    ncaaf_ratings_freshness_op()",
     "    ncaaf_ratings_freshness_op(start=ncaaf_prediction_snapshot_op())",
     "test_the_ratings_monitor_is_not_hosted_inside_the_job_it_watches", None),

    # ⭐ THE SECOND CLAUSE THAT WAS VACUOUS WHEN FIRST WRITTEN: the op's docstring contains "never
    # raises", which satisfied a ban on `raise` until docstrings were stripped too.
    ("the ratings SLA logs instead of paging (E11.30)",
     SNAPSHOT,
     '    send_alert(f"NCAAF strength ratings {verdict[\'verdict\']}", body,',
     '    _unsent = (f"NCAAF strength ratings {verdict[\'verdict\']}", body,',
     "test_the_ratings_monitor_pages_and_never_raises", "send_alert("),

    ("the ratings SLA raises and turns a deadline-critical snapshot run red",
     SNAPSHOT,
     '    context.log.warning("ALERT [ncaaf ratings sla] %s — %s", verdict["verdict"], body)',
     '    raise Exception(body)',
     "test_the_ratings_monitor_pages_and_never_raises", None),

    # ══ activation ═════════════════════════════════════════════════════════════════════════
    # The deploy-held boundary, broken from BOTH sides: the flag stops gating, and the flag gates
    # on something an empty/typo'd env var satisfies.
    ("a tick fires with the deploy-held flag unset",
     SCHEDULE,
     "    if not refit_enabled():",
     "    if False:",
     "test_the_skip_is_loud_and_names_the_flag_rather_than_being_silent", None),

    ("a present-but-empty flag arms the weekly re-fit",
     SCHEDULE,
     'return (source.get(REFIT_ENABLED_FLAG) or "").strip() == "1"',
     "return REFIT_ENABLED_FLAG in source",
     "test_a_tick_fires_nothing_until_the_operator_sets_the_flag", None),

    ("the skip goes silent instead of naming the flag and its artifact-side visibility",
     SCHEDULE,
     # ⚠️ ANCHORED ON THE CLAUSE'S OWN SUBJECT (#815). A first cut broke the SkipReason's
     # OPENING and came back GREEN — VACUOUS: the flag name appears AGAIN in the "TO ENABLE:"
     # sentence further down, so the mutation landed without moving either asserted predicate.
     # What this clause uniquely tests is that the skip says the un-armed state is VISIBLE from
     # the artifact side — the thing separating this flag from the documented-but-never-set class.
     'f"freshness contract will say so within ~8 active days',
     'f"nothing else will report it',
     "test_the_skip_is_loud_and_names_the_flag_rather_than_being_silent", None),

    # ⭐ NF-CAP1: a STOPPED-default schedule in CRITICAL_SCHEDULES cannot see the revert that
    # matters (a wiped toggle leaves no persisted row), so the entry would read as coverage it does
    # not have — and it breaks E11.23's ratified "permanently on" invariant besides.
    ("the schedule stops self-starting, making its heartbeat entry vacuous",
     SCHEDULE,
     "    default_status=DefaultScheduleStatus.RUNNING,",
     "    default_status=DefaultScheduleStatus.STOPPED,",
     "test_the_schedule_self_starts_so_the_heartbeat_entry_is_not_vacuous", None),

    ("the schedule leaves the heartbeat's required-RUNNING set",
     HEALTH,
     '    "sports_ncaaf_strength_refit_schedule",',
     "",
     "test_the_schedule_self_starts_so_the_heartbeat_entry_is_not_vacuous",
     '"sports_ncaaf_strength_refit_schedule",'),

    ("the intended state disappears from BOX_OPERATIONS §10",
     BOX_OPS,
     "| `sports_ncaaf_strength_refit_schedule` |",
     "| `a_schedule_that_does_not_exist` |",
     "test_the_box_operations_table_records_the_intended_state", None),
]


def run_one(test_id: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED"."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_id}", "-q", "--no-header",
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
    baseline = {t: run_one(t) for *_, t, _ in CASES}
    bad = {t: v for t, v in baseline.items() if v != "PASSED"}
    if bad:
        for t, v in bad.items():
            print(f"🚨 baseline: {t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1
    print(f"  all {len(baseline)} green ✅\n")

    results = []
    try:
        for label, path, find, replace, test_id, must_vanish in CASES:
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
            # #815 — a mutation that lands but does not move the asserted predicate comes back
            # GREEN and reads as a real finding. Where the break is a REMOVAL, prove the removal.
            if must_vanish is not None and must_vanish in patched:
                results.append((label, f"BREAK-DID-NOT-REMOVE {must_vanish!r}"))
                continue
            path.write_text(patched)
            try:
                outcome = run_one(test_id)
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
