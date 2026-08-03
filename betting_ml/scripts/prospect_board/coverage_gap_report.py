"""coverage_gap_report.py — E8.5: the board-build side of E8.2's coverage-gap egress.

`app/backend/services/coverage_gap_egress.py` writes one small JSON object per (user, league) to
`s3://baseball-betting-ml-artifacts/baseball/milb/derived/prospect_board_coverage_gaps/` every time
an admin's league is saved, re-uploaded, patched, or drafted from. This module is the OTHER end: it
reads every one of those objects and turns them into a report `build_prospect_board.py` writes
alongside the board itself, so an operator building the next board sees, unprompted, which rostered
"prospects" the current league imports think we are missing.

⚠️ THIS NEVER TOUCHES BOARD MEMBERSHIP. Adding a name to the board is a deliberate, versioned
decision — a new prospect has to run through the MLE translation / FV join / comp assembly like
every other row, which RE-RANKS the whole board, and a board that silently reorders itself because
someone uploaded a fantasy roster would be worse UX and worse provenance than the blind spot this
closes (E8.2's operator decision, carried forward unchanged). `build_report()` only ASSEMBLES a table
for a human to read; nothing here writes to the board DataFrame or the lake.

🩹 A SECOND, INDEPENDENT SELF-HEAL CHECK. `board_match.match_roster` already re-evaluates a
`missing_from_board` flag against the CURRENT board on every API call, so a gap usually clears itself
out of the egress well before a human ever reads this report. But a league nobody has touched since
the last board publish would still carry a STALE egress object — so `still_missing` is recomputed
here too, straight against the board THIS run just assembled, rather than trusted from the S3 blob.
That makes a stale object able to only UNDER-report (it already self-healed and just hasn't been
re-written yet), never over-report a gap that quietly reappeared out of band.

🔒 PRIVACY (E8.2's open question — still open, on purpose). `list_all()` returns every user's
objects, but each row stays tagged with its OWN `user_id`; nothing here merges counts or names across
users. The moment a report is meant to span users is a privacy decision this module does not make.

Never raises on a read failure — a missing/unreadable egress object degrades to "no gaps to report",
never a failed board build (the board itself does not depend on this in any way).
"""

from __future__ import annotations

import json
import logging
import os

import boto3
import pandas as pd

log = logging.getLogger("e8_5.coverage_gap_report")

_REGION = "us-east-2"
_PREFIX = "baseball/milb/derived/prospect_board_coverage_gaps"


def _bucket() -> str:
    return os.getenv("ARTIFACTS_BUCKET", "baseball-betting-ml-artifacts")


def list_all() -> list[dict]:
    """Every league's coverage-gap egress object, exactly as written — one dict per (user, league).

    Tolerates a malformed/legacy object (missing keys, a non-list `coverage_gaps`, or an
    unparseable body — e.g. a blob written by an earlier version of the egress writer) by skipping
    just that one object and logging a warning, never failing the whole read.
    """
    bucket = _bucket()
    s3 = boto3.client("s3", region_name=_REGION)
    out: list[dict] = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=f"{_PREFIX}/")
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                try:
                    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                    record = json.loads(body)
                    if not isinstance(record, dict):
                        raise ValueError("egress object is not a JSON object")
                    out.append(record)
                except Exception:  # noqa: BLE001 — one bad object must not sink the whole report
                    log.warning("coverage_gap_report: could not read %s", key, exc_info=True)
    except Exception:  # noqa: BLE001 — e.g. no objects yet, or a transient S3 error
        log.warning("coverage_gap_report: could not list s3://%s/%s", bucket, _PREFIX, exc_info=True)
    return out


def build_report(board: pd.DataFrame, *, name_col: str = "player_name") -> pd.DataFrame:
    """Cross-reference every egressed gap against the board THIS run just assembled.

    `name_col` defaults to `player_name` — the raw column `build_prospect_board.py`'s `final`
    DataFrame carries (see `export_prospect_board_json.py`'s `_COLUMNS`, which is what remaps it to
    `name` for the served board.json `board_match.py` reads back against).

    Returns an EMPTY DataFrame (not None) when there is nothing to report, so a caller can always
    check `.empty` rather than a None-vs-DataFrame branch.
    """
    board_names = {
        str(n).strip().lower()
        for n in board.get(name_col, pd.Series(dtype=str))
        if str(n).strip()
    }
    rows: list[dict] = []
    for record in list_all():
        if not isinstance(record, dict):
            continue
        gaps = record.get("coverage_gaps")
        if not isinstance(gaps, list):
            continue
        for gap in gaps:
            if not isinstance(gap, dict):
                continue
            name = str(gap.get("name") or "").strip()
            if not name:
                continue
            rows.append({
                "user_id": record.get("user_id"),
                "league_id": record.get("league_id"),
                "league_name": record.get("league_name"),
                "league_scope": record.get("league_scope"),
                "name": name,
                "org": gap.get("org"),
                "positions": gap.get("positions"),
                "status": gap.get("status"),
                "source": gap.get("source"),
                # The belt-and-suspenders self-heal check, against THIS build's board — not the
                # board that was live when the league was last touched.
                "still_missing": name.lower() not in board_names,
            })

    report = pd.DataFrame(rows, columns=[
        "user_id", "league_id", "league_name", "league_scope", "name", "org", "positions",
        "status", "source", "still_missing",
    ])
    if report.empty:
        return report
    return report.sort_values(
        by=["still_missing", "source", "name"], ascending=[False, True, True]
    ).reset_index(drop=True)
