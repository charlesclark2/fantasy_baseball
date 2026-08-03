"""coverage_gap_egress.py — E8.5: durable egress for E8.2's board-coverage-gap signal.

WHY THIS EXISTS. E8.2's `RosterMatch.coverage_gaps` (see `mlb_roster/board_match.py`) captures the
one signal worth keeping out of a roster upload: a rostered prospect our board does not carry. Until
now that signal lived only in the league's DynamoDB record and the API response — a clipboard
checklist an admin could read, but nothing the board BUILD
(`betting_ml/scripts/prospect_board/build_prospect_board.py`, an operator-run DuckDB/S3 job with no
knowledge DynamoDB even exists) could ever see. "Tell a human to go add it by hand" is exactly the
step that gets skipped — this closes that gap by writing to the ONE place both sides can reach: S3.

WHAT THIS WRITES, AND WHAT IT DOES NOT DO. One small JSON object per (user, league), to the SAME S3
bucket the board build already reads from (`baseball-betting-ml-artifacts`), at a prefix the build
now also reads (`betting_ml/scripts/prospect_board/coverage_gap_report.py`). It is advisory input for
a human deciding what to consider for the NEXT board build — board membership itself is never
auto-mutated by anything downstream of this (see that module's docstring for why: adding a prospect
has to run through the projection pipeline, which RE-RANKS the board, and a board that silently
reorders because someone uploaded a fantasy roster would be worse UX and worse provenance than the
gap it would close).

Overwritten WHOLESALE on every write, never merged — so a gap that self-heals (the board adds the
missing player, and `board_match.match_roster` re-matches the `missing_from_board` flag against the
current board on every call) disappears from this egress the next time the league is touched, exactly
as it disappears from the API response. There is no separate "clear this" step to forget.

🔒 PRIVACY (E8.2's open question, left open on purpose). The store is siloed PER USER — the S3 key
carries the user_id, and nothing in this module ever reads or merges across users. Aggregating this
signal across an admin's users would be a genuine privacy decision (even with today's single admin,
moot now, load-bearing later); that decision is NOT made here. The board-build reader
(`coverage_gap_report.py`) lists every user's objects but keeps each one tagged by its own user_id.

Never raises — a coverage-gap egress write is advisory, not serving-critical, and must never be the
reason a league save/update/pick fails. Same non-raising convention as `services/s3_cache.py`.
"""

from __future__ import annotations

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

#: The lakehouse bucket's region — matches `build_prospect_board.py` / `lakehouse_read.py`, NOT the
#: `api-cache` bucket's `us-east-1` (see `s3_cache.py`). This egress rides the lakehouse bucket
#: because that is the bucket the board BUILD already reads from — the whole point is landing this
#: where the build can see it without learning a second bucket/region.
_REGION = "us-east-2"
_PREFIX = "baseball/milb/derived/prospect_board_coverage_gaps"


def _bucket() -> str:
    return os.getenv("ARTIFACTS_BUCKET", "baseball-betting-ml-artifacts")


def _key(user_id: str, league_id: str) -> str:
    return f"{_PREFIX}/user={user_id}/league={league_id}.json"


def write(user_id: str, league_id: str, league_meta: dict, coverage_gaps: list[dict]) -> bool:
    """Persist this ONE league's current coverage-gap list, replacing whatever was there before.

    Called from every league-mutating route (save / per-team upload / patch / assign-pick /
    undo-pick) — never from `preview`, which by design stores nothing at all. `league_meta` is the
    stored league record (or the freshly-created one), used only for the human-legible header fields
    (name/scope/season); nothing in it beyond those three fields is written.
    """
    body = {
        "user_id": user_id,
        "league_id": league_id,
        "league_name": league_meta.get("name"),
        "league_scope": league_meta.get("league_scope"),
        "season": league_meta.get("season"),
        "updated_at": league_meta.get("updated_at"),
        "coverage_gaps": coverage_gaps or [],
    }
    try:
        boto3.client("s3", region_name=_REGION).put_object(
            Bucket=_bucket(),
            Key=_key(user_id, league_id),
            Body=json.dumps(body, default=str),
            ContentType="application/json",
        )
        return True
    except Exception:  # noqa: BLE001 — advisory write, never blocks the caller
        logger.warning(
            "coverage_gap_egress.write failed for user=%s league=%s", user_id, league_id,
            exc_info=True,
        )
        return False


def delete(user_id: str, league_id: str) -> None:
    """Remove one league's egress object when the league itself is deleted.

    Best-effort: an orphaned object left behind on a delete failure is stale advisory data at worst
    (the board-build reader tolerates it — see `coverage_gap_report.py`), never a correctness bug.
    """
    try:
        boto3.client("s3", region_name=_REGION).delete_object(
            Bucket=_bucket(), Key=_key(user_id, league_id)
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "coverage_gap_egress.delete failed for user=%s league=%s", user_id, league_id,
            exc_info=True,
        )
