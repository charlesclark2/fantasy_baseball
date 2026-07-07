"""E9.9 / A0.6 — tests for the /alerts router (preferences + subscribe/unsubscribe).

DynamoDB is replaced with an in-memory fake table; router functions are called
directly (no TestClient — httpx isn't a test dep). Covers: default preferences,
email/SMS opt-in, phone validation, push subscribe/unsubscribe round-trip.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.backend.models.alerts import (
    AlertPreferencesUpdate,
    SubscribeRequest,
    WebPushSubscription,
)
from app.backend.routers import alerts


class _FakeTable:
    """Minimal DynamoDB Table stand-in backed by a dict keyed on user_id."""

    def __init__(self):
        self.store: dict[str, dict] = {}

    def get_item(self, Key):  # noqa: N803 — boto3 kwarg name
        item = self.store.get(Key["user_id"])
        return {"Item": dict(item)} if item else {}

    def put_item(self, Item):  # noqa: N803
        self.store[Item["user_id"]] = dict(Item)


@pytest.fixture
def table(monkeypatch):
    t = _FakeTable()
    monkeypatch.setattr(alerts, "_get_dynamo_table", lambda: t)
    return t


_UID = "sub-123"


def test_defaults_when_no_item(table):
    prefs = alerts.get_alert_preferences(user_id=_UID)
    assert prefs.user_id == _UID
    assert prefs.enabled is False
    assert prefs.email_enabled is True
    assert prefs.push_subscription is None


def test_email_opt_in_persists(table):
    body = AlertPreferencesUpdate(enabled=True, email="u@x.com")
    prefs = alerts.update_alert_preferences(body, user_id=_UID)
    assert prefs.enabled is True
    stored = table.store[_UID]
    assert stored["enabled"] is True and stored["email"] == "u@x.com"
    assert "created_at" in stored and "updated_at" in stored


def test_sms_opt_in_with_valid_phone(table):
    body = AlertPreferencesUpdate(enabled=True, sms_enabled=True, phone_number="+14155550123")
    prefs = alerts.update_alert_preferences(body, user_id=_UID)
    assert prefs.phone_number == "+14155550123"
    assert prefs.sms_enabled is True


def test_invalid_phone_rejected():
    with pytest.raises(ValidationError):
        AlertPreferencesUpdate(phone_number="555-1234")


def test_empty_phone_normalises_to_none():
    assert AlertPreferencesUpdate(phone_number="").phone_number is None


def test_push_subscribe_then_unsubscribe(table):
    sub = WebPushSubscription(endpoint="https://push.example/abc", keys={"p256dh": "k1", "auth": "k2"})
    prefs = alerts.subscribe(SubscribeRequest(subscription=sub, email="u@x.com"), user_id=_UID)
    assert prefs.push_enabled is True and prefs.enabled is True
    assert prefs.push_subscription.endpoint == "https://push.example/abc"

    resp = alerts.unsubscribe(user_id=_UID)
    assert resp.status_code == 204
    stored = table.store[_UID]
    assert stored["push_enabled"] is False
    assert "push_subscription" not in stored
    # email pref survives an unsubscribe
    assert stored["email"] == "u@x.com"
