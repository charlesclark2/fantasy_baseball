#!/usr/bin/env python
"""ncaaf_reserve_tier_red_proof.py — prove every re-serve-tier guard FAILS on a deliberate break.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / INC-39). One defect at a time
against the real source; each must produce a failure.

Guarded against the three ways a RED proof itself lies: the mutation never LANDED (#682), the
anchor was not UNIQUE so it landed on the wrong symbol (E11.24 — a false VACUITY report is the
dangerous direction, because it reads as a finding and invites weakening a correct guard), and it
landed but did not move the ASSERTED predicate (#815). Stale backups from a killed run are
restored at start-up (E11.26).

Run:  uv run python betting_ml/tests/ncaaf_reserve_tier_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TEST = "betting_ml/tests/test_ncaaf_reserve_tier.py"

WRITER = _REPO / "scripts/write_ncaaf_serving_store.py"
JOB = _REPO / "pipeline/jobs/sports_ncaaf_serving_write_job.py"
SCHED = _REPO / "pipeline/schedules/sports_ncaaf_serving_write_schedules.py"

# (label, file, anchor, replacement, pytest -k selector, token that must VANISH)
BREAKS: list[tuple[str, Path, str, str, str, str | None]] = [
    # ── 1. one window, shared with the capture ───────────────────────────────────────────────
    ("the re-serve carries its own copy of the dense window",
     WRITER, "    dense, why = in_dense_window(kickoffs, now=now)",
     "    dense, why = in_dense_window(kickoffs, now=now, dense_window_hours=24)",
     "does_not_carry_its_own_copy or inherits_the_shared_window", None),

    ("the re-serve stops consulting the capture's window at all",
     WRITER, "    dense, why = in_dense_window(kickoffs, now=now)",
     "    dense, why = (False, 'no window')",
     "agree_on_the_dense_window or inherits_the_shared_window or inside_the_window",
     "in_dense_window(kickoffs, now=now)"),

    ("the dense branch never fires — the tier silently reverts to daily-only",
     WRITER, "    if dense:\n        return True, (f\"dense tier: {why}",
     "    if False:\n        return True, (f\"dense tier: {why}",
     "inside_the_window_every_hour_publishes or agree_on_the_dense_window", None),

    # ── 2. monotone: the old daily write must survive ────────────────────────────────────────
    ("the daily baseline write is dropped, so a quiet week never re-serves",
     WRITER, "    if local_hour == baseline_hour_local:", "    if False:",
     "baseline or superset_of_the_old_daily_schedule", None),

    ("the baseline hour moves, so the old daily write happens at a different time",
     WRITER, "SERVING_BASELINE_HOUR_LOCAL = 6", "SERVING_BASELINE_HOUR_LOCAL = 7",
     "superset_of_the_old_daily_schedule", None),

    # ── 3. a skip must say why (NF-FRESH1) ───────────────────────────────────────────────────
    ("a skipped tick stops saying why, so it reads like a schedule that stopped firing",
     WRITER, '    return False, (f"skip: {local_hour:02d}:00 {tz} is not the '
                  '{baseline_hour_local:02d}:00 "',
     '    return False, ("" and (f"skip: {local_hour:02d}:00 {tz} is not the '
                  '{baseline_hour_local:02d}:00 "',
     "names_the_clock or non_empty_reason", None),

    # ── 4. the kickoff read stays lake-only ──────────────────────────────────────────────────
    ("the tier reaches for CFBD, putting a paid key behind a HALT-tier serving write",
     WRITER,
     "    now = now or datetime.now(timezone.utc)\n"
     "    raw = read_snapshots(season, gps.SNAPSHOT_SOURCE, local_root=local_root)",
     "    now = now or datetime.now(timezone.utc)\n"
     "    from x import _season_kickoffs\n"
     "    raw = read_snapshots(season, gps.SNAPSHOT_SOURCE, local_root=local_root)",
     "does_not_reach_for_cfbd", None),

    ("already-kicked-off games are returned as 'upcoming', so the window never closes",
     WRITER,
     "    return [k.to_pydatetime() for k in pd.to_datetime(kicks) if k.to_pydatetime() > now]",
     "    return [k.to_pydatetime() for k in pd.to_datetime(kicks)]",
     "returns_only_future_kickoffs", None),

    ("an absent snapshot table raises instead of reading empty",
     WRITER, '    if raw is None or getattr(raw, "empty", True) or "commence_time" not in raw.columns:',
     '    if False:',
     "absent_snapshot_table", None),

    # ── 5. the op ────────────────────────────────────────────────────────────────────────────
    ("the tier gate FAILS CLOSED — a transient lake read silently freezes the board",
     JOB, '        return True, f"tier unevaluable ({exc}) — failing open to a write"',
     '        return False, f"tier unevaluable ({exc})"',
     "fails_open", None),

    ("the chained snapshot write becomes tier-gated, so a fresh vintage waits for the clock",
     JOB, "    been written later.\n    \"\"\"\n    _run_serving_write(context)",
     "    been written later.\n    \"\"\"\n    if not _tier_decision(context)[0]:\n        return\n"
     "    _run_serving_write(context)",
     "chained_snapshot_write_is_not_tier_gated", None),

    ("a skipped tick logs nothing (the 19-green-runs shape)",
     JOB, '        context.log.info("NCAAF serving write: no re-serve this tick — %s", why)',
     '        pass',
     "logs_on_both_branches", None),

    ("the op stops consulting the tier and publishes every hour unconditionally",
     JOB, "    serve, why = _tier_decision(context)", "    serve, why = (True, 'always')",
     "still_calls_the_write or logs_on_both_branches", "= _tier_decision(context)"),

    # ── 6. the schedule ──────────────────────────────────────────────────────────────────────
    ("the schedule goes back to daily, so the dense tier can never fire",
     SCHED, 'NCAAF_SERVING_WRITE_CRON = "20 * * 8-12,1 *"',
     'NCAAF_SERVING_WRITE_CRON = "20 6 * 8-12,1 *"', "ticks_hourly", None),

    ("the re-serve fires at the same minute as its producer and races it",
     SCHED, 'NCAAF_SERVING_WRITE_CRON = "20 * * 8-12,1 *"',
     'NCAAF_SERVING_WRITE_CRON = "0 * * 8-12,1 *"', "runs_AFTER_the_capture", None),

    ("the in-season window loses the bowl/CFP months",
     SCHED, 'NCAAF_SERVING_WRITE_CRON = "20 * * 8-12,1 *"',
     'NCAAF_SERVING_WRITE_CRON = "20 * * 8-11 *"', "covers_the_bowl_season", None),

    ("the schedule self-starts instead of waiting for the operator",
     SCHED, "    default_status=DefaultScheduleStatus.STOPPED,",
     "    default_status=DefaultScheduleStatus.RUNNING,",
     "still_ships_stopped", "DefaultScheduleStatus.STOPPED"),
]


def _run(selector: str) -> bool:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", _TEST, "-q", "--no-header", "-p", "no:cacheprovider",
         "-k", selector],
        cwd=_REPO, capture_output=True, text=True)
    # A collection error is NOT a red: it proves the file is broken, not that the guard bit.
    if "error" in out.stdout.lower() and "collected 0" in out.stdout.lower():
        return False
    return out.returncode != 0


def main() -> int:
    backups = {p: p.with_suffix(p.suffix + ".redproof.bak") for p in {b[1] for b in BREAKS}}
    for original, backup in backups.items():
        if backup.exists():
            print(f"⚠️  restoring stale backup for {original.name}")
            original.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
            backup.unlink()

    print("baseline (all guards, unbroken source) …", end=" ", flush=True)
    base = subprocess.run([sys.executable, "-m", "pytest", _TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    if base.returncode != 0:
        print("FAILED — fix the suite before RED-proving it")
        print(base.stdout[-3000:])
        return 1
    print("green ✅")

    reds = 0
    for label, path, old, new, selector, must_vanish in BREAKS:
        src = path.read_text(encoding="utf-8")
        occurrences = src.count(old)
        if occurrences != 1:
            print(f"❌ {label}\n      anchor occurs {occurrences}× in {path.name} — a non-unique "
                  "anchor can land the break on the WRONG symbol (E11.24)")
            continue
        backup = backups[path]
        backup.write_text(src, encoding="utf-8")
        try:
            path.write_text(src.replace(old, new, 1), encoding="utf-8")
            landed = path.read_text(encoding="utf-8")
            assert landed != src, f"the mutation for {label!r} did not land on disk"
            if must_vanish is not None and must_vanish in landed:
                print(f"❌ {label}\n      the break landed but {must_vanish!r} is still present — "
                      "it would not move the asserted predicate (#815)")
                continue
            went_red = _run(selector)
        finally:
            path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
            backup.unlink()
        print(("🔴 RED  " if went_red else "❌ GREEN") + f"  {label}")
        reds += int(went_red)

    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    return 0 if reds == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
