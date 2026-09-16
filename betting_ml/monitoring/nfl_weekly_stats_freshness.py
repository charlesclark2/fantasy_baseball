"""NF-INC-0916 node 1(c) — is the weekly model's TRAINING FEED advancing?

⛔ THE FAILURE THIS EXISTS FOR IS NOT AN OUTAGE. It is the incident: two feeds that nothing
ingested, on no cadence, for a whole season — while every job that read them returned SUCCESS,
because a missing stat line is not an error anywhere downstream. `attach_labels` fills it with a
zero under the retained-zero convention and the model learns from it. There was never a red run.

⭐ AND IT IS NOT A `LastModified` CHECK (INC-41). A Delta commit timestamp says when we last
WROTE, not what we wrote — a daily ingest re-landing the same stale vendor file would refresh the
commit every day while the CONTENT stood still. The question this asks is about CONTENT: does the
feed carry the last week that has actually been played?

══ THE THREE STATES, AND WHY "PENDING" HAS TO BE ONE OF THEM ════════════════════════════════════

A week ENDS on a Monday night and the vendor publishes it the NEXT MORNING — measured live on
2026-09-15: week 1 closed Monday 09-14, `snap_counts_2026.parquet` was republished 11:25Z
(≈04:25 PT) and `stats_player_week_2026.parquet` at 14:21Z (≈07:21 PT), each carrying week 1 and
nothing later. So for the hours between a slate ending and the vendor publishing it, a feed that
does NOT carry the just-finished week is perfectly healthy.

A monitor without that state pages every Monday night on the normal cadence, and a monitor that
pages every day on healthy behaviour is one somebody mutes — which is how the INC-37 morning-page
lesson reads in this repo, and the exact reason `check_w11_tail_coverage` judges two of its three
feeds on the PRIOR slate. Hence `SETTLE_HOURS`.

⚠️ UNEVALUABLE IS WARN, NEVER HEALTHY (NF1.7(a)). A check that could not run is not a check that
passed, and this module's whole reason for existing is a year of green runs that examined nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

#: How long after a slate ENDS before a feed that still lacks that week is judged STALE.
#:
#: ⭐ A DESIGN QUANTITY DERIVED FROM A MEASUREMENT, not a round number. The observed publish lag is
#: ~8 h (a Monday slate ends ≈23:30 PT; both feeds were republished 04:25–07:21 PT the next
#: morning). 24 h is three times that, which leaves the vendor a full extra day before we call it
#: a fault — while still catching the thing that actually happened here, a feed that never
#: advanced at all, within a day rather than within a season.
#:
#: ⛔ Do NOT tighten it toward the measured 8 h "to catch problems sooner". The cost of a false
#: page is a muted monitor, and the ONLY defect it would catch earlier is one a single extra day
#: reveals anyway — while the consumer rebuilds daily, so at most one publish rides a late feed.
SETTLE_HOURS = 24.0


@dataclass(frozen=True)
class FeedReading:
    """What one feed carries, as read from the lake."""
    source: str
    #: The newest week present for the season, or None when the season has no rows at all.
    last_week: int | None
    rows: int
    #: Set when the lake could not be read AT ALL for this feed. A read failure is never a zero.
    error: str | None = None

    @property
    def readable(self) -> bool:
        return self.error is None


def classify(
    reading: FeedReading,
    *,
    season: int,
    last_completed_week: int | None,
    slate_ended: datetime | None,
    now: datetime | None = None,
    settle_hours: float = SETTLE_HOURS,
) -> dict:
    """Judge one feed against the last week that has actually been played.

    `last_completed_week` / `slate_ended` come from the SCHEDULE, never from the feed being judged
    — a check that reads its own subject for the standard it is held to can only ever agree with
    itself, which is the circularity `nfl_weekly_freshness` documents for the served week.
    """
    now = now or datetime.now(timezone.utc)

    if not reading.readable:
        return {
            "verdict": "UNREADABLE", "severity": "WARN", "source": reading.source,
            "last_week": None, "expected_week": last_completed_week,
            "detail": (f"could not read `{reading.source}` from the lake, so it was NOT judged: "
                       f"{reading.error}. Reported UNVERIFIED rather than healthy — a check that "
                       "could not run is not a check that passed."),
        }

    if last_completed_week is None:
        return {
            "verdict": "NO_COMPLETED_WEEK", "severity": None, "source": reading.source,
            "last_week": reading.last_week, "expected_week": None,
            "detail": (f"no {season} REG week has finished yet, so there is nothing for "
                       f"`{reading.source}` to carry and no SLA applies."),
        }

    if reading.last_week is not None and reading.last_week >= last_completed_week:
        return {
            "verdict": "OK", "severity": None, "source": reading.source,
            "last_week": reading.last_week, "expected_week": last_completed_week,
            "detail": (f"`{reading.source}` carries {season} week {reading.last_week} "
                       f"({reading.rows} rows); the last completed week is {last_completed_week}."),
        }

    # Behind. Two questions, in this order: is it behind by MORE than the newest week (which no
    # publication delay can explain), and if not, has the vendor had time to publish?
    #
    # ⚠️ THE FIRST QUESTION IS LOAD-BEARING AND THE FIRST CUT OF THIS MODULE GOT IT WRONG. Without
    # it, a feed carrying NOTHING for the season is reported PENDING for a day after every slate —
    # which is to say the incident's own signature, mid-season, would have read as healthy inside
    # the settle window. Only the NEWEST week can legitimately be missing: week W−1 closed at least
    # a week ago, so a feed that lacks it is behind for a reason the vendor's cadence cannot excuse.
    gap = (last_completed_week - reading.last_week) if reading.last_week is not None else None
    explicable = gap == 1 or (reading.last_week is None and last_completed_week == 1)

    hours = None
    if slate_ended is not None:
        if slate_ended.tzinfo is None:
            slate_ended = slate_ended.replace(tzinfo=timezone.utc)
        hours = (now - slate_ended).total_seconds() / 3600.0
        if explicable and hours < settle_hours:
            return {
                "verdict": "PENDING", "severity": None, "source": reading.source,
                "last_week": reading.last_week, "expected_week": last_completed_week,
                "detail": (f"`{reading.source}` is at week {reading.last_week} and week "
                           f"{last_completed_week} closed {hours:.1f} h ago — inside the "
                           f"{settle_hours:.0f} h the vendor is allowed to publish it. Healthy."),
            }

    # ⚠️ A season with NO rows at all is the incident's own signature, and it reads differently
    # from "one week behind": nothing ever landed, rather than a cadence that slipped.
    never = reading.last_week is None
    behind = gap
    when = f"{hours:.1f} h ago" if hours is not None else "some time ago"
    return {
        "verdict": "NEVER_INGESTED" if never else "STALE",
        "severity": "CRITICAL" if never else ("CRITICAL" if (behind or 0) > 1 else "ERROR"),
        "source": reading.source,
        "last_week": reading.last_week, "expected_week": last_completed_week,
        "detail": (
            (f"`{reading.source}` carries NO {season} rows at all, and week "
             f"{last_completed_week} closed {when}."
             if never else
             f"`{reading.source}` is stuck at {season} week {reading.last_week}, "
             f"{behind} week(s) behind the last completed week {last_completed_week}, which "
             f"closed {when}.")
            + " The weekly model TRAINS on this feed, and a missing stat line is not an error "
              "downstream — `attach_labels` fills it with a zero under the retained-zero "
              "convention, so the fit learns a P(zero) from weeks nobody played. That is "
              "NF-INC-0916. Check that `nfl_weekly_stats_ingest_op` ran in the most recent "
              "`sports_nfl_weekly_serving_job` run, and that the vendor asset for this season "
              "exists."
        ),
    }


def is_problem(verdict: dict) -> bool:
    return bool(verdict.get("severity"))


def worst(verdicts: list[dict]) -> str | None:
    """The severity to page at across several feeds. ⛔ Silence only when EVERY feed is healthy —
    one stale feed is a finding even if its sibling is fine."""
    order = {"WARN": 1, "ERROR": 2, "CRITICAL": 3}
    sev = [v.get("severity") for v in verdicts if v.get("severity")]
    return max(sev, key=lambda s: order.get(s, 0)) if sev else None
