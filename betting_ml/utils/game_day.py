"""Canonical US baseball-day resolution (INC-22).

THE BUG THIS CURES — the production box runs in **UTC**. A naive ``date.today()`` /
``datetime.utcnow().date()`` / ``datetime.now(timezone.utc).date()`` rolls over to
*tomorrow* at 00:00 UTC, which is still the **evening of the prior day in the US**
(00:12 UTC = 7:12 pm CDT / 8:12 pm EDT / 5:12 pm PDT). Every prediction's
``game_date``, the MLB slate, and the ``mart_odds_outcomes`` ``_history``/``_current``
split are keyed to the **US baseball-day**, NOT the UTC day. So an evening / intraday
serving or predict job that derives "today" from UTC resolves *tomorrow's* (empty)
date and silently does nothing — the ``write_serving_store_intraday_op`` skip that hid
the stale 6/29 slate on 2026-06-29 (INC-22). The morning ops are only *coincidentally*
immune: they run ~13:00 UTC, still the same calendar day in UTC.

CANONICAL TZ = ``America/Los_Angeles``. Two reasons, both about making the resolved
date **JOIN** with the rest of the path:

1. It is the SAME tz ``scripts/run_w1_lakehouse._la_today`` already uses for the
   lakehouse ``_history``/``_current`` boundary (the split that owns today's odds), so
   the serving date and the odds-mart "current" bucket agree by construction.
2. It is the most-Western US tz, so it keeps "today" pinned to the slate date until the
   last West-coast night game actually finishes (~1 am PT). An Eastern tz would roll to
   tomorrow at midnight ET (= 9 pm PT) **while West-coast games are still being played**
   — and those games' ``game_date`` is still the prior day, so an ET "today" would
   break the join exactly when a live game most needs a fresh serve.

ROUTE EVERY serving / predict "today" through here so the bug can't reappear at a new
call site. (The same TZ-boundary class as INC-21 #5, the LA-vs-UTC date split.)
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# The single source of truth for "what US baseball-day is it right now".
# America/Los_Angeles — see module docstring for why this tz and not ET/UTC.
BASEBALL_DAY_TZ = ZoneInfo("America/Los_Angeles")


def current_game_date(
    now: datetime | None = None,
    tz: ZoneInfo = BASEBALL_DAY_TZ,
) -> date:
    """Today's US baseball-day as a ``date``, in the canonical TZ (default LA).

    Use this everywhere the serving / predict path needs "today" so the resolved date
    always matches the ``game_date`` that predictions and the odds marts are keyed to —
    even after the (UTC) box clock has rolled past midnight UTC. (INC-22)

    ``now`` is injectable purely for deterministic, dependency-free "freeze-time"
    tests; production always calls it with ``now=None``. A naive ``now`` is treated as
    UTC (the production box's wall clock).
    """
    if now is None:
        return datetime.now(tz).date()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(tz).date()


def current_game_date_iso(
    now: datetime | None = None,
    tz: ZoneInfo = BASEBALL_DAY_TZ,
) -> str:
    """``current_game_date()`` as a ``YYYY-MM-DD`` ISO string (the form most CLIs want)."""
    return current_game_date(now, tz).isoformat()
