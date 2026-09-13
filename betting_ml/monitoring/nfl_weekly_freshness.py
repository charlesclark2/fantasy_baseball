"""nfl_weekly_freshness.py — NF-C6-PH2: the freshness SLA for the SERVED weekly projection.

INC-41's central mechanic applies here with full force: freshness is read from the artifact's own
CONTENT, never from an S3 `LastModified`. An mtime is refreshed by any server-side rewrite that
changes no data, `aws s3 ls` prints SHELL-LOCAL time (a ~5-6h phantom staleness), and #638's atomic
server-side copy refreshes an mtime even when the bytes are unchanged. The timestamps used here are
the ones the BUILDER wrote into the manifest.

⭐ TWO DIFFERENT FAILURES, AND THE SECOND IS THE DANGEROUS ONE.

  * `generated_at` frozen ⇒ the build stopped running. A staleness bar catches this.
  * `week` BEHIND the schedule ⇒ the build is running fine and serving LAST WEEK'S projection. Every
    timestamp looks healthy; the number on the page is simply for a game that has already been
    played. This is the INC-37 shape — a month-boundary hole that made every clock-based instrument
    read green while the served universe was a month stale — and no staleness bar can see it,
    because the artifact IS advancing. `week_behind` is the check that can.

⚠️ ACTIVE ONLY WHEN THERE IS A WEEK TO PROJECT. The NFL REG season runs ~September to early January;
for the other seven months there is no upcoming week and the artifact SHOULD be static. An SLA that
paged daily through the off-season would be the muted-monitor pattern (and the INC-45 lesson: do not
put a freshness SLA on a deliberately-static artifact). `is_active_window` derives that from the
SCHEDULE the builder itself reads, not from a pinned month range — a formula would drift the moment
the league moves a week (the NCAAF-P0.6 stale-by-a-season class applied to a cadence).

TIERING — this module DECIDES, it never pages or raises. `pipeline/jobs/…` does the paging so the
policy stays import-safe for the fast gate (E11.23: nothing here imports `pipeline`).

⚠️ AN UNREADABLE ARTIFACT IS `UNKNOWN`/WARN, NEVER HEALTHY (NF1.7(a)) — a check that could not run
is not a check that passed. That distinction is most of why this module exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

#: The build's cadence. It runs DAILY within the season, not weekly: the `week` it targets changes
#: once a week, but its INPUTS (rosters, injuries, snaps) move every day, and a Tuesday build is
#: what carries a Monday-night result into Sunday's projection.
CADENCE_HOURS = 24.0

#: Grace on top of the cadence, sized the way `nfl_board_freshness` sizes its own: it must absorb
#: the CHECK/PUBLISH OFFSET (a monitor riding a different job sees a healthy artifact already
#: ~23h old) plus genuine lateness, while staying comfortably below the ~47h a SKIPPED DAY
#: produces — which is the event this exists to catch.
GRACE_HOURS = 6.75

#: How far ahead of the target week's first kickoff the artifact must be rebuilt at least once.
#: A projection published before a slate and never refreshed is not stale by the clock bar above,
#: but it is a week old by the time the games start.
STALE_BEFORE_KICKOFF_HOURS = 48.0

#: Grace after the SERVED week's LAST GAMEDAY before that slate counts as complete.
#:
#: ⚠️ SIZED FOR DATE GRANULARITY, NOT FOR A KICKOFF TIME. `schedules.gameday` is a DATE — the same
#: column `resolve_target_week` reads, which is why the builder logs a "first kickoff" of midnight
#: UTC — so the last gameday is midnight UTC on the Monday. A Monday-night ET kickoff (20:15 ET) is
#: already 00:15 UTC on TUESDAY, and the game runs ~3.5h beyond that: ~28h past the date we hold.
#: 30h clears it with margin.
#:
#: ⭐ THE ASYMMETRY IS DELIBERATE. Erring LATE delays a genuine wrong-week page by a few hours
#: inside a benign window that is already ~5 days wide — immaterial. Erring EARLY pages CRITICAL
#: while the Monday nighter is in play, which is the false alarm this whole change exists to
#: remove. When one direction is cheap and the other is the bug, size for the cheap one.
SLATE_COMPLETE_GRACE_HOURS = 30.0


def sla_hours() -> float:
    """The staleness bar, in hours since `generated_at`."""
    return CADENCE_HOURS + GRACE_HOURS


@dataclass(frozen=True)
class WeeklyReading:
    """What the PUBLISHED manifest actually said (or why it could not be read)."""

    season: int
    week: int | None = None
    generated_at: datetime | None = None      # tz-aware UTC
    projection_day: datetime | None = None    # the target week's first kickoff
    n_players: int | None = None
    error: str | None = None

    @property
    def readable(self) -> bool:
        return self.error is None and self.generated_at is not None and self.week is not None


def _parse(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        v = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def reading_from_manifest(season: int, blob: object) -> WeeklyReading:
    """Turn a published weekly manifest into a reading. A malformed blob is an ERROR, never a
    default-shaped healthy reading."""
    if not isinstance(blob, dict):
        return WeeklyReading(season=season, error=f"manifest is {type(blob).__name__}, not an object")
    gen = _parse(blob.get("generated_at"))
    if gen is None:
        return WeeklyReading(season=season, error="manifest carries no parseable generated_at")
    week = blob.get("week")
    if not isinstance(week, int):
        return WeeklyReading(season=season, generated_at=gen,
                             error=f"manifest carries no integer week (got {week!r})")
    return WeeklyReading(season=season, week=week, generated_at=gen,
                         projection_day=_parse(blob.get("projection_day")),
                         n_players=blob.get("n_players") if isinstance(blob.get("n_players"), int)
                         else None)


def is_active_window(expected_week: int | None) -> bool:
    """Whether an SLA applies at all.

    `expected_week` is the week the SCHEDULE says should be projected right now (the builder's own
    `resolve_target_week`), or None when no REG week is upcoming. Outside the season the artifact is
    correctly static and paging on it would train the operator to ignore this monitor.
    """
    return expected_week is not None


def classify(reading: WeeklyReading, *, expected_week: int | None,
             served_slate_ends: datetime | None = None,
             now: datetime | None = None) -> dict:
    """The verdict. Never raises, never pages — the caller decides what to do with it.

    Ordered so the most actionable finding wins: a WRONG WEEK outranks a stale timestamp, because a
    build that is running and targeting last week is serving a played slate while every clock reads
    healthy.

    ⭐ `served_slate_ends` IS WHAT SEPARATES A FALSE ALARM FROM THE REAL INC-37 SHAPE, and it is the
    correction to this module's first cut. The target week advances at the previous slate's FIRST
    kickoff, but the roster feed publishes the new week's rows a few days later — so from Thursday
    night until roughly the following Tuesday the served week is LEGITIMATELY one behind the
    schedule's "next" week, while that served slate is still being played. Keying the wrong-week
    check on `reading.week != expected_week` alone fired CRITICAL for ~5 of every 7 days with a
    detail line ("a slate that has already been played") that was false on its face — the
    muted-monitor pattern this module's own docstring warns against. The honest question is not
    "does the served week match the schedule's next week" but "has the served week's slate actually
    FINISHED while we are still serving it".

    ⚠️ ABSENT ⇒ NOT BENIGN (NF1.7(a)). With no slate end the mismatch is judged exactly as before —
    a check that cannot establish the benign case must not assume it.
    """
    now = now or datetime.now(timezone.utc)

    if not is_active_window(expected_week):
        return {"verdict": "OFF_SEASON", "severity": None, "lag_hours": None,
                "detail": ("no REG week is upcoming, so the weekly artifact is correctly static and "
                           "no SLA applies")}

    if not reading.readable:
        # ⛔ UNREADABLE IS NEVER HEALTHY (NF1.7(a)).
        return {"verdict": "UNKNOWN", "severity": "WARN", "lag_hours": None,
                "detail": (f"could not read the published weekly manifest for {reading.season}: "
                           f"{reading.error or 'no generated_at'}. Reported UNVERIFIED rather than "
                           "healthy — a check that could not run is not a check that passed.")}

    lag = (now - reading.generated_at).total_seconds() / 3600.0

    if reading.week != expected_week:
        behind = expected_week - reading.week
        # ⭐ THE BENIGN CASE, AND IT IS THE COMMON ONE IN-SEASON: the served week is exactly one
        # behind and ITS OWN slate has not finished. Nothing is wrong — the target advanced at that
        # slate's first kickoff and the next week's rosters have not published yet, so the build is
        # correctly skipping (EXIT_AWAITING_ROSTERS) and the previous week keeps serving games that
        # are still being played. Deliberately NOT a staleness case either: the artifact is frozen
        # BY DESIGN across this window, so falling through to the daily SLA below would just trade
        # a false WRONG_WEEK for a false STALE.
        if (behind == 1 and served_slate_ends is not None
                and now < served_slate_ends + timedelta(hours=SLATE_COMPLETE_GRACE_HOURS)):
            return {"verdict": "AWAITING_NEXT_WEEK", "severity": None, "lag_hours": round(lag, 2),
                    "detail": (f"serving {reading.season} wk {reading.week} while the schedule's "
                               f"next week is {expected_week}. Week {reading.week}'s slate is still "
                               "being played, so this is the roster feed's cadence, not a defect — "
                               "the build skips until the new week's rosters publish. This turns "
                               f"CRITICAL the moment wk {reading.week} completes and we are still "
                               f"serving it. generated_at is {lag:.1f}h old (frozen by design).")}
        return {"verdict": "WRONG_WEEK", "severity": "CRITICAL", "lag_hours": round(lag, 2),
                "detail": (f"the served weekly projection is for week {reading.week} while the "
                           f"schedule says week {expected_week} is next ({behind:+d}). Every "
                           "timestamp can look healthy here — the build is running, it is simply "
                           "targeting a slate that has already been played (the INC-37 shape). "
                           f"generated_at is {lag:.1f}h old.")}

    if reading.projection_day is not None:
        to_kick = (reading.projection_day - now).total_seconds() / 3600.0
        if 0 < to_kick <= STALE_BEFORE_KICKOFF_HOURS and lag > STALE_BEFORE_KICKOFF_HOURS:
            return {"verdict": "STALE_INTO_KICKOFF", "severity": "ERROR",
                    "lag_hours": round(lag, 2),
                    "detail": (f"week {reading.week} kicks off in {to_kick:.1f}h and its projection "
                               f"was built {lag:.1f}h ago — it has not been refreshed since the "
                               "roster and injury moves of the last two days.")}

    if lag > sla_hours():
        # ≤2× the SLA is a missed cycle; beyond it the build is dead. The two must not be conflated.
        dead = lag > 2 * sla_hours()
        return {"verdict": "STALE", "severity": "CRITICAL" if dead else "WARN",
                "lag_hours": round(lag, 2),
                "detail": (f"the weekly projection for {reading.season} wk {reading.week} was built "
                           f"{lag:.1f}h ago against a {sla_hours():.2f}h SLA "
                           f"(cadence: daily in-season). "
                           + ("Beyond twice the SLA — the build is not running."
                              if dead else "One missed cycle."))}

    return {"verdict": "OK", "severity": None, "lag_hours": round(lag, 2),
            "detail": (f"{reading.season} wk {reading.week}, built {lag:.1f}h ago "
                       f"({reading.n_players} players)")}


def is_problem(verdict: dict) -> bool:
    return bool(verdict.get("severity"))
