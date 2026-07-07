from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

# E.164 phone number, e.g. +14155550123. Kept permissive (any country code) rather
# than US-only so international beta users can opt into SMS. Cognito does NOT capture
# phone numbers, so users enter it in Settings and we store it in DynamoDB (E9.9).
_E164_RE = re.compile(r"\+[1-9]\d{7,14}$")


def _validate_e164(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if not _E164_RE.fullmatch(v):
        raise ValueError("phone_number must be E.164 format, e.g. +14155550123")
    return v


class WebPushKeys(BaseModel):
    """The `keys` object from a browser PushSubscription (Web Push encryption keys)."""

    p256dh: str
    auth: str


class WebPushSubscription(BaseModel):
    """A browser PushSubscription as serialised by `pushManager.subscribe()`."""

    endpoint: str
    keys: WebPushKeys
    # `expirationTime` is usually null; kept for round-tripping, unused server-side.
    expirationTime: float | None = None


class AlertPreferences(BaseModel):
    """Canonical notification preferences for a user (E9.9 / A0.6).

    Stored in DynamoDB keyed by the Cognito `sub`. We use independent per-channel
    toggles (email / push / sms) rather than the single `channel ∈ {email,push,both}`
    the story sketched — this generalises cleanly to the SMS channel (the story did
    not capture phone numbers; Cognito does not hold them, so the user enters one in
    Settings and it lives here). A channel is DELIVERED only when the master `enabled`
    flag is on, its toggle is on, and the required contact detail is present
    (email / push_subscription / phone_number).

    `push_subscription` is present only after the user grants browser push permission.
    """

    user_id: str
    enabled: bool = False
    email_enabled: bool = True
    push_enabled: bool = False
    sms_enabled: bool = False
    email: str | None = None
    phone_number: str | None = None
    push_subscription: WebPushSubscription | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return _validate_e164(v)


class AlertPreferencesUpdate(BaseModel):
    """PUT /alerts/preferences — opt-in / pause + channel toggles + contact details.

    The email and SMS paths need no browser permission, so they are settable here.
    `push_subscription` is intentionally NOT settable here (use POST /alerts/subscribe,
    which needs the browser's `pushManager.subscribe()` result)."""

    enabled: bool | None = None
    email_enabled: bool | None = None
    push_enabled: bool | None = None
    sms_enabled: bool | None = None
    email: str | None = None
    phone_number: str | None = None

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return _validate_e164(v)


class SubscribeRequest(BaseModel):
    """POST /alerts/subscribe — register a Web Push endpoint (and opt in to push)."""

    subscription: WebPushSubscription
    email: str | None = None
