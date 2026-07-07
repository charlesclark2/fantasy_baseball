"""E9.9 / A0.6 — unit tests for the predict_today qualified-plays SNS publish hook.

The load-bearing AC: an SNS/DynamoDB failure must NEVER crash predict_today. Also
covers: message building, backfill-date skip, zero-plays skip, per-day idempotency,
and the unset-topic loud skip.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from betting_ml.utils import qualified_bet_notifier as qbn

_TODAY = "2026-07-06"
_ROWS = [
    {"qualified_bet": True, "home_team_abbrev": "BOS", "away_team_abbrev": "NYY",
     "pick": "Over 8.5", "game_pk": 1},
    {"qualified_bet": False, "home_team_abbrev": "SF", "away_team_abbrev": "LAD",
     "pick": "LAD ML", "game_pk": 2},
    {"qualified_bet": True, "home_team_abbrev": "CHC", "away_team_abbrev": "STL",
     "pick": "Under 7.5", "game_pk": 3},
]


def _freeze(monkeypatch, iso=_TODAY):
    monkeypatch.setattr(qbn, "current_game_date_iso", lambda now=None: iso)


def _env(monkeypatch, topic="arn:aws:sns:us-east-1:1:qb"):
    monkeypatch.setenv("QUALIFIED_BETS_SNS_TOPIC_ARN", topic)
    monkeypatch.setenv("AWS_REGION", "us-east-1")


def test_build_message_counts_only_qualified():
    msg = qbn.build_qualified_plays_message(_TODAY, _ROWS)
    assert msg["n_qualified"] == 2
    assert msg["date"] == _TODAY
    assert {p["matchup"] for p in msg["plays"]} == {"NYY @ BOS", "STL @ CHC"}


def test_publish_happy_path(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns = MagicMock()
    table = MagicMock()  # conditional put succeeds → claimed
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))

    assert qbn.notify_qualified_plays_safe(_TODAY, _ROWS) is True
    sns.publish.assert_called_once()
    _, kwargs = sns.publish.call_args
    assert '"n_qualified": 2' in kwargs["Message"]


def test_backfill_date_never_notifies(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch, iso=_TODAY)
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published!")))
    # target_date != today → skip before any AWS call
    assert qbn.notify_qualified_plays_safe("2026-06-01", _ROWS) is False


def test_zero_qualified_skips(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch)
    rows = [{"qualified_bet": False, "pick": "x"}]
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published!")))
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock())
    assert qbn.notify_qualified_plays_safe(_TODAY, rows) is False


def test_unset_topic_is_loud_skip(monkeypatch):
    monkeypatch.delenv("QUALIFIED_BETS_SNS_TOPIC_ARN", raising=False)
    _freeze(monkeypatch)
    assert qbn.notify_qualified_plays_safe(_TODAY, _ROWS) is False


def test_idempotent_second_send_skipped(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns = MagicMock()
    table = MagicMock()
    # conditional put raises ConditionalCheckFailed → already sent today
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
    )
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))

    assert qbn.notify_qualified_plays_safe(_TODAY, _ROWS) is False
    sns.publish.assert_not_called()


def test_sns_failure_never_raises(monkeypatch):
    """The load-bearing AC: a publish failure must NOT crash predict_today."""
    _env(monkeypatch)
    _freeze(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("SNS is down")

    monkeypatch.setattr("boto3.client", _boom)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock())
    # Must return False, not raise.
    assert qbn.notify_qualified_plays_safe(_TODAY, _ROWS) is False
