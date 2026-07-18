"""test_picks_stale_slate_guard.py — /picks/today dateless-fallback date guard.

The dateless S3 blob `picks/today.json` holds the LAST-written slate. Before this guard, requesting a
date not yet in DynamoDB (e.g. 7/1 before the morning pipeline publishes) surfaced the prior slate's
games (6/30) — the "6/30 games on 7/1" bug. `_blob_matches_date` gates that fallback.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.backend.routers import picks as picks_mod
from app.backend.routers.picks import _blob_matches_date, _resolve_slate_date


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
