"""preflight_s3.py  (NFL-N0.2 — instance-role write preflight)
===============================================================
Confirm the box's instance role can WRITE + READ + DELETE the NFL lake prefix BEFORE the real
backfill — exercising the EXACT auth paths the ingest uses, not a bare boto3 put (a raw put can
pass while delta-rs' object_store signing fails — the AKID landmine):

  1. STS identity   — prints the resolved principal (the instance-role ARN on the box).
  2. delta-rs write — a 1-row throwaway Delta table via `s3io.write_dataframe` (the same
                      `storage_options()` credential-chain path the whole ingest uses).
  3. delta_scan read-back — via `query_lake` (DuckDB credential_chain), proves the object is
                      readable through the serving read path.
  4. cleanup        — deletes the `nfl/raw/_preflight/` prefix (boto3 default chain).

Writes ONLY under `s3://<bucket>/nfl/raw/_preflight/` — touches no real source. Exit 0 = the
role has write+read+delete on the prefix; exit 1 = a permission/auth gap (the message says which
step failed). Run ON THE BOX (the instance role is what we're testing; the laptop IAM is RO).

  docker compose -f services/dagster/aws/docker-compose.yml exec -T \
    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
    python -m quant_sports_intel_models.football.nfl.ingest.preflight_s3
"""
from __future__ import annotations

import sys

from . import s3io
from . import query_lake as ql

SOURCE = "_preflight"


def main() -> int:
    bucket = s3io.DEFAULT_BUCKET
    region = s3io.DEFAULT_REGION
    uri = s3io.table_uri("nfl", SOURCE, bucket=bucket)
    print(f"NFL S3 write preflight → bucket={bucket} region={region}\n  table={uri}")

    # 1) identity — surface the principal delta-rs/boto3 will sign as (the instance role ARN).
    try:
        import boto3

        ident = boto3.client("sts", region_name=region).get_caller_identity()
        print(f"  [1/4] STS identity: {ident.get('Arn')}  (account {ident.get('Account')})")
    except Exception as exc:  # noqa: BLE001
        print(f"  [1/4] STS identity FAILED: {exc}")
        print("PREFLIGHT FAIL — no resolvable AWS credentials (instance role not attached?).")
        return 1

    # 2) delta-rs WRITE via the ingest's own storage_options() (the real path).
    try:
        import pandas as pd

        df = pd.DataFrame({"season": [1900], "probe": ["nfl-n0.2-preflight"]})
        n = s3io.write_dataframe(df, sport="nfl", source=SOURCE, season=1900, bucket=bucket)
        print(f"  [2/4] delta-rs WRITE ok: {n} row → {uri}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [2/4] delta-rs WRITE FAILED: {exc}")
        print("PREFLIGHT FAIL — the role cannot s3:PutObject on nfl/raw/* (or the AKID/object_store "
              "auth is misconfigured — see the CLAUDE.md delta-rs AKID landmine).")
        return 1

    # 3) delta_scan READ-BACK via query_lake (DuckDB credential_chain).
    try:
        got = ql.q(f"select count(*) c, max(probe) p from {ql.delta(SOURCE)}")
        c = int(got["c"].iloc[0])
        assert c >= 1 and got["p"].iloc[0] == "nfl-n0.2-preflight"
        print(f"  [3/4] delta_scan READ-BACK ok: {c} row(s), probe value verified")
    except Exception as exc:  # noqa: BLE001
        print(f"  [3/4] delta_scan READ-BACK FAILED: {exc}")
        print("PREFLIGHT FAIL — wrote but cannot read back (s3:GetObject/ListBucket gap?).")
        return 1

    # 4) CLEANUP — delete the whole _preflight prefix (leave the lake pristine).
    try:
        import boto3

        s3 = boto3.client("s3", region_name=region)
        prefix = f"nfl/raw/{SOURCE}/"
        deleted = 0
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
                deleted += len(objs)
        print(f"  [4/4] CLEANUP ok: deleted {deleted} object(s) under {prefix}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [4/4] CLEANUP FAILED (write+read PASSED, but s3:DeleteObject gap): {exc}")
        print(f"PREFLIGHT PARTIAL — write+read OK; manually remove s3://{bucket}/nfl/raw/{SOURCE}/")
        return 1

    print("PREFLIGHT PASS — instance role has write+read+delete on nfl/raw/*.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
