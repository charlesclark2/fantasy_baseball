"""fantasy_import_telemetry.py — coverage-gap telemetry for platform league imports (NF-C0d).

🎯 THE QUESTION THIS ANSWERS. NF-C0's import already classifies every scoring term a league carries
as applied / derived / CAPTURED (a term the league really scores and our board really ignores — see
`platform_import/canonical.py`'s module docstring), and shows that to the user. Until now the verdict
was thrown away the moment the page closed, so nobody on our side could tell whether a given captured
term is common (worth building) or a long-tail curiosity. This module records just enough to answer
that, and nothing else.

🔒 AGGREGATE, NOT SURVEILLANCE. A row is `{platform, key, weight, verdict, season, imported_at}` —
the SCORING RULE and its point value, never a user id, team name, or roster. The question is "which
settings do our users' leagues have that we can't honour", which needs the rule, not the person.
`fantasy_import.py`'s `/import/telemetry` route enforces this at the boundary: its request model has
no field for anything else, so there is nothing identifying to forward even if a caller tried.

🚫 BEST-EFFORT, NEVER BLOCKING. `record_captured_terms` is called after a league import has already
saved successfully. It must never turn a successful import into a failed one, so every path through
it is non-raising: an absent bucket, a boto3 error, a malformed row — all just log a warning and
return. The import already succeeded; this is peripheral bookkeeping about it (the E11.7 WARN-tier
shape, applied to an API-side write instead of a pipeline op).

💾 STORE: S3, one small JSON object per import (mirrors `s3_cache.py`'s direct `boto3.client` use —
no pandas/pyarrow in this Lambda, see `canonical.py`'s docstring). Deliberately NOT the users table:
this data has no user to key on, and riding a per-user item would mean scanning every user's row to
read it back, which is both slow and puts aggregate telemetry needlessly next to account data.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_REGION = os.getenv("AWS_REGION", "us-east-1")
CACHE_BUCKET = os.getenv("CACHE_BUCKET")
_s3 = boto3.client("s3", region_name=_REGION)

_PREFIX = "fantasy-import-telemetry"

# Hard ceiling on what one import can write — a captured-term list this long would be a client bug,
# not a real league, and there is no reason to let it turn into an unbounded S3 object.
MAX_TERMS_PER_IMPORT = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_captured_terms(platform: str, season: str | None, terms: list[dict]) -> None:
    """Best-effort: write one small JSON blob recording this import's CAPTURED scoring terms.

    `terms` is a list of `{key, weight, verdict}` dicts — exactly the fields the coverage panel
    already renders. Non-raising by design (see the module docstring): an import must never fail,
    or even surface an error, because this write failed.
    """
    if not terms:
        return
    if not CACHE_BUCKET:
        logger.debug("fantasy_import_telemetry: CACHE_BUCKET unset — skipping telemetry write")
        return
    rows = []
    for t in terms[:MAX_TERMS_PER_IMPORT]:
        try:
            rows.append({
                "platform": str(platform),
                "key": str(t["key"])[:120],
                "weight": float(t.get("weight", 0.0)),
                "verdict": str(t.get("verdict") or "captured"),
                "season": str(season) if season else None,
                "imported_at": _now_iso(),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return
    key = f"{_PREFIX}/{platform}/{uuid4()}.json"
    try:
        _s3.put_object(
            Bucket=CACHE_BUCKET,
            Key=key,
            Body=json.dumps(rows).encode("utf-8"),
            ContentType="application/json",
        )
    except Exception:  # noqa: BLE001 — a telemetry write must never propagate
        logger.warning("fantasy_import_telemetry: S3 write failed for %s", key, exc_info=True)


def list_captured_term_rows() -> list[dict]:
    """Every recorded row, flattened across every import object. Non-raising — returns [] on any
    S3 failure so a broken telemetry read can never take down the admin panel."""
    if not CACHE_BUCKET:
        return []
    out: list[dict] = []
    try:
        paginator = _s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=CACHE_BUCKET, Prefix=f"{_PREFIX}/"):
            for obj in page.get("Contents", []):
                try:
                    resp = _s3.get_object(Bucket=CACHE_BUCKET, Key=obj["Key"])
                    rows = json.loads(resp["Body"].read().decode("utf-8"))
                    if isinstance(rows, list):
                        out.extend(r for r in rows if isinstance(r, dict))
                except (ClientError, ValueError, KeyError):
                    logger.warning("fantasy_import_telemetry: skipping unreadable object %s", obj.get("Key"))
    except Exception:  # noqa: BLE001
        logger.warning("fantasy_import_telemetry: S3 list failed", exc_info=True)
        return []
    return out


def aggregate_captured_terms(rows: list[dict]) -> list[dict]:
    """Group CAPTURED rows by (platform, key) and rank by frequency × |weight|.

    Pure function over already-fetched rows, so the ranking math is unit-testable without S3. Only
    `verdict == "captured"` rows count toward the ranking — this module exists to size the coverage
    GAP, and an applied/derived row (if one is ever recorded) would dilute that signal.

    `score = occurrences × avg(|weight|)`, not `occurrences × total(|weight|)`: total already grows
    with occurrences, so scoring on the total would double-count frequency. Averaging isolates "how
    much this rule is worth when a league has it" as the second factor, matching the story's own
    example (a term in 40% of leagues at 6 points matters far more than one seen once at 1 point).
    """
    groups: dict[tuple[str, str], dict] = {}
    for row in rows:
        if str(row.get("verdict") or "captured") != "captured":
            continue
        platform = str(row.get("platform") or "")
        key = str(row.get("key") or "")
        if not platform or not key:
            continue
        try:
            weight = float(row.get("weight", 0.0))
        except (TypeError, ValueError):
            weight = 0.0
        imported_at = str(row.get("imported_at") or "")

        g = groups.setdefault(
            (platform, key),
            {"platform": platform, "key": key, "occurrences": 0, "_abs_weight_sum": 0.0, "last_seen_at": ""},
        )
        g["occurrences"] += 1
        g["_abs_weight_sum"] += abs(weight)
        if imported_at > g["last_seen_at"]:
            g["last_seen_at"] = imported_at

    out = []
    for g in groups.values():
        occurrences = g["occurrences"]
        avg_abs_weight = g["_abs_weight_sum"] / occurrences if occurrences else 0.0
        out.append({
            "platform": g["platform"],
            "key": g["key"],
            "occurrences": occurrences,
            "avg_abs_weight": round(avg_abs_weight, 4),
            "score": round(occurrences * avg_abs_weight, 4),
            "last_seen_at": g["last_seen_at"] or None,
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out
