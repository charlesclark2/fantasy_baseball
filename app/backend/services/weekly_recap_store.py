"""NF-WK-RC1 — the POINT-IN-TIME store for a fetched week's lineups and results.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⛔ THIS IS A RECORD, NOT A CACHE, AND THE DIFFERENCE IS THE WHOLE MODULE
═══════════════════════════════════════════════════════════════════════════════════════════════════

PM ruling (D1/A, 2026-09-16), quoted because the semantics are load-bearing:

    "Fetched weeks are stored server-side, keyed league/week, content-timestamped, as the
     point-in-time record the recap is built from — a recap must be STABLE AFTER IT RENDERS, not
     silently re-derived from a later fetch; a re-fetch that changes a stored final week is a
     NAMED EVENT, not an overwrite."

`s3_cache` is deliberately NOT reused. It is a cache: its keys are date-rotated, and `set_cache`
SWALLOWS a write failure and returns `False`. Both are exactly wrong here — a record that silently
fails to persist is worse than no record, because the next read falls back to a re-fetch and the
"stable after it renders" guarantee is gone with no signal. Writes here RAISE.

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ WHAT "A NAMED EVENT" MEANS MECHANICALLY
───────────────────────────────────────────────────────────────────────────────────────────────────

A second fetch of an already-stored week does NOT overwrite it. `store` compares the new capture
against the stored one on CONTENT (`capturedAt` excluded — a timestamp differs on every fetch and
would make every re-fetch look like a change), and:

  • identical content        → `unchanged`. Nothing is written. This is the common case and it is
                               silent on purpose: a routine re-run must not manufacture events.
  • different content        → `diverged`. The STORED record is KEPT and keeps serving; the new
                               capture is written to a REVISION key so nothing is lost; the caller
                               gets a structured event naming what moved, to page on.
  • nothing stored yet       → `created`.

⚠️ THE DIVERGENCE DIRECTION IS DELIBERATE. Keeping the FIRST capture (rather than the newest) is
what makes a rendered recap stable. A platform can and does restate a played week — a stat
correction, a commissioner override applied late — and the honest product answer is "this is what
we recorded, and here is a notice that the league has since restated it", never a number that
changes underneath a reader with no explanation.

───────────────────────────────────────────────────────────────────────────────────────────────────
WHERE IT LIVES, AND WHY NOT DYNAMO
───────────────────────────────────────────────────────────────────────────────────────────────────

S3 (`CACHE_BUCKET`), under a stable non-rotating prefix. NOT the DynamoDB user row: `fantasy_leagues`
is a map on that row, and NF-C6P3 measured a subscriber's 25 leagues already pressing the shared
400 KB item ceiling with `league_rosters` alone. A per-league-per-week record is league-grained, not
user-grained, and putting it on a user row would also duplicate it for every member of one league.

✅ NO NEW IAM GRANT IS NEEDED — verified rather than assumed (the E8.5 landmine: the first
`app/backend` WRITE to a bucket can hit a read-only grant and fail silently). The API Lambda's
policy already carries `s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket` on
`credence-prod-s3-api-cache` (`infrastructure/aws_resources.md`), and `routers/picks.py` /
`routers/performance.py` write to it today through `s3_cache.set_cache`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

CACHE_BUCKET = os.getenv("CACHE_BUCKET")
_s3 = boto3.client("s3", region_name="us-east-1")

#: A stable, NON-date-rotating prefix. A PIT record is addressable forever or it is not a record.
PREFIX = "fantasy/nfl/recap"

#: Fields excluded from the content comparison. `capturedAt` changes on every fetch by construction,
#: so including it would classify every routine re-fetch as a divergence — an event stream that
#: fires on nothing would be ignored within a week (the muted-monitor pattern).
_VOLATILE_FIELDS: frozenset[str] = frozenset({"capturedAt"})


class RecapStoreError(RuntimeError):
    """The record could not be persisted or read back. Raised rather than swallowed — see header."""


def record_key(season: int | str, week: int, platform: str, league_id: str) -> str:
    return f"{PREFIX}/{int(season)}/wk{int(week)}/{platform}/{league_id}.json"


def revision_key(season: int | str, week: int, platform: str, league_id: str, stamp: str) -> str:
    """Where a DIVERGENT later capture is parked. Never served; kept so nothing is discarded."""
    safe = stamp.replace(":", "").replace("-", "")
    return f"{PREFIX}/{int(season)}/wk{int(week)}/{platform}/{league_id}.revision-{safe}.json"


def _comparable(record: dict) -> str:
    """The record reduced to its CONTENT, canonically ordered, for an exact comparison."""
    return json.dumps(
        {k: v for k, v in record.items() if k not in _VOLATILE_FIELDS},
        sort_keys=True, default=str,
    )


def load(season: int | str, week: int, platform: str, league_id: str) -> dict | None:
    """The stored record, or None if this league-week has never been captured.

    ⛔ A read ERROR is NOT a miss. `NoSuchKey` returns None (there is genuinely nothing stored);
    anything else RAISES, because "we have no record" and "we could not tell" are different facts
    and answering the second with the first would silently trigger a re-fetch that overwrites
    nothing but reports a created record (NF1.7(a): a check that could not run is not a pass).
    """
    if not CACHE_BUCKET:
        raise RecapStoreError("CACHE_BUCKET is not configured; there is nowhere to store a recap")
    key = record_key(season, week, platform, league_id)
    try:
        return json.loads(_s3.get_object(Bucket=CACHE_BUCKET, Key=key)["Body"].read())
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise RecapStoreError(f"could not read the stored recap at {key}: {exc}") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise RecapStoreError(f"the stored recap at {key} is not readable JSON: {exc}") from exc


def _put(key: str, record: dict) -> None:
    try:
        _s3.put_object(
            Bucket=CACHE_BUCKET, Key=key,
            Body=json.dumps(record, default=str), ContentType="application/json",
        )
    except Exception as exc:  # noqa: BLE001
        raise RecapStoreError(f"could not write the recap record at {key}: {exc}") from exc


def store(record: dict) -> dict:
    """Persist a freshly fetched week. Returns `{status, key, ...}`; NEVER overwrites content.

    `status` is one of `created` · `unchanged` · `diverged`. On `diverged` the STORED record is what
    keeps serving and the new capture is parked at `revisionKey`; `changedTeams` names which teams
    moved, so the event says WHAT changed rather than only THAT something did.
    """
    if not CACHE_BUCKET:
        raise RecapStoreError("CACHE_BUCKET is not configured; there is nowhere to store a recap")
    season, week = record["season"], record["week"]
    platform, league_id = record["platform"], record["leagueId"]
    key = record_key(season, week, platform, league_id)

    existing = load(season, week, platform, league_id)
    if existing is None:
        _put(key, record)
        logger.info("recap record created: %s", key)
        return {"status": "created", "key": key}

    if _comparable(existing) == _comparable(record):
        return {"status": "unchanged", "key": key}

    stamp = str(record.get("capturedAt") or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    rev = revision_key(season, week, platform, league_id, stamp)
    _put(rev, record)
    event = {
        "status": "diverged",
        "key": key,
        "revisionKey": rev,
        "storedAt": existing.get("capturedAt"),
        "refetchedAt": record.get("capturedAt"),
        "changedTeams": _changed_teams(existing, record),
    }
    logger.warning("recap record DIVERGED (stored record kept): %s — %s", key, event["changedTeams"])
    return event


def _changed_teams(before: dict, after: dict) -> list[str]:
    """Which teams' entries differ between two captures — the event's substance.

    A team present in only one capture counts as changed; that is a real difference (a roster added
    or removed) and reporting only the intersection would hide exactly the biggest change there is.
    """
    def by_key(rec: dict) -> dict[str, str]:
        return {
            str(t.get("teamKey")): json.dumps(t, sort_keys=True, default=str)
            for t in (rec.get("teams") or []) if isinstance(t, dict)
        }
    a, b = by_key(before), by_key(after)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
