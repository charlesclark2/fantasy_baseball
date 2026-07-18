"""purge_empty_model_skill_cache.py — one-time cleanup for E9.26b (INC-31 anti-freeze class).

WHY: the /performance/model "Model Skill" endpoint cached a DEGENERATE result —
``{"season": 2026, "markets": []}`` — at the first request of the day (the compute
transiently returned nothing before the daily lakehouse export landed / a swallowed
DuckDB-S3 read error in ``lakehouse_read.lakehouse_query`` → ``[]``). The blob is
date-scoped (``api-cache/<date>/performance/model_*.json``) but got RE-written empty
every morning and then SERVED FROZEN for the rest of that day → the page renders empty
even though the data is fine (a fresh recompute returns the populated per-market tally).

The anti-freeze guard in ``app/backend/routers/performance.py`` STOPS new empty blobs
from being cached (and IGNORES an empty cached blob on read), so this purge is belt-and-
suspenders: it removes any already-written empty ``model_*.json`` blobs so the endpoint
recomputes cleanly. A populated blob is NEVER deleted.

WHAT: scans the S3 API-cache bucket (CACHE_BUCKET, us-east-1) for
``**/performance/model_*.json`` objects, parses each, and DELETES only the ones whose
``markets`` list is empty. Dry-run by default; pass --apply to delete. Safe + reversible:
the next /performance/model request rebuilds the blob from the lakehouse.

RUN (laptop, with the baseball-access creds — has S3 DeleteObject):
    uv run python scripts/purge_empty_model_skill_cache.py            # dry-run (report only)
    uv run python scripts/purge_empty_model_skill_cache.py --apply    # delete the empty blobs
"""
from __future__ import annotations

import argparse
import json
import os

import boto3

# Mirror s3_cache.py: the API-cache bucket lives in us-east-1 (DIFFERENT from the
# us-east-2 lakehouse bucket). CACHE_BUCKET is the same env the backend writers use.
_S3_BUCKET = os.environ.get("CACHE_BUCKET", "credence-prod-s3-api-cache")
_S3_REGION = "us-east-1"


def _is_empty_model_blob(body: bytes) -> bool:
    """True when a model_*.json blob carries an EMPTY per-market tally (the degenerate
    result E9.26b froze). A blob we can't parse is left alone (not our target)."""
    try:
        payload = json.loads(body)
    except Exception:  # noqa: BLE001 — unparseable → not a clean empty target, skip
        return False
    return isinstance(payload, dict) and not payload.get("markets")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Purge empty (markets:[]) /performance/model_*.json cache blobs (E9.26b anti-freeze)"
    )
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    ap.add_argument("--bucket", default=_S3_BUCKET, help=f"Cache bucket (default: {_S3_BUCKET})")
    args = ap.parse_args()

    if not args.bucket:
        print("CACHE_BUCKET unset and no --bucket given — nothing to do.")
        return 1

    s3 = boto3.client("s3", region_name=_S3_REGION)
    paginator = s3.get_paginator("list_objects_v2")

    # Every model_*.json under any performance/ prefix (date-scoped api-cache/<date>/... AND
    # the permanent api-cache/permanent/... prefix, in case one was ever written there).
    empty: list[str] = []
    scanned = 0
    for page in paginator.paginate(Bucket=args.bucket, Prefix="api-cache/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if "/performance/model_" not in key or not key.endswith(".json"):
                continue
            scanned += 1
            try:
                body = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
            except Exception as exc:  # noqa: BLE001
                print(f"    (read FAILED for {key}: {type(exc).__name__} — skipping)")
                continue
            if _is_empty_model_blob(body):
                empty.append(key)

    print(f"Scanned {scanned} performance/model_*.json blobs; {len(empty)} are EMPTY (markets:[]).")
    ok = fail = 0
    for key in empty:
        print(f"  {'DELETE' if args.apply else 'would delete'}: {key}")
        if not args.apply:
            continue
        try:
            s3.delete_object(Bucket=args.bucket, Key=key)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"    (delete FAILED for {key}: {type(exc).__name__})")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to delete. Each purged blob rebuilds populated "
              "on the next /performance/model request (the anti-freeze guard won't re-cache empty).")
        return 0

    print(f"\nApplied. S3: {ok} deleted, {fail} failed.")
    if fail:
        print("⚠️ Some deletes failed — re-run, or check S3 DeleteObject permission.")
    else:
        print(f"✅ All {len(empty)} empty Model-Skill cache blobs purged; the page recomputes populated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
