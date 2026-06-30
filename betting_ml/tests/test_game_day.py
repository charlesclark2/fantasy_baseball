"""INC-22 recurrence guard — the serving/predict "today" must resolve to the US
baseball-day across the UTC-midnight boundary, NOT the UTC box clock.

The bug (2026-06-29 ~00:12 UTC): the EVENING intraday serving write derived "today"
from a UTC-keyed `date.today()` on the UTC production box → resolved 2026-06-30 while
the live slate was 6/29 → "No predictions for 2026-06-30" → silent skip → stale slate.

These tests are dependency-free "freeze-time" tests: `current_game_date` accepts an
injectable `now`, so we freeze the clock by passing a fixed UTC instant. (No freezegun.)
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from betting_ml.utils.game_day import (
    BASEBALL_DAY_TZ,
    current_game_date,
    current_game_date_iso,
)

_ET = ZoneInfo("America/New_York")


def test_canonical_tz_is_los_angeles():
    """LA is the canonical baseball-day tz (matches run_w1_lakehouse._la_today + the
    mart_odds_outcomes _history/_current split)."""
    assert str(BASEBALL_DAY_TZ) == "America/Los_Angeles"


def test_incident_0030_utc_resolves_to_us_baseball_day():
    """THE regression guard. 00:30 UTC on 6/30 == the evening of 6/29 in the US.
    The serving date MUST be 6/29 (the live slate), NOT 6/30."""
    incident_now = datetime(2026, 6, 30, 0, 30, tzinfo=timezone.utc)

    # The OLD naive-UTC behavior — encoded here so the bug can't silently come back.
    assert incident_now.date() == date(2026, 6, 30)  # what the buggy code resolved

    # The FIX.
    assert current_game_date(incident_now) == date(2026, 6, 29)
    assert current_game_date_iso(incident_now) == "2026-06-29"


def test_west_coast_game_in_progress_stays_on_slate_day():
    """06:00 UTC == 11:00 pm PDT on 6/29 — a West-coast night game is still being played
    and its game_date is 6/29. LA keeps "today" = 6/29; an Eastern tz would already be on
    6/30 (it is 2 am ET) and break the join. This is WHY the canonical tz is LA, not ET."""
    now = datetime(2026, 6, 30, 6, 0, tzinfo=timezone.utc)
    assert current_game_date(now) == date(2026, 6, 29)            # LA — correct
    assert current_game_date(now, tz=_ET) == date(2026, 6, 30)    # ET — would be wrong


def test_morning_op_is_unchanged_no_regression():
    """The morning daily op runs ~13:00 UTC (= 6 am PDT / 9 am EDT 6/29). It was always
    correct; the fix must not change it."""
    now = datetime(2026, 6, 29, 13, 0, tzinfo=timezone.utc)
    assert current_game_date(now) == date(2026, 6, 29)


def test_rolls_over_after_la_midnight():
    """07:30 UTC == 12:30 am PDT on 6/30 — past LA midnight, the slate has flipped, so
    "today" correctly becomes 6/30."""
    now = datetime(2026, 6, 30, 7, 30, tzinfo=timezone.utc)
    assert current_game_date(now) == date(2026, 6, 30)


def test_naive_now_is_treated_as_utc():
    """The production box clock is UTC; a naive datetime is interpreted as UTC."""
    naive = datetime(2026, 6, 30, 0, 30)  # no tzinfo
    assert current_game_date(naive) == date(2026, 6, 29)


def test_default_now_returns_a_date():
    """Smoke: with now=None (production), it returns a real date in the canonical tz."""
    assert isinstance(current_game_date(), date)
    iso = current_game_date_iso()
    assert isinstance(iso, str) and len(iso) == 10 and iso[4] == "-"
