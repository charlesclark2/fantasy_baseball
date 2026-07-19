"""test_picks_stale_slate_guard.py — /picks/today dateless-fallback date guard.

The dateless S3 blob `picks/today.json` holds the LAST-written slate. Before this guard, requesting a
date not yet in DynamoDB (e.g. 7/1 before the morning pipeline publishes) surfaced the prior slate's
games (6/30) — the "6/30 games on 7/1" bug. `_blob_matches_date` gates that fallback.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.backend.routers import picks as picks_mod
from app.backend.routers.picks import (
    _blob_matches_date,
    _heal_pending_featured_yesterday,
    _resolve_slate_date,
    _resolve_yesterday_recap,
)


def test_matches_when_pick_date_equals_today():
    blob = {"picks": [{"game_date": "2026-07-01", "game_pk": 1}]}
    assert _blob_matches_date(blob, "2026-07-01") is True


def test_rejects_prior_slate():
    # 6/30 blob requested as 7/1 → must NOT be used (this is the bug being fixed).
    blob = {"picks": [{"game_date": "2026-06-30", "game_pk": 1}]}
    assert _blob_matches_date(blob, "2026-07-01") is False


def test_empty_blob_is_allowed():
    # An empty slate is a valid "today has no games / not ready" state — allowed (no stale leak).
    assert _blob_matches_date({"picks": []}, "2026-07-01") is True
    assert _blob_matches_date({}, "2026-07-01") is True


def test_matches_when_any_pick_is_today():
    blob = {"picks": [{"game_date": "2026-06-30"}, {"game_date": "2026-07-01"}]}
    assert _blob_matches_date(blob, "2026-07-01") is True


def test_datetime_prefix_match():
    # game_date may carry a time suffix; prefix match still holds.
    blob = {"picks": [{"game_date": "2026-07-01T23:05:00Z"}]}
    assert _blob_matches_date(blob, "2026-07-01") is True


# --------------------------------------------------------------------------
# E9.41 — _resolve_slate_date future-clamp (the "tomorrow's games" bug).
# A client that computes "today" from new Date() (browser-local tz) can be a
# calendar day AHEAD of the US baseball day → tomorrow's already-posted slate
# would bleed in. A future date must clamp to the canonical game-date.
# --------------------------------------------------------------------------

@pytest.fixture
def pinned_today(monkeypatch):
    monkeypatch.setattr(picks_mod, "current_game_date_iso", lambda: "2026-07-17")
    return "2026-07-17"


def test_future_date_clamps_to_today(pinned_today):
    # Tomorrow's slate requested (ahead-of-US client clock) → clamp to today.
    assert _resolve_slate_date("2026-07-18") == "2026-07-17"


def test_none_resolves_to_canonical_today(pinned_today):
    assert _resolve_slate_date(None) == "2026-07-17"
    assert _resolve_slate_date("") == "2026-07-17"


def test_today_passes_through(pinned_today):
    assert _resolve_slate_date("2026-07-17") == "2026-07-17"


def test_past_date_passes_through(pinned_today):
    # Legitimate historical lookup — must NOT be clamped.
    assert _resolve_slate_date("2026-07-10") == "2026-07-10"


def test_invalid_format_rejected(pinned_today):
    with pytest.raises(HTTPException):
        _resolve_slate_date("07/18/2026")


# --------------------------------------------------------------------------
# E9.41 follow-up — featured "Yesterday: Pending" self-heal. The recap outcome is
# computed from the FRESH mart_game_results final score (2026-07-19: the CLV mirror
# it used to read lagged a full day → SF/SEA stuck 'pending' though mart_game_results
# already had the 4-3 Final). /picks/featured re-checks on read and patches Won/Lost.
# --------------------------------------------------------------------------

def _h2h_row(home_won, pick_side="home"):
    return {"GAME_PK": 1, "HOME_TEAM": "SEA", "AWAY_TEAM": "SF", "MARKET_TYPE": "h2h",
            "PICK_SIDE": pick_side, "HOME_TEAM_WON": home_won,
            "HOME_FINAL_SCORE": 4 if home_won else 3,
            "AWAY_FINAL_SCORE": 3 if home_won else 4, "TOTAL_LINE": None}


def _totals_row(home_score, away_score, total_line, pick_side="over"):
    return {"GAME_PK": 1, "HOME_TEAM": "SEA", "AWAY_TEAM": "SF", "MARKET_TYPE": "totals",
            "PICK_SIDE": pick_side, "HOME_TEAM_WON": None,
            "HOME_FINAL_SCORE": home_score, "AWAY_FINAL_SCORE": away_score, "TOTAL_LINE": total_line}


def test_recap_home_pick_wins_when_home_won():
    r = _resolve_yesterday_recap(_h2h_row(True, "home"))
    assert r["status"] == "win" and r["outcome"] == "Won"


def test_recap_away_pick_wins_when_home_lost():
    r = _resolve_yesterday_recap(_h2h_row(False, "away"))
    assert r["status"] == "win" and r["outcome"] == "Won"


def test_recap_home_pick_loses_when_home_lost():
    r = _resolve_yesterday_recap(_h2h_row(False, "home"))
    assert r["status"] == "loss" and r["outcome"] == "Lost"


def test_recap_totals_sfsea_real_case_over_wins():
    # The actual 2026-07-19 case: SF/SEA totals OVER, line 6.78, final 4-3 = 7 runs > line → Won.
    r = _resolve_yesterday_recap(_totals_row(4, 3, 6.78, "over"))
    assert r["status"] == "win" and r["outcome"] == "Won"
    assert r["matchup"] == "SF @ SEA"


def test_recap_over_pick_loses_when_under():
    r = _resolve_yesterday_recap(_totals_row(2, 3, 6.5, "over"))  # 5 < 6.5
    assert r["status"] == "loss" and r["outcome"] == "Lost"


def test_recap_under_pick_wins_when_under():
    r = _resolve_yesterday_recap(_totals_row(2, 3, 6.5, "under"))  # 5 < 6.5 → under hits
    assert r["status"] == "win" and r["outcome"] == "Won"


def test_recap_pending_when_score_or_line_missing():
    # h2h with no result yet, and totals with no line → can't settle → pending (never a guess).
    assert _resolve_yesterday_recap(_h2h_row(None))["status"] == "pending"
    assert _resolve_yesterday_recap(_totals_row(4, 3, None, "over"))["status"] == "pending"


def test_heal_noop_when_not_pending(monkeypatch):
    calls = []
    monkeypatch.setattr(picks_mod, "lakehouse_query", lambda *a, **k: calls.append(1) or [])
    payload = {"game_pk": 1, "yesterday": {"status": "win", "outcome": "Won"}}
    assert _heal_pending_featured_yesterday(payload, "2026-07-18") is payload
    assert calls == []  # no query when already settled


def test_heal_noop_when_no_yesterday(monkeypatch):
    calls = []
    monkeypatch.setattr(picks_mod, "lakehouse_query", lambda *a, **k: calls.append(1) or [])
    payload = {"game_pk": 1, "yesterday": None}
    assert _heal_pending_featured_yesterday(payload, "2026-07-18") is payload
    assert calls == []


def test_heal_patches_settled_and_writes_back(monkeypatch):
    monkeypatch.setattr(picks_mod, "lakehouse_query", lambda *a, **k: [_h2h_row(True, "home")])
    writes = {}
    monkeypatch.setattr(picks_mod.serving_cache, "set_cache",
                        lambda key, date, payload, *a, **k: writes.update({"key": key, "payload": payload}))
    payload = {"game_pk": 1, "yesterday": {"matchup": "SF @ SEA", "status": "pending", "outcome": "Pending"}}
    out = _heal_pending_featured_yesterday(payload, "2026-07-18")
    assert out["yesterday"]["status"] == "win"
    assert payload["yesterday"]["status"] == "pending"  # original not mutated
    assert writes["key"] == "picks/featured"  # durable write-back happened


def test_heal_stays_pending_when_still_unsettled(monkeypatch):
    # Game not final in mart_game_results yet (heal query returns no row) → stays pending.
    monkeypatch.setattr(picks_mod, "lakehouse_query", lambda *a, **k: [])
    payload = {"game_pk": 1, "yesterday": {"status": "pending", "outcome": "Pending"}}
    out = _heal_pending_featured_yesterday(payload, "2026-07-18")
    assert out["yesterday"]["status"] == "pending"


def test_heal_survives_query_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("lakehouse down")
    monkeypatch.setattr(picks_mod, "lakehouse_query", _boom)
    payload = {"game_pk": 1, "yesterday": {"status": "pending", "outcome": "Pending"}}
    assert _heal_pending_featured_yesterday(payload, "2026-07-18") is payload
