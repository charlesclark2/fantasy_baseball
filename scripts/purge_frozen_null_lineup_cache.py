"""purge_frozen_null_lineup_cache.py — one-time cleanup for INC-31 Defect B.

WHY: the game-detail serving cache (DynamoDB credence-prod-serving-cache, pk='picks',
sk='game/<pk>#PERMANENT') froze a batch of FINAL games with lineups=null. Root cause: the
S3 stg_statsapi_lineups_wide parquet is re-exported only in the daily (morning) run, so an
evening Final game read via the --s3 path missed that slate's lineups → lineups=None, and it
was written PERMANENT. A permanent blob is never re-read, so those games serve null lineups
forever. The anti-freeze guard (write_serving_store.py / picks.py) STOPS new freezes, but the
already-frozen rows must be purged so the next request rebuilds them fresh (the S3 parquet has
since caught up, so the rebuild attaches lineups and — now that lineups are present — re-freezes
them CORRECTLY as permanent).

WHAT: scans pk='picks', sk begins_with 'game/…#PERMANENT', finds rows whose lineups are null/
empty, and DELETES them from DynamoDB (+ the S3 api-cache/permanent/ mirror blob). Dry-run by
default; pass --apply to delete. Deletion is safe + reversible: the very next /picks/<pk>/detail
request (or the next write_serving_store --game-detail run) rebuilds the blob from S3.

RUN (laptop, with the baseball-access creds, OR the box):
    uv run python scripts/purge_frozen_null_lineup_cache.py            # dry-run (report only)
    uv run python scripts/purge_frozen_null_lineup_cache.py --apply    # delete the frozen rows
"""
from __future__ import annotations

import argparse
import json
import os

import boto3
from boto3.dynamodb.conditions import Key

# Mirror the serving-cache config: serving_cache.py (DynamoDB) + s3_cache.py (CACHE_BUCKET, us-east-1).
_DDB_REGION = os.environ.get("AWS_REGION", "us-east-1")
_TABLE = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_S3_BUCKET = os.environ.get("CACHE_BUCKET")  # same env the writers use; None → skip S3


def _lineups_present(payload: dict) -> bool:
    ln = payload.get("lineups") or {}
    return bool(ln.get("home") or ln.get("away"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge frozen null-lineup PERMANENT game-detail cache rows (INC-31)")
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    ap.add_argument("--no-s3", action="store_true", help="Skip the S3 permanent-blob delete")
    args = ap.parse_args()

    tbl = boto3.resource("dynamodb", region_name=_DDB_REGION).Table(_TABLE)
    s3 = None if (args.no_s3 or not _S3_BUCKET) else boto3.client("s3", region_name="us-east-1")
    if not _S3_BUCKET and not args.no_s3:
        print("(CACHE_BUCKET unset — S3 permanent-blob delete skipped; DynamoDB delete still applies.)")

    # Page through every picks/game/* row and keep the PERMANENT ones with null lineups.
    frozen: list[tuple[str, str]] = []  # (sk, game_pk)
    lek = None
    scanned = 0
    while True:
        kw = dict(KeyConditionExpression=Key("pk").eq("picks") & Key("sk").begins_with("game/"))
        if lek:
            kw["ExclusiveStartKey"] = lek
        resp = tbl.query(**kw)
        for it in resp.get("Items", []):
            scanned += 1
            sk = it["sk"]
            if not sk.endswith("#PERMANENT"):
                continue
            try:
                payload = json.loads(it["value"])
            except Exception:
                continue
            if not _lineups_present(payload):
                gp = sk.split("#", 1)[0].split("/", 1)[1]
                frozen.append((sk, gp))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break

    print(f"Scanned {scanned} picks/game rows; {len(frozen)} PERMANENT rows have null lineups.")
    for sk, gp in frozen:
        print(f"  {'DELETE' if args.apply else 'would delete'}: sk={sk} (game_pk={gp})")
        if args.apply:
            tbl.delete_item(Key={"pk": "picks", "sk": sk})
            if s3 is not None:
                key = f"api-cache/permanent/picks/game/{gp}.json"
                try:
                    s3.delete_object(Bucket=_S3_BUCKET, Key=key)
                except Exception as exc:  # noqa: BLE001 — S3 blob may not exist; non-fatal
                    print(f"    (s3 delete skipped for {key}: {exc})")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to delete. Each purged row rebuilds fresh on "
              "the next /picks/<pk>/detail request or write_serving_store --game-detail run.")
    else:
        print(f"\nPurged {len(frozen)} frozen-null PERMANENT rows. They will rebuild populated on next access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
