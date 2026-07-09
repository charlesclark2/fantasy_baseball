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
    ap.add_argument("--no-dynamo", action="store_true",
                    help="Skip the DynamoDB delete (do S3 only). The api-cache DELETE perm is split: "
                         "the LAPTOP (baseball-access) can DeleteObject on S3 but NOT DeleteItem on "
                         "DynamoDB; the BOX role can DeleteItem but not S3. So run --no-dynamo on the "
                         "laptop and --no-s3 on the box — BOTH halves must complete (the API falls "
                         "back to the S3 permanent blob, so deleting only DynamoDB still serves null).")
    args = ap.parse_args()

    tbl = boto3.resource("dynamodb", region_name=_DDB_REGION).Table(_TABLE)
    s3 = None if (args.no_s3 or not _S3_BUCKET) else boto3.client("s3", region_name="us-east-1")
    if not _S3_BUCKET and not args.no_s3:
        print("(CACHE_BUCKET unset — S3 permanent-blob delete skipped; run --no-dynamo on a host with "
              "CACHE_BUCKET set to purge the S3 blobs.)")

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
    ddb_ok = ddb_fail = s3_ok = s3_fail = 0
    for sk, gp in frozen:
        print(f"  {'DELETE' if args.apply else 'would delete'}: sk={sk} (game_pk={gp})")
        if not args.apply:
            continue
        if not args.no_dynamo:
            try:
                tbl.delete_item(Key={"pk": "picks", "sk": sk})
                ddb_ok += 1
            except Exception as exc:  # noqa: BLE001 — perm-split: laptop lacks DeleteItem
                ddb_fail += 1
                print(f"    (DynamoDB delete FAILED for {sk}: {type(exc).__name__} — run --no-s3 on the box)")
        if s3 is not None:
            key = f"api-cache/permanent/picks/game/{gp}.json"
            try:
                s3.delete_object(Bucket=_S3_BUCKET, Key=key)
                s3_ok += 1
            except Exception as exc:  # noqa: BLE001 — S3 blob may not exist / box lacks DeleteObject
                s3_fail += 1
                print(f"    (S3 delete FAILED for {key}: {type(exc).__name__})")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to delete. Each purged row rebuilds fresh on the next "
              "/picks/<pk>/detail request. NOTE the delete perm is split across environments — run "
              "`--apply --no-dynamo` on the LAPTOP (S3 blobs) and `--apply --no-s3` on the BOX (DynamoDB "
              "rows); BOTH must complete or the API keeps serving the surviving null copy.")
        return 0

    print(f"\nApplied. DynamoDB: {ddb_ok} deleted, {ddb_fail} failed. S3: {s3_ok} deleted, {s3_fail} failed.")
    need = []
    if ddb_fail:
        need.append("DynamoDB rows still frozen → run `--apply --no-s3` on the BOX (has DeleteItem)")
    if s3_fail or (s3 is None and not args.no_s3):
        need.append("S3 permanent blobs still frozen → run `--apply --no-dynamo` on the LAPTOP with "
                    "CACHE_BUCKET set (has DeleteObject)")
    if need:
        print("⚠️ INCOMPLETE — the API falls back S3←→DynamoDB, so a game is only fixed once BOTH are gone:")
        for n in need:
            print(f"   • {n}")
    else:
        print(f"✅ All {len(frozen)} frozen finals purged on this backend's side; they rebuild populated on next access.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
