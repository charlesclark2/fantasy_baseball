"""NF-INFRA2 — the INC-41 freshness SLA for the PUBLISHED NFL draft board itself.

WHY THIS EXISTS, AND WHY IT CANNOT LIVE IN THE PUBLISH JOB
──────────────────────────────────────────────────────────
`sports_nfl_board_publish_job` already verifies the artifact it just shipped (`_verify_published`).
That check is necessary and it is structurally incapable of answering the question this module
asks, because **it only runs when the job runs**. The failure this module exists to catch is the
job NOT RUNNING — a schedule reverted to STOPPED by a Dagster-DB reset, a code location that
failed to load, a daemon that stopped ticking, a `SkipReason` branch that started firing every
day. In every one of those states there is no run, so there is no verification, and the last
green run in Dagit is a real green run. The board simply stops advancing and every producer-side
instrument stays quiet.

That is the same lesson INC-41 and NF-FRESH1 already paid for, one level up: **assert the
ARTIFACT, from OUTSIDE the producer.** `sports_delta_freshness` does it for the sports lake's
INPUT tables; this does it for the OUTPUT the user actually reads.

⛔ NEVER AN S3 `LastModified` (INC-41's central mechanic). The exporter re-uploads all ~15 board
files on every publish, so an mtime advances whenever the uploader ran — including a run that
re-uploaded a stale staging directory. The timestamp used here is `manifest.generated_at`, which
the exporter stamps at build time from the build's own clock, so it advances if and only if a
board was actually rebuilt. It is also the exact field `_verify_published` and the served UI
stamp read, so the monitor, the job and the product cannot disagree about what "fresh" means.

⚠️ THE SLA IS DERIVED FROM THE SCHEDULE'S OWN CADENCE, NOT PINNED SEPARATELY. The publish
schedule is daily through draft season and weekly (Mondays) otherwise, and it decides that with
`is_draft_season` — which now lives HERE and is imported by the schedule, so the cadence has ONE
owner. A hand-pinned SLA beside a cadence predicate is the "one logical thing, many owners" shape
this repo keeps paying for (INC-30 / INC-36 / INC-38); a monitor whose window silently disagrees
with its subject's cadence false-pages every off-season Tuesday.

TIERING — this module DECIDES, it never pages or raises (the E11.23 rule: nothing here imports
`pipeline`, so the fast gate can import it). The paging lives in `pipeline/jobs/…`.

⚠️ AN UNREADABLE BOARD IS `UNKNOWN`/WARN, NEVER HEALTHY (NF1.7(a)) — a check that could not run is
not a check that passed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

#: The prod api-cache bucket the gated `/fantasy/nfl/*` routes read, and the region it lives in.
#: Pinned to match `export_draft_board_json._upload_to_s3` + `app.backend.services.s3_cache` —
#: the cache bucket is us-east-1 even though the sports LAKE is us-east-2, and reading it from the
#: wrong region is the INC-45 class (a 301 that returns nothing rather than an error).
DEFAULT_CACHE_BUCKET = "credence-prod-s3-api-cache"
CACHE_BUCKET_REGION = "us-east-1"


def board_manifest_key(season: int) -> str:
    """The published manifest's S3 key — mirrors `export_draft_board_json._upload_to_s3`."""
    return f"fantasy/nfl/{season}/manifest.json"


# ── Cadence (the ONE owner; `sports_rollforward_schedules` imports these) ────────────────────
def is_draft_season(today: date) -> bool:
    """August 1 → September 15: the window in which fantasy drafts actually happen.

    Clock-derived and injectable, never a pinned year — the NCAAF-P0.6 stale-by-a-season landmine
    that `current_season()` exists to avoid, applied to a cadence instead of a season. The end
    bound reaches past the ~Sep-9 opener because leagues keep drafting through week 1.

    The window is intentionally GENEROUS at both ends. Being wrong toward "daily" costs one cheap
    rebuild; being wrong toward "weekly" costs a drafting user a board built on a market up to six
    days old, which is the entire defect NF-FRESH2 existed to fix.

    ⭐ MOVED HERE BY NF-INFRA2 (it was defined in the schedule module) so the publish cadence and
    the freshness SLA that judges it read the SAME predicate. The schedule re-exports it, so every
    existing caller and guard is unchanged."""
    return today.month == 8 or (today.month == 9 and today.day <= 15)


#: The publish schedule's two cadences, in hours (`NFL_BOARD_PUBLISH_CRON` = 07:15 PT daily, with
#: the schedule itself skipping non-Mondays outside draft season).
DAILY_CADENCE_HOURS = 24.0
WEEKLY_CADENCE_HOURS = 168.0

#: Grace on top of the cadence. It has to absorb TWO things, and the first is easy to forget:
#:   * the CHECK/PUBLISH OFFSET — the monitor rides the 06:30 PT NFL job while the board publishes
#:     at 07:15 PT, so a board published exactly on schedule is already **23.25h** old the next
#:     time anything looks at it. An SLA equal to the cadence (24h) therefore leaves just 45
#:     MINUTES of lateness tolerance before it pages on a healthy board — the offset silently eats
#:     almost the entire budget, which is why the grace is sized against the OBSERVED lag and not
#:     against the cadence.
#:   * genuine lateness — a slow build, a deploy window.
#: 6.75h of real lateness tolerance on the daily cadence puts the bar at 30h: comfortably above a
#: healthy 23.25h and comfortably below the 47.25h a SKIPPED DAY produces, which is the event this
#: must catch. The same 12h grace on the weekly cadence sits between a healthy 167.25h and the
#: 335.25h of a skipped Monday.
DAILY_GRACE_HOURS = 6.75
WEEKLY_GRACE_HOURS = 12.75

#: How far back to look when deciding which cadence governed the publish being judged. On the
#: FIRST day(s) of draft season the newest publish may legitimately be the previous WEEKLY one, so
#: judging it by the daily SLA would false-page on exactly the day the daily cadence starts — the
#: seasonal-boundary hole (E9.48(c) / INC-37) applied to an SLA instead of an ingest. Looking back
#: two days means the daily cadence has certainly produced at least one publish before the tighter
#: bar is applied. Erring toward the LOOSER bar at a boundary is the safe direction: the cost is
#: one day of reduced sensitivity, versus a guaranteed false CRITICAL that trains the operator to
#: ignore this monitor.
CADENCE_BOUNDARY_LOOKBACK_DAYS = 2


def cadence_hours(today: date) -> float:
    """The cadence that governs the publish being judged ON `today` — daily only when the daily
    cadence has been in force across the whole lookback window (see the boundary note above)."""
    if all(is_draft_season(today - timedelta(days=d))
           for d in range(CADENCE_BOUNDARY_LOOKBACK_DAYS + 1)):
        return DAILY_CADENCE_HOURS
    return WEEKLY_CADENCE_HOURS


def sla_hours(today: date) -> float:
    """The staleness bar for a board judged on `today` — cadence + its grace."""
    if cadence_hours(today) == DAILY_CADENCE_HOURS:
        return DAILY_CADENCE_HOURS + DAILY_GRACE_HOURS
    return WEEKLY_CADENCE_HOURS + WEEKLY_GRACE_HOURS


def cadence_label(today: date) -> str:
    return ("daily (draft season, Aug 1 – Sep 15)"
            if cadence_hours(today) == DAILY_CADENCE_HOURS
            else "weekly (Mondays, outside draft season)")


# ── The reading ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class BoardReading:
    """What the PUBLISHED manifest actually said (or why it could not be read)."""

    season: int
    generated_at: datetime | None = None   # tz-aware UTC
    adp_as_of: str | None = None
    coherence_present: bool = False
    error: str | None = None

    @property
    def readable(self) -> bool:
        return self.error is None and self.generated_at is not None


def classify(reading: BoardReading, *, now: datetime | None = None,
             today: date | None = None) -> dict:
    """PURE — the verdict for one published-board reading.

    Verdicts: `OK` · `STALE` (over the cadence-derived SLA) · `UNKNOWN` (unreadable — WARN, never
    healthy). Severity mirrors `sports_delta_freshness`: within 2x the SLA is a missed cycle
    (WARN); beyond it the publisher is not running at all (CRITICAL).
    """
    now = now or datetime.now(timezone.utc)
    today = today or now.date()
    bar = sla_hours(today)
    label = cadence_label(today)

    if not reading.readable:
        return {
            "name": "nfl_published_board", "verdict": "UNKNOWN", "severity": "WARN",
            "lag_hours": None, "sla_hours": bar, "cadence": label,
            "detail": (
                f"could not read the published board manifest for season {reading.season} "
                f"(s3://{DEFAULT_CACHE_BUCKET}/{board_manifest_key(reading.season)}): "
                f"{reading.error or 'no generated_at'}. Reported UNVERIFIED rather than healthy — "
                "a check that could not run is not a check that passed. FIRST ACTION: confirm the "
                "object exists and that this box can read the api-cache bucket "
                f"(region {CACHE_BUCKET_REGION})."),
        }

    lag_hours = round((now - reading.generated_at).total_seconds() / 3600.0, 2)
    if lag_hours > bar:
        severity = "WARN" if lag_hours <= 2 * bar else "CRITICAL"
        return {
            "name": "nfl_published_board", "verdict": "STALE", "severity": severity,
            "lag_hours": lag_hours, "sla_hours": bar, "cadence": label,
            "detail": (
                f"the SERVED NFL draft board was generated {lag_hours}h ago "
                f"({reading.generated_at.isoformat()}), over the {bar}h SLA for its {label} "
                "cadence. Users are reading a board that has stopped advancing — market, depth "
                "chart and injury designations are all frozen at that timestamp. The most likely "
                "cause is that sports_nfl_board_publish_job is NOT RUNNING (a schedule reverted "
                "to STOPPED, a code location that failed to load, or a stalled daemon), which "
                "produces no failed run to notice. FIRST ACTION: check "
                "sports_nfl_board_publish_schedule is RUNNING in Dagit and read its most recent "
                "tick; if it is running and ticking, read the last run's logs — the publish op "
                "pages and raises rather than shipping nothing."),
        }
    return {
        "name": "nfl_published_board", "verdict": "OK", "severity": None,
        "lag_hours": lag_hours, "sla_hours": bar, "cadence": label,
        "detail": (f"published board generated {lag_hours}h ago "
                   f"({reading.generated_at.isoformat()}), within the {bar}h {label} SLA"
                   + (f"; adp_as_of={reading.adp_as_of}" if reading.adp_as_of else "")),
    }


def is_problem(verdict: dict) -> bool:
    """True when the verdict warrants operator attention (anything but OK)."""
    return verdict.get("verdict") != "OK"


# ── The reader (IO — imported lazily so this module stays fast-gate safe) ────────────────────
def read_published_manifest(season: int, *, bucket: str | None = None,
                            local_path: str | None = None) -> BoardReading:
    """Read the PUBLISHED manifest. Never raises — an unreadable board becomes a `BoardReading`
    carrying the error, which `classify` turns into UNKNOWN/WARN.

    `local_path` reads a file instead of S3 (used by the guards and by an operator checking a
    staged artifact); it is never the box path."""
    try:
        if local_path:
            blob = json.loads(open(local_path, "rb").read())
        else:
            import boto3  # lazy: keeps this module importable in the fast gate

            # ⛔ NO explicit `aws_access_key_id=os.environ.get(...)` — on the box those vars are
            # UNSET and passing None DISABLES the instance-role credential chain
            # (test_boto3_credential_lint.py enforces this repo-wide).
            s3 = boto3.client("s3", region_name=CACHE_BUCKET_REGION)
            obj = s3.get_object(Bucket=bucket or os.environ.get("CACHE_BUCKET")
                                or DEFAULT_CACHE_BUCKET,
                                Key=board_manifest_key(season))
            blob = json.loads(obj["Body"].read())
        return reading_from_manifest(season, blob)
    except Exception as exc:  # noqa: BLE001 — surfaced as UNKNOWN/WARN, never swallowed
        return BoardReading(season=season, error=f"{type(exc).__name__}: {exc}")


def reading_from_manifest(season: int, blob: object) -> BoardReading:
    """PURE — turn a manifest blob into a `BoardReading`. Split out from the IO so the verdict
    path is testable without S3."""
    if not isinstance(blob, dict):
        return BoardReading(season=season,
                            error=f"manifest is {type(blob).__name__}, not an object")
    raw = blob.get("generated_at")
    try:
        stamp = datetime.fromisoformat(str(raw))
    except Exception:  # noqa: BLE001
        return BoardReading(season=season,
                            error=f"manifest.generated_at is unparseable ({raw!r})")
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return BoardReading(
        season=season,
        generated_at=stamp,
        adp_as_of=blob.get("adp_as_of"),
        coherence_present=isinstance(blob.get("coherence"), dict),
    )


def evaluate(season: int, *, now: datetime | None = None, bucket: str | None = None,
             local_path: str | None = None) -> dict:
    """Read + classify the published board. One verdict dict."""
    now = now or datetime.now(timezone.utc)
    reading = read_published_manifest(season, bucket=bucket, local_path=local_path)
    return classify(reading, now=now)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-INFRA2 — PUBLISH-TIME artifact verification (the guards `_verify_published` fires)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The SLA above asks "is the board still advancing?" from OUTSIDE, on a cadence. This half asks
# "is the thing I am about to serve actually complete?" at publish time, from INSIDE the job.
#
# ⚖️ WHY PRESENCE RAISES AND STALENESS ONLY PAGES — this is a ratified product decision, not a
# taste call, and getting it backwards would be actively harmful. The PM ruled on exactly this
# tradeoff for NF-INJ1's coherence guard (2026-08-21): the guard STAYS ALERT, because HALTing a
# publish blocks EVERY other fix riding that publish — the run that would have been blocked was
# the one that corrected 23 injured players. Blocking publishes blocks injury refreshes. So:
#   * a MISSING stamp / a MISSING coherence block ⇒ FATAL (raise). Absence means the pipeline
#     structurally broke, or a guard silently stopped running (the vacuous-guard class), and a
#     board whose vintage is UNKNOWN is the original NF-FRESH1 defect wearing a new stamp.
#   * a STALE-but-PRESENT stamp ⇒ ALERT (page, publish anyway). Publishing on a known-stale feed
#     is a bounded, HONEST degradation — the served `input_vintage` block says so on every
#     surface — whereas refusing to publish freezes the whole board over one late feed.
#
# ⛔ THE BARS ARE STALENESS BARS, NOT "DID IT ADVANCE" BARS, and that is deliberate. A feed
# legitimately repeats a value between publishes (FantasyPros' ECR label holds for a day; the FFC
# ADP window moves in steps), so requiring every stamp to ADVANCE on every publish would false-
# fail on healthy days. A bar is also strictly STRONGER where it counts: a stamp that advanced
# from 30 days stale to 29 days stale passes "advance" and fails a bar.


@dataclass(frozen=True)
class FeedStamp:
    """One vintage stamp the published manifest must carry, and how stale it may be."""

    name: str                    # `[METRIC]` key
    path: tuple[str, ...]        # where it lives in the manifest blob
    max_lag_hours: float
    why: str                     # what degrades when this feed freezes


#: ⚠️ Deliberately small, and every entry is a stamp we have OBSERVED on a real published board
#: (2026-08-23). An unmeasured claim about a stamp's cadence produces a permanent false page —
#: the reason INC-41 REJECTED `feature_pregame_game_features_raw` from its own registry.
#: ⛔ The INJURY feed is NOT here on purpose: its bar is already owned by
#: `projection_coherence.assess_injury_input_freshness` (72h = 2x the feed's own Delta SLA) and is
#: published in the manifest's `coherence.injury_input` block, which this module READS below.
#: Re-declaring it here would be a second owner of one bar — the exact shape that makes an SLA and
#: its subject drift apart.
REQUIRED_FEED_STAMPS: tuple[FeedStamp, ...] = (
    FeedStamp(
        name="adp_as_of", path=("adp_as_of",), max_lag_hours=96.0,
        why=("the market half of the board — ADP drives every board's ordering reference and the "
             "`--market-refresh` chain that NF-FRESH2 P1 exists to keep live"),
    ),
    FeedStamp(
        name="ecr_as_of", path=("ecr_as_of",), max_lag_hours=96.0,
        why="the expert-consensus reference column shown beside every projection",
    ),
    FeedStamp(
        name="depth_chart_as_of", path=("freshness", "input_vintage", "depth_chart_as_of"),
        max_lag_hours=72.0,
        why=("the most-decayed model INPUT on the board — it decays into the PROJECTION (expected "
             "games, the mover-opportunity rescale, `depth_rank` itself), not just a reference "
             "column. This job refreshes it itself, ALERT-continue, so a frozen stamp means that "
             "refresh has been failing"),
    ),
)


def _parse_stamp(raw: object) -> datetime | None:
    """Parse a vintage stamp into tz-aware UTC, or None if it is unusable.

    ⚠️ The manifest carries THREE shapes today, measured on the real artifact: a DATE
    (`adp_as_of` = "2026-08-23"), a NAIVE datetime (`depth_chart_as_of` =
    "2026-08-23 07:28:22", whose timezone the producer does not declare), and a tz-aware ISO
    stamp (`sleeper_status_as_of`). A naive value is read as UTC — the resulting few hours of
    possible skew is irrelevant against bars measured in DAYS, and the alternative (rejecting it)
    would page on a healthy board. ⛔ Do NOT tighten these bars toward the skew without first
    making the producer declare a timezone: this repo has four separate LTZ/NTZ confusion bugs on
    record, and a bar within the ambiguity would be the fifth."""
    if raw is None:
        return None
    try:
        stamp = datetime.fromisoformat(str(raw))
    except Exception:  # noqa: BLE001
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _dig(blob: dict, path: tuple[str, ...]) -> object:
    cur: object = blob
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def verify_manifest(blob: object, *, started: datetime,
                    now: datetime | None = None) -> dict:
    """PURE — the publish-time verdict on a manifest this run just staged.

    Returns `{"fatal": [...], "alerts": [...], "stamps": {name: lag_hours|None}}`. The caller
    pages on both lists and raises on `fatal` (see the tiering note above).

    `started` is the run's own start time: `generated_at` must not predate it, which is what
    catches an exporter that silently reused a staged directory or a publish that ran against
    yesterday's export. That check is stronger than any staleness bar for this one field, so
    `generated_at` deliberately has no bar."""
    now = now or datetime.now(timezone.utc)
    fatal: list[str] = []
    alerts: list[str] = []
    stamps: dict[str, float | None] = {}

    if not isinstance(blob, dict):
        return {"fatal": [f"the staged manifest is {type(blob).__name__}, not an object"],
                "alerts": [], "stamps": {}}

    # 1. generated_at — this run's, not a reused artifact's.
    raw = blob.get("generated_at")
    generated = _parse_stamp(raw)
    if generated is None:
        fatal.append(f"manifest.generated_at is missing/unparseable ({raw!r})")
    elif generated < started - timedelta(minutes=2):
        # A tiny tolerance absorbs clock skew between the op and the subprocess, nothing more.
        fatal.append(f"manifest.generated_at={raw} predates this run ({started.isoformat()}) — "
                     "a STALE artifact was published")

    # 2. Every declared feed stamp: PRESENT (fatal) and within its bar (alert).
    for stamp in REQUIRED_FEED_STAMPS:
        value = _dig(blob, stamp.path)
        parsed = _parse_stamp(value)
        if parsed is None:
            stamps[stamp.name] = None
            fatal.append(
                f"manifest.{'.'.join(stamp.path)} is missing/unparseable ({value!r}) — the board "
                f"shipped with an UNKNOWN vintage for {stamp.name}. {stamp.why}")
            continue
        lag = round((now - parsed).total_seconds() / 3600.0, 2)
        stamps[stamp.name] = lag
        if lag > stamp.max_lag_hours:
            alerts.append(
                f"{stamp.name}={value} is {lag}h old, over its {stamp.max_lag_hours}h bar. "
                f"{stamp.why}. The board was PUBLISHED ANYWAY (a known-stale feed is an honest, "
                "bounded degradation; refusing to publish would freeze every other fix riding "
                "this cycle) — but this feed's refresh needs attention.")

    # 3. The coherence block — PRESENT is fatal, its verdict is an alert.
    #    ⭐ Presence is fatal because its ABSENCE means `report_publish_coherence` did not run at
    #    all: the NF-INJ1 guard would then be silently GONE while every step still exited 0, which
    #    is precisely the vacuous-guard failure this repo keeps paying for. Its CONTENT is an
    #    alert because the PM ratified that guard as ALERT-tier.
    coherence = blob.get("coherence")
    if not isinstance(coherence, dict):
        fatal.append(
            "manifest.coherence is missing — `report_publish_coherence` (the NF-INJ1 "
            "point-vs-games coherence guard) did not run on this artifact, so the board shipped "
            "UNCHECKED. Every step can still have exited 0; a guard that stopped running is "
            "indistinguishable from a guard that passed unless its output is asserted.")
    else:
        injury = coherence.get("injury_input")
        verdict = (injury or {}).get("verdict") if isinstance(injury, dict) else None
        if verdict is None:
            alerts.append("manifest.coherence.injury_input carries no verdict — the injury-input "
                          "freshness of this board is UNVERIFIED (not healthy).")
        elif verdict != "OK":
            alerts.append(
                f"manifest.coherence.injury_input={verdict}: "
                f"{(injury or {}).get('detail', 'no detail')}")

    return {"fatal": fatal, "alerts": alerts, "stamps": stamps}
