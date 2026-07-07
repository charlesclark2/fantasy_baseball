"""Alerts / notification-preferences endpoints (E9.9 / A0.6).

Users opt in to be notified when the model posts qualified plays for today's slate.
Delivery is fanned out by the `push-notification-sender` Lambda; this router only
manages each user's preferences + push subscription in DynamoDB.

  GET    /alerts/preferences  — read notification preferences
  PUT    /alerts/preferences  — update opt-in / channel toggles / email / phone
  POST   /alerts/subscribe    — register a browser Web Push endpoint (opt in to push)
  DELETE /alerts/subscribe    — remove the Web Push endpoint (and turn push off)

Storage: DynamoDB, one item per user keyed by the Cognito `sub` (PK attribute
`user_id`). The table is the already-provisioned `credence-prod-dynamo-push-subscriptions`
(the story's `credence-prod-user-push-subscriptions` names the identical thing — the
provisioned table already serves this purpose, so we reuse it rather than orphaning it).

user_id is the Cognito JWT `sub`, resolved by the API Gateway JWT authorizer.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response

from app.backend.dependencies import get_user_id
from app.backend.models.alerts import (
    AlertPreferences,
    AlertPreferencesUpdate,
    SubscribeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])

_DYNAMO_TABLE = os.environ.get(
    "DYNAMO_PUSH_SUBSCRIPTIONS_TABLE",
    "credence-prod-dynamo-push-subscriptions",
)
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Attributes that describe preferences (everything except identity/timestamps).
_PREF_FIELDS = ("enabled", "email_enabled", "push_enabled", "sms_enabled", "email", "phone_number")


def _get_dynamo_table():
    ddb = boto3.resource("dynamodb", region_name=_AWS_REGION)
    return ddb.Table(_DYNAMO_TABLE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_item(table, user_id: str) -> dict:
    try:
        resp = table.get_item(Key={"user_id": user_id})
    except ClientError as exc:
        logger.exception("DynamoDB get_item failed")
        raise HTTPException(status_code=503, detail="Preferences unavailable") from exc
    return resp.get("Item") or {}


def _to_prefs(user_id: str, item: dict) -> AlertPreferences:
    """Build an AlertPreferences from a DynamoDB item, applying defaults."""
    sub = item.get("push_subscription")
    return AlertPreferences(
        user_id=user_id,
        enabled=bool(item.get("enabled", False)),
        email_enabled=bool(item.get("email_enabled", True)),
        push_enabled=bool(item.get("push_enabled", False)),
        sms_enabled=bool(item.get("sms_enabled", False)),
        email=item.get("email"),
        phone_number=item.get("phone_number"),
        push_subscription=sub if sub else None,
        created_at=item.get("created_at"),
        updated_at=item.get("updated_at"),
    )


def _write_item(table, item: dict) -> None:
    try:
        table.put_item(Item=item)
    except ClientError as exc:
        logger.exception("DynamoDB put_item failed")
        raise HTTPException(status_code=503, detail="Could not save preferences") from exc


@router.get("/preferences", response_model=AlertPreferences)
def get_alert_preferences(user_id: str = Depends(get_user_id)) -> AlertPreferences:
    table = _get_dynamo_table()
    return _to_prefs(user_id, _read_item(table, user_id))


@router.put("/preferences", response_model=AlertPreferences)
def update_alert_preferences(
    body: AlertPreferencesUpdate, user_id: str = Depends(get_user_id)
) -> AlertPreferences:
    table = _get_dynamo_table()
    item = _read_item(table, user_id)

    updates = body.model_dump(exclude_none=True)
    # Empty-string email/phone clears the field (the model normalises "" phone → None).
    for field in _PREF_FIELDS:
        if field in updates:
            item[field] = updates[field]

    item["user_id"] = user_id
    item.setdefault("created_at", _now_iso())
    item["updated_at"] = _now_iso()
    _write_item(table, item)
    return _to_prefs(user_id, item)


@router.post("/subscribe", response_model=AlertPreferences)
def subscribe(body: SubscribeRequest, user_id: str = Depends(get_user_id)) -> AlertPreferences:
    """Register a browser Web Push endpoint and opt the user in to push alerts."""
    table = _get_dynamo_table()
    item = _read_item(table, user_id)

    item["user_id"] = user_id
    item["push_subscription"] = body.subscription.model_dump(exclude_none=True)
    item["push_enabled"] = True
    item["enabled"] = True
    if body.email:
        item["email"] = body.email
    item.setdefault("email_enabled", True)
    item.setdefault("created_at", _now_iso())
    item["updated_at"] = _now_iso()
    _write_item(table, item)
    return _to_prefs(user_id, item)


@router.delete("/subscribe", status_code=204)
def unsubscribe(user_id: str = Depends(get_user_id)) -> Response:
    """Remove the Web Push endpoint and turn push off (email/SMS prefs untouched)."""
    table = _get_dynamo_table()
    item = _read_item(table, user_id)
    if item:
        item["user_id"] = user_id
        item.pop("push_subscription", None)
        item["push_enabled"] = False
        item["updated_at"] = _now_iso()
        _write_item(table, item)
    return Response(status_code=204)
