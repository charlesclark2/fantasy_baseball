"""DynamoDB service for per-user bets and the users registry (OLTP).

Bets are transactional (single-row writes on log, per-user reads on page load,
point updates on settle), so they live in DynamoDB rather than Snowflake. See
infrastructure/aws_resources.md for the table specs.

Tables:
  credence-prod-dynamo-user-bets — PK user_id (Cognito sub), SK bet_id.
      Sparse GSI gsi-pending-by-game (PK pending_game_pk): only PENDING bets carry
      pending_game_pk, so the settle job (scripts/settle_user_bets.py) finds them
      there; settling REMOVEs it.
  credence-prod-dynamo-users — PK user_id; email, first_seen_at, last_seen_at.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_REGION = os.getenv("AWS_REGION", "us-east-1")
_USER_BETS_TABLE = os.getenv("USER_BETS_TABLE", "credence-prod-dynamo-user-bets")
_USERS_TABLE = os.getenv("USERS_TABLE", "credence-prod-dynamo-users")

_ddb = boto3.resource("dynamodb", region_name=_REGION)


def _bets_table():
    return _ddb.Table(_USER_BETS_TABLE)


def _users_table():
    return _ddb.Table(_USERS_TABLE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dynamo(d: dict) -> dict:
    """Floats → Decimal (DynamoDB rejects floats); drop None-valued keys."""
    clean = {k: v for k, v in d.items() if v is not None}
    return json.loads(json.dumps(clean, default=str), parse_float=Decimal)


def _from_dynamo(item: dict) -> dict:
    """Decimal → int (when integral) or float, for clean JSON responses."""
    out: dict = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v == v.to_integral_value() else float(v)
        else:
            out[k] = v
    return out


# ── Bets ─────────────────────────────────────────────────────────────────────

def put_bet(user_id: str, bet: dict) -> dict:
    """Write a new bet under user_id. Stamps bet_id/placed_at and marks it pending
    (pending_game_pk = game_pk) so the settle job picks it up via the GSI."""
    item = dict(bet)
    item["user_id"] = user_id
    item["bet_id"] = str(uuid4())
    item["placed_at"] = _now_iso()
    item["pending_game_pk"] = int(bet["game_pk"])
    _bets_table().put_item(Item=_to_dynamo(item))
    return _from_dynamo(_to_dynamo(item))


def list_bets(user_id: str) -> list[dict]:
    """All of a user's bets, newest first. Not S3-cached (per-user OLTP read)."""
    items: list[dict] = []
    kwargs = {"KeyConditionExpression": Key("user_id").eq(user_id)}
    while True:
        resp = _bets_table().query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    bets = [_from_dynamo(it) for it in items]
    bets.sort(key=lambda b: b.get("placed_at", ""), reverse=True)
    return bets


def delete_bet(user_id: str, bet_id: str) -> None:
    """Delete a bet owned by user_id. Raises ValueError if not found."""
    table = _bets_table()
    resp = table.get_item(Key={"user_id": user_id, "bet_id": bet_id})
    if "Item" not in resp:
        raise ValueError("not_found")
    table.delete_item(Key={"user_id": user_id, "bet_id": bet_id})


_IMMUTABLE_KEYS = {"user_id", "bet_id", "placed_at", "game_pk", "pending_game_pk"}


def update_bet(user_id: str, bet_id: str, updates: dict) -> dict:
    """Update mutable fields of a bet. Returns the updated item. Raises ValueError if not found."""
    table = _bets_table()
    resp = table.get_item(Key={"user_id": user_id, "bet_id": bet_id})
    if "Item" not in resp:
        raise ValueError("not_found")

    patch = _to_dynamo({k: v for k, v in updates.items() if v is not None and k not in _IMMUTABLE_KEYS})
    if not patch:
        return _from_dynamo(resp["Item"])

    keys = list(patch.keys())
    vals = list(patch.values())
    names = {f"#k{i}": k for i, k in enumerate(keys)}
    values = {f":v{i}": v for i, v in enumerate(vals)}
    set_parts = [f"#k{i} = :v{i}" for i in range(len(keys))]

    result = table.update_item(
        Key={"user_id": user_id, "bet_id": bet_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return _from_dynamo(result["Attributes"])


# ── Users registry ───────────────────────────────────────────────────────────

def upsert_user(user_id: str, email: str | None) -> None:
    """Idempotent login-sync. Sets last_seen_at (+ email) every call; first_seen_at
    only on the first write. `sub` is trusted (from the JWT); email is metadata."""
    now = _now_iso()
    names = {"#ls": "last_seen_at", "#fs": "first_seen_at"}
    values = {":now": now}
    set_parts = ["#ls = :now", "#fs = if_not_exists(#fs, :now)"]
    if email is not None:
        names["#em"] = "email"
        values[":em"] = email
        set_parts.append("#em = :em")
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def record_tos_acceptance(user_id: str, tos_version: str) -> None:
    """Record first-time ToS acceptance. Preserves the original tos_accepted_at if
    already set (if_not_exists) so re-runs don't overwrite the canonical timestamp.
    tos_version is always updated so we track the latest version agreed to."""
    now = _now_iso()
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ta = if_not_exists(#ta, :now), #tv = :ver",
        ExpressionAttributeNames={"#ta": "tos_accepted_at", "#tv": "tos_version"},
        ExpressionAttributeValues={":now": now, ":ver": tos_version},
    )


def get_user_profile(user_id: str) -> dict:
    """Return the user's mutable profile fields (initial_deposit etc.)."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    raw_deposit = item.get("initial_deposit")
    return {
        "initial_deposit": float(raw_deposit) if raw_deposit is not None else None,
    }


def update_user_profile(user_id: str, initial_deposit: float | None) -> dict:
    """Update mutable profile fields. Only initial_deposit for now."""
    if initial_deposit is not None:
        _users_table().update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #id = :v",
            ExpressionAttributeNames={"#id": "initial_deposit"},
            ExpressionAttributeValues={":v": Decimal(str(initial_deposit))},
        )
    return get_user_profile(user_id)
