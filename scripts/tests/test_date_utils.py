"""Unit tests for scripts/date_utils.py."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from date_utils import default_window, format_iso_utc

_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# ── format_iso_utc ─────────────────────────────────────────────────────────────

class TestFormatIsoUtc:
    def test_utc_datetime_is_unchanged(self):
        dt = datetime(2026, 4, 22, 13, 45, 30, tzinfo=timezone.utc)
        assert format_iso_utc(dt) == "2026-04-22T13:45:30Z"

    def test_non_utc_timezone_is_converted(self):
        # UTC-5 → should shift to UTC
        eastern = timezone(timedelta(hours=-5))
        dt = datetime(2026, 4, 22, 8, 0, 0, tzinfo=eastern)
        assert format_iso_utc(dt) == "2026-04-22T13:00:00Z"

    def test_naive_datetime_treated_as_utc(self):
        dt = datetime(2026, 4, 22, 0, 0, 0)
        assert format_iso_utc(dt) == "2026-04-22T00:00:00Z"

    def test_output_format_matches_iso8601(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _ISO_PATTERN.match(format_iso_utc(dt))

    def test_microseconds_are_truncated(self):
        dt = datetime(2026, 4, 22, 12, 0, 0, 999999, tzinfo=timezone.utc)
        assert format_iso_utc(dt) == "2026-04-22T12:00:00Z"

    def test_midnight_boundary(self):
        dt = datetime(2026, 4, 22, 0, 0, 0, tzinfo=timezone.utc)
        assert format_iso_utc(dt) == "2026-04-22T00:00:00Z"

    def test_end_of_day_boundary(self):
        dt = datetime(2026, 4, 22, 23, 59, 59, tzinfo=timezone.utc)
        assert format_iso_utc(dt) == "2026-04-22T23:59:59Z"


# ── default_window ─────────────────────────────────────────────────────────────

class TestDefaultWindow:
    def _anchor(self, year=2026, month=4, day=22, hour=14, minute=30):
        """A mid-day UTC anchor so the midnight truncation is clearly visible."""
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)

    def test_returns_tuple_of_two_strings(self):
        result = default_window(now=self._anchor())
        assert isinstance(result, tuple) and len(result) == 2
        assert all(isinstance(s, str) for s in result)

    def test_window_from_is_midnight_of_anchor_date(self):
        window_from, _ = default_window(now=self._anchor())
        assert window_from == "2026-04-22T00:00:00Z"

    def test_default_window_to_is_7_days_later(self):
        _, window_to = default_window(now=self._anchor())
        assert window_to == "2026-04-29T00:00:00Z"

    def test_custom_days_parameter(self):
        _, window_to = default_window(now=self._anchor(), days=14)
        assert window_to == "2026-05-06T00:00:00Z"

    def test_single_day_window(self):
        window_from, window_to = default_window(now=self._anchor(), days=1)
        assert window_from == "2026-04-22T00:00:00Z"
        assert window_to   == "2026-04-23T00:00:00Z"

    def test_both_outputs_match_iso_pattern(self):
        for s in default_window(now=self._anchor()):
            assert _ISO_PATTERN.match(s), f"{s!r} does not match ISO 8601 pattern"

    def test_both_outputs_are_at_midnight(self):
        for s in default_window(now=self._anchor()):
            assert s.endswith("T00:00:00Z"), f"{s!r} is not at midnight UTC"

    def test_anchor_with_non_utc_timezone(self):
        # UTC+9 anchor at 2026-04-23 08:00 is 2026-04-22 23:00 UTC —
        # the UTC date is the 22nd, so window_from should be 2026-04-22.
        jst = timezone(timedelta(hours=9))
        anchor = datetime(2026, 4, 23, 8, 0, 0, tzinfo=jst)
        window_from, _ = default_window(now=anchor)
        assert window_from == "2026-04-22T00:00:00Z"

    def test_window_from_before_window_to(self):
        window_from, window_to = default_window(now=self._anchor())
        assert window_from < window_to

    def test_month_rollover(self):
        anchor = datetime(2026, 1, 28, tzinfo=timezone.utc)
        window_from, window_to = default_window(now=anchor, days=7)
        assert window_from == "2026-01-28T00:00:00Z"
        assert window_to   == "2026-02-04T00:00:00Z"

    def test_year_rollover(self):
        anchor = datetime(2025, 12, 29, tzinfo=timezone.utc)
        window_from, window_to = default_window(now=anchor, days=7)
        assert window_from == "2025-12-29T00:00:00Z"
        assert window_to   == "2026-01-05T00:00:00Z"

    def test_no_now_uses_current_time(self):
        # Just verify it doesn't raise and returns ISO strings when now is omitted.
        window_from, window_to = default_window()
        assert _ISO_PATTERN.match(window_from)
        assert _ISO_PATTERN.match(window_to)
        assert window_from < window_to
