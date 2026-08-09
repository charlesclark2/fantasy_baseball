"""run_nf_serving_board_snapshot.py — retain the CURRENTLY-SERVED fantasy key space (flip tracking).

Operator requirement (2026-08-08, NF-W2b closeout): before ANY champion/board flip, the
rankings the application is CURRENTLY showing must be retained — for EVERY year it is
showing — so the new rankings can be compared against them. The robust reading of "all years
we're currently showing" is an ENUMERATION of the live key space, not a hardcoded year list:
this tool lists everything under the served prefix (`fantasy/nfl/` — per-season boards +
manifest + projections.json + track_record/) and server-side-copies it to an IMMUTABLE dated
snapshot prefix in the same bucket, OUTSIDE the served key space:

    s3://$CACHE_BUCKET/fantasy/nfl/<season>/board_*.json   →  s3://$CACHE_BUCKET/snapshots/<tag>/fantasy/nfl/<season>/board_*.json

The backend reads only `fantasy/...` keys, so nothing under `snapshots/` can ever serve.
A snapshot tag REFUSES to overwrite (immutability): re-running with the same tag on a
non-empty destination is an error, never a merge.

⚠️ NF-D12-style guard: the default is a DRY-RUN that prints the exact inventory it would
retain. Pass `--execute` to actually write. A dry-run against prod is read-only; `--execute`
writes to the PRODUCTION api-cache bucket (under `snapshots/` only).

RUN (LAPTOP — needs $CACHE_BUCKET; the api-cache bucket lives in us-east-1, pinned here):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_serving_board_snapshot
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_serving_board_snapshot --execute
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_serving_board_snapshot --execute --download artifacts/served_board_snapshots
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

log = logging.getLogger("nfl.fantasy.serving_board_snapshot")

#: The served key space this tool retains. The backend's fantasy reads all live under here
#: (boards/manifest/projections per season + track_record/); `snapshots/` is outside it.
DEFAULT_LIVE_PREFIX = "fantasy/nfl/"
SNAPSHOT_ROOT = "snapshots/"
#: The api-cache bucket region (matches app.backend.services.s3_cache + the board exporter) —
#: pinned so a laptop AWS_DEFAULT_REGION=us-east-2 (the ML-artifacts bucket) can't misroute.
CACHE_REGION = "us-east-1"

_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_tag(tag: str) -> str:
    if not _TAG_RE.match(tag):
        raise ValueError(
            f"snapshot tag {tag!r} must be [A-Za-z0-9._-]+ (it becomes an S3 prefix segment)")
    return tag


def snapshot_key(live_key: str, tag: str) -> str:
    """Destination key: the live key verbatim, under snapshots/<tag>/ — so a diff tool can walk
    the retained tree with the same relative paths the app serves."""
    return f"{SNAPSHOT_ROOT}{tag}/{live_key}"


def list_live_keys(s3, bucket: str, prefix: str) -> list[dict]:
    keys: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append({"Key": obj["Key"], "Size": int(obj["Size"]),
                         "LastModified": str(obj.get("LastModified", ""))})
    return keys


def inventory(keys: list[dict], prefix: str) -> dict:
    """Group by first path segment under the live prefix (season year / track_record / …) so
    the operator can SEE which years are being retained."""
    groups: dict[str, dict] = {}
    for k in keys:
        rel = k["Key"][len(prefix):] if k["Key"].startswith(prefix) else k["Key"]
        seg = rel.split("/", 1)[0] if "/" in rel else "(root)"
        g = groups.setdefault(seg, {"n_files": 0, "bytes": 0})
        g["n_files"] += 1
        g["bytes"] += k["Size"]
    return dict(sorted(groups.items()))


def assert_tag_unused(s3, bucket: str, tag: str) -> None:
    """A snapshot is IMMUTABLE: refuse a tag whose destination prefix already holds objects."""
    resp = s3.list_objects_v2(Bucket=bucket, Prefix=f"{SNAPSHOT_ROOT}{tag}/", MaxKeys=1)
    if resp.get("KeyCount", 0) > 0:
        raise SystemExit(
            f"snapshot tag {tag!r} already exists under s3://{bucket}/{SNAPSHOT_ROOT}{tag}/ — "
            f"a retained snapshot is immutable; pick a new tag instead of overwriting the record")


def run_snapshot(s3, bucket: str, prefix: str, tag: str, *, execute: bool,
                 download_dir: Path | None = None) -> dict:
    keys = list_live_keys(s3, bucket, prefix)
    if not keys:
        raise SystemExit(
            f"nothing is served under s3://{bucket}/{prefix} — refusing to record an empty "
            f"snapshot as if the app were showing nothing (NF1.7 (a))")
    inv = inventory(keys, prefix)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bucket": bucket, "live_prefix": prefix, "tag": tag,
        "snapshot_prefix": f"{SNAPSHOT_ROOT}{tag}/",
        "n_files": len(keys), "total_bytes": sum(k["Size"] for k in keys),
        "groups": inv, "executed": bool(execute),
    }
    log.info("live key space s3://%s/%s — %d files across: %s",
             bucket, prefix, len(keys), ", ".join(inv))
    if not execute:
        log.warning("DRY-RUN (default): nothing written. Re-run with --execute to retain "
                    "%d files under s3://%s/%s%s/", len(keys), bucket, SNAPSHOT_ROOT, tag)
        return summary

    assert_tag_unused(s3, bucket, tag)
    log.warning("🚨 WRITING to the PROD api-cache bucket (snapshots/ prefix only): "
                "s3://%s/%s%s/ (%d files)", bucket, SNAPSHOT_ROOT, tag, len(keys))
    for k in keys:
        s3.copy_object(Bucket=bucket, Key=snapshot_key(k["Key"], tag),
                       CopySource={"Bucket": bucket, "Key": k["Key"]})
    # the retained inventory rides beside the copies — the manifest of what was showing
    s3.put_object(Bucket=bucket, Key=f"{SNAPSHOT_ROOT}{tag}/_snapshot_manifest.json",
                  Body=json.dumps(summary, indent=2).encode(),
                  ContentType="application/json")
    if download_dir is not None:
        for k in keys:
            dest = download_dir / tag / k["Key"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, k["Key"], str(dest))
        log.info("local copies → %s", download_dir / tag)
    log.info("retained %d files under s3://%s/%s%s/", len(keys), bucket, SNAPSHOT_ROOT, tag)
    return summary


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Retain the currently-served fantasy key space")
    ap.add_argument("--bucket", default=os.getenv("CACHE_BUCKET"),
                    help="api-cache bucket (default $CACHE_BUCKET)")
    ap.add_argument("--prefix", default=DEFAULT_LIVE_PREFIX,
                    help=f"served key space to retain (default {DEFAULT_LIVE_PREFIX})")
    ap.add_argument("--tag", default=None,
                    help="snapshot tag (default preflip-<UTCdate>); immutable once written")
    ap.add_argument("--execute", action="store_true",
                    help="actually write (default: DRY-RUN inventory only)")
    ap.add_argument("--download", type=Path, default=None,
                    help="also download local copies under <dir>/<tag>/ (with --execute)")
    args = ap.parse_args(argv)
    if not args.bucket:
        raise SystemExit("no bucket: pass --bucket or set $CACHE_BUCKET")
    tag = validate_tag(args.tag or f"preflip-{datetime.now(timezone.utc).strftime('%Y%m%d')}")

    import boto3  # plain client — instance-role/AWS_PROFILE safe (test_boto3_credential_lint)

    s3 = boto3.client("s3", region_name=CACHE_REGION)
    summary = run_snapshot(s3, args.bucket, args.prefix, tag,
                           execute=args.execute, download_dir=args.download)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
