"""test_picks_stale_slate_guard.py — /picks/today dateless-fallback date guard.

The dateless S3 blob `picks/today.json` holds the LAST-written slate. Before this guard, requesting a
date not yet in DynamoDB (e.g. 7/1 before the morning pipeline publishes) surfaced the prior slate's
games (6/30) — the "6/30 games on 7/1" bug. `_blob_matches_date` gates that fallback.
"""

from __future__ import annotations

from app.backend.routers.picks import _blob_matches_date


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
