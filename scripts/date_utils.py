"""
date_utils.py
-------------
Reusable UTC date/time helpers for Odds API ingestion workflows.

All functions accept an optional `now` parameter so they can be driven by a
fixed datetime in tests instead of calling datetime.now() internally.
"""

from datetime import datetime, timedelta, timezone

_ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def format_iso_utc(dt: datetime) -> str:
    """
    Format *dt* as an ISO 8601 UTC string: YYYY-MM-DDTHH:MM:SSZ.

    Works correctly for timezone-aware datetimes in any zone; naive datetimes
    are assumed to already be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(_ISO_UTC_FORMAT)


def default_window(
    now: datetime | None = None,
    days: int = 7,
) -> tuple[str, str]:
    """
    Return a ``(window_from, window_to)`` pair of ISO 8601 UTC strings.

    *window_from* is today at 00:00:00 UTC.
    *window_to*   is today + *days* at 00:00:00 UTC.

    Args:
        now:  Reference point for "today". Defaults to ``datetime.now(UTC)``.
              Pass an explicit value in tests to get deterministic output.
        days: Length of the forward-looking window in days. Default is 7.

    Returns:
        Tuple of two strings, both formatted as ``YYYY-MM-DDTHH:MM:SSZ``.

    Example::

        from datetime import datetime, timezone
        from date_utils import default_window

        anchor = datetime(2026, 4, 22, 14, 30, tzinfo=timezone.utc)
        window_from, window_to = default_window(now=anchor, days=7)
        # window_from == "2026-04-22T00:00:00Z"
        # window_to   == "2026-04-29T00:00:00Z"
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    midnight = now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return format_iso_utc(midnight), format_iso_utc(midnight + timedelta(days=days))
