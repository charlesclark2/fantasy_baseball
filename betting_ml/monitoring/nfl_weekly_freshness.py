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
             now: datetime | None = None) -> dict:
    """The verdict. Never raises, never pages — the caller decides what to do with it.

    Ordered so the most actionable finding wins: a WRONG WEEK outranks a stale timestamp, because a
    build that is running and targeting last week is serving a played slate while every clock reads
    healthy.
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
