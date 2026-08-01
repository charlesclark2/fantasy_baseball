"""E9.9 / A0.6 -> E9.50 — unit tests for the predict_today post-lineup actionable-
picks SNS publish hook.

The load-bearing ACs: (1) an SNS/DynamoDB failure must NEVER crash predict_today;
(2) the retired morning (pre-lineup) path never notifies; (3) dedupe is per
(date, game_pk) so a pick is emailed exactly once across staggered post-lineup
re-score cycles, never re-sent, and a NEW game in a later cycle still alerts;
(4) a degraded (intraday_fallback) row is never presented as actionable.
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


def _table_claims_all(monkeypatch, sns=None):
    """Every conditional put succeeds (all games unclaimed)."""
    sns = sns or MagicMock()
    table = MagicMock()
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))
    return sns, table


def test_build_message_counts_only_qualified():
    msg = qbn.build_qualified_plays_message(_TODAY, _ROWS)
    assert msg["n_qualified"] == 2
    assert msg["date"] == _TODAY
    assert {p["matchup"] for p in msg["plays"]} == {"NYY @ BOS", "STL @ CHC"}


def test_publish_happy_path(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns, _ = _table_claims_all(monkeypatch)

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, _ROWS, lineup_confirmed=True
    ) is True
    sns.publish.assert_called_once()
    _, kwargs = sns.publish.call_args
    assert '"n_qualified": 2' in kwargs["Message"]


def test_morning_pre_lineup_run_never_notifies(monkeypatch):
    """E9.50: the morning alert is retired — lineup_confirmed=False must never publish,
    even with qualified rows and a healthy topic."""
    _env(monkeypatch)
    _freeze(monkeypatch)
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published!")))
    monkeypatch.setattr("boto3.resource", lambda *a, **k: (_ for _ in ()).throw(AssertionError("touched dynamo!")))

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, _ROWS, lineup_confirmed=False
    ) is False


def test_intraday_fallback_row_is_never_actionable(monkeypatch):
    """A degraded (team-carry-forward) row must not be presented as a confirmed pick."""
    _env(monkeypatch)
    _freeze(monkeypatch)
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published!")))
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock())
    rows = [{"qualified_bet": True, "game_pk": 1, "pick": "x", "data_source": "intraday_fallback"}]

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, rows, lineup_confirmed=True
    ) is False


def test_region_ignores_aws_default_region(monkeypatch):
    # INC-31: AWS_DEFAULT_REGION=us-east-2 (set on the box for DuckDB/S3 lakehouse reads) must NOT
    # leak into the notifier's region — the serving-cache idempotency table AND the SNS topic both
    # live in us-east-1. region resolves via AWS_REGION only (default us-east-1).
    monkeypatch.setenv("QUALIFIED_BETS_SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:1:qb")
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    _freeze(monkeypatch)
    seen: dict[str, str | None] = {}

    def _client(svc, **k):
        seen["client"] = k.get("region_name")
        return MagicMock()

    def _resource(svc, **k):
        seen["resource"] = k.get("region_name")
        return MagicMock(Table=lambda n: MagicMock())

    monkeypatch.setattr("boto3.client", _client)
    monkeypatch.setattr("boto3.resource", _resource)
    qbn.notify_post_lineup_actionable_picks_safe(_TODAY, _ROWS, lineup_confirmed=True)
    assert seen.get("resource") == "us-east-1"  # DynamoDB idempotency table (credence-prod-serving-cache)
    assert seen.get("client") == "us-east-1"    # SNS publish (topic is us-east-1)


def test_backfill_date_never_notifies(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch, iso=_TODAY)
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published!")))
    # target_date != today → skip before any AWS call
    assert qbn.notify_post_lineup_actionable_picks_safe(
        "2026-06-01", _ROWS, lineup_confirmed=True
    ) is False


def test_zero_qualified_skips(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch)
    rows = [{"qualified_bet": False, "pick": "x", "game_pk": 1}]
    monkeypatch.setattr("boto3.client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("published!")))
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock())
    assert qbn.notify_post_lineup_actionable_picks_safe(_TODAY, rows, lineup_confirmed=True) is False


def test_unset_topic_is_loud_skip(monkeypatch):
    monkeypatch.delenv("QUALIFIED_BETS_SNS_TOPIC_ARN", raising=False)
    _freeze(monkeypatch)
    assert qbn.notify_post_lineup_actionable_picks_safe(_TODAY, _ROWS, lineup_confirmed=True) is False


def test_per_game_dedupe_skips_already_alerted_game(monkeypatch):
    """A game already alerted today (conditional put fails) is dropped from the digest,
    but a still-unclaimed game in the same batch still gets emailed."""
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns = MagicMock()
    table = MagicMock()

    def _put_item(Item, **k):
        # game_pk 1 was already alerted earlier today; game_pk 3 is new.
        if Item["sk"].endswith("#1"):
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")

    table.put_item.side_effect = _put_item
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, _ROWS, lineup_confirmed=True
    ) is True
    sns.publish.assert_called_once()
    _, kwargs = sns.publish.call_args
    assert '"n_qualified": 1' in kwargs["Message"]
    assert "STL @ CHC" in kwargs["Message"]
    assert "NYY @ BOS" not in kwargs["Message"]


def test_all_games_already_alerted_sends_nothing(monkeypatch):
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns = MagicMock()
    table = MagicMock()
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
    )
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, _ROWS, lineup_confirmed=True
    ) is False
    sns.publish.assert_not_called()


def test_a_later_cycle_alerts_a_newly_qualified_game(monkeypatch):
    """Simulates two staggered lineup_monitor cycles for the same date: cycle 1 alerts
    game_pk 1, cycle 2 (a different game newly confirming) must still alert game_pk 3 —
    proving dedupe is per-game, not per-day."""
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns = MagicMock()
    claimed: set[str] = set()
    table = MagicMock()

    def _put_item(Item, **k):
        sk = Item["sk"]
        if sk in claimed:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        claimed.add(sk)

    table.put_item.side_effect = _put_item
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))

    cycle_1 = [_ROWS[0]]  # game_pk 1 only
    cycle_2 = [_ROWS[0], _ROWS[2]]  # a re-trigger of game 1 (already sent) + new game 3

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, cycle_1, lineup_confirmed=True
    ) is True
    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, cycle_2, lineup_confirmed=True
    ) is True
    assert sns.publish.call_count == 2
    second_msg = sns.publish.call_args_list[1].kwargs["Message"]
    assert '"n_qualified": 1' in second_msg
    assert "STL @ CHC" in second_msg
    assert "NYY @ BOS" not in second_msg  # not re-sent


def test_claim_failure_for_one_game_does_not_sink_the_batch(monkeypatch):
    """A DynamoDB error on one game's claim (not a ConditionalCheckFailed — a real
    fault) must be swallowed so the rest of the batch still alerts."""
    _env(monkeypatch)
    _freeze(monkeypatch)
    sns = MagicMock()
    table = MagicMock()

    def _put_item(Item, **k):
        if Item["sk"].endswith("#1"):
            raise ClientError({"Error": {"Code": "InternalServerError"}}, "PutItem")

    table.put_item.side_effect = _put_item
    monkeypatch.setattr("boto3.client", lambda *a, **k: sns)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: table))

    assert qbn.notify_post_lineup_actionable_picks_safe(
        _TODAY, _ROWS, lineup_confirmed=True
    ) is True
    sns.publish.assert_called_once()
    assert '"n_qualified": 1' in sns.publish.call_args.kwargs["Message"]


def test_sns_failure_never_raises(monkeypatch):
    """The load-bearing AC: a publish failure must NOT crash predict_today."""
    _env(monkeypatch)
    _freeze(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("SNS is down")

    monkeypatch.setattr("boto3.client", _boom)
    monkeypatch.setattr("boto3.resource", lambda *a, **k: MagicMock(Table=lambda n: MagicMock()))
    # Must return False, not raise.
    assert qbn.notify_post_lineup_actionable_picks_safe(_TODAY, _ROWS, lineup_confirmed=True) is False
