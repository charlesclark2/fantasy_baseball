#!/usr/bin/env python
"""NF-FRESH2 P0 — does each NFL schedule actually fire through the season?

⭐ WHY A SCRIPT AND NOT A ONE-LINER. The claim P0 makes is about what the BOX WILL FIRE, and the
only thing that can answer it is the deployed module evaluated by the same cron engine Dagster
uses. So this imports the real `sports_rollforward_schedules` (never a copy of the strings, never a
source scan) and iterates with Dagster's own `cron_string_iterator` — the vendored engine, because
**`croniter` is NOT installed in the box image** and a `pip install croniter` one-liner would be
answering the question with a different engine than the one that fires.

⭐ AND IT IS TWO-SIDED, which is the part that makes it evidence rather than decoration. A checker
that only ever reports PASS cannot distinguish a fixed cron from a broken one, so `--control`
re-runs the identical assertion against the PRE-NF-FRESH2 `3-8` crons and REQUIRES them to fail. If
the control passes, the checker itself is broken and its PASSes mean nothing (the NF1.7(a) /
INC-38 / INC-39 family: a check whose failure state is indistinguishable from its healthy state has
not verified anything).

Usage (BOX):
  docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \\
    python scripts/check_nfl_schedule_coverage.py --strict

Exit 0 = every schedule fires in every month it must, and the control failed as required.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

# The NFL season runs Sep → Feb. A schedule that feeds the in-season board must fire in all six.
SEASON_MONTHS = (9, 10, 11, 12, 1, 2)
# ...and the offseason/camp churn window must not have been lost while widening.
OFFSEASON_MONTHS = (3, 4, 5, 6, 7, 8)

# The PRE-NF-FRESH2 crons. The checker must REJECT these or it is not a checker.
CONTROL_CRONS = (
    ("OLD roll-forward (pre-NF-FRESH2)", "15 6 * 3-8 1"),
    ("OLD sleeper capture (pre-NF-FRESH2)", "30 6 * 3-8 *"),
)


def _fires(cron: str, tz: str, start: datetime, n: int) -> list[datetime]:
    from dagster._utils.schedules import cron_string_iterator

    it = cron_string_iterator(start.timestamp(), cron, tz)
    return [next(it) for _ in range(n)]


def months_covered(cron: str, tz: str, start: datetime, horizon: int) -> set[int]:
    """Every calendar month this cron fires in over the next `horizon` fires."""
    return {d.month for d in _fires(cron, tz, start, horizon)}


def check(cron: str, tz: str, start: datetime, horizon: int) -> tuple[bool, set[int], list[str]]:
    covered = months_covered(cron, tz, start, horizon)
    missing_season = sorted(set(SEASON_MONTHS) - covered)
    missing_off = sorted(set(OFFSEASON_MONTHS) - covered)
    problems = []
    if missing_season:
        problems.append(f"does NOT fire in season month(s) {missing_season} — the 09-01 cliff")
    if missing_off:
        problems.append(f"lost offseason month(s) {missing_off} while widening")
    return (not problems), covered, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from-date", default="2026-08-30",
                    help="ISO date to start iterating from (default: just before the 09-01 cliff)")
    ap.add_argument("--horizon", type=int, default=400,
                    help="how many FIRES to look ahead — must exceed a year of the sparsest "
                         "schedule (the weekly one) or a month can look uncovered when it is not")
    ap.add_argument("--show", type=int, default=4, help="how many upcoming fires to print each")
    ap.add_argument("--control", action="store_true", default=True,
                    help="also require the pre-NF-FRESH2 crons to FAIL (default; the two-sided half)")
    ap.add_argument("--no-control", dest="control", action="store_false")
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any problem")
    args = ap.parse_args(argv)

    start = datetime.fromisoformat(args.from_date).replace(tzinfo=timezone.utc)

    # Imported HERE, not at module scope: on a machine without the dbt manifest `pipeline`'s
    # __init__ raises, and the failure should name that rather than a bare collection error.
    try:
        import pipeline.schedules.sports_rollforward_schedules as S
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL — could not import the deployed schedule module ({type(exc).__name__}: {exc}).")
        print("       Run this INSIDE the dagster-codeloc container, where `pipeline` imports.")
        return 1

    targets = [
        ("sports_nfl_roll_forward_schedule", S.NFL_ROLL_FORWARD_CRON),
        ("sports_nfl_sleeper_injuries_schedule", S.NFL_SLEEPER_INJURIES_CRON),
        ("sports_nfl_board_publish_schedule", S.NFL_BOARD_PUBLISH_CRON),
    ]
    tz = "America/Los_Angeles"
    failures: list[str] = []

    print(f"Next fires from {start.date()} ({tz}), months checked over {args.horizon} fires:\n")
    for name, cron in targets:
        ok, covered, problems = check(cron, tz, start, args.horizon)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        print(f"        cron   {cron}")
        print(f"        months {sorted(covered)}")
        for d in _fires(cron, tz, start, args.show):
            print(f"        next   {d.isoformat()}")
        for p in problems:
            print(f"        ⛔ {p}")
            failures.append(f"{name}: {p}")
        print()

    if args.control:
        print("Two-sided control — the PRE-NF-FRESH2 crons must be REJECTED:\n")
        for label, cron in CONTROL_CRONS:
            ok, covered, _ = check(cron, tz, start, args.horizon)
            # `ok` True here means the checker FAILED to notice the known-broken cron.
            print(f"  {'⛔ CHECKER BROKEN' if ok else 'rejected (correct)'}  {label}")
            print(f"        cron   {cron}")
            print(f"        months {sorted(covered)}  ← the seven-month hole")
            if ok:
                failures.append(
                    f"CONTROL: the checker PASSED the known-broken cron {cron!r} — every PASS "
                    "above is therefore meaningless, fix the checker before trusting it")
            print()

    if failures:
        print("PROBLEMS:")
        for f in failures:
            print(f"  - {f}")
        return 1 if args.strict else 0
    print("OK — every NFL schedule fires through the season, the offseason window is intact, "
          "and the control was correctly rejected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
