"""INC-16-P6 — unit tests for the shared ops notifier (pipeline.utils.alerting).

All boto3 is mocked — no network. Covers: soft-fail when unconfigured, publish on
happy path, per-key rate-limiting, and the never-raise contract.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load the leaf util directly from its file — importing `pipeline.utils.alerting`
# would run pipeline/__init__.py (which needs SNOWFLAKE_* at import). alerting.py
# has no pipeline deps, so a standalone load is faithful and avoids that.
_ALERTING_PATH = (
    Path(__file__).resolve().parents[2] / "pipeline" / "utils" / "alerting.py"
)
_spec = importlib.util.spec_from_file_location("credence_alerting", _ALERTING_PATH)
alerting = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alerting)


@pytest.fixture(autouse=True)
def _clear_dedup():
    alerting._LAST_SENT.clear()
    yield
    alerting._LAST_SENT.clear()


def test_soft_fail_when_topic_unset(monkeypatch):
    monkeypatch.delenv("ALERT_SNS_TOPIC_ARN", raising=False)
    # must not raise, must return False (alerting unconfigured ≠ caller failure)
    assert alerting.send_alert("subj", "body") is False


def test_publishes_when_configured(monkeypatch):
    monkeypatch.setenv("ALERT_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:credence-prod-alerts")
    client = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **k: client)

    assert alerting.send_alert("box down", "the body", severity="CRITICAL") is True
    client.publish.assert_called_once()
    kwargs = client.publish.call_args.kwargs
    assert kwargs["TopicArn"].endswith("credence-prod-alerts")
    assert kwargs["Subject"].startswith("[Credence PROD] CRITICAL:")
    assert len(kwargs["Subject"]) <= 100


def test_rate_limit_suppresses_repeat(monkeypatch):
    monkeypatch.setenv("ALERT_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    client = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **k: client)

    assert alerting.send_alert("same", "b", dedup_key="k", dedup_ttl_s=3600) is True
    assert alerting.send_alert("same", "b", dedup_key="k", dedup_ttl_s=3600) is False  # suppressed
    assert client.publish.call_count == 1


def test_never_raises_on_publish_error(monkeypatch):
    monkeypatch.setenv("ALERT_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    boom = MagicMock()
    boom.publish.side_effect = RuntimeError("SNS down")
    monkeypatch.setattr("boto3.client", lambda *a, **k: boom)

    assert alerting.send_alert("subj", "body") is False  # swallowed, not raised


def test_subject_clamped_and_ascii(monkeypatch):
    monkeypatch.setenv("ALERT_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    client = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **k: client)

    alerting.send_alert("x" * 200 + "\nnewline—", "body")
    subj = client.publish.call_args.kwargs["Subject"]
    assert len(subj) <= 100
    assert "\n" not in subj
    assert subj.isascii()
