"""Alerts endpoints.

GET /alerts/preferences — read user notification preferences from DynamoDB
PUT /alerts/preferences — write updated preferences to DynamoDB

user_id is extracted from the Cognito JWT sub claim passed by API Gateway.
"""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.models.alerts import AlertPreferences, AlertPreferencesUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alerts", tags=["alerts"])

_DYNAMO_TABLE = os.environ.get(
    "DYNAMO_PUSH_SUBSCRIPTIONS_TABLE",
    "credence-prod-dynamo-push-subscriptions",
)
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_DEFAULTS: dict = {
    "email_enabled": True,
    "sms_enabled": False,
    "phone_number": None,
    "push_enabled": False,
    "alert_threshold_edge": 0.05,
}


def _get_dynamo_table():
    ddb = boto3.resource("dynamodb", region_name=_AWS_REGION)
    return ddb.Table(_DYNAMO_TABLE)


@router.get("/preferences", response_model=AlertPreferences)
def get_alert_preferences(user_id: str = Depends(get_user_id)) -> AlertPreferences:
    table = _get_dynamo_table()
    try:
        resp = table.get_item(Key={"user_id": user_id})
    except ClientError as exc:
        logger.exception("DynamoDB get_item failed")
        raise HTTPException(status_code=503, detail="Preferences unavailable") from exc

    item = resp.get("Item", {})
    return AlertPreferences(
        user_id=user_id,
        email_enabled=item.get("email_enabled", _DEFAULTS["email_enabled"]),
        sms_enabled=item.get("sms_enabled", _DEFAULTS["sms_enabled"]),
        phone_number=item.get("phone_number", _DEFAULTS["phone_number"]),
        push_enabled=item.get("push_enabled", _DEFAULTS["push_enabled"]),
        alert_threshold_edge=float(item.get("alert_threshold_edge", _DEFAULTS["alert_threshold_edge"])),
    )


@router.put("/preferences", response_model=AlertPreferences)
def update_alert_preferences(
    body: AlertPreferencesUpdate, user_id: str = Depends(get_user_id)
) -> AlertPreferences:
    table = _get_dynamo_table()

    # Read existing item first to merge with updates
    try:
        resp = table.get_item(Key={"user_id": user_id})
    except ClientError as exc:
        logger.exception("DynamoDB get_item failed")
        raise HTTPException(status_code=503, detail="Preferences unavailable") from exc

    existing = resp.get("Item", {})
    merged = {
        "user_id": user_id,
        "email_enabled": existing.get("email_enabled", _DEFAULTS["email_enabled"]),
        "sms_enabled": existing.get("sms_enabled", _DEFAULTS["sms_enabled"]),
        "phone_number": existing.get("phone_number", _DEFAULTS["phone_number"]),
        "push_enabled": existing.get("push_enabled", _DEFAULTS["push_enabled"]),
        "alert_threshold_edge": float(existing.get("alert_threshold_edge", _DEFAULTS["alert_threshold_edge"])),
    }

    update = body.model_dump(exclude_none=True)
    merged.update(update)

    try:
        table.put_item(Item=merged)
    except ClientError as exc:
        logger.exception("DynamoDB put_item failed")
        raise HTTPException(status_code=503, detail="Could not save preferences") from exc

    return AlertPreferences(**merged)
