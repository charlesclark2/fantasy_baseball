"""NCAAF-P3.3b — WHEN the served NCAAF ratings last took in games, and when they next will.

The team page prints a strength rating, a band and two ranks. All four move ONLY when the P1.2
posterior is re-fit, and NCAAF-P3.3 measured what that costs a reader: from Saturday kickoff to
whenever the next fit lands, a team can win by 26 while its rating sits unchanged beside the win in
its own schedule. That reads as a broken product rather than a weekly one, and no wording on the
strength block alone can fix it — the missing fact is a DATE.

⭐ BOTH HALVES ARE DATA, AND THAT IS THE WHOLE DESIGN. A sentence ("ratings update Monday
mornings") is written once against whatever was true that week and is then free to be wrong
forever — a bye week, a cancelled opener, a cadence change, or (as it turned out here) a premise
that was never true. A stamp computed from the ARTIFACT and from the SCHEDULE REGISTRY survives
all four by construction.

══ THE MEASUREMENT THAT DECIDED THE SECOND HALF (2026-09-04) ═══════════════════════════════════

P3.3b was specified to derive "next update" from `NCAAF_ROLL_FORWARD_CRON`, on the premise —
recorded in #1081's own commit message — that "the P1.2 strength fit rolls forward weekly". THAT
PREMISE IS FALSE, and it is false three ways that agree:

  1. STRUCTURALLY IMPOSSIBLE. `sports_ncaaf_roll_forward_job` runs an ingest of
     `ROLL_FORWARD_SOURCES` + a dbt mart rebuild. `team_strength_week` is not in that list and
     CANNOT be: `ingest/sources.py` asserts at import that every roll-forward source is a free
     CFBD source, and the ratings table is a derived model output written by `run_team_strength`.
  2. SAID IN THREE PLACES. The roll-forward job's own docstring ("P1.2 must be re-fit ... those are
     the OPERATOR steps ... not wired here, because P1.2 is a once-per-season refit, not a weekly
     one"), the snapshot job's ("THE ONE QUALITY PREREQUISITE (operator, not code)"), and
     `BOX_OPERATIONS.md §10` ("the season's ONE-TIME P1.2 re-fit ... are the operator laptop
     steps"). `grep run_team_strength pipeline/` returns docstrings and no call.
  3. MEASURED ON THE LAKE, TWO-SIDED. `ncaaf/derived/team_strength_week` last committed
     2026-08-18T06:16:36Z (version 67) — the operator's documented re-fit. `ncaaf/raw/games` and
     `ncaaf/raw/talent` last committed 2026-08-31T13:00:51Z / 13:01:13Z, i.e. Monday 06:00 PT: the
     roll-forward FIRED, and the ratings did not move. The chain is alive AND it does not touch
     them. Corroborating on the wire the same day: both captured teams serve `as_of_week 1` with
     one week in the series, one of them beside a completed game.

⇒ printing the roll-forward's next fire under "next update" would promise a ratings refresh that
job structurally cannot deliver. That is precisely the overclaim P3.3b's own acceptance criterion
forbids, so this module REFUSES to derive it and the surface states the absence instead. The
decision is the PM's; the registry below is the one line that changes when they make it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class RatingsArtifact:
    """The lake table whose commit history IS the ratings' vintage."""

    sport: str
    source: str
    tier: str


#: `run_team_strength.py` (`LAKE_SOURCE`/`LAKE_TIER`) is its ONLY writer — verified by grep over
#: every `tier="derived"` write in the NCAAF tree. So a new commit here means a re-fit landed, and
#: nothing else can move this timestamp.
RATINGS_ARTIFACT = RatingsArtifact(sport="ncaaf", source="team_strength_week", tier="derived")

#: The Dagster schedules that REWRITE `RATINGS_ARTIFACT`, by name.
#:
#: ⛔ MEASURED EMPTY 2026-09-04 — see the module docstring. Nothing in `pipeline/` calls
#: `run_team_strength`; the P1.2 re-fit is an operator laptop step. An EMPTY tuple is therefore a
#: measurement, not a stub, and `next_ratings_update` returns None from it so the surface states an
#: absence rather than inventing a date.
#:
#: ⚠️ ⛔ DO NOT ADD `sports_ncaaf_roll_forward_schedule` HERE. That is the exact error this module
#: exists to correct, it is the one a future reader is most likely to make (the claim is still
#: sitting in #1081's commit message), and `test_ncaaf_p3_3b_ratings_stamp.py` refuses it by name.
#: An entry here is a claim that the named schedule's JOB writes the ratings table — verify it
#: writes, do not infer it from the job sounding related.
RATINGS_REFRESH_SCHEDULES: tuple[str, ...] = ()


def read_ratings_vintage(*, bucket: str | None = None,
                         local_root: str | None = None) -> datetime | None:
    """When the ratings artifact was last WRITTEN, or None when that cannot be read.

    ⭐ THE TIMESTAMP COMES FROM INSIDE `_delta_log`, NEVER FROM AN S3 `LastModified` (INC-41): an
    mtime is refreshed by any server-side rewrite that changes no data, and `aws s3 ls` prints
    SHELL-LOCAL time — both would report a frozen artifact as fresh. The commit read, and the
    epoch-milliseconds-or-datetime ambiguity delta-rs has shipped both ways, have ONE owner in
    `sports_delta_freshness`; a second parser here is how the two would drift.

    ⚠️ NEVER RAISES. This feeds a serving write whose tier is ALERT — an unreadable lake must cost
    the page its stamp, not its ratings. None becomes a STATED absence on the surface, never a
    fabricated date (NF1.7(a): a check that could not run is not a check that passed).
    """
    from dataclasses import replace

    from betting_ml.monitoring import sports_delta_freshness as SDF

    probe = replace(
        SDF.REGISTRY[0],
        name="ncaaf_team_strength_week",
        sport=RATINGS_ARTIFACT.sport,
        source=RATINGS_ARTIFACT.source,
        tier=RATINGS_ARTIFACT.tier,
    )
    reading = SDF.read_contract(probe, bucket=bucket, local_root=local_root)
    return reading.last_commit


def next_fire(cron: str, tz: str, now: datetime) -> datetime:
    """The next firing instant of `cron` in `tz`, as tz-aware UTC.

    ⚠️ DAGSTER'S OWN CRON ITERATOR, NEVER `croniter`. croniter is NOT installed on the box (dagster
    1.13 vendors its own), so a croniter-based resolver works on a laptop and fails in production —
    the NF-FRESH2 finding, and exactly the kind of defect CI cannot see because CI is a laptop.

    Pure and injectable on purpose: it takes a cron STRING, so the arithmetic is testable without
    importing `pipeline` (whose package state the fast gate does not have — E11.23).
    """
    from dagster._utils.schedules import cron_string_iterator  # noqa: PLC0415 — see docstring

    return next(cron_string_iterator(now.timestamp(), cron, tz)).astimezone(timezone.utc)


def next_ratings_update(now: datetime | None = None,
                        schedules: tuple[str, ...] | None = None) -> datetime | None:
    """The earliest next fire across the schedules that rewrite the ratings, or None.

    None is the honest answer whenever nothing is registered — which is the state measured on
    2026-09-04 and is why this returns None today. It is NOT a failure and NOT a fallback: it is
    the computed consequence of an empty registry, and the caller renders it as a stated absence.
    """
    names = RATINGS_REFRESH_SCHEDULES if schedules is None else schedules
    if not names:
        return None
    at = now or datetime.now(timezone.utc)
    return min(next_fire(*_schedule_cron(name), at) for name in names)


def _schedule_cron(name: str) -> tuple[str, str]:
    """`(cron_schedule, execution_timezone)` for a Dagster schedule, BY DEFINITION not by copy.

    Reading the live `ScheduleDefinition` rather than re-declaring a cron string is what keeps this
    from becoming a second owner of a cadence — the defect class this whole module is a correction
    for (INC-30/36/38: one logical thing, two execution owners).

    ⛔ RAISES on an unknown name. Returning None would render a stated absence — byte-identical to
    the correct empty-registry answer — so a typo would be indistinguishable from the measured
    truth (NF1.7(a)).
    """
    import pipeline  # noqa: PLC0415 — lazy: `betting_ml/` must import without `pipeline` state

    sched = pipeline.defs.get_schedule_def(name) if name in {
        s.name for s in pipeline.defs.schedules} else None
    if sched is None:
        raise KeyError(f"no Dagster schedule named {name!r} — RATINGS_REFRESH_SCHEDULES is stale")
    return sched.cron_schedule, (sched.execution_timezone or "UTC")


def iso(value: datetime | None) -> str | None:
    """A tz-aware UTC ISO-8601 string, or None. The served form of both stamp halves."""
    if value is None:
        return None
    at = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc).isoformat()


def ratings_vintage_fields(*, now: datetime | None = None,
                           bucket: str | None = None,
                           local_root: str | None = None) -> dict[str, str | None]:
    """The two served stamp halves, as the serving write emits them.

    ONE call so a writer cannot pick up one half and forget the other, and so the "read the
    artifact / resolve the schedule" pair has a single tested entry point.
    """
    if os.environ.get("NCAAF_RATINGS_VINTAGE_DISABLED") == "1":
        # An escape hatch for a lake outage: the page degrades to a stated absence rather than the
        # write failing. Loud by being a declared env var, not a silent try/except.
        return {"ratings_as_of": None, "ratings_next_update": None}
    return {
        "ratings_as_of": iso(read_ratings_vintage(bucket=bucket, local_root=local_root)),
        "ratings_next_update": iso(next_ratings_update(now)),
    }
