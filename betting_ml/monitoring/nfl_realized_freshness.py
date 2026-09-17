"""NF-WK-RC1 ① — is the PUBLISHED realized-week artifact keeping up with the lake?

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS ASKS, AND WHY IT IS NOT AN AGE CHECK
═══════════════════════════════════════════════════════════════════════════════════════════════════

The artifact this judges is a per-week blob: once week 3 is published it is CORRECT for it never to
change again. So an mtime/age SLA is exactly the wrong instrument — INC-45's lesson, where a
freshness SLA on a deliberately-static artifact pages daily on a healthy file and gets muted, and
the FRESH1 mirror image where a static file's refreshed mtime reads green through a real outage.

The question is a COUNT comparison, in the same shape as the completeness gate itself:

    every week the LAKE says is FINAL should have a PUBLISHED manifest.

⭐ BOTH SIDES COME FROM SOMEWHERE ELSE THAN THE ARTIFACT. The expected set is the lake (realized
game counts against the schedule's); the actual set is S3. Reading either off the thing being
judged would make the check circular — the defect no age bar can see is a producer that succeeds
while publishing nothing, and that producer's own artifact always looks healthy from the inside.

───────────────────────────────────────────────────────────────────────────────────────────────────
⏳ ACTIVE-SEASON SEMANTICS, STATED RATHER THAN IMPLIED
───────────────────────────────────────────────────────────────────────────────────────────────────

Out of season, and before the first week completes, there is NO final week — and an artifact that
correctly does not advance must not page. That is `INACTIVE`, and it is a distinct verdict from
`OK` on purpose: "there was nothing to check" and "everything checked out" are different facts, and
collapsing them is how a monitor reports health it never established (NF1.7(a)).

───────────────────────────────────────────────────────────────────────────────────────────────────
🕰️ THE GRACE WINDOW IS DELIBERATELY SLOW, AND THAT IS NOT A COMPROMISE
───────────────────────────────────────────────────────────────────────────────────────────────────

This is the BACKSTOP, not the primary detector. `nfl_realized_week_publish_op` pages the moment a
publish fails, in the run it fails in. The only failure this can see that the op cannot is the op
NOT RUNNING AT ALL — a schedule reverted to STOPPED, a code location that will not load, a daemon
that stalled. In every one of those there is no run, no failure, and no page, and the last run in
Dagit is a genuine green one.

That failure does not get better or worse with hours, so the window is sized to make a FALSE ALARM
structurally impossible rather than to react quickly: the vendor's own publication lag (measured at
node 1: ~23 h after the Monday-night close) plus one full cadence of this daily job, plus slack.
An alert that fires while the vendor has simply not published yet would be paging about someone
else's schedule, every single week — the muted-monitor pattern arriving on day one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

#: Measured at NF-WK-RC1 node 1: 2026 week 1 reached 32/32 teams and 16/16 games about 23 hours
#: after its Monday-night game ended.
VENDOR_LAG_HOURS = 24
#: One full fire of `sports_nfl_weekly_serving_schedule` (daily, 08:30 PT).
CADENCE_HOURS = 24
#: Slack, so a fire that lands slightly late on a box under load is never a page.
SLACK_HOURS = 6
GRACE_HOURS = VENDOR_LAG_HOURS + CADENCE_HOURS + SLACK_HOURS


@dataclass
class RealizedReading:
    """What was observed. `error` set ⇒ nothing was judged."""

    season: int
    #: Weeks with a SERVED manifest in S3 (never a parked revision).
    published_weeks: set[int] = field(default_factory=set)
    #: Weeks the LAKE reports FINAL by the count rule.
    lake_final_weeks: set[int] = field(default_factory=set)
    #: `{week: when that week's slate ended, UTC}` — the grace clock's anchor.
    slate_end_by_week: dict[int, datetime] = field(default_factory=dict)
    error: str | None = None


def _overdue(week: int, reading: RealizedReading, now: datetime) -> bool:
    """Is this unpublished FINAL week past its grace window?

    ⛔ AN UNRESOLVABLE SLATE END COUNTS AS *NOT* OVERDUE. A missing anchor means we cannot say how
    long it has been overdue, and a monitor that guesses in the paging direction on absent evidence
    is how a real finding gets buried under false ones. It can only ever delay a page.
    """
    end = reading.slate_end_by_week.get(week)
    if end is None:
        return False
    return now >= end + timedelta(hours=GRACE_HOURS)


def classify(reading: RealizedReading, *, now: datetime | None = None) -> dict:
    """`INACTIVE` | `OK` | `AWAITING_PUBLISH` | `STALE` | `NOTHING_PUBLISHED` | `UNEVALUABLE`."""
    now = now or datetime.now(timezone.utc)

    if reading.error:
        return {"verdict": "UNEVALUABLE", "severity": "WARN", "missing": [],
                "detail": (f"the realized artifact was NOT judged for {reading.season}: "
                           f"{reading.error}. Reported UNVERIFIED rather than healthy.")}

    final = sorted(reading.lake_final_weeks)
    if not final:
        return {"verdict": "INACTIVE", "severity": None, "missing": [],
                "detail": (f"no {reading.season} REG week is FINAL in the lake yet, so there is "
                           "nothing to publish and the artifact is correctly static. This is 'not "
                           "checked', not 'healthy'.")}

    missing = [w for w in final if w not in reading.published_weeks]
    if not missing:
        return {"verdict": "OK", "severity": None, "missing": [],
                "detail": (f"all {len(final)} FINAL week(s) of {reading.season} are published "
                           f"(through wk {final[-1]}).")}

    overdue = [w for w in missing if _overdue(w, reading, now)]
    if not overdue:
        return {"verdict": "AWAITING_PUBLISH", "severity": None, "missing": missing,
                "detail": (f"{reading.season} wk {missing} became FINAL recently and is not "
                           f"published yet — inside the {GRACE_HOURS}h window the vendor's own lag "
                           "and this job's daily cadence occupy. Not a finding yet.")}

    newest_final = final[-1]
    if not reading.published_weeks:
        verdict, severity = "NOTHING_PUBLISHED", "CRITICAL"
        why = ("NOTHING is published for this season at all while the lake holds "
               f"{len(final)} FINAL week(s). This is the shape 2026 week 1 was lost in.")
    elif newest_final in overdue:
        verdict, severity = "STALE", "CRITICAL"
        why = (f"the newest FINAL week ({newest_final}) is overdue and unpublished, so the recap "
               "surface is serving an older week than the one that has been played.")
    else:
        verdict, severity = "STALE", "ERROR"
        why = (f"week(s) {overdue} are FINAL and overdue but unpublished, while the newest final "
               f"week ({newest_final}) IS published — the self-healing leg is not filling a gap.")

    return {"verdict": verdict, "severity": severity, "missing": missing, "overdue": overdue,
            "detail": (f"{why} Published: {sorted(reading.published_weeks)}; lake FINAL: {final}. "
                       f"⭐ The likely cause is not a failed publish (that pages in its own run) "
                       "but `sports_nfl_weekly_serving_schedule` not RUNNING — check it in Dagit "
                       "and against `check_monitors_healthy_op`.")}


def is_problem(verdict: dict) -> bool:
    """Whether this verdict should page. `INACTIVE`/`OK`/`AWAITING_PUBLISH` are silent by design."""
    return bool(verdict.get("severity"))
