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
# E9.41 follow-up — featured "Yesterday: Pending" self-heal. A late West-coast
# game isn't in Savant/statcast when the morning serving write runs, so the
# recap freezes on 'pending'; /picks/featured re-checks the CLV mart on read
# and patches it to Won/Lost once the game settles.
# --------------------------------------------------------------------------

def _row(outcome, pick_side="home", market="h2h"):
    return {"GAME_PK": 1, "HOME_TEAM": "AZ", "AWAY_TEAM": "STL",
            "MARKET_TYPE": market, "PICK_SIDE": pick_side, "ACTUAL_OUTCOME": outcome}


def test_recap_home_pick_wins_when_home_won():
    r = _resolve_yesterday_recap(_row(1, "home"))
    assert r["status"] == "win" and r["outcome"] == "Won"


def test_recap_away_pick_wins_when_home_lost():
    # actual_outcome is home-perspective (1=home won); an away pick wins when home lost.
    r = _resolve_yesterday_recap(_row(0, "away"))
    assert r["status"] == "win" and r["outcome"] == "Won"


def test_recap_over_pick_loses_when_under():
    r = _resolve_yesterday_recap(_row(0, "over", "totals"))
    assert r["status"] == "loss" and r["outcome"] == "Lost"


def test_recap_null_outcome_is_pending():
    r = _resolve_yesterday_recap(_row(None))
    assert r["status"] == "pending" and r["outcome"] == "Pending"


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
    monkeypatch.setattr(picks_mod, "lakehouse_query", lambda *a, **k: [_row(1, "home")])
    writes = {}
    monkeypatch.setattr(picks_mod.serving_cache, "set_cache",
                        lambda key, date, payload, *a, **k: writes.update({"key": key, "payload": payload}))
    payload = {"game_pk": 1, "yesterday": {"matchup": "STL @ AZ", "status": "pending", "outcome": "Pending"}}
    out = _heal_pending_featured_yesterday(payload, "2026-07-18")
    assert out["yesterday"]["status"] == "win"
    assert payload["yesterday"]["status"] == "pending"  # original not mutated
    assert writes["key"] == "picks/featured"  # durable write-back happened


def test_heal_stays_pending_when_still_unsettled(monkeypatch):
    monkeypatch.setattr(picks_mod, "lakehouse_query", lambda *a, **k: [_row(None, "home")])
    payload = {"game_pk": 1, "yesterday": {"status": "pending", "outcome": "Pending"}}
    out = _heal_pending_featured_yesterday(payload, "2026-07-18")
    assert out["yesterday"]["status"] == "pending"


def test_heal_survives_query_failure(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("lakehouse down")
    monkeypatch.setattr(picks_mod, "lakehouse_query", _boom)
    payload = {"game_pk": 1, "yesterday": {"status": "pending", "outcome": "Pending"}}
    assert _heal_pending_featured_yesterday(payload, "2026-07-18") is payload
