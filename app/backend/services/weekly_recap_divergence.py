"""NF-WK-ACC1 (PM rider ⑥ on NF-WK-RC1's closeout, 2026-09-17) — the divergence RECORDER, wired.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY THIS EXISTS
═══════════════════════════════════════════════════════════════════════════════════════════════════

RC1's D2 disposition (C) required that "the construction still runs, silently, as a divergence
recorder … log the per-week divergence set (which teams, ours vs theirs, delta) to an artifact (B)
consumes". RC1's closeout (⑥) then measured that NOTHING in production called either
`weekly_recap.compare_to_platform` or `realized_dst.dst_row` — the 35-of-48 figure came from a
one-off in-session probe, and the stream the recorder was supposed to produce did not exist.

This module is the production caller. The recap route invokes `record` after scoring a week.

───────────────────────────────────────────────────────────────────────────────────────────────────
⛔ RECORD-ONLY, AS RULED — THREE PROPERTIES, EACH ENFORCED HERE
───────────────────────────────────────────────────────────────────────────────────────────────────

1. IT NEVER PAGES. There is no `send_alert` on this path, and `compare_to_platform` carries
   `mayAlert: False` in the data. A comparison known to diverge must not page (the muted-monitor
   pattern arriving on day one).
2. IT NEVER CHANGES WHAT A USER SEES. The served D/ST seat stays the league's published figure;
   nothing computed here is returned to the caller.
3. IT NEVER FAILS A RECAP. The router wraps `record`, so a missing input or a failed write costs the
   record, not the page. The failure is LOGGED as a warning, never swallowed silently.

⭐ A MISSING D/ST INPUT IS RECORDED, NOT SKIPPED. If the box has not published this week's
`dst_inputs.json`, the player leg is still recorded and the D/ST leg reports
`constructionSupplied: False` — "we could not check" must never look like "it matched" (NF1.7(a)).

───────────────────────────────────────────────────────────────────────────────────────────────────
WHERE IT WRITES, AND HOW OFTEN
───────────────────────────────────────────────────────────────────────────────────────────────────

S3 (`CACHE_BUCKET`, the bucket the recap store already writes — no new IAM grant, see
`weekly_recap_store`'s header), one object per league-week under `recap-divergence/`. The record is
REWRITTEN only when its content changed: the D/ST input legitimately fills in later (the
Monday-night result lands in `schedules` up to a week late, PM card yOhLHprC), so the newest
comparison is the one worth keeping, and an unchanged re-view writes nothing.

⚠️ COVERAGE IS "LEAGUES SOMEONE VIEWED". The recorder runs on the recap path, so a league nobody
opens produces no record. That is the ruled placement ("a production caller on the recap path"),
stated here so the stream is never read as covering every saved league.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from app.backend.services import realized_dst, weekly_recap

logger = logging.getLogger(__name__)

#: Where one league-week's divergence record lives. A stable, non-rotating prefix, separate from the
#: recap store's own `fantasy/nfl/recap/` so neither lister can mistake the other's objects.
PREFIX = "fantasy/nfl/recap-divergence"


_S3 = None


def _client():
    """One lazily-built client per warm container — never built at import (the cold-start rule)."""
    global _S3
    if _S3 is None:
        import boto3
        _S3 = boto3.client("s3", region_name="us-east-1")
    return _S3


def record_key(season: int, week: int, platform: str, league_id: str) -> str:
    return f"{PREFIX}/{int(season)}/wk{int(week)}/{platform}/{league_id}.json"


def captured_weights(coverage: dict) -> dict[str, float]:
    """The league's captured terms and their weights — the input to the explained split."""
    return {
        t["key"]: float(t.get("weight") or 0.0)
        for t in (coverage.get("terms") or [])
        if t.get("verdict") == "captured"
    }


def build_record(
    *,
    scored: dict,
    scoring: dict,
    dst_inputs: dict | None,
    realized_by_seat: dict,
) -> dict:
    """PURE — the record for one league-week. Separate from `record` so it is testable without S3,
    and so the cross-check harness can drive the identical computation."""
    teams = (dst_inputs or {}).get("teams")
    if isinstance(teams, dict):
        dst_points, pending = realized_dst.score_dst_lines(teams, scoring)
    else:
        dst_points, pending = None, None
    comparison = weekly_recap.compare_to_platform(
        scored,
        dst_constructed=dst_points,
        dst_result_pending=pending,
        captured_weights=captured_weights(scored.get("coverage") or {}),
        realized_by_seat=realized_by_seat,
    )
    return {
        "season": scored.get("season"),
        "week": scored.get("week"),
        "platform": scored.get("platform"),
        "leagueId": scored.get("leagueId"),
        "leagueCapturedAt": scored.get("capturedAt"),
        "dstInputsGeneratedAt": (dst_inputs or {}).get("generated_at"),
        "comparison": comparison,
    }


def _content_hash(rec: dict) -> str:
    return hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()


def record(
    *,
    scored: dict,
    scoring: dict,
    dst_inputs: dict | None,
    realized_by_seat: dict,
    league_id: str,
    s3=None,
    bucket: str | None = None,
) -> dict:
    """Build the record and persist it if it changed. Returns `{status, key}`.

    RAISES on a failed read/write — the CALLER decides the tier (the router logs and continues).
    """
    rec = build_record(scored=scored, scoring=scoring, dst_inputs=dst_inputs,
                       realized_by_seat=realized_by_seat)
    # The key is OUR saved-league id; the platform's own id stays on the record beside it.
    rec["platformLeagueId"] = rec.get("leagueId")
    rec["leagueId"] = league_id
    rec["contentSha256"] = _content_hash(rec)
    bucket = bucket or os.getenv("CACHE_BUCKET")
    if not bucket:
        raise RuntimeError("CACHE_BUCKET is not configured; the divergence record has nowhere to go")
    if s3 is None:
        s3 = _client()
    key = record_key(rec["season"], rec["week"], rec["platform"] or "", league_id)
    try:
        prior = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404"):
            raise
        prior = None
    if prior is not None and prior.get("contentSha256") == rec["contentSha256"]:
        return {"status": "unchanged", "key": key}
    rec["recordedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(rec, default=str),
                  ContentType="application/json")
    dst = rec["comparison"]["dstSeats"]
    logger.info("[recap-divergence] %s: players %s/%s diverging (%s unexplained); dst %s/%s "
                "diverging (%s unexplained, construction supplied=%s)", key,
                rec["comparison"]["playerSeats"]["diverging"],
                rec["comparison"]["playerSeats"]["compared"],
                rec["comparison"]["playerSeats"]["unexplained"],
                dst["diverging"], dst["compared"], dst["divergingUnexplained"],
                dst["constructionSupplied"])
    return {"status": "created" if prior is None else "updated", "key": key}
