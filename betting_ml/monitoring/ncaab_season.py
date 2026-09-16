"""NCAAB-P0 — the ONE owner of the D-I season window.

⛔ THIS MODULE IMPORTS NOTHING FROM `sports_delta_freshness`, AND THAT IS THE ENTIRE REASON IT
EXISTS. The window is needed by BOTH `ncaab_freshness` (which defines contracts, so it must
import `SportsDeltaContract`) and `sports_delta_freshness` (whose REGISTRY now carries the armed
NCAAB contracts). Having either import the other back is a cycle — measured, not feared: the
first attempt raised `cannot import name 'SEASON_MONTHS' from partially initialized module`
the moment a test imported `ncaab_freshness` first, which is what the fast gate does.

A "define it above the import so the partial module happens to have it" fix also works and is
NOT used here, deliberately: it survives only while the statement order survives, and the first
linter or editor that hoists imports to the top breaks it silently. A one-way dependency cannot
be broken by reordering.

This mirrors how NCAAF already avoids the same cycle — `ncaaf_strength_refit` owns its window
and imports nothing from the freshness registry.
"""

from __future__ import annotations

#: The D-I season window, MONTH-granular. November through April; April is in because the title
#: game falls in its first week.
#:
#: ⚠️ THE RELATIONSHIP WITH `sources.in_season()` IS CONTAINMENT, NOT EQUALITY, and writing it
#: down is the point. The ingest layer's `in_season()` is DAY-granular (April 1-10, because the
#: season really does end mid-month); `active_months` cannot express a mid-month boundary at
#: all. That is the same shape as INC-41's hour-granularity windows being unable to express a
#: 30-minute grace — the coarser instrument must be the WIDER one, or it suppresses a check on
#: a day the finer one considers live.
#:
#: So the invariant is: every month in which `in_season()` is EVER true must appear here. The
#: converse is deliberately false — this window stays open for the back half of April, when
#: `in_season()` has already closed, which costs at most a few days of a contract ageing
#: against a season that has just ended. That direction is safe; the other direction would
#: silently blind the monitor during live play. `season_month_containment_holds()` asserts it,
#: and a guard test drives it, because two owners of one boundary is this repo's documented
#: seasonal-hole class (E9.48(c) / INC-37 / NCAAF-RF1).
SEASON_MONTHS: tuple[int, ...] = (11, 12, 1, 2, 3, 4)


def season_month_containment_holds() -> tuple[bool, tuple[int, ...]]:
    """Does `SEASON_MONTHS` cover every month the ingest layer ever calls in-season?

    Returns (ok, months_missing_from_SEASON_MONTHS). Imported lazily so this module stays
    import-cheap and free of a cycle.
    """
    from datetime import date

    from quant_sports_intel_models.basketball.ncaab.ingest.sources import in_season

    # 2027 is a non-leap year; every month is probed on days 1, 15 and 28 so a mid-month
    # boundary (April 10) cannot hide between probes.
    live = {m for m in range(1, 13)
            for d in (1, 15, 28) if in_season(date(2027, m, d))}
    missing = tuple(sorted(live - set(SEASON_MONTHS)))
    return (not missing), missing
