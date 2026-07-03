"""Guards the sensor first-pitch coercion (INC-23 recurrence, 2026-07-03).

The lakehouse stores TIMESTAMP columns as ISO VARCHAR, so a DuckDB ``MIN(game_date)`` returns a
**str**. `odds_current_rebuild_sensor`, `pregame_alert_sensor`, and `conviction_pick_alert_sensor`
called ``.astimezone()`` / ``.tzinfo`` on that str → ``AttributeError`` → every tick fail-opened to
SkipReason → served odds froze for 3 days with no alert. `betting_ml.utils.lakehouse_monitor.to_utc_datetime`
is the single coercion all sensors now route through; this locks in that it accepts the str the
lakehouse actually returns (the exact regression) plus the datetime cases.
"""
from datetime import datetime, timezone

from betting_ml.utils.lakehouse_monitor import to_utc_datetime


def test_iso_string_with_trailing_z():
    """The exact lakehouse return value that broke the sensors."""
    got = to_utc_datetime("2026-07-03T22:40:00Z")
    assert got == datetime(2026, 7, 3, 22, 40, tzinfo=timezone.utc)
    assert got.tzinfo is not None


def test_iso_string_without_timezone_assumed_utc():
    got = to_utc_datetime("2026-07-03T17:05:00")
    assert got == datetime(2026, 7, 3, 17, 5, tzinfo=timezone.utc)


def test_iso_string_with_offset_normalized_to_utc():
    got = to_utc_datetime("2026-07-03T18:40:00-04:00")  # 6:40pm EDT → 22:40 UTC
    assert got == datetime(2026, 7, 3, 22, 40, tzinfo=timezone.utc)


def test_naive_datetime_assumed_utc():
    got = to_utc_datetime(datetime(2026, 7, 3, 22, 40))
    assert got == datetime(2026, 7, 3, 22, 40, tzinfo=timezone.utc)


def test_aware_datetime_converted_to_utc():
    from zoneinfo import ZoneInfo

    got = to_utc_datetime(datetime(2026, 7, 3, 18, 40, tzinfo=ZoneInfo("America/New_York")))
    assert got == datetime(2026, 7, 3, 22, 40, tzinfo=timezone.utc)


def test_none_passthrough():
    assert to_utc_datetime(None) is None


def test_result_is_arithmetic_safe():
    """The downstream use: subtracting from a tz-aware 'now' must not raise (the original crash was
    upstream, but this proves the return type supports the window math the sensors do)."""
    now = datetime(2026, 7, 3, 20, 0, tzinfo=timezone.utc)
    fp = to_utc_datetime("2026-07-03T22:40:00Z")
    assert (fp - now).total_seconds() == 2 * 3600 + 40 * 60
