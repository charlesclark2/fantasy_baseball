#!/usr/bin/env python3
"""Audit ToS acceptance coverage across every Cognito account. (E9.58b)

WHY THIS EXISTS. Since E9.58 opened public self-serve signup, `tos_accepted_at` in
credence-prod-dynamo-users is the only evidence that a given account agreed to the Terms.
Until E9.58b that write was fire-and-forget on BOTH sides — the client swallowed its own
failure and the API caught the exception and returned 204 anyway — so an account could be
created and used with no record and nothing anywhere would say so.

`TermsGate` now stops any signed-in account with no record and will not let go until the
write lands, which closes the gap going FORWARD. This script answers the other half:
**who is already missing one**, including accounts created long before any of this.

⚠️ OPERATOR-ONLY. This needs `cognito-idp:ListUsers` and a read on the users table; the
pipeline's `baseball-access-user` is correctly denied every Cognito `Admin*`/`List*` action,
so run it with your own AWS profile:

    AWS_PROFILE=<operator> uv run python scripts/audit_tos_acceptance.py

    # machine-readable, for diffing coverage across runs
    AWS_PROFILE=<operator> uv run python scripts/audit_tos_acceptance.py --json

Exit code is 1 when any account is missing a record, so it can gate a go-live checklist.

⚠️ This reports the STORE, which is the thing that matters legally — an account showing
`MISSING` here has no acceptance on file regardless of what any UI once displayed to them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import boto3

USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "us-east-1_gG9zMbwQt")
USERS_TABLE = os.getenv("DYNAMO_USERS_TABLE", "credence-prod-dynamo-users")
REGION = os.getenv("AWS_REGION", "us-east-1")


def _cognito_accounts() -> list[dict]:
    """Every account in the pool: its `sub` (the user_id everything else keys on), email,
    status, and creation date. Paginated — ListUsers caps at 60 per page."""
    client = boto3.client("cognito-idp", region_name=REGION)
    out, token = [], None
    while True:
        kwargs = {"UserPoolId": USER_POOL_ID, "Limit": 60}
        if token:
            kwargs["PaginationToken"] = token
        resp = client.list_users(**kwargs)
        for u in resp.get("Users", []):
            attrs = {a["Name"]: a["Value"] for a in u.get("Attributes", [])}
            out.append(
                {
                    "user_id": attrs.get("sub"),
                    "email": attrs.get("email", "—"),
                    "username": u.get("Username"),
                    "federated": "@" not in (u.get("Username") or ""),
                    "status": u.get("UserStatus"),
                    "created": u.get("UserCreateDate").isoformat() if u.get("UserCreateDate") else None,
                }
            )
        token = resp.get("PaginationToken")
        if not token:
            return out


def _acceptance_records() -> dict[str, dict]:
    """user_id → {tos_accepted_at, tos_version} for every row that has one."""
    table = boto3.resource("dynamodb", region_name=REGION).Table(USERS_TABLE)
    records, kwargs = {}, {
        "ProjectionExpression": "user_id, tos_accepted_at, tos_version",
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            uid = item.get("user_id")
            if uid:
                records[uid] = {
                    "tos_accepted_at": item.get("tos_accepted_at"),
                    "tos_version": item.get("tos_version"),
                }
        if "LastEvaluatedKey" not in resp:
            return records
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    accounts = _cognito_accounts()
    records = _acceptance_records()

    rows = []
    for a in accounts:
        rec = records.get(a["user_id"] or "", {})
        accepted_at = rec.get("tos_accepted_at")
        rows.append({**a, "tos_accepted_at": accepted_at, "tos_version": rec.get("tos_version"),
                     "ok": accepted_at is not None})

    missing = [r for r in rows if not r["ok"]]

    if args.json:
        print(json.dumps({"total": len(rows), "missing": len(missing), "accounts": rows},
                         indent=2, default=str))
    else:
        print(f"Cognito accounts: {len(rows)}   with acceptance on file: {len(rows) - len(missing)}"
              f"   MISSING: {len(missing)}\n")
        for r in sorted(rows, key=lambda r: (r["ok"], r["email"])):
            mark = "ok     " if r["ok"] else "MISSING"
            src = "google" if r["federated"] else "native"
            print(f"  {mark}  {r['email']:<40s} {src}  created={r['created']}  "
                  f"accepted={r['tos_accepted_at'] or '—'}  v={r['tos_version'] or '—'}")
        if missing:
            print(
                f"\n{len(missing)} account(s) have NO acceptance record.\n"
                "TermsGate will block each of them at their next signed-in page load until they\n"
                "accept, so this list should shrink on its own as they return. It will NOT shrink\n"
                "for an account that never signs in again — decide separately whether a dormant\n"
                "account without a record matters to you."
            )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
