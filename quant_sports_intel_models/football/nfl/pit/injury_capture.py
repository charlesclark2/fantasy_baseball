"""injury_capture.py — nflverse injury reports captured with OUR OWN `capture_timestamp`.

⏰ WHY (NF-W0 defect #2, and it is worse than it sounds). nflverse DELETED `injuries.date_modified`
in 2025 — the only real as-of timestamp in the free stack. Our ingest runs `schema_mode='merge'`,
so the deleted column did not disappear: it was BACKFILLED WITH NULLS and still reads as present,
which is why the loss went unnoticed. ⇒ for every 2025+ injury report there is currently NO
timestamp saying when the report existed, and one cannot be manufactured after the fact. A report
in the release TODAY might have been published Wednesday or Saturday; a Tuesday build that
consumes it is leaking, and nothing in the data can prove otherwise.

**The only as-of timestamp left is one we make.** Capturing the release on a cadence and stamping
our own `capture_timestamp` gives an UPPER BOUND on when the information existed — the report was
knowable no later than when we saw it. That bound is what the leakage guard can enforce.

⭐ THE SECOND JOB: REVISION DETECTION. An injury report is exactly the kind of record a vendor
rewrites in place (Questionable → Out on Sunday morning, backfilled into the season file). The
immutable store hashes each captured payload, so a later capture whose payload differs from the
original is recognised as a REVISION, the original is kept, and the §13 "revised vendor data
replaced the original captured record" rejection has something real to enforce. Without forward
capture there is no original to compare against and the rejection is unenforceable in principle.

⚠️ `report_status` NULL ≠ HEALTHY (NF-W0). A player on the report with no designation carries a
NULL `report_status`; so does a player absent from the report entirely. Distinguishing them is a
consumer's job, but the capture keeps the raw row so the distinction survives.

TIER: WARN. Snowflake-free, $0 (free nflverse release).
"""
from __future__ import annotations

import logging
from datetime import datetime

from . import store
from .schedule import (
    NFLVERSE_RELEASE,
    current_season,
    data_expected_from,
    looks_like_missing_asset,
)
from .timestamps import CaptureStamps, now_utc

log = logging.getLogger(__name__)

CAPTURE_SOURCE = "injuries"

INJURIES_URL_TMPL = f"{NFLVERSE_RELEASE}/injuries/injuries_{{season}}.parquet"

#: The as-of column nflverse deleted in 2025. Probed EVERY capture — its return would be good
#: news we must not miss, and its continued absence is what justifies our own stamp.
VENDOR_ASOF_COLUMN = "date_modified"


def _duck():
    """Box-aware (pit/duck.py) — never a bare `duckdb.connect()`."""
    from .duck import connect

    return connect()


def read_injuries(season: int, *, con=None, url: str | None = None) -> tuple[list[dict], bool]:
    """`(rows, vendor_asof_present)` for a season's injury release.

    `vendor_asof_present` is measured, not assumed: True only when `date_modified` is BOTH a
    column AND non-null on at least one row. A merge-backfilled all-NULL column reads as PRESENT
    to a schema check — that is precisely how the 2025 deletion hid — so presence alone is not
    evidence and the emptiness is what gets recorded.
    """
    con = con or _duck()
    url = url or INJURIES_URL_TMPL.format(season=int(season))
    df = con.execute("SELECT * FROM read_parquet(?)", [url]).df()
    present = False
    if VENDOR_ASOF_COLUMN in df.columns:
        present = bool(df[VENDOR_ASOF_COLUMN].notna().any())
    return df.to_dict("records"), present


def _subject_key(row: dict, season: int) -> str:
    """One injury REPORT ENTRY = (season, week, player). `gsis_id` is the stable key; the name is
    a fallback so a row with a missing id is still captured under a stable identity rather than
    silently dropped (a dropped row is a silent death — the thing this leg exists to prevent)."""
    player = row.get("gsis_id") or row.get("player_id") or row.get("full_name") or "unknown"
    return f"{season}|w{row.get('week')}|{row.get('team')}|{player}"


def run_injury_capture(
    season: int | None = None,
    *,
    now: datetime | None = None,
    cadence_label: str | None = None,
    rows: list[dict] | None = None,
    vendor_asof_present: bool | None = None,
    bucket: str | None = None,
    local_root: str | None = None,
    dry_run: bool = False,
    expected_from: datetime | None = None,
) -> dict:
    """Capture one snapshot of the season's injury reports, stamped with OUR capture time."""
    now = now or now_utc()
    season = season if season is not None else current_season(now)
    cadence_label = cadence_label or now.strftime("%Y-%m-%dT%H")

    manifest = {
        "season": season, "cadence_label": cadence_label, "now": now.isoformat(),
        "rows_read": 0, "captured": 0, "written": 0, "skipped_duplicate": 0,
        "skipped_recapture": 0, "revisions": [], "vendor_asof_present": None,
        "errors": [], "expected_absent": False, "escalate": False,
    }

    if rows is None:
        try:
            rows, vendor_asof_present = read_injuries(season)
        except Exception as exc:  # noqa: BLE001 — WARN tier
            manifest["errors"].append(str(exc))
            # ⏰ NOT-YET-PUBLISHED ≠ BROKEN. `current_season()` rolls to the new season in March,
            # but nflverse publishes `injuries_<season>.parquet` only once injury reports exist
            # (measured 2026-08-05: no 2026 asset at all, newest was 2025). Without this split the
            # leg pages ERROR on every Tue/Fri fire through the whole pre-season — including both
            # fires before the opener — about a file that is absent by design. Only an
            # unambiguous 404 before the bar is quiet; every other failure still escalates.
            if expected_from is None:
                expected_from = data_expected_from(season)
            if looks_like_missing_asset(str(exc)) and now < expected_from:
                manifest["expected_absent"] = True
                log.info(
                    "[nfl/pit/injuries] injuries_%s.parquet is not published yet (EXPECTED, NOT "
                    "paged — nflverse publishes it once injury reports exist; absence after %s "
                    "escalates): %s",
                    season, expected_from.date().isoformat(), exc,
                )
                return manifest
            manifest["escalate"] = True
            log.warning("ALERT [nfl/pit/injuries] read FAILED for season=%s: %s", season, exc)
            return manifest

    manifest["rows_read"] = len(rows)
    manifest["vendor_asof_present"] = vendor_asof_present
    if vendor_asof_present:
        log.info(
            "[nfl/pit/injuries] nflverse `%s` is POPULATED again for season %s — the vendor as-of "
            "timestamp is back; NF-W0 defect #2 may be re-evaluable.", VENDOR_ASOF_COLUMN, season,
        )
    else:
        log.info(
            "[nfl/pit/injuries] nflverse `%s` is absent/all-NULL for season %s (NF-W0 defect #2) — "
            "OUR capture_timestamp is the only as-of bound.", VENDOR_ASOF_COLUMN, season,
        )

    if dry_run:
        return manifest

    out: list[dict] = []
    for row in rows:
        subject = _subject_key(row, season)
        payload = {k: v for k, v in row.items()}
        stamps = CaptureStamps.build(
            capture_source=CAPTURE_SOURCE,
            subject_key=subject,
            checkpoint=cadence_label,
            payload=payload,
            feature_timestamp=now,
            capture_timestamp=now,
            # ⭐ THE POINT OF THIS LEG. When the vendor as-of is gone, source_timestamp is a
            # DECLARED absence — never quietly filled with our own capture time, which would
            # launder our upper bound into a vendor claim.
            source_timestamp=None,
            vendor_release_timestamp=None,
        )
        r = stamps.as_dict()
        r.update(
            {
                "record_tier": "injury",
                "source_timestamp_absent_reason": (
                    f"nflverse deleted injuries.{VENDOR_ASOF_COLUMN} in 2025 (NF-W0 defect #2); "
                    f"our capture_timestamp is the only remaining as-of bound"
                    if not vendor_asof_present
                    else f"{VENDOR_ASOF_COLUMN} present upstream but not adopted as source_timestamp yet"
                ),
                "season": season,
                "week": row.get("week"),
                "team": row.get("team"),
                "gsis_id": row.get("gsis_id"),
                "full_name": row.get("full_name"),
                "position": row.get("position"),
                "report_status": row.get("report_status"),
                "practice_status": row.get("practice_status"),
                "vendor_asof_present": bool(vendor_asof_present),
                "cadence_label": cadence_label,
                "payload": payload,
            }
        )
        out.append(r)

    manifest["captured"] = len(out)
    if out:
        # REVISION semantics: an injury report row is a record the vendor is expected to publish
        # STABLY, so a changed payload IS the §13 revised-vendor-record case (the very rewrite this
        # leg exists to make detectable) — unlike weather/market, which move by design.
        written = store.append_captures(
            out, source=CAPTURE_SOURCE, bucket=bucket, local_root=local_root,
            semantics=store.REVISION_SEMANTICS,
        )
        manifest.update(
            {k: written[k] for k in ("written", "skipped_duplicate", "skipped_recapture", "revisions")}
        )
        if written["revisions"]:
            log.warning(
                "ALERT [nfl/pit/injuries] %d report(s) REVISED upstream since first capture — the "
                "original stands. This is the §13 revised-vendor-record case, observed live.",
                len(written["revisions"]),
            )
    elif manifest["rows_read"]:
        manifest["escalate"] = True
    return manifest
