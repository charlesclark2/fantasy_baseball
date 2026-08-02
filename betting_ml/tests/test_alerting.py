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


# ── INC-39 — a SMOKE page must be distinguishable, and must never blind the real one ──────
# E11.30 mandates a live-box smoke for every ALERT-tier monitor (CI mocks all IO, so only a real
# box run proves the page path). Before `smoke=`, such a self-test went out through the ordinary
# path: same `[Credence PROD]` subject, same severity, same body — a synthetic 2026-08-02
# `public_betting BUILD_GAP 0/15` was read as a genuine serving defect and opened a P2 incident on
# a slate whose built table held 15/15. The dedup collision is the worse half: firing the
# PRODUCTION key parks the real page for the full hour-long TTL, so smoke-testing a monitor could
# blind it exactly while someone is poking at the box.

def _client(monkeypatch):
    monkeypatch.setenv("ALERT_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    client = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **k: client)
    return client


def test_smoke_alert_is_labelled_in_the_subject(monkeypatch):
    client = _client(monkeypatch)
    alerting.send_alert("W11 serving tail coverage gap", "body",
                        severity="CRITICAL", dedup_key="w11_tail_coverage", smoke=True)
    assert "[SMOKE TEST]" in client.publish.call_args.kwargs["Subject"]


def test_smoke_alert_says_so_in_the_body(monkeypatch):
    """The subject is clamped to 100 chars, so the body banner is the durable signal."""
    client = _client(monkeypatch)
    alerting.send_alert("s", "the real detail", smoke=True)
    body = client.publish.call_args.kwargs["Message"]
    assert "SMOKE TEST" in body and "NOT a real incident" in body
    assert "the real detail" in body


def test_a_smoke_never_suppresses_the_real_page_on_the_same_key(monkeypatch):
    """THE INC-39 HAZARD. A smoke on the production dedup_key must leave the real key free."""
    client = _client(monkeypatch)
    assert alerting.send_alert("s", "b", dedup_key="w11_tail_coverage", smoke=True) is True
    # ...and the genuine page fires immediately after, not an hour later.
    assert alerting.send_alert("s", "b", dedup_key="w11_tail_coverage") is True
    assert client.publish.call_count == 2


def test_a_real_page_never_suppresses_a_smoke_either(monkeypatch):
    client = _client(monkeypatch)
    assert alerting.send_alert("s", "b", dedup_key="k") is True
    assert alerting.send_alert("s", "b", dedup_key="k", smoke=True) is True
    assert client.publish.call_count == 2


def test_smoke_pages_still_rate_limit_among_themselves(monkeypatch):
    client = _client(monkeypatch)
    assert alerting.send_alert("s", "b", dedup_key="k", smoke=True) is True
    assert alerting.send_alert("s", "b", dedup_key="k", smoke=True) is False
    assert client.publish.call_count == 1


def test_a_real_page_is_never_labelled_a_smoke(monkeypatch):
    """The mirror-image failure — a real incident dismissed as a self-test — is strictly worse
    than the one this fixes, which is why `smoke` is a keyword arg with no env-var backdoor."""
    client = _client(monkeypatch)
    alerting.send_alert("real problem", "body", severity="CRITICAL")
    assert "SMOKE" not in client.publish.call_args.kwargs["Subject"]
    assert "SMOKE" not in client.publish.call_args.kwargs["Message"]


def test_there_is_no_env_var_that_can_turn_smoke_mode_on(monkeypatch):
    """A left-set `ALERT_SMOKE_TEST=1` would label every real page a smoke — this repo's
    documented-but-never-set flag class (cf. W7B_LAKEHOUSE_S3), facing the dangerous way."""
    client = _client(monkeypatch)
    for var in ("ALERT_SMOKE_TEST", "SMOKE_TEST", "ALERT_SMOKE"):
        monkeypatch.setenv(var, "1")
    alerting.send_alert("real problem", "body", severity="CRITICAL")
    assert "SMOKE" not in client.publish.call_args.kwargs["Subject"]
