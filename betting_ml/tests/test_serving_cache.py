"""INC-16-P2 — unit tests for the DynamoDB serving cache + migrated portfolios.

Covers app/backend/services/serving_cache.py (replaces the Railway PG api_cache)
and the portfolio functions migrated into app/backend/services/dynamo.py. All
DynamoDB IO is mocked (no live AWS) per the repo's unittest.mock fixture style;
fast-gate friendly.

Contracts under test:
  - get_cache: permanent row first, then date-scoped (two point reads).
  - get_cache_latest: newest-by-updated_at across a key's rows.
  - set_cache: structured PK/SK; permanent rows at a date-independent SK.
  - list_cache_by_prefix: Query on the namespace PK.
  - invalidate / invalidate_permanent_picks / invalidate_today: targeted deletes.
  - Every function degrades (None / [] / 0 / no-op) on a DynamoDB error.
  - Portfolios: defaults when unset, round-trip on upsert, defaults on error.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def _mock_table():
    """A MagicMock DynamoDB Table whose batch_writer() works as a context manager."""
    tbl = MagicMock()
    batch = MagicMock()

    @contextmanager
    def _bw():
        yield batch

    tbl.batch_writer.side_effect = _bw
    tbl._batch = batch  # expose for assertions
    return tbl


# ───────────────────────────── get_cache ─────────────────────────────────────

class TestGetCache:
    def test_permanent_row_wins(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.get_item.return_value = {"Item": {"value": json.dumps({"x": 1})}}
        with patch.object(sc, "_table", return_value=tbl):
            out = sc.get_cache("picks/game/123", "2026-06-26")
        assert out == {"x": 1}
        # First lookup is the PERMANENT sk.
        first_key = tbl.get_item.call_args_list[0].kwargs["Key"]
        assert first_key == {"pk": "picks", "sk": "game/123#PERMANENT"}

    def test_falls_through_to_date_row(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.get_item.side_effect = [
            {},  # no permanent row
            {"Item": {"value": json.dumps({"y": 2})}},  # date-scoped row
        ]
        with patch.object(sc, "_table", return_value=tbl):
            out = sc.get_cache("picks/today", "2026-06-26")
        assert out == {"y": 2}
        second_key = tbl.get_item.call_args_list[1].kwargs["Key"]
        assert second_key == {"pk": "picks", "sk": "today#2026-06-26"}

    def test_total_miss_returns_none(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.get_item.return_value = {}
        with patch.object(sc, "_table", return_value=tbl):
            assert sc.get_cache("team/147", "2026-06-26") is None

    def test_returns_none_on_error(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.get_item.side_effect = Exception("ddb down")
        with patch.object(sc, "_table", return_value=tbl):
            assert sc.get_cache("team/147", "2026-06-26") is None


# ─────────────────────────── get_cache_latest ────────────────────────────────

class TestGetCacheLatest:
    def test_picks_newest_by_updated_at(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.return_value = {"Items": [
            {"value": json.dumps({"v": "old"}), "updated_at": "2026-06-25T00:00:00"},
            {"value": json.dumps({"v": "new"}), "updated_at": "2026-06-26T00:00:00"},
        ]}
        with patch.object(sc, "_table", return_value=tbl):
            out = sc.get_cache_latest("picks/book-odds/123")
        assert out == {"v": "new"}

    def test_empty_returns_none(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.return_value = {"Items": []}
        with patch.object(sc, "_table", return_value=tbl):
            assert sc.get_cache_latest("zone_matchup/1_vs_2") is None


# ───────────────────────────────── set_cache ─────────────────────────────────

class TestSetCache:
    def test_date_scoped_put(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        with patch.object(sc, "_table", return_value=tbl):
            sc.set_cache("picks/today", "2026-06-26", {"a": 1})
        item = tbl.put_item.call_args.kwargs["Item"]
        assert item["pk"] == "picks"
        assert item["sk"] == "today#2026-06-26"
        assert item["is_permanent"] is False
        assert item["cache_date"] == "2026-06-26"
        assert json.loads(item["value"]) == {"a": 1}

    def test_permanent_put_uses_permanent_sk(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        with patch.object(sc, "_table", return_value=tbl):
            sc.set_cache("picks/game/99", "2026-06-26", {"final": True}, is_permanent=True)
        item = tbl.put_item.call_args.kwargs["Item"]
        assert item["sk"] == "game/99#PERMANENT"
        assert item["is_permanent"] is True
        assert item["cache_date"] == "PERMANENT"

    def test_set_cache_swallows_errors(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.put_item.side_effect = Exception("item too large")
        with patch.object(sc, "_table", return_value=tbl):
            sc.set_cache("player/1", "2026-06-26", {"big": "x"}, is_permanent=True)  # must not raise


# ─────────────────────────── list_cache_by_prefix ────────────────────────────

class TestListCacheByPrefix:
    def test_lists_team_namespace(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.return_value = {"Items": [
            {"sk": "147#PERMANENT", "value": json.dumps({"team_id": 147})},
            {"sk": "111#PERMANENT", "value": json.dumps({"team_id": 111})},
        ]}
        with patch.object(sc, "_table", return_value=tbl):
            out = sc.list_cache_by_prefix("team/")
        assert {p["team_id"] for p in out} == {147, 111}

    def test_returns_empty_on_error(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.side_effect = Exception("ddb down")
        with patch.object(sc, "_table", return_value=tbl):
            assert sc.list_cache_by_prefix("team/") == []


# ───────────────────────── invalidate_permanent_picks ────────────────────────

class TestInvalidatePermanentPicks:
    def test_deletes_matched_and_returns_count(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.return_value = {"Items": [
            {"pk": "picks", "sk": "game/1#PERMANENT"},
            {"pk": "picks", "sk": "game/2#PERMANENT"},
        ]}
        with patch.object(sc, "_table", return_value=tbl):
            n = sc.invalidate_permanent_picks()
        assert n == 2
        assert tbl._batch.delete_item.call_count == 2
        # A FilterExpression (is_permanent) is applied alongside the key condition.
        assert "FilterExpression" in tbl.query.call_args.kwargs

    def test_returns_zero_on_error(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.query.side_effect = Exception("ddb down")
        with patch.object(sc, "_table", return_value=tbl):
            assert sc.invalidate_permanent_picks() == 0


# ───────────────────────────── invalidate_today ──────────────────────────────

class TestInvalidateToday:
    def test_scans_and_batch_deletes(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.scan.return_value = {"Items": [
            {"pk": "picks", "sk": "today#2026-06-26"},
            {"pk": "performance", "sk": "summary#2026-06-26"},
        ]}
        with patch.object(sc, "_table", return_value=tbl):
            sc.invalidate_today("2026-06-26")
        assert tbl._batch.delete_item.call_count == 2

    def test_swallows_errors(self):
        import app.backend.services.serving_cache as sc
        tbl = _mock_table()
        tbl.scan.side_effect = Exception("ddb down")
        with patch.object(sc, "_table", return_value=tbl):
            sc.invalidate_today("2026-06-26")  # must not raise


# ─────────────────────── portfolios (migrated to dynamo.py) ───────────────────

class TestPortfolioDynamo:
    def test_defaults_when_unset(self):
        import app.backend.services.dynamo as dy
        tbl = MagicMock()
        tbl.get_item.return_value = {"Item": {"user_id": "u1"}}  # no portfolio attr
        with patch.object(dy, "_users_table", return_value=tbl):
            out = dy.get_user_portfolio("u1")
        assert out["user_id"] == "u1"
        assert out["min_ev_threshold"] == 0.02
        assert out["markets"] == ["h2h", "totals"]

    def test_returns_stored_merged_over_defaults(self):
        import app.backend.services.dynamo as dy
        tbl = MagicMock()
        # bankroll dropped at write time (None) — must still resolve via defaults.
        tbl.get_item.return_value = {"Item": {"portfolio": {
            "min_ev_threshold": 0.05, "markets": ["h2h"], "max_kelly_fraction": 0.1,
        }}}
        with patch.object(dy, "_users_table", return_value=tbl):
            out = dy.get_user_portfolio("u1")
        assert out["min_ev_threshold"] == 0.05
        assert out["markets"] == ["h2h"]
        assert out["bankroll"] is None  # from defaults

    def test_defaults_on_error(self):
        import app.backend.services.dynamo as dy
        tbl = MagicMock()
        tbl.get_item.side_effect = Exception("ddb down")
        with patch.object(dy, "_users_table", return_value=tbl):
            out = dy.get_user_portfolio("u1")
        assert out["max_kelly_fraction"] == 0.05

    def test_upsert_writes_portfolio_map_and_returns_prefs(self):
        import app.backend.services.dynamo as dy
        tbl = MagicMock()
        with patch.object(dy, "_users_table", return_value=tbl):
            out = dy.upsert_user_portfolio("u1", {
                "min_ev_threshold": 0.03, "markets": ["totals"],
                "bankroll": 500.0, "max_kelly_fraction": 0.08,
            })
        assert out["user_id"] == "u1"
        assert out["min_ev_threshold"] == 0.03
        assert out["bankroll"] == 500.0
        # Wrote to the `portfolio` attribute on the user item.
        call = tbl.update_item.call_args.kwargs
        assert call["Key"] == {"user_id": "u1"}
        assert call["ExpressionAttributeNames"]["#pf"] == "portfolio"
