"""nfl_ros_freshness.py — NF-ROS1b node 4: the enable flag and the freshness SLA for the PUBLISHED
rest-of-season value (`fantasy/nfl/ros/<season>/...`).

TIERING — this module DECIDES, it never pages or raises, and it imports nothing from `pipeline`
(E11.23: the fast gate must be able to import it). The paging lives in `pipeline/jobs/…`.

⭐ THE DEPLOY-HELD BOUNDARY IS AN ENV FLAG, NOT A `default_status=STOPPED` SCHEDULE. The publish is
a branch of `sports_nfl_weekly_serving_job`, whose schedule already self-starts and is in the
heartbeat's required set. A STOPPED default cannot be heartbeat-checked (the heartbeat flags only a
PERSISTED STOPPED row, and a volume reset leaves none — NCAAF-P1.2W / NF-CAP1), so "merged never
means running" is held by `NF_ROS_PUBLISH_ENABLED` instead: unset or not "1" ⇒ the op skips loudly.

⭐ AND THE FLAG IS WATCHED FROM THE ARTIFACT SIDE, so it cannot become the `W7B_LAKEHOUSE_S3` class
(documented, never set, unnoticed). While the flag is off, this module reports `ARMED_NOT_FIRING`
at WARN every day — visible, never CRITICAL (the deliberate pre-enablement state is not an outage,
and a daily CRITICAL on it would get the monitor muted before it ever catches one). Once the flag is
on, a frozen or behind artifact pages CRITICAL. It is deliberately NOT in `env.required`: that would
fail the next deploy to enforce a default whose correct value at deploy time is OFF.

⛔ NEVER AN S3 `LastModified` (INC-41). Freshness is `manifest.generated_at` and
`manifest.throughWeek`, written by the builder.

⏳ ACTIVE ONLY WHILE THERE IS A FINAL WEEK TO SERVE. Before week 1 is final there is nothing to
update and the publisher exits 3 without writing; the verdict is INACTIVE (not OK — an inactive check
is uninformative, NF1.7(a)). ⚠️ An unreadable artifact or lake is UNKNOWN/WARN, never healthy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

PUBLISH_ENABLED_FLAG = "NF_ROS_PUBLISH_ENABLED"

#: The publish runs inside the DAILY weekly-serving job (08:30 PT). Grace absorbs the offset between
#: that job and the off-cycle job this check rides, and genuine lateness, while staying below the
#: ~47h a skipped day produces — the same sizing `nfl_weekly_freshness` uses for the same cadence.
CADENCE_HOURS = 24.0
GRACE_HOURS = 6.75

#: How long after the lake's newest commit a newly-final week may still be unpublished. The publish
#: runs in the SAME job right after the ingest that makes a week final, so this only has to cover the
#: minutes between the two ops (and an off-cycle read landing in them).
BEHIND_GRACE_HOURS = 2.0


def publish_enabled(env=None) -> bool:
    """PURE — whether a publish tick may fire. Empty counts as unset; anything but "1" is off."""
    import os

    source = os.environ if env is None else env
    return (source.get(PUBLISH_ENABLED_FLAG) or "").strip() == "1"


def sla_hours() -> float:
    return CADENCE_HOURS + GRACE_HOURS


@dataclass(frozen=True)
class RosReading:
    season: int
    through_week: int | None = None
    generated_at: datetime | None = None
    error: str | None = None

    @property
    def published(self) -> bool:
        return self.error is None and self.generated_at is not None


def _parse(raw) -> datetime | None:
    if not raw:
        return None
    try:
        v = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def reading_from_manifest(season: int, blob) -> RosReading:
    """A published manifest → a reading. `None` means NOTHING published (not an error); a malformed
    blob is an error, never a default-shaped healthy reading."""
    if blob is None:
        return RosReading(season=season)
    if not isinstance(blob, dict):
        return RosReading(season=season, error=f"manifest is {type(blob).__name__}")
    gen = _parse(blob.get("generated_at"))
    wk = blob.get("throughWeek")
    if gen is None or not isinstance(wk, int):
        return RosReading(season=season,
                          error=f"manifest lacks generated_at/throughWeek ({blob.get('generated_at')!r}, {wk!r})")
    return RosReading(season=season, through_week=wk, generated_at=gen)


def classify(reading: RosReading, *, enabled: bool, expected_through_week: int | None,
             lake_commit: datetime | None, now: datetime | None = None,
             lake_error: str | None = None) -> dict:
    """PURE — the verdict. `expected_through_week` is the lake's largest contiguous FINAL week
    (0 before week 1 is final); `lake_commit` is `stats_player_week`'s newest commit time."""
    now = now or datetime.now(timezone.utc)
    lag = ((now - reading.generated_at).total_seconds() / 3600
           if reading.generated_at else None)
    base = {"lag_hours": None if lag is None else round(lag, 2),
            "through_week": reading.through_week, "expected_through_week": expected_through_week,
            "sla_hours": sla_hours(), "enabled": enabled}

    def v(verdict, severity, detail):
        return {**base, "verdict": verdict, "severity": severity, "detail": detail}

    if lake_error is not None:
        return v("UNKNOWN", "WARN", f"the lake could not be read ({lake_error}); the published ROS "
                                    "value was NOT judged — unverified, not healthy.")
    if reading.error is not None:
        return v("UNKNOWN", "WARN", f"the published ROS manifest could not be read "
                                    f"({reading.error}) — unverified, not healthy.")
    if not expected_through_week:
        return v("INACTIVE", None, "no REG week is final yet, so there is nothing to update; the "
                                   "check could not have failed (inactive, not passed).")
    if not enabled:
        return v("ARMED_NOT_FIRING", "WARN",
                 f"{PUBLISH_ENABLED_FLAG} is not '1' on the box, so the ROS publish is armed but "
                 f"deliberately not firing (NF-ROS1b's deploy-held state). Week "
                 f"{expected_through_week} is final and the served value "
                 f"{'does not exist' if not reading.published else f'is through week {reading.through_week}'}. "
                 f"TO ENABLE: set {PUBLISH_ENABLED_FLAG}=1 in services/dagster/aws/.env and redeploy.")
    if not reading.published:
        return v("NOTHING_PUBLISHED", "CRITICAL",
                 f"the publish is enabled and week {expected_through_week} is final, but no ROS "
                 f"manifest is served. Consumers keep their stated absences; nothing is updating.")
    if lag is not None and lag > sla_hours():
        return v("STALE", "CRITICAL",
                 f"the served ROS value was generated {lag:.1f}h ago (SLA {sla_hours():.2f}h). The "
                 f"daily publish has stopped landing while it is enabled.")
    if reading.through_week < expected_through_week:
        settled = (lake_commit is None
                   or now - lake_commit > timedelta(hours=BEHIND_GRACE_HOURS))
        if settled:
            return v("BEHIND", "CRITICAL",
                     f"week {expected_through_week} is final in the lake but the served ROS value is "
                     f"through week {reading.through_week}. Every timestamp can look healthy while "
                     f"the value ignores a played week — the INC-37 shape.")
        return v("OK", None, f"week {expected_through_week} became final under "
                             f"{BEHIND_GRACE_HOURS:.0f}h ago; the same-job publish is still due.")
    return v("OK", None, f"through week {reading.through_week}, generated {lag:.1f}h ago.")


def is_problem(verdict: dict) -> bool:
    return verdict.get("severity") is not None
